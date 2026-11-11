"""
Developer test: does the .prism export look the way the chosen graph style says?

Writes .prism files for a matrix of styles with prismfile.write_prism, opens ALL
of them in GraphPad Prism (installed copy, driven by a Prism script: Open /
ExportSVG / ExportPNG / Close), checks that every Prism log says
"COMPLETE! No Errors." and then measures each style property in what Prism drew
(the SVG gives exact stroke colours / widths / shapes; the PNG is checked for
colour). Data: the included cells of a real PeterPiper run (read-only), else a
synthetic stand-in.

Run:  python dev_tests/test_prism_style.py [--keep] [--evidence]
      (needs C:/Program Files/GraphPad/Prism/prism.exe; takes ~1 min)
--evidence copies a few small PNGs to dev_tests/prism_evidence/.
Exit code 0 = all checks passed.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import collections
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
from peterpiper import prismstyle  # noqa: E402
from peterpiper.prismfile import write_prism  # noqa: E402

PRISM = Path(r"C:\Program Files\GraphPad\Prism\prism.exe")
REAL = Path(labdata.T("t17"))

# GraphStyle defaults (Contract 3), so the test does not depend on graphstyle.py
DEFAULT = dict(show_mean=True, error="SEM", error_style="bars", mean_colour="#000000",
               mean_width=1.0, symbol="circle", symbol_size=3.0, show_cells=False,
               cell_colour="#C0C0C0", cell_width=0.5, title="{file} - {comp} (n = {n})",
               x_title="", y_title="", x_min=None, x_max=None, y_min=None, y_max=None,
               font_pt=12.0, baseline_line=False)


def style(**kw) -> dict:
    d = dict(DEFAULT)
    d.update(kw)
    return d


# ---------------------------------------------------------------- the data
def load_data():
    """x (T,), y (T, n), names, source. Reads the graph table of a real V2.2
    export (read-only) when it is there."""
    if REAL.exists():
        with zipfile.ZipFile(REAL) as z:
            doc = json.loads(z.read("document.json"))
            sh = json.loads(z.read(f"data/sheets/{doc['sheets']['data'][0]}/sheet.json"))
            rows = z.read(f"data/tables/{sh['table']['uid']}/data.csv").decode().splitlines()
        a = np.array([[float(v) if v else np.nan for v in r.split(",")] for r in rows])
        return a[:, 0], a[:, 1:], [f"Cell_{k + 1}" for k in range(a.shape[1] - 1)], "real run (MCF10A mito, R/R0 ExRai/GFP)"
    rng = np.random.default_rng(1)
    x = np.arange(31, dtype=float) - 5
    y = 1 + np.where(x[:, None] > 0, (1 + 0.5 * rng.standard_normal(9)) *
                     (1 - np.exp(-np.clip(x, 0, None)[:, None] / 5)), 0) + 0.03 * rng.standard_normal((31, 9))
    return x, y, [f"Cell_{2 * k + 1}" for k in range(9)], "synthetic"


def error_half(y, kind):
    """Half-length of the error bar per timepoint (Contract 3 statistics)."""
    from scipy import stats
    n = np.sum(np.isfinite(y), axis=1)
    sd = np.nanstd(y, axis=1, ddof=1)
    if kind == "SD":
        return sd
    sem = sd / np.sqrt(n)
    if kind == "SEM":
        return sem
    return stats.t.ppf(0.975, n - 1) * sem          # 95% CI


# ------------------------------------------------------------- run Prism
def have_prism() -> bool:
    """GraphPad Prism for Windows is here (it draws the files to check them)."""
    return sys.platform == "win32" and PRISM.exists()


def render(folder: Path, names, batch_name: str, timeout=900) -> str:
    lines = [f'SetPath "{folder}"']
    for n in names:
        lines += [f'Open "{n}.prism"', "GoTo G 1", f'ExportSVG "{n}.svg"', f'ExportPNG "{n}.png"', "Close"]
    lines.append("Exit")
    pzc, log = folder / f"{batch_name}.pzc", folder / f"{batch_name}.log"
    if log.exists():
        log.unlink()
    pzc.write_text("\r\n".join(lines) + "\r\n", encoding="cp1252")
    for attempt in range(2):            # Prism sometimes quits at once right after a run
        p = subprocess.Popen([str(PRISM), str(pzc)])     # only this PID is ever killed
        t0 = time.time()
        while p.poll() is None:
            txt = log.read_text(errors="replace") if log.exists() else ""
            if "PROBLEM" in txt or time.time() - t0 > timeout:
                time.sleep(1)
                p.kill()
                p.wait()
                break
            time.sleep(0.5)
        if log.exists():
            return log.read_text(errors="replace")
        time.sleep(5)
    return "(no log)"


# ------------------------------------------------------------ measuring
ATTR = re.compile(r'([\w:-]+)="([^"]*)"')
TSPAN = re.compile(r'<text[^>]*font-size="([\d.]+)"[^>]*>\s*<tspan y="([-\d.]+)" x="([-\d. ]+)">([^<]*)</tspan>')


class Svg:
    def __init__(self, path: Path):
        s = path.read_text(encoding="utf-8")
        s = re.sub(r"<clipPath\b.*?</clipPath>", "", s, flags=re.S)
        self.s = s
        self.lines = [dict(ATTR.findall(m.group(1))) for m in re.finditer(r"<line ([^>]*)/>", s)]
        self.paths = [dict(ATTR.findall(m.group(1))) for m in re.finditer(r"<path ([^>]*)/>", s)]
        self.texts = [(float(fs), float(y), float(x.split()[0]), html_unescape(t))
                      for fs, y, x, t in TSPAN.findall(s)]
        self.alltext = " ".join(html_unescape(re.sub(r"<[^>]+>", "", m)) for m in
                                re.findall(r"<text[^>]*>(.*?)</text>", s, flags=re.S))

    def ticks(self):
        """(y-tick values with their y, x-tick values with their x)."""
        num = []
        for fs, y, x, t in self.texts:
            try:
                num.append((y, x, float(t.replace("\u2212", "-"))))
            except ValueError:
                pass
        row = collections.Counter(round(y, 1) for y, x, v in num).most_common(1)[0][0]
        xs = sorted((x, v) for y, x, v in num if round(y, 1) == row)
        ys = sorted((y, v) for y, x, v in num if round(y, 1) != row)
        return ys, xs

    def x_axis_span(self):
        """Data values at the two ends of the X axis line (from the axis path:
        the line, then one short segment per tick mark, paired with the labels)."""
        _, xs = self.ticks()
        vals = [v for _, v in xs]
        for p in self.paths:
            d = p.get("d", "")
            m = re.match(r"M ([-\d.]+) ([-\d.]+) L ([-\d.]+) \2 ", d)
            if not (m and "stroke-width" in p and float(m.group(3)) - float(m.group(1)) > 100):
                continue
            ticks = [float(t) for t in re.findall(r"M ([-\d.]+) [-\d.]+ L \1 ", d)]
            if len(ticks) != len(vals) or len(ticks) < 2:
                continue
            a = np.polyfit(ticks, vals, 1)
            half = float(p["stroke-width"]) / 2              # the line overhangs by half its width
            return (np.polyval(a, float(m.group(1)) + half), np.polyval(a, float(m.group(3)) - half))
        return (float("nan"), float("nan"))

    def y_per_pt(self):
        ys, _ = self.ticks()
        a = np.polyfit([p for p, _ in ys], [v for _, v in ys], 1)
        return abs(a[0])

    def polylines(self):
        out = []
        for a in self.paths:
            d = a.get("d", "")
            # (an axis with minor ticks - V2.5 template - is one M per tick: not a data line)
            if a.get("fill") == "none" and d.count("L") > 10 and "C" not in d and \
                    d.count("M") <= d.count("L") // 2:
                out.append(a)
        return out

    def symbols(self):
        """[(shape class, width)] of the small filled marker paths."""
        out = []
        for a in self.paths:
            d = a.get("d", "")
            if "stroke" in a or not d:
                continue
            nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", d)]
            xs, ys = nums[0::2], nums[1::2]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if w < 30 and h < 30:
                c = collections.Counter(re.findall(r"[MLCZ]", d))
                out.append((f"L{c['L']}C{c['C']}", round(w, 2), d))
        return out


def qw(pt: float) -> float:
    """Line widths are drawn in whole units of 0.12 pt."""
    return round(round(pt / prismstyle.LINE_UNIT_PT) * prismstyle.LINE_UNIT_PT, 2)


def html_unescape(t: str) -> str:
    import html
    return html.unescape(t)


def shape_of(sym):
    cls, w, d = sym
    if cls.endswith("C4"):
        return "circle"
    nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", d)]
    pts = list(zip(nums[0::2], nums[1::2]))
    if cls == "L3C0":
        return "square" if len({round(x, 2) for x, _ in pts}) == 2 else "diamond"
    if cls == "L2C0":
        return "triangle" if pts[0][1] < pts[1][1] else "triangle down"
    return cls


def vbar_sum(svg: Svg):
    # vertical lines = error bars; the template's dotted line at X = 0 (V2.5) is not one
    lines = [a for a in svg.lines if abs(float(a["x1"]) - float(a["x2"])) < 1e-6
             and "stroke-dasharray" not in a]
    return len(lines), sum(abs(float(a["y2"]) - float(a["y1"])) for a in lines) * svg.y_per_pt()


def png_has_colour(path: Path, rgb, tol=40, min_px=50):
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    d = np.abs(a - np.array(rgb)[None, None, :]).sum(axis=2)
    return int((d < tol).sum()) >= min_px, int((d < tol).sum())


# ------------------------------------------------------------- the test
def main(argv) -> int:
    if not PRISM.exists():
        print("SKIP: GraphPad Prism is not installed here")
        return 0
    keep = "--keep" in argv
    x, y, names, source = load_data()
    print(f"data: {source}, T = {len(x)}, n = {y.shape[1]}")
    tmp = Path(tempfile.mkdtemp(prefix="pd4nav_prismstyle_"))
    unicode_t = "Mito \u00b5m \u00b1 SEM / \u0394F \u00e9"
    cases = {
        "default": None,
        "style_default": style(),
        "sd": style(error="SD"),
        "ci": style(error="95% CI"),
        "noerr": style(error="none"),
        "band": style(error_style="band"),
        "red": style(mean_colour="#D62728", mean_width=2.0),
        "square": style(symbol="square", symbol_size=5.0),
        "triangle": style(symbol="triangle"),
        "diamond": style(symbol="diamond", symbol_size=4.0),
        "nosym": style(symbol="none"),
        "yrange": style(y_min=0.0, y_max=2.0),
        "xrange": style(x_min=-10.0, x_max=40.0),
        "yhalf": style(y_min=0.5),
        "cells": style(show_cells=True, cell_colour="#1F77B4", cell_width=0.75),
        "unicode": style(),
        "font": style(font_pt=10.0),
    }
    reports, failures = {}, []
    for name, st in cases.items():
        rep: dict = {}
        ttl = unicode_t if name == "unicode" else f"test {name} (n = {y.shape[1]})"
        write_prism(str(tmp / f"{name}.prism"), x, "Time from baseline (min)", "R/R0 ExRai/GFP",
                    unicode_t if name == "unicode" else "R/R0 ExRai/GFP", y, names, ttl,
                    "dev test", name="test", style=st, report=rep)
        reports[name] = rep
    names_all = list(cases)
    half = len(names_all) // 2
    logs = [render(tmp, names_all[:half], "batch1"), render(tmp, names_all[half:], "batch2")]
    for i, lg in enumerate(logs):
        ok = "COMPLETE! No Errors." in lg
        print(f"Prism session {i + 1}: {'COMPLETE' if ok else 'FAILED'}")
        if not ok:
            failures.append(f"session {i + 1} log: {lg.strip()[:200]}")

    def check(cond, what):
        print(("  ok   " if cond else "  FAIL ") + what)
        if not cond:
            failures.append(what)

    with zipfile.ZipFile(tmp / "default.prism") as z:
        names_z = z.namelist()
        doc = json.loads(z.read("document.json"))
        used = set()
        for su in doc["sheets"]["data"]:
            tab = json.loads(z.read(f"data/sheets/{su}/sheet.json"))["table"]
            used.update(tab.get("dataSets", []) + [tab.get("xDataSet"), tab.get("rowTitlesDataSet")])
    orphans = [n for n in names_z if n.startswith("data/sets/") and n.endswith(".json")
               and n[10:-5] not in used]
    misc = [n for n in names_z if n.startswith("misc/") and n.endswith(".bin")]
    check(not orphans and misc == ["misc/used_fonts.bin"],
          f"default: no leftover data sets ({len(orphans)}) or old analyses ({misc})")
    svgs = {n: Svg(tmp / f"{n}.svg") for n in names_all if (tmp / f"{n}.svg").exists()}
    check(len(svgs) == len(names_all), f"all {len(names_all)} graphs exported ({len(svgs)})")
    T = np.isfinite(y).any(axis=1).sum()
    TB = int(np.sum(error_half(y, "SEM") > 0))      # timepoints with an error bar (R/R0 = 1 at baseline)
    for name, kind in (("default", "SEM"), ("style_default", "SEM"), ("sd", "SD"), ("ci", "95% CI")):
        if name not in svgs:
            continue
        cnt, tot = vbar_sum(svgs[name])
        exp = 2 * np.nansum(error_half(y, kind))
        check(cnt == 2 * TB and abs(tot - exp) / exp < 0.02,
              f"{name}: error bars show {kind}: {cnt} bars, total {tot:.3f} vs expected {exp:.3f}")
    if "noerr" in svgs:
        check(vbar_sum(svgs["noerr"])[0] == 0, "noerr: no error bars")
    if "band" in svgs:
        check("error_style" in reports["band"]["not_applied"], "band: reported as not applied in Prism")
    for name, rgb, w in (("style_default", "#000000", 1.0), ("red", "#d62728", 2.0)):
        if name not in svgs:
            continue
        pl = svgs[name].polylines()
        m = [a for a in pl if a.get("stroke", "").lower() == rgb]
        check(len(m) == 1 and abs(float(m[0]["stroke-width"]) - qw(w)) < 0.01,
              f"{name}: mean line colour {rgb}, width {w} pt "
              f"(found {[(a.get('stroke'), a.get('stroke-width')) for a in pl]})")
        bars = [a for a in svgs[name].lines if a.get("stroke", "").lower() == rgb
                and "stroke-dasharray" not in a]          # not the template's dotted line at 0
        check(len(bars) == 4 * TB, f"{name}: error bars drawn in {rgb} ({len(bars)})")
    if "red" in svgs:
        ok, npx = png_has_colour(tmp / "red.png", (0xD6, 0x27, 0x28))
        check(ok, f"red: PNG has the red mean ({npx} px)")
        ok, npx = png_has_colour(tmp / "style_default.png", (0xD6, 0x27, 0x28))
        check(not ok, f"style_default: PNG has no red ({npx} px)")
    for name, shape, size in (("style_default", "circle", 3.0), ("square", "square", 5.0),
                              ("triangle", "triangle", 3.0), ("diamond", "diamond", 4.0)):
        if name not in svgs:
            continue
        syms = svgs[name].symbols()
        shapes = collections.Counter(shape_of(s) for s in syms)
        widths = sorted({s[1] for s in syms})
        exp_w = round(size, 2)
        check(shapes.get(shape, 0) == T and len(widths) == 1 and abs(widths[0] - exp_w) < 0.13,
              f"{name}: {T} {shape} symbols of {exp_w} pt (found {dict(shapes)}, {widths})")
    if "nosym" in svgs:
        check(len(svgs["nosym"].symbols()) == 0, "nosym: no symbols")
    for name, lo, hi in (("yrange", 0.0, 2.0), ("yhalf", 0.5, None)):
        if name not in svgs:
            continue
        ys, _ = svgs[name].ticks()
        vals = [v for _, v in ys]
        okr = abs(min(vals) - lo) < 1e-9 and (hi is None or abs(max(vals) - hi) < 1e-9)
        check(okr, f"{name}: Y axis from {lo} to {hi if hi is not None else 'data'} (ticks {vals})")
    if "xrange" in svgs:
        lo, hi = svgs["xrange"].x_axis_span()
        check(abs(lo + 10) < 0.3 and abs(hi - 40) < 0.3, f"xrange: X axis line from {lo:.2f} to {hi:.2f} (-10..40)")
    if "style_default" in svgs:
        _, xs = svgs["style_default"].ticks()
        vals = [v for _, v in xs]
        check(max(vals) >= np.nanmax(x) - 1e-9 and max(vals) - np.nanmax(x) < 0.5 * (np.nanmax(x) - np.nanmin(x)),
              f"style_default: X axis automatic, covers the data to {np.nanmax(x):.1f} (ticks {vals})")
    if "font" in svgs:
        sz = collections.Counter(fs for fs, _y, _x, _t in svgs["font"].texts)
        tick = sz.most_common(1)[0][0]
        others = sorted(fs for fs, _y, _x, t in svgs["font"].texts
                        if not re.fullmatch(r"[-−\d.]+", t))
        check(abs(tick - 9.0) < 0.1 and others and all(abs(f - 10.0) < 0.1 for f in others),
              f"font: tick labels 9 pt, titles 10 pt (ticks {tick}, titles {others})")
    if "unicode" in svgs:
        flat = re.sub(r"[\s ]", "", svgs["unicode"].alltext)
        check(flat.count(re.sub(r"\s", "", unicode_t)) == 2, "unicode: title and Y title drawn with \u00b5 \u00b1 / \u0394 \u00e9")
        check("Y1Title" not in svgs["default"].alltext if "default" in svgs else True, "default: no stray 'Y1Title'")
    if "cells" in svgs:
        pl = svgs["cells"].polylines()
        c = [a for a in pl if a.get("stroke", "").lower() == "#1f77b4"]
        if prismstyle.SUPPORT.get("show_cells") == "yes":
            check(len(c) == y.shape[1] and all(abs(float(a["stroke-width"]) - qw(0.75)) < 0.01 for a in c),
                  f"cells: {y.shape[1]} cell lines in #1f77b4, {qw(0.75)} pt (found {len(c)})")
            check("Cell_1" not in svgs["cells"].alltext, "cells: no legend listing the cells")
            m = [a for a in pl if a.get("stroke", "").lower() == "#000000"]
            check(len(m) == 1 and svgs["cells"].s.find(m[0]["d"]) > max(svgs["cells"].s.find(a["d"]) for a in c),
                  "cells: mean drawn on top of the cells")
        else:
            check("show_cells" in reports["cells"]["not_applied"], "cells: reported as not applied")
    for name, rep in reports.items():
        if rep.get("applied"):
            bad = [f for f in rep["applied"] if prismstyle.SUPPORT.get(f) != "yes"]
            check(not bad, f"{name}: applies only verified fields {bad}")
    if "--evidence" in argv:
        ev = HERE / "prism_evidence"
        ev.mkdir(exist_ok=True)
        from PIL import Image
        for name in ("default", "cells", "sd", "band", "red", "yrange", "unicode"):
            p = tmp / f"{name}.png"
            if p.exists():
                im = Image.open(p).convert("RGB")
                im.thumbnail((640, 640))
                im.save(ev / f"prism_{name}.png", optimize=True)
    print(f"\n{len(failures)} failure(s)" + ("" if not failures else ":\n  " + "\n  ".join(failures)))
    if keep:
        print("files kept in", tmp)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
