"""Terminal UI renderer for kubefall.

All drawing goes through Screen. Callers build the game flow; Screen handles
every ANSI escape, layout calculation, and timing pause.

Layout (two-panel):
  ╔══(full width)══════════════════════════════╗
  ║ HEADER LEFT                  HEADER RIGHT  ║
  ╠════════════════════╦═══════════════════════╣
  ║  sprite panel      ║  content panel        ║
  ║  20 cols wide      ║  remaining cols       ║
  ║  (1+18+1)          ║                       ║
  ╚════════════════════╩═══════════════════════╝

The sprite panel is exactly 20 chars wide: one vertical border, 18 sprite
chars, one vertical border. The content panel is cols-21 chars wide (the right
border uses 1 more col on the far right).
"""

import re
import shutil
import sys
import time

from . import art


class Screen:

    # ------------------------------------------------------------------
    # Low-level color / style helpers
    # ------------------------------------------------------------------

    def _c(self, n):
        """ANSI 256 foreground color escape."""
        return "\033[38;5;{}m".format(n)

    def _b(self, n):
        """ANSI 256 background color escape."""
        return "\033[48;5;{}m".format(n)

    def _reset(self):
        return "\033[0m"

    def _bold(self, text):
        return "\033[1m{}\033[22m".format(text)

    def _colored(self, text, fg=None, bold=False):
        parts = []
        if bold:
            parts.append("\033[1m")
        if fg is not None:
            parts.append(self._c(fg))
        parts.append(text)
        parts.append(self._reset())
        return "".join(parts)

    # ------------------------------------------------------------------
    # Terminal geometry and HP bar
    # ------------------------------------------------------------------

    def _cols(self):
        return shutil.get_terminal_size().columns

    def _hp_bar(self, hp, max_hp, width=10):
        """Return a colored HP bar string like 'HP ████░░░░░░ 8/20'."""
        if max_hp <= 0:
            filled = 0
        else:
            filled = int(round(width * max(0, hp) / float(max_hp)))
        filled = min(filled, width)
        empty = width - filled

        bar = (
            self._c(46) + "█" * filled
            + self._c(244) + "░" * empty
            + self._reset()
        )
        return "HP {} {}/{}".format(bar, max(0, hp), max_hp)

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear(self):
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Word wrap
    # ------------------------------------------------------------------

    def _wrap(self, text, width):
        """Word-wrap text to a list of lines each at most width chars."""
        if width <= 0:
            return [text]
        words = text.split()
        lines = []
        current = []
        length = 0
        for word in words:
            if length == 0:
                current.append(word)
                length = len(word)
            elif length + 1 + len(word) <= width:
                current.append(word)
                length += 1 + len(word)
            else:
                lines.append(" ".join(current))
                current = [word]
                length = len(word)
        if current:
            lines.append(" ".join(current))
        return lines if lines else [""]

    # ------------------------------------------------------------------
    # Sprite line renderer
    # ------------------------------------------------------------------

    def _render_sprite_line(self, sprite, line_index):
        """Return a colored 18-char string for one sprite line."""
        line = sprite["lines"][line_index]
        color = sprite["accents"].get(line_index, sprite["primary"])
        return self._c(color) + line + self._reset()

    # ------------------------------------------------------------------
    # Core two-panel renderer
    # ------------------------------------------------------------------

    def _draw_panel(self, zone_id, sprite_key, header_left, header_right,
                    hp, max_hp, content_lines, await_input=True):
        """Draw the full two-panel frame to stdout.

        sprite_key is either "villager" or "enemy".
        content_lines is a list of plain strings already wrapped.
        If await_input is True, end with a prompt arrow on stdout; the
        caller then reads stdin.
        """
        cols = self._cols()
        zone_color, zone_dim = art.get_zone_colors(zone_id)

        if sprite_key == "villager":
            sprite = art.get_villager(zone_id)
        else:
            sprite = art.get_enemy(zone_id)

        # Panel geometry
        left_inner = 18       # sprite content width
        left_total = 20       # border + 18 + border
        right_inner = max(cols - left_total - 1, 10)  # remaining - right border

        border = self._c(zone_color)
        reset = self._reset()

        def hbar(left_cap, mid, cross_left, right_cap, width=None):
            """Build a horizontal border line."""
            w = width if width is not None else cols
            inner_left = left_inner + 2   # left panel inner including padding chars
            inner_right = max(w - inner_left - 3, 0)
            return (
                border
                + left_cap
                + mid * inner_left
                + cross_left
                + mid * inner_right
                + right_cap
                + reset
            )

        # Top border
        top = border + "╔" + "═" * (cols - 2) + "╗" + reset

        # Header line
        hp_str = self._hp_bar(hp, max_hp)
        _ansi_re = re.compile(r"\033\[[^m]*m")
        hp_visible = _ansi_re.sub("", hp_str)

        header_left_str = self._colored(" " + header_left, fg=zone_color, bold=True)
        header_right_str = " " + hp_str + "  " + self._colored(header_right, fg=zone_dim)

        left_vis = len(header_left) + 1
        right_vis = len(hp_visible) + 2 + len(header_right) + 2
        padding = cols - 2 - left_vis - right_vis
        if padding < 0:
            padding = 0

        header_line = (
            border + "║" + reset
            + header_left_str
            + " " * padding
            + header_right_str
            + border + "║" + reset
        )

        # Separator
        sep = hbar("╠", "═", "╬", "╣")

        # Content rows
        SPRITE_LINES = 13
        right_rows = list(content_lines)

        while len(right_rows) < SPRITE_LINES:
            right_rows.append("")

        body_rows = max(SPRITE_LINES, len(right_rows))

        # Centre the sprite vertically if body_rows > SPRITE_LINES.
        sprite_top_pad = (body_rows - SPRITE_LINES) // 2

        rows = []
        for i in range(body_rows):
            sprite_idx = i - sprite_top_pad
            if 0 <= sprite_idx < SPRITE_LINES:
                left_cell = self._render_sprite_line(sprite, sprite_idx)
                left_vis_len = left_inner
            else:
                left_cell = " " * left_inner
                left_vis_len = left_inner

            right_cell = right_rows[i] if i < len(right_rows) else ""
            right_pad = right_inner - len(right_cell)
            if right_pad < 0:
                right_cell = right_cell[:right_inner]
                right_pad = 0

            row = (
                border + "║" + reset
                + left_cell
                + border + "║" + reset
                + " " + right_cell + " " * max(0, right_pad - 1)
                + border + "║" + reset
            )
            rows.append(row)

        # Bottom border
        bottom = hbar("╚", "═", "╩", "╝")

        # Render
        self.clear()
        out = [top, header_line, sep] + rows + [bottom]
        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()

        if await_input:
            sys.stdout.write("  > ")
            sys.stdout.flush()

    # ------------------------------------------------------------------
    # Zone transition
    # ------------------------------------------------------------------

    # kubectl-themed banners for each zone. Shown during zone transitions.
    _ZONE_BANNERS = {
        "zone01_pods": [
            r"  kubectl run . kubectl get pods . kubectl describe pod",
            r"  .---------------------------------------------.",
            r"  | pod: the smallest deployable unit in the    |",
            r"  |      cluster. one or more containers.       |",
            r"  '---------------------------------------------'",
        ],
        "zone02_deployments": [
            r"  kubectl create deployment . kubectl rollout status",
            r"  .---------------------------------------------.",
            r"  | deployment -> replicaset -> pod -> pod -> pod|",
            r"  |  scale, rollout, rollback, history           |",
            r"  '---------------------------------------------'",
        ],
        "zone03_services": [
            r"  kubectl expose . kubectl get svc . ClusterIP",
            r"  .---------------------------------------------.",
            r"  | svc routes traffic to matching pods via     |",
            r"  | label selector. NodePort opens a host port. |",
            r"  '---------------------------------------------'",
        ],
        "zone04_config": [
            r"  kubectl create configmap . kubectl create secret",
            r"  .---------------------------------------------.",
            r"  | configmap: plain key=value config data      |",
            r"  | secret: base64-encoded sensitive data       |",
            r"  '---------------------------------------------'",
        ],
        "zone05_debugging": [
            r"  kubectl logs . kubectl describe . kubectl exec",
            r"  .---------------------------------------------.",
            r"  | logs: stdout/stderr stream from a container |",
            r"  | describe: events are where trouble shows    |",
            r"  '---------------------------------------------'",
        ],
        "zone06_cluster_triage": [
            r"  kubectl get pods . describe . logs . events",
            r"  .---------------------------------------------.",
            r"  | triage chain: listing -> detail -> events   |",
            r"  |   -> logs -> previous logs -> exec shell    |",
            r"  '---------------------------------------------'",
        ],
        "zone07_namespaces": [
            r"  kubectl create ns . kubectl config use-context",
            r"  .---------------------------------------------.",
            r"  | namespace: a virtual cluster within the     |",
            r"  | cluster. context: cluster + user + ns tuple.|",
            r"  '---------------------------------------------'",
        ],
        "zone08_apply_rbac": [
            r"  kubectl apply -f . kubectl create role . rolebinding",
            r"  .---------------------------------------------.",
            r"  | role: a set of allowed verbs on resources   |",
            r"  | rolebinding: attaches a role to a subject   |",
            r"  '---------------------------------------------'",
        ],
    }

    def zone_transition(self, zone_id, zone_name, zone_path, zone_theme, cleared):
        """Full-width banner displayed when entering a zone."""
        cols = self._cols()
        zone_color, zone_dim = art.get_zone_colors(zone_id)

        self.clear()
        border = self._c(zone_color)
        reset = self._reset()
        dim = self._c(zone_dim)

        top = border + "╔" + "═" * (cols - 2) + "╗" + reset
        mid = border + "╠" + "═" * (cols - 2) + "╣" + reset
        bot = border + "╚" + "═" * (cols - 2) + "╝" + reset

        def full_row(text, color=None, bold=False):
            c = color if color is not None else zone_color
            inner = cols - 4
            vis = text[:inner]
            pad = inner - len(vis)
            return (
                border + "║" + reset
                + " "
                + self._colored(vis, fg=c, bold=bold)
                + " " * pad
                + " "
                + border + "║" + reset
            )

        cleared_tag = "  [CLEARED]" if cleared else ""
        title = "  ZONE: {}{}".format(zone_name.upper(), cleared_tag)
        path_line = "  {}".format(zone_path)
        theme_line = "  {}".format(zone_theme)

        banners = self._ZONE_BANNERS.get(zone_id, [""])

        rows = [top, full_row(title, bold=True), full_row(path_line, color=zone_dim), mid]
        for banner_line in banners:
            rows.append(full_row(banner_line, color=zone_dim))
        rows += [mid, full_row(theme_line, color=zone_dim), bot]

        sys.stdout.write("\n".join(rows) + "\n")
        sys.stdout.flush()
        input("\n  Press Enter to enter the cluster... ")

    # ------------------------------------------------------------------
    # Villager lore screen
    # ------------------------------------------------------------------

    def villager_lore(self, zone_id, encounter):
        """Display villager lore and all runes. Wait for Enter."""
        zone_color, zone_dim = art.get_zone_colors(zone_id)
        sprite = art.get_villager(zone_id)
        inner_width = max(self._cols() - 22, 20)

        lines = []
        lines.append(self._colored(encounter["name"], fg=zone_color, bold=True))
        lines.append("")

        for wrap_line in self._wrap(encounter.get("lore", ""), inner_width - 2):
            lines.append(wrap_line)
        lines.append("")
        lines.append(self._colored("Commands taught:", fg=zone_dim))
        lines.append("")
        for rune in encounter.get("teaches", []):
            rune_line = "  {} -- {}".format(rune["command"], rune.get("desc", ""))
            for wl in self._wrap(rune_line, inner_width - 2):
                lines.append(wl)
        lines.append("")
        lines.append(self._colored("Press Enter to continue...", fg=zone_dim))

        self._draw_panel(
            zone_id=zone_id,
            sprite_key="villager",
            header_left=encounter["name"],
            header_right="LORE",
            hp=0,
            max_hp=0,
            content_lines=lines,
            await_input=False,
        )
        input()

    # ------------------------------------------------------------------
    # Villager quiz
    # ------------------------------------------------------------------

    def villager_quiz(self, zone_id, encounter, quiz_item, idx, total, wrong_attempts):
        """Draw quiz frame. Does not wait -- caller reads answer after."""
        zone_color, zone_dim = art.get_zone_colors(zone_id)
        inner_width = max(self._cols() - 22, 20)

        progress = "Quiz {}/{}".format(idx + 1, total)
        lines = []
        lines.append(self._colored(encounter["name"], fg=zone_color, bold=True))
        lines.append(self._colored(progress, fg=zone_dim))
        lines.append("")

        for wl in self._wrap(quiz_item["prompt"], inner_width - 2):
            lines.append(wl)
        lines.append("")

        if wrong_attempts > 0:
            hint_text = "  (Attempts: {})  Keep trying.".format(wrong_attempts)
            lines.append(self._colored(hint_text, fg=196))
            lines.append("")

        self._draw_panel(
            zone_id=zone_id,
            sprite_key="villager",
            header_left=encounter["name"],
            header_right=progress,
            hp=0,
            max_hp=0,
            content_lines=lines,
            await_input=True,
        )

    # ------------------------------------------------------------------
    # Villager quiz result
    # ------------------------------------------------------------------

    def villager_quiz_result(self, zone_id, encounter, quiz_item, idx, total, correct):
        """Redraw with colored result then sleep 0.8s."""
        zone_color, zone_dim = art.get_zone_colors(zone_id)
        inner_width = max(self._cols() - 22, 20)

        progress = "Quiz {}/{}".format(idx + 1, total)
        lines = []
        lines.append(self._colored(encounter["name"], fg=zone_color, bold=True))
        lines.append(self._colored(progress, fg=zone_dim))
        lines.append("")

        for wl in self._wrap(quiz_item["prompt"], inner_width - 2):
            lines.append(wl)
        lines.append("")

        if correct:
            lines.append(self._colored("  Correct!", fg=46, bold=True))
        else:
            lines.append(self._colored("  Not quite.", fg=196, bold=True))
            answer_line = "  Answer: {}".format(quiz_item["answers"][0])
            lines.append(self._colored(answer_line, fg=zone_dim))

        self._draw_panel(
            zone_id=zone_id,
            sprite_key="villager",
            header_left=encounter["name"],
            header_right=progress,
            hp=0,
            max_hp=0,
            content_lines=lines,
            await_input=False,
        )
        time.sleep(0.8)

    # ------------------------------------------------------------------
    # Battle prompt
    # ------------------------------------------------------------------

    def battle_prompt(self, zone_id, encounter, hp, max_hp):
        """Draw enemy recall prompt. Does not wait -- caller reads answer."""
        zone_color, zone_dim = art.get_zone_colors(zone_id)
        inner_width = max(self._cols() - 22, 20)
        limit = int(encounter.get("time_limit", 8))

        lines = []
        lines.append(self._colored("-- RECALL BATTLE --", fg=zone_color, bold=True))
        lines.append(self._colored(art.get_enemy(zone_id)["name"], fg=zone_dim))
        lines.append("")

        for wl in self._wrap(encounter.get("prompt", ""), inner_width - 2):
            lines.append(wl)
        lines.append("")
        lines.append(self._colored(
            "  ({} seconds)".format(limit), fg=zone_dim
        ))
        lines.append("")

        self._draw_panel(
            zone_id=zone_id,
            sprite_key="enemy",
            header_left=art.get_enemy(zone_id)["name"],
            header_right="BATTLE",
            hp=hp,
            max_hp=max_hp,
            content_lines=lines,
            await_input=True,
        )

    # ------------------------------------------------------------------
    # Battle result
    # ------------------------------------------------------------------

    def battle_result(self, zone_id, encounter, hp, max_hp, correct, timed_out, shown_answer):
        """Redraw with colored result then sleep 1.2s."""
        zone_color, zone_dim = art.get_zone_colors(zone_id)
        inner_width = max(self._cols() - 22, 20)
        limit = int(encounter.get("time_limit", 8))

        lines = []
        lines.append(self._colored("-- RECALL BATTLE --", fg=zone_color, bold=True))
        lines.append(self._colored(art.get_enemy(zone_id)["name"], fg=zone_dim))
        lines.append("")

        for wl in self._wrap(encounter.get("prompt", ""), inner_width - 2):
            lines.append(wl)
        lines.append("")

        if correct:
            lines.append(self._colored("  Hit!", fg=46, bold=True))
        elif timed_out:
            lines.append(self._colored("  Too slow!", fg=196, bold=True))
            lines.append(self._colored(
                "  The command was: {}".format(shown_answer), fg=zone_dim
            ))
        else:
            lines.append(self._colored("  Miss.", fg=196, bold=True))
            lines.append(self._colored(
                "  The command was: {}".format(shown_answer), fg=zone_dim
            ))

        self._draw_panel(
            zone_id=zone_id,
            sprite_key="enemy",
            header_left=art.get_enemy(zone_id)["name"],
            header_right="BATTLE",
            hp=hp,
            max_hp=max_hp,
            content_lines=lines,
            await_input=False,
        )
        time.sleep(1.2)

    # ------------------------------------------------------------------
    # Solve prompt
    # ------------------------------------------------------------------

    # Usage patterns keyed by encounter name. Values are generic usage hints
    # that show the shape of the command without revealing the exact answer.
    _SOLVE_USAGE = {
        "First Pod": "kubectl run <name> --image=<image>",
        "Three Replicas": "kubectl create deployment <name> --image=<image> --replicas=<n>",
        "Scale Up": "kubectl scale deployment <name> --replicas=<n>",
        "The Front Door": "kubectl expose deployment <name> --port=<n> --target-port=<n>",
        "First Config": "kubectl create configmap <name> --from-literal=<key>=<value>",
        "First Secret": "kubectl create secret generic <name> --from-literal=<key>=<value>",
        "Reading the Symptoms": "kubectl logs <pod> --previous ; kubectl describe pod <pod>",
        "The Interview": "get pods -> describe pod -> logs -> logs --previous -> get configmap",
        "The Right Context": "kubectl create namespace <name>",
        "Access Denied": "kubectl create serviceaccount <name>",
        # Fallback patterns by kubectl verb keyword
        "run": "kubectl run <name> --image=<image>",
        "create deployment": "kubectl create deployment <name> --image=<image>",
        "expose": "kubectl expose <type> <name> --port=<n>",
        "create configmap": "kubectl create configmap <name> --from-literal=<key>=<value>",
        "create secret": "kubectl create secret generic <name> --from-literal=<key>=<value>",
        "create namespace": "kubectl create namespace <name>",
        "apply": "kubectl apply -f <file.yaml>",
        "scale": "kubectl scale deployment <name> --replicas=<n>",
        "rollout": "kubectl rollout status deployment/<name>",
        "logs": "kubectl logs <pod> [--previous] [-c <container>]",
        "describe": "kubectl describe <resource> <name>",
        "exec": "kubectl exec -it <pod> -- <command>",
    }

    def _derive_usage(self, encounter):
        """Return a generic usage hint string for a solve encounter."""
        name = encounter.get("name", "")
        if name in self._SOLVE_USAGE:
            return self._SOLVE_USAGE[name]
        for key, pattern in self._SOLVE_USAGE.items():
            if key.lower() in name.lower():
                return pattern
        hint = encounter.get("hint", "")
        if hint:
            first_word = hint.split()[0] if hint.split() else ""
            if first_word in self._SOLVE_USAGE:
                return self._SOLVE_USAGE[first_word]
            return "{} <args>".format(first_word) if first_word else "<command> <args>"
        return "kubectl <verb> <resource> <name> [flags]"

    def solve_prompt(self, zone_id, encounter, hp, max_hp, world_root=None):
        """Draw solve screen with objective and usage hint.

        Does NOT wait for input -- the I/O (Enter for honor-system, command
        input for dry-run) happens in the terminal below the panel immediately
        after this returns. The panel shows whether the solve is dry-run
        verified or honor-system so the player knows what to expect.
        """
        zone_color, zone_dim = art.get_zone_colors(zone_id)
        inner_width = max(self._cols() - 22, 20)

        usage = self._derive_usage(encounter)
        verify = encounter.get("verify", "honor")
        if verify == "dry-run":
            mode_label = "dry-run verified (kubectl validates the command)"
        else:
            mode_label = "honor system (self-report after running in your terminal)"

        lines = []
        lines.append(self._colored("-- SOLVE BATTLE --", fg=zone_color, bold=True))
        lines.append(self._colored(encounter.get("name", "Boss"), fg=zone_dim))
        lines.append("")
        lines.append(self._colored("Objective:", fg=zone_color))

        for wl in self._wrap(encounter.get("objective", ""), inner_width - 2):
            lines.append("  " + wl)
        lines.append("")
        lines.append(self._colored("Mode:", fg=zone_dim))
        lines.append("  " + self._colored(mode_label, fg=zone_dim))
        lines.append("")
        lines.append(self._colored("Usage pattern:", fg=zone_dim))
        lines.append("  " + self._colored(usage, fg=zone_color, bold=True))
        lines.append("")
        if verify == "dry-run":
            lines.append(self._colored(
                "  Type your kubectl command below the panel.", fg=zone_dim
            ))
        else:
            lines.append(self._colored(
                "  Run the investigation, then press Enter to self-report.", fg=zone_dim
            ))

        self._draw_panel(
            zone_id=zone_id,
            sprite_key="enemy",
            header_left=encounter.get("name", "Boss"),
            header_right="SOLVE",
            hp=hp,
            max_hp=max_hp,
            content_lines=lines,
            await_input=False,
        )

    # ------------------------------------------------------------------
    # Solve result
    # ------------------------------------------------------------------

    def solve_result(self, zone_id, encounter, hp, max_hp, correct, details=None):
        """Redraw with solve result then sleep 1.0s.

        details: optional string (kubectl dry-run output or error text).
        If provided, the first 6 lines are shown in the result panel.
        """
        zone_color, zone_dim = art.get_zone_colors(zone_id)
        inner_width = max(self._cols() - 22, 20)

        lines = []
        lines.append(self._colored("-- SOLVE BATTLE --", fg=zone_color, bold=True))
        lines.append(self._colored(encounter.get("name", "Boss"), fg=zone_dim))
        lines.append("")

        for wl in self._wrap(encounter.get("objective", ""), inner_width - 2):
            lines.append("  " + wl)
        lines.append("")

        if correct:
            lines.append(self._colored("  The cluster accepts it.", fg=46, bold=True))
        else:
            lines.append(self._colored("  The cluster rejects it.", fg=196, bold=True))
            lines.append(self._colored(
                "  Regroup and try the command again.", fg=zone_dim
            ))

        if details:
            lines.append("")
            lines.append(self._colored("  Output:", fg=zone_dim))
            detail_lines = details.rstrip("\n").splitlines()[:6]
            for dl in detail_lines:
                for wl in self._wrap(dl, inner_width - 4):
                    lines.append("    " + wl)

        self._draw_panel(
            zone_id=zone_id,
            sprite_key="enemy",
            header_left=encounter.get("name", "Boss"),
            header_right="SOLVE",
            hp=hp,
            max_hp=max_hp,
            content_lines=lines,
            await_input=False,
        )
        time.sleep(1.0)

    # ------------------------------------------------------------------
    # Intro screen
    # ------------------------------------------------------------------

    def intro(self, cleared, tracked):
        """Full-width intro screen. Does not wait."""
        cols = self._cols()
        self.clear()

        zone_color = 51
        border = self._c(zone_color)
        reset = self._reset()

        top = border + "╔" + "═" * (cols - 2) + "╗" + reset
        bot = border + "╚" + "═" * (cols - 2) + "╝" + reset
        sep = border + "╠" + "═" * (cols - 2) + "╣" + reset

        def row(text, color=None, bold=False, center=False):
            c = color if color is not None else zone_color
            inner = cols - 4
            if center:
                vis = text[:inner]
                pad_left = (inner - len(vis)) // 2
                pad_right = inner - len(vis) - pad_left
                content = " " * pad_left + vis + " " * pad_right
            else:
                vis = text[:inner]
                content = vis + " " * (inner - len(vis))
            return (
                border + "║" + reset
                + " "
                + self._colored(content, fg=c, bold=bold)
                + " "
                + border + "║" + reset
            )

        art_lines = [
            r"  _  ___   _ ____  _____  _____  _    _     _     ",
            r" | |/ / | | | __ )| ____||  ___|| |  | |   | |    ",
            r" | ' /| | | |  _ \|  _|  | |_   | |  | |   | |    ",
            r" | . \| |_| | |_) | |___ |  _|  | |__| |___| |___ ",
            r" |_|\_\\___/|____/|_____||_|    |____|_____|_____|",
        ]

        rows = [top]
        for al in art_lines:
            rows.append(row(al, color=zone_color, bold=True, center=True))
        rows.append(row("", color=zone_color))
        rows.append(row("  A descent through the cluster. The map is the namespace.",
                        color=244, center=True))
        rows.append(sep)
        rows.append(row(
            "  Starting at cluster root    Zones cleared: {}    Commands tracked: {}".format(
                cleared, tracked),
            color=zone_color,
        ))
        rows.append(bot)

        sys.stdout.write("\n".join(rows) + "\n")
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Death screen
    # ------------------------------------------------------------------

    def death(self):
        """Full-width death screen. Does not wait."""
        cols = self._cols()
        self.clear()

        color = 196
        border = self._c(color)
        reset = self._reset()

        top = border + "╔" + "═" * (cols - 2) + "╗" + reset
        bot = border + "╚" + "═" * (cols - 2) + "╝" + reset
        sep = border + "╠" + "═" * (cols - 2) + "╣" + reset

        def row(text, c=None, bold=False, center=False):
            fc = c if c is not None else color
            inner = cols - 4
            if center:
                vis = text[:inner]
                pad_left = (inner - len(vis)) // 2
                pad_right = inner - len(vis) - pad_left
                content = " " * pad_left + vis + " " * pad_right
            else:
                vis = text[:inner]
                content = vis + " " * (inner - len(vis))
            return (
                border + "║" + reset
                + " "
                + self._colored(content, fg=fc, bold=bold)
                + " "
                + border + "║" + reset
            )

        skull_lines = [
            r"        ___",
            r"       /   \      YOU HAVE BEEN EVICTED",
            r"      | x x |",
            r"      |  ^  |     HP reached zero.",
            r"       \_W_/      You wake at the cluster root.",
            r"      /|   |\     Run state wiped.",
            r"     / |   | \    Your memory is intact.",
        ]

        rows = [top]
        for sl in skull_lines:
            rows.append(row(sl, c=color, bold=True, center=True))
        rows.append(sep)
        rows.append(row("  The cluster evicts you. Begin again.", c=88, center=True))
        rows.append(bot)

        sys.stdout.write("\n".join(rows) + "\n")
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Victory screen
    # ------------------------------------------------------------------

    def victory(self, zones, hp):
        """Full-width victory screen. Does not wait."""
        cols = self._cols()
        self.clear()

        color = 220
        border = self._c(color)
        reset = self._reset()

        top = border + "╔" + "═" * (cols - 2) + "╗" + reset
        bot = border + "╚" + "═" * (cols - 2) + "╝" + reset
        sep = border + "╠" + "═" * (cols - 2) + "╣" + reset

        def row(text, c=None, bold=False, center=False):
            fc = c if c is not None else color
            inner = cols - 4
            if center:
                vis = text[:inner]
                pad_left = (inner - len(vis)) // 2
                pad_right = inner - len(vis) - pad_left
                content = " " * pad_left + vis + " " * pad_right
            else:
                vis = text[:inner]
                content = vis + " " * (inner - len(vis))
            return (
                border + "║" + reset
                + " "
                + self._colored(content, fg=fc, bold=bold)
                + " "
                + border + "║" + reset
            )

        victory_art = [
            r"    *   .       .    *    .       .   *",
            r"  .   *    YOU HAVE CLEARED THE CLUSTER   .",
            r"    .    *   .    *   .    *   .    *   ",
            r"  *   .   GATEKEEPER DEFEATED   .   *",
            r"    .    *   .    *   .    *   .    *   ",
        ]

        rows = [top]
        for va in victory_art:
            rows.append(row(va, c=color, bold=True, center=True))
        rows.append(sep)
        rows.append(row(
            "  Cleared all {} zones.  HP remaining: {}.".format(len(zones), max(0, hp)),
            c=226, center=True,
        ))
        rows.append(row(
            "  Mastered commands stay buried. Run again: only gaps remain.",
            c=244, center=True,
        ))
        rows.append(bot)

        sys.stdout.write("\n".join(rows) + "\n")
        sys.stdout.flush()
