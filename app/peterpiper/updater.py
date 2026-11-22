"""
Check for updates (PeterPiper 1.2) - the ONLY place PeterPiper uses the network,
and only when you press "Check for updates".

What it sends: one HTTPS request to GitHub's public release list of this project
(api.github.com/repos/<owner>/PeterPiper/releases/latest), and - only when you
choose to update - the download of that release's file. No name, file, path or
result of yours is sent; the request carries only a generic User-Agent.

What it changes (never your data: profiles, settings, run lists, saved files,
logs and results live in "PeterPiper data" and next to your movies - outside the
program folder - and are never touched):
4.0: ONE release zip (PeterPiperV<x.y>.zip) for Windows AND macOS - the same
files, started with the .bat (Windows) or the .command (Mac). So a zip install
updates the same way on both systems:
- a release of the same program folder (e.g. 4.0.0 -> 4.0.1, same
  PeterPiperV4.0 and the same package list): only the program files that differ
  from the release zip are replaced; each replaced file is first copied to
  <program folder>/_update_backup/<old version>_<time>/. Nothing outside the
  zip's own file list is touched. The file permissions stored in the zip are
  kept (the Mac launcher stays double-clickable).
- a release with a new program folder or new packages: the release is unpacked
  into its own new folder next to this one (never over an existing folder) -
  start it with its own .bat / .command; this version stays as it is.
- the self-contained Mac app (an optional .dmg): the .dmg for this Mac (Apple
  chip or Intel) is saved in Downloads (never over an existing file) and opened;
  a release without one: the zip is saved in Downloads and shown in Finder.
- A developer copy (a git checkout) is never changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import APP_NAME, PROJECT_URL, __version__, platforms

API = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT_S = 20
# never written by an update, whatever a zip contains
PROTECTED = re.compile(r"(^|/)(_out|_work|_home|out|logs?|_update_backup|\.git|__pycache__)(/|$)"
                       r"|\.lnk$|\.pyc$", re.I)


# ------------------------------------------------------------------ versions
def parse_version(text: str) -> tuple:
    """'v1.10.2' / '1.1' -> (1, 10, 2) / (1, 1, 0)."""
    nums = [int(x) for x in re.findall(r"\d+", str(text))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


def repo() -> str:
    """'owner/name' from PROJECT_URL."""
    m = re.search(r"github\.com/([^/]+/[^/#?]+)", PROJECT_URL or "")
    return m.group(1).removesuffix(".git") if m else ""


# ------------------------------------------------------------------ network (only here)
_CTX = None


def _ssl_context():
    """The certificates to trust. The Mac app carries its own Python, which may not
    find the system's certificates: there the ones macOS itself trusts are used
    (exported read-only with Apple's 'security' tool). Elsewhere: Python's default."""
    global _CTX
    if _CTX is not None:
        return _CTX
    import ssl
    ctx = ssl.create_default_context()
    if platforms.IS_MAC:
        try:
            import subprocess
            pem = subprocess.run(
                ["/usr/bin/security", "find-certificate", "-a", "-p",
                 "/System/Library/Keychains/SystemRootCertificates.keychain"],
                capture_output=True, text=True, timeout=20).stdout
            if "BEGIN CERTIFICATE" in pem:
                ctx.load_verify_locations(cadata=pem)
        except Exception:                                          # noqa: BLE001
            pass
    _CTX = ctx
    return ctx


def _get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    import urllib.request
    req = urllib.request.Request(url, headers={"Accept": accept,
                                               "User-Agent": "PeterPiper-update-check"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S,              # noqa: S310 (https only)
                                context=_ssl_context()) as r:
        return r.read()


def fetch_latest() -> dict:
    """The newest release: {"version", "tag", "notes", "url", "assets": [{name, url, size}]}."""
    r = repo()
    if not r:
        raise RuntimeError("This copy of PeterPiper does not know its project page.")
    d = json.loads(_get(API.format(repo=r)).decode("utf-8"))
    return {"version": ".".join(map(str, parse_version(d.get("tag_name", "")))),
            "tag": d.get("tag_name", ""), "notes": d.get("body") or "",
            "url": d.get("html_url") or PROJECT_URL,
            "assets": [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""),
                        "size": int(a.get("size") or 0)} for a in d.get("assets", [])]}


def download(url: str, dest: Path, size: int = 0,
             progress: Optional[Callable[[float, str], object]] = None) -> Path:
    """Stream a release file to dest (chunked); checks the size when GitHub gave one."""
    import urllib.request
    if not url.startswith("https://"):
        raise RuntimeError("Refusing a download that is not https.")
    req = urllib.request.Request(url, headers={"User-Agent": "PeterPiper-update-check"})
    done = 0
    with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=_ssl_context()) as r,             open(dest, "wb") as f:                                   # noqa: S310
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            done += len(b)
            if progress and size:
                progress(min(0.99, done / size), f"Downloading... {done / 1e6:.0f} of "
                                                 f"{size / 1e6:.0f} MB\n{dest}")
            elif progress:                          # 1.2: no size known - a moving bar
                progress(None, f"Downloading... {done / 1e6:.0f} MB\n{dest}")
    if size and done != size:
        raise RuntimeError(f"The download is incomplete ({done} of {size} bytes).")
    return dest


# ------------------------------------------------------------------ this installation
def program_folder() -> Path:
    """The folder holding PeterPiperVx.y.bat / .command and app/ (a zip install)."""
    return Path(__file__).resolve().parents[2]


def launcher_name(sysn: Optional[str] = None) -> str:
    """4.0: the file that starts PeterPiper on this system (the same zip holds both)."""
    return f"{APP_NAME}.command" if platforms._mac(sysn) else f"{APP_NAME}.bat"


def kind_of_install(folder: Optional[Path] = None) -> str:
    """'mac_app' (the self-contained app) | 'developer' (git checkout) | 'zip' (the
    release zip, Windows or Mac) | 'unknown'."""
    if getattr(sys, "frozen", False):
        return "mac_app" if platforms.IS_MAC else "unknown"
    f = folder or program_folder()
    if (f / ".git").exists():
        return "developer"
    if (f / "app" / "peterpiper").is_dir() and (any(f.glob("PeterPiperV*.bat"))
                                                 or any(f.glob("PeterPiperV*.command"))):
        return "zip"
    return "unknown"


def _the_zip(names: List[dict]) -> Optional[dict]:
    return next((a for a in names if re.fullmatch(r"PeterPiperV[\d.]+\.zip", a["name"])), None)


def pick_asset(rel: dict, kind: str, machine: Optional[str] = None) -> Optional[dict]:
    """The release file for this install. 4.0: the ONE zip for Windows and Mac
    zip installs; the self-contained Mac app takes its .dmg (Apple chip / Intel)
    when the release has one, else the zip (saved for the user to unpack)."""
    names = rel.get("assets", [])
    if kind == "mac_app":
        m = (machine or platform.machine()).lower()
        tag = "AppleChip" if m in ("arm64", "aarch64") else "Intel"
        dmg = next((a for a in names if a["name"].endswith(f"-macOS-{tag}.dmg")), None)
        return dmg or _the_zip(names)
    return _the_zip(names)


# ------------------------------------------------------------------ applying a zip
def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_zip(zpath: Path) -> tuple:
    """(top folder name, {relative path: ZipInfo}) of a release zip; refuses unsafe paths."""
    z = zipfile.ZipFile(zpath)
    bad = z.testzip()
    if bad:
        raise RuntimeError(f"The downloaded file is damaged ({bad}).")
    tops, files = set(), {}
    for zi in z.infolist():
        name = zi.filename.replace("\\", "/")
        parts = name.split("/")
        if name.startswith("/") or ".." in parts or ":" in parts[0]:
            raise RuntimeError(f"Unsafe path in the update: {name}")
        tops.add(parts[0])
        if not zi.is_dir() and len(parts) > 1:
            files["/".join(parts[1:])] = zi
    if len(tops) != 1:
        raise RuntimeError("The update has an unexpected layout.")
    return tops.pop(), files


def plan(zpath: Path, folder: Path) -> dict:
    """What an update from this zip would do: {"mode": "in_place" | "new_folder",
    "top", "changed": [...], "new": [...], "why"}."""
    top, files = read_zip(zpath)
    z = zipfile.ZipFile(zpath)
    same_folder = top == folder.name or top == APP_NAME
    req = "app/requirements.txt"
    same_req = (req in files and (folder / req).exists()
                and z.read(files[req]) == (folder / req).read_bytes())
    changed, new = [], []
    for rel, zi in files.items():
        if PROTECTED.search(rel):
            continue
        local = folder / rel
        if not local.exists():
            new.append(rel)
        elif hashlib.sha256(z.read(zi)).hexdigest() != _sha(local):
            changed.append(rel)
    if same_folder and same_req:
        return {"mode": "in_place", "top": top, "changed": sorted(changed), "new": sorted(new),
                "why": ""}
    why = ("its program folder is new" if not same_folder else "it needs other packages")
    return {"mode": "new_folder", "top": top, "changed": sorted(changed), "new": sorted(new),
            "why": why}


def apply_in_place(zpath: Path, folder: Path, p: dict) -> dict:
    """Replace the changed program files and add new ones (backups first)."""
    _top, files = read_zip(zpath)
    z = zipfile.ZipFile(zpath)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup = folder / "_update_backup" / f"{__version__}_{stamp}"
    done = []
    for rel in p["changed"] + p["new"]:
        if PROTECTED.search(rel):
            continue
        dst = folder / rel
        root = str(folder.resolve())
        if not (str(dst.resolve()) + os.sep).startswith(root.rstrip(os.sep) + os.sep):
            continue
        old_mode = None
        if dst.exists():
            old_mode = dst.stat().st_mode
            b = backup / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, b)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".update-tmp")
        tmp.write_bytes(z.read(files[rel]))
        _set_mode(tmp, files[rel], old_mode)
        os.replace(tmp, dst)
        done.append(rel)
    return {"replaced": done, "backup": str(backup) if backup.exists() else ""}


def zip_mode(zi: zipfile.ZipInfo) -> int:
    """The unix permission bits stored in a zip entry (0 when it has none)."""
    return (zi.external_attr >> 16) & 0o777 if zi.create_system == 3 else 0


def _set_mode(path: Path, zi: zipfile.ZipInfo, old_mode: Optional[int] = None) -> None:
    """4.0 (Mac): keep a file runnable - the zip's permission bits (0755 for the
    .command launcher), else the replaced file's own. Nothing to do on Windows."""
    if platforms.IS_WIN:
        return
    mode = zip_mode(zi) or (old_mode & 0o777 if old_mode else 0)
    if mode:
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def unpack_new_folder(zpath: Path, folder: Path) -> Path:
    """Unpack into <parent of this folder>/<zip's top folder>; never over an existing one."""
    top, files = read_zip(zpath)
    dest = folder.parent / top
    if dest.exists():
        raise RuntimeError(f"A folder named {top} is already next to this one: {dest}. "
                           "Start PeterPiper from there, or move it away first.")
    tmp = Path(tempfile.mkdtemp(prefix="pp-update-", dir=folder.parent))
    try:
        zipfile.ZipFile(zpath).extractall(tmp)
        for rel, zi in files.items():                  # 4.0: Python's unzip drops them
            _set_mode(tmp / top / rel, zi)
        os.replace(tmp / top, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest
