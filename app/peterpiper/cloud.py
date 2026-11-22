"""
PeterPiper 1.1 - keeping analyses in OneDrive, Google Drive, Box, Dropbox, iCloud
Drive, a network folder ... through each service's OWN app.

PeterPiper never signs in anywhere, and this module has no network code (the
only network use in PeterPiper is the optional 'Check for updates', updater.py).
Each service has a
free app that puts a folder on the computer and uploads whatever is put into it.
This module only FINDS those folders (read-only looks at the file system; on
Windows also read-only registry look-ups), tells whether a file is stored only
online (opening it downloads it first), and copies an analysis into one of those
folders (backup). The service's app does the uploading.

    places()                    -> [Place(name, path, service, kind)] found here
    service_of(path)            -> "OneDrive", "Google Drive" ... or ""
    is_online_only(path)        -> True if the file is only a stand-in for an online file
    online_warning(path)        -> a plain-words warning, or ""
    backup(nd2, out_dir, target_root, include_movie=True, progress=None, cancel=None)
                                -> BackupReport; copies into
                                   <target_root>/PeterPiper backup/<movie>/ and never
                                   overwrites anything
    results_root() / set_results_root(path or None)   per user (userprefs "storage")
    backup_root()  / set_backup_root(path or None)

Place.kind: "personal" (one person's own cloud folder), "work" (a work or school
account), "shared" (a shared library, shared drive or team folder), "network" (a
network drive or share).

Tests: $PETERPIPER_CLOUD_HOME replaces the home folder, and then nothing outside it
is looked at (no drive letters, registry, environment variables or mounts) except
what TEST_HOOKS gives:
    TEST_HOOKS["system"]   "win32" / "darwin" / "linux" instead of sys.platform
    TEST_HOOKS["drives"]   [{"root": "G:\\", "type": "fixed"|"remote", "label": "...",
                             "unc": "\\\\server\\share"}]   (Windows drive letters)
    TEST_HOOKS["onedrive"] [{"UserFolder": path, "DisplayName": "...", "business": bool,
                             "tenants": [paths], "libraries": [paths]}]  (registry)
    TEST_HOOKS["mounts"]   [(mount point, file system type, source)]   (macOS / Linux)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .safety import error_text, folder_problem, long_path, make_dirs, plain_path

BACKUP_DIR = "PeterPiper backup"          # <target>/PeterPiper backup/<movie>/
RESULTS_DIR = "PeterPiper results"        # suggested results folder inside a cloud place
TOPIC = "storage"                         # userprefs topic

# the services in the order they are listed
SERVICES = ("OneDrive", "Google Drive", "Box", "Dropbox", "iCloud Drive", "Nextcloud",
            "ownCloud", "pCloud", "MEGA", "Sync.com", "Egnyte")
NETWORK = "Network"
KINDS = ("personal", "work", "shared", "network")

TEST_HOOKS: Dict[str, object] = {}

# Windows file attributes of a file whose data is only online (cloud placeholder)
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
# macOS: a file whose data is not on this Mac (iCloud, File Provider apps)
SF_DATALESS = 0x40000000

_stat = os.stat                           # replaced in tests


@dataclass(frozen=True)
class Place:
    name: str        # what the user sees, e.g. "OneDrive - Contoso"
    path: str        # the folder to write into
    service: str     # the app that syncs it ("OneDrive" ... or "Network")
    kind: str        # personal / work / shared / network


# ------------------------------------------------------------------ helpers
def _system() -> str:
    return str(TEST_HOOKS.get("system") or sys.platform)


def _faked() -> bool:
    return bool(os.environ.get("PETERPIPER_CLOUD_HOME"))


def _home() -> Path:
    custom = os.environ.get("PETERPIPER_CLOUD_HOME")
    return Path(custom) if custom else Path.home()


def _isdir(p) -> bool:
    try:
        return bool(p) and os.path.isdir(p)
    except (OSError, ValueError):
        return False


def _subdirs(p) -> List[str]:
    """The folder names in p (one directory listing, nothing deeper)."""
    try:
        with os.scandir(p) as it:
            return sorted(e.name for e in it if not e.name.startswith(".") and e.is_dir())
    except (OSError, ValueError):
        return []


def _key(path) -> str:
    return os.path.normcase(os.path.normpath(str(path))).rstrip("\\/")


def _appdata(local: bool) -> Optional[Path]:
    """%LOCALAPPDATA% / %APPDATA% (under the fake home in tests)."""
    if _faked():
        return _home() / "AppData" / ("Local" if local else "Roaming")
    v = os.environ.get("LOCALAPPDATA" if local else "APPDATA")
    return Path(v) if v else None


class _Found:
    def __init__(self) -> None:
        self.items: List[Place] = []
        self._seen: set = set()

    def add(self, name: str, path, service: str, kind: str, check: bool = True) -> None:
        if not path:
            return
        p = str(path)
        if check and not _isdir(p):
            return
        k = _key(p)
        if k in self._seen:
            return
        self._seen.add(k)
        self.items.append(Place(name, p, service, kind))


# ------------------------------------------------------- Windows look-ups
def _win_drives() -> List[dict]:
    """[{root, type, label, unc}] for the drive letters in use (no network access:
    the drive list, its type, the volume label of local drives only, and the
    remembered network path)."""
    if "drives" in TEST_HOOKS:
        return list(TEST_HOOKS["drives"])                           # type: ignore[arg-type]
    if _faked() or os.name != "nt":
        return []
    out = []
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        old = k32.SetErrorMode(0x0001 | 0x8000)       # no "insert a disk" boxes
        try:
            mask = k32.GetLogicalDrives()
            for i in range(26):
                if not mask & (1 << i):
                    continue
                root = f"{chr(65 + i)}:\\"
                t = k32.GetDriveTypeW(root)
                kind = {2: "removable", 3: "fixed", 4: "remote", 5: "cdrom",
                        6: "ram"}.get(t, "other")
                d = {"root": root, "type": kind, "label": "", "unc": ""}
                if kind == "fixed":
                    buf = ctypes.create_unicode_buffer(261)
                    if k32.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0):
                        d["label"] = buf.value
                elif kind == "remote":
                    d["unc"] = _win_unc(root[0])
                out.append(d)
        finally:
            k32.SetErrorMode(old)
    except Exception:                                              # noqa: BLE001
        return out
    return out


def _win_unc(letter: str) -> str:
    """The \\\\server\\share of a mapped drive, from the registry (HKCU\\Network)
    or Windows' own table of connections - no network access."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Network\\{letter}") as k:
            v, _ = winreg.QueryValueEx(k, "RemotePath")
            if v:
                return str(v)
    except Exception:                                              # noqa: BLE001
        pass
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.c_ulong(1024)
        if ctypes.windll.mpr.WNetGetConnectionW(f"{letter}:", buf, ctypes.byref(n)) == 0:
            return buf.value
    except Exception:                                              # noqa: BLE001
        pass
    return ""


def _reg_values(key) -> List[Tuple[str, object]]:
    import winreg
    out, i = [], 0
    while True:
        try:
            name, data, _ = winreg.EnumValue(key, i)
        except OSError:
            return out
        out.append((name, data))
        i += 1


def _reg_subkeys(key) -> List[str]:
    import winreg
    out, i = [], 0
    while True:
        try:
            out.append(winreg.EnumKey(key, i))
        except OSError:
            return out
        i += 1


def _looks_like_path(s) -> bool:
    return isinstance(s, str) and (re.match(r"^[A-Za-z]:\\", s) is not None or s.startswith("\\\\"))


def _reg_onedrive() -> List[dict]:
    """OneDrive's accounts from HKCU\\Software\\Microsoft\\OneDrive\\Accounts:
    their folders and the SharePoint / Teams libraries synced through them."""
    if "onedrive" in TEST_HOOKS:
        return list(TEST_HOOKS["onedrive"])                         # type: ignore[arg-type]
    if _faked() or os.name != "nt":
        return []
    out: List[dict] = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\OneDrive\Accounts") as acc:
            for sub in _reg_subkeys(acc):
                if sub != "Personal" and not sub.startswith("Business"):
                    continue
                with winreg.OpenKey(acc, sub) as a:
                    vals = dict(_reg_values(a))
                    d = {"UserFolder": str(vals.get("UserFolder") or ""),
                         "DisplayName": str(vals.get("DisplayName") or ""),
                         "business": sub.startswith("Business"),
                         "tenants": [], "libraries": []}
                    try:
                        with winreg.OpenKey(a, "Tenants") as ten:
                            for org in _reg_subkeys(ten):
                                with winreg.OpenKey(ten, org) as o:
                                    for name, data in _reg_values(o):
                                        for s in (name, data):
                                            if _looks_like_path(s):
                                                d["tenants"].append(s)
                    except OSError:
                        pass
                    try:
                        with winreg.OpenKey(a, "ScopeIdToMountPointPathCache") as sc:
                            for _name, data in _reg_values(sc):
                                if _looks_like_path(data):
                                    d["libraries"].append(data)
                    except OSError:
                        pass
                    out.append(d)
    except Exception:                                              # noqa: BLE001
        pass
    return out


# ------------------------------------------------------ macOS / Linux mounts
_NET_FS = ("smbfs", "afpfs", "nfs", "webdav", "cifs", "smb3", "nfs4", "fuse.sshfs")


def _mounts() -> List[Tuple[str, str, str]]:
    """[(mount point, type, source)] of network file systems."""
    if "mounts" in TEST_HOOKS:
        return [tuple(m) for m in TEST_HOOKS["mounts"]]             # type: ignore[union-attr,misc]
    if _faked():
        return []
    out = []
    sysn = _system()
    try:
        if sysn == "darwin":
            import subprocess
            text = subprocess.run(["/sbin/mount"], capture_output=True, text=True,  # noqa: S603
                                  timeout=3).stdout
            for ln in text.splitlines():
                m = re.match(r"^(.*?) on (.*?) \(([^,)]+)", ln)
                if m and m.group(3).strip() in _NET_FS:
                    out.append((m.group(2), m.group(3).strip(), m.group(1)))
        elif sysn.startswith("linux"):
            for ln in Path("/proc/mounts").read_text().splitlines():
                parts = ln.split()
                if len(parts) > 2 and parts[2] in _NET_FS:
                    out.append((parts[1].replace("\\040", " "), parts[2], parts[0]))
    except Exception:                                              # noqa: BLE001
        pass
    return out


# ------------------------------------------------------------- the probes
_CLOUDSTORAGE = {"onedrive": "OneDrive", "googledrive": "Google Drive", "box": "Box",
                 "dropbox": "Dropbox", "nextcloud": "Nextcloud", "owncloud": "ownCloud",
                 "pcloud": "pCloud", "pclouddrive": "pCloud", "mega": "MEGA",
                 "egnyte": "Egnyte", "sync": "Sync.com", "icloud": "iCloud Drive"}


def _google_root(f: _Found, root: Path, suffix: str = "") -> None:
    """A Google Drive folder: 'My Drive' and each shared drive."""
    my = root / "My Drive"
    if _isdir(my):
        f.add("Google Drive" + suffix, my, "Google Drive", "personal")
        for sd in _subdirs(root / "Shared drives")[:12]:
            f.add(f"Google shared drive - {sd}", root / "Shared drives" / sd,
                  "Google Drive", "shared")


def _onedrive_libraries(f: _Found, paths: List[str], home: Path,
                        user_folders: List[str] = ()) -> None:
    """SharePoint / Teams libraries synced through OneDrive. A folder beside the
    OneDrive folder (~/<Org name>) only holds the libraries: they are listed."""
    tops = {_key(home)} | {_key(Path(u).parent) for u in user_folders if u}
    own = {_key(u) for u in user_folders if u}
    for p in paths:
        pp = Path(p)
        if _key(pp) in own or pp.name.startswith("OneDrive"):
            continue
        if _key(pp.parent) in tops:
            for lib in _subdirs(pp)[:12]:
                f.add(f"{lib} ({pp.name})", pp / lib, "OneDrive", "shared")
        else:
            f.add(f"{pp.name} ({pp.parent.name})", pp, "OneDrive", "shared")


def _probe_onedrive(f: _Found, home: Path, sysn: str) -> None:
    accounts = _reg_onedrive()
    folders = [str(a.get("UserFolder") or "") for a in accounts]
    for acc in accounts:
        folder = acc.get("UserFolder") or ""
        if acc.get("business"):
            name = Path(folder).name if Path(folder).name.startswith("OneDrive - ") else (
                f"OneDrive - {acc.get('DisplayName')}" if acc.get("DisplayName")
                else "OneDrive (work or school)")
            f.add(name, folder, "OneDrive", "work")
        else:
            f.add("OneDrive", folder, "OneDrive", "personal")
        _onedrive_libraries(f, list(acc.get("libraries") or []), home, folders)
        _onedrive_libraries(f, list(acc.get("tenants") or []), home, folders)
    if not _faked() and sysn.startswith("win"):
        for var, kind in (("OneDriveConsumer", "personal"), ("OneDriveCommercial", "work"),
                          ("OneDrive", "personal")):
            p = os.environ.get(var)
            if p:
                n = Path(p).name
                f.add(n if n.startswith("OneDrive - ") else "OneDrive", p, "OneDrive",
                      "work" if n.startswith("OneDrive - ") else kind)
    for n in _subdirs(home):
        if n == "OneDrive":
            f.add("OneDrive", home / n, "OneDrive", "personal")
        elif n.startswith("OneDrive - ") or n.startswith("OneDrive-"):
            f.add(n.replace("OneDrive-", "OneDrive - ", 1) if n.startswith("OneDrive-") else n,
                  home / n, "OneDrive", "work")


def _probe_cloudstorage(f: _Found, home: Path) -> None:
    """macOS 12+: every File Provider app's folder is in ~/Library/CloudStorage."""
    cs = home / "Library" / "CloudStorage"
    for n in _subdirs(cs):
        prefix, _, rest = n.partition("-")
        svc = _CLOUDSTORAGE.get(prefix.lower().replace(" ", ""))
        p = cs / n
        if svc == "OneDrive":
            if rest == "Personal" or not rest:
                f.add("OneDrive", p, svc, "personal")
            elif rest.startswith("SharedLibraries"):
                org = rest.partition("-")[2] or "SharePoint"
                for lib in _subdirs(p)[:12]:
                    f.add(f"{lib} ({org})", p / lib, svc, "shared")
            else:
                f.add(f"OneDrive - {rest}", p, svc, "work")
        elif svc == "Google Drive":
            _google_root(f, p, f" ({rest})" if rest else "")
        elif svc is not None:
            f.add(svc if not rest or rest == prefix else f"{svc} ({rest})", p, svc, "personal")
        else:                       # another app's folder (e.g. Synology Drive)
            f.add(n.replace("-", " - ", 1), p, prefix, "personal")


def _probe_google(f: _Found, home: Path, sysn: str, drives: List[dict]) -> None:
    if sysn.startswith("win"):
        for d in drives:          # Google Drive for desktop: a drive labelled "Google Drive"
            if "google" in str(d.get("label", "")).lower():
                _google_root(f, Path(d["root"]))
    g = home / "Google Drive"
    if _isdir(g / "My Drive"):
        _google_root(f, g)
    else:
        f.add("Google Drive", g, "Google Drive", "personal")
    f.add("Google Drive", home / "My Drive", "Google Drive", "personal")   # mirror mode
    if sysn == "darwin" and not _faked():
        _google_root(f, Path("/Volumes/GoogleDrive"))


def _dropbox_info(f: _Found, home: Path, sysn: str) -> None:
    files = [home / ".dropbox" / "info.json"]
    if sysn.startswith("win"):
        for local in (True, False):
            a = _appdata(local)
            if a is not None:
                files.append(a / "Dropbox" / "info.json")
    for fp in files:
        try:
            info = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(info, dict):
            continue
        for acc, kind in (("personal", "personal"), ("business", "work")):
            d = info.get(acc)
            if isinstance(d, dict) and d.get("path"):
                n = Path(str(d["path"])).name
                name = "Dropbox" if kind == "personal" else (
                    n if n.startswith("Dropbox") and n != "Dropbox" else "Dropbox (work)")
                f.add(name, d["path"], "Dropbox", kind)


def _probe_home_names(f: _Found, home: Path, sysn: str, drives: List[dict]) -> None:
    names = _subdirs(home)
    for n in names:                                    # Dropbox, Dropbox (Org)
        if n.startswith("Dropbox"):
            work = "(" in n and "personal" not in n.lower()
            f.add(n, home / n, "Dropbox", "work" if work else "personal")
    f.add("Box", home / "Box", "Box", "personal")
    f.add("Box Sync", home / "Box Sync", "Box", "personal")
    f.add("iCloud Drive", home / "iCloudDrive", "iCloud Drive", "personal")
    f.add("iCloud Drive", home / "iCloud Drive", "iCloud Drive", "personal")
    f.add("iCloud Drive", home / "Library" / "Mobile Documents" / "com~apple~CloudDocs",
          "iCloud Drive", "personal")
    for n in names:
        low = n.lower()
        if low.startswith("nextcloud"):
            f.add(n, home / n, "Nextcloud", "personal")
        elif low.startswith("owncloud"):
            f.add(n, home / n, "ownCloud", "personal")
    _sync_cfg(f, home, sysn)
    for n in ("pCloud Drive", "pCloudDrive"):
        f.add("pCloud", home / n, "pCloud", "personal")
    for p in (home / "MEGA", home / "MEGAsync", home / "Documents" / "MEGAsync",
              home / "Documents" / "MEGA"):
        f.add("MEGA", p, "MEGA", "personal")
    sync = home / "Sync"
    if _isdir(sync) and not os.path.exists(sync / ".stfolder"):     # .stfolder: Syncthing
        f.add("Sync.com", sync, "Sync.com", "personal")
    f.add("Egnyte", home / "Egnyte", "Egnyte", "shared")
    for d in drives:
        label = str(d.get("label", "")).lower()
        unc = str(d.get("unc", "")).lower()
        if "pcloud" in label:
            f.add("pCloud", d["root"], "pCloud", "personal")
        elif "egnyte" in label or "egnyte" in unc:
            f.add("Egnyte", d["root"], "Egnyte", "shared", check=False)


def _sync_cfg(f: _Found, home: Path, sysn: str) -> None:
    """Nextcloud / ownCloud remember their folders in a small settings file
    (localPath=...)."""
    for svc, app, cfg in (("Nextcloud", "Nextcloud", "nextcloud.cfg"),
                          ("ownCloud", "ownCloud", "owncloud.cfg")):
        if sysn.startswith("win"):
            a = _appdata(False)
            files = [a / app / cfg] if a is not None else []
        elif sysn == "darwin":
            files = [home / "Library" / "Preferences" / app / cfg]
        else:
            files = [home / ".config" / app / cfg]
        for fp in files:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in re.finditer(r"localPath=(.+)", text):
                p = m.group(1).strip().rstrip("/\\")
                f.add(f"{svc} ({Path(p).name})" if Path(p).name.lower() != svc.lower()
                      else svc, p, svc, "personal")


def _probe_network(f: _Found, sysn: str, drives: List[dict]) -> None:
    """Mapped network drives (Windows) and network mounts (macOS, Linux). Their
    folders are NOT opened (a server that is off could make that hang)."""
    for d in drives:
        if d.get("type") != "remote":
            continue
        unc = str(d.get("unc") or "")
        if "egnyte" in unc.lower():
            continue
        letter = str(d["root"])[:2]
        f.add(f"Network drive {letter} ({unc})" if unc else f"Network drive {letter}",
              d["root"], NETWORK, "network", check=False)
    for point, fstype, source in _mounts():
        f.add(f"Network folder {Path(point).name} ({source})", point, NETWORK, "network",
              check=False)


def _unique_names(items: List[Place]) -> None:
    """Two places with the same name (two Dropbox folders): each gets its folder's
    name added, e.g. 'Dropbox (Work files)'."""
    counts: Dict[str, int] = {}
    for p in items:
        counts[p.name] = counts.get(p.name, 0) + 1
    for i, p in enumerate(items):
        n = Path(p.path).name
        if counts[p.name] > 1 and n and n != p.name:
            items[i] = Place(f"{p.name} ({n})", p.path, p.service, p.kind)


def places() -> List[Place]:
    """The cloud and network folders on this computer: each service's synced
    folder (only those that exist), no duplicates, in service order. Fast: a
    few folder checks, no searching through folders, no network."""
    home = _home()
    sysn = _system()
    drives = _win_drives() if sysn.startswith("win") else []
    f = _Found()
    for probe in (lambda: _probe_onedrive(f, home, sysn),
                  lambda: _probe_cloudstorage(f, home),
                  lambda: _probe_google(f, home, sysn, drives),
                  lambda: _dropbox_info(f, home, sysn),
                  lambda: _probe_home_names(f, home, sysn, drives),
                  lambda: _probe_network(f, sysn, drives)):
        try:
            probe()
        except Exception:                                          # noqa: BLE001
            pass
    _unique_names(f.items)
    order = {s: i for i, s in enumerate(SERVICES)}
    order[NETWORK] = len(SERVICES) + 1
    return sorted(f.items, key=lambda p: (order.get(p.service, len(SERVICES)),
                                          p.service.lower(), KINDS.index(p.kind)
                                          if p.kind in KINDS else 9, p.name.lower()))


def place_of(path, found: Optional[List[Place]] = None) -> Optional[Place]:
    """The place that holds `path` (the deepest one), or None."""
    k = _key(os.path.abspath(plain_path(str(path))))
    best = None
    for p in (places() if found is None else found):
        pk = _key(p.path)
        if (k == pk or k.startswith(pk + os.sep) or k.startswith(pk + "/")) and \
                (best is None or len(pk) > len(_key(best.path))):
            best = p
    return best


def service_of(path, found: Optional[List[Place]] = None) -> str:
    p = place_of(path, found)
    return p.service if p else ""


# -------------------------------------------------------- online-only files
def is_online_only(path) -> bool:
    """True when the file's data is not on this computer (a OneDrive / Google
    Drive / Box / Dropbox / iCloud placeholder): reading it downloads it first.
    Only the file's attributes are read - nothing is downloaded. 4.0:
    platforms.is_online_only does it (with this module's _system / _stat, which
    tests replace)."""
    from .platforms import is_online_only as _ioo
    return _ioo(path, _system(), _stat)


def human_size(n: float) -> str:
    n = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            if unit == "bytes":
                return f"{int(n)} bytes"
            return f"{n:.1f} {unit}" if n < 100 else f"{n:.0f} {unit}"
        n /= 1000.0
    return f"{n:.1f} TB"


def online_warning(path, what: str = "movie",
                   found: Optional[List[Place]] = None) -> str:
    """'' if the file is on this computer; else e.g. 'This movie is stored only
    online in OneDrive; it will be downloaded first (about 2.3 GB).'"""
    if not is_online_only(path):
        return ""
    svc = service_of(path, found)
    where = f" in {svc}" if svc and svc != NETWORK else ""
    try:
        size = f" (about {human_size(_stat(long_path(str(path))).st_size)})"
    except (OSError, ValueError, AttributeError):
        size = ""
    return f"This {what} is stored only online{where}; it will be downloaded first{size}."


# ------------------------------------------------------------------ backup
_JUNK_PREFIX = (".peterpiper_write_test_", "~$", "._")
_JUNK_SUFFIX = (".tmp", ".lock", ".peterpiper-partial")
_JUNK_NAMES = {".ds_store", "desktop.ini", "thumbs.db"}
CHUNK = 4 * 1024 * 1024
_MTIME_SLACK = 2.0          # seconds: FAT drives and some cloud folders round times


@dataclass
class BackupReport:
    folder: str = ""                                   # <target>/PeterPiper backup/<movie>
    copied: List[Tuple[str, str]] = field(default_factory=list)    # (source, copy)
    skipped: List[Tuple[str, str]] = field(default_factory=list)   # already backed up
    failed: List[Tuple[str, str]] = field(default_factory=list)    # (source, why)
    bytes_copied: int = 0
    total_bytes: int = 0                               # bytes that needed copying
    cancelled: bool = False
    problem: str = ""                                  # nothing could be done: why

    @property
    def ok(self) -> bool:
        return not (self.failed or self.problem or self.cancelled)

    def summary(self) -> str:
        if self.problem:
            return f"Not backed up: {self.problem}"
        parts = []
        if self.copied:
            parts.append(f"{len(self.copied)} file(s) copied ({human_size(self.bytes_copied)})")
        if self.skipped:
            parts.append(f"{len(self.skipped)} already backed up")
        if self.failed:
            parts.append(f"{len(self.failed)} could not be copied")
        text = ", ".join(parts) or ("nothing copied yet" if self.cancelled
                                    else "nothing to back up")
        if self.cancelled:
            text = "Stopped - " + text + ". Start again to finish (nothing is copied twice)"
        return text[0].upper() + text[1:] + "."


def _junk(name: str) -> bool:
    low = name.lower()
    return low in _JUNK_NAMES or low.startswith(_JUNK_PREFIX) or low.endswith(_JUNK_SUFFIX)


def _same(a: os.stat_result, b: os.stat_result) -> bool:
    return a.st_size == b.st_size and abs(a.st_mtime - b.st_mtime) <= _MTIME_SLACK


def _numbered(path: Path, i: int) -> Path:
    return path if i == 1 else path.with_name(f"{path.stem}_{i}{path.suffix}")


def _where_to(src_st: os.stat_result, dst: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """(copy to, None) or (None, the existing identical copy). A different file
    with the same name is never replaced: the copy gets _2, _3 ..."""
    for i in range(1, 1000):
        cand = _numbered(dst, i)
        try:
            st = os.stat(long_path(cand))
        except FileNotFoundError:
            return cand, None
        except OSError:
            continue
        if _same(src_st, st):
            return None, cand
    raise OSError(f"too many copies named {dst.name}")


def _results_rel(nd2: Path, out_dir: Path) -> Path:
    """Where the results go inside the backup folder: OUTPUT_<movie>/<user> as
    next to the movie, so the backed-up movie finds its results."""
    if out_dir.parent.name.upper().startswith("OUTPUT_"):
        return Path(out_dir.parent.name) / out_dir.name
    if out_dir.name.upper().startswith("OUTPUT_"):
        return Path(out_dir.name)
    return Path(f"OUTPUT_{nd2.stem}") / out_dir.name


def _movie_folder(base: Path, nd2: Path, nd2_st: Optional[os.stat_result]) -> Path:
    """<base>/<movie stem>, or <stem>_2 ... if another movie of the same name was
    backed up there before."""
    for i in range(1, 1000):
        folder = base / (nd2.stem if i == 1 else f"{nd2.stem}_{i}")
        try:
            st = os.stat(long_path(folder / nd2.name))
        except OSError:
            return folder
        if nd2_st is None or _same(nd2_st, st):
            return folder
    return base / nd2.stem


def _cancelled(cancel) -> bool:
    if cancel is None:
        return False
    try:
        return bool(cancel.is_set() if hasattr(cancel, "is_set") else cancel())
    except Exception:                                              # noqa: BLE001
        return False


def _copy_one(src: Path, dst: Path, src_st: os.stat_result, report: BackupReport,
              progress, cancel) -> Optional[Path]:
    """Copy in chunks to a hidden partial file, give it the source's time, check
    its size, then give it its name (never over an existing file)."""
    make_dirs(dst.parent)
    part = dst.with_name(f".{dst.name}.peterpiper-partial")
    try:
        with open(long_path(src), "rb") as fi, open(long_path(part), "wb") as fo:
            while True:
                if _cancelled(cancel):
                    report.cancelled = True
                    break
                buf = fi.read(CHUNK)
                if not buf:
                    break
                fo.write(buf)
                report.bytes_copied += len(buf)
                if progress is not None:
                    progress(report.bytes_copied, report.total_bytes, src.name)
        if report.cancelled:
            raise InterruptedError
        os.utime(long_path(part), ns=(src_st.st_atime_ns, src_st.st_mtime_ns))
        got = os.stat(long_path(part)).st_size
        if got != src_st.st_size:
            raise OSError(f"the copy has {got} bytes instead of {src_st.st_size}")
        final = dst
        i = 1
        while os.path.exists(long_path(final)):        # appeared meanwhile
            i += 1
            final = _numbered(dst, i)
        os.rename(long_path(part), long_path(final))
        return final
    except BaseException:
        try:
            os.remove(long_path(part))
        except OSError:
            pass
        raise


def backup(nd2_path, out_dir, target_root, include_movie: bool = True,
           progress: Optional[Callable[[int, int, str], object]] = None,
           cancel=None) -> BackupReport:
    """Copy an analysis into <target_root>/PeterPiper backup/<movie stem>/:
    the results folder (OUTPUT_<movie>/<user>: sessions, ROI files, exports) and,
    with include_movie, the .nd2 itself. Nothing is ever overwritten: a file
    already there with the same size and time is skipped; a different one of the
    same name gets _2, _3 ... Each copy's size is checked. progress(done bytes,
    total bytes, file name) is called while copying; cancel (a function returning
    True, or a threading.Event) stops between chunks - what is half-copied is
    removed, what is fully copied stays. Runs fine in a worker thread."""
    nd2 = Path(plain_path(str(nd2_path)))
    out = Path(plain_path(str(out_dir))) if out_dir else None
    report = BackupReport()
    base = Path(plain_path(str(target_root))) / BACKUP_DIR
    why = folder_problem(base)
    if why:
        report.problem = f"PeterPiper cannot write in {plain_path(str(target_root))}: {why}."
        return report
    nd2_st = None
    if include_movie:
        try:
            nd2_st = os.stat(long_path(nd2))
        except OSError as exc:
            report.failed.append((str(nd2), error_text(exc)))
    folder = _movie_folder(base, nd2, nd2_st)
    report.folder = str(folder)

    todo: List[Tuple[Path, Path, os.stat_result]] = []
    if nd2_st is not None:
        todo.append((nd2, folder / nd2.name, nd2_st))
    if out is not None and os.path.isdir(long_path(out)):
        rel = _results_rel(nd2, out)
        for dirpath, dirnames, filenames in os.walk(long_path(out)):
            dirnames[:] = sorted(d for d in dirnames if not _junk(d))
            here = Path(plain_path(dirpath))
            for n in sorted(filenames):
                if _junk(n):
                    continue
                src = here / n
                try:
                    st = os.stat(long_path(src))
                except OSError as exc:
                    report.failed.append((str(src), error_text(exc)))
                    continue
                todo.append((src, folder / rel / src.relative_to(out), st))
    elif out is not None and not include_movie:
        report.problem = "this movie has no results folder yet."
        return report

    plan: List[Tuple[Path, Path, os.stat_result]] = []
    for src, dst, st in todo:
        try:
            to, same = _where_to(st, dst)
        except OSError as exc:
            report.failed.append((str(src), error_text(exc)))
            continue
        if same is not None:
            report.skipped.append((str(src), str(same)))
        else:
            plan.append((src, to, st))
    report.total_bytes = sum(st.st_size for _s, _d, st in plan)
    try:
        free = shutil.disk_usage(long_path(base)).free
        if free < report.total_bytes + 20_000_000:
            report.problem = (f"there is not enough space: {human_size(report.total_bytes)} "
                              f"needed, {human_size(free)} free.")
            return report
    except OSError:
        pass
    if progress is not None:
        progress(0, report.total_bytes, "")
    for src, dst, st in plan:
        if _cancelled(cancel):
            report.cancelled = True
            break
        try:
            final = _copy_one(src, dst, st, report, progress, cancel)
            report.copied.append((str(src), plain_path(str(final))))
        except InterruptedError:
            break
        except OSError as exc:
            report.failed.append((str(src), error_text(exc)))
    return report


# ------------------------------------------------- 1.2.2: a second copy of results
COPY_MANIFEST = ".peterpiper-copies.json"   # in each copied results folder: what we wrote


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(plain_path(str(p)))).rstrip("\\/")


def copy_target(nd2_path, out_dir, root) -> Path:
    """Where keep_copy puts this movie's results: <root>/OUTPUT_<movie>/<user>."""
    nd2 = Path(plain_path(str(nd2_path)))
    return Path(plain_path(str(root))) / _results_rel(nd2, Path(plain_path(str(out_dir))))


def _retrying(fn, cancel=None):
    """4.0: run a copy again when the error is one a sync app causes for a moment
    (file locked, cloud placeholder not ready, a time-out) - transfers.retry_call."""
    try:
        from .transfers import retry_call
    except Exception:                                              # noqa: BLE001
        return fn()
    return retry_call(fn, cancelled=lambda: _cancelled(cancel), retries=4, backoff=0.5)


def keep_copy(nd2_path, out_dir, root=None, extra=(), progress=None,
              cancel=None, include: Optional[Callable[[str], bool]] = None,
              ) -> BackupReport:
    """1.2.2: keep a second copy of this movie's results (OUTPUT_<movie>/<user>:
    autosaves, SAVEs, exports) in <root>/OUTPUT_<movie>/<user> (root: the user's
    'Also keep a copy in' folder). Only PeterPiper's own result files are copied -
    never the movie. New files are copied; identical ones skipped; a file that
    changed (an autosave written again) replaces OUR earlier copy only if that copy
    is untouched since we wrote it (remembered in COPY_MANIFEST) - any other file
    of the same name is kept and the new copy gets _2, _3 ... `extra`: further
    folders to copy in as <copy>/<their name> (an export saved outside the results
    folder). 4.0: include(relative posix path) -> bool picks which files (None:
    all); a copy that fails for a moment (a sync app holding the file) is tried
    again. Never raises; runs fine in a worker thread."""
    report = BackupReport()
    root = root if root is not None else copy_root()
    if not root:
        report.problem = "no folder is set for a second copy."
        return report
    try:
        out = Path(plain_path(str(out_dir)))
        dst_root = copy_target(nd2_path, out, root)
        report.folder = str(dst_root)
        if _norm(dst_root) == _norm(out):
            report.problem = "the second copy would be the results folder itself."
            return report
        why = folder_problem(Path(plain_path(str(root))))
        if why:
            report.problem = f"PeterPiper cannot write in {plain_path(str(root))}: {why}."
            return report
        man_p = dst_root / COPY_MANIFEST
        try:
            man = json.loads(open(long_path(man_p), encoding="utf-8").read())
            man = man if isinstance(man, dict) else {}
        except (OSError, ValueError):
            man = {}
        sources = [(out, Path("."))] + [(Path(plain_path(str(e))), Path(Path(str(e)).name))
                                        for e in extra if e]
        plan = []
        for base, sub in sources:
            if not os.path.isdir(long_path(base)):
                continue
            if base != out and _norm(base).startswith(_norm(out) + os.sep):
                continue                        # inside the results folder: copied anyway
            for dirpath, dirnames, filenames in os.walk(long_path(base)):
                dirnames[:] = sorted(d for d in dirnames if not _junk(d))
                here = Path(plain_path(dirpath))
                for n in sorted(filenames):
                    if _junk(n) or n == COPY_MANIFEST:
                        continue
                    src = here / n
                    rel = (sub / src.relative_to(base)).as_posix()
                    if include is not None and not include(rel):
                        continue
                    try:
                        st = os.stat(long_path(src))
                    except OSError as exc:
                        report.failed.append((str(src), error_text(exc)))
                        continue
                    dst = dst_root / rel
                    try:
                        dst_st = os.stat(long_path(dst))
                    except FileNotFoundError:
                        plan.append((src, dst, st, rel, False))
                        continue
                    except OSError as exc:
                        report.failed.append((str(src), error_text(exc)))
                        continue
                    if _same(st, dst_st):
                        report.skipped.append((str(src), str(dst)))
                    elif man.get(rel) == [dst_st.st_size, dst_st.st_mtime_ns]:
                        plan.append((src, dst, st, rel, True))      # our own older copy
                    else:
                        try:
                            to, same = _where_to(st, dst)
                        except OSError as exc:
                            report.failed.append((str(src), error_text(exc)))
                            continue
                        if same is not None:
                            report.skipped.append((str(src), str(same)))
                        else:
                            plan.append((src, to, st, None, False))
        report.total_bytes = sum(p[2].st_size for p in plan)
        for src, dst, st, rel, replace in plan:
            if _cancelled(cancel):
                report.cancelled = True
                break
            try:
                start = report.bytes_copied
                if replace:
                    tmp = dst.with_name(f"{dst.name}.peterpiper-new")

                    def one(src=src, tmp=tmp, st=st, start=start):
                        report.bytes_copied = start
                        return _copy_one(src, tmp, st, report, progress, cancel)
                    final = _retrying(one, cancel)
                    os.replace(long_path(final), long_path(dst))
                    final = dst
                else:
                    def one(src=src, dst=dst, st=st, start=start):
                        report.bytes_copied = start
                        return _copy_one(src, dst, st, report, progress, cancel)
                    final = _retrying(one, cancel)
                if rel is not None and Path(final) == dst:
                    fst = os.stat(long_path(final))
                    man[rel] = [fst.st_size, fst.st_mtime_ns]
                report.copied.append((str(src), plain_path(str(final))))
            except InterruptedError:
                break
            except OSError as exc:
                report.failed.append((str(src), error_text(exc)))
        if report.copied:
            try:
                make_dirs(dst_root)
                tmp = man_p.with_name(man_p.name + ".tmp")
                with open(long_path(tmp), "w", encoding="utf-8") as fh:
                    json.dump(man, fh)
                os.replace(long_path(tmp), long_path(man_p))
            except OSError:
                pass
    except Exception as exc:                                       # noqa: BLE001
        report.problem = error_text(exc)
    return report


def copy_root() -> str:
    """1.2.2: the user's 'Also keep a copy in' folder, or '' (off)."""
    return _get("copy_root")


def set_copy_root(path, check: bool = True) -> None:
    """None / '' = off. A folder that cannot be written is refused (ValueError)."""
    _set("copy_root", path, check)


# ----------------------------------------------------- where things go (per user)
def _get(key: str) -> str:
    from . import userprefs
    return str(userprefs.load(TOPIC).get(key) or "")


def _set(key: str, path, check: bool) -> None:
    from . import userprefs
    d = userprefs.load(TOPIC)
    if path:
        p = os.path.abspath(plain_path(os.fspath(path)))
        if check:
            why = folder_problem(p)
            if why:
                raise ValueError(f"PeterPiper cannot write in {p}: {why}.")
        d[key] = p
    else:
        d.pop(key, None)
    userprefs.save(TOPIC, d)


def results_root() -> str:
    """The folder this user's results go to (OUTPUT_<movie>/<user> inside it),
    or '' = next to each movie (the default)."""
    return _get("results_root")


def set_results_root(path, check: bool = True) -> None:
    """None / '' = next to each movie again. A folder that cannot be written is
    refused (ValueError with the reason in plain words)."""
    _set("results_root", path, check)


def backup_root() -> str:
    """Where this user's backups go (<it>/PeterPiper backup/...), or ''."""
    return _get("backup_root")


def set_backup_root(path, check: bool = True) -> None:
    _set("backup_root", path, check)


def cloud_roots_fallback() -> List[Tuple[str, str]]:
    """4.0: [(service, path)] of the sync apps' folders on this computer (no network
    drives - they are not searched). Used when platforms.cloud_roots (the "launch"
    part) is not there."""
    out = []
    for p in places():
        if p.service != NETWORK and _isdir(p.path):
            out.append((p.service, p.path))
    return out


def suggested_results_folder(place: Place) -> str:
    """A results folder in a place: <place>/PeterPiper results (a network drive
    or a shared library: the same), so OUTPUT_ folders do not fill its top."""
    return str(Path(place.path) / RESULTS_DIR)
