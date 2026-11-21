"""건설 중인 건물에도 우클릭 집결지(랠리 포인트) 지정 허용 (Rhakmu.exe 1.000d).

분석:
  게임 화면 우클릭 0x431800: 고른 유닛([0xB412D0])이 내 건물이고 건물 표(0x4FE474 + 종류*0x14)
  +0x3E 의 비트 2(집결지 가능)가 있으면 0x447E60(3, 대상, 층 [0xB412CD], 지점 [0x6E68BC]) 를 부른다.
  (미니맵 우클릭 0x467DA6, 0x4702D6 도 같은 함수에 3 으로 들어온다.)
  0x447E60 은 건물 명령 0x400E 를 만든다:
    [0x400E][0x0F][부명령 word][건물 word][대상 word][층 byte][지점 dword (픽셀 x word, y word)]
  보내기 전에 고른 건물의 상태(+6)에 0x1000 비트가 있으면 (상태 & 0xFFF) - 4 로 표 0x447F52 를 보고
  0 인 상태(0x1004 건설 중, 0x1007, 0x1008, 0x100D)는 아무것도 보내지 않고 끝낸다 (0x447EC4).
  -> 건설 중인 건물에 집결지를 못 찍는 이유는 이 '보내는 쪽' 검사 하나뿐이다.
  실행부(0x4407E0 -> 0x443700, 부명령 3)는 상태를 보지 않고 건물 +0x5E(층, 0xFF = 없음),
  +0x60(지점) 에 저장한다. 건물을 놓을 때(0x43D270) 한 번 0xFF 로 초기화되고, 건설 완료 때 지우지
  않으므로 건설 중에 찍은 집결지는 완성 뒤 생산(0x438E50)에 그대로 쓰인다.

패치:
  0x447EBD 의 jmp [표] (7바이트) -> .text 여유 공간 0x4EBE10 의 코드로 점프.
  표 값이 1 이면 원래대로 보냄, 0 이어도 상태가 0x1004(건설 중)이고 부명령이 3(집결지)이면 보냄.
  나머지(다른 상태, 공격 대상 지정 1/2, 0x11 등)는 원래처럼 막는다.

동기화: 집결지는 명령 0x400E 로 모든 PC에 같은 프레임에 전달되고, 받는 쪽 실행부는 원래 게임 코드
  그대로다. 바뀌는 것은 '이 PC가 그 명령을 보낼지' 뿐이므로 상대 PC가 이 패치를 쓰지 않아도
  게임이 어긋나지 않는다 (리플레이에도 명령으로 남는다). 그래서 항상 켠다.
"""
from __future__ import annotations

import struct

SITE = 0x47EBD                      # 파일 오프셋 (VA 0x447EBD)
SITE_VA = 0x447EBD
ORIGINAL = bytes.fromhex("ff24954a7f4400")       # jmp dword ptr [edx*4 + 0x447F4A]
CAVE = 0xEBE10                      # 파일 오프셋 (VA 0x4EBE10), 모든 패치 조합에서 비어 있음
CAVE_VA = 0x4EBE10
CAVE_SIZE = 0x30
SEND, BLOCK = 0x447EC8, 0x447EC4
CONSTRUCTING = 0x1004
RALLY = 3

SOURCE = f"""
    test edx, edx
    jnz send
    cmp dword ptr [ebp-4], {CONSTRUCTING - 0x1004}
    jne block
    cmp word ptr [ebp+8], {RALLY}
    jne block
send:
    jmp {SEND:#x}
block:
    jmp {BLOCK:#x}
"""
CODE = bytes.fromhex("85d2750d837dfc00750c66837d08037505e9a2c0f5ffe999c0f5ff")
PATCHED = (b"\xe9" + struct.pack("<i", CAVE_VA - (SITE_VA + 5))).ljust(len(ORIGINAL), b"\x90")
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
            raise ValueError(f"건설 중 집결지 패치 코드 충돌: {offset:#x}")
        flags.append(value == patched)
    if len(set(flags)) != 1:
        raise ValueError("불완전한 건설 중 집결지 패치")
    return flags[0]


def transform(data, enabled=True) -> bytes:
    state(data)
    out = bytearray(data)
    for offset, original, patched in SITES:
        out[offset:offset + len(original)] = patched if enabled else original
    return bytes(out)
