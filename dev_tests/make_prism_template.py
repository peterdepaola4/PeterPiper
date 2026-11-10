"""
Developer tool (not shipped): build PeterPiper's Prism look template from a graph
the user styled in GraphPad Prism.

    python dev_tests/make_prism_template.py <styled .prism> [--out app/peterpiper/templates]

The source must be a PeterPiper .prism (V2.4 'Compare runs' or a single-run graph)
changed and saved in Prism, so its graph keeps prismstyle.TEMPLATE_GRAPH_UID.
Written:

  templates/PeterPiper_timecourse.prism   the source's graph block with ONLY the plot
        of the graph table's first data set (the others removed with
        prismstyle.remove_plots), texts set to placeholders, axis ranges
        automatic; ONE data table (3 placeholder rows, one replicate), no other
        sheets, no floating notes, empty project notes. Nothing of the source's
        data, titles or file names is kept.
  templates/PeterPiper_look.json          the look of each data set of the source
        graph in table order (symbol, line / error / symbol colours, line and
        error-bar widths, symbol size, error-bar style byte), the fonts and the
        source's error type - used for the 2nd, 3rd ... data set of compare /
        average graphs and as GraphStyle's default look.

The source path is never written anywhere (only the look is kept).
"""
from __future__ import annotations

import json
import struct
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "app"))

from peterpiper import prismstyle as P  # noqa: E402

SYM = {v: k for k, v in P.SYMBOL_CODES.items()}


def plot_look(gb, R, zd, zmaps, pl) -> dict:
    p28, p9 = P._payload(gb, R[pl["i8028"]]), P._payload(gb, R[pl["i9c"]])
    return {
        "symbol": SYM.get(p9[109], "circle"),
        "colour": P._plot_rgb(zd, zmaps, R, pl, "connectlinecolor"),
        "error_colour": P._plot_rgb(zd, zmaps, R, pl, "errorcolor"),
        "symbol_colour": P._plot_rgb(zd, zmaps, R, pl, "symbolcolor"),
        "symbol_border": P._plot_rgb(zd, zmaps, R, pl, "symbolBorderColor"),
        "line_pt": round(struct.unpack_from("<f", p9, 261)[0] * P.LINE_UNIT_PT, 4),
        "error_line_pt": round(struct.unpack_from("<f", p9, 269)[0] * P.LINE_UNIT_PT, 4),
        "symbol_pt": round(struct.unpack_from("<f", p9, 289)[0] * P.SYMBOL_UNIT_PT, 4),
        "error_style_byte": int(p9[71]),
        "error": {1: "SD", 2: "SEM", 3: "95% CI"}.get(p28[12], "?"),
    }


def _zval_remove_nested(d: bytes, node_path, index: int) -> bytes:
    """Remove element `index` of the Zval array reached by node_path (a list of
    dict keys / array indices from the root), fixing the length of that array
    and of every enclosing value, and the array's element count."""
    _e, root = P._zitems(d)
    chain = [root]
    node = root
    for step in node_path:
        node = node[3][step]
        chain.append(node)
    arr = chain[-1]
    assert arr[0] == "array"
    el = arr[3][index]
    start, end = el[-1], el[2]
    k = end - start
    out = bytearray(d[:start] + d[end:])
    for n in chain:                       # every enclosing Mval: content length - k
        off = n[1] if n[0] in ("dict", "array") else None
        if off is not None and off < start:
            struct.pack_into("<I", out, off + 8, struct.unpack_from("<I", out, off + 8)[0] - k)
    struct.pack_into("<I", out, arr[1] + 16, struct.unpack_from("<I", out, arr[1] + 16)[0] - 1)
    return bytes(out)


def drop_extra_ticks(gb: bytes) -> bytes:
    """The source's X axis has two 'additional ticks': one at X = 0 drawn as a
    dotted line (kept: the baseline marker of the look) and a labelled one at the
    first time of that run (-5 min - run-specific; removed: its 0x0026 + 0x00fc
    records, its label object 0x00a2 + 0x00a8 x2 + 0x00a9 x2, and its entry in
    the Zval IPGAxSeg::addticks array)."""
    R = P.records(gb)
    ticks = [k for k, (o, t, n) in enumerate(R) if t == 0x0026 and n >= 9]
    labels = [k for k, (o, t, n) in enumerate(R) if t == 0x00A2 and n >= 12]
    if len(ticks) != 2 or len(labels) != 2:
        print("additional ticks: layout not as expected - kept")
        return gb
    vals = [struct.unpack_from("<d", P._payload(gb, R[k]), 0)[0] for k in ticks]
    lvals = [struct.unpack_from("<d", P._payload(gb, R[k]), 2)[0] for k in labels]
    if vals[1] != 0.0 or lvals[1] != 0.0 or vals[0] == 0.0 or lvals[0] != vals[0]:
        print("additional ticks: values not as expected - kept", vals, lvals)
        return gb
    assert R[ticks[0] + 1][1] == 0x00FC
    assert [R[labels[0] + j][1] for j in range(1, 5)] == [0x00A8, 0x00A8, 0x00A9, 0x00A9]
    cut = [(R[ticks[0]][0], R[ticks[0] + 2][0]), (R[labels[0]][0], R[labels[0] + 5][0])]
    for a, b in sorted(cut, reverse=True):
        gb = gb[:a] + gb[b:]
    R = P.records(gb)
    z = P._zval(gb, R)
    _e, root = P._zitems(z[1])
    # IPGAxis_Array[0] (X axis) -> [0] (its first segment) -> IPGAxSeg::addticks
    path = ["IPGAxis_Array", 0, 0, "IPGAxSeg::addticks"]
    node = root
    for step in path:
        node = node[3][step]
    assert node[0] == "array" and len(node[3]) == 2, node[:2]
    zd = _zval_remove_nested(z[1], path, 0)
    gb = P._zval_replace(gb, z[0], zd)
    print("removed the additional X tick at", vals[0])
    return gb


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    src = Path(argv[0])
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else \
        REPO / "app" / "peterpiper" / "templates"
    with zipfile.ZipFile(src) as z:
        raw = {i.filename: z.read(i.filename) for i in z.infolist() if not i.is_dir()}
        order = [i.filename for i in z.infolist() if not i.is_dir()]
    doc = json.loads(raw["document.json"])
    gid = doc["sheets"]["graphs"][0]
    if gid != P.TEMPLATE_GRAPH_UID:
        print("The source graph was not made from PeterPiper's template.")
        return 1
    gsid = doc["sheets"]["data"][0]
    sheet = json.loads(raw[f"data/sheets/{gsid}/sheet.json"])
    tab = sheet["table"]
    fens = [int(json.loads(raw[f"data/sets/{u}.json"])["fenID"]) for u in tab["dataSets"]]
    gb = raw[f"graphs/{gid}/data.bin"]
    R = P.records(gb)
    z = P._zval(gb, R)
    zd = z[1]
    zmaps = P._plot_maps(zd)
    pls = P.plots(gb, R)
    by_fen = {p["fen"]: p for p in pls}
    series = [plot_look(gb, R, zd, zmaps, by_fen[f]) for f in fens if f in by_fen]
    font = P._read_font(gb, R)
    look = {"about": "PeterPiper Prism look (V2.5): taken from a graph styled in GraphPad Prism 11. "
                     "series = the look of each data set in turn.",
            "font_pt": font, "series": series,
            "legend_shown": not all(P._payload(gb, R[p["i8028"]])[P.LEGEND_BYTE] & P.LEGEND_HIDE
                                    for p in pls)}

    # ---- graph block: one plot, placeholder texts, automatic axes
    keep = fens[0]
    gb = P.remove_plots(gb, [f for f in fens[1:]])
    for role, txt in (("title", "Title"), ("x", "X"), ("y", "Y"), ("y2", "")):
        gb = P.set_text(gb, role, txt)
    b = bytearray(gb)
    R = P.records(gb)
    P._set_axis(b, R, 0, None, None, 0.0, 1.0)
    P._set_axis(b, R, 1, None, None, 0.0, 1.0)
    gb = bytes(b)
    # record 0x0009 holds a copy of the graph's name: neutral
    for off, tag, n in P.records(gb):
        if (tag & ~0x1000) == 0x0009:
            body = b"PeterPiper graph\x00"
            gb = gb[:off] + struct.pack("<HI", tag, len(body)) + body + gb[off + 6 + n:]
            break
    gb = drop_extra_ticks(gb)
    left = [p["fen"] for p in P.plots(gb)]
    assert left == [keep], left

    # ---- data: the graph table only, one data set, placeholder rows
    files = {}
    proto = tab["dataSets"][0]
    for u in tab["dataSets"][1:]:
        raw.pop(f"data/sets/{u}.json", None)
    d = json.loads(raw[f"data/sets/{proto}.json"])
    d["title"] = "Data"
    r = dict(d["replicate ranges"][0]["replicate"])
    r.update(firstRow=0, lastRow=2)
    d["replicate ranges"] = [{"range": "0", "replicate": r}]
    files[f"data/sets/{proto}.json"] = d
    xd = json.loads(raw[f"data/sets/{tab['xDataSet']}.json"])
    xd["title"] = "X"
    xd["replicates"][0].update(firstRow=0, lastRow=2)
    files[f"data/sets/{tab['xDataSet']}.json"] = xd
    tab["dataSets"] = [proto]
    tab["replicatesCount"] = 1
    sheet["title"] = "Data"
    files[f"data/sheets/{gsid}/sheet.json"] = sheet
    tid = tab["uid"]
    files[f"data/tables/{tid}/data.csv"] = b"0,1\n1,1\n2,1\n"
    files[f"data/tables/{tid}/content.json"] = json.dumps(
        {"$id": "sheets/data_sheet/data_table/data_table_storage.schema.json",
         "numberOfColumns": 2, "numberOfRows": 3, "version": 1}, indent=4).encode()
    for k in list(raw):
        if k.startswith("data/sets/") and k[10:-5] not in (proto, tab["xDataSet"]):
            raw.pop(k)                    # the other sheets' data sets (source data)
        elif k.startswith("data/tables/") and k.split("/")[2] != tid:
            raw.pop(k)
        elif k.startswith("data/sheets/") and k.split("/")[2] != gsid:
            raw.pop(k)
        elif k.startswith("graphs/") and "floating_notes" in k:
            raw.pop(k)
        elif k == f"data/tables/{tid}/data.dt":
            raw.pop(k)
    gs = json.loads(raw[f"graphs/{gid}/sheet.json"])
    gs.pop("floatingNotes", None)
    gs["title"] = "PeterPiper graph"
    # Prism 11 keeps a list of the data sets the graph was made from; the old
    # template had none - left out, so plots of other tables (each cell) are drawn
    gs.pop("inputDataSets", None)
    files[f"graphs/{gid}/sheet.json"] = gs
    files[f"graphs/{gid}/data.bin"] = gb
    for iid in doc["sheets"].get("info", []):
        key = f"info/{iid}/sheet.json"
        info = json.loads(raw[key])
        info["notesText"] = ""
        info.pop("experimentDate", None)
        for c in info.get("constants", []):
            if c.get("name") in ("Experiment Date", "Experiment ID", "Notebook reference",
                                 "Project", "Experimenter", "Protocol"):
                c["value"] = ""
        files[key] = info
    doc["sheets"]["data"] = [gsid]
    for who in ("createdBy", "modifiedBy"):
        if isinstance(doc.get(who), dict):
            doc[who]["user"] = ""
    doc["uiSettings"]["nextDataSheetNumber"] = 2
    doc["uiSettings"]["currentSheets"] = {"data": gsid, "graph": gid,
                                          **{"info": i for i in doc["sheets"].get("info", [])[:1]}}
    doc["sheetAttributesMap"] = {gsid: {"title": "Data"}, gid: {"title": "PeterPiper graph"},
                                 **{i: {"title": "Project info 1"}
                                    for i in doc["sheets"].get("info", [])}}
    files["document.json"] = doc
    out.mkdir(parents=True, exist_ok=True)
    dst = out / "PeterPiper_timecourse.prism"
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
        for k in order:
            if k in files or k in raw:
                v = files.get(k, raw.get(k))
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, indent="\t").encode()
                zo.writestr(k, v)
    (out / "PeterPiper_look.json").write_text(json.dumps(look, indent=2), encoding="utf-8")
    print("wrote", dst, "and PeterPiper_look.json:", json.dumps(look, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
