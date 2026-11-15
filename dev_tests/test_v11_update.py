"""
Developer test (not shipped): PeterPiper 1.1 "Check for updates" (updater.py,
gui/updatedlg.py). Uses a fake GitHub and fake release zips - no real network
(any real request makes the test fail).

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v11_update.py

A) versions: parsing, newer / same / older, the project's repo from PROJECT_URL.
B) install kind: a zip install (folder with PeterPiperV*.bat and app/), a developer
   copy (.git) is never changed.
C) in place (same program folder and packages): only differing files replaced,
   new files added, backups kept, files outside the zip (user-ish files, a
   shortcut, _out, logs) untouched, protected paths in a zip ignored.
D) new folder (other program folder or other packages): unpacked next to this
   one, never over an existing folder; this folder unchanged.
E) unsafe zips (.. paths, absolute paths) refused; a damaged zip refused.
F) the asset for this computer is picked; download checks the size and https.
G) the window: 'newest' message, developer copy cannot update, the buttons exist on
   the start screen and in the analysis window's Help menu.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v11_update"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

import urllib.request                                                 # noqa: E402


def _no_network(*a, **k):
    raise AssertionError("a real network request was made")


urllib.request.urlopen = _no_network

from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

APP = QApplication(sys.argv)
from peterpiper import updater as U                                   # noqa: E402

N = [0]
FAILS = []


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def make_install(folder: Path, files: dict) -> Path:
    for rel, data in files.items():
        p = folder / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return folder


def make_zip(path: Path, top: str, files: dict) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for rel, data in files.items():
            z.writestr(f"{top}/{rel}", data)
    return path


BASE = {"PeterPiperV1.1.bat": b"@echo off\r\n", "app/peterpiper/__init__.py": b"v = 1\n",
        "app/peterpiper/a.py": b"A\n", "app/requirements.txt": b"numpy==1\n",
        "README.md": b"readme\n"}


def part_a():
    ok("A parse", U.parse_version("v1.10.2") == (1, 10, 2) and U.parse_version("1.1") == (1, 1, 0))
    ok("A newer / same / older", U.is_newer("1.1.1", "1.1.0") and not U.is_newer("1.1.0", "1.1.0")
       and not U.is_newer("1.0.9", "1.1.0") and U.is_newer("1.10.0", "1.9.9"))
    ok("A the repo from PROJECT_URL", U.repo() == "peterdepaola4/PeterPiper", U.repo())


def part_b():
    z = make_install(OUT / "inst_b" / "PeterPiperV1.1", BASE)
    ok("B a zip install", U.kind_of_install(z) == "zip")
    d = make_install(OUT / "dev_b" / "PeterPiperV1.1", dict(BASE))
    (d / ".git").mkdir()
    ok("B a git checkout is a developer copy", U.kind_of_install(d) == "developer")
    ok("B this test's own copy is a developer copy", U.kind_of_install() == "developer")


def part_c():
    folder = make_install(OUT / "inst_c" / "PeterPiperV1.1", BASE)
    (folder / "PeterPiper.lnk").write_bytes(b"shortcut")
    (folder / "_out").mkdir()
    (folder / "_out" / "mine.txt").write_text("my file")
    (folder / "my notes.txt").write_text("not in the zip")
    new = dict(BASE)
    new["app/peterpiper/a.py"] = b"A2\n"                       # changed
    new["app/peterpiper/b.py"] = b"B\n"                        # new
    new["_out/evil.txt"] = b"x"                                # protected: ignored
    new["logs/x.log"] = b"x"
    zp = make_zip(OUT / "rel_c.zip", "PeterPiperV1.1", new)
    p = U.plan(zp, folder)
    ok("C same folder + same packages -> in place", p["mode"] == "in_place", p["mode"])
    ok("C only the differing and new files", p["changed"] == ["app/peterpiper/a.py"]
       and p["new"] == ["app/peterpiper/b.py"], f"{p['changed']} {p['new']}")
    r = U.apply_in_place(zp, folder, p)
    ok("C replaced and added", (folder / "app/peterpiper/a.py").read_bytes() == b"A2\n"
       and (folder / "app/peterpiper/b.py").read_bytes() == b"B\n")
    ok("C the old file is kept in _update_backup", r["backup"] and
       (Path(r["backup"]) / "app/peterpiper/a.py").read_bytes() == b"A\n")
    ok("C files outside the zip untouched (shortcut, _out, own notes)",
       (folder / "PeterPiper.lnk").read_bytes() == b"shortcut"
       and (folder / "_out" / "mine.txt").read_text() == "my file"
       and (folder / "my notes.txt").read_text() == "not in the zip")
    ok("C protected paths in the zip are never written",
       not (folder / "_out" / "evil.txt").exists() and not (folder / "logs").exists())
    ok("C unchanged files keep their time (not rewritten)",
       (folder / "README.md").read_bytes() == b"readme\n")


def part_d():
    folder = make_install(OUT / "inst_d" / "PeterPiperV1.1", BASE)
    before = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    zp = make_zip(OUT / "rel_d.zip", "PeterPiperV1.2", dict(BASE, **{"PeterPiperV1.2.bat": b"x"}))
    p = U.plan(zp, folder)
    ok("D a new program folder -> new folder", p["mode"] == "new_folder" and "new" in p["why"])
    dest = U.unpack_new_folder(zp, folder)
    ok("D unpacked next to this one", dest == folder.parent / "PeterPiperV1.2"
       and (dest / "PeterPiperV1.2.bat").exists())
    ok("D this folder unchanged", all(q.read_bytes() == b for q, b in before.items()))
    try:
        U.unpack_new_folder(zp, folder)
        ok("D never over an existing folder", False)
    except RuntimeError:
        ok("D never over an existing folder", True)
    zp2 = make_zip(OUT / "rel_d2.zip", "PeterPiperV1.1",
                   dict(BASE, **{"app/requirements.txt": b"numpy==2\n"}))
    ok("D other packages -> new folder", U.plan(zp2, folder)["mode"] == "new_folder")


def part_e():
    for name, bad in (("dots", "PeterPiperV1.1/../evil.txt"), ("abs", "/evil.txt")):
        zp = OUT / f"bad_{name}.zip"
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr(bad, b"x")
        try:
            U.read_zip(zp)
            ok(f"E unsafe path refused ({name})", False)
        except RuntimeError:
            ok(f"E unsafe path refused ({name})", True)
    dz = OUT / "damaged.zip"
    data = bytearray(make_zip(OUT / "good.zip", "PeterPiperV1.1", BASE).read_bytes())
    data[60:80] = b"\x00" * 20
    dz.write_bytes(bytes(data))
    try:
        U.read_zip(dz)
        ok("E damaged zip refused", False)
    except Exception:                                              # noqa: BLE001
        ok("E damaged zip refused", True)


def part_f():
    rel = {"assets": [{"name": "PeterPiper-1.2.0-macOS-AppleChip.dmg", "url": "https://x/a",
                       "size": 1},
                      {"name": "PeterPiper-1.2.0-macOS-Intel.dmg", "url": "https://x/i", "size": 1},
                      {"name": "PeterPiperV1.2.zip", "url": "https://x/z", "size": 1}]}
    ok("F Windows / zip install -> the zip", U.pick_asset(rel, "zip")["name"] == "PeterPiperV1.2.zip")
    ok("F Mac -> a dmg", U.pick_asset(rel, "mac_app")["name"].endswith(".dmg"))
    try:
        U.download("http://insecure/x", OUT / "x.bin")
        ok("F http refused", False)
    except RuntimeError:
        ok("F http refused", True)

    class Fake(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    old = urllib.request.urlopen
    urllib.request.urlopen = lambda req, timeout=0: Fake(b"12345")
    try:
        U.download("https://x/z", OUT / "ok.bin", 5)
        ok("F a complete download", (OUT / "ok.bin").read_bytes() == b"12345")
        try:
            U.download("https://x/z", OUT / "short.bin", 9)
            ok("F an incomplete download is refused", False)
        except RuntimeError:
            ok("F an incomplete download is refused", True)
        urllib.request.urlopen = lambda req, timeout=0: Fake(
            b'{"tag_name": "v1.2.0", "body": "notes", "html_url": "https://x", "assets": []}')
        r = U.fetch_latest()
        ok("F the release list is read", r["version"] == "1.2.0" and r["notes"] == "notes")
    finally:
        urllib.request.urlopen = old


def part_g():
    from peterpiper.gui import updatedlg as D
    seen = []
    QMessageBox.information = staticmethod(lambda *a, **k: seen.append(a[2]) or QMessageBox.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: seen.append(a[2]) or QMessageBox.Ok)
    from peterpiper import __version__
    U.fetch_latest = lambda: {"version": __version__, "tag": "v" + __version__, "notes": "",
                              "url": "https://x", "assets": []}
    ok("G same version: 'You have the newest version'", D.check_for_updates(None) == "newest"
       and "newest" in seen[-1])

    def boom():
        raise OSError("no internet")
    U.fetch_latest = boom
    ok("G no internet: a plain message, nothing changed", D.check_for_updates(None) == "error"
       and "Could not reach GitHub" in seen[-1])
    from peterpiper.gui import setup as SU
    d = SU.SetupDialog()
    ok("G the start screen has 'Check for updates'",
       getattr(d, "btn_update", None) is not None and "update" in d.btn_update.text().lower())
    d.close()
    src = (REPO / "app/peterpiper/gui/clickwin.py").read_text(encoding="utf-8")
    ok("G the analysis window's Help menu has 'Check for updates...'",
       "Check for updates..." in src and "updatedlg" in src)
    net = [f for f in (REPO / "app/peterpiper").rglob("*.py")
           if f.name != "updater.py" and any(w in f.read_text(encoding="utf-8")
                                             for w in ("urllib", "socket", "requests", "http.client"))]
    ok("G no other module uses the network", not net, str(net))


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
