"""Small vector paths rasterized at display resolution with 4x antialiasing."""
from functools import lru_cache
from PIL import Image, ImageDraw, ImageTk
from dpi import pixels

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


@lru_cache(maxsize=256)
def artwork(kind, size, color):
    n=max(1,size);q=4
    image=Image.new('RGBA',(n*q,n*q))
    draw=ImageDraw.Draw(image)
    unit=n*q/18
    def box(v):return tuple(float(x)*unit for x in v)
    def line(v,width=1.6):
        points=list(zip(v[::2],v[1::2]));thick=max(1,round(width*unit))
        draw.line([tuple(x*unit for x in p) for p in points],fill=color,width=thick,joint='curve')
        for x,y in (points[0],points[-1]):
            r=width/2;draw.ellipse(box((x-r,y-r,x+r,y+r)),fill=color)
    def rect(v,radius=0):
        draw.rounded_rectangle(box(v),radius=radius*unit,outline=color,width=max(1,round(1.5*unit)))
    if kind=='logo':
        draw_logo(draw,n*q,color)
    elif kind in ('Audio','wave'):
        for x,y in ((3,6),(7,3),(11,5),(15,7)):line((x,y,x,18-y),2)
    elif kind=='Timing':
        draw.ellipse(box((2,2,16,16)),outline=color,width=max(1,round(1.5*unit)))
        line((9,5,9,9,12,11))
    elif kind=='Files':
        rect((4,2,14,16),1)
        for y in (6,9,12):line((7,y,11,y),1)
    elif kind=='Presets':line((4,16,4,2,14,2,14,16,9,12,4,16))
    elif kind=='Style':
        for y,x in ((4,6),(9,12),(14,8)):
            line((2,y,16,y),1)
            draw.ellipse(box((x-2,y-2,x+2,y+2)),outline=color,width=max(1,round(1.5*unit)))
    elif kind=='min':line((4,9,14,9),1.3)
    elif kind=='max':rect((4,4,14,14),.5)
    elif kind=='restore':
        line((7,4,14,4,14,11),1.3);rect((4,7,11,14),.5)
    elif kind=='close':line((4,4,14,14),1.3);line((14,4,4,14),1.3)
    elif kind=='chevron-down':line((4,7,9,12,14,7),1.5)
    elif kind=='provider':
        line((6,5,6,15),2);line((12,3,12,15),2)
    elif kind=='warning':
        line((9,2,17,16,1,16,9,2),1.3)
        line((9,6,9,10),1.5)
        draw.ellipse(box((8.25,12,9.75,13.5)),fill=color)
    elif kind=='shield':
        line((9,1,16,4,15,11,9,17,3,11,2,4,9,1),1)
        line((5,8,8,11,13,6),1.3)
    elif kind=='mic':
        rect((6,2,12,11),3)
        draw.arc(box((4,5,14,14)),0,180,fill=color,width=max(1,round(1.5*unit)))
        line((9,14,9,17));line((6,17,12,17))
    elif kind=='volume':
        draw.polygon([tuple(x*unit for x in p) for p in ((2,7),(5,7),(9,3),(9,15),(5,11),(2,11))],fill=color)
        for v in ((8,5,14,13),(8,2,17,16)):
            draw.arc(box(v),-55,55,fill=color,width=max(1,round(1.5*unit)))
    elif kind=='local':
        rect((3,2,15,12),1);line((9,12,9,16));line((6,16,12,16))
    elif kind=='bullet':draw.ellipse(box((6,6,12,12)),fill=color)
    else:raise ValueError('Unknown icon: '+kind)
    return image.resize((n,n),Image.Resampling.LANCZOS)


def photo(widget,kind,size,color):
    return ImageTk.PhotoImage(artwork(kind,pixels(widget,size),color),master=widget)
