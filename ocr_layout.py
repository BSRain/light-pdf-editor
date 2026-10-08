"""Estimate per-line appearance from raster ink, using a substitute font."""
from collections import Counter
import math
import pymupdf as fitz
from pdf_core import add_text, load_font


def ink_bounds(pix, values, background):
    """Bounded sampling; return pixel bounds and dominant contrasting RGB ink."""
    x0,y0,x1,y1=fitz.Rect(values).irect
    x0,y0=max(0,x0),max(0,y0)
    x1,y1=min(pix.width,x1),min(pix.height,y1)
    step=max(1,math.ceil(math.sqrt(max(0,(x1-x0)*(y1-y0))/40000)))
    samples=pix.samples_mv
    colors=Counter();representatives={};bounds=[x1,y1,x0,y0]
    for y in range(y0,y1,step):
        for x in range(x0,x1,step):
            offset=y*pix.stride+x*pix.n
            rgb=tuple(samples[offset:offset+3])
            if max(abs(a-b) for a,b in zip(rgb,background)) < 65:
                continue
            key=tuple(v//16 for v in rgb)
            colors[key]+=1;representatives[key]=rgb
            bounds=[min(bounds[0],x),min(bounds[1],y),max(bounds[2],x+step),max(bounds[3],y+step)]
    if not colors:
        return None,[0,0,0]
    bounds[2],bounds[3]=min(x1,bounds[2]),min(y1,bounds[3])
    return bounds,list(representatives[colors.most_common(1)[0][0]])


def text_box(rect, text, fontfile, size, color, x, y):
    font=load_font(fontfile) if fontfile else fitz.Font('china-s')
    width=max((font.text_length(line,fontsize=size) if fontfile else len(line)*size
               for line in text.splitlines()),default=0)+2
    height=size*(font.ascender-font.descender)+.5
    return dict(x=x,y=y,width=min(rect[2]-x,width),height=min(rect[3]-y,height),text=text,
                size=size,color=list(color),fontfile=fontfile,bold=False,align=0)


def match_line(data, line, fontfile, pix):
    scale=data['scale'];ox,oy=data['origin'];rect=fitz.Rect(data['rect'])
    x0,y0,x1,y1=line['bbox']
    bounds,color=ink_bounds(pix,[(x0-ox)*scale,(y0-oy)*scale,(x1-ox)*scale,(y1-oy)*scale],
                            [round(v*255) for v in data['fill_color']])
    if bounds is None:
        bounds=[(x0-ox)*scale,(y0-oy)*scale,(x1-ox)*scale,(y1-oy)*scale]
    source=fitz.Rect(ox+bounds[0]/scale,oy+bounds[1]/scale,ox+bounds[2]/scale,oy+bounds[3]/scale)
    text=line['text'];font=load_font(fontfile) if fontfile else fitz.Font('china-s')
    # Rasterize the substitute at a known size; font-wide ascender metrics alone
    # overestimate the ink height of Latin text and shift reconstructed baselines.
    reference_size=24
    width=(font.text_length(text,fontsize=reference_size) if fontfile else len(text)*reference_size)+12
    if len(text)>1000 or width>20000:
        raise ValueError('单行文字过长，请分块转换。')
    with fitz.open() as doc:
        page=doc.new_page(width=max(30,width),height=90)
        add_text(page,4,4,text,reference_size,(0,0,0),fontfile,width-4,80)
        reference=page.get_pixmap(alpha=False)
        ink,_=ink_bounds(reference,[0,0,reference.width,reference.height],[255,255,255])
    if ink is None:
        raise ValueError('当前字体不能重建此行，请选择其他字体。')
    size=min(source.width/max(1,ink[2]-ink[0]),source.height/max(1,ink[3]-ink[1]))*reference_size
    size=max(4,min(144,size))
    x=max(rect.x0,source.x0-(ink[0]-4)*size/reference_size)
    y=max(rect.y0,source.y0-(ink[1]-4)*size/reference_size)
    return text_box(list(rect),text,fontfile,round(size,2),[v/255 for v in color],round(x,2),round(y,2))
