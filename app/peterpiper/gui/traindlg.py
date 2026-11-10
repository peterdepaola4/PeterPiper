"""
V3.0 'Train auto-detect' window: teach AUTO-DETECT which cells you pick.

    1  Your runs      tick saved runs you outlined by hand (one per movie; the
                      .nd2 must be on this computer); choose the main channel and
                      the helper channels
    2  Watch it learn it tries rules on your movies and shows a scoreboard per
                      movie (scored on each movie with a rule learned from the
                      OTHER movies - the honest number) and the picture: green =
                      it picked one of yours, red = one of yours it missed, yellow
                      = an extra it picked
    3  Quick quiz     the blobs it is least sure about, one at a time: Keep /
                      Skip / Not sure; your answers sharpen the rule
    4  Save           name it ('Autodetect - Nuclear GFP plus Cy5 (my sensor)'): it
                      becomes a button under AUTO-DETECT for movies with these
                      channels, kept in your profile

The learning itself is peterpiper.detectors (all of its numbers are in the file and
in the Methods sheet of every export that used it).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)
from scipy import ndimage as ndi

from .. import detectors as DT
from . import widgets as W

GREEN, RED, YELLOW = (60, 220, 90), (255, 70, 70), (255, 215, 0)
QUIZ_N = 12


# ------------------------------------------------------------------ pictures
def _grey(plane: np.ndarray, lo: float, hi: float) -> np.ndarray:
    g = (plane.astype(np.float32) - lo) / max(hi - lo, 1e-6)
    return (np.clip(g, 0, 1) * 255).astype(np.uint8)


def _levels(plane: np.ndarray) -> tuple:
    sub = plane[::4, ::4]
    return float(np.percentile(sub, 1)), float(np.percentile(sub, 99.8))


def _outline(rgb: np.ndarray, roi, colour, oy: int = 0, ox: int = 0, width: int = 1) -> None:
    y0, x0, y1, x1 = roi.bbox
    m = roi.mask
    edge = m & ~ndi.binary_erosion(m, iterations=width)
    ys, xs = np.nonzero(edge)
    ys, xs = ys + y0 - oy, xs + x0 - ox
    ok = (ys >= 0) & (xs >= 0) & (ys < rgb.shape[0]) & (xs < rgb.shape[1])
    rgb[ys[ok], xs[ok]] = colour


def _pixmap(rgb: np.ndarray, width: int) -> QPixmap:
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img).scaledToWidth(width, Qt.SmoothTransformation)


# ------------------------------------------------------------------ runs
def my_runs(channels_needed: Sequence[str] = ()) -> List[dict]:
    """Your saved, tracked runs - the newest per movie - with what the trainer needs:
    [{nd2_name, path, nd2, saved, n_cells, channels, ok, why}]."""
    from .. import history, roifile, users
    best = {}
    for r in history.indexed_runs(limit=2000):
        s = roifile.read_summary(r["path"]) or {}
        if not users.is_mine(r["path"], s.get("user")):
            continue
        key = r["nd2_name"]
        if key in best and best[key]["saved"] >= r["saved"]:
            continue
        nd2 = history.resolve(str(s.get("nd2_path") or ""))
        ch = list(s.get("channels") or [])
        why = ""
        if not nd2 or not Path(nd2).exists():
            why = ".nd2 not on this computer"
        elif channels_needed and not all(c in ch for c in channels_needed):
            why = "other channels"
        best[key] = dict(nd2_name=key, path=r["path"], nd2=nd2, saved=r["saved"],
                         n_cells=r["n_cells"], channels=ch, ok=not why, why=why)
    return sorted(best.values(), key=lambda d: d["saved"], reverse=True)


class TrainDialog(QDialog):
    def __init__(self, parent, channels: Sequence[str], main: str = "",
                 helpers: Sequence[str] = ()) -> None:
        super().__init__(parent)
        self.setWindowTitle("Train auto-detect - teach it the cells you pick")
        self.resize(1400, 900)
        self.channels = [str(c) for c in channels]
        self.movies: List[DT.Movie] = []
        self.limits: Optional[dict] = None
        self.held: List[dict] = []
        self.answers: List[dict] = []
        self.quiz: List[tuple] = []
        self.qi = 0
        self.saved_path: Optional[Path] = None
        root = QVBoxLayout(self)
        intro = W.wrapped_label(
            "Tick saved runs where you outlined the nuclei you want (by hand or after fixing "
            "AUTO-DETECT). It learns which blobs you pick on those movies, shows how well that "
            "works on a movie it has NOT seen, then asks you about the blobs it is unsure of. "
            "Save it with a name: it becomes your own AUTO-DETECT button for movies with the "
            "same channels.", muted=True)
        root.addWidget(intro)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)
        # ---- left: 1 runs + channels, 2 scoreboard + rule
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        box, form = W.group("1   Your runs and channels")
        chrow = QWidget()
        cl = QHBoxLayout(chrow)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(QLabel("Main channel"))
        self.cmb_main = QComboBox()
        self.cmb_main.addItems(self.channels)
        if main in self.channels:
            self.cmb_main.setCurrentIndex(self.channels.index(main))
        cl.addWidget(self.cmb_main)
        cl.addWidget(QLabel("  helpers"))
        self.chk_help = {}
        for c in self.channels:
            b = QCheckBox(c)
            b.setChecked(c in helpers)
            b.toggled.connect(lambda _v: self._fill_runs())
            self.chk_help[c] = b
            cl.addWidget(b)
        cl.addStretch(1)
        self.cmb_main.currentIndexChanged.connect(lambda _i: self._fill_runs())
        form.addRow(chrow)
        self.tbl_runs = QTableWidget(0, 4)
        self.tbl_runs.setHorizontalHeaderLabels(["Use", "Movie", "Cells", "Saved"])
        self.tbl_runs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_runs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_runs.verticalHeader().hide()
        self.tbl_runs.setEditTriggers(QAbstractItemView.NoEditTriggers)
        form.addRow(self.tbl_runs)
        self.btn_learn = W.button("Learn from the ticked runs", self.learn,
                                  "Reads the frame you drew on of each ticked movie (the .nd2 "
                                  "is only read) and searches for the rule that picks your "
                                  "cells.", strong=True)
        form.addRow(self.btn_learn)
        ll.addWidget(box, 3)
        box2, form2 = W.group("2   How well it does")
        self.lbl_rule = W.wrapped_label("Not trained yet.")
        form2.addRow(self.lbl_rule)
        self.lbl_score = W.wrapped_label("", muted=True)
        form2.addRow(self.lbl_score)
        self.tbl_score = QTableWidget(0, 6)
        self.tbl_score.setHorizontalHeaderLabels(["Movie", "Your cells", "Found", "Missed",
                                                  "Extra", "F1 (unseen)"])
        self.tbl_score.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_score.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_score.verticalHeader().hide()
        self.tbl_score.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_score.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_score.itemSelectionChanged.connect(self._show_movie)
        self.tbl_score.setToolTip("Each movie scored with the rule learned from the OTHER "
                                  "movies (the honest number). Click a movie to see it.")
        form2.addRow(self.tbl_score)
        ll.addWidget(box2, 4)
        split.addWidget(left)
        # ---- right: picture / quiz, save
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.lbl_legend = W.wrapped_label(
            "Green = it picked one of yours   Red = one of yours it missed   Yellow = an extra "
            "it picked (the rule learned from all ticked movies).", muted=True)
        rl.addWidget(self.lbl_legend)
        self.pic = QLabel("The movie you click in the scoreboard is shown here.")
        self.pic.setAlignment(Qt.AlignCenter)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.pic)
        rl.addWidget(sc, 5)
        box3, form3 = W.group("3   Quick quiz - would you pick this one?")
        self.lbl_q = W.wrapped_label("After learning: the blobs it is least sure about.",
                                     muted=True)
        form3.addRow(self.lbl_q)
        self.q_pics = QLabel("")
        self.q_pics.setAlignment(Qt.AlignCenter)
        form3.addRow(self.q_pics)
        self.btn_quiz = W.button(f"Start the quiz ({QUIZ_N} blobs)", self.start_quiz,
                                 "Shows the blobs nearest the rule's limits, one at a time.")
        self.btn_keep = W.button("Keep  (K)", lambda: self.answer("keep"), strong=True)
        self.btn_skip = W.button("Skip  (S)", lambda: self.answer("skip"))
        self.btn_unsure = W.button("Not sure  (N)", lambda: self.answer("unsure"))
        form3.addRow(W.row(self.btn_quiz, self.btn_keep, self.btn_skip, self.btn_unsure))
        rl.addWidget(box3, 3)
        box4, form4 = W.group("4   Save it as your own AUTO-DETECT button")
        self.ed_name = QLineEdit()
        form4.addRow("Name", self.ed_name)
        self.btn_save = W.button("Save", self.save, strong=True)
        form4.addRow(W.row(self.btn_save, W.button("Close", self.reject)))
        rl.addWidget(box4)
        split.addWidget(right)
        split.setSizes([620, 780])
        self._quiz_buttons(False)
        self.btn_quiz.setEnabled(False)
        self.btn_save.setEnabled(False)
        self._fill_runs()

    # ---------------------------------------------------------------- 1
    def main(self) -> str:
        return self.cmb_main.currentText()

    def helpers(self) -> List[str]:
        return [c for c, b in self.chk_help.items() if b.isChecked() and c != self.main()]

    def chans(self) -> List[str]:
        return [self.main()] + self.helpers()

    def _fill_runs(self) -> None:
        for c, b in self.chk_help.items():
            b.setEnabled(c != self.main())
        hs = self.helpers()
        self.ed_name.setPlaceholderText(f"Autodetect - Nuclear {self.main()}"
                                        + (f" plus {' + '.join(hs)}" if hs else ""))
        ticked = {self.tbl_runs.item(i, 1).data(Qt.UserRole) for i in range(self.tbl_runs.rowCount())
                  if self.tbl_runs.cellWidget(i, 0) is not None
                  and self.tbl_runs.cellWidget(i, 0).isChecked()}
        try:
            runs = my_runs(self.chans())
        except Exception:                                          # noqa: BLE001
            runs = []
        self._runs = runs
        self.tbl_runs.setRowCount(len(runs))
        for i, r in enumerate(runs):
            b = QCheckBox()
            b.setEnabled(r["ok"])
            b.setChecked(r["ok"] and (r["path"] in ticked if ticked else False))
            self.tbl_runs.setCellWidget(i, 0, b)
            it = QTableWidgetItem(r["nd2_name"] + ("" if r["ok"] else f"   ({r['why']})"))
            it.setData(Qt.UserRole, r["path"])
            it.setToolTip(r["path"])
            if not r["ok"]:
                it.setForeground(Qt.gray)
            self.tbl_runs.setItem(i, 1, it)
            self.tbl_runs.setItem(i, 2, QTableWidgetItem(str(r["n_cells"])))
            self.tbl_runs.setItem(i, 3, QTableWidgetItem(r["saved"][:16].replace("T", " ")))
        self.tbl_runs.resizeColumnToContents(0)

    def ticked_runs(self) -> List[dict]:
        return [self._runs[i] for i in range(self.tbl_runs.rowCount())
                if self.tbl_runs.cellWidget(i, 0).isChecked()]

    def tick(self, paths: Sequence[str]) -> None:
        """Tick these runs (tests / scripted use)."""
        want = {str(p) for p in paths}
        for i, r in enumerate(self._runs):
            self.tbl_runs.cellWidget(i, 0).setChecked(r["ok"] and r["path"] in want)

    # ---------------------------------------------------------------- 2
    def learn(self) -> None:
        runs = self.ticked_runs()
        if not runs:
            QMessageBox.information(self, "Train auto-detect", "Tick at least one run first "
                                    "(two or more give an honest score).")
            return
        main, hs, chans = self.main(), self.helpers(), self.chans()

        def work(progress):
            movies = []
            n = len(runs)
            for i, r in enumerate(runs):
                movies.append(DT.load_movie(
                    r["path"], r["nd2"], main, hs,
                    lambda f, m, i=i: progress(0.5 * (i + f) / n,
                                               f"Reading movie {i + 1} of {n}: {m}")))
            DT.apply_quiz(movies, self.answers)
            held = DT.held_out(movies, chans, lambda f, m: progress(0.5 + 0.4 * f, m))
            limits = DT.fit(movies, chans, lambda f, m: progress(0.9 + 0.1 * f, m))
            return movies, held, limits
        self.movies, self.held, self.limits = W.run_with_progress(
            self, "Learning which cells you pick...", work, delay_ms=0)
        self._show_results()

    def relearn(self) -> None:
        """After the quiz: the same movies, your answers included."""
        chans = self.chans()

        def work(progress):
            DT.apply_quiz(self.movies, self.answers)
            held = DT.held_out(self.movies, chans, lambda f, m: progress(0.8 * f, m))
            limits = DT.fit(self.movies, chans, lambda f, m: progress(0.8 + 0.2 * f, m))
            return held, limits
        self.held, self.limits = W.run_with_progress(self, "Learning again with your answers...",
                                                     work, delay_ms=0)
        self._show_results()

    def detector(self, name: str = "") -> DT.Detector:
        chans = self.chans()
        return DT.Detector(name=name or self.ed_name.placeholderText(), main=self.main(),
                           helpers=self.helpers(), limits=self.limits or {},
                           trained_on=[dict(DT.score(m, DT.select(m.feat, self.limits, chans)),
                                            run=m.run) for m in self.movies],
                           held_out=self.held, quiz=list(self.answers))

    def _show_results(self) -> None:
        det = self.detector()
        self.lbl_rule.setText("Learned rule: " + det.rule_text())
        self.lbl_score.setText(det.score_text() + (f"  Your quiz answers so far: "
                                                   f"{len(self.answers)}." if self.answers else ""))
        rows = self.held or det.trained_on
        self.tbl_score.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r["movie"], r["yours"], r["right"], r["yours"] - r["right"], r["extra"],
                    f"{r['f1']:.2f}"]
            for j, v in enumerate(vals):
                self.tbl_score.setItem(i, j, QTableWidgetItem(str(v)))
        self.btn_quiz.setEnabled(bool(self.movies))
        self.btn_save.setEnabled(bool(self.movies))
        if self.movies:
            self.tbl_score.selectRow(0)
            self._show_movie()

    def _show_movie(self) -> None:
        i = self.tbl_score.currentRow()
        if not (0 <= i < len(self.movies)) or self.limits is None:
            return
        vp = self.pic.parentWidget()
        size = vp.size() if vp is not None else None
        pix = self.movie_picture(i, max(400, size.width() - 8) if size else 760)
        if size is not None and pix.height() > size.height() - 8:
            pix = pix.scaledToHeight(max(300, size.height() - 8), Qt.SmoothTransformation)
        self.pic.setPixmap(pix)

    def movie_picture(self, i: int, width: int = 760) -> QPixmap:
        """The movie's main channel with green / red / yellow outlines."""
        m = self.movies[i]
        names = list(self.channels)
        a = names.index(self.main()) if self.main() in names else 0
        plane = m.frame[min(a, m.frame.shape[0] - 1)]
        g = _grey(plane, *_levels(plane))
        rgb = np.dstack([g, g, g])
        keep = DT.select(m.feat, self.limits, self.chans()) & m.use
        for ci, r in enumerate(m.rois):
            if keep[ci]:
                _outline(rgb, r, GREEN if m.yours[ci] else YELLOW, width=2)
        for h in m.hand:                               # yours it missed
            hit = any(keep[ci] and m.yours[ci] and DT._iou(h, r) >= DT.MATCH_IOU
                      for ci, r in enumerate(m.rois))
            if not hit:
                _outline(rgb, h, RED, width=2)
        return _pixmap(rgb, width)

    # ---------------------------------------------------------------- 3
    def _quiz_buttons(self, on: bool) -> None:
        for b in (self.btn_keep, self.btn_skip, self.btn_unsure):
            b.setEnabled(on)

    def start_quiz(self) -> None:
        if not self.movies or self.limits is None:
            return
        self.quiz = DT.uncertain(self.movies, self.limits, self.chans(), QUIZ_N, self.answers)
        self.qi = 0
        if not self.quiz:
            self.lbl_q.setText("Nothing it is unsure about.")
            return
        self.btn_quiz.setEnabled(False)
        self._quiz_buttons(True)
        self._show_question()

    def _show_question(self) -> None:
        mi, ci = self.quiz[self.qi]
        m = self.movies[mi]
        names = list(self.channels)
        tiles = []
        for c in self.chans():
            k = names.index(c) if c in names else 0
            crop, (y0, x0, _y1, _x1) = DT.crop(m, ci)
            lo, hi = _levels(m.frame[min(k, m.frame.shape[0] - 1)])
            g = _grey(crop[min(k, crop.shape[0] - 1)], lo, hi)
            rgb = np.dstack([g, g, g])
            _outline(rgb, m.rois[ci], YELLOW, y0, x0)
            tiles.append(rgb)
            tiles.append(np.full((rgb.shape[0], 6, 3), 30, np.uint8))
        img = np.concatenate(tiles[:-1], axis=1)
        self.q_pics.setPixmap(_pixmap(img, min(900, 260 * len(self.chans()))))
        f = m.feat
        bits = [f"{c} {float(f['snr_' + c][ci]):.0f} x noise" for c in self.chans()]
        self.lbl_q.setText(f"{self.qi + 1} of {len(self.quiz)}  -  {m.name}  -  "
                           f"{', '.join(bits)}, {float(f['area'][ci]):.0f} um2   (left to right: "
                           f"{', '.join(self.chans())})")

    def answer(self, kind: str) -> None:
        if not self.quiz or self.qi >= len(self.quiz):
            return
        mi, ci = self.quiz[self.qi]
        m = self.movies[mi]
        cy, cx = (int(v) for v in m.rois[ci].centroid)
        y0, x0, y1, x1 = m.rois[ci].bbox
        if not m.rois[ci].mask[cy - y0, cx - x0]:       # a point inside the outline
            ys, xs = np.nonzero(m.rois[ci].mask)
            cy, cx = int(ys[len(ys) // 2]) + y0, int(xs[len(xs) // 2]) + x0
        self.answers.append(dict(movie=m.name, y=cy, x=cx, answer=kind))
        self.qi += 1
        if self.qi < len(self.quiz):
            self._show_question()
            return
        self._quiz_buttons(False)
        self.btn_quiz.setEnabled(True)
        self.btn_quiz.setText(f"Another {QUIZ_N}")
        self.q_pics.clear()
        self.lbl_q.setText("Thanks - learning again with your answers.")
        self.relearn()

    def keyPressEvent(self, e) -> None:                 # noqa: N802
        keys = {Qt.Key_K: "keep", Qt.Key_S: "skip", Qt.Key_N: "unsure"}
        if e.key() in keys and self.btn_keep.isEnabled():
            self.answer(keys[e.key()])
            return
        super().keyPressEvent(e)

    # ---------------------------------------------------------------- 4
    def save(self, name: str = "") -> Optional[Path]:
        if not self.movies or self.limits is None:
            return None
        name = (name or self.ed_name.text().strip() or self.ed_name.placeholderText()).strip()
        det = self.detector(name)
        try:
            p = DT.save(det)
        except FileExistsError:
            ans = QMessageBox.question(self, "Train auto-detect",
                                       f"You already have an auto-detect called '{name}'. "
                                       f"Replace it with this one?")
            if ans != QMessageBox.Yes:
                return None
            p = DT.save(det, overwrite=True)
        self.saved_path = p
        QMessageBox.information(self, "Train auto-detect",
                                f"Saved '{name}'. It is now a button under AUTO-DETECT for "
                                f"movies with the channels {', '.join(det.channels())}.")
        self.accept()
        return p
