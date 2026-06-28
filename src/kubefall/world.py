"""Scaffolds the text-only capture fixtures the debugging zones reference.

kubefall's solve battles do not need a filesystem dungeon: the creation zones are
verified by kubectl --dry-run, which is self-contained, and the debugging and
triage zones are honor-system reasoning chains. What they do need is a few fake
command outputs to read, in the spirit of rootfall's captured ss.txt: a
CrashLoopBackOff pod listing, a describe with events, a crashed container's
previous logs, and a cluster event stream.

Everything is written under world/ only and never touches a real cluster or the
real filesystem. There is no live Kubernetes anywhere in kubefall.
"""

import os

# All captures live together under a single directory so a zone can point at one
# place and tests have a stable home to assert against.
CAPTURE_DIR = "captures"

# A pod listing where one pod is wedged in CrashLoopBackOff. Zones 5 and 6 read
# this as the opening symptom of the triage scenario.
_GET_PODS_CRASHLOOP = (
    "NAME                     READY   STATUS             RESTARTS      AGE\n"
    "web-7c9f8b6d4-2xkqr      1/1     Running            0             4h\n"
    "web-7c9f8b6d4-7m2pn      0/1     CrashLoopBackOff   8 (20s ago)   12m\n"
    "api-5d4c7b9f8-q4xzl      1/1     Running            0             4h\n"
    "cache-0                  1/1     Running            0             4h\n"
)

# A describe of the crashing pod, trimmed to the Events block that matters. The
# events point at a container that starts and then exits non-zero, the signature
# of a CrashLoopBackOff caused by the app itself, not by image pull or scheduling.
_DESCRIBE_WEB_EVENTS = (
    "Name:             web-7c9f8b6d4-7m2pn\n"
    "Namespace:        default\n"
    "Status:           Running\n"
    "Containers:\n"
    "  web:\n"
    "    Image:          web:1.4.2\n"
    "    State:          Waiting\n"
    "      Reason:       CrashLoopBackOff\n"
    "    Last State:     Terminated\n"
    "      Reason:       Error\n"
    "      Exit Code:    1\n"
    "Events:\n"
    "  Type     Reason     Age                 From     Message\n"
    "  ----     ------     ----                ----     -------\n"
    "  Normal   Pulled     12m                 kubelet  Container image web:1.4.2 already present\n"
    "  Normal   Created    12m (x4 over 12m)   kubelet  Created container web\n"
    "  Normal   Started    12m (x4 over 12m)   kubelet  Started container web\n"
    "  Warning  BackOff    2m (x44 over 12m)   kubelet  Back-off restarting failed container\n"
)

# The previous container's logs: the app died because a required config value was
# missing. This is what `kubectl logs --previous` surfaces after a restart.
_LOGS_WEB_PREVIOUS = (
    "2026-06-28T00:00:01Z INFO  starting web v1.4.2\n"
    "2026-06-28T00:00:01Z INFO  reading configuration\n"
    "2026-06-28T00:00:01Z FATAL required environment variable DATABASE_URL is not set\n"
    "2026-06-28T00:00:01Z FATAL config came from configmap web-config, key DATABASE_URL missing\n"
    "panic: configuration error: DATABASE_URL\n"
)

# A cluster event stream for the triage zone, newest last. It ties the restarts
# back to the same pod the listing flagged.
_GET_EVENTS = (
    "LAST SEEN   TYPE      REASON      OBJECT                          MESSAGE\n"
    "12m         Normal    Scheduled   pod/web-7c9f8b6d4-7m2pn         Successfully assigned default pod\n"
    "12m         Normal    Pulled      pod/web-7c9f8b6d4-7m2pn         Container image already present\n"
    "12m         Normal    Created     pod/web-7c9f8b6d4-7m2pn         Created container web\n"
    "2m          Warning   BackOff     pod/web-7c9f8b6d4-7m2pn         Back-off restarting failed container\n"
)

_CAPTURES = {
    "get_pods_crashloop.txt": _GET_PODS_CRASHLOOP,
    "describe_web_events.txt": _DESCRIBE_WEB_EVENTS,
    "logs_web_previous.txt": _LOGS_WEB_PREVIOUS,
    "get_events.txt": _GET_EVENTS,
}


def build_world(root="world"):
    """Create (or top up) the capture fixtures. Idempotent and safe on boot.

    Mirrors rootfall's build_world signature so the engine can call it unchanged.
    kubefall writes nothing but text files under world/captures.
    """
    capture_root = os.path.join(root, CAPTURE_DIR)
    os.makedirs(capture_root, exist_ok=True)
    for name, body in _CAPTURES.items():
        path = os.path.join(capture_root, name)
        if not os.path.exists(path):
            with open(path, "w") as handle:
                handle.write(body)
    return root


def capture_path(name, root="world"):
    """Path to one named capture, for reference and tests."""
    return os.path.join(root, CAPTURE_DIR, name)


def expected_fixtures(root="world"):
    """Capture fixtures each zone references, keyed by zone id, for tests.

    Only the two debugging zones reference captures; the four creation zones are
    verified by kubectl --dry-run and seed no world files, so they are absent
    here on purpose (the same way rootfall omits its player-built zone).
    """
    return {
        "zone05_debugging": [
            capture_path("get_pods_crashloop.txt", root),
            capture_path("describe_web_events.txt", root),
        ],
        "zone06_cluster_triage": [
            capture_path("get_pods_crashloop.txt", root),
            capture_path("logs_web_previous.txt", root),
            capture_path("get_events.txt", root),
        ],
    }
