"""
V2.9 'Who is using PeterPiper?' - the first window: pick your name or make a new
user (peterpiper.users). Each user's settings, runs, groups and saved files are kept
in their own folder; nobody else's work is listed. Rename / Remove (only hides -
nothing is deleted) and 'Don't ask again on this Windows account'.

PeterPiper 1.1 (part "profiles"): the main choice first (pick your name / add a
user); below it one calm "Profile & lab" box:
  * Keep in step: Off / <folder> (Change...) - the selected person's profile kept
    in step through a folder of their own cloud drive (profilesync);
  * Lab folder: <folder> / not linked (Lab settings... - admins and developers:
    link / create / unlink the lab's shared folder, the lab user list with
    roles, spellings and passwords, and the lab's .nd2 data folders - labshare);
  * Merge profiles... (two spellings of one person, or a profile from another
    computer, merged INTO a chosen user - nothing deleted), Import a profile...
    and More (Rename, Remove, Export, Password).
On the very first start (nobody yet) the window also offers "Link to your lab's
shared PeterPiper folder..." next to Add user.
Names may carry a small decoration (achievements.name_flair - display only: the
real name is used everywhere else).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton,
                               QRadioButton, QToolButton, QVBoxLayout, QWidget)

from .. import users
from . import widgets as W

PASSWORD_NOTE = ("A password keeps profiles tidy and private between colleagues. It is not "
                 "strong security: the files are on a shared disk.")


# --------------------------------------------------------------- small helpers
class ElideLabel(QLabel):
    """One line; a long folder path is shortened in the middle (the whole text is
    the tooltip), so a long path never makes the window wider."""

    def __init__(self, text: str = "", muted: bool = True) -> None:
        super().__init__()
        self._full = ""
        if muted:
            self.setProperty("muted", True)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self.setText(text)

    def setText(self, text: str) -> None:                     # noqa: N802
        self._full = str(text)
        self.setToolTip(self._full)
        self._elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, ev) -> None:                        # noqa: N802
        super().resizeEvent(ev)
        self._elide()

    def _elide(self) -> None:
        w = max(40, self.width())
        super().setText(self.fontMetrics().elidedText(self._full, Qt.ElideMiddle, w))


def _flair_fns():
    """(name_flair, set_target_user) from achievements (part looks), or Nones."""
    try:
        from .. import achievements as A
        return getattr(A, "name_flair", None), getattr(A, "set_target_user", None)
    except Exception:                                              # noqa: BLE001
        return None, None


def _set_target(name: Optional[str]) -> None:
    _nf, st = _flair_fns()
    if st is not None:
        try:
            st(name)
        except Exception:                                          # noqa: BLE001
            pass


def _labshare():
    try:
        from .. import labshare
        return labshare
    except Exception:                                              # noqa: BLE001
        return None


def _profilesync():
    try:
        from .. import profilesync
        return profilesync
    except Exception:                                              # noqa: BLE001
        return None


def ask_password(parent, who: str, why: str = "") -> Optional[str]:
    """The password of `who` (None = cancelled). Tests replace this."""
    txt, ok = QInputDialog.getText(parent, "Password", (why or f"Password of '{who}':"),
                                   QLineEdit.Password)
    return txt if ok else None


def unlock(parent, who: str, why: str = "") -> bool:
    """True if `who` has no password, or the right one was typed."""
    if not users.has_password(who):
        return True
    for _ in range(3):
        pw = ask_password(parent, who, why)
        if pw is None:
            return False
        if users.check_password(who, pw):
            return True
        why = f"Wrong password - try again. Password of '{who}':"
    return False


def pick_users(parent, title: str, text: str, names: List[str]) -> Optional[List[str]]:
    """A checkable list (all ticked); the ticked names, or None if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle(title)
    lay = QVBoxLayout(d)
    lay.addWidget(W.wrapped_label(text))
    lst = QListWidget()
    for n in names:
        it = QListWidgetItem(n)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked)
        lst.addItem(it)
    lay.addWidget(lst)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    if d.exec() != QDialog.Accepted:
        return None
    return [lst.item(i).text() for i in range(lst.count())
            if lst.item(i).checkState() == Qt.Checked]


def _suggest_start() -> str:
    ps = _profilesync()
    try:
        s = ps.suggest_folders() if ps else []
    except Exception:                                              # noqa: BLE001
        s = []
    return s[0][1] if s else str(Path.home())


# ================================================================= first window
class UserDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from .. import APP_NAME
        self.setWindowTitle(f"{APP_NAME} - who is using it?")
        self.resize(580, 600)
        self.chosen: Optional[str] = None
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.addWidget(W.LogoLabel(60))             # PeterPiper 1.0: the logo
        t = QLabel("Who is using PeterPiper?")
        t.setProperty("role", "title")
        lay.addWidget(t)
        lay.addWidget(W.wrapped_label(
            "Pick your name. Your settings, runs and saved files are kept apart from "
            "everybody else's; results go into OUTPUT_<movie>\\<your name>.", muted=True))
        self.list = QListWidget()
        self.list.setMinimumHeight(110)
        self.list.itemDoubleClicked.connect(lambda _it: self._go())
        self.list.currentItemChanged.connect(lambda *_: self._update())
        lay.addWidget(self.list, 1)
        self.ed_new = QLineEdit()
        self.ed_new.setPlaceholderText("New user: type a name (e.g. Peter, or Smith lab - Ana)")
        self.ed_new.textChanged.connect(lambda _t: self._update())
        self.btn_add = W.button("Add user", self._add, "Make a new user with this name.")
        self.btn_add.setAutoDefault(False)
        lay.addWidget(W.row(self.ed_new, self.btn_add))
        # first start: link to the lab's folder instead of typing a name
        self.btn_lab_first = W.button(
            "Link to your lab's shared PeterPiper folder...", self._link_first,
            "If your lab keeps a shared PeterPiper folder (on a lab server or a cloud "
            "drive): link it, and the lab's users appear here.")
        self.btn_lab_first.setAutoDefault(False)
        self.row_first = W.row(QLabel("or"), self.btn_lab_first)
        self.row_first.layout().addStretch(1)
        lay.addWidget(self.row_first)
        self.lbl_note = W.wrapped_label("", muted=True)
        lay.addWidget(self.lbl_note)

        # ---- Profile & lab: compact, one place
        box = QGroupBox("Profile && lab")
        g = QGridLayout(box)
        g.setContentsMargins(8, 6, 8, 8)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(4)
        g.addWidget(QLabel("Keep in step:"), 0, 0)
        self.lbl_sync = ElideLabel("Off")
        g.addWidget(self.lbl_sync, 0, 1)
        self.btn_sync = W.button("Change...", self._sync,
                                 "Keep this person's profile the same on every computer they "
                                 "use, through a folder of their own cloud drive (OneDrive, "
                                 "Google Drive, Box, Dropbox, iCloud Drive) or a network "
                                 "folder. Free; nothing is deleted.")
        g.addWidget(self.btn_sync, 0, 2)
        g.addWidget(QLabel("Lab folder:"), 1, 0)
        self.lbl_lab = ElideLabel("not linked")
        g.addWidget(self.lbl_lab, 1, 1)
        self.btn_lab = W.button("Lab settings...", self._lab_settings,
                                "Admins and developers: the lab's shared PeterPiper folder, "
                                "the lab user list (roles, spellings, passwords) and the "
                                "lab's data folders.")
        g.addWidget(self.btn_lab, 1, 2)
        g.setColumnStretch(1, 1)
        self.btn_merge = W.button("Merge profiles...", self._merge,
                                  "The same person under two spellings (e.g. 'Ana Lopez' and "
                                  "'A. Lopez'), or a profile from another computer: merge "
                                  "everything into one user. Nothing is deleted.")
        self.btn_import = W.button("Import a profile...", self._import,
                                   "A profile exported on another computer (.zip), or a copied "
                                   "profile folder: added as a user, or merged into the user of "
                                   "the same name (nothing here is overwritten).")
        self.btn_more = QToolButton()
        self.btn_more.setText("More")
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.btn_more)
        self.act_rename = m.addAction("Rename...", self._rename)
        self.act_remove = m.addAction("Remove...", self._remove)
        m.addSeparator()
        self.act_export = m.addAction("Export this profile...", self._export)
        self.act_password = m.addAction("Password...", self._password)
        self.btn_more.setMenu(m)
        self.btn_more.setToolTip("Rename, remove (nothing is deleted), export this profile, "
                                 "or set a password.")
        rb = W.row(self.btn_merge, self.btn_import, self.btn_more)
        rb.layout().addStretch(1)
        g.addWidget(rb, 2, 0, 1, 3)
        lay.addWidget(box)
        # compatibility: the rename / remove actions as buttons (older code / tests)
        self.btn_rename = self.act_rename
        self.btn_remove = self.act_remove

        self.chk_dont = QCheckBox("Don't ask again on this account")
        self.chk_dont.setToolTip("For a computer where each person has their own login: "
                                 "PeterPiper then starts straight away as this user (Switch "
                                 "user... in the first window asks again).")
        self.chk_dont.setChecked(bool(users._load().get("dont_ask")))
        self.btn_go = W.button("Continue", self._go, "Start PeterPiper as this user.", strong=True)
        self.btn_go.setDefault(True)                  # Enter continues
        btn_quit = W.button("Quit", self.reject, "Close PeterPiper.")
        btn_quit.setAutoDefault(False)
        for b in (self.btn_sync, self.btn_lab, self.btn_merge, self.btn_import,
                  self.btn_lab_first):
            b.setAutoDefault(False)
        bl = QHBoxLayout()
        bl.addWidget(self.chk_dont)
        bl.addStretch(1)
        bl.addWidget(btn_quit)
        bl.addWidget(self.btn_go)
        lay.addLayout(bl)
        found = users.adopt_copied_profiles()      # folders pasted in / the lab's list
        self._fill(users.last_user())
        if found:
            self.lbl_note.setText("New here: " + ", ".join(found) + ".")

    # ---------------------------------------------------------------- events
    def keyPressEvent(self, ev) -> None:                          # noqa: N802
        """Enter in the name box adds the user; anywhere else it continues."""
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and self.ed_new.hasFocus():
            if self.ed_new.text().strip():
                self._add()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def showEvent(self, ev) -> None:                              # noqa: N802
        super().showEvent(ev)
        self._fill(self._picked())                 # the decorations change each time

    def done(self, r) -> None:
        _set_target(None)
        super().done(r)

    # ------------------------------------------------------------------ list
    def _item_text(self, u: str) -> tuple:
        nf, _st = _flair_fns()
        fl = {}
        if nf is not None:
            try:
                fl = nf(u) or {}
            except Exception:                                      # noqa: BLE001
                fl = {}
        text = f"{fl.get('prefix') or ''}{u}{fl.get('suffix') or ''}"
        if users.is_admin(u):
            text += f"   · {users.role_label(u)}"
        return text, fl

    def _fill(self, select: Optional[str]) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        owner = users.legacy_owner()
        for u in users.list_users():
            text, fl = self._item_text(u)
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, u)
            if fl.get("bold"):
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            if fl.get("colour"):
                c = QColor(str(fl["colour"]))
                if c.isValid():
                    it.setForeground(QBrush(c))
            tips = [f"{u} - {users.role_label(u)}"]
            if u == owner:
                tips.append("Also has the analyses and settings that were on this computer "
                            "before user profiles.")
            if users.has_password(u):
                tips.append("Has a password.")
            al = users.aliases_of(u)
            if al:
                tips.append("Also known as: " + ", ".join(al))
            it.setToolTip("\n".join(tips))
            self.list.addItem(it)
            if u == select:
                self.list.setCurrentItem(it)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        first = not self.list.count()
        lab = _labshare()
        self.row_first.setVisible(first and lab is not None and not lab.linked_folder())
        if first:
            self.lbl_note.setText("No users yet: type your name and press Add user"
                                  + (", or link your lab's shared folder." if
                                     self.row_first.isVisible() else ".")
                                  + " (PeterPiper starts empty: nothing is taken over "
                                  "from PD4nav; Import a profile... brings one in.)")
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
            n = users.clean_name(txt)
            back = any(u.lower() == n.lower() for u in users.all_users())
            into = users.merged_into(n) if back else None
            self.lbl_note.setText(why or (
                f"Press Add user to bring '{n}' back as a separate user (merged into "
                f"'{into}' earlier; nothing was deleted)." if into else
                f"Press Add user to bring '{n}' back (removed earlier; nothing was deleted)."
                if back else f"Press Add user to make '{n}'."))
        elif self.list.count():
            self.lbl_note.setText("Double-click your name, or pick it and press Continue "
                                  "(Enter).")
        u = self._picked()
        has = u is not None
        _set_target(u)
        self.btn_go.setEnabled(has)
        self.act_rename.setEnabled(has)
        self.act_remove.setEnabled(has)
        self.act_export.setEnabled(has)
        self.act_password.setEnabled(has)
        self.btn_sync.setEnabled(has)
        ps = _profilesync()
        self.lbl_sync.setText((ps.status(u) if ps and u else "Off") or "Off")
        lab = _labshare()
        self.lbl_lab.setText(lab.status() if lab else "not available")
        self.btn_lab.setEnabled(lab is not None and (users.is_admin(u) or not users.list_users()))
        self.btn_lab.setToolTip(
            "The lab's shared folder, lab user list and data folders." if self.btn_lab.isEnabled()
            else "Only an admin or developer can change the lab settings: pick an admin's name "
                 "first.")

    # --------------------------------------------------------------- actions
    def _add(self) -> None:
        txt = self.ed_new.text().strip()
        if not txt or users.name_problem(txt):
            return
        lab = _labshare()
        if lab is not None and lab.linked_folder() and users.list_users() \
                and not lab.anyone_can_add():
            who = self._ask_admin("Only a lab admin can add users here.")
            if who is None:
                return
        try:
            n = users.add_user(txt)
        except (OSError, ValueError) as exc:
            self.lbl_note.setText(f"Could not add the user: {exc}")
            return
        self.ed_new.clear()
        self._fill(n)

    def _ask_admin(self, why: str = "") -> Optional[str]:
        """An admin of this computer, with their password if set; None if not."""
        adm = users.admins()
        if not adm:
            return None
        u = self._picked()
        if u not in adm:
            if len(adm) == 1:
                u = adm[0]
            else:
                u, ok = QInputDialog.getItem(self, "Lab settings", (why + "\n" if why else "")
                                             + "Which admin are you?", adm, 0, False)
                if not ok:
                    return None
        if not unlock(self, u, f"{why}\nPassword of the admin '{u}':".strip()):
            self.lbl_note.setText("Not the right password.")
            return None
        return u

    def _rename(self) -> None:
        old = self._picked()
        if old is None or not unlock(self, old):
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
        if u is None or not unlock(self, u):
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

    def _export(self) -> None:
        u = self._picked()
        if u and unlock(self, u):
            export_profile_dialog(self, u)

    def _password(self) -> None:
        u = self._picked()
        if u is None:
            return
        if users.has_password(u) and not unlock(self, u, f"Present password of '{u}':"):
            return
        d = PasswordDialog(self, u)
        if d.exec() == QDialog.Accepted:
            self._fill(u)
            self.lbl_note.setText(d.result_note)

    def _sync(self) -> None:
        u = self._picked()
        if u is None or not unlock(self, u):
            return
        SyncDialog(self, u).exec()
        self._update()

    def _merge(self) -> None:
        u = self._picked()
        if u is not None and not unlock(self, u):
            return
        d = MergeDialog(self, u)
        d.exec()
        self._fill(d.kept or users.last_user() or u)
        if d.result_note:
            self.lbl_note.setText(d.result_note)

    def _lab_settings(self) -> None:
        if users.list_users():
            who = self._ask_admin()
            if who is None:
                return
        else:
            who = None                                 # first start: whoever sets it up
        LabSettingsDialog(self, who).exec()
        self._fill(self._picked() or users.last_user())

    def _link_first(self) -> None:
        if link_lab_dialog(self):
            self._fill(users.last_user())

    def _go(self) -> None:
        u = self._picked()
        if u is None:
            return
        if not unlock(self, u):
            self.lbl_note.setText(f"Not the right password for '{u}'.")
            return
        self.chosen = u
        users.set_dont_ask(self.chk_dont.isChecked())
        self.accept()


# ============================================================ password dialog
class PasswordDialog(QDialog):
    """Set, change or remove a user's password (optional, off by default)."""

    def __init__(self, parent, user: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Password - {user}")
        self.user = user
        self.result_note = ""
        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(
            ("'" + user + "' has a password. " if users.has_password(user) else
             "'" + user + "' has no password (the usual way). ") + PASSWORD_NOTE, muted=True))
        self.ed1, self.ed2 = QLineEdit(), QLineEdit()
        for e, ph in ((self.ed1, "New password"), (self.ed2, "The same again")):
            e.setEchoMode(QLineEdit.Password)
            e.setPlaceholderText(ph)
            lay.addWidget(e)
        self.lbl = W.wrapped_label("", muted=True)
        lay.addWidget(self.lbl)
        bb = QDialogButtonBox()
        self.btn_set = bb.addButton("Set password", QDialogButtonBox.AcceptRole)
        self.btn_clear = bb.addButton("No password", QDialogButtonBox.DestructiveRole)
        bb.addButton(QDialogButtonBox.Cancel)
        self.btn_set.clicked.connect(self._set)
        self.btn_clear.clicked.connect(self._clear)
        bb.rejected.connect(self.reject)
        self.btn_clear.setEnabled(users.has_password(user))
        lay.addWidget(bb)

    def _set(self) -> None:
        a, b = self.ed1.text(), self.ed2.text()
        if not a:
            self.lbl.setText("Type a password (or press No password).")
            return
        if a != b:
            self.lbl.setText("The two do not match.")
            return
        users.set_password(self.user, a)
        self.result_note = f"'{self.user}' now has a password."
        self.accept()

    def _clear(self) -> None:
        users.clear_password(self.user)
        self.result_note = f"'{self.user}' has no password any more."
        self.accept()


# ============================================================== merge dialog
class MergeDialog(QDialog):
    """Merge profiles: two spellings of one person on this computer, or a profile
    from another computer into a chosen user. Shows what comes over, asks, merges."""

    def __init__(self, parent, selected: Optional[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Merge profiles")
        self.selected = selected
        self.kept: Optional[str] = None
        self.result_note = ""
        self.src: Optional[str] = None
        self.resize(600, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(
            "The same person under two names (e.g. 'Ana Lopez' here and 'A. Lopez' from the "
            "Mac) becomes one user. Everything is added to the kept user - runs, groups, "
            "colours, templates, saved settings, auto-detects, extras. Nothing is overwritten "
            "and nothing is deleted: the merged name is only hidden from the list and counts as "
            "another spelling of the kept user.", muted=True))
        self.rb_local = QRadioButton("Two users of this computer")
        self.rb_file = QRadioButton("A profile from another computer (exported .zip, or a "
                                    "copied profile folder)")
        grp = QButtonGroup(self)
        grp.addButton(self.rb_local)
        grp.addButton(self.rb_file)
        self.rb_local.setChecked(True)
        lay.addWidget(self.rb_local)
        lay.addWidget(self.rb_file)
        form = QGridLayout()
        form.addWidget(QLabel("Keep:"), 0, 0)
        self.cmb_keep = QComboBox()
        form.addWidget(self.cmb_keep, 0, 1, 1, 2)
        self.lbl_from = QLabel("Merge into it:")
        form.addWidget(self.lbl_from, 1, 0)
        self.cmb_other = QComboBox()
        form.addWidget(self.cmb_other, 1, 1, 1, 2)
        self.lbl_src = QLabel("")
        self.lbl_src.setProperty("muted", True)
        self.btn_zip = W.button("Choose .zip...", self._choose_zip, "An exported profile.")
        self.btn_dir = W.button("Choose folder...", self._choose_dir, "A copied profile folder.")
        self.row_src = W.row(self.lbl_src, self.btn_zip, self.btn_dir)
        self.row_src.layout().setStretch(0, 1)
        form.addWidget(self.row_src, 2, 0, 1, 3)
        form.setColumnStretch(1, 1)
        lay.addLayout(form)
        box = QGroupBox("What comes over")
        bl = QVBoxLayout(box)
        self.lbl_sum = W.wrapped_label("")
        self.lbl_sum.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        bl.addWidget(self.lbl_sum)
        bl.addStretch(1)
        lay.addWidget(box, 1)
        bb = QDialogButtonBox()
        self.btn_merge = bb.addButton("Merge...", QDialogButtonBox.AcceptRole)
        bb.addButton(QDialogButtonBox.Close)
        self.btn_merge.clicked.connect(self._do)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        vis = users.list_users()
        admin = users.is_admin(selected)
        keeps = vis if (admin or not selected) else [selected]
        for u in keeps:
            self.cmb_keep.addItem(u)
        if selected in keeps:
            self.cmb_keep.setCurrentText(selected)
        if not admin and selected:
            self.cmb_keep.setToolTip("You can merge into your own profile (an admin can merge "
                                     "any two).")
        self.cmb_keep.currentIndexChanged.connect(lambda _i: self._refill_other())
        self.cmb_other.currentIndexChanged.connect(lambda _i: self._summary())
        self.rb_local.toggled.connect(lambda _on: self._mode())
        self._refill_other()
        self._mode()

    def _refill_other(self) -> None:
        keep = self.cmb_keep.currentText()
        self.cmb_other.blockSignals(True)
        self.cmb_other.clear()
        for u in users.list_users():
            if u != keep:
                self.cmb_other.addItem(u)
        self.cmb_other.blockSignals(False)
        self._summary()

    def _mode(self) -> None:
        local = self.rb_local.isChecked()
        self.lbl_from.setVisible(local)
        self.cmb_other.setVisible(local)
        self.row_src.setVisible(not local)
        self.lbl_src.setText(self.src or "No profile chosen yet.")
        self._summary()

    def _choose_zip(self) -> None:
        p, _f = QFileDialog.getOpenFileName(self, "Profile from another computer", _suggest_start(),
                                            "PeterPiper profile (*.zip)")
        if p:
            self.set_source(p)

    def _choose_dir(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Copied profile folder", _suggest_start())
        if p:
            self.set_source(p)

    def set_source(self, path: str) -> None:
        self.src = str(path)
        self.rb_file.setChecked(True)
        self._mode()

    def _lines(self) -> List[str]:
        keep = self.cmb_keep.currentText()
        if not keep:
            return ["There is no user to keep yet."]
        if self.rb_local.isChecked():
            other = self.cmb_other.currentText()
            if not other:
                return ["Only one user on this computer: nothing to merge."]
            return [f"'{other}' into '{keep}':"] + users.merge_preview(keep, other)
        if not self.src:
            return ["Choose the profile (.zip or folder) from the other computer."]
        try:
            name, lines = users.import_preview(self.src, into=keep)
        except (OSError, ValueError) as exc:
            return [f"Not a profile: {exc}"]
        return [f"'{name}' (from the other computer) into '{keep}':"] + lines

    def _summary(self) -> None:
        lines = self._lines()
        self.lbl_sum.setText("\n".join(("- " + ln) if i else ln for i, ln in enumerate(lines)))
        ok = bool(self.cmb_keep.currentText()) and (
            bool(self.cmb_other.currentText()) if self.rb_local.isChecked() else bool(self.src))
        self.btn_merge.setEnabled(ok)

    def _do(self) -> None:
        keep = self.cmb_keep.currentText()
        lines = self._lines()
        local = self.rb_local.isChecked()
        other = self.cmb_other.currentText() if local else ""
        if local and other and not users.is_admin(self.selected) and \
                not unlock(self, other, f"Password of '{other}' (the profile merged away):"):
            return
        if QMessageBox.question(
                self, "Merge profiles", "\n".join(lines) + "\n\nNothing is deleted"
                + (f": '{other}' is hidden from the list and becomes another name of '{keep}'."
                   if local else ".") + "\n\nMerge now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            if local:
                notes = W.run_with_progress(self, "Merging the profiles",
                                            lambda _p: _p(None, "Copying settings and runs",
                                                          detail=f"'{other}' into '{keep}'")
                                            and users.merge_users(keep, other))
            else:
                src = self.src
                _n, notes = W.run_with_progress(self, "Merging the profile",
                                                lambda _p: _p(None, "Copying settings and runs",
                                                              detail=f"{src} into '{keep}'")
                                                and users.import_profile(src, into=keep))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Merge profiles", f"Not merged: {exc}")
            return
        self.kept = keep
        self.result_note = f"Merged into '{keep}'."
        QMessageBox.information(self, "Merge profiles", "Done: " + "; ".join(notes) + ".")
        self.accept()


# ======================================================= personal sync dialog
class SyncDialog(QDialog):
    """Keep one person's profile in step through a folder (profilesync)."""

    def __init__(self, parent, user: str) -> None:
        super().__init__(parent)
        self.user = user
        self.setWindowTitle(f"Keep in step - {user}")
        self.resize(600, 460)
        ps = _profilesync()
        self.ps = ps
        st = ps.load_state(user) if ps else {}
        self.folder: Optional[str] = st.get("folder") or None
        self.target: Optional[str] = st.get("target") or None
        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(
            f"Keep {user}'s profile the same on every computer they use (a Mac and a "
            f"Windows PC, home and lab ...), through a folder of their own cloud drive "
            f"(OneDrive, Google Drive, Box, Dropbox, iCloud Drive) or a network folder. Free: "
            f"PeterPiper only reads and writes the folder - the cloud app copies it. When "
            f"{user} is chosen the folder's changes come in; when PeterPiper closes this "
            f"computer's go out. Nothing is deleted; runs and lists are united.", muted=True))
        lab_t = None                                   # 1.2.1: the lab folder covers it
        try:
            lab = _labshare()
            lab_t = lab.profile_target(user) if lab else None
        except Exception:                                           # noqa: BLE001
            lab_t = None
        self.lbl_lab = W.wrapped_label(
            f"{user}'s profile is already kept in step through the lab folder "
            f"({lab_t[0]}). You need this only for a folder of your own; the lab "
            f"folder cannot be chosen here." if lab_t else "")
        self.lbl_lab.setVisible(bool(lab_t))
        lay.addWidget(self.lbl_lab)
        self.rb_off = QRadioButton("Off")
        self.rb_on = QRadioButton("Through this folder:")
        grp = QButtonGroup(self)
        grp.addButton(self.rb_off)
        grp.addButton(self.rb_on)
        (self.rb_on if self.folder else self.rb_off).setChecked(True)
        lay.addWidget(self.rb_off)
        self.lbl_folder = ElideLabel(self.folder or "(none chosen)")
        btn_choose = W.button("Choose...", self._choose, "Any folder you can reach from each "
                              "of your computers.")
        r = W.row(self.rb_on, self.lbl_folder, btn_choose)
        r.layout().setStretch(1, 1)
        lay.addWidget(r)
        sugg = ps.suggest_folders() if ps else []
        if sugg:
            rs = QWidget()
            hl = QHBoxLayout(rs)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(QLabel("Found here:"))
            for name, path in sugg[:4]:
                b = QPushButton(name)
                b.setAutoDefault(False)
                b.setToolTip(f"Use {path}{os.sep}PeterPiper")
                b.clicked.connect(lambda _c=False, p=path: self.set_folder(
                    str(Path(p) / "PeterPiper")))
                hl.addWidget(b)
            hl.addStretch(1)
            lay.addWidget(rs)
        self.lbl_which = QLabel("Use the profile:")
        self.cmb_which = QComboBox()
        self.cmb_which.setToolTip("If this folder already holds your profile from another "
                                  "computer (perhaps under another spelling of your name), "
                                  "pick it: both are then kept in step as one.")
        r2 = W.row(self.lbl_which, self.cmb_which)
        r2.layout().setStretch(1, 1)
        lay.addWidget(r2)
        self.lbl_status = W.wrapped_label(
            ("Last kept in step: " + ps.status(user)) if ps and self.folder else "", muted=True)
        lay.addWidget(self.lbl_status)
        lay.addStretch(1)
        bb = QDialogButtonBox()
        self.btn_now = bb.addButton("Save and keep in step now", QDialogButtonBox.AcceptRole)
        bb.addButton(QDialogButtonBox.Close)
        self.btn_now.clicked.connect(self._apply)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._fill_which()

    def _choose(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Folder to keep your profile in step",
                                             self.folder or _suggest_start())
        if p:
            self.set_folder(p)

    def set_folder(self, path: str) -> None:
        if self.ps is not None and self.ps.lab_conflict(path):      # 1.2.1
            QMessageBox.information(self, "Keep in step", self.ps.LAB_CONFLICT)
            return
        self.folder = str(path)
        self.target = None
        self.rb_on.setChecked(True)
        self.lbl_folder.setText(self.folder)
        self._fill_which()

    def _fill_which(self) -> None:
        self.cmb_which.clear()
        ps = self.ps
        if not (ps and self.folder):
            self.lbl_which.setVisible(False)
            self.cmb_which.setVisible(False)
            return
        found = ps.profile_dirs_in(self.folder) if os.path.isdir(self.folder) else []
        new = ps.target_in(self.folder, self.user)
        for p in found:
            self.cmb_which.addItem(f"{ps.profile_label(p)}  ({Path(p).name})", str(p))
        if str(new) not in [str(p) for p in found]:
            self.cmb_which.addItem(f"New: {Path(new).name}", str(new))
        if self.target:
            i = self.cmb_which.findData(self.target)
            if i >= 0:
                self.cmb_which.setCurrentIndex(i)
        show = self.cmb_which.count() > 1
        self.lbl_which.setVisible(show)
        self.cmb_which.setVisible(show)

    def _apply(self) -> None:
        ps = self.ps
        if ps is None:
            return
        if self.rb_off.isChecked() or not self.folder:
            ps.turn_off(self.user)
            self.lbl_status.setText("Off: this computer's profile is no longer copied to the "
                                    "folder (nothing deleted).")
            return
        target = self.cmb_which.currentData() or None
        u, folder = self.user, self.folder
        try:
            note = W.run_with_progress(self, "Keeping the profile in step",
                                       lambda _p: _p(None, "Copying the profile",
                                                     detail=str(folder))
                                       and ps.set_folder(u, folder, target))
        except ValueError as exc:                                  # 1.2.1: a lab folder
            QMessageBox.information(self, "Keep in step", str(exc))
            return
        except OSError as exc:
            note = f"Not kept in step: {exc}"
        self.lbl_status.setText((note or "Done.") + "  -  " + ps.status(self.user))


# ======================================================= lab: link / create
def link_lab_dialog(parent) -> bool:
    """Choose the lab's shared folder and link this computer to it."""
    lab = _labshare()
    if lab is None:
        return False
    p = QFileDialog.getExistingDirectory(parent, "Your lab's shared PeterPiper folder",
                                         lab.linked_folder() or _suggest_start())
    if not p:
        return False
    if not lab.is_lab_folder(p):
        QMessageBox.warning(parent, "Lab folder",
                            f"There is no PeterPiper lab list in {p}.\n\nChoose the folder that "
                            f"holds '{lab.LAB_FILE}', or ask an admin to make one "
                            f"(Lab settings... > Create a lab folder here).")
        return False
    include = []
    mine = users.list_users()
    if mine:
        include = pick_users(parent, "Lab folder", "Add these users of this computer to the lab "
                             "list (people already on it are recognised by their name or "
                             "spelling):", mine)
        if include is None:
            return False
    try:
        notes = lab.link(p, include)
    except (OSError, ValueError) as exc:
        QMessageBox.warning(parent, "Lab folder", f"Not linked: {exc}")
        return False
    QMessageBox.information(parent, "Lab folder", "Linked to the lab folder."
                            + (" " + "; ".join(notes) + "." if notes else ""))
    return True


def create_lab_dialog(parent, admin: Optional[str]) -> bool:
    lab = _labshare()
    if lab is None:
        return False
    p = QFileDialog.getExistingDirectory(parent, "Where to make the lab's shared folder "
                                         "(a lab server or a shared cloud folder)",
                                         _suggest_start())
    if not p:
        return False
    folder = Path(p)
    try:
        if not lab.is_lab_folder(folder) and any(folder.iterdir()):
            folder = folder / "PeterPiper lab"
    except OSError:
        pass
    names = users.list_users()
    include = pick_users(parent, "Create a lab folder", f"The lab folder will be {folder}.\n"
                         "Which users of this computer should be on the lab list?", names) \
        if names else []
    if include is None:
        return False
    try:
        notes = W.run_with_progress(parent, "Making the lab folder",
                                    lambda _p: _p(None, "Writing the lab folder",
                                                  detail=str(folder))
                                    and lab.create_lab(folder, include, admin))
    except (OSError, ValueError) as exc:
        QMessageBox.warning(parent, "Create a lab folder", f"Not made: {exc}")
        return False
    QMessageBox.information(parent, "Create a lab folder",
                            f"Made: {folder} ({'; '.join(notes)}). On each lab computer: "
                            f"Lab settings... > Link to a lab folder..., or on the first start "
                            f"'Link to your lab's shared PeterPiper folder...'.")
    return True


# ===================================================== lab settings (admins)
class LabSettingsDialog(QDialog):
    """Admins / developers: the lab folder, the lab user list (add, rename, role,
    hide, same person / spellings, password reset) and the lab's data folders."""

    def __init__(self, parent, admin: Optional[str]) -> None:
        super().__init__(parent)
        self.admin = admin
        self.lab = _labshare()
        self.setWindowTitle("Lab settings" + (f" - {admin}" if admin else ""))
        self.resize(680, 620)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        # ---- folder
        bf = QGroupBox("Lab folder (shared user list)")
        fl = QVBoxLayout(bf)
        self.lbl_folder = W.wrapped_label("", muted=True)
        fl.addWidget(self.lbl_folder)
        self.lbl_path = ElideLabel("")
        fl.addWidget(self.lbl_path)
        self.btn_link = W.button("Link to a lab folder...", self._link,
                                 "The lab's shared PeterPiper folder (on a lab server or a "
                                 "cloud drive) - made on another computer.")
        self.btn_create = W.button("Create a lab folder here...", self._create,
                                   "Make the lab's shared folder from this computer's users.")
        self.btn_unlink = W.button("Unlink", self._unlink, "This computer stops using the lab "
                                   "folder (nothing is deleted).")
        fl.addWidget(W.row(self.btn_link, self.btn_create, self.btn_unlink))
        lay.addWidget(bf)
        # ---- people
        bp = QGroupBox("Users")
        pl = QVBoxLayout(bp)
        self.lst_people = QListWidget()
        self.lst_people.currentItemChanged.connect(lambda *_: self._upd_buttons())
        pl.addWidget(self.lst_people, 1)
        self.btn_padd = W.button("Add...", self._p_add, "Add a person to the list.")
        self.btn_pren = W.button("Rename...", self._p_rename, "Another name; the old one stays "
                                 "a spelling of theirs.")
        self.btn_role = QToolButton()
        self.btn_role.setText("Role")
        self.btn_role.setPopupMode(QToolButton.InstantPopup)
        rm = QMenu(self.btn_role)
        for r in users.ROLES:
            rm.addAction(users.ROLE_LABELS[r], lambda r=r: self._p_role(r))
        self.btn_role.setMenu(rm)
        self.btn_role.setToolTip("User, Admin or Developer (a title: the same abilities as "
                                 "Admin). There is always at least one admin.")
        self.btn_phide = W.button("Hide / show", self._p_hide, "Hidden people are not offered "
                                  "on the lab's computers (nothing is deleted).")
        self.btn_psame = W.button("Same person as...", self._p_same, "Two entries are one "
                                  "person (different spellings).")
        self.btn_palias = W.button("Spelling...", self._p_alias, "Another spelling of this "
                                   "person's name (e.g. 'A. Lopez').")
        self.btn_ppw = W.button("Clear password", self._p_pw, "Reset: the person has no "
                                "password any more. " + PASSWORD_NOTE)
        r1 = W.row(self.btn_padd, self.btn_pren, self.btn_role, self.btn_phide,
                   self.btn_psame, self.btn_palias, self.btn_ppw)
        r1.layout().addStretch(1)
        pl.addWidget(r1)
        self.chk_anyone = QCheckBox("Anyone can add themselves on a lab computer")
        self.chk_anyone.setToolTip("Off: only an admin can add new users.")
        self.chk_anyone.toggled.connect(self._anyone)
        pl.addWidget(self.chk_anyone)
        lay.addWidget(bp, 1)
        # ---- data folders
        bd = QGroupBox("The lab's data folders (where the .nd2 movies are)")
        dl = QVBoxLayout(bd)
        self.lst_data = QListWidget()
        self.lst_data.setMaximumHeight(90)
        dl.addWidget(self.lst_data)
        dl.addWidget(W.row(W.button("Add...", self._d_add, "A folder with the lab's movies "
                                    "(offered when opening a movie)."),
                           W.button("Label...", self._d_label, "A short name for it."),
                           W.button("Remove", self._d_remove, "Off the list (the folder "
                                    "itself is not touched).")))
        lay.addWidget(bd)
        self.lbl_note = W.wrapped_label("", muted=True)
        lay.addWidget(self.lbl_note)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._refresh()

    # ------------------------------------------------------------- state
    def _linked(self) -> bool:
        return bool(self.lab and self.lab.linked_folder())

    def _refresh(self) -> None:
        lab = self.lab
        linked = self._linked()
        self.lbl_path.setText(("Linked: " + lab.status()) if linked else "")
        self.lbl_path.setVisible(linked)
        self.lbl_folder.setVisible(not linked)
        self.lbl_folder.setText(
            "" if linked else
            "Not linked. Link this computer to the lab's shared folder, or create one here "
            "(on a lab server or a shared cloud folder). Every linked computer then shows the "
            "lab's users, and each person's profile is also kept in the lab folder.")
        self.btn_unlink.setEnabled(linked)
        sel = self._sel()
        self.lst_people.clear()
        if linked:
            for p in lab.people():
                t = p["name"] + f"  -  {users.ROLE_LABELS.get(p['role'], 'User')}"
                if p["aliases"]:
                    t += "   (also: " + ", ".join(p["aliases"]) + ")"
                if p["hidden"]:
                    t += "   [hidden]"
                if (p.get("password") or {}).get("hash"):
                    t += "   [password]"
                it = QListWidgetItem(t)
                it.setData(Qt.UserRole, p["name"])
                self.lst_people.addItem(it)
        else:
            for u in users.all_users():
                if users.merged_into(u):
                    continue
                t = u + f"  -  {users.role_label(u)}"
                if u not in users.list_users():
                    t += "   [hidden]"
                if users.has_password(u):
                    t += "   [password]"
                it = QListWidgetItem(t)
                it.setData(Qt.UserRole, u)
                self.lst_people.addItem(it)
        for i in range(self.lst_people.count()):
            if self.lst_people.item(i).data(Qt.UserRole) == sel:
                self.lst_people.setCurrentRow(i)
        self.chk_anyone.blockSignals(True)
        self.chk_anyone.setChecked(lab.anyone_can_add() if lab else True)
        self.chk_anyone.setEnabled(linked)
        self.chk_anyone.blockSignals(False)
        self.lst_data.clear()
        for label, path in (lab.data_folders() if lab else []):
            it = QListWidgetItem(f"{label}  -  {path}")
            it.setData(Qt.UserRole, path)
            it.setData(Qt.UserRole + 1, label)
            self.lst_data.addItem(it)
        self._upd_buttons()

    def _sel(self) -> Optional[str]:
        it = self.lst_people.currentItem() if hasattr(self, "lst_people") else None
        return str(it.data(Qt.UserRole)) if it is not None else None

    def _upd_buttons(self) -> None:
        has = self._sel() is not None
        linked = self._linked()
        for b in (self.btn_pren, self.btn_role, self.btn_phide, self.btn_ppw):
            b.setEnabled(has)
        self.btn_padd.setEnabled(True)
        self.btn_psame.setEnabled(has and linked)
        self.btn_palias.setEnabled(has and linked)

    def _run(self, fn, ok_note: str = "") -> None:
        try:
            fn()
        except (OSError, ValueError, PermissionError) as exc:
            self.lbl_note.setText(f"Not done: {exc}")
            return
        self.lbl_note.setText(ok_note)
        self._refresh()

    # ----------------------------------------------------------- folder
    def _link(self) -> None:
        if link_lab_dialog(self):
            self._refresh()

    def _create(self) -> None:
        if create_lab_dialog(self, self.admin):
            self._refresh()

    def _unlink(self) -> None:
        if QMessageBox.question(self, "Unlink", "This computer stops using the lab folder. "
                                "Nothing is deleted (here or in the lab folder).",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._run(self.lab.unlink, "Unlinked.")

    # ----------------------------------------------------------- people
    def _p_add(self) -> None:
        n, ok = QInputDialog.getText(self, "Add a user", "Name:")
        if not ok or not n.strip():
            return
        if self._linked():
            self._run(lambda: self.lab.lab_add_person(n), f"Added '{users.clean_name(n)}'.")
        else:
            self._run(lambda: users.add_user(n), f"Added '{users.clean_name(n)}'.")

    def _p_rename(self) -> None:
        s = self._sel()
        if not s:
            return
        n, ok = QInputDialog.getText(self, "Rename", f"New name for '{s}':", QLineEdit.Normal, s)
        if not ok or not n.strip():
            return
        if self._linked():
            self._run(lambda: self.lab.lab_rename(s, n), "Renamed.")
        else:
            self._run(lambda: users.rename_user(s, n), "Renamed.")

    def _p_role(self, r: str) -> None:
        s = self._sel()
        if not s:
            return
        if self._linked():
            self._run(lambda: self.lab.lab_set_role(s, r), f"'{s}' is now {users.ROLE_LABELS[r]}.")
        else:
            self._run(lambda: users.set_role(s, r), f"'{s}' is now {users.ROLE_LABELS[r]}.")

    def _p_hide(self) -> None:
        s = self._sel()
        if not s:
            return
        if self._linked():
            hidden = next((p["hidden"] for p in self.lab.people() if p["name"] == s), False)
            self._run(lambda: self.lab.lab_set_hidden(s, not hidden),
                      f"'{s}' is {'shown again' if hidden else 'hidden (nothing deleted)'}.")
        elif s in users.list_users():
            if users.is_admin(s) and len(users.admins()) == 1 and len(users.list_users()) > 1:
                self.lbl_note.setText("Make someone else admin first.")
                return
            self._run(lambda: users.remove_user(s), f"'{s}' hidden (nothing deleted).")
        else:
            self._run(lambda: users.add_user(s), f"'{s}' shown again.")

    def _p_same(self) -> None:
        s = self._sel()
        if not s:
            return
        others = [p["name"] for p in self.lab.people() if p["name"] != s]
        if not others:
            return
        o, ok = QInputDialog.getItem(self, "Same person", f"'{s}' is the same person as "
                                     f"(its names become spellings of '{s}'):", others, 0, False)
        if ok and o:
            self._run(lambda: self.lab.lab_same_person(s, o), f"'{o}' is now a spelling of '{s}'.")

    def _p_alias(self) -> None:
        s = self._sel()
        if not s:
            return
        a, ok = QInputDialog.getText(self, "Another spelling", f"Another spelling of '{s}':")
        if ok and a.strip():
            self._run(lambda: self.lab.lab_add_alias(s, a), "Added.")

    def _p_pw(self) -> None:
        s = self._sel()
        if not s:
            return
        if self._linked():
            self._run(lambda: self.lab.lab_clear_password(s), f"'{s}' has no password now.")
        else:
            self._run(lambda: users.clear_password(s), f"'{s}' has no password now.")

    def _anyone(self, on: bool) -> None:
        if self._linked():
            self._run(lambda: self.lab.set_anyone_can_add(on), "Saved.")

    # ------------------------------------------------------- data folders
    def _d_add(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "A folder with the lab's movies",
                                             _suggest_start())
        if not p:
            return
        label, ok = QInputDialog.getText(self, "Label", "A short name (optional):",
                                         QLineEdit.Normal, Path(p).name)
        if ok:
            self._run(lambda: self.lab.add_data_folder(p, label), "Added.")

    def _d_label(self) -> None:
        it = self.lst_data.currentItem()
        if it is None:
            return
        p, old = it.data(Qt.UserRole), it.data(Qt.UserRole + 1)
        label, ok = QInputDialog.getText(self, "Label", "A short name:", QLineEdit.Normal, old)
        if ok:
            self._run(lambda: self.lab.add_data_folder(p, label), "Saved.")

    def _d_remove(self) -> None:
        it = self.lst_data.currentItem()
        if it is not None:
            p = it.data(Qt.UserRole)
            self._run(lambda: self.lab.remove_data_folder(p), "Taken off the list.")


# ============================================================ import / export
def import_profile_dialog(parent) -> Optional[str]:
    """V3.0: pick an exported profile (.zip) and import it; says what happened."""
    path, _f = QFileDialog.getOpenFileName(parent, "Import a profile", "",
                                           "PeterPiper profile (*.zip)")
    if not path:
        return None
    try:
        name, notes = W.run_with_progress(parent, "Importing the profile",
                                          lambda _p: _p(None, "Unpacking the profile",
                                                        detail=str(path))
                                          and users.import_profile(path))
    except (OSError, ValueError) as exc:
        QMessageBox.warning(parent, "Import a profile", f"Not imported: {exc}")
        return None
    QMessageBox.information(parent, "Import a profile",
                            f"Imported as '{name}': " + "; ".join(notes) + ". Runs whose "
                            f"files are somewhere else on this computer: Compare / average runs "
                            f"> My data is in... (To merge it into a user with another name: "
                            f"Merge profiles... in the first window.)")
    return name


def export_profile_dialog(parent, user: Optional[str] = None) -> None:
    """V3.0: the current user's whole profile in one zip, for another computer."""
    from datetime import date
    u = user or users.current()
    if not u:
        return
    default = f"PeterPiper profile - {users.folder_name(u)} - {date.today().isoformat()}.zip"
    path, _f = QFileDialog.getSaveFileName(parent, "Export my profile", default,
                                           "PeterPiper profile (*.zip)")
    if not path:
        return
    try:
        out = W.run_with_progress(parent, "Exporting your profile",
                                  lambda _p: _p(None, "Packing the profile into one zip",
                                                detail=str(path))
                                  and users.export_profile(u, path))
    except OSError as exc:
        QMessageBox.warning(parent, "Export my profile", f"Not exported: {exc}")
        return
    QMessageBox.information(parent, "Export my profile",
                            f"Your profile (settings, run list, groups, colours, labels, Prism "
                            f"templates, saved settings, saved-files log) is in: {out}. On the "
                            f"other computer: Import a profile... or Merge profiles... in the "
                            f"first window. Your analyses themselves stay next to your movies "
                            f"(OUTPUT_<movie>/{users.folder_name(u)}) - copy those folders with "
                            f"the movies.")
