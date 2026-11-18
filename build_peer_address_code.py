"""Developer-only assembler; not required by the launcher."""
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

SOURCE = '''
pushfd
pushad
mov esi, [ebp-4]
mov edi, [esi+0x18]
cmp dword ptr [edi+8], 12
jne done
mov edx, [edi+0xc]
cmp word ptr [edx], 0x8813
jne done
cmp word ptr [edx+2], 10
jne done
mov eax, [edx+6]
cmp eax, dword ptr [0xb412c4]
jne done
movzx eax, byte ptr [0xb412cc]
cmp al, byte ptr [edx+5]
jne done
movzx ecx, byte ptr [edx+4]
cmp ecx, 8
jae done
cmp ecx, eax
je done
mov ebx, [edi]
cmp bl, 26
jne done
imul eax, ecx, 0x11e0
cmp byte ptr [eax+0x7f790e], 0x20
jb done
cmp dword ptr [eax+0x7f7934], 0
je done
mov [eax+0x7f7934], ebx
mov edi, ecx
imul ecx, ecx, 0x284
mov [esi+ecx+0x54], ebx
mov word ptr [esi+ecx+0x50], 2
mov word ptr [esi+ecx+0x52], 0xd72b
push edi
push 0x8814
mov ecx, esi
call 0x448de0
done:
popad
popfd
jmp 0x44a2e7
'''

def assemble():
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(SOURCE, addr=0x4eb420)[0])

if __name__ == '__main__':
    print(assemble().hex())
