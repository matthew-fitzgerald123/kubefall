"""Campaign-validation and world-fixture tests.

These guard the data-driven contract: all six zone files load and validate
against the schema, every zone has the three battle types, the creation zones
mark their boss solve dry-run while the debugging zones keep it honor-system, and
world.py scaffolds every referenced capture under a sandbox without error.
"""

import glob
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from kubefall import campaign, world

CAMPAIGN_DIR = os.path.join(ROOT, "campaign")

_CREATION_ZONES = {
    "zone01_pods", "zone02_deployments", "zone03_services", "zone04_config",
    "zone07_namespaces", "zone08_apply_rbac",
}
_DEBUG_ZONES = {"zone05_debugging", "zone06_cluster_triage"}


class CampaignLoadTests(unittest.TestCase):
    def test_all_zone_files_load_and_validate(self):
        files = sorted(glob.glob(os.path.join(CAMPAIGN_DIR, "zone*.yaml")))
        self.assertEqual(len(files), 8, "expected zones 1 through 8")
        for path in files:
            zone = campaign.load_zone_file(path)  # raises CampaignError if bad
            self.assertTrue(zone.id)
            self.assertTrue(zone.commands)
            self.assertTrue(zone.encounters)

    def test_zones_order_by_filename(self):
        zones = campaign.load_campaign(CAMPAIGN_DIR)
        ids = [z.id for z in zones]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(ids[0], "zone01_pods")
        self.assertEqual(ids[-1], "zone08_apply_rbac")

    def test_every_zone_has_villager_recall_and_solve(self):
        for zone in campaign.load_campaign(CAMPAIGN_DIR):
            kinds = set(e["type"] for e in zone.encounters)
            self.assertIn("villager", kinds, zone.id)
            self.assertIn("recall", kinds, zone.id)
            self.assertIn("solve", kinds, zone.id)

    def test_creation_zone_bosses_are_dry_run(self):
        for zone in campaign.load_campaign(CAMPAIGN_DIR):
            solves = [e for e in zone.encounters if e["type"] == "solve"]
            self.assertTrue(solves, zone.id)
            for solve in solves:
                if zone.id in _CREATION_ZONES:
                    self.assertEqual(solve.get("verify"), "dry-run", zone.id)

    def test_debug_zone_bosses_are_honor_system(self):
        for zone in campaign.load_campaign(CAMPAIGN_DIR):
            if zone.id not in _DEBUG_ZONES:
                continue
            for solve in [e for e in zone.encounters if e["type"] == "solve"]:
                # No verify key, or an explicit honor: never dry-run a read verb.
                self.assertNotEqual(solve.get("verify"), "dry-run", zone.id)

    def test_invalid_verify_value_is_rejected(self):
        bad = {
            "id": "zoneXX_bad", "name": "Bad", "path": "x", "theme": "x",
            "commands": ["x"],
            "encounters": [{"type": "solve", "objective": "x", "verify": "sometimes"}],
        }
        with self.assertRaises(campaign.CampaignError):
            campaign.validate_zone(bad, "memory")


class WorldFixtureTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.mkdtemp(prefix="kubefall-world-")
        self.root = os.path.join(self.sandbox, "world")

    def tearDown(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def test_build_world_creates_every_referenced_capture(self):
        world.build_world(self.root)
        for zone_id, paths in world.expected_fixtures(self.root).items():
            for path in paths:
                self.assertTrue(os.path.exists(path), "{}: missing {}".format(zone_id, path))

    def test_build_world_is_idempotent(self):
        world.build_world(self.root)
        world.build_world(self.root)  # must not raise on a second pass
        self.assertTrue(os.path.exists(world.capture_path("get_pods_crashloop.txt", self.root)))

    def test_crashloop_capture_contains_the_symptom(self):
        world.build_world(self.root)
        with open(world.capture_path("get_pods_crashloop.txt", self.root)) as handle:
            body = handle.read()
        self.assertIn("CrashLoopBackOff", body)

    def test_previous_logs_capture_points_at_config(self):
        world.build_world(self.root)
        with open(world.capture_path("logs_web_previous.txt", self.root)) as handle:
            body = handle.read()
        self.assertIn("DATABASE_URL", body)

    def test_solve_fixtures_exist_under_world(self):
        # Every solve fixture a zone names must be a capture world.py builds.
        world.build_world(self.root)
        for zone in campaign.load_campaign(CAMPAIGN_DIR):
            for solve in [e for e in zone.encounters if e["type"] == "solve"]:
                fixture = solve.get("fixture")
                if fixture:
                    self.assertTrue(
                        os.path.exists(os.path.join(self.root, fixture)),
                        "{}: missing fixture {}".format(zone.id, fixture),
                    )


if __name__ == "__main__":
    unittest.main()
