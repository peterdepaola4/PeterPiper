"""
V2.7 'Batch analyse .nd2 files...': run a saved analysis setting on many .nd2
files without clicking - for each file, exactly the steps you would take in the
main window, with the same code:

  1. open the .nd2 and place the background region automatically (only here: in the
     main window you pick it, since V3.0 - with nobody to click, batch still does);
  2. AUTO-DETECT for every compartment that has a tracking rule, in rule order
     (the setting's detection, size and IF-gate settings);
  3. TRACK & MEASURE (the setting's tracking rules, QC);
  4. Export: the setting's export list (else the standard list) into the file's
     OUTPUT_<name> folder, with the ROI file, methods and provenance as always.

Nothing is curated by hand, so every file is flagged 'automatic - check'. A log
(PeterPiper batch <date>.csv) lists per file: what was found and included per
compartment, any background warning, the export folder and any message. Open
a file afterwards (File > Earlier analyses) to check or correct it. Your own
settings (settings.json) are not changed by a batch run.
"""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import io
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QListWidget,
                               QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .. import presets as PR
from ..config import Settings
from ..safety import error_text, folder_problem, new_output_file, plain_path
from . import widgets as W

LOG_HEADERS = ["File", "Status", "Cells found", "Cells included", "Background note",
               "Export folder", "Messages", "Settings"]


@contextlib.contextmanager
def _quiet(messages: List[str]):
    """No dialog waits for a click during a batch run: every message box is
    recorded instead, and the user's settings.json is left alone."""
    from PySide6.QtWidgets import QMessageBox as MB
    from . import clickwin as CW
    saved = {n: getattr(MB, n) for n in ("information", "warning", "critical", "question")}
    exec_, show_ = MB.exec, MB.show
    save_settings = CW.save_settings

    def rec(*a, **k):
        messages.append(str(a[2]) if len(a) > 2 else "")
        return MB.Ok
    try:
        for n in ("information", "warning", "critical"):
            setattr(MB, n, staticmethod(rec))
        MB.question = staticmethod(lambda *a, **k: (rec(*a), MB.Yes)[1])
        MB.exec = lambda self: messages.append(self.text()) or 0
        MB.show = lambda self: messages.append(self.text())
        CW.save_settings = lambda *a, **k: None
        yield
    finally:
        for n, f in saved.items():
            setattr(MB, n, f)
        MB.exec, MB.show = exec_, show_
        CW.save_settings = save_settings


def _wait(w, limit_s: float = 4 * 3600) -> bool:
    t = QElapsedTimer()
    t.start()
    while w._busy_now():
        QApplication.processEvents()
        if t.elapsed() > limit_s * 1000:
            return False
    QApplication.processEvents()
    return True


def _settle(w, quiet_ms: int = 300) -> None:
    """Wait until the window has had no job running for quiet_ms (it starts some
    by itself after opening - frame loading, the background search)."""
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < quiet_ms:
        QApplication.processEvents()
        if w._busy_now():
            _wait(w)
            t.restart()


def analyse_one(path: str, s: Settings, progress: Optional[Callable[[str], None]] = None,
                out_dir: Optional[str] = None) -> dict:
    """One .nd2 with settings s (see the module text). Returns a log row dict."""
    from ..export import catalog, standard
    from ..manual import background_warning
    from ..nd2io import describe, open_source
    from .clickwin import LABELS, ClickWindow
    row = dict(File=str(path), Status="", **{"Cells found": "", "Cells included": "",
                                            "Background note": "", "Export folder": "",
                                            "Messages": ""})
    msgs: List[str] = []
    say = progress or (lambda _t: None)
    src = w = None
    try:
        with _quiet(msgs):
            src = open_source(path)
            from .. import users               # V2.9: OUTPUT_<movie>/<user>
            out = out_dir or users.output_dir(path)
            why = folder_problem(out)          # 1.0.3: a read-only drive
            if why is not None and not out_dir:
                alt = users.fallback_output_dir(path)
                if folder_problem(alt) is None:
                    msgs.append(f"The results could not be written next to the movie "
                                f"({why}); they are in {plain_path(alt)}")
                    out = alt
            exp = describe(src, out_dir=out)
            w = ClickWindow(src, exp, Settings(**vars(s)))
            w._offered = True                          # no 'earlier analyses?' question
            _settle(w)                                 # jobs the window starts by itself
            w._auto_background()
            for comp in list(w.rules):
                i = w.cmb_comp.findData(comp)
                if i < 0:
                    continue
                w.cmb_comp.setCurrentIndex(i)
                say(f"{Path(path).name}: auto-detect {LABELS[comp].lower()} ...")
                _settle(w)
                w._auto_select()
                _wait(w)
            _settle(w)
            if not any(w.cells):
                raise RuntimeError("no ROIs were detected")
            say(f"{Path(path).name}: tracking ...")
            w._track()
            _wait(w)
            if w.track is None:
                raise RuntimeError("tracking did not finish: " + " | ".join(msgs[-2:]))
            comps = w._export_data()
            found = {c: len(d["cells"]) for c, d in comps.items()}
            incl = {c: sum(d["include"].values()) for c, d in comps.items()}
            row["Cells found"] = "; ".join(f"{LABELS[c]} {n}" for c, n in found.items())
            row["Cells included"] = "; ".join(f"{LABELS[c]} {n}" for c, n in incl.items())
            row["Background note"] = background_warning(w.track.get("background") or {},
                                                        channels=list(exp.channels))
            w.settings.baseline_timepoint = int(min(max(1, s.baseline_timepoint),
                                                    exp.n_timepoints))
            cat = catalog(comps, w.settings)
            keys_all = {it["key"] for it in cat}
            keys = [k for k in (s.export_list or []) if k in keys_all] or \
                standard(cat, {c: w._prefer_sheets(c, d["M"]) for c, d in comps.items()})
            say(f"{Path(path).name}: exporting {len(keys)} item(s) ...")
            _settle(w)
            w._run_export(comps, keys)
            _wait(w)
            row["Export folder"] = str(getattr(w, "_exported", "") or "")
            row["Status"] = ("automatic - check" if row["Export folder"] else
                             "tracked, export failed")
    except Exception as e:                                         # noqa: BLE001
        row["Status"] = f"failed: {error_text(e)}"
        msgs.append(traceback.format_exc(limit=2))
    finally:
        if w is not None:
            with _quiet(msgs):
                w.close()
                w.deleteLater()
        if src is not None:
            try:
                src.close()
            except Exception:                                      # noqa: BLE001
                pass
        QApplication.processEvents()
    row["Messages"] = " | ".join(m.strip().replace("\n", " ")[:300] for m in msgs if m.strip())
    return row


def write_log(folder: str, rows: Sequence[dict], settings_name: str) -> str:
    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(LOG_HEADERS)
    for r in rows:
        wr.writerow([r.get(h, "") if h != "Settings" else settings_name for h in LOG_HEADERS])
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if folder_problem(folder) is not None:     # 1.0.3: a read-only drive
        from .. import users
        folder = str(users.results_home())
    with new_output_file(Path(folder) / f"PeterPiper batch {stamp}.csv") as (used, stream):
        stream.write(buf.getvalue().encode("utf-8-sig"))
    return str(used)


class BatchDialog(QDialog):
    def __init__(self, current: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch analyse .nd2 files")
        self.resize(1000, 640)
        self.current = current
        self.rows: List[dict] = []
        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(
            "Every file is analysed without clicking, with the chosen settings: automatic "
            "background, AUTO-DETECT for each compartment with a tracking rule, TRACK & "
            "MEASURE, then the settings' export list into the file's OUTPUT folder (ROI file, "
            "methods and provenance as always). Nothing is checked by hand - open each file "
            "afterwards (File > Earlier analyses of this file) to check or correct it. A log "
            "(CSV) lists what was found per file."))
        self.files = QListWidget()
        lay.addWidget(self.files, 1)
        lay.addWidget(W.row(W.button("Add .nd2 files...", self._add_files),
                            W.button("Add a folder (all .nd2 in it and below)...",
                                     self._add_folder),
                            W.button("Clear", self.files.clear)))
        self.cmb = QComboBox()
        self.cmb.addItem("The settings in use now", "")
        for p in PR.listing():
            try:
                blob = PR.read(p)
            except ValueError:
                continue
            if isinstance(blob.get("analysis"), dict):
                self.cmb.addItem(PR.describe(blob)[:140], str(p))
        lay.addWidget(W.row(W.wrapped_label("Settings:"), self.cmb,
                            W.button("Other file...", self._other)))
        self.btn = W.button("Run", self._run, strong=True)
        lay.addWidget(self.btn)
        self.lbl = W.wrapped_label("", muted=True)
        lay.addWidget(self.lbl)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["File", "Status", "Cells included",
                                              "Background note", "Export folder"])
        lay.addWidget(self.table, 1)

    def _add_paths(self, paths) -> None:
        have = {self.files.item(i).text() for i in range(self.files.count())}
        for p in paths:
            if str(p) not in have:
                self.files.addItem(str(p))

    def _add_files(self) -> None:
        paths, _f = QFileDialog.getOpenFileNames(self, ".nd2 files", "", "Nikon (*.nd2)")
        self._add_paths(paths)

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Folder with .nd2 files")
        if d:
            self._add_paths(sorted(str(p) for p in Path(d).rglob("*.nd2")))

    def _other(self) -> None:
        p, _f = QFileDialog.getOpenFileName(self, "Saved settings", str(PR.folder()),
                                            "PeterPiper settings (*.json)")
        if p:
            self.cmb.addItem(Path(p).name, p)
            self.cmb.setCurrentIndex(self.cmb.count() - 1)

    def settings(self):
        p = self.cmb.currentData()
        if not p:
            return Settings(**vars(self.current)), "settings in use"
        blob = PR.read(p)
        s = PR.analysis_settings(blob, self.current)
        if s is None:
            raise ValueError(f"{Path(p).name} holds no analysis settings.")
        return s, str(blob.get("name") or Path(p).stem)

    def _run(self) -> None:
        paths = [self.files.item(i).text() for i in range(self.files.count())]
        if not paths:
            return
        try:
            s, name = self.settings()
        except ValueError as e:
            QMessageBox.warning(self, "Batch", error_text(e))
            return
        self.btn.setEnabled(False)
        self.rows = []
        self.table.setRowCount(0)
        try:
            for k, p in enumerate(paths):
                self.lbl.setText(f"{k + 1} / {len(paths)}: {Path(p).name}")
                r = analyse_one(p, s, progress=self.lbl.setText)
                self.rows.append(r)
                i = self.table.rowCount()
                self.table.insertRow(i)
                for j, h in enumerate(("File", "Status", "Cells included", "Background note",
                                       "Export folder")):
                    self.table.setItem(i, j, QTableWidgetItem(Path(r[h]).name if h == "File"
                                                              else str(r[h])))
                QApplication.processEvents()
            log = write_log(str(Path(paths[0]).parent), self.rows, name)
            from .. import outlog
            outlog.record("batch", f"Batch of {len(paths)} file(s) - {name}", [log],
                          "The batch log; each file's export is listed on its own.")
            self.lbl.setText(f"Done: {len(paths)} file(s). Log: {plain_path(log)}")
        finally:
            self.btn.setEnabled(True)
