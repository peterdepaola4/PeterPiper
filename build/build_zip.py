"""
Developer tool (not shipped): build the PeterPiper zip that is sent to lab mates.

    python build/build_zip.py [--out DIR] [--force] [--unzip DIR]

Makes <out>/<APP_NAME>.zip (APP_NAME from app/peterpiper/__init__.py, e.g.
PeterPiperV1.0.zip) from this repository's working tree, with every file under a
top folder "<APP_NAME>/". Only files tracked by git ship: a stray untracked
file or folder (test output, a release folder ...) is skipped and listed, never
shipped. Also left out: .git, dev_tests, build, _home, out, _out, _work, release,
__pycache__ folders, *.pyc files and git's own files (.gitignore,
.gitattributes). The zip is reproducible: files in sorted order, one fixed
timestamp (the time of the current git commit), unix permission bits 0644
(0755 for *.command / *.sh launchers, 0755 for folders).

--unzip DIR extracts the zip into DIR/<APP_NAME>/ (refuses if that folder
already exists) and checks that every extracted file is byte-identical to the
repository file and that nothing is missing or extra.

Never overwrites: an existing zip is only replaced with --force.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "dev_tests", "build", "_home", "out", "_out", "_work", "release",
             "__pycache__"}
SKIP_FILES = {".gitignore", ".gitattributes"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
EXEC_SUFFIXES = {".command", ".sh"}


def app_name() -> str:
    text = (REPO / "app" / "peterpiper" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^APP_NAME\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("APP_NAME not found in app/peterpiper/__init__.py")
    return m.group(1)


def git_tracked():
    """Repository-relative paths git tracks (None if git cannot be asked)."""
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True,
                             check=True).stdout.decode("utf-8")
    except Exception:                                  # noqa: BLE001
        return None
    return {p for p in out.split("\0") if p}


def files_to_ship(report: bool = False) -> list:
    """Repository-relative POSIX paths of the shipped files, sorted: the files on
    disk that git tracks (untracked strays are skipped; listed when report)."""
    tracked = git_tracked()
    out = []
    for root, dirs, files in os.walk(REPO):
        rel_root = Path(root).relative_to(REPO)
        # skip folders by name at any depth (dev_tests etc. only exist at the top)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f in SKIP_FILES or Path(f).suffix.lower() in SKIP_SUFFIXES:
                continue
            rel = (rel_root / f).as_posix()
            if tracked is not None and rel not in tracked:
                if report:
                    print(f"skipped (not in git): {rel}")
                continue
            out.append(rel)
    return sorted(out)


def zip_time() -> tuple:
    """The current git commit's time (local), else 1980-01-01: one fixed stamp."""
    try:
        iso = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%cI"],
                             capture_output=True, text=True, check=True).stdout.strip()
        t = _dt.datetime.fromisoformat(iso)
        return (t.year, t.month, t.day, t.hour, t.minute, t.second - t.second % 2)
    except Exception:
        return (1980, 1, 1, 0, 0, 0)


def _info(name: str, mode: int, when: tuple) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(name, date_time=when)
    zi.create_system = 3                      # unix, so the permission bits are honoured
    zi.external_attr = (mode & 0xFFFF) << 16
    if name.endswith("/"):
        zi.external_attr |= 0x10              # MS-DOS directory flag
    else:
        zi.compress_type = zipfile.ZIP_DEFLATED
    return zi


def build(out_dir: Path, force: bool) -> Path:
    name = app_name()
    files = files_to_ship(report=True)
    bat = REPO / f"{name}.bat"
    if f"{name}.bat" not in files:
        raise SystemExit(f"{name}.bat not found in the repository root")
    data = bat.read_bytes()
    if data.count(b"\r\n") != data.count(b"\n"):
        raise SystemExit(f"{name}.bat must have Windows (CRLF) line endings only")
    if git_tracked() is None:
        print("WARNING  git not available: every file on disk ships (check for strays)")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.zip"
    if target.exists() and not force:
        raise SystemExit(f"{target} already exists (use --force to replace it)")
    when = zip_time()
    tmp = target.with_name(target.name + ".part")
    dirs = sorted({p.rsplit("/", i)[0] for p in files for i in range(1, p.count("/") + 1)})
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(_info(f"{name}/", 0o40755, when), b"")
        for d in dirs:
            z.writestr(_info(f"{name}/{d}/", 0o40755, when), b"")
        for rel in files:
            mode = 0o100755 if Path(rel).suffix in EXEC_SUFFIXES else 0o100644
            z.writestr(_info(f"{name}/{rel}", mode, when), (REPO / rel).read_bytes())
    os.replace(tmp, target)
    total = 0
    with zipfile.ZipFile(target) as z:
        for zi in z.infolist():
            if zi.is_dir():
                continue
            total += zi.file_size
            print(f"  {oct(zi.external_attr >> 16 & 0o777)[2:]:>4s} {zi.file_size:>10,d}  {zi.filename}")
    print(f"{len(files)} files, {total:,d} bytes unpacked; "
          f"{target} = {target.stat().st_size:,d} bytes")
    return target


def unzip_and_verify(zip_path: Path, dest: Path) -> bool:
    name = app_name()
    top = dest / name
    if top.exists():
        raise SystemExit(f"{top} already exists - remove it first (nothing was changed)")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():                # no absolute paths / '..' in our own zip
            if not n.startswith(f"{name}/") or ".." in n.split("/"):
                raise SystemExit(f"unexpected entry {n!r}")
        z.extractall(dest)
    want = files_to_ship()
    got = sorted(p.relative_to(top).as_posix() for p in top.rglob("*") if p.is_file())
    ok = True
    for rel in sorted(set(want) | set(got)):
        if rel not in got:
            ok = False
            print(f"MISSING  {rel}")
        elif rel not in want:
            ok = False
            print(f"EXTRA    {rel}")
        elif (top / rel).read_bytes() != (REPO / rel).read_bytes():
            ok = False
            print(f"DIFFERS  {rel}")
    print(("OK" if ok else "FAILED") +
          f": {len(got)} files in {top} " +
          ("are byte-identical to the repository" if ok else "do not match the repository"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(REPO / "out"), help="folder for the zip")
    ap.add_argument("--force", action="store_true", help="replace an existing zip")
    ap.add_argument("--unzip", metavar="DIR", help="also extract it into DIR and verify")
    a = ap.parse_args()
    target = build(Path(a.out), a.force)
    if a.unzip:
        return 0 if unzip_and_verify(target, Path(a.unzip)) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
