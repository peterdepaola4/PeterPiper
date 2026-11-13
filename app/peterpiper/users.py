"""
V2.9 user profiles: one PeterPiper on a lab computer, many people - nobody's data
mixed with anybody else's.

At start the user picks their name (or makes a new one; no password - this keeps
people's work apart, it is not security). Everything PeterPiper remembers then lives
in that user's own folder, <data>/users/<folder>/: settings, the list of their
runs (run index), Compare groups / colours / labels, Prism style templates, saved
settings and the saved-files log. Results written next to the .nd2 go into a
per-user subfolder, OUTPUT_<movie>/<folder>/, and every ROI / session file
records its user, so 'Earlier analyses' only finds the user's own. Another
user's run is opened only on purpose (Compare > Add run file...), and is then
marked with its owner.

<data> = $PETERPIPER_HOME, else %USERPROFILE%/PeterPiper data - the SAME folder for every
PeterPiper version, so a new version finds everyone's profiles (the private Python
install stays in the version's own %USERPROFILE%/.PD4navV2.x). Profiles made
in V2.9 under %USERPROFILE%/.PD4navV2.9 are copied there once (migrate_old_home).

Everything on this computer from before profiles (the newest earlier version's
settings, run index, Compare choices ...) is given to the FIRST user made
(users.json: legacy_owner); later users start empty.

A user can be renamed (their folder keeps its name, and the old name still
identifies their runs: users.json 'aliases') or removed (only hidden from the
list - nothing is deleted; adding the same name again brings them back).

Portable: a user's folder is self-contained and says whose it is (profile.json).
Copy it to <data>/users on another computer (adopt_copied_profiles adds it to
the list), or Export my profile... (one zip) and Import a profile... there (a new
user, or merged into a user of the same name - nothing there is overwritten).
Runs whose files sit elsewhere on the new computer are found again with 'My
data is in...' (history.relocate_runs).
'Don't ask again' skips the start question on this Windows account until
Switch user is used. With no user chosen (tests, IT scripts) everything works
as before, in <data> itself.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

USERS_FILE = "users.json"
DATA_DIR_NAME = "PeterPiper data"
# what a user's folder holds (copied to the first user from before profiles)
DATA_NAMES = ("settings.json", "run_history.json", "compare_colours.json",
              "compare_window.json", "saved_files_log.jsonl",
              "Prism style templates", "Saved settings")
# where earlier versions kept their data, newest first
# PeterPiper 1.0 starts empty: nothing is taken over from PD4nav (its data stays where
# it is, untouched; a PD4nav profile can still be brought in on purpose with
# 'Import a profile...').
OLD_HOMES: tuple = ()

_current: Optional[str] = None


def base_dir() -> Path:
    custom = os.environ.get("PETERPIPER_HOME")
    return Path(custom) if custom else Path.home() / DATA_DIR_NAME


def folder_name(name: str) -> str:
    """A safe folder name for a user name (letters, digits, space, . _ -)."""
    s = re.sub(r"[^\w .-]", "_", name.strip()).strip(" .")
    return s[:40] or "user"


def clean_name(name: str) -> str:
    return " ".join(str(name).split())[:40]


def _load() -> dict:
    try:
        d = json.loads((base_dir() / USERS_FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    p = base_dir() / USERS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def all_users() -> List[str]:
    """Every user ever made here, removed ones included (they still own runs)."""
    return [str(u) for u in _load().get("users", []) if str(u).strip()]


def list_users() -> List[str]:
    """The users offered at start (removed ones hidden)."""
    hidden = {h.lower() for h in _load().get("hidden", [])}
    return [u for u in all_users() if u.lower() not in hidden]


def last_user() -> Optional[str]:
    u = _load().get("last")
    return u if u in list_users() else None


def legacy_owner() -> Optional[str]:
    return _load().get("legacy_owner") or None


def dont_ask() -> bool:
    """'Don't ask again' is on and the last user still exists."""
    return bool(_load().get("dont_ask")) and last_user() is not None


def set_dont_ask(on: bool) -> None:
    d = _load()
    d["dont_ask"] = bool(on)
    _save(d)


def current() -> Optional[str]:
    return _current


def _folder_of(name: str) -> str:
    return str(_load().get("folders", {}).get(name) or folder_name(name))


def _canonical(name: Optional[str]) -> Optional[str]:
    """A name as recorded in a file -> the user's present name (renames)."""
    if not name:
        return None
    n = clean_name(name).lower()
    for u in all_users():
        if u.lower() == n:
            return u
    for u, olds in (_load().get("aliases") or {}).items():
        if n in (str(o).lower() for o in olds):
            return u
    return clean_name(name)


def home() -> Path:
    """Where PeterPiper keeps this user's things (<data>/users/<folder>), or <data>
    when no user is chosen."""
    b = base_dir()
    return b / "users" / _folder_of(_current) if _current else b


def gets_old_data() -> bool:
    """True when the earlier versions' data may be carried over into home(): no
    user chosen (as before), or the first user (who takes over what was here)."""
    return _current is None or _current == legacy_owner()


def name_problem(name: str, renaming: Optional[str] = None) -> str:
    """'' if `name` can be a new user (or the new name of `renaming`), else why not.
    A removed user's name is allowed: adding it brings that user back."""
    n = clean_name(name)
    if not n:
        return "Type a name."
    others = [u for u in list_users() if u != renaming]
    if n.lower() in (u.lower() for u in others):
        return f"'{n}' is already a user - pick it in the list."
    if folder_name(n).lower() in (folder_name(u).lower() for u in others):
        return f"'{n}' is too close to an existing user's name."
    return ""


def add_user(name: str) -> str:
    n = clean_name(name)
    why = name_problem(n)
    if why:
        raise ValueError(why)
    d = _load()
    back = next((u for u in all_users() if u.lower() == n.lower()), None)
    if back is not None:                        # a removed user, brought back
        d["hidden"] = [h for h in d.get("hidden", []) if h.lower() != back.lower()]
        _save(d)
        return back
    d["users"] = all_users() + [n]
    d.setdefault("folders", {})[n] = _free_folder(n, d)
    first = not d.get("legacy_owner")
    if first:
        d["legacy_owner"] = n
    _save(d)
    if first:
        _give_old_data(n)
    _write_profile(n)
    return n


def _free_folder(name: str, d: dict) -> str:
    used = {str(f).lower() for f in (d.get("folders") or {}).values()}
    base, f, i = folder_name(name), folder_name(name), 2
    while f.lower() in used:
        f, i = f"{base}_{i}", i + 1
    return f


def rename_user(old: str, new: str) -> str:
    """New name for a user. Their folder (and OUTPUT_<movie>/<folder>) keeps its
    name, and the old name still identifies the runs they made before."""
    n = clean_name(new)
    if old not in all_users():
        raise ValueError(f"No user '{old}'.")
    if n == old:
        return n
    why = name_problem(n, renaming=old)
    if why:
        raise ValueError(why)
    d = _load()
    d["users"] = [n if u == old else u for u in all_users()]
    folders = d.setdefault("folders", {})
    folders[n] = folders.pop(old, folder_name(old))
    al = d.setdefault("aliases", {})
    al[n] = list(dict.fromkeys(list(al.pop(old, [])) + [old]))
    for key in ("legacy_owner", "last"):
        if d.get(key) == old:
            d[key] = n
    _save(d)
    global _current
    if _current == old:
        _current = n
    _write_profile(n)
    return n


def remove_user(name: str) -> None:
    """Hide a user from the list. Nothing is deleted: their folder, settings and
    runs stay; adding the same name again brings them back."""
    d = _load()
    d["hidden"] = list(dict.fromkeys(list(d.get("hidden", [])) + [name]))
    if d.get("last") == name:
        d["last"] = None
    _save(d)


def migrate_old_home() -> bool:
    """PeterPiper 1.0: nothing to take over - every computer starts empty (PD4nav's
    profiles are left where they are). Kept so callers need not change; always
    False."""
    return False


def _old_data_source() -> Optional[Path]:
    """Where the data from before profiles is: <data> itself (with $PETERPIPER_HOME
    or data left there), else the newest earlier version's folder that has some."""
    cands = [base_dir()] + ([] if os.environ.get("PETERPIPER_HOME") else
                            [Path.home() / h for h in OLD_HOMES])
    for c in cands:
        if any((c / n).exists() for n in ("settings.json", "run_history.json")):
            return c
    return None


def _give_old_data(name: str) -> None:
    """The first user takes over what PeterPiper kept on this computer before
    profiles: copied (never moved, never overwriting) into their folder."""
    dst = base_dir() / "users" / _folder_of(name)
    dst.mkdir(parents=True, exist_ok=True)
    src = _old_data_source()
    if src is None:
        return
    for n in DATA_NAMES:
        a, b = src / n, dst / n
        if not a.exists() or b.exists():
            continue
        try:
            if a.is_dir():
                shutil.copytree(a, b)
            else:
                shutil.copy2(a, b)
        except OSError:
            pass


def activate(name: str) -> Path:
    """Use this user from now on (their folder is made if needed); remembered as
    the last user."""
    global _current
    n = clean_name(name)
    if n not in list_users():
        raise ValueError(f"No user '{n}'.")
    _current = n
    home().mkdir(parents=True, exist_ok=True)
    d = _load()
    d["last"] = n
    _save(d)
    _write_profile(n)
    return home()


def deactivate() -> None:
    global _current
    _current = None


# ------------------------------------------------------------ whose run is it
def output_dir(nd2_path) -> str:
    """The default results folder of a movie: OUTPUT_<movie>/<user folder> (next
    to it); OUTPUT_<movie> with no user chosen."""
    p = Path(str(nd2_path))
    out = p.parent / f"OUTPUT_{p.stem}"
    return str(out / _folder_of(_current)) if _current else str(out)


RESULTS_DIR_NAME = "PeterPiper results"


def results_home() -> Path:
    """Where results go when the movie's own folder cannot be written (a
    read-only drive): $PETERPIPER_RESULTS, else <home>/PeterPiper results."""
    custom = os.environ.get("PETERPIPER_RESULTS")
    return Path(custom) if custom else Path.home() / RESULTS_DIR_NAME


def fallback_output_dir(nd2_path) -> str:
    """The results folder of a movie whose own folder cannot be written:
    <results home>/OUTPUT_<movie>/<user folder> - laid out like output_dir()."""
    out = results_home() / f"OUTPUT_{Path(str(nd2_path)).stem}"
    return str(out / _folder_of(_current)) if _current else str(out)


def _folders() -> Dict[str, str]:
    """{folder name (lower case): user} for every user, removed ones included."""
    return {_folder_of(u).lower(): u for u in all_users()}


def owner_from_path(path) -> Optional[str]:
    """The user whose per-user results folder holds `path` (OUTPUT_<movie>/<user>/
    ...), or None."""
    parts = Path(str(path)).parts
    folders = _folders()
    for i, part in enumerate(parts[:-1]):
        if part.upper().startswith("OUTPUT_") and i + 1 < len(parts) - 1:
            u = folders.get(parts[i + 1].lower())
            if u is not None:
                return u
    return None


def owner_of(path, summary_user: Optional[str] = None) -> Optional[str]:
    """Who made a run: the user recorded in the file (under their present name),
    else its per-user folder, else None (from before profiles)."""
    return _canonical(summary_user) or owner_from_path(path)


def is_mine(path, summary_user: Optional[str] = None) -> bool:
    """Should this run be listed for the current user? Every run with no user
    chosen; the user's own runs; runs from before profiles only for the user who
    took over the old data."""
    if _current is None:
        return True
    who = owner_of(path, summary_user)
    if who is None:
        return _current == legacy_owner()
    return who.lower() == _current.lower()


# --------------------------------------------- V3.0 portable profiles (copy / zip)
PROFILE_FILE = "profile.json"         # in each user's folder: who it belongs to
EXPORT_ROOT = "PeterPiper profile - "     # the folder inside an exported zip
LEGACY_EXPORT_ROOTS = ("PD4nav profile - ",)   # a PD4nav profile can be imported too


def _write_profile(name: str) -> None:
    """The user's folder says whose it is, so a copied folder is recognised."""
    try:
        from . import __version__
        d = _load()
        f = base_dir() / "users" / _folder_of(name)
        f.mkdir(parents=True, exist_ok=True)
        (f / PROFILE_FILE).write_text(json.dumps(dict(
            name=name, aliases=list((d.get("aliases") or {}).get(name, [])),
            peterpiper=__version__), indent=1), encoding="utf-8")
    except OSError:
        pass


def adopt_copied_profiles() -> List[str]:
    """User folders copied into <data>/users by hand (from another computer) are
    added to the list under the name in their profile.json. Returns the names."""
    root = base_dir() / "users"
    if not root.is_dir():
        return []
    d = _load()
    known = {str(f).lower() for f in (d.get("folders") or {}).values()} | \
        {folder_name(u).lower() for u in all_users()}
    added = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.lower() in known:
            continue
        try:
            prof = json.loads((sub / PROFILE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prof = {}
        if not prof and not any((sub / n).exists() for n in DATA_NAMES):
            continue                           # not a profile
        name = clean_name(str(prof.get("name") or sub.name))
        while name.lower() in (u.lower() for u in all_users()):
            name = clean_name(name + " (copied)")
        d = _load()
        d["users"] = all_users() + [name]
        d.setdefault("folders", {})[name] = sub.name
        if prof.get("aliases"):
            d.setdefault("aliases", {})[name] = [str(a) for a in prof["aliases"]]
        _save(d)
        added.append(name)
    return added


def export_profile(name: str, zip_path) -> str:
    """Everything of this user's folder in one zip, to carry to another computer
    (Import a profile... there). Returns the zip's path."""
    import zipfile
    _write_profile(name)
    src = base_dir() / "users" / _folder_of(name)
    root = EXPORT_ROOT + folder_name(name)
    out = Path(zip_path)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            rel = f.relative_to(src)
            if f.is_file() and not f.name.endswith((".lock", ".tmp")) \
                    and rel.parts[0] != "theme":       # the theme's icons are drawn again
                z.write(f, f"{root}/{rel.as_posix()}")
    return str(out)


def _deep_merge(mine, theirs):
    """theirs into mine: keys mine lacks are added, dicts merged, mine wins."""
    if isinstance(mine, dict) and isinstance(theirs, dict):
        out = dict(mine)
        for k, v in theirs.items():
            out[k] = _deep_merge(mine[k], v) if k in mine else v
        return out
    return mine


def _merge_index(mine: dict, theirs: dict) -> dict:
    """Run lists: every run of both (by file path); what is here is kept."""
    out = dict(mine)
    for key, ent in theirs.items():
        if key not in out:
            out[key] = ent
            continue
        cur = dict(out[key])
        have = {str(r.get("path", "")).lower() for r in cur.get("runs", [])}
        cur["runs"] = list(cur.get("runs", [])) + [r for r in ent.get("runs", [])
                                                   if str(r.get("path", "")).lower() not in have]
        cur["paths"] = list(dict.fromkeys(list(cur.get("paths", [])) + list(ent.get("paths", []))))
        out[key] = cur
    return out


def _merge_file(src: Path, dst: Path, notes: List[str]) -> None:
    """One file of an imported profile into the user's folder - never overwriting."""
    rel = dst.name
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    if src.read_bytes() == dst.read_bytes():
        return
    if rel == "settings.json":
        notes.append("your settings on this computer were kept")
        return
    if rel in ("run_history.json", "compare_window.json", "compare_colours.json",
               "moved_data.json"):
        try:
            a = json.loads(dst.read_text(encoding="utf-8"))
            b = json.loads(src.read_text(encoding="utf-8"))
        except ValueError:
            a = b = None
        if isinstance(a, dict) and isinstance(b, dict):
            m = _merge_index(a, b) if rel == "run_history.json" else _deep_merge(a, b)
            dst.write_text(json.dumps(m, indent=1), encoding="utf-8")
            return
        if isinstance(a, list) and isinstance(b, list):
            dst.write_text(json.dumps(a + [x for x in b if x not in a], indent=1),
                           encoding="utf-8")
            return
    if rel.endswith(".jsonl"):
        have = dst.read_text(encoding="utf-8").splitlines()
        new = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln not in have]
        if new:
            with open(dst, "a", encoding="utf-8") as fh:
                fh.write("".join(ln + "\n" for ln in new))
        return
    other = dst.with_name(f"{dst.stem} (imported){dst.suffix}")
    i = 2
    while other.exists():
        other = dst.with_name(f"{dst.stem} (imported {i}){dst.suffix}")
        i += 1
    shutil.copy2(src, other)
    notes.append(f"{dst.name} differed: the imported one is '{other.name}'")


def import_profile(src) -> tuple:
    """A profile from another computer (an exported zip, or a copied folder): a new
    user, or - when a user of that name exists here - merged into theirs (runs,
    groups, colours, labels, templates and saved files added; nothing here is
    overwritten). Returns (user name, [notes])."""
    import tempfile
    import zipfile
    src = Path(src)
    with tempfile.TemporaryDirectory() as tmp:
        if src.is_file() and src.suffix.lower() == ".zip":
            with zipfile.ZipFile(src) as z:
                for m in z.namelist():
                    if m.startswith("/") or ".." in Path(m).parts or ":" in m:
                        raise ValueError("This zip has unsafe file names - not imported.")
                z.extractall(tmp)
            tops = [p for p in Path(tmp).iterdir() if p.is_dir()]
            folder = tops[0] if len(tops) == 1 else Path(tmp)
        elif src.is_dir():
            folder = src
        else:
            raise ValueError("Choose an exported profile (.zip) or a profile folder.")
        try:
            prof = json.loads((folder / PROFILE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prof = {}
        if not prof and not any((folder / n).exists() for n in DATA_NAMES):
            raise ValueError("This is not a PeterPiper profile (no profile.json or settings).")
        raw = str(prof.get("name") or folder.name)
        for root in (EXPORT_ROOT,) + LEGACY_EXPORT_ROOTS:
            if raw.startswith(root):
                raw = raw[len(root):]
                break
        name = clean_name(raw)
        existing = next((u for u in all_users() if u.lower() == name.lower()), None)
        notes: List[str] = []
        if existing is None:
            d = _load()
            d["users"] = all_users() + [name]
            d.setdefault("folders", {})[name] = _free_folder(name, d)
            if prof.get("aliases"):
                d.setdefault("aliases", {})[name] = [str(a) for a in prof["aliases"]]
            _save(d)
            notes.append(f"new user '{name}'")
        else:
            name = existing
            d = _load()
            d["hidden"] = [h for h in d.get("hidden", []) if h.lower() != name.lower()]
            olds = list((d.get("aliases") or {}).get(name, []))
            d.setdefault("aliases", {})[name] = list(dict.fromkeys(
                olds + [str(a) for a in prof.get("aliases", []) if str(a) != name]))
            _save(d)
            notes.append(f"merged into '{name}' (nothing here was overwritten)")
        dst = base_dir() / "users" / _folder_of(name)
        dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(folder.rglob("*")):
            if f.is_file() and f.name != PROFILE_FILE:
                _merge_file(f, dst / f.relative_to(folder), notes)
        _write_profile(name)
    return name, notes
