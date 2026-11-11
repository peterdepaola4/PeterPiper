"""
Developer tests: old code from PD4nav's history (PeterPiper's earlier name).

Some tests compare today's results with PD4nav V2.2's code, taken from git. The
PeterPiper repository was started fresh at 1.0, so that history is in the PD4nav
repository, where the code package was app/roinav. Set PD4NAV_HISTORY_REPO to
that repository (default: the lab computer's copy, from dev_tests/lab_paths.json).
Every function raises if the history cannot be read; the tests then say so.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import os
import subprocess
from pathlib import Path

HISTORY_REPO = Path(os.environ.get("PD4NAV_HISTORY_REPO") or labdata.T("t01"))
OLD_PACKAGE = "app/roinav"


def available() -> bool:
    """PD4nav's history is on this computer (a git repository at HISTORY_REPO)."""
    return (HISTORY_REPO / ".git").exists()


def show(commit: str, rel: str) -> bytes:
    """The file <package>/<rel> as it was at `commit` (PD4nav's app/roinav)."""
    return subprocess.run(["git", "-C", str(HISTORY_REPO), "show", f"{commit}:{OLD_PACKAGE}/{rel}"],
                          capture_output=True, check=True).stdout


def package_files(commit: str) -> dict:
    """{relative path: bytes} of the whole package at `commit`."""
    import io
    import tarfile
    data = subprocess.run(["git", "-C", str(HISTORY_REPO), "archive", "--format=tar", commit,
                           OLD_PACKAGE], capture_output=True, check=True).stdout
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            if m.isfile() and m.name.startswith(OLD_PACKAGE + "/"):
                out[m.name[len(OLD_PACKAGE) + 1:]] = tf.extractfile(m).read()
    return out
