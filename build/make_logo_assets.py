"""
Developer tool (not shipped): make PeterPiper's logo files from the logo picture.

    python build/make_logo_assets.py [build/logo_source.png]

The source is the logo, black on white (the 'Moon ROI lockup'). Writes into
app/peterpiper/assets/:

  logo_black.png, logo_white.png   the whole logo on a transparent background
                                   (black for the light theme, white for the dark)
  PeterPiper.ico / .icns, piper_256.png  the piper alone, black, in a white rounded
                                   square (16 - 256 px) - window, taskbar, shortcuts
  logo_116.txt, logo_100.txt,      the logo drawn with half-block characters for
  logo_72.txt                      the launcher's terminal window, UTF-16 (116 / 100 / 72
                                   characters wide; the launcher shows the widest
                                   that fits). Each character holds two square
                                   'pixels' (top / bottom half): thin parts (the
                                   piper, notes, sparkles, the moon loop) are kept
                                   at a lower ink level than the lettering.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "build" / "logo_source.png"
OUT = REPO / "app" / "peterpiper" / "assets"

# in the source picture's pixels: the piper ends left of x = 455; the lettering
# starts below y = 640; the 'p' of 'peter' starts right of x = 336
FIGURE_RIGHT, LETTERS_TOP, P_LEFT = 455, 640, 336


def load_ink(path: Path) -> np.ndarray:
    g = np.asarray(Image.open(path).convert("L"), float) / 255.0
    return np.clip((1.0 - g - 0.04) / 0.92, 0, 1)            # 0 = paper, 1 = ink


def rgba(alpha: np.ndarray, colour) -> Image.Image:
    a = np.zeros(alpha.shape + (4,), np.uint8)
    a[..., :3] = colour
    a[..., 3] = (alpha * 255).round().astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def tile(fig: np.ndarray, size: int) -> Image.Image:
    """The piper, black, centred on a white rounded square with a thin grey edge."""
    S = size * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.18), fill=(255, 255, 255, 255),
                        outline=(150, 150, 150, 255), width=max(4, S // 64))
    h, w = fig.shape
    k = int(S * 0.80) / max(h, w)
    fw, fh = max(1, int(round(w * k))), max(1, int(round(h * k)))
    f = Image.fromarray((fig * 255).astype(np.uint8)).resize((fw, fh), Image.LANCZOS)
    im.paste(Image.new("RGBA", (fw, fh), (0, 0, 0, 255)), ((S - fw) // 2, (S - fh) // 2), f)
    return im.resize((size, size), Image.LANCZOS)


def text_art(ink: np.ndarray, box, cols: int) -> list:
    """Half-block lines (▀ ▄ █), `cols` characters wide."""
    y0, y1, x0, x1 = box
    img = ink[y0:y1, x0:x1]
    h, w = img.shape
    rows2 = int(round(cols * h / w))
    rows2 += rows2 % 2
    small = np.asarray(Image.fromarray((img * 255).astype(np.uint8)).resize(
        (cols, rows2), Image.BOX), float) / 255.0
    sy, sx = h / rows2, w / cols
    on = np.zeros(small.shape, bool)
    for r in range(rows2):
        for c in range(cols):
            X, Y = c * sx + x0, r * sy + y0
            thr = 0.20 if X < FIGURE_RIGHT else 0.18 if Y < LETTERS_TOP else 0.42
            on[r, c] = small[r, c] >= thr
    lines = []
    for r in range(0, rows2, 2):
        lines.append("".join("█" if a and b else "▀" if a else "▄" if b else " "
                             for a, b in zip(on[r], on[r + 1])).rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def main() -> int:
    ink = load_ink(SRC)
    ys, xs = np.nonzero(ink > 0.5)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    OUT.mkdir(parents=True, exist_ok=True)
    pad = 8
    lock = ink[y0 - pad:y1 + pad, x0 - pad:x1 + pad]
    rgba(lock, (0, 0, 0)).save(OUT / "logo_black.png", optimize=True)
    rgba(lock, (240, 240, 240)).save(OUT / "logo_white.png", optimize=True)
    m = ink.copy()
    yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]]
    m[~((xx < P_LEFT) | ((yy < LETTERS_TOP) & (xx < FIGURE_RIGHT)))] = 0
    fig = m[y0 - pad:y1 + pad, x0 - pad:FIGURE_RIGHT]
    fy, fx = np.nonzero(fig > 0.5)
    fig = fig[fy.min():fy.max() + 1, fx.min():fx.max() + 1]
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    big = tile(fig, 256)
    big.save(OUT / "piper_256.png", optimize=True)
    big.save(OUT / "PeterPiper.ico", sizes=[(s, s) for s in sizes],
             append_images=[tile(fig, s) for s in sizes if s != 256])
    # macOS: the app's icon (Finder, Dock), 16 - 1024 px
    tile(fig, 1024).save(OUT / "PeterPiper.icns",
                         append_images=[tile(fig, s) for s in (16, 32, 64, 128, 256, 512)])
    raw = 1.0 - np.asarray(Image.open(SRC).convert("L"), float) / 255.0   # plain ink level
    ry, rx = np.nonzero(raw > 0.5)
    box = (ry.min() - 6, ry.max() + 6, rx.min() - 6, rx.max() + 6)
    for cols in (116, 100, 72):
        lines = text_art(raw, box, cols)
        # UTF-16 with its byte-order mark: cmd's 'type' shows it as it is. (UTF-8
        # under 'chcp 65001' garbles a block character wherever type's output
        # chunks split one - seen as stray marks in a real console.)
        text = "\r\n".join(s or " " for s in lines) + "\r\n"
        (OUT / f"logo_{cols}.txt").write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
        print(f"logo_{cols}.txt: {len(lines)} lines, {max(len(s) for s in lines)} characters wide")
    print("written to", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
