"""
Remembering earlier analyses of the same .nd2 file (v2.3).

When an .nd2 is opened, find_previous_runs() lists the ROI files made for it
before - the session files the app keeps up to date as you work, exported ROI
files and files saved with File > Save ROIs now - so the GUI can offer to load
one (with its tracking) or to start a fresh analysis.

Two sources, combined:
  1. A scan next to the data: the results folder, <nd2 folder>/OUTPUT_<name>/,
     the folders older versions used (ROInav_results/, PD4nav*_results/) and
     the .nd2's own folder. A file counts if it was saved for an .nd2 of the
     same name (or the same fingerprint) and the same image size.
  2. A small per-computer index, run_history.json in the settings folder
     (~/.<APP_NAME> or $PETERPIPER_HOME), keyed by the .nd2's fingerprint. It finds
     earlier runs even when the .nd2 was moved or renamed, or the results were
     written to another folder.

The fingerprint identifies a file by its CONTENT, not its name: SHA-1 of the
file size plus the first and last 4 MiB (the whole file if it is <= 8 MiB).
For an .nd2 that is the file header, the first images and the metadata/index
at the end - different acquisitions never share these. It reads at most 8 MiB,
so it takes milliseconds even for a 4 GB movie.

Everything here is best-effort: nothing raises into the GUI, and nothing is
ever written next to the data (only run_history.json in the settings folder).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import APP_NAME, users
from .roifile import COMP_WORDS, read_summary
from .safety import is_dir, long_path, plain_path, replace_own_file
from .safety import exists as _exists

QUICK_BYTES = 4 * 1024 * 1024        # fingerprint: first and last 4 MiB
INDEX_NAME = "run_history.json"
SESSION_DIR = "PeterPiper_sessions"
LEGACY_SESSION_DIRS = ("PD4nav_sessions",)    # where PD4nav saved them (still read)
MAX_RUNS_PER_FILE = 100              # index: runs remembered per .nd2
MAX_FILES_IN_INDEX = 2000            # index: .nd2 files remembered (oldest dropped)
SCAN_MAX_FILES = 300                 # ROI files looked at per search (newest first)
SCAN_MAX_ENTRIES = 20000             # folder entries looked at per search
SCAN_SECONDS = 1.5                   # stop scanning after this long

_FP_CACHE: Dict[tuple, dict] = {}


# --------------------------------------------------------------------- places
def home_dir() -> Path:
    """The settings folder: $PETERPIPER_HOME, else ~/.<APP_NAME> (same as config)."""
    try:
        from .config import _settings_file
        return _settings_file().parent
    except Exception:                                          # noqa: BLE001
        custom = os.environ.get("PETERPIPER_HOME")
        return Path(custom) if custom else Path.home() / f".{APP_NAME}"


def session_dir(out_dir) -> Path:
    """<results folder>/PeterPiper_sessions - where the session files live."""
    return Path(out_dir) / SESSION_DIR


def session_path(out_dir, nd2_path, session_id: str) -> Path:
    """<results folder>/PeterPiper_sessions/<nd2 name[:40]>_session_<id>.npz"""
    return session_dir(out_dir) / f"{Path(nd2_path).stem[:40]}_session_{session_id}.npz"


def new_session_id() -> str:
    """A new session id: the local date and time, e.g. '2026-10-29_17-26-39'."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


# ---------------------------------------------------------------- fingerprint
def nd2_fingerprint(path) -> dict:
    """{"name", "size", "mtime", "quick"}: quick = SHA-1 of the size and the
    first and last 4 MiB. quick is "" if the file cannot be read (never raises)."""
    p = Path(path)
    fp = {"name": p.name, "size": 0, "mtime": 0.0, "quick": ""}
    try:
        st = os.stat(long_path(p))
        key = (os.path.normcase(os.path.abspath(p)), st.st_size, st.st_mtime_ns)
        if key in _FP_CACHE:
            return dict(_FP_CACHE[key])
        h = hashlib.sha1()
        h.update(str(st.st_size).encode("ascii"))
        with open(long_path(p), "rb") as f:
            h.update(f.read(QUICK_BYTES))
            if st.st_size > QUICK_BYTES:
                f.seek(max(QUICK_BYTES, st.st_size - QUICK_BYTES))
                h.update(f.read(QUICK_BYTES))
        fp.update(size=int(st.st_size), mtime=round(st.st_mtime, 3), quick=h.hexdigest())
        _FP_CACHE[key] = dict(fp)
    except (OSError, ValueError):
        pass
    return fp


def same_file(fp_a, fp_b) -> bool:
    """True if two fingerprints are the same file contents (it may have been
    moved or renamed in between)."""
    try:
        return bool(fp_a and fp_b and fp_a.get("quick")
                    and fp_a.get("quick") == fp_b.get("quick")
                    and int(fp_a.get("size", -1)) == int(fp_b.get("size", -2)))
    except (AttributeError, TypeError, ValueError):
        return False


# -------------------------------------------------------------------- RunInfo
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
KIND_WORDS = {"session": "autosave", "export": "export", "saved": "saved"}


def _when(saved: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(saved))
    except (TypeError, ValueError):
        return None


@dataclass
class RunInfo:
    """One earlier analysis of this .nd2 (an ROI or session file)."""
    path: str
    saved: str                     # ISO local time
    version: str                   # version of the app that wrote it ("" = PD4nav before v2.0)
    kind: str                      # "session" | "export" | "saved"
    n_cells: int
    comps: List[str]
    tracked: bool                  # the file holds the tracking (every ROI at every timepoint)
    n_timepoints: int              # of the tracking (0 = not known)
    rules: List[str]               # tracking rules as text
    nd2_name: str                  # the .nd2 it was saved for
    match: str                     # "same file" | "same name" | "renamed copy"
    t0: Optional[int] = None       # drawn timepoint, 0-based
    prefix: str = ""               # export name
    note: str = ""                 # plain-language caution for the user, "" = none
    summary: dict = field(default_factory=dict, repr=False)   # roifile.read_summary()
    same_as: List[str] = field(default_factory=list, repr=False)   # identical older files
    app: str = "PD4nav"            # the app that wrote it (files without the name: PD4nav)

    def label(self) -> str:
        """One line for a list, e.g.
        '29 Oct 2026 17:26 · V2.2 · 10 cells · mitochondria · tracked ✓ · export'"""
        d = _when(self.saved)
        when = f"{d.day} {_MONTHS[d.month - 1]} {d.year} {d:%H:%M}" if d else str(self.saved)
        v = str(self.version or "")
        if v.endswith(".0") and v.count(".") >= 2:
            v = v[:-2]
        parts = [when, f"{self.app} {v}" if v else "older version",
                 f"{self.n_cells} cell{'' if self.n_cells == 1 else 's'}",
                 " + ".join(COMP_WORDS.get(c, c) for c in self.comps) or "no ROIs",
                 "tracked ✓" if self.tracked else "not tracked",
                 KIND_WORDS.get(self.kind, self.kind)]
        if self.match == "renamed copy" and self.nd2_name:
            parts.append(f"saved for {self.nd2_name}")
        return " · ".join(parts)


def _sort_key(r: RunInfo):
    d = _when(r.saved)
    return (d.timestamp() if d else 0.0, 1 if r.tracked else 0)


# ---------------------------------------------------------------------- index
OLD_HOMES: tuple = ()     # PeterPiper 1.0 starts empty: no PD4nav run index is taken over


def _index_path() -> Path:
    p = home_dir() / INDEX_NAME
    if not p.exists() and not os.environ.get("PETERPIPER_HOME") and users.gets_old_data():
        _carry_over_index(p)
    return p


def _carry_over_index(new: Path) -> None:
    """V2.5: on first use, the run indexes of the earlier versions on this
    computer are merged into this version's (they are only read, never changed),
    so 'Compare / average runs' and 'Analysed before' know the earlier runs."""
    merged: dict = {}
    for d in OLD_HOMES:
        try:
            data = json.loads((Path.home() / d / INDEX_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key, ent in data.items():
            if not (isinstance(key, str) and isinstance(ent, dict)):
                continue
            cur = merged.setdefault(key, dict(ent, runs=[], paths=[]))
            have = {r.get("path") for r in cur["runs"]}
            cur["runs"] += [r for r in _as_list(ent.get("runs")) if isinstance(r, dict)
                            and isinstance(r.get("path"), str) and r["path"] not in have]
            cur["paths"] += [q for q in _as_list(ent.get("paths"))
                             if isinstance(q, str) and q not in cur["paths"]]
    if merged:
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            with replace_own_file(new) as stream:
                stream.write(json.dumps(merged, indent=1).encode("utf-8"))
        except OSError:
            pass


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(plain_path(str(p))))


class IndexUnreadable(Exception):
    """The run index exists but could not be read (locked, no permission ...):
    it must not be overwritten with a smaller one."""


def _load_index(strict: bool = False) -> dict:
    """The run index; {} if missing. A damaged file is kept aside as
    run_history.corrupt.json and treated as empty. Any other read error gives {}
    for reading, but raises IndexUnreadable when strict (before a write), so a
    file that is only briefly locked is never replaced by an empty index."""
    p = _index_path()
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        if strict:
            raise IndexUnreadable(str(exc)) from exc
        return {}
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not a dict")
    except ValueError:
        try:
            os.replace(p, p.with_name("run_history.corrupt.json"))
        except OSError:
            pass
        return {}
    out = {}
    for key, ent in data.items():
        if isinstance(key, str) and isinstance(ent, dict):
            runs = [r for r in _as_list(ent.get("runs")) if isinstance(r, dict)
                    and isinstance(r.get("path"), str)]
            paths = [q for q in _as_list(ent.get("paths")) if isinstance(q, str)]
            out[key] = dict(ent, runs=runs, paths=paths)
    return out


def _as_list(v) -> list:
    return v if isinstance(v, list) else []


def _save_index(data: dict) -> None:
    with replace_own_file(_index_path()) as stream:
        stream.write(json.dumps(data, indent=1).encode("utf-8"))


LOCK_STALE_S = 30.0                    # a lock older than this was left by a crash


class _IndexLock:
    """Two PeterPiper windows / processes may record runs at the same moment: each
    takes run_history.lock (created exclusively) around read + merge + write, so
    neither loses the other's run. Gives up after `wait` s (then no write)."""

    def __init__(self, wait: float = 5.0):
        self.path = _index_path().with_name("run_history.lock")
        self.wait = wait
        self.fd = None

    def __enter__(self):
        end = time.monotonic() + self.wait
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii"))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_S:
                        os.unlink(self.path)
                        continue
                except OSError:
                    pass
            except OSError as exc:
                raise IndexUnreadable(str(exc)) from exc
            if time.monotonic() > end:
                raise IndexUnreadable("run_history.lock is held by another PeterPiper")
            time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            os.close(self.fd)
        finally:
            try:
                os.unlink(self.path)
            except OSError:
                pass
        return False


# ------------------------------------------------------- V3.0: moved data
MOVED_NAME = "moved_data.json"          # in the user's folder: [[old prefix, new prefix]]


def _moves() -> List[List[str]]:
    try:
        d = json.loads((home_dir() / MOVED_NAME).read_text(encoding="utf-8"))
        return [[str(a), str(b)] for a, b in d if a and b] if isinstance(d, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _add_move(old: str, new: str) -> None:
    moves = [m for m in _moves() if _norm(m[0]) != _norm(old)] + [[old, new]]
    try:
        with replace_own_file(home_dir() / MOVED_NAME) as stream:
            stream.write(json.dumps(moves, indent=1).encode("utf-8"))
    except Exception:                                          # noqa: BLE001
        pass


def resolve(path) -> str:
    """A run's path on this computer: as recorded, else under a place its data was
    moved to ('My data is in...': the remembered old -> new folder prefixes)."""
    p = str(path)
    if _exists(p):
        return p
    low = _norm(p)
    for old, new in reversed(_moves()):
        o = _norm(old).rstrip("\\/")
        if low.startswith(o + os.sep) or low.startswith(o + "/"):
            cand = str(Path(new) / p[len(old.rstrip("\\/")) + 1:])
            if _exists(cand):
                return cand
    return p


def missing_runs() -> List[dict]:
    """Runs in the user's list whose file is not on this computer (not even under
    a remembered new place): [{path, nd2_name, saved}]."""
    out = []
    try:
        for key, ent in _load_index().items():
            for r in ent.get("runs", []):
                if r.get("tracked") and not _exists(resolve(r["path"])):
                    out.append(dict(path=str(r["path"]), nd2_name=str(ent.get("nd2_name") or ""),
                                    saved=str(r.get("saved") or ""), key=str(key)))
    except Exception:                                          # noqa: BLE001
        pass
    return out


def _common_move(old: str, new: str):
    """The folder prefixes that turn `old` into `new` (the longest common file-name
    tail removed): ('D:/lab/2026', 'E:/copy/2026') for D:/lab/2026/a/b.npz ->
    E:/copy/2026/a/b.npz."""
    po, pn = Path(old).parts, Path(new).parts
    k = 0
    while k < min(len(po), len(pn)) and po[-1 - k].lower() == pn[-1 - k].lower():
        k += 1
    if k == 0 or k >= len(po) or k >= len(pn):
        return None
    return str(Path(*po[:len(po) - k])), str(Path(*pn[:len(pn) - k]))


def relocate_runs(folder, progress=None) -> dict:
    """V3.0 'My data is in...': the user's runs missing on this computer are looked
    for under `folder` (subfolders included) and matched EXACTLY - same movie
    fingerprint, same file name, same save time; each match's new place is
    remembered (moved_data.json), so later runs from the same old folder are found
    too. {"found": n, "still_missing": n, "moves": [[old, new], ...]}."""
    missing = missing_runs()
    if not missing:
        return dict(found=0, still_missing=0, moves=[])
    want = {}
    for r in missing:
        want.setdefault(Path(r["path"]).name.lower(), []).append(r)
    found, moves = 0, []
    stack = [Path(plain_path(str(folder)))]
    seen = 0
    while stack and want:
        d = stack.pop()
        try:
            entries = list(os.scandir(long_path(d)))
        except OSError:
            continue
        for e in entries:
            if e.is_dir(follow_symlinks=False):
                if not (e.name.startswith("$") or e.name.startswith(".")):
                    stack.append(d / e.name)
                continue
            cands = want.get(e.name.lower())
            if not cands:
                continue
            seen += 1
            if progress is not None and progress(None, f"{found} found - {d.name}") is False:
                break
            sm = read_summary(d / e.name) or {}
            fpq = str((sm.get("fingerprint") or {}).get("quick") or "")
            for r in list(cands):                  # same movie, same file name, same save time
                if str(sm.get("saved") or "") == r["saved"] and (not fpq or fpq == r["key"]):
                    mv = _common_move(r["path"], str(d / e.name))
                    if mv is not None and mv not in moves:
                        moves.append(mv)
                        _add_move(*mv)
                    cands.remove(r)
                    found += 1
            if not cands:
                want.pop(e.name.lower(), None)
    return dict(found=found, still_missing=len(missing_runs()), moves=moves)


def find_runs_in_folder(folder, progress=None) -> dict:
    """V3.0 'Find my runs in a folder...': every PeterPiper ROI / session file with
    tracking under `folder` (subfolders included; the recycle bin and hidden
    folders skipped). progress(fraction or None, text) -> False stops.
    {"mine": [paths], "others": n (other users' runs, not listed), "untracked": n}."""
    mine: List[str] = []
    others = untracked = 0
    stack = [Path(plain_path(str(folder)))]
    seen = 0
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(long_path(d)))
        except OSError:
            continue
        for e in entries:
            name = e.name
            if e.is_dir(follow_symlinks=False):
                if not (name.startswith("$") or name.startswith(".")):
                    stack.append(d / name)
                continue
            if not name.lower().endswith(".npz"):
                continue
            seen += 1
            if progress is not None and progress(None, f"{seen} file(s) checked - {d.name}")                     is False:
                return dict(mine=mine, others=others, untracked=untracked)
            p = d / name
            s = read_summary(p)
            if s is None:
                continue
            if not s.get("tracked"):
                untracked += 1
                continue
            if not users.is_mine(str(p), s.get("user")):
                others += 1
                continue
            mine.append(str(p))
    return dict(mine=sorted(mine), others=others, untracked=untracked)


def record_run(nd2_path, run_path, summary: Optional[dict] = None) -> None:
    """Add an ROI / session file to the per-computer index of runs for this
    .nd2 (keyed by its fingerprint). Prunes this .nd2's runs whose file is
    gone. Best-effort: never raises."""
    try:
        run = Path(plain_path(run_path))
        if not _exists(run):
            return
        summary = summary or read_summary(run) or {}
        fp = nd2_fingerprint(nd2_path) if nd2_path else {}
        if not fp.get("quick"):
            fp = summary.get("fingerprint") or {}
        key = fp.get("quick")
        if not key:
            return
        now = datetime.now().isoformat(timespec="seconds")
        with _IndexLock():
            _record_locked(key, fp, nd2_path, run, summary, now)
    except Exception:                                          # noqa: BLE001
        pass


def _record_locked(key, fp, nd2_path, run, summary, now) -> None:
    """record_run's read + merge + write, under the index lock. The index is
    read again here (another PeterPiper may have added runs since this one last read
    it); an index that exists but cannot be read is never overwritten."""
    idx = _load_index(strict=True)
    ent = idx.get(key) or {}
    name = Path(nd2_path).name if nd2_path else str(fp.get("name") or "")
    paths = [q for q in ent.get("paths", []) if not nd2_path or _norm(q) != _norm(nd2_path)]
    if nd2_path:
        paths.append(str(Path(nd2_path).absolute()))
    me = _norm(run)
    # V3.0 portable profiles: runs missing here are KEPT (they may be on another
    # computer, or moved - 'My data is in...' finds them again); only the oldest go
    runs = [r for r in ent.get("runs", []) if _norm(r["path"]) != me]
    runs.append(dict(path=str(run.absolute()), saved=summary.get("saved", now),
                     kind=summary.get("kind", ""), tracked=bool(summary.get("tracked")),
                     n_cells=int(summary.get("n_cells") or 0), recorded=now))
    idx[key] = dict(nd2_name=name, size=int(fp.get("size") or 0), paths=paths[-10:],
                    runs=runs[-MAX_RUNS_PER_FILE:], last=now)
    if len(idx) > MAX_FILES_IN_INDEX:                  # forget the longest-unused files
        keep = sorted(idx, key=lambda k: str(idx[k].get("last", "")))[-MAX_FILES_IN_INDEX:]
        idx = {k: idx[k] for k in keep}
    _save_index(idx)


# ----------------------------------------------------------------------- scan
def _wanted(name: str) -> bool:
    low = name.lower()
    return low.endswith(".npz") and ("_rois" in low or "_session" in low)


def _scan(roots, budget: dict) -> List[str]:
    """ROI / session files under each (folder, depth), without following links."""
    out: List[str] = []
    for root, depth in roots:
        stack = [(str(root), depth)]
        while stack:
            if budget["entries"] <= 0 or time.perf_counter() > budget["until"]:
                return out
            folder, d = stack.pop()
            try:
                with os.scandir(long_path(folder)) as it:
                    for e in it:
                        budget["entries"] -= 1
                        if budget["entries"] <= 0:
                            break
                        try:
                            if e.is_dir(follow_symlinks=False):
                                if d > 0:
                                    stack.append((plain_path(e.path), d - 1))
                            elif _wanted(e.name) and e.is_file():
                                out.append(plain_path(e.path))
                        except OSError:
                            continue
            except OSError:
                continue
    return out


def _roots(nd2: Path, out_dir) -> list:
    """(folder, depth) to scan, most specific first, without duplicates."""
    here = nd2.parent
    roots = []
    if out_dir:
        roots.append((Path(out_dir), 3))
    roots.append((here / f"OUTPUT_{nd2.stem}", 4))
    if nd2.stem[:40] != nd2.stem:
        roots.append((here / f"OUTPUT_{nd2.stem[:40]}", 4))
    roots.append((here / "ROInav_results", 1))
    roots.append((users.results_home() / f"OUTPUT_{nd2.stem}", 4))   # 1.0.3: read-only drives
    try:
        with os.scandir(long_path(here)) as it:
            for e in it:
                low = e.name.lower()
                if low.startswith("pd4nav") and low.endswith("_results") and e.is_dir():
                    roots.append((Path(plain_path(e.path)), 1))
    except OSError:
        pass
    roots.append((here, 0))
    best: Dict[str, tuple] = {}                     # same folder twice: the deeper scan
    for folder, depth in roots:
        k = _norm(folder)
        if k not in best or depth > best[k][1]:
            best[k] = (folder, depth)
    return [fd for fd in best.values() if is_dir(fd[0])]


def find_previous_runs(nd2_path, out_dir, image_shape, n_timepoints: Optional[int] = None
                       ) -> List[RunInfo]:
    """
    V2.9: only the current user's analyses (users.is_mine).
    Earlier ROI / session files for this .nd2, newest first (tracked before
    untracked when saved at the same time). A file counts if its image size
    (image_shape = (height, width)) matches and it was saved for an .nd2 of
    the same name or the same fingerprint. n_timepoints (the movie's) only adds
    a note to runs whose tracking has another length. Reads only file
    summaries (fast); never raises.
    """
    found: Dict[str, RunInfo] = {}
    try:
        nd2 = Path(nd2_path)
        name, stem = nd2.name, nd2.stem
        fp = nd2_fingerprint(nd2)
        shape = tuple(int(v) for v in image_shape)[:2] if image_shape is not None else None
        budget = {"entries": SCAN_MAX_ENTRIES, "until": time.perf_counter() + SCAN_SECONDS}
        cands: Dict[str, tuple] = {}                    # norm path -> (path, from index)
        ent = _load_index().get(fp["quick"]) if fp["quick"] else None
        for r in (ent or {}).get("runs", []):
            rp = resolve(r["path"])                     # V3.0: moved data found again
            cands.setdefault(_norm(rp), (rp, True))
        scanned = _scan(_roots(nd2, out_dir), budget)
        for p in scanned:
            cands.setdefault(_norm(p), (p, False))

        def mtime(item):
            try:
                return os.stat(long_path(item[0])).st_mtime
            except OSError:
                return -1.0
        items = sorted(cands.values(), key=lambda it: (it[1], mtime(it)), reverse=True)
        for path, from_index in items[:SCAN_MAX_FILES]:
            if time.perf_counter() > budget["until"] + SCAN_SECONDS:
                break
            info = _run_info(path, from_index, name, stem, fp, shape, n_timepoints)
            if info is not None and not users.is_mine(info.path, info.summary.get("user")):
                continue                          # V2.9: another user's analysis
            if info is not None:
                found.setdefault(_norm(info.path), info)
    except Exception:                                          # noqa: BLE001
        pass
    try:
        return sorted(found.values(), key=_sort_key, reverse=True)
    except Exception:                                          # noqa: BLE001
        return list(found.values())


def _named_for(file_name: str, stem: str) -> bool:
    """<stem[:40]>_ROIs.npz, _ROIs_2.npz ... or <stem[:40]>_session_<id>.npz"""
    pat = re.escape(stem[:40].casefold()) + r"_(rois(_\d+)?|session_.+)\.npz"
    return re.fullmatch(pat, file_name.casefold()) is not None


def _run_info(path, from_index: bool, name: str, stem: str, fp: dict, shape,
              n_timepoints: Optional[int]) -> Optional[RunInfo]:
    s = read_summary(path)
    if s is None:
        return None
    if shape is not None and tuple(s["image_shape"]) != tuple(shape):
        return None
    saved_fp = s.get("fingerprint") or {}
    fp_ok = same_file(saved_fp, fp) or (from_index and not saved_fp.get("quick"))
    if s["nd2"]:
        name_ok = s["nd2"].casefold() == name.casefold()
    else:                                     # files before v1.9 hold no .nd2 name:
        name_ok = _named_for(Path(path).name, stem)   # go by the ROI file's own name
    if not (fp_ok or name_ok):
        return None
    note = ""
    if fp_ok:
        match = "same file" if (name_ok or not s["nd2"]) else "renamed copy"
    else:
        match = "same name"
        if saved_fp.get("quick") and fp.get("quick"):
            note = ("Saved for a file with this name, but the .nd2 has changed since "
                    "(different size or contents).")
    if n_timepoints and s["tracked"] and s["n_timepoints"] != int(n_timepoints):
        note = (note + " " if note else "") + (
            f"Its tracking has {s['n_timepoints']} timepoints; this movie has "
            f"{int(n_timepoints)}.")
    return RunInfo(path=s["path"], saved=s["saved"], version=s["version"], kind=s["kind"],
                   n_cells=s["n_cells"], comps=list(s["comps"]), tracked=s["tracked"],
                   n_timepoints=s["n_timepoints"], rules=list(s["rules"]),
                   nd2_name=s["nd2"] or name, match=match, t0=s["t0"], prefix=s["prefix"],
                   note=note, summary=s, app=str(s.get("app") or "PD4nav"))


def dedupe_runs(runs: List[RunInfo]) -> List[RunInfo]:
    """
    V2.5: one entry per identical analysis. Runs whose files hold the same
    content (roifile content_key: the ROIs, the tracking and the settings that
    matter - not when or by which window they were saved) are shown once: the
    newest is kept (the list is newest first) and remembers the others in
    `same_as` (their paths). Files are never touched.
    """
    out: List[RunInfo] = []
    seen: Dict[str, RunInfo] = {}
    for r in runs:
        key = str((r.summary or {}).get("content_key") or "")
        if key and key in seen:
            seen[key].same_as.append(str(r.path))
            continue
        if key:
            seen[key] = r
        out.append(r)
    return out


def indexed_runs(limit: int = 300) -> List[dict]:
    """V2.4 'Compare runs': every run in this computer's index whose file still
    exists and holds tracking, newest first: [{path, nd2_name, saved, kind,
    n_cells}]. Never raises."""
    out = []
    try:
        for ent in _load_index().values():
            for r in ent.get("runs", []):
                rp = resolve(r["path"])                 # V3.0: moved data found again
                if r.get("tracked") and _exists(rp):
                    out.append(dict(path=str(rp), nd2_name=str(ent.get("nd2_name") or ""),
                                    saved=str(r.get("saved") or ""), kind=str(r.get("kind") or ""),
                                    n_cells=int(r.get("n_cells") or 0)))
        out.sort(key=lambda r: r["saved"], reverse=True)
    except Exception:                                          # noqa: BLE001
        pass
    return out[:limit]
