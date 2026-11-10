"""
Developer check (not shipped): are the pins in app/requirements.txt the tested
environment, and can pip resolve them to wheels on every supported OS / Python?

    python dev_tests/test_pack_pins.py [--freeze-python PATH] [--quick] [--log FILE]

1. Compares app/requirements.txt with 'pip freeze' of the tested environment
   (default: the lab's test environment, from dev_tests/lab_paths.json): every package
   must be pinned with '==' to exactly the installed version, nothing missing,
   nothing extra.
2. For each (platform, Python) cell of the matrix runs
       pip install --dry-run --ignore-installed --only-binary=:all:
                   --platform ... --python-version ... --target <tmp> -r <file>
   Nothing is installed (dry run; the temp folder is deleted). Needs internet.
   app/requirements-compatible.txt is checked the same way (the fallback).

pip quirk: --platform tags are NOT expanded for manylinux_2_X, so the Linux
cells list every glibc tag a typical distribution accepts. macOS tags are
expanded by pip to every older macOS version automatically.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PINNED = REPO / "app" / "requirements.txt"
COMPAT = REPO / "app" / "requirements-compatible.txt"
TESTED_PY = labdata.T("t16")                     # the lab's test environment
if not Path(TESTED_PY).exists():
    TESTED_PY = sys.executable                   # elsewhere: the Python running this


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _linux(max_minor: int) -> list:
    tags = [f"manylinux_2_{m}_x86_64" for m in range(max_minor, 16, -1)]
    return tags + ["manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]


# name -> list of --platform tags
PLATFORMS = {
    "Windows 64-bit (win_amd64)": ["win_amd64"],
    "Windows on ARM (win_arm64)": ["win_arm64"],
    "macOS 12 Apple silicon": ["macosx_12_0_arm64"],
    "macOS 13 Apple silicon": ["macosx_13_0_arm64"],
    "macOS 14+ Apple silicon": ["macosx_14_0_arm64"],
    "macOS 13 Intel": ["macosx_13_0_x86_64"],
    "macOS 14 Intel": ["macosx_14_0_x86_64"],
    "macOS 15+ Intel": ["macosx_15_0_x86_64"],
    "Linux glibc 2.17 (manylinux2014)": _linux(17),
    "Linux glibc 2.28 (RHEL 8, Debian 10)": _linux(28),
    "Linux glibc 2.31 (Ubuntu 20.04)": _linux(31),
    "Linux glibc 2.34 (RHEL 9)": _linux(34),
    "Linux glibc 2.35 (Ubuntu 22.04)": _linux(35),
    "Linux glibc 2.39 (Ubuntu 24.04)": _linux(39),
}
PYTHONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]


def pins(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
        if not m:
            raise SystemExit(f"FAIL  not an exact pin in {path.name}: {line!r}")
        out[_norm(m.group(1))] = m.group(2)
    return out


def check_freeze(python: str) -> bool:
    frozen = subprocess.run([python, "-m", "pip", "freeze"], capture_output=True,
                            text=True, check=True).stdout
    env = {}
    for line in frozen.splitlines():
        if "==" in line:
            n, v = line.split("==", 1)
            env[_norm(n)] = v.strip()
    req = pins(PINNED)
    ok = True
    for n in sorted(set(env) | set(req)):
        if env.get(n) != req.get(n):
            ok = False
            print(f"FAIL  {n}: tested env {env.get(n)!r} vs requirements.txt {req.get(n)!r}")
    print(("PASS" if ok else "FAIL") +
          f"  requirements.txt == pip freeze of the tested env ({len(req)} packages)")
    return ok


def dry_run(python: str, req: Path, tags: list, pyver: str) -> tuple:
    tmp = Path(tempfile.mkdtemp(prefix="pd4pins_"))
    try:
        cmd = [python, "-m", "pip", "install", "--dry-run", "--ignore-installed",
               "--only-binary=:all:", "--python-version", pyver, "--target", str(tmp / "t"),
               "--disable-pip-version-check", "--no-input", "--quiet",
               "--report", str(tmp / "r.json"), "--index-url", "https://pypi.org/simple",
               "-r", str(req)]
        for t in tags:
            cmd += ["--platform", t]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            err = [ln for ln in (p.stderr + p.stdout).splitlines() if ln.strip()]
            why = next((ln for ln in err if "satisfies the requirement" in ln),
                       next((ln for ln in err if "ERROR" in ln and "Ignored" not in ln),
                            err[-1] if err else "?"))
            why = re.sub(r"\(from versions: (.{0,60}).*", r"(from versions: \1...)", why)
            return False, why.replace("ERROR: Could not find a version that satisfies the "
                                      "requirement", "no wheel for").strip()[:170]
        rep = json.loads((tmp / "r.json").read_text(encoding="utf-8"))
        got = {_norm(i["metadata"]["name"]): i["metadata"]["version"] for i in rep["install"]}
        wheels = [i["download_info"]["url"].rsplit("/", 1)[-1] for i in rep["install"]]
        if not all(w.endswith(".whl") for w in wheels):
            return False, "non-wheel file resolved"
        return True, got
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def matrix(python: str, req: Path, pythons: list, platforms: dict) -> dict:
    want = pins(req) if req == PINNED else None
    res = {}
    for pname, tags in platforms.items():
        for pv in pythons:
            t0 = time.time()
            ok, info = dry_run(python, req, tags, pv)
            if ok and want is not None:
                extra = {k: v for k, v in info.items() if want.get(k) != v}
                if extra or set(want) - set(info):
                    ok, info = False, f"resolved set differs from pins: {extra}"
            res[(pname, pv)] = ok
            detail = (f"{len(info)} wheels" if ok else info)
            print(f"{'PASS' if ok else 'FAIL'}  {req.name:28s} {pname:38s} py{pv}: "
                  f"{detail}  ({time.time() - t0:.0f} s)", flush=True)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-python", default=TESTED_PY)
    ap.add_argument("--quick", action="store_true", help="win_amd64 py3.11 only")
    ap.add_argument("--which", choices=("both", "pinned", "compat"), default="both")
    a = ap.parse_args()
    ok = check_freeze(a.freeze_python)
    plats = {k: v for k, v in PLATFORMS.items() if "win_amd64" in v} if a.quick else PLATFORMS
    pys = ["3.11"] if a.quick else PYTHONS
    res = matrix(a.freeze_python, PINNED, pys, plats) if a.which != "compat" else {}
    if COMPAT.exists() and a.which != "pinned":
        resc = matrix(a.freeze_python, COMPAT, pys, plats)
    else:
        resc = {}
    print("\nSUMMARY (pinned / compatible):")
    print(f"{'':38s} " + " ".join(f"{p:>9s}" for p in pys))
    for pname in plats:
        row = []
        for pv in pys:
            a1 = "pin" if res.get((pname, pv)) else "-"
            a2 = "compat" if resc.get((pname, pv)) else ("-" if resc else "")
            row.append(f"{a1 + '/' + a2 if resc else a1:>9s}")
        print(f"{pname:38s} " + " ".join(row))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
