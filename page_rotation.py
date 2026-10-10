"""Coordinate frames for editable boxes on rotated pages."""
from types import SimpleNamespace
import pymupdf as fitz


def object_frame(page, obj):
    rotation=obj.get('page_rotation',page.rotation)
    width,height=page.rect.width,page.rect.height
    delta=(page.rotation-rotation)%360
    if delta in (90,270): width,height=height,width
    frame=fitz.Rect(0,0,width,height)
    matrix=fitz.Matrix(delta)
    bounds=frame*matrix
    matrix=matrix*fitz.Matrix(1,0,0,1,-bounds.x0,-bounds.y0)
    return SimpleNamespace(rect=frame),matrix


def rotate_page(doc,index,delta,objects):
    if type(delta) is not int or delta not in (-90,90):
        raise ValueError('请选择向左或向右旋转 90°。')
    page=doc[index]
    for obj in objects.values():
        if obj['index']==index: obj.setdefault('page_rotation',page.rotation)
    page.set_rotation((page.rotation+delta)%360)
    for obj in objects.values():
        if obj['index']==index:
            _,matrix=object_frame(page,obj)
            spec=obj['spec']
            obj['bbox']=list(fitz.Rect(spec['x'],spec['y'],spec['x']+spec['width'],spec['y']+spec['height'])*matrix)
