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
    try:
        return (Path(folder) / LAB_FILE).is_file()
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
    target = Path(folder) / PROFILES_DIR / (users.EXPORT_ROOT + users.folder_name(lab_name))
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
    (f / PROFILES_DIR).mkdir(exist_ok=True)
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
        raise ValueError("There is no PeterPiper lab list in this folder (choose the folder "
                         f"that holds '{LAB_FILE}', or Create a lab folder here).")
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
