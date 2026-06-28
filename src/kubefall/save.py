"""Two-layer persistence: run state versus meta state.

This split is the central architectural constraint of the game.

RUN STATE is ephemeral. It holds the current descent: zone index, position,
current HP, and the runes, flags, and combos gathered this run. A death deletes
it outright.

META STATE is permanent. It holds the SM-2 scheduling queue, the per-command
error history (carried inside each SRS record), and the set of zones ever
cleared. A death must never touch it. If death ever erased meta state, the whole
point of the game would be lost.

Both layers are plain JSON under saves/, which is gitignored.
"""

import json
import os

META_FILE = "meta_state.json"
RUN_FILE = "run_state.json"

DEFAULT_MAX_HP = 20


def _path(save_dir, name):
    return os.path.join(save_dir, name)


def _write_json(path, data):
    """Write atomically so an interrupted save cannot corrupt meta state."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    os.replace(tmp, path)


# --- Meta state (permanent) ------------------------------------------------

def load_meta(save_dir="saves"):
    """Load permanent meta state, returning a fresh shell on first ever run."""
    path = _path(save_dir, META_FILE)
    if os.path.exists(path):
        with open(path) as handle:
            data = json.load(handle)
    else:
        data = {}
    data.setdefault("version", 1)
    data.setdefault("srs", {})
    data.setdefault("cleared_zones", [])
    return data


def save_meta(meta, save_dir="saves"):
    _write_json(_path(save_dir, META_FILE), meta)


# --- Run state (ephemeral) -------------------------------------------------

def new_run(max_hp=DEFAULT_MAX_HP):
    """Start a fresh descent at the root."""
    return {
        "zone_index": 0,
        "position": "/",
        "hp": max_hp,
        "max_hp": max_hp,
        "runes": [],
        "flags": [],
        "combos": [],
    }


def load_run(save_dir="saves"):
    path = _path(save_dir, RUN_FILE)
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        return json.load(handle)


def save_run(run, save_dir="saves"):
    _write_json(_path(save_dir, RUN_FILE), run)


def clear_run(save_dir="saves"):
    """Wipe run state on death. Meta state is deliberately left untouched."""
    path = _path(save_dir, RUN_FILE)
    if os.path.exists(path):
        os.remove(path)


def has_run(save_dir="saves"):
    return os.path.exists(_path(save_dir, RUN_FILE))
