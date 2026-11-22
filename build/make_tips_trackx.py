"""
Draws the hover pictures of the 4.0 'trackx' part (re-tracking single cells and
the ROI troubleshooter) into app/peterpiper/assets/tips/:

    trackx_troubleshooter.png   one cell tracked several ways; pick the steadiest
    trackx_retrack.png          after a change only that cell (and the neighbours it
                                touches) is tracked again; the other traces stay

    python build/make_tips_trackx.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "app" / "peterpiper" / "assets" / "tips"
W, H = 320, 160
BG, INK, MUTED = (250, 250, 247), (40, 44, 52), (120, 124, 132)
CELL = (238, 51, 136)                   # widgets.PALETTE[4]: a cell colour
GOOD, OK, POOR = (46, 139, 87), (201, 162, 39), (176, 65, 62)


def font(size: int, bold: bool = False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), ("arialbd.ttf" if bold else
                                                                "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def badge(d: ImageDraw.ImageDraw, x: int, y: int, text: str, col) -> None:
    w = int(d.textlength(text, font=font(10, True))) + 10
    d.rounded_rectangle((x, y, x + w, y + 15), 7, fill=col)
    d.text((x + 5, y + 1), text, fill=(255, 255, 255), font=font(10, True))


def tile(d: ImageDraw.ImageDraw, x: int, y: int, label: str, grade: str, wobbly: bool,
         chosen: bool = False) -> None:
    d.rounded_rectangle((x, y, x + 96, y + 104), 8, fill=(255, 255, 255),
                        outline=(80, 120, 230) if chosen else (205, 208, 214),
                        width=3 if chosen else 1)
    d.text((x + 6, y + 4), label, fill=INK, font=font(11, True))
    badge(d, x + 6, y + 82, grade, {"good": GOOD, "ok": OK, "poor": POOR}[grade])
    for i in range(3):                           # the cell at three timepoints
        cx, cy = x + 18 + i * 30, y + 50
        d.rectangle((cx - 13, cy - 16, cx + 13, cy + 16), fill=(30, 30, 34))
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(200, 200, 200))
        if wobbly and i:
            pts = [(cx - 12 + 3 * i, cy - 4), (cx - 4, cy - 12), (cx + 2, cy - 6),
                   (cx - 2, cy + 4), (cx - 10, cy + 6)]
            d.polygon(pts, outline=CELL)
        else:
            d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), outline=CELL, width=2)


def troubleshooter() -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((8, 4), "One cell, tracked several ways", fill=INK, font=font(13, True))
    tile(d, 8, 26, "Now (Cy5)", "poor", True)
    tile(d, 112, 26, "GFP only", "good", False, chosen=True)
    tile(d, 216, 26, "bigger moves", "ok", True)
    d.text((8, 138), "Click the steadiest, then 'Use this for cell 5'.", fill=MUTED,
           font=font(11))
    return im


def retrack() -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((8, 4), "Only what changed is tracked again", fill=INK, font=font(13, True))
    for i in range(5):
        for j in range(3):
            cx, cy = 30 + i * 52, 44 + j * 34
            changed = (i, j) == (2, 1)
            near = abs(i - 2) <= 1 and abs(j - 1) <= 1 and not changed
            col = CELL if changed else (130, 170, 230) if near else (200, 202, 206)
            d.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), outline=col, width=3 if changed else 2)
    d.text((8, 128), "Tracked again: the moved cell (pink) and the", fill=MUTED, font=font(10))
    d.text((8, 141), "neighbours it touches (blue) - same numbers.", fill=MUTED, font=font(10))
    return im


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("trackx_troubleshooter", troubleshooter), ("trackx_retrack", retrack)):
        p = OUT / f"{name}.png"
        fn().save(p)
        print(p)


if __name__ == "__main__":
    main()
