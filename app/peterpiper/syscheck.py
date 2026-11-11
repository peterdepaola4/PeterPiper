"""
V2.9 computer check: is this computer set up the way PeterPiper needs? Shown once
at the first start on a computer (and again whenever a result changes), and any
time from Help > Computer check... Only reads settings - never changes them.

1. Long file paths: Windows' 'Enable Win32 long paths' (registry value
   HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem\\LongPathsEnabled = 1).
   PeterPiper itself reads and writes paths longer than 260 characters, but with
   the setting off, Windows Explorer, Excel and other programs may not open
   results deep in a folder tree (OUTPUT_<movie>\\<user>\\Export_...\\...).
2. Python: the version running PeterPiper (64-bit Python 3.11 - 3.14 are tested).
"""
from __future__ import annotations

import json
import platform
import struct
import sys
from dataclasses import asdict, dataclass
from datetime import date
from typing import List, Optional

STATE_FILE = "computer_check.json"
LONG_PATH_KEY = r"SYSTEM\CurrentControlSet\Control\FileSystem"
# for the user to run in an administrator PowerShell (PeterPiper never runs it)
LONG_PATH_COMMAND = ('New-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem" '
                     '-Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force')
PY_MIN, PY_MAX = (3, 11), (3, 14)


@dataclass
class Item:
    key: str
    title: str
    status: str            # "ok" | "warn" | "bad" | "unknown"
    found: str             # what was found
    advice: str = ""       # what to do ("" = nothing)
    command: str = ""      # a command the user may copy and run themselves


def long_paths_enabled() -> Optional[bool]:
    """Windows' long-path setting: True / False, None when it cannot be read
    (not Windows, or no permission)."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, LONG_PATH_KEY) as k:
            v, _t = winreg.QueryValueEx(k, "LongPathsEnabled")
        return int(v) == 1
    except FileNotFoundError:
        return False                  # value never set = off (the Windows default)
    except OSError:
        return None


def check_long_paths() -> Item:
    on = long_paths_enabled()
    title = "Long file paths (Windows setting)"
    if on is True:
        return Item("long_paths", title, "ok", "On - long folder paths work everywhere.")
    if on is None:
        return Item("long_paths", title, "unknown", "Could not be read on this computer.",
                    "If results deep in a folder tree do not open in Explorer or Excel, ask "
                    "your IT to turn on 'Enable Win32 long paths'.")
    return Item(
        "long_paths", title, "warn",
        "Off (the Windows default). PeterPiper itself handles long paths, but Windows Explorer, "
        "Excel and other programs may fail to open results whose full path is longer than 260 "
        "characters (deep folders, long movie names).",
        "To turn it on (needs administrator rights; once per computer): run the command below "
        "in PowerShell opened with 'Run as administrator', then restart Windows. Or ask your IT "
        "to enable the Group Policy 'Enable Win32 long paths'. Until then, keep data folders "
        "and movie names short.",
        LONG_PATH_COMMAND)


def check_python() -> Item:
    v = sys.version_info
    bits = struct.calcsize("P") * 8
    found = f"Python {v.major}.{v.minor}.{v.micro}, {bits}-bit ({platform.python_implementation()})"
    title = "Python"
    if bits != 64:
        return Item("python", title, "bad", found,
                    "PeterPiper needs 64-bit Python: install 64-bit Python 3.13 from python.org, "
                    "then start PeterPiper again (it reinstalls its packages).")
    if (v.major, v.minor) < PY_MIN:
        return Item("python", title, "bad", found,
                    "Too old: install 64-bit Python 3.13 (or 3.12 / 3.11) from python.org.")
    if (v.major, v.minor) > PY_MAX:
        return Item("python", title, "warn", found,
                    "Newer than the versions PeterPiper was tested with (3.11 - 3.14). It should "
                    "work; if anything fails, install Python 3.13 and start PeterPiper again.")
    return Item("python", title, "ok", found + " - a tested version.")


def check_bundled() -> Item:
    """The Mac / Windows app carries its own Python and packages."""
    v = sys.version_info
    return Item("python", "Python", "ok",
                f"Built into the app (Python {v.major}.{v.minor}.{v.micro}, with the tested "
                f"package versions) - nothing to install.")


def run_checks() -> List[Item]:
    items = []
    if sys.platform == "win32":                    # a Windows setting (macOS has no such limit)
        items.append(check_long_paths())
    items.append(check_bundled() if getattr(sys, "frozen", False) else check_python())
    return items


# ------------------------------------------------------------ when to show it
def _state_path():
    from .users import base_dir
    return base_dir() / STATE_FILE


def _load_state() -> dict:
    try:
        d = json.loads(_state_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def should_show(items: List[Item]) -> bool:
    """At the first start on this computer, and whenever a result changed since
    (e.g. Python updated, the long-path setting turned off)."""
    st = _load_state()
    if not st:
        return True
    if not st.get("show_on_change", True):
        return False
    return st.get("results") != {i.key: i.status for i in items}


def remember(items: List[Item], show_on_change: bool = True) -> None:
    try:
        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(dict(checked=date.today().isoformat(),
                                     results={i.key: i.status for i in items},
                                     found={i.key: i.found for i in items},
                                     show_on_change=bool(show_on_change)), indent=1),
                     encoding="utf-8")
    except OSError:
        pass


def as_dicts(items: List[Item]) -> List[dict]:
    return [asdict(i) for i in items]
