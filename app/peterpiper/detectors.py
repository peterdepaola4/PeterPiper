"""
V3.0 trained auto-detect: a named detector learned from your own hand-analysed
runs (e.g. 'Autodetect - Nuclear GFP plus Cy5 (my sensor)'), so AUTO-DETECT picks
the cells you would pick instead of every nucleus-sized blob.

How it works (all numbers are written into the detector file and the Methods):

1  Candidates. On the frame you drew on, every nucleus-sized blob is outlined
   exactly as AUTO-DETECT does (manual.nucleus_candidates) on three images: the
   helper image (main channel + 0.5 x each helper, rules.guide_plane), the main
   channel and each helper channel; a blob already outlined on an earlier image
   (overlap > 50 %) is not added again.
2  What each candidate is judged on: its area (um2), circularity (4 pi A / P^2)
   and, for the main channel and every helper, its signal-to-noise (the mean
   inside minus the 25th percentile of a 3 um ring around it, divided by that
   channel's background pixel noise - the test the IF rule used) and its
   relative brightness (that signal-to-noise divided by the 95th percentile of
   all candidates of the movie: 1 = as bright as the brightest blobs of this
   movie, so a dish that is brighter or dimmer overall is judged the same way).
3  Your answers. A candidate counts as 'yours' when it is the best match (overlap
   = intersection / union >= 0.3) of one of the nucleus ROIs you saved; every
   ROI you saved counts, so a cell the finder never outlines counts as missed.
4  The rule. Minimum signal-to-noise and relative brightness per channel, an area
   range and a minimum circularity, chosen from fixed grids by coordinate search
   so that the mean F1 over your movies (F1 = 2 x right / (picked + yours)) is as
   high as possible.
5  Honest score. The same search is repeated leaving each movie out and the rule
   is scored on the movie it did not see (held-out) - that is the number shown.
6  Quiz. The candidates closest to the rule's limits are shown to you (keep /
   skip / not sure); your answers replace the match for those blobs and the rule
   is searched again.

A detector is a .json file in your profile ('Auto-detect' folder); it is applied
only to movies that have the same channel names.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import __version__
from . import manual
from . import rules as RL
from .segment import Roi

KIND = "PeterPiper trained auto-detect"
LEGACY_KINDS = ("PD4nav trained auto-detect",)      # made by PD4nav V3.0: still read
MATCH_IOU = 0.3            # a candidate is 'yours' at this overlap with your ROI
DEDUP_IOU = 0.5            # a blob found again on another image is not added twice
REL_PCT = 95.0             # relative brightness: SNR / this percentile of the movie's
# the values the search may choose from (fixed, so a detector is reproducible)
GRID_SNR = [0.0] + [float(v) for v in np.round(np.geomspace(1.0, 300.0, 30), 2)]
GRID_REL = [float(v) for v in np.round(np.linspace(0.0, 1.2, 25), 2)]
GRID_AMIN = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 70.0, 100.0]
GRID_AMAX = [200.0, 300.0, 450.0, 600.0, 800.0, 1000.0, 3000.0]
GRID_CIRC = [0.0, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75]
ProgressFn = Optional[Callable[[float, str], bool]]


# ======================================================================
#  The detector
# ======================================================================
@dataclass
class Detector:
    name: str
    main: str                                   # main channel name
    helpers: List[str] = field(default_factory=list)
    comp: str = "nucleus"
    limits: dict = field(default_factory=dict)  # area_min/max, circ_min, snr{}, rel{}
    trained_on: List[dict] = field(default_factory=list)   # per movie (all-data rule)
    held_out: List[dict] = field(default_factory=list)     # per movie (left out)
    quiz: List[dict] = field(default_factory=list)         # your keep / skip answers
    created: str = ""
    version: str = __version__

    # ---------------------------------------------------------------- words
    def channels(self) -> List[str]:
        return [self.main] + [h for h in self.helpers if h != self.main]

    def fits(self, channels: Sequence[str]) -> bool:
        """True if a movie with these channel names has every channel it needs."""
        have = {str(c) for c in channels}
        return all(c in have for c in self.channels())

    def rule_text(self) -> str:
        """The learned rule in plain words (read-only in the window; in the Methods)."""
        L = self.limits or {}
        parts = []
        for c in self.channels():
            s = float((L.get("snr") or {}).get(c, 0.0))
            r = float((L.get("rel") or {}).get(c, 0.0))
            bits = []
            if s > 0:
                bits.append(f"at least {s:g} x its noise")
            if r > 0:
                bits.append(f"at least {r:.0%} as bright as the brightest blobs of the movie")
            parts.append(f"{c}: " + (" and ".join(bits) if bits else "any"))
        amin, amax = float(L.get("area_min", 0.0)), float(L.get("area_max", 3000.0))
        shape = f"{amin:g} - {amax:g} um2"
        ci = float(L.get("circ_min", 0.0))
        if ci > 0:
            shape += f", circularity at least {ci:g}"
        return "Keeps nucleus-sized blobs with " + "; ".join(parts) + f"; {shape}."

    def score_text(self) -> str:
        """'On a movie it had not seen: 41 of 60 of your cells, 18 extra (F1 0.66)'."""
        if not self.held_out:
            return "Not scored on a movie it had not seen (train on 2 or more movies)."
        right = sum(int(m["right"]) for m in self.held_out)
        yours = sum(int(m["yours"]) for m in self.held_out)
        extra = sum(int(m["extra"]) for m in self.held_out)
        f1 = float(np.mean([m["f1"] for m in self.held_out]))
        return (f"On movies it had not seen: {right} of your {yours} cells found, {extra} "
                f"extra (mean F1 {f1:.2f}; 1 = exactly your picks).")

    def methods_text(self) -> str:
        movies = len(self.trained_on)
        return (f"Nuclei were proposed with the trained auto-detect '{self.name}' (PeterPiper "
                f"{self.version}, trained on {movies} hand-analysed movie(s), main channel "
                f"{self.main}" + (f", helper(s) {', '.join(self.helpers)}" if self.helpers else "")
                + f"). {self.rule_text()} {self.score_text()} Candidate blobs were outlined "
                f"as by AUTO-DETECT; signal-to-noise = (ROI mean - 25th percentile of a 3 um "
                f"ring) / background pixel noise; relative brightness = signal-to-noise / "
                f"the {REL_PCT:g}th percentile of all candidates of the movie.")

    # ---------------------------------------------------------------- file
    def to_dict(self) -> dict:
        return dict(kind=KIND, name=self.name, comp=self.comp, main=self.main,
                    helpers=list(self.helpers), limits=self.limits,
                    trained_on=self.trained_on, held_out=self.held_out, quiz=self.quiz,
                    created=self.created, version=self.version)

    @staticmethod
    def from_dict(d: dict) -> Optional["Detector"]:
        if not isinstance(d, dict) or d.get("kind") not in (KIND,) + LEGACY_KINDS \
                or not d.get("main"):
            return None
        return Detector(name=str(d.get("name") or "Auto-detect"), main=str(d["main"]),
                        helpers=[str(h) for h in d.get("helpers") or []],
                        comp=str(d.get("comp") or "nucleus"), limits=dict(d.get("limits") or {}),
                        trained_on=list(d.get("trained_on") or []),
                        held_out=list(d.get("held_out") or []), quiz=list(d.get("quiz") or []),
                        created=str(d.get("created") or ""), version=str(d.get("version") or ""))


def folder() -> Path:
    """<your profile>/Auto-detect - one .json per trained detector."""
    from .config import _settings_file
    d = _settings_file().parent / "Auto-detect"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in " -_.()+" else "-" for ch in str(name)).strip()
    return keep[:80] or "Auto-detect"


def save(det: Detector, overwrite: bool = False) -> Path:
    """Write the detector into the profile; never replaces another detector unless
    overwrite (the same name trained again)."""
    if not det.created:
        det.created = _dt.datetime.now().isoformat(timespec="seconds")
    p = folder() / f"{safe_name(det.name)}.json"
    if p.exists() and not overwrite:
        raise FileExistsError(str(p))
    p.write_text(json.dumps(det.to_dict(), indent=1), encoding="utf-8")
    return p


def listing(channels: Optional[Sequence[str]] = None) -> List[Detector]:
    """Your detectors (only those that fit these channel names, if given), by name."""
    out = []
    for p in sorted(folder().glob("*.json")):
        try:
            d = Detector.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            d = None
        if d is not None and (channels is None or d.fits(channels)):
            out.append(d)
    return sorted(out, key=lambda d: d.name.lower())


def delete(name: str) -> bool:
    p = folder() / f"{safe_name(name)}.json"
    if p.exists():
        p.unlink()
        return True
    return False


# ======================================================================
#  Candidates and what they are judged on
# ======================================================================
def _iou(a: Roi, b: Roi) -> float:
    ay0, ax0, ay1, ax1 = a.bbox
    by0, bx0, by1, bx1 = b.bbox
    y0, x0, y1, x1 = max(ay0, by0), max(ax0, bx0), min(ay1, by1), min(ax1, bx1)
    if y0 >= y1 or x0 >= x1:
        return 0.0
    ma = a.mask[y0 - ay0:y1 - ay0, x0 - ax0:x1 - ax0]
    mb = b.mask[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]
    inter = float((ma & mb).sum())
    return inter / max(1.0, float(a.mask.sum() + b.mask.sum()) - inter)


def _circ(m: np.ndarray) -> float:
    from skimage.measure import perimeter
    p = perimeter(np.pad(m, 1))
    return float(4 * np.pi * m.sum() / max(p * p, 1e-6))


def candidates(stack: np.ndarray, channels: Sequence[str], main: str,
               helpers: Sequence[str], um: float, progress: ProgressFn = None) -> dict:
    """{"rois": [Roi], "feat": {name: array}} for every candidate blob of this frame
    (stack: C x H x W raw counts). Features: area, circ, snr_<ch>, rel_<ch>."""
    names = [str(c) for c in channels]
    a = names.index(main)
    hs = [names.index(h) for h in helpers if h in names and h != main]
    rule = RL.TrackRule("nucleus", a, RL.HELP, -1, tuple(hs)) if hs else RL.TrackRule("nucleus", a)
    norm = RL.make_norm(stack)
    planes = ([("helper image", RL.guide_plane(stack, rule, norm))] if hs else []) + \
        [(names[a], stack[a])] + [(names[h], stack[h]) for h in hs]
    rois: List[Roi] = []
    for i, (label, pl) in enumerate(planes):
        def tick(f, m, i=i):
            if progress and not progress((i + f) / len(planes), f"Blobs on {label}: {m}"):
                raise manual.Cancelled()
        for c in manual.nucleus_candidates(pl, um, tick=tick):
            r = c["roi"]
            if any(_iou(r, o) > DEDUP_IOU for o in rois):
                continue
            rois.append(r)
    feat: Dict[str, np.ndarray] = {
        "area": np.array([r.area * um * um for r in rois], float),
        "circ": np.array([_circ(r.mask) for r in rois], float)}
    for c in [a] + hs:
        noise = float(norm.noise[c])
        s = np.array([manual._snr(stack[c], r, um, noise) for r in rois], float)
        feat["snr_" + names[c]] = s
        top = float(np.percentile(s, REL_PCT)) if s.size else 1.0
        feat["rel_" + names[c]] = s / max(top, 1e-6)
    return {"rois": rois, "feat": feat}


def select(feat: Dict[str, np.ndarray], limits: dict, chans: Sequence[str]) -> np.ndarray:
    """Which candidates the rule keeps (boolean array)."""
    L = limits or {}
    n = len(feat["area"])
    k = np.ones(n, bool)
    k &= feat["area"] >= float(L.get("area_min", 0.0))
    k &= feat["area"] <= float(L.get("area_max", 1e9))
    k &= feat["circ"] >= float(L.get("circ_min", 0.0))
    for c in chans:
        k &= feat.get("snr_" + c, np.zeros(n)) >= float((L.get("snr") or {}).get(c, 0.0))
        k &= feat.get("rel_" + c, np.zeros(n)) >= float((L.get("rel") or {}).get(c, 0.0))
    return k


def detect(stack: np.ndarray, channels: Sequence[str], det: Detector, um: float,
           taken: Sequence[Roi] = (), progress: ProgressFn = None) -> List[Roi]:
    """The cells this detector picks on one frame (not overlapping `taken`)."""
    cand = candidates(stack, channels, det.main, det.helpers, um, progress)
    keep = select(cand["feat"], det.limits, det.channels())
    out = []
    for r, k in zip(cand["rois"], keep):
        if k and not any(_iou(r, t) > 0.2 for t in taken):
            r.source = "auto"
            out.append(r)
    return out


# ======================================================================
#  Training
# ======================================================================
@dataclass
class Movie:
    """One training movie: its candidates, which are yours, and where it came from."""
    name: str
    run: str
    seg: int
    n_yours: int
    rois: List[Roi]
    feat: Dict[str, np.ndarray]
    yours: np.ndarray                      # bool per candidate (best match of one of yours)
    use: np.ndarray                        # bool per candidate (False: 'not sure')
    frame: Optional[np.ndarray] = None     # C x H x W (for the pictures; may be dropped)
    hand: List[Roi] = field(default_factory=list)
    um: float = 1.0


def hand_nuclei(run_path) -> Tuple[List[Roi], int]:
    """(your nucleus ROIs at the drawn timepoint, that timepoint) of a saved run."""
    from . import roifile
    anchors, _bg, _hw, seg = roifile.load_roi_file(run_path)
    state, comps = roifile.load_roi_state(run_path)
    rois = [r for r in (comps.get("nucleus") or []) if r is not None and r.area]
    if not rois and (state is None or not state.get("comps")):
        rois = [r for r in anchors if r.area]            # older files: the anchors
    return rois, int(seg or 0)


def load_movie(run_path, nd2_path, main: str, helpers: Sequence[str],
               progress: ProgressFn = None, keep_frame: bool = True) -> Movie:
    """Read one training movie (the .nd2 frame you drew on, read-only)."""
    from .nd2io import open_source
    hand, seg = hand_nuclei(run_path)
    src = open_source(str(nd2_path))
    try:
        stack = np.asarray(src.frame(seg))
        channels = list(src.channels)
        um = float(src.um_per_px)
    finally:
        try:
            src.close()
        except Exception:                                          # noqa: BLE001
            pass
    return movie_from_frame(stack, channels, um, hand, main, helpers, name=Path(str(nd2_path)).name,
                            run=str(run_path), seg=seg, progress=progress,
                            keep_frame=keep_frame)


def movie_from_frame(stack: np.ndarray, channels: Sequence[str], um: float, hand: Sequence[Roi],
                     main: str, helpers: Sequence[str], name: str = "movie", run: str = "",
                     seg: int = 0, progress: ProgressFn = None, keep_frame: bool = True) -> Movie:
    """A training movie from one frame and your ROIs on it."""
    hand = list(hand)
    cand = candidates(stack, channels, main, helpers, um, progress)
    rois = cand["rois"]
    yours = np.zeros(len(rois), bool)
    for h in hand:                                   # one candidate per ROI of yours
        best, bi = 0.0, -1
        for i, r in enumerate(rois):
            v = _iou(h, r)
            if v > best:
                best, bi = v, i
        if bi >= 0 and best >= MATCH_IOU:
            yours[bi] = True
    return Movie(name=name, run=run, seg=seg, n_yours=len(hand),
                 rois=rois, feat=cand["feat"], yours=yours, use=np.ones(len(rois), bool),
                 frame=stack if keep_frame else None, hand=hand, um=um)


def score(m: Movie, keep: np.ndarray) -> dict:
    """right / extra / yours / picked / F1 of a selection on one movie."""
    k = keep & m.use
    right = int((k & m.yours).sum())
    extra = int((k & ~m.yours).sum())
    # every ROI you saved counts (missed if never outlined), minus the ones the quiz
    # turned into 'skip' / 'not sure', plus the blobs the quiz made yours
    matched = _hand_matched(m)
    yours = int(m.n_yours) - int((matched & ~(m.yours & m.use)).sum()) \
        + int((m.yours & m.use & ~matched).sum())
    picked = right + extra
    f1 = 2.0 * right / max(1, picked + yours)
    return dict(movie=m.name, picked=picked, right=right, extra=extra, yours=yours, f1=f1)


def _hand_matched(m: Movie) -> np.ndarray:
    """Candidates that are yours because of a saved ROI (not a quiz 'keep')."""
    return getattr(m, "_matched", m.yours)


def apply_quiz(movies: Sequence[Movie], answers: Sequence[dict]) -> None:
    """Your quiz answers: keep -> yours, skip -> not yours, not sure -> left out."""
    for m in movies:
        if not hasattr(m, "_matched"):
            m._matched = m.yours.copy()
    for a in answers:
        for m in movies:
            if m.name != a.get("movie"):
                continue
            i = _at(m, a.get("y"), a.get("x"))
            if i is None:
                continue
            if a.get("answer") == "keep":
                m.yours[i], m.use[i] = True, True
            elif a.get("answer") == "skip":
                m.yours[i], m.use[i] = False, True
            else:
                m.use[i] = False


def _at(m: Movie, y, x) -> Optional[int]:
    """The candidate whose outline holds pixel (y, x)."""
    try:
        y, x = int(y), int(x)
    except (TypeError, ValueError):
        return None
    for i, r in enumerate(m.rois):
        y0, x0, y1, x1 = r.bbox
        if y0 <= y < y1 and x0 <= x < x1 and r.mask[y - y0, x - x0]:
            return i
    return None


def fit(movies: Sequence[Movie], chans: Sequence[str], progress: ProgressFn = None,
        rounds: int = 6) -> dict:
    """The limits with the highest mean F1 over these movies (coordinate search over
    the fixed grids, starting from 'keep everything')."""
    L = dict(area_min=0.0, area_max=3000.0, circ_min=0.0,
             snr={c: 0.0 for c in chans}, rel={c: 0.0 for c in chans})
    if not movies:
        return L

    def obj(Lx):
        return float(np.mean([score(m, select(m.feat, Lx, chans))["f1"] for m in movies]))
    axes = [("area_min", None, GRID_AMIN), ("area_max", None, GRID_AMAX),
            ("circ_min", None, GRID_CIRC)]
    for c in chans:
        axes += [("snr", c, GRID_SNR), ("rel", c, GRID_REL)]
    best = obj(L)
    for rnd in range(rounds):
        moved = False
        for j, (key, c, grid) in enumerate(axes):
            if progress and not progress((rnd + j / len(axes)) / rounds,
                                         f"Trying rules: round {rnd + 1}, mean F1 {best:.2f}"):
                raise manual.Cancelled()
            tries = []
            for v in grid:
                Lx = json.loads(json.dumps(L))
                if c is None:
                    Lx[key] = v
                else:
                    Lx[key][c] = v
                tries.append((obj(Lx), Lx))
            top = max(t[0] for t in tries)
            # a limit that makes no difference stays off (the loosest value); else, of
            # the equally good values, the middle one (as far from both edges of the
            # working range as the grid allows: safer on a new movie)
            loose = len(tries) - 1 if key == "area_max" else 0
            tied = [t for t in tries if t[0] >= top - 1e-9]
            pick = tries[loose] if tries[loose][0] >= top - 1e-9 else tied[(len(tied) - 1) // 2]
            if top > best + 1e-9:
                moved = True
            if top >= best - 1e-9:                     # the current value is on the grid
                best, L = top, pick[1]
        if not moved:
            break
    return L


def held_out(movies: Sequence[Movie], chans: Sequence[str],
             progress: ProgressFn = None) -> List[dict]:
    """Each movie scored with the rule learned from the OTHER movies."""
    out = []
    if len(movies) < 2:
        return out
    for i, m in enumerate(movies):
        def sub(f, msg, i=i):
            return progress((i + f) / len(movies), f"Movie {i + 1} of {len(movies)} left "
                                                   f"out - {msg}") if progress else True
        L = fit([x for j, x in enumerate(movies) if j != i], chans, sub)
        out.append(score(m, select(m.feat, L, chans)))
    return out


def uncertain(movies: Sequence[Movie], limits: dict, chans: Sequence[str],
              n: int = 12, asked: Sequence[dict] = ()) -> List[Tuple[int, int]]:
    """(movie index, candidate index) of the blobs nearest the rule's limits - half
    just kept, half just left out - for the quiz (never one already asked)."""
    done = {(a.get("movie"), _at_key(a)) for a in asked}
    near_in, near_out = [], []
    for mi, m in enumerate(movies):
        keep = select(m.feat, limits, chans)
        for ci in range(len(m.rois)):
            if not m.use[ci]:
                continue
            cy, cx = (int(v) for v in m.rois[ci].centroid)
            if (m.name, (cy, cx)) in done:
                continue
            d = _margin(m.feat, ci, limits, chans)
            (near_in if keep[ci] else near_out).append((abs(d), mi, ci))
    near_in.sort()
    near_out.sort()
    pick = [(mi, ci) for _, mi, ci in near_in[:n // 2]] + \
        [(mi, ci) for _, mi, ci in near_out[:n - min(n // 2, len(near_in))]]
    return pick[:n]


def _at_key(a: dict):
    try:
        return (int(a.get("y")), int(a.get("x")))
    except (TypeError, ValueError):
        return None


def _margin(feat: Dict[str, np.ndarray], i: int, limits: dict, chans: Sequence[str]) -> float:
    """How far candidate i is from the nearest limit, on a log / linear scale
    (small = the rule is unsure about it)."""
    L = limits or {}
    ds = []
    for c in chans:
        s, t = float(feat["snr_" + c][i]), float((L.get("snr") or {}).get(c, 0.0))
        if t > 0:
            ds.append(np.log10(max(s, 1e-3)) - np.log10(t))
        r, tr = float(feat["rel_" + c][i]), float((L.get("rel") or {}).get(c, 0.0))
        if tr > 0:
            ds.append((r - tr) * 2.0)
    a = float(feat["area"][i])
    if L.get("area_min", 0) > 0:
        ds.append(np.log10(max(a, 1e-3)) - np.log10(float(L["area_min"])))
    if L.get("area_max", 3000) < 3000:
        ds.append(np.log10(float(L["area_max"])) - np.log10(max(a, 1e-3)))
    if not ds:
        return 9.0
    neg = [d for d in ds if d < 0]
    return max(neg, key=abs) if neg else min(ds)


def crop(m: Movie, i: int, half_um: float = 15.0) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """(C x h x w crop of the training frame around candidate i, crop box)."""
    r = m.rois[i]
    cy, cx = (int(v) for v in r.centroid)
    h = int(max(16, half_um / max(m.um, 1e-6)))
    H, W = m.frame.shape[1:]
    y0, x0, y1, x1 = max(0, cy - h), max(0, cx - h), min(H, cy + h), min(W, cx + h)
    return m.frame[:, y0:y1, x0:x1], (y0, x0, y1, x1)
