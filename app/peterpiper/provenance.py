"""
Provenance: exactly what was done, with which numbers and which software.

Every export carries it, so a lab mate or a reviewer can see how the numbers
were made and you can write the paper's methods section from it:

    software_versions()      Python, the operating system, PeterPiper and every
                             library that touches the numbers
    PARAM_DOCS               label, unit and meaning of every tracking parameter
                             (manual.track_cells out["params"]) and of every
                             setting that changes a number
    parameter_table(...)     (section, parameter, value, meaning) rows - the
                             Settings and Methods sheets of the workbook
    methods_text(...)        a ready-to-edit methods section with the values
                             actually used, followed by the references
    file_rows(...)           which .nd2 file it was (name, path, size, date,
                             quick fingerprint)
    provenance_note(...)     one line for file notes (Prism)

The algorithm descriptions follow the code (manual.py, measure.py, qc.py,
excel.py, export.py) - change them together with the code.

BLOCK: a new parameter that changes numbers = one PARAM_DOCS entry plus one row
in parameter_table() (and a sentence in methods_text() if it matters).
"""
from __future__ import annotations

import datetime as _dt
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import APP_NAME, __version__

# The compartments, as in manual.py (repeated so this module stays light to import)
_COMPS = ("nucleus", "cell", "cytoplasm", "mito")
_LABELS = {"nucleus": "nucleus", "cell": "whole cell", "cytoplasm": "cytoplasm",
           "mito": "mitochondria"}
_FILE_NAMES = {"nucleus": "nucleus", "cell": "whole_cell", "cytoplasm": "cytoplasm",
               "mito": "mito"}
_MODE_WORDS = {"only": "ONLY", "with": "WITH", "and": "AND", "if": "IF"}

# Fixed values in the code (manual.py) that a tracker before V2.3 did not report.
# The tracker's own out["params"] always wins over these.
_CODE_TRACK = {
    "tracker": "redraw-every-frame",
    "area_step": [0.67, 1.5],                 # _redraw: 0.67 x .. 1.5 x the previous area
    "ring_um": 4.0,                           # _edge_level / _redraw background ring
    "edge_level_clip": [0.12, 0.8],           # _edge_level
    "phase_upsample": 10,                     # _sub_shift
}
_SIGMA_UM = {"nucleus": 0.6, "cell": 1.0, "cytoplasm": 1.0, "mito": 2.0}   # manual.SIGMA_UM
_AUTO_BG_MIN_UM = 25.0                         # manual.BG_AUTO_MIN_UM
_HAND_BG_UM = 60.0                             # manual.BG_HAND_UM
# V2.5 background constants (manual.background_params; the tracker's own record wins)
_BG_CODE = {"method": "per-timepoint exclusions v2.5", "smooth_px": 1.0, "bright_k": 10.0,
            "bright_rel": 1.0,
            "move_k": 8.0, "move_min_k": 3.0, "min_object_px": 4, "halo_um": 1.0,
            "roi_margin_um": 2.0, "auto_min_um": 25.0, "auto_free": 0.9,
            "hand_square_um": 60.0}

# Order of the tracker parameters in the tables
TRACK_KEYS = ("tracker", "t0", "max_move_um", "margin_px", "size_tol", "first_frame_tol",
              "size_limits", "area_step", "sigma_um", "ring_um", "edge_level_clip",
              "phase_upsample", "mito_k", "gate_snr", "overlap_k", "norm", "rule_lock",
              "boundaries", "wall_px")


# ==========================================================================
#  Software versions
# ==========================================================================
_PACKAGES = ("numpy", "scipy", "scikit-image", "nd2", "dask", "PySide6-Essentials", "PySide6",
             "pyqtgraph", "matplotlib", "openpyxl", "tifffile", "imagecodecs")


def _os_name() -> str:
    sysname = platform.system() or "unknown"
    if sysname == "Windows":
        ver = platform.version()                     # e.g. 10.0.26300
        try:
            build = int(ver.split(".")[2])
        except (IndexError, ValueError):
            build = 0
        name = "Windows 11" if build >= 22000 else f"Windows {platform.release()}"
        return f"{name}, version {ver}"
    if sysname == "Darwin":
        return f"macOS {platform.mac_ver()[0] or platform.release()}"
    return f"{sysname} {platform.release()}"


def software_versions() -> Dict[str, str]:
    """{name: version} of PeterPiper, Python, the operating system and the libraries.
    A library that is not installed reads 'not installed' (except PySide6, the
    full Qt bundle, which is listed only when installed: PeterPiper needs only
    PySide6-Essentials)."""
    from importlib import metadata
    out: Dict[str, str] = {
        "PeterPiper": f"{__version__} ({APP_NAME})",
        "Python": platform.python_version(),
        "Operating system": _os_name(),
        "Machine": platform.machine() or "unknown",
    }
    for name in _PACKAGES:
        try:
            out[name] = metadata.version(name)
        except Exception:                              # noqa: BLE001
            if name != "PySide6":
                out[name] = "not installed"
    qt = sys.modules.get("PySide6.QtCore")             # only if the GUI already loaded Qt
    if qt is not None:
        try:
            out["Qt"] = str(qt.qVersion())
        except Exception:                              # noqa: BLE001
            pass
    return out


def _installed(versions: Mapping[str, str], name: str) -> str:
    x = str(versions.get(name, "") or "")
    return "" if x == "not installed" else x


# ==========================================================================
#  References (cited in the order they first appear in methods_text)
# ==========================================================================
CITATIONS: Dict[str, str] = {
    "python": "Python Software Foundation. Python Language Reference. https://www.python.org",
    "numpy": ("Harris, C.R., Millman, K.J., van der Walt, S.J. et al. Array programming with "
              "NumPy. Nature 585, 357-362 (2020). https://doi.org/10.1038/s41586-020-2649-2"),
    "scipy": ("Virtanen, P., Gommers, R., Oliphant, T.E. et al. SciPy 1.0: fundamental "
              "algorithms for scientific computing in Python. Nature Methods 17, 261-272 "
              "(2020). https://doi.org/10.1038/s41592-019-0686-2"),
    "scikit-image": ("van der Walt, S., Schönberger, J.L., Nunez-Iglesias, J. et al. "
                     "scikit-image: image processing in Python. PeerJ 2, e453 (2014). "
                     "https://doi.org/10.7717/peerj.453"),
    "nd2": ("Lambert, T. nd2: a Python reader for Nikon NIS-Elements .nd2 files. "
            "https://github.com/tlambert03/nd2"),
    "dask": ("Dask Development Team. Dask: library for dynamic task scheduling (2016). "
             "https://dask.org"),
    "pyside6": "The Qt Company. Qt for Python (PySide6). https://doc.qt.io/qtforpython-6/",
    "pyqtgraph": ("Campagnola, L. et al. PyQtGraph: scientific graphics and GUI library for "
                  "Python. https://www.pyqtgraph.org"),
    "matplotlib": ("Hunter, J.D. Matplotlib: a 2D graphics environment. Computing in Science "
                   "& Engineering 9(3), 90-95 (2007). https://doi.org/10.1109/MCSE.2007.55"),
    "openpyxl": ("Gazoni, E. & Clark, C. openpyxl: a Python library to read/write Excel "
                 "2010 xlsx/xlsm files. https://openpyxl.readthedocs.io"),
    "tifffile": "Gohlke, C. tifffile. https://github.com/cgohlke/tifffile",
    "prism": ("GraphPad Prism [version], GraphPad Software, Boston, Massachusetts, USA. "
              "https://www.graphpad.com"),
}


class _Refs:
    """Numbers the references in the order they are first cited."""

    def __init__(self) -> None:
        self.keys: List[str] = []

    def __call__(self, key: str) -> str:
        if key not in self.keys:
            self.keys.append(key)
        return f"[{self.keys.index(key) + 1}]"

    def lines(self) -> List[str]:
        return [f"[{i + 1}] {CITATIONS[k]}" for i, k in enumerate(self.keys)]


# ==========================================================================
#  What every parameter means
# ==========================================================================
# key: (label, unit, meaning). Tracker keys = manual.track_cells out["params"];
# the others are Settings fields that change a number in the results.
PARAM_DOCS: Dict[str, Tuple[str, str, str]] = {
    # ---- the tracker (out["params"]) ----
    "tracker": ("Tracking method", "",
                "Every ROI is re-outlined (redrawn) from the pixels of every timepoint, "
                "starting on the timepoint it was drawn on, then forwards to the end and "
                "backwards to the start."),
    "t0": ("ROIs drawn on timepoint", "1-based",
           "The timepoint the ROIs were drawn on; tracking starts there (the tracker stores "
           "it 0-based; shown 1-based like everywhere else)."),
    "max_move_um": ("Largest movement between two timepoints", "µm",
                    "A cell's image shift between consecutive timepoints is searched only up to "
                    "this far, and a redrawn outline may reach at most this far beyond the "
                    "moved one."),
    "margin_px": ("Search margin", "px",
                  "The largest movement in pixels (at least 3 px): limit of the shift search "
                  "and the band around the moved outline in which the new edge may lie."),
    "size_tol": ("Size may change by", "± fraction of the drawn area",
                 "A redrawn ROI must stay within this fraction of the area you drew; a redraw "
                 "outside it is re-fitted to the nearest allowed size (or, if that fails, the "
                 "moved outline is kept and the timepoint is flagged). V2.5: a hard limit - "
                 "never more or fewer pixels than that. 0 = redrawn at every timepoint but "
                 "with exactly the number of pixels drawn."),
    "size_limits": ("Hard size limits", "× drawn pixel count",
                    "The followed region never has more / fewer pixels than these multiples of "
                    "the drawn area: a larger redraw keeps its brightest connected pixels around "
                    "its middle, a smaller one grows by the brightest neighbouring pixels (never "
                    "into another cell or across a boundary line)."),
    "rule_lock": ("Rules locked to the ONLY outline", "",
                  "Every rule follows the cell exactly as ONLY does, on channel A's raw pixels. "
                  "WITH and AND only keep part of that outline's pixels (measured); IF only "
                  "excludes cells. No ROI is ever bigger than its ONLY outline."),
    "boundaries": ("Tracker boundary lines", "image px (x, y), per cell",
                   "Lines drawn by the user that the cell's ROIs never cross: each ROI is kept "
                   "inside the connected part of the image, between the lines, that held the "
                   "drawn ROI."),
    "wall_px": ("Boundary line thickness", "px",
                "Boundary lines are drawn this thick, so no region can pass through a diagonal "
                "gap."),
    "first_frame_tol": ("Size tolerance on the drawn timepoint", "± fraction",
                        "On the timepoint you drew on, the redrawn outline must stay this close "
                        "to your outline (the smaller of 0.10 and the size tolerance); "
                        "otherwise your outline is kept."),
    "area_step": ("Area change between consecutive timepoints", "× previous area",
                  "A redrawn area must also lie between these multiples of the previous "
                  "timepoint's area."),
    "sigma_um": ("Smoothing before redrawing", "µm, Gaussian σ",
                 "Per compartment, the image is smoothed with a Gaussian of this σ (at least "
                 "0.8 px) before the outline is redrawn. Measurements use the raw pixels."),
    "ring_um": ("Local background ring", "µm",
                "Width of the ring around an ROI whose 20th percentile is its local background "
                "when redrawing (not the background that is subtracted)."),
    "edge_level_clip": ("Edge level limits", "fraction",
                        "Each ROI's edge level, (edge − local background) / (inside − local "
                        "background) on the drawn timepoint, is kept within this range."),
    "phase_upsample": ("Sub-pixel shift precision", "1/px",
                       "Upsampling factor of the phase cross-correlation that measures each "
                       "cell's shift (10 = 0.1 px steps)."),
    "mito_k": ("Mitochondria threshold", "× noise",
               "Mitochondria pixels must be brighter than this many times the background noise "
               "in the top-hat filtered image (and above the cell's own Otsu split)."),
    "gate_snr": ("IF rule: minimum signal-to-noise in the second channel", "× noise",
                 "IF rule: a cell is kept only if its second-channel signal inside the ROI is "
                 "this many times the noise above a ring around it."),
    "overlap_k": ("AND rule: pixel threshold in the second channel", "× noise",
                  "AND rule: an ROI pixel is measured only where the second channel is this "
                  "many times its noise above its local background."),
    "norm": ("Channel scaling for WITH / AND rules", "counts",
             "Per channel: background level, bright level and noise, measured once on the "
             "drawn timepoint and then kept fixed for every timepoint."),
    # ---- settings that change numbers ----
    "seg_timepoint": ("ROIs drawn on timepoint", "1-based",
                      "The timepoint tracking started from (also used by QC for the speck "
                      "test)."),
    "track_size_tol": ("Size may change by", "± fraction of the drawn area",
                       "The setting behind the tracker's size tolerance (step 3)."),
    "baseline_timepoint": ("Baseline timepoint (F0, R0)", "1-based",
                           "F/F0 and R/R0 divide by the value at this timepoint; it is time 0 "
                           "on every graph and table."),
    "drift_from": ("Baseline drift: first timepoint", "1-based",
                   "First timepoint of the straight-line fit whose slope is the baseline "
                   "drift."),
    "drift_to": ("Baseline drift: last timepoint", "1-based", "Last timepoint of that fit."),
    "background_max_um": ("Automatic background: largest square", "µm",
                          "The automatic background region starts as a square this size and "
                          "shrinks by 15 % per step (to no less than 25 µm) only if it does not "
                          "fit: at least 90 % of it must be free of very bright objects and the "
                          "measured ROIs. It may hold non-transfected cells (their "
                          "autofluorescence is background)."),
    "background_box_um": ("Background box setting", "µm",
                          "Not used by the click workflow (V2.2 and later): the automatic "
                          "region never shrinks below 25 µm and a hand-placed region is a "
                          "60 µm square."),
    "write_ratio_sheets": ("Ratio sheets", "",
                           "Ratios (R, R/R0) are made for every ordered pair of channels."),
    "ref_channel": ("QC: signal/noise channel", "",
                    "The channel whose signal/noise the QC checks."),
    "qc_max_lost_frac": ("QC: timepoints not redrawn", "fraction",
                         "A note is added when the redraw was rejected (moved outline used) "
                         "at more than this fraction of the timepoints."),
    "qc_max_area_jump": ("QC: largest area change between timepoints", "×",
                         "A note is added when the ROI area changes by more than this factor "
                         "from one timepoint to the next."),
    "qc_min_snr": ("QC: minimum signal/noise", "",
                   "Median background-subtracted signal divided by the median pixel SD of the "
                   "background region; a note is added below this."),
    "qc_max_saturated_frac": ("QC: largest saturated fraction", "fraction of ROI pixels",
                              "A note is added when more of the ROI's pixels than this are at "
                              "the detector maximum (any channel, any timepoint)."),
    "qc_spike_sigma": ("QC: one-frame artefact size", "robust SD",
                       "A one-timepoint jump this many robust SDs away from both neighbours "
                       "(while the outline also glitched) is noted; 0 = off."),
    "qc_min_area_frac": ("QC: speck size", "× median ROI area",
                         "An ROI smaller than this fraction of the median ROI on the drawn "
                         "timepoint is noted; 0 = off."),
    "exclude_border": ("QC: image-edge check", "",
                       "A note is added when an ROI touches the image edge at any timepoint."),
    "resp_enabled": ("Responder check", "",
                     "Notes cells whose response never leaves the cut-off band (off = not "
                     "used)."),
    "resp_threshold": ("Responder cut-off", "fraction of baseline",
                       "A cell responds when its smoothed F/F0 or R/R0 leaves 1 ± this."),
    "resp_direction": ("Responder direction", "", "either / rise / fall."),
    "resp_quantity": ("Key quantities", "",
                      "The quantities the responder check uses; also shown first in graphs "
                      "and exports."),
}


# ==========================================================================
#  Small helpers
# ==========================================================================
def _g(v: Any) -> str:
    """A number as short text (0.25 -> '0.25', 3.0 -> '3')."""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _pct(v: Any) -> str:
    try:
        return f"{float(v) * 100:g}%"
    except (TypeError, ValueError):
        return str(v)


def _label_with_unit(key: str) -> str:
    label, unit, _m = PARAM_DOCS[key]
    return f"{label} ({unit})" if unit else label


def comp_label(c: Any) -> str:
    """'cell' / 'whole_cell' -> 'whole cell' (lower case, for sentences)."""
    k = comp_key(c)
    return _LABELS.get(k, k)


def comp_key(c: Any) -> str:
    """'whole_cell' / 'Whole cell' / 'cell' -> 'cell'."""
    c = str(c)
    if c in _COMPS:
        return c
    for k, v in _FILE_NAMES.items():
        if c == v:
            return k
    for k, v in _LABELS.items():
        if c.lower() == v:
            return k
    return c


def _comps_list(comps) -> List[str]:
    if not comps:
        return []
    keys = [comp_key(c) for c in (comps.keys() if isinstance(comps, Mapping) else comps)]
    out: List[str] = []
    for k in keys:
        if k and k not in out:
            out.append(k)
    return sorted(out, key=lambda k: _COMPS.index(k) if k in _COMPS else 9)


def _join(items: Sequence[str], last: str = "and") -> str:
    items = [str(i) for i in items if str(i)]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {last} " + items[-1]


def _chan_name(v: Any, channels: Sequence[str]) -> str:
    if isinstance(v, int) and not isinstance(v, bool):
        return channels[v] if 0 <= v < len(channels) else ""
    return str(v or "")


def rule_text(d: Mapping, channels: Sequence[str] = ()) -> str:
    """'Track whole cell using mRuby WITH intensity in GFP' from a rule dict
    ({"comp", "a", "mode", "b"}; channel names or indices)."""
    comp = _LABELS.get(comp_key(d.get("comp", "")), str(d.get("comp", "")))
    a = _chan_name(d.get("a", ""), channels)
    b = _chan_name(d.get("b", ""), channels)
    mode = str(d.get("mode", "only") or "only").lower()
    if mode == "only" or not b or b == a:
        return f"Track {comp} using {a} ONLY"
    return f"Track {comp} using {a} {_MODE_WORDS.get(mode, mode.upper())} intensity in {b}"


_RULE_RE = re.compile(r"^\s*Track\s+(.+?)\s+using\s+(.+?)\s+(ONLY|WITH|AND|IF)\b"
                      r"(?:\s+intensity\s+in\s+(.+?))?\s*\.?\s*$")


def parse_rules(rules_text=None, provenance: Optional[Mapping] = None, settings=None,
                channels: Sequence[str] = ()) -> List[Dict[str, str]]:
    """
    The tracking rules as [{text, comp, a, b, mode}] (channel names; mode is the
    effective one: 'only' when it needs a second channel that is missing).
    First source that has any: rules_text (texts, dicts or rules.TrackRule),
    provenance['rules'], settings.track_rules.
    """
    src: List[Any] = list(rules_text or [])
    if not src and provenance:
        src = list(provenance.get("rules") or [])
    if not src and settings is not None:
        src = list(getattr(settings, "track_rules", None) or [])
    out: List[Dict[str, str]] = []
    for r in src:
        if hasattr(r, "to_dict") and not isinstance(r, Mapping):     # a rules.TrackRule
            r = r.to_dict(channels)
        if isinstance(r, Mapping):
            a = _chan_name(r.get("a", ""), channels)
            b = _chan_name(r.get("b", ""), channels)
            mode = str(r.get("mode", "only") or "only").lower()
            if mode == "help":                    # V3.0: main + helper channels
                hs = [_chan_name(h, channels) for h in (r.get("helpers") or [])]
                hs = [h for h in hs if h and h != a]
                out.append(dict(text=rule_text(r, channels), comp=comp_key(r.get("comp", "")),
                                a=a, b=" + ".join(hs), mode="help" if hs else "only"))
                continue
            if mode == "only" or not b or b == a:
                mode, b = "only", ""
            out.append(dict(text=rule_text(r, channels), comp=comp_key(r.get("comp", "")),
                            a=a, b=b, mode=mode))
            continue
        t = str(r)
        m = _RULE_RE.match(t)
        if m:
            mode = m.group(3).lower()
            b = (m.group(4) or "").strip() if mode != "only" else ""
            out.append(dict(text=t, comp=comp_key(m.group(1)), a=m.group(2).strip(),
                            b=b, mode=mode if b else "only"))
        else:
            out.append(dict(text=t, comp="", a="", b="", mode="only"))
    return out


# ==========================================================================
#  The tracking parameters actually used
# ==========================================================================
def track_parameters(settings, exp, track_params: Optional[Mapping] = None
                     ) -> Tuple[Dict[str, Any], bool]:
    """(parameters, recorded): the tracker's own out["params"] when given
    (recorded=True), filled in from the settings and the code's fixed values for
    anything it did not report."""
    um = float(getattr(exp, "um_per_px", 1.0) or 1.0)
    move = float(getattr(settings, "max_move_um", 3.0))
    tol = float(getattr(settings, "track_size_tol", 0.25))
    p: Dict[str, Any] = dict(_CODE_TRACK)
    p.update(
        t0=int(getattr(settings, "seg_timepoint", 1)) - 1,
        max_move_um=move,
        margin_px=int(max(3, round(move / max(um, 1e-9)))),
        size_tol=tol,
        first_frame_tol=min(0.10, tol),
        sigma_um=dict(_SIGMA_UM),
        mito_k=float(getattr(settings, "mito_k", 3.0)),
        gate_snr=float(getattr(settings, "gate_snr", 5.0)),
        overlap_k=float(getattr(settings, "overlap_k", 3.0)),
    )
    recorded = bool(track_params)
    if track_params:
        p.update(dict(track_params))
    return p, recorded


def _fmt_param(key: str, v: Any, channels: Sequence[str] = ()) -> Any:
    """A parameter value as a number (if it is one) or short text."""
    if v is None:
        return ""
    if key == "t0":
        try:
            return int(v) + 1
        except (TypeError, ValueError):
            return str(v)
    if key == "sigma_um" and isinstance(v, Mapping):
        return ", ".join(f"{_LABELS.get(comp_key(c), c)} {_g(s)}" for c, s in v.items())
    if key == "norm" and isinstance(v, Mapping):
        parts = []
        for ch, d in v.items():
            if isinstance(d, Mapping):
                parts.append(f"{_chan_name(ch, channels) or ch}: " + ", ".join(
                    f"{k} {_g(round(float(x), 2)) if isinstance(x, (int, float)) else x}"
                    for k, x in d.items()))
            else:
                parts.append(f"{ch}: {d}")
        return "; ".join(parts)
    if key == "boundaries" and isinstance(v, Mapping):
        parts = []
        for cell, lines in v.items():
            try:
                pts = "; ".join(" / ".join(f"({_g(round(float(q[0]), 1))}, "
                                           f"{_g(round(float(q[1]), 1))})" for q in ln)
                                for ln in lines)
            except (TypeError, ValueError, IndexError):
                pts = str(lines)
            parts.append(f"cell {cell}: {len(lines)} line{'s' if len(lines) != 1 else ''} {pts}")
        return " | ".join(parts)
    if isinstance(v, (list, tuple)):
        return " - ".join(_g(x) for x in v)
    if isinstance(v, Mapping):
        return "; ".join(f"{k}: {_g(x)}" for k, x in v.items())
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return v
    return str(v)


def _extra_meanings(track_params: Optional[Mapping]) -> Dict[str, str]:
    """Meanings of extra tracker keys, from '_note' (a dict) or '<key>_note' strings."""
    out: Dict[str, str] = {}
    if not track_params:
        return out
    note = track_params.get("_note")
    if isinstance(note, Mapping):
        out.update({str(k): str(v) for k, v in note.items()})
    for k, v in track_params.items():
        if isinstance(k, str) and k.endswith("_note") and k != "_note" and isinstance(v, str):
            out[k[:-5]] = v
    return out


def _sat_level(exp) -> int:
    try:
        return int(exp.sat_level)
    except Exception:                                  # noqa: BLE001
        return (1 << int(getattr(exp, "bit_depth", 16) or 16)) - 1


def _ref_name(settings, channels: Sequence[str]) -> str:
    if not channels:
        return ""
    return channels[min(max(0, int(getattr(settings, "ref_channel", 0))), len(channels) - 1)]


def _lost_test_on(s) -> bool:
    """qc_cell only runs the 'not redrawn' test in these (legacy) conditions."""
    return getattr(s, "track_mode", "resegment") == "resegment" and not getattr(s, "cell_finder", "")


# ==========================================================================
#  The parameter table (Settings + Methods sheets)
# ==========================================================================
def parameter_table(settings, exp, track_params: Optional[Mapping] = None,
                    rules_text: Optional[Sequence[str]] = None,
                    provenance: Optional[Mapping] = None) -> List[Tuple[str, str, Any, str]]:
    """
    (section, parameter, value, meaning) for everything that decides a number in
    the results - the values actually used. track_params: manual.track_cells
    out["params"] (None = not recorded: the settings and the code's fixed values
    are shown, and the table says so). provenance (optional): bg_auto (bool),
    comps, rules.
    """
    s, prov = settings, (provenance or {})
    ch = list(getattr(exp, "channels", []) or [])
    T = int(getattr(exp, "n_timepoints", 0) or 0)
    spf = float(getattr(exp, "seconds_per_frame", 0.0) or 0.0)
    rows: List[Tuple[str, str, Any, str]] = []

    def add(section: str, name: str, value: Any, meaning: str = "") -> None:
        rows.append((section, name, value, meaning))

    # ---- image --------------------------------------------------------------
    sec = "Image"
    add(sec, ".nd2 file", Path(str(getattr(exp, "nd2_path", "") or "")).name, "The movie analysed.")
    add(sec, "Channels", ", ".join(ch), "Channel names (from the file; can be renamed at start-up).")
    add(sec, "Timepoints", T, "")
    add(sec, "Image size (px)", f"{getattr(exp, 'width', 0)} x {getattr(exp, 'height', 0)}",
        "Width x height.")
    add(sec, "Pixel size (µm/px)", float(getattr(exp, "um_per_px", 1.0) or 1.0),
        "From the file's calibration, checked at start-up.")
    add(sec, "Frame interval (s)", spf if spf > 0 else "unknown",
        "Median spacing of the frames' time stamps, checked at start-up." if spf > 0 else
        "Not known: time is given in timepoints.")
    span = float(getattr(exp, "span_s", 0.0) or 0.0)
    gaps = exp.gaps_text(limit=20) if hasattr(exp, "gaps_text") else ""
    if span > 0:
        add(sec, "Total duration (min)", round(span / 60.0, 2),
            "First to last frame, from the frames' time stamps.")
    elif spf > 0 and T:
        add(sec, "Total duration (min)", round((T - 1) * spf / 60.0, 2), "")
    if gaps:
        add(sec, "Uneven gaps", gaps,
            "Gaps between timepoints more than 20% off the frame interval (time stamps). "
            "Results space the timepoints evenly at the frame interval, so times next to "
            "these gaps are not the real ones.")
    add(sec, "Bit depth", int(getattr(exp, "bit_depth", 16) or 16),
        f"Pixels at {_sat_level(exp)} counts are counted as saturated.")
    add(sec, "Objective", str(getattr(exp, "objective", "") or "not recorded"), "From the file.")

    # ---- ROIs and tracking rules ----------------------------------------------
    p, recorded = track_parameters(s, exp, track_params)
    rules = parse_rules(rules_text, prov, s, ch)
    modes = {r["mode"] for r in rules}
    comps = _comps_list(prov.get("comps"))
    sec = "ROIs"
    if comps:
        add(sec, "Compartments", ", ".join(_LABELS.get(c, c) for c in comps), "")
    add(sec, _label_with_unit("t0"), _fmt_param("t0", p.get("t0")), PARAM_DOCS["t0"][2])
    if rules:
        for i, r in enumerate(rules):
            add(sec, f"Tracking rule {i + 1}", r["text"],
                "The cells move with the first rule's compartment." if i == 0 else "")
    else:
        add(sec, "Tracking rule", "each ROI on the channel it was drawn on",
            "No rules were set (V2.2 behaviour, the same as ONLY).")
    add(sec, "Channels measured", "every channel in every ROI",
        "The tracking rule only decides where the ROI is; every channel is measured in it.")

    # ---- tracking -------------------------------------------------------------
    sec = "Tracking"
    add(sec, "Parameters recorded by the tracker", "yes" if recorded else "no",
        "yes = the values below were reported by the tracker for this run. no = this "
        "tracking did not record them (e.g. it was done by V2.2): the current settings and "
        "the code's fixed values are shown.")
    extra = _extra_meanings(track_params)
    for key in TRACK_KEYS:
        if key == "t0" or key not in p:
            continue
        if key == "gate_snr" and not modes & {"if", "help"}:
            continue
        if key == "overlap_k" and "and" not in modes:
            continue
        if key == "norm" and not p.get("norm"):
            continue
        if key == "mito_k" and comps and "mito" not in comps:
            continue
        add(sec, _label_with_unit(key), _fmt_param(key, p[key], ch), PARAM_DOCS[key][2])
    for key, v in p.items():                       # anything else the tracker reported
        if key in TRACK_KEYS or key == "background" or str(key).startswith("_") \
                or str(key).endswith("_note"):
            continue
        add(sec, str(key), _fmt_param(key, v, ch), extra.get(key, "Reported by the tracker."))

    # ---- background -----------------------------------------------------------
    sec = "Background"
    auto = prov.get("bg_auto")
    kind = str(prov.get("bg_kind") or "")
    bgp = dict(_BG_CODE)
    if isinstance(p.get("background"), Mapping):
        bgp.update(p["background"])
    new_bg = isinstance(p.get("background"), Mapping)
    add(sec, "Background region", "placed automatically" if auto is True else
        "drawn by hand (freehand outline)" if kind == "hand" else
        "placed by hand" if auto is False else "not recorded (automatic or by hand)",
        ("One fixed region; at every timepoint the mean of ALL its pixels in each channel "
         "is subtracted from every ROI of that channel and timepoint." if bgp.get("all_pixels")
         else "One fixed region; at every timepoint the mean of its remaining pixels in each "
         "channel is subtracted from every ROI of that channel and timepoint."))
    if prov.get("bg_um2"):
        add(sec, "Background region area (µm²)", round(float(prov["bg_um2"]), 1),
            "The whole region (cells included)" + ("; every pixel is used." if
            bgp.get("all_pixels") else ", before the per-timepoint exclusions."))
    if auto is not False:
        add(sec, _label_with_unit("background_max_um"),
            float(getattr(s, "background_max_um", 150.0)), PARAM_DOCS["background_max_um"][2])
        add(sec, "Automatic background: smallest square (µm)", _AUTO_BG_MIN_UM,
            "Fixed in the code.")
    if auto is not True and kind != "hand":
        add(sec, "Hand-placed background square (µm)", _HAND_BG_UM,
            "Fixed in the code (right-click > Put the background region here).")
    if new_bg and bgp.get("all_pixels"):
        add(sec, "Background method", str(bgp.get("method")),
            "Every pixel of the region is used at every timepoint (cells inside included: "
            "autofluorescence of non-transfected cells is background). Nothing is left out; "
            "the background trace is only checked for jumps and drift.")
        add(sec, "Fluctuation check: jump",
            f"> {_g(bgp.get('fluct_k'))} robust SD of the jumps and > "
            f"{_pct(bgp.get('fluct_rel'))} of the background level",
            f"Jump = background - its running median over {_g(bgp.get('fluct_win'))} "
            f"timepoints; robust SD = 1.4826 × median absolute deviation of the jumps; level = "
            f"median of the trace. Recorded, values unchanged.")
        add(sec, "Fluctuation check: drift", f"> {_pct(bgp.get('drift_rel'))} of the level",
            "Largest minus smallest running median. Recorded, values unchanged.")
        if bgp.get("obj_rel") is not None:
            add(sec, "Object check (warns the user)",
                f"very bright pixels raise the background by > {_pct(bgp.get('obj_rel'))} "
                f"above their usual share; or measured cells cover > "
                f"{_pct(bgp.get('roi_warn'))} of the region",
                "Very bright = above the region median + 10 robust SD and above 2 × the median "
                "(that timepoint's raw pixels). Share = sum of (pixel - median) over those "
                "pixels / (pixel count × median); compared with its median over the movie. "
                "Jumps and drift alone are not warned about (V2.7). Values unchanged.")
        bs = prov.get("background") if isinstance(prov.get("background"), Mapping) else None
        if bs:
            fl = list(bs.get("fluct") or [])
            jf = sorted({t for f in fl for t in (f.get("jump_frames") or [])})
            add(sec, "Timepoints where the background jumped",
                ", ".join(str(t) for t in jf) if jf else "none",
                "Largest jump / drift per channel: " + "; ".join(
                    f"{float(f.get('max_jump_rel') or 0) * 100:.1f}% / "
                    f"{float(f.get('drift_rel') or 0) * 100:.1f}%" for f in fl) + ".")
            if "obj_frames" in bs:
                of = list(bs.get("obj_frames") or [])
                add(sec, "Timepoints with a bright object in the region",
                    ", ".join(str(t) for t in of) if of else "none",
                    "Largest rise of the bright-pixel share per channel: " + ", ".join(
                        f"{float(v) * 100:.1f}%" for v in (bs.get("obj_rel_max") or [])) + ".")
            add(sec, "Measured cells inside the region (largest fraction)",
                f"{float(bs.get('max_roi_frac') or 0) * 100:.2f}%",
                "Pixels of tracked ROIs that lay inside the background region (kept, as every "
                "pixel is).")
    elif new_bg:
        add(sec, "Background method", str(bgp.get("method")),
            "Cells inside the region are kept (autofluorescence of non-transfected cells is "
            "background); only the pixels below are left out, decided at every timepoint "
            "from that timepoint's own pixels.")
        add(sec, "Left out: very bright objects", f"> region median + {_g(bgp.get('bright_k'))} "
            f"robust SD and > {_g(1 + float(bgp.get('bright_rel', 1.0)))} × the region median "
            f"(any channel)", "Dead cells, debris. Robust SD = 1.4826 × median absolute "
            f"deviation of the region's raw pixels at that timepoint; tested on the image after "
            f"Gaussian smoothing (σ = {_g(bgp.get('smooth_px'))} px). Both conditions must hold, "
            f"so the dimmer autofluorescence of non-transfected cells is kept.")
        add(sec, "Left out: fast-moving objects",
            f"> 3-timepoint median + {_g(bgp.get('move_k'))} robust SD of the difference, "
            f"and > region median + {_g(bgp.get('move_min_k'))} robust SD",
            "Objects present at that timepoint but at neither neighbour (a slowly moving "
            "cell is present at two of three timepoints and is kept).")
        add(sec, "Objects: smallest size (px) / widened by (µm)",
            f"{_g(bgp.get('min_object_px'))} / {_g(bgp.get('halo_um'))}",
            "Smaller pieces count as noise; objects are widened by their dim rim.")
        add(sec, "Left out: measured ROIs, widened by (µm)", bgp.get("roi_margin_um"),
            "The ROIs of every tracked cell at that timepoint.")
        bs = prov.get("background") if isinstance(prov.get("background"), Mapping) else None
        if bs:
            fr = list(bs.get("frames_with_objects") or [])
            add(sec, "Timepoints with bright / moving objects left out",
                ", ".join(str(t) for t in fr) if fr else "none",
                f"At most {float(bs.get('max_object_frac') or 0) * 100:.2f}% of the region "
                f"at one timepoint. The pixels used per timepoint are on the Area_px sheet.")
    elif recorded:
        add(sec, "Background method", "fixed mask (before V2.5)",
            "This tracking was made before V2.5: bright pixels found when the region was "
            "placed were left out at every timepoint.")

    # ---- normalisation and statistics -----------------------------------------
    sec = "Normalisation"
    add(sec, _label_with_unit("baseline_timepoint"), int(getattr(s, "baseline_timepoint", 1)),
        PARAM_DOCS["baseline_timepoint"][2] + " In this workbook the dropdown at the top of "
        "the Settings sheet can change it.")
    add(sec, "F/F0", "background-subtracted F / F at the baseline", "Baseline reads 1.0.")
    if getattr(s, "write_ratio_sheets", True):
        add(sec, "R/R0", "(F of channel A / F of channel B) / that ratio at the baseline",
            "Made for every ordered pair of channels.")
    add(sec, "Time axis", "minutes from the baseline" if spf > 0 else "timepoints from the baseline",
        "0 = baseline; earlier timepoints are negative.")
    sec = "Statistics"
    add(sec, "Mean and SEM", "of the included cells at each timepoint",
        "SEM = SD / √n; SD with n − 1 in the denominator; n = included cells with a value at "
        "that timepoint.")
    err = str((getattr(s, "graph_style", None) or {}).get("error", "SD") or "SD")
    add(sec, "Error shown on graphs", err,
        {"SEM": "Mean ± SEM.", "SD": "Mean ± SD.",
         "95% CI": "Mean ± t(0.975, n − 1) × SEM.", "none": "Mean only."}.get(err, ""))
    add(sec, "Cells included", "chosen by you",
        "Every cell can be switched off / on (Include sheet); excluded cells stay in the "
        "workbook.")

    # ---- quality control (the tests qc.qc_cell runs after tracking) -----------
    sec = "Quality control"
    add(sec, "What QC does", "notes only",
        "Every ROI is drawn or approved by you, so QC never removes a cell by itself: it "
        "writes notes (QC_report sheet) and you decide on the Include sheet.")
    if _lost_test_on(s):
        add(sec, _label_with_unit("qc_max_lost_frac"), float(s.qc_max_lost_frac),
            PARAM_DOCS["qc_max_lost_frac"][2])
    add(sec, _label_with_unit("qc_max_area_jump"), float(s.qc_max_area_jump),
        PARAM_DOCS["qc_max_area_jump"][2])
    add(sec, PARAM_DOCS["ref_channel"][0], _ref_name(s, ch), PARAM_DOCS["ref_channel"][2])
    add(sec, _label_with_unit("qc_min_snr"), float(s.qc_min_snr), PARAM_DOCS["qc_min_snr"][2])
    add(sec, "QC: at or below background", "in " + ("a channel its tracking rule uses" if rules
                                                    else "any channel"),
        "A note is added when the median background-subtracted intensity is zero or below.")
    add(sec, _label_with_unit("qc_max_saturated_frac"), float(s.qc_max_saturated_frac),
        PARAM_DOCS["qc_max_saturated_frac"][2])
    add(sec, PARAM_DOCS["exclude_border"][0], "on" if s.exclude_border else "off",
        PARAM_DOCS["exclude_border"][2])
    add(sec, _label_with_unit("qc_spike_sigma"), float(s.qc_spike_sigma),
        PARAM_DOCS["qc_spike_sigma"][2])
    add(sec, _label_with_unit("qc_min_area_frac"), float(s.qc_min_area_frac),
        PARAM_DOCS["qc_min_area_frac"][2])
    add(sec, PARAM_DOCS["resp_enabled"][0], "on" if s.resp_enabled else "off",
        PARAM_DOCS["resp_enabled"][2])
    if s.resp_enabled:
        add(sec, _label_with_unit("resp_threshold"), float(s.resp_threshold),
            PARAM_DOCS["resp_threshold"][2])
        add(sec, PARAM_DOCS["resp_direction"][0], str(s.resp_direction),
            PARAM_DOCS["resp_direction"][2])
    add(sec, PARAM_DOCS["resp_quantity"][0], str(s.resp_quantity), PARAM_DOCS["resp_quantity"][2])
    if "if" in modes:
        add(sec, "IF rule gate", f"signal/noise ≥ {_g(p.get('gate_snr'))}",
            "Cells without real signal in the IF channel are excluded, with the reason shown.")

    # ---- baseline drift -------------------------------------------------------
    sec = "Baseline drift"
    add(sec, _label_with_unit("drift_from"), int(getattr(s, "drift_from", 2)),
        PARAM_DOCS["drift_from"][2])
    add(sec, _label_with_unit("drift_to"), int(getattr(s, "drift_to", 9)),
        PARAM_DOCS["drift_to"][2])
    return rows


# ==========================================================================
#  The methods section
# ==========================================================================
def _interval_text(spf: float) -> str:
    if spf <= 0:
        return "at an unknown interval"
    if spf >= 120:
        return f"every {spf / 60:g} min"
    return f"every {spf:g} s"


def _draw_sentences(comps: Sequence[str], mito_k: float) -> List[str]:
    """How a click becomes an outline (manual.draw_* - unchanged since V2.0)."""
    out = []
    if "nucleus" in comps:
        out.append("Nuclei were outlined as the connected region around the brightest point "
                   "within about 2 µm of the click that, after Gaussian smoothing (σ = 0.8 µm), "
                   "was brighter than the local background (15th percentile of the surrounding "
                   "window) plus 35% of the difference to the nucleus's inside brightness "
                   "(median of a 2.5 µm-radius disc), with holes filled.")
    if "cell" in comps or "cytoplasm" in comps:
        out.append("Whole cells were found by Otsu thresholding of a background-flattened, "
                   "noise-scaled, log-transformed copy of the channel (at about 0.5 µm per "
                   "pixel); touching cells were separated by a watershed along the dim lines "
                   "between them, seeded by the user's nucleus ROIs (or by each cell's core), "
                   "and holes were filled.")
    if "cytoplasm" in comps:
        out.append("Cytoplasm was the whole-cell region minus the cell's nucleus ROI (or, "
                   "without one, the dark nuclear hole or dark central core of the cell), "
                   "widened by 0.5 µm.")
    if "mito" in comps:
        out.append(f"Mitochondria were the pixels inside the cell region of a white top-hat "
                   f"filtered image (0.8 µm disc) above both {_g(mito_k)} × the background "
                   f"noise and the cell's own Otsu threshold, plus dense clusters (above the "
                   f"Otsu threshold of the log intensity and still textured); pieces smaller "
                   f"than 0.1 µm² were removed. Only these pixels were measured; the region "
                   f"within 1 µm of them was the outline that was followed.")
    return out


def _hard_size_text(p: Mapping) -> str:
    """V2.5 hard size limits (and size 0 %), for the Tracking paragraph."""
    lim = list(p.get("size_limits") or [])
    if len(lim) != 2:
        return ""
    if abs(float(lim[0]) - float(lim[1])) < 1e-12:
        return (" The size setting was 0%: every ROI was redrawn at every timepoint and then "
                "given exactly the number of pixels drawn - a larger redraw kept its brightest "
                "connected pixels around its middle, a smaller one was grown by the brightest "
                "neighbouring pixels (never into another cell or across a boundary line).")
    return (f" These size limits were hard: a region with more than {_g(lim[1])} × or fewer "
            f"than {_g(lim[0])} × the drawn pixel count was trimmed to its brightest connected "
            f"pixels around its middle or grown by the brightest neighbouring pixels (never "
            f"into another cell or across a boundary line). In every frame, a region that fell "
            f"back to its moved outline gave up any pixel held by another cell.")


def _boundary_text(p: Mapping) -> str:
    b = p.get("boundaries")
    if not isinstance(b, Mapping) or not b:
        return ""
    cells = sorted(b, key=lambda c: int(c) if str(c).isdigit() else 0)
    n = sum(len(v) for v in b.values())
    return (f" For {len(cells)} cell{'s' if len(cells) != 1 else ''} (cell "
            f"{', '.join(str(c) for c in cells)}), {n} boundary line{'s' if n != 1 else ''} "
            f"drawn by the user (fixed in the image, {_g(p.get('wall_px', 3))} px thick) were "
            f"never crossed: the cell's ROIs were kept inside the connected part of the image, "
            f"between the lines, that held its drawn ROI [the coordinates are listed in the "
            f"parameter table].")


def _background_text(bg: Mapping, prov: Mapping, bmax: float) -> str:
    """The V2.5 Background paragraph (cells included, per-timepoint exclusions)."""
    b = dict(_BG_CODE)
    b.update(bg)
    auto, kind = prov.get("bg_auto"), str(prov.get("bg_kind") or "")
    size = f" ({float(prov['bg_um2']):.0f} µm²)" if prov.get("bg_um2") else ""
    if auto is True:
        where = (f"placed automatically{size} as a square of {bmax:g} µm (made smaller, by 15% "
                 f"per step down to {_g(b.get('auto_min_um'))} µm, only where it did not fit), "
                 f"at least {_pct(b.get('auto_free'))} free of very bright objects (on the first, "
                 f"middle and last timepoints) and of the measured ROIs (widened by "
                 f"{_g(b.get('roi_margin_um'))} µm), 5 µm or more from the image edge, nearest "
                 f"the image centre among equally free places")
    elif kind == "hand":
        where = f"drawn by hand as a freehand outline{size}"
    elif auto is False:
        where = f"a {_g(b.get('hand_square_um'))} µm square{size} centred where the user clicked"
    else:
        where = "[placed automatically or by hand - check]"
    bs = prov.get("background") if isinstance(prov.get("background"), Mapping) else {}
    if bg.get("all_pixels"):
        fl = list(bs.get("fluct") or []) if bs else []
        jf = sorted({t for f in fl for t in (f.get("jump_frames") or [])})
        chk = (f" The background trace of each channel was checked for jumps (a timepoint more "
               f"than {_g(b.get('fluct_k'))} robust SD of the jumps and more than "
               f"{_pct(b.get('fluct_rel'))} of the background level away from the running "
               f"median over {_g(b.get('fluct_win'))} timepoints; robust SD = 1.4826 × median "
               f"absolute deviation) and for drift (running median changing by more than "
               f"{_pct(b.get('drift_rel'))} of the level); this check "
               + ("did not change any value." if b.get("obj_rel") is not None else
                  "only informed the user and did not change any value."))
        res = ((f" Jumps were found at timepoint{'s' if len(jf) != 1 else ''} "
                f"{', '.join(str(t) for t in jf)}." if jf else " No jumps were found.")
               if bs else "")
        if b.get("obj_rel") is not None:                  # V2.7: the object check
            chk += (f" The user was warned only when a bright object entered the region (pixels "
                    f"above both the region median + 10 robust SD and twice the median raising "
                    f"the background by more than {_pct(b.get('obj_rel'))} above their usual "
                    f"share) or measured cells covered more than {_pct(b.get('roi_warn'))} of "
                    f"it.")
            if bs and "obj_frames" in bs:
                of = list(bs.get("obj_frames") or [])
                res += (f" A bright object was in the region at timepoint"
                        f"{'s' if len(of) != 1 else ''} {', '.join(str(t) for t in of)}."
                        if of else " No bright object entered the region.")
        return (f"Background. One fixed background region was used, {where}. It included any "
                f"non-transfected cells in it, so their autofluorescence was part of the "
                f"background. Every pixel of the region was used at every timepoint: the "
                f"background of each channel and timepoint was the sum of all the region's raw "
                f"pixel values divided by their number, and was subtracted from every ROI mean "
                f"(the ROI's pixel sum divided by its pixel count) of the same channel and "
                f"timepoint." + chk + res)
    bs = prov.get("background") if isinstance(prov.get("background"), Mapping) else {}
    fr = list(bs.get("frames_with_objects") or []) if bs else []
    obj = (f" Bright or moving objects were left out at {len(fr)} timepoint"
           f"{'s' if len(fr) != 1 else ''} (at most "
           f"{float(bs.get('max_object_frac') or 0) * 100:.2f}% of the region)." if fr else
           (" No bright or moving objects had to be left out." if bs else ""))
    return (f"Background. One fixed background region was used, {where}. It included any "
            f"non-transfected cells in it, so their autofluorescence was part of the "
            f"background. At every timepoint, only these pixels were left out, decided from "
            f"that timepoint's pixels: very bright objects such as dead cells or debris (in any "
            f"channel, after Gaussian smoothing with σ = {_g(b.get('smooth_px'))} px, more than "
            f"{_g(b.get('bright_k'))} robust SD above the region's median at that timepoint "
            f"and more than {_g(1 + float(b.get('bright_rel', 1.0)))} × that median; robust SD = "
            f"1.4826 × median absolute deviation of the region's raw pixels), fast-moving "
            f"objects passing "
            f"through (more than {_g(b.get('move_k'))} robust SD of the difference above the "
            f"median of the same pixel over three consecutive timepoints and more than "
            f"{_g(b.get('move_min_k'))} robust SD above the region's median), each object "
            f"(at least {_g(b.get('min_object_px'))} pixels) widened by "
            f"{_g(b.get('halo_um'))} µm, and the measured ROIs of that timepoint widened by "
            f"{_g(b.get('roi_margin_um'))} µm.{obj} The background of each channel and "
            f"timepoint was the sum of the remaining raw pixel values divided by their number, "
            f"and was subtracted from every ROI mean (the ROI's pixel sum divided by its pixel "
            f"count) of the same channel and timepoint.")


def graphs_text(s) -> str:
    """One sentence (with a leading space) on what the exported graphs show: the
    PNG / SVG in the graph look, the Prism .prism graphs in the closest Prism look
    (graphstyle.prism_look) - or their own look when made from the user's own
    Prism file that was not made from PeterPiper's."""
    from . import graphstyle as GS
    st = GS.coerce(getattr(s, "graph_style", None) or {})
    err = {"SEM": "the mean ± SEM", "SD": "the mean ± SD",
           "95% CI": "the mean ± the 95% confidence interval, t(0.975, n − 1) × SEM",
           "none": "the mean only"}.get(st.error, "the mean ± SD")
    if st.show_mean:
        bars = "" if st.error == "none" else " (error bars)"
        png = err + ("" if st.error == "none" else
                     " (shaded band)" if st.error_style == "band" else bars)
        prism = err + bars
    else:
        png, prism = "no mean", "the mean as a thin line without error bars"
    cells = " and each included cell as a thin line" if st.show_cells else ""
    if not (st.show_mean or st.show_cells):
        png = "no data"
    tpl = str(getattr(s, "prism_template", "") or "")
    own = ""
    if tpl.lower().endswith(".prism"):
        try:
            from .prismfile import template_takes_style
            if not template_takes_style(tpl):
                own = (" Prism .prism graphs were made from the user's own Prism file and "
                       "keep its look [check what they show].")
        except Exception:                          # noqa: BLE001 - text only
            pass
    if png == prism and not own:
        return f" Graphs (PNG / SVG and Prism .prism) show {png}{cells}."
    out = f" PNG / SVG graphs show {png}{cells}"
    if own:
        return out + "." + own
    return out + f"; Prism .prism graphs show {prism}{cells}."


def methods_text(settings, exp, track_params: Optional[Mapping] = None,
                 rules_text: Optional[Sequence[str]] = None, comps=None,
                 versions: Optional[Mapping[str, str]] = None,
                 provenance: Optional[Mapping] = None) -> str:
    """
    A ready-to-edit methods section (plain text; paragraphs separated by blank
    lines) with the values actually used, then the references for the software.
    comps: the compartments analysed (keys, file names or a {comp: ...} dict).
    versions: software_versions() (taken now when None). provenance (optional):
    bg_auto (bool), redrawn ({comp: fraction of ROI-timepoints redrawn}), rules.
    Words in [square brackets] are for you to check or fill in.
    """
    s, prov = settings, (provenance or {})
    v = dict(versions or software_versions())
    ref = _Refs()
    ch = list(getattr(exp, "channels", []) or [])
    T = int(getattr(exp, "n_timepoints", 0) or 0)
    spf = float(getattr(exp, "seconds_per_frame", 0.0) or 0.0)
    um = float(getattr(exp, "um_per_px", 1.0) or 1.0)
    p, recorded = track_parameters(s, exp, track_params)
    rules = parse_rules(rules_text, prov, s, ch)
    modes = {r["mode"] for r in rules}
    comps = (_comps_list(comps) or _comps_list(prov.get("comps"))
             or _comps_list([r["comp"] for r in rules])
             or _comps_list([getattr(s, "roi_mode", "nucleus")]))
    t0 = _fmt_param("t0", p.get("t0"))
    b = int(getattr(s, "baseline_timepoint", 1))
    pd4 = _installed(v, "PeterPiper").split(" (")[0] or __version__
    paras: List[str] = []

    def ver(name: str) -> str:
        x = _installed(v, name)
        return f" {x}" if x else ""

    # ---- image data -------------------------------------------------------------
    span = float(getattr(exp, "span_s", 0.0) or 0.0)       # V3.0: as recorded
    if span > 0 and T > 1:
        dur = f", {span / 60:.4g} min in total"
    else:
        dur = f", {(T - 1) * spf / 60:.4g} min in total" if spf > 0 and T > 1 else ""
    gaps = exp.gaps_text(limit=20) if hasattr(exp, "gaps_text") else ""
    obj = str(getattr(exp, "objective", "") or "")
    paras.append(
        f"Image analysis. Time-lapse images were analysed with PeterPiper {pd4} (custom Python "
        f"software) directly from the Nikon NIS-Elements .nd2 file "
        f"({Path(str(getattr(exp, 'nd2_path', '') or '')).name}), read with the nd2 package "
        f"{ref('nd2')}. The movie had {len(ch)} channel{'s' if len(ch) != 1 else ''} "
        f"({', '.join(ch)}) and {T} timepoints acquired {_interval_text(spf)}{dur}, "
        f"{getattr(exp, 'width', 0)} × {getattr(exp, 'height', 0)} pixels at {um:g} µm per "
        f"pixel, {int(getattr(exp, 'bit_depth', 16) or 16)}-bit"
        + (f", objective {obj}" if obj else "") + ". Pixel size and frame interval were "
        "taken from the file's metadata (frame interval = median spacing of the frame time "
        "stamps) and checked before analysis. "
        + (f"The spacing was uneven ({gaps}); time in the results assumes an even spacing "
           f"at the frame interval, so times next to these gaps are approximate. "
           if gaps else "")
        + "All intensities were measured on the raw pixel "
        "values of each frame (the maximum-intensity projection if the file held a Z-stack); "
        "smoothing was used only to find outlines, never for the measured values.")

    # ---- ROIs ---------------------------------------------------------------------
    names = _join([_LABELS.get(c, c) for c in comps])
    draw = " ".join(_draw_sentences(comps, float(p.get("mito_k", 3.0))))
    paras.append(
        f"Regions of interest. {names[:1].upper() + names[1:]} ROIs were drawn on timepoint "
        f"{t0} by clicking on each cell; each outline was computed from the image around the "
        f"click and could be resized, split, extended or drawn by hand where needed (clearly "
        f"isolated objects could also be proposed automatically and were then reviewed "
        f"[delete if not used]). {draw}".rstrip())

    # ---- tracking -----------------------------------------------------------------
    if rules:
        rule_sent = ("The channel each compartment was outlined and followed on was set by "
                     "tracking rules: " + "; ".join(f'"{r["text"]}"' for r in rules) + ". ")
        lead = rules[0]["comp"]
        lead_txt = f"the cell's {_LABELS.get(lead, lead)} ROI (the first rule)" if lead else \
            "the cell's ROI of the first rule"
    else:
        rule_sent = "Each ROI was outlined and followed on the channel it was drawn on. "
        lead_txt = "the cell's ROI of the first followed compartment"
    mode_sents = []
    locked = bool(p.get("rule_lock"))
    if locked and modes - {"only"}:
        mode_sents.append(
            "Whatever the rule, every ROI was followed exactly as for an ONLY rule, on the "
            "first channel's raw pixels; the second channel could only remove pixels from that "
            "outline (or exclude cells), never enlarge it.")
    if "with" in modes:
        mode_sents.append(
            "For WITH rules, a combined image was made (both channels scaled between their own "
            "background and bright levels, measured once on the drawn timepoint and then kept "
            "fixed, averaged, and expressed in the first channel's counts) and only the pixels "
            "of the followed outline where this image, smoothed as for redrawing, exceeded the "
            "outline's own edge level on it (measured on the drawn timepoint) were measured."
            if locked else
            "For WITH rules, the ROI was found and followed on a combined image: both channels "
            "were scaled between their own background and bright levels (measured once on the "
            "drawn timepoint and then kept fixed), averaged, and expressed in the first "
            "channel's counts.")
    if "and" in modes:
        mode_sents.append(
            f"For AND rules, the ROI was followed on the first channel, and at every timepoint "
            f"only its pixels where the second channel (lightly smoothed) exceeded its local "
            f"background by more than {_g(p.get('overlap_k'))} × its noise were measured (a "
            f"timepoint with no such pixels gave no value).")
    if "help" in modes:
        mode_sents.append(
            f"For rules with helper channels, the ROI was found and followed on a helper image: "
            f"the main channel plus {_g(p.get('help_weight', 0.5))} × each helper channel, each "
            f"scaled between its own background and bright levels (measured once on the drawn "
            f"timepoint and then kept fixed) and expressed in the main channel's counts; at every "
            f"timepoint the outline was kept within {_g(p.get('help_guard_um', 1.0))} µm of the "
            f"outline the main channel alone gave. AUTO-DETECT proposed only cells whose signal "
            f"in every helper channel was at least {_g(p.get('gate_snr'))} × its noise above a "
            f"ring around the ROI (cells added by hand were kept).")
    if prov.get("detector"):
        mode_sents.append(str(prov.get("detector")))
    if "if" in modes:
        mode_sents.append(
            f"For IF rules, the ROI was found and followed on the first channel, and a cell was "
            f"kept only if its second-channel signal inside the ROI on the drawn timepoint was "
            f"at least {_g(p.get('gate_snr'))} × the noise above a ring around it; other cells "
            f"were excluded, with the reason recorded.")
    sig = p.get("sigma_um") or {}
    sig_txt = _join([f"{_g(sig[c])} µm for {_LABELS.get(c, c)}" for c in comps if c in sig]) \
        if isinstance(sig, Mapping) else f"{_g(sig)} µm"
    clip = list(p.get("edge_level_clip") or [0.12, 0.8])
    step = list(p.get("area_step") or [0.67, 1.5])
    redrawn = prov.get("redrawn") or {}
    red_txt = ""
    if isinstance(redrawn, Mapping) and redrawn:
        red_txt = (" The redraw was accepted at " + _join(
            [f"{float(x) * 100:.1f}% ({_LABELS.get(comp_key(c), c)})" for c, x in redrawn.items()])
            + " of all ROI-timepoints.")
    paras.append(
        f"Tracking. {rule_sent}{' '.join(mode_sents)}{' ' if mode_sents else ''}"
        f"Each cell was followed from timepoint {t0} forwards to the last timepoint and "
        f"backwards to the first, and every ROI was redrawn from the pixels of every "
        f"timepoint. (1) Movement: the sub-pixel shift of the neighbourhood of {lead_txt} "
        f"between consecutive timepoints was measured by phase cross-correlation "
        f"(scikit-image {ref('scikit-image')}; upsampling factor {_g(p.get('phase_upsample'))}, "
        f"limited to ±{_g(p.get('margin_px'))} px, i.e. {_g(p.get('max_move_um'))} µm), summed "
        f"over time with sub-pixel precision, and all of the cell's ROIs were moved by the "
        f"whole-pixel part. (2) Redraw: within {_g(p.get('margin_px'))} px of the moved ROI, "
        f"the frame was smoothed with a Gaussian (σ = {sig_txt}) and thresholded at the ROI's "
        f"own edge level, (edge − background) / (inside − background), measured on the drawn "
        f"timepoint and limited to {_g(clip[0])}–{_g(clip[1])} (background = 20th percentile "
        f"of a {_g(p.get('ring_um'))} µm ring around the ROI, inside = median within it); "
        f"pieces covering at least 5% of the moved ROI were kept and holes filled. "
        f"(3) Neighbours: pixels "
        f"nearer another cell's ROI of the same compartment were given to that cell, and other "
        f"cells' nuclei were never included, so no two cells shared pixels. (4) Size guard: "
        f"the redrawn area had to stay within ±{_pct(p.get('size_tol'))} of the drawn area "
        f"and within {_g(step[0])}–{_g(step[1])} × the previous timepoint's area; otherwise "
        f"the threshold level was re-fitted to give the nearest allowed area (and kept for "
        f"later timepoints), and if that failed, or the new outline overlapped the moved one "
        f"by less than half, the moved outline was used and the timepoint was flagged. The "
        f"drawn timepoint itself was redrawn the same way (within "
        f"±{_pct(p.get('first_frame_tol'))} of the drawn outline, which was kept otherwise), "
        f"so every timepoint was outlined by one method."
        + (_hard_size_text(p) if p.get("size_limits") is not None else "")
        + _boundary_text(p)
        + (" Cytoplasm ROIs were followed as whole cells, and the same timepoint's nucleus ROI "
           "(widened by 0.5 µm) was removed." if "cytoplasm" in comps else "")
        + (f" Mitochondria ROIs were followed as their outline, and the mitochondria inside "
           f"were found again at every timepoint (threshold {_g(p.get('mito_k'))} × noise)."
           if "mito" in comps else "")
        + red_txt
        + ("" if recorded else " [These tracking values are the program's settings: this "
           "tracking did not record its own parameters - check them.]"))

    # ---- measurement and background -------------------------------------------------
    paras.append(
        "Measurement. At every timepoint the mean intensity (sum of the pixel values / number of pixels) of every channel was measured in "
        "every ROI (all channels in all ROIs, whichever channel was used for outlining) from "
        "the raw, full-resolution pixels under the final ROI"
        + ("; for cytoplasm ROIs the nucleus was left out" if "cytoplasm" in comps else "")
        + ("; for mitochondria ROIs only the mitochondria pixels were measured"
           if "mito" in comps else "")
        + f". ROI area and the number of saturated pixels (at {_sat_level(exp)} counts) were "
        f"recorded for every ROI and timepoint.")
    auto = prov.get("bg_auto")
    bmax = float(getattr(s, "background_max_um", 150.0))
    if isinstance(p.get("background"), Mapping):            # V2.5 background
        paras.append(_background_text(p["background"], prov, bmax))
    auto_txt = (f"placed automatically as the largest square (starting at {bmax:g} µm and "
                f"shrinking by 15% per step to no less than {_AUTO_BG_MIN_UM:g} µm, at least "
                f"5 µm from the image edge) that was at least 90% free of signal - anything "
                f"brighter than 4 robust SD above the background in any channel on the first, "
                f"middle and last timepoints, plus an 8 µm margin - with the remaining bright "
                f"pixels left out")
    hand_txt = (f"a {_HAND_BG_UM:g} µm square centred on an empty area chosen by the user, "
                f"leaving out any pixel brighter than 4 robust SD above the background in any "
                f"channel (plus a 4 µm margin)")
    where = auto_txt if auto is True else hand_txt if auto is False else \
        f"[either] {auto_txt} [or] {hand_txt}"
    if not isinstance(p.get("background"), Mapping):        # tracked before V2.5
        paras.append(
            f"Background. One fixed, cell-free background region was used at every timepoint, "
            f"{where}. Its mean intensity in each channel and timepoint was subtracted from every "
            f"ROI mean of the same channel and timepoint.")

    # ---- normalisation and statistics ----------------------------------------------
    ratios = bool(getattr(s, "write_ratio_sheets", True))
    paras.append(
        f"Normalisation. For each cell, the background-subtracted intensity F was divided by "
        f"its value at the baseline timepoint (timepoint {b}, defined as time 0): F/F0."
        + (" Ratios R of background-subtracted intensities (channel A / channel B) were made "
           "for every ordered pair of channels and normalised in the same way (R/R0)."
           if ratios and len(ch) > 1 else "")
        + " A missing or zero baseline value gives no value for that cell."
        + (f" A cell's F/F0, ratio and R/R0 were left out when a channel they use was, at the "
           f"baseline timepoint, less than {_g(getattr(s, 'ratio_min_snr', 5.0))} × the noise "
           f"of the ROI's mean above background (the background region's pixel SD / √(ROI "
           f"pixels)), and single ratio values where the denominator fell below that level."
           if float(getattr(s, "ratio_min_snr", 5.0)) > 0 else "")
        + " Time is given in "
        + ("minutes" if spf > 0 else "timepoints") + " from the baseline.")
    err_txt = graphs_text(s)
    from . import graphstyle as GS
    paras.append(
        "Statistics. Results are given for each cell and as the mean ± "
        + {"SEM": "SEM", "95% CI": "95% confidence interval"}.get(
            GS.coerce(getattr(s, "graph_style", None) or {}).error, "SD")
        + " of the included cells at each timepoint (SD with n − 1 in the denominator, SEM = "
        "SD / √n, 95% CI = t(0.975, n − 1) × SEM; n = included cells with a value at that "
        "timepoint)." + err_txt + " Cells were included or "
        "excluded by the user after checking the tracked outlines and the QC notes; excluded "
        "cells remain in the results files. [Add the number of cells and experiments and any "
        "statistical tests here.]")

    # ---- QC ---------------------------------------------------------------------------
    qc = []
    if _lost_test_on(s):
        qc.append(f"the redraw was rejected at more than {_pct(s.qc_max_lost_frac)} of the "
                  f"timepoints")
    qc.append(f"the area changed more than {_g(float(s.qc_max_area_jump))}-fold between "
              f"consecutive timepoints")
    if ch:
        qc.append(f"the signal-to-noise ratio in {_ref_name(s, ch)} (median background-"
                  f"subtracted intensity / median pixel SD of the background region) was below "
                  f"{_g(float(s.qc_min_snr))}")
    if rules:
        per = [f"{_LABELS.get(r['comp'], r['comp'])}: {r['a']}" + (f", {r['b']}" if r["b"] else "")
               for r in rules if r["a"]]
        qc.append("the median background-subtracted intensity was at or below zero in a "
                  "channel used by the cell's tracking rule" + (f" ({'; '.join(per)})" if per else ""))
    else:
        qc.append("the median background-subtracted intensity was at or below zero in any channel")
    qc.append(f"more than {_pct(s.qc_max_saturated_frac)} of the ROI's pixels were saturated "
              f"(any channel, any timepoint)")
    if s.exclude_border:
        qc.append("the ROI touched the image edge")
    if float(s.qc_spike_sigma) > 0:
        qc.append(f"a one-timepoint artefact occurred (a value more than "
                  f"{_g(float(s.qc_spike_sigma))} robust SD and 20% away from both neighbours "
                  f"while they agreed, at a timepoint where the outline also changed by more "
                  f"than 25% or was not redrawn; timepoints where at least a quarter of the "
                  f"cells, and at least 3, jumped together were ignored)")
    if float(s.qc_min_area_frac) > 0:
        qc.append(f"the ROI was smaller than {_g(float(s.qc_min_area_frac))} × the median ROI "
                  f"area on timepoint {t0}")
    if s.resp_enabled:
        sign = {"rise": "+", "fall": "−"}.get(s.resp_direction, "±")
        qc.append(f"the 3-point median-smoothed {s.resp_quantity or 'F/F0'} never changed by "
                  f"more than {sign}{_pct(s.resp_threshold)} from baseline after the baseline")
    paras.append(
        "Quality control. Every tracked cell was checked for technical problems, and a note "
        "was made when " + "; when ".join(qc) + ". Because every ROI was drawn or approved by "
        "the user, these notes did not remove cells automatically; they were used when "
        "deciding which cells to include.")
    a, z = int(getattr(s, "drift_from", 2)), int(getattr(s, "drift_to", 9))
    paras.append(
        f"Baseline drift (where reported) is the slope of a least-squares straight line fitted "
        f"to each cell's trace over timepoints {a}–{z}, per "
        + ("minute." if spf > 0 else "timepoint."))

    # ---- software -----------------------------------------------------------------------
    py_ref = ref("python")                     # cited first in this sentence
    sw = [f"NumPy{ver('numpy')} {ref('numpy')}", f"SciPy{ver('scipy')} {ref('scipy')}",
          f"scikit-image{ver('scikit-image')} {ref('scikit-image')}",
          f"nd2{ver('nd2')} {ref('nd2')}"]
    if _installed(v, "dask"):
        sw.append(f"dask{ver('dask')} {ref('dask')}")
    qt = _installed(v, "PySide6") or _installed(v, "PySide6-Essentials")
    sw.append(f"PySide6{(' ' + qt) if qt else ''} (Qt for Python) {ref('pyside6')}")
    sw.append(f"pyqtgraph{ver('pyqtgraph')} {ref('pyqtgraph')}")
    sw.append(f"matplotlib{ver('matplotlib')} {ref('matplotlib')}")
    sw.append(f"openpyxl{ver('openpyxl')} {ref('openpyxl')}")
    if _installed(v, "tifffile"):
        sw.append(f"tifffile{ver('tifffile')} {ref('tifffile')}")
    paras.append(
        f"Software. PeterPiper {pd4} ran on Python{ver('Python')} {py_ref} under "
        f"{v.get('Operating system', _os_name())} with " + _join(sw) + ". Tables and graphs "
        f"for GraphPad Prism {ref('prism')} were written as .pzfx / .prism files.")
    return "\n\n".join(paras) + "\n\nReferences\n" + "\n".join(ref.lines())


# ==========================================================================
#  The .nd2 file's identity
# ==========================================================================
def file_rows(nd2_path: str, fingerprint: Optional[Mapping] = None) -> List[Tuple[str, Any]]:
    """(label, value) rows that identify the .nd2 file analysed. fingerprint:
    history.nd2_fingerprint() ({name, size, mtime, quick}); when None, size and
    date are read from the file if it is there (no hash is computed here)."""
    p = Path(str(nd2_path or ""))
    fp = dict(fingerprint or {})
    if not fp and str(nd2_path or ""):
        try:
            from .safety import long_path
            st = os.stat(long_path(p))
            fp = {"name": p.name, "size": st.st_size, "mtime": st.st_mtime}
        except OSError:
            fp = {"name": p.name}
    rows: List[Tuple[str, Any]] = [
        (".nd2 file name", str(fp.get("name") or p.name)),
        (".nd2 full path", str(nd2_path or "")),
    ]
    if fp.get("size") is not None:
        try:
            rows.append(("File size (bytes)", int(fp["size"])))
        except (TypeError, ValueError):
            rows.append(("File size (bytes)", str(fp["size"])))
    if fp.get("mtime") is not None:
        try:
            rows.append(("File last modified", _dt.datetime.fromtimestamp(
                float(fp["mtime"])).strftime("%Y-%m-%d %H:%M:%S")))
        except (TypeError, ValueError, OSError, OverflowError):
            rows.append(("File last modified", str(fp["mtime"])))
    rows.append(("Quick fingerprint (SHA-1 of size + first and last 4 MiB)",
                 str(fp.get("quick") or "not recorded")))
    return rows


def provenance_note(provenance: Optional[Mapping] = None, baseline: Optional[int] = None,
                    channels: Sequence[str] = ()) -> str:
    """One short line for file notes (Prism): version, date, rules, baseline."""
    prov = provenance or {}
    parts = [f"Made with {APP_NAME} ({__version__}) on "
             f"{_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}."]
    rules = parse_rules(None, prov, None, channels)
    if rules:
        parts.append("Tracking rules: " + "; ".join(r["text"] for r in rules) + ".")
    if baseline is None and prov.get("baseline") is not None:
        baseline = prov.get("baseline")
    if baseline is not None:
        try:
            parts.append(f"Baseline (F0, R0, time 0) = timepoint {int(baseline)}.")
        except (TypeError, ValueError):
            pass
    fp = prov.get("fingerprint")
    if isinstance(fp, Mapping) and fp.get("quick"):
        parts.append(f".nd2 fingerprint {str(fp['quick'])[:12]}.")
    return " ".join(parts)
