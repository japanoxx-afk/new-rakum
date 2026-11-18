import sys;sys.path.insert(0,'/home/claude/re/ramp9')
from mrender import *
def top2(rkm,jtl,brg,out,ids=((28,32,-360),(88,30,-260))):
    ims=[]
    for ax,ay,dx in ids:
        b=(ax*32+dx,ay*32-200,ax*32+dx+900,ay*32+400)
        im,o,t,T=render(rkm,jtl,box=b); place_subs(im,o,T,brg,b); ims.append(im)
    c=Image.new('RGB',(1806,600),(255,0,0))
    for k,im in enumerate(ims): c.paste(im,(k*906,0))
    c.save(out)
if __name__=='__main__':
    ts=int(sys.argv[1]); n=['East','West','Savage','Dungeon'][ts]; p=n[0]
    jt=sys.argv[2] if len(sys.argv)>2 else '/home/claude/mod/Data/tile/%s.jtl'%n
    br=sys.argv[3] if len(sys.argv)>3 else '/home/claude/mod/Data/tile/%s_Bridge.brg'%p
    top2('/tmp/flip_%d.rkm'%ts if ts else '/tmp/flip2.rkm',jt,br,'/tmp/top_%d.png'%ts)
