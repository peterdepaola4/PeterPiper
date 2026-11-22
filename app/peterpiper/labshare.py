"""
The lab's shared PeterPiper folder - "lab user repository" (PeterPiper 1.1, part
"profiles").

An admin (or developer - the same abilities, only the title differs) creates a LAB
FOLDER on a lab server or a cloud drive (OneDrive, Google Drive, Box, Dropbox,
iCloud Drive, a network share ...) and links it on each lab computer. PeterPiper
never talks to the network: the lab folder is just a folder, carried by the cloud
app or the network share.

    <lab folder>/PeterPiper lab users.json        the lab user list (below)
    <lab folder>/PeterPiper profiles/
        PeterPiper profile - <name>/              each person's profile, laid out
                                                  like an exported profile

The lab user list (no passwords in plain text - optional salted hashes only):
    {"kind": "PeterPiper lab users", "version": 1, "updated": ISO time,
     "settings": {"anyone_can_add": true, "changed": ISO},
     "people": [{"name": "Ana Lopez", "aliases": ["A. Lopez"], "role": "admin",
                 "role_at": ISO, "hidden": false, "hidden_at": ISO,
                 "password": {...salted hash record or {}}, "added": ISO,
                 "changed": ISO}, ...],
     "data_folders": [{"path": "...", "label": "Confocal movies", "removed": false,
                       "changed": ISO}, ...]}

Each linked computer, at start (users.adopt_copied_profiles -> apply_at_start):
  * new lab members appear in 'Who is using PeterPiper?';
  * spellings / aliases map to one person: a local user whose name or alias is any
    of a lab person's names IS that person (the local name stays; the lab's names
    become their aliases, so 'Ana Lopez' on the Mac and 'A. Lopez' on Windows are
    one person and her runs count as hers on both);
  * nobody is removed just because the list changed; a person is hidden here only
    when the lab list says hidden (never deleted);
  * roles and passwords come from the list (the newer change wins);
  * each person's profile is kept in step with their folder in the lab folder
    (profilesync, when they are chosen and when PeterPiper closes).
Adding a user on a linked computer adds them to the lab list (if the lab allows
"anyone can add themselves"; else only an admin can add).

Conflicts (two computers writing at once, or a cloud app's conflict copies such as
'PeterPiper lab users (1).json'): every 'PeterPiper lab users*.json' in the lab
folder is read and united; people are united by any shared name/alias; for single
values the newer change wins; every write is a temporary file + os.replace. A
read-only lab folder is read only (the window says so).

The link is per COMPUTER, in <PeterPiper data>/users.json ("lab"), not per user;
so are the computer's own data folders when no lab is linked ("data_folders").

4.0 - the lab folder made obvious (one concept: this same lab folder):
    <lab folder>/.peterpiper-lab.json             marker: lab name, layout version,
                                                  created by / when, where things are
    <lab folder>/READ ME - PeterPiper lab folder.txt
    <lab folder>/People/<person>/Results|Exports|Backups|Movies
    <lab folder>/Shared/PeterPiper profiles|Detectors|Prism templates|Settings
  setup_lab_folder(folder, name, by)   make that layout (someone choosing to - the
                                       admin); an EXISTING 1.1 lab folder is adopted:
                                       the marker records what is already there
                                       (its 'PeterPiper profiles' stay put) - nothing
                                       is moved or deleted.
  find_lab_root(path)                  any folder in or below a lab -> its root
                                       (walks up to the marker / lab list)
  connect(path, user)                  link this computer (root stored per computer:
                                       Windows and Mac paths differ; everything inside
                                       is relative) and make People/<user>
  scan_for_labs(roots)                 lab folders in the top levels of the sync apps'
                                       folders (for a background thread)
  person_dir(user) / lab_path(key)     where a person's / the lab's things are
  own_folder_setup(user)               the user's results go to a folder of their own
                                       (not People/<user>): explained, switch offered
  health()                             reachable / writable / sync app running / disk
                                       space -> Health(level, text, fix)
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import users

LAB_FILE = "PeterPiper lab users.json"
PROFILES_DIR = "PeterPiper profiles"
KIND = "PeterPiper lab users"
_last_apply = 0.0
APPLY_EVERY_S = 5.0                 # at start it is asked twice: read the list once


def _now() -> str:
    """Change times to the microsecond: two changes in one second still order."""
    return datetime.now().isoformat(timespec="microseconds")


def _key(name: str) -> str:
    return users.clean_name(str(name)).lower()


def _path_key(p) -> str:
    return str(p).replace("\\", "/").rstrip("/").lower()


# ------------------------------------------------------------------ the link
def link_info() -> dict:
    d = users._load().get("lab")
    return dict(d) if isinstance(d, dict) else {}


def linked_folder() -> Optional[str]:
    return link_info().get("folder") or None


def _set_link(**kw) -> None:
    d = users._load()
    lab = d.get("lab") if isinstance(d.get("lab"), dict) else {}
    lab.update(kw)
    d["lab"] = lab
    users._save(d)


def _bind(local: str, lab_name: str) -> None:
    d = users._load()
    b = d.setdefault("lab_names", {})
    if b.get(local) != lab_name:
        b[local] = lab_name
        users._save(d)


def _bound_name(local: str) -> Optional[str]:
    return (users._load().get("lab_names") or {}).get(local)


def writable(folder) -> bool:
    """Can this computer write in the folder? (a test file, removed again)"""
    p = Path(folder) / f".pp-write-test-{secrets.token_hex(4)}"
    try:
        p.write_bytes(b"")
        p.unlink()
        return True
    except OSError:
        return False


def is_lab_folder(folder) -> bool:
    """A lab folder: it holds the lab user list (1.1) or the 4.0 marker file."""
    try:
        return (Path(folder) / LAB_FILE).is_file() or (Path(folder) / MARKER).is_file()
    except OSError:
        return False


def status() -> str:
    """One line for the first window."""
    info = link_info()
    if not info.get("folder"):
        return "not linked"
    s = str(info["folder"])
    if info.get("last"):
        try:
            t = datetime.fromisoformat(info["last"])
            s += "  -  updated " + (t.strftime("today %H:%M") if t.date() == datetime.now().date()
                                    else t.strftime("%d %b %Y %H:%M"))
        except ValueError:
            pass
    if info.get("readonly"):
        s += "  (read-only: this computer can only read it)"
    if info.get("note"):
        s += f"  ({info['note']})"
    return s


# ------------------------------------------------------------ the list file
def _blank() -> dict:
    return {"kind": KIND, "version": 1, "updated": "",
            "settings": {"anyone_can_add": True, "changed": ""},
            "people": [], "data_folders": []}


def _read_one(p: Path) -> Optional[dict]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("kind") != KIND:
        return None
    return d


def read_list(folder) -> dict:
    """The lab list: the file and any conflict copies the cloud app made, united."""
    out = _blank()
    f = Path(folder)
    try:
        files = sorted(f.glob("PeterPiper lab users*.json"))
    except OSError:
        files = []
    for p in files:
        d = _read_one(p)
        if d is not None:
            out = merge_lists(out, d)
    return out


def _person(e: dict) -> Optional[dict]:
    if not isinstance(e, dict) or not users.clean_name(str(e.get("name") or "")):
        return None
    pw = e.get("password") if isinstance(e.get("password"), dict) else {}
    return dict(name=users.clean_name(str(e["name"])),
                aliases=[users.clean_name(str(a)) for a in e.get("aliases") or []
                         if users.clean_name(str(a))],
                role=str(e.get("role") or "user") if str(e.get("role") or "user") in users.ROLES
                else "user",
                role_at=str(e.get("role_at") or ""), hidden=bool(e.get("hidden")),
                hidden_at=str(e.get("hidden_at") or ""), password=dict(pw),
                added=str(e.get("added") or ""), changed=str(e.get("changed") or ""))


def _fold(people: List[dict]) -> List[dict]:
    """People sharing any name or alias are one person (a rename, 'same person',
    or the same entry on two computers). For each value the newer change wins;
    the aliases are united; the present name is one nobody else lists as old."""
    ents = [p for p in (_person(e) for e in people) if p is not None]
    parent = list(range(len(ents)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owner: Dict[str, int] = {}
    for i, e in enumerate(ents):
        for n in [e["name"]] + e["aliases"]:
            k = n.lower()
            if k in owner:
                parent[find(i)] = find(owner[k])
            else:
                owner[k] = i
    groups: Dict[int, List[dict]] = {}
    for i, e in enumerate(ents):
        groups.setdefault(find(i), []).append(e)
    out = []
    for grp in groups.values():
        def latest(seq, field):            # the newest; on a tie the later one (incoming)
            return max(enumerate(seq), key=lambda ie: (str(ie[1][field]), ie[0]))[1]
        newest = latest(grp, "changed")
        olds = {a.lower() for e in grp for a in e["aliases"]}
        cands = [e for e in grp if e["name"].lower() not in olds]
        name = (latest(cands, "changed") if cands else newest)["name"]
        allnames = []
        for e in sorted(grp, key=lambda e: e["added"] or e["changed"]):
            allnames += [e["name"]] + e["aliases"]
        aliases = list(dict.fromkeys(a for a in allnames if a.lower() != name.lower()))
        dedup, seen = [], set()
        for a in aliases:
            if a.lower() not in seen:
                seen.add(a.lower())
                dedup.append(a)
        r = latest(grp, "role_at")
        h = latest(grp, "hidden_at")
        pw = max(enumerate(e["password"] for e in grp),
                 key=lambda ip: (str(ip[1].get("set") or ""), ip[0]))[1]
        added = min((e["added"] for e in grp if e["added"]), default="")
        out.append(dict(name=name, aliases=dedup, role=r["role"], role_at=r["role_at"],
                        hidden=h["hidden"], hidden_at=h["hidden_at"], password=pw,
                        added=added, changed=newest["changed"]))
    return sorted(out, key=lambda e: e["name"].lower())


def merge_lists(a: dict, b: dict) -> dict:
    """Two lab lists -> one (union; the newer change wins for single values)."""
    out = _blank()
    out["people"] = _fold(list(a.get("people") or []) + list(b.get("people") or []))
    sa = a.get("settings") if isinstance(a.get("settings"), dict) else {}
    sb = b.get("settings") if isinstance(b.get("settings"), dict) else {}
    out["settings"] = dict(_blank()["settings"], **(sa if str(sa.get("changed", "")) >=
                                                     str(sb.get("changed", "")) else sb))
    df: Dict[str, dict] = {}
    for e in list(a.get("data_folders") or []) + list(b.get("data_folders") or []):
        if not isinstance(e, dict) or not e.get("path"):
            continue
        k = _path_key(e["path"])
        if k not in df or str(e.get("changed", "")) > str(df[k].get("changed", "")):
            df[k] = dict(path=str(e["path"]), label=str(e.get("label") or ""),
                         removed=bool(e.get("removed")), changed=str(e.get("changed") or ""))
    out["data_folders"] = list(df.values())
    out["updated"] = max(str(a.get("updated") or ""), str(b.get("updated") or ""))
    return out


def write_list(folder, data: dict) -> bool:
    """Unite `data` with what is in the lab folder now and write it (temporary
    file + os.replace). False if the folder cannot be written."""
    f = Path(folder)
    try:
        merged = merge_lists(read_list(f), data)
        merged["updated"] = _now()
        p = f / LAB_FILE
        tmp = f / f".{LAB_FILE}.{secrets.token_hex(3)}.pp-tmp"
        tmp.write_text(json.dumps(merged, indent=1), encoding="utf-8")
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def _change(fn) -> bool:
    """Read the linked lab list, let fn change it, write it back."""
    folder = linked_folder()
    if not folder or not os.path.isdir(folder):
        return False
    data = read_list(folder)
    fn(data)
    data["people"] = _fold(data["people"])
    return write_list(folder, data)


def _find(data: dict, name: str) -> Optional[dict]:
    k = _key(name)
    for e in data["people"]:
        if e["name"].lower() == k or k in (a.lower() for a in e["aliases"]):
            return e
    return None


# --------------------------------------------------------------- people view
def people(folder=None) -> List[dict]:
    """The lab's people (folded), from the linked lab folder (or `folder`)."""
    folder = folder or linked_folder()
    if not folder:
        return []
    return list(read_list(folder)["people"])


def person_of(local: str, data: Optional[dict] = None) -> Optional[dict]:
    """The lab person a local user is (by the binding, else by any name/alias)."""
    folder = linked_folder()
    if not folder:
        return None
    if data is None:
        if not os.path.isdir(folder):
            return None
        data = read_list(folder)
    names = [n for n in [_bound_name(local), local] + users.aliases_of(local) if n]
    for n in names:
        e = _find(data, n)
        if e is not None:
            return e
    return None


def _local_match(names: List[str]) -> Optional[str]:
    """The local user who is one of these names (their own name or an alias)."""
    want = {n.lower() for n in names}
    best = None
    for u in users.all_users():
        cand = {u.lower()} | {a.lower() for a in users.aliases_of(u)}
        b = _bound_name(u)
        if b:
            cand.add(b.lower())
        if cand & want:
            u2 = users._follow(u) or u
            if u2 in users.list_users():
                return u2
            best = best or u2
    return best


def profile_target(local: str) -> Optional[Tuple[str, Path, bool]]:
    """(lab folder, this person's profile folder in it, may write) - for profilesync;
    None when no lab is linked or the user is not on the lab list."""
    folder = linked_folder()
    if not folder:
        return None
    lab_name = _bound_name(local)
    if not lab_name:
        return None
    target = lab_path("profiles", folder) / (users.EXPORT_ROOT + users.folder_name(lab_name))
    return folder, target, not link_info().get("readonly")


# ----------------------------------------------------------- applying at start
def apply_at_start(force: bool = False) -> List[str]:
    """Bring this computer's user list in step with the lab list (see the top).
    Returns the names of users added here. Never raises."""
    global _last_apply
    folder = linked_folder()
    if not folder:
        return []
    if not force and time.monotonic() - _last_apply < APPLY_EVERY_S:
        return []
    _last_apply = time.monotonic()
    try:
        return _apply(folder)
    except Exception as exc:                                    # noqa: BLE001
        _set_link(note=f"could not be read: {exc}")
        return []


def _apply(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        _set_link(note="not reachable now (offline?) - skipped")
        return []
    if not is_lab_folder(folder):
        _set_link(note="no lab list there any more - skipped")
        return []
    ro = not writable(folder)
    data = read_list(folder)
    added: List[str] = []
    push = False
    for p in data["people"]:
        names = [p["name"]] + p["aliases"]
        local = _local_match(names)
        if local is None:
            if p["hidden"]:
                continue
            n = p["name"]
            if users.name_problem(n):
                continue                    # too close to someone else's name here
            users._add_raw(n, role=p["role"], aliases=p["aliases"])
            added.append(n)
            local = n
        else:
            users.add_aliases(local, names)
            if p["role_at"] and users.role(local) != p["role"]:
                try:
                    users.set_role(local, p["role"], sync_lab=False)
                except ValueError:
                    pass
            if p["hidden"] and local in users.list_users():
                users.remove_user(local)
        _bind(local, p["name"])
        lab_pw, my_pw = p["password"], users.password_record(local)
        if str(lab_pw.get("set") or "") > str(my_pw.get("set") or ""):
            users.write_password_record(local, lab_pw, sync_lab=False)
        elif str(my_pw.get("set") or "") > str(lab_pw.get("set") or ""):
            p["password"] = my_pw
            p["changed"] = _now()
            push = True
    if push and not ro:
        write_list(folder, data)
    _set_link(last=_now(), readonly=ro, note="")
    return added


# ------------------------------------------------------- linking / creating
def _entry_for_local(u: str, role_override: Optional[str] = None) -> dict:
    now = _now()
    return dict(name=u, aliases=users.aliases_of(u), role=role_override or users.role(u),
                role_at=now, hidden=False, hidden_at="", password=users.password_record(u),
                added=now, changed=now)


def create_lab(folder, include: List[str], admin: Optional[str]) -> List[str]:
    """'Create a lab folder here': the lab list with these users of this computer
    (whoever creates it is admin in it), their profiles copied in, and this
    computer linked. Returns notes."""
    f = Path(folder)
    f.mkdir(parents=True, exist_ok=True)
    if not writable(f):
        raise ValueError("This folder cannot be written - choose another one.")
    data = read_list(f)
    for u in include:
        r = "developer" if u == admin and users.role(u) == "developer" else \
            ("admin" if u == admin else None)
        data["people"].append(_entry_for_local(u, r))
    if admin and admin not in include:
        data["people"].append(_entry_for_local(admin, "admin"))
    data["settings"] = dict(anyone_can_add=True, changed=_now())
    d = users._load()
    for e in d.get("data_folders") or []:
        if isinstance(e, dict) and e.get("path"):
            data["data_folders"].append(dict(path=e["path"], label=e.get("label", ""),
                                             removed=False, changed=_now()))
    data["people"] = _fold(data["people"])
    if not write_list(f, data):
        raise ValueError("The lab list could not be written there.")
    lab_path("profiles", f).mkdir(parents=True, exist_ok=True)
    _set_link(folder=str(f), last=_now(), readonly=False, note="")
    for u in list(include) + ([admin] if admin and admin not in include else []):
        _bind(u, u)
    notes = [f"lab folder made with {len(include)} user(s)"]
    _sync_people(include)
    return notes


def _sync_people(names) -> None:
    try:
        from . import profilesync
        for u in names:
            profilesync.sync_user(u)
    except Exception:                                           # noqa: BLE001
        pass


def link(folder, include: Optional[List[str]] = None) -> List[str]:
    """Link this computer to an existing lab folder. `include`: users of this
    computer to add to the lab list (those already on it are matched by name /
    alias). The list is then applied here. Returns notes."""
    f = Path(folder)
    if not is_lab_folder(f):
        raise ValueError("This is not a PeterPiper lab folder (choose the lab's PeterPiper "
                         "folder - ask whoever set it up - or set one up).")
    ro = not writable(f)
    _set_link(folder=str(f), readonly=ro, note="")
    notes = []
    if include and not ro:
        data = read_list(f)
        for u in include:
            if person_of(u, data) is None:
                data["people"].append(_entry_for_local(u))
        data["people"] = _fold(data["people"])
        write_list(f, data)
    added = apply_at_start(force=True)
    if added:
        notes.append("from the lab list: " + ", ".join(added))
    if ro:
        notes.append("the lab folder is read-only here: this computer only reads it")
    return notes


def unlink() -> None:
    """This computer stops using the lab folder (nothing is deleted anywhere)."""
    d = users._load()
    d.pop("lab", None)
    d.pop("lab_names", None)
    users._save(d)


# ------------------------------------------------------------ hooks (users)
def _writable_link() -> Optional[str]:
    folder = linked_folder()
    if not folder or link_info().get("readonly") or not os.path.isdir(folder):
        return None
    return folder


def on_user_added(name: str) -> None:
    folder = _writable_link()
    if not folder:
        return
    data = read_list(folder)
    e = person_of(name, data)
    if e is None:
        data["people"].append(_entry_for_local(name))
        e_name = name
    else:
        e_name = e["name"]
        if e["hidden"]:                              # brought back
            e.update(hidden=False, hidden_at=_now(), changed=_now())
    data["people"] = _fold(data["people"])
    if write_list(folder, data):
        _bind(name, e_name)


def on_user_renamed(old: str, new: str) -> None:
    folder = _writable_link()
    d = users._load()
    b = d.get("lab_names") or {}
    if old in b:
        b[new] = b.pop(old)
        users._save(d)
    if not folder:
        return
    data = read_list(folder)
    e = person_of(new, data) or _find(data, old)
    if e is None:
        return
    if e["name"].lower() != new.lower():
        e["aliases"] = [a for a in e["aliases"] if a.lower() != new.lower()] + [e["name"]]
        e["name"] = new
        e["changed"] = _now()
    data["people"] = _fold(data["people"])
    if write_list(folder, data):
        _bind(new, new)


def on_users_merged(keep: str, other: str) -> None:
    """Merge profiles here -> in the lab list they are one person too."""
    folder = _writable_link()
    if not folder:
        return
    data = read_list(folder)
    e = person_of(keep, data)
    o = _find(data, _bound_name(other) or other)
    if e is None:
        data["people"].append(_entry_for_local(keep))
        e = data["people"][-1]
    names = [other] + users.aliases_of(other) + ([o["name"]] + o["aliases"] if o else [])
    e["aliases"] = list(dict.fromkeys(e["aliases"] + [n for n in names
                                                       if n.lower() != e["name"].lower()]))
    e["changed"] = _now()
    data["people"] = _fold(data["people"])
    write_list(folder, data)


def on_role_changed(name: str, role: str) -> None:
    folder = _writable_link()
    if not folder:
        return
    data = read_list(folder)
    e = person_of(name, data)
    if e is None:
        return
    e.update(role=role, role_at=_now(), changed=_now())
    write_list(folder, data)


def on_password_changed(name: str) -> None:
    folder = _writable_link()
    if not folder:
        return
    data = read_list(folder)
    e = person_of(name, data)
    if e is None:
        return
    e.update(password=users.password_record(name), changed=_now())
    write_list(folder, data)


def would_leave_no_admin(name: str, new_role: str) -> bool:
    """In the linked lab list: would this change leave the lab without an admin?"""
    folder = linked_folder()
    if not folder or new_role in ("admin", "developer") or not os.path.isdir(folder):
        return False
    data = read_list(folder)
    me = person_of(name, data)
    if me is None or me["role"] not in ("admin", "developer"):
        return False
    return not [e for e in data["people"] if e is not me and not e["hidden"]
                and e["role"] in ("admin", "developer")]


# ------------------------------------------------- admin: the lab user list
def require_admin(who: Optional[str], password: Optional[str] = None) -> None:
    """PermissionError unless `who` may change lab settings (admin / developer,
    with their password if they set one)."""
    if not users.can_manage_lab(who, password):
        raise PermissionError("Only an admin (or developer) can change the lab settings.")


def lab_add_person(name: str, role: str = "user") -> str:
    n = users.clean_name(name)
    if not n:
        raise ValueError("Type a name.")
    now = _now()
    if not _change(lambda d: d["people"].append(dict(
            name=n, aliases=[], role=role, role_at=now, hidden=False, hidden_at=now,
            password={}, added=now, changed=now))):
        raise ValueError("The lab list could not be written.")
    apply_at_start(force=True)
    return n


def lab_rename(name: str, new: str) -> None:
    n = users.clean_name(new)

    def fn(d):
        e = _find(d, name)
        if e is None:
            raise ValueError(f"'{name}' is not on the lab list.")
        if _find(d, n) not in (None, e):
            raise ValueError(f"'{n}' is already someone else on the lab list.")
        e["aliases"] = [a for a in e["aliases"] if a.lower() != n.lower()] + [e["name"]]
        e["name"] = n
        e["changed"] = _now()
    if not _change(fn):
        raise ValueError("The lab list could not be written.")
    for u, b in list((users._load().get("lab_names") or {}).items()):
        if b == name:
            _bind(u, n)
    apply_at_start(force=True)


def lab_set_role(name: str, role: str) -> None:
    if role not in users.ROLES:
        raise ValueError(f"Not a role: {role}")
    if would_leave_no_admin_lab(name, role):
        raise ValueError(f"'{name}' is the lab's only admin - make someone else admin first.")

    def fn(d):
        e = _find(d, name)
        if e is None:
            raise ValueError(f"'{name}' is not on the lab list.")
        e.update(role=role, role_at=_now(), changed=_now())
    if not _change(fn):
        raise ValueError("The lab list could not be written.")
    local = _local_match([name])
    if local:
        try:
            users.set_role(local, role, sync_lab=False)
        except ValueError:
            pass


def would_leave_no_admin_lab(name: str, role: str) -> bool:
    folder = linked_folder()
    if not folder or role in ("admin", "developer"):
        return False
    data = read_list(folder)
    me = _find(data, name)
    if me is None or me["role"] not in ("admin", "developer"):
        return False
    return not [e for e in data["people"] if e is not me and not e["hidden"]
                and e["role"] in ("admin", "developer")]


def lab_set_hidden(name: str, hidden: bool) -> None:
    """Hide a person on every linked computer (nothing deleted), or show again."""
    if hidden and would_leave_no_admin_lab(name, "user"):
        raise ValueError(f"'{name}' is the lab's only admin - make someone else admin first.")

    def fn(d):
        e = _find(d, name)
        if e is None:
            raise ValueError(f"'{name}' is not on the lab list.")
        e.update(hidden=bool(hidden), hidden_at=_now(), changed=_now())
    if not _change(fn):
        raise ValueError("The lab list could not be written.")
    local = _local_match([name])
    if local and hidden and local in users.list_users():
        users.remove_user(local)
    apply_at_start(force=True)


def lab_same_person(keep: str, other: str) -> None:
    """Two lab entries are one person (other spellings): `other`'s names become
    `keep`'s aliases. On each computer the profiles are then kept in step with
    the one lab profile; two local profiles of hers can be joined with Merge
    profiles."""
    def fn(d):
        e, o = _find(d, keep), _find(d, other)
        if e is None or o is None or e is o:
            raise ValueError("Pick two different people of the lab list.")
        e["aliases"] = list(dict.fromkeys(e["aliases"] + [o["name"]] + o["aliases"]))
        e["changed"] = _now()
    if not _change(fn):
        raise ValueError("The lab list could not be written.")
    apply_at_start(force=True)


def lab_add_alias(name: str, alias: str) -> None:
    a = users.clean_name(alias)

    def fn(d):
        e = _find(d, name)
        if e is None:
            raise ValueError(f"'{name}' is not on the lab list.")
        if a and a.lower() not in (x.lower() for x in [e["name"]] + e["aliases"]):
            e["aliases"].append(a)
            e["changed"] = _now()
    if not _change(fn):
        raise ValueError("The lab list could not be written.")
    apply_at_start(force=True)


def lab_clear_password(name: str) -> None:
    """Admin reset: the person has no password any more (here and in the lab)."""
    local = _local_match([name])
    if local:
        users.clear_password(local)          # also written to the lab list
        return
    rec = users.make_password_record("")

    def fn(d):
        e = _find(d, name)
        if e is not None:
            e.update(password=rec, changed=_now())
    _change(fn)


def anyone_can_add() -> bool:
    """May anyone add themselves on a linked computer? (lab setting, default yes)"""
    folder = linked_folder()
    if not folder or not os.path.isdir(folder):
        return True
    return bool(read_list(folder)["settings"].get("anyone_can_add", True))


def set_anyone_can_add(on: bool) -> None:
    def fn(d):
        d["settings"] = dict(anyone_can_add=bool(on), changed=_now())
    if not _change(fn):
        raise ValueError("The lab list could not be written.")


# ------------------------------------------------------ the lab's data folders
def data_folders() -> List[Tuple[str, str]]:
    """[(label, path)] - the lab's shared .nd2 data folders (from the linked lab
    list) and this computer's own (users.json "data_folders"). For the start
    screen: places to open movies from. Never raises."""
    out: List[Tuple[str, str]] = []
    seen = set()
    try:
        folder = linked_folder()
        if folder and os.path.isdir(folder):
            for e in read_list(folder)["data_folders"]:
                if not e.get("removed") and _path_key(e["path"]) not in seen:
                    seen.add(_path_key(e["path"]))
                    out.append((e.get("label") or Path(e["path"]).name, e["path"]))
        for e in users._load().get("data_folders") or []:
            if isinstance(e, dict) and e.get("path") and _path_key(e["path"]) not in seen:
                seen.add(_path_key(e["path"]))
                out.append((str(e.get("label") or Path(e["path"]).name), str(e["path"])))
    except Exception:                                           # noqa: BLE001
        pass
    return out


def add_data_folder(path: str, label: str = "", lab: bool = True) -> None:
    """Add (or relabel) a data folder: in the lab list when linked and `lab`,
    else for this computer only."""
    path, label = str(path), str(label or "")
    if lab and linked_folder():
        def fn(d):
            d["data_folders"].append(dict(path=path, label=label, removed=False,
                                          changed=_now()))
        if _change(fn):
            return
        raise ValueError("The lab list could not be written.")
    d = users._load()
    lst = [e for e in d.get("data_folders") or []
           if isinstance(e, dict) and _path_key(e.get("path", "")) != _path_key(path)]
    lst.append(dict(path=path, label=label))
    d["data_folders"] = lst
    users._save(d)


def remove_data_folder(path: str) -> None:
    """Take a data folder off the list (the folder itself is not touched)."""
    path = str(path)
    if linked_folder():
        def fn(d):
            for e in d["data_folders"]:
                if _path_key(e["path"]) == _path_key(path):
                    e.update(removed=True, changed=_now())
        _change(fn)
    d = users._load()
    d["data_folders"] = [e for e in d.get("data_folders") or []
                         if isinstance(e, dict) and _path_key(e.get("path", "")) != _path_key(path)]
    users._save(d)


# =========================================================== 4.0: the layout
MARKER = ".peterpiper-lab.json"
MARKER_KIND = "PeterPiper lab folder"
LAYOUT_VERSION = 1
README = "READ ME - PeterPiper lab folder.txt"
PEOPLE_DIR = "People"
SHARED_DIR = "Shared"
PERSON_PARTS = ("Results", "Exports", "Backups", "Movies")
NEW_PATHS = {"people": PEOPLE_DIR, "shared": SHARED_DIR,
             "profiles": f"{SHARED_DIR}/PeterPiper profiles",
             "detectors": f"{SHARED_DIR}/Detectors",
             "templates": f"{SHARED_DIR}/Prism templates",
             "settings": f"{SHARED_DIR}/Settings"}
# where things are in a lab folder WITHOUT a marker (a 1.1 lab folder)
OLD_PATHS = dict(NEW_PATHS, profiles=PROFILES_DIR)
WALK_UP = 30                       # find_lab_root: at most this many folders up
TEST_HOOKS: Dict[str, object] = {}     # "processes": [names]; "free": bytes (tests)

README_TEXT = """PeterPiper lab folder
=====================

This is the lab's shared PeterPiper folder. Your sync app (Box Drive, OneDrive,
Google Drive, Dropbox ...) or the network drive carries it to every lab computer.

  People/<name>/      each person's own things:
      Results/        saves and autosaves (copied here automatically)
      Exports/        Excel, Prism, CSV and pictures
      Backups/        a backup of your PeterPiper profile, settings and run list
      Movies/         analysed .nd2 movies (only if you switched that on)
  Shared/             the lab's shared profiles, detectors, Prism templates, settings

To connect a computer: in PeterPiper's start window, "Lab folder & backup" ->
"Connect..." and pick THIS folder (or any folder inside it). PeterPiper makes
People/<your name> for you.

Please do not rename or move the hidden file .peterpiper-lab.json - it tells
PeterPiper that this is the lab folder. PeterPiper never deletes anything here.
"""


def _now_s() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_marker(folder) -> Optional[dict]:
    """The marker in `folder` ({kind, layout, lab_name, created_by, created, paths,
    ...}) or None."""
    try:
        d = json.loads((Path(folder) / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("kind") != MARKER_KIND:
        return None
    return d


def _write_json(p: Path, data: dict) -> None:
    tmp = p.with_name(f".{p.name}.{secrets.token_hex(3)}.pp-tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def lab_path(key: str, folder=None) -> Path:
    """Where `key` ("people", "shared", "profiles", "detectors", "templates",
    "settings") is in the lab folder (the linked one by default): from the marker,
    else where 1.1 kept it."""
    f = Path(folder or linked_folder() or ".")
    m = read_marker(f)
    paths = dict(OLD_PATHS)
    if m is not None and isinstance(m.get("paths"), dict):
        paths.update({k: str(v) for k, v in m["paths"].items() if isinstance(v, str)})
    rel = paths.get(key, key)
    return f.joinpath(*[p for p in rel.replace("\\", "/").split("/") if p])


def lab_name(folder=None) -> str:
    folder = folder or linked_folder()
    if not folder:
        return ""
    m = read_marker(folder) or {}
    return str(m.get("lab_name") or Path(str(folder)).name)


def _existing(f: Path) -> dict:
    """What is already in a folder that becomes (or already was) a lab folder: its
    1.1 profiles folder, and top-level folders that look like a person's own
    (named like someone on the lab list or a user here) - recorded, never moved."""
    out: Dict[str, object] = {}
    if (f / PROFILES_DIR).is_dir():
        out["profiles"] = PROFILES_DIR
    names = {}
    try:
        for e in read_list(f)["people"]:
            for n in [e["name"]] + e["aliases"]:
                names[n.lower()] = e["name"]
    except Exception:                                           # noqa: BLE001
        pass
    try:
        for u in users.all_users():
            names.setdefault(u.lower(), u)
            for a in users.aliases_of(u):
                names.setdefault(a.lower(), u)
    except Exception:                                           # noqa: BLE001
        pass
    own = {}
    try:
        for e in sorted(f.iterdir()):
            if not e.is_dir() or e.name.startswith(".") or e.name in (PEOPLE_DIR, SHARED_DIR,
                                                                       PROFILES_DIR):
                continue
            low = e.name.lower()
            for n, person in names.items():
                first = n.split()[0] if n.split() else n
                if low == n or low.startswith(n + " ") or low == first \
                        or low.startswith(first + " "):
                    own[person] = e.name
                    break
    except OSError:
        pass
    if own:
        out["people"] = own
    return out


def setup_lab_folder(folder, name: str = "", created_by: str = "") -> dict:
    """'Set up a lab folder': the recommended layout in `folder` (made if needed) -
    the marker, People/, Shared/ and the READ ME. A folder that already is a 1.1
    lab folder (or has the lab's 'PeterPiper profiles') is ADOPTED: the marker
    records what is there and where (its profiles stay where they are) - nothing is
    moved, renamed or deleted; folders already there are left alone. A folder that
    already has a marker is left as it is. Returns {"root", "adopted", "already",
    "made": [relative folders made]}. ValueError when the folder cannot be written."""
    f = Path(folder)
    try:
        f.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"The folder could not be made: {exc}") from exc
    if not writable(f):
        raise ValueError("This folder cannot be written - choose another one.")
    old = read_marker(f)
    if old is not None:
        return {"root": str(f), "adopted": bool(old.get("adopted")), "already": True,
                "made": []}
    adopted = (f / LAB_FILE).is_file() or (f / PROFILES_DIR).is_dir()
    paths = dict(NEW_PATHS)
    if (f / PROFILES_DIR).is_dir():
        paths["profiles"] = PROFILES_DIR
    marker = {"kind": MARKER_KIND, "layout": LAYOUT_VERSION,
              "lab_name": users.clean_name(name) or f.name,
              "created_by": users.clean_name(created_by), "created": _now_s(),
              "adopted": adopted, "paths": paths, "existing": _existing(f)}
    made = []
    for key in ("people", "shared", "profiles", "detectors", "templates", "settings"):
        p = f.joinpath(*paths[key].split("/"))
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
            made.append(paths[key])
    rd = f / README
    if not rd.exists():
        rd.write_text(README_TEXT.replace("\n", os.linesep if os.name == "nt" else "\n"),
                      encoding="utf-8")
    _write_json(f / MARKER, marker)
    return {"root": str(f), "adopted": adopted, "already": False, "made": made}


def find_lab_root(path) -> Optional[Tuple[str, bool]]:
    """(lab root, has the 4.0 marker) for any folder (or file) in or below a lab
    folder: walks up to the nearest marker; a 1.1 lab folder (lab list, no
    marker) counts when no marker is found above it. None: not in a lab folder."""
    try:
        p = Path(os.path.abspath(str(path)))
    except (OSError, ValueError):
        return None
    if p.is_file():
        p = p.parent
    old = None
    for q in [p, *list(p.parents)[:WALK_UP]]:
        try:
            if (q / MARKER).is_file() and read_marker(q) is not None:
                return str(q), True
            if old is None and (q / LAB_FILE).is_file():
                old = str(q)
        except OSError:
            continue
    return (old, False) if old else None


def person_dir(user: Optional[str] = None, folder=None, create: bool = False) -> Optional[Path]:
    """<lab>/People/<person> (the lab-list spelling of `user`, default the current
    user); with create, it and its Results / Exports / Backups / Movies are made.
    None when no lab folder is linked or no user."""
    folder = folder or linked_folder()
    user = user or users.current()
    if not folder or not user:
        return None
    name = _bound_name(user) or user
    p = lab_path("people", folder) / users.folder_name(name)
    if create:
        for part in PERSON_PARTS:
            (p / part).mkdir(parents=True, exist_ok=True)
    return p


def connect(path, user: Optional[str] = None, make_person: bool = True,
            adopt: bool = True) -> dict:
    """'Connect...': `path` is any folder in or below the lab folder. Walks up to
    the lab root, adopts a 1.1 lab folder (marker written, nothing moved - only
    when `adopt` and it can be written), links this computer to it (the root is
    stored for this computer only), adds `user` to the lab list and - with
    make_person - makes People/<user>. Returns {"root", "notes", "person",
    "adopted", "readonly"}. ValueError when `path` is not in a lab folder."""
    found = find_lab_root(path)
    if found is None:
        raise ValueError("There is no PeterPiper lab folder here or in a folder above it. "
                         "Pick the lab's PeterPiper folder (ask whoever set it up), or set "
                         "one up.")
    root, has_marker = found
    ro = not writable(root)
    adopted = False
    if not has_marker and adopt and not ro:
        setup_lab_folder(root, created_by=user or "")
        adopted = True
    user = user or users.current()
    notes = link(root, include=[user] if user else None)
    person = None
    if make_person and user and not ro:
        try:
            person = str(person_dir(user, root, create=True))
        except OSError as exc:
            notes.append(f"your folder could not be made: {exc}")
    return {"root": root, "notes": notes, "person": person, "adopted": adopted,
            "readonly": ro}


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p))).rstrip("\\/")


def _inside(a, b) -> bool:
    a, b = _norm(a), _norm(b)
    return a == b or a.startswith(b + os.sep)


def own_folder_setup(user: Optional[str] = None) -> Optional[dict]:
    """The user's results go to a folder of their own (cloud.results_root) while a
    lab folder is linked - e.g. 'Peter' made inside the lab folder, or 'Peter
    ONLINE' elsewhere in the cloud: {"current", "suggested" (People/<user>/Results),
    "inside" (the own folder is inside the lab folder)}. None when the results
    already go to People/<user> (or nothing is set, or no lab is linked)."""
    user = user or users.current()
    folder = linked_folder()
    if not user or not folder:
        return None
    try:
        from . import cloud
        cur = cloud.results_root()
    except Exception:                                           # noqa: BLE001
        return None
    pd = person_dir(user, folder)
    if not cur or pd is None or _inside(cur, pd):
        return None
    return {"current": cur, "suggested": str(pd / "Results"),
            "inside": _inside(cur, folder)}


def use_lab_results(user: Optional[str] = None) -> str:
    """Results from now on go to People/<user>/Results (made). Nothing already
    saved is moved. Returns the folder."""
    pd = person_dir(user, create=True)
    if pd is None:
        raise ValueError("No lab folder is connected.")
    from . import cloud
    target = str(pd / "Results")
    cloud.set_results_root(target)
    return target


# ------------------------------------------------------- finding lab folders
def _cloud_roots() -> List[Tuple[str, str]]:
    try:
        from .platforms import cloud_roots                      # the "launch" part
        return [(str(s), str(p)) for s, p in cloud_roots()]
    except ImportError:
        from .cloud import cloud_roots_fallback
        return cloud_roots_fallback()


def scan_for_labs(roots: Optional[List[Tuple[str, str]]] = None, depth: int = 3,
                  budget_s: float = 10.0, cancelled=None, found=None) -> List[dict]:
    """Lab folders in the top `depth` levels of each sync app's folder: [{"root",
    "name", "service", "marker" (bool)}]. Reads folder listings only (no file is
    opened except a marker found); at most budget_s seconds per sync folder; a lab
    folder is not searched further. found(entry) is called for each as it is found.
    For a background thread (a folder listing in Box Drive can take a moment)."""
    roots = _cloud_roots() if roots is None else roots
    out: List[dict] = []
    seen = set()
    for service, top in roots:
        t0 = time.monotonic()
        level = [Path(top)]
        for d in range(depth + 1):
            nxt = []
            for p in level:
                if cancelled is not None and cancelled():
                    return out
                if time.monotonic() - t0 > budget_s:
                    nxt = []
                    break
                try:
                    names = os.listdir(p)
                except OSError:
                    continue
                if MARKER in names or LAB_FILE in names:
                    k = _norm(p)
                    if k not in seen:
                        seen.add(k)
                        m = read_marker(p) if MARKER in names else None
                        e = {"root": str(p), "name": str((m or {}).get("lab_name") or p.name),
                             "service": service, "marker": m is not None}
                        out.append(e)
                        if found is not None:
                            found(e)
                    continue
                if d == depth or len(names) > 400:
                    continue
                for n in sorted(names):
                    if n.startswith((".", "$", "~")) or n.upper().startswith("OUTPUT_") \
                            or n.lower().endswith((".nd2", ".tif", ".tiff", ".xlsx", ".zip")):
                        continue
                    q = p / n
                    try:
                        if q.is_dir():
                            nxt.append(q)
                    except OSError:
                        pass
            level = nxt
    return out


# ------------------------------------------------------------------ health
SYNC_APPS = {"Box": ("box.exe", "box", "box drive"),
             "OneDrive": ("onedrive.exe", "onedrive"),
             "Google Drive": ("googledrivefs.exe", "google drive"),
             "Dropbox": ("dropbox.exe", "dropbox"),
             "iCloud Drive": ("icloudrive.exe", "iclouddrive.exe", "bird"),
             "Nextcloud": ("nextcloud.exe", "nextcloud"),
             "ownCloud": ("owncloud.exe", "owncloud"),
             "pCloud": ("pcloud.exe", "pcloud"),
             "MEGA": ("megasync.exe", "megasync"),
             "Egnyte": ("egnytedrive.exe", "egnyte drive", "egnytedrive")}
_proc_cache: Dict[str, object] = {"t": 0.0, "names": None}


def _process_names() -> Optional[List[str]]:
    """The names of the running programs (lower case), or None when that cannot be
    told. A read-only look (tasklist / ps), at most every 30 s."""
    if "processes" in TEST_HOOKS:
        return [str(n).lower() for n in TEST_HOOKS["processes"]]      # type: ignore[union-attr]
    if time.monotonic() - float(_proc_cache["t"]) < 30 and _proc_cache["names"] is not None:
        return list(_proc_cache["names"])                              # type: ignore[arg-type]
    import subprocess
    names: Optional[List[str]] = None
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,   # noqa: S603,S607
                               text=True, timeout=5,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            names = [ln.split('","')[0].strip('"').lower() for ln in r.stdout.splitlines()
                     if ln.strip()]
        else:
            r = subprocess.run(["ps", "-axco", "command"], capture_output=True, text=True,  # noqa: S603,S607
                               timeout=5)
            names = [ln.strip().lower() for ln in r.stdout.splitlines()[1:] if ln.strip()]
    except Exception:                                           # noqa: BLE001
        names = None
    _proc_cache.update(t=time.monotonic(), names=names)
    return names


def sync_app_running(service: str) -> Optional[bool]:
    """Is the sync app of `service` ("Box", "OneDrive" ...) running? None: not known
    (a network drive, an unknown app, or the program list cannot be read)."""
    want = SYNC_APPS.get(service)
    if not want:
        return None
    names = _process_names()
    if names is None:
        return None
    return any(n in want for n in names)


class Health:
    """level: "green" | "amber" | "red" | "grey" (not connected); text: one line;
    fix: what to do, in plain words ('' when nothing); details: more lines."""

    def __init__(self, level: str, text: str, fix: str = "", details=()) -> None:
        self.level, self.text, self.fix, self.details = level, text, fix, list(details)

    def __repr__(self) -> str:
        return f"Health({self.level!r}, {self.text!r})"


FREE_RED = 5e9            # bytes: below this the disk is called nearly full
FREE_AMBER = 20e9


def _gb(n: float) -> str:
    return f"{n / 1e9:.0f} GB" if n >= 10e9 else f"{n / 1e9:.1f} GB"


def health(folder=None, cache_folder=None) -> Health:
    """Is the lab folder usable now? Reachable, can be written, its sync app running,
    enough free disk space here (the movie cache's drive), when another computer
    last changed something. Never raises; may take a moment (for a thread)."""
    folder = folder or linked_folder()
    if not folder:
        return Health("grey", "Not connected to a lab folder.",
                      "Press Connect... and pick the lab's PeterPiper folder.")
    service = ""
    try:
        from . import cloud
        service = cloud.service_of(folder)
    except Exception:                                           # noqa: BLE001
        pass
    app = {"Box": "Box Drive"}.get(service, service) or "the sync app"
    if not os.path.isdir(folder):
        fix = (f"Start {app} and sign in, then press Check again."
               if service and service != "Network" else
               "Connect to the lab's network drive (or plug in the disk), then press "
               "Check again.")
        return Health("red", "The lab folder cannot be reached.", fix, [str(folder)])
    level, notes, fixes = "green", [], []
    if not writable(folder):
        level = "amber"
        notes.append("read-only here")
        fixes.append("Ask whoever set up the lab folder to give you edit rights.")
    running = sync_app_running(service) if service and service != "Network" else None
    if running is False:
        level = "amber"
        notes.append(f"{app} does not seem to be running")
        fixes.append(f"Start {app}: until then nothing you save there is uploaded.")
    elif running:
        notes.append(f"{app} running")
    try:
        import shutil
        free = int(TEST_HOOKS["free"]) if "free" in TEST_HOOKS else \
            shutil.disk_usage(str(cache_folder or users.base_dir())).free
        if free < FREE_RED:
            level = "red"
            notes.append(f"this computer's disk is almost full ({_gb(free)} free)")
            fixes.append("Free some space (empty the movie cache, delete old copies), or "
                         "choose a movie cache on another disk.")
        elif free < FREE_AMBER:
            level = "amber" if level == "green" else level
            notes.append(f"only {_gb(free)} free on this computer")
            fixes.append("Big movies need room in the movie cache - free some space soon.")
        else:
            notes.append(f"{_gb(free)} free")
    except OSError:
        pass
    seen = last_change_elsewhere(folder)
    details = [str(folder)]
    if seen:
        details.append(f"Last change from another computer: {seen}")
    head = {"green": "Lab folder OK", "amber": "Lab folder: needs a look",
            "red": "Lab folder: a problem"}[level]
    return Health(level, head + (" - " + ", ".join(notes) if notes else ""),
                  " ".join(fixes), details)


def last_change_elsewhere(folder=None) -> str:
    """When another computer last wrote its 'seen' note in the lab folder (a hint
    that syncing works): 'today 14:02', '3 days ago' or ''."""
    folder = folder or linked_folder()
    if not folder:
        return ""
    me = _computer()
    best = 0.0
    try:
        for p in lab_path("people", folder).glob("*/.peterpiper-seen-*.json"):
            if p.name != f".peterpiper-seen-{me}.json":
                try:
                    best = max(best, p.stat().st_mtime)
                except OSError:
                    pass
    except OSError:
        return ""
    if not best:
        return ""
    t = datetime.fromtimestamp(best)
    days = (datetime.now() - t).days
    return t.strftime("today %H:%M") if t.date() == datetime.now().date() else (
        f"{days} day{'s' if days != 1 else ''} ago")


def _computer() -> str:
    import platform
    import re
    n = platform.node() or "computer"
    return re.sub(r"[^A-Za-z0-9_-]+", "_", n)[:40]


def note_seen(user: Optional[str] = None) -> bool:
    """Write this computer's small 'seen' note in People/<user> (at most once an
    hour), so other computers can tell that syncing works."""
    pd = person_dir(user)
    if pd is None or not pd.is_dir():
        return False
    p = pd / f".peterpiper-seen-{_computer()}.json"
    try:
        if p.exists() and time.time() - p.stat().st_mtime < 3600:
            return True
        _write_json(p, {"computer": _computer(), "seen": _now_s()})
        return True
    except OSError:
        return False
