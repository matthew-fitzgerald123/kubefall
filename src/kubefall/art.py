"""ASCII sprite data for all 8 zones.

Each zone entry has:
  "zone_color": int   ANSI 256 fg color for zone UI chrome
  "zone_dim":   int   ANSI 256 dimmed/secondary color
  "villager":   dict  {name, lines, primary, accents}
  "enemy":      dict  {name, lines, primary, accents}

Sprite format:
  "lines":   list of exactly 13 strings, each exactly 18 chars wide
  "primary": int   ANSI 256 fg color for most lines
  "accents": dict  {line_index (int): ANSI 256 color}
  "name":    str   display name
"""

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _pad(s):
    """Pad or trim a string to exactly 18 characters."""
    if len(s) >= 18:
        return s[:18]
    return s + " " * (18 - len(s))


def _sprite(name, primary, accents, *lines):
    """Build a sprite dict from raw line strings (exactly 13 required)."""
    assert len(lines) == 13, "sprite {!r} has {} lines, expected 13".format(name, len(lines))
    return {
        "name": name,
        "primary": primary,
        "accents": {int(k): v for k, v in accents.items()},
        "lines": [_pad(ln) for ln in lines],
    }


# ---------------------------------------------------------------------------
# Zone 01  Pods  (zone_color=51  zone_dim=237)
# ---------------------------------------------------------------------------

_z01_villager = _sprite(
    "The Scheduler", 51,
    {0: 231, 1: 231, 5: 51, 6: 51},
    #         123456789012345678
    "   .--CONTROL--.   ",
    "  /  [PLANE]    \\  ",
    " |  .---------.  | ",
    " |  | (o) (o) |  | ",
    " |  |   ___   |  | ",
    "  \\ |  [===]  | /  ",
    "   '+---------+'   ",
    "    |    |    |    ",
    "    |  .-+-,  |    ",
    "    | /  |  \\ |    ",
    "    |/ POD \\  |    ",
    "    |\\_____|  |    ",
    "   (__)   (__)     ",
)

_z01_enemy = _sprite(
    "CrashPod", 196,
    {1: 196, 2: 196, 5: 208, 6: 208, 10: 226, 11: 226},
    #         123456789012345678
    "   .------------.  ",
    "  !! 0/1 RUNNING!! ",
    "  !!  Exit: 1   !! ",
    "   '------------'  ",
    "    |  .-~~~.  |   ",
    "    | /BackOf\\ |   ",
    "    |/ f:  3x \\|   ",
    "    |  CrashLp |   ",
    "    |  ~~~~~~  |   ",
    "   /|  ERROR!  |\\  ",
    "  / | [OOMKill]| \\ ",
    " /  |__________|  \\",
    "    '----------'   ",
)

# ---------------------------------------------------------------------------
# Zone 02  Deployments  (zone_color=33  zone_dim=237)
# ---------------------------------------------------------------------------

_z02_villager = _sprite(
    "The Operator", 33,
    {0: 231, 1: 231, 6: 33, 7: 33, 8: 33},
    #         123456789012345678
    "  .--DEPLOY---.   ",
    "  |[=========]|   ",
    "  |  .------.  |  ",
    "  |  |RS x3 |  |  ",
    "  |  '------'  |  ",
    "  |  .------.  |  ",
    "  |  | pod  |  |  ",
    "  |  | pod  |  |  ",
    "  |  | pod  |  |  ",
    "  |  '------'  |  ",
    "  |[==READY===]|  ",
    "   '----------'   ",
    "   (_)      (_)   ",
)

_z02_enemy = _sprite(
    "StuckRollout", 202,
    {0: 196, 1: 196, 5: 208, 6: 208, 9: 226, 10: 226},
    #         123456789012345678
    " .--ROLLOUT-----. ",
    " |! 2/5 READY  !| ",
    " |  old: [===]  | ",
    " |  new: [=..] ?| ",
    " | no progress  | ",
    " |>--> STUCK -->| ",
    " |  deadline!   | ",
    " |  exceeded    | ",
    " |  waiting...  | ",
    " |!! check RS !!| ",
    " |!! check pod!!| ",
    " '---------------'",
    "  (_)         (_) ",
)

# ---------------------------------------------------------------------------
# Zone 03  Services  (zone_color=46  zone_dim=237)
# ---------------------------------------------------------------------------

_z03_villager = _sprite(
    "The Routist", 46,
    {0: 231, 1: 231, 5: 46, 6: 46, 7: 46},
    #         123456789012345678
    "   .--SERVICE--.  ",
    "   | ClusterIP  | ",
    "   |  .------.  | ",
    "  =+=>|  LB   |=+=>",
    "   |  |router |  | ",
    "   |  '---+---'  | ",
    "   |      |      | ",
    "  pod    pod    pod",
    "   |  .------.  | ",
    "   |  |:8080  |  | ",
    "   |  |:443   |  | ",
    "   |  '------'  | ",
    "  (__)        (__)",
)

_z03_enemy = _sprite(
    "BrokenService", 196,
    {0: 196, 1: 196, 4: 208, 5: 208, 9: 226, 10: 226},
    #         123456789012345678
    "   .--SERVICE--.  ",
    "   |!! ERROR !!|  ",
    "   |  .------.  | ",
    "   |  |  X   |  | ",
    "   |  | disc. |  | ",
    "   |  |0 endp.|  | ",
    "   |  '------'  | ",
    "   |   no pods   | ",
    "   |  matched!   | ",
    "   |!! check !! | ",
    "   |!! selctor!!| ",
    "   '------------' ",
    "  (__)        (__)",
)

# ---------------------------------------------------------------------------
# Zone 04  Config  (zone_color=226  zone_dim=237)
# ---------------------------------------------------------------------------

_z04_villager = _sprite(
    "The Archivist", 226,
    {0: 231, 1: 231, 5: 226, 6: 226, 9: 220, 10: 220},
    #         123456789012345678
    "   .--CONFIGS--.  ",
    "   |  ARCHIVE  |  ",
    "   |  .------, | ",
    "   |  | CM:  | | ",
    "   |  | key= | | ",
    "   |  | val  | | ",
    "   |  '------' | ",
    "   |  .------. | ",
    "   |  |SECRET| | ",
    "   |  |b64=**| | ",
    "   |  '------' | ",
    "   '------------' ",
    "  (__)        (__)",
)

_z04_enemy = _sprite(
    "MissingConfig", 196,
    {0: 196, 1: 196, 4: 208, 5: 208, 9: 226, 10: 226},
    #         123456789012345678
    "   .--CONFIGMAP. ",
    "   |!KEY MISSING| ",
    "   |  .------. | ",
    "   |  |  ???  | | ",
    "   |  |DATABS | | ",
    "   |  |E_URL  | | ",
    "   |  | not   | | ",
    "   |  | found | | ",
    "   |  '------' | ",
    "   |!! crash !!| ",
    "   |!! loop  !!| ",
    "   '------------' ",
    "  (__)        (__)",
)

# ---------------------------------------------------------------------------
# Zone 05  Debugging  (zone_color=208  zone_dim=237)
# ---------------------------------------------------------------------------

_z05_villager = _sprite(
    "The Medic", 208,
    {0: 231, 1: 231, 5: 46, 6: 46, 9: 208, 10: 208},
    #         123456789012345678
    "   .---MEDIC---.  ",
    "   |  [+] [+]  |  ",
    "   |  .-----.  |  ",
    "   |  |diag |  |  ",
    "   |  | log |  |  ",
    "   |  |tools|  |  ",
    "   |  [+][+][+]|  ",
    "   |  '-----'  |  ",
    "   |  .-----.  |  ",
    "   |  |check|  |  ",
    "   |  |event|  |  ",
    "   '------------' ",
    "  (__)        (__)",
)

_z05_enemy = _sprite(
    "CrashLoop", 196,
    {0: 196, 1: 196, 4: 208, 5: 208, 8: 226, 9: 226},
    #         123456789012345678
    "   .--CRASHLOOP.  ",
    "   |!BACKOFF   !| ",
    "   |  .------.  | ",
    "   |  | -->  |  | ",
    "   |  | spin |  | ",
    "   |  | <--  |  | ",
    "   |  '------'  | ",
    "   |  restart#5 | ",
    "   |  in: 5m10s | ",
    "   |!! OOMKill!!| ",
    "   |!! Err:137 !!| ",
    "   '------------' ",
    "  (__)        (__)",
)

# ---------------------------------------------------------------------------
# Zone 06  Cluster Triage  (zone_color=196  zone_dim=237)
# ---------------------------------------------------------------------------

_z06_villager = _sprite(
    "The Chief", 196,
    {0: 231, 1: 231, 5: 196, 6: 196, 9: 208, 10: 208},
    #         123456789012345678
    "  .--CMD CENTER.  ",
    "  | TRIAGE CHIEF| ",
    "  |  .-------.  | ",
    "  |  |STEP 1:|  | ",
    "  |  |getpods|  | ",
    "  |  |STEP 2:|  | ",
    "  |  |describ|  | ",
    "  |  |STEP 3:|  | ",
    "  |  |  logs |  | ",
    "  |  |STEP 4:|  | ",
    "  |  |events |  | ",
    "  '-------------' ",
    "  (__)       (__) ",
)

_z06_enemy = _sprite(
    "Outage", 196,
    {0: 196, 1: 196, 3: 196, 4: 196, 7: 208, 8: 208, 11: 226},
    #         123456789012345678
    "  !!  OUTAGE  !!  ",
    "  !! 0/10 RDY !!  ",
    "  .------------.  ",
    "  |!! FIRE   !!|  ",
    "  |!! FIRE   !!|  ",
    "  |  all pods  |  ",
    "  |  crashing  |  ",
    "  |!! ALERT  !!|  ",
    "  |!! ALERT  !!|  ",
    "  |  svc down  |  ",
    "  |  no endpts |  ",
    "  |!! 503 503!!|  ",
    "  '------------'  ",
)

# ---------------------------------------------------------------------------
# Zone 07  Namespaces  (zone_color=135  zone_dim=237)
# ---------------------------------------------------------------------------

_z07_villager = _sprite(
    "The Navigator", 135,
    {0: 231, 1: 231, 5: 135, 6: 135, 9: 141, 10: 141},
    #         123456789012345678
    "  .--NAVIGATOR-.  ",
    "  | [COMPASS]  |  ",
    "  |  .------.  |  ",
    "  |  |  N   |  |  ",
    "  |  |W-+-E |  |  ",
    "  |  |  S   |  |  ",
    "  |  '------'  |  ",
    "  |  ns: dev   |  ",
    "  |  ns: prod  |  ",
    "  |  ns: stage |  ",
    "  | ctx: local |  ",
    "  '------------'  ",
    "  (__)       (__) ",
)

_z07_enemy = _sprite(
    "ContextMismatch", 196,
    {0: 196, 1: 196, 4: 208, 5: 208, 9: 226, 10: 226},
    #         123456789012345678
    "  !! WRONG CTX !! ",
    "  !! YOU ARE   !! ",
    "  .------------.  ",
    "  | IN  PROD!! |  ",
    "  | not local  |  ",
    "  | not staging |  ",
    "  | not dev     |  ",
    "  | PROD PROD   |  ",
    "  | bad context |  ",
    "  |!! check !! |  ",
    "  |!! ctx now!!|  ",
    "  '------------'  ",
    "  (__)       (__) ",
)

# ---------------------------------------------------------------------------
# Zone 08  Apply & RBAC  (zone_color=220  zone_dim=237)
# ---------------------------------------------------------------------------

_z08_villager = _sprite(
    "The Gatekeeper", 220,
    {0: 231, 1: 231, 5: 220, 6: 220, 9: 226, 10: 226},
    #         123456789012345678
    "  .---RBAC GATE.  ",
    "  | [SHIELD]    | ",
    "  |  .-------.  | ",
    "  |  |Role:  |  | ",
    "  |  |get,   |  | ",
    "  |  |list,  |  | ",
    "  |  |create |  | ",
    "  |  '-------'  | ",
    "  |  RoleBind:  | ",
    "  |  sa->role   | ",
    "  |  .-------.  | ",
    "  '-------------' ",
    "  (__)       (__) ",
)

_z08_enemy = _sprite(
    "RBACDenied", 196,
    {0: 196, 1: 196, 3: 196, 4: 196, 8: 208, 9: 208, 11: 226},
    #         123456789012345678
    "  !! 403 FORBID!! ",
    "  !! DENIED    !! ",
    "  .------------.  ",
    "  |!! no role !!|  ",
    "  |!! bound   !!|  ",
    "  |  cannot    |  ",
    "  |  get pods  |  ",
    "  |  in ns web |  ",
    "  |!! check !! |  ",
    "  |!! SA bind!!|  ",
    "  |  no perms  |  ",
    "  |!! 403 403!!|  ",
    "  '------------'  ",
)

# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

SPRITES = {
    "zone01_pods": {
        "zone_color": 51,
        "zone_dim": 237,
        "villager": _z01_villager,
        "enemy": _z01_enemy,
    },
    "zone02_deployments": {
        "zone_color": 33,
        "zone_dim": 237,
        "villager": _z02_villager,
        "enemy": _z02_enemy,
    },
    "zone03_services": {
        "zone_color": 46,
        "zone_dim": 237,
        "villager": _z03_villager,
        "enemy": _z03_enemy,
    },
    "zone04_config": {
        "zone_color": 226,
        "zone_dim": 237,
        "villager": _z04_villager,
        "enemy": _z04_enemy,
    },
    "zone05_debugging": {
        "zone_color": 208,
        "zone_dim": 237,
        "villager": _z05_villager,
        "enemy": _z05_enemy,
    },
    "zone06_cluster_triage": {
        "zone_color": 196,
        "zone_dim": 237,
        "villager": _z06_villager,
        "enemy": _z06_enemy,
    },
    "zone07_namespaces": {
        "zone_color": 135,
        "zone_dim": 237,
        "villager": _z07_villager,
        "enemy": _z07_enemy,
    },
    "zone08_apply_rbac": {
        "zone_color": 220,
        "zone_dim": 237,
        "villager": _z08_villager,
        "enemy": _z08_enemy,
    },
}


def get_villager(zone_id: str) -> dict:
    return SPRITES.get(zone_id, SPRITES["zone01_pods"])["villager"]


def get_enemy(zone_id: str) -> dict:
    return SPRITES.get(zone_id, SPRITES["zone01_pods"])["enemy"]


def get_zone_colors(zone_id: str) -> tuple:
    z = SPRITES.get(zone_id, SPRITES["zone01_pods"])
    return z["zone_color"], z["zone_dim"]
