"""
V2.9 computer check: is this computer set up the way PeterPiper needs? Shown once
at the first start on a computer (and again whenever a result changes), and any
time from Help > Computer check... Only reads settings; 1.2: the long-path setting
is changed only when you press 'Turn on Windows long paths' (Windows itself asks
for administrator approval - turn_on_long_paths()).

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
# for the user to run in an administrator PowerShell; 1.2: also run (elevated, after
# Windows' own approval) by 'Turn on Windows long paths' - only on that button
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
        "To turn it on (needs administrator rights; once per computer): press 'Turn on Windows "
        "long paths' (Windows asks for administrator approval), or run the command below in "
        "PowerShell opened with 'Run as administrator'. Without administrator rights, ask your "
        "IT to enable the Group Policy 'Enable Win32 long paths'. Explorer and Excel may still "
        "not open very long paths even then (Excel: a workbook over 218 characters), so keep "
        "data folders and movie names short.",
        LONG_PATH_COMMAND)


# ------------------------------------------------- 1.2: turning long paths on
GROUP_POLICY = ("Computer Configuration > Administrative Templates > System > Filesystem > "
                "'Enable Win32 long paths'")
REGISTRY_VALUE = ("HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\FileSystem\\"
                  "LongPathsEnabled = 1 (DWORD)")
NO_ELEVATE_ENV = "PETERPIPER_NO_ELEVATE"     # set (tests): never ask Windows for elevation
_ERROR_CANCELLED = 1223                      # the user said No to Windows' approval


def run_elevated(command: str, poll=None, timeout_s: float = 300.0) -> int:
    """Run a PowerShell command as administrator: Windows shows its own approval
    (ShellExecuteExW 'runas' with powershell -NoProfile -Command ...). Waits for it
    (poll() is called while waiting, e.g. to keep a window drawn). Returns the exit
    code; raises OSError (winerror 1223 = approval not given)."""
    import os
    if sys.platform != "win32":
        raise OSError("Only on Windows.")
    if os.environ.get(NO_ELEVATE_ENV):
        raise OSError("Asking for administrator rights is switched off here.")
    import ctypes
    import time
    from ctypes import wintypes

    class _Info(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE)]
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_Info)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    info = _Info()
    info.cbSize = ctypes.sizeof(_Info)
    info.fMask = 0x00000040 | 0x00000100          # SEE_MASK_NOCLOSEPROCESS | NOASYNC
    info.lpVerb = "runas"
    info.lpFile = "powershell.exe"
    info.lpParameters = f'-NoProfile -NonInteractive -Command "{command}"'
    info.nShow = 0                                 # SW_HIDE: no console window
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error()
        raise OSError(None, "Windows' administrator approval was not given"
                      if err == _ERROR_CANCELLED else ctypes.FormatError(err), None, err)
    if not info.hProcess:
        return 0
    try:
        end = time.monotonic() + timeout_s
        while kernel32.WaitForSingleObject(info.hProcess, 100) == 0x102:   # WAIT_TIMEOUT
            if poll is not None:
                poll()
            if time.monotonic() > end:
                raise OSError("Windows did not finish the change in time.")
        code = wintypes.DWORD(0)
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return int(code.value)
    finally:
        kernel32.CloseHandle(info.hProcess)


def turn_on_long_paths(elevate=None, read=None, poll=None):
    """'Turn on Windows long paths': runs LONG_PATH_COMMAND as administrator
    (Windows asks for approval), then reads the setting again. elevate(command,
    poll=...) / read() replace run_elevated / long_paths_enabled (tests: fakes -
    the real one is never run there). Returns (on: True / False / None, what
    happened in plain words)."""
    elevate = elevate or run_elevated
    read = read or long_paths_enabled
    if sys.platform != "win32" and elevate is run_elevated:
        return None, "Only Windows has this setting - there is nothing to turn on here."
    if read() is True:
        return True, "Windows' long paths are already on."
    it_text = (f"Without administrator rights, ask your IT to turn on the Group Policy "
               f"setting {GROUP_POLICY} - it sets {REGISTRY_VALUE}.")
    try:
        elevate(LONG_PATH_COMMAND.replace('"', "'") + " | Out-Null", poll=poll)
    except OSError as exc:
        if getattr(exc, "winerror", None) == _ERROR_CANCELLED:
            return False, (f"Not changed: Windows' administrator approval was not given (or "
                           f"this account is not an administrator). {it_text}")
        from .safety import error_text
        return read(), f"Not changed ({error_text(exc)}). {it_text}"
    on = read()
    if on is True:
        return True, ("Windows' long paths are ON now. Programs that support them can use paths "
                      "over 260 characters (some only after you restart Windows). Windows "
                      "Explorer and Excel may STILL not open very long paths - Excel never opens "
                      "a workbook whose full path is over 218 characters - so short folder and "
                      "file names stay the safe choice.")
    return on, (f"Windows' long paths are still off (the change did not take - a policy of "
                f"your organisation may keep it off). {it_text}")


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
