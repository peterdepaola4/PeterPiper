"""
Developer test (not shipped): PeterPiper 1.2.1 - "Keep in step" never makes a second
copy of a profile inside the lab folder (profilesync.lab_conflict, gui/userdlg.SyncDialog).

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v121_sync.py

A) the lab folder and a folder inside it are refused (also a folder with a lab list
   that is not linked); a folder of one's own, or one holding the lab folder, is accepted.
B) an older setting that points at the lab folder is not used any more: syncing
   writes no second copy, says why, and the lab folder's copy is still kept in step.
C) the window: says the lab folder already keeps the profile in step, and refuses the
   lab folder when it is chosen (a message, the folder not taken).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v121_sync"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

APP = QApplication(sys.argv)
from peterpiper import labshare, profilesync as PS, users            # noqa: E402

N = [0]
FAILS = []


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


CLOUD = OUT / "Box" / "Lab Box"
LAB = CLOUD / "PeterPiper Repository"
OWN = OUT / "Box" / "My PeterPiper"


def setup():
    users.add_user("Ana")
    LAB.mkdir(parents=True)
    OWN.mkdir(parents=True)
    labshare.create_lab(LAB, ["Ana"], "Ana")


def part_a():
    ok("A the lab is linked", bool(labshare.linked_folder())
       and labshare.profile_target("Ana") is not None)
    ok("A the lab folder is refused", PS.lab_conflict(LAB) is not None)
    ok("A a folder inside it is refused", PS.lab_conflict(LAB / "PeterPiper profiles") is not None)
    ok("A a folder holding it is fine (the copy lands beside the lab folder, not in it)",
       PS.lab_conflict(CLOUD) is None)
    ok("A the same folder written another way is refused",
       PS.lab_conflict(str(LAB).upper() + os.sep) is not None if os.name == "nt" else True)
    other = OUT / "Other lab"
    other.mkdir()
    (other / labshare.LAB_FILE).write_text("{}", encoding="utf-8")
    ok("A a folder with a lab list (not linked) is refused", PS.lab_conflict(other / "x") is not None)
    ok("A a folder of one's own is fine", PS.lab_conflict(OWN) is None)
    try:
        PS.set_folder("Ana", LAB)
        ok("A set_folder refuses the lab folder", False)
    except ValueError as exc:
        ok("A set_folder refuses the lab folder", "lab" in str(exc).lower())
    ok("A ... and nothing was written", not (LAB / ("PeterPiper profile - Ana")).exists()
       and PS.status("Ana") == "Off")
    note = PS.set_folder("Ana", OWN)
    ok("A a folder of one's own is used", (OWN / "PeterPiper profile - Ana").is_dir()
       and "your folder" in note, note)
    PS.turn_off("Ana")


def part_b():
    st = PS.load_state("Ana")                    # as 1.2.0 could leave it
    st["folder"], st["target"] = str(LAB), str(LAB / "PeterPiper profile - Ana")
    PS.save_state("Ana", st)
    (users.user_dir("Ana") / "settings.json").write_text('{"x": 1}', encoding="utf-8")
    note = PS.sync_user("Ana")
    ok("B an older lab-folder setting writes no second copy",
       not (LAB / "PeterPiper profile - Ana").exists(), note)
    ok("B ... and says why", "lab folder" in note and "not used" in note, note)
    lab_copy = LAB / labshare.PROFILES_DIR / "PeterPiper profile - Ana"
    ok("B the lab folder's copy is still kept in step",
       (lab_copy / "settings.json").is_file(), note)
    PS.turn_off("Ana")


def part_c():
    from peterpiper.gui import userdlg as UD
    seen = []
    QMessageBox.information = staticmethod(lambda *a, **k: seen.append(a[2]) or QMessageBox.Ok)
    d = UD.SyncDialog(None, "Ana")
    ok("C the window says the lab folder keeps the profile in step",
       not d.lbl_lab.isHidden() and "lab folder" in d.lbl_lab.text())
    d.set_folder(str(LAB))
    ok("C choosing the lab folder is refused with a message",
       d.folder != str(LAB) and seen and "lab" in seen[-1].lower())
    d.set_folder(str(OWN))
    ok("C a folder of one's own is taken", d.folder == str(OWN))
    d.close()


def main():
    try:
        setup()
    except Exception as exc:                                       # noqa: BLE001
        ok("setup", False, repr(exc))
        return 1
    for part in (part_a, part_b, part_c):
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
