"""
Smart auto-select (PeterPiper 1.1): one click that picks the cells the way YOU
pick them, learned from movies in which you picked the cells by hand.

Bins. Each user keeps named bins, one per kind of experiment (e.g. "GFP/Cy5
nuclei"): every movie in a bin has the same channel names, and may hold any
number of ROIs. A bin's button shows n = the number of hand-picked movies in it,
so a run can be described as e.g. "cells selected with a user-specific detector
learned from n = 44 hand-picked movies (612 ROIs)".

Method. A bin is turned into the V3.0 trained auto-detect (detectors.py: the
candidate blobs, your saved ROIs as the answers, a rule searched on fixed grids,
and an honest held-out score - each movie scored by the rule learned from the
others). The detector's name carries the bin, its n and its ROI count, and its
rule and held-out score are written into the run and its Methods like any
trained auto-detect. Plain AUTO-DETECT is unchanged and always available.

Unlocking (it goes with the Charlotte's Web game: every movie you draw by hand
grows a web): hand-draw the cells on 3 or more movies from a movie queue and
SAVE each. Which movies count: a SAVE (event 'saved') of a movie that is in the
movie queue and on which at least one cell was added by hand since it was opened.
New hand-drawn movies are put into bins in the bins window (review_dialog),
which opens the next time Smart auto-select is used. Kept per
user in smartselect.json (userprefs): run file, movie, channel names, counts,
bin. No images are stored.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import achievements, events, userprefs

_TOPIC = "smartselect"
NEEDED = 3                      # hand-drawn queued movies needed to unlock
MIN_TRAIN = 2                   # movies a bin needs before it can pick cells
NAME = "Smart auto-select"

_manual: Dict[str, int] = {}    # this session: movie -> cells added by hand


def _key(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def _chkey(channels: Sequence[str]) -> tuple:
    return tuple(sorted(str(c) for c in channels or ()))


# ------------------------------------------------------------------ storage
def _load() -> dict:
    d = userprefs.load(_TOPIC)
    if not isinstance(d.get("movies"), list):
        d["movies"] = []
    if not isinstance(d.get("bins"), dict):
        d["bins"] = {}
    return d


def _save(d: dict) -> None:
    userprefs.save(_TOPIC, d)


def hand_drawn_movies() -> List[dict]:
    """Every queued movie you drew by hand and SAVEd (in a bin or not)."""
    return [m for m in _load()["movies"] if isinstance(m, dict)]


def bins() -> Dict[str, dict]:
    """{bin name: {"channels": [...], "created": iso}}."""
    return {k: v for k, v in _load()["bins"].items() if isinstance(v, dict)}


def bin_movies(name: str) -> List[dict]:
    return [m for m in hand_drawn_movies() if m.get("bin") == name]


def totals(movies: Sequence[dict]) -> dict:
    """{"movies": n hand-picked movies, "rois": the ROIs saved in them}."""
    return {"movies": len(movies), "rois": int(sum(int(m.get("n_cells") or 0) for m in movies))}


def bin_fits(name: str, channels: Sequence[str]) -> bool:
    b = bins().get(name)
    return bool(b) and _chkey(b.get("channels", ())) == _chkey(channels)


def new_bin(name: str, channels: Sequence[str]) -> str:
    """Make a bin for movies with these channels (an existing bin of the same name
    and channels is simply returned)."""
    name = " ".join(str(name).split())[:60]
    if not name or name in (NO_BIN, NEW_BIN):
        raise ValueError("Give the bin a name.")
    d = _load()
    old = d["bins"].get(name)
    if old is not None and _chkey(old.get("channels", ())) != _chkey(channels):
        raise ValueError(f"The bin '{name}' already exists for other channels.")
    d["bins"].setdefault(name, {"channels": list(channels),
                                "created": datetime.now().isoformat(timespec="seconds")})
    _save(d)
    return name


def assign(nd2: str, bin_name: Optional[str]) -> None:
    """Put a hand-drawn movie into a bin (None: in no bin). Its channels must fit."""
    d = _load()
    for m in d["movies"]:
        if _key(m.get("nd2", "")) == _key(nd2):
            if bin_name is not None:
                b = d["bins"].get(bin_name)
                if b is None:
                    raise ValueError(f"No bin '{bin_name}'.")
                if m.get("channels") and _chkey(b.get("channels", ())) != _chkey(m["channels"]):
                    raise ValueError(f"'{Path(m['nd2']).name}' has other channels than "
                                     f"the bin '{bin_name}'.")
            m["bin"] = bin_name
            m["reviewed"] = True
    _save(d)


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
    d = _load()
    old = next((m for m in d["movies"] if _key(m.get("nd2", "")) == _key(nd2)), None)
    d["movies"] = [m for m in d["movies"] if m is not old]
    d["movies"].append(dict(nd2=str(nd2), run=str(path), n_hand=int(n_hand),
                            n_cells=int(n_cells or 0), channels=channels,
                            bin=old.get("bin") if old else None,
                            reviewed=bool(old and old.get("reviewed")),
                            saved=datetime.now().isoformat(timespec="seconds")))
    _save(d)
    if len(d["movies"]) >= NEEDED:
        achievements.unlock("smart_select")


def to_sort() -> List[dict]:
    """Hand-drawn movies not yet put into a bin (or left out on purpose)."""
    return [m for m in hand_drawn_movies() if not m.get("reviewed")]


def install() -> None:
    """Start following the analysis window's events (idempotent)."""
    events.on("movie_opened", _on_opened)
    events.on("roi_added", _on_roi)
    events.on("saved", _on_saved)


install()


# ------------------------------------------------------------------ status
HOW = ("Smart auto-select picks cells the way you do. It learns from movies in which\n"
       "you picked the cells by hand, kept in named bins - one per kind of experiment\n"
       "(same channels, any number of ROIs per movie). Each bin's button shows\n"
       "n = how many hand-picked movies it learned from; the more you hand-pick, the\n"
       "better it selects on big samples. Plain AUTO-DETECT is always there too.\n\n"
       "To unlock it: choose several movies at once on the start screen (a movie\n"
       f"queue) and draw the cells BY HAND on {NEEDED} of them, pressing SAVE on each.\n"
       "Each one also grows a web in Charlotte's Web (the pink button). Then you put\n"
       "those movies into bins (or make a new bin and name it).\n\n"
       "Its rule, the bin's n and its tested accuracy go into the Methods of every run.")


def unlocked() -> bool:
    return len(hand_drawn_movies()) >= NEEDED


def bin_info(channels: Optional[Sequence[str]] = None) -> List[dict]:
    """Every bin (only the ones that fit these channels, if given), newest first."""
    out = []
    for name, b in bins().items():
        if channels is not None and _chkey(b.get("channels", ())) != _chkey(channels):
            continue
        t = totals(bin_movies(name))
        out.append({"name": name, "channels": list(b.get("channels", [])),
                    "n_movies": t["movies"], "n_rois": t["rois"],
                    "label": f"{name} (n={t['movies']})", "created": b.get("created", "")})
    return sorted(out, key=lambda x: x["created"], reverse=True)


def status(channels: Optional[Sequence[str]] = None) -> dict:
    n = len(hand_drawn_movies())
    fit = bin_info(channels)
    new = len(to_sort())
    if not unlocked():
        text = f"{NAME}: locked - {min(n, NEEDED)} of {NEEDED} hand-drawn queued movies"
        label = f"{NAME} (locked)"
    elif not fit:
        where = " for these channels" if channels is not None else ""
        text = f"{NAME}: ready - put your hand-drawn movies into a bin{where}"
        label = f"{NAME} (no bin{where})"
    elif len(fit) == 1:
        b = fit[0]
        text = (f"{NAME}: {b['name']} (n={b['n_movies']} hand-picked movies, "
                f"{b['n_rois']} ROIs)")
        label = f"{NAME}: {b['label']}"
    else:
        text = f"{NAME}: {len(fit)} bins - " + ", ".join(b["label"] for b in fit)
        label = f"{NAME} ({len(fit)} bins)"
    if unlocked() and new:
        text += f" - {new} new hand-drawn movie(s) to put into bins"
    return {"unlocked": unlocked(), "text": text, "how": HOW, "label": label,
            "bins": fit, "count": n, "needed": NEEDED, "to_sort": new}


# ------------------------------------------------------------------ learning
def training_runs(bin_name: str, main: str, helpers) -> List[dict]:
    """The bin's movies still on this computer that have these channels."""
    need = [main] + list(helpers)
    out = []
    for m in bin_movies(bin_name):
        ch = list(m.get("channels") or [])
        if ch and not all(c in ch for c in need):
            continue
        if Path(m.get("run", "")).exists() and Path(m.get("nd2", "")).exists():
            out.append(m)
    return out


def learn(runs: List[dict], main: str, helpers, bin_name: str = "", progress=None):
    """A Detector learned from these runs (the V3.0 trained auto-detect, no quiz).
    Its name carries the bin, n (hand-picked movies) and their ROIs, so the Methods
    of every run it is used on say so; the held-out score is kept with it."""
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
    n_rois = int(sum(m.n_yours for m in movies))
    what = f"{bin_name} - " if bin_name else ""
    return DT.Detector(
        name=f"{what}{NAME} (n={len(movies)} hand-picked movies, {n_rois} ROIs)",
        main=main, helpers=[h for h in helpers if h != main], comp="nucleus", limits=limits,
        trained_on=[dict(DT.score(m, DT.select(m.feat, limits, chans)), movie=m.name, run=m.run)
                    for m in movies],
        held_out=held, created=datetime.now().isoformat(timespec="seconds"))


def run(window, bin_name: Optional[str] = None) -> None:
    """The button in the analysis window: learn (in the background) from a bin
    that fits this movie, then pick this movie's cells with that rule."""
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QMenu, QMessageBox
    if not unlocked():
        QMessageBox.information(window, NAME, HOW)
        return
    names = list(window.exp.channels)
    if bin_name is None and to_sort():          # new hand-drawn movies: sort them first
        review_dialog(window)
    fit = bin_info(names)
    if bin_name is None:
        if not fit:
            if QMessageBox.question(
                    window, NAME, "No bin has the channels of this movie yet "
                    f"({', '.join(names)}). Open your bins to make one?") == QMessageBox.Yes:
                review_dialog(window)
            return
        if len(fit) == 1:
            bin_name = fit[0]["name"]
        else:
            menu = QMenu(window)
            for b in fit:
                a = menu.addAction(f"{b['name']}  (n={b['n_movies']})")
                a.setData(b["name"])
            hit = menu.exec(QCursor.pos())
            if hit is None:
                return
            bin_name = hit.data()
    r = window._rule("nucleus")
    main = names[int(r.a)] if 0 <= int(r.a) < len(names) else names[0]
    try:
        hs = [names[h] for h in r.helper_list() if h < len(names)]
    except Exception:                                              # noqa: BLE001
        hs = []
    runs = training_runs(bin_name, main, hs)
    if len(runs) < MIN_TRAIN:
        QMessageBox.information(
            window, NAME,
            f"The bin '{bin_name}' has {len(runs)} hand-picked movie(s) on this computer; "
            f"it needs at least {MIN_TRAIN}. Hand-pick the cells on more movies of this kind "
            "(in a queue), SAVE, and put them into this bin.")
        return
    from .gui.workers import FuncJob
    window._start(FuncJob(learn, runs, main, hs, bin_name),
                  _done(window),
                  f"{NAME} is learning from '{bin_name}' (n={len(runs)} hand-picked movies)...")


def _done(window):
    """After learning: pick the cells (use_detector handles None - ends busy)."""
    use = getattr(window, "use_detector", None)
    if use is not None:
        return use
    return lambda det: window._use_detector(det) if det is not None else window._busy(False)


# ------------------------------------------------------------------ the bins window
NO_BIN = "(not in a bin)"
NEW_BIN = "New bin..."


def review_dialog(parent=None) -> bool:
    """'Your Smart auto-select bins': put each hand-drawn movie into a bin of its
    kind (same channels), make and name new bins. Shown at the end of a batch and
    from the button's menu. Returns True if accepted."""
    from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QInputDialog,
                                   QLabel, QMessageBox, QTreeWidget, QTreeWidgetItem,
                                   QVBoxLayout)
    movies = hand_drawn_movies()
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Your {NAME} bins")
    lay = QVBoxLayout(dlg)
    head = QLabel()
    head.setWordWrap(True)
    lay.addWidget(head)
    tree = QTreeWidget()
    tree.setRootIsDecorated(False)
    tree.setHeaderLabels(["Movie", "ROIs saved", "Drawn by hand", "Channels", "Bin"])
    lay.addWidget(tree)
    combos: List[QComboBox] = []

    def fill(cb: QComboBox, m: dict, current: Optional[str]) -> None:
        cb.blockSignals(True)
        cb.clear()
        cb.addItem(NO_BIN, None)
        for b in bin_info(m.get("channels") or None):
            cb.addItem(f"{b['name']}  (n={b['n_movies']})", b["name"])
        cb.addItem(NEW_BIN, NEW_BIN)
        i = cb.findData(current) if current is not None else 0
        cb.setCurrentIndex(i if i >= 0 else 0)
        cb.blockSignals(False)

    def refresh_head() -> None:
        chosen: Dict[str, int] = {}
        for cb in combos:
            v = cb.currentData()
            if v not in (None, NEW_BIN):
                chosen[v] = chosen.get(v, 0) + 1
        parts = [f"<b>{k}</b>: n = {v}" for k, v in sorted(chosen.items())]
        head.setText("Put each hand-drawn movie into the bin of its kind - every movie in a "
                     "bin has the same channels. A bin's n is its number of hand-picked "
                     "movies.<br>" + ("; ".join(parts) if parts else "No movie in a bin yet."))

    def changed(cb: QComboBox, m: dict) -> None:
        if cb.currentData() != NEW_BIN:
            refresh_head()
            return
        made = None
        name, ok = QInputDialog.getText(dlg, "New bin", "Name of the new bin (the kind of "
                                        "experiment, e.g. 'GFP/Cy5 nuclei'):")
        if ok and name.strip():
            try:
                made = new_bin(name, m.get("channels") or [])
            except ValueError as exc:
                QMessageBox.warning(dlg, "New bin", str(exc))
        for c, mm in zip(combos, movies):
            keep = made if c is cb else c.currentData()
            fill(c, mm, None if keep == NEW_BIN else keep)
        refresh_head()

    for m in movies:
        it = QTreeWidgetItem([Path(m.get("nd2", "")).name, str(m.get("n_cells", 0)),
                              str(m.get("n_hand", 0)), ", ".join(m.get("channels") or [])])
        it.setToolTip(0, str(m.get("nd2", "")))
        tree.addTopLevelItem(it)
        cb = QComboBox()
        fill(cb, m, m.get("bin"))
        cb.currentIndexChanged.connect(lambda _i, cb=cb, m=m: changed(cb, m))
        tree.setItemWidget(it, 4, cb)
        combos.append(cb)
    for c in range(4):
        tree.resizeColumnToContents(c)
    tree.setColumnWidth(4, 240)
    refresh_head()
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    dlg.resize(900, 460)
    accepted = dlg.exec() == QDialog.Accepted
    d = _load()
    by_key = {_key(m.get("nd2", "")): m for m in d["movies"]}
    for m, cb in zip(movies, combos):
        mm = by_key.get(_key(m.get("nd2", "")))
        if mm is None:
            continue
        if accepted and cb.currentData() != NEW_BIN:
            mm["bin"] = cb.currentData()
        mm["reviewed"] = True
    _save(d)
    return accepted
