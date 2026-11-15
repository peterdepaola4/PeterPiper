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
from typing import Optional


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


def _install_charlotte(app) -> bool:
    """1.1: the optional hidden extra (gui/charlotte.py); any problem -> left out."""
    try:
        from .gui import charlotte
        charlotte.install(app)
        return True
    except Exception:                                              # noqa: BLE001
        return False


# ------------------------------------------------- the loop between the windows
def request_of(obj) -> Optional[dict]:
    """The hand-over a closed window / start screen left - next_request ('Next
    movie' in the analysis window) or open_request (start screen, Compare):
    {"nd2": path, "run": file or None}; None if there is none."""
    for name in ("next_request", "open_request"):
        req = getattr(obj, name, None)
        if isinstance(req, dict) and req.get("nd2"):
            return {"nd2": str(req["nd2"]), "run": str(req["run"]) if req.get("run") else None}
    return None


def load_run(window, run: str) -> str:
    """Load a saved run into the analysis window (load_run_file when the window
    has it, else the older _load_roi_file). Returns the method used."""
    if hasattr(window, "load_run_file"):
        window.load_run_file(run)
        return "load_run_file"
    window._load_roi_file(run)
    return "_load_roi_file"


def load_run_when_ready(window, run: str, delay_ms: int = 300) -> None:
    """After the window is shown and has finished its own start-up jobs."""
    from PySide6.QtCore import QTimer

    def go() -> None:
        try:
            if not window.isVisible():
                return
            busy = getattr(window, "_busy_now", None)
            if callable(busy) and busy():
                QTimer.singleShot(delay_ms, go)
                return
        except RuntimeError:                       # the window is gone
            return
        load_run(window, run)
    QTimer.singleShot(delay_ms, go)


def run_loop(ui) -> int:
    """
    The start screen, the analysis window, and back - until the user really
    closes. `ui` does the showing (app.py: _QtUI; tests: a fake):
      ui.start(preload)            -> (start screen after it closed, accepted?);
                                      preload None or {"nd2", "note", "run"}
      ui.prepare(nd2)              -> (source, experiment, settings);
                                      raises NeedsCheck or a reading error
      ui.analyse(src, exp, s, run) -> (analysis window after it closed, exit code)
      ui.pick_user()               -> bool (Switch user)
      ui.error(title, text)
    A next_request / open_request opens that movie directly (prepare), loading
    its run; a movie that needs a look opens the start screen with it instead.
    """
    from .gui.setup import NeedsCheck
    pending: Optional[dict] = None     # open this directly
    preload: Optional[dict] = None     # ... or show it on the start screen
    while True:
        if pending is not None:
            req, pending = pending, None
            try:
                src, exp, s = ui.prepare(req["nd2"])
            except NeedsCheck as nc:
                preload = {"nd2": req["nd2"], "note": nc.text, "run": req.get("run")}
                continue
            except Exception as exc:                               # noqa: BLE001
                from .safety import error_text
                ui.error("Could not open the movie",
                         f"{Path(req['nd2']).name} could not be opened.\n\n{error_text(exc)}")
                continue
            run = req.get("run")
        else:
            dialog, accepted = ui.start(preload)
            preload = None
            if not accepted:
                if getattr(dialog, "switch_user", False) and ui.pick_user():
                    continue
                return 0
            req = request_of(dialog)
            if req is not None:
                pending = req
                continue
            src, exp, s = dialog.result_tuple
            if src is None or exp is None:
                return 0
            run = getattr(dialog, "open_run", None)
        window, code = ui.analyse(src, exp, s, run)
        req = request_of(window)
        if req is not None:
            pending = req
        elif not getattr(window, "go_back", False):
            return code


class _QtUI:
    """run_loop's windows, for real."""

    def __init__(self, app, pick_user) -> None:
        self.app, self._pick_user = app, pick_user

    def start(self, preload: Optional[dict]):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDialog
        from .gui.setup import SetupDialog
        p = preload or {}
        d = SetupDialog(preload=p.get("nd2"), note=p.get("note", ""), run=p.get("run"))
        d.setWindowState(d.windowState() | Qt.WindowMaximized)    # 1.1: the whole screen
        return d, d.exec() == QDialog.Accepted

    def prepare(self, nd2: str):
        from .gui.setup import prepare
        return prepare(nd2, None)

    def analyse(self, src, exp, s, run: Optional[str]):
        from .gui.clickwin import ClickWindow as MainWindow
        from .safety import make_dirs
        make_dirs(exp.out_dir)
        window = MainWindow(src, exp, s)
        if run:
            window._offered = True       # this run is loaded, not the 'analysed before' list
        window.show()
        if run:
            load_run_when_ready(window, run)
        return window, self.app.exec()

    def pick_user(self) -> bool:
        from . import users
        users.set_dont_ask(False)         # Switch user: ask again from now on
        return self._pick_user()

    def error(self, title: str, text: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(None, title, text)


def main() -> int:
    from PySide6.QtWidgets import QApplication, QDialog

    from . import APP_NAME, __version__

    # PeterPiper 1.0: the taskbar shows PeterPiper's own icon, not Python's
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PeterPiper.App")
        except Exception:                                          # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    _install_charlotte(app)                       # 1.1: optional, guarded
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

    # The start screen, then the analysis window; "Choose another file" there
    # comes back round to the start screen, "Next movie" (the queue) and "Open"
    # on a run (start screen, Compare) open that movie directly.
    return run_loop(_QtUI(app, pick_user))


if __name__ == "__main__":
    raise SystemExit(main())
