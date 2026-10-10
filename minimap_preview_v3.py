"""Trial V3: retain native smooth fog boundaries, halve canopy opacity only."""
import struct
from pathlib import Path
import pefile
import minimap_preview_v2 as v2

def build(source):
    source=v2.terrain.transform(source,False)
    data=bytearray(v2.build(source))
    high=source[0xca690]==0xe9
    original=source[0xcb0e2:0xcb0e8]
    native='call 0x4ebf10' if high else 'call dword ptr [0x4ec484]'
    scratch=v2.STATE+0x1000
    wrapper=v2.asm(f'''
        pushfd
        pushad
        sub esp,16
        mov esi,dword ptr [esp+56]
        mov edi,dword ptr [esp+60]
        test esi,esi
        jl end
        test edi,edi
        jl end
        movzx eax,word ptr [0x106a5e0]
        sub eax,esi
        jle end
        cmp eax,dword ptr [esp+64]
        jle width
        mov eax,dword ptr [esp+64]
    width:
        test eax,eax
        jle end
        cmp eax,32
        jg end
        mov dword ptr [esp],eax
        movzx eax,word ptr [0x106a5e2]
        sub eax,edi
        jle end
        cmp eax,dword ptr [esp+68]
        jle height
        mov eax,dword ptr [esp+68]
    height:
        test eax,eax
        jle end
        cmp eax,32
        jg end
        mov dword ptr [esp+4],eax
        xor ebx,ebx
    save_row:
        mov eax,dword ptr [0x4ec438]
        mov edx,dword ptr [eax+0x74]
        lea ecx,[edi+ebx]
        mov edx,dword ptr [edx+ecx*4]
        add edx,dword ptr [eax+0x70]
        lea edx,[edx+esi*2]
        mov eax,ebx
        shl eax,6
        add eax,{scratch}
        mov ecx,dword ptr [esp]
    save_pixel:
        mov bp,word ptr [edx]
        mov word ptr [eax],bp
        add edx,2
        add eax,2
        loop save_pixel
        inc ebx
        cmp ebx,dword ptr [esp+4]
        jl save_row
        push dword ptr [esp+72]
        push dword ptr [esp+72]
        push dword ptr [esp+72]
        push dword ptr [esp+72]
        push dword ptr [esp+72]
        {native}
        xor ebx,ebx
    blend_row:
        mov eax,dword ptr [0x4ec438]
        mov ebp,dword ptr [eax+0x38]
        mov edx,dword ptr [eax+0x74]
        lea ecx,[edi+ebx]
        mov edx,dword ptr [edx+ecx*4]
        add edx,dword ptr [eax+0x70]
        lea edx,[edx+esi*2]
        mov eax,ebx
        shl eax,6
        add eax,{scratch}
        mov dword ptr [esp+8],eax
        mov ecx,dword ptr [esp]
    blend_pixel:
        movzx eax,word ptr [edx]
        mov dword ptr [esp+12],eax
        mov eax,dword ptr [esp+8]
        movzx eax,word ptr [eax]
        cmp eax,dword ptr [esp+12]
        je unchanged
        mov eax,dword ptr [esp+12]
        and eax,ebp
        shr eax,1
        mov dword ptr [esp+12],eax
        mov eax,dword ptr [esp+8]
        movzx eax,word ptr [eax]
        and eax,ebp
        shr eax,1
        add eax,dword ptr [esp+12]
        mov word ptr [edx],ax
    unchanged:
        add edx,2
        add dword ptr [esp+8],2
        loop blend_pixel
        inc ebx
        cmp ebx,dword ptr [esp+4]
        jl blend_row
    end:
        add esp,16
        popad
        popfd
        ret 20
    ''',v2.CODE+0x500)
    if len(wrapper)>0x300:raise ValueError('Code overlaps restoration metadata')
    data[v2.RAW+0x500:v2.RAW+0x500+len(wrapper)]=wrapper
    data[0xcb0e2:0xcb0e8]=v2.asm(f'call {v2.CODE+0x500}',0x4cb0e2)+b'\x90'
    data[v2.RAW+0xb20:v2.RAW+0xb26]=original
    data[v2.RAW+0xb26:v2.RAW+0xb2e]=b'RMMAPV3!'
    data.extend(b'\0'*0x1000)
    pe=pefile.PE(data=data)
    section=pe.sections[-1]
    struct.pack_into('<I',data,section.get_field_absolute_offset('Misc_VirtualSize'),0x2000)
    struct.pack_into('<I',data,section.get_field_absolute_offset('SizeOfRawData'),0x2000)
    struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),0xc72000)
    return bytes(data)

def restore(data):
    if len(data)!=v2.RAW+0x3000 or data[v2.RAW+0xb26:v2.RAW+0xb2e]!=b'RMMAPV3!':
        raise ValueError('Not a complete V3 trial')
    source=bytearray(data[:v2.SIZE])
    source[:0x300]=data[v2.RAW+0x800:v2.RAW+0xb00]
    source[v2.terrain.OFFSET:v2.terrain.OFFSET+5]=v2.terrain.BEFORE
    source[0x673c0:0x673c9]=bytes.fromhex('558bec83ec68535657')
    source[0x6903c:0x69046]=bytes.fromhex('66a1de12b400668945f8')
    source[0xca75a:0xca75c]=b'\xeb\x87'
    source[0xcb026:0xcb02c]=data[v2.RAW+0xb08:v2.RAW+0xb0e]
    source[0xcb150:0xcb156]=data[v2.RAW+0xb0e:v2.RAW+0xb14]
    source[0xcb0e2:0xcb0e8]=data[v2.RAW+0xb20:v2.RAW+0xb26]
    source=bytes(source)
    if build(source)!=data:raise ValueError('Unknown V3 changes')
    return source

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('source',type=Path);a.add_argument('output',type=Path)
    args=a.parse_args()
    result=build(args.source.read_bytes())
    with args.output.open('xb') as f:f.write(result)
