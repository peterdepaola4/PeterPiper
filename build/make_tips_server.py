"""
PeterPiper 4.0, part "server": draws the pictures of the lab folder guide and of
the lab folder options' hover explanations - app/peterpiper/assets/tips/server_*.png
(640 x 320 px, shown at 320 x 160 in hover tips; light background, clear labels).

    python build/make_tips_server.py          (re-makes them all; Qt offscreen)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt                      # noqa: E402
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QPainter,  # noqa: E402
                           QPainterPath, QPen, QPolygonF)

OUT = Path(__file__).resolve().parents[1] / "app" / "peterpiper" / "assets" / "tips"
W, H = 640, 320
BG = QColor("#fbfbf9")
INK = QColor("#1f2328")
MUTED = QColor("#5b636b")
FOLDER = QColor("#e8b84a")
FOLDER_DARK = QColor("#b98a22")
BLUE = QColor("#2f6fb3")
GREEN = QColor("#1f8a4c")
AMBER = QColor("#c27c00")
RED = QColor("#c0392b")
LIGHT = QColor("#e9eef4")


class Pic:
    def __init__(self) -> None:
        self.img = QImage(W, H, QImage.Format_ARGB32)
        self.img.fill(BG)
        self.p = QPainter(self.img)
        self.p.setRenderHint(QPainter.Antialiasing, True)
        self.p.setRenderHint(QPainter.TextAntialiasing, True)

    def font(self, pt: float, bold: bool = False) -> None:
        f = QFont("Segoe UI" if sys.platform == "win32" else "Helvetica")
        f.setPixelSize(int(pt))
        f.setBold(bold)
        self.p.setFont(f)

    def text(self, x, y, s, pt=17, bold=False, colour=INK, w=None, align=Qt.AlignLeft):
        self.font(pt, bold)
        self.p.setPen(colour)
        if w is None:
            self.p.drawText(QPointF(x, y), s)
        else:
            self.p.drawText(QRectF(x, y - pt, w, pt * 4), int(align | Qt.TextWordWrap), s)

    def folder(self, x, y, w=34, h=26, colour=FOLDER):
        p = self.p
        p.setPen(QPen(FOLDER_DARK, 1.5))
        p.setBrush(colour)
        path = QPainterPath()
        path.moveTo(x, y + 5)
        path.lineTo(x + w * 0.38, y + 5)
        path.lineTo(x + w * 0.46, y)
        path.lineTo(x + w * 0.05, y)
        path.closeSubpath()
        p.drawPath(path)
        p.drawRoundedRect(QRectF(x, y + 4, w, h - 4), 3, 3)

    def file(self, x, y, w=22, h=28, colour=QColor("#ffffff")):
        p = self.p
        p.setPen(QPen(MUTED, 1.4))
        p.setBrush(colour)
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(x + w - 7, y)
        path.lineTo(x + w, y + 7)
        path.lineTo(x + w, y + h)
        path.lineTo(x, y + h)
        path.closeSubpath()
        p.drawPath(path)

    def cloud(self, cx, cy, s=1.0, colour=LIGHT, edge=BLUE):
        p = self.p
        p.setPen(QPen(edge, 2))
        p.setBrush(colour)
        path = QPainterPath()
        for dx, dy, r in ((-22, 6, 16), (0, -6, 22), (24, 4, 17), (6, 10, 18)):
            one = QPainterPath()
            one.addEllipse(QPointF(cx + dx * s, cy + dy * s), r * s, r * s)
            path = path.united(one)
        p.drawPath(path)

    def arrow(self, x1, y1, x2, y2, colour=BLUE, width=2.5, both=False):
        import math
        p = self.p
        p.setPen(QPen(colour, width, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        ang = math.atan2(y2 - y1, x2 - x1)
        for (xa, ya, a) in ((x2, y2, ang),) + (((x1, y1, ang + math.pi),) if both else ()):
            pts = [QPointF(xa, ya),
                   QPointF(xa - 11 * math.cos(a - 0.4), ya - 11 * math.sin(a - 0.4)),
                   QPointF(xa - 11 * math.cos(a + 0.4), ya - 11 * math.sin(a + 0.4))]
            p.setBrush(colour)
            p.drawPolygon(QPolygonF(pts))

    def mark(self, x, y, good: bool, r=13):
        p = self.p
        p.setPen(Qt.NoPen)
        p.setBrush(GREEN if good else RED)
        p.drawEllipse(QPointF(x, y), r, r)
        p.setPen(QPen(QColor("#ffffff"), 3, Qt.SolidLine, Qt.RoundCap))
        if good:
            p.drawLine(QPointF(x - 6, y), QPointF(x - 1, y + 5))
            p.drawLine(QPointF(x - 1, y + 5), QPointF(x + 7, y - 5))
        else:
            p.drawLine(QPointF(x - 5, y - 5), QPointF(x + 5, y + 5))
            p.drawLine(QPointF(x + 5, y - 5), QPointF(x - 5, y + 5))

    def dot(self, x, y, colour, r=10):
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(colour)
        self.p.drawEllipse(QPointF(x, y), r, r)

    def line(self, x1, y1, x2, y2, colour=MUTED, width=1.5):
        self.p.setPen(QPen(colour, width))
        self.p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def box(self, x, y, w, h, colour=LIGHT, edge=MUTED):
        self.p.setPen(QPen(edge, 1.2))
        self.p.setBrush(colour)
        self.p.drawRoundedRect(QRectF(x, y, w, h), 8, 8)

    def save(self, name: str) -> Path:
        self.p.end()
        OUT.mkdir(parents=True, exist_ok=True)
        out = OUT / f"{name}.png"
        self.img.save(str(out))
        return out


def layout() -> Path:
    """The lab folder's layout as a tree."""
    a = Pic()
    a.text(20, 32, "The lab folder", 21, True)
    a.folder(24, 50)
    a.text(66, 72, "PeterPiper lab", 18, True)
    rows = [(1, "file", ".peterpiper-lab.json", "marker: 'this is the lab folder'"),
            (1, "file", "READ ME - PeterPiper lab folder.txt", ""),
            (1, "folder", "People", "one folder per person"),
            (2, "folder", "You", "Results · Exports · Backups · Movies"),
            (2, "folder", "Colleague", "theirs"),
            (1, "folder", "Shared", "profiles · detectors · Prism templates · settings")]
    y = 108
    for depth, kind, name, note in rows:
        x = 40 + 30 * depth
        a.line(x - 22, y - 30, x - 22, y - 2)
        a.line(x - 22, y - 2 + 0, x - 4, y - 2)
        if kind == "folder":
            a.folder(x, y - 16, 26, 20)
        else:
            a.file(x + 4, y - 17, 16, 21)
        a.text(x + 34, y, name, 16, name in ("You",))
        if note:
            a.text(x + 44 + a.p.fontMetrics().horizontalAdvance(name), y, note, 14,
                   colour=MUTED)
        y += 36
    return a.save("server_layout")


def pick() -> Path:
    """Which folder to pick when connecting."""
    a = Pic()
    a.text(20, 32, "Which folder do I pick?", 21, True)
    a.box(20, 52, 290, 245, QColor("#eef7f0"), GREEN)
    a.mark(48, 82, True)
    a.text(70, 89, "The lab's folder", 18, True)
    a.folder(44, 112)
    a.text(86, 132, "PeterPiper lab", 16, True)
    a.text(44, 178, "Ask whoever set it up. Any folder inside it works too - "
                    "PeterPiper finds the top.", 14, w=250, colour=INK)
    a.box(330, 52, 290, 245, QColor("#fbeeee"), RED)
    a.mark(358, 82, False)
    a.text(380, 89, "Not your own folder", 18, True)
    a.folder(354, 112)
    a.text(396, 132, "Peter  /  My stuff", 16, True)
    a.text(354, 178, "No need to make one: PeterPiper makes People/<you> for you when "
                     "you connect.", 14, w=250, colour=INK)
    return a.save("server_pick")


def sync() -> Path:
    """Online-only vs on this computer; the movie cache."""
    a = Pic()
    a.text(20, 32, "How the sync app works", 21, True)
    a.cloud(92, 110, 1.4)
    a.text(48, 170, "Box / OneDrive /", 14, colour=MUTED)
    a.text(48, 188, "Google Drive ...", 14, colour=MUTED)
    a.arrow(160, 110, 255, 110, BLUE, both=True)
    a.text(170, 98, "sync app", 13, colour=BLUE)
    a.box(262, 58, 358, 112)
    a.text(278, 84, "On this computer", 16, True)
    a.file(280, 96, 20, 26)
    a.cloud(296, 120, 0.3)
    a.text(312, 118, "online-only: a stand-in; opening it downloads it", 14, w=300)
    a.file(280, 140, 20, 26, QColor("#dff0e3"))
    a.text(312, 158, "available offline: really here", 14)
    a.box(262, 196, 358, 104, QColor("#fff7e6"), AMBER)
    a.text(278, 222, "Big .nd2 movies", 16, True)
    a.text(278, 246, "are first copied into a movie cache on this computer, in the "
                     "background - then they open and scroll fast.", 14, w=330)
    a.arrow(230, 250, 258, 250, AMBER)
    a.folder(150, 230, 40, 30)
    a.text(132, 285, "lab folder", 14, colour=MUTED)
    return a.save("server_sync")


def upload() -> Path:
    """What goes where automatically."""
    a = Pic()
    a.text(20, 32, "What is copied to the lab folder", 21, True)
    a.box(20, 60, 170, 230)
    a.text(36, 88, "PeterPiper", 17, True)
    items = [("SAVE / autosave", "People/You/Results", "on", 128),
             ("Export", "People/You/Exports", "on", 178),
             ("Analysed .nd2", "People/You/Movies", "off", 228),
             ("Closing PeterPiper", "People/You/Backups", "on", 278)]
    for left, right, state, y in items:
        a.text(34, y, left, 15)
        a.arrow(196, y - 5, 360, y - 5, GREEN if state == "on" else MUTED,
                width=2.5 if state == "on" else 1.5)
        a.text(250, y - 12, "on" if state == "on" else "off (big)", 13,
               colour=GREEN if state == "on" else MUTED)
        a.folder(372, y - 22, 26, 20)
        a.text(406, y - 4, right, 15, True)
    a.text(372, 64, "each change, in the background", 13, colour=MUTED)
    return a.save("server_upload")


def paths() -> Path:
    """Windows and Mac paths of the same lab folder."""
    a = Pic()
    a.text(20, 32, "Windows and Mac: different paths, one lab folder", 21, True)
    a.box(20, 60, 290, 110)
    a.text(36, 88, "Windows", 17, True)
    a.text(36, 116, "C:\\Users\\you\\Box\\", 15)
    a.text(36, 138, "    PeterPiper lab", 15, True)
    a.box(330, 60, 290, 110)
    a.text(346, 88, "Mac", 17, True)
    a.text(346, 116, "~/Library/CloudStorage/Box-Box/", 14)
    a.text(346, 138, "    PeterPiper lab", 15, True)
    a.arrow(165, 175, 290, 228, BLUE)
    a.arrow(475, 175, 350, 228, BLUE)
    a.folder(296, 222, 48, 36)
    a.text(170, 290, "Each computer remembers its own path; inside, everything is "
                     "the same.", 15, w=330, align=Qt.AlignHCenter)
    return a.save("server_paths")


def cache() -> Path:
    """The movie cache and its limit."""
    a = Pic()
    a.text(20, 32, "The movie cache (on this computer)", 21, True)
    x0, x1, y = 30, 610, 110
    a.box(x0, y, x1 - x0, 46, LIGHT)
    used = [(0.0, 0.22, "oldest", MUTED), (0.22, 0.45, "", QColor("#9fb7d3")),
            (0.45, 0.66, "open movie", BLUE), (0.66, 0.74, "next", GREEN)]
    for f0, f1, label, colour in used:
        a.p.setPen(Qt.NoPen)
        a.p.setBrush(colour)
        a.p.drawRect(QRectF(x0 + f0 * (x1 - x0), y + 1, (f1 - f0) * (x1 - x0), 44))
        if label:
            a.text(x0 + f0 * (x1 - x0) + 6, y + 30, label, 14, True, QColor("#ffffff"))
    lim = x0 + 0.86 * (x1 - x0)
    a.line(lim, y - 18, lim, y + 64, RED, 3)
    a.text(lim - 18, y - 24, "limit", 15, True, RED)
    a.text(30, 200, "Limit: 50 GB or 20% of the free disk, whichever is smaller "
                    "(or your own).", 15, w=580)
    a.text(30, 250, "Over the limit, the movies used longest ago are removed - never "
                    "the open one. Only copies: the originals stay in the lab folder.",
           15, w=580, colour=MUTED)
    return a.save("server_cache")


def health() -> Path:
    """The coloured line."""
    a = Pic()
    a.text(20, 32, "The lab folder line", 21, True)
    rows = [(GREEN, "Green", "reachable, can be written, sync app running, enough space"),
            (AMBER, "Amber", "works, but: the sync app is not running, read-only, or "
                             "the disk is getting full"),
            (RED, "Red", "cannot be reached, or the disk is full - the line says "
                         "what to do"),
            (MUTED, "Grey", "not connected yet")]
    y = 80
    for colour, name, words in rows:
        a.dot(40, y, colour, 12)
        a.text(64, y + 6, name, 17, True)
        a.text(140, y + 6, words, 15, w=470)
        y += 60
    return a.save("server_health")


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    made = [layout(), pick(), sync(), upload(), paths(), cache(), health()]
    for p in made:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
