"""
PeterPiper 1.2 - what the launcher shows while it installs (standard library only).

The launcher (PeterPiperV1.2.bat) runs this with the freshly made private Python,
BEFORE any package is installed, so it uses nothing but Python's own library.

    python install_progress.py install <requirements.txt> [pip options ...]
        runs  python -m pip install [pip options] -r <requirements.txt>  and shows
        pip's own output as it comes. Whenever pip prints nothing for a few
        seconds (PETERPIPER_HEARTBEAT_S, default 5), a line says it is still
        working, what it is doing and roughly how long is left, e.g.
          still working - installing numpy, scipy, ... (1 min 40 s so far, about 2 min left)
        The exit code is pip's own, unchanged.

    python install_progress.py check <module> [<module> ...]
        imports each module, one by one:  checking numpy ... OK  (1 of 14)
        then "all packages OK"; exit code 1 at the first one that fails (its
        error is shown).

    python install_progress.py run [--total N] -- <command ...>
        the same watching for any command (used by the developer tests).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from typing import List, Optional

QUIET_S = 5.0
TYPICAL_MB = 250.0                 # what the package lists download, about
NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def count_packages(req_path: str) -> Optional[int]:
    """How many packages a requirements file pins exactly (name==version), or
    None when it uses ranges (pip then picks the needed extras itself)."""
    try:
        with open(req_path, encoding="utf-8", errors="replace") as fh:
            lines = [ln.split("#", 1)[0].strip() for ln in fh]
    except OSError:
        return None
    lines = [ln for ln in lines if ln and not ln.startswith("-")]
    if not lines or not all("==" in ln for ln in lines):
        return None
    return len(lines)


def nice_time(s: float) -> str:
    s = int(round(max(0.0, s)))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    return f"{m} min {s} s" if s else f"{m} min"


def _left_text(s: float) -> str:
    if s <= 20:
        return "nearly done"
    if s < 60:
        return "less than a minute left"
    mins = int(s // 60 + (1 if s % 60 >= 30 else 0))
    return f"about {mins} min left"


class Watch:
    """Follows what pip prints and words a 'still working' line from it."""

    def __init__(self, total: Optional[int] = None, now=time.monotonic) -> None:
        self.now = now
        self.t0 = now()
        self.total = total
        self.collected: List[str] = []   # packages pip looked up ("Collecting")
        self.wheels: List[str] = []      # package files downloaded
        self.current = ""                 # the package being looked up / downloaded
        self.size = ""                    # its download size, as pip said it
        self.phase = "start"              # start | collect | download | install | done
        self.installing: List[str] = []
        self.t_install = 0.0
        self.mb = 0.0                     # download sizes pip announced so far

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        low = line.lower()
        if low.startswith("collecting ") or low.startswith("requirement already satisfied:"):
            rest = line.split(None, 1)[1] if low.startswith("collecting ") else line.split(":", 1)[1]
            m = NAME_RE.match(rest)
            if m:
                name = m.group(1)
                if name.lower() not in (c.lower() for c in self.collected):
                    self.collected.append(name)
                self.current, self.size = name, ""
            self.phase = "collect"
        elif low.startswith("downloading "):
            fname = line.split()[1] if len(line.split()) > 1 else ""
            if fname.endswith(".metadata"):
                return                    # only the package's description (a few kB)
            m = re.search(r"\(([\d.]+)\s*([kMG]?B)\)", line)
            self.size = f"{m.group(1)} {m.group(2)}" if m else ""
            if m:
                unit = {"kB": 1e-3, "MB": 1.0, "GB": 1e3}.get(m.group(2), 1e-6)
                self.mb += float(m.group(1)) * unit
            base = fname.rsplit("/", 1)[-1]
            self.current = base.split("-", 1)[0] if "-" in base else (base or self.current)
            self.wheels.append(self.current)
            self.phase = "download"
        elif low.startswith("installing collected packages:"):
            names = [n.strip() for n in line.split(":", 1)[1].split(",") if n.strip()]
            self.installing = names
            self.phase = "install"
            self.t_install = self.now()
        elif low.startswith("successfully installed"):
            self.phase = "done"

    def _left(self) -> Optional[float]:
        """Rough seconds left (None when there is nothing to go on)."""
        t = self.now()
        n = self.total or len(self.collected) or 45
        if self.phase == "install":
            return (30.0 + 2.5 * (len(self.installing) or n)) - (t - self.t_install)
        if self.phase == "download":
            # how far: by megabytes (about TYPICAL_MB in all; the big packages come
            # first) or by package files, whichever is further
            frac = max(min(0.95, self.mb / TYPICAL_MB), min(1.0, len(self.wheels) / n))
            spent = t - self.t0
            if frac < 0.05 or spent < 15:
                return None
            return spent * (1.0 - frac) / frac + 30.0 + 2.5 * n
        return None

    def line(self) -> str:
        spent = nice_time(self.now() - self.t0)
        left = self._left()
        tail = f"{spent} so far" + (f", {_left_text(left)}" if left is not None and left > -60
                                    else (", taking longer than usual" if left is not None else ""))
        of = f" of {self.total}" if self.total else ""
        if self.phase == "install":
            names = self.installing
            shown = ", ".join(names[:4]) + (", ..." if len(names) > 4 else "")
            return (f"  still working - installing {shown} "
                    f"({len(names)} packages; {tail})")
        if self.phase == "download":
            what = f"downloading {self.current}" + (f" ({self.size})" if self.size else "")
            return f"  still working - {what} - {len(self.wheels)}{of} packages ({tail})"
        if self.phase == "collect":
            return (f"  still working - looking up {self.current} - {len(self.collected)}{of} "
                    f"packages ({tail})")
        if self.phase == "done":
            return f"  still working - finishing ({tail})"
        return f"  still working - asking pypi.org for the packages ({tail})"


def watch_command(cmd: List[str], total: Optional[int] = None,
                  quiet_s: Optional[float] = None, out=None) -> int:
    """Run cmd, pass its output through as it comes, print a 'still working'
    line whenever it is quiet for quiet_s seconds. Returns cmd's exit code."""
    if quiet_s is None:
        try:
            quiet_s = float(os.environ.get("PETERPIPER_HEARTBEAT_S", "") or QUIET_S)
        except ValueError:
            quiet_s = QUIET_S
    out = out or getattr(sys.stdout, "buffer", None)
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    try:
        cols = os.get_terminal_size(sys.__stdout__.fileno()).columns
        if cols > 40:
            env["COLUMNS"] = str(cols - 1)
    except (OSError, ValueError, AttributeError):
        pass
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env)
    w = Watch(total)
    lock = threading.Lock()
    state = {"last": time.monotonic(), "nl": True}

    def write(data: bytes) -> None:
        with lock:
            try:
                if out is not None:
                    out.write(data)
                    out.flush()
                else:
                    sys.stdout.write(data.decode("utf-8", "replace"))
                    sys.stdout.flush()
            except (OSError, ValueError):
                pass

    def reader() -> None:
        pending = b""
        stream = proc.stdout
        read = getattr(stream, "read1", stream.read)
        while True:
            try:
                chunk = read(4096)
            except (OSError, ValueError):
                break
            if not chunk:
                break
            write(chunk)
            state["last"] = time.monotonic()
            state["nl"] = chunk.endswith((b"\n", b"\r"))
            pending += chunk
            parts = re.split(rb"[\r\n]", pending)
            pending = parts.pop()
            for p in parts:
                w.feed(p.decode("utf-8", "replace"))
        if pending:
            w.feed(pending.decode("utf-8", "replace"))

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    try:
        while th.is_alive():
            th.join(0.25)
            if time.monotonic() - state["last"] >= quiet_s and th.is_alive():
                msg = w.line()
                write((b"" if state["nl"] else b"\n") + msg.encode("utf-8") + b"\n")
                state["last"] = time.monotonic()
                state["nl"] = True
        rc = proc.wait()
    except KeyboardInterrupt:
        try:
            proc.wait(timeout=10)
        except Exception:                                          # noqa: BLE001
            proc.kill()
        return proc.returncode if proc.returncode else 1
    return rc


def check_modules(names: List[str]) -> int:
    import importlib
    n = len(names)
    for i, name in enumerate(names, 1):
        print(f"  checking {name} ...", end="", flush=True)
        try:
            importlib.import_module(name)
        except Exception as exc:                                   # noqa: BLE001
            print(f" FAILED  ({i} of {n})", flush=True)
            print(f"    {type(exc).__name__}: {exc}", flush=True)
            return 1
        print(f" OK  ({i} of {n})", flush=True)
    print("   all packages OK", flush=True)
    return 0


def main(argv: List[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    mode, rest = argv[0], argv[1:]
    if mode == "install" and rest:
        req, opts = rest[0], rest[1:]
        return watch_command([sys.executable, "-m", "pip", "install", *opts, "-r", req],
                             total=count_packages(req))
    if mode == "check":
        return check_modules(rest)
    if mode == "run" and "--" in rest:
        cut = rest.index("--")
        head, cmd = rest[:cut], rest[cut + 1:]
        total = int(head[head.index("--total") + 1]) if "--total" in head else None
        return watch_command(cmd, total=total)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
