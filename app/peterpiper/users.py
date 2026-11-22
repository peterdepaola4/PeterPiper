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

PeterPiper 1.1 (part "profiles"):
* Merge profiles (merge_users / import_profile(into=...)): the same person under
  two spellings ("Ana Lopez" here, "A. Lopez" from the Mac) becomes ONE user.
  Everything of the merged profile is added to the kept one without overwriting
  anything; the merged one is then hidden (nothing deleted; adding its name again
  brings it back) and its name becomes an alias of the kept user (users.json
  'merged' + 'aliases'), so files and OUTPUT_<movie>/<old folder> results that
  carry the old name count as the kept user's.
  MERGE RULES (manual merge and import - the kept profile wins every tie):
    - settings.json: the kept user's settings stay; settings the kept one does
      not have at all are added; the merged one's own settings are also kept as
      a saved setting 'Settings of <name>' (Saved settings), so nothing is lost.
    - run list (run_history.json): every run of both - movies matched by
      fingerprint, runs united by file path (history.merge_run_indexes).
    - every other JSON file of the profile (compare colours, compare window
      choices, achievements, every userprefs topic ...): dictionaries are united
      key by key (nothing lost); where both have a single value (or a list) for
      the same key the kept profile's value stays.
    - logs (*.jsonl, e.g. the saved-files log): lines united.
    - files in sub-folders (Prism style templates, Saved settings, trained
      Auto-detects, anything else): new ones copied; a different file of the same
      name is kept next to it as '<name> (from <other>)' / '(imported)'.
    - per-computer files are not taken from another computer (storage.json:
      results location, queue.json: movie queue, sync.json: sync state).
* Keeping a profile in step through a folder: profilesync.py. Lab user list:
  labshare.py. Both are called from activate() / deactivate() / add_user() ...
  through guarded imports (a missing module only hides the feature).
* Roles: "user" (default), "admin", "developer" (a title only: the same abilities
  as admin). The first user made on a computer is admin. Old users.json files
  without roles: the user who took over the old data (else the first user) is
  admin. If no visible user is admin any more, that default admin is again.
* Optional passwords (off by default): only a salted hash (PBKDF2-SHA256, a random
  salt per user, many rounds) is stored, in the user's folder (password.json) and,
  when a lab folder is linked, in the lab list. This keeps profiles tidy and
  private between colleagues; it is NOT strong security (the files are on a
  shared disk).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

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

ROLES = ("user", "admin", "developer")
ROLE_LABELS = {"user": "User", "admin": "Admin", "developer": "Developer"}

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


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def user_dir(name: str) -> Path:
    """1.1: <data>/users/<folder> of this user (whether chosen or not)."""
    return base_dir() / "users" / _folder_of(name)


def _follow(name: Optional[str]) -> Optional[str]:
    """1.1: a user merged into another (Merge profiles) -> the kept user."""
    if not name:
        return name
    merged = {str(k).lower(): str(v) for k, v in (_load().get("merged") or {}).items()}
    seen = set()
    while name.lower() in merged and name.lower() not in seen:
        seen.add(name.lower())
        name = merged[name.lower()]
    return name


def merged_into(name: str) -> Optional[str]:
    """The user `name` was merged into, or None."""
    k = _follow(name)
    return k if k and k.lower() != name.lower() else None


def _canonical(name: Optional[str]) -> Optional[str]:
    """A name as recorded in a file -> the user's present name (renames, 1.1:
    merged profiles and other spellings)."""
    if not name:
        return None
    n = clean_name(name).lower()
    for u in all_users():
        if u.lower() == n:
            return _follow(u)
    for u, olds in (_load().get("aliases") or {}).items():
        if n in (str(o).lower() for o in olds):
            return _follow(u)
    return clean_name(name)


def aliases_of(name: str) -> List[str]:
    return [str(a) for a in (_load().get("aliases") or {}).get(name, [])]


def add_aliases(name: str, names) -> List[str]:
    """1.1: other spellings of this user (e.g. from another computer or the lab
    list): files recording them count as this user's. Names that are another
    present user's own name are skipped. Returns the names added."""
    d = _load()
    if name not in all_users():
        return []
    others = {u.lower() for u in all_users() if u != name}
    have = [str(a) for a in (d.get("aliases") or {}).get(name, [])]
    low = {a.lower() for a in have} | {name.lower()}
    new = []
    for a in names:
        a = clean_name(str(a))
        if a and a.lower() not in low and a.lower() not in others:
            new.append(a)
            low.add(a.lower())
    if new:
        d.setdefault("aliases", {})[name] = have + new
        _save(d)
        _write_profile(name)
    return new


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


def _hook(module: str, fn: str, *args):
    """Call profilesync / labshare if they are there; never raises."""
    try:
        if module == "labshare":
            from . import labshare as m
        else:
            from . import profilesync as m
        return getattr(m, fn)(*args)
    except Exception:                                              # noqa: BLE001
        return None


def add_user(name: str) -> str:
    n = clean_name(name)
    why = name_problem(n)
    if why:
        raise ValueError(why)
    d = _load()
    back = next((u for u in all_users() if u.lower() == n.lower()), None)
    if back is not None:                        # a removed user, brought back
        d["hidden"] = [h for h in d.get("hidden", []) if h.lower() != back.lower()]
        merged = d.get("merged") or {}          # 1.1: a merged one becomes separate again
        for k in [k for k in merged if str(k).lower() == back.lower()]:
            kept = merged.pop(k)
            al = d.get("aliases") or {}
            if kept in al:
                al[kept] = [a for a in al[kept] if str(a).lower() != back.lower()]
        _save(d)
        _hook("labshare", "on_user_added", back)
        return back
    first = not d.get("legacy_owner")
    _add_raw(n, role="admin" if first and not all_users() else None)
    if first:
        d = _load()
        d["legacy_owner"] = n
        _save(d)
        _give_old_data(n)
    _write_profile(n)
    _hook("labshare", "on_user_added", n)
    return n


def _add_raw(name: str, role: Optional[str] = None, aliases=()) -> str:
    """A new user in users.json (no old data, no lab hook) - lab list / import."""
    d = _load()
    d["users"] = all_users() + [name]
    d.setdefault("folders", {})[name] = _free_folder(name, d)
    if role in ROLES and role != "user":
        d.setdefault("roles", {})[name] = role
    al = [clean_name(a) for a in aliases if clean_name(a) and clean_name(a).lower() != name.lower()]
    if al:
        d.setdefault("aliases", {})[name] = list(dict.fromkeys(al))
    _save(d)
    return name


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
    roles = d.get("roles") or {}
    if old in roles:
        roles[n] = roles.pop(old)
    for key in ("legacy_owner", "last"):
        if d.get(key) == old:
            d[key] = n
    for k, v in list((d.get("merged") or {}).items()):
        if v == old:
            d["merged"][k] = n
    _save(d)
    global _current
    if _current == old:
        _current = n
    _write_profile(n)
    _hook("labshare", "on_user_renamed", old, n)
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
    the last user. 1.1: their profile is then kept in step with their sync folder
    and the lab folder, if any (profilesync - quietly skipped when offline)."""
    global _current
    n = clean_name(name)
    if n not in list_users():
        raise ValueError(f"No user '{n}'.")
    if _current and _current != n:
        _hook("profilesync", "on_deactivate", _current)
    _current = n
    home().mkdir(parents=True, exist_ok=True)
    d = _load()
    d["last"] = n
    _save(d)
    _write_profile(n)
    _hook("profilesync", "on_activate", n)
    return home()


def deactivate() -> None:
    global _current
    if _current:
        _hook("profilesync", "on_deactivate", _current)
    _current = None


# ------------------------------------------------------------ roles (1.1)
def _default_admin() -> Optional[str]:
    """Who is admin when nobody visible has the admin / developer role: the user
    who took over the old data, else the first user still on the list."""
    vis = list_users()
    lo = legacy_owner()
    if lo and lo in vis:
        return lo
    return vis[0] if vis else None


def role(name: Optional[str]) -> str:
    """'user', 'admin' or 'developer' (developer: a title only, admin's abilities)."""
    if not name:
        return "user"
    d = _load()
    r = str((d.get("roles") or {}).get(name) or "")
    if r in ROLES and r != "user":
        return r
    roles = d.get("roles") or {}
    vis = list_users()
    if not any(str(roles.get(u)) in ("admin", "developer") for u in vis):
        if name == _default_admin():
            return "admin"
    return "user"


def role_label(name: Optional[str]) -> str:
    return ROLE_LABELS.get(role(name), "User")


def is_admin(name: Optional[str]) -> bool:
    """Admins and developers may change the lab settings and other people's roles."""
    return role(name) in ("admin", "developer")


def admins() -> List[str]:
    return [u for u in list_users() if is_admin(u)]


def roles_offered(name: Optional[str]) -> List[str]:
    """4.0: the roles a role menu offers for this person: user and admin; the third
    only for a person who already has it or has found a certain extra."""
    out = ["user", "admin"]
    if name and (role(name) == "developer" or _found_crown(name)):
        out.append("developer")
    return out


def _found_crown(name: str) -> bool:
    try:
        from . import achievements
        return "crown" in achievements.found_for(name)
    except Exception:                                              # noqa: BLE001
        return False


def set_role(name: str, new_role: str, sync_lab: bool = True) -> None:
    """Make a user admin / developer / user. Refused (ValueError) when it would
    leave nobody admin."""
    new_role = str(new_role).lower()
    if new_role not in ROLES:
        raise ValueError(f"Not a role: {new_role}")
    if name not in all_users():
        raise ValueError(f"No user '{name}'.")
    if new_role == "user" and is_admin(name) and \
            not [a for a in admins() if a != name]:
        raise ValueError(f"'{name}' is the only admin - make someone else admin first.")
    if sync_lab and _hook("labshare", "would_leave_no_admin", name, new_role):
        raise ValueError(f"'{name}' is the lab's only admin - make someone else admin first.")
    d = _load()
    roles = d.setdefault("roles", {})
    # the default admin becomes an explicit one, so making a second admin
    # does not take the first one's role away
    for u in admins():
        if u != name and str(roles.get(u)) not in ("admin", "developer"):
            roles[u] = "admin"
    roles[name] = new_role
    _save(d)
    if sync_lab:
        _hook("labshare", "on_role_changed", name, new_role)


# --------------------------------------------------------- passwords (1.1)
PASSWORD_FILE = "password.json"          # in the user's folder: salted hash only
PW_ROUNDS = 200_000


def _pw_path(name: str) -> Path:
    return user_dir(name) / PASSWORD_FILE


def password_record(name: str) -> dict:
    """{'algo', 'n', 'salt', 'hash', 'set'} - hash '' = no password; {} if never set."""
    try:
        d = json.loads(_pw_path(name).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def has_password(name: Optional[str]) -> bool:
    return bool(name) and bool(password_record(name).get("hash"))


def _pw_hash(password: str, salt: bytes, rounds: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds).hex()


def make_password_record(password: str) -> dict:
    now = datetime.now().isoformat(timespec="microseconds")    # newer one wins on sync
    if not password:
        return dict(algo="pbkdf2_sha256", n=0, salt="", hash="", set=now)
    salt = secrets.token_bytes(16)
    return dict(algo="pbkdf2_sha256", n=PW_ROUNDS, salt=salt.hex(),
                hash=_pw_hash(password, salt, PW_ROUNDS), set=now)


def write_password_record(name: str, rec: dict, sync_lab: bool = True) -> None:
    p = _pw_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)
    if sync_lab:
        _hook("labshare", "on_password_changed", name)


def set_password(name: str, password: str) -> None:
    """Set (or with '' clear) this user's password. Only a salted hash is kept."""
    if name not in all_users():
        raise ValueError(f"No user '{name}'.")
    write_password_record(name, make_password_record(password or ""))


def clear_password(name: str) -> None:
    """An admin's 'reset': the user has no password any more."""
    set_password(name, "")


def check_password(name: str, password: str) -> bool:
    """True if the user has no password, or this is it (constant-time compare)."""
    rec = password_record(name)
    if not rec.get("hash"):
        return True
    try:
        got = _pw_hash(password or "", bytes.fromhex(str(rec.get("salt", ""))),
                       int(rec.get("n") or PW_ROUNDS))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, str(rec["hash"]))


def can_manage_lab(name: Optional[str], password: Optional[str] = None) -> bool:
    """May `name` open Lab settings? Admin / developer, with their password if set."""
    if not name or name not in list_users() or not is_admin(name):
        return False
    return check_password(name, password or "") if has_password(name) else True


# ------------------------------------------------------------ whose run is it
def output_dir(nd2_path) -> str:
    """The default results folder of a movie: OUTPUT_<movie>/<user folder> (next
    to it); OUTPUT_<movie> with no user chosen. 1.1: if this user chose a results
    location (e.g. a folder in their OneDrive / Box / Google Drive - storage.json,
    key "results_root"), OUTPUT_<movie> goes there instead of next to the movie."""
    p = Path(str(nd2_path))
    root = _results_root()
    out = (Path(root) if root else p.parent) / f"OUTPUT_{p.stem}"
    return str(out / _folder_of(_current)) if _current else str(out)


def _results_root() -> str:
    """The results location this user chose (1.1, storage.json), or ''."""
    if not _current:
        return ""
    try:
        from . import userprefs
        return str(userprefs.load("storage").get("results_root") or "")
    except Exception:                                              # noqa: BLE001
        return ""


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
    ...), or None. 1.1: the folder of a merged profile -> the kept user."""
    parts = Path(str(path)).parts
    folders = _folders()
    for i, part in enumerate(parts[:-1]):
        if part.upper().startswith("OUTPUT_") and i + 1 < len(parts) - 1:
            u = folders.get(parts[i + 1].lower())
            if u is not None:
                return _follow(u)
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
# 1.1: files that belong to one computer, not to the person (never taken from
# another computer; sync.json is never copied at all)
COMPUTER_ONLY = ("storage.json", "queue.json", "sync.json")
_SKIP_NAMES = ("desktop.ini", "thumbs.db")


def skip_in_profile(rel: Path, foreign: bool = True) -> bool:
    """1.1: True for a file of a profile folder that is not merged / synced:
    drawn theme icons, temporary and lock files, hidden / system files,
    profile.json (handled on its own), sync.json, and - from another computer
    (`foreign`) - the per-computer files (storage.json, queue.json)."""
    parts = Path(rel).parts
    if not parts:
        return True
    name = parts[-1]
    low = name.lower()
    if parts[0] == "theme" and len(parts) > 1:
        return True
    if low.startswith(".") or low in _SKIP_NAMES or low.endswith((".tmp", ".lock", ".pp-tmp")) \
            or low.startswith("~$"):
        return True
    if len(parts) == 1:
        if low == PROFILE_FILE or low == "sync.json":
            return True
        if foreign and low in COMPUTER_ONLY:
            return True
    return False


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
    added to the list under the name in their profile.json. Returns the names.
    1.1: with a linked lab folder, new lab members are added too (labshare)."""
    added = _adopt_folders()
    lab = _hook("labshare", "apply_at_start")
    if isinstance(lab, list):
        added += [n for n in lab if n not in added]
    return added


def _adopt_folders() -> List[str]:
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
                    and rel.parts[0] != "theme" \
                    and not (len(rel.parts) == 1 and f.name == "sync.json"):
                z.write(f, f"{root}/{rel.as_posix()}")
    return str(out)


# ------------------------------------------------------------ merging (1.1)
def _deep_merge(mine, theirs):
    """theirs into mine: keys mine lacks are added, dicts merged, mine wins."""
    if isinstance(mine, dict) and isinstance(theirs, dict):
        out = dict(mine)
        for k, v in theirs.items():
            out[k] = _deep_merge(mine[k], v) if k in mine else v
        return out
    return mine


def _merge_index(mine: dict, theirs: dict) -> dict:
    """Run lists: every run of both (movies by fingerprint, runs by file path);
    what is here comes first (history.merge_run_indexes)."""
    from .history import merge_run_indexes
    return merge_run_indexes(mine, theirs)


def _dump(obj) -> bytes:
    return json.dumps(obj, indent=1).encode("utf-8")


def merge_bytes(name: str, mine: bytes, theirs: bytes, prefer_mine: bool = True
                ) -> Optional[bytes]:
    """1.1: two versions of one top-level profile file -> the merged contents, or
    None if this kind of file cannot be merged (then both copies are kept).
    `prefer_mine`: whose single values win (dictionaries are always united)."""
    low = name.lower()
    if low.endswith(".jsonl"):
        a = mine.decode("utf-8", "replace").splitlines()
        have = set(a)
        b = [ln for ln in theirs.decode("utf-8", "replace").splitlines() if ln not in have]
        return "".join(ln + "\n" for ln in a + b).encode("utf-8")
    if not low.endswith(".json"):
        return None
    try:
        a = json.loads(mine.decode("utf-8"))
        b = json.loads(theirs.decode("utf-8"))
    except ValueError:
        return None
    if low == "run_history.json" and isinstance(a, dict) and isinstance(b, dict):
        return _dump(_merge_index(a, b))
    if low == PASSWORD_FILE and isinstance(a, dict) and isinstance(b, dict):
        return _dump(a if prefer_mine else b)              # one whole record, never mixed
    if isinstance(a, dict) and isinstance(b, dict):
        return _dump(_deep_merge(a, b) if prefer_mine else _deep_merge(b, a))
    if isinstance(a, list) and isinstance(b, list):
        return _dump(a + [x for x in b if x not in a])
    return None


def _aside_name(dst: Path, tag: str) -> Path:
    other = dst.with_name(f"{dst.stem} ({tag}){dst.suffix}")
    i = 2
    while other.exists():
        other = dst.with_name(f"{dst.stem} ({tag} {i}){dst.suffix}")
        i += 1
    return other


def _merge_file(src: Path, dst: Path, notes: List[str], tag: str = "imported",
                top: bool = True) -> None:
    """One file of another profile into the user's folder - never overwriting
    (see MERGE RULES at the top)."""
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    a, b = dst.read_bytes(), src.read_bytes()
    if a == b:
        return
    if top:
        m = merge_bytes(dst.name, a, b, prefer_mine=True)
        if m is not None:
            if m != a:
                tmp = dst.with_name(dst.name + ".pp-tmp")
                tmp.write_bytes(m)
                os.replace(tmp, dst)
            if dst.name == "settings.json":
                notes.append("the settings here were kept")
            return
    other = _aside_name(dst, tag)
    shutil.copy2(src, other)
    notes.append(f"{dst.name} differed: the other one is '{other.name}'")


def _merge_tree(src: Path, dst: Path, notes: List[str], tag: str, foreign: bool) -> int:
    """Every file of profile folder `src` into `dst` (MERGE RULES). Returns the
    number of files looked at."""
    n = 0
    dst.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        if skip_in_profile(rel, foreign=foreign):
            continue
        n += 1
        try:
            _merge_file(f, dst / rel, notes, tag=tag, top=len(rel.parts) == 1)
        except OSError as exc:
            notes.append(f"{rel.as_posix()} not merged: {exc}")
    return n


def _json_file(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def describe_merge(src: Path, dst: Path, foreign: bool = True) -> List[str]:
    """1.1: what merging profile folder `src` into `dst` would bring, in short
    lines for the confirmation (nothing is changed)."""
    from .history import _path_key
    lines: List[str] = []
    a = _json_file(dst / "run_history.json") or {}
    b = _json_file(src / "run_history.json") or {}
    if isinstance(a, dict) and isinstance(b, dict):
        have = {(k, _path_key(r.get("path", ""))) for k, e in a.items() if isinstance(e, dict)
                for r in e.get("runs", []) if isinstance(r, dict)}
        new = [(k, r) for k, e in b.items() if isinstance(e, dict)
               for r in e.get("runs", []) if isinstance(r, dict)
               and (k, _path_key(r.get("path", ""))) not in have]
        movies = {k for k, _r in new}
        lines.append(f"Run list: {len(new)} run(s) of {len(movies)} movie(s) added"
                     if new else "Run list: nothing new")
    ca = ((_json_file(dst / "compare_colours.json") or {}).get("names") or {}) \
        if isinstance(_json_file(dst / "compare_colours.json"), dict) else {}
    cb = ((_json_file(src / "compare_colours.json") or {}).get("names") or {}) \
        if isinstance(_json_file(src / "compare_colours.json"), dict) else {}
    newc = [k for k in cb if k not in ca]
    if cb:
        lines.append(f"Compare colours: {len(newc)} name(s) added" if newc else
                     "Compare colours: nothing new")
    sub: Dict[str, List[int]] = {}
    tops: List[str] = []
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        if skip_in_profile(rel, foreign=foreign):
            continue
        t = dst / rel
        if len(rel.parts) == 1:
            if rel.name in ("run_history.json", "compare_colours.json", PASSWORD_FILE):
                continue
            if not t.exists() or t.read_bytes() != f.read_bytes():
                tops.append(rel.name)
            continue
        c = sub.setdefault(rel.parts[0], [0, 0])
        if not t.exists():
            c[0] += 1
        elif t.read_bytes() != f.read_bytes():
            c[1] += 1
    for folder, (nn, nd) in sorted(sub.items()):
        if nn or nd:
            lines.append(f"{folder}: {nn} added" + (f", {nd} kept as a second copy" if nd else ""))
    if "settings.json" in tops:
        lines.append("Settings: the kept profile's settings stay (the other's are kept as a "
                     "saved setting)")
        tops.remove("settings.json")
    if tops:
        lines.append("Also united: " + ", ".join(t.rsplit(".", 1)[0].replace("_", " ")
                                                 for t in tops))
    return lines or ["Nothing new to bring over."]


def _keep_settings_copy(src: Path, dst: Path, who: str, notes: List[str]) -> None:
    """The merged-away profile's own settings -> a saved setting of the kept user."""
    a, b = _json_file(dst / "settings.json"), _json_file(src / "settings.json")
    if not (isinstance(b, dict) and isinstance(b.get("settings"), dict)):
        return
    if isinstance(a, dict) and a.get("settings") == b.get("settings"):
        return
    try:
        from . import __version__
        folder = dst / "Saved settings"
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w .()-]", "-", f"Settings of {who}").strip()[:80]
        p = _aside_name(folder / f"{safe}.json", "2") if (folder / f"{safe}.json").exists() \
            else folder / f"{safe}.json"
        p.write_text(json.dumps({"kind": "PeterPiper saved settings", "name": f"Settings of {who}",
                                 "version": __version__, "saved": _now(),
                                 "analysis": b["settings"]}, indent=1), encoding="utf-8")
        notes.append(f"{who}'s settings are kept as the saved setting '{p.stem}'")
    except OSError:
        pass


def merge_preview(keep: str, other: str) -> List[str]:
    """What Merge profiles would bring from `other` into `keep` (nothing changed)."""
    return describe_merge(user_dir(other), user_dir(keep), foreign=False)


def merge_users(keep: str, other: str) -> List[str]:
    """1.1 Merge profiles: two profiles of the same person on this computer (e.g.
    'Ana Lopez' and 'A. Lopez') become one. Everything of `other` is added to
    `keep` (MERGE RULES - nothing overwritten); `other` is then hidden (nothing
    deleted; adding the name again brings it back) and its name, spellings, run
    files and results folders count as `keep`'s. Returns notes."""
    if keep not in all_users() or other not in all_users():
        raise ValueError("Pick two users of this computer.")
    if keep == other:
        raise ValueError("Pick two different users.")
    notes: List[str] = []
    src, dst = user_dir(other), user_dir(keep)
    if src.is_dir():
        _keep_settings_copy(src, dst, other, notes)
        _merge_tree(src, dst, notes, tag=f"from {folder_name(other)}", foreign=False)
    d = _load()
    al = d.setdefault("aliases", {})
    al[keep] = list(dict.fromkeys([str(a) for a in al.get(keep, [])] + [other]
                                  + [str(a) for a in al.get(other, []) if str(a) != keep]))
    d.setdefault("merged", {})[other] = keep
    for k, v in list(d["merged"].items()):            # earlier merges into `other`
        if v == other:
            d["merged"][k] = keep
    d["hidden"] = list(dict.fromkeys(list(d.get("hidden", [])) + [other]))
    roles = d.setdefault("roles", {})
    order = {"user": 0, "admin": 1, "developer": 2}
    r_keep, r_other = role(keep), role(other)
    if order.get(r_other, 0) > order.get(r_keep, 0):
        roles[keep] = r_other
    elif r_keep != "user":
        roles[keep] = r_keep
    for key in ("legacy_owner", "last"):
        if d.get(key) == other:
            d[key] = keep
    _save(d)
    if not has_password(keep) and has_password(other):
        write_password_record(keep, password_record(other), sync_lab=False)
    _write_profile(keep)
    global _current
    if _current == other:
        _current = keep
    _hook("profilesync", "on_users_merged", keep, other)
    _hook("labshare", "on_users_merged", keep, other)
    notes.append(f"'{other}' is now part of '{keep}' (hidden from the list, nothing deleted)")
    return notes


@contextmanager
def _profile_source(src) -> Iterator[Tuple[Path, dict, str]]:
    """An exported zip or a profile folder -> (folder, profile.json, its name)."""
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
            prof = prof if isinstance(prof, dict) else {}
        except (OSError, ValueError):
            prof = {}
        if not prof and not any((folder / n).exists() for n in DATA_NAMES):
            raise ValueError("This is not a PeterPiper profile (no profile.json or settings).")
        raw = str(prof.get("name") or folder.name)
        for root in (EXPORT_ROOT,) + LEGACY_EXPORT_ROOTS:
            if raw.startswith(root):
                raw = raw[len(root):]
                break
        yield folder, prof, clean_name(raw)


def profile_name(src) -> str:
    """The name inside an exported profile (.zip) or profile folder."""
    with _profile_source(src) as (_f, _p, name):
        return name


def import_preview(src, into: Optional[str] = None) -> Tuple[str, List[str]]:
    """(the profile's own name, what importing it into `into` would bring)."""
    with _profile_source(src) as (folder, _prof, name):
        target = into or next((u for u in all_users() if u.lower() == name.lower()), None)
        if target is None:
            return name, [f"A new user '{name}' with everything of this profile."]
        return name, describe_merge(folder, user_dir(target), foreign=True)


def import_profile(src, into: Optional[str] = None) -> tuple:
    """A profile from another computer (an exported zip, or a copied folder): a new
    user, or - when a user of that name exists here, or 1.1: into the user `into`
    (the name may differ: it becomes one of their spellings) - merged into theirs
    (runs, groups, colours, labels, templates and saved files added; nothing here
    is overwritten). Returns (user name, [notes])."""
    with _profile_source(src) as (folder, prof, name):
        if into is not None and into not in all_users():
            raise ValueError(f"No user '{into}'.")
        existing = into or next((u for u in all_users() if u.lower() == name.lower()), None)
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
            d = _load()
            d["hidden"] = [h for h in d.get("hidden", []) if h.lower() != existing.lower()]
            _save(d)
            add_aliases(existing, [name] + [str(a) for a in prof.get("aliases", [])])
            notes.append(f"merged into '{existing}' (nothing here was overwritten)")
            name = existing
        dst = base_dir() / "users" / _folder_of(name)
        _merge_tree(folder, dst, notes, tag="imported", foreign=True)
        _write_profile(name)
    return name, notes
