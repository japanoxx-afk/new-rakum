"""Guarded full-height terrain/fog helpers for the 1280x720 research build."""
from viewport_helpers import assemble

ROWS = 0x4eb900
COLUMNS = 0x4eb980
SCANLINE = 0x4ebc40
CLEAR = 0x4ebc80
FILL = 0x4ebf00
REDUCE = 0x4ebf10
HALF = 0x4ebf20
FOG_CLIP = 0x4ebf30


def helpers():
    rows = assemble('''
        cmp word ptr [0x106a5e0], 1280
        jne original
        cmp eax, 720
        jne original
        push ebx
        add eax, 31
        sar eax, 5
        movsx edx, byte ptr [0xb412cd]
        movsx ebx, word ptr [edx*2+0xb412da]
        movsx edx, word ptr [0xb412d6]
        sub edx, ebx
        pop ebx
        test edx, edx
        jns nonnegative
        xor edx, edx
    nonnegative:
        cmp eax, edx
        jle done
        mov eax, edx
    done:
        ret
    original:
        sub eax, 152
        cdq
        and edx, 31
        add eax, edx
        sar eax, 5
        ret
    ''', ROWS)
    columns = assemble('''
        cdq
        and edx, 31
        add eax, edx
        sar eax, 5
        cmp word ptr [0x106a5e0], 1280
        jne done
        cmp word ptr [0x106a5e2], 720
        jne done
        push ebx
        movsx edx, byte ptr [0xb412cd]
        movsx ebx, word ptr [edx*2+0xb412d8]
        movsx edx, word ptr [0xb412d4]
        sub edx, ebx
        pop ebx
        test edx, edx
        jns nonnegative
        xor edx, edx
    nonnegative:
        cmp eax, edx
        jle done
        mov eax, edx
    done:
        ret
    ''', COLUMNS)
    scanline = assemble('''
        movsx edx, word ptr [0x106a5e2]
        movsx ecx, word ptr [0xb41158]
        shl ecx, 5
        sub edx, ecx
        mov ecx, [ebp-0x10]
        cmp dx, word ptr [ecx+2]
        jle limited
        movsx edx, word ptr [ecx+2]
    limited:
        jmp 0x4ca8df
    ''', SCANLINE)
    # Clear before world rendering, NOT after objects or HUD. This also prevents
    # stale pixels outside map bounds and under transparent RLE sprite gaps.
    clear = assemble('''
        pushfd
        pushad
        cmp word ptr [0x106a5e0], 1280
        jne done
        cmp word ptr [0x106a5e2], 720
        jne done
        push 0
        push 720
        push 1280
        push 0
        push 0
        call dword ptr [0x4ec480]
    done:
        popad
        popfd
        push ebp
        mov ebp, esp
        sub esp, 0x58
        jmp 0x4ca696
    ''', CLEAR)
    result = {ROWS: rows, COLUMNS: columns, SCANLINE: scanline, CLEAR: clear}
    for address, iat in ((FILL,0x4ec480),(REDUCE,0x4ec484),(HALF,0x4ec538)):
        result[address] = assemble(f'mov eax, {iat}; jmp {FOG_CLIP}', address)
    # All three fog APIs accept (x,y,width,height,data/color), stdcall. Their
    # buffers start at tile row zero; reducing height keeps RLE row alignment.
    result[FOG_CLIP] = assemble('''
        movsx edx, word ptr [0x106a5e2]
        sub edx, [esp+8]
        test edx, edx
        jle skip
        cmp edx, [esp+16]
        jge draw
        mov [esp+16], edx
    draw:
        jmp dword ptr [eax]
    skip:
        ret 20
    ''', FOG_CLIP)
    return result
