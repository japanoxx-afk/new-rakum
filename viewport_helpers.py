"""Build development-only x86 helpers for the allowlisted viewport probe."""
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

RECTS = 0x4eb800
INIT_RETURN = 0x4eba00
CURSOR_RETURN = 0x4ebb00
LEFT_DECORATION = 0x4ebc00
MENU_CHILDREN = 0x4ebd00
MENU_DRAW = 0x4ebe00
PANEL_GATE = 0x4ebe40
TOOLTIP_RECTS = 0x4eb700
INFO_LAYOUT = 0x4eb850
RESOURCE_ANCHOR = 0x4ebf80
INFO_INITIALIZERS = (0x452830, 0x4529d0, 0x452a30, 0x452a90, 0x452af0,
    0x452b50, 0x452bb0, 0x452c10, 0x452c70, 0x452cf0, 0x452da0,
    0x452e50, 0x452eb0, 0x4530b0, 0x4531d0, 0x453230, 0x453300,
    0x453360, 0x4533c0)


def assemble(source, address):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(source, address)[0])


def helpers():
    # These native initializers only refresh coordinate tables. They must run
    # again after Main_SetWindowRect changes the shared HUD origin.
    info_layout = assemble('pushfd; pushad; ' +
        '; '.join(f'call {address}' for address in INFO_INITIALIZERS) +
        '; popad; popfd; pop edi; pop esi; pop ebx; mov esp, ebp; pop ebp; ret', INFO_LAYOUT)
    resource_anchor = assemble('''
        mov eax, [0x106a5e4]
        cmp word ptr [0x106a5e0], 1280
        jne original_x
        cmp word ptr [0x106a5e2], 720
        jne original_x
        mov eax, 792
        mov ecx, [ebp-4]
        mov word ptr [ecx+0x84], ax
        mov word ptr [ecx+0x86], -6
        jmp 0x45260b
    original_x:
        jmp 0x4525d1
    ''', RESOURCE_ANCHOR)
    tooltip_rects = assemble('''
        pushfd
        pushad
        mov esi, 0x801c78
        mov ecx, 15
        movsx ebx, word ptr [0x501ea0]
        movsx edx, word ptr [0x501ea2]
    next_tip:
        mov eax, [esi]
        add eax, ebx
        mov [esi+16], eax
        mov eax, [esi+4]
        add eax, edx
        mov [esi+20], eax
        mov eax, [esi+8]
        add eax, ebx
        mov [esi+24], eax
        mov eax, [esi+12]
        add eax, edx
        mov [esi+28], eax
        add esi, 32
        loop next_tip
        popad
        popfd
        ret
    ''', TOOLTIP_RECTS)
    panel_gate = assemble(f'''
        cmp word ptr [0x106a5e0], 1280
        jne original_gate
        cmp word ptr [0x106a5e2], 720
        jne original_gate
        call {TOOLTIP_RECTS}
        mov eax, [ebp+8]
        movsx ecx, word ptr [eax]
        cmp ecx, [0x106a690]
        jl outside
        cmp ecx, [0x106a698]
        jg outside
        movsx ecx, word ptr [eax+2]
        cmp ecx, [0x106a694]
        jl outside
        cmp ecx, [0x106a69c]
        jg outside
        jmp 0x462e27
    outside:
        jmp 0x462e20
    original_gate:
        mov eax, [ebp+8]
        movsx ecx, word ptr [eax]
        jmp 0x462da0
    ''', PANEL_GATE)
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
    # CMenuMain creates child base coordinates relative to its ORIGINAL base
    # position. Its background is subsequently centered independently. Do not
    # apply the HUD origin a second time to these screen-space child positions.
    menu_children = assemble('''
        pushfd
        pushad
        movsx ebx, word ptr [ecx+0x3e]
        sub ebx, [ecx+8]
        movsx edx, word ptr [ecx+0x40]
        sub edx, [ecx+12]
        mov esi, [ecx+0x30]
        mov edi, [ecx+0x34]
    next_child:
        cmp esi, edi
        jae finished
        mov eax, [esi]
        mov ecx, [eax+8]
        add ecx, ebx
        mov [eax+0x40], cx
        mov ecx, [eax+12]
        add ecx, edx
        mov [eax+0x42], cx
        add esi, 4
        jmp next_child
    finished:
        popad
        popfd
        ret
    ''', MENU_CHILDREN)
    menu_draw = assemble(f'''
        call {MENU_CHILDREN}
        push ebp
        mov ebp, esp
        sub esp, 0x44
        jmp 0x459f96
    ''', MENU_DRAW)
    return {INFO_LAYOUT: info_layout, RESOURCE_ANCHOR: resource_anchor,
            PANEL_GATE: panel_gate, TOOLTIP_RECTS: tooltip_rects,
            RECTS: rectangles, INIT_RETURN: init_return,
            CURSOR_RETURN: cursor, LEFT_DECORATION: left,
            MENU_CHILDREN: menu_children, MENU_DRAW: menu_draw}
