"""Loads and validates YAML campaign files.

The schema is data driven on purpose. Authoring the six kubefall zones is pure
content work with no engine changes, as long as each zone file matches the shape
validated here. Malformed content fails loudly with a clear message rather than
crashing deep inside a battle.

This is rootfall's schema with one backward-compatible addition for kubefall's
dry-run-verified solve: a solve encounter may carry an optional `verify` key set
to "dry-run" (run the submitted command through kubectl) or "honor" (the default,
self-report). A solve may also carry an optional `fixture` path naming a text
capture under world/ that the player should read. Solves with neither key behave
exactly as they did in rootfall.
"""

import glob
import os

import yaml


class CampaignError(Exception):
    """Raised when a campaign file is missing or malformed."""


class Zone:
    """One zone of the descent, parsed from a single YAML file."""

    def __init__(self, id, name, path, theme, commands, encounters):
        self.id = id
        self.name = name
        self.path = path
        self.theme = theme
        self.commands = commands
        self.encounters = encounters

    def __repr__(self):
        return "Zone({!r}, encounters={})".format(self.id, len(self.encounters))


_REQUIRED_ZONE_KEYS = ("id", "name", "path", "theme", "commands", "encounters")
_VALID_TYPES = ("villager", "recall", "solve")
_VALID_SOLVE_VERIFY = ("dry-run", "honor")

# Per encounter type, the keys that must be present.
_REQUIRED_ENCOUNTER_KEYS = {
    "villager": ("name", "lore", "teaches", "quizzes"),
    "recall": ("prompt", "answers"),
    "solve": ("objective",),
}


def load_campaign(campaign_dir="campaign"):
    """Load every zone file in order, sorted by filename."""
    pattern = os.path.join(campaign_dir, "zone*.yaml")
    files = sorted(glob.glob(pattern))
    if not files:
        raise CampaignError("no zone files found under {!r}".format(campaign_dir))
    return [load_zone_file(path) for path in files]


def load_zone_file(path):
    try:
        with open(path) as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        raise CampaignError("{}: invalid YAML: {}".format(path, error))

    validate_zone(data, path)
    return Zone(
        id=data["id"],
        name=data["name"],
        path=data["path"],
        theme=data["theme"],
        commands=data["commands"],
        encounters=data["encounters"],
    )


def validate_zone(data, source):
    if not isinstance(data, dict):
        raise CampaignError("{}: top level must be a mapping".format(source))

    for key in _REQUIRED_ZONE_KEYS:
        if key not in data:
            raise CampaignError("{}: missing required key {!r}".format(source, key))

    if not isinstance(data["commands"], list) or not data["commands"]:
        raise CampaignError("{}: 'commands' must be a non-empty list".format(source))

    encounters = data["encounters"]
    if not isinstance(encounters, list) or not encounters:
        raise CampaignError("{}: 'encounters' must be a non-empty list".format(source))

    for index, encounter in enumerate(encounters):
        _validate_encounter(encounter, source, index)


def _validate_encounter(encounter, source, index):
    where = "{}: encounter #{}".format(source, index)
    if not isinstance(encounter, dict):
        raise CampaignError("{} must be a mapping".format(where))

    kind = encounter.get("type")
    if kind not in _VALID_TYPES:
        raise CampaignError(
            "{}: type must be one of {}, got {!r}".format(where, _VALID_TYPES, kind)
        )

    for key in _REQUIRED_ENCOUNTER_KEYS[kind]:
        if key not in encounter:
            raise CampaignError("{} ({}) missing key {!r}".format(where, kind, key))

    if kind == "recall":
        answers = encounter["answers"]
        if not isinstance(answers, list) or not answers:
            raise CampaignError("{}: 'answers' must be a non-empty list".format(where))

    if kind == "solve" and "verify" in encounter:
        verify = encounter["verify"]
        if verify not in _VALID_SOLVE_VERIFY:
            raise CampaignError(
                "{}: solve 'verify' must be one of {}, got {!r}".format(
                    where, _VALID_SOLVE_VERIFY, verify
                )
            )

    if kind == "villager":
        teaches = encounter["teaches"]
        if not isinstance(teaches, list) or not teaches:
            raise CampaignError("{}: 'teaches' must be a non-empty list".format(where))
        for rune in teaches:
            if not isinstance(rune, dict) or "command" not in rune:
                raise CampaignError("{}: each 'teaches' item needs a 'command'".format(where))
        quizzes = encounter.get("quizzes")
        if not isinstance(quizzes, list) or not quizzes:
            raise CampaignError("{}: 'quizzes' must be a non-empty list".format(where))
        for qi, q in enumerate(quizzes):
            if not isinstance(q, dict) or "prompt" not in q or "answers" not in q:
                raise CampaignError(
                    "{}: quizzes[{}] needs 'prompt' and 'answers'".format(where, qi)
                )
