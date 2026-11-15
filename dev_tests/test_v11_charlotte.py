"""
Developer test (not shipped): PeterPiper 1.1 - Charlotte's Web, the hidden minigame
(app/peterpiper/gui/charlotte*.py). Made-up movie names only.

    QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python dev_tests/test_v11_charlotte.py

A) the hidden extra: install() is idempotent and only observes keys (a line edit still
   gets every letter); "cha" + "r" held 2 s does nothing before the 20-logo-click
   "palettes" extra; after it, "cha" + r held 2 s (auto-repeat presses, auto-repeat
   press/release pairs, or a plain press ... release) unlocks "charlotte" and shows the
   reveal; a 1 s hold and other words ("cxa", "chb", "ha") do not.
B) 50 themes, about a quarter not spiders, every part of a theme known to the drawing;
   50 distinct kind words incl. the four homage words, none unkind (crude blacklist).
C) every theme renders at n = 0, 1, 3, 5, 6, 10, 20, 60 (common / rare / epic) without
   an error and within the time budget (600 x 600 frame); the drawn elements grow with
   n and stay capped; common < rare < epic in adornment.
D) 200 webs -> 200 distinct seeds and 200 distinct pictures; a web re-rendered from its
   stored params (JSON round trip through userprefs) is identical.
E) rarity: without the extra exactly every 3rd web started is rare / epic (10 of 30),
   the counter survives a restart; with the extra every web is rare / epic; the epic
   share is near the documented odds.
F) the events: the pink button goes into window.extras_bar (QWidget or QLayout) or the
   status bar, with text contrast >= 4.5 on every app theme; the View-menu action;
   roi_added (by hand only) grows the web, roi_removed snaps but never unspins; SAVE
   writes a word; a single movie goes straight into "collection"; queued movies wait in
   the batch tray (with queued=True and n) until "Collect"; the design controls are
   shown only with the extra and the user's design survives re-render and export;
   batch progress text; an empty web is dropped on close.
G) export: one web as a 1600 x 1600 PNG and a contact sheet, never overwriting.
H) screenshots -> _out/shots/: 10 themes at n = 1, 5, 12; common / rare / epic of the
   same themes; the window, the gallery, the batch step, the reveal, the pink button.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "charlotte_test"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
if os.name == "nt" and Path("C:/Windows/Fonts").is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtCore import QEvent, Qt                                  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeyEvent                    # noqa: E402
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLineEdit,  # noqa: E402
                               QMainWindow, QMessageBox, QWidget)

APP = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

from peterpiper import achievements, batchqueue, events, userprefs    # noqa: E402
from peterpiper.gui import charlotte as CH                             # noqa: E402
from peterpiper.gui import charlotte_draw as D                         # noqa: E402
from peterpiper.gui import theme as TH                                 # noqa: E402
from peterpiper.gui.charlotte_themes import THEMES                     # noqa: E402
from peterpiper.gui.charlotte_words import HOMAGE, WORDS               # noqa: E402

N = [0]
FAILS = []
BUDGET_MS = 40.0


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(ms=0):
    end = time.monotonic() + ms / 1000.0
    while True:
        APP.processEvents()
        if time.monotonic() >= end:
            break


def img_hash(img: QImage) -> str:
    img = img.convertToFormat(QImage.Format_ARGB32)
    return hashlib.md5(bytes(img.constBits())).hexdigest()


def forget(key):
    d = userprefs.load("achievements")
    d.get("found", {}).pop(key, None)
    userprefs.save("achievements", d)


def reset_store():
    p = userprefs.path("charlotte")
    if p.exists():
        p.unlink()


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


CLK = Clock()
TS = [1]


def key(widget, press, k, text="", rep=False):
    ev = QKeyEvent(QEvent.KeyPress if press else QEvent.KeyRelease, k, Qt.NoModifier, text, rep)
    TS[0] += 1
    ev.setTimestamp(TS[0])
    QApplication.sendEvent(widget, ev)


def type_word(widget, word, dt=0.12):
    for ch in word:
        k = getattr(Qt, "Key_" + ch.upper())
        key(widget, True, k, ch)
        CLK.t += 0.05
        key(widget, False, k, ch)
        CLK.t += dt


def hold_r(widget, seconds, mode="repeat"):
    key(widget, True, Qt.Key_R, "r")
    t_end = CLK.t + seconds
    if mode == "plain":
        CLK.t = t_end
        key(widget, False, Qt.Key_R, "r")
        return
    while CLK.t < t_end - 1e-9:
        CLK.t = min(t_end, CLK.t + 0.04)
        if mode == "pairs":
            key(widget, False, Qt.Key_R, "r", True)
        key(widget, True, Qt.Key_R, "r", True)
    CLK.t += 0.03
    key(widget, False, Qt.Key_R, "r")


# --------------------------------------------------------------------------- A
def part_a():
    events.clear()
    CH.uninstall()
    t0 = time.perf_counter()
    CH.install(APP)
    dt = (time.perf_counter() - t0) * 1000
    w1 = CH.watcher()
    CH.install(APP)
    ok("A install() is idempotent (one watcher, one listener per event)",
       CH.watcher() is w1 and all(len(events._listeners.get(n, [])) == 1 for n in CH._EVENTS))
    ok("A install() is fast", dt < 200, f"{dt:.1f} ms")
    w1.clock = CLK
    le = QLineEdit()
    le.show()
    pump()
    type_word(le, "cha")
    hold_r(le, 2.5)
    ok("A locked before the 'palettes' extra", not achievements.unlocked("charlotte"))
    ok("A keys are only observed (the line edit got every letter)",
       le.text().startswith("char") and set(le.text()[3:]) == {"r"}, le.text()[:12])
    achievements.unlock("palettes")
    le.clear()
    type_word(le, "cha")
    hold_r(le, 1.0)
    ok("A a 1 s hold does not unlock", not achievements.unlocked("charlotte"))
    for word in ("cxa", "chb", "ha", "chaz"):
        CLK.t += 3
        type_word(le, word)
        hold_r(le, 2.6)
        ok(f"A '{word}' + held r does not unlock", not achievements.unlocked("charlotte"))
    CLK.t += 3
    type_word(le, "cha")
    hold_r(le, 2.1, "repeat")
    ok("A 'cha' + r held 2 s (auto-repeat presses) unlocks", achievements.unlocked("charlotte"))
    pump(50)
    rv = CH.game().reveal
    ok("A the reveal is shown", rv is not None and rv.isVisible())
    if rv is not None:
        rv.t_override = 3.5
        rv.art.repaint()
        rv.grab().save(str(SHOTS / "charlotte_reveal.png"))
        rv.close()
    for mode in ("pairs", "plain"):
        forget("charlotte")
        w1.done = False
        CLK.t += 3
        type_word(le, "char")
        hold_r(le, 2.05, mode)
        ok(f"A 'char' + r held 2 s ({mode}) unlocks", achievements.unlocked("charlotte"))
        rv = CH.game().reveal
        if rv is not None:
            rv.close()
    forget("charlotte")
    w1.done = False
    CLK.t += 3
    type_word(le, "cha")
    key(le, True, Qt.Key_R, "r")
    CLK.t += 1.0
    key(le, False, Qt.Key_R, "r")
    CLK.t += 0.3
    key(le, True, Qt.Key_R, "r")
    CLK.t += 1.0
    key(le, False, Qt.Key_R, "r")
    ok("A two separate 1 s r presses do not unlock", not achievements.unlocked("charlotte"))
    le.close()


# --------------------------------------------------------------------------- B
def part_b():
    ok("B 50 themes, unique keys and names",
       len(THEMES) == 50 and len({t["key"] for t in THEMES}) == 50
       and len({t["name"] for t in THEMES}) == 50)
    non = [t for t in THEMES if not t["spider"]]
    ok("B about 25 % are not spiders", 0.2 <= len(non) / 50 <= 0.3, f"{len(non)} of 50")
    bad = []
    for t in THEMES:
        if t["style"] not in D.STYLES or t["orn"] not in D.ORNAMENTS or \
                t["creature"] not in D.SPRITES or not t["desc"] or \
                any(layer[0] not in D.BACKGROUNDS for layer in t["bg"]):
            bad.append(t["key"])
    ok("B every theme's style, ornament, creature and background are drawn", not bad, bad)
    ok("B 50 distinct kind words", len(WORDS) == 50 and len(set(WORDS)) == 50)
    ok("B the homage words are there", all(w in WORDS for w in ("SOME CELLS", "TERRIFIC",
                                                              "RADIANT", "HUMBLE")))
    black = ("BAD", "UGLY", "STUPID", "DUMB", "WORST", "LAZY", "FAIL", "WRONG", "NOISY",
             "MESSY", "POOR", "AWFUL", "TERRIBLE", "HATE", "LOSER", "BORING", "SLOPPY", "WEAK",
             "OUTLIER", "ARTIFACT", "JUNK", "MEH", "NOT ", "NO ", "BLUR", "ERROR", "SAD")
    unkind = [w for w in WORDS if any(b in w + " " for b in black) and w not in HOMAGE]
    ok("B no unkind or data-quality words", not unkind, unkind)
    ok("B words are short capitals", all(w == w.upper() and len(w) <= 14 for w in WORDS))


# --------------------------------------------------------------------------- C
def part_c():
    D.render_image("rose_quartz", D.new_params(1), 1, 5, 600, 600, word="HELLO", level=3)
    ns = (0, 1, 3, 5, 6, 10, 20, 60)
    errors, slow, worst = [], [], (0.0, "")
    for i, t in enumerate(THEMES):
        seed = 777 + i
        prm = D.new_params(seed)
        for n in ns:
            lv = (0, 2, 3)[(i + n) % 3]
            try:
                best = 1e9
                for _ in range(3):
                    t0 = time.perf_counter()
                    D.render_image(t["key"], prm, seed, n, 600, 600, t=1.0,
                                   word="WELL SPUN" if n in (5, 60) else None, level=lv)
                    best = min(best, (time.perf_counter() - t0) * 1000)
                if best > worst[0]:
                    worst = (best, f"{t['key']} n={n} level={lv}")
                if best > BUDGET_MS:
                    slow.append((t["key"], n, lv, round(best, 1)))
            except Exception as exc:                               # noqa: BLE001
                errors.append((t["key"], n, repr(exc)))
    ok("C every theme renders at n = 0..60 without an error", not errors, errors[:3])
    ok(f"C every 600 x 600 frame renders within {BUDGET_MS:.0f} ms", not slow,
       f"worst {worst[0]:.1f} ms ({worst[1]}) {slow[:3]}")
    grow_bad, caps = [], []
    for t in THEMES[::5] + [THEMES[-1]]:
        prm = D.new_params(99)
        for lv in (0, 2, 3):
            tot = [D.Scene(t["key"], prm, 99, n, 600, 600, lv).stats["total"] for n in range(0, 61)]
            if any(b < a for a, b in zip(tot, tot[1:])) or tot[10] <= tot[1]:
                grow_bad.append((t["key"], lv))
            caps.append(max(tot))
            if tot[40] != tot[60]:
                grow_bad.append((t["key"], lv, "not capped"))
    ok("C drawn elements grow with n (never fewer) and stop growing (capped)", not grow_bad, grow_bad)
    ok("C element counts stay capped", max(caps) < 2600, f"max {max(caps)}")
    s5 = D.Scene("golden_thread", D.new_params(5), 5, 5, 600, 600, 0).stats
    st = [D.Scene("golden_thread", D.new_params(5), 5, 5, 600, 600, lv).stats for lv in (0, 2, 3)]
    ok("C at 5 cells: common < rare < epic in adornment",
       st[0]["ornaments"] < st[1]["ornaments"] < st[2]["ornaments"]
       and st[0]["motes"] == 0 < st[1]["motes"] < st[2]["motes"] and st[2]["signature"] > 0,
       f"{s5['ornaments']} / {st[1]['ornaments']} / {st[2]['ornaments']}")
    s0 = D.Scene("golden_thread", D.new_params(5), 5, 0, 600, 600, 1).stats
    ok("C at 0 cells: only a few anchor / radial threads", s0["rings"] == 0 and s0["radials"] <= 5,
       s0)


# --------------------------------------------------------------------------- D
def part_d():
    store = {"seeds": [], "collection": [], "tray": [], "started": 0}
    webs = [CH.make_web(f"C:/made up/movie {i}.nd2", store, egg=False) for i in range(200)]
    ok("D 200 webs -> 200 distinct seeds", len({w["seed"] for w in webs}) == 200)
    used = list(store["seeds"])
    ok("D a re-roll never repeats a used seed", CH.new_seed("x", used) not in set(used))
    hashes = set()
    for w in webs:
        w["n"] = 5
        hashes.add(img_hash(CH.render_web(w, 96, 96)))
    ok("D 200 webs -> 200 distinct pictures", len(hashes) == 200, len(hashes))
    reset_store()
    w = webs[7]
    w["n"], w["word"], w["done"] = 6, "SPLENDID", True
    h1 = img_hash(CH.render_web(w, 300, 300))
    d = CH._load()
    d["collection"].append(w)
    CH._save(d)
    back = json.loads(userprefs.path("charlotte").read_text(encoding="utf-8"))["collection"][-1]
    h2 = img_hash(CH.render_web(back, 300, 300))
    ok("D re-render from the stored params is identical", h1 == h2)
    ok("D the stored web holds only seed, numbers and metadata",
       set(back) <= {"id", "seed", "theme", "params", "movie", "key", "started", "date", "n",
                     "peak", "snaps", "word", "index", "rarity", "design", "design_theme",
                     "queued", "done"}, sorted(back))
    reset_store()


# --------------------------------------------------------------------------- E
def part_e():
    forget("charlotte")
    reset_store()
    store = CH._load()
    rs = [CH.make_web(f"C:/made up/r{i}.nd2", store, egg=False)["rarity"] for i in range(30)]
    special = [i for i, r in enumerate(rs) if r in ("rare", "epic")]
    ok("E without the extra: exactly 10 of 30 webs are rare / epic, every 3rd",
       special == list(range(2, 30, 3)), special)
    ok("E ... and the other 20 are common", rs.count("common") == 20)
    store = {"seeds": [], "started": 0}
    many = [CH.make_web(f"m{i}", store, egg=False)["rarity"] for i in range(900)]
    sp = [r for r in many if r != "common"]
    share = sp.count("epic") / len(sp)
    ok("E every 3rd: about 75 % rare / 25 % epic", len(sp) == 300 and 0.17 <= share <= 0.33,
       f"{share:.2f}")
    store = {"seeds": [], "started": 0}
    egg = [CH.make_web(f"e{i}", store, egg=True)["rarity"] for i in range(600)]
    share = egg.count("epic") / len(egg)
    ok("E with the extra: every web is rare or epic", set(egg) <= {"rare", "epic"})
    ok("E with the extra: about 65 % rare / 35 % epic", 0.28 <= share <= 0.42, f"{share:.2f}")
    # the counter persists across a restart (new Game, events, user prefs)
    reset_store()
    events.clear()
    CH.uninstall()
    CH.install(APP)
    for i in range(2):
        nd2 = f"C:/made up/count {i}.nd2"
        events.emit("movie_opened", nd2=nd2, window=None)
        events.emit("roi_added", nd2=nd2, manual=True, n_cells=1)
        events.emit("saved", nd2=nd2, path="x", n_cells=1)
        events.emit("movie_closed", nd2=nd2)
    ok("E two webs started", CH._load()["started"] == 2)
    CH.uninstall()
    CH.install(APP)
    nd2 = "C:/made up/count 2.nd2"
    events.emit("movie_opened", nd2=nd2, window=None)
    web = CH._load()["growing"].get(CH._key(nd2), {})
    ok("E the counter survives a restart: the 3rd web is rare / epic",
       web.get("index") == 2 and web.get("rarity") in ("rare", "epic"), web.get("rarity"))
    events.emit("movie_closed", nd2=nd2)
    ok("E an empty web is dropped on close and gives its place back",
       CH._key(nd2) not in CH._load()["growing"] and CH._load()["started"] == 2)
    reset_store()


# --------------------------------------------------------------------------- F
def _dummy_window(kind):
    win = QMainWindow()
    win.menuBar().addMenu("&File")
    win.menuBar().addMenu("&View")
    central = QWidget()
    win.setCentralWidget(central)
    if kind == "widget":
        win.extras_bar = QWidget(central)
    elif kind == "layout":
        win.extras_bar = QHBoxLayout(central)
    win.resize(900, 600)
    return win


def part_f():
    forget("charlotte")
    reset_store()
    batchqueue.clear()
    events.clear()
    CH.uninstall()
    CH.install(APP)
    g = CH.game()
    wins = {k: _dummy_window(k) for k in ("status", "widget", "layout")}
    for k, win in wins.items():
        win.show()
        events.emit("main_window_ready", window=win)
        events.emit("main_window_ready", window=win)
    b_status = getattr(wins["status"], "_charlotte_button", None)
    ok("F pink button in the status bar (no extras_bar)",
       b_status is not None and b_status.parent() is not None
       and wins["status"].statusBar().isAncestorOf(b_status))
    ok("F pink button inside extras_bar (a QWidget)",
       wins["widget"].extras_bar.isAncestorOf(wins["widget"]._charlotte_button))
    lay = wins["layout"].extras_bar
    ok("F pink button inside extras_bar (a QLayout)",
       any(lay.itemAt(i).widget() is wins["layout"]._charlotte_button for i in range(lay.count())))
    ok("F only one button per window",
       len(wins["status"].findChildren(type(b_status), "charlotteButton")) == 1)
    acts = [a for m in wins["status"].menuBar().actions() if m.menu()
            for a in m.menu().actions() if a.text() == "Charlotte's Web"]
    ok("F the View menu has the Charlotte's Web action", len(acts) == 1)
    ok("F the button names the game, not the program",
       "Charlotte's Web" in b_status.text() and "inside PeterPiper" in b_status.toolTip())
    ok("F the app's own window title is untouched", wins["status"].windowTitle() == "")
    stops = CH.PINK_STOPS + CH.PINK_HOVER + CH.PINK_PRESSED
    tx = CH.text_on(stops)
    lows = []
    for name in TH.THEMES:
        TH.apply(APP, name)
        pump()
        b_status.setStyleSheet(b_status.styleSheet())
        img = b_status.grab().toImage()
        c = QColor(img.pixel(img.width() // 2, 3))
        lows.append(min(CH.contrast(tx, s) for s in stops))
        ok(f"F pink button looks pink on theme '{name}'", c.red() > c.green() + 60,
           c.name())
    ok("F pink button text contrast >= 4.5 on every theme and state", min(lows) >= 4.5,
       f"{min(lows):.2f} {tx}")
    TH.apply(APP, TH.DEFAULT)
    wins["status"].grab().save(str(SHOTS / "charlotte_pink_button_statusbar.png"))
    # a single movie: straight into the collection
    win = wins["status"]
    a = "C:/made up/single movie.nd2"
    events.emit("movie_opened", nd2=a, window=win)
    d = CH._load()
    ok("F movie_opened starts a web (n = 0)", d["growing"].get(CH._key(a), {}).get("n") == 0)
    events.emit("roi_added", nd2=a, manual=False, n_cells=1)
    ok("F an auto-detected ROI does not grow the web", CH._load()["growing"][CH._key(a)]["n"] == 0)
    ui = CH.open_window(win)
    pump(30)
    ok("F the window opens from the pink button / View menu", ui is not None and ui.isVisible())
    sizes = []
    for i in range(5):
        events.emit("roi_added", nd2=a, manual=True, n_cells=i + 1)
        sizes.append(CH._load()["growing"][CH._key(a)]["n"])
    ok("F every ROI by hand grows the web", sizes == [1, 2, 3, 4, 5], sizes)
    for _ in range(6):
        events.emit("roi_removed", nd2=a, n_cells=0)
    w = CH._load()["growing"][CH._key(a)]
    ok("F removing ROIs snaps threads but never fully unspins", w["n"] == 3 and w["snaps"] == 2,
       (w["n"], w["snaps"]))
    ui.grab().save(str(SHOTS / "charlotte_window_growing.png"))
    events.emit("saved", nd2=a, path="x.npz", n_cells=3)
    d = CH._load()
    done = d["collection"][-1] if d["collection"] else {}
    ok("F SAVE writes a kind word and adds the web to the collection",
       len(d["collection"]) == 1 and done.get("word") in WORDS and done.get("done")
       and done.get("date") and not d["tray"])
    ok("F the finished web records queued=False and its hand-drawn n",
       done.get("queued") is False and done.get("n") == 3)
    pump(2200)
    ui.grab().save(str(SHOTS / "charlotte_window_word.png"))
    events.emit("saved", nd2=a, path="x.npz", n_cells=3)
    events.emit("saved", nd2=a, path="x.npz", n_cells=3)
    ok("F saving again without new cells does not add a web", len(CH._load()["collection"]) == 1)
    events.emit("exported", nd2=a, folder="C:/made up")
    events.emit("movie_closed", nd2=a)
    ok("F an empty new web is dropped when the movie closes",
       CH._key(a) not in CH._load()["growing"])
    # a queue (batch): webs wait in the tray until Collect
    b, c = "C:/made up/queue movie B.nd2", "C:/made up/queue movie C.nd2"
    batchqueue.set_items([b, c])
    for nd2, cells in ((b, 4), (c, 6)):
        events.emit("movie_opened", nd2=nd2, window=win)
        for i in range(cells):
            events.emit("roi_added", nd2=nd2, manual=True, n_cells=i + 1)
        if nd2 == b:
            ui.refresh()
            ok("F batch progress is shown", "Web 1 of 2 in your batch" in ui.lbl_status.text(),
               ui.lbl_status.text())
        events.emit("saved", nd2=nd2, path="x.npz", n_cells=cells)
        batchqueue.mark(nd2, "saved")
    d = CH._load()
    ok("F queued webs wait in the batch tray, not in the collection",
       len(d["tray"]) == 2 and len(d["collection"]) == 1)
    ok("F tray webs record queued=True and their hand-drawn n",
       [(w["queued"], w["n"]) for w in d["tray"]] == [(True, 4), (True, 6)])
    ok("F hand_drawn_queued_movies() counts them", CH.hand_drawn_queued_movies() == 2)
    ok("F the batch is done", g.batch_done())
    g._offered = False
    g._offer_finish()
    pump(30)
    ok("F the finish step opens when the batch is done", ui.page() == ui.PAGE_FINISH)
    ok("F without the extra: no design controls", not ui.design_box.isVisible())
    ok("F without the extra: set_design does nothing", g.set_design(None, "epic") == 0)
    ok("F the Smart auto-select line is hidden while its module is missing",
       not ui.lbl_smart.isVisible())
    ui.grab().save(str(SHOTS / "charlotte_finish_batch_plain.png"))
    ui.collect()
    d = CH._load()
    ok("F Collect moves the batch into the collection",
       len(d["collection"]) == 3 and not d["tray"])
    # with the extra: design your own version before collecting
    achievements.unlock("charlotte")
    dd, e = "C:/made up/queue movie D.nd2", "C:/made up/queue movie E.nd2"
    batchqueue.set_items([dd, e])
    for nd2 in (dd, e):
        events.emit("movie_opened", nd2=nd2, window=win)
        for i in range(5):
            events.emit("roi_added", nd2=nd2, manual=True, n_cells=i + 1)
        events.emit("saved", nd2=nd2, path="x.npz", n_cells=5)
        batchqueue.mark(nd2, "exported")
    ui.show_page(ui.PAGE_FINISH)
    pump(30)
    ok("F with the extra: the design controls are shown", ui.design_box.isVisible())
    tray = CH._load()["tray"]
    ok("F with the extra: tray webs are rare or epic",
       all(w["rarity"] in ("rare", "epic") for w in tray))
    before = img_hash(CH.render_web(tray[0], 200, 200))
    ui.chk_all.setChecked(True)
    ui.cmb_theme.setCurrentIndex(ui.cmb_theme.findData("frost"))
    ui.slider.setValue(1)               # Common
    tray = CH._load()["tray"]
    ok("F the design applies to every web of the batch",
       all(w["design"] == "common" and w["design_theme"] == "frost" for w in tray))
    ok("F the original roll stays recorded", all(w["rarity"] in ("rare", "epic") for w in tray))
    after = img_hash(CH.render_web(tray[0], 200, 200))
    ok("F the user's design changes the picture, keeping seed and word",
       before != after and tray[0]["word"] in WORDS)
    ui.chk_all.setChecked(False)
    ui.slider.setValue(3)               # Epic, the picked web only
    tray = CH._load()["tray"]
    ok("F the design can apply to one web", [w["design"] for w in tray].count("epic") == 1)
    ui.grab().save(str(SHOTS / "charlotte_finish_batch_designer.png"))
    ui.collect()
    coll = CH._load()["collection"]
    mine = [w for w in coll if w.get("design")]
    ok("F the user's design is kept in the collection", len(mine) == 2)
    h1 = img_hash(CH.render_web(mine[0], 320, 320))
    h2 = img_hash(CH.render_web(json.loads(json.dumps(mine[0])), 320, 320))
    ok("F the user's design survives a re-render", h1 == h2)
    out = CH.export_png(mine[0], OUT / "designed.png")
    exp = QImage(str(out)).convertToFormat(QImage.Format_ARGB32)
    ref = CH.export_image(mine[0], 1600).convertToFormat(QImage.Format_ARGB32)
    ok("F the export uses the user's design", img_hash(exp) == img_hash(ref))
    ui.show_page(ui.PAGE_COLL)
    pump(30)
    ok("F the gallery counts themes, rare and epic",
       "of 50 themes" in ui.lbl_count.text() and "epic" in ui.lbl_count.text(),
       ui.lbl_count.text())
    ui.grab().save(str(SHOTS / "charlotte_gallery.png"))
    for wsz in ((1366, 768), (1280, 800)):
        ok(f"F the window fits a {wsz[0]} x {wsz[1]} screen",
           ui.minimumSizeHint().width() <= wsz[0] and ui.minimumSizeHint().height() <= wsz[1] - 60)
    ui.close()
    ok("F closing the window is remembered", CH._load()["window"].get("closed") is True)
    batchqueue.clear()
    for win in wins.values():
        win.close()


# --------------------------------------------------------------------------- G
def part_g():
    seed = 4242
    web = {"id": "w1", "seed": seed, "theme": "sakura", "params": D.new_params(seed), "n": 6,
           "word": "WONDERFUL", "rarity": "rare", "movie": "made up", "date": "2026-01-01"}
    folder = OUT / "export"
    p1 = CH.export_png(web, folder / "web.png")
    p2 = CH.export_png(web, folder / "web.png")
    ok("G one web exports as a PNG", p1.exists() and QImage(str(p1)).width() == 1600
       and QImage(str(p1)).height() == 1600)
    ok("G a second export never overwrites", p2 != p1 and p2.exists() and p2.name == "web_2.png")
    webs = []
    for i, t in enumerate(THEMES[:12]):
        s = 9000 + i
        webs.append({"id": f"w{i}", "seed": s, "theme": t["key"], "params": D.new_params(s),
                     "n": 3 + i, "word": WORDS[i], "rarity": ("common", "rare", "epic")[i % 3],
                     "movie": f"movie {i}", "date": "2026-01-02"})
    s1 = CH.export_contact_sheet(webs, folder / "all.png")
    s2 = CH.export_contact_sheet(webs, folder / "all.png")
    ok("G 'Export all' writes a contact sheet", s1.exists() and QImage(str(s1)).width() >= 800)
    ok("G the contact sheet never overwrites", s2 != s1 and s2.exists())
    shutil.copy(s1, SHOTS / "charlotte_contact_sheet.png")


# --------------------------------------------------------------------------- H
def part_h():
    from PySide6.QtGui import QPainter
    T = 320
    for n in (1, 5, 12):
        sheet = QImage(5 * T, 2 * T, QImage.Format_RGB32)
        sheet.fill(QColor(0, 0, 0))
        p = QPainter(sheet)
        for i, t in enumerate(THEMES[::5]):
            s = 500 + i
            p.drawImage((i % 5) * T, (i // 5) * T,
                        D.render_image(t["key"], D.new_params(s), s, n, T, T, t=1.2,
                                       word="SOME CELLS" if n == 12 else None, level=(i + n) % 4))
        p.end()
        sheet.save(str(SHOTS / f"charlotte_10_themes_n{n}.png"))
    keys = ["moon_silver", "thunder", "grazing_herd", "cats_cradle", "spaghetti", "wood_wide"]
    sheet = QImage(3 * T, len(keys) * T, QImage.Format_RGB32)
    p = QPainter(sheet)
    for r, k in enumerate(keys):
        s = 31 + r
        for c, lv in enumerate((0, 2, 3)):
            p.drawImage(c * T, r * T, D.render_image(k, D.new_params(s), s, 6, T, T, t=1.3,
                                                     word="TERRIFIC", level=lv))
    p.end()
    sheet.save(str(SHOTS / "charlotte_common_rare_epic.png"))
    ok("H screenshots written", len(list(SHOTS.glob("charlotte_*.png"))) >= 10)


def main():
    for part in (part_a, part_b, part_c, part_d, part_e, part_f, part_g, part_h):
        try:
            part()
        except Exception as exc:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f"{part.__name__} ran without an error", False, repr(exc))
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    for f in FAILS:
        print("  FAILED:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
