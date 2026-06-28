"""The three battle types, with two kubefall-specific extensions.

RECALL  - timed retrieval. A short prompt with a visible countdown. The player
          types the answer into the game and the timer is the grader. This is
          the primary drill, and items come from the SM-2 queue, not in order.
          The matcher is kubectl-aware: for a `kubectl ...` answer it treats
          resource short-names, singular/plural, and the -n/--namespace flag
          forms as equivalent, without ever collapsing distinct resources.
VILLAGER - teaching. An NPC delivers lore and the command or flag, then quiz
          gates the player before letting them pass, so recognition cannot
          masquerade as recall.
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
    "rc": "replicationcontroller", "replicationcontroller": "replicationcontroller",
    "secret": "secret", "secrets": "secret",
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
    """Split into shell-like tokens, keeping quoted spans whole.

    Whitespace separates tokens, except whitespace inside a quoted span, which
    stays part of that single token. This is what guarantees token boundaries:
    a one-argument "foo bar" comes back as one token, never two. Quote
    characters are kept on the token here; stripping happens in _strip_quotes.
    An unterminated quote is treated literally, so the opening quote just rides
    along on the token and nothing is merged or split unexpectedly.
    """
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
    """Strip one matched surrounding quote pair, but only when it is safe.

    Stripped only when the same quote character wraps both ends and the inner
    span has no whitespace, so "config.yaml" becomes config.yaml. A quoted span
    that contains whitespace keeps its quotes, so "foo bar" stays a single
    distinct token and never looks like the two tokens foo bar. Mismatched or
    internal quotes are left untouched.
    """
    if len(token) >= 2 and token[0] in _QUOTES and token[-1] == token[0]:
        inner = token[1:-1]
        if token[0] not in inner and not any(ch.isspace() for ch in inner):
            return inner
    return token


def _normalize_kubectl(tokens):
    """Fold kubectl resource aliases and namespace flag forms to a canonical form.

    Only ever called for a command whose first token is `kubectl`, so it cannot
    affect any non-kubectl answer. Two normalizations happen here:

      - Resource equivalence: a plain-word token that names a resource is mapped
        to that resource's canonical name (po, pods -> pod). Different resources
        map to different canonicals, so they never collapse together.
      - Namespace flag: `-n` and `--namespace` (including the `=value` forms) are
        rewritten to a single `--namespace` word so `-n web` and `--namespace web`
        grade identically. Doing this here, scoped to kubectl, is why it does not
        disturb `grep -n` or `head -n`, where -n is a different flag entirely.
    """
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
    """Reduce a command answer to a form that ignores only safe differences.

    Ignored (safe): surrounding and repeated whitespace; the order of short
    flags; whether short flags are bundled (-tulpn) or separated (-t -u -l);
    surrounding matched quotes around a whitespace-free argument; and, for a
    `kubectl` answer only, resource short-name and singular/plural spelling plus
    the -n/--namespace flag form.

    NOT ignored (would change meaning): the exact multiset of flag letters, so
    -tulpn differs from -tuln; the case of flag letters, so ls -R differs from
    ls -r; token boundaries, so a quoted "foo bar" never equals two arguments;
    distinct kubectl resources, so pods never equals deployments; and every other
    non-flag token. Non-flag words are lowercased for command-name forgiveness,
    matching the original behavior.
    """
    raw_tokens = [_strip_quotes(token) for token in _tokenize(text)]
    if raw_tokens and raw_tokens[0].lower() == "kubectl":
        raw_tokens = _normalize_kubectl(raw_tokens)
    flags = []
    words = []
    for token in raw_tokens:
        if _SHORT_FLAG.fullmatch(token):
            flags.extend(token[1:])  # the letters only, case preserved
        else:
            words.append(token.lower())
    return tuple(words), tuple(sorted(flags))


def matches(answer, accepted):
    """True if answer is equivalent to any accepted option.

    Equivalence is deliberately narrow: flag order, flag bundling, whitespace,
    and (for kubectl) resource short-names and namespace flag form. A missing
    flag, a wrong flag, a different flag case, a different argument, or a
    different resource all fail. See _canonical for the exact contract.
    """
    if answer is None:
        return False
    target = _canonical(answer)
    return any(target == _canonical(option) for option in accepted)


def timed_input(prompt, time_limit):
    """Read a line, but give up after time_limit seconds.

    Returns (answer, elapsed, timed_out). On timeout or end of input the answer
    is None. Uses select so a real terminal gets a hard cutoff; if select is not
    available (an unusual stdin) it falls back to an untimed read.
    """
    sys.stdout.write(prompt + "\n> ")
    sys.stdout.flush()
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

    sys.stdout.write("\n... time!\n")
    return None, time.time() - start, True


# --- RECALL ----------------------------------------------------------------

def recall_battle(scheduler, encounter, miss_damage=3):
    """Timed retrieval drill graded by the countdown."""
    accepted = encounter["answers"]
    key = encounter.get("key") or accepted[0]
    limit = int(encounter.get("time_limit", 8))

    scheduler.ensure(key, encounter["prompt"], accepted[0])

    print()
    print("  -- RECALL --")
    banner = "  {} ({} seconds)".format(encounter["prompt"], limit)
    answer, elapsed, timed_out = timed_input(banner, limit)
    correct = (not timed_out) and matches(answer, accepted)

    scheduler.record(key, correct, elapsed, limit)

    if correct:
        print("  Hit. {:.1f}s.".format(elapsed))
    elif timed_out:
        print("  Too slow. The rune was: {}".format(accepted[0]))
    else:
        print("  Miss. The rune was: {}".format(accepted[0]))

    return {"correct": correct, "damage": 0 if correct else miss_damage}


# --- SOLVE -----------------------------------------------------------------

def solve_battle(scheduler, encounter, world_root="world", miss_damage=5):
    """Dispatch a solve to the dry-run-verified path or the honor-system path.

    A solve marked `verify: dry-run` in the campaign runs the player's submitted
    command through kubectl with --dry-run=client. Every other solve (the
    rootfall default, and the kubefall debugging and triage bosses) is honor
    system, exactly as rootfall always did it.
    """
    if encounter.get("verify") == "dry-run":
        return _solve_dry_run(scheduler, encounter, miss_damage)
    return _solve_honor(scheduler, encounter, world_root, miss_damage)


def _solve_honor(scheduler, encounter, world_root, miss_damage):
    """Honor-system battle solved by the player and self-reported.

    Used for read-verb investigations and reasoning-chain bosses, where there is
    nothing for kubectl to validate. The player states or runs the correct
    commands, then reports.
    """
    key = encounter.get("key") or "solve"
    objective = encounter["objective"]

    print()
    print("  -- SOLVE (honor system) --")
    print("  " + objective)
    if encounter.get("hint"):
        print("  Hint: " + encounter["hint"])
    if encounter.get("fixture"):
        print("  Reference capture: {}/{}".format(world_root, encounter["fixture"]))
    print("  State or run the investigation, then report honestly. This is a prep tool.")

    _prompt("  Press Enter when you have worked it through... ")
    reported = _yes_no("  Did you reach the right answer?")

    scheduler.ensure(key, objective, encounter.get("hint", ""))
    scheduler.record(key, reported, 0.0, 0)

    if reported:
        print("  The gate swings open.")
    else:
        print("  The gate holds. Regroup and walk the chain again.")

    return {"correct": reported, "damage": 0 if reported else miss_damage}


def _solve_dry_run(scheduler, encounter, miss_damage):
    """Verify a kubectl create-style command with --dry-run=client, no cluster.

    The player types their command into the game. kubefall appends
    `--dry-run=client -o yaml` and runs it. kubectl exiting 0 with a manifest is
    a pass, and the manifest is shown as feedback. A kubectl error is a miss, and
    the error is surfaced and fed to SRS. If kubectl is not installed, or a read
    verb is submitted (which dry-run cannot validate), the battle falls back to
    honor-system self-report without crashing.
    """
    key = encounter.get("key") or "solve"
    objective = encounter["objective"]

    print()
    print("  -- SOLVE (dry-run verified) --")
    print("  " + objective)
    if encounter.get("hint"):
        print("  Hint: " + encounter["hint"])

    scheduler.ensure(key, objective, encounter.get("hint", ""))

    if shutil.which("kubectl") is None:
        print("  kubectl is not on PATH, so this solve cannot be verified.")
        print("  Install it with: brew install kubernetes-cli")
        return _report_fallback(scheduler, key, miss_damage)

    command = _prompt("  Type your kubectl command:\n  > ").strip()
    if not command:
        print("  No command entered. The gate holds.")
        scheduler.record(key, False, 0.0, 0)
        return {"correct": False, "damage": miss_damage}

    verb = _kubectl_verb(command)
    if verb in _READ_VERBS:
        print("  '{}' is a read verb. --dry-run cannot validate it, so this".format(verb))
        print("  falls back to honor-system self-report.")
        return _report_fallback(scheduler, key, miss_damage)

    status, output = _run_dry_run(command)

    if status == "pass":
        print("  kubectl accepted it. Generated manifest:")
        print()
        print(_indent(output))
        scheduler.record(key, True, 0.0, 0)
        return {"correct": True, "damage": 0}

    if status == "unverifiable":
        # kubectl is installed but needs a reachable cluster to validate this
        # verb (some, like run and expose, do API discovery even under
        # --dry-run=client). With no cluster we cannot grade it, so degrade to
        # honor-system rather than punish a possibly-correct answer.
        print("  This command needs a reachable cluster to verify (kubectl did")
        print("  API discovery and found none). Falling back to honor-system.")
        return _report_fallback(scheduler, key, miss_damage)

    print("  kubectl rejected it:")
    print(_indent(output or "(no error output)"))
    scheduler.record(key, False, 0.0, 0)
    return {"correct": False, "damage": miss_damage}


def _kubectl_verb(command):
    """The verb of a kubectl command: the first non-flag token after `kubectl`.

    Returns the lowercased verb, or "" if it cannot be determined.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    # Drop a leading `kubectl` if the player included it.
    if tokens and tokens[0].lower() == "kubectl":
        tokens = tokens[1:]
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            if token in _VALUE_FLAGS_BEFORE_VERB:
                skip_next = True  # this flag eats the next token as its value
            continue
        return token.lower()
    return ""


# Substrings that mark a failure as "kubectl could not reach a cluster" rather
# than "the command was wrong". Some create-style verbs (run, expose) still do
# API discovery under --dry-run=client, so with no cluster they error out on
# connectivity, not on the command. We must not grade those as a miss.
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
    """Run command + `--dry-run=client -o yaml`. Returns (status, output).

    status is one of:
      "pass"          kubectl exited 0 and produced a manifest (output is the YAML)
      "fail"          kubectl rejected the command (output is the error text)
      "unverifiable"  kubectl could not reach a cluster it needed for discovery,
                      so the command itself was never graded (output is the error)

    Never raises: a missing binary, a parse failure, or a timeout all come back
    as a clean status so the battle layer can degrade gracefully.
    """
    try:
        argv = shlex.split(command)
    except ValueError as error:
        return "fail", "could not parse the command: {}".format(error)

    if not argv:
        return "fail", "empty command"
    if argv[0].lower() != "kubectl":
        # Be forgiving: let the player omit the leading `kubectl`.
        argv = ["kubectl"] + argv

    argv = argv + ["--dry-run=client", "-o", "yaml"]
    try:
        result = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,  # text mode, 3.9 compatible spelling
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


def _report_fallback(scheduler, key, miss_damage):
    """Honor-system reporter used when a dry-run solve cannot be verified."""
    _prompt("  Run or state the correct command, then press Enter... ")
    reported = _yes_no("  Did it work?")
    scheduler.record(key, reported, 0.0, 0)
    if reported:
        print("  The gate swings open.")
    else:
        print("  The gate holds.")
    return {"correct": reported, "damage": 0 if reported else miss_damage}


def _indent(text, prefix="    "):
    return "\n".join(prefix + line for line in text.rstrip("\n").splitlines())


# --- VILLAGER --------------------------------------------------------------

def villager_battle(scheduler, encounter, compressed=False, miss_damage=1):
    """Teaching NPC that quiz gates before letting the player pass."""
    print()
    print("  -- VILLAGER: {} --".format(encounter["name"]))

    if compressed:
        if not _yes_no("  You have met this villager before. Hear the lore again?", default=False):
            # Compressed mode: tutorial is skippable once the zone is cleared.
            for rune in encounter.get("teaches", []):
                scheduler.ensure(rune["command"], rune.get("desc", ""), rune["command"])
            print("  You nod and walk past.")
            return {"correct": True, "damage": 0}

    print("  " + encounter["lore"])
    print()
    for rune in encounter.get("teaches", []):
        print("    rune {:<28} {}".format(rune["command"], rune.get("desc", "")))
    print()

    quiz = encounter["quiz"]
    attempts = 0
    while True:
        answer = _prompt("  {}\n  > ".format(quiz["prompt"]))
        if matches(answer, quiz["answers"]):
            print("  Correct. The road opens.")
            break
        attempts += 1
        print("  Not quite. The villager waits.")

    # A passed quiz seeds every taught command into the SRS queue.
    for rune in encounter.get("teaches", []):
        scheduler.seed(rune["command"], rune.get("desc", ""), rune["command"])

    return {"correct": True, "damage": min(attempts, 3) * miss_damage}


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
