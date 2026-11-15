"""
PeterPiper 1.1: small colour-science helpers used to CHECK colours (they never
change a measurement). Pure Python + math; no Qt needed.

    luminance("#RRGGBB")            WCAG 2 relative luminance (0 = black, 1 = white)
    contrast(a, b)                  WCAG 2 contrast ratio (1 .. 21)
    composite(rgba, under)          a translucent colour drawn over an opaque one
    simulate(colour, kind)          how a person with protanopia / deuteranopia /
                                    tritanopia sees it (Machado, Oliveira &
                                    Fernandes 2009, severity 1.0, in linear RGB)
    delta_e2000(c1, c2)             CIEDE2000 colour difference (Sharma et al. 2005)
    min_distance(colours, kinds)    the smallest CIEDE2000 distance between any two
                                    colours of a list, as seen with each vision kind

Colours are '#RRGGBB' strings (or 'rgba(r,g,b,a)' where noted).
"""
from __future__ import annotations

import math
import re
from itertools import combinations
from typing import Dict, Iterable, Sequence, Tuple

RGB = Tuple[float, float, float]

# Machado, Oliveira & Fernandes (2009), "A physiologically-based model for simulation
# of color vision deficiency", IEEE TVCG 15(6) - the severity 1.0 matrices (dichromacy),
# applied to linear RGB.
MACHADO_1_0: Dict[str, Tuple[RGB, RGB, RGB]] = {
    "protanopia": ((0.152286, 1.052583, -0.204868),
                   (0.114503, 0.786281, 0.099216),
                   (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968),
                     (0.280085, 0.672501, 0.047413),
                     (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779),
                   (-0.078411, 0.930809, 0.147602),
                   (0.004733, 0.691367, 0.303900)),
}
VISION = ("normal", "protanopia", "deuteranopia", "tritanopia")

_RGBA = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)")


def parse(colour: str) -> Tuple[float, float, float, float]:
    """'#RGB', '#RRGGBB', '#AARRGGBB' (Qt order) or 'rgba(r,g,b,a)' -> r, g, b in 0..255, alpha 0..1."""
    s = str(colour).strip()
    m = _RGBA.fullmatch(s)
    if m:
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return float(m.group(1)), float(m.group(2)), float(m.group(3)), a
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) == 8:                                   # Qt's #AARRGGBB
        a, s = int(s[:2], 16) / 255.0, s[2:]
    else:
        a = 1.0
    if len(s) != 6:
        raise ValueError(f"not a colour: {colour!r}")
    return float(int(s[0:2], 16)), float(int(s[2:4], 16)), float(int(s[4:6], 16)), a


def hex_of(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{int(round(min(255.0, max(0.0, v)))):02X}" for v in rgb[:3])


def _lin(v: float) -> float:
    v = v / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _gamma(v: float) -> float:
    v = min(1.0, max(0.0, v))
    return 255.0 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)


def linear(colour: str) -> RGB:
    r, g, b, _a = parse(colour)
    return _lin(r), _lin(g), _lin(b)


def luminance(colour: str) -> float:
    """WCAG 2 relative luminance (sRGB, 0 = black, 1 = white)."""
    r, g, b = linear(colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG 2 contrast ratio between two opaque colours (1 = none, 21 = black/white)."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def composite(top: str, under: str) -> str:
    """A translucent colour (e.g. 'rgba(91,140,255,0.28)') painted over an opaque
    one, as the screen shows it (alpha blending in sRGB, like Qt)."""
    r, g, b, a = parse(top)
    ur, ug, ub, _ = parse(under)
    return hex_of((r * a + ur * (1 - a), g * a + ug * (1 - a), b * a + ub * (1 - a)))


def simulate(colour: str, kind: str) -> str:
    """The colour as seen with a colour-vision deficiency (kind 'normal' = as is)."""
    if kind == "normal":
        return hex_of(parse(colour)[:3])
    m = MACHADO_1_0[kind]
    lin = linear(colour)
    out = [sum(m[i][j] * lin[j] for j in range(3)) for i in range(3)]
    return hex_of([_gamma(v) for v in out])


def lab(colour: str) -> RGB:
    """CIE L*a*b* (D65) of an sRGB colour."""
    r, g, b = linear(colour)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e2000(c1: str, c2: str) -> float:
    """CIEDE2000 (kL = kC = kH = 1), after Sharma, Wu & Dalal (2005)."""
    L1, a1, b1 = lab(c1)
    L2, a2, b2 = lab(c2)
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p else 0.0
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


def min_distance(colours: Sequence[str], kinds: Iterable[str] = VISION
                 ) -> Tuple[float, str, Tuple[int, int]]:
    """(smallest CIEDE2000 distance between any two colours, vision kind, pair)."""
    best = (float("inf"), "", (-1, -1))
    for kind in kinds:
        seen = [simulate(c, kind) for c in colours]
        for i, j in combinations(range(len(seen)), 2):
            d = delta_e2000(seen[i], seen[j])
            if d < best[0]:
                best = (d, kind, (i, j))
    return best
