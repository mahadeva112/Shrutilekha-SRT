"""Small vector paths rasterized at display resolution with 4x antialiasing."""
from functools import lru_cache
from PIL import Image, ImageDraw, ImageTk
from dpi import pixels


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
        draw.rounded_rectangle((0,0,n*q-1,n*q-1),radius=n*q*.25,fill=color)
        for cy,width in ((7.5,10.44),(12.18,5.4)):
            draw.rectangle(box((9-width/2,cy-.99,9+width/2,cy+.99)),fill='#14150f')
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
