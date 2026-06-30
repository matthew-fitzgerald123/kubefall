"""The three battle types, with two kubefall-specific extensions.

RECALL  - timed retrieval. A short prompt with a visible countdown. The player
          types the answer into the game and the timer is the grader. This is
          the primary drill, and items come from the SM-2 queue, not in order.
          The matcher is kubectl-aware: for a `kubectl ...` answer it treats
          resource short-names, singular/plural, and the -n/--namespace flag
          forms as equivalent, without ever collapsing distinct resources.
VILLAGER - teaching. An NPC delivers lore and every taught command is quizzed
          before letting the player pass. Iterates `quizzes` (list) not a
          single quiz dict.
SOLVE   - two flavors:
          * dry-run verified (creation zones). The player types a kubectl
            create-style command into the game; kubefall appends
            `--dry-run=client -o yaml` and runs it. kubectl validates the
            command with no cluster and the generated manifest is shown as
            feedback. If kubectl is absent, this falls back to honor-system.
          * honor system (debugging and triage zones). The game states a
            read-verb investigation or a reasoning chain; the player self-reports.
            Read verbs (get, describe, logs, exec) are never dry-run validated.

Every battle feeds the spaced-repetition scheduler that lives in meta state.
"""

import re
import select
import shlex
import shutil
import subprocess
import sys
import time

# Outcome dicts use these keys: "correct" (bool) and "damage" (int).

# A bare bundle of short flags: a single dash followed only by ASCII letters,
# such as -l, -tulpn, or -nn. Tokens with digits (-9, -15), long flags
# (--recursive), flags carrying a value (-d:), or anything else are NOT bundles
# and stay as ordinary tokens.
_SHORT_FLAG = re.compile(r"-[A-Za-z]+")
_QUOTES = "\"'"

# kubectl resource short-name and singular/plural equivalence. Each alias maps to
# a canonical resource name. Only forms of the SAME resource share a canonical,
# so pods, deployments, and services stay distinct: pod != deployment != service.
# Applied only when the command starts with `kubectl`, so non-kubectl answers are
# left exactly as rootfall handled them.
_RESOURCE_ALIASES = {
    "po": "pod", "pod": "pod", "pods": "pod",
    "deploy": "deployment", "deployment": "deployment", "deployments": "deployment",
    "svc": "service", "service": "service", "services": "service",
    "cm": "configmap", "configmap": "configmap", "configmaps": "configmap",
    "ns": "namespace", "namespace": "namespace", "namespaces": "namespace",
    "rs": "replicaset", "replicaset": "replicaset", "replicasets": "replicaset",
    "no": "node", "node": "node", "nodes": "node",
    "sa": "serviceaccount", "serviceaccount": "serviceaccount", "serviceaccounts": "serviceaccount",
    "rc": "replicationcontroller", "replicationcontroller": "replicationcontroller",
    "secret": "secret", "secrets": "secret",
    "role": "role", "roles": "role",
    "rolebinding": "rolebinding", "rolebindings": "rolebinding",
}

# Read verbs that --dry-run=client cannot validate. A solve must never run a
# `kubectl get` (or describe/logs/exec) under dry-run, so if one of these is
# submitted to a dry-run solve we drop to honor-system reporting instead.
_READ_VERBS = frozenset([
    "get", "describe", "logs", "exec", "top", "events",
    "explain", "api-resources", "cluster-info", "auth", "port-forward",
])

# Verbs that --dry-run=client can meaningfully validate (imperative create-style).
_CREATE_VERBS = frozenset(["create", "run", "expose", "apply", "set", "scale", "autoscale"])

# kubectl global flags that take a value as the following token. Skipped, with
# their value, when scanning for the verb so `kubectl -n web get pods` reads the
# verb as `get`, not the namespace value `web`.
_VALUE_FLAGS_BEFORE_VERB = frozenset([
    "-n", "--namespace", "--context", "--cluster", "--user",
    "--kubeconfig", "-s", "--server", "--as", "--token",
    "--request-timeout", "--cache-dir",
])


def _tokenize(text):
    """Split into shell-like tokens, keeping quoted spans whole."""
    tokens = []
    current = []
    quote = None
    for ch in text:
        if quote is None:
            if ch.isspace():
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                if ch in _QUOTES:
                    quote = ch
                current.append(ch)
        else:
            current.append(ch)
            if ch == quote:
                quote = None
    if current:
        tokens.append("".join(current))
    return tokens


def _strip_quotes(token):
    """Strip one matched surrounding quote pair, but only when it is safe."""
    if len(token) >= 2 and token[0] in _QUOTES and token[-1] == token[0]:
        inner = token[1:-1]
        if token[0] not in inner and not any(ch.isspace() for ch in inner):
            return inner
    return token


def _normalize_kubectl(tokens):
    """Fold kubectl resource aliases and namespace flag forms to a canonical form."""
    out = []
    for token in tokens:
        lower = token.lower()
        if token in ("-n", "--namespace"):
            out.append("--namespace")
            continue
        if lower.startswith("--namespace=") or lower.startswith("-n="):
            out.append("--namespace")
            out.append(token.split("=", 1)[1])
            continue
        if not token.startswith("-") and lower in _RESOURCE_ALIASES:
            out.append(_RESOURCE_ALIASES[lower])
            continue
        out.append(token)
    return out


def _canonical(text):
    """Reduce a command answer to a form that ignores only safe differences."""
    raw_tokens = [_strip_quotes(token) for token in _tokenize(text)]
    if raw_tokens and raw_tokens[0].lower() == "kubectl":
        raw_tokens = _normalize_kubectl(raw_tokens)
    flags = []
    words = []
    for token in raw_tokens:
        if _SHORT_FLAG.fullmatch(token):
            flags.extend(token[1:])
        else:
            words.append(token.lower())
    return tuple(words), tuple(sorted(flags))


def matches(answer, accepted):
    """True if answer is equivalent to any accepted option."""
    if answer is None:
        return False
    target = _canonical(answer)
    return any(target == _canonical(option) for option in accepted)


# ---------------------------------------------------------------------------
# Stdin drain (prevents desync after a timeout)
# ---------------------------------------------------------------------------

# Set to True when timed_input times out so the next call drains any
# buffered keystrokes the player typed after the timeout fired.
_pending_drain = False


def _drain_stdin(timeout=0.0):
    """Discard any data waiting in stdin."""
    try:
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if not ready:
                break
            line = sys.stdin.readline()
            if not line:
                break
    except (OSError, ValueError):
        pass


def _read_timed(time_limit):
    """Read one line from stdin with a hard timeout. Returns (answer, elapsed, timed_out).

    Does NOT print anything. Handles the pending-drain logic to prevent
    answer desync after a timeout.
    """
    global _pending_drain
    if _pending_drain:
        _drain_stdin(timeout=0.2)
        _pending_drain = False

    start = time.time()
    try:
        ready, _, _ = select.select([sys.stdin], [], [], time_limit)
    except (OSError, ValueError):
        line = sys.stdin.readline()
        elapsed = time.time() - start
        return (None, elapsed, False) if line == "" else (line.strip(), elapsed, False)

    if ready:
        line = sys.stdin.readline()
        elapsed = time.time() - start
        if line == "":
            return None, elapsed, True
        return line.strip(), elapsed, False

    _pending_drain = True
    return None, time.time() - start, True


def timed_input(prompt, time_limit):
    """Read a line, printing prompt and timeout message (plain-text path).

    Returns (answer, elapsed, timed_out).
    """
    sys.stdout.write(prompt + "\n> ")
    sys.stdout.flush()
    answer, elapsed, timed_out = _read_timed(time_limit)
    if timed_out:
        sys.stdout.write("\n... time!\n")
        sys.stdout.flush()
    return answer, elapsed, timed_out


# --- RECALL ----------------------------------------------------------------

def recall_battle(scheduler, encounter, miss_damage=3,
                  screen=None, zone_id=None, hp=0, max_hp=20):
    """Timed retrieval drill graded by the countdown."""
    accepted = encounter["answers"]
    key = encounter.get("key") or accepted[0]
    limit = int(encounter.get("time_limit", 8))

    scheduler.ensure(key, encounter["prompt"], accepted[0])

    if screen:
        screen.battle_prompt(zone_id, encounter, hp, max_hp)
        answer, elapsed, timed_out = _read_timed(limit)
    else:
        print()
        print("  -- RECALL --")
        banner = "  {} ({} seconds)".format(encounter["prompt"], limit)
        answer, elapsed, timed_out = timed_input(banner, limit)

    correct = (not timed_out) and matches(answer, accepted)
    scheduler.record(key, correct, elapsed, limit)

    if screen:
        screen.battle_result(zone_id, encounter, hp, max_hp,
                             correct, timed_out, accepted[0])
    else:
        if correct:
            print("  Hit. {:.1f}s.".format(elapsed))
        elif timed_out:
            print("  Too slow. The rune was: {}".format(accepted[0]))
        else:
            print("  Miss. The rune was: {}".format(accepted[0]))

    return {"correct": correct, "damage": 0 if correct else miss_damage}


# --- SOLVE -----------------------------------------------------------------

def solve_battle(scheduler, encounter, world_root="world", miss_damage=5,
                 screen=None, zone_id=None, hp=0, max_hp=20):
    """Dispatch a solve to the dry-run-verified path or the honor-system path."""
    if encounter.get("verify") == "dry-run":
        return _solve_dry_run(scheduler, encounter, miss_damage,
                              screen=screen, zone_id=zone_id, hp=hp, max_hp=max_hp)
    return _solve_honor(scheduler, encounter, world_root, miss_damage,
                        screen=screen, zone_id=zone_id, hp=hp, max_hp=max_hp)


def _solve_honor(scheduler, encounter, world_root, miss_damage,
                 screen=None, zone_id=None, hp=0, max_hp=20):
    """Honor-system battle: loops until the player self-reports success."""
    key = encounter.get("key") or "solve"
    objective = encounter["objective"]

    scheduler.ensure(key, objective, encounter.get("hint", ""))

    penalty_dealt = False
    while True:
        if screen:
            screen.solve_prompt(zone_id, encounter, hp, max_hp)
        else:
            print()
            print("  -- SOLVE (honor system) --")
            print("  " + objective)
            if encounter.get("hint"):
                print("  Hint: " + encounter["hint"])
            if encounter.get("fixture"):
                print("  Reference capture: {}/{}".format(world_root, encounter["fixture"]))
            print("  State or run the investigation, then report honestly.")

        _prompt("  Press Enter when you have worked it through... ")
        reported = _yes_no("  Did you reach the right answer?")

        if reported:
            scheduler.record(key, True, 0.0, 0)
            if screen:
                screen.solve_result(zone_id, encounter, hp, max_hp, True)
            else:
                print("  The gate swings open.")
            return {"correct": True, "damage": miss_damage if penalty_dealt else 0}

        if not penalty_dealt:
            penalty_dealt = True
        scheduler.record(key, False, 0.0, 0)
        if screen:
            screen.solve_result(zone_id, encounter, hp, max_hp, False)
        else:
            print("  The gate holds. Regroup and walk the chain again.")


def _solve_dry_run(scheduler, encounter, miss_damage,
                   screen=None, zone_id=None, hp=0, max_hp=20):
    """Verify a kubectl command with --dry-run=client. Loops until the command passes."""
    key = encounter.get("key") or "solve"
    objective = encounter["objective"]

    scheduler.ensure(key, objective, encounter.get("hint", ""))

    if shutil.which("kubectl") is None:
        print("  kubectl is not on PATH, so this solve cannot be verified.")
        print("  Install it with: brew install kubernetes-cli")
        return _report_fallback(scheduler, key, miss_damage,
                                screen=screen, zone_id=zone_id,
                                encounter=encounter, hp=hp, max_hp=max_hp)

    penalty_dealt = False
    while True:
        if screen:
            screen.solve_prompt(zone_id, encounter, hp, max_hp)
        else:
            print()
            print("  -- SOLVE (dry-run verified) --")
            print("  " + objective)
            if encounter.get("hint"):
                print("  Hint: " + encounter["hint"])

        command = _prompt("  Type your kubectl command:\n  > ").strip()
        if not command:
            continue

        verb = _kubectl_verb(command)
        if verb in _READ_VERBS:
            msg = "  '{}' is a read verb -- this solve needs a creation command.".format(verb)
            if not screen:
                print(msg)
            else:
                screen.solve_result(zone_id, encounter, hp, max_hp, False, msg)
            if not penalty_dealt:
                penalty_dealt = True
            continue

        status, output = _run_dry_run(command)

        if status == "pass":
            if not screen:
                print("  kubectl accepted it. Generated manifest:")
                print()
                preview_lines = (output or "").rstrip("\n").splitlines()[:8]
                for line in preview_lines:
                    print("    " + line)
                if len((output or "").splitlines()) > 8:
                    print("    ... (truncated)")
            scheduler.record(key, True, 0.0, 0)
            if screen:
                screen.solve_result(zone_id, encounter, hp, max_hp, True, output)
            return {"correct": True, "damage": miss_damage if penalty_dealt else 0}

        # Both "fail" and "unverifiable" stay in the loop -- never kick out to honor system.
        # "unverifiable" means kubectl needs a cluster; the player should try a different
        # command form (e.g. kubectl create instead of kubectl run on older kubectl).
        if not penalty_dealt:
            penalty_dealt = True
        scheduler.record(key, False, 0.0, 0)
        if status == "unverifiable":
            err_msg = (
                "  kubectl needs a live cluster to validate this command.\n"
                "  Try a creation command that works offline, e.g.:\n"
                "    kubectl create deployment <name> --image=<image>\n"
                "    kubectl create namespace <name>"
            )
            if screen:
                screen.solve_result(zone_id, encounter, hp, max_hp, False, err_msg)
            else:
                print(err_msg)
        else:
            if screen:
                screen.solve_result(zone_id, encounter, hp, max_hp, False, output)
            else:
                print("  kubectl rejected it:")
                print(_indent(output or "(no error output)"))
                print("  Try again.")


def _kubectl_verb(command):
    """The verb of a kubectl command: the first non-flag token after `kubectl`."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if tokens and tokens[0].lower() == "kubectl":
        tokens = tokens[1:]
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            if token in _VALUE_FLAGS_BEFORE_VERB:
                skip_next = True
            continue
        return token.lower()
    return ""


_NO_CLUSTER_MARKERS = (
    "connection refused",
    "couldn't get current server api group list",
    "the connection to the server",
    "unable to connect to the server",
    "no configuration has been provided",
    "dial tcp",
    "i/o timeout",
)


def _looks_like_no_cluster(text):
    low = (text or "").lower()
    return any(marker in low for marker in _NO_CLUSTER_MARKERS)


def _run_dry_run(command):
    """Run command + `--dry-run=client -o yaml`. Returns (status, output)."""
    try:
        argv = shlex.split(command)
    except ValueError as error:
        return "fail", "could not parse the command: {}".format(error)

    if not argv:
        return "fail", "empty command"
    if argv[0].lower() != "kubectl":
        argv = ["kubectl"] + argv

    argv = argv + ["--dry-run=client", "-o", "yaml"]
    try:
        result = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=15,
        )
    except FileNotFoundError:
        return "unverifiable", "kubectl not found"
    except subprocess.TimeoutExpired:
        return "unverifiable", "kubectl timed out"
    except OSError as error:
        return "unverifiable", "could not run kubectl: {}".format(error)

    if result.returncode == 0 and result.stdout.strip():
        return "pass", result.stdout

    error_text = result.stderr or result.stdout
    if _looks_like_no_cluster(error_text):
        return "unverifiable", error_text
    return "fail", error_text


def _report_fallback(scheduler, key, miss_damage,
                     screen=None, zone_id=None, encounter=None, hp=0, max_hp=20):
    """Honor-system fallback used when a dry-run solve cannot be verified. Loops until success."""
    penalty_dealt = False
    while True:
        if screen and encounter is not None:
            screen.solve_prompt(zone_id, encounter, hp, max_hp)
        _prompt("  Run the correct command in your terminal, then press Enter... ")
        reported = _yes_no("  Did it work?")
        if reported:
            scheduler.record(key, True, 0.0, 0)
            if screen and encounter is not None:
                screen.solve_result(zone_id, encounter, hp, max_hp, True)
            else:
                print("  The gate swings open.")
            return {"correct": True, "damage": miss_damage if penalty_dealt else 0}
        if not penalty_dealt:
            penalty_dealt = True
        scheduler.record(key, False, 0.0, 0)
        if screen and encounter is not None:
            screen.solve_result(zone_id, encounter, hp, max_hp, False)
        else:
            print("  The gate holds. Try again.")


def _indent(text, prefix="    "):
    return "\n".join(prefix + line for line in text.rstrip("\n").splitlines())


# --- VILLAGER --------------------------------------------------------------

def villager_battle(scheduler, encounter, compressed=False, miss_damage=1,
                    screen=None, zone_id=None):
    """Teaching NPC that quiz-gates on every taught command before letting the player pass."""
    if compressed:
        if not _yes_no("  You have met this villager before. Hear the lore again?",
                       default=False):
            for rune in encounter.get("teaches", []):
                scheduler.ensure(rune["command"], rune.get("desc", ""), rune["command"])
            if screen:
                screen.clear()
            print("  You nod and walk past.")
            return {"correct": True, "damage": 0}

    if screen:
        screen.villager_lore(zone_id, encounter)
    else:
        print()
        print("  -- VILLAGER: {} --".format(encounter["name"]))
        print("  " + encounter["lore"])
        print()
        for rune in encounter.get("teaches", []):
            print("    rune {:<28} {}".format(rune["command"], rune.get("desc", "")))
        print()

    quizzes = encounter.get("quizzes", [])
    total_wrong = 0

    for idx, quiz_item in enumerate(quizzes):
        wrong_attempts = 0
        while True:
            if screen:
                screen.villager_quiz(zone_id, encounter, quiz_item,
                                     idx, len(quizzes), wrong_attempts)
                answer = _prompt("")
            else:
                answer = _prompt("  {}\n  > ".format(quiz_item["prompt"]))

            if matches(answer, quiz_item["answers"]):
                if screen:
                    screen.villager_quiz_result(zone_id, encounter, quiz_item,
                                                idx, len(quizzes), correct=True)
                else:
                    print("  Correct. The road opens.")
                break

            wrong_attempts += 1
            total_wrong += 1
            if screen:
                screen.villager_quiz_result(zone_id, encounter, quiz_item,
                                            idx, len(quizzes), correct=False)
            else:
                print("  Not quite. The villager waits.")

    for rune in encounter.get("teaches", []):
        scheduler.seed(rune["command"], rune.get("desc", ""), rune["command"])

    return {"correct": True, "damage": min(total_wrong, 3) * miss_damage}


# --- small IO helpers ------------------------------------------------------

def _prompt(text):
    try:
        return input(text)
    except EOFError:
        return ""


def _yes_no(question, default=True):
    suffix = " [Y/n] " if default else " [y/N] "
    answer = _prompt(question + suffix).strip().lower()
    if not answer:
        return default
    return answer.startswith("y")
