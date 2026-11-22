"""
Small per-user preference files (PeterPiper 1.1): one JSON file per topic in the
current user's own folder (users.home()), e.g. storage.json, queue.json,
achievements.json. Nothing else is read or written; no network.

    load("storage")            -> {} if the file is missing or unreadable
    save("storage", {...})     -> written in one step (temporary file, then swap)
    update("storage", key=v)   -> load, change, save; returns the new dict
    server_options() / set_server_option(key, v)   4.0: the lab folder options
                                  (server.json; defaults in SERVER_DEFAULTS)

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


# ---- 4.0: the lab folder options (per user, server.json)
SERVER_TOPIC = "server"
SERVER_DEFAULTS = {
    "upload_movies": False,        # analysed .nd2 -> People/<me>/Movies (big files)
    "upload_exports": True,        # exports -> People/<me>/Exports (when connected)
    "upload_saves": True,          # SAVEs and autosaves -> People/<me>/Results
    "backup_on_close": True,       # profile + settings + run list -> People/<me>/Backups
    "backup_daily": True,
    "cache_dir": "",               # '' = <PeterPiper data>/Movie cache
    "cache_limit_gb": 0.0,         # 0 = automatic: 50 GB or 20% of the free disk
    "prefetch": True,              # fetch the next movie of the queue while I work
}


def server_options() -> dict:
    """The lab folder options of the current user, with the defaults filled in."""
    d = load(SERVER_TOPIC)
    out = dict(SERVER_DEFAULTS)
    for k, v in d.items():
        if k not in SERVER_DEFAULTS:
            out[k] = v                     # other values kept there (e.g. last backup)
            continue
        dv = SERVER_DEFAULTS[k]
        if isinstance(dv, bool):
            good = isinstance(v, bool)
        elif isinstance(dv, float):
            good = isinstance(v, (int, float)) and not isinstance(v, bool)
        else:
            good = isinstance(v, type(dv))
        if good:
            out[k] = float(v) if isinstance(dv, float) else v
    return out


def server_option(key: str):
    return server_options().get(key, SERVER_DEFAULTS.get(key))


def set_server_option(key: str, value) -> dict:
    """Change one option (or a value kept with them, e.g. 'last_backup')."""
    if key in SERVER_DEFAULTS:
        kind = type(SERVER_DEFAULTS[key])
        value = float(value) if kind is float else kind(value)
    return update(SERVER_TOPIC, **{key: value})


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
