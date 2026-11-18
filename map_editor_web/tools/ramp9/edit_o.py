import numpy as np
from PIL import Image
import sys;sys.path.insert(0,'/home/claude/re/ramp9')
from edit2 import soft_poly
def edit_under(f,U,poly=[(0,92),(100,52),(152,122),(174,178),(166,212),(0,128)],feather=6):
    H,W=f.shape[:2]; U=np.asarray(U).astype(float)[:H,:W]
    m=soft_poly(W=W,H=H,poly=poly,f=feather)*(U[...,3]>0)*(f[...,3]>0)
    e=f.astype(float).copy(); e[...,:3]=e[...,:3]*(1-m[...,None])+U[...,:3]*m[...,None]
    return np.clip(e,0,255).astype(np.uint8)
def round_tip(f,U,x0=350,x1=455,rmax=34,feather=5):
    """carve the pointed outer mound at the right corner into a rounded end (replace with ground under it)"""
    H,W=f.shape[:2]; U=np.asarray(U).astype(float)[:H,:W]
    yy,xx=np.mgrid[0:H,0:W].astype(float)
    # distance below the upper-right diamond edge (from (255,0) to (510,128))
    d=((yy-0)-(xx-255)*128/255)/np.hypot(1,128/255)
    t=np.clip((xx-x0)/(x1-x0),0,1); r=rmax*np.sin(t*np.pi/2)**1.2
    r=np.where(xx>x1, rmax+(xx-x1)*1.6, r)
    m=np.clip((r-d)/feather,0,1)*(xx>x0)*(U[...,3]>0)*(f[...,3]>0)
    e=f.astype(float).copy(); e[...,:3]=e[...,:3]*(1-m[...,None])+U[...,:3]*m[...,None]
    return np.clip(e,0,255).astype(np.uint8)
def cap(f,U,c=(392,120),rx=36,ry=48,feather=6):
    H,W=f.shape[:2]; U=np.asarray(U).astype(float)[:H,:W]
    yy,xx=np.mgrid[0:H,0:W].astype(float)
    q=np.sqrt(((xx-c[0])/rx)**2+((yy-c[1])/ry)**2)
    m=np.clip((q-1)*min(rx,ry)/feather,0,1)*(xx>c[0])*(yy<c[1]+ry)*(U[...,3]>0)*(f[...,3]>0)
    e=f.astype(float).copy(); e[...,:3]=e[...,:3]*(1-m[...,None])+U[...,:3]*m[...,None]
    return np.clip(e,0,255).astype(np.uint8)
