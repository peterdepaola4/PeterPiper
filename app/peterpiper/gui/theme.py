"""
V2.9: the look of every PeterPiper window - one place for the colours, the font and
the shapes (Qt style sheet + palette), instead of the plain grey 'Fusion' look.

Two themes, chosen in View > Theme (remembered in the settings):

  midnight   dark navy panels, soft white text, a blue accent (the default)
  daylight   light grey window, white panels, dark text, the same blue accent

Graphs keep their white background (they are what you publish). The text font
is Segoe UI Variable (Windows 11), else Segoe UI, at the size chosen under
View > Larger / Smaller text.

Widgets can ask for a role with a Qt property instead of their own colours:
  button.setProperty("primary", True)   the main action of a window (accent)
  label.setProperty("muted", True)      a quieter, secondary text
  label.setProperty("role", "warn" | "danger" | "ok" | "title" | "subtitle")
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str            # window background
    surface: str       # panels / cards
    surface2: str      # inputs, buttons, list headers
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str   # text on the accent colour
    hover: str
    select: str        # selected rows (accent, translucent)
    warn: str
    danger: str
    ok: str
    dark: bool


THEMES: Dict[str, Theme] = {
    "midnight": Theme("midnight", bg="#0E1320", surface="#151C2C", surface2="#1D2639",
                      border="#2B3650", text="#E7ECF5", muted="#93A0B8", accent="#5B8CFF",
                      accent_text="#FFFFFF", hover="#24304A", select="rgba(91,140,255,0.28)",
                      warn="#F5B040", danger="#F05252", ok="#34D399", dark=True),
    "daylight": Theme("daylight", bg="#EEF1F6", surface="#FFFFFF", surface2="#F4F6FA",
                      border="#D5DCE7", text="#1A2233", muted="#5F6B80", accent="#3567F0",
                      accent_text="#FFFFFF", hover="#E6ECF8", select="rgba(53,103,240,0.18)",
                      warn="#B45309", danger="#C81E1E", ok="#047857", dark=False),
}
DEFAULT = "midnight"
_current: Optional[Theme] = None


def current() -> Theme:
    return _current or THEMES[DEFAULT]


def font_family() -> str:
    fams = set(QFontDatabase.families())
    for f in ("Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI",       # Windows
              ".AppleSystemUIFont", "SF Pro Text", "Helvetica Neue",              # macOS
              "Inter", "Arial"):
        if f in fams:
            return f
    return QFont().family()


def _icons(t: Theme) -> Path:
    """Small pictures the style sheet needs (tick mark, arrows), drawn with
    QPainter as PNG (no SVG support is needed), written once per theme next to
    the settings, at twice the size for sharp edges."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter, QPen
    from ..config import _settings_file
    d = _settings_file().parent / "theme" / t.name
    d.mkdir(parents=True, exist_ok=True)

    def draw(name, size, colour, width, points):
        p = d / name
        img = QImage(size * 2, size * 2, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        g = QPainter(img)
        g.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(colour), width * 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        g.setPen(pen)
        pts = [QPointF(x * 2, y * 2) for x, y in points]
        for a, b in zip(pts, pts[1:]):
            g.drawLine(a, b)
        g.end()
        try:
            img.save(str(p), "PNG")
        except Exception:                                          # noqa: BLE001
            pass
    draw("check.png", 16, t.accent_text, 2.2, [(3.5, 8.5), (6.5, 11.5), (12.5, 4.5)])
    draw("partial.png", 16, t.accent_text, 2.2, [(4, 8), (12, 8)])
    draw("down.png", 12, t.muted, 1.6, [(2.5, 4.5), (6, 8), (9.5, 4.5)])
    draw("up.png", 12, t.muted, 1.6, [(2.5, 7.5), (6, 4), (9.5, 7.5)])
    draw("right.png", 12, t.muted, 1.6, [(4.5, 2.5), (8, 6), (4.5, 9.5)])
    draw("open.png", 12, t.accent, 1.8, [(2.5, 4.5), (6, 8), (9.5, 4.5)])
    return d


def style_sheet(t: Theme, pt: float) -> str:
    ic = _icons(t).as_posix()
    small = max(7.0, pt - 1.0)
    return f"""
* {{ font-family: "{font_family()}"; font-size: {pt:g}pt; }}
QWidget {{ color: {t.text}; background: {t.bg}; }}
QDialog, QMainWindow {{ background: {t.bg}; }}
QLabel {{ background: transparent; }}
QLabel[muted="true"] {{ color: {t.muted}; }}
QLabel[role="warn"] {{ color: {t.warn}; }}
QLabel[role="danger"] {{ color: {t.danger}; font-weight: 600; }}
QLabel[role="ok"] {{ color: {t.ok}; }}
QLabel[role="title"] {{ font-size: {pt + 5:g}pt; font-weight: 600; }}
QLabel[role="subtitle"] {{ color: {t.muted}; font-size: {pt + 0.5:g}pt; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

QGroupBox {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px;
    margin-top: 16px; padding: 14px 12px 10px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; left: 12px; top: 2px;
    padding: 0 6px; color: {t.accent}; font-weight: 600; background: transparent;
}}
QGroupBox QWidget {{ background: transparent; }}
QGroupBox[active="true"] {{ border: 1px solid {t.accent}; }}
QGroupBox[folded="true"] {{ background: transparent; border: none;
    border-bottom: 1px solid {t.border}; border-radius: 0; margin-top: 12px; padding: 0; }}
QGroupBox[folded="true"]::title {{ color: {t.muted}; top: 0px; }}
QGroupBox QLineEdit, QGroupBox QComboBox, QGroupBox QSpinBox, QGroupBox QDoubleSpinBox,
QGroupBox QPushButton, QGroupBox QToolButton, QGroupBox QTreeWidget, QGroupBox QListWidget,
QGroupBox QTableWidget {{ background: {t.surface2}; }}

QPushButton, QToolButton {{
    background: {t.surface2}; border: 1px solid {t.border}; border-radius: 8px;
    padding: 6px 14px; min-height: 18px;
}}
QPushButton:hover, QToolButton:hover {{ background: {t.hover}; border-color: {t.accent}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t.select}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.muted}; border-color: {t.border};
                                              background: {t.surface}; }}
QPushButton[primary="true"], QGroupBox QPushButton[primary="true"] {{
    background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent};
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{ background: {QColor(t.accent).lighter(112).name()}; }}
QPushButton[primary="true"]:disabled {{ background: {t.surface2}; color: {t.muted};
                                         border-color: {t.border}; }}
QPushButton[step] {{ border-radius: 13px; padding: 4px 6px; color: {t.muted};
                     background: {t.surface}; }}
QPushButton[step="done"] {{ color: {t.ok}; border-color: {t.border}; }}
QPushButton[step="current"] {{ background: {t.accent}; color: {t.accent_text};
                              border-color: {t.accent}; font-weight: 600; }}
QPushButton:checked, QToolButton:checked {{ background: {t.select}; border-color: {t.accent}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {t.surface2}; border: 1px solid {t.border}; border-radius: 7px;
    padding: 4px 8px; selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {t.accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {t.muted}; background: {t.surface};
}}
QComboBox {{ padding-right: 24px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url("{ic}/down.png"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px;
    selection-background-color: {t.select}; selection-color: {t.text}; outline: none;
    padding: 4px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::down-button {{ border: none; width: 18px; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{ic}/up.png"); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{ic}/down.png"); width: 10px; height: 10px; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QTreeView::indicator, QTableView::indicator, QListView::indicator {{
    width: 16px; height: 16px; border-radius: 5px; border: 1.5px solid {t.muted};
    background: {t.surface2};
}}
QCheckBox::indicator:hover, QTreeView::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked, QTreeView::indicator:checked, QTableView::indicator:checked,
QListView::indicator:checked {{
    background: {t.accent}; border-color: {t.accent}; image: url("{ic}/check.png");
}}
QCheckBox::indicator:indeterminate, QTreeView::indicator:indeterminate {{
    background: {t.accent}; border-color: {t.accent}; image: url("{ic}/partial.png");
}}
QCheckBox::indicator:disabled {{ border-color: {t.border}; background: {t.surface}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px;
                            border: 1.5px solid {t.muted}; background: {t.surface2}; }}
QRadioButton::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}

QTreeView, QTreeWidget, QTableView, QTableWidget, QListView, QListWidget {{
    background: {t.surface}; alternate-background-color: {t.surface2};
    border: 1px solid {t.border}; border-radius: 10px; outline: none;
    selection-background-color: {t.select}; selection-color: {t.text};
    gridline-color: {t.border};
}}
QTreeView::item, QTableView::item, QListView::item {{ padding: 3px 4px; border: none; }}
QTreeView::item:hover, QTableView::item:hover, QListView::item:hover {{ background: {t.hover}; }}
QTreeView::item:selected, QTableView::item:selected, QListView::item:selected {{
    background: {t.select}; color: {t.text};
}}
QTreeView::branch {{ background: transparent; }}
QTreeView::branch:has-children:closed {{ image: url("{ic}/right.png"); }}
QTreeView::branch:has-children:open {{ image: url("{ic}/open.png"); }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{
    background: {t.surface2}; color: {t.muted}; border: none;
    border-bottom: 1px solid {t.border}; padding: 6px 8px; font-weight: 600;
    font-size: {small:g}pt;
}}
QHeaderView::section:hover {{ color: {t.text}; }}
QTableCornerButton::section {{ background: {t.surface2}; border: none; }}

QMenuBar {{ background: {t.bg}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {t.hover}; }}
QMenu {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px;
         padding: 6px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.select}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 5px 8px; }}
QToolTip {{
    background: {t.surface}; color: {t.text}; border: 1px solid {t.accent};
    border-radius: 8px; padding: 7px 9px;
}}
QTabWidget::pane {{ border: 1px solid {t.border}; border-radius: 10px; background: {t.surface}; }}
QTabBar::tab {{ background: transparent; color: {t.muted}; padding: 7px 16px;
                border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; }}
QSlider::groove:horizontal {{ height: 5px; background: {t.surface2}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {t.text}; width: 16px; height: 16px;
                               margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ background: {t.accent}; }}
QProgressBar {{ background: {t.surface2}; border: 1px solid {t.border}; border-radius: 7px;
                text-align: center; color: {t.text}; min-height: 16px; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 6px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 8px; image: none; }}
QSplitter::handle:vertical {{ height: 8px; }}
QSplitter::handle:hover {{ background: {t.select}; border-radius: 4px; }}
QStatusBar {{ background: {t.surface}; color: {t.muted}; border-top: 1px solid {t.border}; }}
QDockWidget::title {{ background: {t.surface2}; padding: 6px 10px; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; min-height: 32px; border-radius: 4px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; min-width: 32px; border-radius: 4px; }}
QScrollBar::handle:hover {{ background: {t.accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QMessageBox QLabel {{ font-size: {pt:g}pt; }}
"""


def palette(t: Theme) -> QPalette:
    p = QPalette()
    c = QColor
    for role, col in ((QPalette.Window, t.bg), (QPalette.WindowText, t.text),
                      (QPalette.Base, t.surface), (QPalette.AlternateBase, t.surface2),
                      (QPalette.Text, t.text), (QPalette.Button, t.surface2),
                      (QPalette.ButtonText, t.text), (QPalette.ToolTipBase, t.surface),
                      (QPalette.ToolTipText, t.text), (QPalette.Highlight, t.accent),
                      (QPalette.HighlightedText, t.accent_text),
                      (QPalette.PlaceholderText, t.muted), (QPalette.Link, t.accent)):
        p.setColor(role, c(col))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, c(t.muted))
    return p


LABELS = {"midnight": "Midnight (dark)", "daylight": "Daylight (light)"}


def switch(name: str, settings=None) -> Theme:
    """Change the theme of the running app (and remember it in settings)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    t = apply(app, name, app.font().pointSizeF())
    for w in QApplication.allWidgets():          # image views: the window's colour
        if w.__class__.__name__ == "GraphicsLayoutWidget" and getattr(w, "_pd4_bg", False):
            w.setBackground(t.bg)
    if settings is not None:
        settings.ui_theme = t.name
        try:
            from ..config import save_settings
            save_settings(settings)
        except Exception:                                          # noqa: BLE001
            pass
    return t


def apply(app, name: Optional[str] = None, pt: Optional[float] = None) -> Theme:
    """Apply a theme to the whole application (name None: the default)."""
    global _current
    t = THEMES.get(str(name or DEFAULT), THEMES[DEFAULT])
    _current = t
    if pt is None:
        pt = app.font().pointSizeF() if app.font().pointSizeF() > 0 else 10.0
    app.setStyle("Fusion")
    app.setPalette(palette(t))
    f = QFont(font_family())
    f.setPointSizeF(pt)
    app.setFont(f)
    app.setStyleSheet(style_sheet(t, pt))
    return t
