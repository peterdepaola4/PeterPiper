"""
Developer test (not shipped): PeterPiper 1.1, part "profiles" - merging profiles,
keeping a profile in step through a folder, the lab's shared folder, roles,
optional passwords and the first window.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v11_profiles.py

Every "computer" is its own PETERPIPER_HOME under _out/v11_profiles; shared and lab
folders are plain folders there (no network). Names are made up.

A) merge two spellings on one computer ('Ana Lopez' keeps, 'A. Lopez' merged): the
   preview says what comes over; settings of the kept one stay (the other's kept
   as a saved setting); runs united (by fingerprint / path); compare colours
   united (kept wins a tie); templates: a differing one kept as '(from ...)';
   auto-detects, achievements, saved-files log, userprefs united; the merged one
   hidden, not deleted (folder still there); its name is an alias: owner_of with
   the old name and OUTPUT_<movie>/<old folder> both count as the kept user's;
   adding the old name brings it back as a separate user.
B) a profile zip "from another computer" merged INTO a differently named user:
   preview, runs added, the zip's name becomes an alias, no new user; the other
   computer's results location (storage.json) is not taken.
C) keep in step through a folder, two fake computers + one shared folder: A's
   profile appears on B (names differ: bound by the folder, aliases both ways);
   B's changes appear on A; changes on both are united (colours, runs - a Mac
   path and a Windows path both kept); the same single setting changed on both:
   the newer wins; a template changed on both: newer keeps the name, older kept
   as '(other copy ...)'; nothing lost; an offline folder is skipped with a note;
   the state file is never copied; the quit hook is installed.
D) lab folder: made on computer L1 (list + profiles in the lab folder), linked on
   L2: L2's list gains L1's users, the spelling 'A. Lopez' maps to 'Ana Lopez'
   (one person, no duplicate), her profile is united through the lab folder; a
   user added on L2 appears on L1 at its next start; a hidden lab member is hidden
   (not deleted); conflict copies of the list are united; a read-only lab folder
   is only read (nothing written, said so); data folders round trip to L2;
   unlink.
E) roles and passwords: the first user is Admin; old users.json without roles ->
   the legacy owner is Admin, others User; Developer has admin abilities; a
   non-admin cannot open Lab settings (API); the last admin cannot be demoted
   (here and in the lab); password set / verify / wrong / reset; only a salted
   hash is stored (the password text is in no file); it reaches another computer
   through the lab folder, and so does the reset.
F) the first window: first start offers the lab link next to Add user; Lab
   settings enabled for an admin only; names decorated by a (stub) name_flair -
   prefix / suffix / bold / colour - while the stored names stay plain, and
   set_target_user follows the selection; no scroll bars at 1366x768 and
   1280x800 in the first window and the merge / sync / lab settings windows;
   screenshots in _out/shots.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v11_profiles"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home_start")
os.environ["PETERPIPER_RESULTS"] = str(OUT / "PeterPiper results")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QDialog,  # noqa: E402
                               QMessageBox)

APP = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

from peterpiper import labshare, profilesync, users                  # noqa: E402
from peterpiper.config import load_settings, save_settings           # noqa: E402

N = [0]
FAILS = []
PW = "Tulip-7342-secret"


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(n=20):
    for _ in range(n):
        APP.processEvents()


def computer(name: str) -> Path:
    """Switch to another fake computer (its own PeterPiper data folder)."""
    users.deactivate()
    h = OUT / f"home_{name}"
    os.environ["PETERPIPER_HOME"] = str(h)
    labshare._last_apply = 0.0
    return h


def jread(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jwrite(p, d):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")


def run_entry(path, saved="2026-11-01T10:00:00"):
    return dict(path=path, saved=saved, kind="saved", tracked=True, n_cells=5, recorded=saved)


def set_gate(v):
    s, _ = load_settings()
    s.gate_snr = float(v)
    save_settings(s)


def runs_of(idx, key):
    return [r["path"] for r in idx.get(key, {}).get("runs", [])]


# ===================================================================== A
def part_a():
    computer("A")
    users.add_user("Ana Lopez")
    users.add_user("A. Lopez")
    users.add_user("Ben")
    users.activate("Ana Lopez")
    set_gate(7)
    h = users.home()
    jwrite(h / "run_history.json", {"fp1": dict(nd2_name="m1.nd2", size=1, paths=["D:/d/m1.nd2"],
                                                runs=[run_entry("D:/d/OUTPUT_m1/Ana Lopez/a.npz")],
                                                last="2026-11-01T10:00:00")})
    jwrite(h / "compare_colours.json", {"names": {"wt": "#111111"}})
    (h / "Prism style templates").mkdir(parents=True, exist_ok=True)
    (h / "Prism style templates" / "look.prism").write_bytes(b"ana look")
    jwrite(h / "achievements.json", {"found": {"palettes": "2026-11-01T09:00:00"}})
    (h / "saved_files_log.jsonl").write_text('{"f": "one"}\n', encoding="utf-8")
    users.activate("A. Lopez")
    set_gate(3)
    h2 = users.home()
    jwrite(h2 / "run_history.json", {
        "fp1": dict(nd2_name="m1.nd2", size=1, paths=["D:/d/m1.nd2"],
                    runs=[run_entry("D:/d/OUTPUT_m1/A. Lopez/b.npz")], last="2026-11-02T10:00:00"),
        "fp2": dict(nd2_name="m2.nd2", size=2, paths=["D:/d/m2.nd2"],
                    runs=[run_entry("D:/d/OUTPUT_m2/A. Lopez/c.npz")], last="2026-11-02T10:00:00")})
    jwrite(h2 / "compare_colours.json", {"names": {"wt": "#999999", "ko": "#222222"}})
    (h2 / "Prism style templates").mkdir(parents=True, exist_ok=True)
    (h2 / "Prism style templates" / "look.prism").write_bytes(b"other look")
    (h2 / "Prism style templates" / "other.prism").write_bytes(b"other")
    jwrite(h2 / "Auto-detect" / "nuclei.json", {"kind": "x", "name": "nuclei"})
    jwrite(h2 / "achievements.json", {"found": {"charlotte": "2026-11-02T09:00:00"}})
    jwrite(h2 / "queue.json", {"items": ["D:/d/m2.nd2"]})
    (h2 / "saved_files_log.jsonl").write_text('{"f": "one"}\n{"f": "two"}\n', encoding="utf-8")
    users.deactivate()
    prev = users.merge_preview("Ana Lopez", "A. Lopez")
    txt = " | ".join(prev)
    ok("A preview: runs, colours, templates, auto-detects, settings rule (nothing changed)",
       "2 run(s) of 2 movie(s)" in txt and "Compare colours: 1 name(s) added" in txt
       and "Prism style templates: 1 added, 1 kept as a second copy" in txt
       and "Auto-detect: 1 added" in txt and "Settings:" in txt
       and not (users.user_dir("Ana Lopez") / "Auto-detect").exists(), txt)
    notes = users.merge_users("Ana Lopez", "A. Lopez")
    users.activate("Ana Lopez")
    h = users.home()
    ok("A settings: the kept user's stay", load_settings()[0].gate_snr == 7.0, str(notes))
    saved = list((h / "Saved settings").glob("Settings of A. Lopez*.json"))
    ok("A ... the merged one's settings kept as a saved setting",
       len(saved) == 1 and jread(saved[0])["analysis"]["gate_snr"] == 3.0)
    idx = jread(h / "run_history.json")
    ok("A runs united by fingerprint / path",
       sorted(runs_of(idx, "fp1")) == ["D:/d/OUTPUT_m1/A. Lopez/b.npz",
                                        "D:/d/OUTPUT_m1/Ana Lopez/a.npz"]
       and runs_of(idx, "fp2") == ["D:/d/OUTPUT_m2/A. Lopez/c.npz"]
       and idx["fp1"]["last"] == "2026-11-02T10:00:00", str(idx))
    col = jread(h / "compare_colours.json")["names"]
    ok("A colours united, the kept one wins a tie", col == {"wt": "#111111", "ko": "#222222"}, str(col))
    tl = sorted(p.name for p in (h / "Prism style templates").iterdir())
    ok("A templates: new copied, a differing one kept beside",
       tl == ["look (from A. Lopez).prism", "look.prism", "other.prism"]
       and (h / "Prism style templates" / "look.prism").read_bytes() == b"ana look", str(tl))
    ok("A auto-detect, achievements, queue, saved-files log united",
       (h / "Auto-detect" / "nuclei.json").exists()
       and set(jread(h / "achievements.json")["found"]) == {"palettes", "charlotte"}
       and jread(h / "queue.json")["items"] == ["D:/d/m2.nd2"]
       and (h / "saved_files_log.jsonl").read_text(encoding="utf-8").splitlines()
       == ['{"f": "one"}', '{"f": "two"}'])
    ok("A merged one hidden, not deleted", "A. Lopez" not in users.list_users()
       and "A. Lopez" in users.all_users() and users.user_dir("A. Lopez").is_dir()
       and (users.user_dir("A. Lopez") / "settings.json").exists())
    ok("A the old name is an alias: files recording it are hers",
       users.owner_of(Path("X:/x.npz"), "A. Lopez") == "Ana Lopez"
       and users.is_mine(Path("X:/x.npz"), "A. Lopez") and "A. Lopez" in users.aliases_of("Ana Lopez"))
    ok("A ... and OUTPUT_<movie>/<old folder> is hers",
       users.owner_of(Path("D:/d/OUTPUT_m1/A. Lopez/PeterPiper_sessions/s.npz")) == "Ana Lopez"
       and users.is_mine(Path("D:/d/OUTPUT_m1/A. Lopez/b.npz")))
    users.deactivate()
    ok("A adding the old name brings it back as a separate user",
       users.add_user("A. Lopez") == "A. Lopez" and "A. Lopez" in users.list_users()
       and users.owner_of(Path("X:/x.npz"), "A. Lopez") == "A. Lopez")
    users.merge_users("Ana Lopez", "A. Lopez")
    ok("A ... and merged again", "A. Lopez" not in users.list_users()
       and users.owner_of(Path("X:/x.npz"), "A. Lopez") == "Ana Lopez")
    try:
        users.merge_users("Ana Lopez", "Ana Lopez")
        same = False
    except ValueError:
        same = True
    ok("A merging a user into itself is refused", same)


# ===================================================================== B
def part_b():
    computer("other")
    users.add_user("Ana")
    users.activate("Ana")
    set_gate(4)
    jwrite(users.home() / "run_history.json", {"fp9": dict(nd2_name="m9.nd2", size=9, paths=[],
                                                           runs=[run_entry("/Users/ana/m9_ROIs.npz")],
                                                           last="2026-11-03T10:00:00")})
    jwrite(users.home() / "storage.json", {"results_root": "/Volumes/Other/results"})
    zp = Path(users.export_profile("Ana", OUT / "ana_other_computer.zip"))
    users.deactivate()
    computer("A")
    name, prev = users.import_preview(zp, into="Ana Lopez")
    ok("B preview of a zip into a differently named user", name == "Ana"
       and any("1 run(s) of 1 movie(s)" in ln for ln in prev), str(prev))
    n_before = len(users.all_users())
    got, notes = users.import_profile(zp, into="Ana Lopez")
    users.activate("Ana Lopez")
    idx = jread(users.home() / "run_history.json")
    ok("B merged into 'Ana Lopez': runs added, no new user, settings kept",
       got == "Ana Lopez" and len(users.all_users()) == n_before
       and runs_of(idx, "fp9") == ["/Users/ana/m9_ROIs.npz"] and runs_of(idx, "fp1")
       and load_settings()[0].gate_snr == 7.0, str(notes))
    ok("B the zip's name is now a spelling of hers",
       users.owner_of(Path("X:/y.npz"), "Ana") == "Ana Lopez")
    ok("B the other computer's results location is not taken",
       not (users.home() / "storage.json").exists()
       or "Volumes" not in (users.home() / "storage.json").read_text(encoding="utf-8"))
    users.deactivate()


# ===================================================================== C
def part_c():
    shared = OUT / "cloud_ana"
    shared.mkdir()
    computer("P1")
    users.add_user("Ana Lopez")
    users.activate("Ana Lopez")
    set_gate(5)
    jwrite(users.home() / "run_history.json", {"fp1": dict(
        nd2_name="m1.nd2", size=1, paths=["C:/d/m1.nd2"],
        runs=[run_entry("C:\\d\\OUTPUT_m1\\Ana Lopez\\a.npz")], last="2026-11-01T10:00:00")})
    jwrite(users.home() / "compare_colours.json", {"names": {"wt": "#111111"}})
    note = profilesync.set_folder("Ana Lopez", shared)
    tgt = shared / "PeterPiper profile - Ana Lopez"
    ok("C the folder holds her profile (exported layout)",
       (tgt / "run_history.json").exists() and (tgt / "settings.json").exists()
       and (tgt / "profile.json").exists() and not (tgt / "sync.json").exists(), note)
    ok("C quit hook installed, status says when", profilesync.install_quit_hook()
       and "last kept in step" in profilesync.status("Ana Lopez"), profilesync.status("Ana Lopez"))
    users.deactivate()
    # ---- computer P2 (the "Mac"): another spelling
    computer("P2")
    users.add_user("A. Lopez")
    users.activate("A. Lopez")
    jwrite(users.home() / "run_history.json", {"fp1": dict(
        nd2_name="m1.nd2", size=1, paths=["/Volumes/d/m1.nd2"],
        runs=[run_entry("/Volumes/d/OUTPUT_m1/Ana Lopez/a.npz")], last="2026-11-02T10:00:00")})
    jwrite(users.home() / "compare_colours.json", {"names": {"ko": "#222222"}})
    found = profilesync.profile_dirs_in(shared)
    ok("C the second computer finds the profile in the folder (other spelling)",
       len(found) == 1 and profilesync.profile_label(found[0]) == "Ana Lopez")
    profilesync.set_folder("A. Lopez", shared, target=found[0])
    h = users.home()
    idx = jread(h / "run_history.json")
    ok("C A's profile appears on B; Mac + Windows paths of a run both kept",
       sorted(runs_of(idx, "fp1")) == sorted(["/Volumes/d/OUTPUT_m1/Ana Lopez/a.npz",
                                               "C:\\d\\OUTPUT_m1\\Ana Lopez\\a.npz"])
       and jread(h / "compare_colours.json")["names"] == {"ko": "#222222", "wt": "#111111"}
       and load_settings()[0].gate_snr == 5.0, str(idx))
    ok("C bound by the folder: her other spelling counts as hers on B",
       users.owner_of(Path("X:/z.npz"), "Ana Lopez") == "A. Lopez")
    (h / "Prism style templates").mkdir(parents=True, exist_ok=True)
    (h / "Prism style templates" / "mac.prism").write_bytes(b"mac look")
    users.deactivate()                                     # sends B's changes
    computer("P1")
    users.activate("Ana Lopez")                            # brings them in
    h = users.home()
    ok("C B's changes appear on A (template, colours, runs)",
       (h / "Prism style templates" / "mac.prism").read_bytes() == b"mac look"
       and "ko" in jread(h / "compare_colours.json")["names"]
       and len(runs_of(jread(h / "run_history.json"), "fp1")) == 2)
    ok("C ... and A's other spelling counts as hers on A",
       users.owner_of(Path("X:/z.npz"), "A. Lopez") == "Ana Lopez")
    # ---- both change while apart
    c = jread(h / "compare_colours.json")
    c["names"]["x1"] = "#333333"
    jwrite(h / "compare_colours.json", c)
    set_gate(11)
    (h / "Prism style templates" / "mac.prism").write_bytes(b"changed on A")
    old = time.time() - 120
    for p in (h / "settings.json", h / "Prism style templates" / "mac.prism"):
        os.utime(p, (old, old))
    users._current = None                                  # leave without syncing
    computer("P2")
    users._current = "A. Lopez"                            # (as if offline: no sync yet)
    h2 = users.home()
    c = jread(h2 / "compare_colours.json")
    c["names"]["x2"] = "#444444"
    jwrite(h2 / "compare_colours.json", c)
    set_gate(12)                                           # B's change is the newer one
    (h2 / "Prism style templates" / "mac.prism").write_bytes(b"changed on B")
    profilesync.sync_user("A. Lopez")
    users._current = None
    computer("P1")
    profilesync.sync_user("Ana Lopez")
    computer("P2")
    profilesync.sync_user("A. Lopez")
    ha, hb = OUT / "home_P1" / "users" / "Ana Lopez", OUT / "home_P2" / "users" / "A. Lopez"
    ca, cb = jread(ha / "compare_colours.json")["names"], jread(hb / "compare_colours.json")["names"]
    ok("C changes on both are united (nothing lost)", ca == cb and {"wt", "ko", "x1", "x2"} <= set(ca),
       str(ca))
    ga = jread(ha / "settings.json")["settings"]["gate_snr"]
    gb = jread(hb / "settings.json")["settings"]["gate_snr"]
    ok("C the same setting changed on both: the newer wins on both", ga == gb == 12.0, f"{ga} {gb}")
    ta = sorted(p.name for p in (ha / "Prism style templates").iterdir())
    tb = sorted(p.name for p in (hb / "Prism style templates").iterdir())
    oc = [n for n in ta if "(other copy" in n]
    ok("C a template changed on both: newer keeps the name, older kept beside",
       ta == tb and len(oc) == 1 and (ha / "Prism style templates" / "mac.prism").read_bytes()
       == b"changed on B" and (ha / "Prism style templates" / oc[0]).read_bytes() == b"changed on A",
       str(ta))
    # ---- the folder offline
    moved = OUT / "cloud_ana_away"
    shared.rename(moved)
    users.add_user("Zed") if "Zed" not in users.all_users() else None
    try:
        note = profilesync.sync_user("A. Lopez")
        raised = False
    except Exception:                                       # noqa: BLE001
        raised, note = True, ""
    ok("C an offline folder is skipped quietly, with a note", not raised and "not reachable" in note
       and "not reachable" in profilesync.status("A. Lopez"), note)
    moved.rename(shared)
    profilesync.turn_off("A. Lopez")
    ok("C turned off: status Off, the folder untouched", profilesync.status("A. Lopez") == "Off"
       and (shared / "PeterPiper profile - Ana Lopez" / "settings.json").exists())
    users.deactivate()


# ===================================================================== D
LAB = OUT / "lab share" / "PeterPiper lab"


def part_d():
    computer("L1")
    users.add_user("Ana Lopez")
    users.add_user("Ben")
    users.activate("Ana Lopez")
    jwrite(users.home() / "compare_colours.json", {"names": {"wt": "#111111"}})
    users.deactivate()
    notes = labshare.create_lab(LAB, ["Ana Lopez", "Ben"], admin="Ana Lopez")
    lst = jread(LAB / labshare.LAB_FILE)
    ppl = {p["name"]: p for p in lst["people"]}
    ok("D lab folder made: the list with the chosen users, the maker is admin",
       set(ppl) == {"Ana Lopez", "Ben"} and ppl["Ana Lopez"]["role"] == "admin"
       and ppl["Ben"]["role"] == "user", str(notes))
    ok("D ... and their profiles are stored in the lab folder too",
       (LAB / labshare.PROFILES_DIR / "PeterPiper profile - Ana Lopez" / "compare_colours.json")
       .exists())
    labshare.lab_add_alias("Ana Lopez", "A. Lopez")
    labshare.add_data_folder("X:/lab/confocal", "Confocal movies")
    # ---- computer L2 has 'A. Lopez' with her own run
    computer("L2")
    users.add_user("A. Lopez")
    users.activate("A. Lopez")
    jwrite(users.home() / "run_history.json", {"fp5": dict(
        nd2_name="m5.nd2", size=5, paths=[], runs=[run_entry("/Volumes/d/m5_ROIs.npz")],
        last="2026-11-04T10:00:00")})
    users.deactivate()
    labshare.link(LAB, include=["A. Lopez"])
    ok("D linked on L2: L2's list gains L1's users, one person for two spellings",
       sorted(users.list_users()) == ["A. Lopez", "Ben"], str(users.list_users()))
    ok("D ... the lab name counts as the L2 user", users.owner_of(Path("X:/q.npz"), "Ana Lopez")
       == "A. Lopez" and len([p for p in labshare.people() if "lopez" in p["name"].lower()]) == 1)
    ok("D data folders round trip to the second computer",
       ("Confocal movies", "X:/lab/confocal") in labshare.data_folders(), str(labshare.data_folders()))
    users.activate("A. Lopez")
    h = users.home()
    ok("D her profile is united through the lab folder (L1's colour on L2)",
       jread(h / "compare_colours.json")["names"].get("wt") == "#111111")
    users.add_user("Cara")
    ok("D a user added on L2 is added to the lab list",
       "Cara" in [p["name"] for p in labshare.people()])
    users.deactivate()                                       # L2's run goes to the lab folder
    computer("L1")
    added = users.adopt_copied_profiles()
    ok("D ... and appears on L1 at its next start", "Cara" in users.list_users() and "Cara" in added,
       str(added))
    users.activate("Ana Lopez")
    ok("D L2's run reaches L1 through the lab folder",
       runs_of(jread(users.home() / "run_history.json"), "fp5") == ["/Volumes/d/m5_ROIs.npz"])
    users.deactivate()
    # hidden by the lab list: hidden here, never deleted
    labshare.lab_set_hidden("Cara", True)
    computer("L2")
    users.adopt_copied_profiles()
    ok("D a person hidden in the lab list is hidden on L2 (not deleted)",
       "Cara" not in users.list_users() and "Cara" in users.all_users())
    # a conflict copy made by a cloud app is united
    data = jread(LAB / labshare.LAB_FILE)
    data["people"].append(dict(name="Dee", aliases=[], role="user", changed="2026-11-05T10:00:00",
                               added="2026-11-05T10:00:00"))
    jwrite(LAB / "PeterPiper lab users (1).json", data)
    labshare._last_apply = 0.0
    users.adopt_copied_profiles()
    ok("D a cloud conflict copy of the list is united", "Dee" in users.list_users())
    # ---- read-only lab folder, on computer L3
    real = labshare.writable
    labshare.writable = lambda f: False
    try:
        computer("L3")
        before = (LAB / labshare.LAB_FILE).read_bytes()
        n_prof = len(list((LAB / labshare.PROFILES_DIR).iterdir()))
        notes = labshare.link(LAB)
        users.add_user("Eve")
        users.activate("Ben")
        users.deactivate()
        ok("D read-only lab folder: read (users appear), nothing written, said so",
           "Ben" in users.list_users() and (LAB / labshare.LAB_FILE).read_bytes() == before
           and len(list((LAB / labshare.PROFILES_DIR).iterdir())) == n_prof
           and "read-only" in labshare.status() and any("read-only" in n for n in notes),
           labshare.status())
        labshare.unlink()
        ok("D unlink: not linked, users stay", labshare.status() == "not linked"
           and "Ben" in users.list_users())
    finally:
        labshare.writable = real


# ===================================================================== E
def part_e():
    computer("E")
    users.add_user("Solo")
    users.add_user("Pat")
    ok("E the first user is Admin, the next User", users.role("Solo") == "admin"
       and users.role("Pat") == "user")
    try:
        users.set_role("Solo", "user")
        refused = False
    except ValueError:
        refused = True
    ok("E the last admin cannot be demoted", refused and users.is_admin("Solo"))
    ok("E a non-admin cannot open Lab settings (API)", not users.can_manage_lab("Pat")
       and users.can_manage_lab("Solo"))
    try:
        labshare.require_admin("Pat")
        denied = False
    except PermissionError:
        denied = True
    ok("E ... require_admin refuses a non-admin", denied)
    users.set_role("Pat", "developer")
    ok("E Developer: a title only, admin abilities", users.role_label("Pat") == "Developer"
       and users.is_admin("Pat") and users.can_manage_lab("Pat"))
    users.set_role("Solo", "user")
    ok("E ... with a developer, the first admin can become a user", users.role("Solo") == "user")
    # old users.json without roles
    computer("old")
    jwrite(OUT / "home_old" / "users.json", {"users": ["Old", "Newer"], "legacy_owner": "Old"})
    ok("E old users.json: the legacy owner is Admin, others User",
       users.role("Old") == "admin" and users.role("Newer") == "user")
    jwrite(OUT / "home_old" / "users.json", {"users": ["First", "Second"]})
    ok("E ... without a legacy owner: the first user", users.role("First") == "admin"
       and users.role("Second") == "user")
    # passwords, through the lab
    computer("L1")
    labshare.link(LAB)
    users.set_password("Ben", PW)
    ok("E password: set, right one accepted, wrong refused", users.has_password("Ben")
       and users.check_password("Ben", PW) and not users.check_password("Ben", "tulip")
       and users.check_password("Ana Lopez", "anything"))
    rec = users.password_record("Ben")
    ok("E only a salted hash is stored", rec.get("algo") == "pbkdf2_sha256" and len(rec["salt"]) == 32
       and rec["n"] >= 100_000 and PW not in json.dumps(rec))
    labp = next(p for p in labshare.people() if p["name"] == "Ben")
    ok("E ... and it is in the lab list (hash only)", labp["password"].get("hash") == rec["hash"])
    computer("L2")
    labshare.link(LAB)
    ok("E the password reaches the other computer", users.has_password("Ben")
       and users.check_password("Ben", PW) and not users.check_password("Ben", "x"))
    users.set_password("Ben", "")                      # no lab admin needed for one's own
    labshare.lab_clear_password("Ben")
    computer("L1")
    users.adopt_copied_profiles()
    ok("E reset (cleared) on L2 -> no password on L1 either", not users.has_password("Ben"))
    users.set_password("Ana Lopez", PW)
    ok("E an admin with a password: Lab settings needs it",
       not users.can_manage_lab("Ana Lopez") and not users.can_manage_lab("Ana Lopez", "nope")
       and users.can_manage_lab("Ana Lopez", PW))
    users.clear_password("Ana Lopez")
    try:
        labshare.lab_set_role("Ana Lopez", "user")
        lab_refused = False
    except ValueError:
        lab_refused = True
    ok("E the lab's last admin cannot be demoted", lab_refused)
    labshare.lab_set_role("Ben", "developer")
    labshare.lab_set_role("Ana Lopez", "user")
    labshare.lab_set_role("Ana Lopez", "admin")
    computer("L2")
    users.adopt_copied_profiles()
    ok("E roles reach the other computer", users.role("Ben") == "developer")
    # the password text is in no file
    leaked = [str(p) for p in OUT.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl")
              and PW in p.read_text(encoding="utf-8", errors="replace")]
    ok("E the password text is in no file", not leaked, str(leaked))
    users.deactivate()


# ===================================================================== F
def _no_scroll(w) -> list:
    bad = []
    for sa in w.findChildren(QAbstractScrollArea):
        if not sa.isVisible():
            continue
        if sa.verticalScrollBar().maximum() > 0 or sa.horizontalScrollBar().maximum() > 0:
            bad.append(type(sa).__name__ + ":" + (sa.objectName() or ""))
    return bad


def _fits(w, size) -> tuple:
    """The window at the screen size's limits: no scroll bars, not larger than the screen."""
    w.show()
    pump(10)
    sh = w.sizeHint()
    w.resize(min(max(w.width(), sh.width()), size[0]), min(max(w.height(), sh.height()), size[1] - 60))
    pump(20)
    bad = _no_scroll(w)
    return (not bad and w.height() <= size[1] - 60 and w.width() <= size[0]
            and w.minimumSizeHint().height() <= size[1] - 60), bad


def part_f():
    from peterpiper import achievements
    from peterpiper.gui import theme as TH
    from peterpiper.gui import userdlg as UD
    from peterpiper.gui import widgets as W
    TH.apply(APP, "midnight", 11.0)
    computer("first")
    d = UD.UserDialog()
    d.show()
    pump(20)
    ok("F first start: 'Link to your lab's shared folder' next to Add user",
       d.row_first.isVisible() and d.btn_lab_first.isVisible() and d.btn_add.isVisible()
       and d.findChild(W.LogoLabel) is not None)
    d.grab().save(str(SHOTS / "v11_who_first_start.png"))
    d.close()
    computer("L1")
    # stub flair (part looks provides the real one)
    calls = []
    old_nf = getattr(achievements, "name_flair", None)
    old_st = getattr(achievements, "set_target_user", None)
    achievements.name_flair = lambda u: {"prefix": "\U0001F578 ", "suffix": " *", "bold": True,
                                         "colour": "#3a8fd8", "tier": 2}
    achievements.set_target_user = lambda u: calls.append(u)
    try:
        d = UD.UserDialog()
        d.show()
        pump(20)
        items = [d.list.item(i) for i in range(d.list.count())]
        it = next(i for i in items if i.data(256) == "Ana Lopez")
        ok("F names decorated (prefix, suffix, bold, colour), stored names plain",
           it.text().startswith("\U0001F578 Ana Lopez *") and it.font().bold()
           and it.foreground().color().name() == "#3a8fd8"
           and "Ana Lopez" in users.list_users()
           and all(u == u.strip() and "*" not in u for u in users.all_users()), it.text())
        ok("F the role shows discreetly next to an admin's name", "Admin" in it.text()
           and "Admin" not in next(i for i in items if i.data(256) == "Dee").text())
        d.list.setCurrentItem(it)
        pump(5)
        ok("F Lab settings enabled for an admin", d.btn_lab.isEnabled() and calls[-1] == "Ana Lopez")
        dee = next(i for i in items if i.data(256) == "Dee")
        d.list.setCurrentItem(dee)
        pump(5)
        ok("F ... disabled for a non-admin; set_target_user follows the selection",
           not d.btn_lab.isEnabled() and calls[-1] == "Dee")
        d.list.setCurrentItem(it)
        for size in ((1366, 768), (1280, 800)):
            fits, bad = _fits(d, size)
            ok(f"F first window: no scroll bars at {size[0]}x{size[1]}", fits, str(bad))
        d.grab().save(str(SHOTS / "v11_who_is_using.png"))
        TH.apply(APP, "daylight", 11.0)
        pump(10)
        d.grab().save(str(SHOTS / "v11_who_is_using_light.png"))
        TH.apply(APP, "midnight", 11.0)
        d.done(QDialog.Rejected)
        ok("F closing the window clears the target user", calls[-1] is None)
        # merge / sync / lab settings windows
        md = UD.MergeDialog(None, "Ana Lopez")
        sd = UD.SyncDialog(None, "Ana Lopez")
        sd.set_folder(str(OUT / "cloud_ana"))
        ld = UD.LabSettingsDialog(None, "Ana Lopez")
        for name, w in (("merge", md), ("sync", sd), ("lab_settings", ld)):
            res = [_fits(w, s) for s in ((1366, 768), (1280, 800))]
            ok(f"F {name} window: no scroll bars at 1366x768 and 1280x800",
               all(r[0] for r in res), str(res))
            w.grab().save(str(SHOTS / f"v11_{name}.png"))
            w.close()
        ok("F merge window: Keep / Merge into it / summary", md.cmb_keep.count() >= 2
           and "into" in md.lbl_sum.text())
        ok("F lab settings lists the lab's people and data folders",
           ld.lst_people.count() >= 3 and ld.lst_data.count() >= 1)
        # a non-admin's merge window only keeps their own profile
        md2 = UD.MergeDialog(None, "Dee")
        ok("F a non-admin merges only into their own profile", md2.cmb_keep.count() == 1
           and md2.cmb_keep.currentText() == "Dee")
        md2.close()
    finally:
        if old_nf is None:
            delattr(achievements, "name_flair")
        else:
            achievements.name_flair = old_nf
        if old_st is None:
            delattr(achievements, "set_target_user")
        else:
            achievements.set_target_user = old_st
    d = UD.UserDialog()
    d.show()
    pump(10)
    ok("F without name_flair the names are plain", d.list.item(0).text().split("   ")[0]
       == d.list.item(0).data(256))
    d.close()
    users.deactivate()


def main():
    for part in (part_a, part_b, part_c, part_d, part_e, part_f):
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
