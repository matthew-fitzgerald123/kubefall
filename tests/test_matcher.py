"""Unit tests for the kubectl-aware recall matcher.

Two contracts are under test here. First, the kubefall additions: resource
short-name and singular/plural equivalence, namespace flag-form equivalence, and
the hard rule that distinct resources never collapse. Second, a regression guard
that rootfall's original matcher behavior (flag order, flag bundling, quote
tolerance, flag-case significance, distinct arguments) is completely unchanged,
because the kubectl normalization only ever fires for a `kubectl ...` answer.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from kubefall import battle, campaign

CAMPAIGN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "campaign")


def _zone(zone_id):
    for zone in campaign.load_campaign(CAMPAIGN_DIR):
        if zone.id == zone_id:
            return zone
    raise AssertionError("zone not found: " + zone_id)


def _recall_starting(zone, prefix):
    for enc in zone.encounters:
        if enc["type"] == "recall" and enc["answers"][0].startswith(prefix):
            return enc["answers"]
    raise AssertionError("no recall starting with: " + prefix)


class KubectlResourceEquivalence(unittest.TestCase):
    def test_short_name_matches_long_name(self):
        self.assertTrue(battle.matches("kubectl get po", ["kubectl get pods"]))
        self.assertTrue(battle.matches("kubectl get deploy", ["kubectl get deployments"]))
        self.assertTrue(battle.matches("kubectl get svc", ["kubectl get services"]))
        self.assertTrue(battle.matches("kubectl get cm", ["kubectl get configmaps"]))
        self.assertTrue(battle.matches("kubectl get ns", ["kubectl get namespaces"]))
        self.assertTrue(battle.matches("kubectl get rs", ["kubectl get replicasets"]))
        self.assertTrue(battle.matches("kubectl get no", ["kubectl get nodes"]))

    def test_plural_matches_singular(self):
        self.assertTrue(battle.matches("kubectl get pod", ["kubectl get pods"]))
        self.assertTrue(battle.matches("kubectl describe service web", ["kubectl describe services web"]))

    def test_long_form_answer_accepts_short_form_input(self):
        self.assertTrue(battle.matches("kubectl get pods", ["kubectl get po"]))

    def test_distinct_resources_do_not_collapse(self):
        self.assertFalse(battle.matches("kubectl get pods", ["kubectl get deployments"]))
        self.assertFalse(battle.matches("kubectl get svc", ["kubectl get pods"]))
        self.assertFalse(battle.matches("kubectl get cm", ["kubectl get secrets"]))
        self.assertFalse(battle.matches("kubectl get rs", ["kubectl get rc"]))


class KubectlNamespaceFlag(unittest.TestCase):
    def test_dash_n_equals_long_namespace(self):
        self.assertTrue(battle.matches(
            "kubectl get pods -n web", ["kubectl get pods --namespace web"]))
        self.assertTrue(battle.matches(
            "kubectl get pods --namespace web", ["kubectl get pods -n web"]))

    def test_equals_form_of_namespace(self):
        self.assertTrue(battle.matches(
            "kubectl get pods --namespace=web", ["kubectl get pods -n web"]))
        self.assertTrue(battle.matches(
            "kubectl get pods -n=web", ["kubectl get pods --namespace web"]))

    def test_namespace_value_still_matters(self):
        self.assertFalse(battle.matches(
            "kubectl get pods -n web", ["kubectl get pods -n prod"]))

    def test_short_name_and_namespace_together(self):
        self.assertTrue(battle.matches(
            "kubectl get po -n kube-system", ["kubectl get pods --namespace kube-system"]))


class RootfallBehaviorUnchanged(unittest.TestCase):
    """These mirror rootfall's own matcher tests: nothing here may regress."""

    def test_flag_order_independent(self):
        self.assertTrue(battle.matches("ss -tlpnu", ["ss -tulpn"]))

    def test_bundled_equals_separated(self):
        self.assertTrue(battle.matches("ss -t -u -l -p -n", ["ss -tulpn"]))

    def test_whitespace_tolerated(self):
        self.assertTrue(battle.matches("ss     -tulpn", ["ss -tulpn"]))

    def test_missing_flag_fails(self):
        self.assertFalse(battle.matches("ss -tuln", ["ss -tulpn"]))

    def test_flag_case_is_significant(self):
        self.assertFalse(battle.matches("ls -r", ["ls -R"]))
        self.assertTrue(battle.matches("ls -R", ["ls -R"]))

    def test_signal_argument_significant(self):
        self.assertFalse(battle.matches("kill -15 6606", ["kill -9 6606"]))

    def test_long_flags_not_treated_as_bundles(self):
        self.assertFalse(battle.matches("grep --recursive x", ["grep -r x"]))

    def test_quoted_argument_matches_unquoted(self):
        self.assertTrue(battle.matches('find . -name "config.yaml"', ["find . -name config.yaml"]))

    def test_quoted_span_with_space_keeps_boundary(self):
        self.assertFalse(battle.matches('grep "foo bar"', ["grep foo bar"]))

    def test_dash_n_not_namespaced_outside_kubectl(self):
        # The critical non-regression: -n in grep/head must NOT become a
        # namespace flag, because the kubectl pass only fires for kubectl.
        self.assertTrue(battle.matches("grep -n ERROR app.log", ["grep -n ERROR app.log"]))
        self.assertEqual(
            battle._canonical("grep -n ERROR app.log"),
            battle._canonical("grep -n ERROR app.log"),
        )
        # Bundled-vs-separated still holds even though one form has a bare -n.
        self.assertTrue(battle.matches("ss -t -u -l -p -n", ["ss -tulpn"]))


class CampaignAnswerMatching(unittest.TestCase):
    def test_pods_recall_accepts_short_name(self):
        answers = _recall_starting(_zone("zone01_pods"), "kubectl get pods")
        self.assertTrue(battle.matches("kubectl get po", answers))
        self.assertFalse(battle.matches("kubectl get deploy", answers))

    def test_namespace_recall_accepts_long_flag(self):
        answers = _recall_starting(_zone("zone01_pods"), "kubectl get pods -n")
        self.assertTrue(battle.matches("kubectl get pods --namespace kube-system", answers))
        self.assertTrue(battle.matches("kubectl get po -n kube-system", answers))


if __name__ == "__main__":
    unittest.main()
