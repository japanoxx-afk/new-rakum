import sys;sys.path.insert(0,'/home/claude/re');sys.path.insert(0,'/home/claude/re/ramp9')
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
import edit5, edit4
def band_tex(lt,base=None):
    """ridge strip from hill-edge tile 70: pixels that differ from plain lowland ground"""
    lt=lt.astype(float)
    if base is None:
        green=gaussian_filter(np.clip((lt[...,1]-lt[...,0]+6)/10,0,1),1.2)*(lt[...,3]>0)
    else:
        bc=np.asarray(base).astype(float); a=bc[...,3]>0; mu=bc[a][:,:3].mean(0); sd=bc[a][:,:3].std()
        dist=np.sqrt(((gaussian_filter(lt[...,:3],(2,2,0))-mu)**2).sum(-1))
        green=gaussian_filter(np.clip((dist-1.2*sd)/(1.5*sd+1),0,1),1.2)*(lt[...,3]>0)
        # find the rim line: top-most non-ground pixel per column, fit a line
        xs=[];ys=[]
        for x in range(60,236,4):
            col=np.where(green[:,x]>0.5)[0]
            if len(col): xs.append(x); ys.append(col.min())
        k,b0=np.polyfit(xs,ys,1)
        src=((80,80*k+b0+4),(225,225*k+b0+4))
        ly,lx=np.mgrid[0:lt.shape[0],0:lt.shape[1]].astype(float)
        below=ly-(lx*k+b0)
        green=np.clip(green*1.5,0,1)*np.clip((below+2)/4,0,1)*np.clip((30-below)/8,0,1)
        return lt,green,src
    return lt,green,((80,78),(225,44))
def paste_bank(out,lt,green,a,b,flip,width=26,taper=(0.15,0.85),src=((80,78),(225,44)),seed=0):
    H,W=out.shape[:2]; yy,xx=np.mgrid[0:H,0:W].astype(float)
    a=np.array(a,float); b=np.array(b,float); d=b-a; L=np.hypot(*d); u=d/L; n=np.array([-u[1],u[0]])
    s=((xx-a[0])*u[0]+(yy-a[1])*u[1])/L
    p=(xx-a[0])*n[0]+(yy-a[1])*n[1]
    if flip: p=-p
    sa=np.array(src[0],float); sb=np.array(src[1],float); sd=sb-sa; sL=np.hypot(*sd); su=sd/sL; sn=np.array([-su[1],su[0]])
    # tile source position: repeat along the source segment
    ss=(s*L/sL)%1.0
    sx=sa[0]+ss*sd[0]+p*sn[0]; sy=sa[1]+ss*sd[1]+p*sn[1]
    rgb=np.stack([map_coordinates(lt[...,c],[sy,sx],order=1,mode='nearest') for c in range(3)],-1)
    g=map_coordinates(green,[sy,sx],order=1,mode='constant')
    tap=np.clip((taper[1]-s)/(taper[1]-taper[0]),0,1)*np.clip(s/0.04,0,1)*(s<=1)
    wid=width*tap
    m=g*np.clip((wid-np.abs(p-wid*0.3))/6,0,1)*(tap>0)
    # soft shade beneath the ridge (corridor side) to give height
    sh=np.exp(-((p+6)/10)**2)*(p<0)*tap
    out[...,:3]*=(1-0.25*sh)[...,None]
    out[...,:3]=out[...,:3]*(1-m[...,None])+rgb*m[...,None]
    return out
def edge_fade(e,T,img,keep_edge=((0,128),(255,256)),dist=60,U=None):
    """blend to lowland/plateau-interior dirt near every sprite border except the high-end edge"""
    H,W=e.shape[:2]; yy,xx=np.mgrid[0:H,0:W].astype(float)
    cx,cy=W/2,H/2
    # distance to each of the 4 diamond edges (in px, approx along normal)
    dd=1-(np.abs(xx+0.5-cx)/cx+np.abs(yy+0.5-cy)/cy)   # 0 at border
    (x0,y0),(x1,y1)=keep_edge
    # closeness to keep edge: signed distance from line
    kd=np.abs((x1-x0)*(yy-y0)-(y1-y0)*(xx-x0))/np.hypot(x1-x0,y1-y0)
    base=edit5.base_layer(T) if U is None else np.asarray(U).astype(float)
    near=np.clip(1-dd/0.30,0,1)          # 1 at border
    away=np.clip((kd-25)/70,0,1) if U is None else 1.0
    w=(near*away)**1.2; w=w*w*(3-2*w)
    e[...,:3]=e[...,:3]*(1-w[...,None])+base[...,:3]*w[...,None]
    return e
def edit(img,T,lip_tile=70,generic=False,U=None):
    if generic=='savage': return edit_savage(img,T,U)
    if generic: return edit_generic(img,T,U)
    e=edit5.edit(img,T,lip_tile).astype(float)
    e=edge_fade(e,T,img,U=U)
    lt,green,src=band_tex(np.asarray(T.get(lip_tile)),None if generic is False else T.get(10))
    # banks: both sides of the corridor, high end (lower-left edge) -> low end (upper-right)
    e=paste_bank(e,lt,green,(58,100),(305,46),flip=True,width=32,taper=(0.25,1.0),src=src)
    e=paste_bank(e,lt,green,(250,236),(452,110),flip=False,width=32,taper=(0.25,1.0),src=src)
    e[...,3]=img[...,3]
    return np.clip(e,0,255).astype(np.uint8)
def paste_bank2(out,tex,a,b,flip,width=26,taper=(0.25,1.0)):
    H,W=out.shape[:2]; yy,xx=np.mgrid[0:H,0:W].astype(float)
    a=np.array(a,float); b=np.array(b,float); d=b-a; L=np.hypot(*d); u=d/L; n=np.array([-u[1],u[0]])
    s=((xx-a[0])*u[0]+(yy-a[1])*u[1])/L
    p=(xx-a[0])*n[0]+(yy-a[1])*n[1]
    if flip: p=-p
    q=np.clip((s-taper[0])/(taper[1]-taper[0]),0,1)
    tap=np.sqrt(np.clip(1-q**2,0,1))*np.clip(s/0.04,0,1)*(s>=0)*(s<=taper[1])
    wid=width*tap+1e-6
    # ridge occupies p in [0,wid] (outward side); noisy edge
    rng=np.random.default_rng(7); nz=gaussian_filter(rng.standard_normal((H,W)),3); nz=nz/nz.std()*2.5
    inner=np.clip((p+nz)/2.5+0.5,0,1); outer=np.clip((wid-p+nz)/6,0,1)
    m=inner*outer*(tap>0.02)
    # lighting: lit crest near p~wid*0.35, darker inner face (towards corridor)
    rel=np.clip(p/wid,0,1)
    light=1.0+0.18*np.exp(-((rel-0.35)/0.18)**2)-0.22*np.exp(-((rel-0.0)/0.15)**2)
    col=tex[...,:3]*light[...,None]
    sh=np.exp(-((p+5)/9)**2)*(p<0)*np.clip(tap*1.5,0,1)
    out[...,:3]*=(1-0.30*sh)[...,None]
    out[...,:3]=out[...,:3]*(1-m[...,None])+col*m[...,None]
    return out
def edit_generic(img,T,U):
    e=edit5.edit(img,T,70).astype(float)
    e=edge_fade(e,T,img,U=U)
    tex=edit5.base_layer(T,ids=(20,21,22,23))
    e=paste_bank2(e,tex,(58,100),(305,46),flip=True,width=24,taper=(0.1,0.68))
    e=paste_bank2(e,tex,(250,236),(452,110),flip=False,width=24,taper=(0.05,0.5))
    e[...,3]=img[...,3]
    return np.clip(e,0,255).astype(np.uint8)
_O3={}
PRE='S'
def _orig3():
    """source art for stairs and pillars: always the ruins (Savage) carved set, recoloured to the
    current tileset's own rock / ramp colours so every tileset gets the same pillar-and-stair entrance"""
    if PRE not in _O3:
        from s16 import S16
        S=S16(open('/home/claude/re/S_BRIDGE.S16','rb').read()).decode(3)[1].astype(float)
        if PRE=='S': _O3[PRE]=S; return S
        O=S16(open('/home/claude/re/%s_BRIDGE.S16'%PRE,'rb').read()).decode(3)[1].astype(float)
        H,W=S.shape[:2]
        rock=edit4.soft_poly(H,W,PILLAR_POLY,0)>0.5; ramp=edit4.soft_poly(H,W,STAIR_SRC,0)>0.5
        a=(O[...,3]>0)
        def recol(src,tgt_mask,src_mask):
            tc=O[tgt_mask&a][:,:3].mean(0); sl=src[...,:3].mean(-1); ms=sl[src_mask&(S[...,3]>0)].mean()
            return np.clip((sl/ms)[...,None]*tc[None,None,:],0,255)
        R=S.copy()
        R[...,:3]=np.where(rock[...,None],recol(S,rock,rock),recol(S,ramp,ramp))
        _O3[PRE]=R
    return _O3[PRE]
def _unused_orig3():
    if PRE not in _O3:
        from s16 import S16
        _O3[PRE]=S16(open('/home/claude/re/%s_BRIDGE.S16'%PRE,'rb').read()).decode(3)[1].astype(float)
    return _O3[PRE]
PILLARS=[  # (polygon in original right-entrance sprite, dy shift into flipped sprite)
    ([(190,152),(203,140),(226,142),(240,156),(242,252),(205,252),(192,228),(177,206),(177,165)], -112, 0),
    ([(360,70),(378,66),(410,70),(452,90),(454,137),(422,135),(400,124),(380,112),(362,96)], 20, 0),
]
def paste_pillars(e,img):
    O=_orig3(); H,W=e.shape[:2]
    for poly,dy,dx in PILLARS:
        m=edit4.soft_poly(H,W,poly,1.0)*(O[...,3]>0)
        src=np.roll(np.roll(O,dy,0),dx,1); mm=np.roll(np.roll(m,dy,0),dx,1)*(img[...,3]>0)
        # contact shadow on the ground around the pillar base
        base=np.roll(np.roll(edit4.soft_poly(H,W,poly,6),dy,0),dx,1)
        sh=np.clip(gaussian_filter(base,5)-mm,0,1)*(img[...,3]>0)
        e[...,:3]*=(1-0.45*sh)[...,None]
        e[...,:3]=e[...,:3]*(1-mm[...,None])+src[...,:3]*mm[...,None]
    return e
def edit_savage(img,T,U):
    e=edit5.edit(img,T,70).astype(float)
    e=fill_floor(e,img)
    e=edge_fade(e,T,img,U=U)
    e=paste_stairs(e,img)
    e=stair_depth(e,img)
    e=lowland_exit(e,img,T)
    e=paste_pillars(e,img)
    e[...,3]=img[...,3]
    return np.clip(e,0,255).astype(np.uint8)

def edit_savage(img,T,U):
    H,W=img.shape[:2]; e=img.astype(float).copy() if PRE=='S' else edit5.edit(img,T,70).astype(float); a=img[...,3]>0
    # remove the upside-down pillar/wall: fill with stair/floor texture shifted along the step lines
    for (poly,dy,dx),(sx,sy) in zip(PILLARS,[(-60,30),(-80,40)]):
        fp=[(x,255-y) for x,y in poly]
        m=edit4.soft_poly(H,W,fp,3)
        src=np.roll(np.roll(img.astype(float),sy,0),sx,1); ok=np.roll(np.roll(a,sy,0),sx,1)
        mm=(m*ok)[...,None]; e[...,:3]=e[...,:3]*(1-mm)+src[...,:3]*mm
    e=fill_floor(e,img)
    e=edge_fade(e,T,img,U=U)
    e=paste_stairs(e,img)
    e=stair_shade(e,img)
    e=lowland_exit(e,img,T)
    e=clean_ghost(e,img,T)
    e=pillar_rows(e,img)
    e[...,3]=img[...,3]
    return np.clip(e,0,255).astype(np.uint8)

STAIR_POLY=[(232,62),(290,30),(420,92),(415,135),(362,188),(236,132)]
def reverse_steps(e,c=(326,110)):
    """mirror the stair block across a line parallel to the step edges so the risers face the other way"""
    H,W=e.shape[:2]; yy,xx=np.mgrid[0:H,0:W].astype(float)
    d=np.array([1,0.5]); d/=np.hypot(*d)
    vx,vy=xx-c[0],yy-c[1]; t=vx*d[0]+vy*d[1]
    sx=c[0]+2*t*d[0]-vx; sy=c[1]+2*t*d[1]-vy
    src=np.stack([map_coordinates(e[...,k],[sy,sx],order=1,mode='nearest') for k in range(3)],-1)
    m=edit4.soft_poly(H,W,STAIR_POLY,5)
    ms=map_coordinates(m,[sy,sx],order=1,mode='constant')
    mm=(m*ms)[...,None]
    out=e.copy(); out[...,:3]=e[...,:3]*(1-mm)+src*mm
    return out

# stairs from the original entrance, mirrored left-right: they sit below the pillar and descend toward the viewer
STAIR_SRC=[(252,132),(340,95),(380,125),(450,155),(400,183),(300,233),(258,240)]
def fill_floor(e,img):
    H,W=e.shape[:2]; a=img[...,3]>0
    m=edit4.soft_poly(H,W,STAIR_POLY,6)
    src=np.roll(np.roll(e,-60,0),120,1); ok=np.roll(np.roll(a,-60,0),120,1)
    mm=(m*ok)[...,None]; out=e.copy(); out[...,:3]=e[...,:3]*(1-mm)+src[...,:3]*mm
    return out
def paste_stairs(e,img):
    O=_orig3()[:, ::-1]; H,W=e.shape[:2]
    poly=[(W-1-x,y) for x,y in STAIR_SRC]
    m=edit4.soft_poly(H,W,poly,7)*(O[...,3]>0)*(img[...,3]>0)
    # reverse the riser side: rotate the stair block 180 deg about its centre (step edges keep their direction,
    # but the dark riser bands move to the far side of each tread -> stairs read as going down, away from the viewer)
    pm=edit4.soft_poly(H,W,poly,1); yy,xx=np.mgrid[0:H,0:W]
    cy,cx=(pm*yy).sum()/pm.sum(),(pm*xx).sum()/pm.sum()
    sy=np.clip(np.round(2*cy-yy).astype(int),0,H-1); sx=np.clip(np.round(2*cx-xx).astype(int),0,W-1)
    O=O[sy,sx]; m=m*pm[sy,sx]*(O[...,3]>0)
    rng=np.random.default_rng(11); nz=gaussian_filter(rng.standard_normal((H,W)),4); nz/=nz.std()
    me=edit4.soft_poly(H,W,poly,12)
    m=m*np.clip((me-0.5+0.2*nz)*3+0.5,0,1)
    m=gaussian_filter(m,1.5)*(img[...,3]>0)
    sh=np.clip(gaussian_filter(edit4.soft_poly(H,W,poly,1),6)-m,0,1)*(img[...,3]>0)
    out=e.copy(); out[...,:3]*=(1-0.25*sh)[...,None]
    out[...,:3]=out[...,:3]*(1-m[...,None])+O[...,:3]*m[...,None]
    return out

def stair_depth(e,img,A=(59,155),B=(169,95),C=(251,240),D=(257,132),hmax=52):
    """depth cues for stairs going DOWN from the A-C end toward the B-D end (pillar side):
    darker toward the bottom, a side wall on the far (upper-left) side that grows taller, bright floor lips"""
    H,W=e.shape[:2]; yy,xx=np.mgrid[0:H,0:W].astype(float); a=img[...,3]>0
    out=e.copy()
    poly=[A,B,D,C]; band=edit4.soft_poly(H,W,poly,4)
    # progress along the descent (0 at top A-C, 1 at bottom B-D)
    m0=(np.array(A)+np.array(C))/2; m1=(np.array(B)+np.array(D))/2; v=m1-m0; L2=v@v
    t=np.clip(((xx-m0[0])*v[0]+(yy-m0[1])*v[1])/L2,0,1)
    out[...,:3]*=(1-0.38*t*band)[...,None]
    # far side wall hanging below edge A-B, height grows with t
    ab=np.array(B,float)-np.array(A,float); s_=np.clip(((xx-A[0])*ab[0]+(yy-A[1])*ab[1])/(ab@ab),0,1)
    ly=A[1]+s_*ab[1]; lx=A[0]+s_*ab[0]
    rng=np.random.default_rng(3); nzw=gaussian_filter(rng.standard_normal((H,W)),2.5); nzw/=nzw.std()
    dy=yy-ly+1.6*nzw; h=hmax*s_**0.9*(1+0.08*nzw)
    inx=(np.abs(xx-lx)<1.5*W)&(s_>0)&(s_<1)
    wall=np.clip(dy/1.5,0,1)*np.clip((h-dy)/2,0,1)*inx*a
    wall=gaussian_filter(wall,0.8)
    stone=_orig3()[...,:3][np.clip(yy.astype(int)+40,0,H-1),np.clip(xx.astype(int)//2+95,0,W-1)]*0.62
    shade=(0.75+0.35*np.clip(dy/np.maximum(h,1),0,1))[...,None]   # lighter toward the bottom of the face (bounce)
    out[...,:3]=out[...,:3]*(1-wall[...,None])+stone*shade*wall[...,None]
    # bright lip on the floor edge above the wall and along the near side C-D
    for P,Q in ((A,B),):
        P=np.array(P,float); Q=np.array(Q,float); d=Q-P
        u=np.clip(((xx-P[0])*d[0]+(yy-P[1])*d[1])/(d@d),0,1)
        dist=np.hypot(xx-(P[0]+u*d[0]),yy-(P[1]+u*d[1]))
        lip=np.exp(-(dist/1.0)**2)*a*np.clip(u/0.15,0,1)*(u<0.98)*(yy<P[1]+u*d[1]+0.5)*0.6
        out[...,:3]=out[...,:3]*(1-0.5*lip[...,None])+np.array([235,215,185.])*0.5*lip[...,None]
    return out

def lowland_exit(e,img,T,A=(59,155),B=(169,95),C=(251,240),D=(257,132)):
    """past the bottom step the trench opens onto the lowland: blend to plain lowland ground,
    and soften the stair/floor borders with ragged sand"""
    H,W=e.shape[:2]; yy,xx=np.mgrid[0:H,0:W].astype(float); a=img[...,3]>0
    m0=(np.array(A)+np.array(C))/2; m1=(np.array(B)+np.array(D))/2; v=m1-m0
    t=((xx-m0[0])*v[0]+(yy-m0[1])*v[1])/(v@v)
    rng=np.random.default_rng(5); nz=gaussian_filter(rng.standard_normal((H,W)),7); nz/=nz.std()
    w=np.clip((t-0.90+0.08*nz)/0.30,0,1); w=w*w*(3-2*w)
    ac=np.array(C,float)-np.array(A,float); uu=((xx-A[0])*ac[0]+(yy-A[1])*ac[1])/(ac@ac)
    lo,hi=(-0.05,1.05) if PRE=='S' else (-0.7,1.7)
    lat=np.clip((uu-lo+0.06*nz)/0.15,0,1)*np.clip((hi-uu+0.06*nz)/0.15,0,1)
    w=w*lat
    low=edit5.base_layer(T)
    out=e.copy(); out[...,:3]=e[...,:3]*(1-w[...,None])+low[...,:3]*w[...,None]
    # sand drift on the lower steps (where they meet the lowland)
    band=edit4.soft_poly(H,W,[A,B,D,C],6)
    drift=np.clip((t-0.65+0.10*nz)/0.35,0,1)*band*0.45
    out[...,:3]=out[...,:3]*(1-drift[...,None])+low[...,:3]*drift[...,None]
    # soft shadow line where the high floor meets the first step
    ac=np.array(C,float)-np.array(A,float); u=np.clip(((xx-A[0])*ac[0]+(yy-A[1])*ac[1])/(ac@ac),0,1)
    dist=np.hypot(xx-(A[0]+u*ac[0]),yy-(A[1]+u*ac[1]))
    side=((xx-A[0])*(-ac[1])+(yy-A[1])*ac[0])   # >0 toward the stairs?
    out[...,:3]*=(1-0.08*np.exp(-(dist/5)**2))[...,None]
    return out

def stair_shade(e,img,A=(59,155),B=(169,95),C=(251,240),D=(257,132)):
    """stairs only: no side wall; just a gentle darkening toward the bottom step"""
    H,W=e.shape[:2]; yy,xx=np.mgrid[0:H,0:W].astype(float)
    band=edit4.soft_poly(H,W,[A,B,D,C],8)
    m0=(np.array(A)+np.array(C))/2; m1=(np.array(B)+np.array(D))/2; v=m1-m0
    t=np.clip(((xx-m0[0])*v[0]+(yy-m0[1])*v[1])/(v@v),0,1)
    out=e.copy(); out[...,:3]*=(1-0.25*t*band)[...,None]
    return out

PILLAR_POLY=[(190,152),(203,140),(226,142),(240,156),(242,252),(205,252),(192,228),(177,206),(177,165)]
def _pillar_img(scale):
    O=_orig3(); H,W=O.shape[:2]
    m=edit4.soft_poly(H,W,PILLAR_POLY,0.8)*(O[...,3]>0)
    x0,y0,x1,y1=170,135,246,246      # crop; base (ground contact) at bottom centre
    rgba=np.dstack([O[y0:y1,x0:x1,:3],m[y0:y1,x0:x1]*255]).astype(np.uint8)
    from PIL import Image
    im=Image.fromarray(rgba,'RGBA'); im=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.LANCZOS)
    return np.asarray(im).astype(float)
def pillar_rows(e,img,A=(59,155),B=(169,95),C=(251,240),scale=0.62,ts=(0.10,0.42,0.74)):
    H,W=e.shape[:2]; a=img[...,3]>0
    P=_pillar_img(scale); ph,pw=P.shape[:2]
    A=np.array(A,float); B=np.array(B,float); C=np.array(C,float); d=B-A
    C2=C-0.12*(C-A)
    bases=[A+t*d+np.array([14,6]) for t in ts]+[C2+t*d for t in ts]
    bases.sort(key=lambda b:b[1])
    out=e.copy(); yy,xx=np.mgrid[0:H,0:W].astype(float)
    for bx,by in bases:
        # contact shadow
        sh=np.exp(-(((xx-bx-4)/14)**2+((yy-by+2)/6)**2))*a
        out[...,:3]*=(1-0.45*sh)[...,None]
        x0=int(round(bx-pw/2)); y0=int(round(by-ph))
        for yy0 in range(ph):
            ty=y0+yy0
            if ty<0 or ty>=H: continue
            for_x=slice(max(0,x0),min(W,x0+pw)); sx=slice(for_x.start-x0,for_x.stop-x0)
            al=(P[yy0,sx,3]/255.0)*a[ty,for_x]
            out[ty,for_x,:3]=out[ty,for_x,:3]*(1-al[:,None])+P[yy0,sx,:3]*al[:,None]
    return out

def clean_ghost(e,img,T):
    H,W=e.shape[:2]
    poly,dy,dx=PILLARS[1]; fp=[(x,255-y) for x,y in poly]
    m=gaussian_filter(edit4.soft_poly(H,W,fp,2),8)*1.6; m=np.clip(m,0,1)
    low=edit5.base_layer(T); out=e.copy()
    out[...,:3]=e[...,:3]*(1-m[...,None])+low[...,:3]*m[...,None]
    return out
