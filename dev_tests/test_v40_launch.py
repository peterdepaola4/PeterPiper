"""
Developer test (not shipped): PeterPiper 4.0 part "launch" - ONE download for
Windows AND macOS (platforms.py, PeterPiperV4.0.bat, PeterPiperV4.0.command,
the uv fallback, build_zip.py, absorb.py on a Mac, updater.py with the one zip).

    python dev_tests/test_v40_launch.py

Runs on Windows, macOS and Linux (CI: .github/workflows/launchers.yml). Nothing
real is changed: every place is a fake folder under _out/v40_launch; no network
(the uv download is faked with a local file whose SHA-256 is wrong, so the
launchers must refuse it); no shortcut on the real Desktop; nothing to the real
Trash.

A) platforms.py with a faked system (TEST_HOOKS / arguments): names (Recycle Bin /
   Trash, Explorer / Finder, Ctrl -> Cmd), install / app-data / log folders and the
   private Python per system, long_path / plain_path, cloud_roots() on a fake
   Windows and a fake Mac home (Box, OneDrive, Google Drive incl. a drive letter,
   Dropbox incl. info.json, iCloud; order; nothing that does not exist; no
   duplicates), is_online_only() from faked file attributes (Windows
   RECALL_ON_DATA_ACCESS / RECALL_ON_OPEN / OFFLINE; Mac SF_DATALESS), the Mac
   wrapper app (Info.plist, start script with a tricky path, icon, never over a
   foreign PeterPiper.app), make_shortcuts (Windows: 3 .lnk through a fake writer;
   Mac: the app + Desktop alias), move_to_trash into a fake Trash.
B) absorb.py on a Mac: an older PeterPiper.app (from a .dmg) is found and goes
   whole to the (fake) Trash; the launcher's own wrapper app is never taken; a
   newer app -> nothing offered.
C) updater.py: the one zip for zip installs on both systems; the Mac app takes its
   .dmg (Apple chip / Intel), else the zip; a folder with only the .command is a
   zip install; the launcher's name per system; permissions from the zip are
   kept (posix only).
D) the .bat: CRLF; the uv pin (version + 64-hex SHA-256) and the question; the
   reuse list starts with 1.2; for real in cmd.exe (Windows only): a fake uv
   archive -> refused (SHA-256 differs), deleted, nothing run, the 'install
   Python yourself' help; 'no' -> the python.org help, nothing downloaded;
   install-only never asks. Optional: a real uv from an earlier manual run
   (_out/uvreal) is found by :uvfind in a folder with '&' and brackets.
E) the .command: LF only, #!/bin/bash, executable in git, bash -n, no bash-4-only
   features (macOS has bash 3.2); its functions sourced in bash: SHA-256 check
   (right / wrong / upper case), Python probe with fake Pythons (3.9 refused, 3.12
   taken), the fake uv archive refused and deleted; whole runs (any system, via
   PETERPIPER_ANY_SYSTEM): not unpacked, no Python + 'no', a fake uv archive;
   on Windows / Linux without that switch it says it is for macOS.
F) build_zip.py: one zip with both launchers, the .command 0755 and LF inside,
   the .bat CRLF, platforms.py inside, nothing from _out / dev_tests / logs /
   lab_paths.json; a missing .command stops the build.
G) the audit: no sys.platform / os.name / os.startfile / winreg / windll left in
   the launch part's own files outside platforms.py (and syscheck's elevation).
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v40_launch"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
os.environ.setdefault("PETERPIPER_HOME", str(OUT / "home"))
sys.path.insert(0, str(REPO / "app"))

from peterpiper import absorb as A                                    # noqa: E402
from peterpiper import platforms as P                                 # noqa: E402
from peterpiper import updater as U                                   # noqa: E402

WIN = sys.platform == "win32"
BAT = REPO / "PeterPiperV4.0.bat"
CMD = REPO / "PeterPiperV4.0.command"
N = [0]
FAILS = []


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def mk(p: Path, data="x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_text(data, encoding="utf-8")
    return p


def mkdirs(*ps):
    for p in ps:
        Path(p).mkdir(parents=True, exist_ok=True)


# ===================================================================== A
def part_a():
    for sysn, trash, fm in (("win32", "Recycle Bin", "Explorer"), ("darwin", "Trash", "Finder"),
                            ("linux", "Trash", "the file manager")):
        ok(f"A {sysn}: '{trash}', '{fm}'",
           P.trash_name(sysn) == trash and P.file_manager_name(sysn) == fm)
    ok("A shortcut words: Ctrl+Z stays on Windows, Cmd+Z on a Mac (Qt maps the key itself)",
       P.key_text("Ctrl+Z", "win32") == "Ctrl+Z" and P.key_text("Ctrl+Z", "darwin") == "Cmd+Z")
    P.TEST_HOOKS["system"] = "darwin"
    try:
        ok("A TEST_HOOKS['system'] fakes the system for the functions",
           P.system() == "darwin" and P.trash_name() == "Trash" and U.launcher_name()
           == "PeterPiperV4.0.command")
    finally:
        P.TEST_HOOKS.clear()
    ok("A exactly one of IS_WIN / IS_MAC / IS_LINUX on this computer",
       int(P.IS_WIN) + int(P.IS_MAC) + int(P.IS_LINUX) == 1, P.SYSTEM)
    home = OUT / "fake home"
    ok("A app-data folder per system",
       P.app_data_dir("PeterPiper", "win32", {"LOCALAPPDATA": "C:/L"}, home) == Path("C:/L/PeterPiper")
       and P.app_data_dir("PeterPiper", "darwin", {}, home)
       == home / "Library" / "Application Support" / "PeterPiper"
       and P.app_data_dir("PeterPiper", "linux", {}, home) == home / ".local" / "share" / "PeterPiper")
    ok("A logs: ~/Library/Logs/PeterPiper on a Mac, PeterPiper data/logs elsewhere",
       P.logs_dir("darwin", home) == home / "Library" / "Logs" / "PeterPiper"
       and P.logs_dir("win32", home) == home / "PeterPiper data" / "logs")
    ok("A install folder: ~/.PeterPiperV4.0, or PETERPIPER_HOME",
       P.install_home("PeterPiperV4.0", {}, home) == home / ".PeterPiperV4.0"
       and P.install_home("PeterPiperV4.0", {"PETERPIPER_HOME": "X"}, home) == Path("X"))
    ok("A private Python: Scripts\\pythonw.exe on Windows, bin/python on a Mac",
       P.venv_python(Path("v"), True, "win32") == Path("v/Scripts/pythonw.exe")
       and P.venv_python(Path("v"), True, "darwin") == Path("v/bin/python"))
    lp = P.long_path(str(OUT / "a"))
    ok("A long_path: \\\\?\\ form on Windows only; plain_path gives the path back",
       (lp.startswith("\\\\?\\") if WIN else lp == str(OUT / "a"))
       and P.plain_path(lp) == (os.path.abspath(str(OUT / "a")) if WIN else str(OUT / "a")))
    ok("A long_paths_enabled: a yes/no on Windows, None elsewhere",
       (P.long_paths_enabled() in (True, False, None)) if WIN else P.long_paths_enabled() is None)

    # ---- cloud roots: a fake Windows home
    wh = OUT / "win home"
    gdrive = OUT / "G drive"
    od_env = wh / "OneDrive - Contoso Lab"
    mkdirs(wh / "Box", od_env, wh / "OneDrive", gdrive / "My Drive", gdrive / "Shared drives",
           wh / "Dropbox (Lab)", wh / "iCloudDrive", wh / "Documents")
    elsewhere = OUT / "elsewhere" / "Dropbox"
    mkdirs(elsewhere)
    mk(wh / "AppData" / "Local" / "Dropbox" / "info.json",
       '{"personal": {"path": "%s"}}' % str(elsewhere).replace("\\", "\\\\"))
    env = {"OneDriveCommercial": str(od_env), "OneDrive": str(od_env),
           "LOCALAPPDATA": str(wh / "AppData" / "Local"),
           "OneDriveConsumer": str(wh / "no such folder")}
    roots = P.cloud_roots("win32", wh, env, drives=[str(gdrive) + os.sep])
    svc = [s for s, _p in roots]
    paths = [Path(p) for _s, p in roots]
    ok("A cloud_roots (Windows): Box, OneDrive (variable + folder), Google Drive (drive: My "
       "Drive + Shared drives), Dropbox (folder + info.json), iCloud - in that order",
       svc == ["Box", "OneDrive", "OneDrive", "Google Drive", "Google Drive", "Dropbox",
               "Dropbox", "iCloud Drive"], str(svc))
    ok("A ... no duplicates (one OneDrive folder named twice), nothing that does not exist",
       len(set(paths)) == len(paths) and all(p.is_dir() for p in paths)
       and wh / "no such folder" not in paths and od_env in paths and elsewhere in paths)
    # ---- cloud roots: a fake Mac home
    mh = OUT / "mac home"
    cs = mh / "Library" / "CloudStorage"
    mkdirs(cs / "Box-Box", cs / "OneDrive-Personal", cs / "OneDrive-ContosoLab",
           cs / "GoogleDrive-someone@example.org" / "My Drive", cs / "Dropbox",
           mh / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    roots = P.cloud_roots("darwin", mh, {}, drives=[])
    svc = [s for s, _p in roots]
    ok("A cloud_roots (Mac): ~/Library/CloudStorage Box-Box, OneDrive-*, GoogleDrive-*/My Drive, "
       "Dropbox, iCloud Drive (Mobile Documents)",
       svc == ["Box", "OneDrive", "OneDrive", "Google Drive", "Dropbox", "iCloud Drive"]
       and str(cs / "GoogleDrive-someone@example.org" / "My Drive") in [p for _s, p in roots],
       str(svc))
    ok("A cloud_roots on this computer answers (never raises)", isinstance(P.cloud_roots(), list))

    # ---- online-only files from faked attributes
    def fake(**kw):
        return lambda _p: SimpleNamespace(**kw)

    def boom(_p):
        raise OSError("gone")
    win_cases = [(0x400000, True), (0x40000, True), (0x1000, True), (0x20, False), (0, False)]
    ok("A is_online_only (Windows): RECALL_ON_DATA_ACCESS / RECALL_ON_OPEN / OFFLINE -> yes; "
       "ARCHIVE / nothing -> no",
       all(P.is_online_only("f", "win32", fake(st_file_attributes=a)) is want
           for a, want in win_cases))
    ok("A is_online_only (Mac): SF_DATALESS in st_flags -> yes; other flags -> no; Linux -> no; "
       "a missing file -> no",
       P.is_online_only("f", "darwin", fake(st_flags=0x40000000))
       and not P.is_online_only("f", "darwin", fake(st_flags=0x20))
       and not P.is_online_only("f", "linux", fake(st_flags=0x40000000))
       and not P.is_online_only("f", "darwin", boom))

    # ---- the Mac wrapper app
    apps = OUT / "Applications & (test)"
    launcher = OUT / "Lab's PeterPiper" / "PeterPiperV4.0.command"
    icns = REPO / "app" / "peterpiper" / "assets" / "PeterPiper.icns"
    app = P.write_mac_app(apps, launcher, icns, "4.0.0")
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes()) if app else {}
    ok("A Mac app: Info.plist (name, executable, icon, version, its own mark)",
       app is not None and info.get("CFBundleExecutable") == "PeterPiper"
       and info.get("CFBundleIconFile") == "PeterPiper" and info.get("CFBundleShortVersionString")
       == "4.0.0" and info.get(P.MAC_MARK) == str(launcher) and info.get("CFBundlePackageType")
       == "APPL" and (app / "Contents" / "Resources" / "PeterPiper.icns").read_bytes()
       == icns.read_bytes(), str(info)[:200])
    script = (app / "Contents" / "MacOS" / "PeterPiper").read_bytes() if app else b""
    ok("A ... start script: bash, LF only, the launcher path safely quoted (a ' in it), "
       "a plain message when the folder moved",
       script.startswith(b"#!/bin/bash\n") and b"\r" not in script
       and ("L='" + str(launcher).replace("'", "'\\''") + "'").encode() in script
       and b"display alert" in script and b"PETERPIPER_FROM_APP=1" in script)
    if not WIN:
        ok("A ... start script is executable (0755)",
           stat.S_IMODE((app / "Contents" / "MacOS" / "PeterPiper").stat().st_mode) == 0o755)
    ok("A ... it is recognised as the launcher's own app; made again over itself",
       P.is_our_mac_app(app) and P.write_mac_app(apps, launcher, None, "4.0.1") == app
       and P.mac_app_version(app) == "4.0.1")
    foreign = OUT / "Apps2" / "PeterPiper.app"
    mk(foreign / "Contents" / "Info.plist",
       plistlib.dumps({"CFBundleName": "PeterPiper", "CFBundleShortVersionString": "1.2.0"}))
    ok("A ... never over a PeterPiper.app it did not make (an older .dmg app)",
       P.write_mac_app(foreign.parent, launcher, None, "4.0.0") is None
       and P.mac_app_version(foreign) == "1.2.0")
    bash = find_bash()
    if bash:
        r = subprocess.run([bash, "-n", str(app / "Contents" / "MacOS" / "PeterPiper")],
                           capture_output=True, text=True)
        ok("A ... start script passes bash -n", r.returncode == 0, r.stderr[:200])
    # ---- shortcuts
    calls = []
    made = P.make_shortcuts(OUT / "prog" / "PeterPiperV4.0.bat", None, "4.0.0", sysn="win32",
                            writer=lambda lnk, tgt, ico, desc: calls.append((lnk, tgt, desc)) or True)
    ok("A make_shortcuts (Windows, fake writer): PeterPiper.lnk next to the .bat (+ Desktop / "
       "Start menu where Windows has them), all starting the .bat",
       calls and calls[0][0] == OUT / "prog" / "PeterPiper.lnk"
       and all(c[1] == OUT / "prog" / "PeterPiperV4.0.bat" and c[0].name == "PeterPiper.lnk"
               for c in calls) and len(made) == len(calls) and "4.0.0" in calls[0][2],
       str([str(c[0]) for c in calls]))
    mhome = OUT / "mac user"
    mkdirs(mhome / "Desktop")
    made = P.make_shortcuts(launcher, icns, "4.0.0", sysn="darwin", home=mhome)
    want_app = mhome / "Applications" / "PeterPiper.app"
    sym_ok = (mhome / "Desktop" / "PeterPiper").is_symlink()
    ok("A make_shortcuts (Mac): ~/Applications/PeterPiper.app" +
       (" + Desktop alias" if sym_ok or not WIN else " (Desktop alias: no symlink right here)"),
       want_app in made and P.is_our_mac_app(want_app) and (sym_ok or WIN), str(made))
    ok("A make_shortcuts on Linux makes nothing", P.make_shortcuts(launcher, sysn="linux") == [])
    # ---- the Trash (fake home; never the real one)
    th = OUT / "trash home"
    f1, f2 = mk(OUT / "junk" / "old.txt", "1"), mk(OUT / "junk2" / "old.txt", "2")
    r1 = P.move_to_trash(f1, "linux", th, native=lambda p: None)
    r2 = P.move_to_trash(f2, "linux", th, native=lambda p: None)
    tr = th / ".local" / "share" / "Trash" / "files"
    ok("A move_to_trash: into the Trash folder, a second one with the same name kept apart",
       r1 == "" and r2 == "" and not f1.exists() and (tr / "old.txt").read_text() == "1"
       and (tr / "old.txt 2").read_text() == "2")
    f3 = mk(OUT / "junk3" / "x.txt")
    r3 = P.move_to_trash(f3, "darwin", th, native=lambda p: (p.unlink(), True)[1])
    ok("A move_to_trash (Mac): macOS' own Move to Trash is used when it works",
       r3 == "" and not f3.exists() and not (th / ".Trash" / "x.txt").exists())
    f4 = mk(OUT / "junk4" / "y.txt")
    r4 = P.move_to_trash(f4, "darwin", th, native=lambda p: None)
    ok("A ... and ~/.Trash when it cannot be used", r4 == "" and (th / ".Trash" / "y.txt").exists())
    ok("A move_to_trash of something already gone: nothing to do",
       P.move_to_trash(OUT / "nothing here", "linux", th) == "")


# ===================================================================== B
def part_b():
    base = OUT / "absorb mac"
    profile, data = base / "Users" / "you", base / "data"
    apps1, apps2 = base / "Applications", base / "Users" / "you" / "Applications"
    mkdirs(profile, data)
    old = apps1 / "PeterPiper.app"
    mk(old / "Contents" / "Info.plist", plistlib.dumps(
        {"CFBundleName": "PeterPiper", "CFBundleShortVersionString": "1.2.0",
         "CFBundleIdentifier": "io.github.example.peterpiper"}))
    mk(old / "Contents" / "MacOS" / "PeterPiper", "binary")
    P.write_mac_app(apps2, base / "PeterPiperV4.0" / "PeterPiperV4.0.command", None, "4.0.0")
    pl = A.Places(profile=profile, program=None, data=data, app_dirs=[apps1, apps2],
                  running=(4, 0))
    found = A.find(pl)
    ok("B Mac: the older PeterPiper.app (1.2 from a .dmg) is found; the launcher's own app is not",
       len(found) == 1 and found[0].version == (1, 2) and found[0].apps == [old],
       str(found))
    p = A.plan(found[0]) if found else A.Plan()
    ok("B ... absorbing moves the WHOLE .app bundle", p.remove == [old], str(p.remove))
    moved = []
    out = A.absorb(found[0], pl, recycler=lambda i: moved.append(i) or "",
                   checker=lambda i: "") if found else None
    ok("B ... to the (fake) Trash; the launcher's app stays",
       out is not None and moved == [old] and not out.problem
       and (apps2 / "PeterPiper.app").exists(), str(moved))
    ok("B a NEWER PeterPiper.app on the Mac -> nothing offered",
       A.find(A.Places(profile=profile, program=None, data=data, app_dirs=[apps1],
                       running=(1, 1))) == [])
    ok("B mac_app_version: a non-PeterPiper app -> None",
       A.mac_app_version(mk(base / "Other.app" / "Contents" / "Info.plist",
                            plistlib.dumps({"CFBundleName": "Other",
                                            "CFBundleShortVersionString": "2.0"})).parents[1])
       is None)


# ===================================================================== C
def part_c():
    rel = {"assets": [{"name": "PeterPiperV4.0.zip"},
                      {"name": "PeterPiper-4.0.0-macOS-AppleChip.dmg"},
                      {"name": "PeterPiper-4.0.0-macOS-Intel.dmg"}]}
    ok("C a zip install (Windows OR Mac) takes the one zip",
       U.pick_asset(rel, "zip")["name"] == "PeterPiperV4.0.zip")
    ok("C the Mac app takes its .dmg: Apple chip / Intel",
       U.pick_asset(rel, "mac_app", "arm64")["name"].endswith("AppleChip.dmg")
       and U.pick_asset(rel, "mac_app", "x86_64")["name"].endswith("Intel.dmg"))
    ok("C ... a release without a .dmg -> the zip (dmg is optional)",
       U.pick_asset({"assets": [{"name": "PeterPiperV4.0.zip"}]}, "mac_app")["name"]
       == "PeterPiperV4.0.zip")
    f = OUT / "zip only command"
    mk(f / "app" / "peterpiper" / "__init__.py")
    mk(f / "PeterPiperV4.0.command", "#!/bin/bash\n")
    ok("C a folder with only the .command (and app/) is a zip install",
       U.kind_of_install(f) == "zip")
    ok("C the launcher's name per system",
       U.launcher_name("win32") == "PeterPiperV4.0.bat"
       and U.launcher_name("darwin") == "PeterPiperV4.0.command")
    # permissions kept through an update (posix; Windows has none to keep)
    z = OUT / "upd.zip"
    with zipfile.ZipFile(z, "w") as zz:
        for name, mode in (("PeterPiperV4.0/PeterPiperV4.0.command", 0o100755),
                           ("PeterPiperV4.0/app/requirements.txt", 0o100644),
                           ("PeterPiperV4.0/app/peterpiper/__init__.py", 0o100644)):
            zi = zipfile.ZipInfo(name)
            zi.create_system = 3
            zi.external_attr = mode << 16
            zz.writestr(zi, "#!/bin/bash\necho new\n" if name.endswith(".command") else "x\n")
    ok("C zip_mode reads the stored permissions",
       U.zip_mode(zipfile.ZipFile(z).getinfo("PeterPiperV4.0/PeterPiperV4.0.command")) == 0o755)
    inst = OUT / "inst" / "PeterPiperV4.0"
    mk(inst / "app" / "requirements.txt", b"x\n")                # same packages: in place
    mk(inst / "app" / "peterpiper" / "__init__.py", b"y\n")
    mk(inst / "PeterPiperV4.0.command", b"#!/bin/bash\necho old\n")
    if not WIN:
        os.chmod(inst / "PeterPiperV4.0.command", 0o644)       # the zip's 0755 must win
    p = U.plan(z, inst)
    r = U.apply_in_place(z, inst, p)
    good = p["mode"] == "in_place" and "PeterPiperV4.0.command" in r["replaced"]
    if not WIN:
        good = good and stat.S_IMODE((inst / "PeterPiperV4.0.command").stat().st_mode) == 0o755
    ok("C an in-place update replaces the .command" + ("" if WIN else " and keeps it executable"),
       good, str(r))
    mkdirs(OUT / "inst2" / "old")
    dest = U.unpack_new_folder(z, OUT / "inst2" / "old")
    good = (dest / "PeterPiperV4.0.command").is_file()
    if not WIN:
        good = good and os.access(dest / "PeterPiperV4.0.command", os.X_OK)
    ok("C a new-folder update unpacks the .command" + ("" if WIN else " executable"), good)


# ===================================================================== D
def bat_text() -> str:
    return BAT.read_bytes().decode("ascii")


def mini_copy(dest: Path, launcher: Path) -> Path:
    mkdirs(dest / "app")
    shutil.copy2(launcher, dest / launcher.name)
    for f in ("PeterPiper.py", "requirements.txt", "requirements-compatible.txt",
              "install_progress.py"):
        shutil.copy2(REPO / "app" / f, dest / "app" / f)
    shutil.copytree(REPO / "app" / "peterpiper" / "assets",
                    dest / "app" / "peterpiper" / "assets", dirs_exist_ok=True)
    return dest / launcher.name


def run_bat(bat: Path, env_extra: dict, log: str):
    sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PETERPIPER_", "UV_"))}
    env.update({"PATH": sys32, "PETERPIPER_INSTALL_ONLY": "1", "PETERPIPER_NO_SHORTCUTS": "1"})
    env.update(env_extra)
    p = subprocess.run(["cmd.exe", "/d", "/c", "call", str(bat)], env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
    out = (p.stdout + p.stderr).decode("mbcs", "replace")
    (OUT / log).write_text(out, encoding="utf-8")
    return p.returncode, out


def part_d():
    raw = BAT.read_bytes()
    ok("D the .bat keeps CRLF line endings only", raw.count(b"\r\n") == raw.count(b"\n") > 0)
    bat = bat_text()
    ver = re.search(r'set "PPUV_VERSION=([^"]+)"', bat)
    sha = re.search(r'set "PPUV_SHA256=([0-9a-f]+)"', bat)
    ok("D uv is PINNED: an exact version and the 64-hex SHA-256 of its Windows zip",
       ver and re.fullmatch(r"\d+\.\d+\.\d+", ver.group(1)) and sha and len(sha.group(1)) == 64)
    cmd = CMD.read_text(encoding="ascii")
    ok("D the .bat and the .command pin the SAME uv version and Python",
       ver and f'PPUV_VERSION="{ver.group(1)}"' in cmd and 'PPUV_PY="3.11"' in cmd
       and 'set "PPUV_PY=3.11"' in bat)
    ok("D the question, word for word, in both launchers",
       all("PeterPiper needs Python 3.11+. Download it automatically now" in t
           and "(about 40 MB, from the official uv / python-build-standalone releases)?" in t
           and "[Y/n]" in t for t in (bat, cmd)))
    ok("D Windows download: PowerShell Invoke-WebRequest + Get-FileHash SHA256, wrong hash -> "
       "deleted, exit 3",
       "Invoke-WebRequest" in bat and "Get-FileHash -Algorithm SHA256" in bat
       and "Remove-Item -LiteralPath $env:PP_UV_FILE" in bat and "exit 3" in bat)
    ok("D uv adds no registry entry and nothing to PATH; its own folders only",
       "--no-bin --no-registry" in bat and 'UV_PYTHON_INSTALL_DIR=%HOME_DIR%\\python' in bat
       and "UV_NO_CONFIG=1" in bat)
    own = re.findall(r'set "(UV_[A-Z_]+)=', bat)
    ok("D the launcher's own variables never start with UV_ (:uvenv clears those)",
       set(own) <= {"UV_PYTHON_INSTALL_DIR", "UV_PYTHON_BIN_DIR", "UV_CACHE_DIR", "UV_NO_CONFIG",
                    "UV_PYTHON_PREFERENCE"}, str(own))
    loop = next(ln for ln in bat.splitlines() if ln.startswith("for %%P in ("))
    ok("D reuse list starts with 1.2, 1.1, 1.0 (newest first)",
       loop.startswith("for %%P in (.PeterPiperV1.2 .PeterPiperV1.1 .PeterPiperV1.0 "))
    ok("D --selftest: runs the self-test in the window, never asks",
       'if /i "%~1"=="--selftest" set "SELFTEST=1"' in bat and ":selftest" in bat
       and "if defined SELFTEST set \"NOASK=1\"" in bat)
    if not WIN:
        return
    base = OUT / "bat uv & (test)"
    bat_copy = mini_copy(base / "prog", BAT)
    fake = mk(base / "fake uv.zip", os.urandom(4096))
    home = base / "home"
    rc, out = run_bat(bat_copy, {"PETERPIPER_HOME": str(home), "PETERPIPER_USE_UV": "1",
                                 "PETERPIPER_UV_FILE": str(fake)}, "bat_uv_fake.log")
    ok("D real cmd.exe: a fake uv archive -> 'NOT the published uv release', deleted, nothing run",
       rc == 1 and "NOT the published uv release" in out and "deleted and nothing was run" in out
       and not (home / "uv" / "uv.exe").exists()
       and not (home / "uv" / "uv-x86_64-pc-windows-msvc.zip").exists(), f"rc={rc}")
    ok("D ... then the 'install Python yourself' help (python.org)",
       "could not be downloaded automatically" in out and "python.org/downloads/windows" in out)
    ok("D ... the original file is untouched", fake.exists() and fake.stat().st_size == 4096)
    rc, out = run_bat(bat_copy, {"PETERPIPER_HOME": str(base / "home2"), "PETERPIPER_UV": "no"},
                      "bat_uv_no.log")
    ok("D real cmd.exe: no Python, answer 'no' -> the python.org help, nothing downloaded",
       rc == 1 and "Python is not installed" in out and "Getting Python with uv" not in out
       and not (base / "home2" / "uv").exists(), f"rc={rc}")
    rc, out = run_bat(bat_copy, {"PETERPIPER_HOME": str(base / "home3")}, "bat_uv_noask.log")
    ok("D install-only (nobody to answer): no question, no download",
       rc == 1 and "Download it automatically now" not in out
       and "Getting Python with uv" not in out, f"rc={rc}")
    real = REPO / "_out" / "uvreal"
    if (real / "uv" / "uv.exe").exists() and (real / "python").is_dir():
        d = OUT / "uv found & (x)"
        mkdirs(d / "uv")
        shutil.copy2(real / "uv" / "uv.exe", d / "uv" / "uv.exe")
        shutil.copytree(real / "python", d / "python")
        vers = sorted(p.name.split("-")[1] for p in (d / "python").glob("cpython-*.*.*-*"))
        mm = ".".join(vers[0].split(".")[:2]) if vers else "3.11"
        b = bat_text()
        r = b[b.index("\r\n:uvenv\r\n") + 2:b.index("\r\nrem ---- 4.0 helper: no suitable Python")]
        t = b[b.index("\r\n:trypy\r\n") + 2:b.index("\r\nrem ---- helper: pip install")]
        h = "\r\n".join(["@echo off", "setlocal DisableDelayedExpansion",
                         f'set "HOME_DIR={d}"', 'set "UVEXE=%HOME_DIR%\\uv\\uv.exe"',
                         f'set "PPUV_PY={mm}"', 'set "PY="', "call :uvfind",
                         "if defined PY call %PY% -c \"print('FOUND')\"",
                         'echo "PPUV_PY=%PPUV_PY%"', "exit /b 0", ""]) + "\r\n" + r + "\r\n" + t
        hb = OUT / "uvfind.bat"
        hb.write_bytes(h.encode("mbcs"))
        p = subprocess.run(["cmd.exe", "/d", "/c", "call", str(hb)], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=120)
        o = (p.stdout + p.stderr).decode("mbcs", "replace")
        ok(f"D (real uv from the manual run) :uvfind finds uv's Python {mm} in a folder with "
           "'&' and brackets; its own settings survive", "FOUND" in o
           and f'"PPUV_PY={mm}"' in o, o[-300:])
    else:
        print("SKIP D real uv (_out/uvreal is not there: no manual uv run on this computer)")


# ===================================================================== E
def find_bash():
    if not WIN:
        return shutil.which("bash")
    for c in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(c):
            return c
    w = shutil.which("bash")
    return w if w and "system32" not in w.lower() else None


def posix(p) -> str:
    return str(p).replace("\\", "/")


def run_bash(bash, script: str, env_extra: dict, log: str):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PETERPIPER_", "UV_"))}
    env.update(env_extra)
    p = subprocess.run([bash, "-c", script], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, timeout=300)
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    (OUT / log).write_text(out, encoding="utf-8")
    return p.returncode, out


def part_e():
    raw = CMD.read_bytes()
    ok("E the .command: #!/bin/bash, LF line endings only", raw.startswith(b"#!/bin/bash\n")
       and b"\r" not in raw)
    try:
        mode = subprocess.run(["git", "-C", str(REPO), "ls-files", "-s", CMD.name],
                              capture_output=True, text=True).stdout.split(" ")[0]
    except OSError:
        mode = ""
    ok("E ... executable in git (100755)", mode == "100755", mode)
    attrs = (REPO / ".gitattributes").read_text(encoding="utf-8")
    ok("E ... .gitattributes keeps it LF on every checkout", "*.command text eol=lf" in attrs)
    code = "\n".join(ln for ln in raw.decode("ascii").splitlines() if not ln.lstrip().startswith("#"))
    bad = [p for p in (r"declare -A", r"\bmapfile\b", r"\breadarray\b", r"\$\{[A-Za-z_]+,,",
                       r"\$\{[A-Za-z_]+\^\^", r"\|&", r"&>>", r"\bcoproc\b", r"\bglobstar\b")
           if re.search(p, code)]
    ok("E ... no bash-4-only features (macOS ships bash 3.2)", not bad, str(bad))
    ok("E ... Mac parts: curl https-only, shasum -a 256, ~/.PeterPiperV4.0/venv, quarantine "
       "removed after a start, ~/Applications app via platforms.py, Apple's python3 never used",
       "--proto '=https'" in code and "shasum -a 256" in code and 'HOME_DIR="$HOME/.$PP_NAME"'
       in code and "xattr -dr com.apple.quarantine" in code and "platforms.py\" shortcuts" in code
       and "/usr/bin/*) ;;" in code)
    bash = find_bash()
    if not bash:
        print("SKIP E bash runs (no bash on this computer)")
        return
    r = subprocess.run([bash, "-n", str(CMD)], capture_output=True, text=True)
    ok("E bash -n: no syntax error", r.returncode == 0, r.stderr[:300])
    src = f'PETERPIPER_SOURCE_ONLY=1 source "{posix(CMD)}"; '
    f = mk(OUT / "sha test.bin", b"PeterPiper" * 1000)
    good = hashlib.sha256(f.read_bytes()).hexdigest()
    rc, out = run_bash(bash, src + f'pp_verify_sha256 "{posix(f)}" {good}; echo A=$?; '
                       f'pp_verify_sha256 "{posix(f)}" {good.upper()}; echo B=$?; '
                       f'pp_verify_sha256 "{posix(f)}" {"0" * 64}; echo C=$?; '
                       f'pp_verify_sha256 "{posix(OUT / "missing")}" {good}; echo D=$?',
                       {}, "cmd_sha.log")
    ok("E SHA-256 check: right -> ok, UPPER case -> ok, wrong -> refused, missing file -> refused",
       "A=0" in out and "B=0" in out and "C=1" in out and "D=1" in out, out[-200:])
    fb = OUT / "fakebin"
    mk(fb / "old3.9", '#!/bin/bash\n[ "$1" = --version ] && { echo "Python 3.9.6"; exit 0; }\nexit 1\n')
    mk(fb / "good3.12", '#!/bin/bash\n[ "$1" = --version ] && { echo "Python 3.12.4"; exit 0; }\n'
       'exit 0\n')
    for n in ("old3.9", "good3.12"):
        os.chmod(fb / n, 0o755)
    rc, out = run_bash(bash, src + f'PY=; ANYPY=; pp_trypy "{posix(fb / "old3.9")}"; '
                       'echo "PY=[$PY] ANY=[$ANYPY]"; '
                       f'pp_trypy "{posix(fb / "good3.12")}"; echo "PY2=[$PY]"', {}, "cmd_trypy.log")
    ok("E Python probe: 3.9 is noted but not used; a 64-bit 3.12 is used",
       f"PY=[] ANY=[{posix(fb / 'old3.9')}]" in out and f"PY2=[{posix(fb / 'good3.12')}]" in out,
       out[-300:])
    hd = OUT / "cmd uv home"
    fake = mk(OUT / "fake uv.tar.gz", os.urandom(2048))
    rc, out = run_bash(bash, src + f'HOME_DIR="{posix(hd)}"; UVEXE="$HOME_DIR/uv/uv"; PY=; '
                       'pp_uv_get; echo RC=$?',
                       {"PETERPIPER_UV_FILE": posix(fake)}, "cmd_uvfake.log")
    ok("E a fake uv archive -> refused (SHA-256 differs), deleted, uv not run (code 3)",
       "RC=3" in out and "NOT the published uv release" in out and "nothing was run" in out
       and not list((hd / "uv").glob("*.tar.gz")) and not (hd / "uv" / "uv").exists(), out[-300:])
    # whole runs (PETERPIPER_ANY_SYSTEM lets the Mac launcher's logic run here)
    if sys.platform != "darwin":
        rc, out = run_bash(bash, f'bash "{posix(CMD)}"', {"PETERPIPER_HOME": posix(OUT / "h0")},
                           "cmd_notmac.log")
        ok("E not a Mac -> 'is for macOS ... double-click the .bat', exit 1",
           rc == 1 and "is for macOS" in out and "PeterPiperV4.0.bat" in out, f"rc={rc}")
    lone = OUT / "cmd lone"
    mkdirs(lone)
    shutil.copy2(CMD, lone / CMD.name)
    any_sys = {"PETERPIPER_ANY_SYSTEM": "1", "PETERPIPER_INSTALL_ONLY": "1",
               "PETERPIPER_NO_SHORTCUTS": "1"}
    rc, out = run_bash(bash, f'bash "{posix(lone / CMD.name)}"',
                       dict(any_sys, PETERPIPER_HOME=posix(OUT / "h1")), "cmd_lone.log")
    ok("E the .command alone (not unpacked) -> how to unpack, exit 1",
       rc == 1 and "cannot start: the folder 'app'" in out, f"rc={rc}")
    copy = mini_copy(OUT / "cmd copy & (x)", CMD)
    nopath = "/usr/bin:/bin"
    rc, out = run_bash(bash, f'PATH={nopath}; bash "{posix(copy)}"',
                       dict(any_sys, PETERPIPER_HOME=posix(OUT / "h2"), PETERPIPER_UV="no"),
                       "cmd_nopython.log")
    ok("E no Python + 'no' -> python.org help (macOS link), nothing downloaded, exit 1",
       rc == 1 and "first-time setup" in out and "python.org/downloads/macos" in out
       and "Getting Python with uv" not in out and not (OUT / "h2" / "uv").exists(), f"rc={rc}")
    rc, out = run_bash(bash, f'PATH={nopath}; bash "{posix(copy)}"',
                       dict(any_sys, PETERPIPER_HOME=posix(OUT / "h3")), "cmd_noask.log")
    ok("E install-only without an answer: no question, no download",
       rc == 1 and "Download it automatically now" not in out
       and "Getting Python with uv" not in out, f"rc={rc}")
    rc, out = run_bash(bash, f'PATH={nopath}; bash "{posix(copy)}"',
                       dict(any_sys, PETERPIPER_HOME=posix(OUT / "h4"), PETERPIPER_USE_UV="1",
                            PETERPIPER_UV_FILE=posix(fake)), "cmd_uvrun.log")
    ok("E whole run, uv with a fake archive -> refused, then 'install Python yourself', exit 1",
       rc == 1 and "NOT the published uv release" in out
       and "could not be downloaded automatically" in out, f"rc={rc}")


# ===================================================================== F
def part_f():
    spec = importlib.util.spec_from_file_location("build_zip", REPO / "build" / "build_zip.py")
    bz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bz)
    tracked = bz.git_tracked() or set()
    if "PeterPiperV4.0.command" not in tracked or "app/peterpiper/platforms.py" not in tracked:
        print("SKIP F (the launch files are not committed / added to git yet)")
        return
    z = bz.build(OUT / "zip", force=True)
    with zipfile.ZipFile(z) as zz:
        names = zz.namelist()
        ci = zz.getinfo("PeterPiperV4.0/PeterPiperV4.0.command")
        cmd, bat = zz.read(ci), zz.read("PeterPiperV4.0/PeterPiperV4.0.bat")
    ok("F one zip, both launchers inside", "PeterPiperV4.0/PeterPiperV4.0.bat" in names
       and "PeterPiperV4.0/PeterPiperV4.0.command" in names, z.name)
    ok("F the .command: 0755 (unix) in the zip entry, LF only; the .bat CRLF",
       ci.create_system == 3 and (ci.external_attr >> 16) & 0o777 == 0o755 and b"\r" not in cmd
       and bat.count(b"\r\n") == bat.count(b"\n"), oct(ci.external_attr >> 16))
    ok("F app/, platforms.py, the install helper and READ ME are in it",
       all(f"PeterPiperV4.0/{n}" in names for n in
           ("app/PeterPiper.py", "app/peterpiper/platforms.py", "app/install_progress.py",
            "READ ME.txt", "app/requirements.txt")))
    bad = [n for n in names if any(part in ("_out", "_home", "_work", "release", "dev_tests",
                                            "logs", "lab_paths.json", "out")
                                   for part in n.split("/"))]
    ok("F nothing from _out / _home / _work / release / dev_tests / logs / lab_paths.json",
       not bad, str(bad[:5]))
    try:
        bz.check_command([n for n in bz.files_to_ship() if not n.endswith(".command")])
        stopped = False
    except SystemExit:
        stopped = True
    ok("F a missing .command stops the build", stopped)


# ===================================================================== G
def part_g():
    own = ["absorb.py", "updater.py", "safety.py", "syscheck.py", "selftest.py",
           "gui/absorbdlg.py", "gui/syscheckdlg.py", "gui/updatedlg.py"]
    hits = []
    for rel in own:
        text = (REPO / "app" / "peterpiper" / rel).read_text(encoding="utf-8")
        for i, ln in enumerate(text.splitlines(), 1):
            if ln.lstrip().startswith("#"):
                continue
            if re.search(r"sys\.platform\s*[=!]=|os\.name\s*[=!]=|os\.startfile|import winreg|"
                         r"\.windll\.", ln):
                hits.append(f"{rel}:{i}")
    ok("G the launch part's files ask platforms.py, not sys.platform / os.name / winreg / "
       "windll themselves", not hits, str(hits))
    text = (REPO / "app" / "peterpiper" / "platforms.py").read_text(encoding="utf-8")
    ok("G platforms.py uses Python's own library only (the launchers run it before any "
       "package is installed)",
       not re.search(r"^\s*(from|import)\s+(PySide6|numpy|peterpiper|\.)", text, re.M))


def main():
    for part in (part_a, part_b, part_c, part_d, part_e, part_f, part_g):
        try:
            part()
        except Exception as exc:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f"{part.__name__} ran without an error", False, repr(exc))
    total = N[0] + len(FAILS)
    print(f"\n{N[0]} / {total} checks passed")
    if FAILS:
        print("  FAILED: " + "; ".join(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
