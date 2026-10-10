"""Conservative single-style text replacement using the original embedded font."""
import hashlib
import math
import statistics
import pymupdf as fitz
from alignment import normalized_family
from pdf_core import text_characters, delete_characters


def targets(page):
    flags=(fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES)|fitz.TEXT_INHIBIT_SPACES|fitz.TEXT_ACCURATE_ASCENDERS
    result=[];serial=0
    for block in page.get_text('rawdict',flags=flags)['blocks']:
        for line in block.get('lines',[]):
            for span in line['spans']:
                chars=span['chars'];ids=list(range(serial,serial+len(chars)));serial+=len(chars)
                if chars and ''.join(c['c'] for c in chars).strip():
                    result.append(dict(span=span,ids=ids,text=''.join(c['c'] for c in chars),direction=line['dir'],wmode=line['wmode']))
    return result


def select(page,point):
    point=fitz.Point(point)
    hits=[(i,t) for i,t in enumerate(targets(page)) if (fitz.Rect(t['span']['bbox'])*page.rotation_matrix).contains(point)]
    if len(hits)!=1:
        raise ValueError('请点击一段可提取、没有重叠的原文字；图片文字需先使用 OCR。')
    return hits[0]


def foreground_overlap(page,seqno,bbox,own_sequences):
    drawings={d['seqno']:d for d in page.get_drawings()}
    for number,(kind,box,*_) in enumerate(page.get_bboxlog()):
        if number<=seqno or number in own_sequences or not fitz.Rect(box).intersects(bbox):continue
        if kind!='stroke-path':return True
        drawing=drawings.get(number)
        if drawing is None:return True
        padding=max(.5,drawing.get('width',1)/2)
        for item in drawing['items']:
            if item[0]=='re':
                r=item[1];segments=[(r.tl,r.tr),(r.tr,r.br),(r.br,r.bl),(r.bl,r.tl)]
            elif item[0]=='l':segments=[(item[1],item[2])]
            else:return True
            for a,b in segments:
                area=fitz.Rect(min(a.x,b.x)-padding,min(a.y,b.y)-padding,max(a.x,b.x)+padding,max(a.y,b.y)+padding)
                if area.intersects(bbox):return True
    return False


def prepare(page,target_id):
    items=targets(page)
    if type(target_id) is not int or not 0<=target_id<len(items):
        raise ValueError('原文字已变化，请重新选择。')
    target=items[target_id];span=target['span'];direction=target['direction']
    if len(target['text'])>2000:
        raise ValueError('原文字段过长，暂不支持直接修改。')
    cardinal=[(1,0),(0,-1),(-1,0),(0,1)]
    rotations=[0,90,180,270]
    turn=next((rotations[i] for i,d in enumerate(cardinal) if max(abs(a-b) for a,b in zip(d,direction))<.001),None)
    if turn is None or target['wmode']!=0 or span.get('bidi',0):
        raise ValueError('暂不支持斜向、竖排排版或双向文字的原位修改。')
    first=span['chars'][0]['origin']
    all_traces=page.get_texttrace()
    traces=[t for t in all_traces if any(abs(c[2][0]-first[0])<.01 and abs(c[2][1]-first[1])<.01 for c in t['chars'])]
    if len(traces)!=1 or traces[0]['type']!=0 or traces[0]['opacity']<=0:
        raise ValueError('此文字使用描边、隐藏或叠加绘制，无法保证原格式，请使用新增文字工具。')
    trace=traces[0]
    # Redrawing above a later foreground object would change the original paint order.
    bbox=fitz.Rect(span['bbox'])
    # A previous edit emits one text operation per character. Those operations
    # belong to this same span and must not be mistaken for foreground content.
    char_keys={(ord(c['c']),round(c['origin'][0],3),round(c['origin'][1],3)) for c in span['chars']}
    own_sequences={t['seqno'] for t in all_traces if t['chars'] and all(
        (c[0],round(c[2][0],3),round(c[2][1],3)) in char_keys for c in t['chars'])}
    if foreground_overlap(page,trace['seqno'],bbox,own_sequences):
        raise ValueError('原文字与后绘制的内容重叠，暂不支持安全原位替换。')
    candidates={}
    for resource in page.get_fonts(full=True):
        try:
            name,ext,kind,buffer=page.parent.extract_font(resource[0])
            if buffer:
                font=fitz.Font(fontbuffer=buffer);key=hashlib.sha256(buffer).hexdigest()
                names=(name,font.name)
                builtin=None
            else:
                builtin=fitz.Base14_fontdict.get(name.lower())
                if not builtin: continue
                font=fitz.Font(fontname=builtin);key=builtin;names=(name,)
            if not any(normalized_family(n)==normalized_family(span['font']) for n in names): continue
            if bool(font.is_bold)!=bool(span['flags']&16) or bool(font.is_italic)!=bool(span['flags']&2): continue
            if not all(font.has_glyph(c[0])==c[1] for c in trace['chars'] if c[0]>32): continue
            candidates[key]=(font,buffer,builtin)
        except (ValueError,RuntimeError):
            continue
    if len(candidates)!=1:
        raise ValueError('无法唯一复用原字体（可能为缺失或特殊子集字体），未修改原文。')
    font,buffer,builtin=next(iter(candidates.values()))
    tracking=[]
    for a,b in zip(span['chars'],span['chars'][1:]):
        advance=sum((b['origin'][i]-a['origin'][i])*direction[i] for i in (0,1))
        tracking.append(advance-font.text_length(a['c'],fontsize=span['size']))
    spacing=statistics.median(tracking) if tracking else 0
    if any(abs(v-spacing)>.05 for v in tracking):
        raise ValueError('原文字包含特殊字距或缩放，暂不能保证格式一致。')
    target.update(font=font,buffer=buffer,builtin=builtin,rotate=turn,trace=trace,tracking=spacing)
    return target


def replacement_bounds(page,target,text):
    if not isinstance(text,str) or len(text)>2000 or any(c in text for c in '\r\n\t'):
        raise ValueError('请修改同一行文字，最多 2000 个字符。')
    font=target['font'];span=target['span']
    missing=[c for c in text if not font.has_glyph(ord(c))]
    if missing:
        raise ValueError('原字体不包含新增字符：'+''.join(sorted(set(missing)))[:30]+'；未替换字体，请取消后使用添加文字工具。')
    width=font.text_length(text,fontsize=span['size'])+max(0,len(text)-1)*target['tracking']
    original=fitz.Rect(span['bbox']);box=fitz.Rect(original);x,y=span['origin'];dx,dy=target['direction']
    if dx>0:box.x0=x;box.x1=x+width
    elif dx<0:box.x0=x-width;box.x1=x
    elif dy>0:box.y0=y;box.y1=y+width
    else:box.y0=y-width;box.y1=y
    visible=box*page.rotation_matrix
    if text and not (page.rect+(-.01,-.01,.01,.01)).contains(visible):
        raise ValueError('新增文字超出页面，请减少字符；不会自动缩小字号。')
    selected=set(target['ids']);old=original*page.rotation_matrix
    if text and any(c['id'] not in selected and visible.intersects(fitz.Rect(c['bbox'])) and not old.intersects(fitz.Rect(c['bbox'])) for c in text_characters(page)):
        raise ValueError('新增文字会碰到相邻文字，请减少字符；不会移动其他内容。')
    return visible


def insert_replacement(page,target,text):
    if not text: return
    name=target['builtin']
    if name is None:
        name='Original'+hashlib.sha256(target['buffer']).hexdigest()[:16]
        page.insert_font(fontname=name,fontbuffer=target['buffer'])
    span=target['span'];trace=target['trace'];point=fitz.Point(span['origin'])
    first_sequence=len(page.get_bboxlog())
    shape=page.new_shape()
    for char in text:
        shape.insert_text(point,char,fontname=name,fontsize=span['size'],color=trace['color'],
                          fill_opacity=trace['opacity'],rotate=target['rotate'])
        advance=target['font'].text_length(char,fontsize=span['size'])+target['tracking']
        point+=fitz.Point(target['direction'])*advance
    shape.commit()
    inserted=''.join(chr(c[0]) for trace in page.get_texttrace() if trace['seqno']>=first_sequence for c in trace['chars'])
    if inserted.replace('\xa0',' ')!=text.replace('\xa0',' '):
        raise ValueError('原字体编码无法写入这些字符，已取消替换。')


def preview(doc,index,target,text):
    page=doc[index]
    box=replacement_bounds(page,target,text)
    old=fitz.Rect(target['span']['bbox'])*page.rotation_matrix
    area=(old|box)+(-12,-12,12,12);area&=page.rect
    delete_characters(page,target['ids'])
    insert_replacement(page,target,text)
    scale=min(3,math.sqrt(2_000_000/max(1,area.get_area())))
    return page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=area,alpha=False)


def verify_original_rendering(doc,index,target,candidate):
    """Refuse transforms / encodings that cannot be reproduced by this editor."""
    page=doc[index]
    box=replacement_bounds(page,target,target['text'])
    area=((fitz.Rect(target['span']['bbox'])*page.rotation_matrix)|box)+(-12,-12,12,12)
    area &= page.rect
    scale=min(3,math.sqrt(2_000_000/max(1,area.get_area())))
    original=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=area,alpha=False)
    rebuilt=preview(candidate,index,target,target['text'])
    a,b=original.samples,rebuilt.samples
    if len(a)!=len(b) or sum(abs(x-y) for x,y in zip(a,b))/max(1,len(a))>1.0 or sum(abs(x-y)>32 for x,y in zip(a,b))/max(1,len(a))>.01:
        raise ValueError('此段文字的缩放、字形或绘制效果无法可靠复现，已保留原文。')
