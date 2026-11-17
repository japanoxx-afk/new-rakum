import sys;sys.path.insert(0,'/home/claude/re');sys.path.insert(0,'/home/claude/re/ramp9')
import numpy as np
from scipy.ndimage import gaussian_filter
import edit4
POS={'top':(127,0),'left':(0,64),'right':(254,64),'bottom':(127,128)}
def base_layer(T,ids=(10,11,12,13),H=256,W=510):
    out=np.zeros((H,W,4),float)
    for (k,(x0,y0)),i in zip(POS.items(),ids):
        t=np.asarray(T.get(i)).astype(float)[:, :min(256,W-x0)]
        m=t[...,3:4]>0; reg=out[y0:y0+128,x0:x0+t.shape[1]]
        reg[...]=np.where(m,t,reg)
    from scipy.ndimage import grey_dilation
    a=out[...,3]>0
    for _ in range(3):
        for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
            sh=np.roll(np.roll(out,dy,0),dx,1); sa=np.roll(np.roll(a,dy,0),dx,1)
            fill=(~a)&sa; out[fill]=sh[fill]; a=a|fill
    return out
def edit(img,T,lip_tile=70,t0=0.36,t1=0.80,seed=3,lip=False):
    e=edit4.edit(img,T.get(lip_tile)).astype(float)
    H,W=img.shape[:2]; yy,xx=np.mgrid[0:H,0:W].astype(float)
    ax=np.array([382-128,64-192.]); L=np.hypot(*ax); u=ax/L
    t=((xx-128)*u[0]+(yy-192)*u[1])/L
    w=np.clip((t-t0)/(t1-t0),0,1); w=w*w*(3-2*w)
    # keep the right-hand plateau strip and its lip: only above the lip line
    (a0,b0),(a1,b1)=edit4.__dict__.get('LIP',((55+254,84+64),(240+254,40+64)))
    sd=((a1-a0)*(yy-b0)-(b1-b0)*(xx-a0))/np.hypot(a1-a0,b1-b0)   # >0 below lip
    w*=np.clip((-sd-6)/14,0,1)*0.0+1.0
    # keep the upright rock wall at upper-left
    # remove the upper-left rock wall too: refill with ramp grass from below it
    rock=edit4.soft_poly(H,W,[(140,10),(275,0),(275,95),(140,100)],7)
    srcg=np.roll(e,-95,0); okg=np.roll(img[...,3]>0,-95,0)
    rr=(rock*okg)[...,None]; e[...,:3]=e[...,:3]*(1-rr)+srcg[...,:3]*rr
    # area beyond the plateau's back edge at the top -> lowland too
    wtop=np.clip((95-yy-(xx-128)*0.15)/45,0,1); wtop=wtop*wtop*(3-2*wtop)
    w=np.maximum(w,wtop)
    rng=np.random.default_rng(seed); nz=gaussian_filter(rng.standard_normal((H,W)),9); nz/=nz.std()
    w=np.clip(w+0.22*nz*w*(1-w)*4,0,1)
    base=base_layer(T)
    e[...,:3]=e[...,:3]*(1-w[...,None])+base[...,:3]*w[...,None]
    # re-apply only the mossy lip band from the hill-edge tile
    lt=np.asarray(T.get(lip_tile)).astype(float); ox,oy=254,64; th,tw=lt.shape[0],W-ox; lt=lt[:,:tw]
    ly,lx=np.mgrid[0:th,0:tw].astype(float); (p0,q0),(p1,q1)=((55,84),(240,40))
    lsd=((p1-p0)*(ly-q0)-(q1-q0)*(lx-p0))/np.hypot(p1-p0,q1-q0)
    green=gaussian_filter(np.clip((lt[...,1]-lt[...,0]+6)/10,0,1),1.5)
    band=np.clip((lsd+4)/6,0,1)*np.clip((22-lsd)/8,0,1)*green*(lt[...,3]>0)*np.clip((lx-70)/50,0,1)
    reg=e[oy:oy+th,ox:ox+tw]; ra=(img[oy:oy+th,ox:ox+tw,3]>0)
    band=band*lip
    bb=(band*ra)[...,None]; reg[...,:3]=reg[...,:3]*(1-bb)+lt[...,:3]*bb
    # soft shadow just beyond (above) the lip
    shd=np.exp(-(np.clip(-lsd,0,None)/10)**2)*(lsd<0)*ra*np.clip((lx-70)/50,0,1)
    reg[...,:3]*=(1-0.30*shd*lip)[...,None]
    e[...,3]=img[...,3]
    return np.clip(e,0,255).astype(np.uint8)
