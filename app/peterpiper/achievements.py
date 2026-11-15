"""
Hidden extras ("easter eggs") and achievements - PeterPiper 1.1.

For anyone reading the code: this is harmless fun. It only remembers which
hidden extras a user has found, in achievements.json in that user's own
PeterPiper folder (see userprefs.py). It never touches analysis results, never
changes a number, and never uses the network. Deleting achievements.json
simply hides the extras again.

    unlocked("palettes")      -> True / False
    unlock("palettes")        -> True the first time (newly found), else False
    found()                   -> {key: ISO date found}
    hidden_count()            -> how many extras of CATALOGUE are still hidden
    get / put                 -> small extra values an extra wants to keep
    REQUIRES                  -> {extra: the extra that must be found first}
    set_target_user(name)     -> 'Who is using PeterPiper?': the user selected there
    name_flair(user)          -> how that user's name is decorated in the user list
                                 (a crown; a little web flair for Charlotte's webs)

Whose extras: the current user's (users.current()). Before anyone is chosen - the
logo in "Who is using PeterPiper?" can be clicked too - an extra goes to the user
selected in that list (set_target_user), or, with nobody selected, into a
computer-level "pending" set that the next user to start takes over
(_claim_pending, done lazily by found() / unlock()).
"""
from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any, Dict, Optional

from . import events, userprefs

_TOPIC = "achievements"

# Every hidden extra, with the words shown once it is found (never before).
CATALOGUE: Dict[str, str] = {
    "palettes": "Colour palettes - you clicked the piper 20 times in a row.",
    "charlotte": "Charlotte's Web - a web for every movie you analyse.",
    "crown": "A crown before your name - the piper clicked 100 times in a row "
             "(or his name typed).",
}

# An extra that can only be found once another one has been (that part checks it).
REQUIRES: Dict[str, str] = {"charlotte": "palettes"}

_target: Optional[str] = None          # the user selected in 'Who is using PeterPiper?'


def set_target_user(name: Optional[str]) -> None:
    """'Who is using PeterPiper?' tells which user is selected in its list (None:
    nobody), so an extra found there (before anyone has started) is theirs."""
    global _target
    from . import users
    _target = users.clean_name(name) if name and str(name).strip() else None


# ------------------------------------------------------------------ the store
def _who() -> Optional[str]:
    """The user whose extras are read / written now (None: the computer-level
    pending set)."""
    from . import users
    return users.current() or _target


def _load() -> dict:
    from . import users
    if users.current() or not _target:
        return userprefs.load(_TOPIC)          # the current user's, or <data> itself
    return userprefs.load_for(_target, _TOPIC)


def _save(d: dict) -> None:
    from . import users
    if users.current() or not _target:
        userprefs.save(_TOPIC, d)
    else:
        userprefs.save_for(_target, _TOPIC, d)


def _claim_pending() -> None:
    """Extras found while no user was chosen (and nobody selected) belong to the
    user who starts next: move them into that user's file and clear them from the
    computer-level one."""
    from . import users
    if not users.current():
        return
    shared = users.base_dir() / f"{_TOPIC}.json"
    try:
        base = json.loads(shared.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    pending = base.get("pending") if isinstance(base, dict) else None
    if not pending or not isinstance(pending, dict):
        return
    d = userprefs.load(_TOPIC)
    f = d.setdefault("found", {})
    for k, when in pending.items():
        f.setdefault(str(k), str(when))
    userprefs.save(_TOPIC, d)
    for k in pending:
        base.get("found", {}).pop(k, None)
    base.pop("pending", None)
    try:
        tmp = shared.with_name(shared.name + ".tmp")
        tmp.write_text(json.dumps(base, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(shared)
    except OSError:
        pass


def found() -> Dict[str, str]:
    try:
        _claim_pending()
    except Exception:                                              # noqa: BLE001
        pass
    return dict(_load().get("found", {}))


def unlocked(key: str) -> bool:
    return key in found()


def hidden_count() -> int:
    """How many extras of the catalogue this user has not found yet."""
    f = found()
    return sum(1 for k in CATALOGUE if k not in f)


def unlock(key: str) -> bool:
    found()                                     # take over anything found before
    d = _load()
    f = d.setdefault("found", {})
    if key in f:
        return False
    f[key] = datetime.now().isoformat(timespec="seconds")
    if _who() is None:                          # nobody chosen or selected: for the next user
        d.setdefault("pending", {})[key] = f[key]
    _save(d)
    events.emit("achievement", key=key)
    return True


def get(key: str, default: Any = None) -> Any:
    return _load().get("extra", {}).get(key, default)


def put(key: str, value: Any) -> None:
    d = _load()
    d.setdefault("extra", {})[key] = value
    _save(d)


def found_for(user: str) -> Dict[str, str]:
    """The extras another user has found (read-only)."""
    from . import users
    if users.current() and users.clean_name(user) == users.current():
        return found()
    return dict(userprefs.load_for(user, _TOPIC).get("found", {}))


# ------------------------------------------------------------- the user list
CROWN = "\U0001F451 "                           # a crown, before the name
# Little pictures after the name for Charlotte's webs - picked at random each
# time the list is shown, from a set that grows with the collection.
WEB_EMOJI = {
    1: ("\U0001F578\ufe0f", "\U0001F577\ufe0f"),                                  # web, spider
    2: ("\U0001F578\ufe0f", "\U0001F577\ufe0f", "\U0001F319", "\U0001F340", "\U0001F338"),
    3: ("\U0001F578\ufe0f", "\u2728", "\U0001F4AB", "\u2b50", "\U0001F338", "\u26a1",
        "\U0001F340"),
    4: ("\U0001F48E", "\u2728", "\U0001F4AB", "\u2b50", "\u26a1", "\U0001F578\ufe0f",
        "\U0001F31F"),
}
SPARKLE = "\u2728"
# tier: (hue in degrees, saturation) of the name's colour - more vivid each tier
_TIER_TINT = {2: (270.0, 0.55), 3: (300.0, 0.80), 4: (320.0, 1.00)}


def web_tier(webs: int) -> int:
    """0: no webs, 1: 1-2, 2: 3-9, 3: 10-24, 4: 25 or more."""
    w = int(webs or 0)
    return 0 if w <= 0 else 1 if w <= 2 else 2 if w <= 9 else 3 if w <= 24 else 4


def web_count(user: str) -> int:
    """How many Charlotte's webs a user has collected (the charlotte part keeps
    them in that user's charlotte.json, key "collection")."""
    try:
        col = userprefs.load_for(user, "charlotte").get("collection", [])
        return len(col) if isinstance(col, (list, tuple, dict)) else 0
    except Exception:                                              # noqa: BLE001
        return 0


def name_flair(user: str, rng: Optional[random.Random] = None) -> Dict[str, Any]:
    """How to show `user`'s name in 'Who is using PeterPiper?':
    {"prefix", "suffix", "bold", "colour" (None or '#RRGGBB', readable on the
    current theme's list), "tier"}. Show it as prefix + name + suffix.

    A crown before the name once "crown" is found (for good). Charlotte's webs:
    0 nothing; 1-2 a small web / spider after the name; 3-9 and a colour; 10-24
    bold and a brighter colour; 25+ bold, the brightest colour, sparkles on both
    ends. The little picture is chosen at random each call (it changes each time
    the list is shown)."""
    rng = rng or random
    out: Dict[str, Any] = {"prefix": "", "suffix": "", "bold": False, "colour": None,
                           "tier": 0}
    try:
        if "crown" in found_for(user):
            out["prefix"] = CROWN
    except Exception:                                              # noqa: BLE001
        pass
    tier = web_tier(web_count(user))
    out["tier"] = tier
    if tier == 0:
        return out
    emoji = rng.choice(WEB_EMOJI[tier])
    out["suffix"] = " " + emoji
    if tier >= 3:
        out["bold"] = True
    if tier == 4:
        out["prefix"] += SPARKLE + " "
        out["suffix"] += " " + SPARKLE
    if tier >= 2:
        try:
            from .gui import theme as TH
            hue, sat = _TIER_TINT[tier]
            out["colour"] = TH.readable_tint(hue, sat, TH.current())
        except Exception:                                          # noqa: BLE001
            out["colour"] = None                # no colour rather than a bad one
    return out
