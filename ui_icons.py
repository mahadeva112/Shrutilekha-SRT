"""The Srutilekha logo as Pillow drawing commands (scripts/make_icon.py)."""

LOGO_INK = '#2d2416'
LOGO_LINES = '#f3d18f'


def draw_logo(draw, n, tile, ink=LOGO_INK, lines=LOGO_LINES, glyph=.72):
    """The Srutilekha mark on an n x n canvas: a speech bubble holding two
    centred subtitle lines, on a rounded gold tile. Speech in, captions out,
    in no particular script. ui/home.html, ui/studio.html and icon.ico
    (scripts/make_icon.py) draw the same shape; change one, change them all.

    `tile` is a colour or None (no tile: the caller has painted it). `glyph` is
    the share of the tile the bubble's 24-unit box takes."""
    if tile is not None:
        draw.rounded_rectangle((0, 0, n - 1, n - 1), radius=n * .25, fill=tile)
    s = n * glyph / 24
    o = n * (1 - glyph) / 2
    def p(x, y): return (o + x * s, o + y * s)
    draw.rounded_rectangle((*p(3, 4.5), *p(21, 17)), radius=3.5 * s, fill=ink)
    draw.polygon([p(7, 16), p(7, 20.3), p(12.5, 16)], fill=ink)
    w = max(1, round(2.2 * s))
    for x0, x1, y in ((7.5, 16.5, 9.3), (9.5, 14.5, 12.7)):
        draw.line([p(x0, y), p(x1, y)], fill=lines, width=w)
        for x in (x0, x1):
            cx, cy = p(x, y)
            draw.ellipse((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), fill=lines)
