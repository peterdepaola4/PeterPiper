"""
v2.3: tracking rules - which channel(s) an ROI is found and followed on.

One rule per compartment, built from the dropdowns:

    Track [Nucleus / Whole cell / Cytoplasm / Mitochondria] using [channel A]
          [ONLY | WITH | AND | IF] intensity in [channel B]

    ONLY  the ROI is found and followed on channel A alone (the V2.2 behaviour);
    WITH  combined: inside the ONLY outline, only the pixels where A and B added
          together (each scaled to its own brightness) are above the outline's
          own edge level are kept (measured);
    AND   overlap: inside the ONLY outline, only the pixels that are also
          clearly bright in B are kept (measured);
    IF    gate: the ONLY outline; a cell is kept only IF it has real signal in
          B at the drawn timepoint (else it is excluded, with the reason shown).

V2.5 lock: EVERY rule follows the cell exactly as ONLY does, on channel A's raw
pixels. The second channel can only TRIM pixels from that outline (AND, WITH)
or exclude cells (IF) - it can never make an ROI bigger than the ONLY outline,
so ROIs no longer bleed into neighbours.

The rule only decides WHERE the ROI is. What is measured never changes: every
channel is read in every ROI at every timepoint from the raw pixels.

Normalisation (WITH / AND / IF) uses constants frozen ONCE, on the frame you
drew on (GuideNorm, make_norm) - so the guide image does not re-scale itself
as the cells brighten or dim during the experiment.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi

from .compartments import _robust_noise
from .manual import COMPS, LABELS, RING_UM, _box, _paint_box, _px, _shape, _snr
from .segment import Roi

MODES = ("only", "with", "and", "if")      # the rules before V3.0 (still applied exactly)
HELP = "help"                              # V3.0: main channel + helper channels
MODE_LABELS = {"only": "ONLY", "with": "WITH", "and": "AND", "if": "IF"}   # older rules
# V3.0 wording of the older rules (shown when a run made with one is loaded)
LEGACY_WORDS = {"with": "{b} trims the outline (combined image)",
                "and": "only the pixels also bright in {b} are measured",
                "if": "cells need {b} signal"}
# V3.0 helper channels: the follow image is the main channel plus HELP_WEIGHT x each
# helper (each scaled to its own background and bright level); the outline may reach
# at most HELP_GUARD_UM beyond where the main channel alone would draw it
HELP_WEIGHT = 0.5
HELP_GUARD_UM = 1.0
MODE_HELP = {   # tooltip / README text, one sentence each
    "only": "The ROI is found and followed on channel A alone.",
    "with": "The ROI is followed on channel A exactly as ONLY; inside that outline only the "
            "pixels where A and B added together (each scaled to its own brightness) are "
            "bright are kept (measured). Never bigger than the ONLY outline.",
    "and": "The ROI is followed on channel A exactly as ONLY; inside that outline only the "
           "pixels that are also bright in channel B are kept (measured). Never bigger than "
           "the ONLY outline.",
    "if": "The ROI is followed on channel A exactly as ONLY; a cell is kept only IF it has "
          "real signal in channel B (else it is excluded, with the reason shown).",
}

# ---- constants (quoted in the methods / README; change only with care) ----
NORM_STRIDE = 4          # GuideNorm statistics use every 4th pixel in y and x (1/16 of the
                         # frame: 360 000 pixels of a 2400 x 2400 frame) - the same sample
                         # as manual._plane_noise, so the noise values agree exactly
NORM_BG_PCT = 20.0       # background level = 20th percentile of that sample
NORM_TOP_PCT = 99.5      # bright level     = 99.5th percentile of that sample
                         # noise = 1.4826 x median absolute deviation of the sample pixels
                         # at or below the median (cells do not count; Gaussian-equivalent SD)
AND_SIGMA_UM = 0.5       # AND: channel B is smoothed (Gaussian, sigma 0.5 um) before the test
AND_BG_PCT = 20.0        # AND: local background of B = 20th percentile of a RING_UM (4 um)
                         # ring around the ROI's region (same ring as the tracker uses)
AND_MIN_RING_PX = 20     # ... if the ring has fewer pixels, the frame's GuideNorm bg is used


def _name(channels: Sequence[str], i: int) -> str:
    if channels is not None and 0 <= int(i) < len(channels):
        return str(channels[int(i)])
    return f"channel {int(i) + 1}"


def _resolve(v, channels: Sequence[str]) -> Optional[int]:
    """A channel given as an index or a name -> its index (None if not found)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, np.integer)):
        i = int(v)
        if i < 0:
            return None
        return i if not channels or i < len(channels) else None
    s = str(v).strip()
    if not s:
        return None
    names = [str(c) for c in (channels or [])]
    if s in names:
        return names.index(s)
    low = [c.lower() for c in names]
    if s.lower() in low:
        return low.index(s.lower())
    return None


@dataclass
class TrackRule:
    comp: str            # compartment key ("nucleus" | "cell" | "cytoplasm" | "mito")
    a: int               # channel index: the ROI is found / followed on this channel
    mode: str = "only"   # "only" | "help" (V3.0) | older: "with" | "and" | "if"
    b: int = -1          # second channel index (older modes; unused for "only" / "help")
    helpers: Tuple[int, ...] = ()   # V3.0 "help": helper channel indices

    def helper_list(self) -> List[int]:
        """The helper channels that count: not channel A, no repeats, >= 0."""
        out: List[int] = []
        for h in self.helpers or ():
            h = int(h)
            if h >= 0 and h != int(self.a) and h not in out:
                out.append(h)
        return out

    def effective_mode(self) -> str:
        """The mode actually applied: 'only' when the mode needs channel B (or a
        helper) but it is missing or the same as A (or the mode is unknown)."""
        m = str(self.mode or "only").lower()
        if m == HELP:
            return HELP if self.helper_list() else "only"
        if m not in MODES:
            return "only"
        if m != "only" and (int(self.b) < 0 or int(self.b) == int(self.a)):
            return "only"
        return m

    def channels_used(self) -> List[int]:
        """Channel indices the rule looks at: [a], [a, b] or [a, helpers...]."""
        m = self.effective_mode()
        if m == HELP:
            return [int(self.a)] + self.helper_list()
        return [int(self.a)] if m == "only" else [int(self.a), int(self.b)]

    def text(self, channels: Sequence[str]) -> str:
        """e.g. 'Track whole cell using mRuby WITH intensity in GFP' (older rules) or
        'Track nucleus using GFP, helped by Cy5' (V3.0) - the methods wording."""
        what = LABELS.get(self.comp, str(self.comp)).lower()
        m = self.effective_mode()
        head = f"Track {what} using {_name(channels, self.a)}"
        if m == HELP:
            return f"{head}, helped by " + " + ".join(_name(channels, h) for h in self.helper_list())
        if m == "only":
            return head + " ONLY"
        return f"{head} {MODE_LABELS[m]} intensity in {_name(channels, self.b)}"

    def display_text(self, channels: Sequence[str]) -> str:
        """V3.0 wording for the window: 'Auto-detect nucleus using GFP, helped by Cy5';
        an older rule in the same words plus what its second channel does."""
        what = LABELS.get(self.comp, str(self.comp)).lower()
        m = self.effective_mode()
        head = f"Auto-detect {what} using {_name(channels, self.a)}"
        if m == HELP:
            return f"{head}, helped by " + " + ".join(_name(channels, h) for h in self.helper_list())
        if m == "only":
            return head
        return f"{head}; {LEGACY_WORDS[m].format(b=_name(channels, self.b))} (older rule, kept exactly)"

    def to_dict(self, channels: Sequence[str]) -> dict:
        """{"comp", "a": name, "mode", "b": name or ""} - channel NAMES, so the rule
        still means the same if a file lists its channels in another order.
        The mode stored is the one actually applied (effective_mode)."""
        m = self.effective_mode()
        if m == HELP:                          # V3.0: helper channels by name
            return {"comp": self.comp, "a": _name(channels, self.a), "mode": m, "b": "",
                    "helpers": [_name(channels, h) for h in self.helper_list()]}
        return {"comp": self.comp, "a": _name(channels, self.a), "mode": m,
                "b": "" if m == "only" else _name(channels, self.b)}

    @classmethod
    def from_dict(cls, d, channels: Sequence[str]) -> Optional["TrackRule"]:
        """A rule from to_dict() output (channel names or indices). None if it does
        not fit these channels: unknown compartment or mode, channel A missing,
        or a channel B that is named but missing (never silently changed into a
        different method)."""
        if not isinstance(d, dict):
            return None
        comp = str(d.get("comp", "")).strip()
        if comp not in COMPS:
            return None
        a = _resolve(d.get("a"), channels)
        if a is None:
            return None
        mode = str(d.get("mode", "only") or "only").strip().lower()
        if mode == HELP:                       # V3.0: every named helper must exist
            hs = []
            for v in d.get("helpers") or []:
                h = _resolve(v, channels)
                if h is None:
                    return None
                hs.append(int(h))
            r = cls(comp, int(a), HELP, -1, tuple(hs))
            return r if r.helper_list() else cls(comp, int(a))
        if mode not in MODES:
            return None
        bv = d.get("b", "")
        given = not (bv is None or (isinstance(bv, str) and not bv.strip())
                     or (isinstance(bv, (int, np.integer)) and not isinstance(bv, bool)
                         and int(bv) < 0))
        b = _resolve(bv, channels) if given else -1
        if b is None:
            if mode != "only":
                return None
            b = -1
        return cls(comp, int(a), mode, int(b))


def default_rules(follow_rows, cells: Sequence[Dict[str, Roi]],
                  channels: Sequence[str]) -> List[TrackRule]:
    """
    Migration from V2.1 / V2.2 (no rules): one ONLY rule per followed compartment
    (follow rows [[comp, [channel names]], ...], first row first), with channel A
    = the channel most of that compartment's ROIs were drawn on (ties: the lower
    channel number), else the row's first measured channel, else channel 0.
    With no follow rows, the compartments that have ROIs are used (in COMPS order).
    """
    C = len(channels or [])
    rows = []
    for row in follow_rows or []:
        if not row:
            continue
        comp = row[0]
        names = row[1] if len(row) > 1 else []
        if isinstance(names, str):
            names = [n.strip() for n in names.split(";") if n.strip()]
        rows.append((comp, list(names or [])))
    if not rows:
        rows = [(c, []) for c in COMPS if any(cell.get(c) is not None for cell in cells or [])]
    out: List[TrackRule] = []
    seen = set()
    for comp, names in rows:
        if comp not in COMPS or comp in seen:
            continue
        seen.add(comp)
        chs = []
        for cell in cells or []:
            r = cell.get(comp) if cell else None
            ch = getattr(r, "channel", None) if r is not None else None
            if ch is None or isinstance(ch, bool):
                continue
            try:
                ch = int(ch)
            except (TypeError, ValueError):
                continue
            if 0 <= ch < max(C, 1):
                chs.append(ch)
        if chs:
            a = max(sorted(set(chs)), key=chs.count)
        else:
            a = next((i for i in (_resolve(n, channels) for n in names) if i is not None), 0)
        out.append(TrackRule(comp, int(a)))
    return out


def complete_rules(rules, cells: Sequence[Dict[str, Roi]], comps: Sequence[str],
                   channels: Sequence[str]) -> Dict[str, TrackRule]:
    """
    The rule of every compartment in `comps`, as used by the tracker: rules given
    as TrackRule or dict (names / indices); a missing or unusable rule (channel
    out of range) is replaced by the migration default for that compartment
    (default_rules: the channel most of its ROIs were drawn on, ONLY).
    """
    C = len(channels or [])
    out: Dict[str, TrackRule] = {}
    for c in comps:
        r = (rules or {}).get(c)
        if isinstance(r, dict):
            r = TrackRule.from_dict(r, channels)
        if isinstance(r, TrackRule):
            r = TrackRule(c, int(r.a), str(r.mode or "only").lower(), int(r.b),
                          tuple(int(h) for h in (r.helpers or ())))
            m = r.effective_mode()
            if not (0 <= r.a < C) or (m in MODES and m != "only" and not (0 <= r.b < C)) \
                    or (m == HELP and not all(0 <= h < C for h in r.helper_list())):
                r = None
        if r is None:
            r = default_rules([[c, []]], cells, channels)[0]
        out[c] = r
    return out


# ==========================================================================
#  Normalisation constants (frozen at the drawn timepoint)
# ==========================================================================
@dataclass
class GuideNorm:
    """Per-channel constants frozen at the reference (drawn) timepoint, in raw counts."""
    bg: np.ndarray      # (C,) robust background level (20th percentile)
    top: np.ndarray     # (C,) robust bright level (99.5th percentile), always > bg
    noise: np.ndarray   # (C,) robust pixel noise (1.4826 x MAD of the darker half)

    def to_dict(self, channels: Sequence[str]) -> dict:
        """{channel name: {"bg", "top", "noise"}} (for the methods record)."""
        return {_name(channels, i): {"bg": float(self.bg[i]), "top": float(self.top[i]),
                                     "noise": float(self.noise[i])}
                for i in range(len(self.bg))}


def make_norm(stack: np.ndarray) -> GuideNorm:
    """
    Robust per-channel levels of one frame (C, H, W raw counts), from every
    NORM_STRIDE-th pixel in y and x:
        bg    = 20th percentile (the dark background between cells)
        top   = 99.5th percentile (bright cell signal, ignoring a few hot pixels)
        noise = 1.4826 x MAD of the pixels at or below the median
                (= manual._plane_noise; Gaussian-equivalent SD of the background;
                1 count if the MAD is 0)
    Guard: top is raised to at least bg + max(noise, 1 count) so the scale
    (top - bg) is never zero or negative (an empty / flat channel).
    """
    st = np.asarray(stack)
    if st.ndim == 2:
        st = st[None]
    C = st.shape[0]
    bg, top, noise = np.zeros(C), np.zeros(C), np.ones(C)
    for c in range(C):
        sub = st[c, ::NORM_STRIDE, ::NORM_STRIDE].astype(np.float32)
        if sub.size == 0:
            continue
        b, t, med = (float(v) for v in np.percentile(sub, [NORM_BG_PCT, NORM_TOP_PCT, 50]))
        lo = sub[sub <= med]
        n = _robust_noise((lo - np.median(lo)).ravel()) if lo.size else 1.0
        bg[c], noise[c] = b, float(n)
        top[c] = max(t, b + max(float(n), 1.0))
    return GuideNorm(bg=bg, top=top, noise=noise)


# ==========================================================================
#  The image the ROI is found / followed on
# ==========================================================================
def _ab(rule: TrackRule, C: int) -> Tuple[int, str, int]:
    """(a, effective mode, b) clamped to the channels that exist."""
    a = int(np.clip(int(rule.a), 0, max(C - 1, 0)))
    m = rule.effective_mode()
    if m == HELP:
        return (a, HELP, -1) if _helpers(rule, C) else (a, "only", -1)
    b = int(rule.b)
    if m != "only" and not (0 <= b < C):
        m = "only"
    return a, m, b


def _helpers(rule: TrackRule, C: int) -> List[int]:
    """V3.0: the helper channels of a 'help' rule that exist in a C-channel stack."""
    return [h for h in rule.helper_list() if h < C] if rule.effective_mode() == HELP else []


def guide_key(rule: TrackRule, C: int) -> tuple:
    """Rules that give the same guide image share one key (ONLY / AND / IF on the
    same channel A all use A's raw plane) - the tracker computes each once per frame."""
    a, m, b = _ab(rule, C)
    if m == HELP:
        return (HELP, a) + tuple(_helpers(rule, C))
    return ("with", a, b) if m == "with" else ("raw", a)


def guide_plane(stack: np.ndarray, rule: TrackRule, norm: Optional[GuideNorm],
                box=None) -> np.ndarray:
    """
    The 2-D image the ROI is drawn / redrawn / followed on (box = (y0, x0, y1, x1)
    crop, or None for the whole frame).

    ONLY, AND, IF: stack[a] itself (the raw plane, unchanged - so ONLY is
                   bit-identical to V2.2).
    WITH:          float32 in channel A's count units:
                       za = (A - bgA) / (topA - bgA)
                       zb = (B - bgB) / (topB - bgB)
                       guide = bgA + (topA - bgA) * (za + zb) / 2
                   i.e. both channels scaled to their own background (0) and
                   bright level (1), averaged, and mapped back to A's counts
                   (some thresholds of the drawing code are in counts).
    """
    C = stack.shape[0]
    a, m, b = _ab(rule, C)
    if box is None:
        ys = xs = slice(None)
    else:
        y0, x0, y1, x1 = (int(v) for v in box)
        ys, xs = slice(y0, y1), slice(x0, x1)
    if m == HELP:
        # V3.0 helpers: za + HELP_WEIGHT x each zh, divided by the total weight and
        # mapped back to A's counts (the main channel counts twice each helper)
        if norm is None:
            raise ValueError("Helper channels need the normalisation constants (make_norm).")
        bga = float(norm.bg[a])
        sa = float(norm.top[a]) - bga
        hs = _helpers(rule, C)
        g = stack[a, ys, xs].astype(np.float32)
        g -= np.float32(bga)
        for h in hs:
            zh = stack[h, ys, xs].astype(np.float32)
            zh -= np.float32(norm.bg[h])
            zh *= np.float32(HELP_WEIGHT * sa / (float(norm.top[h]) - float(norm.bg[h])))
            g += zh
        g *= np.float32(1.0 / (1.0 + HELP_WEIGHT * len(hs)))
        g += np.float32(bga)
        return g
    if m != "with":
        return stack[a, ys, xs]
    if norm is None:
        raise ValueError("A WITH rule needs the normalisation constants (make_norm).")
    bga, bgb = float(norm.bg[a]), float(norm.bg[b])
    sa = float(norm.top[a]) - bga
    sb = float(norm.top[b]) - bgb
    g = stack[a, ys, xs].astype(np.float32)
    g -= np.float32(bga)                                     # A - bgA
    zb = stack[b, ys, xs].astype(np.float32)
    zb -= np.float32(bgb)
    zb *= np.float32(sa / sb)                                # (B - bgB) in A's scale
    g += zb
    g *= np.float32(0.5)
    g += np.float32(bga)
    return g


# ==========================================================================
#  AND: keep only the pixels also bright in channel B
# ==========================================================================
def overlap_mask(stack: np.ndarray, roi_like_region: Roi, rule: TrackRule,
                 norm: GuideNorm, um: float, k: float) -> np.ndarray:
    """
    AND rule: the pixels of the ROI (its measured mask, bbox-local, same shape)
    where channel B is clearly bright:
        B smoothed (Gaussian sigma AND_SIGMA_UM = 0.5 um)
          > local B background + k x B's pixel noise
    local background = 20th percentile of smoothed B in a RING_UM (4 um) ring
    around the ROI's region (outline if it has one); noise = GuideNorm noise of
    B (frozen at the drawn timepoint); k = Settings.overlap_k (default 3).
    """
    r = roi_like_region
    m = np.asarray(r.mask, bool)
    C, H, W = stack.shape
    _a, mode, b = _ab(rule, C)
    if mode == "only" or not m.any():
        return m.copy()
    sig = max(0.5, _px(AND_SIGMA_UM, um))
    ring_px = int(max(2, _px(RING_UM, um)))
    box = _box(r.bbox, ring_px + int(np.ceil(3 * sig)) + 1, H, W)
    by0, bx0, by1, bx1 = box
    sm = ndi.gaussian_filter(stack[b, by0:by1, bx0:bx1].astype(np.float32), sig)
    P = _paint_box([Roi(r.bbox, _shape(r), r.kind)], box)
    ring = ndi.binary_dilation(P, iterations=ring_px) & ~P
    bg = float(np.percentile(sm[ring], AND_BG_PCT)) if ring.sum() >= AND_MIN_RING_PX \
        else float(norm.bg[b])
    bright = sm > bg + float(k) * float(norm.noise[b])
    y0, x0, y1, x1 = r.bbox
    return m & bright[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]


def apply_and(roi: Roi, stack: np.ndarray, rule: TrackRule, norm: GuideNorm, um: float,
              k: float) -> Roi:
    """
    The ROI as measured under an AND rule: a copy whose mask keeps only the
    pixels also bright in channel B (overlap_mask) and whose outline is the
    region it was followed by (unchanged), so the next frame is still followed
    on channel A's shape. The mask may be empty (nothing bright in B there):
    then that frame measures NaN. Other rules: the ROI itself.
    (For display on the drawn frame; keep passing the un-ANDed ROI to tracking.)
    """
    if _ab(rule, stack.shape[0])[1] != "and":
        return roi
    keep = overlap_mask(stack, roi, rule, norm, um, k)
    out = replace(roi, mask=keep, outline=_shape(roi).copy())
    out.channel = getattr(roi, "channel", int(rule.a))
    out.__dict__.pop("_contour_cache", None)
    return out


# ==========================================================================
#  WITH (V2.5): keep the pixels of the ONLY outline where A + B is bright
# ==========================================================================
WITH_MIN_RING_PX = 20    # WITH: fewer ring pixels than this -> channel A's GuideNorm bg


def with_mask(stack: np.ndarray, roi: Roi, rule: TrackRule, norm: GuideNorm, um: float,
              level: float, comp: str = "cell") -> np.ndarray:
    """
    WITH rule (V2.5): the pixels of the ROI (its measured mask, bbox-local) where
    the combined image (guide_plane: A and B scaled and averaged, in A's counts),
    smoothed like the tracker smooths this compartment (manual.SIGMA_UM), is
    above the outline's own edge level on that image:
        guide > bg + level x (inside - bg)
    bg = 20th percentile of the guide in a RING_UM (4 um) ring around the
    outline, inside = its median inside the outline; level = the outline's edge
    level on the combined image at the drawn timepoint (frozen there). Holes
    inside are filled (never beyond the outline). Only ever a subset of the mask.
    """
    from .manual import SIGMA_MIN_PX, SIGMA_UM
    m = np.asarray(roi.mask, bool)
    C, H, W = stack.shape
    a, mode, _b = _ab(rule, C)
    if mode != "with" or not m.any():
        return m.copy()
    sig = max(SIGMA_MIN_PX, _px(SIGMA_UM.get(comp, 1.0), um))
    ring_px = int(max(2, _px(RING_UM, um)))
    box = _box(roi.bbox, ring_px + int(np.ceil(3 * sig)) + 1, H, W)
    by0, bx0, by1, bx1 = box
    g = ndi.gaussian_filter(guide_plane(stack, rule, norm, box).astype(np.float32), sig)
    P = _paint_box([Roi(roi.bbox, _shape(roi), roi.kind)], box)
    if not P.any():
        return m.copy()
    ring = ndi.binary_dilation(P, iterations=ring_px) & ~P
    bg = float(np.percentile(g[ring], AND_BG_PCT)) if ring.sum() >= WITH_MIN_RING_PX         else float(norm.bg[a])
    inner = float(np.median(g[P]))
    if inner - bg <= 1e-6:
        return m.copy()
    keep = ndi.binary_fill_holes(P & (g > bg + float(level) * (inner - bg))) & P
    y0, x0, y1, x1 = roi.bbox
    return m & keep[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]


def apply_with(roi: Roi, stack: np.ndarray, rule: TrackRule, norm: GuideNorm, um: float,
               level: float, comp: str = "cell") -> Roi:
    """The ROI as measured under a WITH rule: a copy whose mask keeps only
    with_mask's pixels and whose outline is the followed (ONLY) region. Other
    rules: the ROI itself."""
    if _ab(rule, stack.shape[0])[1] != "with":
        return roi
    keep = with_mask(stack, roi, rule, norm, um, level, comp)
    out = replace(roi, mask=keep, outline=_shape(roi).copy())
    out.channel = getattr(roi, "channel", int(rule.a))
    out.__dict__.pop("_contour_cache", None)
    return out


# ==========================================================================
#  IF: does the cell have real signal in channel B?
# ==========================================================================
def gate_snr(stack: np.ndarray, roi: Roi, rule: TrackRule, um: float,
             norm: Optional[GuideNorm] = None) -> float:
    """
    IF rule: signal-to-noise of channel B in the ROI = (mean of B inside the ROI's
    region - 25th percentile of B in a 3 um ring around it) / B's background
    pixel noise (manual._snr, the same test auto-detect uses with 5 as its bar).
    The noise is GuideNorm.noise[b] when given (identical to manual._plane_noise).
    NaN if the rule has no channel B.
    """
    C = stack.shape[0]
    b = int(rule.b)
    if not (0 <= b < C) or b == int(rule.a):
        return float("nan")
    noise = float(norm.noise[b]) if norm is not None else None
    return float(_snr(stack[b], roi, um, noise))


def helper_snr(stack: np.ndarray, roi: Roi, rule: TrackRule, um: float,
               norm: Optional[GuideNorm] = None) -> Dict[int, float]:
    """V3.0: {helper channel: signal-to-noise in the ROI} (the IF test, per helper)."""
    C = stack.shape[0]
    out: Dict[int, float] = {}
    for h in _helpers(rule, C):
        noise = float(norm.noise[h]) if norm is not None else None
        out[h] = float(_snr(stack[h], roi, um, noise))
    return out


# ==========================================================================
#  V3.0 helpers: the outline stays near the main channel's own outline
# ==========================================================================
def help_guard(reg: Roi, main_only: Optional[Roi], um: float) -> Roi:
    """The outline followed on the helper image, kept within HELP_GUARD_UM of the
    outline the main channel alone draws (main_only, same frame): pixels further
    out are removed. If nothing would be left, the main-only outline is used."""
    if main_only is None or reg is None:
        return reg
    from dataclasses import replace as _rep
    grow = int(max(1, np.ceil(HELP_GUARD_UM / max(um, 1e-6))))
    y0, x0, y1, x1 = reg.bbox
    my0, mx0, my1, mx1 = main_only.bbox
    oy, ox = my0 - grow, mx0 - grow
    big = np.zeros((my1 - my0 + 2 * grow, mx1 - mx0 + 2 * grow), bool)
    big[grow:grow + main_only.mask.shape[0], grow:grow + main_only.mask.shape[1]] = main_only.mask
    big = ndi.binary_dilation(big, structure=ndi.generate_binary_structure(2, 1),
                              iterations=grow)
    guard = np.zeros(reg.mask.shape, bool)
    a0, b0 = max(y0, oy), max(x0, ox)
    a1, b1 = min(y1, oy + big.shape[0]), min(x1, ox + big.shape[1])
    if a0 < a1 and b0 < b1:
        guard[a0 - y0:a1 - y0, b0 - x0:b1 - x0] = big[a0 - oy:a1 - oy, b0 - ox:b1 - ox]
    keep = reg.mask & guard
    if not keep.any():
        return main_only
    if keep.sum() == reg.mask.sum():
        return reg
    out = _rep(reg, mask=keep)
    if getattr(reg, "fit_level", None) is not None:
        out.fit_level = reg.fit_level
    return out
