"""
PeterPiper 4.0: the ONE place where Windows, macOS (and Linux) differ.

Everything else in PeterPiper is the same code on every system; whatever has to
be done differently goes through a function here. Python's own library only
(no package, no Qt), so the launchers can run it as a script before anything is
installed:

    python app/peterpiper/platforms.py shortcuts <launcher> [--no-desktop]
        (macOS: ~/Applications/PeterPiper.app + a Desktop alias; prints what it made)

The system
    IS_WIN / IS_MAC / IS_LINUX, SYSTEM ("windows" | "mac" | "linux"),
    system()                 the same, honouring TEST_HOOKS["system"] (tests)
    set_windows_app_id()     Windows: the taskbar shows PeterPiper's icon
Files and folders
    open_path(path)          open a file / folder / web link with its own program
    reveal_in_file_manager(path)   show it selected in Explorer / Finder
    file_manager_name()      "Explorer" | "Finder" | "the file manager"
    trash_name()             "Recycle Bin" | "Trash"
    move_to_trash(path)      -> "" when done, else the reason (never deletes for good)
    has_recycle_bin(path)    Windows: False on network drives
    home_dir(), desktop_dir(), app_data_dir(), logs_dir(), install_home(app_name)
Long paths (Windows only; nothing to do elsewhere)
    long_path(path) / plain_path(path), long_paths_enabled() -> True / False / None
Shortcuts
    make_shortcuts(launcher, ...)  Windows: PeterPiper.lnk (folder, Desktop, Start
                             menu); macOS: ~/Applications/PeterPiper.app (Spotlight,
                             Launchpad) + a Desktop alias
    write_windows_shortcut(lnk, target, icon, description)
    write_mac_app(apps_dir, launcher, icns, version)   the small wrapper app
Cloud folders (Box Drive, OneDrive, Google Drive, Dropbox, iCloud Drive)
    cloud_roots()            -> [(service, path)] that exist on this computer
    is_online_only(path)     the file's data is only online (opening downloads it)
Keys
    key_text("Ctrl+Z")       "Cmd+Z" on a Mac (Qt itself maps Ctrl to Cmd there)

Tests: TEST_HOOKS["system"] = "win32" / "darwin" / "linux" makes the functions
that take no explicit `system=` behave as on that system (paths only - nothing
of the other system is ever run). Functions that look at the computer take
their places as arguments (home=, env=, drives=, stat=) so tests can fake them.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

TEST_HOOKS: Dict[str, object] = {}

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
SYSTEM = "windows" if IS_WIN else "mac" if IS_MAC else "linux"

# Windows file attributes of a file whose data is only online (cloud placeholder)
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
ONLINE_ONLY_ATTRS = (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_RECALL_ON_OPEN
                     | FILE_ATTRIBUTE_OFFLINE)
# macOS: a file whose data is not on this Mac (iCloud, File Provider apps), in st_flags
SF_DATALESS = 0x40000000

LONG_PATH_KEY = r"SYSTEM\CurrentControlSet\Control\FileSystem"
APP_LABEL = "PeterPiper"
# the Mac wrapper app's own Info.plist key: marks a PeterPiper.app as made by the launcher
MAC_MARK = "PeterPiperLauncher"
MAC_BUNDLE_ID = "io.github.peterdepaola4.peterpiper.launcher"
SERVICES = ("Box", "OneDrive", "Google Drive", "Dropbox", "iCloud Drive")


# ------------------------------------------------------------------ the system
def system() -> str:
    """sys.platform, or what a test set (TEST_HOOKS["system"])."""
    return str(TEST_HOOKS.get("system") or sys.platform)


def _win(sysn: Optional[str] = None) -> bool:
    return (sysn or system()).startswith("win")


def _mac(sysn: Optional[str] = None) -> bool:
    return (sysn or system()) == "darwin"


def file_manager_name(sysn: Optional[str] = None) -> str:
    return "Explorer" if _win(sysn) else "Finder" if _mac(sysn) else "the file manager"


def trash_name(sysn: Optional[str] = None) -> str:
    return "Recycle Bin" if _win(sysn) else "Trash"


def key_text(keys: str, sysn: Optional[str] = None) -> str:
    """A shortcut as the user types it: 'Ctrl+Z' -> 'Cmd+Z' on a Mac (Qt turns a
    "Ctrl+" shortcut into Cmd there by itself; only the words need changing)."""
    if not _mac(sysn):
        return keys
    return keys.replace("Ctrl+", "Cmd+").replace("Alt+", "Option+")


# ------------------------------------------------------------------ places
def home_dir() -> Path:
    return Path.home()


def desktop_dir(sysn: Optional[str] = None) -> Optional[Path]:
    """The user's Desktop (Windows: the real one, also when OneDrive moved it)."""
    if _win(sysn) and IS_WIN:
        p = _special_folder(0x10)                           # CSIDL_DESKTOPDIRECTORY
        if p:
            return p
    d = Path.home() / "Desktop"
    return d if d.is_dir() else None


def start_menu_dir() -> Optional[Path]:
    """Windows: the user's Start-menu Programs folder (None elsewhere)."""
    return _special_folder(0x02) if IS_WIN else None        # CSIDL_PROGRAMS


def app_data_dir(name: str = APP_LABEL, sysn: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None, home: Optional[Path] = None) -> Path:
    """Where a program keeps its own (not the user's) files: Windows
    %LOCALAPPDATA%\\<name>, macOS ~/Library/Application Support/<name>, Linux
    $XDG_DATA_HOME/<name> (~/.local/share/<name>)."""
    env = os.environ if env is None else env
    home = Path(home) if home is not None else Path.home()
    if _win(sysn):
        base = env.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / name
    if _mac(sysn):
        return home / "Library" / "Application Support" / name
    base = env.get("XDG_DATA_HOME")
    return (Path(base) if base else home / ".local" / "share") / name


def logs_dir(sysn: Optional[str] = None, home: Optional[Path] = None) -> Path:
    """Where a crash log of the packaged app goes: macOS ~/Library/Logs/PeterPiper,
    elsewhere <home>/PeterPiper data/logs."""
    home = Path(home) if home is not None else Path.home()
    if _mac(sysn):
        return home / "Library" / "Logs" / APP_LABEL
    return home / "PeterPiper data" / "logs"


def install_home(app_name: str, env: Optional[Dict[str, str]] = None,
                 home: Optional[Path] = None) -> Path:
    """The launcher's install folder: $PETERPIPER_HOME, else ~/.<app_name>
    (%USERPROFILE%\\.PeterPiperV4.0 on Windows, ~/.PeterPiperV4.0 on a Mac)."""
    env = os.environ if env is None else env
    if env.get("PETERPIPER_HOME"):
        return Path(env["PETERPIPER_HOME"])
    return (Path(home) if home is not None else Path.home()) / f".{app_name}"


def venv_python(venv: Path, windowed: bool = False, sysn: Optional[str] = None) -> Path:
    """The Python inside a private Python folder (venv)."""
    if _win(sysn):
        return Path(venv) / "Scripts" / ("pythonw.exe" if windowed else "python.exe")
    return Path(venv) / "bin" / "python"


def _special_folder(csidl: int) -> Optional[Path]:
    """A Windows known folder (Desktop 0x10, Start-menu Programs 0x02 ...)."""
    if not IS_WIN:
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    except Exception:                                              # noqa: BLE001
        pass
    return None


def set_windows_app_id(app_id: str = "PeterPiper.App") -> None:
    """Windows: the taskbar shows PeterPiper's own icon (not Python's) - call
    before the first window. Nothing to do elsewhere."""
    if not IS_WIN:
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:                                              # noqa: BLE001
        pass


# ------------------------------------------------------------------ opening
def _popen(args: List[str]) -> bool:
    try:
        subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,  # noqa: S603
                         stderr=subprocess.DEVNULL, close_fds=True)
        return True
    except OSError:
        return False


def open_path(path) -> bool:
    """Open a file or folder with its own program (Explorer / Finder, Excel,
    GraphPad Prism ...) or a web link in the browser. False if that failed."""
    p = str(path)
    if IS_WIN:
        try:
            os.startfile(plain_path(p))                            # noqa: S606
            return True
        except OSError:
            return False
    if IS_MAC:
        return _popen(["/usr/bin/open", p])
    return _popen(["xdg-open", p])


def reveal_in_file_manager(path) -> bool:
    """Show a file selected in its folder (Explorer / Finder); a folder is opened."""
    p = plain_path(str(path))
    if os.path.isdir(p):
        return open_path(p)
    if IS_WIN:
        return _popen(["explorer", "/select,", os.path.normpath(p)])
    if IS_MAC:
        return _popen(["/usr/bin/open", "-R", p])
    return open_path(os.path.dirname(p) or ".")


# ------------------------------------------------------------------ long paths
_LONG = "\\\\?\\"                 # \\?\C:\...
_LONG_UNC = "\\\\?\\UNC\\"        # \\?\UNC\server\share\...


def long_path(path) -> str:
    """Windows: the path in the extended-length form (\\\\?\\C:\\... or
    \\\\?\\UNC\\server\\share\\...), absolute and normalised, so it works past 260
    characters. Unchanged on other systems (they have no such limit), for '' and
    for paths already in that form."""
    s = os.fspath(path) if not isinstance(path, str) else path
    if os.name != "nt" or not s or s.startswith(_LONG) or s.startswith("\\\\.\\"):
        return s
    s = os.path.abspath(s)
    if s.startswith("\\\\"):                           # network share
        return _LONG_UNC + s[2:]
    return _LONG + s


def plain_path(path) -> str:
    """The normal form of a path (for messages, lists and the run index)."""
    s = os.fspath(path) if not isinstance(path, str) else path
    if s.startswith(_LONG_UNC):
        return "\\\\" + s[len(_LONG_UNC):]
    if s.startswith(_LONG):
        return s[len(_LONG):]
    return s


def long_paths_enabled() -> Optional[bool]:
    """Windows' long-path setting: True / False, None when it cannot be read
    (not Windows, or no permission). Only reads."""
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


# ------------------------------------------------------------------ the Recycle Bin / Trash
def has_recycle_bin(path) -> bool:
    """Windows: the drive of `path` has a Recycle Bin (network drives do not).
    Always True elsewhere (the Trash)."""
    if not IS_WIN:
        return True
    try:
        import ctypes
        from ctypes import wintypes

        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_int64),
                        ("i64NumItems", ctypes.c_int64)]
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(info)
        root = os.path.splitdrive(os.path.abspath(str(path)))[0] + "\\"
        if root.startswith("\\\\"):
            return False                                   # \\server\share: no Recycle Bin
        return ctypes.windll.shell32.SHQueryRecycleBinW(root, ctypes.byref(info)) == 0
    except Exception:                                              # noqa: BLE001
        return False


def _trash_windows(path: Path) -> str:
    if not has_recycle_bin(path):
        return f"the drive of {path} has no Recycle Bin"
    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", wintypes.WORD), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p),
                        ("lpszProgressTitle", wintypes.LPCWSTR)]
        FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION = 3, 0x4, 0x10
        FOF_ALLOWUNDO, FOF_NOERRORUI, FOF_WANTNUKEWARNING = 0x40, 0x400, 0x4000
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = os.path.abspath(str(path)) + "\0"    # list ends with two nulls
        op.fFlags = (FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
                     | FOF_WANTNUKEWARNING)
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        except Exception:                                          # noqa: BLE001
            pass
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    except Exception as exc:                                       # noqa: BLE001
        return f"Windows could not move it ({exc})"
    if op.fAnyOperationsAborted:
        return "it was stopped (nothing more was moved)"
    if rc != 0:
        return f"Windows could not move it (code {rc:#x}) - is a file in it open?"
    return "" if not path.exists() else "part of it could not be moved (a file in use?)"


def _trash_mac_native(path: Path) -> Optional[bool]:
    """macOS' own 'Move to Trash' (NSFileManager trashItemAtURL - Finder's 'Put
    Back' works), through the Objective-C runtime with ctypes: no extra package,
    no permission prompt. None when the runtime cannot be used."""
    try:
        import ctypes
        import ctypes.util
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "/usr/lib/libobjc.dylib")
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation")
                                or "/System/Library/Frameworks/Foundation.framework/Foundation")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send_addr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value

        def send(obj, sel: bytes, *args, argtypes=(), restype=ctypes.c_void_p):
            fn = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(send_addr)
            return fn(obj, objc.sel_registerName(sel), *args)
        pool = send(send(objc.objc_getClass(b"NSAutoreleasePool"), b"alloc"), b"init")
        try:
            s = send(objc.objc_getClass(b"NSString"), b"stringWithUTF8String:",
                     os.fsencode(str(path)), argtypes=(ctypes.c_char_p,))
            url = send(objc.objc_getClass(b"NSURL"), b"fileURLWithPath:", s,
                       argtypes=(ctypes.c_void_p,))
            fm = send(objc.objc_getClass(b"NSFileManager"), b"defaultManager")
            done = send(fm, b"trashItemAtURL:resultingItemURL:error:", url, None, None,
                        argtypes=(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
                        restype=ctypes.c_bool)
        finally:
            send(pool, b"drain")
        return bool(done)
    except Exception:                                              # noqa: BLE001
        return None


def _trash_folder(sysn: str, home: Path) -> Path:
    if _mac(sysn):
        return home / ".Trash"
    return home / ".local" / "share" / "Trash" / "files"


def move_to_trash(path, sysn: Optional[str] = None, home: Optional[Path] = None,
                  native: Optional[Callable[[Path], Optional[bool]]] = None) -> str:
    """Move a file or folder to the Recycle Bin (Windows) or the Trash (macOS,
    Linux), so it can be restored. '' when done, else the reason. Never deletes
    for good: a Windows drive without a Recycle Bin is refused, and Windows asks
    before anything too large for the Recycle Bin would be deleted."""
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return ""
    sysn = sysn or system()
    if _win(sysn):
        if not IS_WIN:
            return "only Windows has a Recycle Bin"
        return _trash_windows(path)
    if _mac(sysn) and IS_MAC and native is None:
        native = _trash_mac_native
    if native is not None:
        r = native(path)
        if r is True and not path.exists():
            return ""
    # the user's Trash folder (Linux; a Mac whose own 'Move to Trash' was not usable)
    trash = _trash_folder(sysn, Path(home) if home is not None else Path.home())
    try:
        trash.mkdir(parents=True, exist_ok=True)
        dst, i = trash / path.name, 2
        while dst.exists() or dst.is_symlink():
            dst, i = trash / f"{path.name} {i}", i + 1
        shutil.move(str(path), str(dst))
        return ""
    except OSError as exc:
        return f"it could not be moved to the {trash_name(sysn)} ({exc})"


# ------------------------------------------------------------------ shortcuts
def write_windows_shortcut(lnk: Path, target: Path, icon: Optional[Path],
                           description: str) -> bool:
    """(Re)write a Windows shortcut (.lnk) through WScript.Shell, paths passed as
    environment variables (never as code). False on any problem; 30 s at most."""
    if not IS_WIN:
        return False
    env = dict(os.environ, PP_LNK=str(lnk), PP_BAT=str(target), PP_DIR=str(Path(target).parent),
               PP_ICO=(str(icon) + ",0") if icon and Path(icon).exists() else "",
               PP_DESC=description)
    cmd = ("$w=New-Object -ComObject WScript.Shell; $l=$w.CreateShortcut($env:PP_LNK); "
           "$l.TargetPath=$env:PP_BAT; $l.WorkingDirectory=$env:PP_DIR; "
           "if($env:PP_ICO){$l.IconLocation=$env:PP_ICO}; $l.Description=$env:PP_DESC; $l.Save()")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def mac_app_script(launcher: Path) -> str:
    """The wrapper app's start script: runs the launcher (.command) without a
    Terminal window; the launcher opens one itself when it has something to say
    (first install, a problem). If the PeterPiper folder was moved, it says so."""
    name = Path(launcher).name
    return (
        "#!/bin/bash\n"
        "# PeterPiper: starts the PeterPiper launcher below. Made by that launcher\n"
        "# (made again whenever the PeterPiper folder moves). Safe to delete.\n"
        f"L={_sh_quote(str(launcher))}\n"
        'if [ ! -f "$L" ]; then\n'
        "  /usr/bin/osascript -e 'display alert \"PeterPiper cannot be found\" message "
        f"\"The PeterPiper folder was moved or deleted. Open the PeterPiper folder and "
        f"double-click {name} once: it makes this app again.\"' >/dev/null 2>&1\n"
        "  exit 1\n"
        "fi\n"
        "export PETERPIPER_FROM_APP=1\n"
        'exec /bin/bash "$L"\n')


def is_our_mac_app(app: Path) -> bool:
    """A PeterPiper.app made by the launcher (its Info.plist carries MAC_MARK)."""
    try:
        with open(Path(app) / "Contents" / "Info.plist", "rb") as fh:
            return MAC_MARK in plistlib.load(fh)
    except Exception:                                              # noqa: BLE001
        return False


def mac_app_version(app: Path) -> str:
    """CFBundleShortVersionString of a .app ('' when unreadable)."""
    try:
        with open(Path(app) / "Contents" / "Info.plist", "rb") as fh:
            return str(plistlib.load(fh).get("CFBundleShortVersionString") or "")
    except Exception:                                              # noqa: BLE001
        return ""


def write_mac_app(apps_dir: Path, launcher: Path, icns: Optional[Path] = None,
                  version: str = "", name: str = APP_LABEL) -> Optional[Path]:
    """Make (or update) <apps_dir>/<name>.app: a tiny app (Info.plist, a start
    script, the icon) that starts the launcher - so PeterPiper is in Spotlight,
    Launchpad and can be kept in the Dock. Plain files only, so it can be made
    (and tested) anywhere. Never replaces a <name>.app it did not make itself:
    then None."""
    app = Path(apps_dir) / f"{name}.app"
    if (app.exists() or app.is_symlink()) and not is_our_mac_app(app):
        return None
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(parents=True, exist_ok=True)
    info = {
        "CFBundleName": name, "CFBundleDisplayName": name,
        "CFBundleIdentifier": MAC_BUNDLE_ID, "CFBundleExecutable": name,
        "CFBundlePackageType": "APPL", "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleShortVersionString": version or "1.0", "CFBundleVersion": version or "1.0",
        "LSMinimumSystemVersion": "11.0", "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.education",
        MAC_MARK: str(launcher),
    }
    if icns is not None and Path(icns).is_file():
        shutil.copyfile(icns, contents / "Resources" / f"{name}.icns")
        info["CFBundleIconFile"] = name
    with open(contents / "Info.plist", "wb") as fh:
        plistlib.dump(info, fh)
    exe = contents / "MacOS" / name
    with open(exe, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mac_app_script(Path(launcher)))
    os.chmod(exe, 0o755)
    try:
        os.utime(app, None)                         # Finder looks at the icon again
    except OSError:
        pass
    return app


def make_shortcuts(launcher: Path, icon: Optional[Path] = None, version: str = "",
                   desktop: bool = True, menu: bool = True, folder: bool = True,
                   sysn: Optional[str] = None, home: Optional[Path] = None,
                   writer: Optional[Callable[..., bool]] = None) -> List[Path]:
    """PeterPiper shortcuts that start `launcher`; returns what was made.
    Windows: PeterPiper.lnk next to the launcher (folder), on the Desktop and in
    the Start menu (menu); icon = the .ico. macOS: ~/Applications/PeterPiper.app
    (menu: Spotlight, Launchpad) and a Desktop alias to it (desktop); icon = the
    .icns. Linux: nothing."""
    sysn = sysn or system()
    launcher = Path(launcher)
    made: List[Path] = []
    if _win(sysn):
        writer = writer or write_windows_shortcut
        dirs = ([launcher.parent] if folder else []) + \
               ([desktop_dir(sysn)] if desktop else []) + ([start_menu_dir()] if menu else [])
        for d in dirs:
            if d is None:
                continue
            lnk = Path(d) / f"{APP_LABEL}.lnk"
            if writer(lnk, launcher, icon,
                      f"{APP_LABEL} {version} - single-cell fluorescence time courses".replace(
                          "  ", " ")):
                made.append(lnk)
        return made
    if not _mac(sysn):
        return made
    home = Path(home) if home is not None else Path.home()
    app = None
    if menu or desktop:
        app = write_mac_app(home / "Applications", launcher, icon, version)
        if app is not None:
            made.append(app)
            if IS_MAC:                                   # tell Launch Services (quietly)
                lsr = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                       "LaunchServices.framework/Support/lsregister")
                if os.path.exists(lsr):
                    try:
                        subprocess.run([lsr, "-f", str(app)], capture_output=True, timeout=20)
                    except (OSError, subprocess.SubprocessError):
                        pass
    if desktop and app is not None:
        alias = home / "Desktop" / APP_LABEL
        try:
            if alias.is_symlink():
                if os.readlink(alias) != str(app):
                    alias.unlink()
            if not alias.exists() and not alias.is_symlink() and alias.parent.is_dir():
                os.symlink(str(app), str(alias))
            if alias.is_symlink():
                made.append(alias)
        except OSError:
            pass
    return made


# ------------------------------------------------------------------ cloud folders
def _isdir(p) -> bool:
    try:
        return bool(p) and os.path.isdir(p)
    except (OSError, ValueError):
        return False


def _subdirs(p) -> List[str]:
    try:
        with os.scandir(p) as it:
            return sorted(e.name for e in it if not e.name.startswith(".") and e.is_dir())
    except (OSError, ValueError):
        return []


def _win_fixed_drives() -> List[str]:
    """Local drive roots (C:\\ ...): no network drives, no card readers (so no
    'insert a disk' box and nothing that can hang)."""
    if not IS_WIN:
        return []
    out = []
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        old = k32.SetErrorMode(0x0001 | 0x8000)
        try:
            mask = k32.GetLogicalDrives()
            for i in range(26):
                root = f"{chr(65 + i)}:\\"
                if mask & (1 << i) and k32.GetDriveTypeW(root) == 3:      # DRIVE_FIXED
                    out.append(root)
        finally:
            k32.SetErrorMode(old)
    except Exception:                                              # noqa: BLE001
        pass
    return out


def _google_parts(root: Path) -> List[Path]:
    """A Google Drive folder: 'My Drive' and 'Shared drives' when there."""
    return [p for p in (root / "My Drive", root / "Shared drives") if _isdir(p)]


def cloud_roots(sysn: Optional[str] = None, home: Optional[Path] = None,
                env: Optional[Dict[str, str]] = None,
                drives: Optional[Iterable[str]] = None) -> List[Tuple[str, str]]:
    """The folders that Box Drive, OneDrive, Google Drive, Dropbox and iCloud
    Drive keep in step with the cloud on this computer: [(service, path)], only
    folders that exist, no duplicates, in that service order. Fast: a few folder
    checks, nothing is searched, no network.

    Windows: %USERPROFILE%\\Box (Box Drive) and Box Sync; the OneDrive variables
    (OneDrive, OneDriveCommercial, OneDriveConsumer) and %USERPROFILE%\\OneDrive*;
    Google Drive's drive (G:\\My Drive ...; local drives only) or
    %USERPROFILE%\\My Drive / Google Drive; %USERPROFILE%\\Dropbox* (and Dropbox's
    info.json); %USERPROFILE%\\iCloudDrive.
    macOS: ~/Library/CloudStorage/Box-Box, OneDrive-*, GoogleDrive-*/My Drive,
    Dropbox*; the older ~/Box, ~/Dropbox, ~/Google Drive, /Volumes/GoogleDrive;
    iCloud Drive ~/Library/Mobile Documents/com~apple~CloudDocs."""
    sysn = sysn or system()
    env = dict(os.environ) if env is None else dict(env)
    home = Path(home) if home is not None else Path.home()
    found: Dict[str, List[Path]] = {s: [] for s in SERVICES}

    def add(service: str, p) -> None:
        if p and _isdir(p):
            found[service].append(Path(p))

    if _win(sysn):
        add("Box", home / "Box")
        add("Box", home / "Box Sync")
        for var in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive"):
            add("OneDrive", env.get(var))
        for n in _subdirs(home):
            if n == "OneDrive" or n.startswith("OneDrive - ") or n.startswith("OneDrive-"):
                add("OneDrive", home / n)
        for root in (drives if drives is not None else _win_fixed_drives()):
            for part in _google_parts(Path(root)):
                add("Google Drive", part)
        for p in (home / "My Drive", home / "Google Drive"):
            add("Google Drive", p)
        for n in _subdirs(home):
            if n.startswith("Dropbox"):
                add("Dropbox", home / n)
        for var in ("LOCALAPPDATA", "APPDATA"):
            if env.get(var):
                for p in _dropbox_info(Path(env[var]) / "Dropbox" / "info.json"):
                    add("Dropbox", p)
        add("iCloud Drive", home / "iCloudDrive")
    elif _mac(sysn):
        cs = home / "Library" / "CloudStorage"
        for n in _subdirs(cs):
            low = n.lower()
            if low.startswith("box"):
                add("Box", cs / n)
            elif low.startswith("onedrive"):
                add("OneDrive", cs / n)
            elif low.startswith("googledrive"):
                parts = _google_parts(cs / n)
                for part in parts or [cs / n]:
                    add("Google Drive", part)
            elif low.startswith("dropbox"):
                add("Dropbox", cs / n)
            elif low.startswith("icloud"):
                add("iCloud Drive", cs / n)
        add("Box", home / "Box")
        for n in _subdirs(home):
            if n.startswith("OneDrive"):
                add("OneDrive", home / n)
            elif n.startswith("Dropbox"):
                add("Dropbox", home / n)
        for part in _google_parts(home / "Google Drive") or [home / "Google Drive"]:
            add("Google Drive", part)
        if drives is None:
            for part in _google_parts(Path("/Volumes/GoogleDrive")):
                add("Google Drive", part)
        for p in _dropbox_info(home / ".dropbox" / "info.json"):
            add("Dropbox", p)
        add("iCloud Drive", home / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    else:
        for n, svc in (("Dropbox", "Dropbox"), ("OneDrive", "OneDrive"), ("Box", "Box"),
                       ("Google Drive", "Google Drive")):
            add(svc, home / n)
        for p in _dropbox_info(home / ".dropbox" / "info.json"):
            add("Dropbox", p)

    out: List[Tuple[str, str]] = []
    seen = set()
    for svc in SERVICES:
        for p in found[svc]:
            k = os.path.normcase(os.path.normpath(str(p))).rstrip("\\/")
            if k in seen:
                continue
            seen.add(k)
            out.append((svc, str(p)))
    return out


def _dropbox_info(path: Path) -> List[str]:
    """The folders Dropbox's own info.json names (personal, business)."""
    import json
    try:
        info = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(info, dict):
        return []
    return [str(d["path"]) for d in (info.get("personal"), info.get("business"))
            if isinstance(d, dict) and d.get("path")]


def is_online_only(path, sysn: Optional[str] = None,
                   stat: Optional[Callable[[str], os.stat_result]] = None) -> bool:
    """True when the file's data is not on this computer (a OneDrive / Google
    Drive / Box / Dropbox / iCloud placeholder): reading it downloads it first.
    Only the file's attributes are read - nothing is downloaded. Windows:
    RECALL_ON_DATA_ACCESS / RECALL_ON_OPEN / OFFLINE in st_file_attributes;
    macOS: SF_DATALESS in st_flags."""
    sysn = sysn or system()
    try:
        st = (stat or os.stat)(long_path(str(path)))
    except (OSError, ValueError):
        return False
    if _win(sysn):
        return bool(int(getattr(st, "st_file_attributes", 0) or 0) & ONLINE_ONLY_ATTRS)
    if _mac(sysn):
        return bool(int(getattr(st, "st_flags", 0) or 0) & SF_DATALESS)
    return False


# ------------------------------------------------------------------ as a script
def _main(argv: List[str]) -> int:
    """python platforms.py shortcuts <launcher> [--no-desktop] (used by the Mac
    launcher once its private Python is there)."""
    if len(argv) >= 2 and argv[0] == "shortcuts":
        launcher = Path(argv[1]).resolve()
        assets = launcher.parent / "app" / "peterpiper" / "assets"
        version = ""
        try:
            import re
            text = (launcher.parent / "app" / "peterpiper" / "__init__.py").read_text(
                encoding="utf-8")
            m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
            version = m.group(1) if m else ""
        except OSError:
            pass
        icon = assets / ("PeterPiper.ico" if IS_WIN else "PeterPiper.icns")
        made = make_shortcuts(launcher, icon if icon.exists() else None, version,
                              desktop="--no-desktop" not in argv)
        for p in made:
            print(f"  made: {p}")
        return 0 if made else 1
    print(__doc__.strip().splitlines()[0])
    print("usage: platforms.py shortcuts <launcher> [--no-desktop]")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
