"""
V2.7 'Prism style templates...' (File menu of the main window, and the Compare
window): open your two template files in GraphPad Prism to change their look,
take that look over for PeterPiper's own pictures, reset them, or open their folder.
See peterpiper.prismtemplate for what the files are and how they are used.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout

from .. import prismtemplate as T
from ..safety import error_text, plain_path
from . import widgets as W


def _open(path) -> None:
    if not W.open_path(path):                             # opens GraphPad Prism (Windows / macOS)
        raise OSError("no program to open it was found")


class TemplateDialog(QDialog):
    def __init__(self, on_look: Optional[Callable[[dict], None]] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prism style templates")
        self.on_look = on_look
        try:
            T.ensure()
        except OSError as e:
            QMessageBox.warning(self, "Prism style templates", error_text(e))
        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(
            "Every .prism PeterPiper writes is made from these two files, in your PeterPiper folder. "
            "Open one in GraphPad Prism, change the look (fonts, sizes, colours, symbols, "
            "lines, axes, frame, legend), and save it under the same name - from then on "
            "every new .prism uses it. Your data, titles and n always come from your runs."))
        lay.addWidget(W.wrapped_label(
            "1. Graph style: change GRAPH 1 of 'PeterPiper graph style.prism' and save.\n"
            "2. Column graph style (kinetics, drift per cell): in 'PeterPiper column graph "
            "style.prism' select the table 'Example groups', click New graph > Column > "
            "scatter dot plot (or bars) with mean ± SEM, style it and save. Until then, "
            "column tables are written without a graph.\n"
            "To make your look the default for everyone in a later version, send these two "
            "files to the developer.", muted=True))
        self.lbl = W.wrapped_label("")
        lay.addWidget(self.lbl)
        lay.addWidget(W.row(
            W.button("Edit graph style in Prism", lambda: self._edit(T.xy_path()),
                     "Opens 'PeterPiper graph style.prism' in GraphPad Prism."),
            W.button("Edit column graph style in Prism", lambda: self._edit(T.column_path()),
                     "Opens 'PeterPiper column graph style.prism' in GraphPad Prism.")))
        lay.addWidget(W.row(
            W.button("Use this look for PeterPiper's pictures too", self._take_look,
                     "Reads the look of graph 1 (error, colours, line widths, symbols, axis "
                     "ranges, font size) into PeterPiper's graph style, so PNG / SVG / PDF match "
                     "the Prism files."),
            W.button("Open the folder", lambda: _open(T.folder()))))
        lay.addWidget(W.row(
            W.button("Reset graph style", lambda: self._reset("xy"),
                     "Your file is renamed '(old 1)' (never deleted) and PeterPiper's look is "
                     "written again."),
            W.button("Reset column graph style", lambda: self._reset("column")),
            W.button("Close", self.accept)))
        self._status()

    def _status(self) -> None:
        xy = T.active_xy()
        col = T.column_template()
        self.lbl.setText(
            f"Folder: {plain_path(str(T.folder()))}\n"
            f"Graph style: {'yours (used for every XY graph)' if xy else 'not usable - reset it'}"
            f"\nColumn graph style: "
            f"{'made - used for every column table' if col else 'no column graph yet'}")

    def _edit(self, path) -> None:
        try:
            T.ensure()
            _open(path)
        except OSError as e:
            QMessageBox.warning(self, "Prism style templates",
                                f"Could not open {plain_path(str(path))}:\n{error_text(e)}")

    def _take_look(self) -> None:
        from ..prismstyle import read_style
        try:
            st, notes = read_style(str(T.xy_path()), ignore_texts=True)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Prism style templates", error_text(e))
            return
        if self.on_look:
            self.on_look(st)
        QMessageBox.information(self, "Prism style templates",
                                "PeterPiper's pictures now use this look." +
                                ("\n" + "\n".join(notes) if notes else ""))

    def _reset(self, which: str) -> None:
        if QMessageBox.question(self, "Prism style templates",
                                "Put PeterPiper's own look back? Your file is kept, renamed "
                                "'(old 1)'.") != QMessageBox.Yes:
            return
        try:
            T.reset(which)
        except OSError as e:
            QMessageBox.warning(self, "Prism style templates", error_text(e))
        self._status()
