"""
Developer test (not shipped): PeterPiper 1.1 part "looks" - the hidden colour
palettes, the crown, readable themes, colour-blind-safe cell colours.

    QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts python dev_tests/test_v11_looks.py

A) the logo extra: 20 clicks in a row (each within 1.5 s) unlock "palettes"; 19 +
   a pause + 1 do not and show nothing; real mouse clicks count; the unlock is
   per user and persists; the theme lists then hold every palette; a reveal note
   (and sparkle) appears; clicks with no user go to the user selected in 'Who is
   using' (set_target_user) or to the computer-level pending set claimed by the
   next user.
B) the crown: 100 clicks in a row unlock "crown" (99 + pause + 1 do not); 20 clicks
   then typing "peter" anywhere unlocks it (the keys still reach the field);
   typing "peter" without the clicks does not; the crown is per user, permanent.
C) name_flair: crown prefix; Charlotte's webs 0 / 1 / 5 / 12 / 30 -> tiers 0-4
   (emoji, colour, bold, sparkles on both ends); the emoji varies between calls;
   the colour is readable (>= 4.5) on every theme's list backgrounds.
D) themes: about 20; every one passes validate() (WCAG 2 contrast for every text /
   background pair the style sheet uses); the style sheet parses and the icons
   are drawn for each; labels; screenshot grid of a sample window in each theme.
E) cell colours: >= 3:1 against the trace plot background (white in every theme -
   checked on a real TracePanel after each theme switch) and against black; every
   pair >= CELL_MIN_DE2000 CIEDE2000 apart with normal vision, protanopia,
   deuteranopia and tritanopia (Machado 2009, severity 1.0); cell_colour(k) and
   the trace pens identical whatever theme; past the palette length the trace
   pens use cell_pen_style (dashed, dotted, dash-dot); the cell list shows a
   swatch and no coloured text.
F) eggsdlg.show_achievements: the window lists what was found and "N more hidden".
Screenshots: _out/shots/ (theme grid, logo reveal, trace panel in two themes,
user list flair, hidden extras window).
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v11_looks"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtCore import QPoint, Qt, qInstallMessageHandler      # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter                  # noqa: E402
from PySide6.QtTest import QTest                                    # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,   # noqa: E402
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

APP = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

from peterpiper import achievements as A                            # noqa: E402
from peterpiper import userprefs, users                             # noqa: E402
from peterpiper.gui import colourvision as CV                       # noqa: E402
from peterpiper.gui import theme as TH                              # noqa: E402
from peterpiper.gui import widgets as W                             # noqa: E402

N = [0]
FAILS = []
QT_WARN = []


def ok(name, cond, extra=""):
    N[0] += 1
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.2):
    t = time.time()
    while time.time() - t < sec:
        APP.processEvents()
        time.sleep(0.005)


def _qt_msg(mode, ctx, msg):
    QT_WARN.append(str(msg))


qInstallMessageHandler(_qt_msg)


def become(name):
    """Make (if needed) and start as user `name`."""
    if name not in users.list_users():
        users.add_user(name)
    users.activate(name)


def logo_window():
    d = QDialog()
    lay = QVBoxLayout(d)
    logo = W.LogoLabel(70)
    lay.addWidget(logo)
    ed = QLineEdit()
    lay.addWidget(ed)
    d.resize(560, 260)
    d.show()
    pump(0.1)
    return d, logo, ed


def clicks(logo, n, t0=0.0, step=1.0):
    """n clicks 1 s apart (faked times); returns what the last one found."""
    got = ""
    for i in range(n):
        got = logo.logo_clicked(t0 + i * step) or got
    return got


# ===================================================================== A
def part_a():
    TH.apply(APP, "midnight", 10.0)
    become("Tester A")
    d, logo, _ed = logo_window()
    ok("A before: only the basic themes", TH.available_names() == list(TH.BASIC),
       str(TH.available_names()))
    ok("A nothing found yet: no key watching either (no cost)", not W._WATCH)
    got = clicks(logo, 19) or logo.logo_clicked(19 + 1.6)          # a pause, then one
    ok("A 19 clicks + a pause + 1: nothing found, nothing shown",
       got == "" and not A.unlocked("palettes") and logo.reveal is None
       and logo._sparkle_left == 0)
    got = clicks(logo, 20, t0=100.0, step=1.4)
    ok("A 20 clicks in a row (1.4 s apart): the palettes are found",
       got == "palettes" and A.unlocked("palettes"), got)
    ok("A a friendly note appears under the logo (with a sparkle)",
       logo.reveal is not None and logo.reveal.isVisible()
       and "colour palettes" in logo.reveal.label.text() and logo._sparkle_left > 0)
    pump(0.25)
    d.grab().save(str(SHOTS / "logo_reveal.png"))
    names = TH.available_names()
    ok("A the theme list now holds every palette", names[:2] == list(TH.BASIC)
       and set(names) == set(TH.THEMES) and len(names) >= 18, str(len(names)))
    d.close()
    ok("A found() has the date", "palettes" in A.found() and len(A.found()["palettes"]) >= 10)
    # real mouse clicks for another user
    become("Tester B")
    ok("A per user: Tester B has not found it", not A.unlocked("palettes")
       and TH.available_names() == list(TH.BASIC))
    d, logo, _ed = logo_window()
    for _ in range(20):
        QTest.mouseClick(logo, Qt.LeftButton, Qt.NoModifier, logo.rect().center())
    pump(0.05)
    ok("A 20 real mouse clicks on the logo work", A.unlocked("palettes"))
    d.close()
    become("Tester C")
    ok("A Tester C: still only the basic themes", not A.unlocked("palettes"))
    become("Tester A")
    ok("A Tester A keeps it (persists in the user's own file)", A.unlocked("palettes")
       and "palettes" in json.loads(userprefs.path("achievements").read_text())["found"])
    t = TH.switch("neon", None)
    ok("A a palette can be applied (theme.switch)", t.name == "neon" and TH.current().name == "neon")
    TH.apply(APP, "midnight", 10.0)
    # no user yet ('Who is using PeterPiper?'), nobody selected -> pending -> next user
    users.deactivate()
    A.set_target_user(None)
    d, logo, _ed = logo_window()
    got = clicks(logo, 20, t0=500.0)
    shared = users.base_dir() / "achievements.json"
    base = json.loads(shared.read_text())
    ok("A no user: kept as pending on this computer", got == "palettes"
       and "palettes" in base.get("pending", {}), str(base))
    d.close()
    become("Tester P")
    ok("A pending: the next user to start takes it over", A.unlocked("palettes")
       and "pending" not in json.loads(shared.read_text())
       and "palettes" not in json.loads(shared.read_text()).get("found", {}))
    become("Tester Q")
    ok("A ... only that one user", not A.unlocked("palettes"))


# ===================================================================== B
def part_b():
    become("Crown A")
    d, logo, ed = logo_window()
    got = clicks(logo, 99)
    last = logo.logo_clicked(99 + 2.0)
    ok("B 99 clicks + a pause + 1: no crown", got == "palettes" and last == ""
       and not A.unlocked("crown"))
    got = clicks(logo, 100, t0=1000.0)
    ok("B 100 clicks in a row: the crown (and the palettes on the way)",
       got == "crown" and A.unlocked("crown") and A.unlocked("palettes"))
    ok("B its own note", logo.reveal is not None and "crown" in logo.reveal.label.text(),
       logo.reveal.label.text() if logo.reveal else "")
    d.close()
    # typing 'peter'
    become("Crown B")
    W._EXTRAS["streak20"] = False
    d, logo, ed = logo_window()
    d.activateWindow()
    ed.setFocus()
    pump(0.1)
    QTest.keyClicks(ed, "peter")
    pump(0.1)
    ok("B typing 'peter' without the clicks: nothing", not A.unlocked("crown")
       and ed.text() == "peter", ed.text())
    ed.clear()
    clicks(logo, 20, t0=2000.0)
    ok("B 20 clicks (palettes)", A.unlocked("palettes") and not A.unlocked("crown"))
    ed.setFocus()
    QTest.keyClicks(ed, "Pe")
    QTest.keyClicks(ed, "TeR")
    pump(0.1)
    ok("B ... then typing 'peter' (any case): the crown; the keys still reach the field",
       A.unlocked("crown") and ed.text() == "PeTeR", ed.text())
    d.close()
    ok("B the word watch is installed once", len(W._WATCH) == 1 and W.install_word_watch())
    become("Crown C")
    ok("B per user: Crown C has no crown", not A.unlocked("crown"))
    # 'Who is using': the user selected in the list gets it
    users.deactivate()
    A.set_target_user("Crown D")
    users.add_user("Crown D")
    d, logo, ed = logo_window()
    got = clicks(logo, 100, t0=3000.0)
    d.close()
    ok("B no user, 'Crown D' selected: the crown goes into Crown D's own file",
       got == "crown" and "crown" in userprefs.load_for("Crown D", "achievements")["found"]
       and "crown" not in json.loads((users.base_dir() / "achievements.json").read_text()
                                     ).get("pending", {}))
    A.set_target_user(None)
    become("Crown D")
    ok("B ... and Crown D has it when starting", A.unlocked("crown"))
    become("Crown A")
    ok("B permanent: still there later", A.unlocked("crown"))


# ===================================================================== C
def part_c():
    become("Flair 0")
    for name, webs in (("Flair 1", 1), ("Flair 5", 5), ("Flair 12", 12), ("Flair 30", 30)):
        if name not in users.list_users():
            users.add_user(name)
        userprefs.save_for(name, "charlotte", {"collection": [f"w{i}" for i in range(webs)]})
    rng = random.Random(3)
    f = {n: A.name_flair(n, rng) for n in ("Flair 0", "Flair 1", "Flair 5", "Flair 12",
                                            "Flair 30", "Crown A")}
    ok("C 0 webs: nothing", f["Flair 0"] == {"prefix": "", "suffix": "", "bold": False,
                                            "colour": None, "tier": 0}, str(f["Flair 0"]))
    ok("C 1 web: a small emoji after the name, normal weight, no colour",
       f["Flair 1"]["tier"] == 1 and f["Flair 1"]["suffix"].strip() in A.WEB_EMOJI[1]
       and not f["Flair 1"]["bold"] and f["Flair 1"]["colour"] is None)
    ok("C 5 webs: emoji + colour", f["Flair 5"]["tier"] == 2 and f["Flair 5"]["colour"]
       and not f["Flair 5"]["bold"])
    ok("C 12 webs: bold + colour + emoji", f["Flair 12"]["tier"] == 3 and f["Flair 12"]["bold"]
       and f["Flair 12"]["colour"] and f["Flair 12"]["suffix"])
    f30 = f["Flair 30"]
    ok("C 30 webs: bold, sparkles on both ends", f30["tier"] == 4 and f30["bold"]
       and f30["prefix"].startswith(A.SPARKLE) and f30["suffix"].endswith(A.SPARKLE))
    ok("C a crown before the name (Crown A)", f["Crown A"]["prefix"] == A.CROWN
       and f["Crown A"]["tier"] == 0)
    seen = {A.name_flair("Flair 30")["suffix"] for _ in range(40)}
    ok("C the emoji changes between calls", len(seen) >= 3, str(len(seen)))
    bad = []
    for name in TH.THEMES:
        t = TH.apply(APP, name, 10.0)
        cols = []
        for u in ("Flair 5", "Flair 12", "Flair 30"):
            c = A.name_flair(u)["colour"]
            cols.append(c)
            for b in TH.tint_backgrounds(t):
                if CV.contrast(c, b) < 4.5:
                    bad.append(f"{name} {u} {c} on {b}: {CV.contrast(c, b):.2f}")
        if name == "midnight":
            mid = cols
    ok("C the name colours are readable (>= 4.5) on every theme", not bad, "; ".join(bad[:4]))
    for look in ("midnight", "daylight"):
        TH.apply(APP, look, 10.0)
        _flair_shot(look)
    TH.apply(APP, "midnight", 10.0)
    ok("C tier colours get more vivid (saturation 0.55 -> 1.0)",
       QColor(mid[0]).hslSaturationF() < QColor(mid[2]).hslSaturationF(), str(mid))


def _flair_shot(look):
    """A picture of how a user list could show the flair."""
    lst = QListWidget()
    for u in ("Flair 0", "Flair 1", "Flair 5", "Flair 12", "Flair 30", "Crown A"):
        fl = A.name_flair(u)
        it = QListWidgetItem(fl["prefix"] + u + fl["suffix"])
        if fl["bold"]:
            fn = it.font()
            fn.setBold(True)
            it.setFont(fn)
        if fl["colour"]:
            it.setForeground(QColor(fl["colour"]))
        lst.addItem(it)
    lst.resize(360, 220)
    lst.show()
    pump(0.1)
    lst.grab().save(str(SHOTS / f"user_list_flair_{look}.png"))
    lst.close()


# ===================================================================== D
def sample_window(title):
    w = QWidget()
    w.setFixedSize(380, 300)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(8, 6, 8, 6)
    head = QLabel(TH.label(title))
    head.setProperty("role", "subtitle")
    lay.addWidget(head)
    box = QGroupBox("1   Tracking rules")
    bl = QVBoxLayout(box)
    m = QLabel("Quiet text explains a step.")
    m.setProperty("muted", True)
    bl.addWidget(m)
    r = QHBoxLayout()
    for role, txt in (("warn", "Check"), ("danger", "Problem"), ("ok", "Done")):
        q = QLabel(txt)
        q.setProperty("role", role)
        r.addWidget(q)
    cb = QCheckBox("Include")
    cb.setChecked(True)
    r.addWidget(cb)
    bl.addLayout(r)
    r2 = QHBoxLayout()
    e = QLineEdit("GFP / Cy5")
    c = QComboBox()
    c.addItems(["Nucleus", "Whole cell"])
    r2.addWidget(e)
    r2.addWidget(c)
    bl.addLayout(r2)
    lay.addWidget(box)
    tbl = QTableWidget(3, 2)
    tbl.setHorizontalHeaderLabels(["Cell", "Note"])
    for i in range(3):
        tbl.setItem(i, 0, QTableWidgetItem(f"Cell {i + 1}"))
        tbl.setItem(i, 1, QTableWidgetItem("included" if i != 1 else "excluded by you"))
    tbl.selectRow(1)
    tbl.verticalHeader().setVisible(False)
    lay.addWidget(tbl)
    r3 = QHBoxLayout()
    r3.addWidget(QPushButton("Cancel"))
    p = QPushButton("Track && measure")
    p.setProperty("primary", True)
    r3.addWidget(p)
    pb = QProgressBar()
    pb.setValue(60)
    r3.addWidget(pb)
    lay.addLayout(r3)
    w._tbl, w._pb = tbl, pb
    return w


def part_d():
    ok("D about 20 themes", 18 <= len(TH.THEMES) <= 24, str(len(TH.THEMES)))
    ok("D the basic two first, default midnight", list(TH.THEMES)[:2] == list(TH.BASIC)
       and TH.DEFAULT == "midnight")
    probs = [p for t in TH.THEMES.values() for p in TH.validate(t)]
    ok("D every theme passes validate() (WCAG 2 contrast minimums)", not probs,
       "; ".join(probs[:5]))
    worst = min(((x[1] / x[2], t.name, x[0]) for t in TH.THEMES.values()
                 for x in TH.checks(t) if x[0] != "dark flag"))
    print(f"     closest margin: {worst[1]} - {worst[2]} ({worst[0]:.2f} x the minimum)")
    ok("D validate() catches a bad theme", TH.validate(TH._T(
        "bad", True, "#000000", "#101010", "#202020", "#202020", "#555555", "#333333",
        "#777777", "#888888", "#222222", "rgba(255,255,255,0.9)", "#300000", "#300000",
        "#003000")) and TH.validate(TH.THEMES["midnight"].__class__(
            **{**TH.THEMES["daylight"].__dict__, "dark": True})))
    ok("D every theme has a plain label", all(TH.label(n) and "(" in TH.label(n)
                                             for n in TH.THEMES))
    shots = []
    for name in TH.THEMES:
        QT_WARN.clear()
        t = TH.apply(APP, name, 10.0)
        ss = APP.styleSheet()
        w = sample_window(name)
        w.show()
        pump(0.05)
        img = w.grab().toImage()
        # what is really on screen: the selected row and the progress bar's chunk
        rc = w._tbl.visualItemRect(w._tbl.item(1, 0))
        pt = w._tbl.viewport().mapTo(w, rc.topRight()) + QPoint(-4, rc.height() // 2)
        row_px = img.pixelColor(pt).name()
        pp = w._pb.mapTo(w, QPoint(6, w._pb.height() // 2))
        bar_px = img.pixelColor(pp).name()
        seen = (CV.contrast(t.text, row_px), CV.contrast(t.text, bar_px))
        ok(f"D {name}: on screen, a selected row ({row_px}) and the progress bar ({bar_px}) "
           f"keep the text readable", min(seen) >= 4.4, f"{seen[0]:.2f} / {seen[1]:.2f}")
        icons = sorted(p.name for p in TH._icons(t).glob("*.png"))
        parse = [m for m in QT_WARN if "style" in m.lower() or "parse" in m.lower()]
        ok(f"D {name}: style sheet ({len(ss)} chars) parses, icons drawn ({len(icons)})",
           t.name == name and len(ss) > 2000 and not parse and len(icons) >= 6
           and APP.palette().color(APP.palette().ColorRole.Window).name().upper()
           == t.bg.upper(), "; ".join(parse[:2]))
        shots.append(img)
        w.close()
    cols = 4
    tw, th = shots[0].width(), shots[0].height()
    rows = (len(shots) + cols - 1) // cols
    grid = QImage(cols * tw + (cols + 1) * 8, rows * th + (rows + 1) * 8, QImage.Format_RGB32)
    grid.fill(QColor("#808080"))
    g = QPainter(grid)
    for i, im in enumerate(shots):
        g.drawImage(8 + (i % cols) * (tw + 8), 8 + (i // cols) * (th + 8), im)
    g.end()
    grid.save(str(SHOTS / "theme_grid.png"))
    ok("D screenshot grid of every theme saved", (SHOTS / "theme_grid.png").exists())
    TH.apply(APP, "midnight", 10.0)


# ===================================================================== E
def synthetic(T=40, N=14):
    from peterpiper.measure import Measurements
    rng = np.random.default_rng(2)
    t = np.arange(T)
    mean = np.empty((T, 2, N))
    for k in range(N):
        mean[:, 0, k] = 1000 * (1 + 0.06 * k) * (1 + 0.6 / (1 + np.exp(-(t - 15) / 3))) \
            * (1 + 0.02 * rng.normal(size=T)) + 100
        mean[:, 1, k] = 800 + 10 * rng.normal(size=T) + 100
    return Measurements(mean=mean, background=np.full((T, 2), 100.0),
                        area_px=np.full((T, N), 50.0), n_saturated=np.zeros((T, 2, N)),
                        quality=np.ones((T, N)), channels=["GFP", "Cy5"])


def part_e():
    P = W.PALETTE
    ok("E 6 cell colours, all different", len(P) == 6 and len(set(P)) == 6, str(P))
    lo_w = min(CV.contrast(c, W.PLOT_BG) for c in P)
    lo_k = min(CV.contrast(c, "#000000") for c in P)
    ok(f"E >= 3:1 against the white plot ({lo_w:.2f}) and black ({lo_k:.2f})",
       lo_w >= W.CELL_MIN_CONTRAST and lo_k >= W.CELL_MIN_CONTRAST)
    for kind in CV.VISION:
        d, _k, (i, j) = CV.min_distance(P, [kind])
        ok(f"E {kind}: every pair >= {W.CELL_MIN_DE2000:g} CIEDE2000 apart (min {d:.1f})",
           d >= W.CELL_MIN_DE2000, f"{P[i]} / {P[j]}")
    adj = min(CV.delta_e2000(CV.simulate(P[i], k), CV.simulate(P[(i + 1) % len(P)], k))
              for i in range(len(P)) for k in CV.VISION)
    ok(f"E neighbours in the list even further apart ({adj:.1f})", adj >= W.CELL_MIN_DE2000)
    # the colour science itself, on known values
    ok("E colour maths: contrast black/white 21, CIEDE2000 Sharma pair 1 = 2.0425",
       abs(CV.contrast("#000000", "#FFFFFF") - 21) < 1e-9
       and abs(_de_lab((50, 2.6772, -79.7751), (50, 0, -82.7485)) - 2.0425) < 1e-3)
    ok("E Machado: white and black stay white and black; red looks dark-yellowish (protan)",
       CV.simulate("#FFFFFF", "deuteranopia") == "#FFFFFF"
       and CV.simulate("#000000", "tritanopia") == "#000000"
       and CV.lab(CV.simulate("#FF0000", "protanopia"))[0] < 50)
    ok("E styles: solid for the first 6, then dashed, dotted, dash-dot",
       [W.cell_pen_style(k) for k in (0, 5, 6, 11, 12, 18, 24)]
       == [Qt.SolidLine, Qt.SolidLine, Qt.DashLine, Qt.DashLine, Qt.DotLine,
           Qt.DashDotLine, Qt.SolidLine])
    looks = {(W.cell_colour(k), W.cell_pen_style(k)) for k in range(24)}
    ok("E 24 different looks before any repeats", len(looks) == 24)
    # a real trace panel, through every theme
    from peterpiper.config import Experiment
    from peterpiper.gui.traces import TracePanel
    exp = Experiment(nd2_path=str(OUT / "synthetic.nd2"), channels=["GFP", "Cy5"],
                     n_timepoints=40, seconds_per_frame=30.0, out_dir=str(OUT))
    TH.apply(APP, "midnight", 10.0)
    w = TracePanel(exp)
    w.resize(520, 860)
    w.show()
    M = synthetic()
    live = list(range(14))
    inc = [k for k in live if k not in (3, 9)]
    w.set_data(M, live, inc, {k: "included" if k in inc else "excluded by you" for k in live},
               "Nucleus", 4, 0, ["F/F0 - GFP"])
    pump(0.2)

    def pens():
        return [(k, item.opts["pen"].color().name().upper(), item.opts["pen"].style())
                for item, k in w._curves]
    ref, bgs, cols_ok = None, set(), True
    for name in TH.THEMES:
        TH.switch(name, None)
        w.refresh()
        pump(0.03)
        bgs.add(w.plot.backgroundBrush().color().name().upper())
        cols = [W.cell_colour(k) for k in range(30)]
        now = (cols, pens())
        if ref is None:
            ref = now
        cols_ok = cols_ok and now == ref
        if name in ("midnight", "hot_pink"):
            w.grab().save(str(SHOTS / f"traces_{name}.png"))
    ok("E the trace plot stays white in every theme", bgs == {W.PLOT_BG}, str(bgs))
    ok("E cell_colour(k) and every trace pen identical in every theme", cols_ok)
    p = {k: (c, s) for k, c, s in ref[1]}
    ok("E trace pens: the cell's colour; past the 6th the line style changes",
       all(p[k] == (W.cell_colour(k), W.cell_pen_style(k)) for k in inc if k in p)
       and p[7][1] == Qt.DashLine and p[13][1] == Qt.DotLine and p[0][1] == Qt.SolidLine,
       str([(k, p[k]) for k in (0, 7, 13) if k in p]))
    ok("E excluded cells stay grey", all(p[k][0] != W.cell_colour(k) for k in (3, 9)))
    rows = [w.table.item(r, 1) for r in range(w.table.rowCount())]
    ok("E cell list: a colour swatch per cell, no coloured text",
       len(rows) == 14 and all(not it.icon().isNull() for it in rows)
       and all(it.data(Qt.ForegroundRole) is None for it in rows))
    TH.apply(APP, "midnight", 10.0)
    w.close()


def _de_lab(l1, l2):
    """delta_e2000 on Lab values directly (the published test pair)."""
    saved = CV.lab
    try:
        CV.lab = lambda c: l1 if c == "a" else l2
        return CV.delta_e2000("a", "b")
    finally:
        CV.lab = saved


# ===================================================================== F
def part_f():
    from peterpiper.gui.eggsdlg import AchievementsDialog, show_achievements
    become("Crown A")
    d = AchievementsDialog()
    d.show()
    pump(0.1)
    ok("F the hidden extras window lists the found ones and how many are hidden",
       d.rows == ["palettes", "crown"] and d.hidden == 1 and "1 more is hidden"
       in d.lbl_more.text(), f"{d.rows} {d.lbl_more.text()}")
    d.grab().save(str(SHOTS / "hidden_extras.png"))
    d.close()
    ok("F show_achievements is there", callable(show_achievements))


if __name__ == "__main__":
    for part in (part_a, part_b, part_c, part_d, part_e, part_f):
        try:
            part()
        except Exception as exc:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f"{part.__name__} ran without an error", False, repr(exc))
    print(f"\n{N[0] - len(FAILS)} / {N[0]} checks passed")
    sys.exit(1 if FAILS else 0)
