"""
Saving and loading the ROI set (.npz), shared by the main window and batch mode.

.npz is numpy's zip of arrays: here every ROI's outline (as a pixel mask), the
background region and - since v1.9 - the whole session state (Find rows, each ROI
type's ROIs, include / exclude choices, sliders, settings). Since v2.2 it also
holds the tracking (every ROI at every timepoint and the measurements), so
File > Load ROIs in a fresh window puts it all back ready to check and export -
no need to track again.

v2.3 adds:
  - the tracking rules, tracking parameters and IF-gate results inside the
    tracking record, and (in the state) where / when / with what version the
    file was made and which .nd2 it belongs to (fingerprint, see history.py);
  - save_session_file: the app's own "session" file, kept up to date as you
    work by replacing it in one step (the only file the app ever replaces);
  - read_summary: a quick look at a file (no masks decoded) for the
    "this .nd2 was analysed before" list;
  - track_problem: a plain-language reason when saved tracking cannot be used.
v2.5 adds (older files load as before, without them):
  - the raw sums behind every mean (Measurements.sum / background_sum /
    background_npx), what the background left out at each timepoint
    (track["background"], track["bg_excluded"]) and the tracker boundary lines
    (state["boundaries"]);
  - content_key: a hash of everything that matters in the file (ROIs, tracking,
    settings - not when / by which window it was saved), stored in the state, so
    an identical session is not saved twice and the earlier-runs list shows it once.
Every older file still loads: v1.x (ROIs only), v1.9-v2.1 (no tracking), v2.2.
"""
from __future__ import annotations

import copy
import dataclasses
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import hashlib
import json
import os
import zipfile

import numpy as np

from .safety import exists, long_path, new_output_file, replace_own_file
from .segment import Roi

COMPS = ("nucleus", "cell", "cytoplasm", "mito")      # same order as manual.COMPS
COMP_WORDS = {"nucleus": "nucleus", "cell": "whole cell", "cytoplasm": "cytoplasm",
              "mito": "mitochondria"}
_V1_ROWS = {"Nuclei": "nucleus", "Whole cell": "cell", "Cytoplasm": "cytoplasm",
            "Mitochondria": "mito"}


def roi_path(out_dir: str, image_path: str) -> Path:
    return Path(out_dir) / f"{Path(image_path).stem[:40]}_ROIs.npz"


def _json_default(o):
    """numpy numbers / arrays and paths inside the state -> plain JSON."""
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Path):
        return str(o)
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    raise TypeError(f"{type(o).__name__} cannot be saved in an ROI file")


def _dumps(obj) -> str:
    return json.dumps(obj, default=_json_default)


def pack_rois(prefix: str, rois: Sequence[Roi]) -> dict:
    blob = {f"{prefix}n": np.asarray([len(rois)])}
    for i, r in enumerate(rois):
        blob[f"{prefix}bbox_{i}"] = np.asarray(r.bbox)
        blob[f"{prefix}shape_{i}"] = np.asarray(r.mask.shape)
        blob[f"{prefix}mask_{i}"] = np.packbits(r.mask)
        if getattr(r, "outline", None) is not None:
            blob[f"{prefix}outline_{i}"] = np.packbits(r.outline)
    return blob


def unpack_rois(z, prefix: str, kind: str) -> List[Roi]:
    out = []
    for i in range(int(z[f"{prefix}n"][0])):
        shape = tuple(int(x) for x in z[f"{prefix}shape_{i}"])
        size = shape[0] * shape[1]
        m = np.unpackbits(z[f"{prefix}mask_{i}"])[:size].reshape(shape).astype(bool)
        r = Roi(tuple(int(x) for x in z[f"{prefix}bbox_{i}"]), m, kind)
        if f"{prefix}outline_{i}" in z:
            r.outline = np.unpackbits(z[f"{prefix}outline_{i}"])[:size].reshape(shape).astype(bool)
        out.append(r)
    return out


MEAS_FIELDS = ("mean", "background", "area_px", "n_saturated", "quality", "background_sd",
               "sum", "background_sum", "background_npx")       # the last three: v2.5
TRACK_EXTRAS = ("rules", "params", "gate", "background")   # v2.3 (+ v2.5): kept in track_json


def pack_track(track: dict) -> dict:
    """
    v2.2: the tracking result - every ROI at every timepoint (as drawn by the
    tracker) and the measurements - so a reloaded session needs no re-tracking.
    Per compartment: bbox (T, N, 4), shape (T, N, 2), outline flag, and all
    masks bit-packed one after the other (offsets (T, N, 2)).
    v2.3: also the tracking rules, the tracking parameters and the IF-gate
    signal-to-noise per cell (track["rules"], ["params"], ["gate"]), as JSON.
    """
    blob = {}
    comps = sorted(track.get("rois", {}).keys())
    meta = dict(comps=comps, redrawn={c: float(v) for c, v in track.get("redrawn", {}).items()})
    if track.get("rules") is not None:
        meta["rules"] = list(track["rules"])
    for key in ("params", "gate", "background"):
        if track.get(key):
            meta[key] = track[key]
    bgx = track.get("bg_excluded") or {}
    if bgx:                                    # v2.5: bright / moving pixels left out
        ts = sorted(int(t) for t in bgx)
        shape = np.asarray(bgx[ts[0]]).shape
        blob["trk_bgx_t"] = np.asarray(ts, np.int32)
        blob["trk_bgx_shape"] = np.asarray(shape, np.int32)
        blob["trk_bgx_bits"] = np.stack([np.packbits(np.asarray(bgx[t], bool).ravel())
                                         for t in ts])
    for c in comps:
        grid = track["rois"][c]
        T, N = len(grid), len(grid[0]) if grid else 0
        bb = np.zeros((T, N, 4), np.int32)
        sh = np.zeros((T, N, 2), np.int32)
        off = np.zeros((T, N, 2), np.int64)
        has_out = np.zeros((T, N), np.uint8)
        chunks, pos = [], 0
        for t in range(T):
            for k in range(N):
                r = grid[t][k]
                bb[t, k] = r.bbox
                sh[t, k] = r.mask.shape
                pk = np.packbits(r.mask.ravel())
                off[t, k, 0] = pos
                chunks.append(pk)
                pos += pk.size
                o = getattr(r, "outline", None)
                if o is not None and o.shape == r.mask.shape:
                    has_out[t, k] = 1
                    po = np.packbits(o.ravel())
                    off[t, k, 1] = pos
                    chunks.append(po)
                    pos += po.size
        blob[f"trk_{c}_bbox"], blob[f"trk_{c}_shape"] = bb, sh
        blob[f"trk_{c}_off"], blob[f"trk_{c}_hasout"] = off, has_out
        blob[f"trk_{c}_bits"] = np.concatenate(chunks) if chunks else np.zeros(0, np.uint8)
        M = track["meas"][c]
        for f in MEAS_FIELDS:
            v = getattr(M, f, None)
            if v is not None:
                blob[f"trk_{c}_m_{f}"] = np.asarray(v)
        meta[f"chan_{c}"] = list(M.channels)
        meta[f"mode_{c}"] = M.roi_mode
    blob["track_json"] = np.asarray(_dumps(meta))
    return blob


def _channel_index(v, saved: Sequence[str], names: Optional[Sequence[str]]) -> Optional[int]:
    """A saved channel (index into `saved`, or a name) as an index into
    `names` (the channels of the movie now open); matched by NAME when it can
    be (same rule as File > Load ROIs). names None: the index as saved."""
    try:
        if isinstance(v, str):
            if names is not None and v in names:
                return list(names).index(v)
            if v in saved:
                v = list(saved).index(v)
            else:
                return None
        i = int(v)
    except (TypeError, ValueError):
        return None
    if names is None:
        return i
    if 0 <= i < len(saved) and saved[i] in names:
        return list(names).index(saved[i])
    return min(max(0, i), len(names) - 1) if len(names) else None


def _cell_channels(state: Optional[dict], comp: str, n: int,
                   names: Optional[Sequence[str]]) -> List[Optional[int]]:
    """Per cell, the channel its `comp` ROI was drawn / followed on, from the
    saved state (state["cells"] = [{comp: channel}]); None where unknown."""
    out: List[Optional[int]] = [None] * n
    if not isinstance(state, dict) or not state.get("v2"):
        return out
    cells = state.get("cells") or []
    if isinstance(cells, str):
        try:
            cells = json.loads(cells)
        except ValueError:
            return out
    saved = list(state.get("channels") or [])
    for k, chmap in enumerate(cells[:n] if isinstance(cells, list) else []):
        if isinstance(chmap, dict) and comp in chmap:
            out[k] = _channel_index(chmap[comp], saved, names)
    return out


def unpack_track(z, state: Optional[dict] = None,
                 channels: Optional[Sequence[str]] = None) -> Optional[dict]:
    """The tracking result saved by pack_track, or None if the file has none.

    Returns dict(meas={c: Measurements}, rois={c: [T][N] Roi}, redrawn={c: f},
    rules=[rule dicts] or None (files before v2.3), params={...}, gate={c: {k: snr}},
    skipped=[compartments whose tracking could not be read]).
    Each per-frame ROI gets `.channel` from the saved state when it says which
    channel that cell was drawn on (`state` defaults to the file's own; with
    `channels`, the movie's channel names, the index is matched by name).
    T and N are returned as saved, even if they differ from the movie or the
    cells now loaded - see track_problem().
    """
    if "track_json" not in z:
        return None
    from .measure import Measurements
    meta = json.loads(str(z["track_json"]))
    if state is None and "state_json" in z:
        try:
            state = json.loads(str(z["state_json"]))
        except ValueError:
            state = None
    rois, meas, skipped = {}, {}, []
    for c in meta.get("comps", []):
        try:
            bb, sh = z[f"trk_{c}_bbox"], z[f"trk_{c}_shape"]
            off, has_out, bits = z[f"trk_{c}_off"], z[f"trk_{c}_hasout"], z[f"trk_{c}_bits"]
            T, N = bb.shape[:2]
            chans = _cell_channels(state, c, N, channels)
            grid = []
            for t in range(T):
                row = []
                for k in range(N):
                    h, w = (int(v) for v in sh[t, k])
                    n = h * w
                    nb = (n + 7) // 8
                    a = int(off[t, k, 0])
                    m = np.unpackbits(bits[a:a + nb])[:n].reshape(h, w).astype(bool)
                    r = Roi(tuple(int(v) for v in bb[t, k]), m, c, bool(m.any()), "manual")
                    if has_out[t, k]:
                        b = int(off[t, k, 1])
                        r.outline = np.unpackbits(bits[b:b + nb])[:n].reshape(h, w).astype(bool)
                    if chans[k] is not None:
                        r.channel = chans[k]
                    row.append(r)
                grid.append(row)
            kw = {f: z[f"trk_{c}_m_{f}"] for f in MEAS_FIELDS if f"trk_{c}_m_{f}" in z}
            M = Measurements(channels=list(meta.get(f"chan_{c}", [])),
                             roi_mode=meta.get(f"mode_{c}", c), **kw)
        except (KeyError, ValueError, TypeError, IndexError):
            skipped.append(c)                  # damaged part: the rest still loads
            continue
        rois[c], meas[c] = grid, M
    gate = {}
    for c, per in (meta.get("gate") or {}).items():
        try:
            gate[c] = {int(k): float(v) for k, v in per.items()}
        except (AttributeError, TypeError, ValueError):
            pass
    bgx = {}
    if "trk_bgx_t" in z:                       # v2.5
        try:
            h, w = (int(v) for v in z["trk_bgx_shape"])
            bits = z["trk_bgx_bits"]
            for i, t in enumerate(z["trk_bgx_t"]):
                bgx[int(t)] = np.unpackbits(bits[i])[:h * w].reshape(h, w).astype(bool)
        except (KeyError, ValueError, TypeError, IndexError):
            bgx = {}
    out = dict(meas=meas, rois=rois, redrawn=meta.get("redrawn", {}),
               rules=meta.get("rules"), params=meta.get("params") or {}, gate=gate,
               skipped=skipped)
    if meta.get("background"):
        out["background"] = meta["background"]
    if bgx:
        out["bg_excluded"] = bgx
    return out


def load_roi_track(path, channels: Optional[Sequence[str]] = None) -> Optional[dict]:
    """The saved tracking result of an ROI file (v2.2+), or None."""
    with np.load(long_path(path), allow_pickle=False) as z:
        return unpack_track(z, channels=channels)


def load_roi_state(path) -> Tuple[Optional[dict], dict]:
    """(session state or None for files before v1.9, {compartment: [Roi]})."""
    with np.load(long_path(path), allow_pickle=False) as z:
        if "state_json" not in z:
            return None, {}
        state = json.loads(str(z["state_json"]))
        comps = {c: unpack_rois(z, f"comp_{c}_", c) for c in state.get("comps", [])}
    return state, comps


def _blob(nuclei: Sequence[Roi], background: Optional[Roi], shape: Tuple[int, int],
          seg_timepoint: int, state: Optional[dict], comps: Optional[dict],
          track: Optional[dict]) -> dict:
    blob = pack_track(track) if track else {}
    if state is not None:
        state = dict(state, comps=sorted((comps or {}).keys()))
        for c, rois in (comps or {}).items():
            blob.update(pack_rois(f"comp_{c}_", rois))
    for i, r in enumerate(nuclei):
        blob[f"bbox_{i}"] = np.asarray(r.bbox)
        blob[f"mask_{i}"] = np.packbits(r.mask)
        blob[f"shape_{i}"] = np.asarray(r.mask.shape)
        blob[f"flags_{i}"] = np.asarray([int(r.include), 1 if r.source == "manual" else 0])
    if background is not None:
        blob["bg_bbox"] = np.asarray(background.bbox)
        blob["bg_shape"] = np.asarray(background.mask.shape)
        blob["bg_mask"] = np.packbits(background.mask)
    blob["n"] = np.asarray([len(nuclei)])
    blob["image_shape"] = np.asarray(list(shape))
    blob["seg_timepoint"] = np.asarray([seg_timepoint])
    if state is not None:                      # v2.5: what the file holds, as one hash
        state["content_key"] = content_key(blob, state)
        blob["state_json"] = np.asarray(_dumps(state))
    return blob


# ------------------------------------------------- v2.5: identical sessions
# State keys that say WHEN / BY WHAT a file was saved, not what it holds: two
# files that differ only in these hold the same analysis.
VOLATILE_STATE = ("saved", "session_id", "kind", "based_on", "version", "app", "content_key",
                  "nd2_path")


def _norm_state(state: Optional[dict]) -> str:
    st = {k: v for k, v in (state or {}).items() if k not in VOLATILE_STATE}
    fp = st.get("fingerprint")
    if isinstance(fp, dict):                   # the .nd2's content, not where it lies
        st["fingerprint"] = {k: fp.get(k) for k in ("quick", "size")}
    return json.dumps(st, sort_keys=True, default=_json_default)


def content_key(blob: dict, state: Optional[dict] = None) -> str:
    """
    SHA-1 of everything that matters in an ROI / session file: every array
    (name, type, shape, bytes - the ROIs, the tracking, the measurements) and
    the state without VOLATILE_STATE (when it was saved, the session name, the
    PeterPiper version). Two saves of an unchanged analysis give the same key.
    """
    h = hashlib.sha1()
    for key in sorted(blob):
        if key == "state_json":
            continue
        a = np.ascontiguousarray(np.asanyarray(blob[key]))
        h.update(key.encode("utf-8"))
        h.update(str(a.dtype.str).encode("ascii"))
        h.update(str(a.shape).encode("ascii"))
        if a.dtype.kind in "OU":
            h.update(str(a.tolist()).encode("utf-8"))
        else:
            h.update(a.tobytes())
    h.update(_norm_state(state).encode("utf-8"))
    return h.hexdigest()


def _zip_content_key(zf: zipfile.ZipFile, state: Optional[dict]) -> str:
    """A content key for a file saved before v2.5 (no content_key inside): the
    zip's own CRC-32 and size of every array except the state, plus the
    normalised state - nothing is decoded. Only comparable with other such keys."""
    h = hashlib.sha1(b"zip-crc")
    for info in sorted(zf.infolist(), key=lambda i: i.filename):
        if info.filename == "state_json.npy":
            continue
        h.update(f"{info.filename}:{info.CRC}:{info.file_size};".encode("utf-8"))
    h.update(_norm_state(state).encode("utf-8"))
    return h.hexdigest()


def save_roi_file(path: Path, nuclei: Sequence[Roi], background: Optional[Roi],
                  shape: Tuple[int, int], seg_timepoint: int,
                  state: Optional[dict] = None, comps: Optional[dict] = None,
                  track: Optional[dict] = None) -> Path:
    """Write the ROI set (and, v2.2, the tracking result if given); never
    overwrites (adds _2, _3...). Returns the path used."""
    blob = _blob(nuclei, background, shape, seg_timepoint, state, comps, track)
    with new_output_file(Path(path)) as (used, stream):
        np.savez_compressed(stream, **blob)
    return used


def save_session_file(path: Path, nuclei: Sequence[Roi], background: Optional[Roi],
                      shape: Tuple[int, int], seg_timepoint: int,
                      state: Optional[dict] = None, comps: Optional[dict] = None,
                      track: Optional[dict] = None) -> Path:
    """v2.3: the app's own session file (see history.session_path): same
    content as save_roi_file, but this one file is kept up to date - each save
    replaces it in one step (temporary file + os.replace), so it is never half
    written. state["kind"] is set to "session". Refuses to replace a file that
    is not a PeterPiper session file. Returns the path."""
    return write_session_blob(path, session_blob(nuclei, background, shape, seg_timepoint,
                                                 state, comps, track))


def session_blob(nuclei: Sequence[Roi], background: Optional[Roi], shape: Tuple[int, int],
                 seg_timepoint: int, state: Optional[dict] = None,
                 comps: Optional[dict] = None, track: Optional[dict] = None) -> dict:
    """The arrays of a session file (first half of save_session_file). Quick:
    the window packs in its own thread and writes in a background thread
    (write_session_blob), so autosaving never freezes it."""
    state = dict(state or {}, kind="session")
    return _blob(nuclei, background, shape, seg_timepoint, state, comps, track)


def write_session_blob(path: Path, blob: dict) -> Path:
    """Second half of save_session_file: write packed arrays to the session
    file, replacing it in one step. Refuses to replace a file that is not a
    PeterPiper session file."""
    path = Path(path)
    if exists(path) and not _is_session_file(path):
        raise FileExistsError(f"{path.name} is not a PeterPiper session file, so it was not "
                              f"replaced.")
    with replace_own_file(path) as stream:
        _savez_fast(stream, blob)
    return path


def _savez_fast(stream, blob: dict) -> None:
    """Like np.savez_compressed (np.load reads it the same way) but with the
    fastest zip compression: the session file is re-saved as you work, and this
    is ~4x quicker for a ~20% bigger file."""
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for key, val in blob.items():
            with zf.open(key + ".npy", "w", force_zip64=True) as f:
                np.lib.format.write_array(f, np.asanyarray(val), allow_pickle=False)


def _is_session_file(path: Path) -> bool:
    try:
        with zipfile.ZipFile(long_path(path)) as zf:
            st = _state_from_zip(zf)
        return isinstance(st, dict) and st.get("kind") == "session"
    except Exception:                                          # noqa: BLE001
        return False


def load_roi_file(path) -> Tuple[List[Roi], Optional[Roi], Tuple[int, int], Optional[int]]:
    """(nuclei, background, image_shape, seg_timepoint)."""
    with np.load(long_path(path), allow_pickle=False) as z:
        n = int(z["n"][0])
        h, w = (int(x) for x in z["image_shape"])
        rois = []
        for i in range(n):
            shape = tuple(int(x) for x in z[f"shape_{i}"])
            mask = np.unpackbits(z[f"mask_{i}"])[:shape[0] * shape[1]]
            mask = mask.reshape(shape).astype(bool)
            bbox = tuple(int(x) for x in z[f"bbox_{i}"])
            inc, man = (int(x) for x in z[f"flags_{i}"])
            rois.append(Roi(bbox, mask, "nucleus", bool(inc), "manual" if man else "auto"))
        bg = None
        if "bg_bbox" in z:
            y0, x0, y1, x1 = (int(x) for x in z["bg_bbox"])
            m = np.ones((y1 - y0, x1 - x0), bool)
            if "bg_mask" in z:
                sh = tuple(int(x) for x in z["bg_shape"])
                m = np.unpackbits(z["bg_mask"])[:sh[0] * sh[1]].reshape(sh).astype(bool)
            bg = Roi((y0, x0, y1, x1), m, "background")
        seg = int(z["seg_timepoint"][0]) if "seg_timepoint" in z else None
    return rois, bg, (h, w), seg


# ---------------------------------------------------------------- v2.3: summary
def _read_small(zf: zipfile.ZipFile, key: str) -> np.ndarray:
    with zf.open(key + ".npy") as f:
        return np.lib.format.read_array(f, allow_pickle=False)


def _array_shape(zf: zipfile.ZipFile, key: str) -> Tuple[int, ...]:
    """Shape of one array from its .npy header only (nothing else decoded)."""
    with zf.open(key + ".npy") as f:
        version = np.lib.format.read_magic(f)
        if version == (1, 0):
            return tuple(np.lib.format.read_array_header_1_0(f)[0])
        if version == (2, 0):
            return tuple(np.lib.format.read_array_header_2_0(f)[0])
    return tuple(_read_small(zf, key).shape)


def _state_from_zip(zf: zipfile.ZipFile) -> Optional[dict]:
    if "state_json.npy" not in zf.namelist():
        return None
    st = json.loads(str(_read_small(zf, "state_json")))
    return st if isinstance(st, dict) else None


_RULE_CLASS: list = []


def _track_rule_class():
    if not _RULE_CLASS:
        try:
            from .rules import TrackRule
        except Exception:                                      # noqa: BLE001
            TrackRule = None
        _RULE_CLASS.append(TrackRule)
    return _RULE_CLASS[0]


def rule_text(rule: dict, channels: Sequence[str] = ()) -> str:
    """'Track whole cell using mRuby WITH intensity in GFP' for a saved rule
    dict ({"comp", "a", "mode", "b"}; channels as names or indices)."""
    TrackRule = _track_rule_class()
    if TrackRule is not None:                          # the one wording (rules.py)
        try:
            r = TrackRule.from_dict(rule, list(channels))
            if r is not None:
                return r.text(list(channels))
        except Exception:                                      # noqa: BLE001
            pass

    def name(v):
        if isinstance(v, str):
            return v
        try:
            return channels[int(v)]
        except (TypeError, ValueError, IndexError):
            return f"channel {v}"
    comp = COMP_WORDS.get(rule.get("comp"), str(rule.get("comp", "?")))
    a, mode, b = name(rule.get("a", 0)), str(rule.get("mode", "only")).lower(), rule.get("b", "")
    if mode == "only" or b in ("", None, -1) or name(b) == a:
        return f"Track {comp} using {a} ONLY"
    return f"Track {comp} using {a} {mode.upper()} intensity in {name(b)}"


def _rules_of(state: dict) -> List[dict]:
    """The saved rules (v2.3), or for v2.0-v2.2 files the rule they amounted
    to: each followed compartment on the channel most of its ROIs were drawn on."""
    if isinstance(state.get("rules"), list):
        return [r for r in state["rules"] if isinstance(r, dict)]
    if not state.get("v2"):                            # v1.7-v1.9: [label, index, channel name]
        out = []
        for row in state.get("rows") or []:
            if isinstance(row, list) and len(row) >= 3 and row[0] in _V1_ROWS:
                out.append({"comp": _V1_ROWS[row[0]], "a": row[2], "mode": "only", "b": ""})
        return out
    names = list(state.get("channels") or [])
    cells = state.get("cells") or []
    if isinstance(cells, str):
        try:
            cells = json.loads(cells)
        except ValueError:
            cells = []
    out = []
    for row in state.get("follow") or []:
        try:
            comp, chans = row[0], list(row[1])
        except (TypeError, IndexError):
            continue
        used = Counter(c[comp] for c in cells if isinstance(c, dict) and comp in c)
        if used:
            a = used.most_common(1)[0][0]
        elif chans and chans[0] in names:
            a = chans[0]
        else:
            a = 0
        if not isinstance(a, str) and names:
            a = names[min(max(0, int(a)), len(names) - 1)]
        out.append({"comp": comp, "a": a, "mode": "only", "b": ""})
    return out


_SUMMARIES: dict = {}            # V2.9: (path, size, mtime) -> summary (read once)


def read_summary(path) -> Optional[dict]:
    """V2.9: _read_summary, remembered for as long as the file is unchanged (same
    size and time stamp) - the Compare window and the earlier-runs search read the
    same files again and again. A copy is returned (callers may change it)."""
    try:
        st_ = os.stat(long_path(Path(path)))
        key = (os.path.normcase(str(path)), st_.st_size, st_.st_mtime_ns)
    except OSError:
        return None
    if key not in _SUMMARIES:
        if len(_SUMMARIES) > 5000:
            _SUMMARIES.clear()
        _SUMMARIES[key] = _read_summary(path)
    got = _SUMMARIES[key]
    return copy.deepcopy(got) if got is not None else None


def _read_summary(path) -> Optional[dict]:
    """
    A quick look at an ROI / session file for the "analysed before" list: reads
    only the state, the image size, the cell count and the SHAPE of the tracking
    arrays (no masks decoded). None if the file is not a readable PeterPiper ROI file.

    {path, version, saved, nd2, nd2_path, fingerprint, image_shape, n_cells, comps,
     tracked, n_timepoints, rules (texts), kind, t0, prefix, + session_id,
     channels, track_shape {comp: (T, N)}, baseline, size, mtime}
    """
    p = Path(path)
    try:
        st_ = os.stat(long_path(p))
        with zipfile.ZipFile(long_path(p)) as zf:
            names = {n[:-4] for n in zf.namelist() if n.endswith(".npy")}
            if "image_shape" not in names:
                return None
            shape = tuple(int(v) for v in _read_small(zf, "image_shape"))[:2]
            n_anchor = int(_read_small(zf, "n").ravel()[0]) if "n" in names else 0
            seg = (int(_read_small(zf, "seg_timepoint").ravel()[0])
                   if "seg_timepoint" in names else None)
            try:
                state = _state_from_zip(zf) or {}
            except (ValueError, KeyError):
                state = {}
            ckey = str(state.get("content_key") or "") or _zip_content_key(zf, state)
            trk = {}
            if "track_json" in names:
                for key in names:
                    if key.startswith("trk_") and key.endswith("_bbox"):
                        s = _array_shape(zf, key)
                        if len(s) >= 2:
                            trk[key[4:-5]] = (int(s[0]), int(s[1]))
        if len(shape) != 2:
            return None
    except Exception:                                          # noqa: BLE001
        return None

    v2 = bool(state.get("v2"))
    cells = state.get("cells") or []
    if isinstance(cells, str):
        try:
            cells = json.loads(cells)
        except ValueError:
            cells = []
    cells = [c for c in cells if isinstance(c, dict)] if isinstance(cells, list) else []
    if v2:
        n_cells = sum(1 for c in cells if c)
        comps = [c for c in COMPS if any(c in cell for cell in cells)] or \
            [c for c in COMPS if c in (state.get("comps") or [])]
        t0 = state.get("t0")
    elif state:                                        # v1.7-v1.8 state ("rows")
        n_cells = max(0, n_anchor - len(set(state.get("deleted") or [])))
        rows = state.get("rows") or []
        comps = [c for c in COMPS if any(isinstance(r, list) and r and _V1_ROWS.get(r[0]) == c
                                         for r in rows)] or ["nucleus"]
        t0 = state.get("test_t", (seg - 1) if seg else None)
    else:                                              # v1.x: ROIs only
        n_cells, comps = n_anchor, ["nucleus"]
        t0 = (seg - 1) if seg else None
    exp = state.get("exp") if isinstance(state.get("exp"), dict) else {}
    tracked = bool(trk)
    if tracked:
        n_t = max(T for T, _ in trk.values())
    else:
        try:
            n_t = int(exp.get("n_timepoints") or 0)
        except (TypeError, ValueError):
            n_t = 0
    kind = state.get("kind")
    if kind not in ("session", "export", "saved"):
        low = p.name.lower()
        kind = ("session" if "_session" in low or p.parent.name in (
            "PeterPiper_sessions", "PD4nav_sessions") else
                "export" if p.parent.name.startswith("Export_") else "saved")
    saved = state.get("saved")
    if not isinstance(saved, str) or not saved:
        saved = datetime.fromtimestamp(st_.st_mtime).isoformat(timespec="seconds")
    channels = list(state.get("channels") or exp.get("channels") or [])
    rules = []
    for r in _rules_of(state) if state else []:
        try:
            rules.append(rule_text(r, channels))
        except Exception:                                      # noqa: BLE001
            pass
    fp = state.get("fingerprint")
    try:
        t0 = int(t0) if t0 is not None else None
    except (TypeError, ValueError):
        t0 = None
    # PeterPiper 1.0: files say which app wrote them; files without it are PD4nav's
    return dict(path=str(p), version=str(state.get("version") or ""), saved=saved,
                app=str(state.get("app") or "PD4nav"),
                nd2=str(state.get("nd2") or ""), nd2_path=str(state.get("nd2_path") or ""),
                fingerprint=fp if isinstance(fp, dict) else {}, image_shape=shape,
                n_cells=int(n_cells), comps=comps, tracked=tracked, n_timepoints=int(n_t),
                rules=rules, kind=kind, t0=t0, prefix=str(state.get("prefix") or ""),
                session_id=str(state.get("session_id") or ""), channels=channels,
                track_shape=trk, baseline=state.get("baseline"),
                user=str(state.get("user") or ""),
                size=int(st_.st_size), mtime=float(st_.st_mtime), content_key=ckey)


# ---------------------------------------------------------- v2.3: can it be used?
def _version_tuple(v) -> Tuple[int, ...]:
    out = []
    for part in str(v or "").split("."):
        try:
            out.append(int(part))
        except ValueError:
            break
    return tuple(out)


def track_problem(track: Optional[dict], n_timepoints: int, n_cells: int,
                  comps=None, state: Optional[dict] = None,
                  channels: Optional[Sequence[str]] = None) -> Optional[str]:
    """
    None if the saved tracking fits the movie and the cells just loaded;
    otherwise one plain-language sentence saying why it cannot be used.
    comps: the compartments this session follows (None = do not check);
    state: the file's state (to name its version when it has no tracking);
    channels: the movie's channel names (None = do not check the count).
    """
    if track is None:
        ver = (state or {}).get("version")
        vt = _version_tuple(ver)
        if vt and vt < (2, 2):
            return (f"This file was made with PD4nav V{ver}, before tracking was saved in ROI "
                    f"files - press TRACK & MEASURE once and it will be saved.")
        if not vt:                       # files before v2.3 do not say which version made them
            return ("This ROI file holds no tracking (it was made with PD4nav V2.1 or older, "
                    "or saved before TRACK & MEASURE was run) - press TRACK & MEASURE once "
                    "and it will be saved.")
        return ("This ROI file was saved before TRACK & MEASURE was run, so it holds no "
                "tracking - press TRACK & MEASURE once and it will be saved.")
    again = " Press TRACK & MEASURE to track again."
    rois, meas = track.get("rois") or {}, track.get("meas") or {}
    if track.get("skipped"):
        part = ", ".join(COMP_WORDS.get(c, c) for c in track["skipped"])
        return f"Part of the saved tracking ({part}) could not be read - the file may be damaged." \
            + again
    if not rois:
        return "The tracking saved in this file is empty." + again
    if comps is not None:
        extra = [c for c in rois if c not in set(comps)]
        if extra:
            part = ", ".join(COMP_WORDS.get(c, c) for c in extra)
            return f"The saved tracking includes {part} ROIs, which this session does not track." \
                + again
    for c, grid in rois.items():
        if len(grid) != n_timepoints:
            return (f"The saved tracking covers {len(grid)} timepoints but this movie has "
                    f"{n_timepoints} - it was made for a different (or shortened) movie."
                    + again)
    for c, grid in rois.items():
        bad = next((len(row) for row in grid if len(row) != n_cells), None)
        if bad is not None:
            return (f"The saved tracking has {bad} cells but {n_cells} cells were loaded."
                    + again)
    for c, grid in rois.items():
        M = meas.get(c)
        mean = getattr(M, "mean", None)
        if M is None or mean is None or np.ndim(mean) != 3 \
                or mean.shape[0] != len(grid) or mean.shape[2] != n_cells:
            return ("The saved measurements do not match the saved outlines - the file may "
                    "be damaged." + again)
        if channels is not None and mean.shape[1] != len(channels):
            return (f"The saved measurements have {mean.shape[1]} channels but this movie has "
                    f"{len(channels)}." + again)
    return None
