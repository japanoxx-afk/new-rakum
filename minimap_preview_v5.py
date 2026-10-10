"""V5 trial: enqueue only gold/water sprites in the existing world draw list."""
from pathlib import Path
import minimap_preview_v4 as v4
import minimap_preview_v2 as v2

HOOK=0x3e60d
ENTRY=v4.CODE+0x1800
BITMAP=v4.GRID+0x1800  # outside V4's maximum 35x128 raw coverage footprint
RESET=v4.CODE+0x1700
BEFORE=bytes.fromhex('0fbf45fc69c0080200000fbf4df8')

def build(source):
    source=v2.terrain.transform(source,False)
    data=bytearray(v4.build(source))
    if source[HOOK:HOOK+len(BEFORE)]!=BEFORE:raise ValueError('Unsupported decoration list path')
    code=v2.asm(f'''
        pushfd
        pushad
        movsx eax,byte ptr [0xb412cd]
        cmp eax,1
        ja out
        imul eax,eax,0x84080
        movsx ecx,word ptr [ebp-4]
        cmp ecx,520
        jae out
        imul ecx,ecx,0x410
        add eax,ecx
        movsx ecx,word ptr [ebp-8]
        cmp ecx,520
        jae out
        movzx esi,word ptr [eax+ecx*2+0xfe5e0a]
        test esi,esi
        jz out
        cmp esi,0x5dc
        jae out
        mov edi,esi
        shl edi,5
        add edi,0x766970
        cmp word ptr [edi+6],0x5dc
        je out
        cmp word ptr [edi+0xe],0
        jne out
        cmp byte ptr [esi+{BITMAP}],0
        jne out
        cmp byte ptr [edi+0x12],0x63
        je enqueue
        cmp byte ptr [edi+0x12],0x53
        jne out
        cmp dword ptr [edi+0x1c],0
        jle out
    enqueue:
        movsx eax,word ptr [ebp-4]
        imul eax,eax,520
        movsx ecx,word ptr [ebp-8]
        movzx eax,byte ptr [eax+ecx+0x915d50]
        and eax,15
        cmp eax,15
        je force
        movzx ecx,byte ptr [0xb412cc]
        movzx eax,word ptr [ecx*2+0x4f02a0]
        test word ptr [edi+0x10],ax
        jnz out
    force:
        mov byte ptr [esi+{BITMAP}],1
        movsx eax,word ptr [ebp-4]
        imul eax,eax,520
        movsx ecx,word ptr [ebp-8]
        test byte ptr [eax+ecx+0xb4198a],2
        jz lower
        mov ax,word ptr [0xb41164]
        mov word ptr [edi+0xe],ax
        mov al,byte ptr [0xb4115c]
        mov byte ptr [edi+0xc],al
        mov word ptr [0xb41164],si
        mov byte ptr [0xb4115c],1
        jmp out
    lower:
        mov ax,word ptr [0xb41168]
        mov word ptr [edi+0xe],ax
        mov al,byte ptr [0xb4115e]
        mov byte ptr [edi+0xc],al
        mov word ptr [0xb41168],si
        mov byte ptr [0xb4115e],1
    out:
        popad
        popfd
        movsx eax,word ptr [ebp-4]
        imul eax,eax,520
        movsx ecx,word ptr [ebp-8]
        jmp 0x43e61b
    ''',ENTRY)
    if len(code)>0x700:raise ValueError('V5 code overflow')
    original_reset=bytes.fromhex('558bec83ec4c')
    if source[0x3e520:0x3e526]!=original_reset:raise ValueError('Unknown draw-list entry')
    reset=v2.asm(f'pushfd; pushad; cld; xor eax,eax; mov edi,{BITMAP}; mov ecx,375; rep stosd; popad; popfd; push ebp; mov ebp,esp; sub esp,0x4c; jmp 0x43e526',RESET)
    data[v4.RAW+0x1700:v4.RAW+0x1700+len(reset)]=reset
    data[v4.RAW+0x1800:v4.RAW+0x1800+len(code)]=code
    data[v4.RAW+0x1f40:v4.RAW+0x1f48]=b'RMMAPV5!'
    data[HOOK:HOOK+len(BEFORE)]=v2.asm(f'jmp {ENTRY}',0x400000+HOOK)+b'\x90'*(len(BEFORE)-5)
    data[0x3e520:0x3e526]=v2.asm(f'jmp {RESET}',0x43e520)+b'\x90'
    return bytes(data)

def restore(data):
    if len(data)!=v4.RAW+0x6000 or data[v4.RAW+0x1f40:v4.RAW+0x1f48]!=b'RMMAPV5!':raise ValueError('Not complete V5 trial')
    baseline=bytearray(data)
    baseline[HOOK:HOOK+len(BEFORE)]=BEFORE
    baseline[0x3e520:0x3e526]=bytes.fromhex('558bec83ec4c')
    baseline[v4.RAW+0x1700:v4.RAW+0x1f00]=b'\0'*0x800
    baseline[v4.RAW+0x1f40:v4.RAW+0x1f48]=b'\0'*8
    source=v4.restore(bytes(baseline))
    if build(source)!=data:raise ValueError('Unknown V5 modifications')
    return source

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    data=build(args.source.read_bytes())
    with args.output.open('xb') as stream:stream.write(data)
