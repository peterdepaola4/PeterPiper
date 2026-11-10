"""
Program entry point.

Because this is started by double-clicking a .bat file, there is no console to
print a traceback to; an unhandled error therefore has to become a dialog box,
otherwise the window would simply vanish. Hence the exception hook below.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _install_excepthook(app) -> None:
    from PySide6.QtWidgets import QMessageBox

    from . import APP_NAME

    def hook(kind, value, tb) -> None:
        text = "".join(traceback.format_exception(kind, value, tb))
        try:
            box = QMessageBox(QMessageBox.Critical, f"{APP_NAME} - unexpected error",
                              str(value) or kind.__name__)
            box.setInformativeText("The window is still open; you can usually carry on, "
                                   "or restart if something looks wrong.")
            box.setDetailedText(text)
            box.exec()
        except Exception:
            sys.__excepthook__(kind, value, tb)

    sys.excepthook = hook


def _scrollbar_style(app) -> None:
    """Scroll bars that stand out: a track darker than the window and a solid
    handle (the default Fusion ones nearly vanish into the background)."""
    dark = app.palette().window().color().lightness() < 128
    track, handle, hover = (("#151515", "#8c8c8c", "#4a90e2") if dark else
                            ("#9e9e9e", "#3c3c3c", "#1f6fe0"))
    app.setStyleSheet(f"""
        QScrollBar:vertical {{ background: {track}; width: 14px; margin: 0; }}
        QScrollBar:horizontal {{ background: {track}; height: 14px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {handle}; min-height: 30px;
                                       border-radius: 5px; margin: 2px; }}
        QScrollBar::handle:horizontal {{ background: {handle}; min-width: 30px;
                                         border-radius: 5px; margin: 2px; }}
        QScrollBar::handle:hover {{ background: {hover}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    """)


def main() -> int:
    from PySide6.QtWidgets import QApplication, QDialog

    from . import APP_NAME, __version__
    from .gui.clickwin import ClickWindow as MainWindow
    from .gui.setup import SetupDialog

    # PeterPiper 1.0: the taskbar shows PeterPiper's own icon, not Python's
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PeterPiper.App")
        except Exception:                                          # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    from .gui.widgets import app_icon
    app.setWindowIcon(app_icon())
    _install_excepthook(app)

    from .config import load_settings
    from .gui import theme
    from .gui.widgets import apply_font_pt, base_font_pt
    base_font_pt()                                # remember the Windows default first
    saved, _ = load_settings()
    # V2.9: one theme for every window (View > Theme), instead of the grey Fusion look
    theme.apply(app, getattr(saved, "ui_theme", "") or theme.DEFAULT,
                max(10.0, base_font_pt() + 1.0))
    if saved.ui_font_pt:
        apply_font_pt(saved.ui_font_pt)

    # V2.9: who is using it - everything after this is that user's own
    from . import users
    from .gui.userdlg import UserDialog

    users.migrate_old_home()                      # V2.9 profiles -> the version-free folder
    users.adopt_copied_profiles()                 # profile folders copied in by hand

    def pick_user(ask: bool = True) -> bool:
        users.deactivate()
        if not ask and users.dont_ask():          # 'Don't ask again' on this Windows account
            chosen = users.last_user()
        else:
            d = UserDialog()
            if d.exec() != QDialog.Accepted or not d.chosen:
                return False
            chosen = d.chosen
        users.activate(chosen)
        mine, _ = load_settings()                 # this user's look and text size
        from . import measure                     # ... and ratio baseline check
        measure.set_min_snr(getattr(mine, "ratio_min_snr", 5.0))
        theme.apply(app, getattr(mine, "ui_theme", "") or theme.DEFAULT,
                    max(10.0, base_font_pt() + 1.0))
        if mine.ui_font_pt:
            apply_font_pt(mine.ui_font_pt)
        return True
    if not pick_user(ask=False):
        return 0
    # V2.9: the computer check (long paths, Python) - first start, or when it changed
    try:
        from .gui.syscheckdlg import maybe_show
        maybe_show()
    except Exception:                                              # noqa: BLE001
        pass

    # The starting screen, then the main window; "Choose another file" in the
    # main window comes back round to the starting screen.
    while True:
        dialog = SetupDialog()
        if dialog.exec() != QDialog.Accepted:
            if dialog.switch_user:
                users.set_dont_ask(False)         # Switch user: ask again from now on
                if pick_user():
                    continue
            return 0
        source, experiment, settings = dialog.result_tuple
        if source is None or experiment is None:
            return 0
        from .safety import make_dirs
        make_dirs(experiment.out_dir)

        window = MainWindow(source, experiment, settings)
        window.show()
        code = app.exec()
        if not window.go_back:
            return code


if __name__ == "__main__":
    raise SystemExit(main())
