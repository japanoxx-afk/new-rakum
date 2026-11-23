"""마법 순차 시전 (스타크래프트2 방식, Rhakmu.exe 1.000d).

같은 마법 유닛을 여러 기 고르고 대상을 찍는 마법을 쓰면 원래는 고른 유닛이 모두 시전한다.
이 패치는 한 번 쓸 때마다 한 기만 시전하게 한다 (다시 쓰면 다음 유닛).

분석:
  대상이 있는 명령(공격·마법 등)은 0x447D60(명령 word, 대상 word, 층 byte, 지점 dword) 이 명령 0x4009
  [0x4009][0x0D][명령 w][대상 w][층 b][지점 dword] 을 보낸다 (마우스 0x43138C, 미니맵 0x46801A, 패널 0x46F911 …).
  받는 쪽 0x4407E0 -> 0x4425E0 은 '그 플레이어의 선택 목록'(플레이어 +0x34 개수, +0x36 목록)에 든 유닛마다
  유닛 +6(현재 명령)에 명령을 넣는다. 선택 목록은 선택 명령 0x4002 [0x4002][5+2n][n b][번호 w…] (0x447BD0) 로 바뀐다.
  마법 명령은 0x2021 이상: 마법 자료 M = [0x500228 + (명령-0x2020)*0x14], M+8 = 드는 마나(word),
  M+0x42 = 마나 칸 번호 -> 유닛 word [+0xFE + 칸*4] 가 지금 마나 (0x476CA0 이 시전 직전에 이 둘을 비교).
  유닛 마법은 0x2021..0x2060 (0x2061 이상은 건물 마법, 0x4425E0 이 따로 처리).
  대상을 찍지 않고 누르자마자 쓰는 마법은 버튼 함수 0x474200 이 0x447E10(0x400D, 마법 번호 byte) 로 명령 0x400D
  [0x400D][5][번호 b] 를 보낸다 (번호 = 명령 - 0x2020). 받는 쪽 0x442490 은 선택 목록의 유닛(건물 아님)마다
  마법 함수 [0x500234 + 번호*0x14](유닛, 0, 번호) 를 부른다. 0x447E10 은 다른 명령(0x473FCB 등)도 보내는 공용 함수.

패치 (보내는 쪽만) — 두 곳의 머리를 새 섹션 .scast 로:
  (1) 0x447D60 (대상을 찍는 마법). 유닛 마법이고 둘 이상 골랐을 때:
    고른 유닛 중 보이는 유닛([0xB412D0])과 같은 종류·살아 있음·마나가 충분한 것 가운데
    아직 마법을 쓰러 가는 중이 아닌 것 먼저, 그중 찍은 지점에 가까운 것을 하나 고른다.
  (2) 0x447E10 (누르자마자 쓰는 마법, 명령 0x400D 일 때만). 유닛 마법이고 마나가 드는 마법이며 둘 이상 골랐을 때:
    같은 조건의 유닛 가운데 마나가 가장 많은 것을 고른다 (쓰면 마나가 줄어 다음에는 다른 유닛 차례).
    마나가 들지 않는 것(변신·자세 바꾸기 등)은 그대로 모두에게 — 하나씩 하면 같은 유닛만 되풀이하게 된다.
  고른 뒤: 선택 명령 [그 유닛 하나] -> 원래 명령 -> 선택 명령 [원래 고른 전부](0x447BD0) 를 차례로 보낸다.
  고를 유닛이 없으면(마나 부족 등) 원래대로 보낸다. 공격·이동 등 다른 명령은 그대로.
  세 명령 모두 게임이 원래 쓰는 명령이라 상대 PC 가 이 패치를 쓰지 않아도 대전 진행은 같다 (리플레이에도 그대로 남는다).
  화면의 선택(0x80083C…)은 바뀌지 않는다.

섹션은 맨 뒤(.hotkey 뒤)에 붙인다. 코드는 자기 위치와 무관하게 짰다 (게임 주소는 절대값, 안에서는 상대 점프).
다른 패치의 검증 전에 strip() 으로 먼저 걷어낸다.
"""
from __future__ import annotations

import struct

from hotkey_patch import _layout, _u32

SITE_VA = 0x447D60
SITE = 0x47D60
SITE_ORIGINAL = bytes.fromhex("558bec83ec40")          # push ebp; mov ebp,esp; sub esp,0x40
SITE2_VA = 0x447E10                                       # 누르자마자 쓰는 마법 (명령 0x400D) 보내기 — 머리가 같다
SITE2 = 0x47E10
SECTION_NAME = b".scast\0\0"
SECTION_SIZE = 0x1000
CHARACTERISTICS = 0x60000020                              # code | execute | read

UNITS, SHOWN, SEL_COUNT, SEL_LIST_PTR = 0x775A38, 0xB412D0, 0x80083C, 0x43366E
NET, SEND, SEND_SELECTION = 0xB411A4, 0x4494C0, 0x447BD0
MAGIC_TABLE = 0x500228
FIRST_MAGIC, LAST_UNIT_MAGIC, LAST_MAGIC = 0x2021, 0x2060, 0x2071
BUSY = 0x40000000                                         # 이미 마법을 쓰러 가는 유닛은 뒤로

SOURCE = f"""
entry:
    pushal                                   /* 인자: [esp+0x24] 명령, +0x28 대상, +0x2c 층, +0x30 지점 */
    movzx eax, word ptr [esp+0x24]
    lea edx, [eax-{FIRST_MAGIC}]
    cmp edx, {LAST_UNIT_MAGIC - FIRST_MAGIC}
    ja plain
    movsx ecx, word ptr [{SEL_COUNT}]
    cmp ecx, 2
    jl plain
    sub eax, 0x2020
    imul eax, eax, 0x14
    mov ebx, dword ptr [eax+{MAGIC_TABLE}]
    test ebx, ebx
    jz plain
    movsx edi, word ptr [ebx+0x42]           /* 마나 칸 */
    movsx ebp, word ptr [ebx+8]              /* 드는 마나 */
    movsx eax, word ptr [{SHOWN}]
    test eax, eax
    jle plain
    imul eax, eax, 0x138
    cmp word ptr [eax+{UNITS + 2}], 0        /* 건물이면 그대로 */
    jne plain
    mov dx, word ptr [eax+{UNITS + 0xE}]     /* 종류 */
    mov esi, dword ptr [{SEL_LIST_PTR}]      /* 선택 목록 (.sel24 가 옮긴 자리도 따라감) */
    push 0                                   /* [esp+4] 고른 유닛 */
    push 0x7fffffff                          /* [esp]   그 점수 (작을수록 좋음) */
next:
    dec ecx
    js picked
    lodsw
    movzx eax, ax
    test eax, eax
    jz next
    mov ebx, eax
    imul eax, eax, 0x138
    add eax, {UNITS}
    cmp word ptr [eax+8], 0
    jle next
    cmp word ptr [eax+0xe], dx
    jne next
    cmp word ptr [eax+2], 0
    jne next
    push ebx
    movsx ebx, word ptr [eax+edi*4+0xfe]
    cmp ebx, ebp
    pop ebx
    jl next
    push ecx
    push edx
    movsx ecx, word ptr [eax+0x18]           /* 유닛 칸 -> 픽셀, 찍은 지점까지 거리² */
    shl ecx, 5
    movsx edx, word ptr [esp+0x40]           /* 지점 x (pushal 0x20 + 반환 4 + 인자 0xc + 넣어 둔 0x10) */
    sub ecx, edx
    imul ecx, ecx
    movsx edx, word ptr [eax+0x1a]
    shl edx, 5
    push ecx
    movsx ecx, word ptr [esp+0x46]           /* 지점 y */
    sub edx, ecx
    pop ecx
    imul edx, edx
    add ecx, edx
    movzx edx, word ptr [eax+6]              /* 이미 마법 명령을 받은 유닛은 뒤로 */
    sub edx, {FIRST_MAGIC}
    cmp edx, {LAST_MAGIC - FIRST_MAGIC}
    ja idle
    add ecx, {BUSY}
idle:
    cmp ecx, dword ptr [esp+8]
    jae worse
    mov dword ptr [esp+8], ecx
    mov dword ptr [esp+0xc], ebx
worse:
    pop edx
    pop ecx
    jmp next
picked:
    pop eax
    pop ebx                                  /* 고른 유닛 */
    test ebx, ebx
    jz plain
    mov eax, dword ptr [{NET}]               /* 선택 명령: 그 유닛 하나 */
    mov edx, dword ptr [eax+0x44]
    mov word ptr [edx], 0x4002
    mov word ptr [edx+2], 7
    mov byte ptr [edx+4], 1
    mov word ptr [edx+5], bx
    mov ecx, eax
    mov eax, {SEND}
    call eax
    push dword ptr [esp+0x30]                /* 원래 마법 명령 */
    push dword ptr [esp+0x30]
    push dword ptr [esp+0x30]
    push dword ptr [esp+0x30]
    call original
    add esp, 0x10
    mov eax, {SEND_SELECTION}                /* 선택 명령: 원래 고른 전부 */
    call eax
    popal
    ret
plain:
    popal
original:
    push ebp
    mov ebp, esp
    sub esp, 0x40
    push {SITE_VA + 6}
    ret
"""

# 누르자마자 쓰는 마법: 0x447E10(명령 word, 번호 byte) 머리 대신
SOURCE2 = f"""
entry2:
    pushal                                   /* 인자: [esp+0x24] 명령, +0x28 마법 번호 */
    cmp word ptr [esp+0x24], 0x400d
    jne plain2
    movsx ecx, word ptr [{SEL_COUNT}]
    cmp ecx, 2
    jl plain2
    movzx eax, byte ptr [esp+0x28]
    test eax, eax
    jz plain2
    cmp eax, {LAST_UNIT_MAGIC - 0x2020}
    ja plain2
    imul eax, eax, 0x14
    mov ebx, dword ptr [eax+{MAGIC_TABLE}]
    test ebx, ebx
    jz plain2
    movsx edi, word ptr [ebx+0x42]           /* 마나 칸 */
    movsx ebp, word ptr [ebx+8]              /* 드는 마나 */
    test ebp, ebp
    jle plain2                               /* 마나가 들지 않는 것은 모두에게 */
    movsx eax, word ptr [{SHOWN}]
    test eax, eax
    jle plain2
    imul eax, eax, 0x138
    cmp word ptr [eax+{UNITS + 2}], 0
    jne plain2
    mov dx, word ptr [eax+{UNITS + 0xE}]
    mov esi, dword ptr [{SEL_LIST_PTR}]
    push 0                                   /* [esp+4] 고른 유닛 */
    push 0                                   /* [esp]   그 유닛의 마나 (많을수록 좋음) */
next2:
    dec ecx
    js picked2
    lodsw
    movzx eax, ax
    test eax, eax
    jz next2
    mov ebx, eax
    imul eax, eax, 0x138
    add eax, {UNITS}
    cmp word ptr [eax+8], 0
    jle next2
    cmp word ptr [eax+0xe], dx
    jne next2
    cmp word ptr [eax+2], 0
    jne next2
    movsx eax, word ptr [eax+edi*4+0xfe]
    cmp eax, ebp
    jl next2
    cmp eax, dword ptr [esp]
    jle next2
    mov dword ptr [esp], eax
    mov dword ptr [esp+4], ebx
    jmp next2
picked2:
    pop eax
    pop ebx
    test ebx, ebx
    jz plain2
    mov eax, dword ptr [{NET}]               /* 선택 명령: 그 유닛 하나 */
    mov edx, dword ptr [eax+0x44]
    mov word ptr [edx], 0x4002
    mov word ptr [edx+2], 7
    mov byte ptr [edx+4], 1
    mov word ptr [edx+5], bx
    mov ecx, eax
    mov eax, {SEND}
    call eax
    push dword ptr [esp+0x28]                /* 원래 명령 */
    push dword ptr [esp+0x28]
    call original2
    add esp, 8
    mov eax, {SEND_SELECTION}                /* 선택 명령: 원래 고른 전부 */
    call eax
    popal
    ret
plain2:
    popal
original2:
    push ebp
    mov ebp, esp
    sub esp, 0x40
    push {SITE2_VA + 6}
    ret
"""

# SOURCE·SOURCE2 를 조립한 것 (test_smart_cast_patch 가 keystone 으로 다시 조립해 같은지 본다)
CODE = bytes.fromhex(
    "600fb74424248d90dfdfffff83fa3f0f87410100000fbf0d3c08800083f9020f8c310100002d202000006bc0"
    "148b982802500085db0f841b0100000fbf7b420fbf6b080fbf05d012b40085c00f8e0401000069c038010000"
    "6683b83a5a7700000f85f0000000668b90465a77008b356e3643006a0068ffffff7f490f888a00000066ad0f"
    "b7c085c074f089c369c03801000005385a770066837808007edc6639500e75d6668378020075cf530fbf9cb8"
    "fe00000039eb5b7cc151520fbf4818c1e1050fbf54244029d10fafc90fbf501ac1e205510fbf4c244629ca59"
    "0fafd201d10fb7500681ea2120000083fa50770681c1000000403b4c24087308894c2408895c240c5a59e96f"
    "ffffff585b85db7445a1a411b4008b504466c702024066c742020700c642040166895a0589c1b8c0944400ff"
    "d0ff742430ff742430ff742430ff742430e80d00000083c410b8d07b4400ffd061c3615589e583ec4068667d"
    "4400c3"
)
CODE2 = bytes.fromhex(
    "6066817c24240d400f85050100000fbf0d3c08800083f9020f8cf50000000fb644242885c00f84e800000083"
    "f8400f87df0000006bc0148b982802500085db0f84ce0000000fbf7b420fbf6b0885ed0f8ebe0000000fbf05"
    "d012b40085c00f8eaf00000069c0380100006683b83a5a7700000f859b000000668b90465a77008b356e3643"
    "006a006a0049784466ad0fb7c085c074f489c369c03801000005385a770066837808007ee06639500e75da66"
    "8378020075d30fbf84b8fe00000039e87cc73b04247ec2890424895c2404ebb9585b85db743da1a411b4008b"
    "504466c702024066c742020700c642040166895a0589c1b8c0944400ffd0ff742428ff742428e80d00000083"
    "c408b8d07b4400ffd061c3615589e583ec4068167e4400c3"
)
CODE2_OFFSET = 0x200                                      # 섹션 안에서 CODE2 가 놓이는 자리

# 이전 판이 설치한 상태 — 걷어낼 때 인식: (섹션 내용, 그때 바꾼 자리 목록)
LEGACY = (
    (bytes.fromhex("600fb74424248d90dfdfffff83fa3f0f87540100000fb6d06bd21483baccf84f00000f84410100000fbf0d3c08800083f9020f8c310100002d202000006bc0148b982802500085db0f841b0100000fbf7b420fbf6b080fbf05d012b40085c00f8e0401000069c0380100006683b83a5a7700000f85f0000000668b90465a77008b356e3643006a0068ffffff7f490f888a00000066ad0fb7c085c074f089c369c03801000005385a770066837808007edc6639500e75d6668378020075cf530fbf9cb8fe00000039eb5b7cc151520fbf4818c1e1050fbf54244029d10fafc90fbf501ac1e205510fbf4c244629ca590fafd201d10fb7500681ea2120000083fa50770681c1000000403b4c24087308894c2408895c240c5a59e96fffffff585b85db7445a1a411b4008b504466c702024066c742020700c642040166895a0589c1b8c0944400ffd0ff742430ff742430ff742430ff742430e80d00000083c410b8d07b4400ffd061c3615589e583ec4068667d4400c3"), (0,)),              # v0.9096 시험판: 0x447D60 만, 대상 고르기 함수가 있는 마법만
)


def assemble() -> tuple[bytes, bytes]:
    import re
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    return tuple(bytes(ks.asm(re.sub(r"/\*.*?\*/", "", text), addr=0x10000000)[0]) for text in (SOURCE, SOURCE2))


def _body() -> bytes:
    return (CODE.ljust(CODE2_OFFSET, bytes(1)) + CODE2).ljust(SECTION_SIZE, bytes(1))


# (파일 오프셋, 원래 머리, 섹션 안 들어갈 자리)
SITES = ((SITE, SITE_ORIGINAL, 0), (SITE2, SITE_ORIGINAL, CODE2_OFFSET))


def _jump(site, section_va, offset):
    return b"\xe9" + struct.pack("<i", (0x400000 + section_va + offset) - (0x400000 + site + 5)) + b"\x90"


def _installed(data, va, body):
    """섹션 내용과 바꾼 자리가 지금 판 또는 이전 판과 맞으면 True."""
    heads = [bytes(data[site:site + 6]) for site, _, _ in SITES]
    if body == _body():
        return heads == [_jump(site, va, offset) for site, _, offset in SITES]
    for code, used in LEGACY:
        if body == code.ljust(SECTION_SIZE, bytes(1)):
            return heads == [_jump(site, va, offset) if k in used else original
                             for k, (site, original, offset) in enumerate(SITES)]
    return False


def state(data) -> bool:
    """패치 적용 여부 (이전 판이 설치한 상태도 True — apply() 가 지금 판으로 바꾼다). 알 수 없는 상태면 ValueError."""
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    name, va, vsize, rptr, rsize, _ = secs[-1]
    if name == SECTION_NAME:
        if (rsize == SECTION_SIZE and vsize == SECTION_SIZE and rptr + rsize == len(data)
                and _u32(data, soi) == va + SECTION_SIZE and _installed(data, va, bytes(data[rptr:rptr + rsize]))):
            return True
        raise ValueError("마법 순차 시전 패치가 불완전하거나 알 수 없는 변경이 있습니다.")
    if all(bytes(data[site:site + 6]) == original for site, original, _ in SITES):
        return False
    raise ValueError("마법 순차 시전 패치: 지원하지 않는 게임 파일입니다.")


def current(data) -> bool:
    """지금 판이 그대로 들어 있으면 True (런처가 실행 전에 확인)."""
    if not state(data):
        return False
    name, va, vsize, rptr, rsize, _ = _layout(data)[6][-1]
    return bytes(data[rptr:rptr + rsize]) == _body()


def strip(data) -> bytes:
    """패치를 걷어낸 상태 (다른 패치들의 검증 전에 사용)."""
    if not state(data):
        return bytes(data)
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    name, va, vsize, rptr, rsize, h = secs[-1]
    out = bytearray(data[:rptr])
    for site, original, _ in SITES:
        out[site:site + len(original)] = original
    out[h:h + 40] = bytes(40)
    struct.pack_into("<H", out, nt + 6, nsec - 1)
    struct.pack_into("<I", out, soi, va)
    return bytes(out)


def apply(data, enabled: bool = True) -> bytes:
    out = bytearray(strip(data))
    if not enabled:
        return bytes(out)
    nt, nsec, table, salign, falign, soi, secs = _layout(out)
    _, va, vsize, rptr, rsize, _ = secs[-1]
    new_va = (va + max(vsize, rsize) + salign - 1) // salign * salign
    if _u32(out, soi) != new_va:
        raise ValueError("마법 순차 시전 패치: 이미지 크기가 예상과 다릅니다.")
    if len(out) % falign or len(out) != rptr + rsize:
        raise ValueError("마법 순차 시전 패치: 파일 끝에 알 수 없는 데이터가 있습니다.")
    h = table + 40 * nsec
    if h + 40 > min(s[3] for s in secs) or any(out[h:h + 40]):
        raise ValueError("마법 순차 시전 패치: 섹션 헤더를 추가할 공간이 없습니다.")
    raw = len(out)
    out[h:h + 40] = SECTION_NAME + struct.pack("<IIIIIIHHI", SECTION_SIZE, new_va, SECTION_SIZE, raw,
                                              0, 0, 0, 0, CHARACTERISTICS)
    struct.pack_into("<H", out, nt + 6, nsec + 1)
    struct.pack_into("<I", out, soi, new_va + SECTION_SIZE)
    for site, original, offset in SITES:
        out[site:site + len(original)] = _jump(site, new_va, offset)
    out += _body()
    return bytes(out)
