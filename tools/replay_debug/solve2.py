import json
d={int(k):v for k,v in json.load(open('hashdump.json')).items()}
M=1<<32
def H(us):
    h=0
    for u in sorted(us,key=int):
        x=us[u]; h=(h*31+x['hp'])%M; h=(h*31+((x['x']&0xffff)|((x['y']&0xffff)<<16)))%M; h=(h*31+x['type'])%M
    return h
want={8515:0x3887512a,8520:0xdede2512,8525:0xac8c02cc}
for f in sorted(d): print(f, hex(H(d[f])), hex(want[f]))
us=d[8525]; delta=(want[8525]-H(us))%M
ids=sorted(us,key=int); n=len(ids); inv961=pow(961,-1,M)
for i,u in enumerate(ids):
    c=pow(31,3*(n-1-i),M); D=delta*pow(c,-1,M)%M
    for dy in range(-64,65):
      for dx in range(-64,65):
        for dt in range(-3,4):
          r=(D-31*((dx+65536*dy)%M)-dt)%M*inv961%M
          dhp=r if r<1<<31 else r-M
          if abs(dhp)<=3000: print('unit',u,us[u],'dhp',dhp,'dx',dx,'dy',dy,'dt',dt)
