import json, os, struct, sys, glob
# RK_REPO = 저장소 폴더 (기본: 이 파일의 두 단계 위), RK_REPLAY = 분석할 리플레이(.rkr)
sys.path.insert(0, os.environ.get('RK_REPO', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')))
import replay_model as m
rp=m.load(os.environ['RK_REPLAY']); dd=m.ingame_data(rp)
chk={c[0]:struct.unpack('<IIIII',c[2]) for c in dd['records'] if c[1]==0xFD}
d={int(k):v for k,v in json.load(open('hashdump.json')).items()}
M=1<<32
def H(us):
    h=0
    for u in sorted(us,key=int):
        x=us[u]; h=(h*31+x['hp'])%M; h=(h*31+((x['x']&0xffff)|((x['y']&0xffff)<<16)))%M; h=(h*31+x['type'])%M
    return h
F=sorted(d)
for f in F: print(f, len(d[f]), hex(H(d[f])), hex(chk[f][3]), chk[f][4])
a,b=d[F[-2]],d[F[-1]]
for u in sorted(set(a)|set(b),key=int):
    if a.get(u)!=b.get(u): print(u,a.get(u),'->',b.get(u))
us=d[F[-1]]; tgt=chk[F[-1]][3]; delta=(tgt-H(us))%M
ids=sorted(us,key=int); n=len(ids)
for i,u in enumerate(ids):
    c=pow(31,3*(n-1-i),M); D=delta*pow(c,-1,M)%M
    inv31=pow(31,-1,M)
    for dhp in range(-5,6):
      for dt in range(-3,4):
        r=(D-961*dhp-dt)%M*inv31%M      # = dx + 65536*dy
        for dy in range(-600,601):
            dx=(r-65536*dy)%M; dx = dx if dx<1<<31 else dx-M
            if abs(dx)<=600: print('unit',u,us[u],'dx',dx,'dy',dy,'dhp',dhp,'dt',dt)
