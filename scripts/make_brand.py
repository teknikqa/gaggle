#!/usr/bin/env python3
"""Regenerate gaggle's brand PNGs (custom_components/gaggle/brand/).

Mark: a bold "G" letterform + a two-tone blue gas-flame glyph (gas, not
electricity -- deliberately distinct from haggle's dark-green H + orange
bolt). Wordmark: "gaggle" in the same rounded bold face, mark to its left.
Produces icon/icon@2x/logo/logo@2x and dark_* variants at the exact
dimensions HA's brands repo expects (256/512 square icons, 1100x256 /
2200x512 logos).

Requires Pillow (not a project dependency -- run via
`uv run --with pillow python scripts/make_brand.py`) and macOS's bundled
Arial Rounded Bold; there is no cross-platform font fallback, so this is a
macOS-only maintainer tool, not something CI runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print(
        "Pillow is required: uv run --with pillow python scripts/make_brand.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from None

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"

LIGHT_INK = (23, 50, 74, 255)  # deep slate-blue -- mark + wordmark, light mode
DARK_INK = (231, 240, 246, 255)  # pale ice-blue -- mark + wordmark, dark mode
FLAME = (37, 115, 196, 255)  # gas-flame blue (outer) -- constant across light/dark
FLAME_CORE = (127, 208, 234, 255)  # pale cyan inner core, like a real gas flame

OUT_DIR = Path(__file__).resolve().parent.parent / "custom_components/gaggle/brand"


def draw_flame(
    draw: ImageDraw.ImageDraw,
    x0: float,
    y0: float,
    w: float,
    h: float,
    fill: tuple[int, int, int, int],
    scale: float = 1.0,
) -> None:
    """A rounded gas-flame silhouette: an oval body with a tapered, gently
    S-curved tip -- reads as a flame rather than a bolt. `scale` shrinks the
    shape around its own center (used to draw a lighter inner core)."""
    cx = x0 + w / 2
    cy = y0 + h / 2
    if scale != 1.0:
        w, h = w * scale, h * scale
        x0, y0 = cx - w / 2, cy - h / 2

    draw.ellipse(
        [x0 + w * 0.14, y0 + h * 0.42, x0 + w * 0.86, y0 + h * 1.0],
        fill=fill,
    )
    tip = [
        (x0 + w * 0.50, y0 + h * 0.00),
        (x0 + w * 0.74, y0 + h * 0.36),
        (x0 + w * 0.62, y0 + h * 0.34),
        (x0 + w * 0.72, y0 + h * 0.62),
        (x0 + w * 0.50, y0 + h * 0.50),
        (x0 + w * 0.28, y0 + h * 0.62),
        (x0 + w * 0.38, y0 + h * 0.34),
        (x0 + w * 0.26, y0 + h * 0.36),
    ]
    draw.polygon(tip, fill=fill)


def draw_mark(
    draw: ImageDraw.ImageDraw,
    size: float,
    x_off: float,
    ink: tuple[int, int, int, int],
) -> None:
    g_font = ImageFont.truetype(FONT_PATH, int(size * 0.82))
    bbox = draw.textbbox((0, 0), "G", font=g_font)
    gh = bbox[3] - bbox[1]
    gx = x_off + size * 0.06 - bbox[0]
    gy = (size - gh) / 2 - bbox[1]
    draw.text((gx, gy), "G", font=g_font, fill=ink)

    fw, fh = size * 0.34, size * 0.66
    fx, fy = x_off + size * 0.60, size * 0.17
    draw_flame(draw, fx, fy, fw, fh, FLAME)
    draw_flame(draw, fx, fy + fh * 0.20, fw, fh, FLAME_CORE, scale=0.5)


def draw_icon(size: int, ink: tuple[int, int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_mark(ImageDraw.Draw(img), size, 0, ink)
    return img


def draw_logo(height: int, ink: tuple[int, int, int, int]) -> Image.Image:
    width = int(height * 1100 / 256)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    mark_w = height  # square mark area, same as icon
    draw_mark(draw, mark_w, 0, ink)

    word_font = ImageFont.truetype(FONT_PATH, int(height * 0.62))
    wx = mark_w * 1.08
    wbbox = draw.textbbox((0, 0), "gaggle", font=word_font)
    wh = wbbox[3] - wbbox[1]
    wy = (height - wh) / 2 - wbbox[1]
    draw.text((wx, wy), "gaggle", font=word_font, fill=ink)

    return img


def main() -> None:
    draw_icon(256, LIGHT_INK).save(OUT_DIR / "icon.png")
    draw_icon(512, LIGHT_INK).save(OUT_DIR / "icon@2x.png")
    draw_icon(256, DARK_INK).save(OUT_DIR / "dark_icon.png")
    draw_icon(512, DARK_INK).save(OUT_DIR / "dark_icon@2x.png")

    draw_logo(256, LIGHT_INK).save(OUT_DIR / "logo.png")
    draw_logo(512, LIGHT_INK).save(OUT_DIR / "logo@2x.png")
    draw_logo(256, DARK_INK).save(OUT_DIR / "dark_logo.png")
    draw_logo(512, DARK_INK).save(OUT_DIR / "dark_logo@2x.png")

    print(f"Wrote 8 brand PNGs to {OUT_DIR}")


if __name__ == "__main__":
    main()
