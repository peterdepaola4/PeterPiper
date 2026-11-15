"""
Charlotte's Web (a hidden extra, PeterPiper 1.1) - the drawing.

Harmless easter egg: everything here only paints pictures with QPainter. No
image files, no network, nothing read from or written to the analysis - a web
is described only by its theme, its random seed and a few numbers (params).

    new_params(seed)                 the continuous numbers that make a web unique
    Scene(theme_key, params, seed, n, w, h)
        .draw(p, t=0, word=None, word_progress=1.0)   the whole picture
        .draw_background(p) / .draw_web(p) / .draw_overlay(p, t, word, progress)
        .stats                       how many elements were drawn (capped)
    render_image(theme_key, params, seed, n, w, h, ...) -> QImage

Design level (rarity): 0 common - deliberately plain: a simple creature, a plain
thread, hardly any adornment; 1 (in between, kept for drawing only); 2 rare - a
cute, more elaborate creature with its accessory and pattern, a lace edge, a hub
rosette, more twinkling dew, sparkle, a soft halo and floating motes; 3 epic -
all of rare plus a glowing aura, eyelashes or a tiny crown, a golden filigree
frame, an iridescent sheen on the rings, a light sweep and a signature ring of
the theme's own ornaments circling the creature. Every level is capped.

Growth with n (cells drawn by hand on that movie): anchors and a few radial
threads at 0; radials and spiral rings fill in quickly (lovely at 4-6); from
about 8 extra decorations, from 10 mini-webs at the knots (recursion depth 2 at
most), sparkles and friends. Every count is capped, so any n renders quickly.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QFontDatabase,
                           QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPolygonF, QRadialGradient, QTransform)

from .charlotte_themes import BY_KEY, THEMES

TAU = 2.0 * math.pi
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))

MAX_RADIALS = 22
MAX_ORN = 40
MAX_MINI = 6
MAX_SPARKLES = 18
MAX_FRIENDS = 3

_COARSE = QTransform.fromScale(0.3, 0.3)          # flatten curves a little coarser
_UNCOARSE = QTransform.fromScale(1 / 0.3, 1 / 0.3)
STRAIGHT = {"crystal", "paper", "stained", "string"}
WAVY = {"noodle", "ribbon", "mycelium", "twine", "grass", "trail", "dendrite", "yarn",
        "drizzle", "honey", "fluff", "wash"}
MULTI = {"rainbow", "neon", "twine", "yarn", "dendrite", "fluff"}
PLAIN_WHEN_COMMON = {"glow", "neon", "beaded", "fluff", "wash", "trail", "crystal", "frost",
                     "rainbow"}
STYLES = {"silk", "glow", "crystal", "lightning", "beaded", "yarn", "noodle", "grass", "twine",
          "circuit", "drizzle", "rainbow", "mycelium", "brass", "neon", "paper", "ribbon",
          "frost", "stained", "fluff", "wash", "honey", "trail", "string", "dendrite"}


# ----------------------------------------------------------------- growth rules
def n_radials(n: int) -> int:
    return min(MAX_RADIALS, 4 + int(round(2.4 * max(0, n))))


def n_rings(n: int, rmax: int) -> int:
    return 0 if n <= 0 else max(2, int(round(rmax * (1.0 - math.exp(-n / 3.2)))))


def n_ornaments(n: int) -> int:
    return 0 if n <= 0 else min(MAX_ORN, 2 + 3 * n)


def n_minis(n: int) -> int:
    return max(0, min(MAX_MINI, (n - 8) // 2))


def n_subminis(n: int) -> int:
    return max(0, min(2, (n - 14) // 4))


def n_stab(n: int) -> int:
    return max(0, min(4, (n - 5) // 2))


def n_sparkles(n: int) -> int:
    return max(0, min(MAX_SPARKLES, (n - 9) * 3))


def n_friends(n: int) -> int:
    return max(0, min(MAX_FRIENDS, (n - 6) // 4))


def n_herd(n: int) -> int:
    return 1 + min(5, (n + 1) // 2)


# ---------------------------------------------------------------------- params
def _r(x: float) -> float:
    return round(float(x), 5)


def new_params(seed: int) -> dict:
    """The continuous numbers of one web (stored with it, so it re-renders the same)."""
    g = random.Random(seed)
    na = g.choice((4, 4, 5, 5, 6))
    base = g.uniform(0, TAU)
    anchors = []
    jit = 0.12 if na == 3 else 0.25      # the web's centre always stays inside its frame
    for i in range(na):
        a = base + i * TAU / na + g.uniform(-jit, jit) * TAU / na
        anchors.append([_r(a), _r(g.uniform(0.43, 0.53))])
    return {
        "v": 1,
        "cx": _r(g.uniform(-0.05, 0.05)), "cy": _r(g.uniform(-0.05, 0.04)),
        "r_out": _r(g.uniform(0.36, 0.42)),
        "env": [[_r(g.uniform(0.0, a)), _r(g.uniform(0, TAU))] for a in (0.08, 0.05, 0.03)],
        "rot": _r(g.uniform(0, TAU)),
        "rings": g.randint(14, 19),
        "curve": _r(g.uniform(0.82, 1.18)),
        "hub": _r(g.uniform(0.055, 0.08)),
        "sag": _r(g.uniform(0.03, 0.11)),
        "wobble": _r(g.uniform(0.0, 1.0)),
        "dir": g.choice((1, -1)),
        "anchors": anchors,
        "hue": _r(g.uniform(-9, 9)), "sat": _r(g.uniform(0.9, 1.08)),
        "light": _r(g.uniform(0.95, 1.05)),
        "thread": _r(g.random()), "orn": _r(g.random()),
        "creature": {"slot": _r(g.random()), "frac": _r(g.uniform(0.15, 0.6)),
                     "tilt": _r(g.uniform(-14, 14)), "phase": _r(g.uniform(0, TAU)),
                     "scale": _r(g.uniform(0.92, 1.08)), "flip": g.choice((1, -1)),
                     "spot": _r(g.random())},
        "word_dy": _r(g.uniform(-0.03, 0.03)), "word_tilt": _r(g.uniform(-4, 4)),
        "bg": g.getrandbits(40),
    }


class _Derived:
    """Per-element jitter, derived from the seed (not stored: same seed, same values)."""

    def __init__(self, seed: int) -> None:
        g = random.Random((int(seed) * 2654435761 + 97) & ((1 << 62) - 1))
        self.jit = [g.uniform(-1, 1) for _ in range(MAX_RADIALS)]
        self.rlen = [g.uniform(0.0, 1.0) for _ in range(MAX_RADIALS)]
        self.orn = [(g.random(), g.random(), g.random(), g.uniform(0.75, 1.25), g.uniform(0, TAU))
                    for _ in range(MAX_ORN)]
        self.mini = [(g.uniform(-0.25, 0.25), g.uniform(0.55, 0.75), g.uniform(0.8, 1.15),
                      g.uniform(0, TAU)) for _ in range(MAX_MINI)]
        self.spark = [(g.random(), g.random(), g.uniform(0, TAU), g.uniform(0.6, 1.4))
                      for _ in range(MAX_SPARKLES)]
        self.friends = [(g.random(), g.uniform(0.3, 0.8), g.uniform(-12, 12), g.uniform(0, TAU))
                        for _ in range(8)]
        self.noise = g.uniform(0, 1000)


# ---------------------------------------------------------------------- colour
def qc(x, a: Optional[int] = None) -> QColor:
    c = QColor(x) if not isinstance(x, QColor) else QColor(x)
    if a is not None:
        c.setAlpha(max(0, min(255, int(a))))
    return c


def alpha(c: QColor, a: float) -> QColor:
    c = QColor(c)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def mix(c1: QColor, c2: QColor, f: float) -> QColor:
    return QColor(int(c1.red() + (c2.red() - c1.red()) * f),
                  int(c1.green() + (c2.green() - c1.green()) * f),
                  int(c1.blue() + (c2.blue() - c1.blue()) * f),
                  int(c1.alpha() + (c2.alpha() - c1.alpha()) * f))


def light(c: QColor, f: float = 0.4) -> QColor:
    return mix(c, QColor(255, 255, 255, c.alpha()), f)


def dark(c: QColor, f: float = 0.4) -> QColor:
    return mix(c, QColor(0, 0, 0, c.alpha()), f)


def adjust(hexs: str, hue: float, sat: float, lig: float) -> QColor:
    c = QColor(hexs)
    h, s, l_, a = c.getHslF()
    if h < 0:
        h = 0.0
    h = (h + hue / 360.0) % 1.0
    return QColor.fromHslF(h, max(0.0, min(1.0, s * sat)), max(0.0, min(1.0, l_ * lig)), a)


class Pal:
    def __init__(self, th: dict, prm: dict) -> None:
        hu, sa, li = prm.get("hue", 0), prm.get("sat", 1), prm.get("light", 1)
        f = lambda lst: [adjust(x, hu, sa, li) for x in lst]                    # noqa: E731
        self.thread = f(th["thread"])
        k = int(prm.get("thread", 0) * len(self.thread)) % len(self.thread)
        if th["style"] not in MULTI:                 # the main colour: one of the theme's
            self.thread = self.thread[k:] + self.thread[:k]
        self.orns = f(th["orns"])
        self.body = f(th["body"])
        self.fur = f(th.get("fur", th["body"][:1]))
        self.word = QColor(th["word"])
        self.raw_bg = th["bg"]


def hn(*xs: float) -> float:
    """Deterministic hash noise in [0, 1)."""
    v = 0.0
    for i, x in enumerate(xs):
        v += x * (12.9898 + 41.17 * i)
    v = math.sin(v) * 43758.5453
    return v - math.floor(v)


def pen(c: QColor, w: float, cap=Qt.RoundCap) -> QPen:
    pn = QPen(c, max(0.35, w))
    pn.setCapStyle(cap)
    pn.setJoinStyle(Qt.RoundJoin)
    return pn


def star_path(cx: float, cy: float, r1: float, r2: float, pts: int, rot: float = -math.pi / 2):
    path = QPainterPath()
    for i in range(pts * 2):
        r = r1 if i % 2 == 0 else r2
        a = rot + i * math.pi / pts
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def soft_disc(p: QPainter, x: float, y: float, r: float, c: QColor, a_in=200, a_out=0) -> None:
    g = QRadialGradient(x, y, max(0.5, r))
    g.setColorAt(0, alpha(c, a_in))
    g.setColorAt(1, alpha(c, a_out))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(x, y), r, r)


# ---------------------------------------------------------------- backgrounds
def _bg_grad(p, W, H, S, g, cols):
    gr = QLinearGradient(0, 0, 0, H)
    for i, c in enumerate(cols):
        gr.setColorAt(i / max(1, len(cols) - 1), qc(c))
    p.fillRect(QRectF(0, 0, W, H), gr)


def _bg_rgrad(p, W, H, S, g, cols):
    gr = QRadialGradient(W / 2, H / 2, max(W, H) * 0.75)
    for i, c in enumerate(cols):
        gr.setColorAt(i / max(1, len(cols) - 1), qc(c))
    p.fillRect(QRectF(0, 0, W, H), gr)


def _bg_vignette(p, W, H, S, g, a):
    gr = QRadialGradient(W / 2, H / 2, max(W, H) * 0.72)
    gr.setColorAt(0.55, QColor(0, 0, 0, 0))
    gr.setColorAt(1.0, QColor(0, 0, 0, int(a)))
    p.fillRect(QRectF(0, 0, W, H), gr)


def _bg_stars(p, W, H, S, g, count, col):
    c = qc(col)
    p.setPen(Qt.NoPen)
    for i in range(int(count)):
        x, y = g.random() * W, g.random() ** 1.3 * H
        r = S / 600 * (0.5 + 1.3 * g.random() ** 3)
        p.setBrush(alpha(c, 90 + 165 * g.random()))
        p.drawEllipse(QPointF(x, y), r, r)
        if i % 23 == 0:
            p.setBrush(alpha(c, 200))
            p.drawPath(star_path(x, y, r * 4, r * 0.6, 4, 0))


def _bg_moon(p, W, H, S, g, x, y, r, col, crescent):
    x, y, r = x * W, y * H, r * S
    c = qc(col)
    soft_disc(p, x, y, r * 2.6, c, 60, 0)
    path = QPainterPath()
    path.addEllipse(QPointF(x, y), r, r)
    if crescent:
        cut = QPainterPath()
        cut.addEllipse(QPointF(x + r * 0.45, y - r * 0.2), r * 0.95, r * 0.95)
        path = path.subtracted(cut)
    p.setBrush(c)
    p.drawPath(path)
    if not crescent:
        p.setBrush(alpha(dark(c, 0.15), 120))
        for _ in range(4):
            a, d = g.uniform(0, TAU), g.uniform(0, r * 0.6)
            cr = r * g.uniform(0.1, 0.22)
            p.drawEllipse(QPointF(x + d * math.cos(a), y + d * math.sin(a)), cr, cr)


def _bg_sun(p, W, H, S, g, x, y, r, col):
    x, y, r = x * W, y * H, r * S
    c = qc(col)
    soft_disc(p, x, y, r * 3.2, c, 120, 0)
    p.setBrush(alpha(c, 240))
    p.drawEllipse(QPointF(x, y), r, r)


def _hill_path(W, H, base, amp, g, n=5):
    path = QPainterPath(QPointF(0, H))
    ph = [g.uniform(0, TAU) for _ in range(3)]
    steps = 24
    for i in range(steps + 1):
        x = W * i / steps
        y = base + amp * (math.sin(x / W * TAU * 0.8 + ph[0]) * 0.6
                          + math.sin(x / W * TAU * 1.7 + ph[1]) * 0.3
                          + math.sin(x / W * TAU * 3.1 + ph[2]) * 0.1)
        path.lineTo(x, y)
    path.lineTo(W, H)
    path.closeSubpath()
    return path


def _bg_hills(p, W, H, S, g, cols):
    p.setPen(Qt.NoPen)
    for i, c in enumerate(cols):
        p.setBrush(qc(c))
        p.drawPath(_hill_path(W, H, H * (0.8 + 0.07 * i), H * 0.05, g))


def _bg_dunes(p, W, H, S, g, cols):
    p.setPen(Qt.NoPen)
    for i, c in enumerate(cols):
        gr = QLinearGradient(0, H * 0.7, 0, H)
        gr.setColorAt(0, light(qc(c), 0.15))
        gr.setColorAt(1, dark(qc(c), 0.15))
        p.setBrush(gr)
        p.drawPath(_hill_path(W, H, H * (0.74 + 0.08 * i), H * 0.06, g))


def _bg_grass_bottom(p, W, H, S, g, col):
    c = qc(col)
    path = QPainterPath(QPointF(0, H))
    x = 0.0
    while x < W:
        w = S * g.uniform(0.008, 0.02)
        h = H * g.uniform(0.05, 0.15)
        path.lineTo(x, H - H * 0.03)
        path.quadTo(x + w * 0.3, H - h * 0.6, x + w * g.uniform(-0.6, 1.6), H - h)
        path.lineTo(x + w, H - H * 0.03)
        x += w
    path.lineTo(W, H)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPath(path)


def _bg_field(p, W, H, S, g, c1, c2):
    p.fillRect(QRectF(0, 0, W, H), qc(c1))
    p.save()
    p.translate(W / 2, H / 2)
    p.rotate(g.uniform(-30, 30))
    d = max(W, H) * 1.5
    step = S * 0.09
    p.setPen(Qt.NoPen)
    p.setBrush(alpha(qc(c2), 140))
    y = -d / 2
    while y < d / 2:
        p.drawRect(QRectF(-d / 2, y, d, step / 2))
        y += step
    p.restore()
    tuft = QPainterPath()
    for _ in range(260):
        x, y = g.random() * W, g.random() * H
        h = S * g.uniform(0.008, 0.016)
        for k in (-1, 0, 1):
            tuft.moveTo(x, y)
            tuft.lineTo(x + k * h * 0.5, y - h)
    p.setPen(pen(dark(qc(c1), 0.25), S / 600 * 1.0))
    p.drawPath(tuft)


def _bg_bokeh(p, W, H, S, g, count, cols, a):
    for _ in range(int(count)):
        c = qc(g.choice(cols))
        soft_disc(p, g.random() * W, g.random() * H, S * g.uniform(0.02, 0.075), c, a, 0)


def _bg_clouds(p, W, H, S, g, count, col, ymax):
    c = qc(col)
    p.setPen(Qt.NoPen)
    for _ in range(int(count)):
        x, y = g.random() * W, g.random() * H * ymax
        s = S * g.uniform(0.04, 0.08)
        p.setBrush(alpha(c, g.uniform(150, 220)))
        path = QPainterPath()
        for k in range(5):
            path.addEllipse(QPointF(x + (k - 2) * s * 0.8, y - s * 0.35 * (k % 2) * (1 + (k == 2))),
                            s * (0.8 + 0.2 * (k % 2)), s * 0.7)
        path.setFillRule(Qt.WindingFill)
        p.drawPath(path.simplified())


def _bg_aurora(p, W, H, S, g, cols):
    for i, col in enumerate(cols):
        c = qc(col)
        y0 = H * (0.18 + 0.1 * i)
        amp = H * 0.06
        ph = g.uniform(0, TAU)
        top = QPainterPath()
        pts = []
        for k in range(25):
            x = W * k / 24
            pts.append(QPointF(x, y0 + amp * math.sin(x / W * TAU * 1.2 + ph)))
        top.moveTo(pts[0])
        for q in pts[1:]:
            top.lineTo(q)
        for q in reversed(pts):
            top.lineTo(q.x(), q.y() + H * 0.22)
        top.closeSubpath()
        gr = QLinearGradient(0, y0 - amp, 0, y0 + H * 0.25)
        gr.setColorAt(0, alpha(c, 0))
        gr.setColorAt(0.25, alpha(c, 110))
        gr.setColorAt(1, alpha(c, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(gr)
        p.drawPath(top)


def _bg_snow(p, W, H, S, g, count, col):
    c = qc(col)
    p.setPen(Qt.NoPen)
    for _ in range(int(count)):
        r = S / 600 * g.uniform(0.8, 2.6)
        p.setBrush(alpha(c, g.uniform(120, 230)))
        p.drawEllipse(QPointF(g.random() * W, g.random() * H), r, r)


def _bg_petals(p, W, H, S, g, count, col):
    c = qc(col)
    p.setPen(Qt.NoPen)
    for _ in range(int(count)):
        p.save()
        p.translate(g.random() * W, g.random() * H)
        p.rotate(g.uniform(0, 360))
        s = S * g.uniform(0.006, 0.012)
        p.setBrush(alpha(c, g.uniform(150, 230)))
        p.drawEllipse(QRectF(-s, -s * 0.6, s * 2, s * 1.2))
        p.restore()


def _bg_leaves_fall(p, W, H, S, g, count, cols):
    for _ in range(int(count)):
        orn_maple(p, g.random() * W, g.random() * H, S * g.uniform(0.012, 0.022),
                  alpha(qc(g.choice(cols)), 170), g.uniform(0, TAU), S / 600)


def _bg_rays(p, W, H, S, g, col):
    c = qc(col)
    p.setPen(Qt.NoPen)
    for _ in range(6):
        x = g.random() * W
        w = S * g.uniform(0.03, 0.09)
        dx = W * g.uniform(-0.25, 0.25)
        gr = QLinearGradient(0, 0, 0, H)
        gr.setColorAt(0, alpha(c, 45))
        gr.setColorAt(1, alpha(c, 0))
        p.setBrush(gr)
        p.drawPolygon(QPolygonF([QPointF(x - w, 0), QPointF(x + w, 0),
                                 QPointF(x + dx + w * 2.5, H), QPointF(x + dx - w * 2.5, H)]))


def _bg_particles(p, W, H, S, g, count, col):
    c = qc(col)
    p.setPen(Qt.NoPen)
    for _ in range(int(count)):
        r = S / 600 * g.uniform(0.6, 1.8)
        p.setBrush(alpha(c, g.uniform(50, 160)))
        p.drawEllipse(QPointF(g.random() * W, g.random() * H), r, r)


def _bg_checks(p, W, H, S, g, c1, c2, size):
    p.fillRect(QRectF(0, 0, W, H), qc(c2))
    st = S * size
    p.setPen(Qt.NoPen)
    p.setBrush(alpha(qc(c1), 110))
    x = 0.0
    while x < W:
        p.drawRect(QRectF(x, 0, st / 2, H))
        x += st
    y = 0.0
    while y < H:
        p.drawRect(QRectF(0, y, W, st / 2))
        y += st


def _bg_plate(p, W, H, S, g, rim, inner):
    cx, cy, r = W / 2, H / 2, S * 0.48
    soft_disc(p, cx + S * 0.01, cy + S * 0.015, r * 1.06, QColor(0, 0, 0), 90, 0)
    p.setBrush(qc(rim))
    p.setPen(pen(QColor(0, 0, 0, 40), S / 600))
    p.drawEllipse(QPointF(cx, cy), r, r)
    gr = QRadialGradient(cx, cy, r * 0.8)
    gr.setColorAt(0, qc(inner))
    gr.setColorAt(1, dark(qc(inner), 0.06))
    p.setBrush(gr)
    p.drawEllipse(QPointF(cx, cy), r * 0.78, r * 0.78)


def _bg_pcb(p, W, H, S, g, col):
    c = qc(col)
    path = QPainterPath()
    pads = []
    for _ in range(40):
        x, y = g.random() * W, g.random() * H
        path.moveTo(x, y)
        for _k in range(g.randint(2, 4)):
            if g.random() < 0.5:
                x += g.uniform(-0.2, 0.2) * S
            else:
                y += g.uniform(-0.2, 0.2) * S
            path.lineTo(x, y)
        pads.append((x, y))
    p.setPen(pen(c, S / 600 * 2.2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(pen(light(c, 0.2), S / 600 * 1.6))
    for x, y in pads:
        p.drawEllipse(QPointF(x, y), S * 0.006, S * 0.006)


def _bg_glass(p, W, H, S, g, cols):
    n = 7
    pts = [[QPointF(W * i / (n - 1) + (g.uniform(-0.3, 0.3) * W / n if 0 < i < n - 1 else 0),
                    H * j / (n - 1) + (g.uniform(-0.3, 0.3) * H / n if 0 < j < n - 1 else 0))
             for i in range(n)] for j in range(n)]
    for j in range(n - 1):
        for i in range(n - 1):
            poly = QPolygonF([pts[j][i], pts[j][i + 1], pts[j + 1][i + 1], pts[j + 1][i]])
            p.setBrush(alpha(qc(g.choice(cols)), 200))
            p.setPen(pen(QColor(10, 8, 6, 220), S / 600 * 4))
            p.drawPolygon(poly)


def _hexagon(cx, cy, r):
    return QPolygonF([QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
                      for a in [k * TAU / 6 for k in range(6)]])


def _bg_honeycomb(p, W, H, S, g, line, fill):
    r = S * 0.065
    dx, dy = r * 1.5, r * math.sqrt(3)
    i = 0
    x = -r
    while x < W + r:
        y = -dy + (dy / 2 if i % 2 else 0)
        while y < H + dy:
            p.setBrush(alpha(qc(fill), g.uniform(40, 170)))
            p.setPen(pen(qc(line), S / 600 * 3))
            p.drawPolygon(_hexagon(x, y, r * 0.96))
            y += dy
        x += dx
        i += 1


def _bg_lava(p, W, H, S, g, cols):
    for _ in range(9):
        c = qc(g.choice(cols))
        soft_disc(p, g.random() * W, H * g.uniform(0.75, 1.05), S * g.uniform(0.08, 0.2), c, 150, 0)
    path = QPainterPath()
    for _ in range(8):
        x, y = g.random() * W, H * g.uniform(0.8, 1.0)
        path.moveTo(x, y)
        for _k in range(4):
            x += S * g.uniform(-0.05, 0.05)
            y += S * g.uniform(-0.03, 0.03)
            path.lineTo(x, y)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen(alpha(qc(cols[1]), 160), S / 600 * 1.5))
    p.drawPath(path)


def _bg_kelp(p, W, H, S, g, count, cols):
    for i in range(int(count)):
        x0 = W * (i + g.random()) / count
        c = qc(g.choice(cols))
        path = QPainterPath(QPointF(x0, H))
        ph = g.uniform(0, TAU)
        top = H * g.uniform(0.05, 0.4)
        y = H
        while y > top:
            y -= S * 0.04
            path.lineTo(x0 + math.sin(y / S * 9 + ph) * S * 0.02, y)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen(alpha(c, 200), S / 600 * 6))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(alpha(c, 170))
        y = H
        k = 0
        while y > top + S * 0.05:
            y -= S * 0.07
            xx = x0 + math.sin(y / S * 9 + ph) * S * 0.02
            side = 1 if k % 2 else -1
            p.drawEllipse(QRectF(xx + (0 if side > 0 else -S * 0.05), y - S * 0.01, S * 0.05,
                                 S * 0.02))
            k += 1


def _bg_floor(p, W, H, S, g, cols):
    y0 = H * 0.74
    rows = 5
    for r_ in range(rows):
        ya = y0 + (H - y0) * (r_ / rows) ** 1.4
        yb = y0 + (H - y0) * ((r_ + 1) / rows) ** 1.4
        n = 6 + r_ * 2
        for k in range(n):
            p.setPen(pen(QColor(0, 0, 0, 120), S / 600))
            p.setBrush(alpha(qc(g.choice(cols)), g.uniform(60, 170)))
            xa, xb = W * k / n, W * (k + 1) / n
            p.drawRect(QRectF(xa, ya, xb - xa, yb - ya))


def _bg_beams(p, W, H, S, g, cols):
    p.setPen(Qt.NoPen)
    for i, col in enumerate(cols):
        x = W * (0.2 + 0.3 * i) + g.uniform(-0.05, 0.05) * W
        gr = QLinearGradient(0, 0, 0, H)
        gr.setColorAt(0, alpha(qc(col), 70))
        gr.setColorAt(1, alpha(qc(col), 0))
        p.setBrush(gr)
        dx = g.uniform(-0.35, 0.35) * W
        p.drawPolygon(QPolygonF([QPointF(x - S * 0.01, 0), QPointF(x + S * 0.01, 0),
                                 QPointF(x + dx + S * 0.12, H), QPointF(x + dx - S * 0.12, H)]))


def _bg_paper(p, W, H, S, g, col):
    c = qc(col)
    path = QPainterPath()
    for _ in range(160):
        x, y = g.random() * W, g.random() * H
        a = g.uniform(0, TAU)
        l_ = S * g.uniform(0.005, 0.02)
        path.moveTo(x, y)
        path.lineTo(x + l_ * math.cos(a), y + l_ * math.sin(a))
    p.setPen(pen(alpha(c, 70), S / 600 * 0.8))
    p.drawPath(path)
    p.setPen(pen(alpha(c, 60), S / 600 * 1.2))
    for _ in range(3):
        x = g.random() * W
        p.drawLine(QPointF(x, 0), QPointF(x + g.uniform(-0.4, 0.4) * W, H))


def _bg_swirl(p, W, H, S, g, cols):
    gr = QConicalGradient(W / 2, H / 2, g.uniform(0, 360))
    cl = list(cols) * 2
    for i, c in enumerate(cl + [cl[0]]):
        gr.setColorAt(i / len(cl), qc(c))
    p.fillRect(QRectF(0, 0, W, H), gr)
    rg = QRadialGradient(W / 2, H / 2, S * 0.7)
    rg.setColorAt(0, QColor(255, 255, 255, 150))
    rg.setColorAt(0.25, QColor(255, 255, 255, 30))
    rg.setColorAt(0.5, QColor(255, 255, 255, 70))
    rg.setColorAt(0.75, QColor(255, 255, 255, 10))
    rg.setColorAt(1, QColor(255, 255, 255, 50))
    p.fillRect(QRectF(0, 0, W, H), rg)


def _bg_galaxy(p, W, H, S, g, cols):
    cx, cy = W * g.uniform(0.35, 0.65), H * g.uniform(0.35, 0.65)
    soft_disc(p, cx, cy, S * 0.35, qc(cols[0]), 90, 0)
    soft_disc(p, cx, cy, S * 0.12, qc("#ffffff"), 120, 0)
    p.setPen(Qt.NoPen)
    rot = g.uniform(0, TAU)
    for arm in range(2):
        for k in range(90):
            t = k / 90
            a = rot + arm * math.pi + t * 3.4
            r = S * (0.04 + 0.42 * t)
            x = cx + r * math.cos(a) + g.gauss(0, S * 0.02)
            y = cy + r * math.sin(a) * 0.7 + g.gauss(0, S * 0.02)
            c = qc(cols[k % len(cols)])
            p.setBrush(alpha(c, 140 * (1 - t) + 40))
            rr = S / 600 * g.uniform(0.8, 2.4)
            p.drawEllipse(QPointF(x, y), rr, rr)


def _bg_cave(p, W, H, S, g, col):
    c = qc(col)
    path = QPainterPath(QPointF(0, 0))
    x = 0.0
    while x < W:
        w = S * g.uniform(0.04, 0.1)
        path.lineTo(x, H * 0.03)
        path.lineTo(x + w / 2, H * g.uniform(0.06, 0.2))
        path.lineTo(x + w, H * 0.03)
        x += w
    path.lineTo(W, 0)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPath(path)
    p.drawPath(_hill_path(W, H, H * 0.93, H * 0.03, g))


def _bg_bigleaves(p, W, H, S, g, cols):
    for i in range(7):
        c = qc(g.choice(cols))
        edge = i % 4
        x = (0 if edge == 0 else W if edge == 1 else g.random() * W)
        y = (g.random() * H if edge < 2 else (0 if edge == 2 else H))
        p.save()
        p.translate(x, y)
        p.rotate(math.degrees(math.atan2(H / 2 - y, W / 2 - x)) + g.uniform(-30, 30))
        L = S * g.uniform(0.18, 0.3)
        leaf = QPainterPath(QPointF(0, 0))
        leaf.quadTo(L * 0.5, -L * 0.35, L, 0)
        leaf.quadTo(L * 0.5, L * 0.35, 0, 0)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPath(leaf)
        p.setPen(pen(light(c, 0.2), S / 600 * 1.5))
        p.drawLine(QPointF(0, 0), QPointF(L * 0.95, 0))
        p.restore()


def _bg_rain(p, W, H, S, g, count, col):
    path = QPainterPath()
    for _ in range(int(count)):
        x, y = g.random() * W, g.random() * H
        l_ = S * g.uniform(0.015, 0.035)
        path.moveTo(x, y)
        path.lineTo(x - l_ * 0.25, y + l_)
    p.setPen(pen(alpha(qc(col), 70), S / 600 * 1.0))
    p.drawPath(path)


def _bg_blots(p, W, H, S, g, count, cols):
    p.setPen(Qt.NoPen)
    for _ in range(int(count)):
        c = qc(g.choice(cols))
        x, y = g.random() * W, g.random() * H
        r = S * g.uniform(0.08, 0.2)
        for layer in range(2):
            path = QPainterPath()
            m = 14
            for k in range(m + 1):
                a = k * TAU / m
                rr = r * (0.8 + 0.25 * g.random()) * (1 - 0.15 * layer)
                q = QPointF(x + rr * math.cos(a), y + rr * math.sin(a))
                path.moveTo(q) if k == 0 else path.lineTo(q)
            p.setBrush(alpha(c, 55))
            p.drawPath(path)


def _bg_staff(p, W, H, S, g, col):
    p.setPen(pen(alpha(qc(col), 170), S / 600 * 1.3))
    for y0 in (H * 0.08, H * 0.86):
        for k in range(5):
            y = y0 + k * S * 0.016
            p.drawLine(QPointF(0, y), QPointF(W, y))


def _bg_diamonds(p, W, H, S, g, col):
    path = QPainterPath()
    st = S * 0.08
    k = -H
    while k < W + H:
        path.moveTo(k, 0)
        path.lineTo(k + H, H)
        path.moveTo(k + H, 0)
        path.lineTo(k, H)
        k += st
    p.setPen(pen(alpha(qc(col), 160), S / 600 * 1.0))
    p.drawPath(path)


def _bg_lights(p, W, H, S, g, cols):
    for row in range(2):
        y0 = H * (0.04 + 0.1 * row)
        sag = H * 0.08
        path = QPainterPath(QPointF(-10, y0))
        path.quadTo(W / 2, y0 + 2 * sag, W + 10, y0)
        p.setPen(pen(QColor(30, 30, 30, 200), S / 600 * 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        for k in range(12):
            t = (k + 0.5) / 12
            pt = path.pointAtPercent(t)
            c = qc(cols[(k + row) % len(cols)])
            soft_disc(p, pt.x(), pt.y() + S * 0.01, S * 0.03, c, 120, 0)
            p.setBrush(c)
            p.drawEllipse(QPointF(pt.x(), pt.y() + S * 0.01), S * 0.007, S * 0.009)


def _bg_stripes(p, W, H, S, g, cols):
    st = S * 0.06
    x = 0.0
    k = 0
    while x < W:
        p.fillRect(QRectF(x, 0, st, H), qc(cols[k % len(cols)]))
        x += st
        k += 1


def _bg_rug(p, W, H, S, g, cols):
    cx, cy = W / 2, H / 2
    p.setPen(Qt.NoPen)
    for k in range(24, 0, -1):          # filled rings from the outside in (fast)
        r = S * 0.025 * k + S * 0.015
        c = qc(cols[(k // 2) % len(cols)]) if k % 2 == 0 else qc(cols[-1])
        p.setBrush(alpha(c, 150) if k % 2 == 0 else alpha(c, 90))
        p.drawEllipse(QPointF(cx, cy), r, r * 0.9)


def _bg_soil(p, W, H, S, g, cols):
    _bg_grad(p, W, H, S, g, cols)
    p.setPen(Qt.NoPen)
    for _ in range(40):
        p.setBrush(alpha(light(qc(cols[-1]), 0.15), g.uniform(60, 160)))
        r = S * g.uniform(0.004, 0.015)
        p.drawEllipse(QPointF(g.random() * W, g.random() * H), r * 1.3, r)
    path = QPainterPath()
    for _ in range(9):
        x, y = g.random() * W, H * 0.12
        path.moveTo(x, y)
        for _k in range(6):
            x += S * g.uniform(-0.04, 0.04)
            y += S * g.uniform(0.02, 0.06)
            path.lineTo(x, y)
    p.setPen(pen(alpha(QColor("#6b4a32"), 160), S / 600 * 2.5))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def _bg_moss(p, W, H, S, g, col):
    c = qc(col)
    path = QPainterPath(QPointF(0, 0))
    x = 0.0
    while x <= W:
        path.lineTo(x, H * 0.1 + S * g.uniform(-0.01, 0.015))
        x += S * 0.02
    path.lineTo(W, 0)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPath(path)
    p.setBrush(light(c, 0.2))
    for _ in range(30):
        r = S * g.uniform(0.008, 0.02)
        p.drawEllipse(QPointF(g.random() * W, H * 0.1 - r * 0.3), r, r * 0.7)


def _bg_water(p, W, H, S, g, col):
    c = qc(col)
    p.setBrush(Qt.NoBrush)
    for _ in range(18):
        x, y = g.random() * W, H * g.uniform(0.45, 1.0)
        w = S * g.uniform(0.04, 0.12)
        p.setPen(pen(alpha(c, g.uniform(50, 120)), S / 600 * 1.4))
        p.drawArc(QRectF(x - w, y - w * 0.12, 2 * w, w * 0.24), 0, 180 * 16)


def _bg_knit(p, W, H, S, g, col):
    path = []
    st = S * 0.035
    y = 0.0
    while y < H:
        x = 0.0
        while x < W:
            path.append(QLineF(x, y, x + st * 0.5, y + st))
            path.append(QLineF(x + st, y, x + st * 0.5, y + st))
            x += st
        y += st * 0.8
    p.setPen(pen(alpha(qc(col), 200), S / 600 * 2.2, Qt.FlatCap))
    p.drawLines(path)


def _gear_path(cx, cy, r, teeth, rot=0.0):
    path = QPainterPath()
    m = teeth * 4
    for k in range(m + 1):
        a = rot + k * TAU / m
        rr = r if (k % 4) in (0, 1) else r * 0.82
        q = QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a))
        path.moveTo(q) if k == 0 else path.lineTo(q)
    path.closeSubpath()
    path.addEllipse(QPointF(cx, cy), r * 0.3, r * 0.3)
    return path


def _bg_gears(p, W, H, S, g, col):
    c = qc(col)
    for _ in range(4):
        x, y = g.choice((0.08, 0.92)) * W, g.random() * H
        r = S * g.uniform(0.08, 0.16)
        p.setPen(pen(alpha(c, 140), S / 600 * 2))
        p.setBrush(alpha(c, 60))
        p.drawPath(_gear_path(x, y, r, g.randint(8, 12), g.uniform(0, 1)))


def _bg_fog(p, W, H, S, g, col):
    for _ in range(6):
        soft_disc(p, g.random() * W, H * g.uniform(0.75, 1.0), S * g.uniform(0.15, 0.3),
                  qc(col), 50, 0)


def _bg_milky(p, W, H, S, g, col):
    c = qc(col)
    p.save()
    p.translate(W / 2, H / 2)
    p.rotate(g.uniform(-50, -20))
    gr = QLinearGradient(0, -S * 0.15, 0, S * 0.15)
    gr.setColorAt(0, alpha(c, 0))
    gr.setColorAt(0.5, alpha(c, 50))
    gr.setColorAt(1, alpha(c, 0))
    p.fillRect(QRectF(-W, -S * 0.15, 2 * W, S * 0.3), gr)
    p.setPen(Qt.NoPen)
    for _ in range(140):
        p.setBrush(alpha(QColor(255, 255, 255), g.uniform(40, 160)))
        r = S / 600 * g.uniform(0.4, 1.2)
        p.drawEllipse(QPointF(g.uniform(-W, W), g.gauss(0, S * 0.06)), r, r)
    p.restore()


def _bg_branch(p, W, H, S, g, col):
    c = qc(col)
    path = QPainterPath(QPointF(-5, H * 0.12))
    path.quadTo(W * 0.25, H * 0.05, W * 0.45, H * 0.14)
    path.moveTo(W * 0.2, H * 0.09)
    path.quadTo(W * 0.27, H * 0.18, W * 0.3, H * 0.24)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen(c, S / 600 * 6))
    p.drawPath(path)
    for k in range(9):
        q = path.pointAtPercent(g.random())
        orn_blossom(p, q.x() + S * g.uniform(-0.02, 0.02), q.y() + S * g.uniform(-0.02, 0.02),
                    S * 0.016, QColor("#ffc1d4"), g.uniform(0, TAU), S / 600)


def _bg_rainbow_arc(p, W, H, S, g):
    cols = ["#ff595e", "#ff924c", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93"]
    p.setBrush(Qt.NoBrush)
    for k, c in enumerate(cols):
        r = S * (0.75 - 0.03 * k)
        p.setPen(pen(alpha(qc(c), 90), S * 0.03, Qt.FlatCap))
        p.drawArc(QRectF(W / 2 - r, H * 1.05 - r, 2 * r, 2 * r), 0, 180 * 16)


BACKGROUNDS = {
    "grad": _bg_grad, "rgrad": _bg_rgrad, "vignette": _bg_vignette, "stars": _bg_stars,
    "moon": _bg_moon, "sun": _bg_sun, "hills": _bg_hills, "dunes": _bg_dunes,
    "grass_bottom": _bg_grass_bottom, "field": _bg_field, "bokeh": _bg_bokeh,
    "clouds": _bg_clouds, "aurora": _bg_aurora, "snow": _bg_snow, "petals": _bg_petals,
    "leaves_fall": _bg_leaves_fall, "rays": _bg_rays, "particles": _bg_particles,
    "checks": _bg_checks, "plate": _bg_plate, "pcb": _bg_pcb, "glass": _bg_glass,
    "honeycomb": _bg_honeycomb, "lava": _bg_lava, "kelp": _bg_kelp, "floor": _bg_floor,
    "beams": _bg_beams, "paper": _bg_paper, "swirl": _bg_swirl, "galaxy": _bg_galaxy,
    "cave": _bg_cave, "bigleaves": _bg_bigleaves, "rain": _bg_rain, "blots": _bg_blots,
    "staff": _bg_staff, "diamonds": _bg_diamonds, "lights": _bg_lights,
    "stripes": _bg_stripes, "rug": _bg_rug, "soil": _bg_soil, "moss": _bg_moss,
    "water": _bg_water, "knit": _bg_knit, "gears": _bg_gears, "fog": _bg_fog,
    "milky": _bg_milky, "branch": _bg_branch, "rainbow_arc": _bg_rainbow_arc,
}


# ------------------------------------------------------------------ ornaments
# (p, x, y, s = radius in px, colour, angle, u = pixels per unit at 600 px)
def orn_dew(p, x, y, s, c, a, u):
    g = QRadialGradient(x - s * 0.35, y - s * 0.4, s * 1.3)
    g.setColorAt(0, QColor(255, 255, 255, 240))
    g.setColorAt(0.45, alpha(light(c, 0.3), 170))
    g.setColorAt(1, alpha(c, 90))
    p.setBrush(g)
    p.setPen(pen(alpha(light(c, 0.5), 160), u * 0.6))
    p.drawEllipse(QPointF(x, y), s, s * 1.08)


def orn_gem(p, x, y, s, c, a, u):
    poly = QPolygonF([QPointF(x + s * 1.2 * math.cos(a + k * TAU / 6),
                              y + s * 1.2 * math.sin(a + k * TAU / 6)) for k in range(6)])
    p.setBrush(c)
    p.setPen(pen(dark(c, 0.35), u * 0.7))
    p.drawPolygon(poly)
    p.setPen(pen(alpha(light(c, 0.6), 200), u * 0.5))
    for k in range(0, 6, 2):
        p.drawLine(QPointF(x, y), poly[k])
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 210))
    p.drawEllipse(QPointF(x - s * 0.35, y - s * 0.4), s * 0.25, s * 0.25)


def orn_spark(p, x, y, s, c, a, u):
    p.setPen(Qt.NoPen)
    soft_disc(p, x, y, s * 2.0, c, 90, 0)
    p.setBrush(light(c, 0.3))
    p.drawPath(star_path(x, y, s * 1.6, s * 0.35, 4, a * 0.2))


def orn_snowflake(p, x, y, s, c, a, u):
    path = QPainterPath()
    for k in range(6):
        ang = a + k * TAU / 6
        ex, ey = x + s * 1.4 * math.cos(ang), y + s * 1.4 * math.sin(ang)
        path.moveTo(x, y)
        path.lineTo(ex, ey)
        mx, my = x + s * 0.8 * math.cos(ang), y + s * 0.8 * math.sin(ang)
        for d in (-0.6, 0.6):
            path.moveTo(mx, my)
            path.lineTo(mx + s * 0.45 * math.cos(ang + d), my + s * 0.45 * math.sin(ang + d))
    p.setPen(pen(c, max(0.6 * u, s * 0.18)))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def orn_star(p, x, y, s, c, a, u):
    soft_disc(p, x, y, s * 2.2, c, 70, 0)
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawPath(star_path(x, y, s * 1.3, s * 0.55, 5, -math.pi / 2 + a * 0.1))


def orn_eye(p, x, y, s, c, a, u):
    p.setPen(Qt.NoPen)
    for f, col in ((1.3, QColor("#2ec4b6")), (1.0, QColor("#ffd166")), (0.7, c),
                   (0.35, QColor("#0b1f2e"))):
        p.setBrush(col)
        p.drawEllipse(QPointF(x, y), s * f, s * f * 1.15)


def orn_ember(p, x, y, s, c, a, u):
    soft_disc(p, x, y, s * 2.4, c, 130, 0)
    soft_disc(p, x, y, s * 0.8, light(c, 0.6), 255, 120)


def orn_glowdot(p, x, y, s, c, a, u):
    soft_disc(p, x, y, s * 2.6, c, 120, 0)
    p.setBrush(light(c, 0.7))
    p.drawEllipse(QPointF(x, y), s * 0.55, s * 0.55)


def orn_puff(p, x, y, s, c, a, u):
    p.setPen(Qt.NoPen)
    p.setBrush(alpha(c, 230))
    for dx, dy, r in ((-0.6, 0.15, 0.75), (0.6, 0.15, 0.75), (0, -0.25, 0.95)):
        p.drawEllipse(QPointF(x + dx * s, y + dy * s), r * s, r * s)


def orn_crane(p, x, y, s, c, a, u):
    p.save()
    p.translate(x, y)
    p.rotate(math.degrees(a) * 0.15)
    p.setPen(pen(dark(c, 0.3), u * 0.5))
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(-s * 1.6, -s * 0.2), QPointF(0, s * 0.5),
                             QPointF(s * 1.6, -s * 0.9), QPointF(s * 0.2, -s * 0.1)]))
    p.setBrush(light(c, 0.3))
    p.drawPolygon(QPolygonF([QPointF(-s * 0.3, 0), QPointF(s * 0.5, -s * 1.5),
                             QPointF(s * 0.4, s * 0.3)]))
    p.restore()


def orn_led(p, x, y, s, c, a, u):
    soft_disc(p, x, y, s * 2.2, c, 120, 0)
    p.setPen(pen(QColor("#c0c8d0"), u * 0.6))
    p.setBrush(c)
    p.drawRoundedRect(QRectF(x - s * 0.8, y - s * 0.55, s * 1.6, s * 1.1), s * 0.2, s * 0.2)


def orn_blossom(p, x, y, s, c, a, u):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    for k in range(5):
        ang = a + k * TAU / 5
        p.drawEllipse(QPointF(x + s * 0.65 * math.cos(ang), y + s * 0.65 * math.sin(ang)),
                      s * 0.6, s * 0.6)
    p.setBrush(QColor("#ffe08a"))
    p.drawEllipse(QPointF(x, y), s * 0.32, s * 0.32)


def orn_sprinkle(p, x, y, s, c, a, u):
    p.setPen(pen(c, s * 0.7))
    p.drawLine(QPointF(x - s * math.cos(a), y - s * math.sin(a)),
               QPointF(x + s * math.cos(a), y + s * math.sin(a)))


def orn_daisy(p, x, y, s, c, a, u):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    for k in range(8):
        ang = a + k * TAU / 8
        p.save()
        p.translate(x + s * 0.7 * math.cos(ang), y + s * 0.7 * math.sin(ang))
        p.rotate(math.degrees(ang))
        p.drawEllipse(QRectF(-s * 0.55, -s * 0.22, s * 1.1, s * 0.44))
        p.restore()
    p.setBrush(QColor("#ffc93c"))
    p.drawEllipse(QPointF(x, y), s * 0.38, s * 0.38)


def orn_wisp(p, x, y, s, c, a, u):
    path = QPainterPath(QPointF(x - s, y + s))
    path.lineTo(x - s, y)
    path.arcTo(QRectF(x - s, y - s, 2 * s, 2 * s), 180, -180)
    path.lineTo(x + s, y + s)
    for k in range(3):
        path.quadTo(x + s - (k + 0.5) * 2 * s / 3, y + s * 0.6, x + s - (k + 1) * 2 * s / 3, y + s)
    p.setPen(Qt.NoPen)
    p.setBrush(alpha(c, 220))
    p.drawPath(path)
    p.setBrush(QColor(60, 50, 90))
    p.drawEllipse(QPointF(x - s * 0.35, y - s * 0.1), s * 0.16, s * 0.2)
    p.drawEllipse(QPointF(x + s * 0.35, y - s * 0.1), s * 0.16, s * 0.2)


def orn_cog(p, x, y, s, c, a, u):
    p.setPen(pen(dark(c, 0.4), u * 0.5))
    p.setBrush(c)
    path = _gear_path(x, y, s * 1.3, 8, a)
    path.setFillRule(Qt.OddEvenFill)
    p.drawPath(path)


def orn_yarnball(p, x, y, s, c, a, u):
    r = s * 1.3
    p.setPen(pen(dark(c, 0.3), u * 0.6))
    p.setBrush(c)
    p.drawEllipse(QPointF(x, y), r, r)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen(dark(c, 0.25), u * 0.6))
    for k in range(3):
        p.drawArc(QRectF(x - r * (0.4 + 0.25 * k), y - r, r * (0.8 + 0.5 * k), 2 * r),
                  int((60 + 30 * k + math.degrees(a)) * 16), 140 * 16)
    p.setPen(pen(c, u * 0.8))
    p.drawLine(QPointF(x + r * 0.8, y + r * 0.5), QPointF(x + r * 1.6, y + r * 1.2))


def orn_mirror(p, x, y, s, c, a, u):
    p.save()
    p.translate(x, y)
    p.rotate(45 + math.degrees(a) * 0.1)
    p.setPen(pen(QColor(80, 80, 110), u * 0.4))
    p.setBrush(c)
    p.drawRect(QRectF(-s * 0.8, -s * 0.8, s * 1.6, s * 1.6))
    p.setPen(pen(QColor(255, 255, 255, 220), u * 0.5))
    p.drawLine(QPointF(-s * 0.5, -s * 0.2), QPointF(-s * 0.2, -s * 0.5))
    p.restore()


def orn_scoop(p, x, y, s, c, a, u):
    r = s * 1.2
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(x, y), r, r)
    p.drawEllipse(QPointF(x - r * 0.4, y + r * 0.75), r * 0.35, r * 0.35)
    p.setBrush(QColor(255, 255, 255, 160))
    p.drawEllipse(QPointF(x - r * 0.35, y - r * 0.4), r * 0.28, r * 0.2)


def orn_maple(p, x, y, s, c, a, u):
    path = QPainterPath()
    pts = [(0, -1.4), (0.35, -0.7), (1.0, -0.95), (0.8, -0.3), (1.35, 0.0), (0.5, 0.35),
           (0.6, 0.8), (0, 0.5), (-0.6, 0.8), (-0.5, 0.35), (-1.35, 0.0), (-0.8, -0.3),
           (-1.0, -0.95), (-0.35, -0.7)]
    ca, sa = math.cos(a), math.sin(a)
    for i, (px, py) in enumerate(pts):
        q = QPointF(x + s * (px * ca - py * sa), y + s * (px * sa + py * ca))
        path.moveTo(q) if i == 0 else path.lineTo(q)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPath(path)
    p.setPen(pen(dark(c, 0.3), u * 0.6))
    p.drawLine(QPointF(x, y), QPointF(x - s * 1.2 * sa, y + s * 1.2 * ca))


def orn_bubble(p, x, y, s, c, a, u):
    r = s * 1.4
    g = QRadialGradient(x, y, r)
    g.setColorAt(0.7, alpha(c, 30))
    g.setColorAt(1.0, alpha(light(c, 0.3), 160))
    p.setBrush(g)
    p.setPen(pen(alpha(light(c, 0.5), 200), u * 0.6))
    p.drawEllipse(QPointF(x, y), r, r)
    p.setPen(pen(QColor(255, 255, 255, 220), u * 0.8))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(x - r * 0.7, y - r * 0.7, r * 1.4, r * 1.4), 100 * 16, 60 * 16)


def orn_firefly(p, x, y, s, c, a, u):
    soft_disc(p, x, y, s * 3.0, c, 140, 0)
    p.setBrush(QColor(40, 40, 30))
    p.drawEllipse(QPointF(x - s * 0.5, y), s * 0.45, s * 0.35)
    p.setBrush(light(c, 0.5))
    p.drawEllipse(QPointF(x + s * 0.2, y), s * 0.5, s * 0.45)


def orn_leaf(p, x, y, s, c, a, u):
    p.save()
    p.translate(x, y)
    p.rotate(math.degrees(a))
    leaf = QPainterPath(QPointF(-s * 1.4, 0))
    leaf.quadTo(0, -s * 1.1, s * 1.4, 0)
    leaf.quadTo(0, s * 1.1, -s * 1.4, 0)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPath(leaf)
    p.setPen(pen(light(c, 0.35), u * 0.5))
    p.drawLine(QPointF(-s * 1.3, 0), QPointF(s * 1.2, 0))
    p.restore()


def orn_note(p, x, y, s, c, a, u):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.save()
    p.translate(x, y + s * 0.6)
    p.rotate(-25)
    p.drawEllipse(QRectF(-s * 0.7, -s * 0.45, s * 1.4, s * 0.9))
    p.restore()
    p.setPen(pen(c, u * 0.9))
    p.drawLine(QPointF(x + s * 0.6, y + s * 0.5), QPointF(x + s * 0.6, y - s * 1.6))
    p.drawLine(QPointF(x + s * 0.6, y - s * 1.6), QPointF(x + s * 1.3, y - s * 0.9))


def orn_pearl(p, x, y, s, c, a, u):
    g = QRadialGradient(x - s * 0.3, y - s * 0.35, s * 1.3)
    g.setColorAt(0, QColor(255, 255, 255))
    g.setColorAt(0.6, c)
    g.setColorAt(1, dark(c, 0.2))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(x, y), s, s)


def orn_lantern(p, x, y, s, c, a, u):
    soft_disc(p, x, y, s * 2.6, c, 110, 0)
    p.setPen(pen(dark(c, 0.3), u * 0.5))
    p.setBrush(c)
    p.drawEllipse(QRectF(x - s * 0.9, y - s * 1.1, s * 1.8, s * 2.2))
    p.setBrush(QColor("#ffd166"))
    p.drawRect(QRectF(x - s * 0.5, y - s * 1.3, s, s * 0.3))
    p.drawRect(QRectF(x - s * 0.5, y + s * 1.0, s, s * 0.3))


def orn_blot(p, x, y, s, c, a, u):
    p.setPen(Qt.NoPen)
    p.setBrush(alpha(c, 110))
    p.drawEllipse(QPointF(x, y), s * 1.4, s * 1.1)
    p.setBrush(alpha(c, 90))
    p.drawEllipse(QPointF(x + s * 0.4 * math.cos(a), y + s * 0.3 * math.sin(a)), s * 0.9, s * 0.8)


def orn_meatball(p, x, y, s, c, a, u):
    r = s * 1.5
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(170, 40, 30, 150))
    p.drawEllipse(QPointF(x, y + r * 0.15), r * 1.25, r * 1.1)
    g = QRadialGradient(x - r * 0.3, y - r * 0.35, r * 1.4)
    g.setColorAt(0, light(c, 0.3))
    g.setColorAt(1, dark(c, 0.3))
    p.setBrush(g)
    p.drawEllipse(QPointF(x, y), r, r)
    p.setBrush(dark(c, 0.45))
    for k in range(4):
        ang = a + k * 1.7
        p.drawEllipse(QPointF(x + r * 0.5 * math.cos(ang), y + r * 0.5 * math.sin(ang)),
                      r * 0.13, r * 0.13)


def orn_mushroom(p, x, y, s, c, a, u):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#f5ecd7"))
    p.drawRoundedRect(QRectF(x - s * 0.35, y - s * 0.2, s * 0.7, s * 1.1), s * 0.2, s * 0.2)
    p.setBrush(c)
    p.drawChord(QRectF(x - s * 1.1, y - s * 0.9, s * 2.2, s * 1.6), 0, 180 * 16)
    p.setBrush(QColor(255, 255, 255, 220))
    p.drawEllipse(QPointF(x - s * 0.4, y - s * 0.45), s * 0.17, s * 0.17)
    p.drawEllipse(QPointF(x + s * 0.35, y - s * 0.55), s * 0.13, s * 0.13)


def orn_honeydrop(p, x, y, s, c, a, u):
    path = QPainterPath(QPointF(x, y - s * 1.4))
    path.quadTo(x + s * 1.1, y + s * 0.1, x, y + s * 0.9)
    path.quadTo(x - s * 1.1, y + s * 0.1, x, y - s * 1.4)
    g = QRadialGradient(x - s * 0.3, y, s * 1.4)
    g.setColorAt(0, light(c, 0.5))
    g.setColorAt(1, dark(c, 0.15))
    p.setPen(pen(dark(c, 0.3), u * 0.4))
    p.setBrush(g)
    p.drawPath(path)


def orn_seed(p, x, y, s, c, a, u):
    ang = -math.pi / 2 + (hn(x, y) - 0.5) * 0.8
    tx, ty = x + s * 1.6 * math.cos(ang), y + s * 1.6 * math.sin(ang)
    path = QPainterPath(QPointF(x, y))
    path.lineTo(tx, ty)
    for k in range(9):
        b = ang - 1.3 + k * 2.6 / 8
        path.moveTo(tx, ty)
        path.lineTo(tx + s * 0.9 * math.cos(b), ty + s * 0.9 * math.sin(b))
    p.setPen(pen(alpha(c, 230), u * 0.6))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#8a6a3c"))
    p.drawEllipse(QPointF(x, y), s * 0.22, s * 0.35)


def orn_kite(p, x, y, s, c, a, u):
    p.setPen(pen(dark(c, 0.3), u * 0.5))
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(x, y - s * 1.5), QPointF(x + s, y), QPointF(x, y + s * 1.8),
                             QPointF(x - s, y)]))
    p.setPen(pen(alpha(dark(c, 0.3), 200), u * 0.5))
    p.drawLine(QPointF(x, y - s * 1.5), QPointF(x, y + s * 1.8))
    p.drawLine(QPointF(x - s, y), QPointF(x + s, y))
    path = QPainterPath(QPointF(x, y + s * 1.8))
    path.cubicTo(x + s, y + s * 2.6, x - s, y + s * 3.2, x + s * 0.3, y + s * 4)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


ORNAMENTS = {
    "dew": orn_dew, "gem": orn_gem, "spark": orn_spark, "snowflake": orn_snowflake,
    "star": orn_star, "eye": orn_eye, "ember": orn_ember, "glowdot": orn_glowdot,
    "puff": orn_puff, "crane": orn_crane, "led": orn_led, "blossom": orn_blossom,
    "sprinkle": orn_sprinkle, "daisy": orn_daisy, "wisp": orn_wisp, "cog": orn_cog,
    "yarnball": orn_yarnball, "mirror": orn_mirror, "scoop": orn_scoop, "maple": orn_maple,
    "bubble": orn_bubble, "firefly": orn_firefly, "leaf": orn_leaf, "note": orn_note,
    "pearl": orn_pearl, "lantern": orn_lantern, "blot": orn_blot, "meatball": orn_meatball,
    "mushroom": orn_mushroom, "honeydrop": orn_honeydrop, "seed": orn_seed, "kite": orn_kite,
}
ORN_SCALE = {"meatball": 1.25, "yarnball": 1.1, "lantern": 1.1, "kite": 1.0, "sprinkle": 0.8,
             "glowdot": 0.7, "ember": 0.8, "firefly": 0.8, "mirror": 0.9, "seed": 1.2}


# -------------------------------------------------------------------- sprites
# Drawn in a small unit space (about -16..16) that the caller scales.
def _face(p, x, y, eye_r=2.2, gap=2.5, closed=False, cheek=True, mouth=True, lashes=False):
    if closed:
        p.setPen(pen(QColor(30, 25, 30), 0.8))
        p.setBrush(Qt.NoBrush)
        for sx in (-1, 1):
            p.drawArc(QRectF(x + sx * gap - eye_r * 0.8, y - eye_r * 0.5, eye_r * 1.6, eye_r * 1.2),
                      200 * 16, 140 * 16)
    else:
        p.setPen(Qt.NoPen)
        for sx in (-1, 1):
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(x + sx * gap, y), eye_r, eye_r * 1.08)
            p.setBrush(QColor(25, 22, 30))
            p.drawEllipse(QPointF(x + sx * gap + 0.25, y + 0.35), eye_r * 0.58, eye_r * 0.62)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(x + sx * gap - 0.25, y - 0.4), eye_r * 0.24, eye_r * 0.24)
            if lashes:
                p.setPen(pen(QColor(25, 22, 30), 0.45))
                for k in range(3):
                    a = -math.pi / 2 + sx * (0.5 + 0.35 * k)
                    p.drawLine(QPointF(x + sx * gap + eye_r * math.cos(a), y + eye_r * math.sin(a)),
                               QPointF(x + sx * gap + eye_r * 1.45 * math.cos(a),
                                       y + eye_r * 1.45 * math.sin(a)))
                p.setPen(Qt.NoPen)
    if cheek:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 120, 150, 110))
        for sx in (-1, 1):
            p.drawEllipse(QPointF(x + sx * (gap + eye_r * 0.9), y + eye_r * 1.4), 1.2, 0.75)
    if mouth:
        p.setPen(pen(QColor(30, 25, 30), 0.7))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(x - 1.2, y + eye_r * 0.7, 2.4, 1.8), 200 * 16, 140 * 16)


def _acc_back(p, acc, b, t):
    if acc == "fan":
        cols = [QColor("#ffd166"), QColor("#ff7b00"), QColor("#3a86ff"), QColor("#2ec4b6"),
                QColor("#e63946")]
        for k, c in enumerate(cols):
            r = 17 - k * 2.6
            p.setPen(pen(dark(c, 0.3), 0.4))
            p.setBrush(c)
            p.drawPie(QRectF(-r, 4 - r, 2 * r, 2 * r), 15 * 16, 150 * 16)
    elif acc == "helmet":           # a little red cape
        p.setPen(Qt.NoPen)
        p.setBrush(b[3])
        cape = QPainterPath(QPointF(-5, 0))
        cape.quadTo(-11, 12 + math.sin(t * 2) * 1.5, -6, 17)
        cape.lineTo(6, 17)
        cape.quadTo(11, 12 + math.sin(t * 2 + 1) * 1.5, 5, 0)
        p.drawPath(cape)


def _acc_front(p, acc, b, t):
    acc_c = b[3]
    if acc == "tiara":
        p.setPen(pen(QColor("#b0577f"), 0.5))
        p.setBrush(QColor("#ffd6ea"))
        p.drawPolygon(QPolygonF([QPointF(-4, -9.8), QPointF(-4.6, -13.4), QPointF(-2, -11.4),
                                 QPointF(0, -15), QPointF(2, -11.4), QPointF(4.6, -13.4),
                                 QPointF(4, -9.8)]))
        orn_gem(p, 0, -12.2, 1.1, QColor("#ff6fae"), 0.3, 0.3)
    elif acc == "helmet":
        p.setPen(pen(QColor("#4a5560"), 0.5))
        p.setBrush(QColor("#c7d1db"))
        p.drawChord(QRectF(-6.8, -13.5, 13.6, 9.5), 0, 180 * 16)
        p.setBrush(QColor("#ffffff"))
        for sx in (-1, 1):
            w = QPainterPath(QPointF(sx * 5.5, -10))
            w.quadTo(sx * 11, -15, sx * 10.5, -18.5)
            w.quadTo(sx * 9, -13, sx * 6.5, -12.5)
            p.drawPath(w)
        p.setPen(pen(QColor("#6b4a2b"), 1.2))
        p.drawLine(QPointF(10.5, 4), QPointF(14.5, -4))
        p.setPen(pen(QColor("#4a5560"), 0.5))
        p.setBrush(QColor("#9aa7b4"))
        p.save()
        p.translate(14.8, -5)
        p.rotate(25)
        p.drawRoundedRect(QRectF(-3.2, -2, 6.4, 4), 0.8, 0.8)
        p.restore()
    elif acc == "shades":
        p.setPen(pen(acc_c, 0.8))
        p.setBrush(QColor(15, 10, 25))
        p.drawRoundedRect(QRectF(-5.6, -6.6, 4.8, 3.6), 1.2, 1.2)
        p.drawRoundedRect(QRectF(0.8, -6.6, 4.8, 3.6), 1.2, 1.2)
        p.drawLine(QPointF(-0.8, -5.2), QPointF(0.8, -5.2))
        p.setPen(pen(QColor(255, 255, 255, 200), 0.5))
        p.drawLine(QPointF(-4.6, -4.0), QPointF(-3.4, -5.8))
        p.drawLine(QPointF(1.8, -4.0), QPointF(3.0, -5.8))
    elif acc == "scarf":
        p.setPen(Qt.NoPen)
        p.setBrush(acc_c)
        p.drawRoundedRect(QRectF(-6.2, 1.2, 12.4, 2.8), 1.3, 1.3)
        p.drawRoundedRect(QRectF(2.5, 2.5, 2.6, 7 + math.sin(t * 2) * 0.6), 0.8, 0.8)
        p.setBrush(QColor(255, 255, 255, 200))
        for x in (-4, -1, 2):
            p.drawRect(QRectF(x, 1.2, 1, 2.8))
    elif acc == "wizard":
        p.setPen(pen(dark(b[1], 0.4), 0.4))
        p.setBrush(QColor("#3b4592"))
        p.drawPolygon(QPolygonF([QPointF(-6.5, -9.6), QPointF(6.5, -9.6), QPointF(2.5, -22)]))
        p.drawEllipse(QRectF(-8, -11, 16, 2.8))
        p.setBrush(acc_c)
        p.setPen(Qt.NoPen)
        p.drawPath(star_path(0.5, -15, 1.6, 0.7, 5))
        p.drawPath(star_path(3, -11.5, 0.9, 0.4, 5))
    elif acc == "lure":
        p.setPen(pen(dark(b[1], 0.2), 0.7))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(0, -10.5))
        path.quadTo(1, -19, 7, -18)
        p.drawPath(path)
        soft_disc(p, 7, -18, 5 + math.sin(t * 3) * 0.8, acc_c, 200, 0)
        p.setBrush(light(acc_c, 0.6))
        p.drawEllipse(QPointF(7, -18), 1.4, 1.4)
    elif acc == "bow":
        p.setPen(pen(dark(acc_c, 0.3), 0.4))
        p.setBrush(QColor("#ff6fae"))
        p.drawPolygon(QPolygonF([QPointF(4.5, -10), QPointF(0.5, -13), QPointF(0.8, -7.5)]))
        p.drawPolygon(QPolygonF([QPointF(4.5, -10), QPointF(8.5, -13), QPointF(8.2, -7.5)]))
        p.drawEllipse(QPointF(4.5, -10), 1.2, 1.2)
    elif acc == "robot":
        p.setPen(pen(QColor("#3e4c59"), 0.7))
        p.drawLine(QPointF(0, -10.8), QPointF(0, -15.5))
        soft_disc(p, 0, -16.2, 3 + math.sin(t * 4), acc_c, 220, 0)
        p.setBrush(QColor("#ff4d4d"))
        p.drawEllipse(QPointF(0, -16.2), 1.2, 1.2)
        p.setBrush(QColor("#3e4c59"))
        for sx in (-1, 1):
            p.drawEllipse(QPointF(sx * 6.9, -4), 0.8, 0.8)
    elif acc == "beanie":
        p.setPen(Qt.NoPen)
        p.setBrush(acc_c)
        p.drawChord(QRectF(-6.6, -14, 13.2, 10), 0, 180 * 16)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(-7, -10.4, 14, 2.4), 1.1, 1.1)
        p.drawEllipse(QPointF(0, -14.2), 1.8, 1.8)
    elif acc == "flower":
        orn_blossom(p, 5, -9.5, 2.6, QColor("#ff8fb1"), 0.3, 0.3)
    elif acc == "party":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ff595e"))
        p.drawPolygon(QPolygonF([QPointF(-3.6, -9.8), QPointF(3.6, -9.8), QPointF(1, -20)]))
        p.setBrush(acc_c)
        p.drawPolygon(QPolygonF([QPointF(-2.4, -13), QPointF(2.6, -13), QPointF(2.1, -15),
                                 QPointF(-1.7, -15)]))
        p.setBrush(QColor("#8ac926"))
        p.drawEllipse(QPointF(1, -20), 1.4, 1.4)
    elif acc == "chef":
        p.setPen(pen(QColor(200, 200, 200), 0.4))
        p.setBrush(QColor("#ffffff"))
        p.drawRect(QRectF(-4, -14, 8, 4.4))
        for dx in (-3, 0, 3):
            p.drawEllipse(QPointF(dx, -15), 2.8, 2.6)
    elif acc == "flowerband":
        p.setPen(pen(QColor("#ff006e"), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(-6.8, -11, 13.6, 10), 10 * 16, 160 * 16)
        for x, y in ((-5, -8.5), (0, -11), (5, -8.5)):
            orn_daisy(p, x, y, 1.5, QColor("#ffffff"), 0.2, 0.3)
    elif acc == "tophat":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1e1610"))
        p.drawRoundedRect(QRectF(-7, -11.2, 14, 1.8), 0.6, 0.6)
        p.drawRect(QRectF(-4.3, -19, 8.6, 8))
        p.setBrush(acc_c)
        p.drawRect(QRectF(-4.3, -13, 8.6, 1.4))
        p.setPen(pen(acc_c, 0.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(2.5, -4.6), 2.7, 2.7)
        p.drawLine(QPointF(5, -3.5), QPointF(6.5, 2))
        _cog = _gear_path(-4.5, -15, 1.6, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(acc_c)
        p.drawPath(_cog)
    elif acc == "glasses":
        p.setPen(pen(QColor("#8a6a3c"), 0.6))
        p.setBrush(QColor(255, 255, 255, 40))
        for sx in (-1, 1):
            p.drawEllipse(QPointF(sx * 2.5, -4.6), 2.8, 2.8)
        p.drawLine(QPointF(-0.1, -4.8), QPointF(0.1, -4.8))
        p.setPen(pen(QColor("#d9d9d9"), 0.8))
        p.drawLine(QPointF(-9, 14), QPointF(7, 6))
        p.drawLine(QPointF(9, 14), QPointF(-7, 6))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e9c46a"))
        p.drawRoundedRect(QRectF(-2.8, 5.5, 5.6, 3.8 + math.sin(t) * 0.3), 0.8, 0.8)
        p.setBrush(QColor("#ff6b6b"))
        for x in (-9, 9):
            p.drawEllipse(QPointF(x, 14), 0.9, 0.9)
    elif acc == "discohat":
        orn_mirror(p, 0, -13.5, 3.6, QColor("#e6e6f5"), 0, 0.3)
        orn_spark(p, 3.5, -16.5, 1.0, QColor("#ffffff"), 0, 0.3)
    elif acc == "cone":
        p.setPen(pen(QColor("#b5854b"), 0.4))
        p.setBrush(QColor("#e9b872"))
        p.drawPolygon(QPolygonF([QPointF(-3.6, -12), QPointF(3.6, -12), QPointF(0.4, -21)]))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffb5d8"))
        p.drawEllipse(QPointF(0, -11), 4.6, 3.2)
        for k, c in enumerate(("#ff4d6d", "#4cc9f0", "#ffd60a")):
            p.setBrush(QColor(c))
            p.drawEllipse(QPointF(-2.5 + k * 2.4, -12 + (k % 2)), 0.5, 0.5)
    elif acc == "leaf":
        orn_maple(p, -1, -12, 4.0, QColor("#e8590c"), 0.3, 0.3)
    elif acc == "sunhat":
        p.setPen(pen(QColor("#b08850"), 0.4))
        p.setBrush(QColor("#f2d49b"))
        p.drawEllipse(QRectF(-11, -11.6, 22, 4.4))
        p.drawChord(QRectF(-5, -15.5, 10, 9), 0, 180 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(acc_c)
        p.drawRect(QRectF(-5, -12.2, 10, 1.4))
    elif acc == "astronaut":
        p.setPen(pen(QColor(255, 255, 255, 170), 0.7))
        p.setBrush(QColor(200, 230, 255, 45))
        p.drawEllipse(QPointF(0, -4), 9.6, 9.6)
        p.setPen(pen(QColor(255, 255, 255, 200), 0.9))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(-7.5, -11.5, 15, 15), 100 * 16, 50 * 16)
    elif acc == "headphones":
        p.setPen(pen(QColor("#2f2d3a"), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(-7.6, -13.5, 15.2, 16), 0, 180 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(acc_c)
        for sx in (-1, 1):
            p.drawRoundedRect(QRectF(sx * 7.6 - 1.8, -7, 3.6, 5), 1.2, 1.2)
        orn_note(p, 10, -14 + math.sin(t * 3), 1.2, acc_c, 0, 0.3)
    elif acc == "beret":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#c1121f"))
        p.save()
        p.translate(-0.5, -10.5)
        p.rotate(-12)
        p.drawEllipse(QRectF(-7, -2.8, 14, 5))
        p.drawRect(QRectF(-0.4, -4, 0.8, 1.6))
        p.restore()
    elif acc == "crown":
        p.setPen(pen(dark(acc_c, 0.3), 0.4))
        p.setBrush(acc_c)
        p.drawPolygon(QPolygonF([QPointF(-5, -9.6), QPointF(-5.6, -15), QPointF(-2.6, -12),
                                 QPointF(0, -16), QPointF(2.6, -12), QPointF(5.6, -15),
                                 QPointF(5, -9.6)]))
        for x, c in ((-2.8, "#e0115f"), (0, "#0f52ba"), (2.8, "#50c878")):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c))
            p.drawEllipse(QPointF(x, -11), 0.8, 0.8)


def sprite_spider(p, b, t, acc="", pattern="plain", baby=False, level=1):
    ab, hd, dk, ac = b[0], b[1], b[2], b[3]
    if acc == "ghost":
        p.setOpacity(p.opacity() * 0.72)
    _acc_back(p, acc, b, t)
    legs = QPainterPath()
    for side in (-1, 1):
        for i in range(4):
            w = math.sin(t * 3 + i * 1.3 + (side > 0)) * 0.9
            hip = QPointF(side * 4, 0.5 + i * 2.0)
            knee = QPointF(side * (11.5 + i * 0.4), -6 + i * 4.6 + w)
            foot = QPointF(side * (15 - i * 0.2), 2.5 + i * 5.6 + w * 0.5)
            legs.moveTo(hip)
            legs.quadTo(knee, foot)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen(dk, 1.6))
    p.drawPath(legs)
    # abdomen (behind the head)
    body = QPainterPath()
    if pattern == "paper":
        body.addPolygon(QPolygonF([QPointF(0, -3), QPointF(9, 3), QPointF(7, 14), QPointF(0, 17),
                                   QPointF(-7, 14), QPointF(-9, 3), QPointF(0, -3)]))
    else:
        body.addEllipse(QPointF(0, 6.5), 9, 9.8)
    if pattern == "pearl":
        g = QRadialGradient(-3, 3, 13)
        g.setColorAt(0, QColor(255, 255, 255))
        g.setColorAt(0.5, ab)
        g.setColorAt(1, QColor("#c9b8ff"))
        p.setBrush(g)
    elif pattern == "glow":
        g = QRadialGradient(0, 6, 11)
        g.setColorAt(0, light(ac, 0.3))
        g.setColorAt(1, ab)
        p.setBrush(g)
    else:
        p.setBrush(ab)
    p.setPen(pen(dk, 0.7))
    p.drawPath(body)
    p.save()
    p.setClipPath(body)
    p.setPen(Qt.NoPen)
    if pattern == "stripes":
        p.setBrush(alpha(dk if ac.lightness() > 150 else ac, 170))
        for y in (2, 6.5, 11):
            p.drawRect(QRectF(-10, y, 20, 1.8))
    elif pattern == "spots":
        p.setBrush(alpha(ac, 200))
        for x, y, r in ((-4, 4, 1.8), (3.5, 6, 2.2), (-2, 11, 1.6), (4, 11.5, 1.2)):
            p.drawEllipse(QPointF(x, y), r, r)
    elif pattern == "facets":
        p.setPen(pen(alpha(light(ab, 0.6), 200), 0.5))
        for k in range(6):
            a = k * TAU / 6 + 0.3
            p.drawLine(QPointF(0, 6.5), QPointF(12 * math.cos(a), 6.5 + 12 * math.sin(a)))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 120))
        p.drawPolygon(QPolygonF([QPointF(-5, 1), QPointF(-1, -1), QPointF(-3, 4)]))
    elif pattern == "moon":
        p.setBrush(dk)
        p.drawRect(QRectF(-10, -4, 10, 22))
        m = QPainterPath()
        m.addEllipse(QPointF(-4, 6), 3.4, 3.4)
        cut = QPainterPath()
        cut.addEllipse(QPointF(-2.6, 5.2), 3, 3)
        p.setBrush(QColor("#f4f1e4"))
        p.drawPath(m.subtracted(cut))
        p.setBrush(QColor(20, 20, 20))
        p.drawEllipse(QPointF(4, 7), 1.0, 1.0)
        p.drawEllipse(QPointF(5.5, 11.5), 0.7, 0.7)
    elif pattern == "peacock":
        for r, c in ((7, QColor("#3a86ff")), (5, QColor("#ffd166")), (3, QColor("#e63946"))):
            p.setBrush(c)
            p.drawEllipse(QPointF(0, 7), r, r * 0.9)
    elif pattern == "stars":
        p.setBrush(ac)
        for x, y, r in ((-4, 4, 1.5), (3, 8, 2.0), (-1, 12, 1.2), (5, 2.5, 1.0)):
            p.drawPath(star_path(x, y, r, r * 0.45, 5))
    elif pattern == "heart":
        h = QPainterPath(QPointF(0, 12))
        h.cubicTo(-7, 6, -3, 1, 0, 4.5)
        h.cubicTo(3, 1, 7, 6, 0, 12)
        p.setBrush(ac)
        p.drawPath(h)
    elif pattern == "robot":
        p.setPen(pen(dark(ab, 0.3), 0.5))
        p.drawLine(QPointF(-10, 6), QPointF(10, 6))
        p.drawLine(QPointF(0, -4), QPointF(0, 18))
        p.setPen(Qt.NoPen)
        p.setBrush(ac)
        p.drawEllipse(QPointF(4, 10), 1.3, 1.3)
    elif pattern == "paper":
        p.setPen(pen(alpha(dark(ab, 0.3), 200), 0.5))
        p.drawLine(QPointF(0, -3), QPointF(0, 17))
        p.drawLine(QPointF(-9, 3), QPointF(7, 14))
    elif pattern == "fuzzy":
        p.setBrush(alpha(ac, 220))
        p.drawEllipse(QPointF(0, 8), 5, 4)
    p.restore()
    if pattern == "fuzzy":
        fz = QPainterPath()
        for k in range(26):
            a = k * TAU / 26
            fz.moveTo(9 * math.cos(a), 6.5 + 9.8 * math.sin(a))
            fz.lineTo(10.6 * math.cos(a + 0.08), 6.5 + 11.4 * math.sin(a + 0.08))
        p.setPen(pen(dk, 0.5))
        p.drawPath(fz)
    # head
    if pattern == "paper":
        head = QPainterPath()
        head.addPolygon(QPolygonF([QPointF(0, -11), QPointF(7, -6), QPointF(6, 1), QPointF(-6, 1),
                                   QPointF(-7, -6), QPointF(0, -11)]))
    else:
        head = QPainterPath()
        head.addEllipse(QPointF(0, -4), 7, 6.8)
    p.setBrush(hd)
    p.setPen(pen(dk, 0.7))
    p.drawPath(head)
    big = pattern == "fuzzy"
    er = 2.9 if big else (2.5 if level >= 2 else 2.2)
    _face(p, 0, -4.6, eye_r=er if level else 1.9, gap=2.9 if big else 2.6, lashes=level >= 3,
          cheek=level >= 1)
    if big:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 20))
        p.drawEllipse(QPointF(-5.5, -8), 0.8, 0.8)
        p.drawEllipse(QPointF(5.5, -8), 0.8, 0.8)
    if not baby:
        _acc_front(p, acc, b, t)


def sprite_cow(p, b, t, **k):
    white, black, pink, horn = b[0], b[1], b[2], b[3]
    p.setPen(Qt.NoPen)
    p.setBrush(dark(white, 0.15))
    for x in (-9, -4, 4.5, 9):
        p.drawRoundedRect(QRectF(x - 1.3, 3, 2.6, 8), 1, 1)
    p.setBrush(black)
    for x in (-9, -4, 4.5, 9):
        p.drawRect(QRectF(x - 1.3, 10, 2.6, 1.6))
    tail = QPainterPath(QPointF(12, -3))
    tail.quadTo(16, 1 + math.sin(t * 2.5) * 2, 14.5, 7)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen(dark(white, 0.3), 0.8))
    p.drawPath(tail)
    p.setPen(Qt.NoPen)
    p.setBrush(black)
    p.drawEllipse(QPointF(14.5, 7.5), 1.2, 1.6)
    body = QPainterPath()
    body.addRoundedRect(QRectF(-12, -7, 25, 13), 6, 6)
    p.setPen(pen(dark(white, 0.35), 0.6))
    p.setBrush(white)
    p.drawPath(body)
    p.save()
    p.setClipPath(body)
    p.setPen(Qt.NoPen)
    p.setBrush(black)
    p.drawEllipse(QPointF(-4, -4), 4.5, 3.4)
    p.drawEllipse(QPointF(6, 1), 3.8, 4.2)
    p.drawEllipse(QPointF(11, -6), 2.5, 2)
    p.restore()
    p.setPen(Qt.NoPen)
    p.setBrush(pink)
    p.drawEllipse(QPointF(3, 6.2), 2.4, 1.3)
    hy = 2 + math.sin(t * 2) * 0.7
    p.save()
    p.translate(-14.5, hy)
    p.setBrush(horn)
    p.drawEllipse(QPointF(0.5, -5.2), 0.9, 1.6)
    p.drawEllipse(QPointF(3.2, -4.8), 0.9, 1.6)
    p.setBrush(black)
    p.drawEllipse(QPointF(4.2, -3.4), 2.2, 1.2)
    p.setPen(pen(dark(white, 0.35), 0.6))
    p.setBrush(white)
    p.drawEllipse(QPointF(0, 0), 5, 4.4)
    p.setPen(Qt.NoPen)
    p.setBrush(pink)
    p.drawEllipse(QPointF(-2.6, 2.6), 3.4, 2.4)
    p.setBrush(dark(pink, 0.4))
    p.drawEllipse(QPointF(-3.8, 2.4), 0.5, 0.6)
    p.drawEllipse(QPointF(-1.6, 2.4), 0.5, 0.6)
    p.setPen(pen(QColor(30, 30, 30), 0.6))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(0.2, -2.2, 2.2, 1.6), 200 * 16, 140 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 120, 150, 110))
    p.drawEllipse(QPointF(1.8, 0.6), 1.1, 0.7)
    p.restore()
    p.setPen(pen(QColor("#3f8a2a"), 0.7))           # a mouthful of grass
    p.drawLine(QPointF(-18, hy + 3.5), QPointF(-19.5, hy + 6))
    p.drawLine(QPointF(-17, hy + 3.8), QPointF(-17, hy + 6.4))


def sprite_cat(p, b, t, fur=None, **k):
    c = fur or b[0]
    dk = dark(c, 0.35)
    tail = QPainterPath(QPointF(6, 12))
    tail.cubicTo(16, 12, 14, 2 + math.sin(t * 2) * 2, 11, -1)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen(c, 2.6))
    p.drawPath(tail)
    p.setPen(pen(dk, 0.6))
    p.setBrush(c)
    p.drawEllipse(QPointF(0, 6), 8, 8.5)
    p.setBrush(light(c, 0.5))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(0, 8), 4.5, 5)
    p.setPen(pen(dk, 0.6))
    p.setBrush(c)
    for sx in (-1, 1):
        p.drawPolygon(QPolygonF([QPointF(sx * 6.5, -8), QPointF(sx * 6, -15.5), QPointF(sx * 1.5, -11)]))
    p.drawEllipse(QPointF(0, -6), 7.4, 6.6)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 170, 190))
    for sx in (-1, 1):
        p.drawPolygon(QPolygonF([QPointF(sx * 5.6, -9), QPointF(sx * 5.4, -13.5), QPointF(sx * 2.8, -11)]))
    paw = math.sin(t * 3.2) * 2.2
    p.setPen(pen(dk, 0.6))
    p.setBrush(c)
    p.drawEllipse(QPointF(6.5, 1 + paw), 2.2, 2)
    p.drawEllipse(QPointF(-3, 13.5), 2.4, 1.6)
    p.drawEllipse(QPointF(3, 13.5), 2.4, 1.6)
    _face(p, 0, -6.5, eye_r=1.7, gap=2.8, mouth=False)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 140, 160))
    p.drawPolygon(QPolygonF([QPointF(-0.8, -4.1), QPointF(0.8, -4.1), QPointF(0, -3.2)]))
    p.setPen(pen(QColor(40, 30, 30), 0.5))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(-1.6, -3.6, 1.6, 1.4), 180 * 16, 180 * 16)
    p.drawArc(QRectF(0, -3.6, 1.6, 1.4), 180 * 16, 180 * 16)
    p.setPen(pen(QColor(60, 50, 50, 160), 0.35))
    for sx in (-1, 1):
        for dy in (-0.6, 0.4):
            p.drawLine(QPointF(sx * 3.2, -3.4 + dy), QPointF(sx * 8.5, -4 + dy * 2))


def sprite_meatball(p, b, t, **k):
    c = b[0]
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(180, 40, 30, 200))
    p.drawEllipse(QPointF(0, 3), 13, 11)
    g = QRadialGradient(-3, -4, 14)
    g.setColorAt(0, light(c, 0.35))
    g.setColorAt(1, dark(c, 0.25))
    p.setBrush(g)
    p.drawEllipse(QPointF(0, 0), 10.5, 10)
    p.setBrush(dark(c, 0.4))
    for x, y in ((-6, 4), (5, -5), (6, 5), (-4, -6), (1, 7)):
        p.drawEllipse(QPointF(x, y), 0.9, 0.8)
    p.setBrush(b[3])
    leaf = QPainterPath(QPointF(-1, -9))
    leaf.quadTo(3, -15, 8, -12)
    leaf.quadTo(4, -8, -1, -9)
    p.drawPath(leaf)
    _face(p, 0, -0.5, eye_r=2.0, gap=3.2)


def sprite_mushroom(p, b, t, **k):
    cap, stem = b[0], b[1]
    p.setPen(pen(dark(stem, 0.3), 0.5))
    p.setBrush(stem)
    p.drawRoundedRect(QRectF(-5.5, -2, 11, 13), 3.5, 3.5)
    p.setBrush(cap)
    p.setPen(pen(dark(cap, 0.3), 0.5))
    p.drawChord(QRectF(-13, -15, 26, 22), 0, 180 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 230))
    for x, y, r in ((-7, -7, 1.8), (0, -11, 2.2), (6.5, -6.5, 1.6), (-2, -5.5, 1.1)):
        p.drawEllipse(QPointF(x, y), r, r)
    _face(p, 0, 3.5, eye_r=1.6, gap=2.4)


def sprite_bee(p, b, t, **k):
    flap = abs(math.sin(t * 18))
    p.setPen(pen(QColor(150, 180, 210, 180), 0.4))
    p.setBrush(QColor(230, 245, 255, 170))
    for dx in (-1.5, 2.5):
        p.drawEllipse(QRectF(dx - 3, -12 + 3 * (1 - flap), 6, 9 * (0.5 + 0.5 * flap)))
    body = QPainterPath()
    body.addEllipse(QPointF(0, 0), 10, 7.5)
    p.setPen(pen(QColor(60, 40, 0), 0.6))
    p.setBrush(b[0])
    p.drawPath(body)
    p.save()
    p.setClipPath(body)
    p.setPen(Qt.NoPen)
    p.setBrush(b[1])
    for x in (0, 5):
        p.drawRect(QRectF(x, -8, 2.4, 16))
    p.restore()
    p.setBrush(b[1])
    p.drawPolygon(QPolygonF([QPointF(9.5, -1), QPointF(13, 0), QPointF(9.5, 1)]))
    p.setPen(pen(b[1], 0.5))
    p.drawLine(QPointF(-6, -6), QPointF(-8, -10.5))
    p.drawLine(QPointF(-3.5, -6.6), QPointF(-4, -11))
    _face(p, -4.5, -1, eye_r=1.6, gap=2.0)


def sprite_otter(p, b, t, **k):
    br, cream = b[0], b[1]
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawEllipse(QRectF(-18, 3, 34, 6))
    p.setBrush(br)
    p.drawEllipse(QPointF(12, 1), 5, 2)
    p.setPen(pen(dark(br, 0.3), 0.5))
    p.drawEllipse(QPointF(0, 0), 12, 5.5)
    p.setPen(Qt.NoPen)
    p.setBrush(light(br, 0.25))
    p.drawEllipse(QPointF(1, -1.5), 8, 3)
    p.setPen(pen(dark(br, 0.3), 0.5))
    p.setBrush(br)
    p.drawEllipse(QPointF(-12, -3), 6, 5.6)
    p.setPen(Qt.NoPen)
    p.setBrush(cream)
    p.drawEllipse(QPointF(-12.5, -1.8), 4.4, 3.4)
    _face(p, -12.5, -3.4, eye_r=1.2, gap=2.0, closed=True, mouth=False)
    p.setBrush(QColor(40, 25, 20))
    p.drawEllipse(QPointF(-12.5, -1.6), 1, 0.7)
    p.setBrush(b[3])
    orn_star(p, -2, -5.5, 1.8, b[3], 0, 0.3)
    p.setBrush(br)
    p.drawEllipse(QPointF(-4, -5), 1.6, 1.2)
    p.drawEllipse(QPointF(0, -5), 1.6, 1.2)


def sprite_ladybug(p, b, t, **k):
    red, blk = b[0], b[1]
    p.setPen(pen(blk, 0.7))
    for sx in (-1, 1):
        for y in (-1, 3, 7):
            p.drawLine(QPointF(sx * 6, y), QPointF(sx * 10, y + 2 + math.sin(t * 4 + y) * 0.6))
    p.drawLine(QPointF(-2, -9), QPointF(-4, -14))
    p.drawLine(QPointF(2, -9), QPointF(4, -14))
    p.setPen(Qt.NoPen)
    p.setBrush(blk)
    p.drawEllipse(QPointF(0, -7), 5.6, 4.6)
    shell = QPainterPath()
    shell.addEllipse(QPointF(0, 3), 9, 9.5)
    p.setPen(pen(dark(red, 0.4), 0.6))
    p.setBrush(red)
    p.drawPath(shell)
    p.setPen(pen(blk, 0.7))
    p.drawLine(QPointF(0, -6.5), QPointF(0, 12.5))
    p.setPen(Qt.NoPen)
    p.setBrush(blk)
    for x, y, r in ((-4.5, 0, 1.8), (4.5, 0.5, 1.8), (-3.5, 7, 1.5), (3.8, 7, 1.5)):
        p.drawEllipse(QPointF(x, y), r, r)
    p.setBrush(QColor(255, 255, 255, 120))
    p.drawEllipse(QPointF(-4, -2.5), 1.6, 1)
    _face(p, 0, -7.5, eye_r=1.3, gap=1.9, mouth=False)


def sprite_snail(p, b, t, **k):
    shell, body = b[0], b[1]
    p.setPen(pen(dark(body, 0.3), 0.6))
    p.setBrush(body)
    slug = QPainterPath(QPointF(-13, 7))
    slug.quadTo(-14, 0, -9, 0)
    slug.lineTo(10, 3)
    slug.quadTo(14, 6, 12, 8)
    slug.lineTo(-13, 8)
    p.drawPath(slug)
    for x in (-11.5, -8.5):
        p.drawLine(QPointF(x + 1.5, 1), QPointF(x, -6 + math.sin(t * 2 + x) * 0.6))
        p.setBrush(QColor(30, 30, 30))
        p.drawEllipse(QPointF(x, -6.5 + math.sin(t * 2 + x) * 0.6), 1, 1)
        p.setBrush(body)
    p.setPen(pen(dark(shell, 0.4), 0.6))
    p.setBrush(shell)
    p.drawEllipse(QPointF(2, -3), 8, 8)
    sp = QPainterPath(QPointF(2, -3))
    for k_ in range(1, 40):
        a = k_ * 0.35
        r = 0.2 * k_
        sp.lineTo(2 + r * math.cos(a), -3 + r * math.sin(a))
    p.setBrush(Qt.NoBrush)
    p.drawPath(sp)
    p.setPen(pen(QColor(30, 25, 30), 0.6))
    p.drawArc(QRectF(-12, 3, 2.4, 1.6), 200 * 16, 140 * 16)


def sprite_bird(p, b, t, **k):
    c, belly = b[0], b[1]
    hop = abs(math.sin(t * 2.5)) * 1.2
    p.translate(0, -hop)
    p.setPen(pen(QColor("#e09a2c"), 0.7))
    p.drawLine(QPointF(-2, 7), QPointF(-2, 10))
    p.drawLine(QPointF(2, 7), QPointF(2, 10))
    p.setPen(Qt.NoPen)
    p.setBrush(dark(c, 0.2))
    p.drawPolygon(QPolygonF([QPointF(7, 2), QPointF(14, -1), QPointF(13, 4)]))
    p.setPen(pen(dark(c, 0.3), 0.5))
    p.setBrush(c)
    p.drawEllipse(QPointF(0, 0), 8.5, 8)
    p.setPen(Qt.NoPen)
    p.setBrush(belly)
    p.drawEllipse(QPointF(-1, 3), 5, 4.2)
    p.setBrush(dark(c, 0.2))
    p.drawEllipse(QPointF(3.5, 1.5), 4.5, 3)
    p.setBrush(b[3])
    p.drawPolygon(QPolygonF([QPointF(-8, -1.5), QPointF(-12.5, 0), QPointF(-8, 1.5)]))
    _face(p, -3.6, -2.8, eye_r=1.4, gap=1.8, mouth=False)


def sprite_octopus(p, b, t, **k):
    c = b[0]
    tent = QPainterPath()
    for i in range(8):
        x0 = -7 + i * 2
        tent.moveTo(x0, 2)
        sx = (i - 3.5) / 3.5
        ph = t * 2 + i
        tent.cubicTo(x0 + sx * 6, 8 + math.sin(ph) * 2, x0 + sx * 10, 10,
                     x0 + sx * 12 + math.sin(ph) * 1.5, 15)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen(c, 2.4))
    p.drawPath(tent)
    p.setPen(pen(dark(c, 0.3), 0.6))
    p.setBrush(c)
    p.drawEllipse(QPointF(0, -4), 9.5, 9)
    p.setPen(Qt.NoPen)
    p.setBrush(light(c, 0.35))
    p.drawEllipse(QPointF(-3, -9), 2.5, 1.6)
    _face(p, 0, -3, eye_r=2.0, gap=3)
    p.setPen(pen(QColor("#d9d9d9"), 0.8))
    p.drawLine(QPointF(-10, 9), QPointF(6, 1))
    p.drawLine(QPointF(10, 9), QPointF(-6, 1))
    p.setPen(Qt.NoPen)
    p.setBrush(b[3] if b[3].lightness() < 240 else QColor("#ffd166"))
    p.drawRoundedRect(QRectF(-2.8, 2.5, 5.6, 4), 0.8, 0.8)


def sprite_silkworm(p, b, t, **k):
    c = b[0]
    for i in range(6, -1, -1):
        x = 12 - i * 3.6 + (math.sin(t * 2 + i) * 0.4)
        y = math.sin(t * 2 + i * 0.8) * 0.8
        r = 4.2 + (6 - i) * 0.15 if i < 6 else 5.0
        p.setPen(pen(dark(c, 0.25), 0.5))
        p.setBrush(c)
        p.drawEllipse(QPointF(x, y), r, r * 1.05)
        p.setPen(Qt.NoPen)
        p.setBrush(dark(c, 0.3))
        p.drawEllipse(QPointF(x, y + r), 0.6, 0.6)
    hx = 12 - 6 * 3.6
    _face(p, hx, -0.5, eye_r=1.4, gap=1.8)
    p.setPen(pen(dark(c, 0.4), 0.5))
    p.drawLine(QPointF(hx - 1, -4.5), QPointF(hx - 2.5, -7))
    p.drawLine(QPointF(hx + 1, -4.5), QPointF(hx + 2.5, -7))


def sprite_cell(p, b, t, **k):
    c = b[0]
    br = QPainterPath()
    for i in range(6):
        a = i * TAU / 6 + 0.4
        x0, y0 = 8 * math.cos(a), 8 * math.sin(a)
        x1, y1 = 15 * math.cos(a + 0.1), 15 * math.sin(a + 0.1)
        br.moveTo(x0, y0)
        br.lineTo(x1, y1)
        br.moveTo((x0 + x1) / 2 + 0.5 * (x1 - x0) / 2, (y0 + y1) / 2 + 0.5 * (y1 - y0) / 2)
        br.lineTo(x1 + 3 * math.cos(a + 0.9), y1 + 3 * math.sin(a + 0.9))
    p.setBrush(Qt.NoBrush)
    p.setPen(pen(c, 1.6))
    p.drawPath(br)
    soft_disc(p, 0, 0, 14, b[3], 60 + 30 * math.sin(t * 2), 0)
    p.setPen(pen(dark(c, 0.3), 0.6))
    p.setBrush(c)
    p.drawEllipse(QPointF(0, 0), 9, 8.6)
    p.setPen(Qt.NoPen)
    p.setBrush(alpha(b[1], 170))
    p.drawEllipse(QPointF(2.5, -3), 3.2, 2.6)
    _face(p, 0, 1, eye_r=1.7, gap=2.4)


def sprite_glowworm(p, b, t, **k):
    c = b[0]
    soft_disc(p, 0, 10, 10 + math.sin(t * 2.5) * 1.5, b[3], 200, 0)
    for i in range(5):
        y = -8 + i * 4
        x = math.sin(t * 1.5 + i * 0.7) * 0.8
        p.setPen(pen(dark(c, 0.3), 0.5))
        p.setBrush(c if i < 4 else light(b[3], 0.4))
        p.drawEllipse(QPointF(x, y), 4.4 - i * 0.3, 3.2)
    _face(p, math.sin(t * 1.5) * 0.8, -8.3, eye_r=1.3, gap=1.7)


HEAD_TOP = {"cow": (-15, -6), "cat": (3, -12), "meatball": (-4, -9), "mushroom": (5, -13),
            "bee": (-4, -8), "otter": (-12, -8.5), "ladybug": (0, -11), "snail": (2, -11),
            "bird": (-3, -8), "octopus": (3, -12.5), "silkworm": (-10, -5.5), "cell": (0, -9),
            "glowworm": (0, -11.5)}


def _bow(p, x, y):
    p.setPen(pen(QColor("#b0306a"), 0.4))
    p.setBrush(QColor("#ff6fae"))
    p.drawPolygon(QPolygonF([QPointF(x, y), QPointF(x - 3.6, y - 2.4), QPointF(x - 3.4, y + 2.2)]))
    p.drawPolygon(QPolygonF([QPointF(x, y), QPointF(x + 3.6, y - 2.4), QPointF(x + 3.4, y + 2.2)]))
    p.drawEllipse(QPointF(x, y), 1.0, 1.0)


def _tiny_crown(p, x, y, t):
    gold = QColor("#f5d76e")
    p.setPen(pen(dark(gold, 0.35), 0.4))
    p.setBrush(gold)
    p.drawPolygon(QPolygonF([QPointF(x - 3.4, y + 1), QPointF(x - 3.8, y - 3), QPointF(x - 1.6, y - 1),
                             QPointF(x, y - 4), QPointF(x + 1.6, y - 1), QPointF(x + 3.8, y - 3),
                             QPointF(x + 3.4, y + 1)]))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#e0115f"))
    p.drawEllipse(QPointF(x, y - 0.6), 0.7, 0.7)
    tw = 0.5 + 0.5 * math.sin(t * 3)
    orn_spark(p, x + 4.5, y - 4.5, 0.6 + 0.5 * tw, QColor(255, 255, 230, int(150 + 100 * tw)), 0, 0.3)


SPRITES = {
    "spider": sprite_spider, "cow": sprite_cow, "cat": sprite_cat, "meatball": sprite_meatball,
    "mushroom": sprite_mushroom, "bee": sprite_bee, "otter": sprite_otter,
    "ladybug": sprite_ladybug, "snail": sprite_snail, "bird": sprite_bird,
    "octopus": sprite_octopus, "silkworm": sprite_silkworm, "cell": sprite_cell,
    "glowworm": sprite_glowworm,
}


@lru_cache(maxsize=1)
def word_font_family() -> str:
    fams = set(QFontDatabase.families())
    for f in ("Segoe Print", "Bradley Hand", "Chalkboard SE", "Comic Sans MS", "Marker Felt",
              "Segoe UI", "Helvetica Neue", "Arial"):
        if f in fams:
            return f
    return QFont().family()


# ---------------------------------------------------------------------- scene
class Scene:
    """One web at one size and one n; geometry is built once, drawn many times."""

    def __init__(self, theme_key: str, params: dict, seed: int, n: int, w: int, h: int,
                 level: int = 1) -> None:
        self.level = max(0, min(3, int(level)))
        self.th = BY_KEY.get(theme_key) or THEMES[0]
        self.prm = params or new_params(int(seed))
        self.seed = int(seed)
        self.n = max(0, int(n))
        self.W, self.H = float(w), float(h)
        self.S = min(self.W, self.H)
        self.u = self.S / 600.0
        self.pal = Pal(self.th, self.prm)
        self.d = _Derived(self.seed)
        self.style = self.th["style"] if self.th["style"] in STYLES else "silk"
        self.stats: Dict[str, int] = {}
        self._lines: Dict[int, list] = {}
        self._bead_cache: Dict[tuple, list] = {}
        self._keep: List[QPainterPath] = []
        self._build()

    # ---------------------------------------------------------------- geometry
    def _env(self, th: float) -> float:
        e = 1.0
        for h, (a, ph) in zip((2, 3, 5), self.prm["env"]):
            e += a * math.cos(h * th + ph)
        return self.R * e

    def _frame_dist(self, th: float) -> float:
        dx, dy = math.cos(th), math.sin(th)
        best = self.S
        for (ax, ay), (bx, by) in zip(self.anchor_pts, self.anchor_pts[1:] + self.anchor_pts[:1]):
            ex, ey = bx - ax, by - ay
            ox, oy = ax - self.cx, ay - self.cy
            den = dx * ey - dy * ex
            if abs(den) < 1e-9:
                continue
            tt = (ox * ey - oy * ex) / den
            ss = (ox * dy - oy * dx) / den
            if tt > 0 and -1e-6 <= ss <= 1 + 1e-6:
                best = min(best, tt)
        return best

    def _ring_r(self, j: float, th: float) -> float:
        f = ((self.dir * (th - self.rot)) % TAU) / TAU
        x = min(1.0, (j + f) / self.rmax)
        env = self.envs[th] if th in self.envs else min(self._env(th), 0.9 * self._frame_dist(th))
        inner = min(0.9, self.rh * 1.45 / max(1.0, env))
        return env * (0.94 - (0.94 - inner) * x ** self.curve)

    def P(self, j: float, th: float) -> QPointF:
        r = self._ring_r(j, th)
        return QPointF(self.cx + r * math.cos(th), self.cy + r * math.sin(th))

    def _seg(self, path: QPainterPath, a: QPointF, b: QPointF, key: float, sag: Optional[float] = None):
        st = self.style
        dx, dy = b.x() - a.x(), b.y() - a.y()
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        nz = hn(key, self.d.noise) - 0.5
        if st == "circuit":
            if hn(key, 3.1) < 0.5:
                path.lineTo(b.x(), a.y())
            else:
                path.lineTo(a.x(), b.y())
            path.lineTo(b)
            return 2
        if st == "lightning":
            q1 = 0.33 + 0.1 * nz
            q2 = 0.66 - 0.1 * nz
            j1 = (hn(key, 1.7) - 0.5) * ln * 0.35
            j2 = (hn(key, 2.9) - 0.5) * ln * 0.35
            path.lineTo(a.x() + dx * q1 + nx * j1, a.y() + dy * q1 + ny * j1)
            path.lineTo(a.x() + dx * q2 + nx * j2, a.y() + dy * q2 + ny * j2)
            path.lineTo(b)
            return 3
        if st in WAVY:
            w = ln * (0.12 + 0.12 * self.wob) * (1 if nz > 0 else -1)
            path.cubicTo(a.x() + dx / 3 + nx * w, a.y() + dy / 3 + ny * w,
                         a.x() + 2 * dx / 3 - nx * w * 0.8, a.y() + 2 * dy / 3 - ny * w * 0.8, b.x(), b.y())
            return 1
        sg = self.sag if sag is None else sag
        if st in STRAIGHT:
            sg *= 0.25
        mx, my = (a.x() + b.x()) / 2, (a.y() + b.y()) / 2
        cx = mx + (self.cx - mx) * sg + nx * nz * ln * 0.12 * self.wob
        cy = my + (self.cy - my) * sg + ny * nz * ln * 0.12 * self.wob
        path.quadTo(cx, cy, b.x(), b.y())
        return 1

    def _build(self) -> None:
        prm, d, S = self.prm, self.d, self.S
        n = self.n
        self.cx = self.W / 2 + prm["cx"] * S
        self.cy = self.H / 2 + prm["cy"] * S
        self.R = prm["r_out"] * S
        self.rot = prm["rot"]
        self.dir = 1 if prm.get("dir", 1) >= 0 else -1
        self.rmax = int(prm["rings"]) - (2 if self.level == 0 else 0)
        self.curve = prm["curve"]
        self.rh = prm["hub"] * S
        self.sag = prm["sag"]
        self.wob = prm["wobble"]
        self.anchor_pts = [(self.cx + dd * S * math.cos(a), self.cy + dd * S * math.sin(a))
                           for a, dd in sorted(prm["anchors"], key=lambda q: q[0] % TAU)]
        self.k = n_radials(n)
        self.rings = n_rings(n, self.rmax)
        segs = 0
        # radial angles: golden-angle slots, so the first k are always well spread
        self.slot_th = [(self.rot + i * GOLDEN + d.jit[i] * 0.09) % TAU for i in range(MAX_RADIALS)]
        self.envs = {th: min(self._env(th), 0.9 * self._frame_dist(th)) for th in self.slot_th}
        vis = sorted(self.slot_th[:self.k], key=lambda th: ((self.dir * (th - self.rot)) % TAU))
        self.vis = vis
        heavy = QPainterPath()
        # mooring lines and frame
        for i, (ax, ay) in enumerate(self.anchor_pts):
            a = math.atan2(ay - self.cy, ax - self.cx)
            heavy.moveTo(ax, ay)
            heavy.lineTo(ax + S * math.cos(a + 0.15 * (hn(i, 5) - 0.5)),
                         ay + S * math.sin(a + 0.15 * (hn(i, 5) - 0.5)))
            segs += 1
        ap = self.anchor_pts
        for i in range(len(ap)):
            a, b = QPointF(*ap[i]), QPointF(*ap[(i + 1) % len(ap)])
            heavy.moveTo(a)
            segs += self._seg(heavy, a, b, 100 + i, sag=0.05)
        # radials
        self.radial_end = {}
        for i in range(self.k):
            th = self.slot_th[i]
            fd = self._frame_dist(th)
            e = QPointF(self.cx + fd * math.cos(th), self.cy + fd * math.sin(th))
            s0 = QPointF(self.cx + self.rh * 0.15 * math.cos(th), self.cy + self.rh * 0.15 * math.sin(th))
            heavy.moveTo(s0)
            segs += self._seg(heavy, s0, e, 200 + i, sag=0.0)
            self.radial_end[th] = e
        self.heavy = heavy
        # capture spiral, one path per ring (outside in)
        self.ring_paths: List[QPainterPath] = []
        self.ring_pts: List[List[QPointF]] = []
        for j in range(self.rings):
            pts = [self.P(j, th) for th in vis] + [self.P(j + 1, vis[0])]
            self.ring_pts.append(pts)
            path = QPainterPath(pts[0])
            for s in range(1, len(pts)):
                segs += self._seg(path, pts[s - 1], pts[s], j * 31.0 + s)
            self.ring_paths.append(path)
        # hub
        hub = QPainterPath()
        if n >= 1:
            hv = vis[:min(len(vis), 12)]
            hv = sorted(hv, key=lambda th: th % TAU)
            for ring in range(3):
                rr = self.rh * (0.35 + 0.22 * ring)
                pts = [QPointF(self.cx + rr * (1 + 0.12 * ((q + ring) % 2)) * math.cos(th),
                               self.cy + rr * (1 + 0.12 * ((q + ring) % 2)) * math.sin(th))
                       for q, th in enumerate(hv)]
                hub.moveTo(pts[0])
                for q in pts[1:] + pts[:1]:
                    hub.lineTo(q)
                    segs += 1
        self.hub = hub
        # stabilimentum (zig-zag silk decoration), spider themes only
        stab = QPainterPath()
        if self.th["spider"] and self.level >= 1:
            for q in range(n_stab(n)):
                th = vis[(q * max(1, len(vis) // 4)) % len(vis)]
                r0, r1 = self.rh * 1.1, self.rh * 1.1 + 0.22 * self.envs.get(th, self.R)
                ux, uy = math.cos(th), math.sin(th)
                nx, ny = -uy, ux
                steps = 12
                for z in range(steps + 1):
                    rr = r0 + (r1 - r0) * z / steps
                    w = S * 0.018 * (1 if z % 2 else -1) * (1 - 0.5 * z / steps)
                    pt = QPointF(self.cx + ux * rr + nx * w, self.cy + uy * rr + ny * w)
                    if z == 0:
                        stab.moveTo(pt)
                    else:
                        stab.lineTo(pt)
                        segs += 1
        self.stab = stab
        # mini-webs at knots (recursion depth 2 at most)
        mini = QPainterPath()
        self.mini_centres = []
        for m in range(n_minis(n + (0, 0, 1, 3)[self.level])):
            dj, fr, sc, ang = d.mini[m]
            th = self.rot + (m + 0.5) * TAU / MAX_MINI + dj
            env = min(self._env(th), 0.9 * self._frame_dist(th))
            mc = QPointF(self.cx + env * fr * math.cos(th), self.cy + env * fr * math.sin(th))
            size = S * 0.062 * sc
            segs += self._mini(mini, mc, size, 7, 3, ang)
            self.mini_centres.append((mc, size))
            for sub in range(n_subminis(n)):
                a2 = ang + (sub * 3 + 1) * TAU / 7
                sc2 = QPointF(mc.x() + size * math.cos(a2), mc.y() + size * math.sin(a2))
                segs += self._mini(mini, sc2, size * 0.42, 5, 2, a2)
                self.mini_centres.append((sc2, size * 0.42))
        self.mini = mini
        # style extras: twigs (mycelium / dendrites), frost spikes, circuit pads
        extra = QPainterPath()
        self.pads: List[QPointF] = []
        if self.style in ("mycelium", "dendrite", "frost"):
            cnt = min(80, self.k * 3 + self.rings * 2)
            for q in range(cnt):
                th = self.slot_th[q % self.k]
                rr = (0.2 + 0.75 * hn(q, 7.7)) * self.envs.get(th, self.R)
                x, y = self.cx + rr * math.cos(th), self.cy + rr * math.sin(th)
                for sgn in (-1, 1):
                    if self.style != "frost" and sgn > 0 and hn(q, 9.1) < 0.5:
                        continue
                    a = th + sgn * (0.7 if self.style == "frost" else 0.5 + 0.6 * hn(q, sgn))
                    L = S * (0.012 if self.style == "frost" else 0.02 + 0.03 * hn(q, 4.4))
                    extra.moveTo(x, y)
                    extra.lineTo(x + L * math.cos(a), y + L * math.sin(a))
                    segs += 1
        if self.style == "circuit":
            self.pads = [self.radial_end[th] for th in self.slot_th[:self.k]]
            for j in range(0, self.rings, 3):
                for s in range(0, len(vis), 2):
                    self.pads.append(self.P(j, vis[s]))
        self.extra = extra
        # stained glass panes
        self.panes: Dict[int, QPainterPath] = {}
        if self.style == "stained" and self.rings >= 2:
            nc = len(self.pal.orns)
            for j in range(self.rings - 1):
                A, B = self.ring_pts[j], self.ring_pts[j + 1]
                for s in range(min(len(A), len(B)) - 1):
                    ci = int(hn(j, s, 2.2) * nc) % nc
                    pp = self.panes.setdefault(ci, QPainterPath())
                    pp.addPolygon(QPolygonF([A[s], A[s + 1], B[s + 1], B[s], A[s]]))
        # ornaments: each appears at one n and then stays where it is
        self.orn_pos = []
        n_orn = min(MAX_ORN, int(round(n_ornaments(n) * (0.35, 1.0, 1.25, 1.45)[self.level])))
        for o in range(n_orn):
            u_, v_, cpick, size, ang = d.orn[o]
            n_o = min(max(1, n), max(1, (o - 2) // 3 + 1))
            jj = min(self.rings - 1, int(u_ * n_rings(n_o, self.rmax)))
            ii = min(self.k - 1, int(v_ * n_radials(n_o)))
            if jj < 0:
                continue
            pt = self.P(jj, self.slot_th[ii])
            col = self.pal.orns[int(cpick * len(self.pal.orns)) % len(self.pal.orns)]
            self.orn_pos.append((pt, size, col, ang))
        self.sparkles = []
        for q in range(n_sparkles(n + (-99, 0, 6, 10)[self.level] if n else 0)):
            a, rr, ph, sz = d.spark[q]
            th = a * TAU
            r = (0.25 + 0.85 * rr) * self.R
            self.sparkles.append((QPointF(self.cx + r * math.cos(th), self.cy + r * math.sin(th)), ph, sz))
        self.all_rings = QPainterPath()
        for rp in self.ring_paths:
            self.all_rings.addPath(rp)
        self.light_paths = QPainterPath()
        self.light_paths.addPath(self.hub)
        self.light_paths.addPath(self.mini)
        # rare and epic: a scalloped lace edge and a rosette round the hub
        lace = QPainterPath()
        if self.level >= 2 and self.rings >= 1 and n >= 2:
            pts = self.ring_pts[0]
            for s_ in range(len(pts) - 1):
                a, b = pts[s_], pts[s_ + 1]
                mx, my = (a.x() + b.x()) / 2, (a.y() + b.y()) / 2
                ox, oy = mx - self.cx, my - self.cy
                ol = math.hypot(ox, oy) or 1.0
                bulge = S * (0.03 if self.level == 2 else 0.045)
                lace.moveTo(a)
                lace.quadTo(mx + ox / ol * bulge, my + oy / ol * bulge, b.x(), b.y())
                segs += 1
        if self.level >= 2 and n >= 1:
            petals = 8 if self.level == 2 else 12
            for q in range(petals):
                a0 = self.rot + q * TAU / petals
                r1 = self.rh * (1.05 if self.level == 2 else 1.25)
                p1 = QPointF(self.cx + self.rh * 0.3 * math.cos(a0), self.cy + self.rh * 0.3 * math.sin(a0))
                p2 = QPointF(self.cx + self.rh * 0.3 * math.cos(a0 + TAU / petals),
                             self.cy + self.rh * 0.3 * math.sin(a0 + TAU / petals))
                am = a0 + TAU / petals / 2
                lace.moveTo(p1)
                lace.quadTo(self.cx + r1 * 1.4 * math.cos(am), self.cy + r1 * 1.4 * math.sin(am),
                            p2.x(), p2.y())
                segs += 1
        self.lace = lace
        self._place_creatures()
        self.halo = (n >= 12 and self.level >= 1) or (self.level >= 2 and n >= 2) or self.level == 3
        # rare / epic adornments of the creature: floating motes, epic signature ring
        g = random.Random(self.seed ^ 0xA5A5)
        self.motes = [(g.uniform(0, TAU), g.uniform(0.7, 1.5), g.uniform(0.4, 1.0), g.uniform(0, TAU))
                      for _ in range((0, 0, 6, 9)[self.level])]
        self.signature = (0, 0, 0, 6)[self.level]
        self.stats = {
            "radials": self.k, "rings": self.rings, "segments": segs,
            "ornaments": len(self.orn_pos), "minis": len(self.mini_centres),
            "sparkles": len(self.sparkles), "creatures": len(self.creatures),
            "stab": n_stab(n) if self.th["spider"] and self.level >= 1 else 0,
            "pads": len(self.pads), "motes": len(self.motes), "signature": self.signature,
        }
        self.stats["total"] = sum(self.stats.values())

    def _mini(self, path, c: QPointF, size: float, nr: int, nring: int, ang: float) -> int:
        segs = 0
        ths = [ang + q * TAU / nr + 0.25 * (hn(c.x(), q) - 0.5) for q in range(nr)]
        for th in ths:
            path.moveTo(c)
            path.lineTo(c.x() + size * math.cos(th), c.y() + size * math.sin(th))
            segs += 1
        for ring in range(nring):
            rr = size * (0.28 + 0.66 * ring / max(1, nring - 1))
            pts = [QPointF(c.x() + rr * math.cos(th), c.y() + rr * math.sin(th)) for th in ths]
            path.moveTo(pts[0])
            for q in pts[1:] + pts[:1]:
                path.lineTo(q)
                segs += 1
        return segs

    def _place_creatures(self) -> None:
        th, S, prm = self.th, self.S, self.prm
        cr = prm.get("creature", {})
        place = th["place"]
        kind = th["creature"]
        base = S * (0.092 if kind == "spider" else 0.085) * cr.get("scale", 1.0)
        out = []
        flip = cr.get("flip", 1)
        if place == "herd":
            m = n_herd(self.n)
            for q in range(m):
                a = self.rot + q * TAU / m + 0.4 * (self.d.friends[q % 8][0] - 0.5)
                r = 0.43 * S
                x = min(self.W - base * 0.8, max(base * 0.8, self.cx + r * math.cos(a)))
                y = min(self.H - base * 0.5, max(base * 0.5, self.cy + r * math.sin(a)))
                out.append((QPointF(x, y), base * 0.9, 0, 1 if math.cos(a) > 0 else -1, q, False))
        elif place == "ring":
            m = 2 + min(4, self.n // 3)
            for q in range(m):
                a = self.rot + 0.3 + q * TAU / m
                r = 0.4 * S
                x = min(self.W - base, max(base, self.cx + r * math.cos(a)))
                y = min(self.H - base, max(base, self.cy + r * math.sin(a)))
                out.append((QPointF(x, y), base * 1.05, 0, 1 if math.cos(a) < 0 else -1, q, False))
        elif place == "swarm":
            m = 1 + min(5, self.n // 2)
            for q in range(m):
                a, rr, tilt, ph = self.d.friends[q % 8]
                r = (0.12 + 0.3 * rr) * S
                th2 = a * TAU
                out.append((QPointF(self.cx + r * math.cos(th2), self.cy + r * math.sin(th2)),
                            base * 0.7, tilt, 1 if q % 2 else -1, q, False))
        else:
            if place == "hub":
                pt = QPointF(self.cx, self.cy)
            elif place == "bottom":
                pt = QPointF(self.W / 2 + (cr.get("spot", 0.5) - 0.5) * S * 0.4, self.H - base * 1.2)
            elif place == "top":
                pt = QPointF(self.W / 2 + (cr.get("spot", 0.5) - 0.5) * S * 0.5, base * 1.3)
            else:       # radial: part way out along one thread
                th2 = self.slot_th[int(cr.get("slot", 0) * self.k) % self.k]
                r = (0.3 + 0.4 * cr.get("frac", 0.4)) * self.envs.get(th2, self.R)
                pt = QPointF(self.cx + r * math.cos(th2), self.cy + r * math.sin(th2))
            out.append((pt, base * (1.15 if kind == "spider" else 1.0), cr.get("tilt", 0), flip, 0,
                        False))
            for q in range(n_friends(self.n)):
                a, rr, tilt, ph = self.d.friends[q]
                th2 = self.slot_th[int(a * self.k) % self.k]
                r = (0.45 + 0.45 * rr) * self.envs.get(th2, self.R)
                out.append((QPointF(self.cx + r * math.cos(th2), self.cy + r * math.sin(th2)),
                            base * 0.55, tilt, 1 if q % 2 else -1, q + 1, True))
        self.creatures = out

    # ----------------------------------------------------------------- drawing
    def draw_background(self, p: QPainter) -> None:
        g = random.Random(int(self.prm.get("bg", 0)))
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(QRectF(0, 0, self.W, self.H), QColor(self.th["bg"][0][1][0])
                   if self.th["bg"] and isinstance(self.th["bg"][0][1], list) else QColor(20, 20, 30))
        for layer in self.th["bg"]:
            fn = BACKGROUNDS.get(layer[0])
            if fn is None:
                continue
            p.save()
            try:
                fn(p, self.W, self.H, self.S, g, *layer[1:])
            finally:
                p.restore()
        p.restore()

    def _lines_of(self, path: QPainterPath):
        key = id(path)
        ls = self._lines.get(key)
        if ls is None:
            ls = []
            for poly in path.toSubpathPolygons(_COARSE):
                poly = _UNCOARSE.map(poly)
                pts = list(poly)                # point pairs for drawLines (fast)
                ls.extend(q for ab in zip(pts[:-1], pts[1:]) for q in ab)
            self._lines[key] = ls
            self._keep.append(path)
        return ls

    def _beads(self, p: QPainter, path: QPainterPath, c: QColor, size: float, gap: float) -> None:
        """Little beads along a path (instead of a slow dotted pen)."""
        key = (id(path), round(gap, 2))
        pts = self._bead_cache.get(key)
        if pts is None:
            pts, carry = [], 0.0
            ls = self._lines_of(path)
            for i in range(0, len(ls) - 1, 2):
                a, b = ls[i], ls[i + 1]
                dx, dy = b.x() - a.x(), b.y() - a.y()
                L = math.hypot(dx, dy)
                d = gap - carry
                while d <= L and L > 0:
                    pts.append(QPointF(a.x() + dx * d / L, a.y() + dy * d / L))
                    d += gap
                carry = (carry + L) % gap if gap > 0 else 0.0
            self._bead_cache[key] = pts
        p.setPen(pen(c, size))
        p.drawPoints(pts)

    def _dp(self, p: QPainter, path: QPainterPath) -> None:
        """Stroke a path. Wide solid pens go through drawLines (several times faster
        than stroking a long curved path with a wide pen)."""
        pn = p.pen()
        if pn.widthF() > 1.0 and pn.style() == Qt.SolidLine:
            pn.setCapStyle(Qt.FlatCap)
            p.setPen(pn)
            p.drawLines(self._lines_of(path))
        else:
            p.drawPath(path)

    def _stroke(self, p: QPainter, path: QPainterPath, c: QColor, w: float) -> None:
        st = self.style
        if self.level == 0 and st in PLAIN_WHEN_COMMON:
            st = "silk"
        p.setBrush(Qt.NoBrush)
        if st in ("glow", "neon", "lightning", "honey"):
            p.setPen(pen(alpha(c, 70), w * 3.6))
            self._dp(p, path)
            p.setPen(pen(light(c, 0.55) if st != "honey" else c, w * (0.9 if st != "honey" else 1.8)))
            self._dp(p, path)
        elif st == "crystal":
            p.setPen(pen(alpha(c, 210), w * 1.2))
            self._dp(p, path)
            p.setPen(pen(QColor(255, 255, 255, 150), w * 0.45))
            self._dp(p, path)
        elif st == "beaded":
            p.setPen(pen(alpha(c, 150), w * 0.7))
            self._dp(p, path)
            self._beads(p, path, light(c, 0.4), w * 2.4, w * 13.0)
        elif st == "yarn":
            p.setPen(pen(dark(c, 0.35), w * 3.4))
            self._dp(p, path)
            p.setPen(pen(c, w * 2.5))
            self._dp(p, path)
            p.setPen(pen(alpha(light(c, 0.45), 220), w * 0.8))
            self._dp(p, path)
        elif st == "noodle":
            p.save()
            p.translate(1.5 * self.u, 2 * self.u)
            p.setPen(pen(QColor(120, 60, 20, 70), w * 5))
            self._dp(p, path)
            p.restore()
            p.setPen(pen(dark(c, 0.12), w * 4.6))
            self._dp(p, path)
            p.setPen(pen(light(c, 0.45), w * 1.5))
            self._dp(p, path)
        elif st == "grass":
            p.setPen(pen(alpha(c, 170), w * 8))
            self._dp(p, path)
            p.setPen(pen(alpha(light(c, 0.25), 150), w * 3.5))
            self._dp(p, path)
        elif st == "twine":
            p.setPen(pen(dark(c, 0.4), w * 2.8))
            self._dp(p, path)
            p.setPen(pen(c, w * 2.0))
            self._dp(p, path)
            p.setPen(pen(alpha(light(c, 0.3), 200), w * 0.6))
            self._dp(p, path)
        elif st in ("circuit", "brass", "drizzle"):
            p.setPen(pen(dark(c, 0.5), w * 3.0))
            self._dp(p, path)
            p.setPen(pen(c, w * 2.0))
            self._dp(p, path)
            p.setPen(pen(alpha(light(c, 0.5), 200), w * 0.7))
            self._dp(p, path)
        elif st == "paper":
            p.save()
            p.translate(0.8 * self.u, 0.8 * self.u)
            p.setPen(pen(alpha(dark(c, 0.3), 120), w * 1.6))
            self._dp(p, path)
            p.restore()
            p.setPen(pen(c, w * 1.1))
            self._dp(p, path)
        elif st == "ribbon":
            p.setPen(pen(alpha(c, 200), w * 5))
            self._dp(p, path)
            p.setPen(pen(alpha(dark(c, 0.3), 200), w * 0.9))
            self._dp(p, path)
        elif st in ("mycelium", "dendrite"):
            p.setPen(pen(alpha(c, 45), w * 3.5))
            self._dp(p, path)
            p.setPen(pen(alpha(c, 220), w * 1.0))
            self._dp(p, path)
        elif st == "frost":
            p.setPen(pen(alpha(c, 60), w * 3.0))
            self._dp(p, path)
            p.setPen(pen(c, w * 1.0))
            self._dp(p, path)
        elif st == "stained":
            p.setPen(pen(c, w * 3.6))
            self._dp(p, path)
        elif st == "fluff":
            p.setPen(pen(alpha(c, 60), w * 7))
            self._dp(p, path)
            p.setPen(pen(alpha(c, 130), w * 3.4))
            self._dp(p, path)
            p.setPen(pen(light(c, 0.5), w * 1.0))
            self._dp(p, path)
        elif st == "wash":
            p.setPen(pen(alpha(c, 45), w * 6))
            self._dp(p, path)
            p.setPen(pen(alpha(c, 190), w * 1.2))
            self._dp(p, path)
        elif st == "trail":
            p.setPen(pen(alpha(c, 45), w * 6))
            self._dp(p, path)
            p.setPen(pen(alpha(c, 160), w * 0.9))
            self._dp(p, path)
            self._beads(p, path, QColor(255, 255, 255, 230), w * 1.6, w * 9.0)
        elif st == "rainbow":
            p.setPen(pen(alpha(c, 60), w * 3.5))
            self._dp(p, path)
            p.setPen(pen(c, w * 1.5))
            self._dp(p, path)
        else:   # silk, string
            p.setPen(pen(alpha(c, 235), w))
            self._dp(p, path)

    def draw_web(self, p: QPainter) -> None:
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        u, pal = self.u, self.pal
        wf = float(self.th.get("width", 1.0))
        w = max(0.6, 1.15 * u * wf)
        main = pal.thread[0]
        if self.halo:
            soft_disc(p, self.cx, self.cy, self.R * 0.9, main, 55, 0)
        p.setRenderHint(QPainter.Antialiasing, False)    # the lead lines hide the pane edges
        for ci, pp in self.panes.items():
            p.setPen(Qt.NoPen)
            p.setBrush(alpha(pal.orns[ci], 170))
            p.drawPath(pp)
        p.setRenderHint(QPainter.Antialiasing, True)
        self._stroke(p, self.heavy, main, w * 1.25)
        multi = self.style in MULTI and len(pal.thread) > 1
        if multi:
            for j, rp in enumerate(self.ring_paths):
                self._stroke(p, rp, pal.thread[j % len(pal.thread)], w)
        elif self.ring_paths:
            self._stroke(p, self.all_rings, main, w)
        if not self.light_paths.isEmpty():      # hub and mini-webs: one fine pass (fast)
            p.setBrush(Qt.NoBrush)
            lc = pal.thread[-1] if multi else main
            if self.style in ("stained", "circuit", "brass", "drizzle", "yarn", "noodle", "twine"):
                lc = dark(lc, 0.3) if self.style == "stained" else lc
                p.setPen(pen(lc, w * 1.6))
                self._dp(p, self.light_paths)
            else:
                p.setPen(pen(light(lc, 0.25), 1.0))
                p.drawPath(self.light_paths)
        if self.level == 3 and self.ring_paths:
            cg = QConicalGradient(self.cx, self.cy, math.degrees(self.rot))
            for i, col in enumerate(("#ff8fd8", "#8fe8ff", "#fff38f", "#a98fff", "#8fffc0", "#ff8fd8")):
                cg.setColorAt(i / 5, QColor(col))
            sp = QPen(QBrush(cg), 1.0)
            p.setBrush(Qt.NoBrush)
            p.setOpacity(0.55)
            p.setPen(sp)
            p.drawPath(self.all_rings)
            p.setOpacity(1.0)
        if not self.lace.isEmpty():
            p.setBrush(Qt.NoBrush)
            p.setPen(pen(alpha(light(main, 0.35), 230), 1.0))
            p.drawPath(self.lace)
        if not self.stab.isEmpty():
            p.setPen(pen(alpha(light(main, 0.5), 230), w * 2.2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(self.stab)
        if not self.extra.isEmpty():
            p.setPen(pen(alpha(pal.thread[-1], 220), 1.0))
            p.drawPath(self.extra)
        if self.pads:
            p.setPen(pen(dark(main, 0.4), u * 0.8))
            p.setBrush(main)
            for q in self.pads:
                p.drawEllipse(q, 2.6 * u, 2.6 * u)
        fn = ORNAMENTS.get(self.th["orn"], orn_dew)
        sc = ORN_SCALE.get(self.th["orn"], 1.0)
        for pt, size, col, ang in self.orn_pos:
            fn(p, pt.x(), pt.y(), self.S * 0.011 * size * sc, col, ang, u)
        for mc, size in self.mini_centres:
            orn_dew(p, mc.x(), mc.y(), max(1.5, size * 0.09), pal.orns[0], 0, u)
        p.restore()

    def creature_home(self) -> QPointF:
        return self.creatures[0][0] if self.creatures else QPointF(self.cx, self.cy)

    def draw_creature(self, p: QPainter, pt: QPointF, size: float, tilt: float, flip: int,
                      idx: int, baby: bool, t: float) -> None:
        kind = self.th["creature"]
        fn = SPRITES.get(kind, sprite_spider)
        p.save()
        if not baby:
            size *= (0.95, 1.0, 1.15, 1.28)[self.level]
        bob = math.sin(t * 1.6 + idx * 1.3 + self.prm["creature"].get("phase", 0)) * size * 0.04
        p.translate(pt.x(), pt.y() + bob)
        p.rotate(tilt)
        p.scale(size / 20.0 * flip, size / 20.0)
        kw = {}
        lv = self.level
        if kind == "spider":
            pat = self.th.get("pattern", "plain")
            if lv == 0 and pat not in ("moon", "paper", "robot", "peacock"):
                pat = "plain"
            acc = self.th.get("acc", "") if lv >= 2 else ""
            if lv >= 2 and not acc:                 # every rare / epic spider dresses up
                acc = "bow" if lv == 2 else "crown"
            kw = {"acc": acc, "pattern": pat, "baby": baby, "level": lv}
        elif kind == "cat":
            kw = {"fur": self.pal.fur[idx % len(self.pal.fur)]}
        try:
            if lv >= 2 and not baby:
                soft_disc(p, 0, 0, (17 if lv == 2 else 25) + 2 * math.sin(t * 2.2),
                          light(self.pal.thread[0], 0.5), 95 if lv == 2 else 130, 0)
            fn(p, self.pal.body, t + idx * 0.7, **kw)
            if kind != "spider" and lv >= 2 and not baby:
                hx, hy = HEAD_TOP.get(kind, (0, -12))
                if lv == 2:
                    _bow(p, hx, hy)
                else:
                    _tiny_crown(p, hx, hy, t)
        finally:
            p.restore()

    def _word_layout(self, word: str):
        fam = word_font_family()
        f = QFont(fam)
        f.setBold(True)
        f.setPixelSize(max(6, int(self.S * 0.085)))
        fm = QFontMetricsF(f)
        wd = fm.horizontalAdvance(word)
        maxw = self.S * 0.62
        if wd > maxw:
            f.setPixelSize(max(6, int(f.pixelSize() * maxw / wd)))
            fm = QFontMetricsF(f)
            wd = fm.horizontalAdvance(word)
        x = self.cx - wd / 2
        y = self.cy - self.R * 0.46 + self.prm.get("word_dy", 0) * self.S
        y = max(fm.ascent() + 4 * self.u, y)
        path = QPainterPath()
        path.addText(QPointF(x, y), f, word)
        return path, QRectF(x, y - fm.ascent(), wd, fm.height())

    def draw_word(self, p: QPainter, word: str, progress: float, t: float) -> Optional[QPointF]:
        if not word:
            return None
        path, box = self._word_layout(word)
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.translate(box.center())
        p.rotate(self.prm.get("word_tilt", 0))
        p.translate(-box.center())
        wc = self.pal.word
        patch = QColor(0, 0, 0) if wc.lightness() > 128 else QColor(255, 255, 255)
        a = min(1.0, progress * 3.0)
        pr = box.adjusted(-box.height() * 0.5, -box.height() * 0.25, box.height() * 0.5,
                          box.height() * 0.25)
        g = QRadialGradient(pr.center(), pr.width() * 0.6)
        g.setColorAt(0, alpha(patch, 75 * a))
        g.setColorAt(1, alpha(patch, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(pr.center(), pr.width() * 0.6, pr.height() * 0.95)
        xr = box.left() + box.width() * max(0.0, min(1.0, progress))
        p.setClipRect(QRectF(box.left() - 20, box.top() - 40, xr - box.left() + 20, box.height() + 80))
        p.setPen(pen(alpha(wc, 70), self.u * 4))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(pen(wc, max(0.5, self.u * 1.1)))
        p.setBrush(alpha(wc, 200))
        p.drawPath(path)
        p.restore()
        return QPointF(xr, box.center().y())

    def _draw_filigree(self, p: QPainter, t: float) -> None:
        """Epic: a thin golden frame with curls in the corners."""
        S, u = self.S, self.u
        gold = QColor("#f5d76e")
        m = S * 0.025
        r = QRectF(m, m, self.W - 2 * m, self.H - 2 * m)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen(alpha(gold, 200), max(1.0, 1.6 * u)))
        p.drawRoundedRect(r, S * 0.03, S * 0.03)
        p.setPen(pen(alpha(gold, 140), 1.0))
        p.drawRoundedRect(r.adjusted(S * 0.008, S * 0.008, -S * 0.008, -S * 0.008), S * 0.025, S * 0.025)
        for cx, cy, sx, sy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                               (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            curl = QPainterPath(QPointF(cx + sx * S * 0.01, cy + sy * S * 0.09))
            curl.cubicTo(cx + sx * S * 0.03, cy + sy * S * 0.03, cx + sx * S * 0.07, cy + sy * S * 0.03,
                         cx + sx * S * 0.09, cy + sy * S * 0.01)
            curl.moveTo(cx + sx * S * 0.03, cy + sy * S * 0.05)
            curl.quadTo(cx + sx * S * 0.06, cy + sy * S * 0.06, cx + sx * S * 0.05, cy + sy * S * 0.03)
            p.setBrush(Qt.NoBrush)
            p.setPen(pen(alpha(gold, 220), max(1.0, 1.4 * u)))
            p.drawPath(curl)
            tw = 0.5 + 0.5 * math.sin(t * 2 + cx * 0.01 + cy * 0.02)
            orn_spark(p, cx + sx * S * 0.035, cy + sy * S * 0.035, S * 0.008 * (0.6 + 0.6 * tw),
                      alpha(QColor(255, 250, 220), 160 + 90 * tw), 0, u)

    def draw_overlay(self, p: QPainter, t: float = 0.0, word: Optional[str] = None,
                     word_progress: float = 1.0) -> None:
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.level == 3:
            self._draw_filigree(p, t)
        for q, (pt, size, col, ang) in enumerate(self.orn_pos[:(6, 10, 14, 18)[self.level]]):
            tw = max(0.0, math.sin(t * 1.3 + ang * 3)) ** 6
            if tw > 0.05:
                orn_spark(p, pt.x() + 2 * self.u, pt.y() - 2 * self.u, self.S * 0.006 * (0.6 + tw),
                          QColor(255, 255, 255, int(220 * tw)), 0, self.u)
        for pt, ph, sz in self.sparkles:
            tw = 0.35 + 0.65 * max(0.0, math.sin(t * 1.1 + ph)) ** 2
            orn_spark(p, pt.x(), pt.y(), self.S * 0.007 * sz * tw, alpha(light(self.pal.thread[0], 0.6), 230 * tw),
                      ph, self.u)
        if self.level == 3:
            self._draw_sweep(p, t)
        pen_pt = None
        if word:
            pen_pt = self.draw_word(p, word, word_progress, t)
        for idx, (pt, size, tilt, flip, q, baby) in enumerate(self.creatures):
            if idx == 0 and pen_pt is not None and word_progress < 1.0:
                pt = QPointF(pen_pt.x(), pen_pt.y() + size * 0.15)
            if idx == 0:
                self._draw_adornments(p, pt, size, t, behind=True)
            self.draw_creature(p, pt, size, tilt, flip, q, baby, t)
            if idx == 0:
                self._draw_adornments(p, pt, size, t, behind=False)
        p.restore()

    def _draw_sweep(self, p: QPainter, t: float) -> None:
        """Epic: a soft band of light that slowly sweeps across the web."""
        pos = ((t * 0.12 + 0.35) % 1.6) - 0.3
        x = self.W * pos
        g = QLinearGradient(x - self.S * 0.12, 0, x + self.S * 0.12, self.S * 0.08)
        g.setColorAt(0, QColor(255, 255, 255, 0))
        g.setColorAt(0.5, QColor(255, 255, 255, 46))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        clip = QPainterPath()
        clip.addEllipse(QPointF(self.cx, self.cy), self.R * 1.02, self.R * 1.02)
        p.save()
        p.setClipPath(clip)
        p.fillRect(QRectF(0, 0, self.W, self.H), g)
        p.restore()

    def _draw_adornments(self, p: QPainter, pt: QPointF, size: float, t: float, behind: bool) -> None:
        """Rare: floating motes round the creature. Epic: also the theme's own ornaments
        circling it (a signature per theme) and a little stardust trail."""
        if self.level < 2:
            return
        cx, cy = pt.x(), pt.y()
        glow = light(self.pal.thread[0], 0.5)
        for a0, rr, sz, ph in self.motes:
            a = a0 + t * 0.6 * (1 if sz > 0.7 else -1)
            front = math.sin(a) > 0
            if front == behind:
                continue
            x = cx + math.cos(a) * size * rr
            y = cy + math.sin(a) * size * rr * 0.45
            tw = 0.55 + 0.45 * math.sin(t * 2.3 + ph)
            soft_disc(p, x, y, size * 0.12 * sz * (0.8 + tw * 0.4), glow, 200 * tw, 0)
        if self.level == 3 and not behind:
            fn = ORNAMENTS.get(self.th["orn"], orn_dew)
            for k in range(self.signature):
                a = t * 0.5 + k * TAU / self.signature
                x = cx + math.cos(a) * size * 1.25
                y = cy - size * 0.15 + math.sin(a) * size * 0.5
                c = self.pal.orns[k % len(self.pal.orns)]
                fn(p, x, y, size * 0.075, c, a, self.u)
            for k in range(6):
                a = t * 0.5 - 0.25 * (k + 1)
                x = cx + math.cos(a) * size * 1.25
                y = cy - size * 0.15 + math.sin(a) * size * 0.5
                p.setPen(Qt.NoPen)
                p.setBrush(alpha(glow, 170 - 25 * k))
                p.drawEllipse(QPointF(x, y), size * 0.025, size * 0.025)

    def draw(self, p: QPainter, t: float = 0.0, word: Optional[str] = None,
             word_progress: float = 1.0) -> None:
        self.draw_background(p)
        self.draw_web(p)
        self.draw_overlay(p, t, word, word_progress)


def render_image(theme_key: str, params: dict, seed: int, n: int, w: int, h: int,
                 t: float = 0.0, word: Optional[str] = None, word_progress: float = 1.0,
                 level: int = 1) -> QImage:
    img = QImage(int(w), int(h), QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    try:
        Scene(theme_key, params, seed, n, w, h, level).draw(p, t, word, word_progress)
    finally:
        p.end()
    return img
