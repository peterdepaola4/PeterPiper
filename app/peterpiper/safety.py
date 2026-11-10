"""Local output safeguards; no network access or analysis calculations."""
from __future__ import annotations

import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

# --------------------------------------------------------------------------
#  Long paths (Windows). Without the extended-length form a path longer than
#  260 characters (folders: 248) cannot be opened or created, and results go
#  deep: <your folder>/OUTPUT_<file>/Export_<date>/<Compartment>/Prism graphs/
#  <file>_<compartment>_<quantity>.prism. Every file the app writes or reads
#  back goes through long_path() (the \\?\ form); what the user is SHOWN uses
#  plain_path() / error_text() (the normal form).
# --------------------------------------------------------------------------
_LONG = "\\\\?\\"                 # \\?\C:\...
_LONG_UNC = "\\\\?\\UNC\\"        # \\?\UNC\server\share\...


def long_path(path) -> str:
    """The path in Windows' extended-length form (\\\\?\\C:\\... or
    \\\\?\\UNC\\server\\share\\...), absolute and normalised ('/', '.', '..'),
    so it works past 260 characters. Unchanged on other systems, for '' and
    for paths already in that form."""
    s = os.fspath(path) if not isinstance(path, str) else path
    if os.name != "nt" or not s or s.startswith(_LONG) or s.startswith("\\\\.\\"):
        return s
    s = os.path.abspath(s)
    if s.startswith("\\\\"):                           # network share
        return _LONG_UNC + s[2:]
    return _LONG + s


def plain_path(path) -> str:
    """The normal form of a path (for messages, lists and the run index)."""
    s = os.fspath(path) if not isinstance(path, str) else path
    if s.startswith(_LONG_UNC):
        return "\\\\" + s[len(_LONG_UNC):]
    if s.startswith(_LONG):
        return s[len(_LONG):]
    return s


def error_text(exc: BaseException) -> str:
    """A file error in words with the normal path form (str(OSError) shows the
    path with doubled backslashes and the \\\\?\\ prefix)."""
    if isinstance(exc, OSError) and exc.filename:
        what = exc.strerror or type(exc).__name__
        text = f"{what}: {plain_path(str(exc.filename))}"
        if exc.filename2:
            text += f" -> {plain_path(str(exc.filename2))}"
        return text
    text = str(exc) or type(exc).__name__
    return text.replace(_LONG_UNC, "\\\\").replace(_LONG, "")


def make_dirs(path) -> None:
    """Create a folder (and its parents) - long paths included."""
    os.makedirs(long_path(path), exist_ok=True)


def exists(path) -> bool:
    return bool(path) and os.path.exists(long_path(path))


def is_dir(path) -> bool:
    return bool(path) and os.path.isdir(long_path(path))


def validate_filename_part(value: str, label: str = "Name") -> str:
    """Reject Windows/path syntax rather than silently changing user labels."""
    if (not value or value in (".", "..") or value.endswith((" ", "."))
            or any(ord(ch) < 32 or ch in '<>:"/\\|?*' for ch in value)):
        raise ValueError(
            f"{label} must be a plain name without path separators, control "
            'characters, <>:"|?*, or a trailing space/period.')
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10))
    if value.split(".", 1)[0].upper() in reserved:
        raise ValueError(f"{label} is a reserved Windows filename.")
    return value


@contextmanager
def new_output_file(path: Path):
    """Exclusively create an output, adding _2, _3, ... instead of overwriting.

    The exclusive open also refuses an existing symlink at the output filename.
    A failed write can leave a partial new file, but never replaces an old file.
    Works past Windows' 260-character limit (the path yielded is in the form
    given: show it with plain_path).
    """
    path = Path(path)
    validate_filename_part(path.name, "Output filename")
    make_dirs(path.parent)
    number = 1
    while True:
        candidate = (path if number == 1 else
                     path.with_name(f"{path.stem}_{number}{path.suffix}"))
        try:
            stream = open(long_path(candidate), "xb")
        except FileExistsError:
            number += 1
            continue
        with stream:
            yield candidate, stream
        return


@contextmanager
def replace_own_file(path: Path):
    """v2.3: write one of the app's OWN files (the current session file, the
    run index) so that it is either fully the old or fully the new version.

    The bytes go to a temporary file in the same folder, are flushed to disk,
    and then take the old file's place in one step (os.replace). A crash, a
    full disk or an error while writing leaves the old file untouched (the
    temporary file is removed). Results the user keeps (workbooks, PNGs, Prism,
    exported ROI files) never use this - they use new_output_file above.
    """
    path = Path(path)
    validate_filename_part(path.name, "Output filename")
    make_dirs(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.stem[:24]}.", suffix=".tmp",
                               dir=long_path(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        _replace(tmp, long_path(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _replace(src: str, dst: Path, tries: int = 8) -> None:
    """os.replace, retried briefly: on Windows a virus scanner or the file
    indexer can hold the old file open for a moment."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))
