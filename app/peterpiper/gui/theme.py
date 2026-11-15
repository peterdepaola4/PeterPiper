"""
V2.9: the look of every PeterPiper window - one place for the colours, the font and
the shapes (Qt style sheet + palette), instead of the plain grey 'Fusion' look.

Two themes, chosen in View > Theme (remembered in the settings):

  midnight   dark navy panels, soft white text, a blue accent (the default)
  daylight   light grey window, white panels, dark text, the same blue accent

1.1: eighteen more "colour palettes" (Rose, Hot Pink, Forest, Neon, High Contrast
...) appear in the theme lists once a user has found them (a hidden extra:
achievements.py, widgets.LogoLabel). available_names() lists what this user may
choose. Every theme must pass validate(): WCAG 2 contrast minimums for each text /
background pair the style sheet uses (MIN_* below), checked by
dev_tests/test_v11_looks.py - so no palette can make text hard to read.

Graphs keep their white background (they are what you publish), and the cells'
colours never change with the theme (widgets.cell_colour). The text font
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


# The themes. midnight and daylight are always offered; the others are the hidden
# "colour palettes" (1.1) - every one must pass validate() below (readable text,
# checked by dev_tests/test_v11_looks.py). Graphs keep their white background in
# every theme and cell colours never follow the theme (widgets.cell_colour).
def _T(name, dark, bg, surface, surface2, border, text, muted, accent, accent_text, hover,
       select, warn, danger, ok) -> Theme:
    return Theme(name, bg=bg, surface=surface, surface2=surface2, border=border, text=text,
                 muted=muted, accent=accent, accent_text=accent_text, hover=hover,
                 select=select, warn=warn, danger=danger, ok=ok, dark=dark)


THEMES: Dict[str, Theme] = {t.name: t for t in (
    # ---- the basic two (1.1: midnight's accent text is dark and its red lighter,
    # so a primary button and a red warning are readable - see validate())
    _T("midnight", True, "#0E1320", "#151C2C", "#1D2639", "#2B3650", "#E7ECF5", "#93A0B8",
       "#5B8CFF", "#0B1222", "#24304A", "rgba(91,140,255,0.28)", "#F5B040", "#FF6B6B",
       "#34D399"),
    _T("daylight", False, "#EEF1F6", "#FFFFFF", "#F4F6FA", "#CDD5E2", "#1A2233", "#5F6B80",
       "#3567F0", "#FFFFFF", "#E6ECF8", "rgba(53,103,240,0.18)", "#A64B08", "#C81E1E",
       "#047857"),
    # ---- light palettes
    _T("rose", False, "#FBEFF2", "#FFFFFF", "#FDF5F7", "#EAC6D0", "#3A1420", "#7A4A58",
       "#C2185B", "#FFFFFF", "#F8E1E8", "rgba(194,24,91,0.16)", "#9A4A00", "#B3132B",
       "#2E7D32"),
    _T("bubblegum", False, "#FDEEF7", "#FFFFFF", "#FFF5FB", "#F0C2DF", "#2B1030", "#6E4A72",
       "#1565C0", "#FFFFFF", "#FADDEF", "rgba(21,101,192,0.16)", "#9A4A00", "#B3132B",
       "#2E7D32"),
    _T("cherry_blossom", False, "#FFF3F5", "#FFFFFF", "#FFF8F9", "#EFCCD5", "#3B1E2B",
       "#7D5565", "#8E3B66", "#FFFFFF", "#FBE3E9", "rgba(142,59,102,0.16)", "#9A4A00",
       "#B3132B", "#2E7D32"),
    _T("mint", False, "#EAF7F1", "#FFFFFF", "#F2FBF7", "#BFE0D0", "#0F2A20", "#4B6B5E",
       "#0E7A55", "#FFFFFF", "#DDF1E7", "rgba(14,122,85,0.16)", "#9A4A00", "#B3132B",
       "#0E6B47"),
    _T("lavender", False, "#F2EFFA", "#FFFFFF", "#F8F6FD", "#D6CCEC", "#241A3A", "#5F5478",
       "#6A4BC4", "#FFFFFF", "#E8E2F7", "rgba(106,75,196,0.16)", "#9A4A00", "#B3132B",
       "#2E7D32"),
    _T("arctic", False, "#E9F1F7", "#FFFFFF", "#F2F7FB", "#C5D7E5", "#0D2233", "#4A6275",
       "#0B6E99", "#FFFFFF", "#DDEAF3", "rgba(11,110,153,0.16)", "#9A4A00", "#B3132B",
       "#28712C"),
    _T("mono", False, "#F0F0F0", "#FFFFFF", "#F7F7F7", "#C8C8C8", "#111111", "#555555",
       "#2A2A2A", "#FFFFFF", "#E6E6E6", "rgba(0,0,0,0.12)", "#8A5300", "#B3132B",
       "#2E6B30"),
    # ---- dark palettes
    _T("hot_pink", True, "#1A0A14", "#25101D", "#311627", "#5A2A48", "#FCE8F3", "#D79DBE",
       "#FF4FA3", "#1A0A14", "#3D1C31", "rgba(255,79,163,0.28)", "#F5B040", "#FF7A7A",
       "#4ADE80"),
    _T("crimson", True, "#160A0C", "#211013", "#2C161A", "#57292F", "#F8E9EA", "#CC9FA4",
       "#F2606A", "#160A0C", "#3A1C21", "rgba(242,96,106,0.28)", "#F5B040", "#FF8A8A",
       "#4ADE80"),
    _T("forest", True, "#0C1610", "#122019", "#192B21", "#2C4A39", "#E6F2EA", "#9DBBA8",
       "#4CC38A", "#07120C", "#21392B", "rgba(76,195,138,0.26)", "#F5B040", "#FF7A7A",
       "#6EE7A8"),
    _T("ocean", True, "#08141F", "#0D1D2B", "#132738", "#23415A", "#E3F1FA", "#8FB3CC",
       "#2BB3E6", "#04121C", "#1A3347", "rgba(43,179,230,0.26)", "#F5B040", "#FF7A7A",
       "#4ADE80"),
    _T("peacock", True, "#061C20", "#0B262B", "#113137", "#22525A", "#E6F6F3", "#93C3BC",
       "#3CC7E0", "#061C20", "#183E45", "rgba(60,199,224,0.26)", "#F2C14E", "#FF7A7A",
       "#5EEAB0"),
    _T("sunset", True, "#1C1020", "#27162B", "#331D37", "#5A3560", "#FFEFE5", "#D6AABB",
       "#FF8A4C", "#1C1020", "#42264A", "rgba(255,138,76,0.26)", "#FFC15C", "#FF7A8A",
       "#4ADE80"),
    _T("coffee", True, "#1B1410", "#251C16", "#30251D", "#4E3D30", "#F3E9DF", "#BFA894",
       "#D29A5C", "#1B1410", "#3D3026", "rgba(210,154,92,0.26)", "#F5B040", "#FF7A7A",
       "#7DD99A"),
    _T("slate", True, "#1E232A", "#262C35", "#2F3640", "#4A5563", "#EEF1F5", "#AAB4C1",
       "#86ADE0", "#11161C", "#3A4350", "rgba(134,173,224,0.26)", "#F5B040", "#FF8A8A",
       "#6EE7A8"),
    _T("gold_on_black", True, "#000000", "#0E0E0E", "#181818", "#4A3F1E", "#F5E6B8",
       "#C2AB70", "#E6B422", "#000000", "#262214", "rgba(230,180,34,0.26)", "#FFB347",
       "#FF7A7A", "#7DD99A"),
    _T("neon", True, "#07070F", "#0E0E1C", "#151529", "#34346A", "#EAFFFE", "#9DB9DA",
       "#00E5FF", "#07070F", "#202044", "rgba(0,229,255,0.24)", "#FFD23F", "#FF5FD2",
       "#39FF88"),
    _T("high_contrast", True, "#000000", "#000000", "#0A0A0A", "#FFFFFF", "#FFFFFF",
       "#E6E6E6", "#FFE600", "#000000", "#1F1F1F", "rgba(255,230,0,0.32)", "#FFB000",
       "#FF7B7B", "#5CFF8A"),
)}
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
    row = selected_row(t)          # 1.1: opaque, so stacked layers cannot change it
    chunk = progress_chunk(t)
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
QPushButton[primary="true"]:hover {{ background: {accent_hover(t)}; }}
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
    selection-background-color: {row}; selection-color: {t.text}; outline: none;
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
    selection-background-color: {row}; selection-color: {t.text};
    gridline-color: {t.border};
}}
QTreeView::item, QTableView::item, QListView::item {{ padding: 3px 4px; border: none; }}
QTreeView::item:hover, QTableView::item:hover, QListView::item:hover {{ background: {t.hover}; }}
QTreeView::item:selected, QTableView::item:selected, QListView::item:selected {{
    background: {row}; color: {t.text};
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
QMenu::item:selected {{ background: {row}; }}
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
QProgressBar::chunk {{ background: {chunk}; border-radius: 6px; }}
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


LABELS = {"midnight": "Midnight (dark)", "daylight": "Daylight (light)",
          "rose": "Rose (light)", "bubblegum": "Bubblegum (light)",
          "cherry_blossom": "Cherry Blossom (light)", "mint": "Mint (light)",
          "lavender": "Lavender (light)", "arctic": "Arctic (light)", "mono": "Mono (light)",
          "hot_pink": "Hot Pink (dark)", "crimson": "Crimson (dark)", "forest": "Forest (dark)",
          "ocean": "Ocean (dark)", "peacock": "Peacock (dark)", "sunset": "Sunset (dark)",
          "coffee": "Coffee (dark)", "slate": "Slate (dark)",
          "gold_on_black": "Gold on Black (dark)", "neon": "Neon (dark)",
          "high_contrast": "High Contrast (dark)"}
BASIC = ("midnight", "daylight")      # always offered; the others are hidden extras (1.1)


# ------------------------------------------------------------------ 1.1 readability
# Minimum WCAG 2 contrast ratios every theme must meet (validate()). 7.0 = WCAG AAA
# for body text, 4.5 = AA for normal text, 3.0 = AA for bold headings / controls.
MIN_TEXT = 7.0          # text on bg, surface, surface2 and hover
MIN_MUTED = 4.5         # quiet text (muted) on bg, surface, surface2
MIN_ON_ACCENT = 4.5     # accent_text on the accent (and on the accent's hover shade)
MIN_STATUS = 4.5        # warn / danger / ok: used AS TEXT (QLabel roles, finished steps)
MIN_SELECTED = 4.5      # text on a selected row (select drawn over bg / surface / surface2)
MIN_ACCENT_UI = 3.0     # accent as box titles (bold), focus frames, ticks: on bg and surface
MIN_LOGO = 4.5          # the logo (white on dark themes, black on light) on bg
MIN_BORDER = 1.25       # a border still visible on bg


def accent_hover(t: Theme) -> str:
    """The accent when the mouse is on a primary button: moved AWAY from the
    accent's text colour (lighter under dark text, darker under light text), so
    the hover never makes the button's text harder to read."""
    from .colourvision import luminance
    c = QColor(t.accent)
    return (c.lighter(112) if luminance(t.accent_text) < luminance(t.accent)
            else c.darker(112)).name()


def on_colour(bg: str) -> str:
    """Black or white - whichever reads better on the colour bg (for a widget
    that paints its own background, e.g. a theme colour)."""
    from .colourvision import contrast
    return "#101010" if contrast("#101010", bg) >= contrast("#FFFFFF", bg) else "#FFFFFF"


def selected_row(t: Theme) -> str:
    """The (opaque) colour of a selected row in lists, tables and menus: the
    translucent select colour as strong as it looked up to 1.0 (Qt painted it
    three times over the list's surface) - weaker where the row's text would
    then be hard to read - painted as one layer, so the text contrast is
    exactly what validate() checks."""
    from .colourvision import composite, contrast, parse
    r, g, b, a = parse(t.select)
    alpha = 1.0 - (1.0 - a) ** 3
    while True:
        c = composite(f"rgba({r:g},{g:g},{b:g},{alpha:.4f})", t.surface)
        if alpha <= a or contrast(t.text, c) >= MIN_SELECTED:
            return c
        alpha = max(a, alpha - 0.02)


def progress_chunk(t: Theme) -> str:
    """The filled part of a progress bar: the accent over the bar's groove, as
    strong as it can be while the percentage (theme text) stays readable on it."""
    from .colourvision import composite, contrast, parse
    r, g, b, _a = parse(t.accent)
    alpha = 1.0
    while alpha > 0.3:
        c = composite(f"rgba({r:g},{g:g},{b:g},{alpha:.2f})", t.surface2)
        if contrast(t.text, c) >= MIN_SELECTED:
            return c
        alpha -= 0.05
    return composite(f"rgba({r:g},{g:g},{b:g},0.3)", t.surface2)


def tint_backgrounds(t: Theme) -> list:
    """The backgrounds a coloured name in a list can sit on: the list (surface),
    alternate rows, hover and the window. (A selected row shows the theme's own
    text colour - the style sheet's selection colour wins over an item's.)"""
    return [t.surface, t.surface2, t.hover, t.bg]


def readable_tint(hue: float, saturation: float, t: Optional[Theme] = None,
                  minimum: float = MIN_MUTED) -> str:
    """The most vivid colour of this hue and saturation (HSL) that is still
    readable (contrast >= minimum) on every background of tint_backgrounds(t):
    lightness starts at 0.5 and moves towards the theme's text until it reads."""
    from .colourvision import contrast
    t = t or current()
    bgs = tint_backgrounds(t)
    step = 0.01 if t.dark else -0.01
    light = 0.5
    for _ in range(60):
        c = QColor.fromHslF((hue % 360.0) / 360.0, max(0.0, min(1.0, saturation)), light)
        name = c.name().upper()
        if all(contrast(name, b) >= minimum for b in bgs):
            return name
        light = max(0.0, min(1.0, light + step))
    return t.text.upper()


def checks(t: Theme) -> list:
    """Every readability check of a theme: [(what, ratio, minimum)]."""
    from .colourvision import composite, contrast, luminance
    out = []

    def need(what, a, b, minimum):
        out.append((what, round(contrast(a, b), 2), minimum))
    for k in ("bg", "surface", "surface2", "hover"):
        need(f"text on {k}", t.text, getattr(t, k), MIN_TEXT)
    for k in ("bg", "surface", "surface2"):
        need(f"muted on {k}", t.muted, getattr(t, k), MIN_MUTED)
        for s in ("warn", "danger", "ok"):
            need(f"{s} on {k}", getattr(t, s), getattr(t, k), MIN_STATUS)
        need(f"text on selection over {k}", t.text, composite(t.select, getattr(t, k)),
             MIN_SELECTED)
    need("text on a selected row", t.text, selected_row(t), MIN_SELECTED)
    need("text on the progress bar", t.text, progress_chunk(t), MIN_SELECTED)
    need("progress bar visible", progress_chunk(t), t.surface2, 1.4)
    need("accent_text on accent", t.accent_text, t.accent, MIN_ON_ACCENT)
    need("accent_text on accent (hover)", t.accent_text, accent_hover(t), MIN_ON_ACCENT)
    for k in ("bg", "surface"):
        need(f"accent on {k}", t.accent, getattr(t, k), MIN_ACCENT_UI)
    need("logo on bg", "#FFFFFF" if t.dark else "#000000", t.bg, MIN_LOGO)
    need("border on bg", t.border, t.bg, MIN_BORDER)
    dark_ok = (luminance(t.bg) < luminance(t.text)) == bool(t.dark)
    out.append(("dark flag", 1.0 if dark_ok else 0.0, 1.0))
    return out


def validate(t: Theme) -> list:
    """The readability problems of a theme ([] = none): text / background pairs
    below the WCAG 2 contrast minimums above, and a wrong dark flag."""
    return [f"{t.name}: {what} {ratio:g} < {minimum:g}" if what != "dark flag"
            else f"{t.name}: the dark flag does not match its colours"
            for what, ratio, minimum in checks(t) if ratio < minimum]


def available_names() -> list:
    """The themes this user can choose, in menu order (1.1: the basic two, plus the
    extra palettes once found - achievements.py). Build theme menus from this
    each time they are shown, so a newly found palette appears at once."""
    names = [n for n in BASIC if n in THEMES]
    try:
        from .. import achievements
        if achievements.unlocked("palettes"):
            names += [n for n in THEMES if n not in names]
    except Exception:                                              # noqa: BLE001
        pass
    return names


def label(name: str) -> str:
    return LABELS.get(name) or name.replace("_", " ").title()


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
