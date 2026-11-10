"""
Developer check (not shipped): build/build_zip.py.

    python dev_tests/test_pack_zip.py

Builds the zip twice into <repo>/out/ziptest (deleted afterwards) and checks:
same bytes both times (reproducible); one top folder <APP_NAME>/; nothing from
.git, dev_tests, build, _home, out, __pycache__, *.pyc, .gitignore; every
shipped file is tracked by git; permission bits 0644 (0755 for folders and
*.command / *.sh); the .bat keeps CRLF endings inside the zip; --unzip gives
byte-identical files; an existing zip is not replaced without --force.
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_zip", REPO / "build" / "build_zip.py")
bz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bz)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""), flush=True)


def main() -> int:
    work = REPO / "out" / "ziptest"
    shutil.rmtree(work, ignore_errors=True)
    name = bz.app_name()
    # V2.4 (L10): untracked stray files / folders are skipped, never shipped or fatal
    stray = [REPO / "app" / "stray_test_folder" / "junk.txt", REPO / "stray_test_file.txt"]
    for q in stray:
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text("not in git", encoding="utf-8")
    try:
        shipped = bz.files_to_ship()
        zs = bz.build(work / "stray", force=False)
        with zipfile.ZipFile(zs) as z:
            zn = z.namelist()
        okz = bz.unzip_and_verify(zs, work / "stray_unz")
    finally:
        for q in stray:
            q.unlink()
        (REPO / "app" / "stray_test_folder").rmdir()
    check("untracked stray file + folder skipped: not listed, not in the zip, unzip verifies (L10)",
          not any("stray_test" in n for n in shipped + zn) and okz)
    z1 = bz.build(work / "a", force=False)
    z2 = bz.build(work / "b", force=False)
    h = [hashlib.sha256(z.read_bytes()).hexdigest() for z in (z1, z2)]
    check("zip name from APP_NAME", z1.name == f"{name}.zip", z1.name)
    check("reproducible (two builds, same sha256)", h[0] == h[1], h[0][:16])

    p = subprocess.run([sys.executable, str(REPO / "build" / "build_zip.py"), "--out",
                        str(work / "a")], capture_output=True, text=True)
    check("existing zip not replaced without --force",
          p.returncode != 0 and "already exists" in (p.stdout + p.stderr)
          and hashlib.sha256(z1.read_bytes()).hexdigest() == h[0])

    with zipfile.ZipFile(z1) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        bat = z.read(f"{name}/{name}.bat")
    check("one top folder", all(n.startswith(f"{name}/") for n in names))
    bad = [n for n in names if any(part in bz.SKIP_DIRS or part in bz.SKIP_FILES
                                   for part in n.split("/")) or n.endswith((".pyc", ".pyo"))]
    check("no excluded files", not bad, str(bad[:5]))
    files = [n for n in names if not n.endswith("/")]
    check("sorted order", files == sorted(files))
    tracked = set(subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True,
                                 text=True, check=True).stdout.splitlines())
    untracked = [n for n in files if n[len(name) + 1:] not in tracked]
    check("every shipped file is tracked by git", not untracked, str(untracked[:5]))
    must = [f"{name}/{name}.bat", f"{name}/READ ME.txt", f"{name}/app/PeterPiper.py",
            f"{name}/app/requirements.txt", f"{name}/app/requirements-compatible.txt",
            f"{name}/app/peterpiper/__init__.py", f"{name}/app/peterpiper/templates/PeterPiper_timecourse.prism",
            f"{name}/app/peterpiper/templates/PeterPiper_look.json"]
    check("key files present", all(m in names for m in must),
          str([m for m in must if m not in names]))
    modes = {}
    for i in infos:
        want = 0o755 if (i.filename.endswith("/") or i.filename.endswith((".command", ".sh"))) else 0o644
        if i.create_system != 3 or (i.external_attr >> 16) & 0o777 != want:
            modes[i.filename] = oct((i.external_attr >> 16) & 0o777)
    check("permission bits 0644 files / 0755 folders and launchers (unix attrs)", not modes,
          str(list(modes.items())[:5]))
    zi = bz._info(f"{name}/x.command", 0o100755, (2026, 1, 1, 0, 0, 0))
    check("a *.command entry would get 0755 in external_attr",
          (zi.external_attr >> 16) & 0o777 == 0o755 and zi.create_system == 3,
          hex(zi.external_attr))
    check(".bat keeps CRLF endings inside the zip",
          bat.count(b"\r\n") == bat.count(b"\n") > 0)

    ok = bz.unzip_and_verify(z1, work / "unz")
    check("--unzip: byte-identical to the repository", ok)
    try:
        bz.unzip_and_verify(z1, work / "unz")
        refused = False
    except SystemExit:
        refused = True
    check("--unzip refuses an existing folder", refused)

    shutil.rmtree(work, ignore_errors=True)
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed" +
          (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
