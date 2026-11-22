"""같은 생산 건물 여러 개를 골라 생산·업그레이드를 나눠 맡기는 패치 (스타크래프트2 방식, Rhakmu.exe 1.000d).

분석:
  건물 생산·연구 버튼(0x45F92B..)은 명령 0x4008 [종류 0x4008][크기 9][유닛 word][세부 byte][값 word]
  를 0x447CF0(종류, 유닛, 세부, 값) 으로 보낸다. 유닛은 늘 정보 창에 보이는 유닛 [0xB412D0].
  실행 0x4416A0 (세부 5..10):
    5  유닛 생산 0x1005 : 쉬고 있으면 시작, 이미 생산 중(0x1005)이면 예약(+0x52 개수 < 4, +0x54 목록),
                          다른 일(연구 등, 명령 & 0x1000) 중이면 무시.
    6  업그레이드·연구 0x1006 / 10  0x100A : 쉬고 있을 때만 (명령 & 0x1000 이면 무시).
  같은 종류 선택 0x4335F0 (더블클릭, 0x4314C7): 화면 안의 같은 종류 내 유닛을 최대 12(24)개 고른다.
    0x43360E: 누른 유닛이 건물(+2 != 0)이면 아무것도 안 함, 0x433AD8: 화면 탐색에서 건물은 건너뜀.
    그래서 건물은 하나씩만 고를 수 있었다. 고른 유닛이 모두 같은 종류면 0x432F30 이 첫 유닛을
    정보 창 유닛 [0xB412D0] 으로 정해 그 건물의 생산 버튼이 나온다.

패치:
  1) 0x433603 (18바이트): '건물이면 그만' -> '내 유닛이 아니면 그만' (주인 +0x10 != [0xB412CC]).
     내 건물을 더블클릭하면 화면 안의 같은 종류 내 건물을 모두 고른다.
  2) 0x433AC0 (50바이트): 화면 탐색에서 건물도 고르되 누른 유닛과 분류(+2)가 같은 것만 (건물·유닛 종류 번호가 겹침).
     0x433896 (59바이트): 공중 유닛 탐색은 누른 유닛이 건물이면 아무것도 고르지 않음.
     선택 음성 0x49E400 세 곳 -> 건물이면 건너뜀 (여러 건물을 고를 때 유닛 음성이 나던 것).
  4) 0x46049F (30바이트): 같은 건물을 둘 이상 골랐으면 정보 창 건물이 연구 중이어도 생산·연구 버튼을 보여 준다
     (원래는 '취소'만 보여 줘서 다른 건물에 연구를 맡길 수 없었다). 하나만 골랐을 때는 원래대로.
  3) 0x447CF0 머리 (6바이트) -> 여유 공간 코드: 명령 0x4008 세부 5/6/10 이면 보낼 건물을 고른다.
     내 선택 목록(주소는 0x43366A 명령의 값을 읽음 — 선택 한도 24 패치가 옮겨도 맞음) 중 정보 창 유닛과
     같은 종류, 내 것, 체력 > 0 인 건물의 '할 일 수'를 센다: 쉬면 0, 생산 중이면 1 + 예약 수(세부 5만),
     그 밖에는 받을 수 없음. 가장 적은 건물에 보낸다 (같으면 정보 창 유닛, 그다음 선택 순서).
     받을 건물이 없으면 원래대로 정보 창 유닛에 보낸다 (게임이 원래처럼 무시).

  5) 0x447E60 머리 (6바이트) -> 여유 공간 코드: 부명령 3(집결지)이고 둘 이상 골랐으면 선택 중 같은 종류·내 것·
     체력 > 0 건물마다 정보 창 유닛을 잠깐 그 건물로 두고 원래 함수를 불러 명령 0x400E 를 하나씩 보낸다
     (우클릭 0x43194F, 미니맵 우클릭 0x467DA6·0x4702D6 이 이 함수를 부름). 끝나면 정보 창 유닛을 되돌린다.

동기화: 보내는 쪽에서 명령 안의 건물 번호만 고르는 것이라 게임 진행 코드는 그대로다.
  상대 PC가 이 패치를 쓰지 않아도 같은 명령을 같은 결과로 실행한다.
"""
from __future__ import annotations

import struct

SEND = 0x447CF0                               # 명령 보내기 (종류, 유닛, 세부, 값)
SEND_BODY = SEND + 6                          # 머리 push ebp / mov ebp,esp / sub esp,0x40 뒤
SHOWN, ME, SEL_COUNT = 0xB412D0, 0xB412CC, 0x80083C
SEL_LIST_REF = 0x43366E                       # movsx eax, word [edx*2 + 목록] 의 목록 주소 (선택 한도 24 패치가 옮김)
UNITS = 0x775A38
HP, ORDER, TYPE, OWNER, QUEUE = UNITS + 8, UNITS + 6, UNITS + 0xE, UNITS + 0x10, UNITS + 0x52

# (파일 오프셋, 원래, 바꾼 것) — 더블클릭으로 같은 종류 건물 고르기
PICK_SITE = 0x33603
PICK_ORIGINAL = bytes.fromhex("33c9668b883a5a770085c97405e9c8050000")
PICK_PATCHED = (bytes.fromhex("8a88") + struct.pack("<I", OWNER) +           # mov cl, [eax+주인]
                bytes.fromhex("3a0d") + struct.pack("<I", ME) +              # cmp cl, [내 번호]
                b"\x0f\x85" + struct.pack("<i", 0x433BDD - 0x433615))        # jne 끝
# 화면 탐색(땅 유닛 칸 0xB839CA)의 후보 검사 0x433AC0..0x433AF2 (50바이트): 원래 '건물이면 건너뜀' + '이미 고름(0x80)'.
# -> '이미 고름' + '누른 유닛과 분류(+2)가 다르면 건너뜀'. 건물과 유닛은 종류 번호(+0xE)가 겹칠 수 있어서
#    (무휼 본진과 일꾼이 같은 번호) 종류만 비교하면 본진을 더블클릭할 때 일꾼까지 섞여 골라졌다 (첫 선택이 건물이면
#    이동 명령 0x441240 이 통째로 무시되어 '선택은 되는데 조종이 안 됨').
SCAN_SITE = 0x33AC0
SCAN_ORIGINAL = bytes.fromhex("0fbf051269760069c03801000033c9668b883a5a770085c975180fbf151269760033c0"
                              "8a82e412b400258000000085c07405")
SCAN_PATCHED = bytes.fromhex("0fbf0512697600f680e412b40080752269c0380100000fbf4d0c69c938010000668b903a5a7700"
                             "663b913a5a77007502eb05")
# 공중 유닛 칸(0xC8BACA) 탐색의 후보 검사 0x433896..0x4338D1 (59바이트): 체력·'이미 고름'은 그대로,
# 누른 유닛이 건물이면 건너뜀 (건물 종류 번호가 공중 유닛 종류와 겹쳐 이 길로 와도 공중 유닛을 고르지 않게).
AIR_SITE = 0x33896
AIR_ORIGINAL = bytes.fromhex("0fbf151269760069d2380100000fbf82405a770085c07f05e9250300000fbf0d1269760033d2"
                             "8a91e412b40081e28000000085d27405e902030000")
AIR_PATCHED = bytes.fromhex("0fbf0512697600f680e412b40080752469c0380100006683b8405a7700007e140fbf4d0c69c938"
                            "0100006683b93a5a7700007407e9a8000000") + b"\x90\x90"
# 여럿 골랐을 때 선택 음성 0x49E400(유닛) 을 건물에도 불러 유닛 음성('마이')이 나왔다 -> 건물이면 건너뜀.
# (건물 선택 소리는 더블클릭의 첫 클릭에서 이미 난다.) 선택 확정 0x432F30 의 세 곳.
VOICE = 0x49E400
VOICE_SITES = (0x331F7, 0x3333A, 0x33360)
VOICE_CAVE = 0x4EBA0F
VOICE_CODE = bytes.fromhex("8b44240466837802007505e9e129fbffc3")     # 건물(+2 != 0)이면 ret, 아니면 jmp 0x49E400
SEND_SITE, SEND_ORIGINAL = SEND - 0x400000, bytes.fromhex("558bec83ec40")
RALLY = 0x447E60                              # 건물 명령 0x400E 보내기 (부명령, 대상, 층, 지점) — 3 = 집결지
RALLY_BODY = RALLY + 6
RALLY_SITE, RALLY_ORIGINAL = RALLY - 0x400000, bytes.fromhex("558bec83ec44")
# 정보 창 건물이 연구 등으로 바쁘면 패널이 '취소'만 보여 준다 (0x4604BB). 같은 건물 여럿을 골랐으면
# 버튼 목록(0x460508)을 보여 줘서 쉬는 다른 건물에 맡길 수 있게 한다 (하나만 골랐을 때는 원래대로).
PANEL_SITE = 0x6049F
PANEL_ORIGINAL = bytes.fromhex("0fbf05d012b40069c0380100000fbf883e5a770081e10010000085c9744b")
PANEL_PATCHED = bytes.fromhex("803d3c088000017760a1d012b4009869c038010000f6803f5a770010744b")

# (VA, 크기) — 원본과 모든 패치 조합에서 0 인 .text 여유 공간 조각들 (시험이 확인).
# 남은 여유 공간이 잘게 나뉘어 있어 코드를 작은 조각으로 나누고 jmp 로 잇는다. 이름은 모든 조각에서 공통.
CHUNKS = {
    "entry": (0x4EB9C6, 0x3A), "pick": (0x4EBCBB, 0x45), "scan": (0x4EBC65, 0x1B), "pend": (0x4EBEF0, 0x10),
    "load": (0x4EB94E, 0x32), "load2": (0x4EB5E6, 0x1A), "load3": (0x4EB778, 0x18),
    "rentry": (0x4EB741, 0x1F), "rpick": (0x4EB7D0, 0x30),
    "rscan": (0x4EBC14, 0x2C), "rsend": (0x4EB8D0, 0x30),
}

SOURCES = {
    # ---- 생산·연구: 0x447CF0 대신. [esp+4] 종류, [esp+8] 유닛, [esp+0xC] 세부
    "entry": """
entry:
    cmp dword ptr [esp+4], 0x4008
    jne orig
    pushal
    mov dl, byte ptr [esp+0x2c]
    cmp dl, 5
    je go
    cmp dl, 6
    je go
    cmp dl, 10
    jne done
go:
    jmp {pick}
done:
    popal
orig:
    push ebp
    mov ebp, esp
    sub esp, 0x40
    jmp {SEND_BODY}
""",
    # dl = 세부. ebx = 고른 건물, edi = 그 할 일 수, ebp = 종류, esi = 선택 목록, ecx = 남은 개수
    "pick": """
pick:
    movsx eax, word ptr [{SHOWN}]
    test eax, eax
    je {done}
    mov ebx, eax
    imul ebp, eax, 0x138
    movsx ebp, word ptr [ebp+{TYPE}]
    call {load}
    mov edi, eax
    mov esi, dword ptr [{SEL_LIST_REF}]
    movsx ecx, word ptr [{SEL_COUNT}]
    jmp {scan}
""",
    "scan": """
scan:
    dec ecx
    js {pend}
    lodsw
    cwde
    push eax
    call {load}
    cmp eax, edi
    jae keep
    xchg eax, edi
    mov ebx, dword ptr [esp]
keep:
    pop eax
    jmp scan
""",
    "pend": """
pend:
    cmp edi, 0x40
    jae out
    mov word ptr [esp+0x28], bx
out:
    jmp {done}
""",
    # eax = 유닛 -> eax = 할 일 수. dl = 세부, bp = 종류. esi 만 쓰고 되돌림.
    #   0 쉼, 1..4 생산 중(1 + 예약; 세부 5만), 그 밖은 받을 수 없음:
    #   0x40 / 0x40 + 주인*0x100 (죽음·남의 것·다른 종류, 0x1000 미만), 상태값 0x1xxx (바쁨: 생산 못 받음·연구 중 등)
    "load": """
load:
    push esi
    imul esi, eax, 0x138
    add esi, {UNITS}
    push 0x40
    pop eax
    cmp word ptr [esi+8], 0
    jle lret
    mov ah, byte ptr [esi+0x10]
    cmp ah, byte ptr [{ME}]
    jne lret
    cmp word ptr [esi+0xe], bp
    je {load2}
lret:
    pop esi
    ret
""",
    "load2": """
load2:
    movzx eax, word ptr [esi+6]
    test ah, 0x10
    je idle
    cmp dl, 5
    jne l2ret
    jmp {load3}
idle:
    xor eax, eax
l2ret:
    pop esi
    ret
""",
    "load3": """
load3:
    cmp ax, 0x1005
    jne l3ret
    movsx eax, byte ptr [esi+0x52]
    inc eax
    cmp al, 5
    jb l3ret
    mov al, 0x40
l3ret:
    pop esi
    ret
""",
    # ---- 집결지: 0x447E60 대신. [esp+4] 부명령(3 = 집결지), 인자 4개. 같은 종류 건물을 여럿 골랐으면
    #      건물마다 정보 창 유닛을 잠깐 그 건물로 두고 원래 함수를 불러 명령 0x400E 를 하나씩 보낸다.
    "rentry": """
rentry:
    cmp byte ptr [esp+4], 3
    jne rorig
    cmp byte ptr [{SEL_COUNT}], 1
    ja {rpick}
rorig:
    push ebp
    mov ebp, esp
    sub esp, 0x44
    jmp {RALLY_BODY}
""",
    "rpick": """
rpick:
    pushal
    movsx ebx, word ptr [{SHOWN}]
    imul eax, ebx, 0x138
    movsx ebp, word ptr [eax+{TYPE}]
    mov esi, dword ptr [{SEL_LIST_REF}]
    movsx edi, word ptr [{SEL_COUNT}]
    mov dl, 6
    jmp {rscan}
""",
    # load 의 값: 0 (쉼) 또는 0x1000 이상(바쁨)이면 집결지를 받는 내 같은 종류 건물
    "rscan": """
rscan:
    dec edi
    js rfin
    lodsw
    cwde
    push eax
    call {load}
    pop ecx
    cmp eax, 0x40
    jb rok
    cmp eax, 0x1000
    jb rscan
rok:
    jmp {rsend}
rfin:
    mov word ptr [{SHOWN}], bx
    popal
    ret
""",
    "rsend": """
rsend:
    mov word ptr [{SHOWN}], cx
    push dword ptr [esp+0x30]
    push dword ptr [esp+0x30]
    push dword ptr [esp+0x30]
    push dword ptr [esp+0x30]
    call {rorig}
    add esp, 0x10
    mov dl, 6
    jmp {rscan}
""",
}

# 미리 조립한 코드 (assemble() 과 같아야 함 — 시험이 확인)
CODE = {
    "entry": bytes.fromhex("817c240408400000751a608a54242c80fa05740a80fa06740580fa0a7505e9d2020000615589e583ec40e901c3f5ff"),
    "pick": bytes.fromhex("0fbf05d012b40085c00f841ffdffff89c369e8380100000fbfad465a7700e870fcffff89c78b356e3643000fbf0d3c088000e973ffffff"),
    "scan": bytes.fromhex("490f888402000066ad9850e8d9fcffff39f87304978b1c2458ebe5"),
    "pend": bytes.fromhex("83ff40730566895c2428e9eafaffff"),
    "load": bytes.fromhex("5669f03801000081c6385a77006a405866837e08007e158a66103a25cc12b400750a66396e0e0f846cfcffff5ec3"),
    "load2": bytes.fromhex("0fb74606f6c410740a80fa057507e97f01000031c05ec3"),
    "load3": bytes.fromhex("663d0510750b0fbe4652403c057202b0405ec3"),
    "rentry": bytes.fromhex("807c2404037509803d3c08800001777f5589e583ec44e90ac7f5ff"),
    "rpick": bytes.fromhex("600fbf1dd012b40069c3380100000fbfa8465a77008b356e3643000fbf3d3c088000b206e91b040000"),
    "rscan": bytes.fromhex("4f781b66ad9850e82efdffff5983f84072073d0010000072e7e99efcffff66891dd012b40061c3"),
    "rsend": bytes.fromhex("66890dd012b400ff742430ff742430ff742430ff742430e865feffff83c410b206e91e030000"),
}


def assemble() -> dict:
    """keystone 으로 조각들을 조립. 이름(줄 첫머리 'x:')은 모든 조각에서 공통이고, 다른 조각의 이름은
    {x} 로 적어 주소로 바꾼다. 조각 사이 주소가 서로 맞을 때까지 반복."""
    import re
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    consts = dict(SEND_BODY=hex(SEND_BODY), RALLY_BODY=hex(RALLY_BODY), SHOWN=hex(SHOWN), SEL_LIST_REF=hex(SEL_LIST_REF),
                  SEL_COUNT=hex(SEL_COUNT), TYPE=hex(TYPE), ME=hex(ME), UNITS=hex(UNITS))
    defined = {name: re.findall(r"^(\w+):", src, re.M) for name, src in SOURCES.items()}
    labels = {lab: CHUNKS[name][0] for name, labs in defined.items() for lab in labs}
    for _ in range(6):
        code, found = {}, {}
        for name, src in SOURCES.items():
            va = CHUNKS[name][0]
            text = src.format(**consts, **{k: (k if k in defined[name] else hex(v)) for k, v in labels.items()})
            code[name] = bytes(ks.asm(text, addr=va)[0])
            for lab in defined[name]:                    # 이 조각 안의 이름 위치 (끝에 붙인 .long 값)
                tail = bytes(ks.asm(text + f"\n.long {lab}", addr=va)[0])[-4:]
                found[lab] = struct.unpack("<I", tail)[0]
        if all(labels[k] == found[k] for k in found):
            return code
        labels.update(found)
    raise RuntimeError("조립 주소가 맞지 않음")


def _sites():
    send_jump = (b"\xe9" + struct.pack("<i", CHUNKS["entry"][0] - (SEND + 5))).ljust(len(SEND_ORIGINAL), b"\x90")
    rally_jump = (b"\xe9" + struct.pack("<i", CHUNKS["rentry"][0] - (RALLY + 5))).ljust(len(RALLY_ORIGINAL), b"\x90")
    sites = [(PICK_SITE, PICK_ORIGINAL, PICK_PATCHED), (SCAN_SITE, SCAN_ORIGINAL, SCAN_PATCHED),
             (AIR_SITE, AIR_ORIGINAL, AIR_PATCHED), (VOICE_CAVE - 0x400000, bytes(len(VOICE_CODE)), VOICE_CODE)]
    for at in VOICE_SITES:
        sites.append((at, b"\xe8" + struct.pack("<i", VOICE - (0x400000 + at + 5)),
                      b"\xe8" + struct.pack("<i", VOICE_CAVE - (0x400000 + at + 5))))
    sites += [
             (SEND_SITE, SEND_ORIGINAL, send_jump), (PANEL_SITE, PANEL_ORIGINAL, PANEL_PATCHED),
             (RALLY_SITE, RALLY_ORIGINAL, rally_jump)]
    for k, (va, size) in CHUNKS.items():
        assert len(CODE[k]) <= size, (k, len(CODE[k]), size)
        sites.append((va - 0x400000, bytes(size), CODE[k].ljust(size, b"\x90")))
    return tuple(sites)


def _match(data, sites):
    """True = 모두 바뀜, False = 모두 원래, None = 섞임·모르는 바이트."""
    flags = set()
    for offset, original, patched in sites:
        value = bytes(data[offset:offset + len(original)])
        if value not in (original, patched):
            return None
        flags.add(value == patched)
    return flags.pop() if len(flags) == 1 else None


def _legacy(data):
    """이전 판(v0.9086)이 설치한 상태면 그 자리 목록."""
    for sites in LEGACY_SITES:
        if all(bytes(data[o:o + len(p)]) == p for o, _, p in sites):
            return sites
    return None


def state(data) -> bool:
    now = _match(data, SITES)
    if now is not None:
        return now
    if _legacy(data):
        return True
    raise ValueError("생산 나눠 맡기기 패치: 불완전하거나 알 수 없는 변경이 있습니다.")


def transform(data, enabled=True) -> bytes:
    out = bytearray(data)
    if _match(data, SITES) is None:
        old = _legacy(data)
        if not old:
            raise ValueError("생산 나눠 맡기기 패치: 불완전하거나 알 수 없는 변경이 있습니다.")
        for offset, original, _ in old:                # 이전 판을 걷어냄
            out[offset:offset + len(original)] = original
    for offset, original, patched in SITES:
        out[offset:offset + len(original)] = patched if enabled else original
    return bytes(out)


# 이전 판이 설치한 상태 — 걷어낼 때 인식: (파일 오프셋, 원래, 바꾼 것)
LEGACY_SITES = (
    (   # v0.9086 시험판 (집결지 동시 지정 전)
        (0x33603, bytes.fromhex("33c9668b883a5a770085c97405e9c8050000"), bytes.fromhex("8a88485a77003a0dcc12b4000f85c8050000")),
        (0x33ad8, bytes.fromhex("7518"), bytes.fromhex("9090")),
        (0x47cf0, bytes.fromhex("558bec83ec40"), bytes.fromhex("e9cb3f0a0090")),
        (0x6049f, bytes.fromhex("0fbf05d012b40069c0380100000fbf883e5a770081e10010000085c9744b"), bytes.fromhex("803d3c088000017760a1d012b4009869c038010000f6803f5a770010744b")),
        (0xebcc0, bytes(64), bytes.fromhex("817c240408400000751a608a54242c80fa05740a80fa06740580fa0a7505e9e5fcffff615589e583ec40e907c0f5ff9090909090909090909090909090909090")),
        (0xeb9c8, bytes(56), bytes.fromhex("0fbf05d012b40085c00f840c03000089c369e8380100000fbfad465a7700e8e5fdffff89c78b356e3643000fbf0d3c088000e951ffffff90")),
        (0xeb950, bytes(48), bytes.fromhex("49781466ad9850e874feffff39f87304978b1c2458ebe983ff40730566895c2428e96d03000090909090909090909090")),
        (0xeb7d0, bytes(48), bytes.fromhex("5669f03801000081c6385a77006a405866837e08007e158a66103a25cc12b400750a66396e0e0f84d40000005ec39090")),
        (0xeb8d0, bytes(48), bytes.fromhex("0fb74606f6c410741880fa057515663d0510750f0fbe4652403c057206b040eb0231c05ec39090909090909090909090")),
    ),
    (   # v0.9086
        (0x33603, bytes.fromhex("33c9668b883a5a770085c97405e9c8050000"), bytes.fromhex("8a88485a77003a0dcc12b4000f85c8050000")),
        (0x33ad8, bytes.fromhex("7518"), bytes.fromhex("9090")),
        (0x47cf0, bytes.fromhex("558bec83ec40"), bytes.fromhex("e9d13c0a0090")),
        (0x6049f, bytes.fromhex("0fbf05d012b40069c0380100000fbf883e5a770081e10010000085c9744b"), bytes.fromhex("803d3c088000017760a1d012b4009869c038010000f6803f5a770010744b")),
        (0x47e60, bytes.fromhex("558bec83ec44"), bytes.fromhex("e9dc380a0090")),
        (0xeb9c6, bytes(58), bytes.fromhex("817c240408400000751a608a54242c80fa05740a80fa06740580fa0a7505e9d2020000615589e583ec40e901c3f5ff9090909090909090909090")),
        (0xebcbb, bytes(69), bytes.fromhex("0fbf05d012b40085c00f841ffdffff89c369e8380100000fbfad465a7700e870fcffff89c78b356e3643000fbf0d3c088000e973ffffff9090909090909090909090909090")),
        (0xebc65, bytes(27), bytes.fromhex("490f888402000066ad9850e8d9fcffff39f87304978b1c2458ebe5")),
        (0xebef0, bytes(16), bytes.fromhex("83ff40730566895c2428e9eafaffff90")),
        (0xeb94e, bytes(50), bytes.fromhex("5669f03801000081c6385a77006a405866837e08007e158a66103a25cc12b400750a66396e0e0f846cfcffff5ec390909090")),
        (0xeb5e6, bytes(26), bytes.fromhex("0fb74606f6c410740a80fa057507e97f01000031c05ec3909090")),
        (0xeb778, bytes(24), bytes.fromhex("663d0510750b0fbe4652403c057202b0405ec39090909090")),
        (0xeb741, bytes(31), bytes.fromhex("807c2404037509803d3c08800001777f5589e583ec44e90ac7f5ff90909090")),
        (0xeb7d0, bytes(48), bytes.fromhex("600fbf1dd012b40069c3380100000fbfa8465a77008b356e3643000fbf3d3c088000b206e91b04000090909090909090")),
        (0xebc14, bytes(44), bytes.fromhex("4f781b66ad9850e82efdffff5983f84072073d0010000072e7e99efcffff66891dd012b40061c39090909090")),
        (0xeb8d0, bytes(48), bytes.fromhex("66890dd012b400ff742430ff742430ff742430ff742430e865feffff83c410b206e91e03000090909090909090909090")),
    ),
)

SITES = _sites()
