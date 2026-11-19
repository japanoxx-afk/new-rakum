"""Developer-only assembler for hotkey_patch.CODE; not required by the launcher.

The code is position independent (calls into .text go through a register,
returns to .text use push/ret), so it can live at any section address.
"""
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

SOURCE = '''
entry:
    mov eax, dword ptr [ebp+8]
    cmp eax, 0xbe
    je period
    cmp eax, 0x71
    je f2
    sub eax, 0x30
    cmp eax, 9
    jbe digit
orig:
    push 0x11
    call dword ptr [0x4ec350]
    push 0x42efd6
    ret
finish:
    push 0x42f106
    ret

period:
    call allowed
    test eax, eax
    jz orig
    push 0
    call select_units
    add esp, 4
    jmp finish

f2:
    push 0x11
    call dword ptr [0x4ec350]
    test ax, ax
    js orig
    call allowed
    test eax, eax
    jz orig
    push 1
    call select_units
    add esp, 4
    jmp finish

digit:
    push 0x10
    call dword ptr [0x4ec350]
    test ax, ax
    jns orig
    push 0x11
    call dword ptr [0x4ec350]
    test ax, ax
    js orig
    call allowed
    test eax, eax
    jz orig
    mov eax, dword ptr [ebp+8]
    sub eax, 0x30
    push eax
    call add_to_group
    add esp, 4
    jmp finish

allowed:
    mov ecx, 0x6e66d8
    call dword ptr [0x4ec520]
    test al, al
    jnz al_no
    cmp byte ptr [0xb40749], 0
    jne al_no
    cmp dword ptr [0x801eac], 0
    jne al_no
    cmp byte ptr [0xb412cc], 8
    jae al_no
    mov eax, 1
    ret
al_no:
    xor eax, eax
    ret

unit_ok:
    xor eax, eax
    cmp word ptr [ebx+8], 0
    jle uo_ret
    cmp word ptr [ebx+2], 0
    je uo_ret
    mov cl, byte ptr [ebx+0x10]
    cmp cl, byte ptr [0xb412cc]
    jne uo_ret
    test byte ptr [ebx+7], 0x10
    jnz uo_ret
    cmp byte ptr [ebx+0x2b], 0
    jne uo_ret
    inc eax
uo_ret:
    ret

select_units:
    push ebp
    mov ebp, esp
    sub esp, 24
    push ebx
    push esi
    push edi
    xor edi, edi
    mov esi, 1
su_loop:
    imul ebx, esi, 0x138
    add ebx, 0x775a38
    call unit_ok
    test eax, eax
    jz su_next
    movzx eax, word ptr [ebx+0xe]
    imul eax, eax, 0x1c
    mov eax, dword ptr [eax+0x4fcd88]
    test eax, eax
    jz su_next
    xor ecx, ecx
    cmp word ptr [eax+0x40], 1
    sete cl
    cmp dword ptr [ebp+8], 0
    jne su_mil
    test ecx, ecx
    jz su_next
    cmp word ptr [ebx+6], 2
    jne su_next
    jmp su_add
su_mil:
    test ecx, ecx
    jnz su_next
su_add:
    mov word ptr [ebp+edi*2-24], si
    inc edi
    cmp edi, 12
    jae su_done
su_next:
    inc esi
    cmp esi, 0x6a6
    jb su_loop
su_done:
    test edi, edi
    jz su_out
    lea eax, [ebp-24]
    push edi
    push eax
    call commit
    add esp, 8
su_out:
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret

commit:
    push ebp
    mov ebp, esp
    push ebx
    push esi
    push edi
    mov esi, dword ptr [ebp+8]
    mov edi, dword ptr [ebp+12]
    push 0x6a6
    push 0
    push 0xb412e4
    mov eax, 0x4de7f0
    call eax
    add esp, 12
    xor ecx, ecx
cm_copy:
    cmp ecx, 12
    jae cm_copied
    xor eax, eax
    cmp ecx, edi
    jae cm_store
    movzx eax, word ptr [esi+ecx*2]
    mov byte ptr [eax+0xb412e4], 1
cm_store:
    mov word ptr [ecx*2+0x80083e], ax
    inc ecx
    jmp cm_copy
cm_copied:
    mov word ptr [0x80083c], di
    mov byte ptr [0xb412ce], 0xff
    mov eax, 0x447bd0
    call eax
    movzx eax, word ptr [0x80083e]
    imul edx, eax, 0x138
    mov dx, word ptr [edx+0x775a46]
    mov ecx, 1
cm_lead:
    cmp ecx, edi
    jae cm_lead_done
    movzx ebx, word ptr [ecx*2+0x80083e]
    imul ebx, ebx, 0x138
    cmp dx, word ptr [ebx+0x775a46]
    jne cm_mixed
    inc ecx
    jmp cm_lead
cm_mixed:
    xor eax, eax
cm_lead_done:
    mov word ptr [0xb412d0], ax
    mov word ptr [0x801ec4], 0
    push 1
    imul eax, eax, 0x138
    add eax, 0x775a38
    push eax
    mov ecx, 0x801e58
    mov eax, 0x4659e0
    call eax
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret

add_to_group:
    push ebp
    mov ebp, esp
    sub esp, 24
    push ebx
    push esi
    push edi
    movsx eax, byte ptr [0xb412cc]
    imul eax, eax, 0xd0
    mov ecx, dword ptr [ebp+8]
    imul ecx, ecx, 0x1a
    lea esi, [eax+ecx+0x106a6c0]
    xor edi, edi
    xor ecx, ecx
ag_old:
    cmp ecx, 12
    jae ag_old_done
    movzx eax, word ptr [esi+ecx*2+2]
    push ecx
    call ag_try
    pop ecx
    inc ecx
    jmp ag_old
ag_old_done:
    xor ecx, ecx
ag_new:
    cmp ecx, 12
    jae ag_new_done
    movzx eax, word ptr [ecx*2+0x80083e]
    push ecx
    call ag_try
    pop ecx
    inc ecx
    jmp ag_new
ag_new_done:
    xor ecx, ecx
ag_w:
    cmp ecx, 12
    jae ag_w_done
    xor eax, eax
    cmp ecx, edi
    jae ag_ws
    mov ax, word ptr [ebp+ecx*2-24]
ag_ws:
    mov word ptr [esi+ecx*2+2], ax
    inc ecx
    jmp ag_w
ag_w_done:
    mov eax, edi
    mov byte ptr [esi], al
    mov byte ptr [0xb412ce], 0xff
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret

ag_try:
    test eax, eax
    jz at_ret
    cmp eax, 0x6a6
    jae at_ret
    cmp edi, 12
    jae at_ret
    imul ebx, eax, 0x138
    add ebx, 0x775a38
    push eax
    call unit_ok
    mov edx, eax
    pop eax
    test edx, edx
    jz at_ret
    xor ecx, ecx
at_dup:
    cmp ecx, edi
    jae at_add
    cmp ax, word ptr [ebp+ecx*2-24]
    je at_ret
    inc ecx
    jmp at_dup
at_add:
    mov word ptr [ebp+edi*2-24], ax
    inc edi
at_ret:
    ret
'''


def assemble(addr=0x10000000):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(SOURCE, addr=addr)[0])


if __name__ == '__main__':
    a = assemble()
    assert a == assemble(0x20000000), 'code must be position independent'
    print(len(a))
    print(a.hex())
