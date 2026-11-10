"""
V2.9 'Who is using PeterPiper?' - the first window: pick your name or make a new
user (peterpiper.users). Each user's settings, runs, groups and saved files are kept
in their own folder; nobody else's work is listed. Rename / Remove (only hides -
nothing is deleted) and 'Don't ask again on this Windows account'.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QVBoxLayout)

from .. import users
from . import widgets as W


class UserDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from .. import APP_NAME
        self.setWindowTitle(f"{APP_NAME} - who is using it?")
        self.resize(540, 560)
        self.chosen: Optional[str] = None
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(W.LogoLabel(70))             # PeterPiper 1.0: the logo
        t = QLabel("Who is using PeterPiper?")
        t.setProperty("role", "title")
        lay.addWidget(t)
        lay.addWidget(W.wrapped_label(
            "Each person's settings, runs, groups and saved files are kept in their own "
            "folder, and results next to a movie go into OUTPUT_<movie>\\<your name>. You only "
            "see your own analyses. (No password: this keeps work apart, it does not lock it.)",
            muted=True))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _it: self._go())
        self.list.currentItemChanged.connect(lambda *_: self._update())
        lay.addWidget(self.list, 1)
        self.btn_rename = W.button("Rename...", self._rename,
                                   "Give the selected user another name - their runs stay "
                                   "theirs.")
        self.btn_remove = W.button("Remove...", self._remove,
                                   "Take the selected user off this list. Nothing is deleted; "
                                   "adding the same name again brings them back.")
        self.btn_import = W.button("Import a profile...", self._import,
                                   "A profile exported on another computer (.zip), or a copied "
                                   "profile folder: added as a user, or merged into the user of "
                                   "the same name (nothing here is overwritten).")
        self.btn_import.setAutoDefault(False)
        r = W.row(self.btn_rename, self.btn_remove)
        r.layout().addStretch(1)
        r.layout().addWidget(self.btn_import)
        lay.addWidget(r)
        self.ed_new = QLineEdit()
        self.ed_new.setPlaceholderText("New user: type a name (e.g. Peter, or Smith lab - Ana)")
        self.ed_new.textChanged.connect(lambda _t: self._update())
        self.btn_add = W.button("Add user", self._add, "Make a new user with this name.")
        self.btn_add.setAutoDefault(False)
        lay.addWidget(W.row(self.ed_new, self.btn_add))
        self.lbl_note = W.wrapped_label("", muted=True)
        lay.addWidget(self.lbl_note)
        self.chk_dont = QCheckBox("Don't ask again on this Windows account (Switch user... in "
                                  "the first window asks again)")
        self.chk_dont.setToolTip("For a computer where each person has their own Windows "
                                 "login: PeterPiper then starts straight away as this user.")
        self.chk_dont.setChecked(bool(users._load().get("dont_ask")))
        lay.addWidget(self.chk_dont)
        self.btn_go = W.button("Continue", self._go, "Start PeterPiper as this user.", strong=True)
        self.btn_go.setDefault(True)                  # Enter continues
        btn_quit = W.button("Quit", self.reject, "Close PeterPiper.")
        btn_quit.setAutoDefault(False)
        for b in (self.btn_rename, self.btn_remove):
            b.setAutoDefault(False)
        bl = QHBoxLayout()
        bl.addStretch(1)
        bl.addWidget(btn_quit)
        bl.addWidget(self.btn_go)
        lay.addLayout(bl)
        found = users.adopt_copied_profiles()      # folders pasted in from another computer
        self._fill(users.last_user())
        if found:
            self.lbl_note.setText("Found copied profile(s): " + ", ".join(found) + ".")

    def keyPressEvent(self, ev) -> None:                          # noqa: N802
        """Enter in the name box adds the user; anywhere else it continues."""
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and self.ed_new.hasFocus():
            if self.ed_new.text().strip():
                self._add()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def _fill(self, select: Optional[str]) -> None:
        self.list.clear()
        owner = users.legacy_owner()
        for u in users.list_users():
            it = QListWidgetItem(u)
            it.setData(Qt.UserRole, u)
            if u == owner:
                it.setToolTip("Also has the analyses and settings that were on this computer "
                              "before user profiles.")
            self.list.addItem(it)
            if u == select:
                self.list.setCurrentItem(it)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        if not self.list.count():
            self.lbl_note.setText("No users yet: type your name and press Add user. "
                                  "(PeterPiper starts empty: nothing is taken "
                                  "over from PD4nav; Import a profile... brings one in.)")
            self.ed_new.setFocus()
        else:
            self.list.setFocus()
        self._update()

    def _picked(self) -> Optional[str]:
        it = self.list.currentItem()
        return str(it.data(Qt.UserRole)) if it is not None else None

    def _update(self) -> None:
        txt = self.ed_new.text().strip()
        why = users.name_problem(txt) if txt else ""
        self.btn_add.setEnabled(bool(txt) and not why)
        if txt:
            back = any(u.lower() == users.clean_name(txt).lower() for u in users.all_users())
            self.lbl_note.setText(why or (f"Press Add user to bring '{users.clean_name(txt)}' "
                                          f"back (removed earlier; nothing was deleted)."
                                          if back else
                                          f"Press Add user to make '{users.clean_name(txt)}'."))
        elif self.list.count():
            self.lbl_note.setText("Double-click your name, or pick it and press Continue "
                                  "(Enter).")
        has = self._picked() is not None
        self.btn_go.setEnabled(has)
        self.btn_rename.setEnabled(has)
        self.btn_remove.setEnabled(has)

    def _add(self) -> None:
        txt = self.ed_new.text().strip()
        if not txt or users.name_problem(txt):
            return
        try:
            n = users.add_user(txt)
        except (OSError, ValueError) as exc:
            self.lbl_note.setText(f"Could not add the user: {exc}")
            return
        self.ed_new.clear()
        self._fill(n)

    def _rename(self) -> None:
        old = self._picked()
        if old is None:
            return
        new, ok = QInputDialog.getText(self, "Rename user", f"New name for '{old}':",
                                       QLineEdit.Normal, old)
        if not ok or not new.strip() or users.clean_name(new) == old:
            return
        try:
            n = users.rename_user(old, new)
        except (OSError, ValueError) as exc:
            self.lbl_note.setText(f"Not renamed: {exc}")
            return
        self._fill(n)
        self.lbl_note.setText(f"'{old}' is now '{n}' - the same folder and runs.")

    def _remove(self) -> None:
        u = self._picked()
        if u is None:
            return
        if QMessageBox.question(
                self, "Remove user",
                f"Take '{u}' off this list?\n\nNothing is deleted: their settings, runs and "
                f"results stay on disk, and adding the name '{u}' again brings them back.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        users.remove_user(u)
        self._fill(users.last_user())
        self.lbl_note.setText(f"'{u}' removed from the list (nothing deleted).")

    def _import(self) -> None:
        import_profile_dialog(self)
        self._fill(users.last_user())

    def _go(self) -> None:
        u = self._picked()
        if u is None:
            return
        self.chosen = u
        users.set_dont_ask(self.chk_dont.isChecked())
        self.accept()


def import_profile_dialog(parent) -> Optional[str]:
    """V3.0: pick an exported profile (.zip) and import it; says what happened."""
    from PySide6.QtWidgets import QFileDialog
    path, _f = QFileDialog.getOpenFileName(parent, "Import a profile", "",
                                           "PeterPiper profile (*.zip)")
    if not path:
        return None
    try:
        name, notes = W.run_with_progress(parent, "Importing the profile",
                                          lambda _p: users.import_profile(path))
    except (OSError, ValueError) as exc:
        QMessageBox.warning(parent, "Import a profile", f"Not imported: {exc}")
        return None
    QMessageBox.information(parent, "Import a profile",
                            f"Imported as '{name}': " + "; ".join(notes) + ". Runs whose "
                            f"files are somewhere else on this computer: Compare / average runs "
                            f"> My data is in...")
    return name


def export_profile_dialog(parent) -> None:
    """V3.0: the current user's whole profile in one zip, for another computer."""
    from datetime import date
    from PySide6.QtWidgets import QFileDialog
    u = users.current()
    if not u:
        return
    default = f"PeterPiper profile - {users.folder_name(u)} - {date.today().isoformat()}.zip"
    path, _f = QFileDialog.getSaveFileName(parent, "Export my profile", default,
                                           "PeterPiper profile (*.zip)")
    if not path:
        return
    try:
        out = W.run_with_progress(parent, "Exporting your profile",
                                  lambda _p: users.export_profile(u, path))
    except OSError as exc:
        QMessageBox.warning(parent, "Export my profile", f"Not exported: {exc}")
        return
    QMessageBox.information(parent, "Export my profile",
                            f"Your profile (settings, run list, groups, colours, labels, Prism "
                            f"templates, saved settings, saved-files log) is in: {out}. On the "
                            f"other computer: Import a profile... in the first window. Your "
                            f"analyses themselves stay next to your movies (OUTPUT_<movie>/"
                            f"{users.folder_name(u)}) - copy those folders with the movies.")
