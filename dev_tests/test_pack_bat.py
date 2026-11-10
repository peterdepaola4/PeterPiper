"""
Developer check (not shipped): runs PeterPiperV1.0.bat for real, non-interactively.

    python dev_tests/test_pack_bat.py            # quick message tests only
    python dev_tests/test_pack_bat.py --install  # + a REAL install (internet, ~600 MB)

Every run sets PETERPIPER_INSTALL_ONLY=1 (the .bat stops before opening the app)
and feeds stdin from NUL, so no 'pause' can block. Nothing is written outside
<repo>/_home (the install, fake user folders, copies of the launcher).

Quick tests (no network): not-extracted message; no Python; unsupported
Python (a fake python.cmd, which also proves a .cmd/.bat shim returns control
to the launcher); reuse of an earlier version's install only when its stamp is
byte-identical (fake USERPROFILE).

--install: (1) fresh install into "<repo>/_home/inst test/venv" (path with a
space) -> pip freeze must equal app/requirements.txt exactly, the stamp and
installed_versions.txt must exist; (2) second run takes the fast path;
(3) a copy of the launcher in a folder named "pack test & (copy)" whose
requirements.txt contains an impossible pin -> the exact install fails and the
compatible fallback runs (reuses the installed packages, so no new download);
(4) the copy's second run takes the fast path; (5) both lists impossible and
a long install path -> the 'path is too long' message; (6) the same with a
short path -> the internet / firewall advice. The test venv is then deleted
(unless --keep).

--home DIR puts the test install in DIR (default <repo>/_home). Its path must
be short (Windows limits paths to 260 characters unless long paths are turned
on, and the longest PySide6 file needs about 170): from a deep folder, point a
junction with a short path at a folder inside _home and pass that.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BAT = REPO / "PeterPiperV1.0.bat"
HOME = REPO / "_home"
LOGS = REPO / "dev_tests" / "logs"
SYS32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""), flush=True)


# the logo is typed as UTF-8 bytes; run_bat decodes the output as mbcs
BLOCK = "\u2588".encode("utf-8").decode("mbcs", errors="replace")


def run_bat(bat: Path, env_extra: dict, log_name: str, drop=(), timeout=1800):
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_extra)
    env["PETERPIPER_INSTALL_ONLY"] = "1"
    env["PETERPIPER_NO_SHORTCUTS"] = "1"          # never touch the real Desktop / Start menu
    t0 = time.time()
    p = subprocess.run(["cmd.exe", "/d", "/c", "call", str(bat)], env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    dt = time.time() - t0
    out = (p.stdout + p.stderr).decode("mbcs", errors="replace")
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / log_name).write_text(f"exit code {p.returncode}, {dt:.1f} s\n{out}", encoding="utf-8")
    return p.returncode, out, dt


def norm(n):
    return re.sub(r"[-_.]+", "-", n).lower()


def pins(path: Path) -> dict:
    d = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if "==" in ln:
            n, v = ln.split("==", 1)
            d[norm(n)] = v.strip()
    return d


def mini_copy(dest: Path, req_text: bytes | None = None, compat_text: bytes | None = None) -> Path:
    """The launcher plus the few app files it looks at, in <dest>."""
    (dest / "app").mkdir(parents=True, exist_ok=True)
    shutil.copy2(BAT, dest / BAT.name)
    for f in ("PeterPiper.py", "requirements.txt", "requirements-compatible.txt"):
        shutil.copy2(REPO / "app" / f, dest / "app" / f)
    shutil.copytree(REPO / "app" / "peterpiper" / "assets", dest / "app" / "peterpiper" / "assets",
                    dirs_exist_ok=True)                # the logo the launcher shows
    if req_text is not None:
        (dest / "app" / "requirements.txt").write_bytes(req_text)
    if compat_text is not None:
        (dest / "app" / "requirements-compatible.txt").write_bytes(compat_text)
    return dest / BAT.name


def quick_tests():
    base = HOME / "bat quick & (tests)"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)

    # 1. not extracted: the .bat alone, without its app folder
    lone = base / "lone"
    lone.mkdir()
    shutil.copy2(BAT, lone / BAT.name)
    rc, out, _ = run_bat(lone / BAT.name, {"PETERPIPER_HOME": str(base / "h1")}, "bat_notextracted.log")
    check("not extracted -> message, exit 1",
          rc == 1 and "cannot run from inside the zip" in out, f"rc={rc}")

    # 2. no Python anywhere on PATH
    bat = mini_copy(base / "copy")
    rc, out, _ = run_bat(bat, {"PETERPIPER_HOME": str(base / "h2"), "PATH": SYS32}, "bat_nopython.log")
    check("no Python -> install instructions, exit 1",
          rc == 1 and "Python is not installed" in out and "first-time setup" in out, f"rc={rc}")
    check("no Python -> no venv created", not (base / "h2" / "venv").exists())

    # 3. only an unsupported Python (a .cmd shim reporting 3.9)
    fake = base / "fakebin"
    fake.mkdir()
    (fake / "python.cmd").write_text(
        "@echo off\r\nif \"%~1\"==\"--version\" (echo Python 3.9.13& exit /b 0)\r\nexit /b 1\r\n",
        encoding="ascii")
    rc, out, _ = run_bat(bat, {"PETERPIPER_HOME": str(base / "h3"), "PATH": f"{fake};{SYS32}"},
                         "bat_badpython.log")
    check("Python 3.9 shim -> 'cannot run' message naming 3.9, exit 1",
          rc == 1 and "cannot run PeterPiperV1.0" in out and "3.9.13" in out, f"rc={rc}")
    check("... and says 3.15+ and 32-bit Python are not supported (V2.4, L3)",
          "3.15 and newer are not supported" in out and "32-bit Python does not work" in out)
    txt = BAT.read_text(encoding="utf-8")
    chk = txt[txt.index("[3/3] Checking"):]
    check("failed import check -> its own message, not the download one (L3)",
          chk.splitlines()[2].strip() == "if errorlevel 1 goto checkfail"
          and "check that they load FAILED" in txt)
    check("compatible-versions note says how to retry the exact versions (L3)",
          "To try the exact tested versions again later" in txt)

    # 4. reuse of an earlier version's install (fake user folder, no PETERPIPER_HOME)
    prof = base / "profile"
    req = (REPO / "app" / "requirements.txt").read_bytes()
    for ver, stamp in ((".PD4navV2.2", req), (".PD4navV2.1", req)):
        v = prof / ver / "venv"
        # a real (empty) private Python: the launcher checks that it still starts
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(v)], check=True)
        (v / "installed_requirements.txt").write_bytes(stamp)
    env = {"USERPROFILE": str(prof), "PATH": SYS32}
    rc, out, _ = run_bat(bat, env, "bat_reuse_v22.log", drop=("PETERPIPER_HOME",))
    check("identical V2.2 install is reused (fast path)",
          rc == 0 and "Already installed" in out and ".PD4navV2.2\\venv" in out, f"rc={rc}")
    # its base Python uninstalled (pyvenv.cfg points nowhere): not reused
    cfg = prof / ".PD4navV2.2" / "venv" / "pyvenv.cfg"
    good_cfg = cfg.read_text(encoding="utf-8")
    cfg.write_text(re.sub(r"(?m)^home\s*=.*$", r"home = C:\\no such python", good_cfg),
                   encoding="utf-8")
    rc, out, _ = run_bat(bat, env, "bat_reuse_v22_broken.log", drop=("PETERPIPER_HOME",))
    check("V2.2 install whose Python no longer starts is not reused (V2.1's is)",
          rc == 0 and ".PD4navV2.1\\venv" in out, f"rc={rc}")
    # this version's own install, up to date but its Python gone: set up again
    # (here: no Python on PATH -> the install instructions), never 'Already installed'
    own = base / "h_broken"
    shutil.copytree(prof / ".PD4navV2.2" / "venv", own / "venv")
    rc, out, _ = run_bat(bat, {"PETERPIPER_HOME": str(own), "PATH": SYS32},
                         "bat_broken_own.log")
    check("own install whose Python no longer starts -> set up again, not opened",
          rc == 1 and "first-time setup" in out and "Already installed" not in out, f"rc={rc}")
    cfg.write_text(good_cfg, encoding="utf-8")
    (prof / ".PD4navV2.2" / "venv" / "installed_requirements.txt").write_bytes(req + b"x\n")
    rc, out, _ = run_bat(bat, env, "bat_reuse_v21.log", drop=("PETERPIPER_HOME",))
    check("V2.2 stamp differs -> identical V2.1 install is reused",
          rc == 0 and ".PD4navV2.1\\venv" in out, f"rc={rc}")
    (prof / ".PD4navV2.1" / "venv" / "installed_requirements.txt").write_bytes(b"numpy>=1.24\n")
    rc, out, _ = run_bat(bat, env, "bat_reuse_none.log", drop=("PETERPIPER_HOME",))
    check("no identical earlier install -> not reused, goes to setup",
          rc == 1 and "first-time setup" in out and "Python is not installed" in out, f"rc={rc}")
    check("fake user folder: .PeterPiperV1.0 created there, not in the real profile",
          (prof / ".PeterPiperV1.0").is_dir())
    head = out[:out.index("first-time setup")].splitlines()
    check("first-time setup starts with the PeterPiper logo (its block-character lines, not "
          "the plain heading)", sum(1 for s in head if len(s.strip()) > 30) >= 8
          and "  PeterPiper 1.0" not in head, f"{len(head)} lines before the setup text")
    shutil.rmtree(base, ignore_errors=True)


def freeze(py: Path) -> dict:
    out = subprocess.run([str(py), "-m", "pip", "freeze", "--disable-pip-version-check"],
                         capture_output=True, text=True, check=True).stdout
    return {norm(l.split("==")[0]): l.split("==")[1].strip() for l in out.splitlines() if "==" in l}


def install_tests(keep: bool, home_base: Path):
    # The venv path must stay short: Windows (without "long paths" turned on)
    # limits a path to 260 characters and the longest PySide6 file needs ~170.
    home = home_base / "inst test"
    venv = home / "venv"
    if venv.exists():
        shutil.rmtree(venv)
    env = {"PETERPIPER_HOME": str(home)}

    rc, out, dt = run_bat(BAT, env, "bat_install_run1.log")
    check(f"run 1: fresh install finished ({dt:.0f} s)",
          rc == 0 and "Setup finished" in out and "all packages OK" in out, f"rc={rc}")
    check("run 1: exact list used, no fallback",
          "Trying the compatible" not in out and "COMPATIBLE" not in out)
    py = venv / "Scripts" / "python.exe"
    want = pins(REPO / "app" / "requirements.txt")
    got = freeze(py) if py.exists() else {}
    diff = {k: (got.get(k), want.get(k)) for k in set(got) | set(want) if got.get(k) != want.get(k)}
    check(f"venv pip freeze == requirements.txt ({len(got)} packages)", not diff, str(diff)[:300])
    stamp = venv / "installed_requirements.txt"
    check("stamp is a byte copy of requirements.txt",
          stamp.exists() and stamp.read_bytes() == (REPO / "app" / "requirements.txt").read_bytes())
    iv = venv / "installed_versions.txt"
    ivt = iv.read_text(encoding="mbcs", errors="replace") if iv.exists() else ""
    check("installed_versions.txt written (header + freeze)",
          "# package list: requirements.txt" in ivt and "# Python 3." in ivt and "numpy==" in ivt)
    ver = subprocess.run([str(py), "-c", "import sys;print(sys.version.split()[0])"],
                         capture_output=True, text=True).stdout.strip() if py.exists() else "?"
    print(f"      venv Python {ver}; {len(ivt.splitlines())} lines in installed_versions.txt")

    rc, out, dt = run_bat(BAT, env, "bat_install_run2.log")
    check(f"run 2: fast path ({dt:.1f} s)",
          rc == 0 and "Already installed" in out and "first-time setup" not in out and dt < 20,
          f"rc={rc}")

    # 3. fallback: impossible pin in a copy -> exact install fails -> compatible list
    req = (REPO / "app" / "requirements.txt").read_bytes()
    bad = req + b"numpy==0.0.1\n"
    cdir = HOME / "pack test & (copy)"
    shutil.rmtree(cdir, ignore_errors=True)
    bat = mini_copy(cdir, bad)
    rc, out, dt = run_bat(bat, env, "bat_install_run3_fallback.log")
    check(f"run 3: exact pins fail -> compatible fallback succeeds ({dt:.0f} s)",
          rc == 0 and "Trying the compatible versions instead" in out
          and "COMPATIBLE package versions" in out and "all packages OK" in out, f"rc={rc}")
    ivt = iv.read_text(encoding="mbcs", errors="replace") if iv.exists() else ""
    check("run 3: installed_versions.txt says compatible list",
          "# package list: requirements-compatible.txt" in ivt)
    check("run 3: stamp = the copy's requirements.txt (no retry on every launch)",
          stamp.read_bytes() == bad)
    rc, out, dt = run_bat(bat, env, "bat_install_run4.log")
    check(f"run 4: fast path after a fallback install ({dt:.1f} s)",
          rc == 0 and "Already installed" in out, f"rc={rc}")
    shutil.rmtree(cdir, ignore_errors=True)

    # 5. both lists impossible -> pip fails; the message names the cause:
    #    a too-long install path, or (short path) the generic download advice
    imp = b"numpy==0.0.1\n"
    cdir = HOME / "pack test & (fail)"
    shutil.rmtree(cdir, ignore_errors=True)
    bat = mini_copy(cdir, imp, imp)
    longhome = HOME / ("long path test " + "x" * max(0, 90 - len(str(HOME))))
    rc, out, dt = run_bat(bat, {"PETERPIPER_HOME": str(longhome)}, "bat_fail_longpath.log")
    check(f"run 5: pip fails in a long install path -> 'path is too long' message (rc={rc})",
          rc == 1 and "path is too long" in out and "Usually: no internet" not in out,
          f"venv path {len(str(longhome / 'venv'))} chars")
    shorthome = home_base / "f"
    rc, out, dt = run_bat(bat, {"PETERPIPER_HOME": str(shorthome)}, "bat_fail_shortpath.log")
    check(f"run 6: pip fails in a short install path -> internet / firewall advice (rc={rc})",
          rc == 1 and "Usually: no internet" in out and "path is too long" not in out,
          f"venv path {len(str(shorthome / 'venv'))} chars")
    for d in (cdir, longhome, shorthome):
        shutil.rmtree(d, ignore_errors=True)

    if not keep:
        shutil.rmtree(home, ignore_errors=True)
        check("test venv deleted", not venv.exists())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--home", default=str(HOME),
                    help="folder for the test install (short path; may be a junction to _home)")
    a = ap.parse_args()
    if os.name != "nt":
        print("Windows only")
        return 1
    crlf = BAT.read_bytes()
    check("PeterPiperV1.0.bat has CRLF line endings only",
          crlf.count(b"\r\n") == crlf.count(b"\n") > 0)
    quick_tests()
    if a.install:
        install_tests(a.keep, Path(a.home))
    bad = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} passed" + (f"; FAILED: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
