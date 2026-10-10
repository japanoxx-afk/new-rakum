"""Offline V4: continuous, filtered fog coverage from native current-vision masks.

Reads the game's render mask only. Does not reveal simulation/exploration data.
"""
import struct
import pefile
from pathlib import Path
import minimap_preview_v2 as v2

CODE=v2.CODE+0x2000
GRID=CODE+0x2000
RAW=v2.RAW+0x2000

def build(source):
    source=v2.terrain.transform(source,False)
    result=bytearray(v2.build(source))
    high=source[0xca690]==0xe9
    before=bytes.fromhex('558bec83ec40')
    if source[0xcaf40:0xcaf46]!=before:raise ValueError('Unsupported fog entry')
    pe=pefile.PE(data=source)
    header=pe.sections[-1].get_file_offset()+40
    if any(source[header:header+160]):raise ValueError('PE headers occupied')
    # Native Draw_WarFog uses high nibble when present, otherwise low nibble.
    # Each nibble is the four-corner fog mask; F means a fully covered tile.
    coverage=bytes(((n>>4) or (n&15)).bit_count()*32 for n in range(256))
    gaussian=[]
    for yy,wy in enumerate((1,2,1)):
        for xx,wx in enumerate((1,2,1)):
            gaussian.append(f'movzx eax,byte ptr [ecx+{GRID+yy*128+xx}]')
            if wy*wx>1:gaussian.append(f'shl eax,{1 if wy*wx==2 else 2}')
            gaussian.append('add edx,eax')
    height_fix='' if high else 'sub eax,152; and eax,0xffffffe0'
    code=v2.asm(f'''
        pushfd
        pushad
        sub esp,80
        movzx eax,word ptr [0x106a5e0]
        test eax,eax
        jle finish
        cmp eax,2048
        jg finish
        mov dword ptr [esp],eax
        add eax,31
        shr eax,5
        mov dword ptr [esp+8],eax
        movzx eax,word ptr [0x106a5e2]
        {height_fix}
        test eax,eax
        jle finish
        cmp eax,1024
        jg finish
        mov dword ptr [esp+4],eax
        add eax,31
        shr eax,5
        mov dword ptr [esp+12],eax
        movzx eax,byte ptr [0xb412cd]
        cmp eax,1
        jg finish
        movsx edx,word ptr [eax*2+0xb412d8]
        mov dword ptr [esp+16],edx
        movsx edx,word ptr [eax*2+0xb412da]
        mov dword ptr [esp+20],edx
        mov eax,dword ptr [0x4ec438]
        mov edx,dword ptr [eax+0x38]
        mov dword ptr [esp+76],edx
        and edx,0xffff
        mov dword ptr [esp+68],0xf81f
        mov dword ptr [esp+72],0x7e0
        cmp edx,0xf7de
        je raw_start
        cmp edx,0x7bde
        jne finish
        mov dword ptr [esp+68],0x7c1f
        mov dword ptr [esp+72],0x3e0
    raw_start:
        xor esi,esi
    raw_y:
        xor edi,edi
    raw_x:
        mov ebx,128
        mov eax,dword ptr [esp+20]
        lea eax,[eax+esi-1]
        cmp eax,520
        jae raw_write
        imul eax,eax,520
        mov edx,dword ptr [esp+16]
        lea edx,[edx+edi-1]
        cmp edx,520
        jae raw_write
        add eax,edx
        movzx eax,byte ptr [eax+0x957d90]
        movzx ebx,byte ptr [eax+{CODE+0x1000}]
    raw_write:
        mov edx,esi
        shl edx,7
        add edx,edi
        mov byte ptr [edx+{GRID}],bl
        inc edi
        mov eax,dword ptr [esp+8]
        add eax,3
        cmp edi,eax
        jl raw_x
        inc esi
        mov eax,dword ptr [esp+12]
        add eax,3
        cmp esi,eax
        jl raw_y
        xor esi,esi
    filter_y:
        xor edi,edi
    filter_x:
        mov ecx,esi
        shl ecx,7
        add ecx,edi
        xor edx,edx
        {'; '.join(gaussian)}
        shr edx,4
        mov byte ptr [ecx+{GRID+0x2000}],dl
        inc edi
        cmp edi,dword ptr [esp+8]
        jle filter_x
        inc esi
        cmp esi,dword ptr [esp+12]
        jle filter_y
        xor esi,esi
    frame_y:
        mov eax,dword ptr [0x4ec438]
        mov edi,dword ptr [eax+0x74]
        mov edi,dword ptr [edi+esi*4]
        add edi,dword ptr [eax+0x70]
        mov eax,esi
        and eax,31
        mov dword ptr [esp+24],eax
        mov ebp,esi
        shr ebp,5
        shl ebp,7
        add ebp,{GRID+0x2000}
        mov dword ptr [esp+28],0
    tile_x:
        mov ecx,dword ptr [esp+28]
        movzx eax,byte ptr [ebp+ecx]
        movzx edx,byte ptr [ebp+ecx+128]
        sub edx,eax
        imul edx,dword ptr [esp+24]
        shl eax,5
        add eax,edx
        mov dword ptr [esp+32],eax
        movzx eax,byte ptr [ebp+ecx+1]
        movzx edx,byte ptr [ebp+ecx+129]
        sub edx,eax
        imul edx,dword ptr [esp+24]
        shl eax,5
        add eax,edx
        sub eax,dword ptr [esp+32]
        mov ebx,eax
        mov edx,dword ptr [esp+32]
        shl edx,5
        shl ecx,5
        mov eax,dword ptr [esp]
        sub eax,ecx
        cmp eax,32
        jle pixel_count
        mov eax,32
    pixel_count:
        mov ecx,eax
        cmp edx,131072
        jne pixels
        test ebx,ebx
        jne pixels
    half_pixels:
        movzx eax,word ptr [edi]
        and eax,dword ptr [esp+76]
        shr eax,1
        mov word ptr [edi],ax
        add edi,2
        loop half_pixels
        jmp tile_next
    pixels:
        mov eax,edx
        shr eax,10
        test eax,eax
        jz pixel_next
        neg eax
        add eax,256
        mov dword ptr [esp+52],eax
        movzx eax,word ptr [edi]
        mov dword ptr [esp+56],eax
        and eax,dword ptr [esp+68]
        and eax,0xffffffe0
        imul eax,dword ptr [esp+52]
        shr eax,8
        and eax,dword ptr [esp+68]
        and eax,0xffffffe0
        mov dword ptr [esp+60],eax
        mov eax,dword ptr [esp+56]
        and eax,dword ptr [esp+72]
        imul eax,dword ptr [esp+52]
        shr eax,8
        and eax,dword ptr [esp+72]
        or eax,dword ptr [esp+60]
        mov dword ptr [esp+64],eax
        mov eax,dword ptr [esp+56]
        and eax,31
        imul eax,dword ptr [esp+52]
        shr eax,8
        and eax,31
        or eax,dword ptr [esp+64]
        mov word ptr [edi],ax
    pixel_next:
        add edx,ebx
        add edi,2
        dec ecx
        jnz pixels
    tile_next:
        inc dword ptr [esp+28]
        mov eax,dword ptr [esp+28]
        cmp eax,dword ptr [esp+8]
        jl tile_x
        inc esi
        cmp esi,dword ptr [esp+4]
        jl frame_y
    finish:
        add esp,80
        popad
        popfd
        ret
    ''',CODE)
    if len(code)>0x1000:raise ValueError('Fog code overflow')
    result[0xcaf40:0xcaf46]=v2.asm(f'jmp {CODE}',0x4caf40)+b'\x90'
    result.extend(code+b'\0'*(0x1000-len(code)))
    result.extend(coverage+b'\0'*(0xf00))
    result.extend(b'\0'*0x4000)
    result[RAW+0x1f00:RAW+0x1f08]=b'RMMAPV4!'
    struct.pack_into('<H',result,pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'),8)
    struct.pack_into('<I',result,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),0xc77000)
    for i,(name,rva,raw,size,flags) in enumerate([(b'.fogcode',CODE-0x400000,RAW,0x2000,0x60000020),(b'.foggrid',GRID-0x400000,RAW+0x2000,0x4000,0xc0000040)],2):
        struct.pack_into('<8sIIIIIIHHI',result,header+i*40,name,size,rva,size,raw,0,0,0,0,flags)
    return bytes(result)

def restore(data):
    if len(data)!=RAW+0x6000 or data[RAW+0x1f00:RAW+0x1f08]!=b'RMMAPV4!':raise ValueError('Not a complete V4 trial')
    source=bytearray(data[:v2.SIZE])
    source[:0x300]=data[v2.RAW+0x800:v2.RAW+0xb00]
    source[0x300:0x340]=b'\0'*0x40
    source[v2.terrain.OFFSET:v2.terrain.OFFSET+5]=v2.terrain.BEFORE
    source[0x673c0:0x673c9]=bytes.fromhex('558bec83ec68535657')
    source[0x6903c:0x69046]=bytes.fromhex('66a1de12b400668945f8')
    source[0xca75a:0xca75c]=b'\xeb\x87'
    source[0xcb026:0xcb02c]=data[v2.RAW+0xb08:v2.RAW+0xb0e]
    source[0xcb150:0xcb156]=data[v2.RAW+0xb0e:v2.RAW+0xb14]
    source[0xcaf40:0xcaf46]=bytes.fromhex('558bec83ec40')
    source=bytes(source)
    if build(source)!=data:raise ValueError('Unknown V4 modifications')
    return source

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('source',type=Path);a.add_argument('output',type=Path)
    args=a.parse_args()
    result=build(args.source.read_bytes())
    with args.output.open('xb') as stream:stream.write(result)
