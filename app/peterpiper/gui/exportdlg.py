"""
'Choose outputs': left, everything that can be made (grouped by compartment);
right, YOUR EXPORT LIST. Add (or double-click) puts an item on the list, Remove
takes it off; only what is on the list is written - one tidy folder per export.

SaveGraphDialog: 'Save this graph...' in the trace panel ('As exported' view) -
the graph shown as a Prism file, a 300 dpi PNG and / or an SVG.
"""
from __future__ import annotations

from typing import List, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import graphstyle as GS
from ..prismfile import template_takes_style
from . import widgets as W


class ExportDialog(QDialog):

    def __init__(self, cat: Sequence[dict], chosen: Sequence[str], standard: Sequence[str],
                 where: str, parent=None, template: str = "", prefix: str = "",
                 graph_look: str = "", graph_style: dict = None) -> None:
        super().__init__(parent)
        self._graph_style = dict(graph_style or {})
        self.setWindowTitle("Choose outputs")
        self.resize(1000, 620)
        self._cat = {it["key"]: it for it in cat}
        self._standard = [k for k in standard if k in self._cat]
        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(
            "Put what you want on YOUR EXPORT LIST (right): select items on the left and press "
            "'Add', or double-click them. Only the list is written, into a new folder:  "
            + where, muted=True))

        from PySide6.QtWidgets import QLineEdit
        nrow = QWidget()
        nl = QHBoxLayout(nrow)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.addWidget(QLabel("<b>Name for the files:</b>"))
        self.ed_prefix = QLineEdit(prefix)
        self.ed_prefix.setToolTip("Every file of this export starts with this name, e.g. "
                                  "<name>_nucleus.xlsx. Letters, numbers, - _ . ( ) and spaces.")
        self.ed_prefix.textChanged.connect(lambda _t: self._show_example())
        nl.addWidget(self.ed_prefix, 1)
        self.lbl_example = QLabel("")
        self.lbl_example.setProperty("muted", True)
        nl.addWidget(self.lbl_example)
        lay.addWidget(nrow)
        self._default_prefix = prefix

        mid = QWidget()
        ml = QHBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("<b>Available outputs</b>"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(lambda it, _c: self._add([it]))
        lv.addWidget(self.tree, 1)
        ml.addWidget(left, 3)

        buttons = QWidget()
        bv = QVBoxLayout(buttons)
        bv.addStretch(1)
        self.btn_add = QPushButton("Add  →")
        self.btn_add.setProperty("primary", True)
        self.btn_add.clicked.connect(lambda: self._add(self.tree.selectedItems()))
        bv.addWidget(self.btn_add)
        self.btn_rem = QPushButton("←  Remove")
        self.btn_rem.clicked.connect(self._remove)
        bv.addWidget(self.btn_rem)
        bv.addStretch(1)
        ml.addWidget(buttons)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.lbl_list = QLabel("")
        rv.addWidget(self.lbl_list)
        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lst.itemDoubleClicked.connect(lambda _it: self._remove())
        rv.addWidget(self.lst, 1)
        rv.addWidget(W.row(W.button("Standard set", self._use_standard,
                                    "Excel, Prism, F/F0 and R/R0 graphs, the ROI picture and "
                                    "the ROI file."),
                           W.button("Everything", self._use_all),
                           W.button("Clear list", self._clear)))
        ml.addWidget(right, 3)
        lay.addWidget(mid, 1)

        # ---- Prism graphs from your own template
        self.template = template or ""
        trow = QWidget()
        tl = QHBoxLayout(trow)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(QLabel("<b>Prism graph style:</b>"))
        self.lbl_tpl = QLabel("")
        self.lbl_tpl.setWordWrap(True)
        tl.addWidget(self.lbl_tpl, 1)
        tl.addWidget(W.button("Choose style...", self._choose_tpl,
                              "A .prism file (Prism 10+) whose FIRST graph is styled the way you "
                              "want, made on an XY table with cells as replicates. Every "
                              "'Prism graphs' file then uses that style. (A .pzfx with graphs "
                              "also works, for '..._with_graphs.pzfx'.)"))
        tl.addWidget(W.button("Built-in", lambda: self._set_tpl("")))
        tl.addWidget(W.button("How?", self._tpl_help))
        lay.addWidget(trow)
        self._set_tpl(self.template)
        # ---- the graph look (chosen in the trace panel) and what Prism gets of it
        self.lbl_look = W.wrapped_label(
            f"<b>Graph look:</b> {graph_look or 'mean ± SEM'} - change it in the Traces "
            f"panel, 'As exported' view (what you see there is what the PNG graphs show).")
        lay.addWidget(self.lbl_look)
        self.lbl_prism_look = W.wrapped_label("", muted=True)
        lay.addWidget(self.lbl_prism_look)
        self._sync_prism_look()

        self.chk_remember = QCheckBox("Remember this list for next time")
        self.chk_remember.setChecked(True)
        lay.addWidget(self.chk_remember)
        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addStretch(1)
        bl.addWidget(W.button("Cancel", self.reject))
        self.btn_go = W.button("Export", self.accept, strong=True)
        self.btn_go.setMinimumWidth(140)
        bl.addWidget(self.btn_go)
        lay.addWidget(bottom)

        self._fill_tree()
        for k in chosen:
            if k in self._cat:
                self._put(k)
        self._sync()
        self._show_example()

    # -------------------------------------------------------------- file names
    def prefix(self) -> str:
        from ..export import clean_prefix
        return clean_prefix(self.ed_prefix.text()) or self._default_prefix

    def _show_example(self) -> None:
        p = self.prefix()
        self.lbl_example.setText(f"e.g.  {p}_nucleus.xlsx")
        self.btn_go.setEnabled(bool(self.keys()) and bool(p))

    # ---------------------------------------------------------- Prism template
    def _set_tpl(self, path: str) -> None:
        from pathlib import Path
        self.template = path or ""
        if self.template and Path(self.template).exists():
            if not self.template.lower().endswith(".prism"):
                kind = "each .pzfx also comes as ..._with_graphs.pzfx"
            elif template_takes_style(self.template):
                kind = ("made from PeterPiper's Prism file: 'Prism graphs' use its layout with "
                        "your graph look")
            else:
                kind = ("not made from PeterPiper's Prism file: 'Prism graphs' keep this file's "
                        "own look (only the data and the titles are filled in)")
            self.lbl_tpl.setText(f"your file {Path(self.template).name} - {kind}")
        else:
            self.template = ""
            self.lbl_tpl.setText("built-in: the graph in your graph look (below).")
        if hasattr(self, "lbl_prism_look"):
            self._sync_prism_look()

    def _sync_prism_look(self) -> None:
        """What the .prism graphs will show, said plainly."""
        tpl = self.template if self.template.lower().endswith(".prism") else ""
        if not template_takes_style(tpl):
            self.lbl_prism_look.setText(
                "Prism files (.prism): your own Prism file's look wins - the live graph's "
                "look (colours, error type, lines, axis ranges, font size) is not applied "
                "to it. For the live graph's look in Prism, press 'Built-in' or choose a "
                "file made from one of PeterPiper's .prism files.")
            return
        warn = GS.prism_look(self._graph_style)[1]
        self.lbl_prism_look.setText(
            "Prism files (.prism) get this look too (error type, colours, lines, symbols, "
            "each cell, titles, axis ranges, font size)."
            + ((" Not possible in Prism: " + " ".join(warn)) if warn else ""))

    def _choose_tpl(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getOpenFileName(self, "Your Prism graph style", "",
                                              "Prism 10+ project (*.prism);;Prism XML (*.pzfx)")
        if not path:
            return
        try:
            if path.lower().endswith(".prism"):
                import json
                import zipfile
                from ..safety import long_path
                with zipfile.ZipFile(long_path(path)) as zf:
                    doc = json.loads(zf.read("document.json"))
                if not doc.get("sheets", {}).get("graphs") or not doc["sheets"].get("data"):
                    raise ValueError("That file has no graph (or no data table).")
            else:
                from ..prism import read_template
                read_template(path)
        except Exception as exc:                            # noqa: BLE001
            from ..safety import error_text
            QMessageBox.warning(self, "Not a usable style file", error_text(exc))
            return
        self._set_tpl(path)

    def _tpl_help(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Prism graphs",
            "'Prism graphs (.prism)' on the list writes one Prism 10+ project per key quantity "
            "with the graph ALREADY MADE from the included cells, in your graph look (Traces "
            "panel, 'As exported' view): error type (SEM / SD / 95% CI), colours, line "
            "widths, symbols, each cell, titles, axis ranges and font size. Its tables: cells "
            "as replicates (the graph's data), mean / SEM / n, each cell by name, and the "
            "baseline drift slopes if chosen.\n\n"
            "Prism cannot draw a shaded band, a hidden mean or the dashed line at time 0: "
            "the Prism file then shows error bars instead of the band, the mean as a "
            "hairline, and no dashed line. The Traces panel warns you when your look has "
            "one of these.\n\n"
            "Your own Prism file ('Choose style...'): if it was made from one of PeterPiper's "
            ".prism files (opened in Prism, changed, File > Save), its layout is used and "
            "your graph look is applied on top of it. Any other Prism file keeps its own "
            "look: only the data and the titles are filled in.\n\n"
            "Prism 9 or older: use 'Prism tables (.pzfx)'.")

    # ------------------------------------------------------------------ build
    def _fill_tree(self) -> None:
        groups, sections = {}, {}
        for key, it in self._cat.items():
            g = groups.get(it["group"])
            if g is None:
                g = QTreeWidgetItem(self.tree, [it["group"]])
                g.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                g.setExpanded(True)
                groups[it["group"]] = g
            parent = g
            if it["section"]:
                sk = (it["group"], it["section"])
                parent = sections.get(sk)
                if parent is None:
                    parent = QTreeWidgetItem(g, [it["section"]])
                    parent.setExpanded(True)
                    sections[sk] = parent
            leaf = QTreeWidgetItem(parent, [it["label"]])
            leaf.setData(0, Qt.UserRole, key)

    def _leaves(self, items) -> List[str]:
        keys = []

        def walk(it):
            k = it.data(0, Qt.UserRole)
            if k:
                keys.append(k)
            for i in range(it.childCount()):
                walk(it.child(i))
        for it in items:
            walk(it)                          # a group / section adds all its items
        return keys

    # ---------------------------------------------------------------- actions
    def _put(self, key: str) -> None:
        if key in self.keys():
            return
        it = self._cat[key]
        txt = it["label"] if it["group"] == "Whole experiment" else f"{it['group']}  ·  {it['label']}"
        li = QListWidgetItem(txt)
        li.setData(Qt.UserRole, key)
        self.lst.addItem(li)

    def _add(self, items) -> None:
        for k in self._leaves(items):
            self._put(k)
        self._sync()

    def _remove(self) -> None:
        for li in self.lst.selectedItems():
            self.lst.takeItem(self.lst.row(li))
        self._sync()

    def _clear(self) -> None:
        self.lst.clear()
        self._sync()

    def _use_standard(self) -> None:
        self.lst.clear()
        for k in self._standard:
            self._put(k)
        self._sync()

    def _use_all(self) -> None:
        for k in self._cat:
            self._put(k)
        self._sync()

    def _sync(self) -> None:
        on = set(self.keys())
        n = len(on)
        self.lbl_list.setText(f"<b>Your export list ({n} item{'s' if n != 1 else ''})</b>")
        self.btn_go.setText(f"Export {n} item{'s' if n != 1 else ''}")
        self.btn_go.setEnabled(n > 0)

        normal, muted = self.tree.palette().text(), QBrush(QColor(140, 140, 140))

        def walk(it):
            k = it.data(0, Qt.UserRole)
            if k:
                it.setForeground(0, muted if k in on else normal)
                it.setText(0, ("✓  " if k in on else "") + self._cat[k]["label"])
            for i in range(it.childCount()):
                walk(it.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def keys(self) -> List[str]:
        return [self.lst.item(i).data(Qt.UserRole) for i in range(self.lst.count())]


class SaveGraphDialog(QDialog):
    """'Save this graph...': the graph shown in the trace panel ('As exported'),
    as a Prism file, a 300 dpi PNG and / or an SVG. Nothing is replaced."""

    FORMAT_TEXT = {
        "prism": "Prism file (.prism, Prism 10+) - the same data, titles and look (see "
                 "below for what Prism cannot draw)",
        "png": "PNG picture, 300 dpi - exactly as shown in the panel",
        "svg": "SVG drawing - exactly as shown; the text stays editable (Illustrator, "
               "Inkscape, PowerPoint)",
    }

    def __init__(self, what: str, folder: str, name: str, formats: Sequence[str] = ("prism",
                 "png"), prism_style: str = "", parent=None,
                 graph_style: dict = None) -> None:
        from pathlib import Path
        from PySide6.QtWidgets import QLineEdit
        super().__init__(parent)
        self.setWindowTitle("Save this graph")
        self.resize(640, 380)
        self._folder = str(folder)
        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(f"<b>{what}</b>"))
        self.chk: dict = {}
        for f in ("prism", "png", "svg"):
            c = QCheckBox(self.FORMAT_TEXT[f])
            c.setChecked(f in set(formats))
            c.toggled.connect(lambda _v: self._sync())
            self.chk[f] = c
            lay.addWidget(c)
        if prism_style and not template_takes_style(prism_style):
            note = (f"The .prism file is made from your own Prism file "
                    f"{Path(prism_style).name}, which was not made from PeterPiper's: it keeps "
                    f"that file's look - only the data (the included cells), the title and "
                    f"the axis titles are filled in. The PNG / SVG show the look shown here.")
        else:
            warn = GS.prism_look(graph_style or {})[1]
            note = ("The .prism file shows the graph in the look shown here: "
                    f"{GS.prism_summary(graph_style or {})}, with the same colours, lines, "
                    "symbols, titles, axis ranges and font size"
                    + (f" (on the layout of your Prism file {Path(prism_style).name})"
                       if prism_style else "") + "."
                    + ((" Not possible in Prism: " + " ".join(warn)) if warn else ""))
        self.lbl_prism_note = W.wrapped_label(note, muted=True)
        lay.addWidget(self.lbl_prism_note)

        frow = QWidget()
        fl = QHBoxLayout(frow)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(QLabel("<b>Folder:</b>"))
        self.lbl_folder = QLabel(self._folder)
        self.lbl_folder.setWordWrap(True)
        self.lbl_folder.setToolTip(self._folder)
        fl.addWidget(self.lbl_folder, 1)
        fl.addWidget(W.button("Change...", self._choose_folder))
        lay.addWidget(frow)
        nrow = QWidget()
        nl = QHBoxLayout(nrow)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.addWidget(QLabel("<b>File name:</b>"))
        self.ed_name = QLineEdit(name)
        self.ed_name.setToolTip("Letters, numbers, - _ . ( ) and spaces. The ending (.prism, "
                                ".png, .svg) is added.")
        self.ed_name.textChanged.connect(lambda _t: self._sync())
        nl.addWidget(self.ed_name, 1)
        lay.addWidget(nrow)
        self._default_name = name
        lay.addWidget(W.wrapped_label("Existing files are never replaced: a file of the same "
                                      "name gets _2, _3 ... added.", muted=True))
        lay.addStretch(1)
        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addStretch(1)
        bl.addWidget(W.button("Cancel", self.reject))
        self.btn_go = W.button("Save", self.accept, strong=True)
        bl.addWidget(self.btn_go)
        lay.addWidget(bottom)
        self._sync()

    def _choose_folder(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Save the graph in", self._folder)
        if d:
            self._folder = d
            self.lbl_folder.setText(d)
            self.lbl_folder.setToolTip(d)

    def _sync(self) -> None:
        self.btn_go.setEnabled(bool(self.formats()) and bool(self.name()))

    def formats(self) -> List[str]:
        return [f for f, c in self.chk.items() if c.isChecked()]

    def folder(self) -> str:
        return self._folder

    def name(self) -> str:
        from ..export import clean_prefix
        return clean_prefix(self.ed_name.text(), 150) or ""
