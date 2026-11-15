"""
Smart auto-select (PeterPiper 1.1): one click that picks the cells the way YOU
pick them, learned from your own hand-drawn movies.

It is the V3.0 trained auto-detect (detectors.py: candidates, your answers, a rule
searched on fixed grids, an honest held-out score), trained automatically on the
movies you analysed BY HAND in a movie queue, so there is nothing to set up. The
detector it uses is written into the run and its Methods like any trained
auto-detect (name 'Smart auto-select', its rule and its held-out score). Plain
AUTO-DETECT is unchanged and always available.

How it is unlocked (it goes with the Charlotte's Web game: every movie you
draw by hand grows a web; this only stores which movies you drew by hand):
hand-draw cells on 3 or more movies from a movie queue and SAVE each.

Which movies count: a SAVE (event 'saved') of a movie that is in the movie queue
and on which at least one cell was added by hand since it was opened. They are
kept per user in smartselect.json (userprefs): the saved run file, the movie and
its channel names. No images are stored.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import achievements, events, userprefs

_TOPIC = "smartselect"
NEEDED = 3                      # hand-drawn queued movies needed
NAME = "Smart auto-select"

_manual: Dict[str, int] = {}    # this session: movie -> cells added by hand


def _key(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


# ------------------------------------------------------------------ tracking
def _on_opened(nd2=None, **_kw) -> None:
    if nd2:
        _manual[_key(nd2)] = 0


def _on_roi(nd2=None, manual=False, **_kw) -> None:
    if nd2 and manual:
        _manual[_key(nd2)] = _manual.get(_key(nd2), 0) + 1


def _on_saved(nd2=None, path=None, n_cells=0, **_kw) -> None:
    if not nd2 or not path:
        return
    from . import batchqueue
    n_hand = _manual.get(_key(nd2), 0)
    if n_hand < 1 or batchqueue.position(nd2) is None:
        return
    channels: List[str] = []
    try:
        from . import roifile
        channels = list((roifile.read_summary(path) or {}).get("channels") or [])
    except Exception:                                              # noqa: BLE001
        pass
    d = userprefs.load(_TOPIC)
    movies = [m for m in d.get("movies", []) if _key(m.get("nd2", "")) != _key(nd2)]
    movies.append(dict(nd2=str(nd2), run=str(path), n_hand=int(n_hand),
                       n_cells=int(n_cells or 0), channels=channels,
                       saved=datetime.now().isoformat(timespec="seconds")))
    d["movies"] = movies
    d.pop("cache", None)                    # a new movie: learn again next time
    userprefs.save(_TOPIC, d)
    if len(movies) >= NEEDED:
        achievements.unlock("smart_select")


def install() -> None:
    """Start following the analysis window's events (idempotent)."""
    events.on("movie_opened", _on_opened)
    events.on("roi_added", _on_roi)
    events.on("saved", _on_saved)


install()


# ------------------------------------------------------------------ status
def hand_drawn_movies() -> List[dict]:
    return [m for m in userprefs.load(_TOPIC).get("movies", []) if isinstance(m, dict)]


HOW = ("Smart auto-select picks cells the way you do, learned from your own "
       "hand-drawn movies (plain AUTO-DETECT is always there too).\n\n"
       "To unlock it: choose several movies at once on the start screen (a movie\n"
       f"queue) and draw the cells BY HAND on {NEEDED} of them, pressing SAVE on each.\n"
       "Each one also grows a web in Charlotte's Web (the pink button).\n\n"
       "It learns only from movies with the same channel names as the one you have open.")


def unlocked() -> bool:
    return len(hand_drawn_movies()) >= NEEDED


def status() -> dict:
    n = len(hand_drawn_movies())
    if unlocked():
        achievements.unlock("smart_select")
        text = f"{NAME}: ready - learns from your {n} hand-drawn movies"
    else:
        text = f"{NAME}: locked - {min(n, NEEDED)} of {NEEDED} hand-drawn queued movies"
    return {"unlocked": unlocked(), "text": text, "how": HOW, "count": n, "needed": NEEDED}


# ------------------------------------------------------------------ learning
def training_runs(channels, main: str, helpers) -> List[dict]:
    """The hand-drawn movies usable for these channels (run file and .nd2 present)."""
    need = [main] + list(helpers)
    out = []
    for m in hand_drawn_movies():
        ch = list(m.get("channels") or [])
        if ch and not all(c in ch for c in need):
            continue
        if not (Path(m.get("run", "")).exists() and Path(m.get("nd2", "")).exists()):
            continue
        out.append(m)
    return out


def learn(runs: List[dict], main: str, helpers, progress=None):
    """A Detector learned from these runs (the trained auto-detect, no quiz)."""
    from . import detectors as DT
    chans = [main] + [h for h in helpers if h != main]
    prog = progress or (lambda f, m: True)
    movies = []
    n = len(runs)
    for i, r in enumerate(runs):
        movies.append(DT.load_movie(r["run"], r["nd2"], main, list(helpers),
                                    lambda f, m, i=i: prog(0.6 * (i + f) / n,
                                                           f"Reading your movie {i + 1} of {n}"),
                                    keep_frame=False))
    held = DT.held_out(movies, chans, lambda f, m: prog(0.6 + 0.3 * f, "Checking itself..."))
    limits = DT.fit(movies, chans, lambda f, m: prog(0.9 + 0.1 * f, "Learning your way..."))
    return DT.Detector(
        name=NAME, main=main, helpers=[h for h in helpers if h != main], comp="nucleus",
        limits=limits,
        trained_on=[dict(DT.score(m, DT.select(m.feat, limits, chans)), movie=m.name, run=m.run)
                    for m in movies],
        held_out=held, created=datetime.now().isoformat(timespec="seconds"))


def run(window) -> None:
    """The button in the analysis window: learn (in the background) from your
    hand-drawn movies, then pick this movie's cells with that rule."""
    from PySide6.QtWidgets import QMessageBox
    if not unlocked():
        QMessageBox.information(window, NAME, HOW)
        return
    names = list(window.exp.channels)
    r = window._rule("nucleus")
    main = names[int(r.a)] if 0 <= int(r.a) < len(names) else names[0]
    try:
        hs = [names[h] for h in r.helper_list() if h < len(names)]
    except Exception:                                              # noqa: BLE001
        hs = []
    runs = training_runs(names, main, hs)
    if len(runs) < 2:
        QMessageBox.information(
            window, NAME,
            f"{NAME} learns from your hand-drawn movies that have the channels "
            f"{', '.join([main] + hs)} and are still on this computer - found {len(runs)}. "
            "Draw by hand on a couple more of these and SAVE, then try again.")
        return
    from .gui.workers import FuncJob
    window._start(FuncJob(learn, runs, main, hs),
                  lambda det: window._use_detector(det) if det is not None else None,
                  f"{NAME} is learning from your {len(runs)} hand-drawn movies...")
