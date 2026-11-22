"""
Developer test (not shipped): PeterPiper 1.2 part "launcher" - taking in older
PeterPiper versions (absorb.py, gui/absorbdlg.py) and the install progress in the
terminal (app/install_progress.py, PeterPiperV1.2.bat).

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v12_launcher.py

Everything happens in a FAKE user folder tree under _out/v12_launcher (passed to
absorb.py as explicit places - USERPROFILE is not changed). Nothing real is moved:
the Recycle Bin is faked, except one temporary test file that really goes to the
Recycle Bin (restorable).

A) install_progress.py: standard library only; package count of requirements.txt;
   the 'still working' words (downloading / installing, time so far, time left);
   a fake slow "pip" -> its output passed through, heartbeat lines while it is
   quiet, its exit code returned exactly (3 and 0); 'check' one by one with the
   count and 'all packages OK', exit 1 at a failing module; 'install' runs
   python -m pip install <options> -r <list>.
B) the launcher: earlier PeterPiper installs first in the reuse list (1.1, 1.0,
   then PD4nav's); step 2 for both lists through :pipinstall (helper, or plain pip
   when the helper is missing), step 3 through :checkpkgs (same module list as the
   plain check); 'Starting PeterPiper ...' before the program starts; CRLF. The
   two routines run for real in cmd.exe (a folder with '&' and brackets): pip's
   exit code comes back unchanged with and without the helper; the check passes.
C) detection: versions 1.0 (next to the running folder, its .lnk and its
   shortcuts_for.txt) and 1.1 (found only through the Desktop shortcut) are
   found; the running version, PD4nav's folders, a newer version (-> nothing
   offered) and a developer copy (.git: refused, its private Python kept) are
   handled; shortcut targets read from the .lnk file; fast; never raises.
D) carry-over: non-empty error logs and installed_versions.txt to
   <data>/logs/<version>, never over an existing file; settings found in the old
   folder go to the user (or 'carried over' when the user has them); a run list is
   merged, the user's own entries unchanged.
E) absorbing: only program files and the private Python go to the (fake)
   Recycle Bin; the user's files stay (and are listed); an emptied folder goes;
   the private Python the running PeterPiper uses is kept ("kept: PeterPiper 1.2
   uses it"); a file in use, that version still open (its error log held open)
   or a failing move stops that version and says so;
   the running folder and PeterPiper data are untouched; the shortcuts (real .lnk
   files in fake Desktop / Start-menu folders) now start the running .bat; the
   real in-use test; one real Recycle Bin move of a temp file.
F) "don't ask again" per folder (a new folder of that version is asked about again).
G) the start screen: the window appears once per start (not modal, the start
   screen stays usable), shows versions / folders / sizes, not with nothing found
   or PETERPIPER_NO_ABSORB; Don't ask again; Absorb shows what was done; fits 1366x768.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v12_launcher"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.pop("PETERPIPER_NO_ABSORB", None)
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtCore import Qt                                        # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox             # noqa: E402

APP = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

import install_progress as IP                                         # noqa: E402
from peterpiper import absorb as A                                    # noqa: E402

N = [0]
FAILS = []
BAT = REPO / "PeterPiperV4.0.bat"   # 4.0: the launcher was renamed
WIN = sys.platform == "win32"


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        APP.processEvents()
        time.sleep(0.01)


# ===================================================================== A
FAKE_PIP = r'''
import sys, time
print("Collecting numpy==2.4.6", flush=True)
print("  Downloading numpy-2.4.6-cp311-cp311-win_amd64.whl (12.6 MB)", flush=True)
time.sleep(2.6)
print("Collecting scipy==1.17.1", flush=True)
print("Installing collected packages: numpy, scipy, pillow, six, zipp", flush=True)
time.sleep(2.6)
print("Successfully installed numpy-2.4.6 scipy-1.17.1", flush=True)
sys.exit(int(sys.argv[1]))
'''


def part_a():
    src = (REPO / "app" / "install_progress.py").read_text(encoding="utf-8")
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    std = getattr(sys, "stdlib_module_names", set())
    ok("A the helper uses Python's own library only (runs before any package is there)",
       mods and all(m in std or m == "__future__" for m in mods), str(sorted(mods)))
    ok("A requirements.txt: 45 exact packages; the compatible list (ranges): no count",
       IP.count_packages(str(REPO / "app" / "requirements.txt")) == 45
       and IP.count_packages(str(REPO / "app" / "requirements-compatible.txt")) is None)
    clock = [100.0]
    w = IP.Watch(45, now=lambda: clock[0])
    # pip 24+: every package is looked up first (its description only), then the files
    for n in ("numpy==2.4.6", "scipy==1.17.1", "pillow==13.0.0"):
        w.feed(f"Collecting {n} (from -r C:/x/requirements.txt (line 13))")
        w.feed(f"  Downloading {n.split('==')[0]}-1.0-cp311-win_amd64.whl.metadata (6.6 kB)")
    clock[0] += 10
    l0 = w.line()
    w.feed("Downloading numpy-2.4.6-cp311-cp311-win_amd64.whl (12.6 MB)")
    w.feed("   ---------------------------------------- 12.6/12.6 MB 29.7 MB/s eta 0:00:00")
    w.feed("Downloading scipy-1.17.1-cp311-cp311-win_amd64.whl (36.6 MB)")
    w.feed("Downloading pyside6_essentials-6.12.0-cp310-abi3-win_amd64.whl (82.2 MB)")
    clock[0] += 90
    l1 = w.line()
    w.feed("Installing collected packages: numpy, scipy, pillow, six, zipp, tzdata")
    clock[0] += 40
    l3 = w.line()
    ok("A heartbeat words while looking up: the package, n of 45, time so far (no guess yet)",
       l0 == "  still working - looking up pillow - 3 of 45 packages (10 s so far)", l0)
    ok("A ... while downloading: the package file being fetched (its size), n of 45, time "
       "so far and left (by megabytes)",
       "still working - downloading pyside6_essentials (82.2 MB) - 3 of 45 packages" in l1
       and "1 min 40 s so far" in l1 and "min left" in l1, l1)
    ok("A ... installing the listed packages (first ones, then ...)",
       "still working - installing numpy, scipy, pillow, six, ..." in l3
       and "6 packages" in l3 and "2 min 20 s so far" in l3, l3)

    fake = OUT / "fake_pip.py"
    fake.write_text(FAKE_PIP, encoding="utf-8")
    env = dict(os.environ, PETERPIPER_HEARTBEAT_S="1")
    t0 = time.time()
    p = subprocess.run([sys.executable, str(REPO / "app" / "install_progress.py"), "run",
                        "--total", "45", "--", sys.executable, str(fake), "3"],
                       capture_output=True, env=env, timeout=120)
    out = p.stdout.decode("utf-8", "replace")
    ok("A fake slow pip: exit code 3 comes back exactly", p.returncode == 3, str(p.returncode))
    ok("A ... pip's own lines are passed through, in order",
       out.index("Collecting numpy") < out.index("Collecting scipy")
       < out.index("Successfully installed"), out[:200])
    hb = [ln for ln in out.splitlines() if "still working" in ln]
    ok("A ... 'still working' lines while it is quiet (download, then install)",
       any("downloading numpy" in h for h in hb) and any("installing numpy, scipy" in h
                                                         for h in hb), "\n".join(hb))
    ok("A ... and no heartbeat before 1 s of quiet (not flooding)", len(hb) <= 8, str(len(hb)))
    p = subprocess.run([sys.executable, str(REPO / "app" / "install_progress.py"), "run", "--",
                        sys.executable, str(fake), "0"], capture_output=True, env=env, timeout=120)
    ok("A ... exit code 0 too", p.returncode == 0, str(p.returncode))
    ok("A ... (took a few seconds, as the fake)", time.time() - t0 > 9, f"{time.time() - t0:.1f}")
    p = subprocess.run([sys.executable, str(REPO / "app" / "install_progress.py"), "check",
                        "json", "os.path"], capture_output=True, timeout=60)
    out = p.stdout.decode("utf-8", "replace")
    ok("A check: one by one with the count, then 'all packages OK', exit 0",
       p.returncode == 0 and "checking json ... OK  (1 of 2)" in out
       and "checking os.path ... OK  (2 of 2)" in out and "   all packages OK" in out, out)
    p = subprocess.run([sys.executable, str(REPO / "app" / "install_progress.py"), "check",
                        "json", "no_such_package_xyz", "os"], capture_output=True, timeout=60)
    out = p.stdout.decode("utf-8", "replace")
    ok("A check: a missing package -> FAILED with its error, exit 1, stops there",
       p.returncode == 1 and "no_such_package_xyz ... FAILED  (2 of 3)" in out
       and "ModuleNotFoundError" in out and "checking os" not in out
       and "all packages OK" not in out, out)
    seen = {}
    real = IP.watch_command
    IP.watch_command = lambda cmd, total=None, **k: seen.update(cmd=cmd, total=total) or 7
    try:
        rc = IP.main(["install", "C:/x/requirements.txt", "--no-input", "--only-binary=:all:"])
    finally:
        IP.watch_command = real
    ok("A install: python -m pip install <options> -r <list>, the list's count, pip's code",
       rc == 7 and seen["cmd"] == [sys.executable, "-m", "pip", "install", "--no-input",
                                   "--only-binary=:all:", "-r", "C:/x/requirements.txt"]
       and seen["total"] is None, str(seen))


# ===================================================================== B
def part_b():
    raw = BAT.read_bytes()
    ok("B the launcher keeps CRLF line endings only", raw.count(b"\r\n") == raw.count(b"\n"))
    bat = raw.decode("ascii")
    loop = next(ln for ln in bat.splitlines() if ln.startswith("for %%P in ("))
    ok("B reuse list (4.0): .PeterPiperV1.2, .PeterPiperV1.1, .PeterPiperV1.0, then PD4nav's "
       "(newest first)",
       loop.startswith("for %%P in (.PeterPiperV1.2 .PeterPiperV1.1 .PeterPiperV1.0 .PD4navV3.0 "),
       loop)
    ok("B step 2 (both lists) goes through :pipinstall; no direct pip call left there",
       bat.count('call :pipinstall "%APP%\\requirements.txt"') == 1
       and bat.count('call :pipinstall "%APP%\\requirements-compatible.txt"') == 1
       and bat.count("-m pip install") == 1, "")
    sub = bat[bat.index("\r\n:pipinstall\r\n"):bat.index("\r\n:checkpkgs\r\n")]
    ok("B :pipinstall: the helper when it is there, plain pip otherwise, exit code passed on",
       'if not exist "%APP%\\install_progress.py" goto pipplain' in sub
       and '"%VPY%" "%APP%\\install_progress.py" install "%~1" %PIPOPT%' in sub
       and '"%VPY%" -m pip install %PIPOPT% -r "%~1"' in sub
       and sub.count("exit /b %errorlevel%") == 2)
    chk = bat[bat.index("\r\n:checkpkgs\r\n"):]
    mods = chk[chk.index('set "MODS=') + 10:].split('"', 1)[0].split()
    plain = chk[chk.index("import ") + 7:].split(";", 1)[0].split(",")
    ok("B :checkpkgs checks the same 14 modules as the plain check", mods == plain
       and len(mods) == 14, str(mods))
    launch = bat[bat.index("\r\n:launch\r\n"):bat.index("\r\n:installonly\r\n")]
    ok("B the start says what happens ('Starting PeterPiper - the window opens in about "
       "10-20 seconds' the first time) before the program starts",
       "Starting PeterPiper - the window opens in about 10-20 seconds" in launch
       and launch.index("Starting PeterPiper") < launch.index("pythonw.exe"))
    ok("B step 1 says how long it takes", "(about 10-30 seconds; nothing is downloaded yet)" in bat)
    if not WIN:
        return
    # the two routines for real, in a folder with '&' and brackets
    d = OUT / "bat run & (x)"
    (d / "app").mkdir(parents=True)
    req = d / "app" / "requirements.txt"
    req.write_text("numpy==2.4.6\n", encoding="utf-8")
    shutil.copy2(REPO / "app" / "install_progress.py", d / "app" / "install_progress.py")
    routines = bat[bat.index("\r\n:pipinstall\r\n") + 2:]
    routines = routines[:routines.index("\r\nrem ---- helper: the PeterPiper logo")]
    for name, with_helper in (("helper", True), ("plain", False)):
        if not with_helper:
            (d / "app" / "install_progress.py").unlink()
        harness = ("@echo off\r\nsetlocal DisableDelayedExpansion\r\n"
                   f'set "APP={d / "app"}"\r\nset "VPY={sys.executable}"\r\n'
                   'set "PIPOPT=--no-such-option-xyz"\r\n'
                   'call :pipinstall "%APP%\\requirements.txt"\r\necho RC=%errorlevel%\r\n'
                   "call :checkpkgs\r\necho CHECK=%errorlevel%\r\nexit /b 0\r\n\r\n" + routines)
        hb = d / f"harness_{name}.bat"
        hb.write_bytes(harness.encode("mbcs"))
        p = subprocess.run(["cmd.exe", "/d", "/c", "call", str(hb)], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=300)
        out = (p.stdout + p.stderr).decode("mbcs", "replace")
        ok(f"B real cmd.exe ({name}): pip's exit code (2: unknown option) comes back unchanged",
           "RC=2" in out and "no-such-option-xyz" in out, out[-300:])
        if with_helper:
            ok("B real cmd.exe: the package check passes one by one in this Python ('checking "
               "numpy ... OK  (1 of 14)' ... 'all packages OK')",
               "checking numpy ... OK  (1 of 14)" in out and "all packages OK" in out
               and "CHECK=0" in out, out[-400:])
        else:
            ok("B real cmd.exe (plain): the one-line check still works", "all packages OK" in out
               and "CHECK=0" in out, out[-300:])


# ===================================================================== C
def mk(p: Path, data: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data, encoding="utf-8")
    return p


def program(folder: Path, name: str, extra_user=()) -> Path:
    mk(folder / f"{name}.bat", "@echo off\r\n")
    mk(folder / "app" / "peterpiper" / "__init__.py", "v = 1\n")
    mk(folder / "app" / "PeterPiper.py", "print(1)\n")
    for n in ("README.md", "README.html", "READ ME.txt", "LICENSE", "CITATION.cff",
              "CHANGELOG.md", "CONTRIBUTING.md", "PeterPiper.lnk"):
        mk(folder / n)
    mk(folder / "docs" / "manual.md")
    mk(folder / "_update_backup" / "1.0.0_x" / "old.py")
    for rel in extra_user:
        mk(folder / rel, "the user's own")
    return folder


def home(profile: Path, ver: str, bat: Path = None, logs=True) -> Path:
    h = profile / f".PeterPiperV{ver}"
    mk(h / "venv" / "Scripts" / "python.exe", "not really python")
    mk(h / "venv" / "Lib" / "site-packages" / "numpy" / "__init__.py", "0" * 5000)
    mk(h / "venv" / "installed_requirements.txt", "numpy==2.4.6\n")
    mk(h / "venv" / "installed_versions.txt", f"# PeterPiperV{ver} install\nnumpy==2.4.6\n")
    if bat is not None:
        mk(h / "shortcuts_for.txt", f"{bat}\n")
    if logs:
        mk(h / "error_123.txt", "Traceback: something\n")
        mk(h / "error_456.txt", "")
    return h


T = {}


def files_under(p: Path) -> list:
    return sorted(str(x.relative_to(p)) for x in p.rglob("*"))


def setup_tree():
    base = OUT / "tree"
    profile = base / "Users" / "you"
    progs = base / "Programs"
    running = program(progs / "PeterPiperV1.2", "PeterPiperV1.2")
    v10 = program(progs / "PeterPiperV1.0", "PeterPiperV1.0",
                  extra_user=("OUTPUT_movie 1/PeterPiper_sessions/s.npz", "my notes.txt",
                              "movie 7.nd2"))
    v11 = program(base / "Elsewhere" / "PeterPiper old", "PeterPiperV1.1")
    pd = progs / "PD4navV3.0"
    mk(pd / "PD4navV3.0.bat")
    mk(pd / "app" / "roinav" / "__init__.py")
    mk(profile / ".PD4navV3.0" / "venv" / "Scripts" / "python.exe")
    h10 = home(profile, "1.0", v10 / "PeterPiperV1.0.bat")
    h11 = home(profile, "1.1", v11 / "PeterPiperV1.1.bat", logs=False)
    mk(h10 / "settings.json", json.dumps({"from": "old"}))
    mk(h10 / "run_history.json", json.dumps({"fpB": {"runs": [{"path": "C:/b.npz"}],
                                                     "paths": ["C:/b.nd2"]}}))
    mk(h10 / "compare_colours.json", json.dumps({"old": 1}))
    desk, start = base / "Desktop", base / "Start Menu Programs"
    desk.mkdir(parents=True)
    start.mkdir(parents=True)
    data = OUT / "home"
    user = data / "users" / "Test User"
    mk(user / "run_history.json", json.dumps({"fpA": {"runs": [{"path": "C:/a.npz"}],
                                                      "paths": ["C:/a.nd2"]}}))
    mk(user / "compare_colours.json", json.dumps({"mine": 1}))
    mk(data / "logs" / "PeterPiperV1.0" / "installed_versions.txt", "NEWER - keep me\n")
    T.update(base=base, profile=profile, progs=progs, running=running, v10=v10, v11=v11,
             h10=h10, h11=h11, desk=desk, start=start, data=data, user=user, pd=pd)
    lnk_ok = False
    if WIN:
        lnk_ok = (A.write_shortcut(desk / "PeterPiper.lnk", v11 / "PeterPiperV1.1.bat", None, "t")
                  and A.write_shortcut(start / "PeterPiper.lnk", v10 / "PeterPiperV1.0.bat",
                                       None, "t"))
        (h11 / "shortcuts_for.txt").unlink()        # 1.1 only through the Desktop shortcut
    T["lnk"] = lnk_ok
    return places()


def places(**kw) -> A.Places:
    d = dict(profile=T["profile"], program=T["running"], data=T["data"],
             shortcut_dirs=[T["desk"], T["start"]], in_use=[T["h11"] / "venv"], running=(1, 2),
             running_bat=T["running"] / "PeterPiperV1.2.bat", user_home=T["user"])
    d.update(kw)
    return A.Places(**d)


def part_c():
    pl = setup_tree()
    if WIN:
        ok("C shortcut targets are read from the .lnk file itself",
           T["lnk"] and A.read_lnk_target(T["desk"] / "PeterPiper.lnk").lower()
           == str(T["v11"] / "PeterPiperV1.1.bat").lower(),
           A.read_lnk_target(T["desk"] / "PeterPiper.lnk"))
    t0 = time.time()
    found = A.find(pl)
    dt = time.time() - t0
    vs = {f.version: f for f in found}
    ok("C found: 1.0 and 1.1 (not 1.2 itself, not PD4nav's)", sorted(vs) == [(1, 0), (1, 1)],
       str(sorted(vs)))
    ok("C ... fast (no folder walks)", dt < 1.0, f"{dt:.3f} s")
    f10, f11 = vs.get((1, 0)), vs.get((1, 1))
    ok("C 1.0: its program folder (next to the running one) and its private Python",
       f10 and [str(p) for p in f10.programs] == [str(T["v10"])] and f10.home == T["h10"]
       and not f10.keep_home and f10.absorbable)
    ok("C 1.1: found through the Desktop shortcut only (a folder with another name)",
       (not WIN) or (f11 and [str(p) for p in f11.programs] == [str(T["v11"])]))
    ok("C 1.1: the private Python the running PeterPiper uses is kept",
       f11 and f11.keep_home == "kept: PeterPiper 1.2 uses it", f11.keep_home if f11 else "")
    ok("C nothing found is the running folder or PD4nav's",
       all(str(T["running"]) not in map(str, f.programs)
           and str(T["pd"]) not in map(str, f.programs) for f in found))
    ok("C never raises: a user folder that is a file / missing places -> nothing",
       A.find(places(profile=mk(OUT / "notafolder"), program=OUT / "nope" / "x",
                     shortcut_dirs=[])) == []
       and A.find(object()) == [])
    newer = T["profile"] / ".PeterPiperV1.3"
    newer.mkdir()
    ok("C a NEWER PeterPiper on the computer -> nothing offered (the newest one absorbs)",
       A.find(pl) == [] and A.to_offer(pl) == [])
    newer.rmdir()
    # developer copy of 1.1 (a git checkout): refused, its private Python kept
    dev = program(T["base"] / "Code" / "PeterPiperV1.1", "PeterPiperV1.1")
    (dev / ".git").mkdir()
    devrun = program(T["base"] / "Code" / "run" / "PeterPiperV1.2", "PeterPiperV1.2")
    pl_dev = places(in_use=[], shortcut_dirs=[], profile=T["base"] / "Users" / "dev",
                    program=devrun, running_bat=devrun / "PeterPiperV1.2.bat")
    hd = home(pl_dev.profile, "1.1", dev / "PeterPiperV1.1.bat")
    fd = A.find(pl_dev)
    ok("C a developer copy (.git) is refused and the private Python it uses is kept",
       len(fd) == 1 and fd[0].programs == [] and fd[0].dev_copies == [dev]
       and fd[0].keep_home.startswith("kept: the developer copy") and not fd[0].absorbable
       and A.to_offer(pl_dev) == [], str(fd))
    out = A.absorb(fd[0], pl_dev, recycler=lambda p: T.setdefault("dev_moved", []).append(p) or "",
                   writer=lambda *a: True, checker=lambda p: "")
    ok("C ... even asked directly, nothing of it is moved", not T.get("dev_moved")
       and (dev / "app").is_dir() and (hd / "venv").is_dir(), str(out.lines()))
    T["pl"] = pl
    T["found"] = vs


# ===================================================================== D / E
class FakeBin:
    def __init__(self, folder: Path):
        self.folder, self.moved = folder, []
        folder.mkdir(parents=True, exist_ok=True)

    def __call__(self, p: Path) -> str:
        self.moved.append(Path(p))
        shutil.move(str(p), str(self.folder / f"{len(self.moved)}_{Path(p).name}"))
        return ""


def part_d():
    pl, f10 = T["pl"], T["found"][(1, 0)]
    done = A.carry_over(f10, pl)
    logs = T["data"] / "logs" / "PeterPiperV1.0"
    ok("D a non-empty error log is copied to <data>/logs/PeterPiperV1.0; an empty one is not",
       (logs / "error_123.txt").read_text() == "Traceback: something\n"
       and not (logs / "error_456.txt").exists(), str(done))
    ok("D an existing (newer) file there is never overwritten",
       (logs / "installed_versions.txt").read_text() == "NEWER - keep me\n")
    ok("D settings found in the old folder go to the user (they had none)",
       json.loads((T["user"] / "settings.json").read_text()) == {"from": "old"})
    cc = T["data"] / "carried over" / "PeterPiperV1.0" / "compare_colours.json"
    ok("D the user's own file stays; the old one is kept aside under 'carried over'",
       json.loads((T["user"] / "compare_colours.json").read_text()) == {"mine": 1}
       and json.loads(cc.read_text()) == {"old": 1})
    idx = json.loads((T["user"] / "run_history.json").read_text())
    ok("D the run lists are merged: the user's entry unchanged, the old one added",
       idx.get("fpA", {}).get("runs") == [{"path": "C:/a.npz"}] and "fpB" in idx, str(idx)[:200])
    again = A.carry_over(f10, pl)
    ok("D carrying over twice adds nothing new", not [a for a in again if "->" in a], str(again))


def part_e():
    pl, f10, f11 = T["pl"], T["found"][(1, 0)], T["found"].get((1, 1))
    running_before = files_under(T["running"])
    data_before = files_under(T["data"])
    p = A.plan(f10)
    names = sorted(x.name for x in p.remove)
    ok("E plan for 1.0: exactly its program files and its private Python folder's own items",
       names == sorted(["PeterPiperV1.0.bat", "app", "README.md", "README.html", "READ ME.txt",
                        "LICENSE", "CITATION.cff", "CHANGELOG.md", "CONTRIBUTING.md",
                        "PeterPiper.lnk", "docs", "_update_backup", "venv", "error_123.txt",
                        "error_456.txt", "shortcuts_for.txt"]), str(names))
    kept = sorted(x.name for x, _w in p.keep)
    ok("E ... the user's files in it are kept (results, notes, a movie; settings files in the "
       "old Python folder too)",
       {"OUTPUT_movie 1", "my notes.txt", "movie 7.nd2"} <= set(kept)
       and "settings.json" in kept, str(kept))
    s = A.sizes(f10)
    ok("E sizes: program files and private Python counted", s["program"] > 0
       and s["python"] > 5000 and s["kept"] > 0, str(s))
    # a file in use stops everything for that version
    out = A.absorb(f10, pl, recycler=lambda p: "should not be called",
                   writer=lambda *a: False, checker=lambda p: "a file in it is in use"
                   if p.name == "venv" else "")
    ok("E a file in use -> nothing of that version moved, said plainly",
       "Nothing of PeterPiper 1.0 was moved" in out.problem and not out.recycled
       and (T["v10"] / "app").is_dir() and (T["h10"] / "venv").is_dir(), out.problem)
    # that version open now: its launcher holds its error log open
    out = A.absorb(f10, pl, recycler=lambda p: "should not be called", writer=lambda *a: False,
                   checker=lambda p: "in use" if p.name == "error_123.txt" else "")
    ok("E that version still open (its log is in use) -> 'seems to be open - close it', "
       "nothing moved", "PeterPiper 1.0 seems to be open - close it" in out.problem
       and not out.recycled and (T["v10"] / "app").is_dir(), out.problem)
    if WIN:
        log = T["h10"] / "error_123.txt"
        fh = open(log, "a")
        try:
            busy = A.in_use(log)
        finally:
            fh.close()
        ok("E ... the real test sees a log file held open", busy != "" and log.exists(), busy)
    # a failing move stops there; what moved is listed
    calls = []

    def flaky(p):
        calls.append(p)
        return "" if len(calls) == 1 else "the drive has no Recycle Bin"
    fb_dir = OUT / "fakebin_flaky"
    fb = FakeBin(fb_dir)
    out = A.absorb(f10, pl, recycler=lambda p: flaky(p) or fb(p), writer=lambda *a: False,
                   checker=lambda p: "")
    ok("E a failing move stops that version: one moved, the rest kept, said plainly",
       len(out.recycled) == 1 and "Stopped here" in out.problem and len(calls) == 2
       and any("stopped before" in ln for ln in out.lines()), out.problem)
    # put the moved item back, then the real run (fake bin, real shortcuts)
    back = next(fb_dir.iterdir())
    shutil.move(str(back), str(out.recycled[0]))
    bin1 = FakeBin(OUT / "fakebin")
    writes = []

    def writer(lnk, target, icon, desc):
        writes.append((lnk, target))
        return A.write_shortcut(lnk, target, icon, desc) if WIN else True
    out = A.absorb(f10, pl, recycler=bin1, writer=writer, checker=lambda p: "")
    moved = sorted(p.name for p in bin1.moved)
    ok("E absorbing 1.0: program files and private Python to the Recycle Bin, nothing else",
       not out.problem and {"PeterPiperV1.0.bat", "app", "venv", "docs"} <= set(moved)
       and "my notes.txt" not in moved and "OUTPUT_movie 1" not in moved, out.problem or str(moved))
    ok("E ... the user's files are still where they were",
       (T["v10"] / "my notes.txt").exists() and (T["v10"] / "movie 7.nd2").exists()
       and (T["v10"] / "OUTPUT_movie 1" / "PeterPiper_sessions" / "s.npz").exists())
    txt = "\n".join(out.lines())
    ok("E ... and the window text says what was kept and where",
       f"kept where they are, in {T['v10']}" in txt and "my notes.txt" in txt
       and "can be restored" in txt, txt)
    ok("E ... the old Python folder keeps only what is not PeterPiper's",
       sorted(x.name for x in T["h10"].iterdir()) == ["compare_colours.json", "run_history.json",
                                                      "settings.json"])
    ok("E the start-menu shortcut that started 1.0 now starts the running .bat",
       writes and writes[0][0] == T["start"] / "PeterPiper.lnk"
       and writes[0][1] == T["running"] / "PeterPiperV1.2.bat"
       and (not WIN or A.read_lnk_target(T["start"] / "PeterPiper.lnk").lower()
            == str(T["running"] / "PeterPiperV1.2.bat").lower()), str(writes))
    ok("E ... the Desktop one (it starts 1.1) is left for 1.1",
       not WIN or "PeterPiper old" in A.read_lnk_target(T["desk"] / "PeterPiper.lnk"))
    ok("E the running program folder is untouched", files_under(T["running"]) == running_before)
    data_after = [x for x in files_under(T["data"]) if x not in data_before]
    ok("E PeterPiper data: only things were added (nothing removed)",
       all(x in files_under(T["data"]) for x in data_before), str(data_after))
    if f11 is not None and WIN:
        bin2 = FakeBin(OUT / "fakebin2")
        writes.clear()
        out = A.absorb(f11, pl, recycler=bin2, writer=writer, checker=lambda p: "")
        ok("E absorbing 1.1: its program folder goes (then empty, so removed too)",
           not out.problem and not T["v11"].exists() and (T["v11"].parent).exists(),
           out.problem)
        ok("E ... its private Python is KEPT (PeterPiper 1.2 uses it) and said so",
           (T["h11"] / "venv" / "Scripts" / "python.exe").exists()
           and not any(p.name == "venv" for p in bin2.moved)
           and f"kept: {T['h11']} - PeterPiper 1.2 uses it" in "\n".join(out.lines()),
           "\n".join(out.lines()))
        ok("E ... the Desktop shortcut now starts the running .bat",
           A.read_lnk_target(T["desk"] / "PeterPiper.lnk").lower()
           == str(T["running"] / "PeterPiperV1.2.bat").lower())
    # a shortcut to a developer copy is never re-pointed
    if WIN:
        dev = T["base"] / "Code" / "PeterPiperV1.1"
        lnk_dir = OUT / "desk_dev"
        lnk_dir.mkdir()
        A.write_shortcut(lnk_dir / "PeterPiper.lnk", dev / "PeterPiperV1.1.bat", None, "t")
        fdev = A.Found(version=(1, 1), dev_copies=[dev], running_label="PeterPiper 1.2")
        got = A.repoint_shortcuts(fdev, places(shortcut_dirs=[lnk_dir]), writer=lambda *a: True)
        ok("E a shortcut that starts a developer copy is not re-pointed", got == [], str(got))
    # the real in-use test and one real Recycle Bin move
    if WIN:
        d = OUT / "inuse test"
        mk(d / "f.txt")
        fh = open(d / "f.txt", "rb")
        try:
            busy = A.in_use(d)
        finally:
            fh.close()
        ok("E real in-use test: a folder with an open file is 'in use'; closed it is free",
           busy != "" and A.in_use(d) == "" and (d / "f.txt").exists(), busy)
        ok("E no Recycle Bin on a network path -> refused (nothing deleted for good)",
           A.has_recycle_bin(Path(r"\\server\share\x")) is False
           and A.has_recycle_bin(OUT) is True)
        tmp = mk(OUT / f"PeterPiper absorb test - safe to delete {os.getpid()}.txt", "test")
        why = A.recycle(tmp)
        ok("E one real move of a temp test file to the Recycle Bin (restorable)",
           why == "" and not tmp.exists(), why)


# ===================================================================== F
def part_f():
    pl = T["pl"]
    # fresh tree for the offer state
    left = A.to_offer(pl)
    A.set_dont_ask(left, pl.data)
    st = json.loads((pl.data / A.STATE_FILE).read_text())
    ok("F 'Don't ask again' is remembered per folder in PeterPiper data (absorb.json)",
       left and A.to_offer(pl) == [] and all(k in st["dont_ask"] for f in left for k in f.keys()),
       str(st)[:200])
    extra = program(T["progs"] / "PeterPiperV1.0 copy", "PeterPiperV1.0")
    again = A.to_offer(pl)
    ok("F a new folder of that version is asked about again",
       len(again) == 1 and extra in again[0].programs, str(again))
    T["extra"] = extra


# ===================================================================== G
def part_g():
    from peterpiper.gui import absorbdlg as AD
    from peterpiper.gui.setup import SetupDialog
    from peterpiper import users
    from peterpiper.gui import theme as TH
    TH.apply(APP, "midnight", 11.0)
    if "Test User" not in users.all_users():
        users.add_user("Test User")
    # a fresh tree (the earlier parts moved things)
    shutil.rmtree(OUT / "tree", ignore_errors=True)
    shutil.rmtree(OUT / "home", ignore_errors=True)
    pl = setup_tree()
    real_default = A.default_places
    A.default_places = lambda: pl
    AD._offered = False
    try:
        d = SetupDialog()
        d.show()
        pump(1.2)
        dlg = getattr(d, "absorb_dlg", None)
        ok("G the start screen opens the 'older versions' window by itself, after it shows",
           isinstance(dlg, AD.AbsorbDialog) and dlg.isVisible())
        ok("G ... not modal: the start screen stays usable", dlg is not None and not dlg.isModal()
           and dlg.windowModality() == Qt.NonModal and d.isEnabled())
        btns = [b.text() for b in dlg.findChildren(type(dlg.btn_absorb)) if b.isVisible()]
        ok("G ... buttons Absorb / Not now / Don't ask again for these",
           {"Absorb", "Not now", "Don't ask again for these"} <= set(btns), str(btns))
        pump(1.5)
        txt = "\n".join(lab.text() for lab in dlg.details)
        ok("G ... it shows each version, its folders and sizes",
           [c.text() for c in dlg.checks] == ["PeterPiper 1.0", "PeterPiper 1.1"][:len(dlg.checks)]
           and str(T["v10"]) in txt and "counting" not in txt and "bytes)" in txt, txt)
        ok("G ... and the kept private Python", "kept: PeterPiper 1.2 uses it" in txt
           or not WIN, txt)
        ok("G ... and what absorbing does (Recycle Bin, own files stay)",
           any("Recycle Bin" in lab.text() and "stay where they are" in lab.text()
               for lab in dlg.findChildren(type(dlg.lbl_result))))
        dlg.adjustSize()
        hint = dlg.size()
        ok("G ... fits 1366 x 768", hint.width() <= 1366 and hint.height() <= 700,
           f"{hint.width()} x {hint.height()}")
        os.environ["QT_QPA_FONTDIR"] = os.environ.get("QT_QPA_FONTDIR", "C:/Windows/Fonts")
        dlg.grab().save(str(SHOTS / "v12_absorb_prompt.png"))
        d2 = SetupDialog()
        d2.show()
        pump(1.0)
        ok("G once per program start: a second start screen does not ask again",
           getattr(d2, "absorb_dlg", None) is None)
        d2.close()
        # Absorb from the window (fake Recycle Bin and shortcuts)
        fb = FakeBin(OUT / "fakebin_gui")
        real_rec, real_use, real_w = A.recycle, A.in_use, A.write_shortcut
        A.recycle, A.in_use, A.write_shortcut = fb, (lambda p: ""), (lambda *a: True)
        try:
            dlg._absorb()
        finally:
            A.recycle, A.in_use, A.write_shortcut = real_rec, real_use, real_w
        pump(0.3)
        res = dlg.lbl_result.text()
        ok("G Absorb: the window says what was done and what was kept where",
           dlg.choice == "absorb" and res.startswith("Done.") and "PeterPiper 1.0:" in res
           and f"kept where they are, in {T['v10']}" in res and dlg.btn_close.isVisible()
           and not dlg.btn_absorb.isVisible(), res[:300])
        ok("G ... the program files really went (fake Recycle Bin), the notes stayed",
           not (T["v10"] / "app").exists() and (T["v10"] / "my notes.txt").exists())
        dlg.grab().save(str(SHOTS / "v12_absorb_done.png"))
        hint = dlg.size()
        ok("G ... the result still fits 1366 x 768", hint.width() <= 1366 and hint.height() <= 700,
           f"{hint.width()} x {hint.height()}")
        dlg.close()
        d.close()
        # Don't ask again from the window
        shutil.rmtree(OUT / "tree", ignore_errors=True)
        pl = setup_tree()
        A.default_places = lambda: pl
        AD._offered = False
        w = AD.offer_on_start(None)
        ok("G (a new start) the window comes again", isinstance(w, AD.AbsorbDialog))
        w._dont_ask()
        AD._offered = False
        ok("G Don't ask again: closes, and the next start asks nothing",
           w.choice == "dont_ask" and AD.offer_on_start(None) is None)
        # nothing found / switched off
        AD._offered = False
        A.default_places = lambda: places(profile=OUT / "empty", program=OUT / "empty" / "p",
                                          shortcut_dirs=[])
        ok("G nothing to take in -> no window", AD.offer_on_start(None) is None)
        AD._offered = False
        shutil.rmtree(OUT / "tree", ignore_errors=True)
        shutil.rmtree(OUT / "home" / A.STATE_FILE, ignore_errors=True)
        (OUT / "home" / A.STATE_FILE).unlink(missing_ok=True)
        pl = setup_tree()
        A.default_places = lambda: pl
        os.environ["PETERPIPER_NO_ABSORB"] = "1"
        try:
            ok("G PETERPIPER_NO_ABSORB=1 -> no window", AD.offer_on_start(None) is None)
        finally:
            os.environ.pop("PETERPIPER_NO_ABSORB", None)
        AD._offered = False
        A.default_places = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        ok("G a problem while looking never reaches the start screen",
           AD.offer_on_start(None) is None)
    finally:
        A.default_places = real_default
        users.deactivate()


def main():
    for part in (part_a, part_b, part_c, part_d, part_e, part_f, part_g):
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
