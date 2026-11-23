"""
Developer test (not shipped): PeterPiper 1.2 part "export" - pick the export folder
in the export list, long paths (shorten names / another folder / turn Windows'
long paths on), batch exports, and Compare's Close button. Synthetic movie only
(dev_tests/data/synthetic_movie.npz), made-up deep folder names under _out. The
real Windows elevation is NEVER run (PETERPIPER_NO_ELEVATE is set and every test
uses a fake); the registry is only read through a fake.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v12_export.py

A) the path maths (exportpaths): cutting the middle keeps the start and the end,
   the short folder name, Excel / Explorer limits, shorter names that make every
   path <= 218 (else <= 259), names stay unique, the distinguishing end kept, an
   unreachable folder says so; the planned paths are exactly the files a real
   export writes (same names, same longest length).
B) 'Save in' in the export list: the usual folder shown, Change... (a fake folder
   dialog) sends EVERY output (Excel, Prism, Prism graphs, CSV, PNG, ROI pictures,
   ROI .npz, methods text) to <chosen>/Export_..., the export log and the
   'exported' event name that folder, the run's autosave stays in the movie's
   results folder; a folder that cannot be written is refused in plain words;
   'Usual folder' goes back; the choice is kept for the next export.
C) the long-path warning (long paths faked off): its buttons (Shorten names for me
   = default, Choose another folder..., Turn on Windows long paths, Export anyway,
   Cancel), the new name and longest path shown first; Shorten writes every file
   within the limit with the end of the name kept; Export anyway keeps the names;
   Cancel writes nothing; another folder (an unwritable one refused first); Turn on
   (fake elevation: approved -> on, Excel limit still told; declined -> 'Not
   changed' with the IT setting's name); long paths on / not readable (a Mac): no
   warning.
D) syscheck: turn_on_long_paths with fakes (the command, the texts), the real
   elevation refuses while PETERPIPER_NO_ELEVATE is set; the Computer check window
   offers 'Turn on Windows long paths' and looks again after it.
E) batch: analyse_one shortens by itself (no dialog) and says so in the log's
   Messages; a chosen export folder gets one subfolder per movie; the run stays
   in the movie's results folder; the batch window's 'Save exports in' row.
F) Compare: a Close button at the bottom right does what the X does (closeEvent,
   rejected, exec() returns).
G) no scroll bars at 1366 x 768 in the windows touched; screenshots in _out/shots.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))
os.environ["PETERPIPER_NO_ELEVATE"] = "1"         # belt and braces: never ask Windows
from peterpiper.safety import long_path, plain_path                 # noqa: E402

OUT = REPO / "_out" / "v12_export"
SHOTS = REPO / "_out" / "shots"
if OUT.exists():
    shutil.rmtree(long_path(OUT))
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox  # noqa: E402

app = QApplication(sys.argv)
BOXES = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (BOXES.append(a[1:3]),
                                                           QMessageBox.Ok)[1]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

import synthmovie as SM                                                # noqa: E402
from peterpiper import exportpaths as E                                # noqa: E402
from peterpiper import syscheck as SC                                  # noqa: E402
from peterpiper.config import Settings                                 # noqa: E402
from peterpiper.gui import theme as TH                                 # noqa: E402

TH.apply(app, "midnight", 10.0)
FAILS: list = []
N = [0]
REAL_READ = SC.long_paths_enabled
REAL_ELEVATE = SC.run_elevated


def ok(name, cond, extra=""):
    N[0] += bool(cond)
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.005)


def wait(w, limit=180):
    t = time.time()
    pump(0.1)
    while (w._busy_now() or w.bg_busy() or w.retracking()) and time.time() - t < limit:
        pump(0.05)
    pump(0.3)


def files_in(folder) -> list:
    out = []
    for root, _d, fs in os.walk(long_path(folder)):
        out += [plain_path(os.path.join(root, f)) for f in fs]
    return out


def deep_root(base: Path, total: int) -> Path:
    """A made-up folder path of about `total` characters (folders of <= 40)."""
    p, i = str(base), 0
    while len(p) < total - 1:
        room = min(40, total - len(p) - 1)
        p = p + os.sep + (f"Project_{i}_" + "lab_results_folder_xxxxxxxxxxxxxxx")[:max(1, room)]
        i += 1
    return Path(p)


class FakeRegistry:
    """Stands in for Windows' long-path setting (never the real registry)."""

    def __init__(self, on=False, approve=True):
        self.on, self.approve, self.calls = on, approve, []

    def read(self):
        return self.on

    def elevate(self, command, poll=None):
        self.calls.append(command)
        if not self.approve:
            raise OSError(None, "Windows' administrator approval was not given", None, 1223)
        self.on = True
        return 0


def use_registry(reg):
    SC.long_paths_enabled = reg.read
    SC.run_elevated = reg.elevate


def real_registry():
    SC.long_paths_enabled = REAL_READ
    SC.run_elevated = REAL_ELEVATE


# ===================================================================== A
def part_a():
    print("\n=== A) path maths ===", flush=True)
    ok("A cut_middle keeps the start and the end", E.cut_middle("experiment_long_name_dish3", 14)
       == "exper..._dish3")
    ok("A cut_middle: short names unchanged", E.cut_middle("dish3", 14) == "dish3")
    ok("A cut_middle: at most n characters", all(len(E.cut_middle("x" * 50, n)) <= n
                                                for n in range(1, 50)))
    import datetime as dt
    when = dt.datetime(2026, 11, 16, 14, 30, 5)
    ok("A export folder names", E.export_folder_name(when) == "Export_2026-11-16_14-30-05"
       and E.export_folder_name(when, short=True) == "Export_261116-1430"
       and E.is_short_folder("Export_261116-1430")
       and not E.is_short_folder("Export_2026-11-16_14-30-05"))
    ok("A limits: Excel 218, Explorer 259", E.EXCEL_MAX == 218 and E.WINDOWS_MAX == 259)
    ok("A too_long: a workbook over 218, anything over 259",
       E.too_long(["C:\\" + "a" * 220 + ".xlsx", "C:\\" + "a" * 220 + ".prism",
                   "C:\\" + "a" * 260 + ".png"])
       == ["C:\\" + "a" * 220 + ".xlsx", "C:\\" + "a" * 260 + ".png"])
    comps = {"nucleus": dict(label="Nucleus", name="nucleus",
                             sheets=["dRR_GFP_over_Cy5", "dFF_GFP", "BgSub_GFP"],
                             prism=["dRR_GFP_over_Cy5", "dFF_GFP"]),
             "ring": dict(label="Perinuclear ring", name="ring",
                          sheets=["dRR_GFP_over_Cy5", "dFF_GFP"], prism=["dFF_GFP"])}
    keys = ["nucleus|excel", "nucleus|prism", "nucleus|prismgraph", "nucleus|csv",
            "nucleus|graph|dFF_GFP", "nucleus|roi_every", "nucleus|drift", "ring|excel",
            "ring|prismgraph", "*|methods", "*|roifile", "*|tiffs"]
    stem = "Experiment_2026_condition_A_treated_10uM_dish3"

    def rel(st, tg):
        return E.relative_paths(keys, comps, st, tg, "movie_x", ["Cy5", "GFP"], 60, 0, (2, 9))
    ok("A relative paths: names as the export writes them",
       "Nucleus/Prism graphs/" + stem + "_nucleus_R-R0_GFP-Cy5.prism" in rel(stem, stem)
       and "Perinuclear ring/" + stem + "_ring.xlsx" in rel(stem, stem)
       and "Nucleus/ROI pictures/nucleus_ROIs_t51_check.png" in rel(stem, "")
       and "Raw TIFFs/movie_x_GFP_t060.tif" in rel(stem, ""))
    for total in (110, 130, 150, 175):
        root = deep_root(OUT / "math", total)
        f = E.shorter_names(root, rel, stem, stem, when)
        paths = E.full_paths(root, f.folder_name, rel(f.stem, f.tag))
        lim = 218 if f.limit == 218 else 259
        ok(f"A root {len(str(root))}: every path <= {lim}"
           + (", Excel's within 218" if f.excel_ok else " (Excel's 218 out of reach here)"),
           f.ok and max(map(len, paths)) <= lim
           and (not E.too_long(paths)) == f.excel_ok,
           f"{f.before} -> {f.longest}, name {f.stem!r}, {f.folder_name}")
        # nothing longer would do: one more character of the name breaks the limit
        if f.changed and len(f.stem) < len(stem):
            n1 = len(f.stem) + 1
            more = E.full_paths(root, f.folder_name, rel(E.cut_middle(stem, n1),
                                                         E.cut_middle(stem, n1)))
            ok(f"A root {len(str(root))}: the longest name that fits",
               E.too_long(more, 218 if f.excel_ok else 259, f.limit) != [])
        head, _c, end = f.stem.partition(E.CUT)
        ok(f"A root {len(str(root))}: names unique, the start and the (longer) end kept",
           len(set(paths)) == len(paths) and stem.startswith(head) and stem.endswith(end)
           and len(end) >= len(head) and len(f.stem) >= E.MIN_NAME, f.stem)
    root = deep_root(OUT / "math", 80)
    f = E.shorter_names(root, rel, stem, stem, when)
    ok("A a folder high enough: nothing changed", not f.changed and f.stem == stem
       and f.folder_name == E.export_folder_name(when), f"{f.longest}")
    root = deep_root(OUT / "math", 175)
    f = E.shorter_names(root, rel, stem, stem, when)
    m = E.cut_middle(stem, E.READABLE_NAME)
    with_long = E.full_paths(root, E.export_folder_name(when), rel(m, m))
    ok("A deep: the short export folder only when a readable name is not enough",
       f.ok and E.is_short_folder(f.folder_name)
       and E.too_long(with_long, 218 if f.excel_ok else 259, f.limit) != [],
       f"{f.stem} {f.folder_name}")
    root = deep_root(OUT / "math", 245)
    f = E.shorter_names(root, rel, stem, stem, when)
    ok("A too deep for any name: says so (ok False), the shortest names", not f.ok
       and len(f.stem) == E.MIN_NAME and E.is_short_folder(f.folder_name), f"{f.longest}")


def check_plan_matches(w, keys):
    """The planned paths of an export are exactly the files it writes."""
    from peterpiper.export import path_plan, run_export
    from peterpiper.exportpaths import file_tag
    comps = w._export_data()
    root = OUT / "plan"
    stem = "my_typed_name"
    out = run_export(str(root), w.exp, w.settings, comps, keys, src=w.src,
                     background=w.background, t0=int(w.t0 or 0), prefix=stem,
                     roi_file_fn=lambda f: _touch(Path(f) / f"{stem}_ROIs.npz"))
    real = sorted(os.path.relpath(f, out["folder"]).replace(os.sep, "/") for f in out["files"])
    rel = path_plan(w.exp, w.settings, comps, keys, int(w.t0 or 0))
    plan = sorted(rel(stem, file_tag(stem, Path(w.exp.nd2_path).stem)))
    ok("A the planned paths are exactly the files a real export writes", plan == real,
       f"only planned {sorted(set(plan) - set(real))[:3]}, only real "
       f"{sorted(set(real) - set(plan))[:3]}")
    ok("A ... and the same longest path", max(map(len, E.full_paths(
        root, Path(out["folder"]).name, plan))) == max(len(plain_path(f)) for f in out["files"]))


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


# ===================================================================== window
def make_window(name):
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    src, exp = SM.load(OUT / name)
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=2))
    w.resize(1366, 768)
    w.show()
    t = time.time()
    while not w._offered and time.time() - t < 30:
        pump(0.1)
    pump(0.3)
    w._auto_select()
    wait(w)
    w._place_background(225.0, 96.0)
    pump(0.2)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._track()
    wait(w)
    return w


KEYS_ALL = None


def every_key(w):
    from peterpiper.export import catalog
    return [it["key"] for it in catalog(w._export_data(), w.settings)
            if it["key"] not in ("*|tiffs", "*|views")]


# ===================================================================== B
def part_b(w):
    print("\n=== B) 'Save in' in the export list ===", flush=True)
    from peterpiper import events, outlog
    from peterpiper.gui.exportdlg import ExportDialog
    use_registry(FakeRegistry(on=True))           # this part: no long-path question
    keys = every_key(w)
    check_plan_matches(w, keys)
    usual = str(w.exp.out_dir)
    chosen = OUT / "Somewhere else" / "my exports"
    chosen.mkdir(parents=True)
    bad = OUT / "not_a_folder.txt"
    bad.write_text("a file, not a folder")
    picks = [str(bad / "sub"), str(chosen).replace("\\", "/")]
    seen = {}
    real_dir = QFileDialog.getExistingDirectory
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: picks.pop(0) if picks else "")
    real_exec = ExportDialog.exec

    def run_dialog(dlg):
        seen["first"] = dlg.lbl_folder.full_text()
        seen["usual_off"] = not dlg.btn_usual.isEnabled()
        n0 = len(BOXES)
        dlg.btn_folder.click()                     # an unwritable choice
        seen["refused"] = BOXES[n0:]
        seen["after_refused"] = dlg.folder()
        dlg.btn_folder.click()                     # a good one
        seen["chosen"] = dlg.folder()
        seen["label"] = dlg.lbl_folder.full_text()
        seen["usual_on"] = dlg.btn_usual.isEnabled()
        dlg.lbl_folder.resize(200, 20)
        seen["elided"] = dlg.lbl_folder.text()
        dlg.resize(1366 - 40, 768 - 80)
        pump(0.2)
        dlg.grab().save(str(SHOTS / "v12_export_list_save_in.png"))
        seen["min"] = dlg.minimumSizeHint()
        for k in keys:
            dlg._put(k)
        dlg._sync()
        dlg.accept()
        return QDialog.Accepted
    ExportDialog.exec = run_dialog
    got = []
    events.on("exported", lambda **k: got.append(k))
    w.settings.export_list = keys
    w._choose_outputs()
    wait(w)
    ExportDialog.exec = real_exec
    ok("B the export list shows 'Save in' = the movie's results folder",
       seen.get("first", "").startswith(usual) and seen.get("usual_off"), seen.get("first"))
    ok("B a folder that cannot be written is refused in plain words",
       seen.get("after_refused") == usual and any("Cannot save there" in str(b[0])
                                                  and "cannot write" in str(b[1])
                                                  for b in seen.get("refused", [])),
       str(seen.get("refused"))[:200])
    ok("B Change... takes the chosen folder", Path(seen.get("chosen", "")) == chosen
       and "not the movie's results folder" in seen.get("label", "")
       and seen.get("usual_on"), seen.get("label"))
    ok("B a long path is cut in the middle on screen (whole on hover)",
       "…" in seen.get("elided", "") or len(seen.get("elided", "")) < len(seen.get("label", "")),
       seen.get("elided"))
    folder = Path(w._exported or "")
    ok("B the export is in <chosen>/Export_<date>_<time>", folder.parent == chosen
       and folder.name.startswith("Export_20"), str(folder))
    fs = files_in(chosen)
    ends = (".xlsx", ".pzfx", ".prism", ".csv", ".png", "_ROIs.npz", "_methods.txt")
    ok("B every kind of output went there", all(any(f.endswith(e) for f in fs) for e in ends)
       and all(Path(f).is_relative_to(folder) for f in fs), f"{len(fs)} files")
    in_usual = [f for f in files_in(usual) if "Export_" in f]
    ok("B nothing of this export in the usual folder", not in_usual, str(in_usual[:2]))
    ok("B the 'exported' event names the chosen folder",
       got and Path(got[-1]["folder"]) == folder, str(got[-1:]))
    log = outlog.entries()
    ok("B the export log lists the files in the chosen folder",
       log and Path(log[-1]["folder"]).is_relative_to(folder)
       and all(Path(f).is_relative_to(folder) for f in log[-1]["files"]), str(log[-1:])[:200])
    w._mark_dirty()
    w._autosave(even_if_busy=True)
    wait(w)
    pump(1.0)
    sf = w._session_file
    ok("B the run's autosave stays in the movie's results folder (not changed)",
       w.exp.out_dir == usual and sf is not None and Path(sf).is_relative_to(usual)
       and not (chosen / "PeterPiper_sessions").exists(), str(sf))
    ok("B the folder is kept for this movie's next export", w._export_folder() == str(chosen)
       or Path(w._export_folder()) == chosen)
    # the dialog again: 'Usual folder' goes back
    back = {}

    def run_back(dlg):
        back["start"] = dlg.folder()
        dlg.btn_usual.click()
        back["after"] = dlg.folder()
        dlg.reject()
        return QDialog.Rejected
    ExportDialog.exec = run_back
    w._choose_outputs()
    ExportDialog.exec = real_exec
    ok("B opens with the chosen folder; 'Usual folder' goes back",
       Path(back.get("start", "")) == chosen and back.get("after") == usual, str(back))
    ok("B the export list fits 1366 x 768 (no scroll bars)",
       seen["min"].width() <= 1366 and seen["min"].height() <= 728,
       f"{seen['min'].width()} x {seen['min'].height()}")
    QFileDialog.getExistingDirectory = real_dir
    w._export_root = None
    real_registry()


# ===================================================================== C
def click(text):
    """QMessageBox.exec replaced: press the button with this text."""
    def ex(box):
        CLICKED.append([b.text() for b in box.buttons()])
        TEXTS.append(box.text())
        for b in box.buttons():
            if b.text() == text or (text == "Cancel" and box.buttonRole(b) ==
                                    QMessageBox.RejectRole):
                b.click()
                return 0
        raise AssertionError(f"no button {text}")
    return ex


CLICKED: list = []
TEXTS: list = []


def part_c(w):
    print("\n=== C) the long-path warning ===", flush=True)
    from peterpiper.export import export_names
    w.prefix = "Experiment_2026_condition_A_treated_10uM_dish3"
    keys = ["nucleus|excel", "nucleus|prismgraph", "nucleus|csv", "nucleus|roi_drawn",
            "*|methods", "*|roifile"]
    comps = w._export_data()
    probe = export_names(str(OUT), w.exp, w.settings, comps, keys, w.prefix)
    extra = probe["longest"] - len(str(OUT))       # the export's own part
    root = deep_root(OUT / "deep", 250 - extra)
    plan = export_names(str(root), w.exp, w.settings, comps, keys, w.prefix)
    ok("C made-up deep folder: workbooks over Excel's 218 with the typed name",
       plan["bad"] and plan["fit"].ok and plan["fit"].excel_ok,
       f"{plan['longest']} -> {plan['fit'].longest}")
    reg = FakeRegistry(on=False)
    use_registry(reg)
    real_exec = QMessageBox.exec
    w._export_root = str(root)
    # the box itself
    box, b = w._long_path_box(plan, plan["fit"], str(root))
    ok("C the warning's buttons", [x.text() for x in box.buttons()] and
       {"Shorten names for me", "Choose another folder...", "Turn on Windows long paths",
        "Export anyway"} <= {x.text() for x in box.buttons()} and b["cancel"] is not None)
    ok("C 'Shorten names for me' is the default", box.defaultButton() is b["shorten"])
    ok("C the new name and the longest new path are shown first",
       plan["fit"].stem in box.text() and str(plan["fit"].longest) in box.text()
       and plan["fit"].longest_path in box.detailedText(), box.text()[:200])
    box.resize(box.sizeHint())
    ok("C the warning fits 1366 x 768", box.sizeHint().width() <= 1366
       and box.sizeHint().height() <= 728, str(box.sizeHint()))
    box.show()
    pump(0.2)
    box.grab().save(str(SHOTS / "v12_long_path_warning.png"))
    box.close()
    # Cancel: nothing written
    w._exported = None
    QMessageBox.exec = click("Cancel")
    w._run_export(comps, keys)
    wait(w)
    ok("C Cancel: nothing exported", w._exported is None and not (
        os.path.isdir(long_path(root)) and any(
            p.startswith("Export_") for p in os.listdir(long_path(root)))))
    # Shorten names for me
    QMessageBox.exec = click("Shorten names for me")
    w._run_export(comps, keys)
    wait(w)
    fs = files_in(w._exported) if w._exported else []
    longest = max(map(len, fs)) if fs else 0
    fit = plan["fit"]
    ok("C Shorten: written, every path within the limit",
       fs and longest <= fit.limit and not E.too_long(fs), f"{len(fs)} files, longest {longest}")
    ok("C ... the shortened name on the files, its end kept",
       any(Path(f).name == f"{fit.stem}_nucleus.xlsx" for f in fs)
       and fit.stem.endswith("dish3") and fit.stem != w.prefix, fit.stem)
    ok("C ... the longest path as the warning said", longest == fit.longest,
       f"{longest} vs {fit.longest}")
    import zipfile
    pr = [f for f in fs if f.endswith(".prism")]
    blob = b""
    if pr:
        with zipfile.ZipFile(long_path(pr[0])) as z:
            blob = b"".join(z.read(n) for n in z.namelist())
    ok("C ... the graphs' titles keep the whole name (only the file names are short)",
       w.prefix.encode() in blob, pr[0][-60:] if pr else "no .prism")
    ok("C ... the status line says what was shortened", "names shortened" in w._path_note
       and fit.stem in w._path_note, w._path_note)
    # Export anyway
    QMessageBox.exec = click("Export anyway")
    w._run_export(comps, keys)
    wait(w)
    fs = files_in(w._exported) if w._exported else []
    ok("C Export anyway: the names as typed (the long paths written)",
       any(Path(f).name == f"{w.prefix}_nucleus.xlsx" for f in fs)
       and max(map(len, fs)) == plan["longest"], str(max(map(len, fs)) if fs else 0))
    # Choose another folder...: an unwritable one is refused, then a short one
    short = OUT / "short"
    bad = OUT / "a_file_not_a_folder"
    bad.write_text("x")
    picks = [str(bad / "x"), str(short)]
    real_dir = QFileDialog.getExistingDirectory
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: picks.pop(0) if picks else "")
    answers = ["Choose another folder...", "Choose another folder..."]

    def ex(box):
        CLICKED.append([x.text() for x in box.buttons()])
        return click(answers.pop(0) if answers else "Cancel")(box)
    QMessageBox.exec = ex
    n0 = len(BOXES)
    w._run_export(comps, keys)
    wait(w)
    QFileDialog.getExistingDirectory = real_dir
    ok("C another folder: an unwritable one refused plainly",
       any("Cannot save there" in str(x[0]) for x in BOXES[n0:]), str(BOXES[n0:])[:200])
    ok("C another folder: the export goes there with the names as typed",
       w._exported and Path(w._exported).parent == short
       and any(Path(f).name == f"{w.prefix}_nucleus.xlsx" for f in files_in(w._exported)),
       str(w._exported))
    w._export_root = str(root)
    # Turn on Windows long paths: declined, then approved
    reg.approve = False
    answers[:] = ["Turn on Windows long paths", "Cancel"]
    n0 = len(BOXES)
    w._exported = None
    w._run_export(comps, keys)
    wait(w)
    said = " ".join(str(x[1]) for x in BOXES[n0:])
    ok("C Turn on, approval not given: 'Not changed', the IT setting named, asked again",
       reg.calls and "Not changed" in said and "Enable Win32 long paths" in said
       and w._exported is None and not reg.on, said[:200])
    ok("C ... the command run is the long-path one", "LongPathsEnabled" in reg.calls[-1]
       and '"' not in reg.calls[-1], reg.calls[-1])
    reg.approve = True
    answers[:] = ["Turn on Windows long paths", "Shorten names for me"]
    n0 = len(BOXES)
    nb = len(TEXTS)
    w._run_export(comps, keys)
    wait(w)
    said = " ".join(str(x[1]) for x in BOXES[n0:])
    ok("C Turn on, approved: on now, and Explorer / Excel may STILL not open long paths",
       reg.on and "ON now" in said and "STILL" in said and "218" in said, said[:200])
    ok("C ... asked again (Excel's limit stays): the warning says long paths are on now",
       len(TEXTS) - nb == 2 and "long paths are on now" in TEXTS[-1], TEXTS[-1][:160])
    ok("C ... then Shorten writes the export", w._exported is not None)
    # long paths on / not readable (a Mac): no warning
    for state in (True, None):
        use_registry(FakeRegistry(on=state))
        nb = len(TEXTS)
        w._exported = None
        QMessageBox.exec = click("Cancel")
        w._run_export(comps, keys)
        wait(w)
        ok(f"C long paths {'on' if state else 'not readable (Mac)'}: no warning, exported",
           len(TEXTS) == nb and w._exported is not None)
    QMessageBox.exec = real_exec
    w._export_root = None
    real_registry()


# ===================================================================== D
def part_d():
    print("\n=== D) syscheck: turning long paths on ===", flush=True)
    try:
        REAL_ELEVATE("Write-Output nothing")
        refused = False
    except OSError:
        refused = True
    ok("D the real elevation refuses while PETERPIPER_NO_ELEVATE is set (or off Windows)",
       refused)
    reg = FakeRegistry(on=False, approve=True)
    on, text = SC.turn_on_long_paths(elevate=reg.elevate, read=reg.read)
    if sys.platform == "win32":
        ok("D approved: on, with the Explorer / Excel caveat", on is True and "STILL" in text
           and "218" in text and reg.calls and "LongPathsEnabled" in reg.calls[0], text[:120])
        reg = FakeRegistry(on=False, approve=False)
        on, text = SC.turn_on_long_paths(elevate=reg.elevate, read=reg.read)
        ok("D declined: not changed, ask IT for 'Enable Win32 long paths' (exact setting)",
           on is False and "Not changed" in text and "Enable Win32 long paths" in text
           and "LongPathsEnabled = 1" in text, text[:160])
        reg = FakeRegistry(on=False, approve=True)
        on, text = SC.turn_on_long_paths(elevate=lambda c, poll=None: 0, read=reg.read)
        ok("D ran but still off (a policy): says so", on is False and "still off" in text)
        on, text = SC.turn_on_long_paths(elevate=reg.elevate, read=lambda: True)
        ok("D already on: nothing run", on is True and "already" in text)
        # the Computer check window
        from PySide6.QtWidgets import QPushButton
        from peterpiper.gui.syscheckdlg import ComputerCheckDialog
        reg = FakeRegistry(on=False)
        use_registry(reg)
        d = ComputerCheckDialog(None, SC.run_checks())
        d.resize(1366 - 40, 768 - 80)
        d.show()
        pump(0.2)
        d.grab().save(str(SHOTS / "v12_computer_check.png"))
        btn = [x for x in d.findChildren(QPushButton) if x.text() == "Turn on Windows long paths"]
        ok("D the Computer check offers 'Turn on Windows long paths'", len(btn) == 1)
        ok("D the Computer check fits 1366 x 768", d.minimumSizeHint().height() <= 728,
           str(d.minimumSizeHint()))
        n0 = len(BOXES)
        if btn:
            btn[0].click()
            pump(0.2)
        ok("D pressing it: the fake ran, the result said, the check looked again (now ok)",
           reg.calls and BOXES[n0:] and "ON now" in str(BOXES[n0][1])
           and d.items[0].status == "ok", str(BOXES[n0:])[:120])
        d.accept()
        real_registry()
    else:
        ok("D off Windows: nothing to turn on", on is None)


# ===================================================================== E
def part_e():
    print("\n=== E) batch exports ===", flush=True)
    from peterpiper import nd2io
    from peterpiper.gui import batchdlg as B
    reg = FakeRegistry(on=False)
    use_registry(reg)
    movie_dir = deep_root(OUT / "batchdeep", 80)
    os.makedirs(long_path(movie_dir), exist_ok=True)
    movie = movie_dir / "Experiment_2026_condition_A_treated_10uM_dish3.nd2"
    with open(long_path(movie), "wb") as fh:
        fh.write(b"stands in for a movie " * 40)
    real_open, real_desc = nd2io.open_source, nd2io.describe

    def fake_open(path):
        src, _e = SM.load(OUT / "batch_tmp")
        return src

    def fake_describe(src, out_dir=""):
        _s, exp = SM.load(out_dir)
        exp.nd2_path = str(movie)
        exp.out_dir = str(out_dir)
        return exp
    nd2io.open_source, nd2io.describe = fake_open, fake_describe
    try:
        n_shown = len(TEXTS)
        real_exec = QMessageBox.exec
        QMessageBox.exec = click("Cancel")
        row = B.analyse_one(str(movie), Settings(baseline_timepoint=2))
        QMessageBox.exec = real_exec
        folder = row["Export folder"]
        fs = files_in(folder) if folder else []
        ok("E batch: exported without any question", row["Status"] == "automatic - check"
           and len(TEXTS) == n_shown and "would have paths" not in row["Messages"],
           f"{row['Status']} | {row['Messages'][:200]}")
        ok("E batch: every path within the limit (shortened by itself)",
           fs and not E.too_long(fs), str(max(map(len, fs)) if fs else 0))
        ok("E batch: the log's Messages say the names were shortened",
           "names shortened" in row["Messages"], row["Messages"][:200])
        log = B.write_log(str(OUT / "batchlog"), [row], "test settings")
        import csv
        rows = list(csv.reader(open(log, encoding="utf-8-sig")))
        ok("E batch log CSV carries it", "names shortened" in rows[1][LOG_COL()])
        # a chosen export folder: one subfolder per movie, the run stays put
        chosen = OUT / "batch exports"
        row2 = B.analyse_one(str(movie), Settings(baseline_timepoint=2),
                             export_dir=str(chosen))
        f2 = Path(row2["Export folder"]) if row2["Export folder"] else Path("none")
        ok("E batch into a chosen folder: <chosen>/<movie>/Export_...",
           f2.parent == Path(B.export_dir_for(str(chosen), str(movie)))
           and f2.parent.parent == chosen and f2.name.startswith("Export_"), str(f2))
        sess = [f for f in files_in(chosen) if "PeterPiper_sessions" in f]
        ok("E ... nothing of the run itself there", not sess, str(sess[:1]))
    finally:
        nd2io.open_source, nd2io.describe = real_open, real_desc
        real_registry()
    # the batch window's row
    dlg = B.BatchDialog(Settings())
    picks = [str(OUT / "a_file_not_a_folder" / "y"), str(OUT / "batch pick")]
    (OUT / "batch pick").mkdir(exist_ok=True)
    real_dir = QFileDialog.getExistingDirectory
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: picks.pop(0) if picks else "")
    n0 = len(BOXES)
    dlg._choose_export_dir()
    refused = dlg.export_dir == "" and any("Cannot save there" in str(x[0]) for x in BOXES[n0:])
    dlg._choose_export_dir()
    QFileDialog.getExistingDirectory = real_dir
    ok("E batch window: 'Save exports in' - unwritable refused, a folder taken",
       refused and Path(dlg.export_dir) == OUT / "batch pick"
       and dlg.btn_export_usual.isEnabled(), dlg.lbl_export.text())
    dlg.resize(1366 - 40, 768 - 80)
    dlg.show()
    pump(0.2)
    dlg.grab().save(str(SHOTS / "v12_batch_save_in.png"))
    ok("E batch window fits 1366 x 768", dlg.minimumSizeHint().height() <= 728
       and dlg.minimumSizeHint().width() <= 1366, str(dlg.minimumSizeHint()))
    dlg.btn_export_usual.click()
    ok("E 'Usual folders' goes back", dlg.export_dir == "" and "as usual" in
       dlg.lbl_export.text())
    dlg.close()


def LOG_COL():
    from peterpiper.gui.batchdlg import LOG_HEADERS
    return LOG_HEADERS.index("Messages")


# ===================================================================== F
def part_f():
    print("\n=== F) Compare: Close ===", flush=True)
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QAbstractScrollArea, QGraphicsView
    from peterpiper import graphstyle as GS
    from peterpiper.gui.comparewin import CompareWindow
    CompareWindow.ASK_UNKNOWN = False
    cw = CompareWindow(GS.GraphStyle().to_dict())
    cw.setWindowState(cw.windowState() & ~__import__("PySide6.QtCore", fromlist=["Qt"]).Qt
                      .WindowMaximized)
    cw.resize(1366, 768)
    cw.show()
    pump(0.5)
    b = getattr(cw, "btn_close", None)
    ok("F Compare has a Close button", b is not None and b.isVisible() and b.text() == "Close")
    if b is not None:
        r = b.geometry()
        tl = b.mapTo(cw, r.topLeft() - r.topLeft())
        ok("F ... at the bottom right of the window",
           tl.x() + b.width() > cw.width() - 60 and tl.y() + b.height() > cw.height() - 60,
           f"{tl.x()},{tl.y()} in {cw.width()}x{cw.height()}")
        # 4.0 (on purpose): Close sits under both pages (graph builder / averages), not in
        # the averages page's Save row
        ok("F ... under both pages (not inside one page)",
           not cw.tabs.isAncestorOf(b) and b.mapTo(cw, b.rect().topLeft()).y() >
           cw.tabs.mapTo(cw, cw.tabs.rect().bottomLeft()).y() - 2)
    bad = []
    for s in cw.findChildren(QAbstractScrollArea):
        if not s.isVisible() or s.window() is not cw or s is cw.tree or \
                isinstance(s, QGraphicsView) or s.parent() is cw.tree:
            continue
        if s.verticalScrollBar().maximum() or s.horizontalScrollBar().maximum():
            bad.append(type(s).__name__)
    ok("F Compare at 1366 x 768: no scroll bars", not bad, str(bad))
    cw.grab().save(str(SHOTS / "v12_compare_close.png"))
    flushed = []
    real_flush = cw._flush_state
    cw._flush_state = lambda: (flushed.append(1), real_flush())[1]
    b.click()
    pump(0.2)
    ok("F Close does what the X does: closed, state saved, rejected",
       not cw.isVisible() and flushed and cw.result() == QDialog.Rejected)
    # from the start screen: exec() returns as after the X
    cw2 = CompareWindow(GS.GraphStyle().to_dict())
    QTimer.singleShot(400, lambda: cw2.btn_close.click())
    t = time.time()
    r = cw2.exec()
    ok("F exec() (start screen) returns after Close, as after the X",
       r == QDialog.Rejected and time.time() - t < 30 and cw2.open_request is None)
    cw3 = CompareWindow(GS.GraphStyle().to_dict())
    QTimer.singleShot(400, lambda: cw3.close())                  # the X
    ok("F (the X gives the same)", cw3.exec() == QDialog.Rejected)


# ===================================================================== G
def part_g(w):
    print("\n=== G) screens ===", flush=True)
    w.grab().save(str(SHOTS / "v12_analysis_window.png"))
    ok("G the analysis window keeps its way out ('Another file', top left)",
       w.btn_back.isVisible() and "Another file" in w.btn_back.text())


def main():
    part_a()
    w = make_window("win")
    ok("setup: tracked", w.track is not None)
    if w.track is None:
        return
    part_b(w)
    part_c(w)
    part_d()
    part_e()
    part_f()
    part_g(w)
    w._dirty = False
    w.close()
    pump(0.3)


if __name__ == "__main__":
    main()
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed", flush=True)
    if FAILS:
        print("FAILED:", *FAILS, sep="\n  ")
    sys.exit(1 if FAILS else 0)
