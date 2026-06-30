"""The main game loop: zone traversal, run lifecycle, and death handling.

A run is one descent through the cluster, from pods down to triage. There is a
single HP bar across the whole descent; misses chip it and zero HP ends the run,
sending the player back to the top. Death deletes run state but never meta state,
so the spaced-repetition memory carries across every restart.

On a fresh run the player still traverses every zone from the top, but any zone
already in the meta-state "cleared" set runs in COMPRESSED mode: villager
tutorials become skippable and recall battles are SRS driven, so mastered
commands with stretched intervals rarely surface. Early descent gets faster as
mastery grows. Nothing is skipped outright, it is only compressed.
"""

import os

from . import battle
from . import campaign
from . import display
from . import save
from . import srs
from . import world


def _zone_number(zone_id):
    """Return the 1-based zone number from an id like 'zone07_namespaces'."""
    try:
        return int(zone_id.split("_")[0].replace("zone", ""))
    except (ValueError, IndexError):
        return 0


class Engine:
    def __init__(self, save_dir="saves", world_root="world", campaign_dir="campaign"):
        self.save_dir = save_dir
        self.world_root = world_root
        self.campaign_dir = campaign_dir
        self.meta = save.load_meta(save_dir)
        self.scheduler = srs.Scheduler(self.meta["srs"])
        self.zones = campaign.load_campaign(campaign_dir)
        self.screen = display.Screen()
        self.current_run = None

    # -- lifecycle ----------------------------------------------------------

    def run(self):
        """Play one full descent. Returns 0 on a clean exit."""
        world.build_world(self.world_root)
        run = save.new_run()
        self.current_run = run
        save.save_run(run, self.save_dir)

        self._intro()

        start_index = self._find_start_zone()
        if start_index > 0:
            zone_name = self.zones[start_index].name
            try:
                answer = input(
                    "\n  You have cleared {} zone(s). Jump to {}? [Y/n] ".format(
                        start_index, zone_name
                    )
                ).strip().lower()
            except EOFError:
                answer = "y"
            if not (not answer or answer.startswith("y")):
                start_index = 0

        for index in range(start_index, len(self.zones)):
            zone = self.zones[index]
            run["zone_index"] = index
            run["position"] = zone.path
            compressed = zone.id in self.meta["cleared_zones"]
            save.save_run(run, self.save_dir)

            self._enter_zone(zone, compressed)
            alive = self._play_zone(zone, run, compressed)

            if not alive:
                self._death(run)
                return 0

            if zone.id not in self.meta["cleared_zones"]:
                self.meta["cleared_zones"].append(zone.id)
            self._persist_meta()
            self.screen.clear()
            print("\n  Zone cleared: {}.".format(zone.name))

        self._victory(run)
        save.clear_run(self.save_dir)
        return 0

    def _find_start_zone(self):
        """Return the index of the first uncleared zone (0 if all cleared)."""
        cleared = set(self.meta["cleared_zones"])
        for i, zone in enumerate(self.zones):
            if zone.id not in cleared:
                return i
        return 0

    # -- zone play ----------------------------------------------------------

    def _play_zone(self, zone, run, compressed):
        for encounter in zone.encounters:
            outcome = self._fight(zone, encounter, run, compressed)
            if outcome is None:
                continue  # compressed-mode skip of a stretched recall

            run["hp"] -= outcome["damage"]
            if outcome["damage"]:
                self._show_hp(run)
            save.save_run(run, self.save_dir)

            if run["hp"] <= 0:
                return False
        return True

    def _fight(self, zone, encounter, run, compressed):
        kind = encounter["type"]
        hp = run["hp"]
        max_hp = run["max_hp"]

        if kind == "villager":
            return battle.villager_battle(
                self.scheduler, encounter,
                compressed=compressed,
                screen=self.screen,
                zone_id=zone.id,
            )

        if kind == "recall":
            key = encounter.get("key") or encounter["answers"][0]
            if compressed and not self.scheduler.is_due(key):
                return None
            return battle.recall_battle(
                self.scheduler, encounter,
                screen=self.screen,
                zone_id=zone.id,
                hp=hp,
                max_hp=max_hp,
            )

        if kind == "solve":
            return battle.solve_battle(
                self.scheduler, encounter,
                world_root=self.world_root,
                screen=self.screen,
                zone_id=zone.id,
                hp=hp,
                max_hp=max_hp,
            )

        raise campaign.CampaignError("unknown encounter type: {!r}".format(kind))

    # -- death and persistence ---------------------------------------------

    def _death(self, run):
        self.screen.death()
        save.clear_run(self.save_dir)
        self._persist_meta()
        print("\n  Run state wiped. Your memory is intact: {} commands tracked.".format(
            len(self.scheduler.items)
        ))

    def _persist_meta(self):
        self.meta["srs"] = self.scheduler.items
        save.save_meta(self.meta, self.save_dir)

    # -- presentation -------------------------------------------------------

    def _intro(self):
        cleared = len(self.meta["cleared_zones"])
        tracked = len(self.scheduler.items)
        self.screen.intro(cleared, tracked)

    def _enter_zone(self, zone, compressed):
        self.screen.zone_transition(
            zone_id=zone.id,
            zone_name=zone.name,
            zone_path=zone.path,
            zone_theme=zone.theme,
            cleared=compressed,
        )

    def _show_hp(self, run):
        hp = max(0, run["hp"])
        width = 20
        filled = int(round(width * hp / float(run["max_hp"]))) if run["max_hp"] else 0
        bar = "#" * filled + "." * (width - filled)
        print("  HP [{}] {}/{}".format(bar, hp, run["max_hp"]))

    def _victory(self, run):
        self.screen.victory(self.zones, run["hp"])


def main(argv=None):
    """Entry point used by both kubefall.py and the console script."""
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    save_dir = os.path.join(here, "saves")
    world_root = os.path.join(here, "world")
    campaign_dir = os.path.join(here, "campaign")
    try:
        engine = Engine(save_dir=save_dir, world_root=world_root, campaign_dir=campaign_dir)
    except campaign.CampaignError as error:
        print("Campaign error: {}".format(error))
        return 1
    try:
        return engine.run()
    except (KeyboardInterrupt, EOFError):
        print("\n  Descent paused. Meta state is safe.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
