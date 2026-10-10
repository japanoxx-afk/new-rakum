"""Offline trial: cached resource minimap markers and terrain-only fog presentation.

No simulation/visibility-table writes. Not integrated into the release launcher.
"""
import struct
from pathlib import Path
import pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import minimap_preview_patch as terrain

SIZE = 1069098
RAW = 0x106000
CODE = 0x106f000
STATE = CODE + 0x1000
KS = Ks(KS_ARCH_X86, KS_MODE_32)

def asm(source, address):
    return bytes(KS.asm(source, address)[0])

def build(source):
    source = terrain.transform(source, False)  # strict full-image validation
    result = bytearray(terrain.transform(source))
    pe = pefile.PE(data=source)
    if pe.OPTIONAL_HEADER.ImageBase != 0x400000 or pe.OPTIONAL_HEADER.SizeOfImage != 0xc6f000:
        raise ValueError('Unsupported PE layout')
    header = pe.sections[-1].get_file_offset()+40
    if any(source[header:header+80]): raise ValueError('Section headers occupied')
    code = bytearray(0x1000)
    # Determine supported viewport layout by the verified terrain draw prologue.
    highres = source[0xca690] == 0xe9
    sites = []
    def hook(offset, before, target, length=None):
        if source[offset:offset+len(before)] != before:
            raise ValueError(f'Unsupported instruction at {offset:x}')
        n = length or len(before)
        result[offset:offset+n] = asm(f'jmp {target}', 0x400000+offset)+b'\x90'*(n-5)
        sites.append((offset, before))
    # New map invalidates only our private resource-ID cache.
    reset = asm(f'pushfd; mov dword ptr [{STATE}],0; popfd; push ebp; mov ebp,esp; sub esp,0x68; push ebx; push esi; push edi; jmp 0x4673c9',CODE)
    code[:len(reset)] = reset
    hook(0x673c0, bytes.fromhex('558bec83ec68535657'), CODE)
    # At native resource drawing point, skip only the old gold drawing block.
    # The following enemy unit/building visibility checks are untouched.
    resource_code = asm(f'''
        pushfd
        pushad
        mov ebp,ecx
        cmp dword ptr [{STATE}],1
        je draw
        mov dword ptr [{STATE+4}],0
        mov esi,1
    scan:
        mov edi,esi
        shl edi,5
        add edi,0x766970
        cmp word ptr [edi+6],0x5dc
        je scan_next
        mov al,byte ptr [edi+0x12]
        cmp al,0x53
        je cache
        cmp al,0x63
        jne scan_next
    cache:
        mov edx,dword ptr [{STATE+4}]
        mov word ptr [edx*2+{STATE+16}],si
        inc dword ptr [{STATE+4}]
    scan_next:
        inc esi
        cmp esi,0x5dc
        jl scan
        mov dword ptr [{STATE}],1
    draw:
        xor esi,esi
    resource_loop:
        cmp esi,dword ptr [{STATE+4}]
        jge done
        movzx edi,word ptr [esi*2+{STATE+16}]
        shl edi,5
        add edi,0x766970
        cmp word ptr [edi+6],0x5dc
        je next
        movzx ebx,byte ptr [edi+0x12]
        cmp ebx,0x63
        je water
        cmp ebx,0x53
        jne next
        cmp dword ptr [edi+0x1c],0
        jle next
        mov eax,dword ptr [0x4ec438]
        mov eax,dword ptr [eax+0x38]
        and eax,0xffff
        mov ebx,0xffe0
        cmp eax,0xf7de
        je marker
        cmp eax,0x7bde
        jne next
        mov ebx,0x7fe0
        jmp marker
    water:
        mov ebx,0x1f
    marker:
        movsx eax,word ptr [edi+0x14]
        cmp eax,0
        jl next
        cmp eax,0x208
        jge next
        movsx edx,word ptr [ebp+eax*2+0x20254]
        movsx eax,word ptr [edi+0x16]
        cmp eax,0
        jl next
        cmp eax,0x208
        jge next
        movsx ecx,word ptr [ebp+eax*2+0x20664]
        cmp edx,0
        jl next
        cmp edx,125
        jg next
        cmp ecx,0
        jl next
        cmp ecx,125
        jg next
        shl ecx,8
        add ecx,ebp
        lea edx,[ecx+edx*2+0x1002c]
        mov ecx,3
    row:
        mov word ptr [edx],bx
        mov word ptr [edx+2],bx
        mov word ptr [edx+4],bx
        add edx,256
        loop row
    next:
        inc esi
        jmp resource_loop
    done:
        popad
        popfd
        jmp 0x4690a2
    ''',CODE+0x100)
    code[0x100:0x100+len(resource_code)] = resource_code
    hook(0x6903c,bytes.fromhex('66a1de12b400668945f8'),CODE+0x100)
    # Draw_Tile: render underlying terrain even for previously unexplored tiles.
    if source[0xca75a:0xca75c] != b'\xeb\x87': raise ValueError('Unsupported terrain skip')
    result[0xca75a:0xca75c] = b'\x90\x90'
    sites.append((0xca75a,b'\xeb\x87'))
    # Both full-black drawing branches become a half-bright framebuffer overlay.
    # No temporary fog-buffer changes; rectangle clipped to real viewport dimensions.
    fog = asm('''
        pushfd
        pushad
        mov esi,dword ptr [esp+40]
        mov edi,dword ptr [esp+44]
        test esi,esi
        jl end
        test edi,edi
        jl end
        movzx eax,word ptr [0x106a5e0]
        sub eax,esi
        jle end
        cmp eax,dword ptr [esp+48]
        jle width
        mov eax,dword ptr [esp+48]
    width:
        test eax,eax
        jle end
        mov ebp,eax
        movzx eax,word ptr [0x106a5e2]
        sub eax,edi
        jle end
        cmp eax,dword ptr [esp+52]
        jle height
        mov eax,dword ptr [esp+52]
    height:
        test eax,eax
        jle end
        mov ebx,eax
        mov eax,dword ptr [0x4ec438]
        mov edx,dword ptr [eax+0x38]
    rows:
        mov eax,dword ptr [0x4ec438]
        mov ecx,dword ptr [eax+0x74]
        mov ecx,dword ptr [ecx+edi*4]
        add ecx,dword ptr [eax+0x70]
        lea ecx,[ecx+esi*2]
        push ebx
        mov ebx,ebp
    pixels:
        movzx eax,word ptr [ecx]
        and eax,edx
        shr eax,1
        mov word ptr [ecx],ax
        add ecx,2
        dec ebx
        jnz pixels
        pop ebx
        inc edi
        dec ebx
        jnz rows
    end:
        popad
        popfd
        ret 20
    ''',CODE+0x400)
    code[0x400:0x400+len(fog)] = fog
    for offset in (0xcb026,0xcb150):
        before = source[offset:offset+6]
        expected = (b'\xe8' if highres else b'\xff\x15')
        if not before.startswith(expected): raise ValueError('Unsupported fog call')
        result[offset:offset+6] = asm(f'call {CODE+0x400}',0x400000+offset)+b'\x90'
        sites.append((offset,before))
    # Save exact original headers + hook bytes for reversible offline restoration.
    code[0x800:0x800+0x300] = source[:0x300]
    code[0xb00:0xb08] = b'RMMAPV2!'
    code[0xb08:0xb0e] = source[0xcb026:0xcb02c]
    code[0xb0e:0xb14] = source[0xcb150:0xcb156]
    result.extend(b'\0'*(RAW-len(result)))
    result.extend(code)
    result.extend(b'\0'*0x1000)
    struct.pack_into('<H',result,pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'),6)
    struct.pack_into('<I',result,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),0xc71000)
    for i,(name,rva,raw,flags) in enumerate([(b'.mmpcode',CODE-0x400000,RAW,0x60000020),(b'.mmpdata',STATE-0x400000,RAW+0x1000,0xc0000040)]):
        struct.pack_into('<8sIIIIIIHHI',result,header+i*40,name,0x1000,rva,0x1000,raw,0,0,0,0,flags)
    return bytes(result)

def restore(data):
    if len(data)!=RAW+0x2000 or data[RAW+0xb00:RAW+0xb08]!=b'RMMAPV2!':
        raise ValueError('Not a complete V2 trial')
    original=bytearray(data[:SIZE])
    original[:0x300]=data[RAW+0x800:RAW+0xb00]
    original[terrain.OFFSET:terrain.OFFSET+5]=terrain.BEFORE
    original[0x673c0:0x673c9]=bytes.fromhex('558bec83ec68535657')
    original[0x6903c:0x69046]=bytes.fromhex('66a1de12b400668945f8')
    original[0xca75a:0xca75c]=b'\xeb\x87'
    original[0xcb026:0xcb02c]=data[RAW+0xb08:RAW+0xb0e]
    original[0xcb150:0xcb156]=data[RAW+0xb0e:RAW+0xb14]
    original=bytes(original)
    if build(original)!=data: raise ValueError('V2 trial has unknown modifications')
    return original

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--restore',action='store_true')
    args=parser.parse_args()
    result=(restore if args.restore else build)(args.source.read_bytes())
    with args.output.open('xb') as stream: stream.write(result)
