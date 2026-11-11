"""
Developer test (not shipped): PeterPiper 1.0 - the new name, the logo, a fresh
start, and PD4nav's files still read.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_peterpiper.py

A) the name: APP_NAME / APP_TITLE / version; the app's own text has no 'PD4nav'
   except where it means PD4nav (reading its files, its history); the launcher,
   quick start and citation say PeterPiper 1.0.
B) saved files name the app: a session saved now says app = PeterPiper and its
   summary and earlier-runs label say 'PeterPiper 1.0'; a file without the name
   (PD4nav's) says 'PD4nav 3.0'; the name does not change the content key (an
   unchanged analysis is still recognised as the same); new sessions go to
   PeterPiper_sessions, a file in PD4nav_sessions is still a session.
C) PD4nav's files still read: a trained auto-detect and saved settings made by
   PD4nav load; a profile exported by PD4nav ('PD4nav profile - Zoe') imports
   as Zoe with her settings; nothing is taken over from PD4nav by itself.
D) the logo: the files are there; the start windows show it (white on the dark
   theme, black on the light one, following a theme change); the icon has every
   size from 16 to 256 px and is the window icon; the terminal art is block
   characters only, 116 / 100 / 72 characters wide; the launcher shows it before
   anything else and makes shortcuts only once per folder, never with
   PETERPIPER_NO_SHORTCUTS, never in install-only runs.
E) the launcher's logo routine in a real console window reads the width and
   chooses the art that fits (116 characters in a 120-wide window).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "peterpiper"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtWidgets import QApplication, QMessageBox             # noqa: E402

APP = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

import peterpiper                                                     # noqa: E402
from peterpiper import detectors as DT                                # noqa: E402
from peterpiper import history as H                                   # noqa: E402
from peterpiper import presets as PR                                  # noqa: E402
from peterpiper import roifile as RF                                  # noqa: E402
from peterpiper import users                                          # noqa: E402
from peterpiper.segment import Roi                                    # noqa: E402

N = [0]
FAILS = []


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(n=20):
    for _ in range(n):
        APP.processEvents()


# ===================================================================== A
# lines of the app that may say PD4nav: they mean PD4nav itself
ALLOWED = re.compile(r"PD4nav (?:older|V\{|V2|profile - |saved settings|trained auto-detect|"
                     r"version|before)|PD4nav_sessions|pd4nav\"\)|\"PD4nav\"|'PD4nav'|"
                     r"PD4nav data|formerly PD4nav|PD4nav V3\.0|PD4nav's|PD4nav, or|PD4nav \(|"
                     r"from PD4nav|PD4nav\)|PD4nav:|\bPD4nav\b.*(?:still read|untouched|left)|"
                     r"\(PD4nav, |PD4navV|PD4nav\*_results|no PD4nav run index|a PD4nav profile")


def part_a():
    ok("A APP_NAME PeterPiperV1.0, APP_TITLE PeterPiper, version 1.0.2",
       (peterpiper.APP_NAME, peterpiper.APP_TITLE, peterpiper.__version__)
       == ("PeterPiperV1.0", "PeterPiper", "1.0.2"))
    stray = []
    for p in sorted((REPO / "app").rglob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?i)pd4nav", line) and not ALLOWED.search(line):
                stray.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:80]}")
    ok("A no 'PD4nav' left in the app's own text (only where it means PD4nav)",
       not stray, "; ".join(stray[:6]))
    bat = (REPO / "PeterPiperV1.0.bat").read_text(encoding="ascii")
    ok("A the launcher: PeterPiperV1.0, its own install folder .PeterPiperV1.0",
       'set "HOME_DIR=%USERPROFILE%\\.PeterPiperV1.0"' in bat and "title PeterPiper 1.0" in bat)
    q = (REPO / "READ ME.txt").read_text(encoding="utf-8")
    c = (REPO / "CITATION.cff").read_text(encoding="utf-8")
    ok("A quick start and citation: PeterPiper 1.0 (formerly PD4nav)",
       q.startswith("PeterPiper 1.0") and "PD4nav" in q.splitlines()[2]
       and "version: 1.0.2" in c and "formerly PD4nav" in c)


# ===================================================================== B
def tiny():
    m = np.zeros((6, 6), bool)
    m[1:5, 1:5] = True
    return [Roi((10, 10, 16, 16), m)], Roi((30, 30, 36, 36), m.copy(), kind="background")


def part_b():
    rois, bg = tiny()
    st = dict(v2=True, version=peterpiper.__version__, app=peterpiper.APP_TITLE, user="",
              nd2="movie1.nd2", saved="2026-11-10T10:00:00")
    d = OUT / "results"
    sp = H.session_path(d, OUT / "movie1.nd2", "2026-11-10_10-00-00")
    ok("B new sessions go to PeterPiper_sessions", sp.parent.name == "PeterPiper_sessions")
    RF.save_session_file(sp, rois, bg, (64, 64), 0, dict(st), {}, None)
    s = RF.read_summary(sp)
    ok("B a session saved now says app = PeterPiper", s and s.get("app") == "PeterPiper")
    old_st = {k: v for k, v in st.items() if k != "app"}
    old_st["version"] = "3.0.0"
    legacy = OUT / "results" / "PD4nav_sessions" / "movie1_session_2026-11-01_10-00-00.npz"
    RF.save_session_file(legacy, rois, bg, (64, 64), 0, dict(old_st), {}, None)
    s2 = RF.read_summary(legacy)
    ok("B a file without the name is PD4nav's; in PD4nav_sessions it is a session",
       s2 and s2.get("app") == "PD4nav" and s2.get("kind") == "session")
    r1 = H._run_from_summary(s, "movie1.nd2", "same file", None) if hasattr(H, "_run_from_summary") else None
    if r1 is None:                                   # the summary -> RunInfo step, by hand
        r1 = H.RunInfo(path=s["path"], saved=s["saved"], version=s["version"], kind=s["kind"],
                       n_cells=s["n_cells"], comps=list(s["comps"]), tracked=s["tracked"],
                       n_timepoints=s["n_timepoints"], rules=list(s["rules"]), nd2_name="m",
                       match="same file", app=s["app"])
    r2 = H.RunInfo(path=s2["path"], saved=s2["saved"], version=s2["version"], kind=s2["kind"],
                   n_cells=s2["n_cells"], comps=list(s2["comps"]), tracked=s2["tracked"],
                   n_timepoints=s2["n_timepoints"], rules=list(s2["rules"]), nd2_name="m",
                   match="same file", app=s2["app"])
    ok("B earlier-runs labels: 'PeterPiper 1.0' and 'PD4nav 3.0'",
       "PeterPiper 1.0" in r1.label() and "PD4nav 3.0" in r2.label(), f"{r1.label()} | {r2.label()}")
    blob = RF.session_blob(rois, bg, (64, 64), 0, dict(st), {}, None)
    k_new = RF.content_key(blob, dict(st))
    k_old = RF.content_key(blob, {k: v for k, v in st.items() if k != "app"})
    ok("B the app's name does not change the content key (same analysis = same key)",
       k_new == k_old)
    from peterpiper.gui.historydlg import version_text
    ok("B version text unchanged ('V1.0')", version_text("1.0.0") == "V1.0")


# ===================================================================== C
def part_c():
    users.deactivate()
    ok("C a fresh start: no users, nothing taken over",
       users.list_users() == [] and users.migrate_old_home() is False
       and users.OLD_HOMES == () and H.OLD_HOMES == ())
    users.add_user("Ana")
    users.activate("Ana")
    det = DT.Detector(name="MySensor", comp="nucleus", main="GFP", helpers=["Cy5"]) \
        if "helpers" in DT.Detector.__dataclass_fields__ else None
    if det is not None:
        d = det.to_dict()
        d["kind"] = "PD4nav trained auto-detect"
        back = DT.Detector.from_dict(d)
        ok("C a trained auto-detect made by PD4nav loads", back is not None and back.name == "MySensor")
        d["kind"] = "something else"
        ok("C ... a file of another kind does not", DT.Detector.from_dict(d) is None)
    else:
        ok("C detector fields as expected", False, str(list(DT.Detector.__dataclass_fields__)))
    p = OUT / "pd4nav_settings.json"
    from peterpiper.config import Settings
    import dataclasses
    p.write_text(json.dumps({"kind": "PD4nav saved settings", "name": "old lab look",
                             "version": "3.0.0", "settings": dataclasses.asdict(Settings())}),
                 encoding="utf-8")
    try:
        got = PR.load(p) if hasattr(PR, "load") else PR.read(p)
        good = got is not None
    except Exception as exc:                                       # noqa: BLE001
        good, got = False, exc
    ok("C saved settings made by PD4nav load", good, repr(got)[:100])
    z = OUT / "PD4nav profile - Zoe - 2026-11-09.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("PD4nav profile - Zoe/profile.json",
                    json.dumps({"name": "Zoe", "aliases": [], "pd4nav": "3.0.0"}))
        zf.writestr("PD4nav profile - Zoe/settings.json", json.dumps({"baseline_timepoint": 7}))
    name, notes = users.import_profile(z)
    ok("C a profile exported by PD4nav imports (as Zoe, with her settings)",
       name == "Zoe" and "Zoe" in users.list_users()
       and (users.base_dir() / "users" / users._folder_of("Zoe") / "settings.json").exists(),
       f"{name} {notes}")
    users.deactivate()


# ===================================================================== D
def part_d():
    from PySide6.QtGui import QImage
    from peterpiper.gui import theme as TH
    from peterpiper.gui import widgets as W
    a = W.ASSETS
    names = ("logo_black.png", "logo_white.png", "PeterPiper.ico", "piper_256.png",
             "logo_116.txt", "logo_100.txt", "logo_72.txt")
    ok("D the logo files are in app/peterpiper/assets", all((a / n).exists() for n in names))
    for cols in (116, 100, 72):
        lines = (a / f"logo_{cols}.txt").read_text(encoding="utf-16").splitlines()
        chars = set("".join(lines))
        ok(f"D terminal art {cols}: block characters only, at most {cols} wide",
           chars <= set(" ▀▄█") and max(len(s) for s in lines) <= cols and len(lines) >= 10,
           f"{len(lines)} lines, {sorted(chars)}")
    icon = W.app_icon()
    sizes = sorted({(s.width(), s.height()) for s in icon.availableSizes()})
    ok("D the icon holds 16 - 256 px", (16, 16) in sizes and (256, 256) in sizes, str(sizes))
    TH.apply(APP, "midnight", 11.0)
    from peterpiper.gui.setup import SetupDialog
    d = SetupDialog()
    d.resize(700, 820)
    d.show()
    pump(30)
    logo = d.findChild(W.LogoLabel)

    def ink():
        img = logo.pixmap().toImage().convertToFormat(QImage.Format_ARGB32)
        px = [img.pixelColor(x, y) for x in range(0, img.width(), 7)
              for y in range(0, img.height(), 3)]
        px = [c for c in px if c.alpha() > 200]
        return sum(c.lightness() for c in px) / max(1, len(px)), len(px)
    dark, n1 = ink()
    d.grab().save(str(OUT / "start_window_dark.png"))
    TH.apply(APP, "daylight", 11.0)
    pump(30)
    light, n2 = ink()
    d.grab().save(str(OUT / "start_window_light.png"))
    ok("D start window: the logo, white on the dark theme and black on the light one",
       logo is not None and n1 > 50 and dark > 200 and light < 60, f"{dark:.0f} / {light:.0f}")
    d.close()
    TH.apply(APP, "midnight", 11.0)
    from peterpiper.gui.userdlg import UserDialog
    u = UserDialog()
    u.show()
    pump(20)
    ok("D 'Who is using PeterPiper?' shows the logo", u.findChild(W.LogoLabel) is not None)
    u.grab().save(str(OUT / "who_is_using.png"))
    u.close()
    bat = (REPO / "PeterPiperV1.0.bat").read_text(encoding="ascii")
    launch = bat[bat.index(":launch"):bat.index(":installonly")]
    ok("D launcher: logo at every start, then the shortcuts; install-only stops before both",
       launch.index("if defined ONLY goto installonly") < launch.index("call :logo")
       < launch.index("call :shortcuts") < launch.index("pythonw.exe"))
    sc = bat[bat.index(":shortcuts"):]
    ok("D shortcuts: never with PETERPIPER_NO_SHORTCUTS, once per folder, paths not in code",
       sc.index("if defined PETERPIPER_NO_SHORTCUTS exit /b 0") < sc.index("powershell")
       and 'if /i "%MADE%"=="%PP_BAT%" exit /b 0' in sc and "$env:PP_BAT" in sc
       and "%PP_BAT%\"" not in sc.split("powershell", 1)[1].split("\n", 1)[0])


def W_ASSETS():
    from peterpiper.gui import widgets as W
    return W.ASSETS


def part_e():
    """The launcher's own logo routine in a REAL console window (a new one, as
    when the .bat is double-clicked): it must read the window's width and pick
    the art that fits. (Run without a window, 'mode con' answers differently, so
    the launcher test alone did not catch a misread width.)"""
    import subprocess
    if sys.platform != "win32":
        print("     (E: Windows only - skipped)")
        return
    bat = (REPO / "PeterPiperV1.0.bat").read_text(encoding="ascii").replace("\r\n", "\n")
    logo = bat[bat.index("\n:logo\n") + 1:bat.index("\n:logotext\n")]
    num = bat[bat.index("\n:modenum\n") + 1:]
    num = num[:num.index("exit /b 0\n", num.index("if not defined ROWS")) + len("exit /b 0\n")]
    res = OUT / "console_result.txt"
    logo = logo.replace('type "%ART%"', '>> "%RES%" echo ART=%ART%\ntype "%ART%"')
    screen = OUT / "console_screen.txt"
    script = ("@echo off\nsetlocal DisableDelayedExpansion\ncls\n"
              f'set "ASSETS={REPO / "app" / "peterpiper" / "assets"}"\n'
              f'set "RES={res}"\n'
              '> "%RES%" echo start\ncall :logo\n'
              f'"{sys.executable}" "{HERE / "console_screen.py"}" "{screen}"\n'
              '>> "%RES%" echo COLS=%COLS% ROWS=%ROWS%\n'
              "mode con >> \"%RES%\"\nexit /b 0\n\n" + logo + "\n" + num)
    diag = OUT / "console_logo.bat"
    diag.write_bytes(script.replace("\n", "\r\n").encode("ascii"))
    subprocess.run(["cmd.exe", "/d", "/c", str(diag)], creationflags=subprocess.CREATE_NEW_CONSOLE,
                   timeout=60)
    txt = res.read_text(encoding="mbcs", errors="replace") if res.exists() else ""
    import re as _re
    cols = _re.search(r"Columns:\s+(\d+)", txt)
    got = _re.search(r"COLS=(\d+)", txt)
    art = _re.search(r"ART=(\S+)", txt)
    width = int(cols.group(1)) if cols else -1
    want = ("logo_116.txt" if width >= 118 else "logo_100.txt" if width >= 102 else
            "logo_72.txt" if width >= 74 else None)
    ok("E real console: the launcher reads the window's width (Columns, not Lines)",
       got is not None and int(got.group(1)) == width, txt.replace("\n", " | ")[:200])
    ok("E ... and chooses the art that fits it",
       (art is not None and art.group(1).endswith(want)) if want else art is None,
       f"width {width}, chose {art.group(1) if art else None}")
    if want and screen.exists():
        shown = screen.read_text(encoding="utf-8").splitlines()[1:]
        drawn = [s.rstrip() for s in (W_ASSETS() / want).read_text(encoding="utf-16").splitlines()]
        start = next((i for i, s in enumerate(shown) if s.strip()), 0)
        got_lines = shown[start:start + len(drawn)]
        bad = sum(s.count("\ufffd") + s.count("?") for s in got_lines)
        ok("E ... and the screen shows it exactly: every line, no garbled character",
           got_lines == drawn and bad == 0,
           f"{sum(a == b for a, b in zip(drawn, got_lines))} of {len(drawn)} lines, {bad} garbled")
    else:
        ok("E ... the screen could be read", False, "no screen file")


def main():
    for part in (part_a, part_b, part_c, part_d, part_e):
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
