exec(open('solve4.py').read().split("F=sorted(d)")[0])
F=sorted(d); us=d[F[-1]]; tgt=chk[F[-1]][3]
nu=us['56']; base={k:v for k,v in us.items() if k!='56'}
ids=sorted(base,key=int)
for s in range(1,120):
    if str(s) in base: continue
    # hash = prefix (units < s) , new unit, suffix
    pre=[u for u in ids if int(u)<s]; suf=[u for u in ids if int(u)>s]
    def h(seq,h0=0):
        h=h0
        for x in seq: h=(h*31+x['hp'])%M; h=(h*31+((x['x']&0xffff)|((x['y']&0xffff)<<16)))%M; h=(h*31+x['type'])%M
        return h
    hp=h([base[u] for u in pre]); k=len(suf)
    hs=h([base[u] for u in suf]); p=pow(31,3*k,M)
    # tgt = (H(pre+new) * p + hs) ; H(pre+new) = ((hp*31+HP)*31+POS)*31+T
    need=(tgt-hs)%M*pow(p,-1,M)%M
    for T in (nu['type'],):
      for HP in (nu['hp'],):
        r=(need-T)%M*pow(31,-1,M)%M
        POS=(r-(hp*31+HP)*31)%M
        x=POS&0xffff; y=POS>>16
        if abs(x-nu['x'])<1500 and abs(y-nu['y'])<1500: print('slot',s,'x',x,'y',y)
