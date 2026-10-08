from keystone import Ks, KS_ARCH_X86, KS_MODE_32
SOURCE = '''
mov edx, [eax]
mov [ebp-0x20], edx
test edx, edx
jz fail
push 4
push edx
call dword ptr [0x4ec2a0]
test eax,eax
jnz fail
mov ecx,[ebp-0x20]
mov edx,[ecx]
test edx,edx
jz fail
mov [ebp-0x60],edx
push 0x34
push edx
call dword ptr [0x4ec2a0]
test eax,eax
jnz fail
mov edx,[ebp-0x60]
mov eax,[edx+0x30]
test eax,eax
jz fail
mov [ebp-0x60],eax
push eax
call dword ptr [0x4ec2a4]
test eax,eax
jnz fail
mov ecx,[ebp-0x20]
call dword ptr [ebp-0x60]
test eax,eax
jz done
mov [ebp-0x5c],eax
push 4
push eax
call dword ptr [0x4ec2a0]
test eax,eax
jnz done
mov eax,[ebp-0x5c]
mov eax,[eax]
mov [ebp-8],eax
jmp done
fail:
add esp,8
done:
jmp 0x463517
'''
def assemble():
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(SOURCE, addr=0x4eb600)[0])
if __name__ == '__main__':
    print(assemble().hex())
