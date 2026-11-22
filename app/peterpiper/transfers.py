"""
PeterPiper 4.0: safe copies to and from the lab folder, in the background
(tasks.TaskCenter). PeterPiper never talks to a server itself: the lab folder is a
folder kept by a sync app (Box Drive, OneDrive, Google Drive, Dropbox ...) or a
network drive. This module copies files into and out of it - carefully.

Copying one file:
    copy_file(src, dst, progress=None, cancelled=None, overwrite=False) -> CopyResult
        in chunks (progress(done, total, name)), into a hidden temporary name,
        flushed to disk, size checked (+ SHA-256 for files under 200 MB), then
        renamed in one step - a half-copied file never carries the real name. A
        moment's trouble (the sync app holding the file, a cloud placeholder still
        downloading, a network time-out) -> tried again after 0.5, 1, 2, 4 ... s;
        each try starts over (no resume). overwrite=False: an identical file there
        is skipped, a different one is kept and the copy gets _2, _3 ...
    retry_call(fn, cancelled, retries, backoff)   the same retrying for any copy

Movies from the lab folder (a local movie cache):
    needs_fetch(path)          the movie is online-only (a placeholder) or on a network
                               drive: reading it there would be slow
    fetch_movie(path) -> Task  copies it into the cache (result: the local path); a
                               copy already there with the same size + time is reused
    prefetch(paths)            the next movie(s) of the queue, quietly, behind the rest
    cached_copy(path) / local_movie(path) / server_path_of(local)
    pin(local) / unpin(local)  the open movie is never removed from the cache
    cleanup_cache(limit)       oldest-used first, down to the limit (default 50 GB or
                               20% of the free disk, whichever is smaller)

Results to the lab folder (People/<me>/...; reusing cloud.keep_copy):
    upload_results(nd2, out_dir, what="saves"|"exports")      -> Task or None
    upload_movie(nd2)                                         -> Task or None
    on_results_written(nd2, out_dir, kind, extra=())          after SAVE / autosave /
                               export: uploads what the user's options say
    backup_profile(user) / backup_task() / backup_due() / install_quit_backup()
                               profile + settings + run list -> People/<me>/Backups
    measure_throughput(folder, size)   copy speed on this computer (MB/s)

Tests: TEST_HOOKS["fault"](src, attempt, done) -> an exception to raise (or None),
asked before each chunk; TEST_HOOKS["chunk_delay"] seconds per chunk;
TEST_HOOKS["needs_fetch"](path) -> bool; TEST_HOOKS["free"] free bytes.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import secrets
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from . import tasks as T
from .safety import error_text, long_path, plain_path

try:                                                    # the "launch" part (4.0)
    from .platforms import is_online_only               # type: ignore
except ImportError:                                     # until it is merged
    from .cloud import is_online_only

CHUNK = 8 * 1024 * 1024
HASH_LIMIT = 200_000_000           # files smaller than this are also checked by SHA-256
CACHE_DIR_NAME = "Movie cache"
CACHE_INDEX = "cache index.json"
CACHE_MAX = 50e9                   # automatic cache limit: 50 GB ...
CACHE_SHARE = 0.20                 # ... or 20% of the free disk, whichever is smaller
SPARE = 1e9                        # always leave this much free when fetching
BACKUP_PREFIX = "PeterPiper backup "
BACKUPS_KEPT = 30                  # our own daily backups kept (older ones of ours removed)
TEST_HOOKS: Dict[str, object] = {}

# errors a sync app or a network causes for a moment (Windows error numbers):
# 32/33 file in use / locked, 53/59/64/121 network gone or timed out,
# 358-401 cloud file provider errors (placeholder not ready, provider busy ...)
_WIN_TRANSIENT = {5, 32, 33, 53, 59, 64, 121, 1117, 1231} | set(range(358, 402))
_ERRNO_TRANSIENT = {errno.EIO, errno.EAGAIN, errno.EBUSY, errno.EACCES,
                    getattr(errno, "ETIMEDOUT", 110), getattr(errno, "ETXTBSY", 26),
                    getattr(errno, "EDEADLK", 35)}


# ======================================================== one careful copy
@dataclass
class CopyResult:
    src: str
    dst: str
    bytes: int = 0
    seconds: float = 0.0
    attempts: int = 1
    hashed: bool = False
    skipped: bool = False          # an identical file was already there

    @property
    def speed(self) -> float:
        """Bytes per second."""
        return self.bytes / self.seconds if self.seconds > 0 else 0.0


def is_transient(exc: BaseException) -> bool:
    """True for an error that may be gone in a moment (worth trying again)."""
    if isinstance(exc, (InterruptedError, FileNotFoundError, IsADirectoryError,
                        NotADirectoryError, T.Cancelled)):
        return False
    if isinstance(exc, (PermissionError, TimeoutError)):
        return True
    if not isinstance(exc, OSError):
        return False
    if exc.errno == errno.ENOSPC:
        return False
    win = getattr(exc, "winerror", None)
    if win is not None and win in _WIN_TRANSIENT:
        return True
    return exc.errno in _ERRNO_TRANSIENT


def _sleep(seconds: float, cancelled: Optional[Callable[[], bool]]) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cancelled is not None and cancelled():
            raise T.Cancelled()
        time.sleep(min(0.05, max(0.0, end - time.monotonic())))


def retry_call(fn: Callable, cancelled: Optional[Callable[[], bool]] = None,
               retries: int = 5, backoff: float = 0.5, max_wait: float = 20.0,
               on_retry: Optional[Callable[[int, BaseException], None]] = None):
    """fn() - again after backoff, 2x backoff ... (at most max_wait) when it fails
    with a passing error (is_transient), at most `retries` more times."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except BaseException as exc:                               # noqa: BLE001
            if attempt > retries or not is_transient(exc) or \
                    (cancelled is not None and cancelled()):
                raise
            if on_retry is not None:
                on_retry(attempt, exc)
            _sleep(min(max_wait, backoff * (2 ** (attempt - 1))), cancelled)


def _same(a: os.stat_result, b: os.stat_result) -> bool:
    return a.st_size == b.st_size and abs(a.st_mtime - b.st_mtime) <= 2.0


def _free_name(dst: Path, st: os.stat_result) -> Tuple[Optional[Path], Optional[Path]]:
    """(copy to, None) or (None, the identical file already there)."""
    for i in range(1, 1000):
        cand = dst if i == 1 else dst.with_name(f"{dst.stem}_{i}{dst.suffix}")
        try:
            other = os.stat(long_path(cand))
        except FileNotFoundError:
            return cand, None
        except OSError:
            continue
        if _same(st, other):
            return None, cand
    raise OSError(errno.EEXIST, f"too many copies named {dst.name}")


def _hash_file(p: Path, cancelled) -> str:
    h = hashlib.sha256()
    with open(long_path(p), "rb") as fh:
        while True:
            if cancelled is not None and cancelled():
                raise T.Cancelled()
            b = fh.read(CHUNK)
            if not b:
                return h.hexdigest()
            h.update(b)


def copy_file(src, dst, progress: Optional[Callable] = None,
              cancelled: Optional[Callable[[], bool]] = None, overwrite: bool = False,
              verify: bool = True, retries: int = 5, backoff: float = 0.5,
              chunk: int = CHUNK) -> CopyResult:
    """See the top of the module. Raises the last error when every try failed, and
    tasks.Cancelled when cancelled (the partial file is removed either way)."""
    src, dst = Path(plain_path(str(src))), Path(plain_path(str(dst)))
    st = os.stat(long_path(src))
    final = dst
    if not overwrite:
        final, same = _free_name(dst, st)
        if same is not None:
            return CopyResult(str(src), str(same), 0, 0.0, 0, False, True)
    t0 = time.monotonic()
    tries = [0]

    def once() -> CopyResult:
        tries[0] += 1
        return _copy_once(src, final, st, tries[0], progress, cancelled, verify, chunk)
    res = retry_call(once, cancelled, retries, backoff)
    res.attempts = tries[0]
    res.seconds = time.monotonic() - t0
    return res


def _copy_once(src: Path, final: Path, st: os.stat_result, attempt: int, progress,
               cancelled, verify: bool, chunk: int) -> CopyResult:
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(f".{final.name}.{secrets.token_hex(3)}.peterpiper-partial")
    hashing = verify and st.st_size < HASH_LIMIT
    h = hashlib.sha256() if hashing else None
    fault = TEST_HOOKS.get("fault")
    delay = float(TEST_HOOKS.get("chunk_delay") or 0)              # type: ignore[arg-type]
    done = 0
    t0 = time.monotonic()
    try:
        if fault is not None:
            e = fault(str(src), attempt, 0)                        # type: ignore[operator]
            if e is not None:
                raise e
        with open(long_path(src), "rb") as fi, open(long_path(tmp), "wb") as fo:
            if progress is not None:
                progress(0, st.st_size, src.name)
            while True:
                if cancelled is not None and cancelled():
                    raise T.Cancelled()
                buf = fi.read(chunk)
                if not buf:
                    break
                fo.write(buf)
                if h is not None:
                    h.update(buf)
                done += len(buf)
                if progress is not None:
                    progress(done, st.st_size, src.name)
                if delay:
                    _sleep(delay, cancelled)
                if fault is not None:
                    e = fault(str(src), attempt, done)             # type: ignore[operator]
                    if e is not None:
                        raise e
            fo.flush()
            try:
                os.fsync(fo.fileno())
            except OSError:
                pass
        got = os.stat(long_path(tmp)).st_size
        if got != st.st_size:
            raise OSError(errno.EIO, f"the copy has {got} bytes instead of {st.st_size}")
        if h is not None and _hash_file(tmp, cancelled) != h.hexdigest():
            raise OSError(errno.EIO, "the copy is not the same as the original (checksum)")
        os.utime(long_path(tmp), ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(long_path(tmp), long_path(final))
    except BaseException:
        try:
            os.remove(long_path(tmp))
        except OSError:
            pass
        raise
    return CopyResult(str(src), str(final), done, time.monotonic() - t0, attempt,
                      h is not None, False)


# ============================================================ the options
def _opts() -> dict:
    try:
        from . import userprefs
        return userprefs.server_options()
    except Exception:                                              # noqa: BLE001
        return {}


def _person(user: Optional[str] = None) -> Optional[Path]:
    """People/<user> in the linked lab folder (made), or None."""
    try:
        from . import labshare
        folder = labshare.linked_folder()
        if not folder or not os.path.isdir(folder):
            return None
        return labshare.person_dir(user, folder, create=True)
    except Exception:                                              # noqa: BLE001
        return None


def connected() -> bool:
    try:
        from . import labshare
        f = labshare.linked_folder()
        return bool(f) and os.path.isdir(f)
    except Exception:                                              # noqa: BLE001
        return False


# ======================================================== the movie cache
_cache_lock = threading.RLock()
_pinned: set = set()


def _key(path) -> str:
    return os.path.normcase(os.path.abspath(plain_path(str(path))))


def cache_dir() -> Path:
    """The local movie cache (the user's choice, else <PeterPiper data>/Movie cache)."""
    want = str(_opts().get("cache_dir") or "")
    if want:
        try:
            Path(want).mkdir(parents=True, exist_ok=True)
            return Path(want)
        except OSError:
            pass                                    # e.g. a Windows path on the Mac
    from . import users
    p = users.base_dir() / CACHE_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _free(folder) -> int:
    if "free" in TEST_HOOKS:
        return int(TEST_HOOKS["free"])                             # type: ignore[arg-type]
    try:
        return int(shutil.disk_usage(str(folder)).free)
    except OSError:
        return 0


def _load_index(cd: Path) -> dict:
    try:
        d = json.loads((cd / CACHE_INDEX).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_index(cd: Path, d: dict) -> None:
    p = cd / CACHE_INDEX
    tmp = p.with_name(p.name + f".{secrets.token_hex(3)}.tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def cache_size(cd: Optional[Path] = None) -> int:
    cd = cd or cache_dir()
    with _cache_lock:
        total = 0
        for e in _load_index(cd).values():
            try:
                total += os.stat(long_path(cd / e["local"])).st_size
            except (OSError, KeyError, TypeError):
                pass
        return total


def cache_limit_bytes(cd: Optional[Path] = None) -> int:
    """The user's limit, else min(50 GB, 20% of the free disk + what the cache holds)."""
    gb = float(_opts().get("cache_limit_gb") or 0)
    if gb > 0:
        return int(gb * 1e9)
    cd = cd or cache_dir()
    return int(min(CACHE_MAX, CACHE_SHARE * (_free(cd) + cache_size(cd))))


def needs_fetch(path) -> bool:
    """Reading this movie where it is would be slow: it is only a placeholder of an
    online file (Box Drive, OneDrive ... 'online-only'), or it is on a network drive."""
    hook = TEST_HOOKS.get("needs_fetch")
    if hook is not None:
        return bool(hook(str(path)))                               # type: ignore[operator]
    p = plain_path(str(path))
    if p.startswith("\\\\") or p.startswith("//"):
        return True
    try:
        if is_online_only(p):
            return True
        from . import cloud
        pl = cloud.place_of(p)
        return pl is not None and pl.service == cloud.NETWORK
    except Exception:                                              # noqa: BLE001
        return False


def cached_copy(server_path) -> Optional[str]:
    """The cached copy of this movie when it is still the same file (size and time
    of the original unchanged), else None."""
    cd = cache_dir()
    k = _key(server_path)
    with _cache_lock:
        e = _load_index(cd).get(k)
    if not e:
        return None
    try:
        local = cd / e["local"]
        lst = os.stat(long_path(local))
        sst = os.stat(long_path(plain_path(str(server_path))))
    except (OSError, KeyError, TypeError):
        return None
    if lst.st_size != e.get("size") or sst.st_size != e.get("size") or \
            sst.st_mtime_ns != int(e.get("mtime_ns") or 0):
        return None
    return str(local)


def _touch(server_path) -> None:
    cd = cache_dir()
    with _cache_lock:
        d = _load_index(cd)
        e = d.get(_key(server_path))
        if e:
            e["used"] = time.time()
            _save_index(cd, d)


def local_movie(server_path) -> str:
    """The cached copy when there is a good one, else the path itself."""
    return cached_copy(server_path) or str(server_path)


def server_path_of(local) -> Optional[str]:
    """The lab-folder movie a cached copy came from (None: not a cached copy)."""
    cd = cache_dir()
    lk = _key(local)
    with _cache_lock:
        for e in _load_index(cd).values():
            if _key(cd / e.get("local", "")) == lk:
                return str(e.get("src") or "") or None
    return None


def pin(local) -> None:
    """A movie open now: never removed from the cache while pinned."""
    _pinned.add(_key(local))


def unpin(local) -> None:
    _pinned.discard(_key(local))


def cleanup_cache(limit: Optional[int] = None, keep: Iterable = ()) -> Tuple[int, int]:
    """Remove the least recently used cached movies until the cache is within
    `limit` bytes (default cache_limit_bytes()). Pinned (open) movies and `keep`
    stay. Only files the cache index lists are removed - nothing else. Returns
    (bytes freed, files removed)."""
    cd = cache_dir()
    limit = cache_limit_bytes(cd) if limit is None else int(limit)
    keep_k = {_key(k) for k in keep} | set(_pinned)
    freed = removed = 0
    with _cache_lock:
        d = _load_index(cd)
        sizes = {}
        for k, e in d.items():
            try:
                sizes[k] = os.stat(long_path(cd / e["local"])).st_size
            except (OSError, KeyError, TypeError):
                sizes[k] = 0
        total = sum(sizes.values())
        for k, e in sorted(d.items(), key=lambda kv: float(kv[1].get("used") or 0)):
            if total <= limit:
                break
            local = cd / e.get("local", "")
            if _key(local) in keep_k or k in keep_k:
                continue
            try:
                if local.is_file():
                    os.remove(long_path(local))
                try:
                    local.parent.rmdir()               # its own folder, if now empty
                except OSError:
                    pass
            except OSError:
                continue
            total -= sizes[k]
            freed += sizes[k]
            removed += 1
            del d[k]
        _save_index(cd, d)
    return freed, removed


def _local_name(server_path) -> Path:
    p = Path(plain_path(str(server_path)))
    tag = hashlib.sha1(_key(p).encode("utf-8")).hexdigest()[:10]
    return Path(tag) / p.name


def fetch_now(server_path, progress=None, cancelled=None) -> str:
    """Fetch one movie into the cache, in this thread (fetch_movie's work)."""
    src = plain_path(str(server_path))
    if not needs_fetch(src):
        return src
    have = cached_copy(src)
    if have:
        _touch(src)
        return have
    cd = cache_dir()
    st = os.stat(long_path(src))
    need = st.st_size + SPARE
    if _free(cd) < need:
        cleanup_cache(max(0, cache_size(cd) - int(need - _free(cd))), keep=[src])
    if _free(cd) < need:
        raise OSError(errno.ENOSPC, f"There is not enough space for the movie cache: "
                                    f"{T.human_bytes(st.st_size)} needed, "
                                    f"{T.human_bytes(_free(cd))} free. Free some space "
                                    f"or choose a cache on another disk.")
    rel = _local_name(src)
    local = cd / rel

    def prog(done, total, name):
        if progress is not None:
            progress(None, done, total, f"{Path(src).name}")
    copy_file(src, local, prog, cancelled, overwrite=True)
    with _cache_lock:
        d = _load_index(cd)
        d[_key(src)] = {"src": src, "local": rel.as_posix(), "size": st.st_size,
                        "mtime_ns": st.st_mtime_ns, "used": time.time(),
                        "fetched": time.time()}
        _save_index(cd, d)
    cleanup_cache(keep=[local])
    return str(local)


def fetch_movie(server_path, center: Optional[T.TaskCenter] = None,
                on_done: Optional[Callable] = None, priority: int = 1,
                kind: str = "fetch") -> T.Task:
    """Fetch a movie into the local cache in the background (result: the path to
    open - the movie itself when it is on this computer already). The same movie
    asked for again gets the same task (moved to the front)."""
    c = center or T.center()
    key = "fetch:" + _key(server_path)
    old = c.find(key)
    if old is not None:
        c.bump(old, priority)
        if on_done is not None:
            if old.on_done is None:
                old.on_done = on_done
            else:
                first = old.on_done
                old.on_done = lambda t, a=first, b=on_done: (a(t), b(t))
        if kind == "fetch" and old.kind == "prefetch":
            old.kind = "fetch"
        return old
    last = c.find(key, include_ended=True)
    if last is not None and last.state == T.DONE and last.result and             os.path.isfile(long_path(str(last.result))):
        if on_done is not None:                    # here already: tell at once
            if c.ui_call is not None:
                c.ui_call(lambda: on_done(last))
            else:
                on_done(last)
        return last
    name = Path(str(server_path)).name
    data = {"path": str(server_path), "folder": str(Path(str(server_path)).parent)}

    def work(progress, cancelled):
        local = fetch_now(server_path, progress, cancelled)
        if _key(local) == _key(server_path):
            data["quiet"] = True                   # nothing had to be copied
        return local
    return c.submit(kind, f"Fetching {name}", work, on_done=on_done, priority=priority,
                    key=key, data=data)


def prefetch(paths: Iterable, center: Optional[T.TaskCenter] = None) -> List[T.Task]:
    """Quietly fetch these movies (the next ones of the queue) behind other work -
    when the user's 'Fetch the next movie' option is on."""
    if not _opts().get("prefetch", True):
        return []
    return [fetch_movie(p, center, priority=8, kind="prefetch") for p in paths if p]


def fetch_state(server_path, center: Optional[T.TaskCenter] = None) -> dict:
    """For the queue list, without touching the disk: {"state": "fetching" | "ready"
    | "failed" | "", "progress": 0-1 or None, "task": Task or None}."""
    c = center or T.center()
    t = c.find("fetch:" + _key(server_path), include_ended=True)
    if t is None:
        return {"state": "", "progress": None, "task": None}
    if t.state in (T.QUEUED, T.RUNNING):
        return {"state": "fetching", "progress": t.progress, "task": t}
    if t.state == T.DONE:
        local = str(t.result or "")
        return {"state": "ready" if local and _key(local) != _key(server_path) else "",
                "progress": 1.0, "task": t}
    return {"state": "failed" if t.state == T.FAILED else "", "progress": None, "task": t}


# ============================================================ uploads
_EXPORT_ENDINGS = (".xlsx", ".xls", ".csv", ".prism", ".pzfx")


def is_export(rel: str) -> bool:
    """An export (Export_<date>/..., or a workbook / Prism file) - not a SAVE."""
    first = rel.replace("\\", "/").split("/")[0].lower()
    return first.startswith("export_") or rel.lower().endswith(_EXPORT_ENDINGS)


def is_save(rel: str) -> bool:
    """A SAVE / autosave (ROI and session files, their notes) - not an export, not
    raw TIFFs or viewing copies."""
    low = rel.lower()
    return not is_export(rel) and low.endswith((".npz", ".json", ".jsonl", ".txt"))


def upload_results(nd2_path, out_dir, what: str = "saves", extra=(),
                   user: Optional[str] = None, center: Optional[T.TaskCenter] = None,
                   on_done: Optional[Callable] = None) -> Optional[T.Task]:
    """Mirror this movie's results into the lab folder - SAVEs to People/<me>/Results,
    exports to People/<me>/Exports (each OUTPUT_<movie>/<me>, as cloud.keep_copy
    does: new files copied, PeterPiper's own earlier copy updated, anything else
    kept). None when no lab folder is connected."""
    pd = _person(user)
    if pd is None:
        return None
    root = pd / ("Exports" if what == "exports" else "Results")
    include = is_export if what == "exports" else is_save
    from . import cloud
    nd2s, outs = str(nd2_path), str(out_dir)
    extra = [str(e) for e in extra if e] if what == "exports" else []

    def work(progress, cancelled):
        rep = cloud.keep_copy(nd2s, outs, str(root), extra=extra,
                              progress=lambda d, tot, n: progress(None, d, tot, n),
                              cancel=cancelled, include=include)
        if rep.problem:
            raise OSError(rep.problem)
        if rep.failed:
            raise OSError(f"{len(rep.failed)} file(s) could not be copied: {rep.failed[0][1]}")
        return rep
    word = "exports" if what == "exports" else "saves"
    return (center or T.center()).submit(
        "upload", f"Uploading {word} of {Path(nd2s).name}", work, on_done=on_done,
        key=f"upload:{what}:{_key(outs)}",
        data={"folder": str(cloud.copy_target(nd2s, outs, root)), "path": outs})


def upload_movie(nd2_path, user: Optional[str] = None,
                 center: Optional[T.TaskCenter] = None) -> Optional[T.Task]:
    """Copy an analysed .nd2 to People/<me>/Movies (an identical copy there is
    skipped). None when no lab folder is connected or the movie is already a
    lab-folder movie."""
    pd = _person(user)
    if pd is None:
        return None
    src = plain_path(str(nd2_path))
    src = server_path_of(src) or src
    try:
        from . import labshare
        if labshare.find_lab_root(src) is not None:
            return None                     # it is in the lab folder already
    except Exception:                                              # noqa: BLE001
        pass
    dst = pd / "Movies" / Path(src).name

    def work(progress, cancelled):
        return copy_file(src, dst, lambda d, tot, n: progress(None, d, tot, n), cancelled)
    return (center or T.center()).submit(
        "upload", f"Uploading {Path(src).name}", work, key="upload:movie:" + _key(src),
        data={"folder": str(dst.parent), "path": src})


def on_results_written(nd2_path, out_dir, kind: str = "save", extra=(),
                       center: Optional[T.TaskCenter] = None) -> List[T.Task]:
    """Call after a SAVE / autosave ('save') or an export ('export'): uploads what
    the user's options say (only when a lab folder is connected). Returns the tasks."""
    if not connected():
        return []
    o = _opts()
    out = []
    if kind == "export" and o.get("upload_exports", True):
        out.append(upload_results(nd2_path, out_dir, "exports", extra, center=center))
    if kind in ("save", "autosave", "export") and o.get("upload_saves", True):
        out.append(upload_results(nd2_path, out_dir, "saves", center=center))
    if kind in ("save", "export") and o.get("upload_movies", False):
        out.append(upload_movie(nd2_path, center=center))
    return [t for t in out if t is not None]


# ============================================================ backups
def backup_folder(user: Optional[str] = None) -> Optional[Path]:
    """People/<me>/Backups, else the 1.1 'Back up to' folder/PeterPiper backup/
    Profile, else None."""
    pd = _person(user)
    if pd is not None:
        return pd / "Backups"
    try:
        from . import cloud
        root = cloud.backup_root()
        if root and os.path.isdir(root):
            return Path(root) / cloud.BACKUP_DIR / "Profile"
    except Exception:                                              # noqa: BLE001
        pass
    return None


def backup_profile(user: Optional[str] = None, progress=None, cancelled=None) -> str:
    """Profile + settings + run list (the user's PeterPiper folder, as 'Export my
    profile' makes it) -> <backup folder>/PeterPiper backup <name> <date>.zip (one
    per day: today's is replaced; our own backups beyond BACKUPS_KEPT, oldest
    first, are removed - nothing else). Returns the backup's path."""
    from . import users, userprefs
    user = user or users.current()
    if not user:
        raise ValueError("No user is chosen.")
    dest = backup_folder(user)
    if dest is None:
        raise ValueError("No lab folder is connected (and no backup folder is set).")
    tmp_dir = users.base_dir() / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{BACKUP_PREFIX}{users.folder_name(user)} {datetime.now():%Y-%m-%d}"
    tmp = tmp_dir / f"{stem}.{secrets.token_hex(3)}.zip"
    try:
        users.export_profile(user, tmp)
        dest.mkdir(parents=True, exist_ok=True)
        res = copy_file(tmp, dest / f"{stem}.zip",
                        (lambda d, t, n: progress(None, d, t, n)) if progress else None,
                        cancelled, overwrite=True)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    ours = sorted(p for p in dest.glob(f"{BACKUP_PREFIX}{users.folder_name(user)} "
                                       f"????-??-??.zip"))
    for p in ours[:-BACKUPS_KEPT]:
        try:
            p.unlink()
        except OSError:
            pass
    userprefs.set_server_option("last_backup", datetime.now().isoformat(timespec="seconds"))
    userprefs.set_server_option("last_backup_file", res.dst)
    return res.dst


def backup_task(user: Optional[str] = None, center: Optional[T.TaskCenter] = None,
                on_done: Optional[Callable] = None) -> T.Task:
    return (center or T.center()).submit(
        "backup", "Backing up your profile, settings and run list",
        lambda progress, cancelled: backup_profile(user, progress, cancelled),
        on_done=on_done, key="backup:profile",
        data={"folder": str(backup_folder(user) or "")})


def last_backup() -> str:
    return str(_opts().get("last_backup") or "")


def backup_due(now: Optional[datetime] = None) -> bool:
    """Daily backups on and the last one is a day old (or none yet)."""
    if not _opts().get("backup_daily", True):
        return False
    last = last_backup()
    if not last:
        return True
    try:
        return ((now or datetime.now()) - datetime.fromisoformat(last)).total_seconds() > 86400
    except ValueError:
        return True


_quit_hooked = False


def _on_quit() -> None:
    try:
        if _opts().get("backup_on_close", True) and backup_folder() is not None:
            backup_profile()
    except Exception:                                              # noqa: BLE001
        pass
    try:
        T.center().shutdown(timeout=3.0)
    except Exception:                                              # noqa: BLE001
        pass


def install_quit_backup() -> bool:
    """Back up when PeterPiper closes (QApplication.aboutToQuit, once)."""
    global _quit_hooked
    if _quit_hooked:
        return True
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return False
        app.aboutToQuit.connect(_on_quit)
        _quit_hooked = True
        return True
    except Exception:                                              # noqa: BLE001
        return False


# ============================================================ speed check
def measure_throughput(folder, size: int = 1_000_000_000) -> dict:
    """Write a `size`-byte file in `folder`, copy it there with copy_file, delete
    both. {"write_mb_s", "copy_mb_s", "seconds"} - this computer's local copy speed."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    a = folder / f".pp-speed-{secrets.token_hex(3)}.bin"
    b = folder / (a.stem + "-copy.bin")
    block = os.urandom(CHUNK)
    t0 = time.monotonic()
    try:
        with open(a, "wb") as fh:
            left = size
            while left > 0:
                fh.write(block[:min(left, len(block))])
                left -= len(block)
            fh.flush()
            os.fsync(fh.fileno())
        tw = time.monotonic() - t0
        r = copy_file(a, b, overwrite=True)
        return {"write_mb_s": size / 1e6 / max(tw, 1e-6), "copy_mb_s": r.speed / 1e6,
                "seconds": time.monotonic() - t0, "hashed": r.hashed}
    finally:
        for p in (a, b):
            try:
                p.unlink()
            except OSError:
                pass


def describe_error(exc: BaseException) -> str:
    return error_text(exc)
