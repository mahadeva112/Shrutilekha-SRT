"""Rebuild icon.ico (installer, .exe, tray) from ui_icons.draw_logo.

    python scripts/make_icon.py

The tile gets the same light-to-deep gold gradient as the web header's mark.
Each size is drawn at 4x and scaled down, so the small sizes stay crisp.
"""
import pathlib
import sys

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ui_icons import draw_logo  # noqa: E402

TOP, BOTTOM = (0xF3, 0xD1, 0x8F), (0xE9, 0xBE, 0x68)
SIZES = (16, 24, 32, 48, 64, 128, 256)


def tile(n):
    q = n * 4
    grad = Image.new("RGBA", (q, q))
    gd = ImageDraw.Draw(grad)
    for y in range(q):
        t = y / (q - 1)
        gd.line([(0, y), (q, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    mask = Image.new("L", (q, q))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, q - 1, q - 1), radius=q * .25, fill=255)
    image = Image.new("RGBA", (q, q))
    image.paste(grad, (0, 0), mask)
    draw_logo(ImageDraw.Draw(image), q, None)
    return image.resize((n, n), Image.Resampling.LANCZOS)


def main():
    images = [tile(n) for n in SIZES]
    out = ROOT / "icon.ico"
    images[-1].save(out, format="ICO", sizes=[(n, n) for n in SIZES], append_images=images[:-1])
    print("wrote", out)


if __name__ == "__main__":
    main()
