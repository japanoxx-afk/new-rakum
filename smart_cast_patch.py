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

(3) 미니맵 시야 표시 (v0.9100~, 0x49BE70 의 call 0x469030 을 가로챔). 미니맵 미리보기 패치(minimap_patch)는
    미니맵 그림(+0x1002C)을 지형 전체(+0x2C)로 채워 어디가 보이는 곳인지 구분이 없었다.
    시야 계산 함수 0x49B6A0 (틱마다 0x4D586D 에서 부름: 시야 지도 0x999DD0 을 지우고 유닛마다 다시 채움) 의 끝,
    유닛 점을 찍는 0x469030 직전에: 그림 = 지형 반 밝기, 내가(동맹 포함, 표 0x4F02A0[내 번호]) 지금 보는 칸만 원래 밝기.
    전체 보기([0xB412C8] & 1) 일 때는 그대로. 화면 전용 — 진행(시야 지도)은 읽기만 한다. 싱글·멀티 모두 같다.

(4) 공격이 없는 유닛의 A 키 (v0.9104~, 0x45CF82 = 버튼 칸 누르기 0x45CF60 의 앞부분).
    단축키 A,S,D,F,G,Z,X,C,V,B 는 아래 패널의 칸 번호 0..9 이다 (0x42F43B 가 표 0x4FCD28 에서 찾아 0x465890 -> 0x45CF60(칸)).
    칸의 명령은 패널 +0x1BA + 칸*2 (R1_DATA_MENU.STB; 기본 유닛은 A 공격 1, S 정지 2, D 이동 3, F 순찰 4, G 고정 5).
    공격이 없는 유닛(아스트리아 일꾼 곤, 라바, 마령가마, 나루, 디거웜, 네크로멘서 …)은 A 칸이 비어 A 키가 아무 일도 하지 않았다.
    A 칸이 비어 있고 D 칸이 이동(3)이면 A 를 D(이동)로 처리한다 — 공격할 수 없는 유닛의 '공격 이동' 은 이동. 건물은 그대로.
    보내는 명령은 원래의 이동 명령이라 대전 진행에는 영향이 없다.

(5) 로비 BGM 끄기를 기억 (v0.9107~). 로비의 BGM 버튼(0x4214AF)은 지금 나오는 음악을 끄거나 다시 틀 뿐 기억하지 않아,
    다른 화면에 갔다 오거나 게임을 다시 켜면 메뉴 음악이 다시 나왔다 (메뉴 폼들이 열릴 때마다 0x49D150 으로 튼다).
    버튼을 누를 때 게임의 설정 저장 함수(0x425B70, 레지스트리 HKLM SOFTWARE\\TriggerSoft\\RhakMu — KeyScroll·BGM 등을 두는 곳)로
    'MenuBGMOff' = 1(끔)/0(켬) 을 적고, 음악 틀기 0x49D150 의 머리에서, 부른 곳이 메뉴 쪽(복귀 주소 < 0x4D7400 — 시작할 때 트는 0x4D71D3 포함; 경기 음악은 0x4D74E0..)이고 그 값이 1 이면 틀지 않는다.
    경기 중 음악(게임 안 옵션의 BGM 음량)은 건드리지 않는다.

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

SITE3 = 0x9BE70                                           # 시야 계산 끝의 call 0x469030 (미니맵 유닛 점 찍기)
SITE3_ORIGINAL = bytes.fromhex("e8bbd1fcff")
VISIBLE, PLAYER_BITS, LOCAL_PLAYER, MAP_W, MAP_H, DRAW_DOTS = 0x999DD0, 0x4F02A0, 0xB412CC, 0xB412D4, 0xB412D6, 0x469030

SOURCE3 = f"""
entry:                                       /* ecx = 미니맵 객체 (0x469030 의 this) */
    test byte ptr [0xb412c8], 1              /* 전체 보기 */
    jne dots
    test ecx, ecx
    je dots
    pushfd
    pushal
    mov ebx, ecx
    mov eax, dword ptr [0x4ec438]
    mov edx, dword ptr [eax+0x38]            /* 반 밝기 마스크 (게임이 쓰는 값) */
    lea esi, [ebx+0x2c]
    lea edi, [ebx+0x1002c]
    mov ecx, 0x4000
    cld
half:
    lodsw
    and eax, edx
    shr eax, 1
    stosw
    dec ecx
    jne half
    movsx eax, byte ptr [{LOCAL_PLAYER}]
    movzx ebp, byte ptr [eax*2+{PLAYER_BITS}]
    xor edx, edx
row:
    movsx eax, word ptr [{MAP_H}]
    cmp edx, eax
    jge done
    cmp edx, 519
    jge done
    movzx edi, word ptr [ebx+edx*2+0x20664]  /* 이 줄의 미니맵 y */
    cmp edi, 128
    jae nextrow
    imul esi, edx, 0x208
    add esi, {VISIBLE}
    xor ecx, ecx
cell:
    movsx eax, word ptr [{MAP_W}]
    cmp ecx, eax
    jge nextrow
    cmp ecx, 519
    jge nextrow
    movzx eax, byte ptr [esi+ecx]
    test eax, ebp
    je nextcell
    push ecx
    push edx
    push esi
    push edi
    movzx eax, word ptr [ebx+ecx*2+0x20254]  /* 미니맵 x */
    cmp eax, 128
    jae skip
    movzx esi, word ptr [ebx+ecx*2+0x20256]  /* 다음 칸의 x 까지 채운다 (작은 맵은 한 칸이 여러 점): 너비 1..4 */
    sub esi, eax
    dec esi
    cmp esi, 3
    jbe wok
    xor esi, esi
wok:
    inc esi
    movzx ecx, word ptr [ebx+edx*2+0x20666]  /* 높이 1..4 */
    sub ecx, edi
    dec ecx
    cmp ecx, 3
    jbe vloop
    xor ecx, ecx
vloop:
    cmp edi, 128
    jae skip
    mov edx, edi
    shl edx, 8
    lea edx, [edx+eax*2]
    push esi
    push eax
hloop:
    cmp eax, 128
    jae hend
    push ecx
    mov cx, word ptr [ebx+edx+0x2c]
    mov word ptr [ebx+edx+0x1002c], cx
    pop ecx
    inc eax
    add edx, 2
    dec esi
    jne hloop
hend:
    pop eax
    pop esi
    inc edi
    dec ecx
    jns vloop
skip:
    pop edi
    pop esi
    pop edx
    pop ecx
nextcell:
    inc ecx
    jmp cell
nextrow:
    inc edx
    jmp row
done:
    popal
    popfd
dots:
    push {DRAW_DOTS}
    ret
"""

SITE4 = 0x5CF82                                           # 버튼 칸 누르기 0x45CF60 의 '칸 읽기' (movsx ecx,[ebp+8]; mov edx,[ebp-4])
SITE4_ORIGINAL = bytes.fromhex("0fbf4d088b55fc")

SOURCE4 = f"""
entry:                                       /* 0x45CF82 대신: 누른 칸(인자 [ebp+8]), 패널 [ebp-4] */
    movsx ecx, word ptr [ebp+8]
    mov edx, dword ptr [ebp-4]
    test ecx, ecx
    jne back                                 /* A 칸(0)만 */
    cmp word ptr [edx+0x1ba], 0
    jne back                                 /* 공격 버튼이 있으면 그대로 */
    cmp word ptr [edx+0x1be], 3
    jne back                                 /* D 칸이 '이동'(명령 3)일 때만 */
    movsx eax, word ptr [0xb412d0]
    test eax, eax
    jle back
    imul eax, eax, 0x138
    cmp word ptr [eax+0x775a3a], 0
    jne back                                 /* 건물은 그대로 */
    mov ecx, 2
    mov word ptr [ebp+8], cx
back:
    push 0x45cf89
    ret
"""

SITE5 = 0x9D150                                           # 음악 틀기 0x49D150 의 머리 (push ebp; mov ebp,esp; sub esp,0x48)
SITE5_ORIGINAL = bytes.fromhex("558bec83ec48")
SITE6 = 0x214AF                                           # 로비 BGM 버튼 처리 (0x4214AF..0x4214F0)
SITE6_ORIGINAL = bytes.fromhex("833d285cae00007438a1285cae0033c98a889801000085c9740d8b0d285cae00e8ecbc0700eb1a"
                               "6a018b0d285cae00e86dbc07006a078b0d285cae00e810bd0700")
TOGGLE_OFFSET = 0x80                                      # CODE5 안에서 toggle 이 놓이는 자리

SOURCE5 = f"""
start_music:                                 /* 0x49D150 (음악 틀기, 인자 = 곡 번호) 의 머리 */
    cmp dword ptr [esp], 0x4d7400
    jae go                                   /* 경기 음악(부른 곳이 게임 루프 0x4D74E0·0x4D74EF·0x4D74FE)은 그대로 */
    pushal
    call here1
here1:
    pop eax
    add eax, name - here1
    push eax
    mov ecx, 0x6e0ce0
    mov eax, 0x425ad0                        /* 레지스트리 정수 읽기 (없으면 0) */
    call eax
    test eax, eax
    popal
    jne muted
go:
    push ebp
    mov ebp, esp
    sub esp, 0x48
    push 0x49d156
    ret
muted:
    ret 4

    .balign 0x80, 0x90
toggle:                                      /* 0x4214AF (로비 BGM 버튼: 나오는 중이면 끄고, 아니면 튼다) 대신 */
    cmp dword ptr [0xae5c28], 0
    je out
    call here2
here2:
    pop ebx
    add ebx, name - here2
    mov eax, dword ptr [0xae5c28]
    cmp byte ptr [eax+0x198], 0
    je play
    mov ecx, eax
    mov eax, 0x49d1c0                        /* 끄기 */
    call eax
    push 1
    push ebx
    mov ecx, 0x6e0ce0
    mov eax, 0x425b70                        /* 레지스트리 정수 쓰기: 꺼 둠 */
    call eax
    jmp out
play:
    push 0
    push ebx
    mov ecx, 0x6e0ce0
    mov eax, 0x425b70                        /* 켜 둠 (먼저 적어야 아래 0x49D150 이 튼다) */
    call eax
    push 1
    mov ecx, dword ptr [0xae5c28]
    mov eax, 0x49d150
    call eax
    push 7
    mov ecx, dword ptr [0xae5c28]
    mov eax, 0x49d200
    call eax
out:
    push 0x4214f0
    ret
name:
    .asciz "MenuBGMOff"
"""

# SOURCE·SOURCE2·SOURCE3·SOURCE4·SOURCE5 를 조립한 것 (test_smart_cast_patch 가 keystone 으로 다시 조립해 같은지 본다)
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
CODE3 = bytes.fromhex(
    "f605c812b400010f851a01000085c90f84120100009c6089cba138c44e008b50388d732c8dbb2c000100b900"
    "400000fc66ad21d0d1e866ab4975f50fbe05cc12b4000fb62c45a0024f0031d20fbf05d612b40039c20f8dca"
    "00000081fa070200000f8dbe0000000fb7bc536406020081ff800000000f83a400000069f20802000081c6d0"
    "9d990031c90fbf05d412b40039c10f8d8700000081f9070200007d7f0fb6040e85e87471515256570fb7844b"
    "540202003d80000000735a0fb7b44b5602020029c64e83fe03760231f6460fb78c536606020029f94983f903"
    "760231c981ff80000000732d89fac1e2088d144256503d80000000731651668b4c132c66898c132c00010059"
    "4083c2024e75e3585e474979cb5f5e5a5941e96affffff42e927ffffff619d6830904600c3"
)
CODE2_OFFSET = 0x200                                      # 섹션 안에서 CODE2 가 놓이는 자리
CODE3_OFFSET = 0x400                                      # CODE3 (미니맵 시야)
CODE4 = bytes.fromhex("0fbf4d088b55fc85c975386683baba01000000752e6683babe0100000375240fbf05d012b40085c07e1969c0380100006683b83a5a7700007509b90200000066894d086889cf4500c3")
CODE4_OFFSET = 0x580                                      # CODE4 (공격 없는 유닛의 A 키)
CODE5 = bytes.fromhex(
    "813c2400744d00731f60e8000000005881c0de00000050b9e00c6e00b8d05a4200ffd085c061750c5589e583"
    "ec486856d14900c3c204006666666666662e0f1f8400000000006666666666662e0f1f840000000000666666"
    "6666662e0f1f8400000000006666666666662e0f1f840000000000666666662e0f1f840000000000833d285c"
    "ae0000745ee8000000005b83c35fa1285cae0080b89801000000741a89c1b8c0d14900ffd06a0153b9e00c6e"
    "00b8705b4200ffd0eb2d6a0053b9e00c6e00b8705b4200ffd06a018b0d285cae00b850d14900ffd06a078b0d"
    "285cae00b800d24900ffd068f0144200c34d656e7542474d4f666600"
)
CODE5_OFFSET = 0x600                                      # CODE5 (메뉴 음악 끄기 기억): 머리 +0, 버튼 +TOGGLE_OFFSET

# 이전 판이 설치한 상태 — 걷어낼 때 인식: (섹션 내용, 그때 바꾼 자리 목록)
LEGACY = (
    (bytes.fromhex("600fb74424248d90dfdfffff83fa3f0f87540100000fb6d06bd21483baccf84f00000f84410100000fbf0d3c08800083f9020f8c310100002d202000006bc0148b982802500085db0f841b0100000fbf7b420fbf6b080fbf05d012b40085c00f8e0401000069c0380100006683b83a5a7700000f85f0000000668b90465a77008b356e3643006a0068ffffff7f490f888a00000066ad0fb7c085c074f089c369c03801000005385a770066837808007edc6639500e75d6668378020075cf530fbf9cb8fe00000039eb5b7cc151520fbf4818c1e1050fbf54244029d10fafc90fbf501ac1e205510fbf4c244629ca590fafd201d10fb7500681ea2120000083fa50770681c1000000403b4c24087308894c2408895c240c5a59e96fffffff585b85db7445a1a411b4008b504466c702024066c742020700c642040166895a0589c1b8c0944400ffd0ff742430ff742430ff742430ff742430e80d00000083c410b8d07b4400ffd061c3615589e583ec4068667d4400c3"), (0,)),              # v0.9096 시험판: 0x447D60 만, 대상 고르기 함수가 있는 마법만
    ((CODE.ljust(CODE2_OFFSET, bytes(1)) + CODE2), (0, 1)),          # v0.9097~v0.9099: 미니맵 시야 없음
    ((CODE.ljust(CODE2_OFFSET, bytes(1)) + CODE2).ljust(CODE3_OFFSET, bytes(1)) + CODE3, (0, 1, 2)),   # v0.9100~v0.9103
    (((CODE.ljust(CODE2_OFFSET, bytes(1)) + CODE2).ljust(CODE3_OFFSET, bytes(1)) + CODE3).ljust(CODE4_OFFSET, bytes(1)) + CODE4,
     (0, 1, 2, 3)),                                                                                      # v0.9104~v0.9106
)


def assemble() -> tuple:
    import re
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    return tuple(bytes(ks.asm(re.sub(r"/\*.*?\*/", "", text), addr=0x10000000)[0]) for text in (SOURCE, SOURCE2, SOURCE3, SOURCE4, SOURCE5))


def _body() -> bytes:
    body = CODE.ljust(CODE2_OFFSET, bytes(1)) + CODE2
    body = body.ljust(CODE3_OFFSET, bytes(1)) + CODE3
    body = body.ljust(CODE4_OFFSET, bytes(1)) + CODE4
    return (body.ljust(CODE5_OFFSET, bytes(1)) + CODE5).ljust(SECTION_SIZE, bytes(1))


# (파일 오프셋, 원래 바이트, 섹션 안 들어갈 자리) — 원래가 call(5바이트)이면 call 로, 함수 머리(6바이트)면 jmp + nop 로 바꾼다
SITES = ((SITE, SITE_ORIGINAL, 0), (SITE2, SITE_ORIGINAL, CODE2_OFFSET), (SITE3, SITE3_ORIGINAL, CODE3_OFFSET),
         (SITE4, SITE4_ORIGINAL, CODE4_OFFSET), (SITE5, SITE5_ORIGINAL, CODE5_OFFSET),
         (SITE6, SITE6_ORIGINAL, CODE5_OFFSET + TOGGLE_OFFSET))


def _jump(site, section_va, offset):
    rel = struct.pack("<i", (0x400000 + section_va + offset) - (0x400000 + site + 5))
    if site == SITE3:
        return b"\xe8" + rel
    return (b"\xe9" + rel).ljust(next(len(original) for at, original, _ in SITES if at == site), b"\x90")


def _installed(data, va, body):
    """섹션 내용과 바꾼 자리가 지금 판 또는 이전 판과 맞으면 True."""
    heads = [bytes(data[site:site + len(original)]) for site, original, _ in SITES]
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
    if all(bytes(data[site:site + len(original)]) == original for site, original, _ in SITES):
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
