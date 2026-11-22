"""
PeterPiper 4.0: 'Lab folder & backup' - on the start window only.

    ServerPanel(parent)         the panel (a tab of the start window):
        * one coloured line: is the lab folder usable? (labshare.health, worked out
          in a background thread) with the fix in plain words, and Check;
        * the lab folder; Connect... / Set up a lab folder... / How this works;
        * when the user's results go to a folder of their own: said, with
          'Use People/<you>' (default: keep as is);
        * the options (userprefs.server_options): upload movies / exports / saves,
          back up on close / daily, fetch the next movie, the movie cache and its
          limit - each with a hover explanation;
        * last backup + Back up now.
    ConnectDialog(parent)       pick the lab folder: the ones found on this computer
                                (searched in the background) or any folder in it
    set_up_lab(parent)          'Set up a lab folder...' (whoever chooses to - the
                                lab's admin, usually)

Nothing here moves or deletes a user's file; every change is offered, not forced.
Tests replace ConnectDialog._ask / ServerPanel._ask / _pick_folder.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QGridLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import labshare as L
from .. import tasks as T
from .. import transfers as X
from .. import userprefs as UP
from . import widgets as W
from .tips import help_button, tip

DOT = "●"
LEVEL_ROLE = {"green": "ok", "amber": "warn", "red": "danger", "grey": ""}


def _style(label: QLabel, role: str = "", muted: bool = False) -> None:
    label.setProperty("role", role)
    label.setProperty("muted", muted)
    label.style().unpolish(label)
    label.style().polish(label)


class _Elide(QLabel):
    """One line, shortened in the middle (the full text as tooltip)."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.set(text)

    def set(self, text: str) -> None:
        self._full = str(text)
        self.setToolTip(self._full)
        self._fit()

    def full(self) -> str:
        return self._full

    def _fit(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full, Qt.ElideMiddle,
                                                      max(40, self.width() - 4)))

    def resizeEvent(self, ev) -> None:                             # noqa: N802
        super().resizeEvent(ev)
        self._fit()


class _Relay(QObject):
    """Carries results from worker threads into the window thread."""
    health = Signal(object)
    found = Signal(object)
    scan_done = Signal()
    sizes = Signal(object)


def _when(iso: str) -> str:
    from datetime import datetime
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "never"
    if t.date() == datetime.now().date():
        return t.strftime("today %H:%M")
    return t.strftime("%d %b %Y %H:%M")


# =============================================================== Connect...
class ConnectDialog(QDialog):
    """Pick the lab folder: found ones (background search) or any folder in it."""

    def __init__(self, parent: Optional[QWidget] = None, scan: bool = True,
                 roots=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect to the lab folder")
        self.chosen: Optional[str] = None
        self.result_info: Optional[dict] = None
        self._relay = _Relay()
        self._relay.found.connect(self._add_found)
        self._relay.scan_done.connect(self._scan_done)
        self._stop = threading.Event()
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel("Pick the lab's PeterPiper folder")
        t.setProperty("role", "title")
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(help_button(
            "Pick the folder whoever set up PeterPiper in your lab made (ask them) - or "
            "any folder inside it. Not your own subfolder: PeterPiper makes "
            "People/<you> for you.", title="Which folder?", pic="server_pick"))
        lay.addLayout(head)
        lay.addWidget(W.wrapped_label(
            "Ask whoever set it up - not your own subfolder: PeterPiper makes "
            "People/<you> for you.", muted=True))
        self.lbl_search = QLabel("Looking in your Box, OneDrive, Google Drive and Dropbox "
                                 "folders...")
        _style(self.lbl_search, muted=True)
        lay.addWidget(self.lbl_search)
        self.lst = QListWidget()
        self.lst.setMinimumHeight(110)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lst.setTextElideMode(Qt.ElideMiddle)
        self.lst.itemDoubleClicked.connect(lambda *_: self._connect_selected())
        self.lst.currentItemChanged.connect(lambda *_: self._buttons())
        tip(self.lst, "Lab folders found in the top folders of your sync apps. Double-click "
                      "one to connect.", title="Found on this computer")
        lay.addWidget(self.lst, 1)
        bl = QHBoxLayout()
        self.btn_browse = W.button("Choose a folder...", self._browse,
                                   "Pick the lab folder yourself (or any folder inside it).")
        bl.addWidget(self.btn_browse)
        bl.addStretch(1)
        self.btn_cancel = W.button("Cancel", self.reject, "Close without connecting.")
        self.btn_ok = W.button("Connect", self._connect_selected,
                               "Connect this computer to the selected lab folder.", strong=True)
        for b in (self.btn_browse, self.btn_cancel, self.btn_ok):
            b.setAutoDefault(False)
        bl.addWidget(self.btn_cancel)
        bl.addWidget(self.btn_ok)
        lay.addLayout(bl)
        self.resize(560, 360)
        self._buttons()
        if scan:
            self._thread = threading.Thread(target=self._scan, args=(roots,), daemon=True)
            self._thread.start()
        else:
            self._scan_done()

    # ---------------------------------------------------------- searching
    def _scan(self, roots) -> None:
        try:
            L.scan_for_labs(roots, cancelled=self._stop.is_set,
                            found=lambda e: self._emit(self._relay.found, e))
        except Exception:                                          # noqa: BLE001
            pass
        self._emit(self._relay.scan_done)

    @staticmethod
    def _emit(sig, *a) -> None:
        try:
            sig.emit(*a)
        except RuntimeError:                       # the window was closed meanwhile
            pass

    def _add_found(self, e: dict) -> None:
        parts = Path(e["root"]).parts
        short = "/".join(parts[-2:]) if len(parts) > 1 else e["root"]
        it = QListWidgetItem(f"{e['name']}   -   {e['service']}: .../{short}"
                             + ("" if e.get("marker") else "   (earlier PeterPiper)"))
        it.setData(Qt.UserRole, e["root"])
        it.setToolTip(f"{e['service']}: {e['root']}")
        self.lst.addItem(it)
        if self.lst.count() == 1:
            self.lst.setCurrentRow(0)
        self._buttons()

    def _scan_done(self) -> None:
        n = self.lst.count()
        self.lbl_search.setText(f"Found {n} lab folder{'s' if n != 1 else ''} on this computer."
                                if n else "No lab folder found in your sync apps' folders - "
                                          "choose it yourself.")

    def _buttons(self) -> None:
        self.btn_ok.setEnabled(self.lst.currentItem() is not None)

    def done(self, r: int) -> None:
        self._stop.set()
        super().done(r)

    # ------------------------------------------------------------ choosing
    def _pick_folder(self) -> str:                    # tests replace this
        return QFileDialog.getExistingDirectory(self, "Choose the lab folder", "")

    def _browse(self) -> None:
        f = self._pick_folder()
        if f:
            self.connect_to(f)

    def _connect_selected(self) -> None:
        it = self.lst.currentItem()
        if it is not None:
            self.connect_to(str(it.data(Qt.UserRole)))

    def _ask(self, kind: str, title: str, text: str, buttons: List[str]) -> str:
        """Ask; returns the button text chosen ('' = closed). Tests replace this."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question if kind == "question" else QMessageBox.Information)
        box.setWindowTitle(title)
        box.setText(text)
        hits = [box.addButton(b, QMessageBox.AcceptRole if i == 0 else QMessageBox.RejectRole
                              if b == "Cancel" else QMessageBox.ActionRole)
                for i, b in enumerate(buttons)]
        box.setDefaultButton(hits[0])
        box.exec()
        hit = box.clickedButton()
        return next((b for b, h in zip(buttons, hits) if h is hit), "")

    def connect_to(self, path: str) -> bool:
        """Connect to the lab folder `path` is in (asking what needs asking)."""
        from .. import users
        found = L.find_lab_root(path)
        if found is None:
            self._ask("info", "Not a lab folder",
                      "There is no PeterPiper lab folder here or in a folder above it.\n\n"
                      "Pick the lab's PeterPiper folder (ask whoever set it up), or set one "
                      "up with 'Set up a lab folder...'.", ["OK"])
            return False
        root, has_marker = found
        adopt = True
        if not has_marker and L.writable(root):
            a = self._ask("question", "A lab folder from an earlier PeterPiper",
                          f"{root}\n\nis a lab folder from an earlier PeterPiper. Make it "
                          "ready for this one? PeterPiper adds a small marker file, a READ ME "
                          "and the folders People and Shared - nothing is moved or deleted.",
                          ["Make it ready", "Connect without changes", "Cancel"])
            if a in ("", "Cancel"):
                return False
            adopt = a == "Make it ready"
        user = users.current()
        make = False
        if user and L.writable(root):
            name = users.folder_name(user)
            have = (L.lab_path("people", root) / name).is_dir()
            if have:
                make = True
            else:
                a = self._ask("question", "Your own folder",
                              f"Make your folder People/{name} in the lab folder? Your "
                              "results, exports and backups go there (in Results, Exports, "
                              "Backups and Movies).", ["Make it", "Not now"])
                make = a == "Make it"
        try:
            info = L.connect(root, user, make_person=make, adopt=adopt)
        except (OSError, ValueError) as exc:
            self._ask("info", "Could not connect", str(exc), ["OK"])
            return False
        self.chosen, self.result_info = root, info
        self.accept()
        return True


# ======================================================= Set up a lab folder
def set_up_lab(parent: Optional[QWidget], folder: Optional[str] = None,
               name: Optional[str] = None, ask=None) -> Optional[dict]:
    """'Set up a lab folder...': choose (or make) the folder - in the lab's shared
    Box / OneDrive / ... folder or a network drive - and a name; the layout is made
    there and this computer connected. A folder that is not empty and not a lab
    folder gets a new 'PeterPiper lab' folder inside it (asked). Returns
    labshare.setup_lab_folder's dict + {"notes"}, or None (cancelled)."""
    from .. import users

    def _ask(title, text, buttons):
        if ask is not None:
            return ask(title, text, buttons)
        box = QMessageBox(parent)
        box.setWindowTitle(title)
        box.setText(text)
        hits = [box.addButton(b, QMessageBox.AcceptRole if i == 0 else QMessageBox.RejectRole)
                for i, b in enumerate(buttons)]
        box.exec()
        return next((b for b, h in zip(buttons, hits) if h is box.clickedButton()), "")

    if folder is None:
        folder = QFileDialog.getExistingDirectory(
            parent, "Where should the lab folder be? (in the lab's shared cloud folder or "
                    "network drive)", "")
        if not folder:
            return None
    f = Path(folder)
    found = L.find_lab_root(f)
    if found is not None and found[1]:
        _ask("Already a lab folder", f"{found[0]}\n\nis a lab folder already - connect to it "
                                     "with Connect...", ["OK"])
        return None
    try:
        busy = f.is_dir() and any(not n.startswith(".") for n in os.listdir(f))
    except OSError:
        busy = False
    if busy and not L.is_lab_folder(f):
        a = _ask("Set up a lab folder", f"{f}\n\nalready holds other files. Make a new folder "
                                        "'PeterPiper lab' inside it for the lab folder? "
                                        "(Nothing there is changed.)",
                 ["Make 'PeterPiper lab' inside", "Use this folder", "Cancel"])
        if a in ("", "Cancel"):
            return None
        if a.startswith("Make"):
            f = f / "PeterPiper lab"
    if name is None:
        name, ok = QInputDialog.getText(parent, "The lab's name",
                                        "A name for the lab (shown to everyone who connects):",
                                        text=f.name)
        if not ok:
            return None
    me = users.current() or ""
    res = L.setup_lab_folder(f, name or f.name, me)
    notes = []
    if not (f / L.LAB_FILE).is_file() and me:
        notes += L.create_lab(f, [me], admin=me)
    else:
        notes += L.link(f, include=[me] if me else None)
    if me:
        L.person_dir(me, f, create=True)
    res["notes"] = notes
    return res


# ================================================================ the panel
class ServerPanel(QWidget):
    """See the top of the module."""

    changed = Signal()                     # connected / options changed

    def __init__(self, parent: Optional[QWidget] = None, check: bool = True) -> None:
        super().__init__(parent)
        self._relay = _Relay()
        self._relay.health.connect(self._show_health)
        self._relay.sizes.connect(self._show_sizes)
        self._health_running = False
        self.health: Optional[L.Health] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # -- the state line
        top = QHBoxLayout()
        top.setSpacing(6)
        self.lbl_dot = QLabel(DOT)
        top.addWidget(self.lbl_dot)
        self.lbl_health = _Elide("Checking the lab folder...")
        top.addWidget(self.lbl_health, 1)
        self.btn_check = W.button("Check", self.check_health,
                                  "Look again: can the lab folder be reached and written, is "
                                  "the sync app running, is there enough disk space?")
        self.btn_check.setAutoDefault(False)
        top.addWidget(self.btn_check)
        top.addWidget(help_button(
            "Green: all fine. Amber: it works, but something needs a look (the sync app is "
            "not running, read-only, the disk is getting full). Red: the lab folder cannot "
            "be reached or the disk is full. The line under it says what to do.",
            title="The lab folder line", pic="server_health"))
        lay.addLayout(top)
        self.lbl_fix = W.wrapped_label("", muted=True)
        self.lbl_fix.setVisible(False)
        lay.addWidget(self.lbl_fix)

        # -- the folder + actions
        fr = QHBoxLayout()
        fr.setSpacing(6)
        lab = QLabel("Lab folder:")
        fr.addWidget(lab)
        self.lbl_folder = _Elide("")
        fr.addWidget(self.lbl_folder, 1)
        lay.addLayout(fr)
        self.btn_connect = W.button("Connect...", self.connect_dialog, "")
        tip(self.btn_connect, "Connect this computer to your lab's PeterPiper folder: pick it "
                              "from the ones found, or choose it (any folder inside it works). "
                              "Ask whoever set it up which one.", title="Connect",
            pic="server_pick")
        self.btn_setup = W.button("Set up a lab folder...", self.setup_dialog, "")
        tip(self.btn_setup, "Make the lab's folder (usually done once, by the lab's admin) "
                            "in a shared Box / OneDrive / Google Drive / Dropbox folder or on "
                            "a network drive: People, Shared and a READ ME. An existing lab "
                            "folder is kept as it is - nothing is moved.",
            title="Set up a lab folder", pic="server_layout")
        self.btn_guide = W.button("How this works", self.open_guide,
                                  "A short guide: the lab folder, which folder to pick, how "
                                  "Box Drive & co. sync, what is copied when, Windows and Mac, "
                                  "and what to do when something is wrong.")
        for b in (self.btn_connect, self.btn_setup, self.btn_guide):
            b.setAutoDefault(False)
        acts = W.row(self.btn_connect, self.btn_setup, self.btn_guide)
        acts.layout().addStretch(1)
        lay.addWidget(acts)

        # -- your own folder (when found)
        self.own_box = QWidget()
        ol = QVBoxLayout(self.own_box)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(4)
        self.lbl_own = W.wrapped_label("")
        _style(self.lbl_own, "warn")
        ol.addWidget(self.lbl_own)
        self.btn_use_lab = W.button("Use People/me", self._use_lab_results, "")
        self.btn_keep = W.button("Keep as is", self._keep_own, "Your results keep going to "
                                 "your own folder (you can switch later).")
        for b in (self.btn_use_lab, self.btn_keep):
            b.setAutoDefault(False)
        r = W.row(self.btn_use_lab, self.btn_keep)
        r.layout().addStretch(1)
        ol.addWidget(r)
        self.own_box.setVisible(False)
        lay.addWidget(self.own_box)

        # -- options
        box = QGroupBox("Copy to the lab folder automatically")
        g = QGridLayout(box)
        g.setContentsMargins(8, 6, 8, 6)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(3)
        self.chk = {}
        opts = [("upload_saves", "Saves and autosaves",
                 "Every SAVE and autosave is copied to People/<you>/Results in the "
                 "background - safe from a broken laptop.", "server_upload"),
                ("upload_exports", "Exports",
                 "Excel, Prism, CSV and pictures are copied to People/<you>/Exports right "
                 "after each export, in the background.", "server_upload"),
                ("upload_movies", "Analysed movies (.nd2)",
                 "Copies each movie you SAVE or export to People/<you>/Movies. Off by "
                 "default: movies are big (often several GB each) and fill the lab's "
                 "storage. Movies already in the lab folder are never copied again.",
                 "server_upload"),
                ("prefetch", "Fetch the next movie in the queue while I work",
                 "While you work on one movie, the next one of your queue is copied from "
                 "the lab folder to this computer - so Next movie opens it at once.",
                 "server_sync"),
                ("backup_on_close", "Back up when PeterPiper closes",
                 "Your profile, settings and run list (no movies, no results) go to "
                 "People/<you>/Backups when PeterPiper closes - a few MB.", "server_upload"),
                ("backup_daily", "Back up once a day",
                 "The same backup once a day while PeterPiper is open. One file per day; "
                 "the last 30 are kept.", "server_upload")]
        for i, (key, text, explain, pic) in enumerate(opts):
            c = QCheckBox(text)
            tip(c, explain, title=text, pic=pic)
            c.toggled.connect(lambda on, k=key: self._set_opt(k, on))
            self.chk[key] = c
            g.addWidget(c, i // 2, i % 2)
        cache = QHBoxLayout()
        cache.setSpacing(6)
        lbl_c = QLabel("Movie cache:")
        tip(lbl_c, "Movies from the lab folder are copied here first, so they open and "
                   "scroll fast. Only copies - the originals stay in the lab folder.",
            title="Movie cache", pic="server_cache")
        cache.addWidget(lbl_c)
        self.lbl_cache = _Elide("")
        cache.addWidget(self.lbl_cache, 1)
        self.btn_cache = W.button("Change...", self._pick_cache, "Choose where the movie "
                                  "cache is (a fast local disk with room).")
        self.btn_cache.setAutoDefault(False)
        cache.addWidget(self.btn_cache)
        cache.addWidget(QLabel("limit"))
        self.sp_limit = QDoubleSpinBox()
        self.sp_limit.setRange(0, 5000)
        self.sp_limit.setDecimals(0)
        self.sp_limit.setSuffix(" GB")
        self.sp_limit.setSpecialValueText("auto")
        tip(self.sp_limit, "The most the cache may hold. auto: 50 GB or 20% of the free "
                           "disk, whichever is smaller. Over it, the movies used longest ago "
                           "are removed - never the open one.", title="Cache limit",
            pic="server_cache")
        self.sp_limit.valueChanged.connect(lambda v: self._set_opt("cache_limit_gb", float(v)))
        cache.addWidget(self.sp_limit)
        g.addLayout(cache, 3, 0, 1, 2)
        lay.addWidget(box)

        # -- backup
        br = QHBoxLayout()
        br.setSpacing(6)
        self.lbl_backup = _Elide("")
        br.addWidget(self.lbl_backup, 1)
        self.btn_backup = W.button("Back up now", self.backup_now,
                                   "Your profile, settings and run list -> "
                                   "People/<you>/Backups, now (in the background).")
        self.btn_open_backups = W.button("Open", self._open_backups,
                                         "Show your backups (Explorer / Finder).")
        for b in (self.btn_backup, self.btn_open_backups):
            b.setAutoDefault(False)
            br.addWidget(b)
        lay.addLayout(br)
        lay.addStretch(1)

        self._bridge = T.qt_bridge()
        self._bridge.finished.connect(self._task_finished)
        X.install_quit_backup()
        self.refresh()
        if check:
            QTimer.singleShot(0, self.check_health)
        self._daily = QTimer(self)                       # daily backups while open
        self._daily.setInterval(30 * 60 * 1000)
        self._daily.timeout.connect(self._maybe_daily_backup)
        self._daily.start()
        QTimer.singleShot(3000, self._maybe_daily_backup)

    # ------------------------------------------------------------- state
    def refresh(self) -> None:
        from .. import users
        folder = L.linked_folder()
        me = users.current()
        name = users.folder_name(me) if me else "me"
        self.lbl_folder.set(f"{L.lab_name(folder)}  -  {folder}" if folder else
                            "not connected")
        _style(self.lbl_folder, muted=not folder)
        self.btn_connect.setText("Connect..." if not folder else "Change...")
        o = UP.server_options()
        for k, c in self.chk.items():
            c.blockSignals(True)
            c.setChecked(bool(o.get(k)))
            c.setEnabled(bool(folder) or k == "prefetch")
            c.blockSignals(False)
        self.sp_limit.blockSignals(True)
        self.sp_limit.setValue(float(o.get("cache_limit_gb") or 0))
        self.sp_limit.blockSignals(False)
        try:
            self.lbl_cache.set(str(X.cache_dir()))
        except OSError:
            self.lbl_cache.set("")
        last = X.last_backup()
        dest = X.backup_folder() if folder else None
        self.lbl_backup.set(f"Last backup: {_when(last) if last else 'none yet'}"
                            + ("" if dest is not None else "  (connect a lab folder first)"))
        self.btn_backup.setEnabled(dest is not None)
        self.btn_open_backups.setEnabled(dest is not None and dest.is_dir())
        own = L.own_folder_setup(me) if me else None
        if own:
            where = "inside the lab folder" if own["inside"] else "of your own"
            self.lbl_own.setText(f"Your results go to {own['current']} - a folder {where}. "
                                 f"The lab folder has People/{name}/Results for that.")
            self.btn_use_lab.setText(f"Use People/{name}")
            tip(self.btn_use_lab, f"From now on results go to {own['suggested']}. Nothing "
                                  "already saved is moved; your folder stays as it is.",
                title="Use the lab's folder for you", pic="server_layout")
        self.own_box.setVisible(bool(own) and not self._own_dismissed())

    def _own_dismissed(self) -> bool:
        return bool(UP.server_options().get("keep_own_results"))

    def _set_opt(self, key: str, value) -> None:
        UP.set_server_option(key, value)
        self.changed.emit()

    # ------------------------------------------------------------ health
    def check_health(self) -> None:
        """Work out the lab folder line in a background thread."""
        if self._health_running:
            return
        self._health_running = True
        self.lbl_health.set("Checking the lab folder...")
        relay = self._relay
        try:
            cache = X.cache_dir()
        except OSError:
            cache = None

        def work():
            try:
                h = L.health(cache_folder=cache)
                try:
                    L.note_seen()
                except Exception:                                  # noqa: BLE001
                    pass
            except Exception as exc:                               # noqa: BLE001
                h = L.Health("red", "The lab folder could not be checked.", str(exc))
            try:
                relay.health.emit(h)
            except RuntimeError:
                pass
            try:
                relay.sizes.emit(_queue_size())
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _show_health(self, h) -> None:
        self._health_running = False
        self.health = h
        self.lbl_health.set(h.text)
        self.lbl_health.setToolTip("\n".join([h.text] + list(h.details)))
        role = LEVEL_ROLE.get(h.level, "")
        _style(self.lbl_dot, role, muted=not role)
        self.lbl_fix.setText(h.fix)
        self.lbl_fix.setVisible(bool(h.fix))
        self.changed.emit()

    def _show_sizes(self, n_bytes) -> None:
        c = self.chk.get("upload_movies")
        if c is None:
            return
        c.setText("Analysed movies (.nd2" + (f", queue {T.human_bytes(n_bytes)})"
                                             if n_bytes else ")"))

    # ----------------------------------------------------------- actions
    def connect_dialog(self) -> None:
        d = ConnectDialog(self)
        if d.exec():
            self._after_connect(d.result_info or {})

    def _after_connect(self, info: dict) -> None:
        self.refresh()
        self.check_health()
        self.changed.emit()

    def setup_dialog(self) -> None:
        try:
            res = set_up_lab(self)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Set up a lab folder", str(exc))
            return
        if res:
            self.refresh()
            self.check_health()
            self.changed.emit()

    def open_guide(self, page: int = 0):
        from .serverguide import show_guide
        self.guide = show_guide(self, page)
        return self.guide

    def _use_lab_results(self) -> None:
        try:
            target = L.use_lab_results()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "PeterPiper", str(exc))
            return
        UP.set_server_option("keep_own_results", False)
        self.refresh()
        self.lbl_fix.setText(f"From now on, results go to {target}.")
        self.lbl_fix.setVisible(True)
        self.changed.emit()

    def _keep_own(self) -> None:
        UP.set_server_option("keep_own_results", True)
        self.own_box.setVisible(False)

    def _pick_cache_folder(self) -> str:                # tests replace this
        return QFileDialog.getExistingDirectory(self, "Choose the movie cache folder",
                                                str(X.cache_dir()))

    def _pick_cache(self) -> None:
        f = self._pick_cache_folder()
        if f:
            from ..safety import folder_problem
            why = folder_problem(f)
            if why:
                QMessageBox.warning(self, "PeterPiper", f"PeterPiper cannot write in\n{f}\n\n{why}.")
                return
            UP.set_server_option("cache_dir", f)
            self.refresh()

    def backup_now(self) -> Optional[T.Task]:
        self.btn_backup.setEnabled(False)
        self.lbl_backup.set("Backing up...")
        return X.backup_task()

    def _maybe_daily_backup(self) -> None:
        try:
            if L.linked_folder() and X.backup_due() and X.backup_folder() is not None:
                if T.center().find("backup:profile") is None:
                    X.backup_task()
        except Exception:                                          # noqa: BLE001
            pass

    def _task_finished(self, t) -> None:
        if t is not None and t.kind == "backup":
            self.refresh()
            if t.state == T.FAILED:
                self.lbl_backup.set(f"Backup failed: {t.error}")

    def _open_backups(self) -> None:
        d = X.backup_folder()
        if d is not None:
            W.open_path(str(d))

    def level(self) -> str:
        return self.health.level if self.health is not None else ""


def _queue_size() -> int:
    """The movies still to do in the queue, in bytes (a thread: stat per file)."""
    total = 0
    try:
        from .. import batchqueue
        for it in batchqueue.items():
            if it["status"] == "todo":
                try:
                    total += os.stat(it["nd2"]).st_size
                except OSError:
                    pass
    except Exception:                                              # noqa: BLE001
        pass
    return total
