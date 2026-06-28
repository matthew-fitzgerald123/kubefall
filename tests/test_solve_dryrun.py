"""Tests for the dry-run-verified solve path (engine change 1).

The important behaviors, none of which require a cluster:
  - the verb parser finds the verb even past global value-taking flags like -n
  - read verbs are recognized so a solve never dry-runs a `kubectl get`
  - connectivity failures are classified "unverifiable", not "fail", so a
    possibly-correct answer is never graded as a miss
  - when kubectl is absent the solve degrades to honor-system without crashing

The kubectl-absent and dispatch tests stub out shutil.which and the interactive
prompts, so they run identically whether or not kubectl is installed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from kubefall import battle, srs


class VerbParsingTests(unittest.TestCase):
    def test_plain_verb(self):
        self.assertEqual(battle._kubectl_verb("kubectl run web --image=nginx"), "run")

    def test_verb_after_namespace_flag(self):
        # -n eats its value; the verb is get, not the namespace value.
        self.assertEqual(battle._kubectl_verb("kubectl -n web get pods"), "get")

    def test_verb_after_equals_namespace(self):
        self.assertEqual(battle._kubectl_verb("kubectl --namespace=web get pods"), "get")

    def test_leading_kubectl_optional(self):
        self.assertEqual(battle._kubectl_verb("create deployment web"), "create")

    def test_read_verbs_are_recognized(self):
        for command in ["kubectl get pods", "kubectl -n web describe pod web", "kubectl logs web"]:
            self.assertIn(battle._kubectl_verb(command), battle._READ_VERBS)


class ClassificationTests(unittest.TestCase):
    def test_no_cluster_markers_detected(self):
        self.assertTrue(battle._looks_like_no_cluster(
            "The connection to the server localhost:8080 was refused"))
        self.assertTrue(battle._looks_like_no_cluster(
            "couldn't get current server API group list: dial tcp ..."))
        self.assertFalse(battle._looks_like_no_cluster(
            'error: required flag(s) "image" not set'))

    def test_unparseable_command_is_a_clean_fail(self):
        status, output = battle._run_dry_run('kubectl run "unterminated')
        self.assertEqual(status, "fail")
        self.assertIn("parse", output.lower())


class FakeScheduler(srs.Scheduler):
    """A real scheduler is fine; this just records what was graded."""
    def __init__(self):
        super().__init__()
        self.graded = []

    def record(self, key, correct, elapsed=0.0, time_limit=0, now=None):
        self.graded.append((key, correct))
        return super().record(key, correct, elapsed, time_limit, now)


class KubectlAbsentFallbackTests(unittest.TestCase):
    def setUp(self):
        self._which = battle.shutil.which
        self._prompt = battle._prompt
        self._yes_no = battle._yes_no
        # Simulate kubectl missing from PATH.
        battle.shutil.which = lambda name: None
        # Stub the interactive layer: Enter, then "yes, it worked".
        battle._prompt = lambda text="": ""
        battle._yes_no = lambda question, default=True: True

    def tearDown(self):
        battle.shutil.which = self._which
        battle._prompt = self._prompt
        battle._yes_no = self._yes_no

    def test_dry_run_solve_degrades_to_honor_without_crashing(self):
        scheduler = FakeScheduler()
        encounter = {
            "type": "solve",
            "verify": "dry-run",
            "objective": "Create a pod named web from nginx.",
            "hint": "kubectl run web --image=nginx",
            "key": "kubectl run pod",
        }
        outcome = battle.solve_battle(scheduler, encounter)
        self.assertTrue(outcome["correct"])
        self.assertEqual(outcome["damage"], 0)
        self.assertEqual(scheduler.graded, [("kubectl run pod", True)])

    def test_honor_solve_is_unaffected_by_kubectl(self):
        scheduler = FakeScheduler()
        encounter = {
            "type": "solve",
            "objective": "Walk the triage chain.",
            "key": "triage chain",
        }
        outcome = battle.solve_battle(scheduler, encounter)
        self.assertTrue(outcome["correct"])
        self.assertEqual(scheduler.graded, [("triage chain", True)])


@unittest.skipIf(battle.shutil.which("kubectl") is None, "kubectl not installed")
class KubectlPresentTests(unittest.TestCase):
    """Only runs when a real kubectl is on PATH. No cluster is needed."""

    def test_create_configmap_validates_offline(self):
        status, output = battle._run_dry_run(
            "kubectl create configmap web-config --from-literal=COLOR=blue")
        self.assertEqual(status, "pass")
        self.assertIn("ConfigMap", output)

    def test_garbage_command_is_rejected(self):
        status, output = battle._run_dry_run("kubectl create deployment")
        self.assertEqual(status, "fail")


if __name__ == "__main__":
    unittest.main()
