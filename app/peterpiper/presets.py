"""
V2.7 saved settings: your analysis and plot conditions as a named file, to
load into another run (or a batch of runs) later.

A settings file (.json, in 'Saved settings' next to PeterPiper's settings, or any
folder you choose) holds

  "analysis": every Settings field - tracking rules (by channel NAME), detection,
              size limits, background, QC, baseline timepoint, the export list
              and the graph look - exactly what the main window uses;
  "plot":     the Compare window's plot (xyplot.Spec: Y measure, vs Time or a
              measure, right Y axis, points), what is shown (each run / mean of
              dish means / pooled), error, baseline choice, title, file types
              and kinetics graphs.

Either part may be missing (a plot-only file, an analysis-only file). Loading
never changes an analysis already made: analysis settings apply to the next
detection / tracking / export; plot settings to the Compare window.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import Settings

KIND = "PeterPiper saved settings"
LEGACY_KINDS = ("PD4nav saved settings",)           # made by PD4nav: still read


def folder() -> Path:
    from .config import _settings_file
    d = _settings_file().parent / "Saved settings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in " -_.()" else "-" for ch in str(name)).strip()
    return keep[:80] or "settings"


def save(path, name: str, analysis: Optional[Settings] = None,
         plot: Optional[dict] = None) -> str:
    """Write a settings file (never overwrites: adds _2, _3 ...). Returns its path."""
    from .safety import new_output_file
    blob = {"kind": KIND, "name": str(name), "version": __version__,
            "saved": dt.datetime.now().isoformat(timespec="seconds")}
    if analysis is not None:
        blob["analysis"] = dataclasses.asdict(analysis)
    if plot is not None:
        blob["plot"] = dict(plot)
    with new_output_file(Path(path)) as (used, stream):
        stream.write(json.dumps(blob, indent=1).encode("utf-8"))
    return str(used)


def read(path) -> dict:
    """The file's contents; ValueError (plain words) if it is not a settings file."""
    try:
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{Path(path).name} could not be read: {e}") from None
    if not isinstance(blob, dict) or blob.get("kind") not in (KIND,) + LEGACY_KINDS:
        raise ValueError(f"{Path(path).name} is not a PeterPiper settings file.")
    return blob


def analysis_settings(blob: dict, base: Optional[Settings] = None) -> Optional[Settings]:
    """A Settings with the file's analysis fields (unknown / renamed fields are
    ignored; fields the file lacks keep base's value). None if the file has
    no analysis part."""
    a = blob.get("analysis")
    if not isinstance(a, dict):
        return None
    s = dataclasses.replace(base) if base is not None else Settings()
    known = {f.name for f in dataclasses.fields(Settings)}
    for k, v in a.items():
        if k in known:
            setattr(s, k, v)
    return s


def listing() -> List[Path]:
    """The settings files in the 'Saved settings' folder, newest first."""
    try:
        return sorted(folder().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []


def describe(blob: dict) -> str:
    """One line: name, what it holds."""
    parts = []
    a = blob.get("analysis")
    if isinstance(a, dict):
        rules = a.get("track_rules") or []
        txt = "; ".join(f"{d.get('comp')} on {d.get('a')}" + (f" {d.get('mode')} {d.get('b')}"
                                                              if d.get("mode") not in (None, "only")
                                                              else "")
                        for d in rules if isinstance(d, dict))
        parts.append(f"analysis (baseline T{a.get('baseline_timepoint')}"
                     + (f", tracking: {txt}" if txt else "") + ")")
    p = blob.get("plot")
    if isinstance(p, dict):
        from .xyplot import Spec
        sp = Spec.from_dict(p.get("spec"))
        parts.append("plot" + (f": {sp.sentence()}" if sp else ""))
    return f"{blob.get('name', '?')} - " + (" + ".join(parts) or "empty")
