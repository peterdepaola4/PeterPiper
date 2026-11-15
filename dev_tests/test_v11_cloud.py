"""
Developer test (not shipped): PeterPiper 1.1 part "cloud" - cloud / network folders
found through each service's own sync app, online-only files, backups, the
results / backup folder settings and the 'Storage & cloud' windows.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts \
        python dev_tests/test_v11_cloud.py

A) detection on a made-up home folder (Windows layout): OneDrive personal and
   work, a SharePoint / Teams library (registry stand-in), Google Drive on a
   drive letter with a shared drive, Box, Dropbox (+ info.json, also a Dropbox
   folder only named there), iCloud Drive, Nextcloud (+ its settings file),
   pCloud, MEGA, Sync.com, a mapped network drive; no duplicates; sorted by
   service; a Syncthing 'Sync' folder is not Sync.com; macOS layout
   (~/Library/CloudStorage, iCloud, a network mount); an empty home finds
   nothing; it is fast; place_of / service_of.
B) online-only files with mocked file attributes: Windows RECALL_ON_DATA_ACCESS,
   RECALL_ON_OPEN, OFFLINE; macOS SF_DATALESS; ordinary files are not; the
   warning in plain words names the service and the size.
C) backup of a made-up movie + results folder: layout <target>/PeterPiper backup/
   <movie>/ (movie + OUTPUT_<movie>/<user>/...), sizes and times kept, junk
   files left out, byte progress; a second run skips everything; a changed file
   gets _2 (the first copy stays); the movie left out on request; another movie
   of the same name goes to <movie>_2; Stop removes the half-copied file and a
   new run finishes the rest; a target that cannot be written is reported and
   nothing is copied.
D) settings per user: results_root / backup_root round trip, users.output_dir
   follows results_root (and goes back next to the movie when cleared); an
   unwritable folder is refused.
E) windows offscreen at 1366x768 and 1280x800 (no scroll bars, they fit):
   Storage & cloud with places and with none; choosing a place for results
   (-> <place>/PeterPiper results) and saving; the backup window runs a backup
   with progress and shows 'Open backup folder'; Stop works; pick_place menu.
F) cloud.py and storagedlg.py import no network modules.
G) (only when this computer has Google Drive for desktop on G:) the real Google
   Drive is found. With PETERPIPER_TEST_CLOUD_WRITE=1 also a real backup into a
   new folder 'G:\\My Drive\\PeterPiper test 1.1' (tiny made-up files), checked,
   is_online_only read, and that one folder deleted again.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v11_cloud"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtCore import Qt, QTimer                                  # noqa: E402
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication,      # noqa: E402
                               QMessageBox)

APP = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

from peterpiper import cloud as C                                      # noqa: E402
from peterpiper import users                                           # noqa: E402
from peterpiper.gui import storagedlg as SD                            # noqa: E402
from peterpiper.gui import theme as TH                                 # noqa: E402
from peterpiper.gui import widgets as W                                # noqa: E402

N = [0]
FAILS = []


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def mk(*parts) -> Path:
    p = Path(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def fake_home(name: str) -> Path:
    h = mk(OUT / name)
    os.environ["PETERPIPER_CLOUD_HOME"] = str(h)
    C.TEST_HOOKS.clear()
    return h


def write(p: Path, nbytes: int, seed: int = 1) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(bytes((i * seed + seed) % 251 for i in range(nbytes)))
    return p


# ======================================================================== A
print("--- A) detection")
h = fake_home("home_win")
for d in ("OneDrive", "OneDrive - Contoso Lab", "Box", "Dropbox", "Dropbox (Contoso)",
          "iCloudDrive", "Nextcloud", "pCloud Drive", "MEGA", "Sync",
          "Contoso Lab/Lab Team - Documents", "Contoso Lab/Imaging Core - Shared",
          "Documents", "Pictures", "Elsewhere/Work files"):
    mk(h, d)
gdrive = mk(OUT, "fake_G")
mk(gdrive, "My Drive")
mk(gdrive, "Shared drives", "Team Imaging")
mk(h, "AppData", "Local", "Dropbox")
(h / "AppData" / "Local" / "Dropbox" / "info.json").write_text(json.dumps({
    "personal": {"path": str(h / "Dropbox"), "is_team": False},
    "business": {"path": str(h / "Dropbox (Contoso)"), "is_team": True}}), encoding="utf-8")
mk(h, "AppData", "Roaming", "Dropbox")
(h / "AppData" / "Roaming" / "Dropbox" / "info.json").write_text(json.dumps({
    "personal": {"path": str(h / "Elsewhere" / "Work files")}}), encoding="utf-8")
mk(h, "AppData", "Roaming", "Nextcloud")
(h / "AppData" / "Roaming" / "Nextcloud" / "nextcloud.cfg").write_text(
    "[Accounts]\n0\\Folders\\1\\localPath=" + str(h / "Nextcloud").replace("\\", "/") + "/\n",
    encoding="utf-8")
C.TEST_HOOKS.update(system="win32", drives=[
    {"root": str(gdrive) + os.sep, "type": "fixed", "label": "Google Drive"},
    {"root": "Z:\\", "type": "remote", "label": "", "unc": "\\\\labserver\\share"},
    {"root": "Y:\\", "type": "remote", "label": "", "unc": "\\\\EgnyteDrive\\contoso"}],
    onedrive=[{"UserFolder": str(h / "OneDrive"), "DisplayName": "", "business": False},
              {"UserFolder": str(h / "OneDrive - Contoso Lab"), "DisplayName": "Contoso Lab",
               "business": True, "tenants": [str(h / "Contoso Lab"), str(h / "OneDrive - Contoso Lab")],
               "libraries": [str(h / "Contoso Lab" / "Lab Team - Documents")]}])
t0 = time.perf_counter()
P = C.places()
dt = time.perf_counter() - t0
names = [p.name for p in P]
svcs = {p.service for p in P}
print("    found:", [(p.service, p.kind, p.name) for p in P])
for s in ("OneDrive", "Google Drive", "Box", "Dropbox", "iCloud Drive", "Nextcloud", "pCloud",
          "MEGA", "Sync.com", "Egnyte", "Network"):
    ok(f"A found {s}", s in svcs)
ok("A no duplicate folders", len({C._key(p.path) for p in P}) == len(P))
order = list(C.SERVICES) + ["Network"]
idx = [order.index(p.service) for p in P]
ok("A sorted by service", idx == sorted(idx), str(idx))
ok("A OneDrive personal + work", any(p.kind == "personal" and p.service == "OneDrive" for p in P)
   and any(p.name == "OneDrive - Contoso Lab" and p.kind == "work" for p in P))
lib = [p for p in P if p.service == "OneDrive" and p.kind == "shared"]
ok("A SharePoint / Teams libraries (both, the org folder itself not)",
   sorted(Path(p.path).name for p in lib) == ["Imaging Core - Shared", "Lab Team - Documents"]
   and all(Path(p.path).name != "Contoso Lab" for p in P), str([p.name for p in lib]))
ok("A Google Drive = its My Drive", any(p.service == "Google Drive" and
                                         Path(p.path) == gdrive / "My Drive" for p in P))
ok("A Google shared drive", any(p.kind == "shared" and p.service == "Google Drive" and
                                 p.path.endswith("Team Imaging") for p in P))
ok("A Dropbox from info.json only", any(p.service == "Dropbox" and
                                         p.path.endswith("Work files") for p in P))
ok("A names are unique (two Dropbox folders)", len(set(names)) == len(names) and
   "Dropbox (Work files)" in names, str(names))
ok("A Dropbox business is 'work'", any(p.service == "Dropbox" and p.kind == "work" for p in P))
ok("A network drive with its share", any(p.kind == "network" and "Z:" in p.name and
                                          "labserver" in p.name for p in P))
ok("A Egnyte drive not listed as plain network",
   not any(p.service == "Network" and "Egnyte" in p.name for p in P))
ok("A ordinary folders not listed", not any(Path(p.path).name in ("Documents", "Pictures")
                                            for p in P))
ok("A fast", dt < 0.5, f"{dt * 1000:.1f} ms")
od = next(p for p in P if p.name == "OneDrive")
ok("A place_of / service_of", C.service_of(Path(od.path) / "x" / "movie.nd2", P) == "OneDrive"
   and C.place_of(Path(od.path) / "a.nd2", P) == od and C.service_of(OUT / "nowhere", P) == "")
ok("A results folder suggested inside a place",
   C.suggested_results_folder(od) == str(Path(od.path) / "PeterPiper results"))

# Syncthing's Sync folder is not Sync.com
h2 = fake_home("home_syncthing")
mk(h2, "Sync", ".stfolder")
C.TEST_HOOKS.update(system="win32")
ok("A Syncthing 'Sync' is not Sync.com", not any(p.service == "Sync.com" for p in C.places()))

# macOS
hm = fake_home("home_mac")
for d in ("Library/CloudStorage/OneDrive-Personal", "Library/CloudStorage/OneDrive-Contoso",
          "Library/CloudStorage/OneDrive-SharedLibraries-Contoso/Lab Team - Documents",
          "Library/CloudStorage/GoogleDrive-test.user@example.com/My Drive",
          "Library/CloudStorage/GoogleDrive-test.user@example.com/Shared drives/Core",
          "Library/CloudStorage/Box-Box", "Library/CloudStorage/Dropbox",
          "Library/Mobile Documents/com~apple~CloudDocs", "pCloud Drive", "Desktop"):
    mk(hm, d)
mk(hm, ".dropbox")
(hm / ".dropbox" / "info.json").write_text(json.dumps(
    {"personal": {"path": str(hm / "Library" / "CloudStorage" / "Dropbox")}}), encoding="utf-8")
C.TEST_HOOKS.update(system="darwin", mounts=[("/Volumes/labshare", "smbfs", "//srv/labshare")])
PM = C.places()
print("    mac:", [(p.service, p.kind, p.name) for p in PM])
sm = {p.service for p in PM}
ok("A mac services", {"OneDrive", "Google Drive", "Box", "Dropbox", "iCloud Drive", "pCloud",
                      "Network"} <= sm, str(sorted(sm)))
ok("A mac OneDrive personal + work + library",
   any(p.name == "OneDrive" for p in PM) and any(p.name == "OneDrive - Contoso" for p in PM)
   and any(p.kind == "shared" and p.service == "OneDrive" for p in PM))
ok("A mac Google Drive is My Drive (+ shared drive)",
   any(p.path.endswith("My Drive") for p in PM) and
   any(p.service == "Google Drive" and p.kind == "shared" for p in PM))
ok("A mac Dropbox once", sum(p.service == "Dropbox" for p in PM) == 1)
ok("A mac network mount", any(p.kind == "network" and p.path == "/Volumes/labshare" for p in PM))
ok("A mac no duplicates", len({C._key(p.path) for p in PM}) == len(PM))

fake_home("home_empty")
ok("A empty home: nothing", C.places() == [])
C.TEST_HOOKS.update(system="darwin")
ok("A empty home (mac): nothing", C.places() == [])

# ======================================================================== B
print("--- B) online-only files")
h = fake_home("home_win")          # the Windows layout again
C.TEST_HOOKS.update(system="win32")
P = C.places()
od = next(p for p in P if p.name == "OneDrive")
real_stat = C._stat
ATTR = {"v": 0, "flags": 0}
C._stat = lambda path: SimpleNamespace(st_file_attributes=ATTR["v"], st_flags=ATTR["flags"],
                                       st_size=2_300_000_000)
for val, want, what in ((0x400000, True, "RECALL_ON_DATA_ACCESS"), (0x40000, True, "RECALL_ON_OPEN"),
                        (0x1000, True, "OFFLINE"), (0x20, False, "ARCHIVE only"),
                        (0x400020, True, "RECALL + ARCHIVE")):
    ATTR["v"] = val
    ok(f"B windows {what} -> {want}", C.is_online_only("x.nd2") is want)
ATTR["v"] = 0x400000
w = C.online_warning(Path(od.path) / "movie.nd2", found=P)
ok("B warning in plain words", w == "This movie is stored only online in OneDrive; it will be "
   "downloaded first (about 2.3 GB).", w)
ATTR["v"] = 0
ok("B no warning for a local file", C.online_warning(Path(od.path) / "movie.nd2", found=P) == "")
C.TEST_HOOKS["system"] = "darwin"
ATTR["flags"] = 0x40000000
ok("B mac SF_DATALESS -> True", C.is_online_only("x.nd2") is True)
ATTR["flags"] = 0x20
ok("B mac ordinary -> False", C.is_online_only("x.nd2") is False)
C._stat = real_stat
C.TEST_HOOKS["system"] = "win32"
ok("B missing file -> False", C.is_online_only(OUT / "no such file.nd2") is False)
real = write(OUT / "local.bin", 100)
ok("B real local file -> False", C.is_online_only(real) is False)
ok("B human sizes", (C.human_size(2_300_000_000), C.human_size(512), C.human_size(45_600_000))
   == ("2.3 GB", "512 bytes", "45.6 MB"))

# ======================================================================== C
print("--- C) backup")
C.CHUNK = 64 * 1024                       # several chunks per file in the test
src = mk(OUT, "lab", "2026-01 imaging")
movie = write(src / "movie_A.nd2", 400_000, 3)
res = mk(src, "OUTPUT_movie_A", "alice")
files = {"PeterPiper_sessions/movie_A_session_1.npz": 150_000,
         "movie_A_ROIs_saved.npz": 20_000,
         "Export_2026-01-05/movie_A.xlsx": 70_000,
         "Export_2026-01-05/Whole cell/Prism graphs/movie_A_ratio.prism": 5_000}
for rel, n in files.items():
    write(res / rel, n, 5)
write(res / "PeterPiper_sessions" / ".movie_A.tmp", 10)
write(res / "~$movie_A.xlsx", 10)
write(res / ".peterpiper_write_test_abc", 0)
tgt = mk(OUT, "cloud_target")
prog = []
r1 = C.backup(movie, res, tgt, True, lambda d, t, n: prog.append((d, t, n)))
bk = tgt / "PeterPiper backup" / "movie_A"
print("    ", r1.summary())
ok("C first run copies movie + results", r1.ok and len(r1.copied) == 1 + len(files)
   and not r1.skipped, r1.summary())
ok("C layout: movie + OUTPUT_<movie>/<user>", (bk / "movie_A.nd2").is_file() and
   (bk / "OUTPUT_movie_A" / "alice" / "PeterPiper_sessions" / "movie_A_session_1.npz").is_file()
   and Path(r1.folder) == bk)
allsame = all((bk / "OUTPUT_movie_A" / "alice" / rel).stat().st_size == n for rel, n in files.items())
ok("C sizes verified", allsame and (bk / "movie_A.nd2").stat().st_size == 400_000)
ok("C contents identical", (bk / "movie_A.nd2").read_bytes() == movie.read_bytes())
ok("C times kept", abs((bk / "movie_A.nd2").stat().st_mtime - movie.stat().st_mtime) < 0.01)
copied_names = {Path(b).name for _a, b in r1.copied}
ok("C junk files left out", not ({".movie_A.tmp", "~$movie_A.xlsx"} & copied_names) and
   not list(bk.rglob(".peterpiper_write_test_*")) and not list(bk.rglob("*.peterpiper-partial")))
ok("C byte progress", len(prog) > 8 and prog[-1][0] == prog[-1][1] == r1.total_bytes ==
   r1.bytes_copied and all(a[0] <= b[0] for a, b in zip(prog, prog[1:])),
   f"{len(prog)} calls, total {r1.total_bytes}")
r2 = C.backup(movie, res, tgt, True)
ok("C second run skips everything", not r2.copied and len(r2.skipped) == len(r1.copied)
   and r2.ok, r2.summary())
xl = res / "Export_2026-01-05" / "movie_A.xlsx"
before = (bk / "OUTPUT_movie_A" / "alice" / "Export_2026-01-05" / "movie_A.xlsx").read_bytes()
write(xl, 71_000, 9)
r3 = C.backup(movie, res, tgt, True)
two = bk / "OUTPUT_movie_A" / "alice" / "Export_2026-01-05" / "movie_A_2.xlsx"
ok("C changed file -> _2, first copy kept", len(r3.copied) == 1 and two.is_file()
   and two.read_bytes() == xl.read_bytes() and
   (bk / "OUTPUT_movie_A" / "alice" / "Export_2026-01-05" / "movie_A.xlsx").read_bytes() == before,
   r3.summary())
r4 = C.backup(movie, res, tgt, True)
ok("C after that everything skipped again", not r4.copied and r4.ok)
r5 = C.backup(movie, res, mk(OUT, "target_nomovie"), include_movie=False)
ok("C movie left out on request", r5.ok and not any(a.endswith(".nd2") for a, _b in r5.copied)
   and not (OUT / "target_nomovie" / "PeterPiper backup" / "movie_A" / "movie_A.nd2").exists())
other = write(mk(OUT, "lab", "other day") / "movie_A.nd2", 300_000, 7)
r6 = C.backup(other, None, tgt, True)
ok("C another movie of the same name -> movie_A_2", r6.ok and
   Path(r6.folder).name == "movie_A_2" and (Path(r6.folder) / "movie_A.nd2").read_bytes() ==
   other.read_bytes())
# Stop
tc = mk(OUT, "target_cancel")
calls = [0]


def stop_soon():
    calls[0] += 1
    return calls[0] > 4


r7 = C.backup(movie, res, tc, True, None, stop_soon)
ok("C Stop: cancelled, half-copied file removed", r7.cancelled and not r7.ok and
   not list(tc.rglob("*.peterpiper-partial")), r7.summary())
ev = threading.Event()
ev.set()
r7b = C.backup(movie, res, mk(OUT, "target_cancel_ev"), True, None, ev)
ok("C Stop with a threading.Event", r7b.cancelled and not r7b.copied)
r8 = C.backup(movie, res, tc, True)
ok("C new run after Stop finishes the rest", r8.ok and
   len(r8.copied) + len(r8.skipped) == 1 + len(files) and len(r8.copied) >= 1, r8.summary())
# a target that cannot be written
blocker = write(OUT / "not a folder", 10)
r9 = C.backup(movie, res, blocker, True)
ok("C unwritable target reported, nothing copied", bool(r9.problem) and not r9.copied
   and r9.summary().startswith("Not backed up"), r9.problem)
real_fp = C.folder_problem
C.folder_problem = lambda p: "the drive is read-only"
r10 = C.backup(movie, res, mk(OUT, "target_ro"), True)
C.folder_problem = real_fp
ok("C read-only drive reported in plain words", "read-only" in r10.problem and not r10.copied,
   r10.problem)
if os.name != "nt":
    ro = mk(OUT, "target_chmod")
    os.chmod(ro, 0o555)
    r11 = C.backup(movie, res, ro, True)
    os.chmod(ro, 0o755)
    ok("C read-only folder (chmod) reported", bool(r11.problem) and not r11.copied, r11.problem)
r12 = C.backup(OUT / "lab" / "gone.nd2", OUT / "lab" / "no results", mk(OUT, "t12"), False)
ok("C no results folder yet -> said so", "no results" in r12.problem, r12.problem)

# ======================================================================== D
print("--- D) settings")
users.add_user("Test User")
users.activate("Test User")
nd2 = OUT / "lab" / "2026-01 imaging" / "movie_A.nd2"
ok("D default: results next to the movie", C.results_root() == "" and
   Path(users.output_dir(nd2)) == nd2.parent / "OUTPUT_movie_A" / users.folder_name("Test User"))
rr = mk(OUT, "cloud_results")
C.set_results_root(rr)
ok("D results_root round trip", Path(C.results_root()) == rr and
   json.loads((users.home() / "storage.json").read_text())["results_root"] == str(rr))
ok("D users.output_dir follows it", Path(users.output_dir(nd2)) ==
   rr / "OUTPUT_movie_A" / users.folder_name("Test User"))
C.set_backup_root(tgt)
ok("D backup_root round trip", Path(C.backup_root()) == tgt and Path(C.results_root()) == rr)
C.set_results_root(None)
ok("D cleared: next to the movie again", C.results_root() == "" and
   Path(users.output_dir(nd2)).parent == nd2.parent / "OUTPUT_movie_A" and
   "results_root" not in json.loads((users.home() / "storage.json").read_text()))
try:
    C.set_backup_root(blocker)
    refused = False
except ValueError as exc:
    refused = "cannot write" in str(exc)
ok("D unwritable folder refused", refused and Path(C.backup_root()) == tgt)

# ======================================================================== E
print("--- E) windows")
TH.apply(APP, "midnight")
fake_home("home_win")
C.TEST_HOOKS.update(system="win32", drives=[
    {"root": str(gdrive) + os.sep, "type": "fixed", "label": "Google Drive"},
    {"root": "Z:\\", "type": "remote", "label": "", "unc": "\\\\labserver\\share"}])
P = C.places()


def no_scroll(w) -> bool:
    for a in w.findChildren(QAbstractScrollArea):
        if a.isVisible() and (a.verticalScrollBar().maximum() > 0 or
                              a.horizontalScrollBar().maximum() > 0):
            return False
    return True


def check_fits(w, name):
    for sw, sh in ((1366, 768), (1280, 800)):
        w.show()
        w.adjustSize()
        APP.processEvents()
        need = w.sizeHint()
        fits = need.width() <= sw - 40 and w.minimumSizeHint().height() <= sh - 80 and \
            w.height() <= sh - 80
        ok(f"E {name} fits {sw}x{sh}, no scroll bars", fits and no_scroll(w),
           f"{w.width()}x{w.height()}")
    p = SHOTS / f"v11_cloud_{name}.png"
    w.grab().save(str(p))
    return p


sd = SD.StorageDialog(None, P)
shot1 = check_fits(sd, "storage")
ok("E storage lists the places", sd.findChildren(SD._PathLabel)[0].path() == P[0].path)
ok("E 'next to each movie' is the default", sd.rb_next.isChecked())
gd = next(p for p in P if p.service == "Google Drive" and p.kind == "personal")
sd._menu_choice = lambda button, extra=None: gd.path
sd._choose_results()
ok("E a place for results -> <place>/PeterPiper results",
   sd.lbl_results.path() == str(Path(gd.path) / "PeterPiper results") and sd.rb_folder.isChecked())
od = next(p for p in P if p.name == "OneDrive")
sd._menu_choice = lambda button, extra=None: od.path
sd._choose_backup()
sd._save()
ok("E Save stores both", Path(C.results_root()) == Path(gd.path) / "PeterPiper results" and
   Path(C.backup_root()) == Path(od.path) and sd.result() == 1)
ok("E results then go into the cloud folder", Path(users.output_dir(nd2)) ==
   Path(gd.path) / "PeterPiper results" / "OUTPUT_movie_A" / users.folder_name("Test User"))
sd2 = SD.StorageDialog(None, P)
ok("E reopened shows the saved choice", sd2.rb_folder.isChecked() and
   sd2.lbl_results.path() == C.results_root())
sd2._menu_choice = lambda button, extra=None: "none"
sd2._choose_backup()
sd2.rb_next.setChecked(True)
sd2._save()
ok("E back to defaults", C.results_root() == "" and C.backup_root() == "")
sd.close()
sd2.close()
sd3 = SD.StorageDialog(None, [])
shot2 = check_fits(sd3, "storage_none")
ok("E nothing found: says what to install", any(SD.NONE_FOUND in lab.text() for lab in
                                                sd3.findChildren(W.FitLabel)))
sd3.close()
TH.apply(APP, "daylight")
sd4 = SD.StorageDialog(None, P)
shot3 = check_fits(sd4, "storage_light")
sd4.close()
TH.apply(APP, "midnight")

# backup window
C.set_backup_root(None)
bt = mk(OUT, "dlg_target")
bd = SD.BackupDialog(None, movie, res, P)
ok("E backup: movie size on the checkbox", "400 KB" in bd.chk_movie.text() and bd.chk_movie.isChecked(),
   bd.chk_movie.text())
ok("E backup: default target = first place", bd.lbl_target.path() == P[0].path)
bd._menu_choice = lambda: str(bt)
bd._change()
shot4 = check_fits(bd, "backup_ready")
bd._start()
t0 = time.time()
while bd.running() or bd._timer.isActive():
    APP.processEvents()
    time.sleep(0.01)
    if time.time() - t0 > 30:
        break
ok("E backup ran from the window", bd.report is not None and bd.report.ok and
   len(bd.report.copied) == 1 + len(files), bd.report.summary() if bd.report else "none")
ok("E summary + Open backup folder shown", bd.btn_open.isVisible() and
   "copied" in bd.lbl_status.text() and bd.bar.value() == 1000)
ok("E chosen target remembered", Path(C.backup_root()) == bt)
opened = []
SD.W.open_path = lambda p: opened.append(p) or True
bd._open()
ok("E Open backup folder opens it", opened and Path(opened[0]) == bt / "PeterPiper backup" / "movie_A")
shot5 = check_fits(bd, "backup_done")
bd.close()
# Stop in the window
C.CHUNK = 4096
bd2 = SD.BackupDialog(None, movie, res, P)
bd2._menu_choice = lambda: str(mk(OUT, "dlg_target_stop"))
bd2._change()
bd2.show()
bd2._start()
bd2._cancel_or_close()
t0 = time.time()
while bd2.running() or bd2._timer.isActive():
    APP.processEvents()
    time.sleep(0.01)
    if time.time() - t0 > 30:
        break
ok("E Stop in the window", bd2.report is not None and bd2.report.cancelled and
   "Stopped" in bd2.lbl_status.text(), bd2.lbl_status.text())
bd2.close()
C.CHUNK = 64 * 1024
# a movie stored only online: the warning shows
C._stat = lambda path: SimpleNamespace(st_file_attributes=0x400000, st_flags=0,
                                       st_size=2_300_000_000)
on = write(Path(od.path) / "movie_B.nd2", 1000)
bd3 = SD.BackupDialog(None, on, None, P)
C._stat = real_stat
ok("E online-only movie warned in the window", not bd3.lbl_online.isHidden() and
   "only online in OneDrive" in bd3.lbl_online.text(), bd3.lbl_online.text())
shot6 = check_fits(bd3, "backup_online")
bd3.close()

# pick_place: a menu with the places + Other folder...
seen = {}


def choose_second():
    m = APP.activePopupWidget()
    seen["actions"] = [a.text() for a in m.actions() if a.text()] if m else []
    if m is not None:
        acts = [a for a in m.actions() if not a.isSeparator()]
        m.setActiveAction(acts[1])
        from PySide6.QtTest import QTest
        QTest.keyClick(m, Qt.Key_Return)


QTimer.singleShot(200, choose_second)
got = SD.pick_place(None, P)
ok("E pick_place offers the places + Other folder...", len(seen.get("actions", [])) == len(P) + 1
   and seen["actions"][-1] == "Other folder...", str(len(seen.get("actions", []))))
ok("E pick_place returns the folder", got == P[1].path, str(got))
m = SD.place_menu(None, [])
ok("E place menu with nothing found: only Other folder...",
   [a.text() for a in m.actions()] == ["Other folder..."])

# ======================================================================== F
print("--- F) no network code")
for f in (REPO / "app" / "peterpiper" / "cloud.py",
          REPO / "app" / "peterpiper" / "gui" / "storagedlg.py"):
    text = f.read_text(encoding="utf-8")
    bad = re.findall(r"^\s*(?:import|from)\s+(socket|urllib\w*|requests|http\w*|ssl|ftplib|"
                     r"smtplib|aiohttp|httpx|webbrowser|QtNetwork)\b", text, re.M)
    bad += re.findall(r"\b(QtNetwork|urlopen|QNetworkAccessManager)\b", text)
    ok(f"F no network imports in {f.name}", not bad, str(bad))

# ======================================================================== G
print("--- G) this computer's Google Drive (if any)")
os.environ.pop("PETERPIPER_CLOUD_HOME", None)
C.TEST_HOOKS.clear()
GD = Path("G:/My Drive")
if os.name == "nt" and GD.is_dir():
    t0 = time.perf_counter()
    real = C.places()
    dt = time.perf_counter() - t0
    ok("G real Google Drive on G: found", any(p.service == "Google Drive" and
                                              C._key(p.path) == C._key(GD) for p in real),
       f"{len(real)} places, {dt * 1000:.0f} ms")
    ok("G real detection fast", dt < 1.0, f"{dt * 1000:.0f} ms")
    if os.environ.get("PETERPIPER_TEST_CLOUD_WRITE") == "1":
        TEST_DIR = GD / "PeterPiper test 1.1"
        shutil.rmtree(TEST_DIR, ignore_errors=True)
        TEST_DIR.mkdir()
        try:
            lsrc = mk(OUT, "gd_src")
            lmovie = write(lsrc / "movie.nd2", 4096, 11)
            lres = mk(lsrc, "OUTPUT_movie", "tester")
            write(lres / "movie_ROIs_saved.npz", 2048, 12)
            write(lres / "PeterPiper_sessions" / "movie_session_1.npz", 3000, 13)
            g1 = C.backup(lmovie, lres, TEST_DIR, True)
            gb = TEST_DIR / "PeterPiper backup" / "movie"
            ok("G backup into Google Drive", g1.ok and len(g1.copied) == 3 and
               (gb / "movie.nd2").stat().st_size == 4096 and
               (gb / "OUTPUT_movie" / "tester" / "movie_ROIs_saved.npz").read_bytes() ==
               (lres / "movie_ROIs_saved.npz").read_bytes(), g1.summary())
            g2 = C.backup(lmovie, lres, TEST_DIR, True)
            ok("G second run skips (times kept on Google Drive)", not g2.copied and
               len(g2.skipped) == 3, g2.summary())
            ok("G service_of the backup = Google Drive",
               C.service_of(gb / "movie.nd2", real) == "Google Drive")
            st = os.stat(gb / "movie.nd2")
            print(f"    attributes of the copy: 0x{getattr(st, 'st_file_attributes', 0):x}; "
                  f"online only: {C.is_online_only(gb / 'movie.nd2')}")
            ok("G is_online_only runs on Google Drive", isinstance(
                C.is_online_only(gb / "movie.nd2"), bool))
        finally:
            shutil.rmtree(TEST_DIR, ignore_errors=True)
        ok("G test folder removed again", not TEST_DIR.exists())
    else:
        print("    (writing into Google Drive skipped - set PETERPIPER_TEST_CLOUD_WRITE=1)")
else:
    print("SKIPPED - no Google Drive for desktop on G: here")

print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
print("screenshots:", ", ".join(str(p) for p in (shot1, shot2, shot3, shot4, shot5, shot6)))
if FAILS:
    print("FAILED:", FAILS)
    sys.exit(1)
