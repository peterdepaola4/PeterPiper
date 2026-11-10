"""
Tests that need the Schmitt lab's own .nd2 movies (not shipped: unpublished data)
call need(...) first. Without the files the test says 'SKIPPED - lab data only'
and ends with exit code 0, so it is not counted as a failure; everyone else runs
the tests that use the shipped synthetic movie (synthmovie.py).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The lab's own file names and folders are not in this repository (they name
# unpublished experiments). Tests ask for them by key - labdata.T("t07") - and
# get them from dev_tests/lab_paths.json (or the file in $PETERPIPER_LAB_PATHS),
# which stays on the lab's computers and is never uploaded (.gitignore). Without
# it every key gives a path that does not exist, so those tests are skipped.
LAB_PATHS = Path(os.environ.get("PETERPIPER_LAB_PATHS")
                 or Path(__file__).resolve().parent / "lab_paths.json")
_texts = None


def T(key: str) -> str:
    """The lab's own file name / folder for `key` ('lab-data-not-here/<key>' without
    the local list)."""
    global _texts
    if _texts is None:
        try:
            _texts = json.loads(LAB_PATHS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _texts = {}
    return str(_texts.get(key) or f"lab-data-not-here/{key}")

SKIP_CODE = 0
SKIP_WORD = "SKIPPED - lab data only"


def missing(*paths) -> list:
    return [str(p) for p in paths if p and not Path(str(p)).exists()]


def need(*paths, what: str = "this test") -> None:
    """End the test as skipped (not failed) when any of these files is absent."""
    gone = missing(*paths)
    if gone:
        print(f"{SKIP_WORD}: {what} needs the lab's own movies, not found here:")
        for g in gone:
            print(f"    {g}")
        sys.exit(SKIP_CODE)
