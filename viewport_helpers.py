"""Build development-only x86 helpers for the allowlisted viewport probe."""
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

RECTS = 0x4eb800
INIT_RETURN = 0x4eba00
CURSOR_RETURN = 0x4ebb00
LEFT_DECORATION = 0x4ebc00


def assemble(source, address):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(source, address)[0])


def helpers():
    rectangles = assemble('''
        pushfd
        pushad
        lea edi, [ecx+0xd8]
        xor esi, esi
    next_rect:
        movsx eax, word ptr [esi*4+0x4ff6a8]
        movsx ebx, word ptr [0x501ea0]
        add eax, ebx
        movsx edx, word ptr [esi*4+0x4ff6aa]
        movsx ebx, word ptr [0x501ea2]
        add edx, ebx
        mov [edi], eax
        mov [edi+4], edx
        add eax, 40
        add edx, 40
        mov [edi+8], eax
        mov [edi+12], edx
        add edi, 16
        inc esi
        cmp esi, 10
        jl next_rect
        popad
        popfd
        ret
    ''', RECTS)
    init_return = assemble(f'''
        mov ecx, [ebp-4]
        call {RECTS}
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    ''', INIT_RETURN)
    # Match Game_DrawMouseOnly's original background restore, but also validate
    # the rectangle against the current surface after a resolution transition.
    cursor = assemble('''
        pushfd
        pushad
        cmp dword ptr [0x7668ec], 0
        je done
        movsx ebx, word ptr [0x6e68c4]
        movsx edx, word ptr [0x6e68c6]
        movsx esi, word ptr [0x6e68c8]
        movsx edi, word ptr [0x6e68ca]
        test ebx, ebx
        js done
        test edx, edx
        js done
        test esi, esi
        jle done
        test edi, edi
        jle done
        cmp esi, 512
        jge done
        cmp edi, 512
        jge done
        lea eax, [ebx+esi]
        movsx ecx, word ptr [0x106a5e0]
        cmp eax, ecx
        jg done
        lea eax, [edx+edi]
        movsx ecx, word ptr [0x106a5e2]
        cmp eax, ecx
        jg done
        push esi
        push edi
        push esi
        push 0x6e68cc
        push edx
        push ebx
        call dword ptr [0x4ec588]
    done:
        popad
        popfd
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    ''', CURSOR_RETURN)
    left = assemble('''
        movsx edx, word ptr [ecx+eax+2]
        add edx, dword ptr [0x106a690]
        sub edx, 112
        push edx
        jmp 0x464778
    ''', LEFT_DECORATION)
    return {RECTS: rectangles, INIT_RETURN: init_return,
            CURSOR_RETURN: cursor, LEFT_DECORATION: left}
