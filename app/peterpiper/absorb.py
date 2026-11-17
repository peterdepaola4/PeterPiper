"""
PeterPiper 1.2: take in ("absorb") older PeterPiper versions left on this computer.

Profiles, settings and run lists already live in the SHARED "PeterPiper data"
folder (users.base_dir()), so every version sees them. What each version keeps
for itself:
  - its program folder (e.g. ...\\PeterPiperV1.1 with PeterPiperV1.1.bat and app\\),
  - %USERPROFILE%\\.PeterPiperV1.1: its private Python (venv, about 0.5 GB),
    shortcuts_for.txt (the .bat its shortcuts start) and error logs,
  - the PeterPiper.lnk shortcuts (program folder, Desktop, Start menu).

find() looks for those (PeterPiper 1.0 and newer, older than the running one;
PD4nav's installs are never part of this) quickly, without walking folders,
and never raises. absorb() then, for one version:
  1. carries over what is not yet in PeterPiper data (error logs and the list of
     installed package versions to <data>/logs/<version>; settings files found in
     the version folder to the current user) - nothing there is overwritten,
  2. makes the Desktop / Start-menu PeterPiper.lnk that started that version
     start the running version's .bat,
  3. moves to the Recycle Bin (Mac: the Trash) ONLY what is recognised as that
     version's program files and its private Python. Anything else in its
     folder (results, notes, movies ...) stays where it is and is listed as kept.
     An emptied program folder is then removed.
Never touched: the running program folder, the private Python the running
PeterPiper uses (when the launcher reused it, it says "kept: PeterPiper 1.2 uses
it"), a developer copy (a folder with .git) and the private Python it uses,
anything outside the found versions' own folders, PeterPiper data. Before
anything is moved every item is checked (rename test: a file in use stops it;
that version still open - its launcher holds its error log open - too); if a step fails, that version's removal stops,
the rest is kept and the reason is said. Nothing is ever deleted for good.

Every function takes its places explicitly (Places), so tests can use a fake
user folder; default_places() gives the real ones.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

STATE_FILE = "absorb.json"                # <data>/absorb.json: "don't ask" per folder
FIRST = (1, 0)                            # the first PeterPiper version
HOME_RE = re.compile(r"^\.PeterPiperV(\d+)\.(\d+)$", re.I)
BAT_RE = re.compile(r"^PeterPiperV(\d+)\.(\d+)\.(?:bat|command|sh)$", re.I)
LNK = "PeterPiper.lnk"

# what a version's program folder holds (lower case); everything else is the user's
PROGRAM_FILES = {"read me.txt", "license", "license.txt", "license.md", "citation.cff",
                 "changelog.md", "contributing.md", "security.md", "peterpiper.lnk",
                 ".gitignore", ".gitattributes"}
PROGRAM_DIRS = {"app", "docs", "build", "__pycache__", "_update_backup"}
# what a version's own %USERPROFILE%\.PeterPiperV<x.y> holds
HOME_FILES = {"shortcuts_for.txt"}
HOME_LOG_RE = re.compile(r"^error_\d*\.txt$", re.I)


# ------------------------------------------------------------------ places
@dataclass
class Places:
    profile: Path                         # where the .PeterPiperV<x.y> folders are
    program: Optional[Path]               # the running program folder
    data: Path                            # PeterPiper data
    shortcut_dirs: List[Path] = field(default_factory=list)   # Desktop, Start menu
    in_use: List[Path] = field(default_factory=list)          # Python(s) running now
    running: Tuple[int, int] = (0, 0)
    running_bat: Optional[Path] = None    # what the shortcuts should start
    user_home: Optional[Path] = None      # where carried settings go (current user)


def _version_tuple(text: str) -> Tuple[int, int]:
    nums = [int(x) for x in re.findall(r"\d+", str(text))[:2]]
    return tuple((nums + [0, 0])[:2])                             # type: ignore[return-value]


def _special_folder(csidl: int) -> Optional[Path]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    except Exception:                                              # noqa: BLE001
        pass
    return None


def default_places() -> Places:
    """The real places on this computer (never raises)."""
    from . import APP_NAME, __version__, users
    try:
        from .updater import program_folder
        prog: Optional[Path] = program_folder()
    except Exception:                                              # noqa: BLE001
        prog = None
    if getattr(sys, "frozen", False):                             # the Mac .app: nothing to absorb
        prog = None
    dirs = [d for d in (_special_folder(0x10), _special_folder(0x02)) if d]  # Desktop, Programs
    in_use = [Path(sys.prefix), Path(sys.executable).parent]
    bat = (prog / f"{APP_NAME}.bat") if prog else None
    try:
        user_home: Optional[Path] = users.home() if users.current() else None
    except Exception:                                              # noqa: BLE001
        user_home = None
    return Places(profile=Path.home(), program=prog, data=users.base_dir(), shortcut_dirs=dirs,
                  in_use=in_use, running=_version_tuple(__version__),
                  running_bat=bat if bat and bat.exists() else None, user_home=user_home)


# ------------------------------------------------------------------ found versions
@dataclass
class Found:
    version: Tuple[int, int]
    programs: List[Path] = field(default_factory=list)     # program folders it may take in
    home: Optional[Path] = None                            # %USERPROFILE%\.PeterPiperV<x.y>
    dev_copies: List[Path] = field(default_factory=list)   # developer copies: left alone
    keep_home: str = ""                                    # why its private Python stays
    running_label: str = ""

    @property
    def name(self) -> str:
        return f"PeterPiperV{self.version[0]}.{self.version[1]}"

    @property
    def label(self) -> str:
        return f"PeterPiper {self.version[0]}.{self.version[1]}"

    @property
    def venv(self) -> Optional[Path]:
        if self.home is not None and (self.home / "venv").is_dir():
            return self.home / "venv"
        return None

    def keys(self) -> List[str]:
        """The folders of this version ('Don't ask again' remembers them)."""
        return sorted({_key(p) for p in self.programs + ([self.home] if self.home else [])})

    @property
    def absorbable(self) -> bool:
        return bool(self.programs) or (self.home is not None and not self.keep_home)


def _key(p: Path) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def _same(a: Path, b: Path) -> bool:
    return _key(a) == _key(b)


def _inside(p: Path, folder: Path) -> bool:
    """p is folder or lies inside it."""
    a, b = _key(p), _key(folder)
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _program_version(folder: Path) -> Optional[Tuple[int, int]]:
    """The version of a PeterPiper program folder (its PeterPiperV<x.y>.bat next to
    app/peterpiper), else None. One folder listing."""
    try:
        if not (folder / "app" / "peterpiper").is_dir():
            return None
        for n in os.listdir(folder):
            m = BAT_RE.match(n)
            if m:
                return int(m.group(1)), int(m.group(2))
    except OSError:
        pass
    return None


def read_lnk_target(path: Path) -> str:
    """The target of a Windows shortcut (.lnk), read from the file itself (no
    PowerShell, so it cannot hang); '' when it cannot be read."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(1 << 16)
    except OSError:
        return ""
    try:
        if len(data) < 0x4C or data[:4] != b"\x4c\x00\x00\x00":
            return ""
        flags = struct.unpack_from("<I", data, 0x14)[0]
        pos = 0x4C
        if flags & 0x01:                                  # HasLinkTargetIDList
            pos += 2 + struct.unpack_from("<H", data, pos)[0]
        if flags & 0x02:                                  # HasLinkInfo
            size, hdr, li_flags, _vol, lbp, _cnr, cps = struct.unpack_from("<7I", data, pos)
            if li_flags & 0x01:
                if hdr >= 0x24:
                    off = struct.unpack_from("<I", data, pos + 0x1C)[0]
                    end = off
                    while data[pos + end:pos + end + 2] not in (b"\0\0", b""):
                        end += 2
                    base = data[pos + off:pos + end].decode("utf-16-le", "replace")
                else:
                    end = data.index(b"\0", pos + lbp)
                    base = data[pos + lbp:end].decode("mbcs" if os.name == "nt" else "latin-1",
                                                      "replace")
                suffix = ""
                if cps:
                    e2 = data.index(b"\0", pos + cps)
                    suffix = data[pos + cps:e2].decode("latin-1", "replace")
                if base:
                    return base + suffix
    except (struct.error, ValueError, IndexError):
        pass
    for enc, start in (("utf-16-le", 0), ("utf-16-le", 1), ("latin-1", 0)):   # last resort
        m = re.search(r"[A-Za-z]:\\[^\x00-\x1f<>\"|?*]*?\.bat", data[start:].decode(enc, "ignore"))
        if m:
            return m.group(0)
    return ""


def find(places: Optional[Places] = None) -> List[Found]:
    """Older PeterPiper versions on this computer, oldest first. Fast (a few
    folder listings and small files) and never raises. Empty when a NEWER
    version than the running one is there too: the newest one takes the rest in."""
    try:
        return _find(places if places is not None else default_places())
    except Exception:                                              # noqa: BLE001
        return []


def _find(pl: Places) -> List[Found]:
    from . import APP_TITLE
    running_label = f"{APP_TITLE} {pl.running[0]}.{pl.running[1]}"
    homes: Dict[Tuple[int, int], Path] = {}
    progs: Dict[Tuple[int, int], Dict[str, Path]] = {}

    def add_program(folder: Path) -> None:
        if pl.program is not None and _same(folder, pl.program):
            return
        v = _program_version(folder)
        if v is not None:
            progs.setdefault(v, {})[_key(folder)] = folder

    def from_bat(bat_text: str) -> None:
        bat = Path(bat_text.strip().strip('"'))
        if bat_text and BAT_RE.match(bat.name) and bat.is_file():
            add_program(bat.parent)

    # 1. %USERPROFILE%\.PeterPiperV<x.y> and the .bat each one's shortcuts start
    try:
        entries = list(os.scandir(pl.profile))
    except OSError:
        entries = []
    for e in entries:
        m = HOME_RE.match(e.name)
        if not m or not e.is_dir():
            continue
        homes[(int(m.group(1)), int(m.group(2)))] = Path(e.path)
        try:
            with open(Path(e.path) / "shortcuts_for.txt", encoding="mbcs" if os.name == "nt"
                      else "utf-8", errors="replace") as fh:
                from_bat(fh.readline())
        except OSError:
            pass
    # 2. the PeterPiper shortcuts (Desktop, Start menu, the running program folder)
    for d in list(pl.shortcut_dirs) + ([pl.program] if pl.program else []):
        t = read_lnk_target(Path(d) / LNK)
        if t:
            from_bat(t)
    # 3. PeterPiperV<x.y> folders next to the running program folder
    if pl.program is not None:
        try:
            for e in os.scandir(pl.program.parent):
                if e.name.lower().startswith("peterpiperv") and e.is_dir():
                    add_program(Path(e.path))
        except OSError:
            pass

    versions = set(homes) | set(progs)
    if any(v > pl.running for v in versions):
        return []                                  # a newer PeterPiper is here: it absorbs
    out: List[Found] = []
    for v in sorted(versions):
        if not (FIRST <= v < pl.running):
            continue
        f = Found(version=v, home=homes.get(v), running_label=running_label)
        for folder in progs.get(v, {}).values():
            if (folder / ".git").exists():
                f.dev_copies.append(folder)
            elif _touchable(folder, pl):
                f.programs.append(folder)
        if f.home is not None:
            if any(_inside(p, f.home) for p in pl.in_use):
                f.keep_home = f"kept: {running_label} uses it"
            elif f.dev_copies:
                f.keep_home = f"kept: the developer copy {f.dev_copies[0]} uses it"
            elif not _touchable(f.home, pl):
                f.keep_home = "kept"
        if f.programs or f.home is not None or f.dev_copies:
            out.append(f)
    return out


def _touchable(folder: Path, pl: Places) -> bool:
    """Not the running program, not holding it / PeterPiper data / a running Python."""
    guard = [pl.data] + list(pl.in_use) + ([pl.program] if pl.program else [])
    return not any(_inside(g, folder) or _inside(folder, g) for g in guard)


# ------------------------------------------------------------------ "don't ask"
def _load_state(data: Path) -> dict:
    try:
        d = json.loads((Path(data) / STATE_FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_dont_ask(found: List[Found], data: Path) -> None:
    """Remember not to offer these versions' folders again (computer-level)."""
    d = _load_state(data)
    keys = set(d.get("dont_ask") or [])
    for f in found:
        keys.update(f.keys())
    d["dont_ask"] = sorted(keys)
    try:
        p = Path(data) / STATE_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def to_offer(places: Optional[Places] = None) -> List[Found]:
    """The versions to offer at start: absorbable and not 'don't ask'-ed (a
    version comes back when a folder of it appears that was not seen then)."""
    try:
        pl = places if places is not None else default_places()
        skip = set(_load_state(pl.data).get("dont_ask") or [])
        return [f for f in find(pl) if f.absorbable and not set(f.keys()) <= skip]
    except Exception:                                              # noqa: BLE001
        return []


# ------------------------------------------------------------------ sizes / plan
def folder_size(p: Path) -> int:
    """Bytes in a file or folder tree (0 when unreadable); never raises."""
    total, stack = 0, [str(p)]
    try:
        if Path(p).is_file():
            return Path(p).stat().st_size
    except OSError:
        return 0
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def nice_size(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.0f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KB"
    return f"{n} bytes"


@dataclass
class Plan:
    remove: List[Path] = field(default_factory=list)            # to the Recycle Bin
    keep: List[Tuple[Path, str]] = field(default_factory=list)  # stays, and why


def plan(f: Found) -> Plan:
    """What absorbing f moves to the Recycle Bin and what stays."""
    p = Plan()
    for folder in f.programs:
        bats = {f"{f.name}.bat".lower(), f"{f.name}.command".lower(), f"{f.name}.sh".lower()}
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            p.keep.append((folder, "could not be read"))
            continue
        for n in names:
            item, low = folder / n, n.lower()
            if (low in bats or low in PROGRAM_FILES or low.startswith("readme")
                    or (low in PROGRAM_DIRS and item.is_dir())):
                p.remove.append(item)
            else:
                p.keep.append((item, USER_FILE))
    for d in f.dev_copies:
        p.keep.append((d, "a developer copy - left as it is"))
    if f.home is not None:
        if f.keep_home:
            p.keep.append((f.home, f.keep_home))
        else:
            try:
                names = sorted(os.listdir(f.home))
            except OSError:
                names = []
            for n in names:
                item = f.home / n
                if n.lower() == "venv" or n.lower() in HOME_FILES or HOME_LOG_RE.match(n):
                    p.remove.append(item)
                else:
                    p.keep.append((item, NOT_OURS))
    return p


def sizes(f: Found) -> Dict[str, int]:
    """program: the program files absorbing removes; python: its private Python
    (0 when kept); kept: the user's files that stay. Slow-ish (walks folders)."""
    pl = plan(f)
    out = {"program": 0, "python": 0, "kept": 0}
    for item in pl.remove:
        out["python" if f.home is not None and _inside(item, f.home) else "program"] += \
            folder_size(item)
    for item, _why in pl.keep:
        if not any(_same(item, d) for d in f.dev_copies) and not (f.home and _same(item, f.home)):
            out["kept"] += folder_size(item)
    if f.home is not None and f.keep_home and f.venv is not None:
        out["python_kept"] = folder_size(f.venv)
    return out


# ------------------------------------------------------------------ the steps
def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def carry_over(f: Found, pl: Places) -> List[str]:
    """Copy what this version kept for itself into PeterPiper data, never over
    anything already there. Returns what was copied (words, one line per folder)."""
    from . import users
    done: Dict[str, List[str]] = {}
    extra: List[str] = []
    logs = Path(pl.data) / "logs" / f.name

    def copied(src_name: str, dst: Path) -> None:
        done.setdefault(str(dst.parent), []).append(src_name)
    if f.home is not None:
        srcs = []
        try:
            srcs = [f.home / n for n in sorted(os.listdir(f.home)) if HOME_LOG_RE.match(n)]
        except OSError:
            pass
        if f.venv is not None and (f.venv / "installed_versions.txt").is_file():
            srcs.append(f.venv / "installed_versions.txt")
        for s in srcs:
            try:
                if s.stat().st_size == 0:
                    continue                                  # an empty log says nothing
                dst = logs / s.name
                if dst.exists():
                    continue
                logs.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, dst)
                copied(s.name, dst)
            except OSError:
                pass
        # settings an old version may have written into its own folder
        target = Path(pl.user_home) if pl.user_home else Path(pl.data)
        for n in users.DATA_NAMES:
            s = f.home / n
            if not s.exists():
                continue
            dst = target / n
            try:
                if n == "run_history.json" and dst.exists():
                    from .history import merge_run_indexes
                    mine = json.loads(dst.read_text(encoding="utf-8"))
                    theirs = json.loads(s.read_text(encoding="utf-8"))
                    if isinstance(mine, dict) and isinstance(theirs, dict):
                        merged = merge_run_indexes(mine, theirs)
                        if merged != mine:
                            tmp = dst.with_suffix(".tmp")
                            tmp.write_text(json.dumps(merged, indent=1), encoding="utf-8")
                            os.replace(tmp, dst)
                            extra.append(f"its run list was added to {dst}")
                    continue
                if _same_file(s, dst):
                    continue                                  # already there
                if dst.exists():
                    dst = Path(pl.data) / "carried over" / f.name / n
                    if dst.exists():
                        continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                if s.is_dir():
                    shutil.copytree(s, dst)
                else:
                    shutil.copy2(s, dst)
                copied(n, dst)
            except (OSError, ValueError):
                pass
    return [f"{_few(names)} -> {folder}" for folder, names in done.items()] + extra


def write_shortcut(lnk: Path, target: Path, icon: Optional[Path], description: str) -> bool:
    """(Re)write a Windows shortcut through WScript.Shell, paths passed as
    environment variables (never as code). False on any problem; 30 s at most."""
    if sys.platform != "win32":
        return False
    env = dict(os.environ, PP_LNK=str(lnk), PP_BAT=str(target), PP_DIR=str(target.parent),
               PP_ICO=(str(icon) + ",0") if icon and icon.exists() else "", PP_DESC=description)
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


def repoint_shortcuts(f: Found, pl: Places,
                      writer: Callable[[Path, Path, Optional[Path], str], bool] = None
                      ) -> List[str]:
    """The Desktop / Start-menu PeterPiper.lnk that start this version (or a
    PeterPiper .bat that is gone) start the running version's .bat instead."""
    writer = writer or write_shortcut
    if pl.running_bat is None:
        return []
    olds = [_key(p) for p in f.programs + f.dev_copies]
    done: List[str] = []
    for d in pl.shortcut_dirs:
        lnk = Path(d) / LNK
        if not lnk.is_file():
            continue
        t = read_lnk_target(lnk)
        if not t or _same(Path(t), pl.running_bat):
            continue
        tp = Path(t)
        m = BAT_RE.match(tp.name)
        if not m or (int(m.group(1)), int(m.group(2))) != f.version:
            continue
        mine = _key(tp.parent) in olds and not any(_same(tp.parent, d2) for d2 in f.dev_copies)
        if not (mine or not tp.exists()):
            continue
        icon = pl.running_bat.parent / "app" / "peterpiper" / "assets" / "PeterPiper.ico"
        from . import APP_TITLE
        desc = (f"{APP_TITLE} {pl.running[0]}.{pl.running[1]} - single-cell fluorescence "
                "time courses")
        if writer(lnk, pl.running_bat, icon, desc):
            done.append(f"{lnk} now starts {pl.running_bat.name}")
    return done


def _trash_word() -> str:
    return "Trash" if sys.platform != "win32" else "Recycle Bin"


def has_recycle_bin(path: Path) -> bool:
    """Windows: the drive of `path` has a Recycle Bin (network drives do not)."""
    if sys.platform != "win32":
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


def recycle(path: Path) -> str:
    """Move a file or folder to the Recycle Bin (Mac: the Trash) so it can be
    restored. '' when done, else the reason. Never deletes for good: a drive
    without a Recycle Bin is refused, and Windows asks before anything too large
    for the Recycle Bin would be deleted (answer No to keep it)."""
    path = Path(path)
    if not path.exists():
        return ""
    if sys.platform == "win32":
        if not has_recycle_bin(path):
            return f"the drive of {path} has no {_trash_word()}"
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
            except Exception:                                      # noqa: BLE001
                pass
            rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        except Exception as exc:                                   # noqa: BLE001
            return f"Windows could not move it ({exc})"
        if op.fAnyOperationsAborted:
            return "it was stopped (nothing more was moved)"
        if rc != 0:
            return f"Windows could not move it (code {rc:#x}) - is a file in it open?"
        return "" if not path.exists() else "part of it could not be moved (a file in use?)"
    # Mac / Linux: into the user's Trash
    trash = (Path.home() / ".Trash") if sys.platform == "darwin" else \
        Path.home() / ".local" / "share" / "Trash" / "files"
    try:
        trash.mkdir(parents=True, exist_ok=True)
        dst, i = trash / path.name, 2
        while dst.exists():
            dst, i = trash / f"{path.name} {i}", i + 1
        shutil.move(str(path), str(dst))
        return ""
    except OSError as exc:
        return f"it could not be moved to the {_trash_word()} ({exc})"


def in_use(path: Path) -> str:
    """Windows: '' when nothing inside `path` is open (a rename test: a folder
    with a file in use cannot be renamed), else the reason."""
    if sys.platform != "win32" or not path.exists():
        return ""
    probe = path.with_name(path.name + ".pp-check")
    if probe.exists():
        return f"{probe} is in the way"
    try:
        os.rename(path, probe)
    except OSError:
        return "a file in it is in use (is that PeterPiper version still open?)"
    for _ in range(20):
        try:
            os.rename(probe, path)
            return ""
        except OSError:
            import time
            time.sleep(0.1)
    return f"it was renamed to {probe} for a test and could not be renamed back - rename it by hand"


USER_FILE = "your files"
NOT_OURS = "not PeterPiper's"
STOPPED = "stopped before they were moved"


def _by_folder(paths: List[Path]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for p in paths:
        out.setdefault(str(p.parent), []).append(p.name)
    return out


def _few(names: List[str], n: int = 8) -> str:
    more = len(names) - n
    return ", ".join(names[:n]) + (f" and {more} more" if more > 0 else "")


@dataclass
class Outcome:
    found: Found
    carried: List[str] = field(default_factory=list)
    shortcuts: List[str] = field(default_factory=list)
    recycled: List[Path] = field(default_factory=list)
    kept: List[Tuple[Path, str]] = field(default_factory=list)
    problem: str = ""

    def lines(self) -> List[str]:
        f, bin_ = self.found, _trash_word()
        out = [f"{f.label}:"]
        if self.problem:
            out.append(f"  NOT finished: {self.problem}")
        for c in self.carried:
            out.append(f"  copied: {c}")
        for s in self.shortcuts:
            out.append(f"  shortcut: {s}")
        for parent, names in _by_folder(self.recycled).items():
            out.append(f"  moved to the {bin_} (can be restored from there), from {parent}: "
                       + _few(names))
        groups: Dict[Tuple[str, str], List[str]] = {}
        for p, why in self.kept:
            if why in (USER_FILE, NOT_OURS, STOPPED):
                groups.setdefault((str(p.parent), why), []).append(p.name)
            else:
                out.append(f"  kept: {p} - {why[6:] if why.startswith('kept: ') else why}")
        for (parent, why), names in groups.items():
            out.append(f"  kept where they are, in {parent} ({why}): " + _few(names))
        if len(out) == 1:
            out.append("  nothing to do")
        return out


def _removable(item: Path, f: Found, pl: Places) -> bool:
    """Last check before an item goes: directly inside one of this version's own
    folders and not holding anything that must stay."""
    owners = list(f.programs) + ([f.home] if f.home is not None and not f.keep_home else [])
    if not any(_same(item.parent, o) for o in owners):
        return False
    if any(_inside(item, d) or _inside(d, item) for d in f.dev_copies):
        return False
    if (item.parent / ".git").exists():
        return False
    return _touchable(item, pl)


def absorb(f: Found, places: Optional[Places] = None,
           recycler: Callable[[Path], str] = None,
           writer: Callable[[Path, Path, Optional[Path], str], bool] = None,
           checker: Callable[[Path], str] = None,
           progress: Callable[[Optional[float], str], object] = None) -> Outcome:
    """Take one older version in (see the module text). Never raises."""
    pl = places if places is not None else default_places()
    recycler, checker = recycler or recycle, checker or in_use
    say = progress or (lambda *a: None)
    out = Outcome(found=f)
    try:
        say(None, f"{f.label}: copying what it kept for itself ...")
        out.carried = carry_over(f, pl)
        say(None, f"{f.label}: shortcuts ...")
        out.shortcuts = repoint_shortcuts(f, pl, writer)
        p = plan(f)
        out.kept = list(p.keep)
        items = [i for i in p.remove if _removable(i, f, pl)]
        out.kept += [(i, "not recognised as safe to move - kept") for i in p.remove
                     if i not in items]
        # all checked before anything moves; that version's open log (its launcher
        # holds it while it runs) means it is open now
        logs = []
        if f.home is not None and items:
            try:
                logs = [f.home / n for n in os.listdir(f.home) if HOME_LOG_RE.match(n)]
            except OSError:
                pass
        for i in logs + [i for i in items if i not in logs]:
            why = checker(i)
            if why:
                if i in logs:
                    why = f"{f.label} seems to be open - close it, then try again"
                out.problem = f"{i}: {why}. Nothing of {f.label} was moved."
                out.kept += [(j, STOPPED) for j in items]
                return out
        for k, i in enumerate(items):
            say(k / max(1, len(items)), f"{f.label}: to the {_trash_word()}: {i.name} ...")
            why = recycler(i)
            if why:
                out.problem = (f"{i}: {why}. Stopped here; what is listed as moved can be "
                               f"restored from the {_trash_word()}, the rest is kept.")
                out.kept += [(j, STOPPED) for j in items[k:]]
                return out
            out.recycled.append(i)
        for folder in list(f.programs) + ([f.home] if f.home is not None and not f.keep_home
                                         else []):
            try:
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()                       # an empty folder: nothing in it
            except OSError:
                pass
    except Exception as exc:                                       # noqa: BLE001
        out.problem = f"an unexpected problem ({exc}); the rest is kept."
    return out
