"""Narrow guards for ERR-proven invalid dispatches; not heap corruption repair.

Only validate immediately used pointers. Readable freed memory and later list
nodes cannot be diagnosed by this guard; preserve normal engine dispatch.
"""
from viewport_helpers import assemble

HUD_DRAW, FORM_CHECK, FORM_DRAW, FORM_PROCESS = 0x4eb520,0x4eb570,0x4eb760,0x4eb790

def helpers():
    hud=assemble('''
        pushfd; pushad
        mov ebx, ecx
        push 4; push ebx; call dword ptr [0x4ec2a0]
        test eax,eax; jnz bad
        mov esi,[ebx]; test esi,esi; jz bad
        push 0x30; push esi; call dword ptr [0x4ec2a0]
        test eax,eax; jnz bad
        mov edi,[esi+0x2c]; test edi,edi; jz bad
        push edi; call dword ptr [0x4ec2a4]
        test eax,eax; jnz bad
        popad; popfd
        mov edx,[ecx]; mov ecx,[ebp-8]; call dword ptr [edx+0x2c]
        jmp 0x463a9c
    bad:
        popad; popfd; jmp 0x463a9c
    ''',HUD_DRAW)
    # EDX is requested virtual method offset; return boolean in EAX, preserving
    # every other register. The log faults at form+3c's sentinel dereference.
    check=assemble('''
        pushad
        mov ebx,ecx; mov ebp,edx
        test ebx,ebx; jz bad
        push 0x40; push ebx; call dword ptr [0x4ec2a0]
        test eax,eax; jnz bad
        mov esi,[ebx]; test esi,esi; jz bad
        push 0x24; push esi; call dword ptr [0x4ec2a0]
        test eax,eax; jnz bad
        mov edi,[esi+ebp]; test edi,edi; jz bad
        push edi; call dword ptr [0x4ec2a4]
        test eax,eax; jnz bad
        mov esi,[ebx+0x3c]; test esi,esi; jz bad
        push 0xc; push esi; call dword ptr [0x4ec2a0]
        test eax,eax; jnz bad
        mov edi,[esi]; test edi,edi; jz bad
        push 0xc; push edi; call dword ptr [0x4ec2a0]
        test eax,eax; jnz bad
        mov dword ptr [esp+0x1c],1; popad; ret
    bad:
        mov dword ptr [esp+0x1c],0; popad; ret
    ''',FORM_CHECK)
    draw=assemble(f'''
        mov edx,0x20; call {FORM_CHECK}; test eax,eax; jz skip
        mov edx,[ecx]; call dword ptr [edx+0x20]
    skip: jmp 0x428923
    ''',FORM_DRAW)
    process=assemble(f'''
        mov edx,0x1c; call {FORM_CHECK}; test eax,eax; jz skip
        mov edx,[ecx]; call dword ptr [edx+0x1c]; jmp 0x4289a6
    skip: add esp,0xc; xor eax,eax; jmp 0x4289a6
    ''',FORM_PROCESS)
    return {HUD_DRAW:hud,FORM_CHECK:check,FORM_DRAW:draw,FORM_PROCESS:process}
