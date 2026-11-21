"""ESC 생산 취소를 '예약된 대기열'부터 지우게 하는 패치 (Rhakmu.exe 1.000d).

분석:
  0x42EF90 (게임 화면 WM_KEYDOWN) 의 ESC 경로 0x42F048: 메뉴가 없으면 선택한 유닛마다
  0x447F60 (명령 0x400A '현재 작업 취소', 6바이트 [type][size][unit]) 을 보낸다.
  그래서 생산·연구 중인 건물에서 ESC 를 누르면 대기열이 남아 있어도 지금 진행 중인 것이 취소된다.
  유닛 +0x50 진행 중인 생산, +0x52 예약 개수(byte, 진행 중인 것 제외), +0x54 예약 목록 word 4칸.
  게임에는 예약 칸 하나를 지우는 명령 0x400B ([type][size][unit][칸 번호 byte], 0x447FB0) 이 이미 있다:
  정보 창의 예약 아이콘 클릭(0x4541F4)이 그 칸 번호로 보내고, 실행부 0x443590 은 그 칸을 비용 환불
  (0x4DAF60) 후 목록에서 빼고 개수를 줄인다. 진행 중인 생산은 건드리지 않는다.

패치:
  0x42F0C4 의 call 0x447F60 (5바이트) -> .text 여유 공간 0x4EBEA0 의 코드 호출.
  선택 유닛의 예약 개수가 1~4 면 0x400B(유닛, 개수-1) = 마지막에 예약한 것 하나 취소,
  예약이 없으면 원래대로 0x400A (진행 중인 생산·연구 취소, 그 밖의 유닛도 원래 동작).
  게임이 원래 가진 명령을 고르는 것만 바뀌므로 상대 PC 가 이 패치를 쓰지 않아도 동기화에 영향이 없다.
"""
from __future__ import annotations

import struct

SITE = 0x2F0C4                      # 파일 오프셋 (VA 0x42F0C4)
SITE_VA = 0x42F0C4
ORIGINAL = bytes.fromhex("e8978e0100")           # call 0x447F60
CAVE = 0xEBEA0                      # 파일 오프셋 (VA 0x4EBEA0), 모든 패치 조합에서 비어 있음
CAVE_VA = 0x4EBEA0
CAVE_SIZE = 0x50
CANCEL_CURRENT, CANCEL_SLOT = 0x447F60, 0x447FB0
UNITS, UNIT_SIZE, QUEUE_COUNT, QUEUE_SLOTS = 0x775A38, 0x138, 0x52, 4

SOURCE = f"""
    movsx eax, word ptr [esp+4]
    imul edx, eax, {UNIT_SIZE:#x}
    movsx ecx, byte ptr [edx+{UNITS + QUEUE_COUNT:#x}]
    test ecx, ecx
    jle current
    cmp ecx, {QUEUE_SLOTS}
    jg current
    dec ecx
    push ecx
    push eax
    mov eax, {CANCEL_SLOT:#x}
    call eax
    add esp, 8
    ret
current:
    push eax
    mov eax, {CANCEL_CURRENT:#x}
    call eax
    add esp, 4
    ret
"""
CODE = bytes.fromhex(
    "0fbf44240469d0380100000fbe8a8a5a770085c97e1383f9047f0e495150b8b07f4400ffd083c408c350"
    "b8607f4400ffd083c404c3"
)
PATCHED = b"\xe8" + struct.pack("<i", CAVE_VA - (SITE_VA + 5))
SITES = ((SITE, ORIGINAL, PATCHED), (CAVE, bytes(CAVE_SIZE), CODE.ljust(CAVE_SIZE, b"\x90")))
assert len(CODE) <= CAVE_SIZE


def assemble():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(SOURCE, addr=CAVE_VA)[0])


def state(data) -> bool:
    flags = []
    for offset, original, patched in SITES:
        value = bytes(data[offset:offset + len(original)])
        if value not in (original, patched):
            raise ValueError(f"ESC 예약 취소 패치 코드 충돌: {offset:#x}")
        flags.append(value == patched)
    if len(set(flags)) != 1:
        raise ValueError("불완전한 ESC 예약 취소 패치")
    return flags[0]


def transform(data, enabled=True) -> bytes:
    state(data)
    out = bytearray(data)
    for offset, original, patched in SITES:
        out[offset:offset + len(original)] = patched if enabled else original
    return bytes(out)
