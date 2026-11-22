"""
PeterPiper 4.0 graph builder - typed sentences <-> GraphSpec (offline, forgiving).

    "R/R0 nuclear Cy5/GFP vs cytoplasmic mCherry"
    "whole cell mCherry at T=30 vs F/F0 GFP binned by summed nuclear DAPI at T=0"
    "R/R0 nuclear Cy5/GFP vs cytoplasmic mCherry vs nuclear DAPI"   (3rd = colour)

Parts are joined by 'vs' (vs. / versus / against). The third part can also come
with 'coloured by' (colour) or 'binned by' / 'grouped by' / 'split by' (bins);
'in 4 bins' / 'in 3 equal-width bins' / 'terciles' / 'quartiles' / 'median split' /
'bins at 1e6, 2e6' choose the bins. 'in N bins' right after the X part (no third
part) bins X: mean Y per X bin.

A part: [measure] [compartment] channel(s) [time], in any order, e.g.
    measure      mean / average / intensity            -> mean intensity
                 summed / sum / total / integrated     -> summed total intensity
                 F/F0, R/R0, ratio, area, raw, x background (x bg, over background)
    compartment  nucleus / nuclear / nuc, cytoplasm / cytoplasmic / cyto, whole cell /
                 cell, mito; 'nuclear/cytoplasmic GFP' = their ratio per cell
    channels     the run's channel names (any case); 'Cy5/GFP' or 'Cy5 over GFP' for
                 ratios (A/B in that order); dye names (JF646, Alexa 488, Hoechst ...)
                 are read as the run's channel of that colour, with a note
    time         T=30 / t30 / at T=30   30 timepoints after the baseline (T=0 =
                                        the baseline, as on the graphs' time axis)
                 at 30 min              30 minutes after the baseline
                 frame 12               the movie's own frame 12
                 at baseline / at the end / max / min / mean over T=0..10 /
                 AUC over 0-30 min / slope over frames 2-9 / full trace
    'time' as the X part = against Time.
Options anywhere: per run / by condition / by group / pooled, SEM / SD / 95% CI,
log x / log y / log-log, spearman / pearson / no r, trajectories / points coloured
by time, no points / means only, all cells (also the excluded ones),
drift corrected frames 2-9 (the drift add-on).
Conditions: 'where <part> > 2e6 and <part> between 1 and 3 and condition = U2OS'.

parse() never raises: unknown words become Issues (start, end, word, message,
suggestions) for the box to underline; the spec is made from what was understood.
sentence(spec) writes the canonical sentence back (parse(sentence(s)) == s).
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .graphbuilder import (COMP_ADJ, COMPS, BinSpec, Filter, GraphSpec, Quantity,
                           range_text, t_text)

# ------------------------------------------------------------------ words
COMP_WORDS = {
    "nucleus": "nucleus", "nuclear": "nucleus", "nuc": "nucleus", "nuclei": "nucleus",
    "nucl": "nucleus", "nucleolar": "nucleus",
    "cytoplasm": "cytoplasm", "cytoplasmic": "cytoplasm", "cyto": "cytoplasm",
    "cyt": "cytoplasm", "cytosol": "cytoplasm", "cytosolic": "cytoplasm",
    "cytoplasmatic": "cytoplasm",
    "whole cell": "cell", "whole-cell": "cell", "wholecell": "cell", "cell": "cell",
    "cellular": "cell", "wc": "cell",
    "mito": "mito", "mitochondria": "mito", "mitochondrial": "mito", "mitochondrion": "mito",
}
MEASURE_WORDS = [  # longest first when matched
    ("summed total intensity", "total"), ("summed total", "total"),
    ("total summed intensity", "total"), ("summed intensity", "total"),
    ("total intensity", "total"), ("integrated intensity", "total"),
    ("integrated density", "total"), ("sum intensity", "total"), ("summed", "total"),
    ("total", "total"), ("sum", "total"), ("integrated", "total"), ("intden", "total"),
    ("mean intensity", "mean"), ("average intensity", "mean"), ("avg intensity", "mean"),
    ("intensity", "mean"), ("brightness", "mean"), ("signal", "mean"),
    ("mean", "mean"), ("average", "mean"), ("avg", "mean"),
    ("raw intensity", "raw"), ("raw mean", "raw"), ("raw", "raw"),
    ("r/r0", "rr0"), ("r / r0", "rr0"), ("rr0", "rr0"), ("r/ro", "rr0"),
    ("f/f0", "ff0"), ("f / f0", "ff0"), ("ff0", "ff0"), ("f/fo", "ff0"),
    ("fold change", "ff0"),
    ("ratio", "ratio"),
    ("area", "area"), ("size", "area"),
    ("x background", "xbg"), ("× background", "xbg"), ("times background", "xbg"),
    ("over background", "xbg"), ("above background", "xbg"), ("fold background", "xbg"),
    ("x bg", "xbg"), ("xbg", "xbg"), ("signal to background", "xbg"),
    ("signal/background", "xbg"), ("s/b", "xbg"),
]
MEASURE_CANON = {"mean": "intensity", "total": "summed", "ff0": "F/F0", "rr0": "R/R0",
                 "ratio": "ratio", "raw": "raw intensity", "area": "area",
                 "xbg": "x background"}
FILLER = {"of", "the", "in", "a", "an", "per", "cell's", "cells", "channel", "channels",
          "for", "its", "their", "plot", "show", "graph", "me", "and", "to", "value",
          "values", "level", "levels", "intensities", "by", "on", "from", "with", "each"}
# dye / filter names -> words a channel name may contain (the run's channel of that colour)
DYES = [
    (("jf646", "jf 646", "jf-646", "alexa647", "alexa 647", "af647", "a647", "atto647", "sir",
      "far red", "farred", "647", "640", "cy5.5", "irfp", "draq5", "mitotracker deep red"),
     ("cy5", "far", "647", "640", "jf646", "a647")),
    (("rfp", "mcherry", "tagrfp", "mscarlet", "mruby", "tdtomato", "dsred", "texas red",
      "alexa594", "alexa 594", "a594", "594", "561", "568", "jf549", "jf 549", "tmrm", "cy3",
      "red"), ("mcherry", "rfp", "red", "594", "561", "cy3", "tritc")),
    (("gfp", "egfp", "fitc", "alexa488", "alexa 488", "a488", "488", "mneongreen", "neon",
      "yfp", "venus", "citrine", "fluo4", "gcamp", "green"),
     ("gfp", "fitc", "488", "green", "yfp")),
    (("dapi", "hoechst", "bfp", "405", "nuclear stain", "blue", "draq", "sytox blue"),
     ("dapi", "405", "blue", "hoechst", "bfp")),
]
TIME_X_WORDS = {"time", "t", "timepoint", "timepoints", "time (min)", "minutes", "frame",
                "frames", "time course", "over time"}
_NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?"
_SEP_VS = re.compile(r"\s+(?:vs\.?|versus|against|v\.?)\s+", re.I)
_Z_INTRO = re.compile(r"\s+(?:(?:binned|grouped|split|divided|sorted)\s+(?:up\s+)?(?:by|on)|"
                      r"(?:colou?red|shaded|colou?r|tinted)\s+by|in\s+bins\s+of)\s+", re.I)
_WHERE = re.compile(r"\s+(?:where|if|only\s+cells?\s+(?:with|where)|for\s+cells?\s+with|"
                    r"when|cells?\s+with)\s+", re.I)


@dataclass
class Issue:
    start: int
    end: int
    word: str
    message: str
    suggestions: List[str] = field(default_factory=list)
    level: str = "error"               # 'error' (not understood) | 'note' (read as ...)


@dataclass
class Parsed:
    spec: Optional[GraphSpec]
    issues: List[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.spec is not None and not any(i.level == "error" for i in self.issues)

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "error"]


# -------------------------------------------------------------- helpers
def _fnum(s: str) -> float:
    s = s.strip().lower().replace(",", "").replace("×", "x")
    m = re.fullmatch(r"(" + _NUM + r")\s*x\s*10\^?\s*([-+]?\d+)", s)
    if m:
        return float(m.group(1)) * 10 ** int(m.group(2))
    mult = 1.0
    for w, f in (("million", 1e6), ("thousand", 1e3), ("k", 1e3), ("m", 1e6)):
        if s.endswith(w) and re.fullmatch(_NUM, s[:-len(w)].strip() or "x"):
            s, mult = s[:-len(w)].strip(), f
            break
    return float(s) * mult


class _Text:
    """A part of the sentence with its offset, and which characters are used up."""

    def __init__(self, text: str, offset: int) -> None:
        self.text, self.off = text, offset
        self.low = text.lower()
        self.used = [False] * len(text)

    def take(self, a: int, b: int) -> None:
        for i in range(a, b):
            self.used[i] = True

    def free(self, a: int, b: int) -> bool:
        return not any(self.used[a:b])

    def find(self, pattern: str, flags=re.I):
        for m in re.finditer(pattern, self.text, flags):
            if self.free(m.start(), m.end()):
                yield m

    def leftovers(self) -> List[Tuple[int, int, str]]:
        out = []
        for m in re.finditer(r"[^\s,;]+", self.text):
            a, b = m.start(), m.end()
            if any(not self.used[i] for i in range(a, b)):
                w = "".join(ch for i, ch in enumerate(self.text[a:b]) if not self.used[a + i])
                w = w.strip(".()[]'\"-:")
                if w:
                    out.append((self.off + a, self.off + b, w))
        return out


def _wb(word: str) -> str:
    """Regex for a word / phrase with word-ish boundaries."""
    return r"(?<![\w/])" + re.escape(word).replace(r"\ ", r"\s+") + r"(?![\w])"


def dye_channel(word: str, channels: Sequence[str]) -> Optional[str]:
    """The run's channel that a dye / filter name means (JF646 -> Cy5), or None."""
    w = word.lower().replace("-", "").replace(" ", "")
    for dyes, keys in DYES:
        if any(w == d.replace(" ", "").replace("-", "") for d in dyes):
            for ch in channels:
                cl = ch.lower()
                if any(k in cl for k in keys) or any(d.replace(" ", "") in cl for d in dyes):
                    return ch
    return None


def suggest(word: str, channels: Sequence[str], extra: Sequence[str] = ()) -> List[str]:
    vocab = list(channels) + list(COMP_WORDS) + [w for w, _ in MEASURE_WORDS] + list(extra) + \
        ["vs", "binned by", "coloured by", "at T=0", "where", "time", "max", "min", "mean",
         "slope", "auc", "baseline"]
    low = {v.lower(): v for v in vocab}
    got = difflib.get_close_matches(word.lower(), list(low), n=4, cutoff=0.6)
    out = [low[g] for g in got]
    d = dye_channel(word, channels)
    if d and d not in out:
        out.insert(0, d)
    return out


# ------------------------------------------------------------ one part
def _parse_time(T: _Text, q: dict, issues: List[Issue]) -> None:
    """Time phrases -> q['time'], 't1', 't2', 'unit'."""
    unitw = r"(?:min(?:ute)?s?|m)\b"
    rng = (r"(?:(?:from|over|between|during|in)\s+)?(?:t\s*=?\s*)?(" + _NUM + r")\s*(" + unitw +
           r")?\s*(?:-|–|to|\.\.|and|until)\s*(?:t\s*=?\s*)?(" + _NUM + r")\s*(" + unitw + r")?")
    frng = r"(?:from\s+|over\s+|between\s+)?frames?\s*(\d+)\s*(?:-|–|to|\.\.|and)\s*(\d+)"
    red = (r"(mean|average|avg|max(?:imum)?|peak|min(?:imum)?(?!\s*\d)|auc|area\s+under\s+"
           r"(?:the\s+)?curve|integral|slope|rate)")
    words = {"mean": "mean", "average": "mean", "avg": "mean", "max": "max", "maximum": "max",
             "peak": "max", "min": "min", "minimum": "min", "auc": "auc", "integral": "auc",
             "slope": "slope", "rate": "slope"}

    def red_key(s: str) -> str:
        s = s.lower()
        return "auc" if s.startswith("area") else words.get(s, "mean")
    # a window: 'over frames 2-9', 'over T=0..10', 'from 0 to 20 min', 'mean T=0..10' -
    # and the reduction word next to it ('mean over ...') or anywhere in the part
    # ('AUC of F/F0 GFP over 0-20 min'); a window without one = the mean over it
    win = None
    for m in T.find(frng):
        win = (m, float(m.group(1)), float(m.group(2)), "frame")
        break
    if win is None:
        for m in T.find(r"(?:(?:from|over|between|during)\s+|(?<=\s)|^)" + rng[len(
                r"(?:(?:from|over|between|during|in)\s+)?"):]):
            pre = T.text[:m.start()]
            word_before = re.search(red + r"\s*(?:of\s+)?$", pre, re.I)
            has_lead = re.match(r"(?:from|over|between|during)\s", m.group(0), re.I)
            if not (has_lead or word_before or re.match(r"\s*t\s*=", m.group(0), re.I)):
                continue
            unit = "min" if (m.group(2) or m.group(4)) else "tp"
            win = (m, float(m.group(1)), float(m.group(3)), unit)
            break
    if win is not None:
        m, a, b, unit = win
        T.take(m.start(), m.end())
        key = "mean"
        mb = re.search(red + r"\s*(?:of\s+)?$", T.text[:m.start()], re.I)
        if mb and T.free(mb.start(1), mb.end(1)):
            key = red_key(mb.group(1))
            T.take(mb.start(1), mb.end(1))
        else:
            other = (r"\b(max(?:imum)?|peak|min(?:imum)?(?!\s*\d)|auc|area\s+under\s+"
                     r"(?:the\s+)?curve|integral|slope|rate)\b")
            for mo in T.find(other):
                key = red_key(mo.group(1))
                T.take(mo.start(), mo.end())
                break
        q.update(time=key, t1=a, t2=b, unit=unit)
        return
    for m in T.find(red + r"\s+(?:over\s+)?(?:time|the\s+movie|the\s+whole\s+movie|"
                    r"all\s+times?)\b"):
        q.update(time=red_key(m.group(1)), t1=None, t2=None, unit="tp")
        T.take(m.start(), m.end())
        return
    # single times
    pats = [
        (r"(?:at\s+)?(?:the\s+)?baseline\b|\bat\s+t\s*=?\s*0\b(?!\.\d)", lambda m: (0.0, "tp")),
        (r"(?:at\s+)?(?:the\s+)?(?:end|last(?:\s+time\s*point)?|final(?:\s+time\s*point)?)\b",
         None),
        (r"(?:at\s+)?(?:the\s+)?(?:start|first\s+time\s*point|beginning)\b",
         lambda m: (1.0, "frame")),
        (r"(?:at\s+)?(?:t\s*=?\s*)?(" + _NUM + r")\s*" + unitw,
         lambda m: (float(m.group(1)), "min")),
        (r"(?:at\s+)?(?:frame|time\s*point|tp)\s*#?\s*(\d+)", lambda m: (float(m.group(1)),
                                                                         "frame")),
        (r"(?:at\s+)?\bt\s*=?\s*(" + _NUM + r")\b", lambda m: (float(m.group(1)), "tp")),
        (r"\bat\s+(" + _NUM + r")\b", lambda m: (float(m.group(1)), "tp")),
    ]
    for pat, fn in pats:
        for m in T.find(pat):
            T.take(m.start(), m.end())
            if fn is None:
                q.update(time="end", t1=None, t2=None, unit="tp")
            else:
                v, u = fn(m)
                q.update(time="at", t1=v, t2=None, unit=u)
            return
    bare = (r"\b(max(?:imum)?|peak|min(?:imum)?|auc|area\s+under\s+(?:the\s+)?curve|integral|"
            r"slope)\b")
    for m in T.find(bare):
        T.take(m.start(), m.end())
        q.update(time=red_key(m.group(1)), t1=None, t2=None, unit="tp")
        return
    for m in T.find(r"\b(?:full\s+trace|trace|over\s+time|time\s+course|every\s+timepoint)\b"):
        T.take(m.start(), m.end())
        q.update(time="trace", t1=None, t2=None, unit="tp")
        return


def parse_quantity(text: str, offset: int, channels: Sequence[str], comps: Sequence[str],
                   issues: List[Issue], role: str = "Y") -> Optional[Quantity]:
    """One part ('R/R0 nuclear Cy5/GFP at T=30') -> Quantity; problems -> issues."""
    T = _Text(text, offset)
    q = dict(time="trace", t1=None, t2=None, unit="tp")
    _parse_time(T, q, issues)
    # compartment ratio 'nuclear/cytoplasmic', 'nuc/cyto', 'n/c'
    comp = comp2 = None
    cw = sorted(COMP_WORDS, key=len, reverse=True)
    alt = "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in cw)
    for m in T.find(r"(?<![\w/])(" + alt + r")\s*(?:/|÷|\bto\b|\bover\b)\s*(" + alt +
                    r")(?![\w])"):
        a, b = COMP_WORDS[m.group(1).lower()], COMP_WORDS[m.group(2).lower()]
        if a != b:
            comp, comp2 = a, b
            T.take(m.start(), m.end())
            break
    for m in T.find(r"(?<![\w/])n\s*/\s*c(?![\w])"):
        comp, comp2 = "nucleus", "cytoplasm"
        T.take(m.start(), m.end())
    # measure
    measure = None
    for w, key in MEASURE_WORDS:
        for m in T.find(_wb(w)):
            if measure is None or measure == "mean":       # 'F/F0 GFP intensity' = F/F0
                measure = key if (measure is None or key != "mean") else measure
            T.take(m.start(), m.end())
            break
    if any(T.find(r"\bdelta\b|\bΔ\b|\bdf/f\b|\bdr/r\b")):
        for m in T.find(r"\bdelta\b|\bΔ\b|\bdf/f\b|\bdr/r\b"):
            issues.append(Issue(offset + m.start(), offset + m.end(), m.group(0),
                                "ΔF/F0 is F/F0 - 1: plotted as F/F0 (or R/R0).", ["F/F0"],
                                "note"))
            T.take(m.start(), m.end())
            measure = measure or "ff0"
    # channels: the run's names (longest first), 'A/B', 'A over B', dyes
    chans: List[Tuple[int, str]] = []
    for ch in sorted(channels, key=len, reverse=True):
        for m in T.find(r"(?<![\w])" + re.escape(ch) + r"(?![\w])"):
            chans.append((m.start(), ch))
            T.take(m.start(), m.end())
    for a, b, w in T.leftovers():
        d = dye_channel(w, channels)
        if d:
            chans.append((a - offset, d))
            T.take(a - offset, b - offset)
            issues.append(Issue(a, b, w, f"'{w}' read as the {d} channel.", [d], "note"))
    chans.sort()
    names = [c for _p, c in chans]
    # compartment words (after channels: a channel may hold such a word)
    if comp is None:
        for w in cw:
            for m in T.find(_wb(w)):
                comp = COMP_WORDS[w]
                T.take(m.start(), m.end())
                break
            if comp:
                break
    for m in T.find(r"/|÷|\bover\b|\bto\b"):
        T.take(m.start(), m.end())             # 'Cy5/GFP', 'Cy5 over GFP'
    for m in T.find(r"(?<![\w])(?:" + "|".join(re.escape(f) for f in FILLER) + r")(?![\w])"):
        T.take(m.start(), m.end())
    for a, b, w in T.leftovers():
        if role == "Z" and w.lower() in ("bins",):
            continue
        sug = suggest(w, channels)
        msg = f"'{w}' is not understood."
        if not names and not sug:
            sug = list(channels)
            msg = f"'{w}' is not a channel of this run."
        elif sug:
            msg += " Did you mean " + " or ".join(sug[:3]) + "?"
        issues.append(Issue(a, b, w, msg, sug))
    # defaults and checks
    if comp is None:
        comp = next((c for c in ("nucleus", "cell", "cytoplasm", "mito") if c in comps),
                    comps[0] if comps else "nucleus")
    if measure is None:
        measure = "ratio" if len(names) >= 2 else ("mean" if names else None)
    if measure is None:
        if not any(offset <= i.start < offset + len(text) and i.level == "error"
                   for i in issues):
            issues.append(Issue(offset, offset + len(text), text.strip() or role,
                                f"{role}: which channel? ({', '.join(channels)})",
                                list(channels)))
        return None
    if measure == "area":
        names = []
    elif measure in ("rr0", "ratio"):
        if len(names) < 2:
            issues.append(Issue(offset, offset + len(text), text.strip(),
                                f"{'R/R0' if measure == 'rr0' else 'A ratio'} needs two channels, "
                                f"e.g. {'/'.join(channels[:2])}.", []))
            if not names:
                return None
            names = names + [c for c in channels if c != names[0]][:1]
        names = names[:2]
    else:
        if len(names) >= 2:
            newm = "rr0" if measure == "ff0" else "ratio"
            issues.append(Issue(offset, offset + len(text), text.strip(),
                                f"Two channels: read as {'R/R0' if newm == 'rr0' else 'the ratio'} "
                                f"{names[0]}/{names[1]}.", [], "note"))
            measure, names = newm, names[:2]
        if not names:
            if not any(offset <= i.start < offset + len(text) and i.level == "error"
                       for i in issues):
                issues.append(Issue(offset, offset + len(text), text.strip() or role,
                                    f"{role}: which channel? ({', '.join(channels)})",
                                    list(channels)))
            return None
    if comps and comp not in comps:
        issues.append(Issue(offset, offset + len(text), text.strip(),
                            f"This run has no {COMP_ADJ.get(comp, comp)} ROIs (it has "
                            f"{', '.join(COMP_ADJ.get(c, c) for c in comps)}).",
                            [COMP_ADJ.get(c, c) for c in comps]))
    return Quantity(comp=comp, chan="/".join(names), measure=measure, time=q["time"],
                    t1=q["t1"], t2=q["t2"], unit=q["unit"], comp2=comp2 or "")


# ------------------------------------------------------------ options
_OPTIONS = [
    (r"\b(?:per|by|each|split\s+by|colou?r(?:ed)?\s+by)\s+runs?\b|\bper\s+movie\b",
     {"split": "run"}),
    (r"\b(?:per|by|split\s+by|colou?r(?:ed)?\s+by)\s+(?:conditions?|cell\s+lines?)\b",
     {"split": "condition"}),
    (r"\b(?:per|by|split\s+by|colou?r(?:ed)?\s+by)\s+groups?\b", {"split": "group"}),
    (r"\bpool(?:ed)?\b|\ball\s+runs\s+together\b", {"split": "pool"}),
    (r"\b95\s*%?\s*ci\b|\bconfidence\s+interval\b", {"error": "95% CI"}),
    (r"\bsem\b|\bstandard\s+error\b", {"error": "SEM"}),
    (r"\bsd\b|\bstandard\s+deviation\b", {"error": "SD"}),
    (r"\bno\s+error(?:\s+bars)?\b", {"error": "none"}),
    (r"\blog[\s-]*log\b|\blog\s+both\b|\bboth\s+log\b", {"log_x": True, "log_y": True}),
    (r"\blog\s*x\b|\bx\s+log\b|\blog\s+x[\s-]*axis\b", {"log_x": True}),
    (r"\blog\s*y\b|\by\s+log\b|\blog\s+y[\s-]*axis\b", {"log_y": True}),
    (r"\bspearman\b", {"corr": "spearman"}),
    (r"\bpearson\b", {"corr": "pearson"}),
    (r"\bno\s+(?:r|correlation)\b", {"corr": "none"}),
    (r"\btrajector(?:y|ies)\b|\bper[\s-]+cell\s+lines\b", {"pairs": "trajectories"}),
    (r"\bpoints?\s+colou?red\s+by\s+time\b|\bcolou?red\s+by\s+time\b", {"pairs": "points"}),
    (r"\bno\s+(?:cell\s+)?points\b|\bmeans?\s+only\b|\bwithout\s+(?:cells|points)\b|"
     r"\bno\s+cells\b", {"show_cells": False}),
    (r"\bno\s+means?\b|\bcells\s+only\b", {"show_mean": False}),
    (r"\ball\s+cells\b|\bexcluded\s+(?:cells\s+)?too\b|\bincluding\s+excluded\b",
     {"included_only": False}),
    (r"\bincluded(?:\s+cells)?\s+only\b|\bonly\s+included(?:\s+cells)?\b", {"included_only": True}),
]
_DRIFT = re.compile(r"\b(?:drift[\s-]*correct(?:ed|ion)?|corrected\s+for\s+drift)"
                    r"(?:\s*(?:over|through|from|,)?\s*(?:frames?|t)?\s*(\d+)\s*(?:-|–|to|\.\.)"
                    r"\s*(?:t)?(\d+))?", re.I)
_BINS = [
    (r"\bmedian\s+split\b|\bhalves\b|\bin\s+(?:two|2)\s+halves\b", ("count", 2)),
    (r"\bterciles?\b|\btertiles?\b", ("count", 3)),
    (r"\bquartiles?\b", ("count", 4)),
    (r"\bquintiles?\b", ("count", 5)),
    (r"\bdeciles?\b", ("count", 10)),
]
_NBINS = re.compile(r"\b(?:in(?:to)?\s+)?(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+"
                    r"(equal[\s-]*(?:count|number|size|n|sized)|equal[\s-]*width|even(?:ly\s+"
                    r"spaced)?|quantile|same[\s-]*(?:count|size|width))?\s*bins?\b"
                    r"(?:\s+(?:of\s+)?(equal[\s-]*(?:count|number|size|n|width)|"
                    r"the\s+same\s+(?:count|width|size)))?", re.I)
_CUTS = re.compile(r"\b(?:bins?\s+at|cut(?:\s*-?offs?)?\s+at|cut\s+at|split\s+at|thresholds?"
                   r"\s+(?:at\s+)?|cutoffs?\s+(?:at\s+)?)\s*((?:" + _NUM + r"\s*(?:,|and|;)?\s*)+)",
                   re.I)
_WORDNUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10}


def _bins_in(text: str) -> Tuple[Optional[BinSpec], List[Tuple[int, int]]]:
    """A bin choice in text and the spans it used."""
    spans, b = [], None
    m = _CUTS.search(text)
    if m:
        cuts = tuple(sorted(_fnum(v) for v in re.findall(_NUM, m.group(1), re.I)))
        b = BinSpec("custom", len(cuts) + 1, cuts)
        spans.append((m.start(), m.end()))
        return b, spans
    m = _NBINS.search(text)
    if m:
        n = _WORDNUM.get(m.group(1).lower()) or int(m.group(1))
        kind_w = (m.group(2) or m.group(3) or "").lower()
        kind = "width" if ("width" in kind_w or "even" in kind_w) else "count"
        b = BinSpec(kind, max(1, n))
        spans.append((m.start(), m.end()))
    for pat, (kind, n) in _BINS:
        mm = re.search(pat, text, re.I)
        if mm:
            b = BinSpec(kind, n)
            spans.append((mm.start(), mm.end()))
            break
    mm = re.search(r"\bequal[\s-]*width\b", text, re.I)
    if b is not None and mm and not any(a <= mm.start() < e for a, e in spans):
        b = BinSpec("width", b.n)
        spans.append((mm.start(), mm.end()))
    return b, spans


def _blank(text: str, spans) -> str:
    out = list(text)
    for a, b in spans:
        for i in range(a, b):
            out[i] = " "
    return "".join(out)


# ------------------------------------------------------------ filters
_OPS = [(r">=|≥|\bat\s+least\b|\bnot\s+below\b", ">="), (r"<=|≤|\bat\s+most\b|\bnot\s+above\b",
                                                          "<="),
        (r">|\babove\b|\bover\b|\bmore\s+than\b|\bhigher\s+than\b|\bgreater\s+than\b|"
         r"\bbrighter\s+than\b", ">"),
        (r"<|\bbelow\b|\bunder\b|\bless\s+than\b|\blower\s+than\b|\bdimmer\s+than\b", "<")]


def parse_filter(text: str, offset: int, channels: Sequence[str], comps: Sequence[str],
                 issues: List[Issue]) -> Optional[Filter]:
    """'nuclear DAPI summed at T=0 > 2e6' / 'GFP x background between 2 and 5' /
    'condition = U2OS' / 'run is dish 2' -> Filter."""
    t = text.strip()
    m = re.match(r"(condition|cell\s*line|run|movie|group)\s*(?:=|==|is|:)\s*(.+)$", t, re.I)
    if m:
        kind = {"cell line": "condition", "cellline": "condition", "movie": "run"}.get(
            re.sub(r"\s+", " ", m.group(1).lower()), m.group(1).lower())
        return Filter(kind=kind, text=m.group(2).strip().strip("'\""))
    m = re.search(r"\b(not\s+)?between\s+(" + _NUM + r"(?:\s*x\s*10\^?\d+)?)\s*(?:and|-|to)\s*(" +
                  _NUM + r"(?:\s*x\s*10\^?\d+)?)", text, re.I)
    if m:
        q = parse_quantity(text[:m.start()], offset, channels, comps, issues, "Condition")
        if q is None:
            return None
        return Filter(q=q, op="outside" if m.group(1) else "between", a=_fnum(m.group(2)),
                      b=_fnum(m.group(3)))
    best = None                      # the last comparison in the text (times come before it)
    for pat, op in _OPS:
        for m in re.finditer(r"(" + pat + r")\s*(" + _NUM + r"(?:\s*x\s*10\^?\s*[-+]?\d+)?"
                             r"(?:\s*(?:million|thousand|k|m)\b)?)\s*$", text, re.I):
            if best is None or m.start() > best[0].start():
                best = (m, op)
    if best is not None:
        m, op = best
        try:
            v = _fnum(m.group(2))
        except ValueError:
            v = None
        if v is not None:
            q = parse_quantity(text[:m.start()], offset, channels, comps, issues, "Condition")
            if q is None:
                return None
            return Filter(q=q, op=op, a=v)
    issues.append(Issue(offset, offset + len(text), t, f"Condition '{t}' needs a comparison, "
                        f"e.g. '> 2e6' or 'between 1 and 3'.", ["> 1000", "between 1 and 3"]))
    return None


# ------------------------------------------------------------ sentence
def parse(text: str, channels: Sequence[str], comps: Sequence[str] = COMPS,
          base: Optional[GraphSpec] = None) -> Parsed:
    """A typed sentence -> Parsed(spec, issues). base: the spec shown before (its
    bin settings are kept when the sentence says 'binned by' without saying how)."""
    issues: List[Issue] = []
    src = str(text or "")
    if not src.strip():
        return Parsed(None, [Issue(0, 0, "", "Type what to plot, e.g. "
                                   f"'F/F0 {channels[0] if channels else 'GFP'} vs time'.", [],
                                   "note")])
    channels = list(channels)
    comps = list(comps) or list(COMPS)
    opts: Dict[str, object] = {}
    spans = []
    for pat, upd in _OPTIONS:
        for m in re.finditer(pat, src, re.I):
            opts.update(upd)
            spans.append((m.start(), m.end()))
    m = _DRIFT.search(src)
    if m:
        a, b = (int(m.group(1)), int(m.group(2))) if m.group(1) else (2, 9)
        opts["drift"] = (min(a, b), max(a, b))
        spans.append((m.start(), m.end()))
    work = _blank(src, spans)
    # conditions
    filters: List[Filter] = []
    wm = _WHERE.search(work)
    if wm:
        ftxt = work[wm.end():]
        foff = wm.end()
        work = work[:wm.start()] + " " * (len(work) - wm.start())
        prot = re.sub(r"between\s+(\S+)\s+and\s+", lambda mm: mm.group(0).replace(" and ", " &&& "),
                      ftxt, flags=re.I)
        pos = 0
        for chunk in re.split(r"\s+and\s+|\s*;\s*|\s*,\s*(?=\S)", prot):
            i = prot.find(chunk, pos)
            pos = i + len(chunk)
            ch = chunk.replace(" &&& ", " and ")
            if ch.strip():
                f = parse_filter(ch, foff + i, channels, comps, issues)
                if f is not None:
                    filters.append(f)
    # parts: Y vs X [vs|binned by|coloured by Z]
    z_mode = None
    zm = _Z_INTRO.search(work)
    z_text, z_off = None, 0
    if zm:
        intro = zm.group(0).lower()
        z_mode = "colour" if ("colo" in intro or "shad" in intro or "tint" in intro) else "bins"
        z_text, z_off = work[zm.end():], zm.end()
        work = work[:zm.start()] + " " * (len(work) - zm.start())
    pieces, starts, last = [], [], 0
    for m in _SEP_VS.finditer(work):
        pieces.append(work[last:m.start()])
        starts.append(last)
        last = m.end()
    pieces.append(work[last:])
    starts.append(last)
    if len(pieces) > 3:
        a = starts[3]
        issues.append(Issue(a, len(src), src[a:].strip(), "At most three things (two 'vs').",
                            []))
        pieces, starts = pieces[:3], starts[:3]
    if z_text is not None and len(pieces) == 3:
        issues.append(Issue(z_off, len(src), z_text.strip(), "Already three things: this part "
                            "is left out.", []))
        z_text = None
    if z_text is None and len(pieces) == 3:
        z_text, z_off = pieces[2], starts[2]
        z_mode = "colour"
        pieces, starts = pieces[:2], starts[:2]
    # bins: after Z -> Z bins; after X (no Z) -> X bins
    z_bins, x_bins = None, None
    if z_text is not None:
        b, sp = _bins_in(z_text)
        if b is not None:
            z_bins = b
            z_mode = "bins"
            z_text = _blank(z_text, sp)
    elif len(pieces) >= 2:
        b, sp = _bins_in(pieces[1])
        if b is not None:
            x_bins = b
            pieces[1] = _blank(pieces[1], sp)
    if z_text is None:
        b, sp = _bins_in(pieces[0])
        if b is not None:
            issues.append(Issue(starts[0], starts[0] + len(pieces[0]), "bins",
                                "Bins of what? Add 'binned by <something>'.", ["binned by"]))
            pieces[0] = _blank(pieces[0], sp)
    y = parse_quantity(pieces[0], starts[0], channels, comps, issues, "Y")
    x = None
    if len(pieces) >= 2:
        xt = re.sub(r"[\s,;.]+", " ", pieces[1]).strip().lower()
        mt = re.match(r"\s*(?:the\s+)?(time(?:\s*\(?(?:min|minutes|s)\)?)?|timepoints?|frames?|"
                      r"t|time\s+course)(?![\w/])", pieces[1], re.I)
        if xt in TIME_X_WORDS or mt:
            x = None
            if mt:                                      # words after 'time': not understood
                rest = _Text(pieces[1], starts[1])
                rest.take(0, mt.end())
                for m in rest.find(r"[,;.]"):
                    rest.take(m.start(), m.end())
                for a, b, w in rest.leftovers():
                    sug = suggest(w, channels)
                    issues.append(Issue(a, b, w, f"'{w}' is not understood." + (
                        " Did you mean " + " or ".join(sug[:3]) + "?" if sug else ""), sug))
        else:
            x = parse_quantity(pieces[1], starts[1], channels, comps, issues, "X")
            if x is None:
                return Parsed(None, issues)
    z = parse_quantity(z_text, z_off, channels, comps, issues, "Z") if z_text and \
        z_text.strip() else None
    if y is None:
        return Parsed(None, issues)
    # the sentence says everything: what it does not mention is the default
    keep_bins = base.z_bins if (base is not None and base.z is not None and z_bins is None
                                and z_mode == "bins") else BinSpec()
    spec = GraphSpec(y=y, x=x, z=z, z_mode=z_mode or "colour", z_bins=z_bins or keep_bins,
                     x_bins=x_bins, filters=tuple(filters))
    spec = replace(spec, **opts) if opts else spec
    return Parsed(spec, issues)


# ------------------------------------------------------------ spec -> words
def quantity_text(q: Quantity) -> str:
    """'R/R0 nuclear Cy5/GFP', 'summed nuclear DAPI at T=0', 'whole cell area max'."""
    comp = COMP_ADJ.get(q.comp, q.comp)
    if q.comp2:
        comp = f"{COMP_ADJ.get(q.comp, q.comp).replace('whole cell', 'cell')}/" \
               f"{COMP_ADJ.get(q.comp2, q.comp2).replace('whole cell', 'cell')}"
    m = MEASURE_CANON.get(q.measure, q.measure)
    if q.measure == "area":
        body = f"{comp} area"
    elif q.measure == "xbg":
        body = f"{comp} {q.chan} x background"
    else:
        body = f"{m} {comp} {q.chan}"
    t = _time_words(q)
    return f"{body} {t}".strip()


def _time_words(q: Quantity) -> str:
    if q.time == "trace":
        return ""
    if q.time == "end":
        return "at the end"
    if q.time == "at":
        if q.t1 is None or (q.unit == "tp" and q.t1 == 0):
            return "at T=0"
        if q.unit == "frame":
            return f"at frame {q.t1:g}"
        return "at " + t_text(q.t1, q.unit)
    w = {"mean": "mean", "max": "max", "min": "min", "auc": "AUC", "slope": "slope"}[q.time]
    if q.t1 is None and q.t2 is None:
        return w
    a = q.t1 if q.t1 is not None else (1 if q.unit == "frame" else 0)
    if q.t2 is None:
        return f"{w} over time"
    if q.unit == "frame":
        return f"{w} over frames {a:g}-{q.t2:g}"
    if q.unit == "min":
        return f"{w} over {a:g}-{q.t2:g} min"
    return f"{w} over T={a:g}..{q.t2:g}"


def _bins_text(b: BinSpec) -> str:
    if b.kind == "custom" and b.cuts:
        return "bins at " + ", ".join(f"{c:g}" for c in b.cuts)
    return f"in {b.n} {'equal-width' if b.kind == 'width' else 'equal-count'} bins"


def filter_text(f: Filter) -> str:
    """The chip text: 'summed nuclear DAPI at T=0 > 2e+06'."""
    if f.kind in ("condition", "run", "group"):
        return f"{f.kind} = {f.text}"
    if f.q is None:
        return "?"
    q = quantity_text(f.q)
    if f.op in ("between", "outside"):
        return f"{q} {'not ' if f.op == 'outside' else ''}between {f.a:g} and {f.b:g}"
    return f"{q} {f.op} {f.a:g}"


def sentence(spec: GraphSpec) -> str:
    """The canonical sentence for spec (parse(sentence(spec)) gives spec back)."""
    s = quantity_text(spec.y) + " vs " + (quantity_text(spec.x) if spec.x else "time")
    if spec.x is not None and spec.x_bins is not None:
        s += " " + _bins_text(spec.x_bins)
    if spec.z is not None:
        if spec.z_mode == "bins":
            s += " binned by " + quantity_text(spec.z) + " " + _bins_text(spec.z_bins)
        else:
            s += " vs " + quantity_text(spec.z)
    opts = []
    if spec.split != "pool":
        opts.append({"run": "per run", "condition": "per condition", "group": "per group"}
                    [spec.split])
    if spec.error != "SD":
        opts.append({"SEM": "SEM", "95% CI": "95% CI", "none": "no error"}[spec.error])
    if spec.log_x and spec.log_y:
        opts.append("log-log")
    elif spec.log_x:
        opts.append("log x")
    elif spec.log_y:
        opts.append("log y")
    if spec.corr != "pearson":
        opts.append("spearman" if spec.corr == "spearman" else "no r")
    if spec.pairs == "trajectories":
        opts.append("trajectories")
    if not spec.show_cells:
        opts.append("means only")
    if not spec.show_mean:
        opts.append("no means")
    if not spec.included_only:
        opts.append("all cells")
    if spec.drift:
        opts.append(f"drift corrected frames {spec.drift[0]}-{spec.drift[1]}")
    if opts:
        s += ", " + ", ".join(opts)
    fl = [filter_text(f) for f in spec.filters if f.on]
    if fl:
        s += " where " + " and ".join(fl)
    return s


# ------------------------------------------------------------ autocomplete
CONNECTORS = ["vs", "vs time", "binned by", "coloured by", "where", "at T=0", "at T=", "max",
              "mean over T=0..10", "in 3 bins", "per run", "log y", "SEM"]


def complete(text: str, channels: Sequence[str], comps: Sequence[str] = COMPS,
             limit: int = 12) -> List[str]:
    """Whole-sentence suggestions for a partly typed sentence (the last word
    completed, or the next sensible words after a space)."""
    text = str(text or "")
    words = [w for w, _ in MEASURE_WORDS if " " not in w or w.startswith(("summed", "mean"))]
    comp_words = sorted({COMP_ADJ.get(c, c) for c in comps} | {c for c in comps if c != "cell"})
    vocab = list(dict.fromkeys(list(channels) + ["F/F0", "R/R0", "summed", "intensity",
                                                  "ratio", "area", "x background"] +
                               comp_words + CONNECTORS + words))
    if text and not text.endswith(" "):
        m = re.search(r"(\S+)$", text)
        frag = m.group(1)
        head = text[:m.start()]
        fl = frag.lower()
        got = [v for v in vocab if v.lower().startswith(fl) and v.lower() != fl]
        if "/" in frag and frag.split("/")[0].lower() in {c.lower() for c in channels}:
            a = frag.split("/")[0]
            b = frag.split("/", 1)[1].lower()
            got = [f"{a}/{c}" for c in channels if c.lower() != a.lower() and
                   c.lower().startswith(b)] + got
        return [head + g for g in got][:limit]
    # after a space: what is missing in the current part
    part = _SEP_VS.split(text)[-1].lower()
    has_ch = any(re.search(r"(?<![\w])" + re.escape(c.lower()) + r"(?![\w])", part)
                 for c in channels)
    has_comp = any(re.search(_wb(w), part) for w in COMP_WORDS)
    nxt: List[str] = []
    if not part.strip():
        nxt = ["F/F0", "R/R0", "summed", "intensity"] + comp_words + ["time"]
    elif not has_comp and not has_ch:
        nxt = comp_words + list(channels)
    elif not has_ch:
        nxt = list(channels)
    else:
        n_vs = len(_SEP_VS.findall(" " + text))
        nxt = (["vs", "at T=0", "at T=30", "max", "binned by", "coloured by", "where"] if n_vs < 2
               else ["at T=0", "in 3 bins", "where", "per run"])
    return [text + w for w in nxt][:limit]


def highlight_html(text: str, issues: Sequence[Issue]) -> str:
    """The sentence with not-understood words underlined red, notes orange (rich text)."""
    import html
    chosen: List[Tuple[int, int, str]] = []       # the smallest spans first, no overlaps
    for i in sorted(issues, key=lambda i: (i.end - i.start, i.start)):
        if i.end > i.start and not any(i.start < b and a < i.end for a, b, _l in chosen):
            chosen.append((i.start, i.end, i.level))
    out, pos = [], 0
    for a, b, lvl in sorted(chosen):
        out.append(html.escape(text[pos:a]))
        col = "#C00000" if lvl == "error" else "#B35900"
        out.append(f"<span style='color:{col};text-decoration:underline'>"
                   f"{html.escape(text[a:b])}</span>")
        pos = b
    out.append(html.escape(text[pos:]))
    return "".join(out)
