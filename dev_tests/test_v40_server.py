"""
Developer test (not shipped): PeterPiper 4.0, part "server" - the lab folder made
obvious, the background task center, safe copies, the movie cache, uploads and
backups, the start window's 'Lab folder & backup' tab, the guide, the role menu.
Everything happens in fake lab folders under _out (no real cloud, no network; the
sync-app check and the free disk space are faked).

    PYTHONIOENCODING=utf-8 MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \\
        QT_QPA_FONTDIR=C:/Windows/Fonts python dev_tests/test_v40_server.py

A) layout: 'Set up a lab folder' makes the marker, People, Shared/*, the READ ME;
   a second time changes nothing; an existing 1.1 lab folder is adopted - every
   file still there unchanged, its 'PeterPiper profiles' kept where they are (the
   marker says so), a person's own folder ('Peter') recorded, nothing moved.
B) find_lab_root walks up from any folder or file inside (marker first, a 1.1 lab
   list when no marker); outside a lab -> None.
C) connect: from a deep subfolder; the root stored for THIS computer; People/<me>
   with Results / Exports / Backups / Movies; profiles go to Shared/ in a new lab;
   own_folder_setup sees results going to an own folder (inside / outside the lab),
   use_lab_results switches (nothing moved).
D) scan_for_labs finds lab folders in the top 3 levels of each sync folder (not
   deeper), says which have the marker, stops when cancelled, is quick.
E) health: grey (not connected), red (unreachable / disk full), amber (sync app not
   running / little space), green - each with a plain fix.
F) TaskCenter: at most 2 heavy tasks at once (light ones beside them), cancel a
   waiting and a running task, a failure keeps its error, Retry, priority / bump,
   a waiting task with the same key reused, the status line, on_done; through the
   Qt bridge on_done runs in the window thread.
G) copy_file: never a half file under the real name (hidden partial name while
   copying), a file locked by the sync app is tried again until it works, a lasting
   error fails cleanly (no partial file left), cancel removes the partial file,
   overwrite=False keeps the other file (_2) or skips an identical one, SHA-256
   checked for small files; keep_copy (1.2.2) retries a locked file too.
H) movie cache: fetch_movie copies an online-only movie into the cache, reuses it
   (size + time), fetches again when the original changed; a movie on this
   computer is not copied; the same movie asked twice -> one task; LRU cleanup over
   the limit never removes the open (pinned) movie; too little space -> a clear
   failure; prefetch follows the option; the queue: todo_after, prefetch_next,
   fetch_words, open_path.
I) uploads: on_results_written copies SAVEs to People/<me>/Results and exports to
   People/<me>/Exports (OUTPUT_<movie>/<me>), nothing when the options are off or no
   lab is connected; analysed movies only when switched on.
J) backups: backup_profile -> People/<me>/Backups/PeterPiper backup <me> <date>.zip
   (profile, settings, run list), last backup remembered, backup_due daily.
K) roles: the role menu offers User and Admin; the third role only for a person who
   has it or found a certain extra.
L) GUI: the start window with the 'Lab folder & backup' tab at 1366 x 768 and
   1366 x 698 - no scroll bars; connected / health / own-folder states; Connect
   dialog (found list, walk-up, adopt question, own folder question); the guide
   pages; the task status line and list (progress, Cancel, Retry, Open folder);
   waiting for a movie (never blocking) - screenshots in _out/shots.
M) this computer's copy speed (a 1 GB file in _out, deleted again) - printed.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v40_server"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS = REPO / "_out" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ["PETERPIPER_CLOUD_HOME"] = str(OUT / "cloudhome")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtCore import QThread                                    # noqa: E402
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QWidget  # noqa: E402

APP = QApplication(sys.argv)
from peterpiper import batchqueue, cloud, labshare as L, tasks as T   # noqa: E402
from peterpiper import transfers as X, userprefs as UP, users         # noqa: E402
from peterpiper.gui import theme as TH                                # noqa: E402

N = [0]
FAILS = []
TIMES = {}


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(s=0.2):
    end = time.monotonic() + s
    while time.monotonic() < end:
        APP.processEvents()
        time.sleep(0.01)


def wait_for(cond, s=10.0):
    end = time.monotonic() + s
    while time.monotonic() < end:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def snapshot(folder: Path) -> dict:
    """{relative path: bytes} of every file (to show nothing was changed / moved)."""
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob("*")) if p.is_file()}


CLOUD = OUT / "cloudhome"
BOX = CLOUD / "Box"                     # cloud.places() finds <home>/Box as "Box"
BOX.mkdir(parents=True)
for u in ("Test User", "Ana"):
    if u not in users.all_users():
        users.add_user(u)
users.activate("Test User")
ME = users.folder_name("Test User")


# ============================================================== A layout
def part_a():
    lab = BOX / "Lab share" / "PeterPiper lab"
    res = L.setup_lab_folder(lab, "Test lab", "Test User")
    m = L.read_marker(lab)
    ok("A setup: the marker with name, layout version, made by / when",
       m is not None and m["lab_name"] == "Test lab" and m["layout"] == L.LAYOUT_VERSION
       and m["created_by"] == "Test User" and m["created"] and not res["adopted"], str(m))
    want = ["People", "Shared", "Shared/PeterPiper profiles", "Shared/Detectors",
            "Shared/Prism templates", "Shared/Settings"]
    ok("A ... People, Shared and its parts, and the READ ME",
       all((lab / w).is_dir() for w in want) and (lab / L.README).is_file()
       and "Connect" in (lab / L.README).read_text(encoding="utf-8"))
    before = snapshot(lab)
    again = L.setup_lab_folder(lab, "Other name", "Ana")
    ok("A setting it up again changes nothing", again["already"] and snapshot(lab) == before
       and L.read_marker(lab)["lab_name"] == "Test lab")
    ok("A lab_path: profiles are in Shared/ in a new lab",
       L.lab_path("profiles", lab) == lab / "Shared" / "PeterPiper profiles")

    # an existing 1.1 lab folder (made by create_lab), with someone's own folder
    old = BOX / "PeterPiper Repository"
    L.create_lab(old, ["Test User", "Ana"], admin="Test User")
    (old / "Peter").mkdir()
    (old / "Peter" / "my results.xlsx").write_bytes(b"keep me")
    (old / "Ana").mkdir()
    (old / "Ana" / "notes.txt").write_text("hello")
    (old / "Other stuff").mkdir()
    users.add_aliases("Test User", ["Peter"])
    before = snapshot(old)
    res = L.setup_lab_folder(old, "", "Test User")
    after = snapshot(old)
    m = L.read_marker(old)
    ok("A adopting a 1.1 lab folder: every file there is still there, unchanged",
       all(after.get(k) == v for k, v in before.items()), str(set(before) - set(after)))
    ok("A ... adopted; its profiles stay in 'PeterPiper profiles' (the marker says so)",
       res["adopted"] and m["paths"]["profiles"] == L.PROFILES_DIR
       and L.lab_path("profiles", old) == old / L.PROFILES_DIR
       and not (old / "Shared" / "PeterPiper profiles").exists(), str(m["paths"]))
    ok("A ... the own folders found are recorded, not moved",
       m["existing"].get("people", {}).get("Test User") == "Peter"
       and m["existing"].get("people", {}).get("Ana") == "Ana"
       and "Other stuff" not in m["existing"].get("people", {}).values()
       and (old / "Peter" / "my results.xlsx").read_bytes() == b"keep me",
       str(m["existing"]))
    ok("A ... and the new folders are added beside them",
       (old / "People").is_dir() and (old / "Shared" / "Detectors").is_dir()
       and (old / L.README).is_file())
    L.unlink()


# ============================================================ B walk-up
def part_b():
    lab = BOX / "Lab share" / "PeterPiper lab"
    deep = lab / "People" / "Someone" / "Results" / "OUTPUT_x" / "deeper"
    deep.mkdir(parents=True)
    f = deep / "a file.txt"
    f.write_text("x")
    ok("B walk-up from a deep folder finds the lab root (marker)",
       L.find_lab_root(deep) == (str(lab), True), str(L.find_lab_root(deep)))
    ok("B ... and from a file in it", L.find_lab_root(f) == (str(lab), True))
    ok("B ... the lab folder itself", L.find_lab_root(lab) == (str(lab), True))
    ok("B outside any lab folder -> None", L.find_lab_root(BOX / "Lab share") is None
       and L.find_lab_root(OUT / "home") is None)
    old11 = BOX / "Old lab"
    old11.mkdir()
    L.write_list(old11, L._blank())
    (old11 / "sub").mkdir()
    ok("B a 1.1 lab folder (lab list, no marker) counts when nothing is above",
       L.find_lab_root(old11 / "sub") == (str(old11), False))
    nested = lab / "People" / "Someone" / "old copy"
    nested.mkdir(parents=True)
    L.write_list(nested, L._blank())
    ok("B ... but the marker above wins over a stray lab list below it",
       L.find_lab_root(nested) == (str(lab), True))


# ============================================================ C connect
def part_c():
    lab = BOX / "Lab share" / "PeterPiper lab"
    sub = lab / "People" / "Someone" / "Results"
    info = L.connect(sub, "Test User")
    ok("C connect from a subfolder links the lab ROOT", info["root"] == str(lab)
       and L.linked_folder() == str(lab), str(info))
    d = json.loads((users.base_dir() / users.USERS_FILE).read_text(encoding="utf-8"))
    ok("C ... stored for this computer (users.json 'lab'), not in the lab folder",
       d.get("lab", {}).get("folder") == str(lab)
       and str(lab) not in (lab / L.MARKER).read_text(encoding="utf-8"))
    pd = lab / "People" / ME
    ok("C ... People/<me> made with Results, Exports, Backups, Movies",
       all((pd / p).is_dir() for p in L.PERSON_PARTS) and info["person"] == str(pd))
    ok("C ... on the lab list, profile kept in Shared/PeterPiper profiles",
       L.person_of("Test User") is not None and
       L.profile_target("Test User")[1].parent == lab / "Shared" / "PeterPiper profiles")
    import peterpiper.profilesync as PS
    PS.sync_user("Test User")
    ok("C ... the profile sync writes it there",
       (lab / "Shared" / "PeterPiper profiles" / f"PeterPiper profile - {ME}").is_dir())
    ok("C no own folder set -> nothing to say", L.own_folder_setup() is None)
    own = lab / "Peter"
    own.mkdir()
    cloud.set_results_root(own)
    o = L.own_folder_setup()
    ok("C results going to an own folder inside the lab are noticed",
       o is not None and o["inside"] and o["current"] == str(own)
       and o["suggested"] == str(pd / "Results"), str(o))
    outside = BOX / "Peter ONLINE"
    outside.mkdir()
    cloud.set_results_root(outside)
    o = L.own_folder_setup()
    ok("C ... and an own folder elsewhere in the cloud", o is not None and not o["inside"])
    (outside / "a.txt").write_text("mine")
    t = L.use_lab_results()
    ok("C use_lab_results: results go to People/<me>/Results; the old folder untouched",
       cloud.results_root() == t == str(pd / "Results") and L.own_folder_setup() is None
       and (outside / "a.txt").read_text() == "mine"
       and users.output_dir("x/m.nd2").startswith(str(pd / "Results")))
    cloud.set_results_root(None)


# =============================================================== D scan
def part_d():
    roots = OUT / "scan"
    a = roots / "Box"
    (a / "Team" / "Imaging" / "PP lab").mkdir(parents=True)
    L.setup_lab_folder(a / "Team" / "Imaging" / "PP lab", "Imaging lab", "x")
    (a / "One" / "Two" / "Three" / "Four" / "deep lab").mkdir(parents=True)
    L.setup_lab_folder(a / "One" / "Two" / "Three" / "Four" / "deep lab", "deep", "x")
    old = a / "Old"
    old.mkdir()
    L.write_list(old, L._blank())
    for i in range(30):
        (a / f"folder {i}" / "x").mkdir(parents=True)
    t0 = time.monotonic()
    got = []
    res = L.scan_for_labs([("Box", str(a)), ("OneDrive", str(roots / "missing"))],
                          found=got.append)
    TIMES["scan (34 folders, depth 3)"] = time.monotonic() - t0
    names = {Path(e["root"]).name: e for e in res}
    ok("D found the lab 3 levels down, with its name and the marker",
       "PP lab" in names and names["PP lab"]["marker"] and names["PP lab"]["name"] ==
       "Imaging lab" and names["PP lab"]["service"] == "Box", str(res))
    ok("D ... and the 1.1 lab folder (no marker)", "Old" in names and not names["Old"]["marker"])
    ok("D ... not one deeper than 3 levels", "deep lab" not in names)
    ok("D ... each one reported as found; quick", len(got) == len(res)
       and TIMES["scan (34 folders, depth 3)"] < 3.0)
    ok("D cancelled -> stops at once", L.scan_for_labs([("Box", str(a))],
                                                       cancelled=lambda: True) == [])


# ============================================================== E health
def part_e():
    lab = L.linked_folder()
    keep = L.link_info()
    L.unlink()
    h = L.health()
    ok("E not connected: grey, 'Connect'", h.level == "grey" and "Connect" in h.fix)
    L._set_link(folder=str(BOX / "gone"))
    h = L.health()
    ok("E unreachable: red, says to start Box Drive", h.level == "red"
       and "Box Drive" in h.fix and "reached" in h.text, f"{h.text} / {h.fix}")
    L._set_link(**keep)
    L.TEST_HOOKS["processes"] = ["explorer.exe", "box.exe"]
    L.TEST_HOOKS["free"] = 200e9
    h = L.health()
    ok("E all fine: green, 'Box Drive running', space shown", h.level == "green"
       and "running" in h.text and "GB free" in h.text and not h.fix, h.text)
    L.TEST_HOOKS["processes"] = ["explorer.exe"]
    h = L.health()
    ok("E the sync app not running: amber, with the fix", h.level == "amber"
       and "Start Box Drive" in h.fix, f"{h.text} / {h.fix}")
    L.TEST_HOOKS["processes"] = ["box.exe"]
    L.TEST_HOOKS["free"] = 12e9
    h = L.health()
    ok("E little space: amber", h.level == "amber" and "12 GB" in h.text, h.text)
    L.TEST_HOOKS["free"] = 2e9
    h = L.health()
    ok("E disk almost full: red, says what to do", h.level == "red" and "Free some space"
       in h.fix, f"{h.text} / {h.fix}")
    L.TEST_HOOKS["free"] = 200e9
    other = Path(lab) / "People" / "Ana"
    other.mkdir(parents=True, exist_ok=True)
    (other / ".peterpiper-seen-OTHERPC.json").write_text("{}")
    ok("E another computer's 'seen' note -> when syncing last worked",
       L.last_change_elsewhere().startswith("today"))
    ok("E note_seen writes this computer's note in People/<me>", L.note_seen()
       and list((Path(lab) / "People" / ME).glob(".peterpiper-seen-*.json")))
    ok("E sync_app_running: unknown service -> None", L.sync_app_running("Network") is None)


# ========================================================= F task center
def part_f():
    c = T.TaskCenter(max_heavy=2, max_light=3)
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def heavy(progress, cancelled):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        for i in range(10):
            if cancelled():
                with lock:
                    state["now"] -= 1
                raise T.Cancelled()
            progress(i / 10, done=i * 1000, total=10000)
            time.sleep(0.02)
        with lock:
            state["now"] -= 1
        return "ok"
    ts = [c.submit("copy", f"copy {i}", heavy) for i in range(6)]
    light = c.submit("autosave", "autosave", lambda p, cc: time.sleep(0.05) or 1)
    time.sleep(0.03)
    ok("F at most 2 heavy tasks run at once; a light one runs beside them",
       sum(t.state == T.RUNNING for t in ts) == 2 and light.state == T.RUNNING,
       str([t.state for t in ts]))
    ok("F the status line", c.status_text() in ("6 copies · 1 autosave", "6 copies"),
       c.status_text())
    ts[5].cancel()
    ok("F cancel a waiting task: cancelled at once", ts[5].state == T.CANCELLED)
    ts[0].cancel()
    c.wait_all(10)
    ok("F ... a running one stops (cancelled), the rest done; never more than 2 at once",
       ts[0].state == T.CANCELLED and all(t.state == T.DONE for t in ts[1:5])
       and state["max"] == 2 and ts[1].result == "ok", str([t.state for t in ts]))
    ok("F done: progress 1, bytes done = total", ts[1].progress == 1.0
       and ts[1].bytes_done == ts[1].bytes_total == 10000)

    calls = []

    def bad(progress, cancelled):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError(13, "The file is locked by Box Drive")
        return "second time"
    done = []
    t = c.submit("upload", "upload", bad, on_done=done.append)
    t.wait(5)
    ok("F a failure keeps its error; on_done is called", t.state == T.FAILED
       and "locked" in t.error and done == [t], t.error)
    ok("F failed tasks show in the status line", c.status_text() == "" and c.failed())
    t2 = c.retry(t)
    t2.wait(5)
    ok("F Retry: the same job again", t2.state == T.DONE and t2.result == "second time"
       and t2 is not t and done == [t, t2])

    c2 = T.TaskCenter(max_heavy=1)
    gate = threading.Event()
    order = []
    first = c2.submit("copy", "blocker", lambda p, cc: gate.wait(5))
    a = c2.submit("prefetch", "a", lambda p, cc: order.append("a"), priority=8)
    b = c2.submit("upload", "b", lambda p, cc: order.append("b"), priority=5)
    k1 = c2.submit("upload", "k", lambda p, cc: order.append("k"), key="same")
    k2 = c2.submit("upload", "k again", lambda p, cc: order.append("k2"), key="same")
    c2.bump(a, 0)
    gate.set()
    c2.wait_all(5)
    ok("F priority: the bumped task first; a waiting task with the same key is reused",
       order == ["a", "b", "k"] and k1 is k2 and first.state == T.DONE, str(order))

    # the Qt bridge: on_done in the window thread
    T._bridge = None
    cq = T.TaskCenter()
    br = T.qt_bridge(cq)
    where = []
    seen = []
    br.finished.connect(lambda t: seen.append(t.id))
    tq = cq.submit("export", "x", lambda p, cc: 1,
                   on_done=lambda t: where.append(QThread.currentThread() is APP.thread()))
    wait_for(lambda: where and seen, 5)
    ok("F Qt bridge: on_done and 'finished' arrive in the window thread",
       where == [True] and seen == [tq.id], str(where))
    T._bridge = None
    T.qt_bridge()                                    # the program's center again
    ok("F time left / speed from the progress", ts[1].summary() == "done"
       and T.fmt_seconds(130) == "2 min" and T.human_bytes(2.5e9) == "2.5 GB")


# ========================================================== G copy_file
def part_g():
    d = OUT / "copies"
    d.mkdir()
    src = d / "movie.nd2"
    src.write_bytes(os.urandom(5_000_000))
    seen = {}

    def watch(path, attempt, done):
        if done and not seen:
            seen["final"] = (d / "out" / "movie.nd2").exists()
            seen["partial"] = [p.name for p in (d / "out").iterdir()]
        return None
    X.TEST_HOOKS.update(fault=watch, chunk_delay=0.01)
    r = X.copy_file(src, d / "out" / "movie.nd2", chunk=1_000_000)
    X.TEST_HOOKS.clear()
    ok("G while copying only a hidden partial file exists - never the real name",
       seen.get("final") is False and len(seen["partial"]) == 1
       and seen["partial"][0].startswith(".movie.nd2.")
       and seen["partial"][0].endswith(".peterpiper-partial"), str(seen))
    ok("G ... then the real name, same bytes and time, checksum checked",
       (d / "out" / "movie.nd2").read_bytes() == src.read_bytes() and r.hashed
       and abs((d / "out" / "movie.nd2").stat().st_mtime - src.stat().st_mtime) < 0.01
       and len(list((d / "out").iterdir())) == 1)

    tries = []

    def locked(path, attempt, done):
        tries.append(attempt)
        if attempt <= 3 and done >= 2_000_000:
            e = OSError(13, "The process cannot access the file (Box Drive)")
            e.winerror = 32
            return e
        return None
    X.TEST_HOOKS["fault"] = locked
    t0 = time.monotonic()
    r = X.copy_file(src, d / "locked" / "movie.nd2", chunk=1_000_000, backoff=0.05)
    X.TEST_HOOKS.clear()
    ok("G a file locked by the sync app: tried again with growing waits until it works",
       r.attempts == 4 and (d / "locked" / "movie.nd2").read_bytes() == src.read_bytes()
       and time.monotonic() - t0 >= 0.05 + 0.1 + 0.2
       and len(list((d / "locked").iterdir())) == 1, f"{r.attempts} tries")

    X.TEST_HOOKS["fault"] = lambda p, a, done: OSError(5, "I/O error (device gone)") \
        if done >= 1_000_000 else None
    try:
        X.copy_file(src, d / "broken" / "movie.nd2", chunk=1_000_000, retries=2, backoff=0.01)
        failed = False
    except OSError as exc:
        failed = "I/O" in str(exc)
    X.TEST_HOOKS.clear()
    ok("G a lasting error: raised after the tries, no partial file left",
       failed and list((d / "broken").iterdir()) == [])

    stop = threading.Event()
    X.TEST_HOOKS.update(chunk_delay=0.02)
    X.TEST_HOOKS["fault"] = lambda p, a, done: (stop.set() if done >= 2_000_000 else None)
    try:
        X.copy_file(src, d / "cancel" / "movie.nd2", cancelled=stop.is_set, chunk=1_000_000)
        cancelled = False
    except T.Cancelled:
        cancelled = True
    X.TEST_HOOKS.clear()
    ok("G cancelled: stops, the partial file removed", cancelled
       and list((d / "cancel").iterdir()) == [])

    other = d / "out2"
    other.mkdir()
    (other / "movie.nd2").write_bytes(b"someone else's file")
    r = X.copy_file(src, other / "movie.nd2")
    ok("G overwrite=False: a different file of that name is kept; the copy gets _2",
       (other / "movie.nd2").read_bytes() == b"someone else's file"
       and Path(r.dst).name == "movie_2.nd2")
    r2 = X.copy_file(src, other / "movie.nd2")
    ok("G ... an identical copy already there is skipped", r2.skipped
       and Path(r2.dst).name == "movie_2.nd2")
    ok("G is_transient: locked / time-out / cloud errors yes; missing file, disk full no",
       X.is_transient(PermissionError(13, "x")) and X.is_transient(TimeoutError())
       and X.is_transient(_win(362)) and not X.is_transient(FileNotFoundError(2, "x"))
       and not X.is_transient(OSError(28, "No space left")))

    # keep_copy (1.2.2 'Also keep a copy in') retries a locked file too
    out = d / "OUTPUT_m" / ME
    out.mkdir(parents=True)
    (out / "m_ROIs.npz").write_bytes(b"rois" * 1000)
    calls = []
    real = cloud._copy_one

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError(13, "locked")
        return real(*a, **k)
    cloud._copy_one = flaky
    try:
        rep = cloud.keep_copy(d / "m.nd2", out, d / "second")
    finally:
        cloud._copy_one = real
    ok("G keep_copy: a locked file is tried again (copied, nothing failed)",
       rep.ok and len(rep.copied) == 1 and len(calls) == 2, rep.summary())


def _win(n):
    e = OSError(22, "cloud")
    e.winerror = n
    return e


# =========================================================== H the cache
def part_h():
    server = BOX / "Lab share" / "PeterPiper lab" / "Data"
    server.mkdir(parents=True, exist_ok=True)
    movies = []
    for i in range(4):
        p = server / f"movie {i}.nd2"
        p.write_bytes(os.urandom(3_000_000))
        movies.append(p)
    local_movie = OUT / "local movie.nd2"
    local_movie.write_bytes(b"x" * 1000)
    X.TEST_HOOKS["needs_fetch"] = lambda p: "Data" in p
    UP.set_server_option("cache_dir", str(OUT / "cache"))
    UP.set_server_option("cache_limit_gb", 0.007)          # 7 MB: two movies
    c = T.TaskCenter()
    t = X.fetch_movie(movies[0], c)
    again = X.fetch_movie(movies[0], c)
    t.wait(10)
    local = Path(str(t.result))
    ok("H fetch_movie: copied into the cache, same bytes; asked twice -> one task",
       t.state == T.DONE and local.is_file() and local.read_bytes() == movies[0].read_bytes()
       and str(OUT / "cache") in str(local) and again is t and local.name == "movie 0.nd2",
       f"{t.state} {t.error}")
    m1 = local.stat().st_mtime_ns
    t2 = X.fetch_movie(movies[0], T.TaskCenter())
    t2.wait(5)
    ok("H the same movie again: the cached copy is reused (not copied again)",
       Path(str(t2.result)) == local and local.stat().st_mtime_ns == m1
       and X.cached_copy(movies[0]) == str(local))
    ok("H server_path_of / local_movie", X.server_path_of(local) == str(movies[0])
       and X.local_movie(movies[0]) == str(local))
    time.sleep(0.05)
    movies[0].write_bytes(os.urandom(3_000_000))
    ok("H the original changed -> the cached copy is not used", X.cached_copy(movies[0]) is None)
    t3 = X.fetch_movie(movies[0], T.TaskCenter())
    t3.wait(10)
    ok("H ... fetched again", Path(str(t3.result)).read_bytes() == movies[0].read_bytes())
    t4 = X.fetch_movie(local_movie, T.TaskCenter())
    t4.wait(5)
    ok("H a movie on this computer is not copied (opened where it is)",
       t4.result == str(local_movie) and t4.data.get("quiet"))
    X.pin(t3.result)
    c = T.TaskCenter()
    for m in movies[1:3]:
        X.fetch_movie(m, c).wait(10)
    size = X.cache_size()
    names = sorted(Path(e["local"]).name for e in X._load_index(X.cache_dir()).values())
    ok("H over the limit: the least recently used removed - never the open (pinned) one",
       size <= 7_000_000 and "movie 0.nd2" in names and "movie 2.nd2" in names
       and "movie 1.nd2" not in names, f"{size} {names}")
    X.unpin(t3.result)
    freed, removed = X.cleanup_cache(0)
    ok("H cleanup to 0: only the cache's own files removed; the originals untouched",
       removed == 2 and X.cache_size() == 0 and all(m.is_file() for m in movies)
       and (OUT / "cache" / X.CACHE_INDEX).is_file())
    X.TEST_HOOKS["free"] = 2_000_000
    t5 = X.fetch_movie(movies[3], T.TaskCenter())
    t5.wait(5)
    X.TEST_HOOKS.pop("free")
    ok("H too little space: a clear failure", t5.state == T.FAILED and "space" in t5.error,
       t5.error)
    UP.set_server_option("cache_limit_gb", 0.0)
    ok("H automatic limit = min(50 GB, 20% of free + cache)",
       0 < X.cache_limit_bytes() <= 50e9)

    # the queue
    batchqueue.set_items([str(m) for m in movies[:3]] + [str(local_movie)])
    batchqueue.mark(str(movies[1]), "saved")
    ok("H todo_after: the next ones still to do", batchqueue.todo_after(str(movies[0]), 2)
       == [str(movies[2]), str(local_movie)])
    UP.set_server_option("prefetch", False)
    ok("H prefetch off -> nothing fetched", batchqueue.prefetch_next(str(movies[0])) == [])
    UP.set_server_option("prefetch", True)
    X.TEST_HOOKS["chunk_delay"] = 0.05
    X.TEST_HOOKS["fault"] = None
    pts = batchqueue.prefetch_next(str(movies[0]))
    wait_for(lambda: pts[0].progress, 5)
    words = batchqueue.fetch_words(str(movies[2]))
    ok("H prefetch_next fetches the next one quietly; the queue list says how far",
       len(pts) == 1 and pts[0].kind == "prefetch" and pts[0].priority == 8
       and words.startswith("fetching"), words)
    got = []
    t6 = batchqueue.open_path(str(movies[2]), on_ready=got.append)
    ok("H open_path (Next movie) on the movie being prefetched: the same task, now first",
       t6 is pts[0] and t6.kind == "fetch" and t6.priority == 0)
    X.TEST_HOOKS.pop("chunk_delay")
    t6.wait(10)
    pump(0.2)
    ok("H ... on_ready called with the task; 'ready here' in the list",
       got and got[0] is t6 and batchqueue.fetch_words(str(movies[2])) == "ready here")
    X.TEST_HOOKS.clear()
    batchqueue.clear()


# ============================================================ I uploads
def part_i():
    lab = Path(L.linked_folder())
    pd = lab / "People" / ME
    nd2 = OUT / "movies" / "cells 01.nd2"
    nd2.parent.mkdir(parents=True)
    nd2.write_bytes(b"movie" * 1000)
    out = Path(users.output_dir(str(nd2)))
    (out / "PeterPiper_sessions").mkdir(parents=True)
    (out / "cells 01_ROIs.npz").write_bytes(b"rois")
    (out / "PeterPiper_sessions" / "cells 01_session_1.npz").write_bytes(b"session")
    exp = out / "Export_2026-11-22_10-00-00"
    exp.mkdir()
    (exp / "cells 01.xlsx").write_bytes(b"excel")
    (out / "Raw TIFFs").mkdir()
    (out / "Raw TIFFs" / "t001.tif").write_bytes(b"tiff")
    c = T.TaskCenter()
    ts = X.on_results_written(nd2, out, "export", center=c)
    c.wait_all(20)
    res = pd / "Results" / f"OUTPUT_{nd2.stem}" / ME
    exs = pd / "Exports" / f"OUTPUT_{nd2.stem}" / ME
    ok("I after an export: SAVEs -> People/<me>/Results, exports -> People/<me>/Exports",
       len(ts) == 2 and all(t.state == T.DONE for t in ts)
       and (res / "cells 01_ROIs.npz").read_bytes() == b"rois"
       and (res / "PeterPiper_sessions" / "cells 01_session_1.npz").is_file()
       and (exs / exp.name / "cells 01.xlsx").read_bytes() == b"excel",
       str([(t.state, t.error) for t in ts]))
    ok("I ... exports not among the saves, raw TIFFs in neither, no movie",
       not (res / exp.name).exists() and not (res / "Raw TIFFs").exists()
       and not (exs / "Raw TIFFs").exists() and not (pd / "Movies" / nd2.name).exists())
    ok("I the task says where it went (Open folder)", ts[0].data.get("folder") in
       (str(res), str(exs)))
    (out / "cells 01_ROIs.npz").write_bytes(b"rois changed")
    ts = X.on_results_written(nd2, out, "autosave", center=c)
    c.wait_all(10)
    ok("I an autosave: only the saves, PeterPiper's own earlier copy updated",
       len(ts) == 1 and (res / "cells 01_ROIs.npz").read_bytes() == b"rois changed")
    UP.set_server_option("upload_saves", False)
    UP.set_server_option("upload_exports", False)
    ok("I options off -> nothing uploaded", X.on_results_written(nd2, out, "export",
                                                               center=c) == [])
    UP.set_server_option("upload_saves", True)
    UP.set_server_option("upload_exports", True)
    UP.set_server_option("upload_movies", True)
    ts = X.on_results_written(nd2, out, "save", center=c)
    c.wait_all(10)
    ok("I analysed movies switched on: the .nd2 goes to People/<me>/Movies",
       (pd / "Movies" / nd2.name).read_bytes() == nd2.read_bytes())
    inlab = lab / "Data" / "movie 0.nd2"
    ok("I ... but never a movie that is in the lab folder already",
       inlab.is_file() and X.upload_movie(inlab, center=c) is None)
    UP.set_server_option("upload_movies", False)
    keep = L.link_info()
    L.unlink()
    ok("I no lab folder connected -> nothing", X.on_results_written(nd2, out, "export",
                                                                   center=c) == [])
    L._set_link(**keep)


# ============================================================ J backups
def part_j():
    lab = Path(L.linked_folder())
    UP.set_server_option("last_backup", "")
    ok("J no backup yet -> due", X.backup_due())
    p = Path(X.backup_profile())
    ok("J backup_profile: People/<me>/Backups/PeterPiper backup <me> <date>.zip",
       p.parent == lab / "People" / ME / "Backups" and p.is_file()
       and p.name == f"PeterPiper backup {ME} {datetime.now():%Y-%m-%d}.zip", str(p))
    names = zipfile.ZipFile(p).namelist()
    ok("J ... holds the profile, settings and run list (the user's folder)",
       any(n.endswith("profile.json") for n in names)
       and any(n.endswith("server.json") for n in names), str(names[:8]))
    ok("J ... remembered; not due again today", X.last_backup() and not X.backup_due())
    ok("J ... due after a day", X.backup_due(datetime.now() + timedelta(days=1, minutes=1)))
    p2 = Path(X.backup_profile())
    ok("J one file per day (today's replaced)", p2 == p and
       len(list(p.parent.glob("PeterPiper backup *.zip"))) == 1)
    t = X.backup_task(center=T.TaskCenter())
    t.wait(10)
    ok("J backup as a background task", t.state == T.DONE and Path(t.result).is_file())


# ============================================================== K roles
def part_k():
    from peterpiper import achievements
    ok("K roles offered: User and Admin", users.roles_offered("Ana") == ["user", "admin"])
    users.set_role("Ana", "developer", sync_lab=False)
    ok("K ... a person who has the third role keeps it offered",
       users.roles_offered("Ana") == ["user", "admin", "developer"])
    users.set_role("Ana", "user", sync_lab=False)
    ok("K ... gone again once not", users.roles_offered("Ana") == ["user", "admin"])
    ok("K ... the current user without the extra: two", users.roles_offered("Test User")
       == ["user", "admin"])
    achievements.unlock("crown")
    ok("K ... with it: three", users.roles_offered("Test User") ==
       ["user", "admin", "developer"])
    L.link(L.linked_folder(), include=["Ana"])
    from peterpiper.gui.userdlg import LabSettingsDialog
    dlg = LabSettingsDialog(None, "Test User")
    labels = {}
    for i in range(dlg.lst_people.count()):
        it = dlg.lst_people.item(i)
        name = str(it.data(0x0100))
        dlg.lst_people.setCurrentRow(i)
        dlg._fill_role_menu()
        labels[name] = [a.text() for a in dlg._role_menu.actions()]
    ok("K the lab settings role menu follows the person", labels.get("Ana") == ["User", "Admin"]
       and labels.get("Test User") == ["User", "Admin", "Developer"], str(labels))
    import re
    txt = dlg.btn_role.toolTip()
    ok("K the role menu's hover text names only User and Admin",
       "Developer" not in txt and not re.search(r"crown|click", txt, re.I))
    dlg.close()
    d = achievements._load()
    d.get("found", {}).pop("crown", None)
    achievements._save(d)


# ================================================================ L GUI
def scroll_report(d, w, h):
    bad = []
    if (d.width(), d.height()) != (w, h):
        bad.append(f"window became {d.width()} x {d.height()}")
    for a in d.findChildren(QAbstractScrollArea):
        if a.isVisible() and (a.verticalScrollBar().maximum() > 0
                              or a.horizontalScrollBar().maximum() > 0):
            bad.append(f"{type(a).__name__} scrolls")
    ms = d.layout().totalMinimumSize()
    if ms.height() > h or ms.width() > w:
        bad.append(f"needs at least {ms.width()} x {ms.height()}")
    for wid in d.findChildren(QWidget):
        if wid.isVisible() and not wid.isWindow() and wid.width() > 0:
            r = wid.rect().translated(wid.mapTo(d, wid.rect().topLeft()))
            if r.bottom() > h + 1 or r.right() > w + 1:
                bad.append(f"{type(wid).__name__} reaches {r.right()} x {r.bottom()}")
                break
    return bad


def part_l():
    from peterpiper.gui import serverpanel as SP
    from peterpiper.gui import setup as SU
    from peterpiper.gui import taskstatus as TS
    from peterpiper.gui.serverguide import PAGES, ServerGuide
    TH.apply(APP, "midnight", 10.0)
    L.TEST_HOOKS["processes"] = ["box.exe"]
    L.TEST_HOOKS["free"] = 200e9
    lab = Path(L.linked_folder())
    cloud.set_results_root(lab / "Peter")
    UP.set_server_option("keep_own_results", False)
    for theme in ("midnight", "daylight"):
        TH.apply(APP, theme, 10.0)
        for (w, h) in ((1366, 768), (1366, 698)):
            d = SU.SetupDialog()
            d.resize(w, h)
            d.show()
            d.tabs.setCurrentIndex(2)
            wait_for(lambda: d.server_panel.health is not None, 5)
            pump(0.2)
            bad = scroll_report(d, w, h)
            ok(f"L {theme} {w}x{h}: the 'Lab folder & backup' tab - no scroll bars",
               not bad, "; ".join(bad))
            if w == 1366 and h == 768:
                d.grab().save(str(SHOTS / f"v40_start_lab_tab_{theme}.png"))
            if theme == "midnight" and h == 768:
                p = d.server_panel
                ok("L the tab: green line, the lab folder, own folder noticed, options",
                   p.level() == "green" and "Test lab" in p.lbl_folder.full()
                   and p.own_box.isVisible() and p.chk["upload_saves"].isChecked()
                   and not p.chk["upload_movies"].isChecked()
                   and p.btn_connect.text() == "Change..."
                   and d.tabs.tabText(2) == "Lab folder && backup"
                   and not d.tabs.tabIcon(2).isNull(), p.lbl_health.full())
                ok("L every option has a hover explanation (with a picture)",
                   all("<img" in c.toolTip() for c in p.chk.values())
                   and p.sp_limit.toolTip() and p.btn_connect.toolTip())
                p.chk["upload_movies"].setChecked(True)
                ok("L ... ticking one saves it", UP.server_option("upload_movies") is True)
                p.chk["upload_movies"].setChecked(False)
                p.grab().save(str(SHOTS / "v40_server_panel.png"))
                p._keep_own()
                ok("L 'Keep as is' hides the note (results unchanged)",
                   not p.own_box.isVisible() and cloud.results_root() == str(lab / "Peter"))
                ok("L the task status line in the footer", d.task_status is not None
                   and d.task_status.isVisible() and d.task_status.text() == TS.IDLE,
                   d.task_status.text() if d.task_status else "")
            d.reject()
    TH.apply(APP, "midnight", 10.0)

    # not connected
    keep = L.link_info()
    L.unlink()
    d = SU.SetupDialog()
    d.resize(1366, 768)
    d.show()
    d.tabs.setCurrentIndex(2)
    wait_for(lambda: d.server_panel.health is not None, 5)
    p = d.server_panel
    ok("L not connected: grey line, 'Connect...', backup asks to connect first",
       p.level() == "grey" and p.btn_connect.text() == "Connect..."
       and not p.btn_backup.isEnabled() and "connect" in p.lbl_backup.full()
       and d.tabs.tabIcon(2).isNull())
    d.grab().save(str(SHOTS / "v40_start_not_connected.png"))
    d.reject()

    # the Connect dialog: found labs, walk-up, adopt question, own folder question
    asked = []
    roots = [("Box", str(BOX))]
    cd = SP.ConnectDialog(None, roots=roots)
    cd.show()
    wait_for(lambda: "Found" in cd.lbl_search.text() or "No lab" in cd.lbl_search.text(), 10)
    pump(0.1)
    items = [cd.lst.item(i).text() for i in range(cd.lst.count())]
    ok("L Connect: lab folders found in the sync folder are listed",
       any("Test lab" in t for t in items) and cd.btn_ok.isEnabled(), str(items))
    cd.grab().save(str(SHOTS / "v40_connect_dialog.png"))
    cd._ask = lambda kind, title, text, buttons: asked.append(title) or buttons[0]
    shutil.rmtree(lab / "People" / ME)
    ok("L Connect via a subfolder: walks up, asks before making People/<me>",
       cd.connect_to(str(lab / "Shared" / "Detectors")) and cd.chosen == str(lab)
       and "Your own folder" in asked and (lab / "People" / ME / "Results").is_dir(), str(asked))
    old11 = BOX / "Old lab"
    asked.clear()
    cd2 = SP.ConnectDialog(None, scan=False)
    cd2._ask = lambda kind, title, text, buttons: asked.append(title) or \
        ("Connect without changes" if "earlier" in title else buttons[0])
    ok("L an earlier PeterPiper's lab folder: asked; 'without changes' writes no marker",
       cd2.connect_to(str(old11 / "sub")) and "A lab folder from an earlier PeterPiper"
       in asked and not (old11 / L.MARKER).exists() and L.linked_folder() == str(old11))
    cd3 = SP.ConnectDialog(None, scan=False)
    cd3._ask = lambda kind, title, text, buttons: asked.append(title) or buttons[0]
    nowhere = OUT / "not a lab"
    nowhere.mkdir()
    ok("L not in a lab folder: says so, nothing linked",
       not cd3.connect_to(str(nowhere)) and asked[-1] == "Not a lab folder"
       and L.linked_folder() == str(old11))
    L._set_link(**keep)

    # set up a lab folder
    fresh = BOX / "Lab share" / "Busy folder"
    fresh.mkdir(parents=True)
    (fresh / "someone's file.docx").write_bytes(b"doc")
    res = SP.set_up_lab(None, str(fresh), "New lab",
                        ask=lambda t, x, b: asked.append(t) or b[0])
    ok("L Set up in a folder with other files: a new 'PeterPiper lab' inside it, linked",
       res and Path(res["root"]) == fresh / "PeterPiper lab"
       and (fresh / "someone's file.docx").read_bytes() == b"doc"
       and L.read_marker(fresh / "PeterPiper lab")["lab_name"] == "New lab"
       and L.linked_folder() == str(fresh / "PeterPiper lab")
       and (fresh / "PeterPiper lab" / "People" / ME).is_dir()
       and users.role("Test User") in ("admin", "developer"), str(res))
    L._set_link(**keep)
    L.apply_at_start(force=True)

    # the guide
    g = ServerGuide(None)
    g.show()
    pump(0.1)
    ok("L the guide: 7 pages, each with its picture; Back / Next",
       len(PAGES) == 7 and g.stack.count() == 7 and not g.btn_back.isEnabled()
       and all((REPO / "app" / "peterpiper" / "assets" / "tips" / f"{p}.png").is_file()
               for _t, _x, p in PAGES))
    sizes = []
    for i in range(len(PAGES)):
        g.show_page(i)
        pump(0.05)
        sizes.append((g.width(), g.height()))
        g.grab().save(str(SHOTS / f"v40_guide_{i + 1}.png"))
    ok("L ... fits a 1366 x 768 screen", all(w <= 1366 and h <= 740 for w, h in sizes),
       str(sizes))
    words = " ".join(t + x for t, x, _p in PAGES).lower()
    ok("L ... says which folder to pick, online-only, cache, Windows/Mac, conflicts",
       all(w in words for w in ("not your own subfolder", "online-only", "movie cache",
                                "windows", "(1).xlsx", "sync app not running",
                                "disk full")))
    ok("L ... and never mentions hidden extras", not any(w in words for w in
                                                          ("crown", "logo", "developer")))
    g.close()

    # the task status line and list
    T._bridge = None
    c = T.center()
    T.qt_bridge()
    c.clear_ended()
    c.max_heavy = 6
    w = QWidget()
    w.resize(700, 120)
    btn = TS.TaskStatusButton(w)
    btn.move(10, 80)
    w.show()
    gate = threading.Event()

    def slow(progress, cancelled):
        for i in range(400):
            if cancelled() or gate.is_set():
                break
            progress(None, i * 5_000_000, 2_000_000_000, "big movie.nd2")
            time.sleep(0.01)
        return "x"
    t_up = c.submit("upload", "Uploading saves of cells 01.nd2", slow,
                    data={"folder": str(lab)})
    t_up2 = c.submit("upload", "Uploading exports of cells 01.nd2", slow)
    t_fetch = c.submit("fetch", "Fetching movie 3.nd2", slow)
    t_ex = c.submit("export", "Excel and Prism for cells 01", slow)
    t_bad = c.submit("copy", "Copy to the second folder",
                     lambda p, cc: (_ for _ in ()).throw(OSError("The disk is full")),
                     heavy=False)
    t_done = c.submit("backup", "Backing up your profile", lambda p, cc: "ok",
                      data={"folder": str(lab)}, heavy=False)
    wait_for(lambda: t_bad.finished and t_done.finished and t_up.progress, 5)
    pump(0.5)
    ok("L the status line: '↑ 2 uploading · ↓ 1 fetching · 1 export'",
       btn.text() == "↑ 2 uploading · ↓ 1 fetching · 1 export", btn.text())
    pop = btn.open_list()
    pump(0.4)
    rows = list(pop.rows.values())
    ok("L the list: a bar per task; Cancel on running, Retry on failed, Open folder on done",
       len(rows) == 6 and any(r.task is t_bad and r.btn_retry.isVisibleTo(pop)
                              and "disk is full" in r.lbl_state.text() for r in rows)
       and any(r.task is t_done and r.btn_open.isVisibleTo(pop) for r in rows)
       and any(r.task is t_up and r.btn_cancel.isVisibleTo(pop)
               and "MB/s" in r.lbl_state.text() for r in rows),
       str([(r.task.title, r.lbl_state.text()) for r in rows]))
    pop.grab().save(str(SHOTS / "v40_task_list.png"))
    w.grab().save(str(SHOTS / "v40_task_status_line.png"))
    next(r for r in rows if r.task is t_fetch)._cancel()
    wait_for(lambda: t_fetch.finished, 5)
    ok("L Cancel in the list cancels that task", t_fetch.state == T.CANCELLED)
    gate.set()
    c.wait_all(5)
    c.max_heavy = T.MAX_HEAVY
    pump(0.4)
    ok("L afterwards the line says a task failed", "failed" in btn.text(), btn.text())
    pop._clear()
    pop.hide()

    # waiting for a movie: never blocks
    server = lab / "Data"
    X.TEST_HOOKS["needs_fetch"] = lambda p: "Data" in p
    X.TEST_HOOKS["chunk_delay"] = 0.25
    big = server / "slow movie.nd2"
    big.write_bytes(os.urandom(5 * X.CHUNK))
    got = []
    t0 = time.monotonic()
    mw = TS.wait_for_movie(None, str(big), got.append)
    back = time.monotonic() - t0
    pump(0.6)
    ok("L wait_for_movie returns at once and shows a bar while the movie is copied",
       back < 0.2 and mw is not None and mw.isVisible() and not got, f"{back:.3f} s")
    mw.grab().save(str(SHOTS / "v40_movie_wait.png"))
    ticks = [0]
    tm = __import__("PySide6.QtCore", fromlist=["QTimer"]).QTimer()
    tm.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
    tm.start(20)
    wait_for(lambda: got, 15)
    tm.stop()
    X.TEST_HOOKS.clear()
    ok("L ... the window kept working meanwhile; on_ready gets the cached copy",
       got and Path(got[0]).read_bytes() == big.read_bytes() and ticks[0] > 5
       and not mw.isVisible(), f"{ticks[0]} ticks")
    got2 = []
    mw2 = TS.wait_for_movie(None, str(big), got2.append)
    pump(0.1)
    ok("L ... asked again: no window, at once", mw2 is None and got2 == got)
    cloud.set_results_root(None)


# ================================================================ M speed
def part_m():
    size = int(os.environ.get("PP_SPEED_BYTES", 1_000_000_000))
    r = X.measure_throughput(OUT / "speed", size)
    TIMES["local copy speed (MB/s)"] = round(r["copy_mb_s"], 1)
    TIMES["local write speed (MB/s)"] = round(r["write_mb_s"], 1)
    ok("M copy speed measured, the test files deleted",
       r["copy_mb_s"] > 0 and not list((OUT / "speed").iterdir()), str(r))


def main():
    for part in (part_a, part_b, part_c, part_d, part_e, part_f, part_g, part_h, part_i,
                 part_j, part_k, part_l, part_m):
        try:
            part()
        except Exception as exc:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f"{part.__name__} ran without an error", False, repr(exc))
    for k, v in TIMES.items():
        print(f"TIME {k}: {v if isinstance(v, (int, str)) else round(v, 3)}")
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    for f in FAILS:
        print("  FAILED:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
