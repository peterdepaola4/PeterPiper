"""
Settings for PeterPiper (this version: peterpiper.APP_NAME / peterpiper.__version__).

Everything the user can change lives in one dataclass so that new options can be
added in one place and will automatically be saved to / loaded from JSON and
written into the Settings sheet of the output workbook.

BLOCK: add new parameters here, give them a default, and they flow everywhere.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# --------------------------------------------------------------------------
# Experiment description (filled by the start-up dialog, mostly from metadata)
# --------------------------------------------------------------------------
@dataclass
class Experiment:
    nd2_path: str = ""
    out_dir: str = ""
    channels: List[str] = field(default_factory=list)   # user-editable channel names
    n_timepoints: int = 0
    width: int = 0
    height: int = 0
    um_per_px: float = 1.0
    seconds_per_frame: float = 0.0
    bit_depth: int = 16
    objective: str = ""
    export_tiffs: bool = True
    tiff_subdir: str = "tiffs"
    # V3.0: from every frame's time stamp (not saved; read again when a movie opens).
    # Gaps between timepoints more than GAP_TOLERANCE off the median: [(t, seconds)],
    # t = the 1-based timepoint the gap starts at; span_s = first to last frame.
    frame_gaps: List[tuple] = field(default_factory=list)
    span_s: float = 0.0

    @property
    def n_channels(self) -> int:
        return len(self.channels)

    @property
    def sat_level(self) -> int:
        return (1 << self.bit_depth) - 1

    def time_minutes(self, t: int) -> float:
        """Elapsed minutes at 0-based timepoint index t."""
        return t * self.seconds_per_frame / 60.0

    def recorded_minutes(self) -> float:
        """V3.0: first to last frame as recorded (the time stamps); the even-spacing
        total when they are not known."""
        if self.span_s > 0:
            return self.span_s / 60.0
        return self.time_minutes(max(0, self.n_timepoints - 1))

    def gaps_text(self, limit: int = 4) -> str:
        """V3.0: the uneven gaps in words ('' if none): 'timepoint 1 → 2: 3 h 17 min;
        10 → 11: 54.5 s'."""
        g = list(self.frame_gaps or [])
        if not g:
            return ""
        parts = [f"{int(t)} → {int(t) + 1}: {duration_text(s)}" for t, s in g[:limit]]
        more = f"; and {len(g) - limit} more" if len(g) > limit else ""
        return f"timepoint{'s' if len(g) > 1 else ''} " + "; ".join(parts) + more

    def time_axis(self, n_t: int, base: int):
        """(x, label) with 0 at the baseline (0-based index `base`): earlier
        timepoints are negative. Minutes when the frame interval is known."""
        import numpy as np
        steps = np.arange(n_t, dtype=float) - int(base)
        if self.seconds_per_frame > 0:
            return steps * self.seconds_per_frame / 60.0, "Time from baseline (min)"
        return steps, "Timepoints from baseline"

    def time_label(self, t: int, base: int) -> str:
        """'-4.5 min' / '+3 min' / 'baseline' for the timepoint label."""
        if t == base:
            return "baseline"
        if self.seconds_per_frame > 0:
            v = (t - base) * self.seconds_per_frame / 60.0
            return f"{v:+.4g} min"
        return f"{t - base:+d}"


GAP_TOLERANCE = 0.2          # V3.0: a gap 20% off the median is reported as uneven


def duration_text(sec: float) -> str:
    """'54.5 s' / '4 min 10 s' / '3 h 17 min'."""
    sec = float(sec)
    if sec < 120:
        return f"{sec:.3g} s" if sec < 100 else f"{sec:.0f} s"
    if sec < 7200:
        m, s = divmod(int(round(sec)), 60)
        return f"{m} min" + (f" {s} s" if s else "")
    h, m = divmod(int(round(sec / 60.0)), 60)
    return f"{h} h" + (f" {m} min" if m else "")


def uneven_gaps(times_s, tolerance: float = GAP_TOLERANCE) -> List[tuple]:
    """V3.0: [(t, gap seconds)] for gaps between timepoints that differ from the
    median gap by more than `tolerance` x the median (t = 1-based timepoint the gap
    starts at). [] for fewer than 3 time stamps or no usable median."""
    import numpy as np
    ts = np.asarray(times_s, dtype=float)
    if ts.size < 3 or not np.all(np.isfinite(ts)):
        return []
    d = np.diff(ts)
    med = float(np.median(d))
    if med <= 0:
        return []
    return [(int(i) + 1, round(float(d[i]), 3)) for i in range(d.size)
            if abs(d[i] - med) > tolerance * med]


# --------------------------------------------------------------------------
# Analysis settings
# --------------------------------------------------------------------------
@dataclass
class Settings:
    # --- which channel drives detection, and what we are measuring ---
    ref_channel: int = 0                 # index into Experiment.channels
    roi_mode: str = "nucleus"            # "nucleus" | "cytoplasm"
    seg_timepoint: int = 1               # 1-based, shown to the user

    # --- nucleus detection ---
    smooth_sigma_px: float = 2.0         # Gaussian smoothing before thresholding
    background_radius_px: float = 60.0   # local-background scale; > nuclear radius
    threshold_factor: float = 1.0        # multiplies the automatic threshold
    core_fraction: float = 0.0           # keep pixels > frac * object's own bright level
    min_area_um2: float = 30.0
    max_area_um2: float = 900.0
    split_touching: bool = True
    split_strength: float = 4.0          # lower splits more readily
    shrink_px: int = 1                   # erode outline inward
    min_solidity: float = 0.80           # 0 disables
    exclude_border: bool = True
    max_shared_border: float = 0.35      # reject watershed fragments; 0 disables
    reject_attached: bool = True         # reject pieces cut off a rejected clump

    # --- optional "only expressing cells" pre-filter ---
    sensor_filter: bool = False
    sensor_channel: int = 1
    min_sensor_signal: float = 50.0      # counts above local background

    # --- cytoplasm (perinuclear ring) ---
    ring_width_um: float = 3.0           # ring thickness outward from nuclear edge
    ring_gap_um: float = 0.5             # gap between nucleus edge and ring start
    ring_exclude_neighbour_um: float = 1.0   # keep clear of neighbouring nuclei
    ring_min_signal_frac: float = 0.0    # drop ring pixels dimmer than frac*nuc signal

    # --- tracking ---
    track_mode: str = "resegment"        # "resegment" | "shift" | "static"
    max_shift_px: int = 25               # largest expected movement per timepoint
    min_overlap: float = 0.15            # IoU needed to call it the same cell
    max_area_change: float = 1.8         # refuse a match that grows/shrinks more than this

    # --- automatic quality control after tracking ---
    qc_enabled: bool = True              # exclude cells that fail QC automatically
    qc_max_lost_frac: float = 0.20       # fraction of timepoints not re-detected
    qc_max_area_jump: float = 2.0        # largest frame-to-frame area ratio
    qc_min_snr: float = 3.0              # signal / background noise, reference channel
    qc_max_saturated_frac: float = 0.02  # fraction of ROI pixels saturated
    qc_spike_sigma: float = 6.0          # one-frame artefact size in robust SDs; 0 disables
    expr_gate: float = 5.0               # biosensor gate, x background noise at baseline

    # --- channel roles and extra compartments (v1.7) ---
    channel_roles: List[str] = field(default_factory=list)   # per channel: nuclear/cell/mito/other
    compartments: List[str] = field(default_factory=list)    # extra: 'cytoplasm', 'mito'
    cell_max_um: float = 30.0            # a cell territory never reaches further than this
    mito_k: float = 3.0                  # mitochondria: x local noise above background
    ref_preblur_um: float = 0.0          # blur before finding cells (old mito method)
    cell_finder: str = ""                # "" = nucleus finder; "cell" / "mito" = whole cells
                                         # from a fill / mito channel (no nuclear stain)
    natural_cutoff: float = -3.0         # start excluded below this naturalness (0 = typical)
    qc_min_area_frac: float = 0.35       # smaller than this x the median cell = speck; 0 off

    # --- responders only: drop cells that never leave +/- resp_threshold of baseline
    resp_enabled: bool = False          # off: cells are chosen in the image / in Excel
    resp_threshold: float = 0.10         # 0.10 = must change by more than 10% from F0
    # what decides it: "any channel", or "; "-separated "F/F0 - <ch>" / "R/R0 - <a>/<b>";
    # a cell is kept if ANY listed quantity responds. Names missing from a file are
    # ignored (all missing -> any channel). 480 = GFP, 647 = Cy5.
    resp_quantity: str = "F/F0 - GFP; R/R0 - GFP/Cy5"
    resp_direction: str = "either"       # "either" (+/-), "rise", "fall"

    # --- display ---
    ui_font_pt: float = 0.0              # text size of the whole app; 0 = Windows default
    ui_theme: str = "midnight"            # V2.9: "midnight" (dark) | "daylight" (light)
    ui_fold_steps: bool = True           # V2.9: the steps you are not on fold to their title
    # V3.0 ratio check: a cell's F/F0 / ratio / R/R0 is left out when a channel it uses
    # is below this x the noise of the ROI's mean at baseline (and a ratio's points
    # where its denominator is) - measure.Measurements.ratio_checked. 0 = off
    ratio_min_snr: float = 5.0
    # v2.1: 'Follow [compartment] - measure [channels]' rows, e.g. [["nucleus", ["GFP", "Cy5"]]]
    follow_rows: List[list] = field(default_factory=list)
    export_list: List[str] = field(default_factory=list)    # your remembered export list
    prism_template: str = ""            # a Prism-saved .pzfx whose graphs are reused
    drift_from: int = 2                 # baseline drift slope: straight line through
    drift_to: int = 9                   #   timepoints drift_from..drift_to
    play_fps: float = 8.0
    seen_prismgraph: bool = False       # v2.2: the .prism graphs were offered once
    seen_methods: bool = False          # v2.3: the Methods text file was offered once
    track_size_tol: float = 0.25        # v2.2: tracked ROI area within +/- this of the drawn size

    # --- v2.3: tracking rules, e.g. "Track [whole cell] using [mRuby] [WITH] intensity in [GFP]"
    # one dict per rule: {"comp": "cell", "a": "mRuby", "mode": "with", "b": "GFP"}
    # (channel NAMES; mode only / with / and / if - see rules.py). Replaces follow_rows.
    track_rules: List[dict] = field(default_factory=list)
    max_move_um: float = 3.0            # largest movement of a cell between two timepoints
    gate_snr: float = 5.0               # IF rule: the second channel must be this x its noise
    overlap_k: float = 3.0              # AND rule: pixel kept if second channel > bg + k x noise
    # --- v2.3: how graphs look (live graph panel, PNG and Prism export) - see graphstyle.py
    graph_style: dict = field(default_factory=dict)
    # --- v2.3: remembering earlier analyses of the same .nd2 (history.py)
    autosave_sessions: bool = True      # keep the session (ROIs + tracking) saved as you work
    ask_previous_runs: bool = True      # on opening an .nd2 analysed before: offer to load it

    # --- automatic tuning ---
    auto_tuned: str = ""                 # summary of the last auto-tune, for the record

    # --- background ROI ---
    background_box_um: float = 25.0      # smallest automatic box (and the hand-drawn default)
    background_max_um: float = 150.0     # the automatic region starts this large (V2.5: 150,
                                         # it may hold non-transfected cells)
    bg_v25: bool = False                 # V2.5: the old 120 um default was moved to 150 once
    sd_v29: bool = False                 # V3.0: a saved SEM (the old default) became SD once

    # --- normalisation / export ---
    baseline_timepoint: int = 1          # 1-based; the dropdown default in Excel
    write_ratio_sheets: bool = True
    normalisation: str = "F/F0"          # fold change, baseline reads 1.0

    # ---------------------------------------------------------------- helpers
    def area_limits_px(self, um_per_px: float) -> tuple[float, float]:
        a = um_per_px * um_per_px
        return self.min_area_um2 / a, self.max_area_um2 / a

    def px(self, microns: float, um_per_px: float) -> float:
        return microns / um_per_px if um_per_px > 0 else microns


# --------------------------------------------------------------------------
# Persistence: remember the last-used settings between runs
# --------------------------------------------------------------------------
def _settings_file() -> Path:
    import os
    custom = os.environ.get("PETERPIPER_HOME")          # set by IT / testing: keep all here
    from . import users
    base = users.home()                             # V2.9: the user's own folder
    base.mkdir(parents=True, exist_ok=True)
    new = base / "settings.json"
    # PeterPiper 1.0 starts empty: no settings are taken over from PD4nav
    olds = [] if custom or not users.gets_old_data() else [
        Path.home() / d / "settings.json" for d in users.OLD_HOMES]
    old = next((o for o in olds if o.exists()), None)
    if not new.exists() and old is not None:        # carry earlier settings over once
        try:
            new.write_bytes(old.read_bytes())
        except OSError:
            pass
    # V2.6: the Compare window's remembered colours / cell lines / groups, once
    for name in ("compare_colours.json", "compare_window.json"):
        dst = base / name
        src = next((o.parent / name for o in olds if (o.parent / name).exists()), None)
        if not dst.exists() and src is not None:
            try:
                dst.write_bytes(src.read_bytes())
            except OSError:
                pass
    return base / "settings.json"


def save_settings(settings: Settings, experiment: Optional[Experiment] = None) -> None:
    """Best-effort save; never raise into the GUI."""
    try:
        blob = {"settings": dataclasses.asdict(settings)}
        if experiment is None:                     # V2.9: keep the last folders
            try:
                old = json.loads(_settings_file().read_text(encoding="utf-8"))
                for k in ("last_dir", "last_out"):
                    if isinstance(old, dict) and k in old:
                        blob[k] = old[k]
            except (OSError, ValueError):
                pass
        if experiment is not None:
            blob["last_dir"] = str(Path(experiment.nd2_path).parent) if experiment.nd2_path else ""
            blob["last_out"] = experiment.out_dir
        _settings_file().write_text(json.dumps(blob, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_settings() -> tuple[Settings, dict]:
    """Return (settings, extras). Unknown / renamed keys are ignored."""
    s = Settings()
    extras: dict = {}
    try:
        blob = json.loads(_settings_file().read_text(encoding="utf-8"))
        known = {f.name for f in dataclasses.fields(Settings)}
        for k, v in (blob.get("settings") or {}).items():
            if k in known:
                setattr(s, k, v)
        extras = {k: v for k, v in blob.items() if k != "settings"}
    except Exception:
        pass
    if not s.bg_v25:                     # V2.5: the automatic background starts at 150 um
        if abs(float(s.background_max_um) - 120.0) < 1e-9:     # (120 was the old default)
            s.background_max_um = 150.0
        # ... and a graph look still at the old (V2.3/V2.4) defaults takes the new
        # template defaults; anything the user changed is kept
        gs = dict(s.graph_style or {})
        for k, old, new in (("mean_colour", "#000000", "#28D2F0"), ("mean_width", 1.0, 0.59),
                            ("symbol_size", 3.0, 4.32), ("font_pt", 12.0, 18.0)):
            if k in gs and (gs[k] == old if isinstance(old, str) else
                            abs(float(gs[k]) - old) < 1e-9):
                gs[k] = new
        s.graph_style = gs
        s.bg_v25 = True
    if not s.sd_v29:                     # V3.0: mean ± SD is the default everywhere; SEM was
        gs = dict(s.graph_style or {})   # only ever saved as the old default - choose it
        if gs.get("error") == "SEM":     # again under Error if you want it
            gs["error"] = "SD"
        s.graph_style = gs
        s.sd_v29 = True
    return s, extras
