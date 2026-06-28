"""Unit tests for the SM-2 scheduler.

This is rootfall's scheduler reused unchanged, so these tests are adapted only in
their import path. They must pass exactly as they did in rootfall:
  - a correct fast answer stretches the interval
  - a wrong answer resets the repetition count and shrinks the interval
  - the ease factor never drops below the 1.3 floor
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from kubefall import srs


class GradeResponseTests(unittest.TestCase):
    def test_fast_correct_is_high_quality(self):
        self.assertEqual(srs.grade_response(True, 2.0, 10), 5)

    def test_slow_correct_is_passing(self):
        self.assertEqual(srs.grade_response(True, 9.0, 10), 3)

    def test_wrong_is_failing(self):
        self.assertLess(srs.grade_response(False, 1.0, 10), 3)

    def test_no_timer_solve_is_mid_high(self):
        # A solve has no timer; a reported success lands at quality 4.
        self.assertEqual(srs.grade_response(True, 0.0, 0), 4)


class ReviewTests(unittest.TestCase):
    def test_correct_fast_answer_stretches_interval(self):
        item = srs.new_item("kubectl get pods")
        srs.review(item, 5, now=0)
        self.assertEqual(item["interval"], 1)
        srs.review(item, 5, now=0)
        self.assertEqual(item["interval"], 6)
        srs.review(item, 5, now=0)
        self.assertGreater(item["interval"], 6)
        self.assertEqual(item["repetition"], 3)

    def test_wrong_answer_resets_repetition_and_shrinks_interval(self):
        item = srs.new_item("kubectl run")
        srs.review(item, 5, now=0)
        srs.review(item, 5, now=0)
        self.assertEqual(item["interval"], 6)
        grown_repetition = item["repetition"]

        srs.review(item, 1, now=0)  # a wrong/timeout grade

        self.assertEqual(item["repetition"], 0)
        self.assertLess(item["interval"], 6)
        self.assertLess(item["repetition"], grown_repetition)
        self.assertEqual(item["errors"], 1)

    def test_ease_never_drops_below_floor(self):
        item = srs.new_item("kubectl expose")
        for _ in range(10):
            srs.review(item, 0, now=0)
        self.assertGreaterEqual(item["ease"], srs.EASE_FLOOR)
        self.assertAlmostEqual(item["ease"], srs.EASE_FLOOR)

    def test_due_advances_after_review(self):
        item = srs.new_item("kubectl describe")
        srs.review(item, 4, now=1000.0)
        self.assertGreater(item["due"], 1000.0)
        self.assertEqual(item["last_reviewed"], 1000.0)


class SchedulerTests(unittest.TestCase):
    def test_record_uses_timer_to_grade(self):
        scheduler = srs.Scheduler()
        scheduler.record("kubectl get svc", correct=True, elapsed=1.0, time_limit=10, now=0)
        item = scheduler.items["kubectl get svc"]
        self.assertEqual(item["repetition"], 1)
        self.assertEqual(item["errors"], 0)

    def test_wrong_item_resurfaces_at_front(self):
        scheduler = srs.Scheduler()
        scheduler.record("kubectl get pods", correct=True, elapsed=1.0, time_limit=10, now=0)
        scheduler.record("kubectl get pods", correct=True, elapsed=1.0, time_limit=10, now=0)
        scheduler.record("kubectl scale", correct=False, elapsed=10.0, time_limit=10, now=0)
        nxt = scheduler.next_due(now=10 * srs.DAY_SECONDS)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt["key"], "kubectl scale")

    def test_seed_only_reviews_once(self):
        scheduler = srs.Scheduler()
        scheduler.seed("kubectl run", now=0)
        scheduler.seed("kubectl run", now=0)
        self.assertEqual(scheduler.items["kubectl run"]["reviews"], 1)


if __name__ == "__main__":
    unittest.main()
