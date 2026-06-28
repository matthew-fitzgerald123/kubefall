"""SM-2 spaced repetition, implemented from scratch with no dependencies.

This module is the one thing that survives death. It holds, per command, the
ease factor, interval, repetition count, and due time, plus a small error
history. The player never self-grades a recall: the battle layer converts answer
correctness and response time into an SM-2 quality score and hands it here.

Nothing is ever permanently learned. Even a long-interval item eventually comes
due again and resurfaces.
"""

import time

# SM-2 constants.
EASE_FLOOR = 1.3
DEFAULT_EASE = 2.5
DAY_SECONDS = 86400.0


def new_item(key, prompt="", answer=""):
    """Create a fresh, JSON-serializable SRS record for one command or flag."""
    return {
        "key": key,
        "prompt": prompt,
        "answer": answer,
        "ease": DEFAULT_EASE,
        "interval": 0,
        "repetition": 0,
        "last_reviewed": None,
        "due": 0.0,
        "reviews": 0,
        "errors": 0,
    }


def grade_response(correct, elapsed, time_limit):
    """Map correctness and response time onto an SM-2 quality score (0-5).

    Fast and correct stretches the interval. Slow but correct holds steady.
    Wrong or timed out scores below 3, which resets the repetition count and
    pulls the item back to the front of the queue.
    """
    if not correct:
        return 0
    if time_limit <= 0:
        # No timer on this battle (for example a solve). A reported success is
        # solid but not "instant recall" fast, so it lands mid-high.
        return 4
    ratio = elapsed / float(time_limit)
    if ratio <= 0.4:
        return 5
    if ratio <= 0.7:
        return 4
    return 3


def _update_ease(ease, quality):
    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return max(EASE_FLOOR, ease)


def review(item, quality, now=None):
    """Apply one SM-2 review to an item in place and return it.

    On quality < 3 the repetition resets and the interval shrinks back to 1 so
    the item resurfaces hot. The ease factor is always updated but is floored at
    1.3 and never drops below it.
    """
    now = time.time() if now is None else now
    quality = max(0, min(5, int(quality)))

    item["ease"] = _update_ease(item["ease"], quality)

    if quality < 3:
        item["repetition"] = 0
        item["interval"] = 1
        item["errors"] = item.get("errors", 0) + 1
    else:
        if item["repetition"] == 0:
            item["interval"] = 1
        elif item["repetition"] == 1:
            item["interval"] = 6
        else:
            item["interval"] = max(1, int(round(item["interval"] * item["ease"])))
        item["repetition"] += 1

    item["reviews"] = item.get("reviews", 0) + 1
    item["last_reviewed"] = now
    item["due"] = now + item["interval"] * DAY_SECONDS
    return item


class Scheduler:
    """A thin wrapper over a dict of SRS records.

    The dict is owned by the meta-state save so persistence is just a JSON dump.
    The scheduler only adds SM-2 logic and queue ordering on top of it.
    """

    def __init__(self, items=None):
        self.items = items if items is not None else {}

    def ensure(self, key, prompt="", answer=""):
        """Return the record for key, creating it on first sight."""
        if key not in self.items:
            self.items[key] = new_item(key, prompt, answer)
        else:
            # Keep the human-facing text fresh if the campaign changed it.
            if prompt:
                self.items[key]["prompt"] = prompt
            if answer:
                self.items[key]["answer"] = answer
        return self.items[key]

    def record(self, key, correct, elapsed=0.0, time_limit=0, now=None):
        """Grade a battle outcome and schedule the next review."""
        item = self.ensure(key)
        quality = grade_response(correct, elapsed, time_limit)
        return review(item, quality, now=now)

    def seed(self, key, prompt="", answer="", now=None):
        """Introduce a freshly taught command into the queue.

        A passed villager quiz seeds the command at a modest quality so it
        enters the rotation soon rather than being treated as mastered.
        """
        item = self.ensure(key, prompt, answer)
        if item["reviews"] == 0:
            review(item, 3, now=now)
        return item

    def due_items(self, now=None):
        now = time.time() if now is None else now
        ready = [i for i in self.items.values() if i["due"] <= now]
        return sorted(ready, key=lambda i: i["due"])

    def next_due(self, now=None):
        ready = self.due_items(now)
        return ready[0] if ready else None

    def is_due(self, key, now=None):
        """Unseen and overdue items are due. Stretched items are not."""
        now = time.time() if now is None else now
        item = self.items.get(key)
        return item is None or item["due"] <= now
