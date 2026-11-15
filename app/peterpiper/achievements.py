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
    get / put                 -> small extra values an extra wants to keep
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from . import events, userprefs

_TOPIC = "achievements"

# Every hidden extra, with the words shown once it is found (never before).
CATALOGUE: Dict[str, str] = {
    "palettes": "Colour palettes - you clicked the piper 20 times in a row.",
    "charlotte": "Charlotte's Web - a web for every movie you analyse.",
}


def found() -> Dict[str, str]:
    return dict(userprefs.load(_TOPIC).get("found", {}))


def unlocked(key: str) -> bool:
    return key in found()


def unlock(key: str) -> bool:
    d = userprefs.load(_TOPIC)
    f = d.setdefault("found", {})
    if key in f:
        return False
    f[key] = datetime.now().isoformat(timespec="seconds")
    userprefs.save(_TOPIC, d)
    events.emit("achievement", key=key)
    return True


def get(key: str, default: Any = None) -> Any:
    return userprefs.load(_TOPIC).get("extra", {}).get(key, default)


def put(key: str, value: Any) -> None:
    d = userprefs.load(_TOPIC)
    d.setdefault("extra", {})[key] = value
    userprefs.save(_TOPIC, d)
