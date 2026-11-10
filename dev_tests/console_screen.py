"""
Developer test helper (not shipped): what a real console window shows.

    python dev_tests/console_screen.py OUT.txt

Run INSIDE the console to read (e.g. from a .bat started in a new console
window): writes the console's visible screen buffer, one line per row (trailing
spaces removed), as UTF-8 to OUT.txt. Uses ReadConsoleOutputCharacterW, so the
text is exactly the characters on screen - a garbled character shows up as
U+FFFD or '?', not as what the file held.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

STD_OUTPUT_HANDLE = -11


class COORD(ctypes.Structure):
    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [("Left", wintypes.SHORT), ("Top", wintypes.SHORT),
                ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT)]


class CSBI(ctypes.Structure):
    _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD), ("wAttributes", wintypes.WORD),
                ("srWindow", SMALL_RECT), ("dwMaximumWindowSize", COORD)]


def main() -> int:
    k32 = ctypes.windll.kernel32
    h = k32.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)   # the console itself
    info = CSBI()
    if not k32.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
        open(sys.argv[1], "w", encoding="utf-8").write("NO CONSOLE\n")
        return 1
    w = info.dwSize.X
    rows = []
    for y in range(0, info.dwCursorPosition.Y + 1):
        buf = ctypes.create_unicode_buffer(w + 1)
        n = wintypes.DWORD()
        k32.ReadConsoleOutputCharacterW(h, buf, w, COORD(0, y), ctypes.byref(n))
        rows.append(buf.value[:n.value].rstrip())
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write(f"WIDTH {w}\n")
        f.write("\n".join(rows) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
