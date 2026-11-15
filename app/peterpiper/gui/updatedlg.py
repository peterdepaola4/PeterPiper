"""
"Check for updates" (PeterPiper 1.1): asks GitHub for the newest release - only
when pressed - and offers to update (see updater.py for exactly what is sent and
what is changed; your data is never touched).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from .. import __version__
from .. import updater as U
from ..safety import error_text
from . import widgets as W


def check_for_updates(parent=None) -> str:
    """Returns what happened: 'newest' | 'updated' | 'unpacked' | 'downloaded' |
    'later' | 'error' | 'developer'."""
    kind = U.kind_of_install()
    try:
        rel = W.run_with_progress(parent, "Asking GitHub for the newest version...",
                                  lambda progress: U.fetch_latest(), delay_ms=300)
    except Exception as exc:                                       # noqa: BLE001
        QMessageBox.warning(parent, "Check for updates",
                            "Could not reach GitHub (no internet, or it is blocked here).\n\n"
                            f"{error_text(exc)}")
        return "error"
    if not U.is_newer(rel["version"]):
        QMessageBox.information(parent, "Check for updates",
                                f"You have the newest version ({__version__}).")
        return "newest"
    notes = rel["notes"].strip()
    notes = (notes[:1500] + " ...") if len(notes) > 1500 else notes
    box = QMessageBox(parent)
    box.setWindowTitle("Check for updates")
    box.setText(f"PeterPiper {rel['version']} is available (you have {__version__}).")
    box.setInformativeText("Your profiles, settings, saved runs, logs and results are never "
                           "touched by an update.")
    box.setDetailedText(notes or "See the release page.")
    if kind == "developer":
        box.setInformativeText("This is a developer copy (a git folder): update it with git.")
        b_up = None
    else:
        b_up = box.addButton("Update now" if kind == "zip" else "Download", QMessageBox.AcceptRole)
    b_page = box.addButton("Open the release page", QMessageBox.ActionRole)
    box.addButton("Later", QMessageBox.RejectRole)
    box.exec()
    hit = box.clickedButton()
    if hit is b_page:
        W.open_path(rel["url"])
        return "later"
    if b_up is None or hit is not b_up:
        return "developer" if kind == "developer" else "later"
    asset = U.pick_asset(rel, kind)
    if asset is None:
        QMessageBox.information(parent, "Check for updates",
                                "This release has no file for this computer yet - try again "
                                "in a few minutes, or use the release page.")
        W.open_path(rel["url"])
        return "later"
    try:
        if kind == "mac_app":
            return _mac(parent, asset)
        return _windows(parent, asset)
    except Exception as exc:                                       # noqa: BLE001
        QMessageBox.warning(parent, "Check for updates",
                            f"The update did not finish; nothing of yours was changed.\n\n"
                            f"{error_text(exc)}")
        return "error"


def _mac(parent, asset) -> str:
    from ..safety import new_output_file
    dl = Path.home() / "Downloads"
    dl.mkdir(exist_ok=True)
    with new_output_file(dl / asset["name"]) as (used, stream):
        stream.close()
        W.run_with_progress(parent, "Downloading the new PeterPiper...",
                            lambda progress: U.download(asset["url"], Path(used), asset["size"],
                                                        progress), delay_ms=0)
    W.open_path(str(used))
    QMessageBox.information(parent, "Check for updates",
                            "The new PeterPiper is open in Finder: drag it onto Applications "
                            "and replace the old one, then start it again. Your data stays.")
    return "downloaded"


def _windows(parent, asset) -> str:
    folder = U.program_folder()
    tmpdir = Path(tempfile.mkdtemp(prefix="pp-update-"))
    z = tmpdir / asset["name"]
    W.run_with_progress(parent, "Downloading the new PeterPiper...",
                        lambda progress: U.download(asset["url"], z, asset["size"], progress),
                        delay_ms=0)
    p = U.plan(z, folder)
    if p["mode"] == "in_place":
        n = len(p["changed"]) + len(p["new"])
        if QMessageBox.question(
                parent, "Check for updates",
                f"{n} program file(s) will be replaced or added (the old ones are kept in "
                f"_update_backup). Then restart PeterPiper. Go ahead?") != QMessageBox.Yes:
            return "later"
        r = U.apply_in_place(z, folder, p)
        QMessageBox.information(parent, "Check for updates",
                                f"Updated {len(r['replaced'])} file(s). Close PeterPiper and "
                                "start it again to use the new version.")
        return "updated"
    dest = U.unpack_new_folder(z, folder)
    QMessageBox.information(
        parent, "Check for updates",
        f"The new version is a separate install ({p['why']}), so it was unpacked next to "
        f"this one:\n{dest}\n\nStart it with the .bat in that folder (the first start installs "
        "its packages, about 5 minutes). Your users and runs are shared; this version stays "
        "as it is.")
    W.open_path(str(dest))
    return "unpacked"
