"""
The movie queue (PeterPiper 1.1): several .nd2 files chosen at once and analysed
one after another by hand - draw / check ROIs, SAVE, export, then Next movie.
Kept per user in queue.json (userprefs), so it survives closing the app.

Each item: {"nd2": path, "status": "todo" | "saved" | "exported" | "skipped"}.
"""
from __future__ import annotations

import os
from typing import List, Optional

from . import events, userprefs

_TOPIC = "queue"
STATUSES = ("todo", "saved", "exported", "skipped")


def _key(p: str) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def items() -> List[dict]:
    out = []
    for it in userprefs.load(_TOPIC).get("items", []):
        if isinstance(it, dict) and it.get("nd2"):
            st = it.get("status") if it.get("status") in STATUSES else "todo"
            out.append({"nd2": str(it["nd2"]), "status": st})
    return out


def _save(its: List[dict]) -> None:
    userprefs.update(_TOPIC, items=its)
    events.emit("queue_changed")


def set_items(paths) -> None:
    """A new queue (keeps the status of files that were already in it)."""
    old = {_key(it["nd2"]): it["status"] for it in items()}
    seen, its = set(), []
    for p in paths:
        k = _key(p)
        if k not in seen:
            seen.add(k)
            its.append({"nd2": str(p), "status": old.get(k, "todo")})
    _save(its)


def add(paths) -> None:
    set_items([it["nd2"] for it in items()] + [str(p) for p in paths])


def remove(nd2: str) -> None:
    _save([it for it in items() if _key(it["nd2"]) != _key(nd2)])


def clear() -> None:
    _save([])


def mark(nd2: str, status: str) -> None:
    """status for a file in the queue; 'saved' never downgrades 'exported'."""
    if status not in STATUSES:
        raise ValueError(status)
    its = items()
    for it in its:
        if _key(it["nd2"]) == _key(nd2):
            if not (status == "saved" and it["status"] == "exported"):
                it["status"] = status
    _save(its)


def position(nd2: str) -> Optional[tuple]:
    """(1-based index, total) of a file in the queue, or None."""
    its = items()
    for i, it in enumerate(its):
        if _key(it["nd2"]) == _key(nd2):
            return i + 1, len(its)
    return None


def next_after(nd2: Optional[str] = None) -> Optional[str]:
    """The next file still to do after nd2 (wrapping round), or None."""
    its = items()
    if not its:
        return None
    start = 0
    if nd2:
        for i, it in enumerate(its):
            if _key(it["nd2"]) == _key(nd2):
                start = i + 1
                break
    for j in range(len(its)):
        it = its[(start + j) % len(its)]
        if it["status"] == "todo" and (not nd2 or _key(it["nd2"]) != _key(nd2)):
            return it["nd2"]
    return None
