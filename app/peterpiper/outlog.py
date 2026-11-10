"""
V2.8: the log of everything PeterPiper saved - so you can always find your files.

Every save (an export, a Compare / average save, a graph, a batch analysis) adds
one line to 'saved_files_log.jsonl' next to PeterPiper's settings: when, what, the
name you gave it, the folder and every file written. 'Saved files...' (start
window, File menu, Compare window) lists them newest first; double-click opens
the file or its folder. The log only lists paths - deleting a line or the log
never touches your files.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import List, Sequence

LOG_NAME = "saved_files_log.jsonl"


def log_path() -> Path:
    from .config import _settings_file
    return _settings_file().parent / LOG_NAME


def record(kind: str, name: str, files: Sequence[str], detail: str = "") -> None:
    """Add one save to the log (best effort - never raises into the caller)."""
    files = [str(f) for f in files if f]
    if not files:
        return
    try:
        import os
        try:
            folder = os.path.commonpath([str(Path(f).parent) for f in files])
        except ValueError:                          # files on different drives
            folder = str(Path(files[0]).parent)
        entry = dict(when=dt.datetime.now().isoformat(timespec="seconds"), kind=str(kind),
                     name=str(name), folder=folder, files=files, detail=str(detail))
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:                                              # noqa: BLE001
        pass


def entries() -> List[dict]:
    """Every logged save, newest first (unreadable lines are skipped)."""
    out = []
    try:
        for line in log_path().read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                if isinstance(d, dict) and d.get("files"):
                    out.append(d)
            except ValueError:
                continue
    except OSError:
        return []
    return sorted(out, key=lambda d: str(d.get("when", "")), reverse=True)
