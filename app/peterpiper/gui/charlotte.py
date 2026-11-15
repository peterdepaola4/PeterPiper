"""
Charlotte's Web - a small minigame inside PeterPiper 1.1.

FOR ANYONE READING THE CODE: this is a harmless easter egg / minigame.
  * It only draws pictures (QPainter, in code - no image files, no network).
  * It stores only its own collection (random seeds, a few drawing numbers,
    theme, movie name, date, the number of cells drawn by hand, the kind word
    and the user's design choices) in the user's own PeterPiper folder:
    userprefs topic "charlotte".
  * It never reads, changes or writes analysis data or any number of it; it
    only listens to app events (events.py) and every listener is guarded, so a
    failure here can never disturb an analysis.
  * Nothing is taken from the book beyond the name and a few short kind words
    written into the web as a light homage.

How it plays (for everyone):
  * Every movie (.nd2) you analyse gets its own web. It starts as a few anchor
    and radial threads and grows with every cell ROI you add BY HAND on that
    movie (roi_added with manual=True). Removing an ROI may snap a thread, but
    a web never fully unspins.
  * SAVE finishes the web: the little creature writes one kind word into it.
    A movie that is not in a queue goes straight into the Collection. Webs of
    a movie queue (batch) wait in "This batch" until the batch is finished
    (every queued movie saved / exported / skipped, or "Finish batch"), then
    "Collect" adds them. A later SAVE of the same movie, after more cells by
    hand, finishes a new web.
  * Each web is rolled once, when it starts: one of 50 themes (about a quarter
    are not spiders) and a rarity:
        everyone        a per-user counter of webs started: every 3rd web is
                        special - Rare (75 %) or Epic (25 %); the other two are
                        Common (deliberately plain).
        hidden extra    every web is Rare (65 %) or Epic (35 %).
  * Hidden extra (needs the 20-logo-click "palettes" extra first): type "cha"
    and hold "r" for 2 seconds anywhere in the app -> achievements "charlotte".
    It also lets you design your own version of a finished batch's webs (Web
    design slider and theme) before you collect them. Each web keeps its seed
    and word; the choices are stored with the web, the original roll too.

userprefs "charlotte":
    collection  list, one entry per collected web (other parts count these)
    tray        finished webs of a batch waiting for "Collect"
    growing     {movie key: web} - webs still growing
    seeds       every seed used (never the same web twice)
    started     webs started so far (the every-3rd counter)
    window      {"geo": [x, y, w, h], "closed": bool}

Hooks:
    install(app)                 app-wide key watcher (observes only) + events
    open_window(parent=None)     shows the "Charlotte's Web" window
    make_pink_button(parent)     the pink button (also added by main_window_ready)
    export_png(web, path) / export_contact_sheet(webs, path)
    hand_drawn_queued_movies()   different queued movies with a finished web that
                                 has cells drawn by hand (for Smart auto-select)
"""
from __future__ import annotations

import hashlib
import math
import os
import random
import re
import time
import weakref
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QBuffer, QByteArray, QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
                               QHBoxLayout, QLabel, QLayout, QListWidget, QListWidgetItem,
                               QPushButton, QSizePolicy, QSlider, QStackedWidget, QVBoxLayout,
                               QWidget)

from . import charlotte_draw as D
from .charlotte_themes import BY_KEY, THEMES
from .charlotte_words import WORDS

_TOPIC = "charlotte"
RARITIES = ("common", "rare", "epic")
LEVEL = {"common": 0, "uncommon": 1, "rare": 2, "epic": 3}
RARITY_LABEL = {"common": "Common", "rare": "Rare", "epic": "Epic"}
# badge colours (white text on each: contrast >= 4.5)
RARITY_COLOUR = {"common": "#5f6670", "rare": "#2457c5", "epic": "#8a2bb5"}
EVERY = 3                    # everyone: every 3rd web started is rare or epic
EPIC_SHARE_PLAIN = 0.25      # ... of those: 75 % rare, 25 % epic
EPIC_SHARE_EGG = 0.35        # with the hidden extra every web: 65 % rare, 35 % epic
DESIGN_STEPS = ("As rolled", "Common", "Rare", "Epic")     # the Web design slider
PINK_STOPS = ("#c2185b", "#ad1457")          # the pink button's gradient (top, bottom)
PINK_HOVER = ("#d81b60", "#c2185b")
PINK_PRESSED = ("#ad1457", "#880e4f")


# ----------------------------------------------------------------- small helpers
def _rel_lum(c: QColor) -> float:
    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contrast(a, b) -> float:
    la, lb = _rel_lum(QColor(a)), _rel_lum(QColor(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def text_on(colours) -> str:
    """White or a dark plum, whichever reads better on every colour given."""
    return max(("#ffffff", "#2a0716"), key=lambda t: min(contrast(t, c) for c in colours))


def pink_button_style() -> str:
    tx = text_on(PINK_STOPS + PINK_HOVER + PINK_PRESSED)
    g = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {}, stop:1 {})"
    return (f"QPushButton#charlotteButton {{ background: {g.format(*PINK_STOPS)}; color: {tx};"
            f" border: 1px solid #880e4f; border-radius: 9px; padding: 4px 14px;"
            f" font-weight: 600; }}"
            f"QPushButton#charlotteButton:hover {{ background: {g.format(*PINK_HOVER)}; color: {tx}; }}"
            f"QPushButton#charlotteButton:pressed {{ background: {g.format(*PINK_PRESSED)};"
            f" color: {tx}; }}"
            f"QPushButton#charlotteButton:disabled {{ background: #9e8a94; color: #2a0716; }}")


def _key(nd2) -> str:
    return hashlib.sha1(os.path.normcase(os.path.abspath(str(nd2))).encode("utf-8",
                        "replace")).hexdigest()[:16]


def _movie_name(nd2) -> str:
    return Path(str(nd2)).stem


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> dict:
    try:
        from .. import userprefs
        d = userprefs.load(_TOPIC)
    except Exception:                                              # noqa: BLE001
        d = {}
    for k, empty in (("seeds", list), ("collection", list), ("tray", list), ("growing", dict),
                     ("window", dict)):
        if not isinstance(d.get(k), empty):
            d[k] = empty()
    if not isinstance(d.get("started"), int):
        d["started"] = 0
    return d


def _save(d: dict) -> None:
    try:
        from .. import userprefs
        userprefs.save(_TOPIC, d)
    except Exception:                                              # noqa: BLE001
        pass


def egg_found() -> bool:
    try:
        from .. import achievements
        return achievements.unlocked("charlotte")
    except Exception:                                              # noqa: BLE001
        return False


def new_seed(movie: str, used) -> int:
    used = set(int(x) for x in used)
    while True:
        h = hashlib.sha256(os.urandom(16) + str(movie).encode("utf-8", "replace")
                           + str(time.time_ns()).encode()).digest()
        s = int.from_bytes(h[:6], "big")
        if s not in used:
            return s


def roll_rarity(rng: random.Random, egg: bool, index: int) -> str:
    """index = 0-based number of this web among all webs this user started."""
    if egg:
        return "epic" if rng.random() < EPIC_SHARE_EGG else "rare"
    if (index + 1) % EVERY == 0:
        return "epic" if rng.random() < EPIC_SHARE_PLAIN else "rare"
    return "common"


def pick_theme(rng: random.Random, seen: List[dict]) -> str:
    found = {w.get("theme") for w in seen}
    unfound = [t["key"] for t in THEMES if t["key"] not in found]
    if unfound and rng.random() < 0.7:
        return rng.choice(unfound)
    return rng.choice(THEMES)["key"]


def pick_word(rng: random.Random, seen: List[dict]) -> str:
    recent = {w.get("word") for w in seen[-25:]}
    fresh = [w for w in WORDS if w not in recent]
    return rng.choice(fresh or list(WORDS))


def shown_rarity(web: dict) -> str:
    r = web.get("design") or web.get("rarity") or "common"
    return r if r in LEVEL else "common"


def level_of(web: dict) -> int:
    return LEVEL.get(shown_rarity(web), 0)


def shown_theme(web: dict) -> str:
    t = web.get("design_theme") or web.get("theme")
    return t if t in BY_KEY else THEMES[0]["key"]


def make_web(nd2, store: dict, egg: Optional[bool] = None) -> dict:
    seed = new_seed(_movie_name(nd2), store.get("seeds", []))
    store.setdefault("seeds", []).append(seed)
    index = int(store.get("started", 0))
    store["started"] = index + 1
    rng = random.Random(seed ^ 0x5DEECE66D)
    egg = egg_found() if egg is None else egg
    return {
        "id": f"w{seed:012x}", "seed": seed,
        "theme": pick_theme(rng, store.get("collection", []) + store.get("tray", [])),
        "params": D.new_params(seed), "movie": _movie_name(nd2), "key": _key(nd2),
        "started": _now_iso(), "date": None, "n": 0, "peak": 0, "snaps": 0, "word": None,
        "index": index, "rarity": roll_rarity(rng, egg, index), "design": None,
        "design_theme": None, "queued": False, "done": False,
    }


def render_web(web: dict, w: int, h: int, t: float = 0.0, word_progress: float = 1.0) -> QImage:
    return D.render_image(shown_theme(web), web.get("params"), int(web.get("seed", 0)),
                          int(web.get("n", 0)), w, h, t=t, word=web.get("word"),
                          word_progress=word_progress, level=level_of(web))


def _png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _write_new(path, data: bytes) -> Path:
    from .. import safety
    with safety.new_output_file(Path(path)) as (real, stream):
        stream.write(data)
    return Path(real)


CAPTION = "PeterPiper \u00b7 Charlotte's Web"      # the program is PeterPiper; this is its game


def export_image(web: dict, size: int = 1600) -> QImage:
    """The picture that "Export picture" saves: the web as shown (with the user's
    design) and a small caption in the corner."""
    img = render_web(web, size, size, t=1.0)
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.TextAntialiasing, True)
        f = QFont()
        f.setPixelSize(max(9, size // 64))
        p.setFont(f)
        r = QRectF(0, size - size / 22, size - size / 60, size / 26)
        p.setPen(QColor(0, 0, 0, 140))
        p.drawText(r.translated(1, 1), Qt.AlignRight | Qt.AlignVCenter, CAPTION)
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(r, Qt.AlignRight | Qt.AlignVCenter, CAPTION)
    finally:
        p.end()
    return img


def export_png(web: dict, path, size: int = 1600) -> Path:
    """One web as a PNG (export_image). Never overwrites: adds _2, _3 ...
    Returns the file written."""
    return _write_new(path, _png_bytes(export_image(web, size)))


def export_contact_sheet(webs: List[dict], path) -> Path:
    """All webs on one picture with their theme, rarity, movie, date and word."""
    webs = list(webs)
    n = max(1, len(webs))
    cols = max(1, min(8, math.ceil(math.sqrt(n))))
    rows = math.ceil(n / cols)
    tile = int(max(150, min(400, math.sqrt(40e6 / n) * 0.8)))
    cap = max(34, tile // 6)
    head = 70
    W, H = cols * tile, head + rows * (tile + cap)
    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor("#1b1420"))
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        f = QFont(D.word_font_family())
        f.setPixelSize(30)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#ffd6ea"))
        themes = len({w.get("theme") for w in webs})
        p.drawText(QRectF(16, 0, W - 32, head), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{CAPTION} - {len(webs)} webs, {themes} of {len(THEMES)} themes")
        fs = QFont()
        fs.setPixelSize(max(10, cap // 3))
        for i, web in enumerate(webs):
            x, y = (i % cols) * tile, head + (i // cols) * (tile + cap)
            p.drawImage(x, y, render_web(web, tile, tile, t=1.0))
            p.setFont(fs)
            p.setPen(QColor("#f4eef7"))
            th = BY_KEY[shown_theme(web)]["name"]
            date = (web.get("date") or web.get("started") or "")[:10]
            p.drawText(QRectF(x + 6, y + tile, tile - 12, cap / 2), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{th} - {RARITY_LABEL.get(shown_rarity(web), '')}")
            p.setPen(QColor("#c9bcd2"))
            p.drawText(QRectF(x + 6, y + tile + cap / 2, tile - 12, cap / 2),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{web.get('movie', '')} - {date} - {web.get('word') or ''}")
    finally:
        p.end()
    return _write_new(path, _png_bytes(img))


def hand_drawn_queued_movies(store: Optional[dict] = None) -> int:
    """Different queued movies with a finished (saved) web that has cells drawn by hand
    (collected or still waiting in the batch tray)."""
    store = store if store is not None else _load()
    return len({w.get("key") for w in store.get("collection", []) + store.get("tray", [])
                if w.get("queued") and int(w.get("n", 0)) > 0})


def _smart_line() -> Optional[str]:
    try:
        from ..smartselect import status
    except Exception:                                              # noqa: BLE001
        return None
    try:
        st = status()
    except Exception:                                              # noqa: BLE001
        return None
    if isinstance(st, str):
        return st
    try:
        if isinstance(st, dict):
            done = st.get("count", st.get("done", 0))
            need = st.get("needed", st.get("need", 3))
            unl = st.get("unlocked", False)
        else:
            done, need, unl = st
        if unl:
            return "Smart auto-select: unlocked!"
        return f"Smart auto-select: {done} of {need} hand-drawn queued movies"
    except Exception:                                              # noqa: BLE001
        return None


# ------------------------------------------------------------------ key watcher
class KeyWatcher(QObject):
    """Watches key events app-wide and NEVER consumes them (always returns False):
    'cha' then 'r' held for 2 s (auto-repeat presses, press/release pairs, or a
    plain press ... release) finds the hidden extra - only once the 'palettes'
    extra was found. The clock can be swapped for tests."""

    HOLD = 2.0
    GAP = 0.6
    _MODS = {Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr,
             Qt.Key_CapsLock}

    def __init__(self, on_found: Callable[[], None], clock: Callable[[], float] = time.monotonic,
                 parent=None) -> None:
        super().__init__(parent)
        self.on_found = on_found
        self.clock = clock
        self.buf = ""
        self.r_on = False
        self.r_start = 0.0
        self.r_last = 0.0
        self.r_down = False
        self._sig = None
        self.done = False

    def eventFilter(self, obj, ev) -> bool:                     # noqa: N802
        try:
            et = ev.type()
            if (et == QEvent.KeyPress or et == QEvent.KeyRelease) and not self.done \
                    and isinstance(obj, QWidget):
                sig = (int(et), ev.key(), ev.isAutoRepeat(), ev.timestamp())
                if sig != self._sig:            # the same event passed on to a parent
                    self._sig = sig
                    self.feed(et == QEvent.KeyPress, ev.key(), ev.text(), ev.isAutoRepeat(),
                              ev.modifiers())
        except Exception:                                          # noqa: BLE001
            pass
        return False                            # observe only - never block a key

    def feed(self, press: bool, key: int, text: str = "", autorep: bool = False,
             mods=Qt.NoModifier) -> None:
        now = self.clock()
        if key in self._MODS:
            return
        try:
            if mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
                self._reset()
                return
        except TypeError:
            pass
        if key == Qt.Key_R:
            if self.r_on and not self.r_down and now - self.r_last > self.GAP:
                self.r_on = False               # a pause with the key up: not a hold
            if press:
                if not self.r_on and re.search(r"char*$", self.buf + "r"):
                    self.r_on, self.r_start = True, now
                self.buf = (self.buf + "r")[-12:]
                self.r_down = True
            else:
                self.r_down = bool(autorep)     # an auto-repeat release: still held
            self.r_last = now
            if self.r_on and now - self.r_start >= self.HOLD - 1e-9:
                self.r_on = False
                self._found()
            elif not press and not autorep:
                self.r_on = False
            return
        if press:
            self.r_on = self.r_down = False
            ch = (text or "").lower()
            self.buf = (self.buf + ch)[-12:] if len(ch) == 1 and ch.isalpha() else ""

    def _reset(self) -> None:
        self.buf, self.r_on, self.r_down = "", False, False

    def _found(self) -> None:
        self.buf = ""
        try:
            from .. import achievements
            if not achievements.unlocked("palettes"):
                return
            self.done = True
            if achievements.unlock("charlotte") and self.on_found:
                self.on_found()
        except Exception:                                          # noqa: BLE001
            pass


# ------------------------------------------------------------------- the canvas
class WebCanvas(QWidget):
    """Shows one web, gently animated (about 12 frames a second, only while visible)."""

    FPS = 12

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.web: Optional[dict] = None
        self.placeholder = "Draw a cell by hand to start this movie's web."
        self._cache_key = None
        self._static: Optional[QPixmap] = None
        self._scene = None
        self._t0 = time.monotonic()
        self._write_t0: Optional[float] = None
        self._snap_t0: Optional[float] = None
        self._burst_t0: Optional[float] = None
        self._grow_t0: Optional[float] = None
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / self.FPS))
        self.timer.timeout.connect(self.update)
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_web(self, web: Optional[dict]) -> None:
        self.web = dict(web) if web else None
        self._cache_key = None
        self.update()

    def write_word(self) -> None:
        self._write_t0 = time.monotonic()

    def snap(self) -> None:
        self._snap_t0 = time.monotonic()

    def burst(self) -> None:
        self._burst_t0 = time.monotonic()

    def grow(self) -> None:
        self._grow_t0 = time.monotonic()

    def showEvent(self, ev) -> None:                             # noqa: N802
        self.timer.start()
        super().showEvent(ev)

    def hideEvent(self, ev) -> None:                             # noqa: N802
        self.timer.stop()
        super().hideEvent(ev)

    def _ensure(self, side: int) -> None:
        w = self.web
        key = (w.get("id"), w.get("n"), level_of(w), shown_theme(w), side)
        if key == self._cache_key and self._static is not None:
            return
        dpr = max(1.0, self.devicePixelRatioF())
        px = int(side * dpr)
        sc = D.Scene(shown_theme(w), w.get("params"), int(w.get("seed", 0)), int(w.get("n", 0)),
                     px, px, level_of(w))
        img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        try:
            sc.draw_background(p)
            sc.draw_web(p)
        finally:
            p.end()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self._static, self._scene, self._cache_key = pm, sc, key

    def paintEvent(self, ev) -> None:                            # noqa: N802
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            side = max(50, min(self.width(), self.height()))
            ox, oy = (self.width() - side) / 2, (self.height() - side) / 2
            if not self.web:
                p.setPen(self.palette().windowText().color())
                p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignCenter | Qt.TextWordWrap,
                           self.placeholder)
                return
            self._ensure(side)
            p.drawPixmap(QPointF(ox, oy), self._static)
            now = time.monotonic()
            t = now - self._t0
            word = self.web.get("word")
            prog = 1.0
            if word and self._write_t0 is not None:
                prog = (now - self._write_t0) / (1.2 + 0.22 * len(word))
                if prog >= 1.0:
                    self._write_t0, prog = None, 1.0
            dpr = self._static.devicePixelRatio()
            p.save()
            p.translate(ox, oy)
            p.scale(1 / dpr, 1 / dpr)
            if self._grow_t0 is not None:
                g = (now - self._grow_t0) / 0.9
                if g >= 1:
                    self._grow_t0 = None
                else:
                    D.soft_disc(p, self._scene.cx, self._scene.cy, self._scene.R * (0.4 + g),
                                QColor(255, 255, 255), 70 * (1 - g), 0)
            self._scene.draw_overlay(p, t, word, max(0.0, prog))
            if self._snap_t0 is not None:
                self._draw_snap(p, now - self._snap_t0)
            if self._burst_t0 is not None:
                self._draw_burst(p, now - self._burst_t0)
            p.restore()
        except Exception:                                          # noqa: BLE001
            pass
        finally:
            p.end()

    def _draw_snap(self, p: QPainter, dt: float) -> None:
        if dt > 1.6:
            self._snap_t0 = None
            return
        sc = self._scene
        a = sc.rot + 1.0
        x0, y0 = sc.cx + sc.R * 0.6 * math.cos(a), sc.cy + sc.R * 0.6 * math.sin(a)
        path = QPainterPath(QPointF(x0, y0))
        drop = sc.S * 0.15 * min(1.0, dt * 1.5)
        path.quadTo(x0 + sc.S * 0.03, y0 + drop * 0.5, x0 + math.sin(dt * 5) * sc.S * 0.02, y0 + drop)
        c = QColor(sc.pal.thread[0])
        c.setAlpha(int(230 * (1 - dt / 1.6)))
        p.setPen(QPen(c, max(1.0, sc.u * 1.2)))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def _draw_burst(self, p: QPainter, dt: float) -> None:
        if dt > 1.4:
            self._burst_t0 = None
            return
        sc = self._scene
        for k in range(14):
            a = k * D.TAU / 14
            r = sc.R * (0.2 + 0.9 * dt / 1.4)
            D.orn_spark(p, sc.cx + r * math.cos(a), sc.cy + r * math.sin(a), sc.S * 0.012,
                        D.alpha(D.light(sc.pal.thread[0], 0.5), 255 * (1 - dt / 1.4)), 0, sc.u)


def _badge(rarity: str) -> str:
    bg = RARITY_COLOUR.get(rarity, "#5f6670")
    return (f"QLabel {{ background: {bg}; color: #ffffff; border-radius: 8px; padding: 1px 9px;"
            f" font-weight: 600; }}")


# ------------------------------------------------------------------- the window
class WebWindow(QWidget):
    """Small non-modal, resizable tool window: the current web, the collection,
    and the "Finish your batch" step (with the Web design controls after the
    hidden extra)."""

    PAGE_WEB, PAGE_COLL, PAGE_FINISH = 0, 1, 2

    def __init__(self, game: "Game", parent=None) -> None:
        super().__init__(parent, Qt.Tool)
        self.game = game
        self.viewing: Optional[dict] = None       # a web picked in the collection
        self.fin_sel: Optional[str] = None        # the web picked in the batch tray
        self._thumbs: Dict[tuple, QIcon] = {}
        self._quiet = False
        self.setWindowTitle("Charlotte's Web - PeterPiper")
        self.setObjectName("charlotteWindow")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        top = QHBoxLayout()
        self.lbl_title = QLabel("Charlotte's Web")
        self.lbl_title.setProperty("role", "subtitle")
        f = self.lbl_title.font()
        f.setBold(True)
        self.lbl_title.setFont(f)
        self.lbl_badge = QLabel("")
        top.addWidget(self.lbl_title, 1)
        top.addWidget(self.lbl_badge, 0)
        v.addLayout(top)
        self.lbl_desc = QLabel("")
        self.lbl_desc.setProperty("muted", True)
        self.lbl_desc.setWordWrap(True)
        v.addWidget(self.lbl_desc)
        self.stack = QStackedWidget()
        # page 0: the web
        self.canvas = WebCanvas()
        self.stack.addWidget(self.canvas)
        # page 1: the collection
        gal = QWidget()
        gv = QVBoxLayout(gal)
        gv.setContentsMargins(0, 0, 0, 0)
        self.lbl_count = QLabel("")
        self.lbl_count.setWordWrap(True)
        gv.addWidget(self.lbl_count)
        self.gallery = self._icon_list(120, QSize(150, 196))
        self.gallery.itemDoubleClicked.connect(self._open_item)
        gv.addWidget(self.gallery, 1)
        self.stack.addWidget(gal)
        # page 2: finish your batch
        fin = QWidget()
        fv = QVBoxLayout(fin)
        fv.setContentsMargins(0, 0, 0, 0)
        self.lbl_fin = QLabel("")
        self.lbl_fin.setWordWrap(True)
        fv.addWidget(self.lbl_fin)
        self.preview = WebCanvas()
        self.preview.setMinimumSize(160, 160)
        fv.addWidget(self.preview, 1)
        self.tray = self._icon_list(72, QSize(88, 104))
        self.tray.setFlow(QListWidget.LeftToRight)
        self.tray.setWrapping(False)
        self.tray.setFixedHeight(122)
        self.tray.currentItemChanged.connect(self._tray_pick)
        fv.addWidget(self.tray)
        self.design_box = QWidget()
        db = QVBoxLayout(self.design_box)
        db.setContentsMargins(0, 0, 0, 0)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Web design"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, len(DESIGN_STEPS) - 1)
        self.slider.setPageStep(1)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setToolTip("Make your own version: Common, Rare or Epic. The web keeps "
                               "its own seed and word.")
        self.lbl_design = QLabel(DESIGN_STEPS[0])
        self.lbl_design.setMinimumWidth(70)
        r1.addWidget(self.slider, 1)
        r1.addWidget(self.lbl_design)
        db.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Theme"))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem("As rolled", None)
        for t in sorted(THEMES, key=lambda x: x["name"]):
            self.cmb_theme.addItem(t["name"], t["key"])
        r2.addWidget(self.cmb_theme, 1)
        db.addLayout(r2)
        self.chk_all = QCheckBox("Apply to every web of this batch")
        db.addWidget(self.chk_all)
        self.slider.valueChanged.connect(self._design_changed)
        self.cmb_theme.currentIndexChanged.connect(self._design_changed)
        fv.addWidget(self.design_box)
        self.stack.addWidget(fin)
        v.addWidget(self.stack, 1)
        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("muted", True)
        self.lbl_status.setWordWrap(True)
        v.addWidget(self.lbl_status)
        self.lbl_smart = QLabel("")
        self.lbl_smart.setProperty("muted", True)
        v.addWidget(self.lbl_smart)
        btns = QHBoxLayout()
        self.btn_coll = QPushButton("Collection")
        self.btn_coll.clicked.connect(self.toggle_collection)
        self.btn_finish = QPushButton("Finish batch")
        self.btn_finish.clicked.connect(lambda: self.show_page(self.PAGE_FINISH))
        self.btn_png = QPushButton("Export picture...")
        self.btn_png.clicked.connect(self._export_one)
        self.btn_all = QPushButton("Export all...")
        self.btn_all.clicked.connect(self._export_all)
        self.btn_later = QPushButton("Later")
        self.btn_later.clicked.connect(lambda: self.show_page(self.PAGE_WEB))
        self.btn_collect = make_pink_button(None, "Collect")
        self.btn_collect.clicked.connect(self.collect)
        for b in (self.btn_coll, self.btn_finish):
            btns.addWidget(b)
        btns.addWidget(self.btn_later)
        btns.addStretch(1)
        for b in (self.btn_png, self.btn_all, self.btn_collect):
            btns.addWidget(b)
        v.addLayout(btns)
        self._geo_timer = QTimer(self)
        self._geo_timer.setSingleShot(True)
        self._geo_timer.setInterval(700)
        self._geo_timer.timeout.connect(self._remember_geometry)
        self.resize(460, 600)
        self.refresh()

    @staticmethod
    def _icon_list(icon: int, grid: QSize) -> QListWidget:
        lw = QListWidget()
        lw.setViewMode(QListWidget.IconMode)
        lw.setIconSize(QSize(icon, icon))
        lw.setGridSize(grid)
        lw.setResizeMode(QListWidget.Adjust)
        lw.setMovement(QListWidget.Static)
        lw.setWordWrap(True)
        lw.setUniformItemSizes(True)
        return lw

    # ----------------------------------------------------------------- state
    def page(self) -> int:
        return self.stack.currentIndex()

    def show_page(self, page: int) -> None:
        self.stack.setCurrentIndex(page)
        if page != self.PAGE_WEB:
            self.viewing = None if page == self.PAGE_FINISH else self.viewing
        self.refresh()

    def shown_web(self) -> Optional[dict]:
        if self.page() == self.PAGE_FINISH:
            return self._fin_web()
        return self.viewing or self.game.current_web()

    def refresh(self) -> None:
        try:
            self._refresh()
        except Exception:                                          # noqa: BLE001
            pass

    def _refresh(self) -> None:
        page = self.page()
        web = self.shown_web()
        if page == self.PAGE_WEB:
            self.canvas.set_web(web)
        if page == self.PAGE_COLL:
            self.lbl_title.setText("Your collection")
            self.lbl_desc.setText("Double-click a web to see it large.")
            self.lbl_badge.setVisible(False)
        elif web:
            th = BY_KEY[shown_theme(web)]
            self.lbl_title.setText(th["name"])
            self.lbl_desc.setText(th["desc"])
            r = shown_rarity(web)
            self.lbl_badge.setText(RARITY_LABEL.get(r, ""))
            self.lbl_badge.setStyleSheet(_badge(r))
            self.lbl_badge.setVisible(True)
        else:
            self.lbl_title.setText("Charlotte's Web")
            self.lbl_desc.setText("Every movie you analyse spins its own web.")
            self.lbl_badge.setVisible(False)
        self.lbl_status.setText("" if page == self.PAGE_FINISH else
                                self.game.status_text(self.viewing if page == self.PAGE_WEB else None))
        self.lbl_status.setVisible(page != self.PAGE_FINISH)
        sm = _smart_line()
        self.lbl_smart.setVisible(bool(sm))
        self.lbl_smart.setText(sm or "")
        tray = self.game.tray()
        self.btn_coll.setText("Back to the web" if page == self.PAGE_COLL else "Collection")
        self.btn_coll.setVisible(page != self.PAGE_FINISH)
        self.btn_finish.setText(f"Finish batch ({len(tray)})")
        self.btn_finish.setVisible(page == self.PAGE_WEB and bool(tray))
        self.btn_png.setVisible(page != self.PAGE_FINISH)
        self.btn_png.setEnabled(web is not None)
        self.btn_all.setVisible(page == self.PAGE_COLL)
        self.btn_all.setEnabled(bool(self.game.collection()))
        self.btn_later.setVisible(page == self.PAGE_FINISH)
        self.btn_collect.setVisible(page == self.PAGE_FINISH)
        self.btn_collect.setEnabled(bool(tray))
        if page == self.PAGE_COLL:
            self._fill_gallery()
        elif page == self.PAGE_FINISH:
            self._fill_tray(tray)

    # -------------------------------------------------------------- gallery
    def toggle_collection(self) -> None:
        self.show_page(self.PAGE_WEB if self.page() == self.PAGE_COLL else self.PAGE_COLL)

    def _thumb(self, web: dict, size: int) -> QIcon:
        key = (web.get("id"), web.get("n"), level_of(web), shown_theme(web), web.get("word"), size)
        ic = self._thumbs.get(key)
        if ic is None:
            ic = QIcon(QPixmap.fromImage(render_web(web, size, size, t=1.0)))
            self._thumbs[key] = ic
        return ic

    def _fill_gallery(self) -> None:
        coll = self.game.collection()
        themes = {w.get("theme") for w in coll}
        rare = sum(1 for w in coll if w.get("rarity") == "rare")
        epic = sum(1 for w in coll if w.get("rarity") == "epic")
        self.lbl_count.setText(f"{len(coll)} webs - {len(themes)} of {len(THEMES)} themes, "
                               f"{rare} rare, {epic} epic found")
        self.gallery.clear()
        for web in reversed(coll):
            th = BY_KEY[shown_theme(web)]
            r = RARITY_LABEL.get(shown_rarity(web), "")
            date = (web.get("date") or "")[:10]
            it = QListWidgetItem(self._thumb(web, 120),
                                 f"{th['name']} ({r})\n{web.get('movie', '')}\n"
                                 f"{date}  {web.get('word') or ''}")
            it.setData(Qt.UserRole, web.get("id"))
            it.setToolTip(f"{th['name']} - {th['desc']}\n{r} - {web.get('n', 0)} cells by hand")
            self.gallery.addItem(it)

    def _open_item(self, item) -> None:
        wid = item.data(Qt.UserRole)
        for w in self.game.collection():
            if w.get("id") == wid:
                self.viewing = w
        self.stack.setCurrentIndex(self.PAGE_WEB)
        self.refresh()

    def selected_web(self) -> Optional[dict]:
        if self.page() == self.PAGE_COLL:
            it = self.gallery.currentItem()
            if it is not None:
                for w in self.game.collection():
                    if w.get("id") == it.data(Qt.UserRole):
                        return w
        return self.shown_web()

    # --------------------------------------------------------- finish batch
    def _fin_web(self) -> Optional[dict]:
        tray = self.game.tray()
        for w in tray:
            if w.get("id") == self.fin_sel:
                return w
        return tray[0] if tray else None

    def _fill_tray(self, tray: List[dict]) -> None:
        self._quiet = True
        try:
            egg = egg_found()
            self.design_box.setVisible(egg)
            if not tray:
                self.lbl_fin.setText("No webs are waiting. Webs of a movie queue wait here "
                                     "until the batch is finished.")
            elif egg:
                self.lbl_fin.setText(f"Your batch: {len(tray)} webs. Make your own design, "
                                     "then Collect.")
            else:
                self.lbl_fin.setText(f"Your batch: {len(tray)} webs are ready to collect.")
            cur = self._fin_web()
            self.fin_sel = cur.get("id") if cur else None
            self.tray.clear()
            for w in tray:
                it = QListWidgetItem(self._thumb(w, 72), RARITY_LABEL.get(shown_rarity(w), ""))
                it.setData(Qt.UserRole, w.get("id"))
                it.setToolTip(f"{BY_KEY[shown_theme(w)]['name']} - {w.get('movie', '')}")
                self.tray.addItem(it)
                if w.get("id") == self.fin_sel:
                    self.tray.setCurrentItem(it)
            self.preview.set_web(cur)
            if cur:
                d = cur.get("design")
                self.slider.setValue(0 if not d else RARITIES.index(d) + 1 if d in RARITIES else 0)
                self.lbl_design.setText(DESIGN_STEPS[self.slider.value()])
                i = self.cmb_theme.findData(cur.get("design_theme"))
                self.cmb_theme.setCurrentIndex(max(0, i))
        finally:
            self._quiet = False

    def _tray_pick(self, item, _prev=None) -> None:
        if self._quiet or item is None:
            return
        self.fin_sel = item.data(Qt.UserRole)
        self.refresh()

    def _design_changed(self, *_a) -> None:
        self.lbl_design.setText(DESIGN_STEPS[self.slider.value()])
        if self._quiet:
            return
        v = self.slider.value()
        design = None if v == 0 else RARITIES[v - 1]
        theme = self.cmb_theme.currentData()
        ids = None if self.chk_all.isChecked() else [self.fin_sel]
        self.game.set_design(ids, design, theme)
        self.refresh()

    def collect(self) -> None:
        n = self.game.collect_tray()
        self.fin_sel = None
        self.stack.setCurrentIndex(self.PAGE_COLL)
        self.refresh()
        if n:
            self.lbl_status.setText(f"{n} webs joined your collection.")

    # --------------------------------------------------------------- export
    def _ask_path(self, title: str, name: str) -> Optional[str]:
        from PySide6.QtCore import QStandardPaths
        folder = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or str(Path.home())
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "web"
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path(folder) / name),
                                              "PNG picture (*.png)",
                                              options=QFileDialog.DontConfirmOverwrite)
        if not path:
            return None
        if not path.lower().endswith(".png"):
            path += ".png"
        return path

    def _export_one(self) -> None:
        web = self.selected_web()
        if not web:
            return
        th = BY_KEY[shown_theme(web)]["name"]
        path = self._ask_path("Export picture", f"Charlotte's web - {web.get('movie', '')} - {th}.png")
        if path:
            try:
                out = export_png(web, path)
                self.lbl_status.setText(f"Saved {out.name}")
            except Exception as exc:                               # noqa: BLE001
                self.lbl_status.setText(f"Could not save the picture: {exc}")

    def _export_all(self) -> None:
        coll = self.game.collection()
        if not coll:
            return
        path = self._ask_path("Export all webs", "Charlotte's webs.png")
        if path:
            try:
                out = export_contact_sheet(coll, path)
                self.lbl_status.setText(f"Saved {out.name}")
            except Exception as exc:                               # noqa: BLE001
                self.lbl_status.setText(f"Could not save the picture: {exc}")

    # ------------------------------------------------------------- geometry
    def moveEvent(self, ev) -> None:                             # noqa: N802
        self._geo_timer.start()
        super().moveEvent(ev)

    def resizeEvent(self, ev) -> None:                           # noqa: N802
        self._geo_timer.start()
        super().resizeEvent(ev)

    def _remember_geometry(self) -> None:
        try:
            g = self.geometry()
            d = _load()
            d["window"]["geo"] = [g.x(), g.y(), g.width(), g.height()]
            _save(d)
        except Exception:                                          # noqa: BLE001
            pass

    def restore_geometry(self) -> None:
        try:
            geo = _load()["window"].get("geo")
            if geo and len(geo) == 4:
                from PySide6.QtCore import QRect
                r = QRect(*[int(x) for x in geo])
                if QApplication.screenAt(r.center()) is not None:
                    self.setGeometry(r)
                else:
                    self.resize(r.width(), r.height())
        except Exception:                                          # noqa: BLE001
            pass

    def closeEvent(self, ev) -> None:                            # noqa: N802
        try:
            self._remember_geometry()
            self.game.set_closed_by_user(True)
        except Exception:                                          # noqa: BLE001
            pass
        super().closeEvent(ev)


# ------------------------------------------------------------------- the reveal
class RevealDialog(QDialog):
    """The hidden extra was found: a little spider drops in and spins an epic web."""

    def __init__(self, parent=None, on_done: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Charlotte's Web - PeterPiper")
        self.setModal(False)
        self.on_done = on_done
        self._t0 = time.monotonic()
        self.t_override: Optional[float] = None
        seed = int.from_bytes(os.urandom(5), "big")
        self.web = {"theme": random.choice(["rose_quartz", "golden_thread", "starweaver", "royal",
                                            "aurora", "sakura"]),
                    "seed": seed, "params": D.new_params(seed), "n": 0, "word": None,
                    "rarity": "epic"}
        v = QVBoxLayout(self)
        self.art = QWidget()
        self.art.setMinimumSize(360, 300)
        self.art.paintEvent = self._paint_art                     # type: ignore[assignment]
        v.addWidget(self.art, 1)
        t = QLabel("Charlotte's Web magic!")
        t.setProperty("role", "title")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        m = QLabel("From now on every web is Rare or Epic, and when a batch is finished "
                   "you can design your own version of its webs before you collect them.")
        m.setWordWrap(True)
        m.setAlignment(Qt.AlignCenter)
        v.addWidget(m)
        b = make_pink_button(self, "Show me my web")
        b.clicked.connect(self._done)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.art.update)
        self.timer.start()
        self.resize(420, 470)

    def _done(self) -> None:
        self.timer.stop()
        self.accept()
        if self.on_done:
            try:
                self.on_done()
            except Exception:                                      # noqa: BLE001
                pass

    def _paint_art(self, ev) -> None:
        p = QPainter(self.art)
        try:
            t = self.t_override if self.t_override is not None else time.monotonic() - self._t0
            w, h = self.art.width(), self.art.height()
            side = min(w, h)
            n = int(min(8, max(0, (t - 1.2) * 4)))
            sc = D.Scene(self.web["theme"], self.web["params"], self.web["seed"], n, side, side, 3)
            p.translate((w - side) / 2, (h - side) / 2)
            sc.draw_background(p)
            sc.draw_web(p)
            drop = min(1.0, t / 1.2)
            hub = QPointF(sc.cx, sc.cy)
            if drop < 1.0:
                y = -sc.S * 0.1 + (hub.y() + sc.S * 0.1) * (1 - (1 - drop) ** 2)
                p.setPen(QPen(QColor(255, 255, 255, 200), 1))
                p.drawLine(QPointF(hub.x(), 0), QPointF(hub.x(), y))
                sc.creatures = [(QPointF(hub.x(), y),) + tuple(sc.creatures[0][1:])]
            sc.draw_overlay(p, t)
        except Exception:                                          # noqa: BLE001
            pass
        finally:
            p.end()


BUTTON_TEXT = "\U0001F578 Charlotte's Web"
BUTTON_TIP = ("A little game inside PeterPiper: every movie you analyse by hand grows a web "
              "for your collection")


def make_pink_button(parent=None, text: str = BUTTON_TEXT) -> QPushButton:
    """The pink button of the little game (its own colours, readable on every app
    theme). The program stays PeterPiper; only this game is "Charlotte's Web"."""
    b = QPushButton(text, parent)
    b.setObjectName("charlotteButton")
    b.setStyleSheet(pink_button_style())
    b.setCursor(Qt.PointingHandCursor)
    if text == BUTTON_TEXT:
        b.setToolTip(BUTTON_TIP)
    return b


# --------------------------------------------------------------------- the game
class Game:
    """Follows the app's events and keeps the webs. Everything is guarded."""

    def __init__(self) -> None:
        self.movie: Optional[str] = None
        self.window_ref = None
        self.ui: Optional[WebWindow] = None
        self.reveal = None
        self._offered = False

    # ----------------------------------------------------------------- store
    def collection(self) -> List[dict]:
        return list(_load()["collection"])

    def tray(self) -> List[dict]:
        return list(_load()["tray"])

    def all_webs(self) -> List[dict]:
        d = _load()
        return d["collection"] + d["tray"] + list(d["growing"].values())

    def current_web(self) -> Optional[dict]:
        if not self.movie:
            return None
        d = _load()
        return d["growing"].get(_key(self.movie)) or self._last_finished(d, self.movie)

    @staticmethod
    def _last_finished(d: dict, nd2) -> Optional[dict]:
        k = _key(nd2)
        for w in reversed(d["collection"] + d["tray"]):
            if w.get("key") == k:
                return w
        return None

    @staticmethod
    def _growing(d: dict, nd2, create: bool = True) -> Optional[dict]:
        k = _key(nd2)
        web = d["growing"].get(k)
        if web is None and create:
            web = make_web(nd2, d)
            d["growing"][k] = web
        return web

    def status_text(self, viewing: Optional[dict] = None) -> str:
        if viewing:
            date = (viewing.get("date") or "")[:10]
            return f"From your collection: {viewing.get('movie', '')}, {date}"
        if not self.movie:
            return "Open a movie to start its web."
        web = self.current_web()
        n = int(web.get("n", 0)) if web else 0
        cells = f"{n} cell{'s' if n != 1 else ''} drawn by hand"
        if web and web.get("done"):
            parts = [f"Finished with {cells} - draw more and SAVE again for a new web"]
        else:
            parts = [f"{cells} - SAVE finishes the web" if n else
                     "Draw a cell by hand to grow this web"]
        try:
            from .. import batchqueue
            if batchqueue.items():
                pos = batchqueue.position(self.movie)
                if pos:
                    parts.append(f"Web {pos[0]} of {pos[1]} in your batch")
        except Exception:                                          # noqa: BLE001
            pass
        return "  -  ".join(parts)

    def set_closed_by_user(self, closed: bool) -> None:
        d = _load()
        d["window"]["closed"] = bool(closed)
        _save(d)

    # ----------------------------------------------------------------- batch
    @staticmethod
    def batch_done() -> bool:
        """Every queued movie saved / exported / skipped (or no queue any more)."""
        try:
            from .. import batchqueue
            items = batchqueue.items()
        except Exception:                                          # noqa: BLE001
            return True
        return all(it.get("status") != "todo" for it in items)

    def set_design(self, ids: Optional[List[str]], design: Optional[str],
                   theme: Optional[str] = None) -> int:
        """The user's own design for webs in the batch tray (ids None = all of them).
        Only with the hidden extra. The original roll stays in 'rarity' / 'theme'."""
        if not egg_found():
            return 0
        if design is not None and design not in RARITIES:
            return 0
        if theme is not None and theme not in BY_KEY:
            theme = None
        d = _load()
        n = 0
        for w in d["tray"]:
            if ids is None or w.get("id") in ids:
                w["design"] = design
                w["design_theme"] = theme
                n += 1
        _save(d)
        return n

    def collect_tray(self) -> int:
        d = _load()
        tray = d["tray"]
        d["collection"].extend(tray)
        d["tray"] = []
        _save(d)
        self._offered = False
        return len(tray)

    def _offer_finish(self) -> None:
        """When a batch is done, show the "Finish your batch" step once."""
        if self._offered or not self.tray() or not self.batch_done():
            return
        self._offered = True
        ui = open_window(self.parent_window(), remember=False)
        if ui is not None:
            ui.show_page(WebWindow.PAGE_FINISH)

    # --------------------------------------------------------------- windows
    def attach(self, window) -> None:
        """The pink button and the View-menu action in an analysis window."""
        if window is None or getattr(window, "_charlotte_attached", False):
            return
        try:
            window._charlotte_attached = True
        except Exception:                                          # noqa: BLE001
            return
        self.window_ref = weakref.ref(window)
        try:
            btn = make_pink_button(None)
            btn.clicked.connect(lambda: open_window(window))
            bar = getattr(window, "extras_bar", None)
            if isinstance(bar, QLayout):
                bar.addWidget(btn)
            elif isinstance(bar, QWidget):
                lay = bar.layout()
                if lay is None:
                    lay = QHBoxLayout(bar)
                    lay.setContentsMargins(0, 0, 0, 0)
                lay.addWidget(btn)
            else:
                window.statusBar().addPermanentWidget(btn)
            window._charlotte_button = btn
        except Exception:                                          # noqa: BLE001
            pass
        try:
            menu = None
            for a in window.menuBar().actions():
                if a.menu() is not None and a.text().replace("&", "").strip().lower() == "view":
                    menu = a.menu()
                    break
            if menu is not None:
                menu.addSeparator()
                act = QAction("Charlotte's Web", window)
                act.triggered.connect(lambda: open_window(window))
                menu.addAction(act)
                window._charlotte_action = act
        except Exception:                                          # noqa: BLE001
            pass

    def parent_window(self):
        w = self.window_ref() if self.window_ref else None
        try:
            import shiboken6
            if w is not None and not shiboken6.isValid(w):
                return None
        except Exception:                                          # noqa: BLE001
            pass
        return w

    def live_ui(self) -> Optional[WebWindow]:
        ui = self.ui
        if ui is not None:
            try:
                import shiboken6
                if not shiboken6.isValid(ui):
                    self.ui = ui = None
            except Exception:                                      # noqa: BLE001
                pass
        return ui

    def refresh_ui(self) -> Optional[WebWindow]:
        ui = self.live_ui()
        if ui is not None:
            ui.refresh()
        return ui

    # ---------------------------------------------------------------- events
    def on_main_window_ready(self, window=None, **_k) -> None:
        self.attach(window)
        self._offer_finish()

    def on_movie_opened(self, nd2=None, window=None, **_k) -> None:
        if window is not None:
            self.attach(window)
        if not nd2:
            return
        self.movie = str(nd2)
        d = _load()
        if _key(nd2) not in d["growing"] and self._last_finished(d, nd2) is None:
            self._growing(d, nd2)
            _save(d)
        ui = self.live_ui()
        if ui is not None:
            ui.viewing = None
            ui.refresh()
        elif d["window"].get("closed") is False:       # the user had it open last time
            open_window(window or self.parent_window(), remember=False)

    def on_roi_added(self, nd2=None, manual=False, n_cells=None, **_k) -> None:
        if not manual or not nd2:
            return
        d = _load()
        web = self._growing(d, nd2)
        web["n"] = int(web.get("n", 0)) + 1
        web["peak"] = max(int(web.get("peak", 0)), web["n"])
        _save(d)
        if self.movie is None:
            self.movie = str(nd2)
        ui = self.refresh_ui()
        if ui is not None and _key(self.movie) == _key(nd2):
            ui.canvas.grow()

    def on_roi_removed(self, nd2=None, n_cells=None, **_k) -> None:
        if not nd2:
            return
        d = _load()
        web = self._growing(d, nd2, create=False)
        if not web or int(web.get("n", 0)) <= 0:
            return
        peak = int(web.get("peak", 0))
        floor = max(1, math.ceil(peak / 2)) if peak else 0     # never fully unspins
        if web["n"] > floor:
            web["n"] -= 1
            web["snaps"] = int(web.get("snaps", 0)) + 1
            _save(d)
            ui = self.refresh_ui()
            if ui is not None:
                ui.canvas.snap()

    def on_saved(self, nd2=None, path=None, n_cells=None, **_k) -> None:
        if not nd2:
            return
        d = _load()
        k = _key(nd2)
        web = d["growing"].get(k)
        if web is None:
            # already finished: a fresh web starts for more cells drawn by hand
            self._growing(d, nd2)
            _save(d)
            self.refresh_ui()
            return
        if int(web.get("n", 0)) == 0 and self._last_finished(d, nd2) is not None:
            return                                   # nothing new drawn by hand since
        rng = random.Random(int(web["seed"]) ^ 0xC0FFEE)
        web["word"] = pick_word(rng, d["collection"] + d["tray"])
        web["date"] = _now_iso()
        web["done"] = True
        try:
            from .. import batchqueue
            web["queued"] = batchqueue.position(nd2) is not None
        except Exception:                                          # noqa: BLE001
            web["queued"] = False
        d["growing"].pop(k, None)
        (d["tray"] if web["queued"] else d["collection"]).append(web)
        _save(d)
        if self.movie is None:
            self.movie = str(nd2)
        ui = self.refresh_ui()
        if ui is not None and _key(self.movie) == k:
            ui.canvas.write_word()
        QTimer.singleShot(2500, self._offer_finish_safe)

    def _offer_finish_safe(self) -> None:
        try:
            self._offer_finish()
        except Exception:                                          # noqa: BLE001
            pass

    def on_exported(self, nd2=None, folder=None, **_k) -> None:
        ui = self.refresh_ui()
        if ui is not None:
            ui.canvas.burst()
        self._offer_finish()

    def on_queue_changed(self, **_k) -> None:
        self.refresh_ui()
        self._offer_finish()

    def on_movie_closed(self, nd2=None, **_k) -> None:
        if not nd2:
            return
        d = _load()
        k = _key(nd2)
        web = d["growing"].get(k)
        if web is not None and int(web.get("n", 0)) == 0:
            d["growing"].pop(k, None)               # an empty web is not kept (its seed is)
            if web.get("index") == d["started"] - 1:
                d["started"] -= 1                   # ... and its place in the every-3rd count
            _save(d)
        if self.movie and _key(self.movie) == k:
            self.movie = None
        self.refresh_ui()

    def on_found(self) -> None:
        """The hidden extra was just found: a reveal, then the window."""
        try:
            parent = self.parent_window() or QApplication.activeWindow()
            dlg = RevealDialog(parent, on_done=lambda: open_window(parent))
            dlg.show()
            self.reveal = dlg
            self.refresh_ui()
        except Exception:                                          # noqa: BLE001
            pass


_GAME: Optional[Game] = None
_WATCHER: Optional[KeyWatcher] = None
_EVENTS = ("main_window_ready", "movie_opened", "roi_added", "roi_removed", "saved",
           "exported", "movie_closed", "queue_changed")
_HANDLERS: Dict[str, Callable] = {}


def game() -> Game:
    global _GAME
    if _GAME is None:
        _GAME = Game()
    return _GAME


def _guard(fn):
    def run(**kw):
        try:
            fn(**kw)
        except Exception:                                          # noqa: BLE001
            pass
    run.__name__ = getattr(fn, "__name__", "charlotte")
    return run


def install(app=None) -> None:
    """Idempotent and fast (no file access): the key watcher plus the event
    listeners. Called by app.py inside a guarded import."""
    global _WATCHER
    try:
        app = app or QApplication.instance()
        g = game()
        if _WATCHER is None and app is not None:
            _WATCHER = KeyWatcher(g.on_found, parent=app)
            app.installEventFilter(_WATCHER)
        from .. import events
        for name in _EVENTS:
            if name not in _HANDLERS:
                _HANDLERS[name] = _guard(getattr(g, "on_" + name))
            events.on(name, _HANDLERS[name])
    except Exception:                                              # noqa: BLE001
        pass


def uninstall() -> None:
    """Tests: undo install()."""
    global _WATCHER, _GAME
    try:
        app = QApplication.instance()
        if _WATCHER is not None and app is not None:
            app.removeEventFilter(_WATCHER)
        from .. import events
        for name, fn in _HANDLERS.items():
            events.off(name, fn)
    except Exception:                                              # noqa: BLE001
        pass
    _WATCHER = None
    _GAME = None
    _HANDLERS.clear()


def watcher() -> Optional[KeyWatcher]:
    return _WATCHER


def open_window(parent=None, remember: bool = True) -> Optional[WebWindow]:
    """Show the Charlotte's Web window (non-modal tool window over the analysis window)."""
    try:
        g = game()
        if remember:
            g.set_closed_by_user(False)
        ui = g.live_ui()
        if ui is None:
            parent = parent or g.parent_window()
            ui = WebWindow(g, parent)
            ui.restore_geometry()
            g.ui = ui
        ui.viewing = None
        ui.refresh()
        ui.show()
        ui.raise_()
        return ui
    except Exception:                                              # noqa: BLE001
        return None
