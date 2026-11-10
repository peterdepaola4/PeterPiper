"""
How a time-course graph looks - one description shared by the live graph
panel ('As exported' view), the 300 dpi PNG / SVG export and the Prism export.

    GraphStyle      every choice (error type, colours, line widths, symbols,
                    titles, axis ranges, font size); saved as a plain dict in
                    Settings.graph_style and in the ROI / session file
    PRESETS         ready-made looks for the 'Look' dropdown
    describe/stats  THE mean, SD, SEM, 95% CI and n of the included cells -
                    every graph and the CSV tables use these numbers
    draw_matplotlib draws one graph onto a matplotlib Axes (PNG / SVG / PDF)
    PRISM_SUPPORT   which choices a .prism file can carry (prismstyle.SUPPORT,
                    checked in Prism 11); prism_look gives the closest Prism
                    look for the others and the warnings the GUI shows

Statistics (per timepoint, over the included cells that have a value there;
cells with no value at a timepoint - NaN - are left out of that timepoint):
    mean  = arithmetic mean
    SD    = sample standard deviation (n - 1 in the denominator)
    SEM   = SD / sqrt(n)
    95% CI half-width = t(0.975, n - 1) x SEM   (Student's t, scipy.stats.t)
With fewer than 2 values SD, SEM and CI are undefined (empty / no error bar).

The defaults reproduce the look of the bundled Prism template (V2.5: the
graph styled in GraphPad Prism that templates/PeterPiper_timecourse.prism and
templates/PeterPiper_look.json were made from - dev_tests/make_prism_template.py):
#28D2F0 4.32 pt filled circles, a 0.59 pt mean line, capped error bars, 18 pt
axis titles, no individual cells, no grid. In the .prism file the template's
bytes are kept wherever these defaults are unchanged (prismstyle.apply_style).
One difference: the template graph hides its connecting line; PeterPiper draws the
0.59 pt line (as the live graph and the PNG do) - a mean line width of 0 gives
exactly the template's symbols-only look in every output. The error type stays
SEM (a statistic, not a look - the template graph itself showed SD).

BLOCK: a new style choice = one dataclass field (+ its line in
prismstyle.SUPPORT once checked in Prism, else a PRISM_FIELD_NOTE and a case
in prism_look) (+ a control in gui/traces.py); from_dict() picks up old files
without it.
"""
from __future__ import annotations

import dataclasses
import re
import textwrap
import warnings
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

ERRORS = ("SEM", "SD", "95% CI", "none")
ERROR_STYLES = ("bars", "band")
SYMBOLS = ("circle", "square", "triangle", "diamond", "none")
# matplotlib / pyqtgraph marker codes for SYMBOLS
MPL_MARKER = {"circle": "o", "square": "s", "triangle": "^", "diamond": "D", "none": None}
PG_SYMBOL = {"circle": "o", "square": "s", "triangle": "t1", "diamond": "d", "none": None}

PX_PER_PT = 96.0 / 72.0      # screen pixels per point (live view line widths, symbol sizes)
TICK_SCALE = 0.9             # tick labels = 0.9 x the axis-title size
BAND_ALPHA = 0.25            # shaded error band opacity
BASELINE_COLOUR = "#404040"  # dashed line at time 0
FONT_FAMILY = "Arial"        # Prism's default font; falls back to the default font

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class GraphStyle:
    show_mean: bool = True
    error: str = "SD"                # "SEM" | "SD" | "95% CI" | "none" (V3.0: SD default)
    error_style: str = "bars"        # "bars" | "band"
    mean_colour: str = "#28D2F0"     # V2.5: the template's (was #000000)
    mean_width: float = 0.59         # pt (V2.5: the template's; was 1.0)
    symbol: str = "circle"           # "circle" | "square" | "triangle" | "diamond" | "none"
    symbol_size: float = 4.32        # pt (diameter; V2.5: the template's, was 3.0)
    show_cells: bool = False         # each included cell as a thin line
    cell_colour: str = "#C0C0C0"
    cell_width: float = 0.5          # pt
    title: str = "{file} - {comp} (n = {n})"   # template; "" = no title
    x_title: str = ""                # "" = automatic, e.g. "Time from baseline (min)"
    y_title: str = ""                # "" = automatic (the quantity, e.g. "R/R0 GFP/Cy5")
    x_min: Optional[float] = None    # None = automatic
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    font_pt: float = 18.0            # V2.5: the template's (was 12); axis-title size (tick labels and title scale from it)
    baseline_line: bool = False      # dashed vertical line at time 0
    # --- beyond the design contract (PNG / SVG and live view only) ---
    legend: bool = False             # a key: 'Mean ± SEM (n = 8)', 'Each cell'
    width_in: float = 6.0            # size of the saved PNG / SVG / PDF (inches)
    height_in: float = 4.5

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "GraphStyle":
        """A style from a saved dict: unknown keys are ignored, values are
        converted to the right type, and anything unusable falls back to the
        default (so an old or hand-edited file never breaks the graph)."""
        st = cls()
        if isinstance(d, GraphStyle):
            d = d.to_dict()
        if not isinstance(d, dict):
            return st
        for f in fields(cls):
            if f.name not in d:
                continue
            ok, v = _coerce(f.name, d[f.name], getattr(st, f.name))
            if ok:
                setattr(st, f.name, v)
        return st

    def copy(self, **changes) -> "GraphStyle":
        return dataclasses.replace(self, **changes)


# limits for the numbers (pt / inches); outside -> clipped
_LIMITS = {"mean_width": (0.0, 20.0), "symbol_size": (0.0, 40.0), "cell_width": (0.0, 20.0),
           "font_pt": (4.0, 72.0), "width_in": (1.0, 30.0), "height_in": (1.0, 30.0)}
_CHOICES = {"error": ERRORS, "error_style": ERROR_STYLES, "symbol": SYMBOLS}
_ERROR_ALIASES = {"sem": "SEM", "se": "SEM", "sd": "SD", "stdev": "SD", "95% ci": "95% CI",
                  "95ci": "95% CI", "ci": "95% CI", "95%ci": "95% CI", "ci95": "95% CI",
                  "none": "none", "": "none", "no": "none", "off": "none"}


def _bool(v: Any) -> Optional[bool]:
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, float, np.integer, np.floating)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on", "y"):
            return True
        if s in ("0", "false", "no", "off", "n", ""):
            return False
    return None


def _float(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _coerce(name: str, v: Any, default: Any) -> Tuple[bool, Any]:
    """(usable?, value) for one field."""
    if name in ("x_min", "x_max", "y_min", "y_max"):
        if v is None or (isinstance(v, str) and v.strip().lower() in ("", "auto", "none")):
            return True, None
        x = _float(v)
        return (x is not None), x
    if isinstance(default, bool):
        b = _bool(v)
        return (b is not None), b
    if isinstance(default, float):
        x = _float(v)
        if x is None:
            return False, None
        lo, hi = _LIMITS.get(name, (-np.inf, np.inf))
        return True, float(min(max(x, lo), hi))
    if name in ("mean_colour", "cell_colour"):
        s = str(v).strip()
        if re.fullmatch(r"#[0-9a-fA-F]{3}", s):           # #abc -> #aabbcc
            s = "#" + "".join(ch * 2 for ch in s[1:])
        return (bool(_HEX.match(s))), s.upper()
    if name == "error":
        s = str(v).strip()
        s = _ERROR_ALIASES.get(s.lower(), s)
        return (s in ERRORS), s
    if name in _CHOICES:
        s = str(v).strip().lower()
        return (s in _CHOICES[name]), s
    if isinstance(default, str):
        return (v is not None), ("" if v is None else str(v))
    return False, None


def coerce(style: Any) -> GraphStyle:
    """GraphStyle from a GraphStyle, a dict or None (None / {} = the defaults)."""
    if isinstance(style, GraphStyle):
        return style
    return GraphStyle.from_dict(style or {})


# --------------------------------------------------------------------------
#  Presets ('Look' dropdown). A preset only sets how the data are drawn
#  (LOOK_FIELDS); your titles, axis ranges and font size are kept.
# --------------------------------------------------------------------------
LOOK_FIELDS = ("show_mean", "error", "error_style", "mean_colour", "mean_width", "symbol",
               "symbol_size", "show_cells", "cell_colour", "cell_width")

# V3.0: every preset names its error itself (the default became SD)
PRESETS: Dict[str, GraphStyle] = {
    "Prism default - mean ± SD": GraphStyle(error="SD"),
    "Prism default - mean ± SEM": GraphStyle(error="SEM"),
    "Mean ± SD + each cell": GraphStyle(error="SD", show_cells=True),
    "Mean ± SEM + each cell": GraphStyle(error="SEM", show_cells=True),
    "Mean ± 95% CI": GraphStyle(error="95% CI"),
    "Shaded SD band": GraphStyle(error="SD", error_style="band", symbol="none", mean_width=1.5,
                                 mean_colour="#1F6FE0"),
    "Shaded SEM band": GraphStyle(error="SEM", error_style="band", symbol="none",
                                  mean_width=1.5, mean_colour="#1F6FE0"),
    "Shaded SEM band + each cell": GraphStyle(error="SEM", error_style="band", symbol="none",
                                              mean_width=1.5, mean_colour="#1F6FE0",
                                              show_cells=True, cell_colour="#A0A0A0"),
    "Each cell only": GraphStyle(show_mean=False, error="none", show_cells=True,
                                 cell_colour="#404040", cell_width=0.75),
}
DEFAULT_PRESET = "Prism default - mean ± SD"


def apply_preset(style: Any, name: str) -> GraphStyle:
    """`style` with the look of preset `name` (titles, ranges, fonts kept)."""
    st = coerce(style)
    p = PRESETS.get(name)
    if p is None:
        return st
    return st.copy(**{f: getattr(p, f) for f in LOOK_FIELDS})


def preset_name(style: Any) -> str:
    """The preset whose look this style has, or "" (= your own look)."""
    st = coerce(style)
    for name, p in PRESETS.items():
        if all(getattr(st, f) == getattr(p, f) for f in LOOK_FIELDS):
            return name
    return ""


# --------------------------------------------------------------------------
#  What a .prism file can carry - prismstyle.SUPPORT is the one list (every
#  "yes" was checked in GraphPad Prism 11). "no" = Prism cannot draw it: the
#  .prism file gets the closest look (prism_look) and the GUI says so.
# --------------------------------------------------------------------------
def _support() -> Dict[str, str]:
    from .prismstyle import SUPPORT
    out = {"data": "yes"}
    out.update(SUPPORT)
    for f in fields(GraphStyle):
        out.setdefault(f.name, "no")       # legend, width_in, height_in: PNG / SVG only
    return out


PRISM_SUPPORT: Dict[str, str] = _support()
LINE_MIN_PT = 0.12          # Prism draws lines in whole units of 0.12 pt (prismstyle)
# per field: what the .prism file shows instead (plain words for tooltips)
PRISM_FIELD_NOTE: Dict[str, str] = {
    "show_mean": "Prism can't hide the mean - the .prism file draws it as a hairline "
                 "(0.12 pt) without symbols or error bars",
    "error_style": "Prism can't draw a shaded band - the .prism file shows error bars instead",
    "baseline_line": "Prism file: no dashed line at time 0 (add one in Prism if you need it)",
    "legend": "Prism file: no key",
    "width_in": "Size of the saved PNG / SVG / PDF only; the Prism graph keeps its own size",
    "height_in": "Size of the saved PNG / SVG / PDF only; the Prism graph keeps its own size",
}
PRISM_NOTE = ("Everything else you choose here (error type, colours, line widths, symbols, "
              "each cell, titles, axis ranges, font size) goes into the Prism file too")


def prism_support(field_name: str) -> str:
    return PRISM_SUPPORT.get(field_name, "no")


def prism_look(style: Any) -> Tuple[dict, List[str]]:
    """(the style written into a .prism file, plain-language warnings).
    Looks Prism cannot draw get the closest Prism look:
        shaded band          -> error bars (same error type)
        mean hidden          -> mean as a 0.12 pt hairline, no symbols, no error bars
        mean line width 0    -> symbols not joined (no symbols either: 0.12 pt hairline)
        cell line width 0    -> 0.12 pt hairline
        symbol size 0        -> no symbol (the same look)
        dashed line at 0     -> left out
        key (legend)         -> left out
    The warnings list only what the graph shown now has (empty = Prism matches)."""
    st = coerce(style)
    d = st.to_dict()
    warn: List[str] = []
    if st.symbol_size <= 0:
        d["symbol"] = "none"
    if not st.show_mean:
        d.update(mean_width=LINE_MIN_PT, symbol="none", error="none", error_style="bars")
        warn.append(PRISM_FIELD_NOTE["show_mean"] + ".")
    else:
        if st.error != "none" and st.error_style == "band":
            d["error_style"] = "bars"
            warn.append(f"Prism can't draw a shaded band - the .prism file shows "
                        f"{error_label(st.error)} error bars instead.")
        if st.mean_width < LINE_MIN_PT / 2:              # V2.5: Prism can leave the
            d["mean_width"] = 0.0                        # symbols unjoined (009c byte 8)
            if st.symbol == "none" or st.symbol_size <= 0:
                d["mean_width"] = LINE_MIN_PT
                warn.append("Without symbols and without a line nothing would be drawn - "
                            "the .prism file draws a 0.12 pt line.")
    if st.show_cells and st.cell_width < LINE_MIN_PT / 2:
        d["cell_width"] = LINE_MIN_PT
        warn.append("Prism can't draw 0 pt cell lines - the .prism file uses 0.12 pt.")
    if st.baseline_line:
        warn.append("The dashed line at time 0 is not in the .prism file.")
    if st.legend:
        warn.append("The key is not in the .prism file.")
    return d, warn


def prism_summary(style: Any) -> str:
    """What the .prism graph shows, in words: 'mean ± SD (error bars)'."""
    d, _w = prism_look(style)
    st = coerce(d)
    parts: List[str] = []
    if coerce(style).show_mean:
        e = error_label(st.error)
        parts.append(f"mean ± {e} (error bars)" if e else "mean (no error shown)")
    else:
        parts.append("the mean as a hairline")
    if st.show_cells:
        parts.append("each cell as a thin line")
    return " and ".join(parts)


# --------------------------------------------------------------------------
#  Statistics - the ONE implementation (graphs, live view, CSV)
# --------------------------------------------------------------------------
@dataclass
class Summary:
    mean: np.ndarray       # (T,)
    sd: np.ndarray         # (T,) sample SD (ddof = 1); NaN where n < 2
    sem: np.ndarray        # (T,) SD / sqrt(n); NaN where n < 2
    ci95: np.ndarray       # (T,) half-width t(0.975, n-1) x SEM; NaN where n < 2
    n: np.ndarray          # (T,) int: cells with a value at that timepoint


def describe(y: np.ndarray) -> Summary:
    """Per-timepoint statistics over the columns (cells) of y (T x n);
    NaN values are left out. Same arithmetic as V2.2's CSV tables."""
    y = np.asarray(y)
    if not np.issubdtype(y.dtype, np.floating):
        y = y.astype(float)
    if y.ndim == 1:
        y = y[:, None]
    T = y.shape[0]
    n = np.sum(np.isfinite(y), axis=1)
    if y.shape[1] == 0:
        nan = np.full(T, np.nan)
        return Summary(nan, nan.copy(), nan.copy(), nan.copy(), n.astype(int))
    with np.errstate(invalid="ignore", divide="ignore"):
        with warnings.catch_warnings():            # all-NaN rows / n < 2: NaN, quietly
            warnings.simplefilter("ignore", RuntimeWarning)
            mean = np.nanmean(y, axis=1)
            sd = np.nanstd(y, axis=1, ddof=1)
        sem = sd / np.sqrt(np.maximum(n, 1))
    few = n < 2
    sd[few] = np.nan
    sem[few] = np.nan
    ci = np.full(T, np.nan)
    if (~few).any():
        from scipy.stats import t as student_t
        ci[~few] = student_t.ppf(0.975, n[~few] - 1) * sem[~few]
    return Summary(mean, sd, sem, ci, n.astype(int))


def stats(y: np.ndarray, error: str = "SEM") -> Tuple[np.ndarray, np.ndarray, np.ndarray,
                                                       np.ndarray]:
    """(mean, low, high, n per timepoint) of y (T x n cells) for error
    "SEM" | "SD" | "95% CI" | "none" (low = high = mean). Low / high are NaN
    where the error is undefined (fewer than 2 cells with a value)."""
    s = describe(y)
    _ok, error = _coerce("error", error, "SEM")
    err = {"SEM": s.sem, "SD": s.sd, "95% CI": s.ci95}.get(error)
    if err is None:
        return s.mean, s.mean.copy(), s.mean.copy(), s.n
    return s.mean, s.mean - err, s.mean + err, s.n


def error_label(error: str) -> str:
    return {"SEM": "SEM", "SD": "SD", "95% CI": "95% CI"}.get(error, "")


# --------------------------------------------------------------------------
#  Text
# --------------------------------------------------------------------------
def quantity_title(name: str) -> str:
    """'R/R0 - GFP/Cy5' (trace panel name) -> 'R/R0 GFP/Cy5' (axis / file title,
    the same text as the export's names)."""
    return str(name).replace(" - ", " ", 1)


def title_text(style: Any, file: str, comp: str, quantity: str, n: int) -> str:
    """The graph title from the template: {file} {comp} {n} {quantity}."""
    tpl = coerce(style).title or ""
    out = tpl
    for key, val in (("{file}", file), ("{comp}", comp), ("{n}", str(int(n))),
                     ("{quantity}", quantity)):
        out = out.replace(key, str(val))
    return out.strip()


def axis_titles(style: Any, x_label: str, y_label: str) -> Tuple[str, str]:
    """(x title, y title): yours, or the automatic ones."""
    st = coerce(style)
    return (st.x_title.strip() or x_label), (st.y_title.strip() or y_label)


def legend_text(style: Any, n: int) -> str:
    st = coerce(style)
    e = error_label(st.error)
    return f"Mean ± {e} (n = {n})" if e else f"Mean (n = {n})"


# --------------------------------------------------------------------------
#  matplotlib (PNG / SVG / PDF; object API, safe in a worker thread)
# --------------------------------------------------------------------------
_FAMILY: Optional[str] = None


def font_family() -> str:
    """Arial when this computer has it (Prism's font), else matplotlib's default."""
    global _FAMILY
    if _FAMILY is None:
        try:
            from matplotlib import font_manager
            font_manager.findfont(font_manager.FontProperties(family=FONT_FAMILY),
                                  fallback_to_default=False)
            _FAMILY = FONT_FAMILY
        except Exception:                          # noqa: BLE001 - any failure: default
            _FAMILY = "DejaVu Sans"
    return _FAMILY


def cap_pt(style: Any) -> float:
    """Half-width of the error-bar caps in points (matplotlib 'capsize')."""
    return max(2.0, 0.8 * coerce(style).symbol_size)


def _wrap(text: str, width_in: float, pt: float) -> str:
    """Break a long title so it fits the figure width (about 0.55 em per character)."""
    per_line = max(20, int(width_in * 72.0 / (0.55 * pt)))
    return "\n".join(textwrap.fill(line, per_line) for line in text.split("\n"))


def draw_matplotlib(ax, x, y, names: Sequence[str], style: Any, x_label: str, y_label: str,
                    title: str) -> None:
    """Draw the graph onto `ax`: y (T x n) = the included cells, x (T) = time.
    `x_label` / `y_label` are the automatic axis titles (the style's own titles
    win); `title` is the finished title text (see title_text)."""
    st = coerce(style)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float).reshape(x.size, -1)
    fam = font_family()
    fs = float(st.font_pt)
    n_cells = y.shape[1]
    if st.show_cells and n_cells:
        lines = ax.plot(x, y, color=st.cell_colour, lw=st.cell_width, zorder=1)
        if lines:
            lines[0].set_label("Each cell")
    if st.show_mean and n_cells:
        m, lo, hi, _n = stats(y, st.error)
        if st.error != "none":
            if st.error_style == "band":
                ax.fill_between(x, lo, hi, color=st.mean_colour, alpha=BAND_ALPHA, lw=0,
                                zorder=2)
            else:
                ok = np.isfinite(m) & np.isfinite(lo) & np.isfinite(hi)
                if ok.any():
                    ax.errorbar(x[ok], m[ok], yerr=[m[ok] - lo[ok], hi[ok] - m[ok]], fmt="none",
                                ecolor=st.mean_colour, elinewidth=max(st.mean_width, 0.5),
                                capsize=cap_pt(st), capthick=max(st.mean_width, 0.5), zorder=2)
        marker = MPL_MARKER.get(st.symbol)
        ax.plot(x, m, color=st.mean_colour, lw=st.mean_width,
                ls="-" if st.mean_width > 0 else "none",
                marker=marker, ms=st.symbol_size, mfc=st.mean_colour, mec=st.mean_colour,
                mew=0, zorder=3, label=legend_text(st, n_cells))
    if st.baseline_line:
        ax.axvline(0.0, color=BASELINE_COLOUR, lw=0.75, ls=(0, (4, 3)), zorder=0)
    xt, yt = axis_titles(st, x_label, y_label)
    ax.set_xlabel(xt, fontsize=fs, family=fam)
    ax.set_ylabel(yt, fontsize=fs, family=fam)
    if title:
        w = ax.figure.get_figwidth() if ax.figure is not None else st.width_in
        ax.set_title(_wrap(title, w, fs), fontsize=fs, fontweight="bold", family=fam)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_linewidth(1.0)
        ax.spines[side].set_color("black")
    ax.tick_params(direction="out", length=4, width=1.0, colors="black",
                   labelsize=fs * TICK_SCALE, labelfontfamily=fam)
    ax.grid(False)
    if st.x_min is not None or st.x_max is not None:
        ax.set_xlim(left=st.x_min, right=st.x_max)
    if st.y_min is not None or st.y_max is not None:
        ax.set_ylim(bottom=st.y_min, top=st.y_max)
    if st.legend and (st.show_mean or st.show_cells) and n_cells:
        ax.legend(frameon=False, loc="best", prop={"family": fam, "size": fs * TICK_SCALE * 0.85})


def save_figure(path, x, y, names: Sequence[str], style: Any, x_label: str, y_label: str,
                title: str, fmt: Optional[str] = None, dpi: int = 300) -> str:
    """Write the graph as PNG (300 dpi), SVG or PDF (from the file ending unless
    `fmt` is given). Never overwrites: an existing name gets _2, _3 ...
    Returns the path written."""
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from .safety import new_output_file
    st = coerce(style)
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".") or "png").lower()
    if fmt not in ("png", "svg", "pdf"):
        raise ValueError(f"Graphs can be saved as PNG, SVG or PDF, not '{fmt}'.")
    fig = Figure(figsize=(st.width_in, st.height_in), dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    draw_matplotlib(ax, x, y, names, st, x_label, y_label, title)
    fig.tight_layout()
    # SVG / PDF keep the text as text (editable in Illustrator / Inkscape)
    with matplotlib.rc_context({"svg.fonttype": "none", "pdf.fonttype": 42}):
        with new_output_file(path) as (used, stream):
            fig.savefig(stream, format=fmt, dpi=dpi)
    return str(used)


def style_summary(style: Any) -> str:
    """What is drawn, in words: 'mean ± SEM (error bars) and each cell'."""
    st = coerce(style)
    parts: List[str] = []
    if st.show_mean:
        e = error_label(st.error)
        parts.append(f"mean ± {e} ({'shaded band' if st.error_style == 'band' else 'error bars'})"
                     if e else "mean (no error shown)")
    if st.show_cells:
        parts.append("each cell as a thin line")
    return " and ".join(parts) if parts else "nothing drawn"


def describe_style(style: Any) -> str:
    """One plain sentence for the methods / Settings sheet."""
    st = coerce(style)
    if not (st.show_mean or st.show_cells):
        return "Graph: no data drawn."
    return f"Graph: {style_summary(st)}, of the included cells."
