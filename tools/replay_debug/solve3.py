exec(open('solve2.py').read().split("us=d[8525]")[0].replace("for f in sorted(d): print","for f in []: print"))
us=d[8525]; prev=d[8520]
delta=(want[8525]-H(us))%M
ids=sorted(us,key=int); n=len(ids)
coef={u:pow(31,3*(n-1-i),M) for i,u in enumerate(ids)}
R=48
table={}
for u in ids:
    c=coef[u]
    for dy in range(-R,R+1):
        for dx in range(-R,R+1):
            if dx==dy==0: continue
            table.setdefault(c*31*((dx+65536*dy)%M)%M,[]).append((u,dx,dy))
moving=[u for u in ids if prev.get(u) and (prev[u]['x'],prev[u]['y'])!=(us[u]['x'],us[u]['y'])]
print('moving', moving)
hits=set()
for v,lst in table.items():
    w=(delta-v)%M
    for a in lst:
        for b in table.get(w,[]):
            if a[0]<b[0]: hits.add((a,b))
for a,b in sorted(hits): print(a, us[a[0]], b, us[b[0]])
