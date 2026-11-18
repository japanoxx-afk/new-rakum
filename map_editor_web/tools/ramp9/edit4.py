import sys;sys.path.insert(0,'/home/claude/re');sys.path.insert(0,'/home/claude/re/ramp9')
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from edit2 import soft_poly
def edit(img, liptile, A=(150,2,262,82), src_off=(-250,8), dark=0.30, light=0.10,
         lipline=((55,84),(240,40)), lipoff=(254,64), lipfade=(70,120)):
    H,W=img.shape[:2]; out=img.astype(float).copy(); alpha=img[...,3]>0
    yy,xx=np.mgrid[0:H,0:W].astype(float)
    # 1) upper-left wall: SE-facing (visible) rock face, made upright
    x0,y0,x1,y1=A; patch=img[y0:y1,x0:x1][::-1].astype(float)
    m=soft_poly(H,W,[(x0+8,y0+8),(x1-8,y0+8),(x1-8,y1-8),(x0+8,y1-8)],4)[y0:y1,x0:x1,None]*(patch[...,3:4]>0)
    out[y0:y1,x0:x1,:3]=out[y0:y1,x0:x1,:3]*(1-m)+patch[...,:3]*m
    # 2) lower-right: remove upside-down rocks
    mb=soft_poly(H,W,[(320,88),(430,70),(500,112),(480,150),(400,205),(300,248),(280,180)],6); dx,dy=src_off
    src=np.roll(np.roll(img.astype(float),dy,0),dx,1); ok=np.roll(np.roll(alpha,dy,0),dx,1)
    mbb=(mb*ok)[...,None]; out[...,:3]=out[...,:3]*(1-mbb)+src[...,:3]*mbb
    # 3) corridor shading
    ax=np.array([382-128,64-192.]); L=np.hypot(*ax); u=ax/L
    t=np.clip(((xx-128)*u[0]+(yy-192)*u[1])/L,0,1)
    n=np.abs((xx-128)*(-u[1])+(yy-192)*u[0]); corridor=np.exp(-(n/80)**2)
    cx,cy=W/2,H/2; d=1-(np.abs(xx+0.5-cx)/cx+np.abs(yy+0.5-cy)/cy); fade=np.clip(d/0.10,0,1)
    g=1+(light*(1-t)*2-dark*t**1.3)*corridor*fade
    out[...,:3]*=g[...,None]
    # 4) NW-facing back edge (lip) of the right-hand plateau strip, from the game's own hill-edge tile
    lt=np.asarray(liptile).astype(float); th,tw=lt.shape[:2]
    ly,lx=np.mgrid[0:th,0:tw].astype(float)
    (ax0,ay0),(ax1,ay1)=lipline
    side=(ax1-ax0)*(ly-ay0)-(ay1-ay0)*(lx-ax0)   # >0 below line
    sd=side/np.hypot(ax1-ax0,ay1-ay0)
    green=gaussian_filter(np.clip((lt[...,1]-lt[...,0]+6)/10,0,1),1.5)
    lm=np.clip((sd+4)/8,0,1)*green*(lt[...,3]>0)*np.clip((lx-lipfade[0])/(lipfade[1]-lipfade[0]),0,1)
    # shadow just above the lip on corridor side
    sh=np.exp(-(np.clip(-sd,0,None)/14)**2)*(sd<0)*(lt[...,3]>0)*np.clip((lx-lipfade[0])/(lipfade[1]-lipfade[0]),0,1)
    ox,oy=lipoff
    reg=out[oy:oy+th,ox:ox+tw]; ra=img[oy:oy+th,ox:ox+tw,3:4]>0
    reg[...,:3]*= (1-0.35*sh[...,None]*ra)
    mm=(lm[...,None]*ra)
    reg[...,:3]=reg[...,:3]*(1-mm)+lt[...,:3]*mm
    out[...,3]=img[...,3]
    return np.clip(out,0,255).astype(np.uint8)
