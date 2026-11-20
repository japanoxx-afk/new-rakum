"""메뉴 해제 크래시 보호 (Rhakmu.exe 1.000d).

RhakMU.ERR:
  GameCtrl.dll class_form::DeleteAllControls()+8   (mov esi, [ebx], ebx = [form+0x3C])
  <- CGameMenu::Free()+0x63 (0x42414F)  <- Free_BaseData (게임 종료) / Menu_GameBeforeProcess (대전 시작)
CGameMenu::Free (0x424110) 는 [this] 의 현재 메뉴 폼을 0x428780 으로 지우는데, 그 폼이 이미 지워져
컨트롤 목록 포인터([form+0x3C])가 쓰레기면 크래시한다.

패치: 0x42413D (18바이트: [this] 검사 + 0x428780 호출) -> .text 여유 공간 0x4EBD40 의 코드로 점프.
폼(0x44 바이트)과 컨트롤 목록 머리(8 바이트)를 IsBadReadPtr 로 확인해 읽을 수 있을 때만 원래대로 지우고,
아니면 건너뛴다 (지워진 폼을 다시 지우지 않음). 화면·게임 진행에는 영향 없음.
"""
from __future__ import annotations

import struct

SITE = 0x2413D                      # 파일 오프셋 (VA 0x42413D)
SITE_VA = 0x42413D
ORIGINAL = bytes.fromhex("8b45fc833800740a8b4dfc8b09e831460000")
CAVE = 0xEBD40                      # 파일 오프셋 (VA 0x4EBD40), 모든 패치 조합에서 비어 있음
CAVE_VA = 0x4EBD40
CAVE_SIZE = 0x60
CODE = bytes.fromhex(
    "8b45fc8b0885c9742e6a4451ff15a0c24e0085c075218b45fc8b088b493c6a0851ff15a0c24e0085c0750c"
    "8b45fc8b08b880874200ffd0684f414200c3"
)
JUMP = (b"\xe9" + struct.pack("<i", CAVE_VA - (SITE_VA + 5))).ljust(len(ORIGINAL), b"\x90")
SITES = ((SITE, ORIGINAL, JUMP), (CAVE, bytes(CAVE_SIZE), CODE.ljust(CAVE_SIZE, b"\x90")))
assert len(CODE) <= CAVE_SIZE

SOURCE = """
    mov eax, dword ptr [ebp-4]
    mov ecx, dword ptr [eax]
    test ecx, ecx
    je back
    push 0x44
    push ecx
    call dword ptr [0x4ec2a0]
    test eax, eax
    jne back
    mov eax, dword ptr [ebp-4]
    mov ecx, dword ptr [eax]
    mov ecx, dword ptr [ecx+0x3c]
    push 8
    push ecx
    call dword ptr [0x4ec2a0]
    test eax, eax
    jne back
    mov eax, dword ptr [ebp-4]
    mov ecx, dword ptr [eax]
    mov eax, 0x428780
    call eax
back:
    push 0x42414f
    ret
"""


def assemble():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(SOURCE, addr=CAVE_VA)[0])


def state(data) -> bool:
    flags = []
    for offset, original, patched in SITES:
        value = bytes(data[offset:offset + len(original)])
        if value not in (original, patched):
            raise ValueError(f"메뉴 해제 보호 코드 충돌: {offset:#x}")
        flags.append(value == patched)
    if len(set(flags)) != 1:
        raise ValueError("불완전한 메뉴 해제 보호 패치")
    return flags[0]


def transform(data, enabled=True) -> bytes:
    state(data)
    out = bytearray(data)
    for offset, original, patched in SITES:
        out[offset:offset + len(original)] = patched if enabled else original
    return bytes(out)
