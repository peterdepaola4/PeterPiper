"""
Small per-user preference files (PeterPiper 1.1): one JSON file per topic in the
current user's own folder (users.home()), e.g. storage.json, queue.json,
achievements.json. Nothing else is read or written; no network.

    load("storage")            -> {} if the file is missing or unreadable
    save("storage", {...})     -> written in one step (temporary file, then swap)
    update("storage", key=v)   -> load, change, save; returns the new dict

Without a chosen user (tests, the very first start) the files go into
<PeterPiper data> itself (users.base_dir()).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


def _folder() -> Path:
    from . import users
    return users.home() if users.current() else users.base_dir()


def path(topic: str) -> Path:
    if not _NAME.match(topic):
        raise ValueError(f"not a preference topic: {topic!r}")
    return _folder() / f"{topic}.json"


def load(topic: str) -> dict:
    p = path(topic)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(topic: str, data: dict) -> None:
    p = path(topic)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def update(topic: str, **changes) -> dict:
    d = load(topic)
    d.update(changes)
    save(topic, d)
    return d


# ---- 1.1: another user's file (e.g. the user list shows each user's extras)
def path_for(user: str, topic: str) -> Path:
    """Where `user`'s file of this topic is (<data>/users/<their folder>)."""
    from . import users
    if not _NAME.match(topic):
        raise ValueError(f"not a preference topic: {topic!r}")
    return users.base_dir() / "users" / users._folder_of(users.clean_name(user)) / f"{topic}.json"


def load_for(user: str, topic: str) -> dict:
    """Read another user's preference file ({} if missing or unreadable). Read-only."""
    try:
        d = json.loads(path_for(user, topic).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_for(user: str, topic: str, data: dict) -> None:
    """Write a named user's file (used only for a hidden extra found in 'Who is
    using PeterPiper?' while that user is selected there)."""
    p = path_for(user, topic)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)
