from keystone import Ks, KS_ARCH_X86, KS_MODE_32
CAVE=0x4eba20
SITE=0x473425          # movsx ecx,[ebp+14]; sar ecx,5  (7 bytes)
EXACT=0x47345d         # original: exact cell has resource flag -> unit/building check
GATHER=0x4734de        # mov ax,0x2006 ; jmp end
MOVE=0x4734e7          # mov ax,0x2003 ; jmp end
RADIUS=2
asm=f"""
    movsx ecx, word ptr [ebp+0x14]
    sar ecx, 5
    mov word ptr [ebp-4], cx
    movsx edx, word ptr [ebp+0x16]
    sar edx, 5
    mov word ptr [ebp-2], dx
    imul eax, edx, 0x208
    test byte ptr [eax+ecx+0xb4198a], 2
    jnz {EXACT:#x}
    mov ebx, 1
pass_:
    mov edi, ebx
    neg edi
row_:
    mov esi, ebx
    neg esi
col_:
    lea eax, [edx+edi]
    imul eax, eax, 0x208
    add eax, ecx
    movzx eax, byte ptr [eax+esi+0xb4198a]
    cmp al, 0x53
    je found_
    cmp al, 0x63
    je found_
    inc esi
    cmp esi, ebx
    jle col_
    inc edi
    cmp edi, ebx
    jle row_
    inc ebx
    cmp ebx, {RADIUS}
    jle pass_
    jmp {MOVE:#x}
found_:
    add ecx, esi
    add edx, edi
    shl ecx, 5
    add ecx, 16
    shl edx, 5
    add edx, 16
    mov eax, dword ptr [ebp]
    mov word ptr [eax+0x14], cx
    mov word ptr [eax+0x16], dx
    mov word ptr [ebp+0x14], cx
    mov word ptr [ebp+0x16], dx
    jmp {GATHER:#x}
"""
ks=Ks(KS_ARCH_X86,KS_MODE_32)
code,_=ks.asm(asm,CAVE); CODE=bytes(code)
jmp,_=ks.asm(f"jmp {CAVE:#x}",SITE); HOOK=bytes(jmp)+b'\x90'*(7-len(jmp))
if __name__=='__main__':
    print(len(CODE),CODE.hex()); print(HOOK.hex())
