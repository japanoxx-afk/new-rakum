"""생산된 유닛을 집결지(랠리 포인트) 쪽 건물 가장자리에서 나오게 하는 패치 (Rhakmu.exe 1.000d).

분석:
  생산 완료 0x438E50(건물): 진행값이 다 차면 빈 유닛 번호를 받고(0x43BE70), 지상 유닛이면
  0x439022 에서 빈 자리 탐색 0x477C30(층 [+0x16], 건물 칸 위치 [+0x18], 건물 종류 [+0xE], 0x20, 크기)
  를 부른다. 찾으면 전역 [0x8023C0]/[0x8023C2] (칸 x, y) 에 유닛을 만든다(0x43CAF0).
  그 뒤 집결지가 있으면(+0x5E >= 0) 새 유닛의 경로 목록에 집결지(+0x60, 픽셀)를 넣어 걸어가게 한다.
  0x477C30: 건물 모양 = [[0x510B10] + 모양*0x5C] (모양 = [0x4FE474 + 종류*0x14] +0x40),
  +0x18 폭, +0x1C 높이 (칸). 왼쪽 = x - 폭/2, 위 = y - 높이/2.
  1) 건물 안 아래쪽 줄부터 가운데 -> 왼쪽, 가운데 -> 오른쪽으로 2) 건물 둘레를 왼쪽 아래부터 돌며
  한 칸씩 넓혀 지형 칸 0xB4198A[y*0x208+x] == 0x40 이고 점유 0xB839CA[(y*0x208+x)*2] == 0 인 칸을 찾는다.
  그래서 집결지와 상관없이 늘 건물 아래(남쪽) 가운데 근처에서 나온다.
  공중 유닛(종류 +0x58 == -0x80)은 0x4784A0 을 쓰므로 이 패치와 무관하다.

패치:
  0x439022 call 0x477C30 -> 여유 공간 코드 호출 (인자 그대로).
  건물에 집결지가 있고 집결지 층(+0x5E)이 건물 층(+0x16)과 같으면:
    집결지 칸(픽셀 >> 5)을 건물 바로 바깥 테두리(왼쪽-1 ~ 오른쪽+1, 위-1 ~ 아래+1)로 잘라
    '집결지 쪽 가장자리 칸'을 정하고, 그 칸에서 가까운 순서(거리 0, 1, √2, 2, √5 — 표 OFFSETS, 21칸)로
    원래와 같은 조건(지형 0x40, 점유 0, 지도 안 4 <= x < 폭, 4 <= y < 높이)의 빈 칸을 찾는다.
    그 칸이 다른 유닛으로 막혀 있어도 집결지 쪽 가까운 곳에서 나온다.
    찾으면 [0x8023C0]/[0x8023C2] 에 쓰고 1 을 돌려준다.
  집결지가 없거나, 다른 층이거나, 집결지가 건물 안이거나, 그 근처가 막혀 있으면 원래 0x477C30.

동기화: 유닛이 생기는 위치가 바뀌므로 게임 진행(시뮬레이션) 코드다. 대전의 모든 PC가 같은 설정이어야
  한다 (집결지 금광 인식·선택 한도 24 와 같이 서버 PC의 대전 규칙으로 맞춘다).
  입력은 모두 시뮬레이션 상태(건물·지형·점유 표, 집결지는 명령 0x400E 로 모든 PC에 같은 값)뿐이고
  난수·시간·화면 상태를 쓰지 않으므로 같은 패치를 쓴 PC끼리는 결과가 같다.

코드는 .text 여유 공간 세 곳, 표는 한 곳에 나눠 둔다 (원본에서 0 이고 모든 패치 조합과 함께 빌드됨을 시험이 확인).
"""
from __future__ import annotations

import struct

SITE = 0x39022                      # 파일 오프셋 (VA 0x439022)
SITE_VA = 0x439022
SEARCH = 0x477C30                   # 원래 빈 자리 탐색
ORIGINAL = b"\xe8" + struct.pack("<i", SEARCH - (SITE_VA + 5))   # call 0x477C30
SHAPES, BUILDING_TYPES = 0x510B10, 0x4FE474
TERRAIN, OCCUPANCY, MAP_W, MAP_H = 0xB4198A, 0xB839CA, 0xB412D4, 0xB412D6
SPOT_X, SPOT_Y = 0x8023C0, 0x8023C2
RALLY_LAYER, RALLY_POINT, LAYER = 0x5E, 0x60, 0x16
# 가장자리 칸에서 찾을 (dx, dy): 거리 제곱 0, 1, 2, 4, 5 순서, 같은 거리는 위->아래, 왼쪽->오른쪽
OFFSETS = sorted(((dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if dx * dx + dy * dy <= 5),
                 key=lambda d: (d[0] * d[0] + d[1] * d[1], d[1], d[0]))
TABLE = bytes(b & 0xFF for d in OFFSETS for b in d)

# (VA, 크기) — 원본과 모든 패치 조합에서 0 인 .text 여유 공간 (VA - 0x400000 = 파일 오프셋)
CHUNKS = {"entry": (0x4EBB80, 0x80), "search": (0x4EBDA0, 0x60), "tail": (0x4EBAB0, 0x50),
          "table": (0x4EBF50, 0x30)}

SOURCES = {
    # 진입: 집결지 확인, 건물 모양, 집결지 쪽 가장자리 칸 (ebp = x, ecx = y)
    "entry": """
    mov eax, dword ptr [ebp+8]
    mov dl, byte ptr [eax+{RALLY_LAYER}]
    cmp dl, byte ptr [eax+{LAYER}]
    jne {orig}
    pushal
    mov esi, eax
    movsx edx, byte ptr [esp+0x2c]
    imul edx, edx, 0x14
    mov edx, dword ptr [edx+{BUILDING_TYPES}]
    movsx edx, word ptr [edx+0x40]
    imul edi, edx, 0x5c
    add edi, dword ptr [{SHAPES}]
    movsx eax, word ptr [esp+0x28]
    movsx edx, word ptr [edi+0x18]
    movsx ecx, word ptr [esi+{RALLY_POINT}]
    call {dim}
    mov ebp, ecx
    push edx
    movsx eax, word ptr [esp+0x2e]
    movsx edx, word ptr [edi+0x1c]
    movsx ecx, word ptr [esi+{RALLY_POINT_Y}]
    call {dim}
    pop eax
    or eax, edx
    jz {fail}
    jmp {search}
""",
    # 표의 (dx, dy) 를 차례로: 가장자리 칸 (ebp, ecx) 에서 가까운 칸부터
    "search": """
    mov esi, {TABLE}
next:
    movsx ebx, byte ptr [esi]
    add ebx, ebp
    movsx edi, byte ptr [esi+1]
    add edi, ecx
    add esi, 2
    cmp ebx, 4
    jl skip
    cmp bx, word ptr [{MAP_W}]
    jge skip
    cmp edi, 4
    jl skip
    cmp di, word ptr [{MAP_H}]
    jge skip
    imul eax, edi, 0x208
    add eax, ebx
    cmp byte ptr [eax+{TERRAIN}], 0x40
    jne skip
    cmp word ptr [eax*2+{OCCUPANCY}], 0
    je {found}
skip:
    cmp esi, {TABLE_END}
    jb next
    jmp {fail}
""",
    # 한 축: eax = 건물 중심 칸, edx = 크기, ecx = 집결지 픽셀 -> ecx = 바깥 테두리로 자른 칸,
    #        edx = 1 (테두리 줄에 있음) / 0 (건물 폭 안)
    "tail": """
dim:
    mov ebx, edx
    sar ebx, 1
    sub eax, ebx
    dec eax
    lea ebx, [eax+edx+1]
    sar ecx, 5
    cmp ecx, eax
    cmovl ecx, eax
    cmp ecx, ebx
    cmovg ecx, ebx
    xor edx, edx
    cmp ecx, eax
    je edge
    cmp ecx, ebx
    jne done
edge:
    inc edx
done:
    ret
found:
    mov word ptr [{SPOT_X}], bx
    mov word ptr [{SPOT_Y}], di
    popal
    mov al, 1
    ret
fail:
    popal
orig:
    jmp {SEARCH}
""",
}

# 미리 조립한 코드 (assemble() 과 같아야 함 — 시험이 확인)
CODE = {
    "entry": bytes.fromhex(
        "8b45088a505e3a50160f8558ffffff6089c60fbe54242c6bd2148b9274e44f000fbf52406bfa5c033d10"
        "0b51000fbf4424280fbf57180fbf4e60e8f1feffff89cd520fbf44242e0fbf571c0fbf4e62e8dcfeffff"
        "5809d00f8409ffffffe9be010000"),
    "search": bytes.fromhex(
        "be50bf4e000fbe1e01eb0fbe7e0101cf83c60283fb047c37663b1dd412b4007d2e83ff047c29663b3dd6"
        "12b4007d2069c70802000001d880b88a19b40040750f66833c45ca39b800000f84e5fcffff81fe7abf4e"
        "0072aee9eafcffff"),
    "tail": bytes.fromhex(
        "89d3d1fb29d8488d5c1001c1f90539c10f4cc839d90f4fcb31d239c1740439d9750142c366891dc02380"
        "0066893dc223800061b001c361e944c1f8ff"),
    "table": TABLE,
}
PATCHED = b"\xe8" + struct.pack("<i", CHUNKS["entry"][0] - (SITE_VA + 5))     # call 진입 조각
SITES = ((SITE, ORIGINAL, PATCHED),) + tuple(
    (CHUNKS[k][0] - 0x400000, bytes(CHUNKS[k][1]), CODE[k].ljust(CHUNKS[k][1], bytes(1) if k == "table" else b"\x90"))
    for k in CHUNKS)
assert all(len(CODE[k]) <= CHUNKS[k][1] for k in CHUNKS)


def assemble() -> dict:
    """keystone 으로 세 조각을 조립 (조각 사이 주소가 서로 맞을 때까지 반복)."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    consts = dict(RALLY_LAYER=RALLY_LAYER, LAYER=LAYER, RALLY_POINT=RALLY_POINT, RALLY_POINT_Y=RALLY_POINT + 2,
                  BUILDING_TYPES=BUILDING_TYPES, SHAPES=SHAPES, MAP_W=MAP_W, MAP_H=MAP_H, TERRAIN=TERRAIN,
                  OCCUPANCY=OCCUPANCY, SPOT_X=SPOT_X, SPOT_Y=SPOT_Y, SEARCH=SEARCH,
                  TABLE=CHUNKS["table"][0], TABLE_END=CHUNKS["table"][0] + len(TABLE))
    labels = {"search": CHUNKS["search"][0], "dim": CHUNKS["tail"][0], "found": 0, "fail": 0, "orig": 0}
    for _ in range(4):
        code = {}
        for name, src in SOURCES.items():
            va = CHUNKS[name][0]
            code[name] = bytes(ks.asm(src.format(**consts, **{k: hex(v or va) for k, v in labels.items()}),
                                      addr=va)[0])
        # 조각 'tail' 안 이름 위치
        tail_va = CHUNKS["tail"][0]
        lines = SOURCES["tail"].format(**consts, **{k: hex(v or tail_va) for k, v in labels.items()})
        before = {}
        for label in ("found", "fail", "orig"):
            head = lines.split(f"{label}:")[0]
            before[label] = tail_va + len(ks.asm(head + "\n nop", addr=tail_va)[0]) - 1
        if all(labels[k] == before[k] for k in before):
            return {**code, "table": TABLE}
        labels.update(before)
    raise RuntimeError("조립 주소가 맞지 않음")


def state(data) -> bool:
    flags = []
    for offset, original, patched in SITES:
        value = bytes(data[offset:offset + len(original)])
        if value not in (original, patched):
            raise ValueError(f"집결지 쪽 생산 위치 패치 코드 충돌: {offset:#x}")
        flags.append(value == patched)
    if len(set(flags)) != 1:
        raise ValueError("불완전한 집결지 쪽 생산 위치 패치")
    return flags[0]


def transform(data, enabled=True) -> bytes:
    state(data)
    out = bytearray(data)
    for offset, original, patched in SITES:
        out[offset:offset + len(original)] = patched if enabled else original
    return bytes(out)
