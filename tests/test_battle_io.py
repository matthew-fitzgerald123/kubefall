"""Tests for the timed_input stdin desync fix.

After a recall times out, the player may press Enter just after the timer
fires. That line stays buffered in stdin and the next prompt's select sees it
immediately, grading the stale answer against the wrong question. These tests
verify that the _pending_drain / _drain_stdin mechanism prevents the desync.
"""

import io
import os
import select
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from contextlib import redirect_stdout

from kubefall import battle


def _pipe():
    r_fd, w_fd = os.pipe()
    return os.fdopen(r_fd, "r"), w_fd


class DrainStdinTests(unittest.TestCase):
    def test_drain_discards_buffered_line(self):
        """_drain_stdin must consume a complete line already waiting in stdin."""
        r_file, w_fd = _pipe()
        os.write(w_fd, b"stale input\n")
        orig = sys.stdin
        sys.stdin = r_file
        try:
            battle._drain_stdin(0)
            ready, _, _ = select.select([r_file], [], [], 0)
            self.assertEqual(ready, [], "buffer must be empty after drain")
        finally:
            sys.stdin = orig
            r_file.close()
            os.close(w_fd)

    def test_drain_noop_when_nothing_buffered(self):
        """_drain_stdin must return immediately when stdin has no data."""
        r_file, w_fd = _pipe()
        orig = sys.stdin
        sys.stdin = r_file
        try:
            before = time.monotonic()
            battle._drain_stdin(0)
            self.assertLess(time.monotonic() - before, 0.1,
                            "should return immediately on empty buffer")
        finally:
            sys.stdin = orig
            r_file.close()
            os.close(w_fd)


class TimedInputTimeoutTests(unittest.TestCase):
    def test_timeout_sets_pending_drain_flag(self):
        """timed_input must set _pending_drain to True when it times out."""
        r_file, w_fd = _pipe()
        orig_stdin = sys.stdin
        orig_flag = battle._pending_drain
        sys.stdin = r_file
        battle._pending_drain = False
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                _, _, timed_out = battle.timed_input("test", 0.05)
            self.assertTrue(timed_out)
            self.assertTrue(battle._pending_drain,
                            "_pending_drain must be True after a timeout")
        finally:
            sys.stdin = orig_stdin
            battle._pending_drain = orig_flag
            r_file.close()
            os.close(w_fd)

    def test_desync_fix_stale_input_discarded(self):
        """When _pending_drain is True, timed_input drains the stale line before
        reading the next answer, so the correct answer is graded, not the one
        the player typed too late."""
        r_file, w_fd = _pipe()

        # Simulate a player pressing Enter just after the previous timeout.
        os.write(w_fd, b"wrong stale answer\n")

        # The real answer arrives after the drain window finishes (~0.2 s).
        def write_real():
            time.sleep(0.4)
            os.write(w_fd, b"kubectl get pods\n")

        t = threading.Thread(target=write_real, daemon=True)
        t.start()

        orig_stdin = sys.stdin
        orig_flag = battle._pending_drain
        sys.stdin = r_file
        battle._pending_drain = True   # simulate a previous timeout
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                answer, _, timed_out = battle.timed_input("test prompt", 5)
            self.assertFalse(timed_out)
            self.assertEqual(answer, "kubectl get pods",
                             "fresh answer must be read, not the stale one")
            self.assertFalse(battle._pending_drain,
                             "_pending_drain must be cleared after draining")
        finally:
            t.join(timeout=6)
            sys.stdin = orig_stdin
            battle._pending_drain = orig_flag
            r_file.close()
            os.close(w_fd)


if __name__ == "__main__":
    unittest.main()
