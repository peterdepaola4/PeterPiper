"""
Run every developer test, one after another, and say which passed, failed or
were skipped (lab data only / no Prism). Each test gets its own settings folder
and writes only to _out/ in the repository.

    python dev_tests/run_tests.py            all tests
    python dev_tests/run_tests.py v29 graph  only these (names as listed below)

Tests that drive GraphPad Prism need Prism 11; tests that need the lab's own
movies are skipped without them (labdata.py). Logs: _out/tests/<name>.txt
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "tests"
# (name, script, extra arguments) - in the order they are run
TESTS = [
    ("peterpiper", "test_peterpiper.py", []),
    ("v30", "test_v30.py", []),
    ("v29", "test_v29.py", []),
    ("v28", "test_v28.py", []),
    ("v27", "test_v27.py", []),
    ("v26_kinetics", "test_v26_kinetics.py", []),
    ("compare_groups", "test_compare_groups.py", []),
    ("v25_track", "test_v25_track.py", []),
    ("gui_v25", "test_gui_v25.py", []),
    ("provenance", "test_provenance.py", []),
    ("rules_unit", "test_rules_unit.py", []),
    ("graph", "test_graph.py", [str(OUT / "graph")]),
    ("compare", "test_compare.py", []),
    ("rules_track", "test_rules_track.py", []),
    ("gui_rules", "test_gui_rules.py", []),
    ("history", "test_history.py", []),
    ("gui_history", "test_gui_history.py", []),
    ("gui_graph", "test_gui_graph.py", []),
    ("prism_live", "test_prism_live.py", []),
    ("prism_style", "test_prism_style.py", []),
    ("pack_bat", "test_pack_bat.py", []),
]


def main(argv) -> int:
    want = set(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg",
               PYTHONIOENCODING="utf-8")
    rows = []
    for name, script, extra in TESTS:
        if want and name not in want:
            continue
        log = OUT / f"{name}.txt"
        env["PETERPIPER_HOME"] = str(OUT / f"home_{name}")
        t0 = time.time()
        with open(log, "w", encoding="utf-8") as fh:
            code = subprocess.call([sys.executable, str(HERE / script)] + extra, env=env,
                                   stdout=fh, stderr=subprocess.STDOUT, cwd=str(REPO))
        text = log.read_text(encoding="utf-8", errors="replace")
        if "SKIPPED" in text and code == 0:
            state = "SKIPPED"
        else:
            state = "PASS" if code == 0 else "FAIL"
        tally = re.findall(r"(\d+)\s*(?:/|of)\s*(\d+)\s*(?:checks )?passed", text)
        rows.append((name, state, f"{tally[-1][0]}/{tally[-1][1]}" if tally else "",
                     time.time() - t0))
        print(f"{state:8s} {name:16s} {rows[-1][2]:>9s}  {rows[-1][3]:6.0f} s", flush=True)
    bad = [r for r in rows if r[1] == "FAIL"]
    print(f"\n{len(rows) - len(bad)} of {len(rows)} passed or skipped; logs in {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
