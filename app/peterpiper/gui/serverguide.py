"""
PeterPiper 4.0: 'How this works' - a short guide to the lab folder, a few pages
with a picture each (assets/tips/server_*.png, made by build/make_tips_server.py).

    ServerGuide(parent, page=0).exec()      or  show_guide(parent, page=0)
    PAGES                                   [(title, html text, picture name)]
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout,
                               QWidget)

from . import widgets as W
from .tips import pic_path

PIC_W = 480                       # px: the pictures are shown at this width

PAGES = [
    ("What the lab folder is",
     "<p>The <b>lab folder</b> is one shared folder for the whole lab - in Box, "
     "OneDrive, Google Drive, Dropbox or on a network drive. The sync app (or the "
     "network) carries it to every lab computer; PeterPiper itself never goes "
     "online.</p>"
     "<p>In it, each person has <b>People/&lt;name&gt;</b> for their results, "
     "exports and backups, and <b>Shared</b> keeps what the lab shares: profiles, "
     "detectors, Prism templates and settings.</p>"
     "<p>Usually one person (the lab's admin) sets it up once. Everyone else just "
     "<b>connects</b>.</p>",
     "server_layout"),
    ("Which folder do I pick?",
     "<p>Pick <b>the lab's PeterPiper folder</b> - ask whoever set it up. Any folder "
     "inside it works too: PeterPiper walks up and finds the top.</p>"
     "<p><b>Not your own subfolder.</b> You do not need to make a folder for "
     "yourself - PeterPiper makes <b>People/&lt;you&gt;</b> for you when you "
     "connect (it asks first).</p>"
     "<p>If your results already go to a folder of your own, PeterPiper says so and "
     "offers to use People/&lt;you&gt; instead. Nothing already saved is moved.</p>",
     "server_pick"),
    ("How Box Drive & co. work",
     "<p>The sync app shows the lab folder on your computer, but a file can be "
     "<b>online-only</b> - only a stand-in: opening it downloads it first. Files "
     "marked <b>available offline</b> are really on your computer.</p>"
     "<p>A big .nd2 movie read straight from the cloud or a network drive is slow. "
     "So PeterPiper first <b>copies it into a movie cache</b> on your computer, in the "
     "background, and opens that copy. With 'Fetch the next movie' on, the next "
     "movie of your queue is copied while you work.</p>"
     "<p>OneDrive, Google Drive and Dropbox work the same way; a network drive has "
     "no stand-ins, but is fetched the same way.</p>",
     "server_sync"),
    ("What is copied, and when",
     "<p>While you work, PeterPiper copies in the background - Next movie never "
     "waits:</p><ul>"
     "<li><b>SAVE / autosave</b> -&gt; People/you/Results (on)</li>"
     "<li><b>Exports</b> -&gt; People/you/Exports (on)</li>"
     "<li><b>Analysed .nd2 movies</b> -&gt; People/you/Movies (off: big files)</li>"
     "<li><b>Backup</b> of your profile, settings and run list -&gt; People/you/Backups "
     "when PeterPiper closes and once a day (on)</li></ul>"
     "<p>Each copy is checked, then given its name - a half-copied file never "
     "looks finished. The small line at the bottom shows what runs.</p>",
     "server_upload"),
    ("Windows and Mac",
     "<p>The same lab folder has a different path on each computer (e.g. "
     "<i>C:\\Users\\you\\Box\\...</i> on Windows, <i>~/Library/CloudStorage/Box-Box/...</i> "
     "on a Mac). Each computer remembers its own path; everything inside is the "
     "same, so it works on both.</p>"
     "<p>On a new computer: install the sync app, sign in there, then Connect... "
     "in PeterPiper.</p>",
     "server_paths"),
    ("The movie cache",
     "<p>The cache holds copies only - the originals stay in the lab folder. Its "
     "limit is 50 GB or 20% of the free disk, whichever is smaller (you can choose "
     "your own). Over the limit, the movies used longest ago are removed; the open "
     "movie never is.</p>",
     "server_cache"),
    ("When something is wrong",
     "<p>The coloured line in 'Lab folder &amp; backup' says what is wrong and what to "
     "do:</p><ul>"
     "<li><b>Sync app not running</b> - start it (Box Drive, OneDrive ...): until "
     "then nothing is uploaded.</li>"
     "<li><b>Disk full</b> - free some space, or choose a cache on another disk.</li>"
     "<li><b>Conflict copies</b> like <i>file (1).xlsx</i> - two computers changed a "
     "file at once; the sync app kept both. Keep the one you want.</li>"
     "<li><b>Slow first open</b> - the movie is being downloaded; the next time it "
     "comes from the cache.</li>"
     "<li><b>Cannot be reached</b> - sign in to the sync app, or connect to the "
     "network drive, then press Check.</li></ul>",
     "server_health"),
]


class ServerGuide(QDialog):
    """The guide: one page at a time, Back / Next."""

    def __init__(self, parent: Optional[QWidget] = None, page: int = 0) -> None:
        super().__init__(parent)
        self.setWindowTitle("How the lab folder works")
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        self.stack = QStackedWidget()
        for title, text, pic in PAGES:
            self.stack.addWidget(self._page(title, text, pic))
        lay.addWidget(self.stack, 1)
        bl = QHBoxLayout()
        self.lbl_n = QLabel("")
        self.lbl_n.setProperty("muted", True)
        bl.addWidget(self.lbl_n)
        bl.addStretch(1)
        self.btn_back = W.button("Back", lambda: self.go(-1), "The page before.")
        self.btn_next = W.button("Next", lambda: self.go(1), "The next page.", strong=True)
        self.btn_close = W.button("Close", self.accept, "Close the guide.")
        for b in (self.btn_back, self.btn_next, self.btn_close):
            b.setAutoDefault(False)
            bl.addWidget(b)
        lay.addLayout(bl)
        self.setMinimumWidth(PIC_W + 60)
        self.show_page(page)

    def _page(self, title: str, text: str, pic: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(8)
        t = QLabel(title)
        t.setProperty("role", "title")
        v.addWidget(t)
        p = pic_path(pic)
        if p is not None:
            img = QLabel()
            pm = QPixmap(str(p))
            img.setPixmap(pm.scaledToWidth(PIC_W, Qt.SmoothTransformation))
            img.setAlignment(Qt.AlignHCenter)
            v.addWidget(img)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        body.setMaximumWidth(PIC_W + 40)
        v.addWidget(body)
        v.addStretch(1)
        return w

    def show_page(self, i: int) -> None:
        i = max(0, min(len(PAGES) - 1, int(i)))
        self.stack.setCurrentIndex(i)
        self.lbl_n.setText(f"Page {i + 1} of {len(PAGES)}")
        self.btn_back.setEnabled(i > 0)
        self.btn_next.setEnabled(i < len(PAGES) - 1)

    def go(self, step: int) -> None:
        self.show_page(self.stack.currentIndex() + step)


def show_guide(parent: Optional[QWidget] = None, page: int = 0) -> ServerGuide:
    d = ServerGuide(parent, page)
    d.show()
    return d
