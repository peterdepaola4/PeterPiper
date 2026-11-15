"""
Keep a person's profile in step through a folder (PeterPiper 1.1, part "profiles").

Free and simple: the folder is any folder the person can reach from each of their
computers - their own OneDrive, Google Drive, Box, Dropbox, iCloud Drive or a
network folder. PeterPiper never talks to the network itself: the cloud app (or
the network share) carries the files; PeterPiper only reads and writes a folder.

    <folder>/PeterPiper profile - <name>/     the profile, laid out like an
                                              exported profile (Export my profile)

When:  when the user is chosen (users.activate: the folder's changes come in, then
this computer's go out), when another user is chosen or PeterPiper closes
(QApplication.aboutToQuit) - and the same for the person's folder in the lab
folder (labshare), so the profile is kept in several places.

Rules (never delete, never overwrite blindly):
  * a file only one side has is copied to the other;
  * the run list is united (movies by fingerprint, runs by path - a Mac path and a
    Windows path of the same run are both kept; history finds runs by the movie's
    fingerprint);
  * every other JSON file of the profile (settings, compare colours / choices,
    achievements, userprefs ...) is united key by key; where both sides changed
    the same single value (or list) since the last sync, the NEWER file wins
    (newest-wins only for single values). A side that did not change since the
    last sync (remembered as a checksum per file) never wins over one that did;
  * logs (*.jsonl) are united line by line;
  * other files (Prism style templates, saved settings, trained auto-detects):
    the changed one is taken; if both changed, the newer keeps the name and the
    older is kept next to it as '<name> (other copy <date>)';
  * per-computer files are never synced (storage.json: results location,
    queue.json: movie queue, sync.json: this state);
  * every write is a temporary file then os.replace (no half-written files);
  * the folder offline / missing -> skipped quietly, with a note.
The local name and the folder's name may differ (e.g. 'Ana Lopez' here, 'A. Lopez'
on the Mac): the profile is bound by the chosen folder, and the other spelling
becomes one of the user's aliases (their runs count as hers).

State, per user, in <their folder>/sync.json (never synced):
    {"folder": chosen folder, "target": profile folder in it, "last": ISO time,
     "note": last result, "base": {target: {file: sha1}}}
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import users

STATE_FILE = "sync.json"
_quit_hooked = False


# ------------------------------------------------------------------ state
def _state_path(user: str) -> Path:
    return users.user_dir(user) / STATE_FILE


def load_state(user: str) -> dict:
    try:
        d = json.loads(_state_path(user).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(user: str, d: dict) -> None:
    p = _state_path(user)
    p.parent.mkdir(parents=True, exist_ok=True)
    _write(p, json.dumps(d, indent=1, sort_keys=True).encode("utf-8"))


def _write(p: Path, data: bytes) -> None:
    """Temporary file next to it, then one os.replace."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".pp-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


def _read(p: Path) -> Optional[bytes]:
    try:
        return p.read_bytes()
    except OSError:
        return None


def _h(b: Optional[bytes]) -> str:
    return hashlib.sha1(b).hexdigest() if b is not None else ""


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


# --------------------------------------------------------------- folders
def suggest_folders() -> List[Tuple[str, str]]:
    """Likely cloud / shared folders on this computer: [(what to call it, path)].
    Uses cloud.places() (another part) when it is there, else a short list of
    the usual places that exist."""
    out: List[Tuple[str, str]] = []
    try:
        from . import cloud                                     # optional part
        for p in cloud.places():
            if getattr(p, "path", "") and os.path.isdir(str(p.path)):
                out.append((str(getattr(p, "name", "") or Path(p.path).name), str(p.path)))
        if out:
            return out
    except Exception:                                           # noqa: BLE001
        pass
    h = Path.home()
    cands: List[Tuple[str, Path]] = []
    try:
        cands += [(p.name.replace("OneDrive-", "OneDrive - "), p) for p in sorted(h.glob("OneDrive*"))]
    except OSError:
        pass
    try:
        cs = h / "Library" / "CloudStorage"
        if cs.is_dir():
            cands += [(p.name, p) for p in sorted(cs.iterdir())]
    except OSError:
        pass
    cands += [("Dropbox", h / "Dropbox"), ("Box", h / "Box"), ("Google Drive", h / "Google Drive"),
              ("Google Drive", Path("G:/My Drive")), ("iCloud Drive", h / "iCloudDrive"),
              ("iCloud Drive", h / "Library" / "Mobile Documents" / "com~apple~CloudDocs")]
    seen = set()
    for name, p in cands:
        try:
            if p.is_dir() and str(p).lower() not in seen:
                seen.add(str(p).lower())
                out.append((name, str(p)))
        except OSError:
            pass
    return out


def is_profile_dir(p) -> bool:
    p = Path(p)
    return p.name.startswith(users.EXPORT_ROOT) or (p / users.PROFILE_FILE).is_file()


def profile_dirs_in(folder) -> List[Path]:
    """Profiles kept in this folder (the folder itself if it is one)."""
    f = Path(folder)
    try:
        if is_profile_dir(f):
            return [f]
        return sorted(p for p in f.iterdir() if p.is_dir() and is_profile_dir(p))
    except OSError:
        return []


def profile_label(p) -> str:
    """The name of the person a profile folder belongs to."""
    p = Path(p)
    try:
        d = json.loads((p / users.PROFILE_FILE).read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("name"):
            return str(d["name"])
    except (OSError, ValueError):
        pass
    n = p.name
    return n[len(users.EXPORT_ROOT):] if n.startswith(users.EXPORT_ROOT) else n


def target_in(folder, user: str) -> Path:
    """Where `user`'s profile goes in `folder`: the folder itself if it already is
    a profile folder, else <folder>/PeterPiper profile - <name>."""
    f = Path(folder)
    if is_profile_dir(f):
        return f
    return f / (users.EXPORT_ROOT + users.folder_name(user))


def folder_of(user: str) -> Optional[str]:
    return load_state(user).get("folder") or None


def set_folder(user: str, folder, target=None, sync_now: bool = True) -> str:
    """Keep `user` in step through `folder` (target: the profile folder in it to
    use - e.g. the one the Mac made under another spelling). Returns the note."""
    st = load_state(user)
    st["folder"] = str(folder)
    st["target"] = str(Path(target) if target else target_in(folder, user))
    st["note"] = ""
    save_state(user, st)
    return sync_user(user) if sync_now else ""


def turn_off(user: str) -> None:
    """Stop keeping `user` in step through their folder (nothing is deleted)."""
    st = load_state(user)
    for k in ("folder", "target"):
        st.pop(k, None)
    st["note"] = "Off"
    save_state(user, st)


def _fmt_time(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    if t.date() == datetime.now().date():
        return "today " + t.strftime("%H:%M")
    return t.strftime("%d %b %Y %H:%M")


def status(user: Optional[str]) -> str:
    """One line for the first window: 'Off' or '<folder> - last kept in step: ...'."""
    if not user:
        return ""
    st = load_state(user)
    if not st.get("folder"):
        return "Off"
    s = str(st["folder"])
    if st.get("last"):
        s += f"  -  last kept in step: {_fmt_time(st['last'])}"
    if st.get("note") and "skipped" in str(st["note"]):
        s += f"  ({st['note']})"
    return s


# ------------------------------------------------------------------- sync
def _targets(user: str) -> List[Tuple[str, Path, Path, bool]]:
    """[(what, root folder, profile folder, may write)] for this user."""
    out = []
    st = load_state(user)
    if st.get("folder"):
        out.append(("your folder", Path(st["folder"]),
                    Path(st.get("target") or target_in(st["folder"], user)), True))
    try:
        from . import labshare
        t = labshare.profile_target(user)
        if t is not None:
            root, target, writable = t
            out.append(("the lab folder", Path(root), Path(target), bool(writable)))
    except Exception:                                           # noqa: BLE001
        pass
    return out


def sync_user(user: str) -> str:
    """Keep `user`'s profile in step with their folder and their lab folder (both
    ways). Never raises; returns a short note (also kept in sync.json)."""
    if not user or user not in users.all_users():
        return ""
    notes = []
    st = load_state(user)
    bases: Dict[str, dict] = dict(st.get("base") or {})
    any_ok = False
    for what, root, target, writable in _targets(user):
        try:
            if not os.path.isdir(root):
                notes.append(f"{what} is not reachable now (offline?) - skipped")
                continue
            if not writable and not target.is_dir():
                notes.append(f"{what} is read-only and has no profile of you yet")
                continue
            key = str(target)
            res = sync_dirs(users.user_dir(user), target, bases.get(key, {}),
                            write_remote=writable)
            bases[key] = res["base"]
            _bind_names(user, target, writable)
            any_ok = True
            got, sent = res["to_local"], res["to_remote"]
            part = f"{what}: " + (f"{got} in, {sent} out" if got or sent else "already in step")
            if not writable:
                part += " (read-only: only read)"
            if res["errors"]:
                part += f", {res['errors']} file(s) could not be written"
            notes.append(part)
        except Exception as exc:                                # noqa: BLE001
            notes.append(f"{what}: skipped ({exc})")
    if not notes:
        return ""
    st = load_state(user)                    # re-read: written again below
    st["base"] = bases
    st["note"] = "; ".join(notes)
    if any_ok:
        st["last"] = datetime.now().isoformat(timespec="seconds")
    try:
        save_state(user, st)
    except OSError:
        pass
    return st["note"]


def _conflict_name(rel: str, have) -> str:
    p = Path(rel)
    stamp = datetime.now().strftime("%Y-%m-%d")
    i = 1
    while True:
        tag = f" (other copy {stamp})" if i == 1 else f" (other copy {stamp} {i})"
        cand = (p.parent / f"{p.stem}{tag}{p.suffix}").as_posix()
        if cand not in have:
            return cand
        i += 1


def sync_dirs(local: Path, remote: Path, base: dict, write_local: bool = True,
              write_remote: bool = True) -> dict:
    """Two copies of one profile -> both the same, nothing lost (rules at the
    top). base: {file: sha1} from the last sync. Returns {base, to_local,
    to_remote, copies, errors}."""
    local, remote = Path(local), Path(remote)
    files = set()
    for root in (local, remote):
        if root.is_dir():
            for f in root.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(root)
                    if not users.skip_in_profile(rel, foreign=True):
                        files.add(rel.as_posix())
    new_base: dict = {}
    res = dict(to_local=0, to_remote=0, copies=0, errors=0)
    if write_remote and files:
        remote.mkdir(parents=True, exist_ok=True)
    for rel in sorted(files):
        lp, rp = local / rel, remote / rel
        a, b = _read(lp), _read(rp)
        if a is not None and a == b:
            new_base[rel] = _h(a)
            continue
        if a is None:
            final = b
        elif b is None:
            final = a
        else:
            ha, hb, h0 = _h(a), _h(b), base.get(rel)
            if ha == h0:
                local_newer = False
            elif hb == h0:
                local_newer = True
            else:
                local_newer = _mtime(lp) >= _mtime(rp)
            m = None
            if "/" not in rel:
                if rel.lower() == users.PASSWORD_FILE:
                    local_newer = _pw_set(a) >= _pw_set(b)
                m = users.merge_bytes(rel, a, b, prefer_mine=local_newer)
            if m is not None:
                final = m
            elif h0 in (ha, hb):                 # only one side changed: take it
                final = a if local_newer else b
            else:                                # both changed: keep both
                final, older = (a, b) if local_newer else (b, a)
                aside = _conflict_name(rel, files)
                files.add(aside)
                for side, ok in ((local, write_local), (remote, write_remote)):
                    if ok:
                        try:
                            _write(side / aside, older)
                        except OSError:
                            res["errors"] += 1
                res["copies"] += 1
        done_l = done_r = True
        if final != a:
            if write_local:
                try:
                    _write(lp, final)
                    res["to_local"] += 1
                except OSError:
                    res["errors"] += 1
                    done_l = False
            else:
                done_l = False
        if final != b:
            if write_remote:
                try:
                    _write(rp, final)
                    res["to_remote"] += 1
                except OSError:
                    res["errors"] += 1
                    done_r = False
            else:
                done_r = False
        if done_l and done_r:
            new_base[rel] = _h(final)
        elif rel in base:
            new_base[rel] = base[rel]
    res["base"] = new_base
    return res


def _pw_set(b: bytes) -> str:
    try:
        return str(json.loads(b.decode("utf-8")).get("set") or "")
    except (ValueError, AttributeError):
        return ""


def _bind_names(user: str, target: Path, writable: bool) -> None:
    """The folder's profile and this user are one person: each side learns the
    other's spellings (aliases)."""
    p = target / users.PROFILE_FILE
    try:
        prof = json.loads(p.read_text(encoding="utf-8"))
        prof = prof if isinstance(prof, dict) else {}
    except (OSError, ValueError):
        prof = {}
    theirs = [str(prof.get("name") or "")] + [str(a) for a in prof.get("aliases") or []]
    users.add_aliases(user, [t for t in theirs if t])
    if not writable:
        return
    mine = [user] + users.aliases_of(user)
    name = str(prof.get("name") or user)
    al = list(dict.fromkeys([a for a in [str(x) for x in prof.get("aliases") or []] + mine
                             if a and a.lower() != name.lower()]))
    if prof.get("name") == name and prof.get("aliases") == al:
        return
    try:
        from . import __version__
        new = dict(prof, name=name, aliases=al, peterpiper=__version__)
        _write(p, json.dumps(new, indent=1).encode("utf-8"))
    except OSError:
        pass


# ------------------------------------------------------------------ hooks
def on_activate(user: str) -> None:
    """users.activate: bring the folder's changes in and send this computer's out;
    then make sure PeterPiper sends them again when it closes."""
    try:
        sync_user(user)
    finally:
        install_quit_hook()


def on_deactivate(user: str) -> None:
    sync_user(user)


def on_users_merged(keep: str, other: str) -> None:
    """Merge profiles: the kept user takes over the merged one's sync folder if
    they had none (it is the same person)."""
    a, b = load_state(keep), load_state(other)
    if not a.get("folder") and b.get("folder"):
        a.update(folder=b["folder"], target=b.get("target") or "", note="")
        save_state(keep, a)


def _on_quit() -> None:
    u = users.current()
    if u:
        try:
            sync_user(u)
        except Exception:                                       # noqa: BLE001
            pass


def install_quit_hook() -> bool:
    """Connect QApplication.aboutToQuit once (guarded: no Qt app -> nothing)."""
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
    except Exception:                                           # noqa: BLE001
        return False
