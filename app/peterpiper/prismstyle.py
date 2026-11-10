"""
The look of the graph inside a .prism file (GraphPad Prism 10+).

PeterPiper writes .prism projects by copying a graph TEMPLATE made in Prism and
replacing its data (prismfile.write_prism). This module changes the template's
graph so it matches the graph style chosen in PeterPiper (GraphStyle.to_dict()).
GraphPad does not document the graph format, so every edit below was worked out
by changing one field, opening the file in GraphPad Prism 11 (11.0.0.84,
Windows) with a Prism script (Open / ExportSVG / ExportPNG) and measuring what
Prism drew. Only fields that were checked that way are written; SUPPORT lists
them. dev_tests/test_prism_style.py repeats the check for a matrix of styles.

Binary layout (graphs/<id>/data.bin)
------------------------------------
* "PCFFGRA4" + a 128-byte header, then records: uint16 tag, uint32 length
  (little-endian), payload. Tags with bit 0x4000 are 2-byte markers without a
  length. The file ends with 4 spare bytes.
* Every graph object (legend, each plot, each axis, each text) starts with a
  0x00db record; bytes 158-161 of it hold the object's uint32 id. Record 0x8018
  bytes 4-7 hold the number of 0x00db objects.
* Graph-level lists: 0x0015 = the plots (uint32 n, n x uint32 plot id);
  0x0016 = the data sets shown (uint16 n, n x (uint32 fenID + 8 x 0xff));
  0x00a0 = the same (uint32 2, uint32 n, n x 32 bytes: fenID, -1, -1, -2,
  -1, -1, -1, -1); 0x0091 = uint32 n, n x uint32 0. A plot that is not in all
  of them is not drawn (found by adding plots; the entries are written the way
  Prism itself saves them).
* One PLOT per plotted data set: records
      8020 84 00db 8028 0029 009c 4028 0030 0031 0078 00a9 4020
  Prism draws them in file order (later = on top).
  - 8028 bytes 0-3: plot id (= its 00db id); bytes 4-5: fenID of the data set
    it draws (0xfffd = none); byte 8: error-bar direction (2 = both);
    byte 12: what the error bar shows: 1 = SD, 2 = SEM, 3 = 95% CI, 4 = range.
    (Measured: the bundled template had 1, i.e. it drew mean +/- SD although
    its data set was titled "mean +/- SEM" - so did every V2.2 export; checked
    against SD, SEM and t(0.975, n-1)*SEM computed from the data, to < 1 %.)
    Byte 113 bit 0x08: the data set is not listed in the legend (without it
    Prism adds a legend as soon as a graph shows more than one data set).
  - 009c byte 8: 1 = the symbols are joined by a line, 0 = no line (V2.5; the
    look template has 0 - a mean line width of 0 writes 0).
  - 009c byte 71: error bar style: 0 = none, 1 = bars with caps,
    2 = bars without caps, 3 = dotted envelope lines, 4 = envelope lines.
    No byte of the plot (all 461 bytes changed one at a time and every byte
    copied from a Prism example with a shaded band) gave a shaded band for a
    data set; the shaded bands in Prism's examples belong to fitted curves.
  - 009c byte 109: symbol: 0 none, 1 square, 2 triangle, 3 triangle down,
    4 diamond, 5 circle (6-10 the open versions).
  - 009c float32 @261: connecting-line thickness in units of 0.12 pt (Prism
    draws whole units: 1.0 pt -> 0.96 pt): 6.0 = 0.72 pt (the template).
    float32 @269: error-bar line thickness, same unit. float32 @289: symbol
    size; symbol diameter = 1.44 pt x size (drawn to about 0.12 pt);
    negative = automatic (the template has -3).
  - 009c bytes 313-316: the data set's fenID again (kept equal to 8028 4-5).
* Colours are taken from the compressed "Zval" dictionary (record 0x0852:
  "Zval", uint32 compressed length, uint32 length, zlib data). Its
  SEDObject_Array has one entry per 00db object, in file order; a plot's entry
  holds XYPlot_Map / PCFF_Plot::connectlinecolor (the line), errorcolor (error
  bars), symbolcolor (symbol fill and border), fillcolor ... as RGBA.
  PlotWithPoints_Array has one entry per plot. The 24-bit RGB copies in 8028
  (bytes 72, 80) and 009c (209, 221, 241) are NOT what Prism draws from
  (changing only them changed nothing); they are kept in step anyway. Zval
  values are "Mval" <uint32 type> <uint32 length of the content> ... "Mend";
  dictionaries (type 5) are "Dkey" <len> key "Dval" value ... "Dfin"; arrays
  (type 6) are "Asiz" <n> then n x ("Aval" + value) then "Afin".
* Axes: record 0x0017, one per axis (X, Y, right Y): float64 data min @0,
  data max @8, axis min @16, axis max @24, axis min again @32; uint16 @40:
  0x10 = automatic range, 0x1c = range set by hand (the same flag is in the
  axis' 0x00a5 record at @4 - that one is what Prism obeys; @6 bit 0 = tick
  interval set by hand); uint16 @54 = id of the axis' first segment. The
  segment record 0x8025 (uint16 @0 = segment id) holds float64 min @2,
  max @10, (max - min) / 1500 @18, major tick interval @54 and first tick @70
  (= min). Ground truth: Prism's own script command SetAxisLimits wrote
  exactly these fields. (The template's X axis starts its ticks at 0, so an X
  range from -10 shows ticks 0, 10, ... on an axis that starts at -10.)
* Texts: 0x902b (header, 18 bytes: role 0x81 title, 0x82 X title, 0x83 Y
  title, 0x84 right-Y title; uint16 @6 = text length in bytes), 0x102c (the
  text), 0x102d (the style run: uint16 1, uint16 n, uint32 start, then n x
  (uint16 id, uint32 value); id 1 = size in pt, 9 = size x 1000, 2 = bold,
  6 = rotation in 0.1 degree, 10 = code page) and 0x502b (end); the text
  object's 0x00a9 record keeps a copy of the size x 1000 at @16. Bit 0x1000 of
  these four tags means the text is UTF-8 (code page 65001); without it
  (files saved by Prism on Windows) the text is cp1252. Checked: UTF-8 text
  with the byte length shows "\u00b5 \u00b1 / \u0394 \u00e9" correctly; a
  cp1252 text switched to UTF-8 (tags + code page) does too; V2.2 wrote cp1252
  bytes into UTF-8 texts (wrong for any non-ASCII character).
* Tick labels: float32 @33 of each axis' 0x00ad records = font size in pt.

A user's own template ("Choose style...") gets the style only when it was made
from PeterPiper's template (changed and saved in Prism: its graph keeps the id
TEMPLATE_GRAPH_UID; checked with a Prism-saved copy). Any other Prism graph
gets only the data and the texts (as in V2.2): on Prism's own example graphs
the edits were accepted but the extra cell plots were not drawn, so nothing
else is written there.
"""
from __future__ import annotations

import math
import struct
import zlib
from typing import Dict, List, Optional, Sequence, Tuple

# Which GraphStyle fields the .prism export applies ("yes"), verified in Prism 11.
SUPPORT: Dict[str, str] = {
    "show_mean": "no",
    "error": "yes",
    "error_style": "no",          # "bars" yes; Prism draws no shaded band for data
    "mean_colour": "yes",
    "mean_width": "yes",
    "symbol": "yes",
    "symbol_size": "yes",
    "show_cells": "yes",
    "cell_colour": "yes",
    "cell_width": "yes",
    "title": "yes",
    "x_title": "yes",
    "y_title": "yes",
    "x_min": "yes", "x_max": "yes", "y_min": "yes", "y_max": "yes",
    "font_pt": "yes",
    "baseline_line": "no",
}

# The graph of templates/PeterPiper_timecourse.prism; Prism keeps this id when the
# file is changed and saved, so a user's template made from it is recognised.
TEMPLATE_GRAPH_UID = "A0E3F48E-25ED-4AA5-B4E5-F5CE93C7C727"

ERROR_CODE = {"SD": 1, "SEM": 2, "95% CI": 3}
SYMBOL_CODE = {"none": 0, "square": 1, "triangle": 2, "diamond": 4, "circle": 5}
LEGEND_BYTE, LEGEND_HIDE = 113, 0x08   # 8028 flag: data set not listed in the legend
FIRST_NEW_ID = 0x1000                  # ids given to the extra (each cell) plots
LINE_UNIT_PT = 0.12          # thickness unit (pt) of the 009c line floats
CONNECT_BYTE = 8             # 009c byte 8: 1 = symbols joined by a line, 0 = not (V2.5,
                             # checked in Prism 11: the look template has 0)
SYMBOL_UNIT_PT = 1.44        # symbol diameter (pt) per unit of symbol size

_HEADER = 136
TAG_DB, TAG_PLOT, TAG_PSTYLE, TAG_COUNT = 0x00DB, 0x8028, 0x009C, 0x8018
TAG_ZVAL, TAG_AXIS, TAG_SEGMENT, TAG_PLOTLIST = 0x0852, 0x0017, 0x8025, 0x0015
TAG_AXMODE, AXIS_AUTO, AXIS_MANUAL = 0x00A5, 0x10, 0x1C


# ------------------------------------------------------------------ records
def records(b: bytes) -> List[Tuple[int, int, int]]:
    """[(offset, tag, payload length)] of a graph block; raises ValueError."""
    if b[:8] != b"PCFFGRA4":
        raise ValueError("not a Prism graph block")
    out, i = [], _HEADER
    while i < len(b) - 6:
        tag = struct.unpack_from("<H", b, i)[0]
        if tag & 0x4000:
            out.append((i, tag, 0))
            i += 2
            continue
        n = struct.unpack_from("<I", b, i + 2)[0]
        if n > len(b) - i - 6:
            raise ValueError(f"damaged graph block at byte {i}")
        out.append((i, tag, n))
        i += 6 + n
    return out


def _payload(b, rec) -> bytes:
    off, _t, n = rec
    return b[off + 6:off + 6 + n]


def _put(b: bytearray, rec, pos: int, data: bytes) -> None:
    off, _t, n = rec
    if pos < 0 or pos + len(data) > n:
        raise ValueError("field outside its record")
    b[off + 6 + pos:off + 6 + pos + len(data)] = data


# --------------------------------------------------------------------- Zval
def _zval(b: bytes, R) -> Optional[Tuple[tuple, bytes]]:
    for rec in R:
        if rec[1] == TAG_ZVAL:
            p = _payload(b, rec)
            if p[:4] == b"Zval":
                clen, n = struct.unpack_from("<II", p, 4)
                d = zlib.decompress(p[12:12 + clen])
                if len(d) == n:
                    return rec, d
    return None


def _zval_replace(b: bytes, rec, d: bytes) -> bytes:
    off, tag, n = rec
    p = b[off + 6:off + 6 + n]
    clen = struct.unpack_from("<I", p, 4)[0]
    comp = zlib.compress(d)
    np_ = b"Zval" + struct.pack("<II", len(comp), len(d)) + comp + p[12 + clen:]
    return b[:off] + struct.pack("<HI", tag, len(np_)) + np_ + b[off + 6 + n:]


def _zitems(d: bytes, o: int = 0):
    """Walk one Mval at o. Yields nothing; returns (end, node) where node is
    ('dict', start, end, {key: node}) / ('array', start, end, [node]) /
    ('value', value offset, length)."""
    if d[o:o + 4] != b"Mval":
        raise ValueError("bad Zval")
    typ, n = struct.unpack_from("<II", d, o + 4)
    if typ == 5:
        q, items = o + 12, {}
        while d[q:q + 4] == b"Dkey":
            kl = struct.unpack_from("<I", d, q + 4)[0]
            key = d[q + 8:q + 8 + kl].decode("latin-1")
            q += 8 + kl
            if d[q:q + 4] != b"Dval":
                raise ValueError("bad Zval")
            q, items[key] = _zitems(d, q + 4)
        if d[q:q + 4] != b"Dfin":
            raise ValueError("bad Zval")
        return q + 8, ("dict", o, q + 8, items)
    if typ == 6:
        q = o + 12
        if d[q:q + 4] != b"Asiz":
            raise ValueError("bad Zval")
        cnt = struct.unpack_from("<I", d, q + 4)[0]
        q += 8
        items = []
        for _ in range(cnt):
            if d[q:q + 4] != b"Aval":
                raise ValueError("bad Zval")
            start = q
            q, node = _zitems(d, q + 4)
            items.append(node + (start,))
        if d[q:q + 4] != b"Afin":
            raise ValueError("bad Zval")
        return q + 8, ("array", o, q + 8, items)
    return o + 12 + n + 4, ("value", o + 12, n)


def _plot_maps(d: bytes) -> Optional[list]:
    """SEDObject_Array entries (one per 00db object, file order)."""
    _end, root = _zitems(d)
    sed = root[3].get("SEDObject_Array")
    return sed[3] if sed and sed[0] == "array" else None


_PLOT_COLOURS = ("connectlinecolor", "errorcolor", "symbolcolor", "symbolBorderColor",
                 "fillcolor", "patterncolor", "BarBoxBordercolor")


def _set_plot_colour(d: bytearray, entry, rgb: Tuple[int, int, int]) -> bool:
    if entry[0] != "dict" or "XYPlot_Map" not in entry[3]:
        return False
    m = entry[3]["XYPlot_Map"][3]
    done = False
    for k in _PLOT_COLOURS:
        node = m.get(f"PCFF_Plot::{k}")
        if node and node[0] == "value" and node[2] == 4:
            d[node[1]:node[1] + 3] = bytes(rgb)
            d[node[1] + 3] = 0xFF
            done = True
    return done


# -------------------------------------------------------------------- plots
def plots(b: bytes, R=None) -> List[dict]:
    """The plot objects: [{'i8028', 'i9c', 'idb', 'id', 'fen', 'first', 'last'}]
    (record indices; first/last = the plot's 8020 ... 4020 records)."""
    R = R or records(b)
    out = []
    for k, (off, tag, n) in enumerate(R):
        if tag != TAG_PLOT or n < 64 or k < 3 or k + 2 >= len(R):
            continue
        if R[k + 2][1] != TAG_PSTYLE or R[k - 1][1] != TAG_DB or R[k + 2][2] < 317:
            continue
        p = _payload(b, R[k])
        last = next((j for j in range(k + 3, min(k + 12, len(R))) if R[j][1] == 0x4020), None)
        if last is None or R[k - 3][1] != 0x8020:
            continue
        out.append({"i8028": k, "i9c": k + 2, "idb": k - 1, "first": k - 3, "last": last,
                    "id": struct.unpack_from("<I", p, 0)[0],
                    "fen": struct.unpack_from("<H", p, 4)[0]})
    return out


def _db_index(R, k_db: int) -> int:
    """Position of a 00db object among all 00db objects (= its Zval index)."""
    return sum(1 for j in range(k_db) if R[j][1] == TAG_DB)


def _line_units(pt) -> float:
    """Line thickness in Prism's unit (0.12 pt; Prism draws whole units)."""
    return float(max(1, round(max(0.0, float(pt)) / LINE_UNIT_PT)))


def _rgb(c: str) -> Tuple[int, int, int]:
    c = str(c).strip().lstrip("#")
    if len(c) != 6:
        raise ValueError(f"colour {c!r}")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _style_plot(b: bytearray, R, pl: dict, zd: Optional[bytearray], zmaps, *,
                error: Optional[str] = None, bars: Optional[bool] = None,
                colour: Optional[str] = None, width: Optional[float] = None,
                symbol: Optional[str] = None, symbol_size: Optional[float] = None) -> List[str]:
    """Edit one plot in place; returns the names of what was set."""
    r28, r9c = R[pl["i8028"]], R[pl["i9c"]]
    done = []
    if error is not None:
        if error in ERROR_CODE:
            _put(b, r28, 12, bytes([ERROR_CODE[error]]))
            _put(b, r28, 8, bytes([2]))
            if _payload(b, r9c)[71] in (0, 3, 4):     # V2.5: keep the template's own
                _put(b, r9c, 71, bytes([1]))            # capped-bar style (5) as it is
        else:                                      # "none"
            _put(b, r9c, 71, bytes([0]))
        done.append("error")
    if colour is not None and zd is not None and zmaps is not None:
        idx = _db_index(R, pl["idb"])
        if idx < len(zmaps) and _set_plot_colour(zd, zmaps[idx], _rgb(colour)):
            rgb = bytes(_rgb(colour))
            for pos in (72, 80):
                _put(b, r28, pos, rgb)
            for pos in (209, 221, 241):
                _put(b, r9c, pos, rgb)
            done.append("colour")
    if width is not None:
        if float(width) < LINE_UNIT_PT / 2:            # V2.5: 0 = no connecting line
            _put(b, r9c, CONNECT_BYTE, bytes([0]))
        else:
            v = struct.pack("<f", _line_units(width))
            _put(b, r9c, CONNECT_BYTE, bytes([1]))
            _put(b, r9c, 261, v)
            _put(b, r9c, 269, v)
        done.append("width")
    if symbol is not None and symbol in SYMBOL_CODE:
        _put(b, r9c, 109, bytes([SYMBOL_CODE[symbol]]))
        done.append("symbol")
    if symbol_size is not None:
        _put(b, r9c, 289, struct.pack("<f", max(0.1, float(symbol_size)) / SYMBOL_UNIT_PT))
        done.append("symbol_size")
    return done


# --------------------------------------------------------------------- axes
def _nice_step(span: float) -> float:
    if not span > 0:
        return 1.0
    raw = span / 5.0
    e = 10.0 ** math.floor(math.log10(raw))
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= m * e * 1.0000001:
            return m * e
    return 10.0 * e


def _set_axis(b: bytearray, R, which: int, lo: Optional[float], hi: Optional[float],
              data_lo: float, data_hi: float) -> bool:
    """which: 0 = X, 1 = Y (the 0x0017 / 0x00a5 records in order). lo/hi None =
    automatic. Only one end given: the other is the data's end (+/- 5 %)."""
    axes = [rec for rec in R if rec[1] == TAG_AXIS and rec[2] >= 56]
    modes = [rec for rec in R if rec[1] == TAG_AXMODE and rec[2] >= 8]
    if which >= len(axes) or which >= len(modes):
        return False
    rec, mode = axes[which], modes[which]
    if lo is None and hi is None:
        _put(b, rec, 40, struct.pack("<H", AXIS_AUTO))
        _put(b, mode, 4, struct.pack("<H", AXIS_AUTO))
        # V2.7: and an automatic tick interval - the template's Y interval was set
        # by hand (1.0, for ratios), which drew a label at every unit of an
        # intensity axis (50 ... 100)
        _put(b, mode, 6, bytes([_payload(b, mode)[6] & ~0x01 & 0xFF]))
        return True
    pad = 0.05 * ((data_hi - data_lo) or 1.0)
    lo = float(lo) if lo is not None else data_lo - pad
    hi = float(hi) if hi is not None else data_hi + pad
    if not (math.isfinite(lo) and math.isfinite(hi) and hi > lo):
        return False
    _put(b, rec, 16, struct.pack("<ddd", lo, hi, lo))
    _put(b, rec, 40, struct.pack("<H", AXIS_MANUAL))
    _put(b, mode, 4, struct.pack("<H", AXIS_MANUAL))
    seg_id = struct.unpack_from("<H", _payload(b, rec), 54)[0]
    step = _nice_step(hi - lo)
    for seg in R:
        if seg[1] == TAG_SEGMENT and seg[2] >= 62 and \
                struct.unpack_from("<H", _payload(b, seg), 0)[0] == seg_id:
            _put(b, seg, 2, struct.pack("<ddd", lo, hi, (hi - lo) / 1500.0))
            _put(b, seg, 54, struct.pack("<d", step))
            _put(b, seg, 70, struct.pack("<d", lo))
            _put(b, mode, 6, bytes([_payload(b, mode)[6] | 0x01]))   # interval set by hand
            break
    return True


# -------------------------------------------------------------------- texts
TEXT_ROLE = {"title": 0x81, "x": 0x82, "y": 0x83, "y2": 0x84}


def set_text(b: bytes, role: str, text: str) -> bytes:
    """Replace a graph text (title, X / Y axis title) keeping its style.
    UTF-8 texts (tag bit 0x1000) are written as UTF-8; cp1252 texts (files
    saved by Prism on Windows) as cp1252 when the text fits, otherwise the text
    is switched to UTF-8 (tags + code page 65001). Unchanged if not found."""
    code = TEXT_ROLE[role]
    text = text.replace("\r\n", "\n").replace("\n", "\r")
    R = records(b)
    for k, (off, tag, n) in enumerate(R):
        if (tag & ~0x1000) != 0x802B or n != 18 or k + 2 >= len(R):
            continue
        hdr = bytearray(_payload(b, R[k]))
        t_off, t_tag, t_n = R[k + 1]
        if hdr[0] != code or (t_tag & ~0x1000) != 0x002C:
            continue
        if struct.unpack_from("<H", hdr, 6)[0] != t_n:
            continue
        utf8 = bool(tag & 0x1000)
        if not utf8:
            try:
                new = text.encode("cp1252")
            except UnicodeEncodeError:
                return set_text(_to_utf8(b, R, k), role, text.replace("\r", "\n"))
        else:
            new = text.encode("utf-8")
        struct.pack_into("<H", hdr, 6, len(new))
        return (b[:off + 6] + bytes(hdr) + struct.pack("<HI", t_tag, len(new)) + new +
                b[t_off + 6 + t_n:])
    return b


def _to_utf8(b: bytes, R, k: int) -> bytes:
    """Switch one cp1252 text object to UTF-8 (its 2b / 2c / 2d / end tags get
    bit 0x1000; its style run's code page becomes 65001)."""
    out = bytearray(b)
    for j in range(k, min(k + 6, len(R))):
        off, tag, n = R[j]
        base = tag & ~0x1000
        if base in (0x802B, 0x002C, 0x002D, 0x402B):
            struct.pack_into("<H", out, off, tag | 0x1000)
        if base == 0x002D and n >= 8:
            cnt = struct.unpack_from("<H", out, off + 6 + 2)[0]
            for i in range(cnt):
                p = off + 6 + 8 + 6 * i
                if p + 6 <= off + 6 + n and struct.unpack_from("<H", out, p)[0] == 10:
                    struct.pack_into("<I", out, p + 2, 65001)
        if base == 0x402B:
            break
    # re-decode the old text so the caller can rewrite it as UTF-8
    t_off, t_tag, t_n = R[k + 1]
    old = bytes(out[t_off + 6:t_off + 6 + t_n]).decode("cp1252", "replace").encode("utf-8")
    hdr = bytearray(out[R[k][0] + 6:R[k][0] + 24])
    struct.pack_into("<H", hdr, 6, len(old))
    return (bytes(out[:R[k][0] + 6]) + bytes(hdr) + struct.pack("<HI", t_tag | 0x1000, len(old)) +
            old + bytes(out[t_off + 6 + t_n:]))


TICK_SCALE = 0.9      # tick labels = 0.9 x font_pt (as graphstyle.draw_matplotlib)


def _set_fonts(b: bytearray, R, font_pt: float) -> bool:
    """Graph title and axis titles = font_pt, tick labels = 0.9 x font_pt."""
    fs = max(4.0, min(72.0, float(font_pt)))
    done = False
    for k, (off, tag, n) in enumerate(R):
        if (tag & ~0x1000) == 0x802B and n == 18 and b[off + 6] in (0x81, 0x82, 0x83):
            for j in range(k + 1, min(k + 4, len(R))):
                o2, t2, n2 = R[j]
                if (t2 & ~0x1000) != 0x002D or n2 < 8:
                    continue
                cnt = struct.unpack_from("<H", b, o2 + 6 + 2)[0]
                old9 = None
                for i in range(cnt):
                    p = o2 + 6 + 8 + 6 * i
                    if p + 6 > o2 + 6 + n2:
                        break
                    pid = struct.unpack_from("<H", b, p)[0]
                    if pid == 1:
                        struct.pack_into("<I", b, p + 2, int(round(fs)))
                    elif pid == 9:
                        old9 = struct.unpack_from("<I", b, p + 2)[0]
                        struct.pack_into("<I", b, p + 2, int(round(fs * 1000)))
                        done = True
                # the object's 00a9 record keeps a copy of the size x 1000
                for jj in range(j + 1, min(j + 6, len(R))):
                    o3, t3, n3 = R[jj]
                    if t3 == 0x00A9 and n3 >= 20 and old9 is not None and \
                            struct.unpack_from("<I", b, o3 + 6 + 16)[0] == old9:
                        struct.pack_into("<I", b, o3 + 6 + 16, int(round(fs * 1000)))
                        break
                break
    for off, tag, n in R:
        if tag == 0x00AD and n >= 37:
            struct.pack_into("<f", b, off + 6 + 33, fs * TICK_SCALE)
            done = True
    return done


# -------------------------------------------------------------------- apply
def fix_template(gb: bytes, data_fen: int, error: str = "SEM") -> bytes:
    """The bundled template as PeterPiper means it: the mean plot shows `error`
    (it was saved showing SD) and the X axis range is automatic (it was fixed
    at -5..55 min, which cut off longer movies)."""
    b = bytearray(gb)
    R = records(gb)
    pls = [p for p in plots(gb, R) if p["fen"] == data_fen]
    if pls:
        _style_plot(b, R, pls[-1], None, None, error=error)
    _set_axis(b, R, 0, None, None, 0.0, 1.0)
    return bytes(b)


def apply_style(gb: bytes, style: Optional[dict], *, data_fen: int,
                y_range: Tuple[float, float], x_range: Tuple[float, float]
                ) -> Tuple[bytes, List[str], List[str]]:
    """
    Apply a GraphStyle dict to a graph block. data_fen: fenID of the data set
    the mean plot draws (the graph table's first data set). y_range / x_range:
    (min, max) of what is plotted, used when only one end of an axis is set.
    Returns (new block, fields applied, fields not applied).
    """
    if not style:
        return gb, [], []
    applied, skipped = [], []
    b = bytearray(gb)
    R = records(gb)
    pls = [p for p in plots(gb, R) if p["fen"] == data_fen]
    z = _zval(gb, R)
    zd = bytearray(z[1]) if z else None
    zmaps = _plot_maps(bytes(zd)) if zd is not None else None
    keep: List[str] = []
    if pls:
        pl = pls[-1]
        # V2.5: a look field whose value is already the template's own (the bundled
        # template's look is GraphStyle's default) is left byte-for-byte as the
        # template has it (its black symbol borders, its 0.72 pt error bars under a
        # 0.59 pt line, its own title / tick sizes) - Prism draws the same look.
        p9 = _payload(b, R[pl["i9c"]])
        cur_col = _plot_rgb(bytes(zd) if zd is not None else None, zmaps, R, pl)
        if cur_col and str(style.get("mean_colour", "")).upper() == cur_col.upper():
            keep.append("mean_colour")
        cur_w = struct.unpack_from("<f", p9, 261)[0]
        w_ = style.get("mean_width")
        # (the look template stores a 0.59 pt line but hides it - byte 8 = 0; a style
        # width > 0 shows the line, as the live graph and the PNG draw it; 0 = hidden)
        if w_ is not None and (
                (p9[CONNECT_BYTE] == 0 and float(w_) < LINE_UNIT_PT / 2) or
                (p9[CONNECT_BYTE] != 0 and math.isfinite(cur_w) and cur_w > 0 and
                 float(w_) >= LINE_UNIT_PT / 2 and
                 _line_units(w_) == float(max(1, round(cur_w))))):
            keep.append("mean_width")
        cur_s = struct.unpack_from("<f", p9, 289)[0]
        if style.get("symbol_size") is not None and math.isfinite(cur_s) and cur_s > 0 and \
                abs(float(style["symbol_size"]) - cur_s * SYMBOL_UNIT_PT) < 0.01:
            keep.append("symbol_size")
    if style.get("font_pt") is not None:
        cur_f = _read_font(gb, R)
        if cur_f and abs(float(style["font_pt"]) - cur_f) < 0.01:
            keep.append("font_pt")
    if pls:
        err = str(style.get("error", "SEM"))
        if style.get("error_style", "bars") == "bars" or err == "none":
            done = _style_plot(b, R, pl, zd, zmaps, error=err if err in ERROR_CODE or err == "none" else None)
            applied += ["error"] if done else []
        else:
            done = _style_plot(b, R, pl, zd, zmaps, error=err if err in ERROR_CODE else None)
            applied += ["error"] if done else []
            skipped.append("error_style")
        sym = str(style.get("symbol", "circle"))
        done = _style_plot(
            b, R, pl, zd, zmaps,
            colour=None if "mean_colour" in keep else style.get("mean_colour", "#000000"),
            width=None if "mean_width" in keep else style.get("mean_width", 1.0), symbol=sym,
            symbol_size=None if "symbol_size" in keep else style.get("symbol_size", 3.0))
        applied += [f for f, k in (("mean_colour", "colour"), ("mean_width", "width"),
                                   ("symbol", "symbol"), ("symbol_size", "symbol_size")) if k in done]
        applied += [f for f in keep if f != "font_pt"]
    else:
        skipped += ["error", "error_style", "mean_colour", "mean_width", "symbol", "symbol_size"]
    ok_x = _set_axis(b, R, 0, style.get("x_min"), style.get("x_max"), *x_range)
    ok_y = _set_axis(b, R, 1, style.get("y_min"), style.get("y_max"), *y_range)
    applied += (["x_min", "x_max"] if ok_x else []) + (["y_min", "y_max"] if ok_y else [])
    if SUPPORT.get("font_pt") == "yes" and style.get("font_pt") is not None:
        if "font_pt" in keep or _set_fonts(b, R, style["font_pt"]):
            applied.append("font_pt")
    out = bytes(b)
    if z and zd is not None:
        out = _zval_replace(out, z[0], bytes(zd))
    skipped += [f for f, v in SUPPORT.items() if v != "yes" and f not in skipped
                and f not in ("title", "x_title", "y_title")]
    return out, sorted(set(applied)), sorted(set(skipped) - set(applied))


# --------------------------------------------------------------- each cell
def _zval_insert_copies(d: bytes, array_key: str, src_index: int, at_index: int,
                        count: int, patch=None) -> bytes:
    """Insert `count` copies of element src_index of a top-level Zval array
    before element at_index (fixing the element count and the lengths of the
    array and the root). patch(bytes) -> bytes may edit each copy (same length)."""
    _end, root = _zitems(d)
    arr = root[3].get(array_key)
    if not arr or arr[0] != "array" or not (0 <= src_index < len(arr[3])):
        raise ValueError(f"no {array_key}")
    el = arr[3][src_index]
    start, end = el[-1], el[2]
    chunk = d[start:end]
    if patch is not None:
        chunk = patch(chunk)
    ins_at = arr[3][at_index][-1] if at_index < len(arr[3]) else arr[2] - 8
    add = chunk * count
    out = bytearray(d[:ins_at] + add + d[ins_at:])
    a_off = arr[1]
    struct.pack_into("<I", out, a_off + 8, struct.unpack_from("<I", out, a_off + 8)[0] + len(add))
    struct.pack_into("<I", out, a_off + 16, struct.unpack_from("<I", out, a_off + 16)[0] + count)
    struct.pack_into("<I", out, 8, struct.unpack_from("<I", out, 8)[0] + len(add))
    return bytes(out)


def _add_dataset_entries(b: bytes, fens: List[int]) -> bytes:
    """Add data sets to the graph's data-set lists (records 0x0016: uint16 n +
    n x (uint32 fenID, 8 x 0xff); 0x00a0: uint32 2, uint32 n + n x 32 bytes
    (fenID, -1, -1, -2, -1, -1, -1, -1); 0x0091: uint32 n + n x uint32 0),
    in the form Prism itself saves them."""
    for tag in (0x0016, 0x00A0, 0x0091):
        for off, t, n in records(b):
            if t != tag:
                continue
            p = b[off + 6:off + 6 + n]
            if tag == 0x0016:
                cnt = struct.unpack_from("<H", p, 0)[0]
                if n != 2 + 12 * cnt:
                    raise ValueError("unknown data set list")
                p = struct.pack("<H", cnt + len(fens)) + p[2:] + b"".join(
                    struct.pack("<I", f) + b"\xff" * 8 for f in fens)
            elif tag == 0x00A0:
                cnt = struct.unpack_from("<I", p, 4)[0]
                if n != 8 + 32 * cnt:
                    raise ValueError("unknown data set list")
                p = p[:4] + struct.pack("<I", cnt + len(fens)) + p[8:] + b"".join(
                    struct.pack("<Iiiiiiii", f, -1, -1, -2, -1, -1, -1, -1) for f in fens)
            else:
                cnt = struct.unpack_from("<I", p, 0)[0]
                if n != 4 + 4 * cnt:
                    raise ValueError("unknown data set list")
                p = struct.pack("<I", cnt + len(fens)) + p[4:] + b"\x00\x00\x00\x00" * len(fens)
            b = b[:off] + struct.pack("<HI", t, len(p)) + p + b[off + 6 + n:]
            break
        else:
            raise ValueError("this graph has no data set list")
    return b


def add_cell_plots(gb: bytes, data_fen: int, cell_fens: Sequence[int], colour: str,
                   width: float) -> bytes:
    """One extra plot per cell (a copy of the mean plot bound to that cell's data
    set): thin line, no symbols, no error bars, drawn behind the mean."""
    return _copy_plots(gb, data_fen, cell_fens, [colour] * len(cell_fens), cells=True,
                       width=width)


def add_dataset_plots(gb: bytes, data_fen: int, fens: Sequence[int],
                      colours: Sequence[str]) -> bytes:
    """V2.4 'Compare runs': one more plot per data set (fens), each a copy of the
    mean plot (same error, symbol, line width) in its own colour and listed in
    the legend (Prism shows a legend of the data set titles). Drawn behind the
    mean plot's data set."""
    return _copy_plots(gb, data_fen, fens, colours, cells=False)


def _copy_plots(gb: bytes, data_fen: int, cell_fens: Sequence[int], colours: Sequence[str],
                cells: bool, width: float = 0.5) -> bytes:
    if not cell_fens:
        return gb
    R = records(gb)
    pls = [p for p in plots(gb, R) if p["fen"] == data_fen]
    z = _zval(gb, R)
    if not pls or z is None:
        raise ValueError("this graph has no plot of the data or no colour table")
    pl = pls[-1]
    g0 = R[pl["first"]][0]
    g1 = R[pl["last"]][0] + 2
    proto = gb[g0:g1]
    rel = {k: R[k][0] - g0 for k in (pl["idb"], pl["i8028"], pl["i9c"])}
    sub = [(off - g0, tag, n) for off, tag, n in R[pl["first"]:pl["last"] + 1]]
    rgbs = [bytes(_rgb(c)) for c in colours]
    used = {struct.unpack_from("<I", gb, off + 6 + 158)[0] for off, tag, n in R
            if tag == TAG_DB and n >= 162}
    new_id = FIRST_NEW_ID
    copies, new_ids = [], []
    for fen, rgb in zip(cell_fens, rgbs):
        while new_id in used:
            new_id += 1
        used.add(new_id)
        new_ids.append(new_id)
        c = bytearray(proto)
        struct.pack_into("<I", c, rel[pl["idb"]] + 6 + 158, new_id)
        struct.pack_into("<I", c, rel[pl["i8028"]] + 6, new_id)
        struct.pack_into("<H", c, rel[pl["i8028"]] + 6 + 4, fen)
        o9 = rel[pl["i9c"]] + 6
        struct.pack_into("<I", c, o9 + 313, fen)
        o28 = rel[pl["i8028"]] + 6
        if cells:
            c[o9 + 71] = 0                               # no error bars
            c[o9 + 109] = 0                              # no symbols
            w = struct.pack("<f", _line_units(width))
            c[o9 + 261:o9 + 265] = w
            c[o9 + CONNECT_BYTE] = 1                     # drawn as a line
            c[o28 + LEGEND_BYTE] |= LEGEND_HIDE          # not listed in the legend
        for pos in (72, 80):
            c[o28 + pos:o28 + pos + 3] = rgb
        for pos in (209, 221, 241):
            c[o9 + pos:o9 + pos + 3] = rgb
        copies.append(bytes(c))
    out = bytearray(gb[:g0] + b"".join(copies) + gb[g0:])
    if cells:      # the mean is not listed either (Prism would otherwise add a legend)
        out[g0 + len(b"".join(copies)) + rel[pl["i8028"]] + 6 + LEGEND_BYTE] |= LEGEND_HIDE
    # object count
    for off, tag, n in R:
        if tag == TAG_COUNT and n >= 8 and off < g0:
            struct.pack_into("<I", out, off + 6 + 4,
                             struct.unpack_from("<I", out, off + 6 + 4)[0] + len(cell_fens))
            break
    # colour table: copy the mean plot's entries, recoloured
    zrec, zd = z
    idx = _db_index(R, pl["idb"])
    pidx = [p["i8028"] for p in plots(gb, R)].index(pl["i8028"])

    def recolour(chunk: bytes, rgb: bytes) -> bytes:
        c = bytearray(chunk)
        for key in _PLOT_COLOURS:
            tag_ = f"PCFF_Plot::{key}".encode()
            i = c.find(tag_)
            if i >= 0:
                v = c.find(b"Mval", i) + 12
                c[v:v + 3] = rgb
                c[v + 3] = 0xFF
        return bytes(c)
    if len(set(rgbs)) == 1:
        zd = _zval_insert_copies(zd, "SEDObject_Array", idx, idx, len(cell_fens),
                                 lambda ch: recolour(ch, rgbs[0]))
    else:                       # one colour each: insert one at a time, in file order
        for j, rgb in enumerate(rgbs):
            zd = _zval_insert_copies(zd, "SEDObject_Array", idx + j, idx + j, 1,
                                     lambda ch, rgb=rgb: recolour(ch, rgb))
    try:
        zd = _zval_insert_copies(zd, "PlotWithPoints_Array", pidx, pidx, len(cell_fens))
    except ValueError:
        pass
    out = bytes(out)
    # the graph's list of plots (record 0x0015: uint32 count, uint32 ids)
    for off, tag, n in records(out):
        if tag == TAG_PLOTLIST and n >= 4:
            cnt = struct.unpack_from("<I", out, off + 6)[0]
            if n == 4 + 4 * cnt and pl["id"] in struct.unpack_from(f"<{cnt}I", out, off + 10):
                ids = struct.pack(f"<{len(new_ids)}I", *new_ids)
                body = struct.pack("<I", cnt + len(new_ids)) + out[off + 10:off + 6 + n] + ids
                out = out[:off] + struct.pack("<HI", tag, len(body)) + body + out[off + 6 + n:]
                break
    else:
        raise ValueError("this graph has no list of plots")
    out = _add_dataset_entries(out, list(cell_fens))
    for rec in records(out):
        if rec[1] == TAG_ZVAL:
            return _zval_replace(out, rec, zd)
    return out


# ------------------------------------------------------------ read back (V2.4)
# "Load look from a Prism file...": the inverse of apply_style / add_cell_plots.
# Only what is read from fields checked in Prism 11 (see the layout above).
READ_FIELDS = ("error", "error_style", "mean_colour", "mean_width", "symbol", "symbol_size",
               "show_cells", "cell_colour", "cell_width", "x_min", "x_max", "y_min", "y_max",
               "font_pt", "title", "x_title", "y_title")
_SYMBOL_READ = {0: "none", 1: "square", 2: "triangle", 3: "triangle", 4: "diamond", 5: "circle",
                6: "square", 7: "triangle", 8: "triangle", 9: "diamond", 10: "circle"}
_ERROR_READ = {v: k for k, v in ERROR_CODE.items()}
NO_PLOT_FEN = 0xFFFD
AUTO_X_TITLES = ("Time from baseline (min)", "Timepoints from baseline")   # Experiment.time_axis


def _plot_rgb(zd: Optional[bytes], zmaps, R, pl: dict, key: str = "connectlinecolor"
              ) -> Optional[str]:
    if zd is None or zmaps is None:
        return None
    idx = _db_index(R, pl["idb"])
    if idx >= len(zmaps) or zmaps[idx][0] != "dict" or "XYPlot_Map" not in zmaps[idx][3]:
        return None
    node = zmaps[idx][3]["XYPlot_Map"][3].get(f"PCFF_Plot::{key}")
    if not node or node[0] != "value" or node[2] != 4:
        return None
    r, g, b = zd[node[1]:node[1] + 3]
    return f"#{r:02X}{g:02X}{b:02X}"


def read_texts(b: bytes) -> Dict[str, str]:
    """{role: text} of the graph title ('title') and axis titles ('x', 'y')."""
    out: Dict[str, str] = {}
    R = records(b)
    roles = {v: k for k, v in TEXT_ROLE.items()}
    for k, (off, tag, n) in enumerate(R):
        if (tag & ~0x1000) != 0x802B or n != 18 or k + 1 >= len(R):
            continue
        role = roles.get(b[off + 6])
        t_off, t_tag, t_n = R[k + 1]
        if role is None or role in out or (t_tag & ~0x1000) != 0x002C:
            continue
        raw = b[t_off + 6:t_off + 6 + t_n]
        txt = raw.decode("utf-8", "replace") if tag & 0x1000 else raw.decode("cp1252", "replace")
        out[role] = txt.replace("\r\n", "\n").replace("\r", "\n")
    return out


def _read_font(b: bytes, R) -> Optional[float]:
    """Size (pt) of the axis titles (X title first, then Y, then the graph title)."""
    found: Dict[int, float] = {}
    for k, (off, tag, n) in enumerate(R):
        if (tag & ~0x1000) != 0x802B or n != 18 or b[off + 6] not in (0x81, 0x82, 0x83):
            continue
        for j in range(k + 1, min(k + 4, len(R))):
            o2, t2, n2 = R[j]
            if (t2 & ~0x1000) != 0x002D or n2 < 8:
                continue
            cnt = struct.unpack_from("<H", b, o2 + 6 + 2)[0]
            v1 = v9 = None
            for i in range(cnt):
                p = o2 + 6 + 8 + 6 * i
                if p + 6 > o2 + 6 + n2:
                    break
                pid, val = struct.unpack_from("<HI", b, p)
                if pid == 1:
                    v1 = float(val)
                elif pid == 9:
                    v9 = val / 1000.0
            v = v9 if v9 else v1
            if v and b[off + 6] not in found:
                found[b[off + 6]] = v
            break
    for role in (0x82, 0x83, 0x81):
        if role in found:
            return found[role]
    return None


def _read_axis(b: bytes, R, which: int) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """(min, max) when the range is set by hand, (None, None) when automatic,
    None when the axis is not found."""
    axes = [rec for rec in R if rec[1] == TAG_AXIS and rec[2] >= 56]
    modes = [rec for rec in R if rec[1] == TAG_AXMODE and rec[2] >= 8]
    if which >= len(axes):
        return None
    p = _payload(b, axes[which])
    flag = struct.unpack_from("<H", _payload(b, modes[which]), 4)[0] if which < len(modes) \
        else struct.unpack_from("<H", p, 40)[0]
    if flag != AXIS_MANUAL:
        return None, None
    lo, hi = struct.unpack_from("<dd", p, 16)
    if not (math.isfinite(lo) and math.isfinite(hi) and hi > lo):
        return None
    return float(lo), float(hi)


def read_graph_style(gb: bytes, data_fen: Optional[int] = None) -> Tuple[dict, List[str]]:
    """(GraphStyle fields read from one graph block, plain-language notes).
    The mean plot is the one drawing data_fen (the graph table's first data
    set); without it (or not found) the plot drawn last that shows data.
    Fields that cannot be read are left out of the dict."""
    R = records(gb)
    pls = [p for p in plots(gb, R) if p["fen"] != NO_PLOT_FEN]
    if not pls:
        raise ValueError("no plotted data")
    mean = next((p for p in reversed(pls) if p["fen"] == data_fen), None) \
        if data_fen is not None else None
    mean = mean or pls[-1]
    z = _zval(gb, R)
    zd = z[1] if z else None
    zmaps = _plot_maps(zd) if zd is not None else None
    out: dict = {}
    notes: List[str] = []
    p28, p9c = _payload(gb, R[mean["i8028"]]), _payload(gb, R[mean["i9c"]])
    if p9c[71] == 0:
        out["error"] = "none"
    elif p28[12] in _ERROR_READ:
        out["error"] = _ERROR_READ[p28[12]]
        if p9c[71] in (3, 4):
            notes.append("The Prism graph draws the error as lines above and below the mean; "
                         "PeterPiper shows error bars.")
    else:
        notes.append("Its error type (not SD, SEM or 95% CI) is not one PeterPiper draws - "
                     "your error type is kept.")
    out["error_style"] = "bars"
    sym = p9c[109]
    if sym in _SYMBOL_READ:
        out["symbol"] = _SYMBOL_READ[sym]
        if sym in (3, 8):
            notes.append("Prism's downward triangles are shown as triangles.")
        elif sym >= 6:
            notes.append("Prism's open (hollow) symbols are shown filled.")
    else:
        notes.append("Its symbol shape is not one PeterPiper draws - your symbol is kept.")
    w = struct.unpack_from("<f", p9c, 261)[0]
    if p9c[CONNECT_BYTE] == 0:                         # V2.5: symbols not joined
        out["mean_width"] = 0.0
    elif math.isfinite(w) and w >= 0:
        out["mean_width"] = round(w * LINE_UNIT_PT, 4)
    size = struct.unpack_from("<f", p9c, 289)[0]
    if math.isfinite(size) and size > 0:
        out["symbol_size"] = round(size * SYMBOL_UNIT_PT, 4)
    elif sym != 0:
        notes.append("Prism chooses its symbol size automatically there - your symbol size "
                     "is kept.")
    col = _plot_rgb(zd, zmaps, R, mean)
    if col:
        out["mean_colour"] = col
        ecol = _plot_rgb(zd, zmaps, R, mean, "errorcolor")
        if ecol and ecol != col and out.get("error") != "none":
            notes.append(f"The error bars there have their own colour ({ecol}); PeterPiper draws "
                         f"them in the mean colour.")
    else:
        notes.append("The mean's colour could not be read - your colour is kept.")
    others = [p for p in pls if p is not mean and p["fen"] != mean["fen"]]
    shown = [p for p in others if not _payload(gb, R[p["i8028"]])[LEGEND_BYTE] & LEGEND_HIDE]
    others = [p for p in others if p not in shown]       # each-cell lines: not in the legend
    if shown:
        notes.append(f"The graph shows {len(shown) + 1} data sets; the look of the first one "
                     f"was used.")
    out["show_cells"] = bool(others)
    if others:
        c = _plot_rgb(zd, zmaps, R, others[0])
        if c:
            out["cell_colour"] = c
        cw = struct.unpack_from("<f", _payload(gb, R[others[0]["i9c"]]), 261)[0]
        if math.isfinite(cw) and cw >= 0:
            out["cell_width"] = round(cw * LINE_UNIT_PT, 4)
    for which, (a, bb) in ((0, ("x_min", "x_max")), (1, ("y_min", "y_max"))):
        rng = _read_axis(gb, R, which)
        if rng is None:
            notes.append(f"The {'X' if which == 0 else 'Y'} axis range could not be read - "
                         f"yours is kept.")
        else:
            out[a], out[bb] = rng
    fs = _read_font(gb, R)
    if fs:
        out["font_pt"] = round(fs, 3)
    t = read_texts(gb)
    for role, f in (("title", "title"), ("x", "x_title"), ("y", "y_title")):
        if role in t:
            out[f] = t[role]
    return out, notes


def read_style(src, *, ignore_texts: bool = False) -> Tuple[dict, List[str]]:
    """
    The graph look of a .prism file (a path) or of one graph block (bytes):
    (dict of GraphStyle fields, plain-language notes). Only fields that can be
    read reliably are in the dict (READ_FIELDS); the notes say what was not
    taken over. From a file, texts that only name that file's data (the
    automatic axis titles, a title made by PeterPiper's default "{file} - {comp}
    (n = {n})") come back as the automatic ones; ignore_texts leaves every text
    out. Raises ValueError with a plain message when nothing usable is found.
    """
    import json
    import re
    import zipfile
    from pathlib import Path
    if isinstance(src, (bytes, bytearray)):
        st, notes = read_graph_style(bytes(src))
        if ignore_texts:
            for f in ("title", "x_title", "y_title"):
                st.pop(f, None)
        return st, notes
    from .safety import long_path
    p = Path(src)
    data_fen, quantity, n = None, None, None
    try:
        with zipfile.ZipFile(long_path(p)) as z:
            doc = json.loads(z.read("document.json"))
            gids = list((doc.get("sheets") or {}).get("graphs") or [])
            if not gids:
                raise ValueError(f"{p.name} has no graph. Make the graph in Prism, save the "
                                 f"file and try again.")
            gb = z.read(f"graphs/{gids[0]}/data.bin")
            for sid in (doc["sheets"].get("data") or [])[:1]:
                try:
                    tab = json.loads(z.read(f"data/sheets/{sid}/sheet.json"))["table"]
                    ds = json.loads(z.read(f"data/sets/{tab['dataSets'][0]}.json"))
                    data_fen = int(ds.get("fenID"))
                    title = str(ds.get("title") or "")
                    if "  (mean" in title:
                        quantity = title.split("  (mean", 1)[0]
                        if "n = " in title:
                            n = title.rsplit("n = ", 1)[1].rstrip(")").strip()
                except (KeyError, ValueError, TypeError, IndexError):
                    pass
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError):
        raise ValueError(f"{p.name} could not be read as a Prism project (.prism files are "
                         f"made by Prism 10 or newer).") from None
    try:
        st, notes = read_graph_style(gb, data_fen)
    except ValueError:
        raise ValueError(f"The graph in {p.name} shows no data PeterPiper can take a look from "
                         f"(it needs an XY graph with a line or symbols).") from None
    if len(gids) > 1:
        notes.append(f"The file has {len(gids)} graphs; the look of the first one was used.")
    if ignore_texts:
        for f in ("title", "x_title", "y_title"):
            st.pop(f, None)
        return st, notes
    # texts that only describe that file's data -> automatic
    if st.get("x_title") in AUTO_X_TITLES:
        st["x_title"] = ""
    if quantity and st.get("y_title") in (quantity, quantity.replace(" - ", " ", 1)):
        st["y_title"] = ""
    t = st.get("title")
    if t and n is not None:
        if re.fullmatch(r".+ - .+ \(n = " + re.escape(n) + r"\)", t, flags=re.S):
            st["title"] = "{file} - {comp} (n = {n})"
        elif f"n = {n}" in t:
            st["title"] = t.replace(f"n = {n}", "n = {n}")
    return st, notes


# ------------------------------------------------------- V2.5: the look template
# templates/PeterPiper_timecourse.prism holds ONE plot (the template's first data
# set). The look of the further data sets (compare / average graphs) - the
# symbol of each data set in turn - is in templates/PeterPiper_look.json, taken
# from the same Prism graph. These helpers edit plots of a graph block; each
# edit was checked by opening the result in GraphPad Prism 11 (dev_tests/
# test_prism_template.py renders every case and compares it with the template).
SYMBOL_CODES = {"none": 0, "square": 1, "triangle": 2, "triangle_down": 3, "diamond": 4,
                "circle": 5, "open_square": 6, "open_triangle": 7, "open_triangle_down": 8,
                "open_diamond": 9, "open_circle": 10}


def _zval_remove(d: bytes, array_key: str, index: int) -> bytes:
    """Remove element `index` of a top-level Zval array (fixing the element
    count and the lengths of the array and the root) - the inverse of
    _zval_insert_copies."""
    _end, root = _zitems(d)
    arr = root[3].get(array_key)
    if not arr or arr[0] != "array" or not (0 <= index < len(arr[3])):
        raise ValueError(f"no {array_key}[{index}]")
    el = arr[3][index]
    if el[0] not in ("dict", "array"):
        raise ValueError("unexpected Zval element")
    start, end = el[-1], el[2]
    out = bytearray(d[:start] + d[end:])
    a_off, k = arr[1], end - start
    struct.pack_into("<I", out, a_off + 8, struct.unpack_from("<I", out, a_off + 8)[0] - k)
    struct.pack_into("<I", out, a_off + 16, struct.unpack_from("<I", out, a_off + 16)[0] - 1)
    struct.pack_into("<I", out, 8, struct.unpack_from("<I", out, 8)[0] - k)
    return bytes(out)


def remove_plots(gb: bytes, drop_fens: Sequence[int]) -> bytes:
    """Remove every plot drawing one of drop_fens (and those data sets from the
    graph's lists): its records, its colour-table entries, its entry in the plot
    list and in the data-set lists, and the object count. The inverse of
    _copy_plots."""
    drop_fens = set(int(f) for f in drop_fens)
    while True:
        R = records(gb)
        pls = plots(gb, R)
        pl = next((p for p in pls if p["fen"] in drop_fens), None)
        if pl is None:
            break
        z = _zval(gb, R)
        idx = _db_index(R, pl["idb"])
        pidx = [p["i8028"] for p in pls].index(pl["i8028"])
        g0, g1 = R[pl["first"]][0], R[pl["last"]][0] + 2
        out = bytearray(gb[:g0] + gb[g1:])
        for off, tag, n in R:
            if tag == TAG_COUNT and n >= 8 and off < g0:
                struct.pack_into("<I", out, off + 6 + 4,
                                 struct.unpack_from("<I", out, off + 6 + 4)[0] - 1)
                break
        out = bytes(out)
        for off, tag, n in records(out):          # the plot list
            if tag == TAG_PLOTLIST and n >= 4:
                cnt = struct.unpack_from("<I", out, off + 6)[0]
                ids = list(struct.unpack_from(f"<{cnt}I", out, off + 10))
                if pl["id"] in ids:
                    ids.remove(pl["id"])
                    body = struct.pack(f"<I{len(ids)}I", len(ids), *ids)
                    out = out[:off] + struct.pack("<HI", tag, len(body)) + body + out[off + 6 + n:]
                break
        if not any(p["fen"] == pl["fen"] for p in pls if p is not pl):
            out = _remove_dataset_entries(out, pl["fen"])
        if z is not None:
            zd = _zval_remove(z[1], "SEDObject_Array", idx)
            try:
                zd = _zval_remove(zd, "PlotWithPoints_Array", pidx)
            except ValueError:
                pass
            for rec in records(out):
                if rec[1] == TAG_ZVAL:
                    out = _zval_replace(out, rec, zd)
                    break
        gb = out
    return gb


def _remove_dataset_entries(b: bytes, fen: int) -> bytes:
    """Drop one data set from the lists 0x0016 / 0x00a0 / 0x0091 (see
    _add_dataset_entries)."""
    for tag in (0x0016, 0x00A0, 0x0091):
        for off, t, n in records(b):
            if t != tag:
                continue
            p = b[off + 6:off + 6 + n]
            if tag == 0x0016:
                cnt = struct.unpack_from("<H", p, 0)[0]
                ents = [p[2 + 12 * i:14 + 12 * i] for i in range(cnt)]
                keep = [e for e in ents if struct.unpack_from("<I", e, 0)[0] != fen]
                p = struct.pack("<H", len(keep)) + b"".join(keep)
            elif tag == 0x00A0:
                cnt = struct.unpack_from("<I", p, 4)[0]
                ents = [p[8 + 32 * i:40 + 32 * i] for i in range(cnt)]
                keep = [e for e in ents if struct.unpack_from("<I", e, 0)[0] != fen]
                p = p[:4] + struct.pack("<I", len(keep)) + b"".join(keep)
            else:
                cnt = struct.unpack_from("<I", p, 0)[0]
                if cnt:
                    p = struct.pack("<I", cnt - 1) + p[8:]
            b = b[:off] + struct.pack("<HI", t, len(p)) + p + b[off + 6 + n:]
            break
    return b


# ------------------------------------------------- more graphs in one file (V2.7)
TAG_GRAPH_FEN, TAG_GRAPH_NAME, TAG_GRAPH_KEY = 0x8012, 0x0009, 0x2015


def repoint(gb: bytes, old_fen: int, new_fen: int) -> bytes:
    """A copy of a graph block that draws data set new_fen where it drew old_fen:
    the plot (8028 bytes 4-5, 009c @313) and the graph's data-set lists (0x0016
    @2 + 12 k, 0x00a0 @8 + 32 k). V2.7, checked in Prism 11: a graph copied this
    way draws the other table."""
    b = bytearray(gb)
    R = records(gb)
    for p in plots(gb, R):
        if p["fen"] == old_fen:
            struct.pack_into("<H", b, R[p["i8028"]][0] + 6 + 4, new_fen)
            struct.pack_into("<I", b, R[p["i9c"]][0] + 6 + 313, new_fen)
    for off, tag, n in R:
        if tag == 0x0030 and n >= 4 and struct.unpack_from("<I", b, off + 6)[0] == old_fen:
            struct.pack_into("<I", b, off + 6, new_fen)        # a legend entry's data set
        elif tag == 0x0016:
            cnt = struct.unpack_from("<H", b, off + 6)[0]
            for k in range(cnt):
                if struct.unpack_from("<I", b, off + 8 + 12 * k)[0] == old_fen:
                    struct.pack_into("<I", b, off + 8 + 12 * k, new_fen)
        elif tag == 0x00A0:
            cnt = struct.unpack_from("<I", b, off + 10)[0]
            for k in range(cnt):
                if struct.unpack_from("<I", b, off + 14 + 32 * k)[0] == old_fen:
                    struct.pack_into("<I", b, off + 14 + 32 * k, new_fen)
    return bytes(b)


# Where a graph's object ids are used (record tag -> [(offset, width)]). Worked
# out by letting GraphPad Prism 11 duplicate a PeterPiper graph (script command
# DuplicateFamily) and comparing the copy with the original: Prism gives every
# object of the copy a new id that no other graph of the document uses - the
# objects (00db @158), plots (8028 @0, the plot list 0015, legend entries 002f
# as two uint16), axis segments (8025 @0, 002a @0, axis 0017 @54 / 56 / 58),
# axis titles (0017 @48), the graph title (0013 @32) and texts (802b / 902b @0).
_ID_REFS = {0x00DB: [(158, 4)], 0x8028: [(0, 4)], 0x8025: [(0, 2)], 0x002A: [(0, 2)],
            0x0017: [(48, 2), (54, 2), (56, 2), (58, 2)], 0x0013: [(32, 2)],
            0x802B: [(0, 2)], 0x902B: [(0, 2)], 0x002F: [(0, 2), (2, 2)]}


def object_ids(gb: bytes) -> List[int]:
    """Every object and axis segment id of a graph block (its 00db and 8025
    records)."""
    out = []
    for off, tag, n in records(gb):
        if tag == TAG_DB and n >= 162:
            v = struct.unpack_from("<I", gb, off + 6 + 158)[0]
        elif tag == TAG_SEGMENT and n >= 2:
            v = struct.unpack_from("<H", gb, off + 6)[0]
        else:
            continue
        if v != 0xFFFFFFFF and v not in out:
            out.append(v)
    return out


def clone_graph(gb: bytes, graph_fen: int, sheet_fen: int, first_id: int) -> Tuple[bytes, int]:
    """A copy of a graph block that is a graph of its own (V2.7), as Prism's own
    DuplicateFamily makes it: new object / segment ids from first_id on (see
    _ID_REFS), its own fenID (0x8012, each plot's 009c @113; 0x0013 @8 and 0x8018
    @0 move with it), and the fenID of the data table it belongs to (0x0014 @4).
    The data sets it draws are set with repoint(). Returns (block, next free id)."""
    b = bytearray(gb)
    R = records(gb)
    old = object_ids(gb)
    new = {v: first_id + k for k, v in enumerate(old)}
    old_fen = next((struct.unpack_from("<H", gb, off + 6)[0] for off, tag, n in R
                    if tag == TAG_GRAPH_FEN and n == 2), graph_fen)
    for off, tag, n in R:
        if tag == TAG_GRAPH_FEN and n == 2:
            struct.pack_into("<H", b, off + 6, graph_fen)
        elif tag in (0x0013, TAG_COUNT) and n >= 10:
            pos = 8 if tag == 0x0013 else 0
            v = struct.unpack_from("<H", b, off + 6 + pos)[0]
            struct.pack_into("<H", b, off + 6 + pos, (v + graph_fen - old_fen) & 0xFFFF)
        elif tag == 0x0014 and n >= 8:
            struct.pack_into("<I", b, off + 6 + 4, sheet_fen)
        elif tag == TAG_PSTYLE and n >= 317:
            struct.pack_into("<H", b, off + 6 + 113, graph_fen)
    return _renumber(bytes(b), new, first_id + len(old))


def _renumber(gb: bytes, new: Dict[int, int], nxt: int) -> Tuple[bytes, int]:
    """Replace object ids old -> new wherever _ID_REFS / the plot list use them."""
    if nxt > 0xFFFF:
        raise ValueError("too many graph objects")
    b = bytearray(gb)
    for off, tag, n in records(gb):
        for pos, w in _ID_REFS.get(tag, []):
            if pos + w <= n:
                f = "<I" if w == 4 else "<H"
                v = struct.unpack_from(f, b, off + 6 + pos)[0]
                if v in new:
                    struct.pack_into(f, b, off + 6 + pos, new[v])
        if tag == TAG_PLOTLIST and n >= 4:
            cnt = struct.unpack_from("<I", b, off + 6)[0]
            if n == 4 + 4 * cnt:
                for k in range(cnt):
                    v = struct.unpack_from("<I", b, off + 10 + 4 * k)[0]
                    if v in new:
                        struct.pack_into("<I", b, off + 10 + 4 * k, new[v])
    return bytes(b), nxt


def set_identity(gb: bytes, fen: int, name: str, key: str) -> bytes:
    """The graph's own fenID (record 0x8012, = its sheet.json fenID), its name
    (0x0009, NUL-terminated) and its key text (0x2015, NUL-terminated), so a
    copy of a graph block is a graph of its own (V2.7)."""
    out, pos = bytearray(), 0
    for off, tag, n in records(gb):
        if tag == TAG_GRAPH_FEN and n == 2:
            body = struct.pack("<H", fen)
        elif tag == TAG_GRAPH_NAME:
            body = str(name).encode("cp1252", "replace")[:250] + b"\x00"
        elif tag == TAG_GRAPH_KEY:
            body = str(key).encode("ascii") + b"\x00"
        else:
            continue
        out += gb[pos:off] + struct.pack("<HI", tag, len(body)) + body
        pos = off + 6 + n
    out += gb[pos:]
    return bytes(out)


def set_legend(gb: bytes, show: bool, fens: Optional[Sequence[int]] = None) -> bytes:
    """List (show=True) or hide the data sets of the plots drawing `fens` (all
    plots when None) in the graph's legend (8028 byte 113 bit 0x08)."""
    b = bytearray(gb)
    R = records(gb)
    for p in plots(gb, R):
        if fens is not None and p["fen"] not in set(fens):
            continue
        off = R[p["i8028"]][0] + 6 + LEGEND_BYTE
        b[off] = (b[off] & ~LEGEND_HIDE) if show else (b[off] | LEGEND_HIDE)
    return bytes(b)


def style_series(gb: bytes, fen: int, colour: Optional[str] = None,
                 symbol: Optional[str] = None) -> bytes:
    """Colour (line, error bars, symbols) and symbol of the plot drawing `fen`
    (symbol: a key of SYMBOL_CODES)."""
    b = bytearray(gb)
    R = records(gb)
    z = _zval(gb, R)
    zd = bytearray(z[1]) if z else None
    zmaps = _plot_maps(bytes(zd)) if zd is not None else None
    for p in plots(gb, R):
        if p["fen"] != fen:
            continue
        if colour:
            _style_plot(b, R, p, zd, zmaps, colour=colour)
        if symbol in SYMBOL_CODES:
            _put(b, R[p["i9c"]], 109, bytes([SYMBOL_CODES[symbol]]))
    out = bytes(b)
    if z and zd is not None:
        out = _zval_replace(out, z[0], bytes(zd))
    return out
