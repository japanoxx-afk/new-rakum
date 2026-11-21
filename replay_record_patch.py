"""리플레이 패치 (Rhakmu.exe 1.000d) — 실제 게임 화면 리플레이의 기록과 재생.

대전은 모든 PC가 같은 명령을 같은 프레임에 실행하는 방식(lockstep)이다.
  Game_Loop 0x4D7310: 대전 준비(srand([0x6E1A78]) @0x4D7376 …) 뒤 0x4D7554 에서 게임 루프를 고른다.
  Game_Multi 0x4D7A80: 매 프레임 시뮬레이션, 5프레임마다 0x447AF0(내 턴 + rand 1회) → 0x44A840(턴 처리)
    → 0x4407E0(플레이어, 명령 묶음, 길이) (0x44AABC). 프레임 [0xB412B4], 프레임 시간 ms [0xB412B8].
  싱글/불러온 게임 루프 0x4D78E0 는 0x447AF0·0x44A840 을 매 프레임 부른다 (재생 때 5프레임마다로 맞춤).
  난수: CRT rand [0x501EC0], 엔진 난수 객체 0xB40FE8 (+0x10 LCG).
  저장: SaveGameData(이름) 0x4D9120 -> USERs\\<[0x6E61F4]>\\<이름>.SAV (그리고 [0x6E61F4] 를 내 플레이어 이름에 복사)
  지도 공개: 치트 비트 [0xB412C8]|1 + 0x4991E0(this=0x915698) — 안개는 PC마다 달라도 동기화에 영향 없음.
WangGun 리플레이(WGReplay.dll)와 같은 방식: 시작 상태는 게임 자체 저장, 그 뒤는 프레임별 명령과 검사값.

패치 (새 섹션 .rkrec, 위치 독립 코드):
  1) 0x44AABC call 0x4407E0 -> 기록 후 원래 함수 (플레이어 0..7: 명령 묶음)
  2) 0x4D7554 (게임 루프 직전) -> 기록: 시작 기록(0xFE) + (켜져 있으면) SaveGameData("RKREPLAY")
                                  재생: RKREPLAY.RKP 읽기, 난수·시드·프레임 되돌리기, 지도 공개
  3) 0x44A840 (턴 처리 시작) -> 기록: 검사값(0xFD) / 재생: 원래 턴 처리 건너뜀 (내 클릭·네트워크 무시)
  2") 재생: 저장에는 건물 시야 지도(0xDD5C0A, 건설 가능 판정 0x4373E0 이 씀)가 없어 불러온 뒤 비어 있다 ->
      살아 있는 유닛마다 0x4369F0(건물 시야 더하기; 건설 중 0x1004 제외)을 불러 다시 만든다.
      없으면 '그곳엔 건설을 할 수 없습니다'로 기록된 건설 명령이 실패해 경기가 달라진다.
  2') 재생: 저장을 불러온 뒤 [0xB412CB]=1 — 기록한 경기처럼 대전 루프(Game_Multi)로 돈다
      (대전 여부에 따라 AI 등 시뮬레이션이 달라 싱글 루프로는 첫 검사에서 어긋남).
  4) 0x447AF0 (내 턴 보내기) -> 재생: 5프레임마다 원래 함수와 같은 WinRandom(0, 0x7FFF, ...) 1회만 (보내기 0x4496C0 는
     받는 쪽이 없어 32턴 뒤 멈춤) + 기록된 명령 주입·검사값 비교·1/2/4 배속
  7) 0x4D65F3 call 0x463A20 (아래 패널 그리기) -> 재생 중 HUD 숨김(I 키)이면 건너뜀. 보일 때는 그리는 동안만
     내 번호 [0xB412CC] 를 고른 유닛([0xB412D0])의 주인으로 바꿔, 상대 건물의 생산·업그레이드 창과
     그 플레이어의 자원줄이 보이게 한다 (패널 코드가 '주인 == 나' 를 14곳에서 검사).
  11) 0x404D4A call 0x404C70 (채팅 글자 -> 치트 찾기) -> 'money', 'speed' 이면 치트 명령.
      대전([0xB412CB]=1)이면 0x448110(번호) 로 치트 명령 0x4013 을 모두에게 보내고(기록·재생에도 남음),
      싱글이면 바로 적용. 다른 글자는 원래 함수로.
  12) 0x440C65 call 0x404990 (명령 0x4013 실행) -> 번호 0x30/0x31 이면 보낸 플레이어([ebp+8])에게 적용.
      0x30 money: 금·물·카르마·글로리 +50000, 인구 최대 +1000 (1000 미만일 때, 인구 제한 해제).
      0x31 speed: 게임 자체 빠른 생산 치트 비트 [0xB412C8] & 8 켜기/끄기 (생산·건설·업그레이드 빠름, 모두에게).
      대전에서는 모든 PC가 이 판 런처여야 같은 결과가 된다.
  9) 0x4D6602 call 0x46A3B0 (미니맵 등) -> HUD 숨김이면 건너뜀
  10) 0x4D6DD4 (시작 방식 4 의 화면 크기 800x600) -> 재생 + 고해상도 패치면 대전처럼 1280x720
  8) 0x4D6607 call 0x4D4440 (마우스 그리기 직전) -> 재생: I 키로 HUD 켜기/끄기, 오른쪽 위에 참가자 자원·생산·업그레이드
     (게임 글자 그리기와 같은 방식: 뒤 화면 GetDC, 글꼴 [0x106AE3C], TextOutA). 생산 = 건물 명령 0x1005,
     업그레이드 = 0x1006/0x100A, +0x50 종류, +0x4C 진행(프레임), 전체 = [[0x4FCD88+종류*0x1C]+0x28].
  6) 0x4D6AA1 시작 방식 바이트 (원래 0 = 로그인 화면) -> 재생: 4 = 개발용 '저장 불러오기로 바로 게임' 방식
     (로그인·로비 없이 상태 2 -> Game_Loop). 온라인 게임이라 싱글 메뉴가 없어서 실행하자마자 재생.
  5) 0x4D7319 (Game_Loop 시작) -> 재생(싱글): 게임 자체 '저장 불러오기' 경로를 켬 ([0x6DFF8D]=1, 이름 0x6E62F4 = RKREPLAY,
     계정 이름 0x6E61F4 = RKREPLAY -> 저장 위치 GamePath\\USERs\\RKREPLAY\\RKREPLAY.SAV).
     시작 방식 4 에서는 [0xB412CB](대전 여부)가 0이 아니라서 재생 때는 0(싱글 루프)으로 둔다.
     -> 0x4D75A0, LoadGameData 0x4D8220(GamePath\\USERs\\<계정>\\RKREPLAY.SAV), 0x4D7880. 게임에 불러오기 메뉴가 없어서.

링 버퍼 (섹션 + BUF, 기록): +0 total +4 pos +0xC 기록 수, +0x10.. [u32 프레임][u8 플레이어][0][u16 길이][내용] (4바이트 맞춤)
재생 자료 (섹션 + BUF, 재생; RKREPLAY.RKP 그대로): 'RKP1', 기록 바이트 수, 읽은 위치, 시작 프레임, rand, 난수 객체 20,
  시드, 마지막 프레임 (+0x40 부터 기록, 형식은 링과 같음)
설정 (섹션 + FLAGS_OFF): +0 시작 저장 끄기, +4 저장 결과, +8 재생 모드, +0xC 어긋난 프레임(0 없음, 0xFFFFFFFF 자료 없음),
  +0x10 주입한 묶음 수
"""
from __future__ import annotations

import os
import struct

SECTION_NAME = b".rkrec\0\0"
DISPATCH = 0x4407E0
FRAME = 0xB412B4
CODE_SIZE = 0x1000
BUF = 0x1000
DATA = BUF + 0x10
RING = 0x200000
VIRTUAL_SIZE = (CODE_SIZE + 0x10 + RING + 0x1000 + 0xFFF) & ~0xFFF
CHARACTERISTICS = 0xE0000060
WRAP = 0xFFFFFFFF
MAX_BATCH = 0x4000
P_START, P_CHECK = 0xFE, 0xFD
SAVE_NAME = b"RKREPLAY"
PLAY_FILE = b"RKREPLAY.RKP"
OFF = {"dispatch": 0x000, "start": 0x080, "turn": 0x280, "put": 0x300, "hash": 0x380, "send": 0x400, "feed": 0x480, "load": 0x600, "vision": 0x6c0,
       "cheatexec": 0x40, "cheatmsg": 0x3C0, "cheatapply": 0x590, "cheatmatch": 0x740,
       "panel": 0xA00, "panel2": 0xA80, "overlay": 0xAB0, "text": 0xB30, "draw": 0xBB0,
       "grid": 0x664, "gridrec": 0x7E0, "keys": 0xB80}
DATA_OFF = 0xE00                          # 글자 형식·색 (코드 영역 안, 이름·설정·임시 0x800..0x9FF 뒤)
S_PLAYER, S_LINE, S_MAKE, S_UPG, S_CPU, COLORS = 0xE00, 0xE60, 0xE80, 0xE90, 0xEA0, 0xF00
W_MONEY, W_SPEED, S_MONEY, S_SPON, S_SPOFF = 0xEB0, 0xEB8, 0xF20, 0xF60, 0xF90
CHEAT_MONEY, CHEAT_SPEED = 0x30, 0x31
RES_OFF, RES_800, RES_1280 = 0xD6DD4, bytes.fromhex("68580200006820030000"), bytes.fromhex("68d00200006800050000")
HIGHRES_MARK = 0x237F8                    # 고해상도 패치가 대전 화면을 1280x720 으로 바꾼 자리
F_HIDE, F_KEYPREV = 0x20, 0x21            # FLAGS_OFF 기준 바이트: HUD 숨김, I 키 이전 상태
F_GRID, F_GRIDOK = 0x24, 0x28             # 비 효과 격자를 만들기 직전의 rand (기록), 기록했으면 1
NAME_OFF, PLAY_NAME_OFF, FLAGS_OFF, SCR_OFF = 0x800, 0x810, 0x820, 0x880
F_NOSAVE, F_SAVED, F_PLAY, F_DIVERGED, F_FED, F_ACTUAL = 0, 4, 8, 0xC, 0x10, 0x14   # ACTUAL: 첫 어긋남의 rand·해시·유닛 수
START_FMT = "<II20sIB3x8s"            # 시드, rand, 난수 객체 0x14, 프레임, 내 번호, 대전 설정 8
START_LEN = struct.calcsize(START_FMT)
START_FMT2 = START_FMT + "II"         # + 비 효과 격자 직전 rand, 있음(1) — v0.9065 부터
START_LEN2 = struct.calcsize(START_FMT2)
RKP_GRID = 0x30                       # RKP 머리 +0x30: 격자 rand, +0x34: 있음(1)
WEATHER, WEATHER_INIT = 0xAEF078, 0x49EFF0
# 게임 시작 때 비 효과 격자(0xAE7878, 칸마다 물방울 수명)를 rand 로 채운다 (0x4D763B, 2040칸 x 4번 = 8160번 + 1).
# 이 격자는 저장 파일에 없고, 재생은 그 뒤(0x4D7554)에서 rand 를 되돌리므로 격자가 원래 경기와 달라져
# 비가 내리는 순간 rand 소비량이 달라지고 경기가 어긋났다 (CharGND_NullAni 크래시까지).
CHECK_FMT = "<IIIII"                  # 프레임, rand, LCG, 유닛 해시, 유닛 수
CHECK_LEN = struct.calcsize(CHECK_FMT)
RKP_MAGIC = b"RKP1"
RKP_HEAD = 0x60                       # +0x40: 내 플레이어 이름(32, 불러오기가 계정 이름으로 덮어써서)
RKP_NAME = 0x40
FRAME_MS = {0x31: 33, 0x32: 16, 0x34: 8}   # 1 / 2 / 4 키 -> 프레임 시간(ms)

# (파일 오프셋, 원래 바이트, 섹션 안 대상, 'call' | 'jmp')
SITES = (
    (0x4AABC, bytes.fromhex("e81f5dffff"), OFF["dispatch"], "call"),
    (0xD7554, bytes.fromhex("8b0da411b400"), OFF["start"], "call"),
    (0x4A840, bytes.fromhex("558bec83ec44"), OFF["turn"], "jmp"),
    (0x47AF0, bytes.fromhex("558bec83ec40"), OFF["send"], "jmp"),
    (0xD7319, bytes.fromhex("0fbe058dff6d00"), OFF["load"], "call"),
    (0xD65F3, bytes.fromhex("e828d4f8ff"), OFF["panel"], "call"),
    (0xD6607, bytes.fromhex("e834deffff"), OFF["overlay"], "call"),
    (0xD6602, bytes.fromhex("e8a93df9ff"), OFF["panel2"], "call"),
    (0x4D4A, bytes.fromhex("e821ffffff"), OFF["cheatmatch"], "call"),
    (0x40C65, bytes.fromhex("e8263dfcff"), OFF["cheatexec"], "call"),
    (0xD763B, bytes.fromhex("e8b079fcff"), OFF["gridrec"], "call"),
)
SITE, SITE_VA, SITE_ORIGINAL = 0x4AABC, 0x44AABC, SITES[0][1]
MODE_OFF, MODE_PLAY = 0xD6AA4, 4        # WinMain 'mov byte [ebp-0x10], 0' 의 값 (시작 방식)

_BASE = """
    call L_here
L_here:
    pop ebp
    sub ebp, L_here - {entry:#x}
    sub ebp, {off:#x}
"""


def _base(name):
    return _BASE.format(entry=0x10000000 + OFF[name], off=OFF[name])


SOURCES = {
    "dispatch": "    pushad\n" + _base("dispatch") + f"""
    cmp dword ptr [ebp+{FLAGS_OFF + F_PLAY:#x}], 0
    jne L_d
    mov esi, dword ptr [esp+0x28]
    mov ecx, dword ptr [esp+0x2c]
    movzx ebx, byte ptr [esp+0x24]
    test esi, esi
    je L_d
    lea eax, [ebp+{OFF['put']:#x}]
    call eax
L_d:
    popad
    push {DISPATCH:#x}
    ret
""",
    "start": "    pushad\n" + _base("start") + f"""
    cmp dword ptr [ebp+{FLAGS_OFF + F_PLAY:#x}], 0
    jne L_play
    lea edi, [ebp+{SCR_OFF:#x}]
    mov eax, dword ptr [0x6e1a78]
    stosd
    mov eax, dword ptr [0x501ec0]
    stosd
    mov esi, 0xb40fe8
    mov ecx, 5
    .byte 0xf3, 0xa5
    mov eax, dword ptr [{FRAME:#x}]
    stosd
    movzx eax, byte ptr [0xb412cc]
    stosd
    mov esi, 0x6dff88
    mov ecx, 2
    .byte 0xf3, 0xa5
    lea esi, [ebp+{FLAGS_OFF + F_GRID:#x}]
    .byte 0xa5, 0xa5
    lea esi, [ebp+{SCR_OFF:#x}]
    mov ecx, {START_LEN2}
    mov ebx, {P_START}
    lea eax, [ebp+{OFF['put']:#x}]
    call eax
    cmp dword ptr [ebp+{FLAGS_OFF + F_NOSAVE:#x}], 0
    jne L_out
    movzx eax, byte ptr [0xb412cc]
    imul eax, eax, 0x11e0
    add eax, 0x7f7910
    mov ebx, eax
    mov esi, 0x6e61f4
    lea edi, [ebp+{SCR_OFF + 0x80:#x}]
    mov ecx, 8
    .byte 0xf3, 0xa5
    mov esi, ebx
    mov edi, 0x6e61f4
    mov ecx, 8
    .byte 0xf3, 0xa5
    mov byte ptr [0x6e6213], 0
    lea edi, [ebp+{SCR_OFF + 0xc0:#x}]
    mov dword ptr [edi], 0x52455355
    mov word ptr [edi+4], 0x5c73
    add edi, 6
    mov esi, ebx
    mov ecx, 31
L_cp:
    lodsb
    stosb
    test al, al
    je L_cpd
    dec ecx
    jne L_cp
    mov byte ptr [edi], 0
L_cpd:
    push 0
    lea eax, [ebp+{SCR_OFF + 0xc0:#x}]
    push eax
    call dword ptr [0x4ec284]
    lea eax, [ebp+{NAME_OFF:#x}]
    push eax
    mov eax, 0x4d9120
    call eax
    add esp, 4
    movzx eax, al
    mov dword ptr [ebp+{FLAGS_OFF + F_SAVED:#x}], eax
    lea esi, [ebp+{SCR_OFF + 0x80:#x}]
    mov edi, 0x6e61f4
    mov ecx, 8
    .byte 0xf3, 0xa5
    jmp L_out
L_play:
    mov dword ptr [ebp+{FLAGS_OFF + F_DIVERGED:#x}], 0xffffffff
    push 0
    push 0x80
    push 3
    push 0
    push 1
    push 0x80000000
    lea eax, [ebp+{PLAY_NAME_OFF:#x}]
    push eax
    call dword ptr [0x4ec27c]
    cmp eax, -1
    je L_out
    mov esi, eax
    push 0
    lea eax, [ebp+{SCR_OFF + 0x100:#x}]
    push eax
    push {RING}
    lea eax, [ebp+{BUF:#x}]
    push eax
    push esi
    call dword ptr [0x4ec260]
    push esi
    call dword ptr [0x4ec1ac]
    cmp dword ptr [ebp+{BUF:#x}], {struct.unpack('<I', RKP_MAGIC)[0]:#x}
    jne L_out
    mov dword ptr [ebp+{BUF + 8:#x}], 0
    mov eax, dword ptr [ebp+{BUF + 0x10:#x}]
    mov dword ptr [0x501ec0], eax
    push dword ptr [0xb40ff0]
    lea esi, [ebp+{BUF + 0x14:#x}]
    mov edi, 0xb40fe8
    mov ecx, 5
    .byte 0xf3, 0xa5
    pop dword ptr [0xb40ff0]
    mov eax, dword ptr [ebp+{BUF + 0x28:#x}]
    mov dword ptr [0x6e1a78], eax
    mov eax, dword ptr [ebp+{BUF + 0xc:#x}]
    mov dword ptr [{FRAME:#x}], eax
    mov dword ptr [ebp+{FLAGS_OFF + F_DIVERGED:#x}], 0
    lea eax, [ebp+{OFF['grid']:#x}]
    call eax
    lea eax, [ebp+{OFF['vision']:#x}]
    call eax
L_out:
    popad
    mov ecx, dword ptr [0xb411a4]
    ret
""",
    "turn": "    pushad\n" + _base("turn") + f"""
    cmp dword ptr [ebp+{FLAGS_OFF + F_PLAY:#x}], 0
    jne L_skip
    lea eax, [ebp+{OFF['hash']:#x}]
    call eax
    lea ebx, [ebp+{SCR_OFF + 0x40:#x}]
    mov eax, dword ptr [{FRAME:#x}]
    mov dword ptr [ebx], eax
    mov eax, dword ptr [0x501ec0]
    mov dword ptr [ebx+4], eax
    mov eax, dword ptr [0xb40ff8]
    mov dword ptr [ebx+8], eax
    mov dword ptr [ebx+12], edx
    mov dword ptr [ebx+16], edi
    mov esi, ebx
    mov ecx, {CHECK_LEN}
    mov ebx, {P_CHECK}
    lea eax, [ebp+{OFF['put']:#x}]
    call eax
    popad
    push ebp
    mov ebp, esp
    sub esp, 0x44
    push 0x44a846
    ret
L_skip:
    popad
    mov al, 1
    ret
""",
    # put: ebx = 플레이어, esi = 내용, ecx = 길이; ebp = 섹션 시작. eax, edx, edi 사용.
    "put": f"""
    cmp ecx, {MAX_BATCH}
    ja L_d
    lea edx, [ecx+11]
    and edx, 0xfffffffc
    lea edi, [ebp+{BUF:#x}]
    mov eax, dword ptr [edi+4]
    push ebx
    lea ebx, [eax+edx]
    cmp ebx, {RING}
    jbe L_f
    mov ebx, {RING}
    sub ebx, eax
    cmp ebx, 4
    jb L_m
    mov dword ptr [edi+eax+0x10], {WRAP}
L_m:
    add dword ptr [edi], ebx
    xor eax, eax
    mov dword ptr [edi+4], eax
L_f:
    lea ebx, [edi+eax+0x10]
    add eax, edx
    mov dword ptr [edi+4], eax
    add dword ptr [edi], edx
    inc dword ptr [edi+0xc]
    mov eax, dword ptr [{FRAME:#x}]
    mov dword ptr [ebx], eax
    pop eax
    mov byte ptr [ebx+4], al
    mov byte ptr [ebx+5], 0
    mov word ptr [ebx+6], cx
    lea edi, [ebx+8]
    cld
    rep movsb
L_d:
    ret
""",
    # hash: edx = 유닛 해시, edi = 살아 있는 유닛 수 (eax, ecx, esi 사용)
    "hash": f"""
    xor edx, edx
    xor edi, edi
    mov esi, {0x775a38 + 0x138:#x}
    mov ecx, 0x6a5
L_h:
    movsx eax, word ptr [esi+8]
    test eax, eax
    jle L_n
    inc edi
    imul edx, edx, 31
    add edx, eax
    imul edx, edx, 31
    add edx, dword ptr [esi+0x12]
    imul edx, edx, 31
    movzx eax, word ptr [esi+0xe]
    add edx, eax
L_n:
    add esi, 0x138
    dec ecx
    jne L_h
    ret
""",
    "send": "    pushad\n" + _base("send") + f"""
    cmp dword ptr [ebp+{FLAGS_OFF + F_PLAY:#x}], 0
    jne L_play
    popad
    push ebp
    mov ebp, esp
    sub esp, 0x40
    push 0x447af6
    ret
L_play:
    mov eax, dword ptr [{FRAME:#x}]
    xor edx, edx
    mov ecx, 5
    div ecx
    test edx, edx
    jne L_ret
    push 0
    push 0
    push 0
    push 0
    movsx ecx, word ptr [0x4ff414]
    add ecx, 4
    push ecx
    push 0x4ef080
    push 0x7fff
    push 0
    mov ecx, 0xb40fe8
    mov eax, 0x4c9c10
    call eax
    lea eax, [ebp+{OFF['feed']:#x}]
    call eax
L_ret:
    popad
    ret
""",
    # feed (재생, 5프레임마다): 이 프레임의 기록된 묶음 주입, 검사값 비교, 배속 키. ebp = 섹션 시작.
    "feed": f"""
    mov edi, dword ptr [{FRAME:#x}]
    mov ebx, dword ptr [ebp+{BUF + 8:#x}]
L_loop:
    cmp ebx, dword ptr [ebp+{BUF + 4:#x}]
    jae L_done
    lea edx, [ebp+ebx+{BUF + RKP_HEAD:#x}]
    mov eax, dword ptr [edx]
    cmp eax, edi
    ja L_done
    movzx ecx, word ptr [edx+6]
    lea eax, [ecx+11]
    and eax, 0xfffffffc
    add ebx, eax
    mov eax, dword ptr [edx]
    cmp eax, edi
    jb L_loop
    movzx eax, byte ptr [edx+4]
    cmp eax, {P_CHECK}
    jne L_cmd
    push ebx
    push edi
    push edx
    lea eax, [ebp+{OFF['hash']:#x}]
    call eax
    mov ecx, edx
    pop edx
    mov eax, dword ptr [0x501ec0]
    cmp eax, dword ptr [edx+12]
    jne L_bad
    cmp ecx, dword ptr [edx+20]
    jne L_bad
    cmp edi, dword ptr [edx+24]
    je L_ok
L_bad:
    cmp dword ptr [ebp+{FLAGS_OFF + F_DIVERGED:#x}], 0
    jne L_ok
    mov dword ptr [ebp+{FLAGS_OFF + F_ACTUAL:#x}], eax
    mov dword ptr [ebp+{FLAGS_OFF + F_ACTUAL + 4:#x}], ecx
    mov dword ptr [ebp+{FLAGS_OFF + F_ACTUAL + 8:#x}], edi
    pop edi
    push edi
    mov dword ptr [ebp+{FLAGS_OFF + F_DIVERGED:#x}], edi
L_ok:
    pop edi
    pop ebx
    jmp L_loop
L_cmd:
    cmp eax, 8
    jae L_loop
    push ebx
    push edi
    cmp dword ptr [ebp+{FLAGS_OFF + F_DIVERGED:#x}], 0
    je L_feed
    lea esi, [edx+8]
    mov edi, ecx
    test edi, edi
    jle L_feed
L_f:
    cmp word ptr [esi], 0x4002
    jne L_fn
    push ecx
    movzx ecx, byte ptr [esi+4]
L_u:
    dec ecx
    js L_ue
    movsx ebx, word ptr [esi+ecx*2+5]
    imul ebx, ebx, 0x138
    cmp byte ptr [ebx+0x775a48], al
    je L_u
    and word ptr [esi+ecx*2+5], 0
    jmp L_u
L_ue:
    pop ecx
L_fn:
    movzx ebx, word ptr [esi+2]
    add esi, ebx
    sub edi, ebx
    jg L_f
L_feed:
    push ecx
    lea ecx, [edx+8]
    push ecx
    push eax
    mov eax, {DISPATCH:#x}
    call eax
    add esp, 12
    inc dword ptr [ebp+{FLAGS_OFF + F_FED:#x}]
    pop edi
    pop ebx
    jmp L_loop
L_done:
    mov dword ptr [ebp+{BUF + 8:#x}], ebx
    lea eax, [ebp+{OFF['keys']:#x}]
    jmp eax
""",
    # keys (재생, feed 끝): 1 / 2 / 4 키 -> 프레임 시간 33 / 16 / 8 ms (FRAME_MS)
    "keys": f"""
    push 1
    pop edi
    push {FRAME_MS[0x31]}
    pop ebx
L_k:
    lea eax, [edi+0x30]
    push eax
    call dword ptr [0x4ec350]
    test ax, ax
    jns L_kn
    mov dword ptr [0xb412b8], ebx
L_kn:
    shr ebx, 1
    shl edi, 1
    cmp edi, 8
    jb L_k
    ret
""",
    # load (Game_Loop 시작, 재생 모드 싱글 게임): 저장 불러오기 경로를 켠다.
    "load": "    pushad\n" + _base("load") + f"""
    cmp dword ptr [ebp+{FLAGS_OFF + F_PLAY:#x}], 0
    je L_lo
    mov byte ptr [0xb412cb], 0
    cmp byte ptr [0x6dff8d], 2
    je L_lo
    mov byte ptr [0x6dff8d], 1
    cld
    lea esi, [ebp+{NAME_OFF:#x}]
    mov edi, 0x6e62f4
    mov ecx, {len(SAVE_NAME) + 1}
    rep movsb
    lea esi, [ebp+{NAME_OFF:#x}]
    mov edi, 0x6e61f4
    mov ecx, {len(SAVE_NAME) + 1}
    rep movsb
L_lo:
    popad
    movsx eax, byte ptr [0x6dff8d]
    ret
""",
    # vision (재생 시작, 저장을 불러온 뒤): 대전 루프로, 건물 시야 다시 만들기(0x4369F0 — 저장에 시야 지도가 없음), 지도 공개.
    # 재생: 원래 경기가 비 효과 격자를 만들 때의 rand 로 격자를 다시 만든다 (rand·난수 객체 횟수는 그대로 둠).
    "grid": f"""
    cmp dword ptr [ebp+{BUF + RKP_GRID + 4:#x}], 1
    jne L_go
    push dword ptr [0x501ec0]
    push dword ptr [0xb40fe8]
    mov eax, dword ptr [ebp+{BUF + RKP_GRID:#x}]
    mov dword ptr [0x501ec0], eax
    mov ecx, {WEATHER:#x}
    mov eax, {WEATHER_INIT:#x}
    call eax
    pop dword ptr [0xb40fe8]
    pop dword ptr [0x501ec0]
L_go:
    ret
""",
    # 기록: 격자를 만들기 직전(0x4D763B)의 rand 를 남겨 시작 기록에 넣는다. ecx(날씨 객체)는 그대로 넘긴다.
    "gridrec": f"""
    pushad
    call L_h
L_h:
    pop ebp
    mov eax, dword ptr [0x501ec0]
    mov dword ptr [ebp+{FLAGS_OFF + F_GRID - 0x7E6:#x}], eax
    mov byte ptr [ebp+{FLAGS_OFF + F_GRIDOK - 0x7E6:#x}], 1
    popad
    push {WEATHER_INIT:#x}
    ret
""",
    "vision": f"""
    mov byte ptr [0xb412cb], 1
    cmp byte ptr [ebp+{BUF + RKP_NAME:#x}], 0
    je L_nn
    lea esi, [ebp+{BUF + RKP_NAME:#x}]
    movsx edi, byte ptr [0xb412cc]
    imul edi, edi, 0x11e0
    add edi, 0x7f7910
    mov ecx, 8
    .byte 0xf3, 0xa5
L_nn:
    mov esi, {0x775a38 + 0x138:#x}
    mov ebx, 0x6a5
L_vis:
    movsx eax, word ptr [esi+8]
    test eax, eax
    jle L_vn
    cmp word ptr [esi+6], 0x1004
    je L_vn
    push esi
    mov eax, 0x4369f0
    call eax
    add esp, 4
L_vn:
    add esi, 0x138
    dec ebx
    jne L_vis
    or word ptr [0xb412c8], 1
    mov ecx, 0x915698
    mov eax, 0x4991e0
    call eax
    ret
""",
    # cheatexec (0x440C65 대신, ecx=0x6E66C8, [esp+4]=치트 번호, ebp=명령 처리 함수의 틀 -> [ebp+8] 플레이어)
    "cheatexec": f"""
    movzx eax, word ptr [esp+4]
    cmp eax, {CHEAT_MONEY:#x}
    je L_ce
    cmp eax, {CHEAT_SPEED:#x}
    je L_ce
    push 0x404990
    ret
L_ce:
    movsx edx, byte ptr [ebp+8]
    pushad
""" + _base("cheatexec") + f"""
    lea ecx, [ebp+{OFF['cheatapply']:#x}]
    call ecx
    popad
    mov al, 1
    ret 4
""",
    # cheatapply (ebp=섹션, eax=번호, edx=플레이어)
    "cheatapply": f"""
    cmp eax, {CHEAT_SPEED:#x}
    je L_sp
    and edx, 7
    imul edx, edx, 0x11e0
    lea ecx, [edx+0x7f816c]
    mov al, 4
L_add:
    add dword ptr [ecx], 50000
    add ecx, 4
    dec al
    jne L_add
    cmp word ptr [edx+0x7f7908], 1000
    jge L_pm
    add word ptr [edx+0x7f7908], 1000
L_pm:
    lea eax, [ebp+{S_MONEY:#x}]
    jmp L_msg
L_sp:
    xor word ptr [0xb412c8], 8
    lea eax, [ebp+{S_SPON:#x}]
    test word ptr [0xb412c8], 8
    jne L_msg
    lea eax, [ebp+{S_SPOFF:#x}]
L_msg:
    lea ecx, [ebp+{OFF['cheatmsg']:#x}]
    jmp ecx
""",
    # cheatmsg (eax = 알림 글자): 게임 알림 줄 0x4DA9C0(글자, 8, [0x106A650], 0)
    "cheatmsg": f"""
    push 0
    push dword ptr [0x106a650]
    push 8
    push eax
    mov eax, 0x4da9c0
    call eax
    add esp, 0x10
    ret
""",
    # cheatmatch (0x404D4A 대신, ecx=0x6E66C8, [esp+4]=채팅 글자): 'money'/'speed' (대소문자 무시)
    "cheatmatch": "    pushad\n" + _base("cheatmatch") + f"""
    mov esi, dword ptr [esp+0x24]
    lea edi, [ebp+{W_MONEY:#x}]
    call L_eq
    mov ebx, {CHEAT_MONEY:#x}
    test eax, eax
    jne L_hit
    lea edi, [ebp+{W_SPEED:#x}]
    call L_eq
    mov ebx, {CHEAT_SPEED:#x}
    test eax, eax
    jne L_hit
    popad
    push 0x404c70
    ret
L_hit:
    cmp byte ptr [0xb412cb], 0
    je L_single
    push ebx
    mov eax, 0x448110
    call eax
    add esp, 4
    jmp L_done
L_single:
    mov eax, ebx
    movsx edx, byte ptr [0xb412cc]
    lea ecx, [ebp+{OFF['cheatapply']:#x}]
    call ecx
L_done:
    popad
    mov eax, 1
    ret 4
L_eq:
    xor ecx, ecx
L_ql:
    mov al, byte ptr [esi+ecx]
    mov dl, byte ptr [edi+ecx]
    cmp al, 0x41
    jb L_qn
    cmp al, 0x5a
    ja L_qn
    or al, 0x20
L_qn:
    cmp al, dl
    jne L_qne
    test dl, dl
    je L_qe
    inc ecx
    jmp L_ql
L_qe:
    mov eax, 1
    ret
L_qne:
    xor eax, eax
    ret
""",
    # panel (0x4D65F3 대신, ecx = 패널 관리자): 재생 중 HUD 숨김이면 그리지 않음.
    "panel": f"""
    call L_pb
L_pb:
    pop eax
    sub eax, L_pb - {0x10000000 + OFF['panel']:#x}
    sub eax, {OFF['panel']:#x}
    cmp dword ptr [eax+{FLAGS_OFF + F_PLAY:#x}], 0
    je L_pgo
    cmp byte ptr [eax+{FLAGS_OFF + F_HIDE:#x}], 0
    je L_pshow
    ret
L_pshow:
    movsx edx, word ptr [0xb412d0]
    test edx, edx
    jle L_pgo
    cmp edx, 0x6a6
    jge L_pgo
    imul edx, edx, 0x138
    movzx edx, byte ptr [edx+0x775a48]
    cmp edx, 8
    jae L_pgo
    movzx eax, byte ptr [0xb412cc]
    push eax
    mov byte ptr [0xb412cc], dl
    mov eax, 0x463a20
    call eax
    pop eax
    mov byte ptr [0xb412cc], al
    ret
L_pgo:
    push 0x463a20
    ret
""",
    "panel2": f"""
    call L_qb
L_qb:
    pop eax
    sub eax, L_qb - {0x10000000 + OFF['panel2']:#x}
    sub eax, {OFF['panel2']:#x}
    cmp dword ptr [eax+{FLAGS_OFF + F_PLAY:#x}], 0
    je L_qgo
    cmp byte ptr [eax+{FLAGS_OFF + F_HIDE:#x}], 0
    je L_qgo
    ret
L_qgo:
    push 0x46a3b0
    ret
""",
    # overlay (0x4D6607 대신, 마우스 그리기 0x4D4440 직전): I 키 처리, 자원·생산 글자.
    "overlay": "    pushad\n" + _base("overlay") + f"""
    cmp dword ptr [ebp+{FLAGS_OFF + F_PLAY:#x}], 0
    je L_od
    push 0x49
    call dword ptr [0x4ec350]
    test ax, ax
    js L_kd
    mov byte ptr [ebp+{FLAGS_OFF + F_KEYPREV:#x}], 0
    jmp L_kc
L_kd:
    cmp byte ptr [ebp+{FLAGS_OFF + F_KEYPREV:#x}], 0
    jne L_kc
    mov byte ptr [ebp+{FLAGS_OFF + F_KEYPREV:#x}], 1
    xor byte ptr [ebp+{FLAGS_OFF + F_HIDE:#x}], 1
L_kc:
    cmp byte ptr [ebp+{FLAGS_OFF + F_HIDE:#x}], 0
    jne L_od
    lea eax, [ebp+{OFF['draw']:#x}]
    call eax
L_od:
    popad
    push 0x4d4440
    ret
""",
    # text(dc, x, y, 글자, 길이, 색) stdcall: 검은 그림자 + 색 글자
    "text": f"""
    push ebp
    mov ebp, esp
    push 0
    push dword ptr [ebp+8]
    call dword ptr [0x4ec03c]
    push dword ptr [ebp+0x18]
    push dword ptr [ebp+0x14]
    mov eax, dword ptr [ebp+0x10]
    inc eax
    push eax
    mov eax, dword ptr [ebp+0xc]
    inc eax
    push eax
    push dword ptr [ebp+8]
    call dword ptr [0x4ec034]
    push dword ptr [ebp+0x1c]
    push dword ptr [ebp+8]
    call dword ptr [0x4ec03c]
    push dword ptr [ebp+0x18]
    push dword ptr [ebp+0x14]
    push dword ptr [ebp+0x10]
    push dword ptr [ebp+0xc]
    push dword ptr [ebp+8]
    call dword ptr [0x4ec034]
    pop ebp
    ret 0x18
""",
    # draw (ebp = 섹션): [esp] dc, +4 y, +8 플레이어, +0xC 줄 수, +0x10 유닛, +0x14 진행, +0x18 x, +0x1C 남은 유닛, +0x20 이름표, +0x40 글자
    "draw": f"""
    sub esp, 0x140
    mov eax, dword ptr [0x4ec438]
    mov esi, dword ptr [eax+0x18]
    test esi, esi
    je L_x
    mov dword ptr [esp], 0
    lea eax, [esp]
    push eax
    push esi
    mov eax, dword ptr [esi]
    call dword ptr [eax+0x44]
    test eax, eax
    jne L_x
    push dword ptr [0x106ae3c]
    push dword ptr [esp+4]
    call dword ptr [0x4ec020]
    push 1
    push dword ptr [esp+4]
    call dword ptr [0x4ec038]
    movsx eax, word ptr [0x106a5e0]
    sub eax, 370
    mov dword ptr [esp+0x18], eax
    mov dword ptr [esp+4], 30
    mov dword ptr [esp+8], 0
L_p:
    mov ebx, dword ptr [esp+8]
    imul ebx, ebx, 0x11e0
    add ebx, 0x7f7908
    test byte ptr [ebx+6], 0x30
    je L_np
    lea edi, [esp+0x40]
    movsx eax, word ptr [ebx]
    push eax
    movsx eax, word ptr [ebx+2]
    push eax
    push dword ptr [ebx+0x86c]
    push dword ptr [ebx+0x870]
    push dword ptr [ebx+0x868]
    push dword ptr [ebx+0x864]
    lea eax, [ebx+8]
    cmp byte ptr [eax], 0
    jne L_nm
    lea eax, [ebp+{S_CPU:#x}]
L_nm:
    push eax
    lea eax, [ebp+{S_PLAYER:#x}]
    push eax
    push edi
    mov eax, 0x4de774
    call eax
    add esp, 0x24
    mov ecx, dword ptr [esp+8]
    mov edx, dword ptr [ebp+ecx*4+{COLORS:#x}]
    push edx
    push eax
    push edi
    push dword ptr [esp+0x10]
    push dword ptr [esp+0x28]
    push dword ptr [esp+0x14]
    lea eax, [ebp+{OFF['text']:#x}]
    call eax
    add dword ptr [esp+4], 16
    mov dword ptr [esp+0xc], 0
    mov dword ptr [esp+0x10], {0x775a38 + 0x138:#x}
    mov dword ptr [esp+0x1c], 0x6a5
L_u:
    mov esi, dword ptr [esp+0x10]
    movsx eax, word ptr [esi+8]
    test eax, eax
    jle L_un
    cmp word ptr [esi+2], 0
    je L_un
    movzx eax, byte ptr [esi+0x10]
    cmp eax, dword ptr [esp+8]
    jne L_un
    movzx eax, word ptr [esi+6]
    lea edx, [ebp+{S_MAKE:#x}]
    cmp eax, 0x1005
    je L_ok
    lea edx, [ebp+{S_UPG:#x}]
    cmp eax, 0x1006
    je L_ok
    cmp eax, 0x100a
    jne L_un
L_ok:
    mov dword ptr [esp+0x20], edx
    movsx ebx, word ptr [esi+0x50]
    test ebx, ebx
    jle L_un
    cmp ebx, 0xd2
    jge L_un
    fld dword ptr [esi+0x4c]
    fistp dword ptr [esp+0x14]
    imul eax, ebx, 0x1c
    mov eax, dword ptr [eax+0x4fcd88]
    test eax, eax
    je L_nt
    movsx ecx, word ptr [eax+0x28]
    test ecx, ecx
    jle L_nt
    mov eax, dword ptr [esp+0x14]
    imul eax, eax, 100
    cdq
    idiv ecx
    cmp eax, 100
    jle L_pc
    mov eax, 100
    jmp L_pc
L_nt:
    xor eax, eax
L_pc:
    lea edi, [esp+0x40]
    push eax
    imul ebx, ebx, 0x80
    add ebx, 0x5038ec
    push ebx
    push dword ptr [esp+0x28]
    lea eax, [ebp+{S_LINE:#x}]
    push eax
    push edi
    mov eax, 0x4de774
    call eax
    add esp, 0x14
    mov ecx, dword ptr [esp+8]
    mov edx, dword ptr [ebp+ecx*4+{COLORS:#x}]
    push edx
    push eax
    push edi
    push dword ptr [esp+0x10]
    push dword ptr [esp+0x28]
    push dword ptr [esp+0x14]
    lea eax, [ebp+{OFF['text']:#x}]
    call eax
    add dword ptr [esp+4], 15
    inc dword ptr [esp+0xc]
    cmp dword ptr [esp+0xc], 6
    jge L_ue
L_un:
    add dword ptr [esp+0x10], 0x138
    dec dword ptr [esp+0x1c]
    jne L_u
L_ue:
    add dword ptr [esp+4], 6
L_np:
    inc dword ptr [esp+8]
    cmp dword ptr [esp+8], 8
    jl L_p
    mov eax, dword ptr [0x4ec438]
    mov esi, dword ptr [eax+0x18]
    push dword ptr [esp]
    push esi
    mov eax, dword ptr [esi]
    call dword ptr [eax+0x68]
L_x:
    add esp, 0x140
    ret
""",
}


def data_blob() -> bytes:
    """글자 형식(cp949)과 플레이어 색 (COLORREF 0x00BBGGRR)."""
    b = bytearray(CODE_SIZE - DATA_OFF)
    for off, text in ((S_PLAYER, "%s   금 %d  물 %d  카르마 %d  글로리 %d  인구 %d/%d"),
                      (S_LINE, "   %s %s %d%%"), (S_MAKE, "생산"), (S_UPG, "업그레이드"), (S_CPU, "컴퓨터"),
                      (W_MONEY, "money"), (W_SPEED, "speed"), (S_MONEY, "치트: 자원 +50000, 인구 제한 해제"),
                      (S_SPON, "치트: 빠른 생산 켜짐"), (S_SPOFF, "치트: 빠른 생산 꺼짐")):
        raw = text.encode("cp949") + b"\0"
        b[off - DATA_OFF:off - DATA_OFF + len(raw)] = raw
    for i, c in enumerate((0x4848FF, 0xFF9040, 0x40E040, 0x40FFFF, 0xFF60D0, 0x2090FF, 0xF0F0F0, 0xFFFF60)):
        struct.pack_into("<I", b, COLORS - DATA_OFF + 4 * i, c)
    return bytes(b).rstrip(b"\0")


def assemble() -> bytes:
    """섹션 코드 영역 (0..CODE_SIZE). 각 진입점은 OFF 위치; 서로 부를 땐 ebp(섹션 시작) 기준이라 위치 독립.
    0x800..0x9FF 는 이름·설정·임시(body 가 채움), DATA_OFF.. 는 글자 형식·색."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    out = bytearray(CODE_SIZE)
    for name, src in SOURCES.items():
        code = bytes(ks.asm(src, addr=0x10000000 + OFF[name])[0])
        nxt = min([o for o in OFF.values() if o > OFF[name]] + [NAME_OFF if OFF[name] < NAME_OFF else DATA_OFF])
        assert len(code) <= nxt - OFF[name], (name, len(code), nxt - OFF[name])
        out[OFF[name]:OFF[name] + len(code)] = code
    d = data_blob()
    out[DATA_OFF:DATA_OFF + len(d)] = d
    return bytes(out)


CODE = bytes.fromhex(
    "60e8000000005d81ed0600000083ed0083bd280800000075198b7424288b4c242c0fb65c242485f674088d85"
    "00030000ffd06168e0074400c3000000000000000fb744240483f830740b83f83174066890494000c30fbe55"
    "0860e8000000005d81ed1f00000083ed408d8d90050000ffd161b001c2040000000000000000000060e80000"
    "00005d81ed0600000081ed8000000083bd28080000000f85080100008dbd80080000a1781a6e00aba1c01e50"
    "00abbee80fb400b905000000f3a5a1b412b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db54408"
    "0000a5a58db580080000b934000000bbfe0000008d8500030000ffd083bd20080000000f85690100000fb605"
    "cc12b40069c0e01100000510797f0089c3bef4616e008dbd00090000b908000000f3a589debff4616e00b908"
    "000000f3a5c60513626e00008dbd40090000c7075553455266c74704735c83c70689deb91f000000acaa84c0"
    "74064975f7c607006a008d854009000050ff1584c24e008d850008000050b820914d00ffd083c4040fb6c089"
    "85240800008db500090000bff4616e00b908000000f3a5e9c6000000c7852c080000ffffffff6a0068800000"
    "006a036a006a0168000000808d851008000050ff157cc24e0083f8ff0f849400000089c66a008d8580090000"
    "5068000020008d85001000005056ff1560c24e0056ff15acc14e0081bd00100000524b50317563c785081000"
    "00000000008b8510100000a3c01e5000ff35f00fb4008db514100000bfe80fb400b905000000f3a58f05f00f"
    "b4008b8528100000a3781a6e008b850c100000a3b412b400c7852c080000000000008d8564060000ffd08d85"
    "c0060000ffd0618b0da411b400c30000000000000000000060e8000000005d81ed0600000081ed8002000083"
    "bd2808000000754c8d8580030000ffd08d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb4008943"
    "0889530c897b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c361b001c3"
    "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
    "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c300000000000000000000"
    "0000000000000000000000000000000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c2"
    "6bd21f0356126bd21f0fb7460e01c281c6380100004975dac300000000000000000000006a00ff3550a60601"
    "6a0850b8c0a94d00ffd083c410c3000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000060e8000000005d81ed0600000081ed0004000083bd2808000000750d615589e5"
    "83ec4068f67a4400c3a1b412b40031d2b905000000f7f185d275336a006a006a006a000fbf0d14f44f0083c1"
    "04516880f04e0068ff7f00006a00b9e80fb400b8109c4c00ffd08d8580040000ffd061c30000000000000000"
    "00000000000000008b3db412b4008b9d081000003b9d041000000f83e90000008d941d601000008b0239f80f"
    "87d80000000fb74a068d410b83e0fc01c38b0239f872d10fb642043dfd000000754c5357528d8580030000ff"
    "d089d15aa1c01e50003b420c750a3b4a1475053b7a18742383bd2c08000000751a898534080000898d380800"
    "0089bd3c0800005f5789bd2c0800005f5be97affffff83f8080f8371ffffff535783bd2c08000000743e8d72"
    "0889cf85ff7e3566813e02407524510fb64e0449781b0fbf5c4e0569db380100003883485a770074ea668364"
    "4e0500ebe2590fb75e0201de29df7fcb518d4a085150b8e0074400ffd083c40cff85300800005f5be90bffff"
    "ff899d081000008d85800b0000ffe00083f831743a83e20769d2e01100008d8a6c817f00b004810150c30000"
    "83c104fec875f36681ba08797f00e8037d0966818208797f00e8038d85200f0000eb1f668335c812b400088d"
    "85600f000066f705c812b400080075068d85900f00008d8dc0030000ffe10000000000000000000060e80000"
    "00005d81ed0600000081ed0006000083bd2808000000743cc605cb12b40000803d8dff6d0002742cc6058dff"
    "6d0001fc8db500080000bff4626e00b909000000f3a48db500080000bff4616e00b909000000f3a4610fbe05"
    "8dff6d00c300000083bd3410000001752fff35c01e5000ff35e80fb4008b8530100000a3c01e5000b978f0ae"
    "00b8f0ef4900ffd08f05e80fb4008f05c01e5000c30000000000000000000000000000000000000000000000"
    "000000000000000000000000c605cb12b4000180bd401000000074208db5401000000fbe3dcc12b40069ffe0"
    "11000081c710797f00b908000000f3a5be705b7700bba50600000fbf460885c07e1366817e060410740b56b8"
    "f0694300ffd083c40481c6380100004b75dc66830dc812b40001b998569100b8e0914900ffd0c30000000000"
    "000000000000000060e8000000005d81ed0600000081ed400700008b7424248dbdb00e0000e854000000bb30"
    "00000085c0751b8dbdb80e0000e840000000bb3100000085c075076168704c4000c3803dcb12b40000740d53"
    "b810814400ffd083c404eb1189d80fbe15cc12b4008d8d90050000ffd161b801000000c2040031c98a040e8a"
    "140f3c4172063c5a77020c2038d0750d84d2740341ebe5b801000000c331c0c30000000060e8000000005da1"
    "c01e500089455ec64562016168f0ef4900c30000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000e8000000005881e8050000002d000a000083b82808000000744b80b840080000007401c3"
    "0fbf15d012b40085d27e3681faa60600007d2e69d2380100000fb692485a770083fa08731c0fb605cc12b400"
    "508815cc12b400b8203a4600ffd058a2cc12b400c368203a4600c30000000000000000000000000000000000"
    "00000000e8000000005881e8050000002d800a000083b82808000000740a80b840080000007401c368b0a346"
    "00c300000000000060e8000000005d81ed0600000081edb00a000083bd2808000000743e6a49ff1550c34e00"
    "6685c07809c6854108000000eb1780bd4108000000750ec685410800000180b5400800000180bd4008000000"
    "75088d85b00b0000ffd0616840444d00c3000000000000000000000000000000000000000000000000000000"
    "000000005589e56a00ff7508ff153cc04e00ff7518ff75148b451040508b450c4050ff7508ff1534c04e00ff"
    "751cff7508ff153cc04e00ff7518ff7514ff7510ff750cff7508ff1534c04e005dc21800000000006a015f6a"
    "215b8d473050ff1550c34e006685c07906891db812b400d1ebd1e783ff0872e2c30000000000000000000000"
    "81ec40010000a138c44e008b701885f60f8427020000c70424000000008d042450568b06ff504485c00f850e"
    "020000ff353cae0601ff742404ff1520c04e006a01ff742404ff1538c04e000fbf05e0a506012d7201000089"
    "442418c74424041e000000c7442408000000008b5c240869dbe011000081c308797f00f64306300f84980100"
    "008d7c24400fbf03500fbf430250ffb36c080000ffb370080000ffb368080000ffb3640800008d4308803800"
    "75068d85a00e0000508d85000e00005057b874e74d00ffd083c4248b4c24088b948d000f0000525057ff7424"
    "10ff742428ff7424148d85300b0000ffd08344240410c744240c00000000c7442410705b7700c744241ca506"
    "00008b7424100fbf460885c00f8eec00000066837e02000f84e10000000fb646103b4424080f85d30000000f"
    "b746068d95800e00003d0510000074188d95900e00003d06100000740b3d0a1000000f85aa00000089542420"
    "0fbf5e5085db0f8e9a00000081fbd20000000f8d8e000000d9464cdb5c24146bc31c8b8088cd4f0085c0741e"
    "0fbf482885c97e168b4424146bc06499f7f983f8647e09b864000000eb0231c08d7c24405069db8000000081"
    "c3ec38500053ff7424288d85600e00005057b874e74d00ffd083c4148b4c24088b948d000f0000525057ff74"
    "2410ff742428ff7424148d85300b0000ffd0834424040fff44240c837c240c067d128144241038010000ff4c"
    "241c0f85f2feffff8344240406ff442408837c2408080f8c3ffeffffa138c44e008b7018ff3424568b06ff50"
    "6881c440010000c30000000000000000000000002573202020b1dd2025642020b9b02025642020c4abb8a3b8"
    "b62025642020b1dbb7ceb8ae2025642020c0ceb1b82025642f25640000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000020202025732025732025642525000000"
    "00000000000000000000000000000000bbfdbbea000000000000000000000000bef7b1d7b7b9c0ccb5e50000"
    "00000000c4c4c7bbc5cd000000000000000000006d6f6e657900000073706565640000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000ff4848004090ff0040e04000ffff4000d060ff00ff902000f0f0f00060ffff00"
    "c4a1c6ae3a20c0dabff8202b35303030302c20c0ceb1b820c1a6c7d120c7d8c1a60000000000000000000000"
    "0000000000000000000000000000000000000000c4a1c6ae3a20bafcb8a520bbfdbbea20c4d1c1fc00000000"
    "000000000000000000000000000000000000000000000000c4a1c6ae3a20bafcb8a520bbfdbbea20b2a8c1fc"
)
# 이전 판 — 이미 설치된 파일을 걷어낼 때 인식: (코드, 각 위치의 섹션 안 대상)
LEGACY = (
    (bytes.fromhex(
    "60e8000000005d81ed0600000083ed0083bd280800000075198b7424288b4c242c0fb65c242485f674088d85"
    "00030000ffd06168e0074400c3000000000000000fb744240483f830740b83f83174066890494000c30fbe55"
    "0860e8000000005d81ed1f00000083ed408d8d90050000ffd161b001c2040000000000000000000060e80000"
    "00005d81ed0600000081ed8000000083bd28080000000f85080100008dbd80080000a1781a6e00aba1c01e50"
    "00abbee80fb400b905000000f3a5a1b412b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db54408"
    "0000a5a58db580080000b934000000bbfe0000008d8500030000ffd083bd20080000000f85690100000fb605"
    "cc12b40069c0e01100000510797f0089c3bef4616e008dbd00090000b908000000f3a589debff4616e00b908"
    "000000f3a5c60513626e00008dbd40090000c7075553455266c74704735c83c70689deb91f000000acaa84c0"
    "74064975f7c607006a008d854009000050ff1584c24e008d850008000050b820914d00ffd083c4040fb6c089"
    "85240800008db500090000bff4616e00b908000000f3a5e9c6000000c7852c080000ffffffff6a0068800000"
    "006a036a006a0168000000808d851008000050ff157cc24e0083f8ff0f849400000089c66a008d8580090000"
    "5068000020008d85001000005056ff1560c24e0056ff15acc14e0081bd00100000524b50317563c785081000"
    "00000000008b8510100000a3c01e5000ff35f00fb4008db514100000bfe80fb400b905000000f3a58f05f00f"
    "b4008b8528100000a3781a6e008b850c100000a3b412b400c7852c080000000000008d8564060000ffd08d85"
    "c0060000ffd0618b0da411b400c30000000000000000000060e8000000005d81ed0600000081ed8002000083"
    "bd2808000000754c8d8580030000ffd08d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb4008943"
    "0889530c897b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c361b001c3"
    "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
    "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c300000000000000000000"
    "0000000000000000000000000000000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c2"
    "6bd21f0356126bd21f0fb7460e01c281c6380100004975dac300000000000000000000006a00ff3550a60601"
    "6a0850b8c0a94d00ffd083c410c3000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000060e8000000005d81ed0600000081ed0004000083bd2808000000750d615589e5"
    "83ec4068f67a4400c3a1b412b40031d2b905000000f7f185d275336a006a006a006a000fbf0d14f44f0083c1"
    "04516880f04e0068ff7f00006a00b9e80fb400b8109c4c00ffd08d8580040000ffd061c30000000000000000"
    "00000000000000008b3db412b4008b9d081000003b9d041000000f83b10000008d941d601000008b0239f80f"
    "87a00000000fb74a068d410b83e0fc01c38b0239f872d10fb642043dfd000000754e5357528d8580030000ff"
    "d089d15aa1c01e50003b420c750c3b4a1475073b7a187502eb2383bd2c08000000751a898534080000898d38"
    "08000089bd3c0800005f5789bd2c0800005f5be978ffffff83f8080f836fffffff83bd2c080000000f8562ff"
    "ffff5357518d4a085150b8e0074400ffd083c40cff85300800005f5be943ffffff899d08100000be31000000"
    "bb21000000e81f000000be32000000bb10000000e810000000be34000000bb08000000e801000000c356ff15"
    "50c34e006685c07906891db812b400c383f831743a83e20769d2e01100008d8a6c817f00b004810150c30000"
    "83c104fec875f36681ba08797f00e8037d0966818208797f00e8038d85200f0000eb1f668335c812b400088d"
    "85600f000066f705c812b400080075068d85900f00008d8dc0030000ffe10000000000000000000060e80000"
    "00005d81ed0600000081ed0006000083bd2808000000743cc605cb12b40000803d8dff6d0002742cc6058dff"
    "6d0001fc8db500080000bff4626e00b909000000f3a48db500080000bff4616e00b909000000f3a4610fbe05"
    "8dff6d00c300000083bd3410000001752fff35c01e5000ff35e80fb4008b8530100000a3c01e5000b978f0ae"
    "00b8f0ef4900ffd08f05e80fb4008f05c01e5000c30000000000000000000000000000000000000000000000"
    "000000000000000000000000c605cb12b4000180bd401000000074208db5401000000fbe3dcc12b40069ffe0"
    "11000081c710797f00b908000000f3a5be705b7700bba50600000fbf460885c07e1366817e060410740b56b8"
    "f0694300ffd083c40481c6380100004b75dc66830dc812b40001b998569100b8e0914900ffd0c30000000000"
    "000000000000000060e8000000005d81ed0600000081ed400700008b7424248dbdb00e0000e854000000bb30"
    "00000085c0751b8dbdb80e0000e840000000bb3100000085c075076168704c4000c3803dcb12b40000740d53"
    "b810814400ffd083c404eb1189d80fbe15cc12b4008d8d90050000ffd161b801000000c2040031c98a040e8a"
    "140f3c4172063c5a77020c2038d0750d84d2740341ebe5b801000000c331c0c30000000060e8000000005da1"
    "c01e500089455ec64562016168f0ef4900c30000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000e8000000005881e8050000002d000a000083b82808000000744b80b840080000007401c3"
    "0fbf15d012b40085d27e3681faa60600007d2e69d2380100000fb692485a770083fa08731c0fb605cc12b400"
    "508815cc12b400b8203a4600ffd058a2cc12b400c368203a4600c30000000000000000000000000000000000"
    "00000000e8000000005881e8050000002d800a000083b82808000000740a80b840080000007401c368b0a346"
    "00c300000000000060e8000000005d81ed0600000081edb00a000083bd2808000000743e6a49ff1550c34e00"
    "6685c07809c6854108000000eb1780bd4108000000750ec685410800000180b5400800000180bd4008000000"
    "75088d85b00b0000ffd0616840444d00c3000000000000000000000000000000000000000000000000000000"
    "000000005589e56a00ff7508ff153cc04e00ff7518ff75148b451040508b450c4050ff7508ff1534c04e00ff"
    "751cff7508ff153cc04e00ff7518ff7514ff7510ff750cff7508ff1534c04e005dc218000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "81ec40010000a138c44e008b701885f60f8427020000c70424000000008d042450568b06ff504485c00f850e"
    "020000ff353cae0601ff742404ff1520c04e006a01ff742404ff1538c04e000fbf05e0a506012d7201000089"
    "442418c74424041e000000c7442408000000008b5c240869dbe011000081c308797f00f64306300f84980100"
    "008d7c24400fbf03500fbf430250ffb36c080000ffb370080000ffb368080000ffb3640800008d4308803800"
    "75068d85a00e0000508d85000e00005057b874e74d00ffd083c4248b4c24088b948d000f0000525057ff7424"
    "10ff742428ff7424148d85300b0000ffd08344240410c744240c00000000c7442410705b7700c744241ca506"
    "00008b7424100fbf460885c00f8eec00000066837e02000f84e10000000fb646103b4424080f85d30000000f"
    "b746068d95800e00003d0510000074188d95900e00003d06100000740b3d0a1000000f85aa00000089542420"
    "0fbf5e5085db0f8e9a00000081fbd20000000f8d8e000000d9464cdb5c24146bc31c8b8088cd4f0085c0741e"
    "0fbf482885c97e168b4424146bc06499f7f983f8647e09b864000000eb0231c08d7c24405069db8000000081"
    "c3ec38500053ff7424288d85600e00005057b874e74d00ffd083c4148b4c24088b948d000f0000525057ff74"
    "2410ff742428ff7424148d85300b0000ffd0834424040fff44240c837c240c067d128144241038010000ff4c"
    "241c0f85f2feffff8344240406ff442408837c2408080f8c3ffeffffa138c44e008b7018ff3424568b06ff50"
    "6881c440010000c30000000000000000000000002573202020b1dd2025642020b9b02025642020c4abb8a3b8"
    "b62025642020b1dbb7ceb8ae2025642020c0ceb1b82025642f25640000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000020202025732025732025642525000000"
    "00000000000000000000000000000000bbfdbbea000000000000000000000000bef7b1d7b7b9c0ccb5e50000"
    "00000000c4c4c7bbc5cd000000000000000000006d6f6e657900000073706565640000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000ff4848004090ff0040e04000ffff4000d060ff00ff902000f0f0f00060ffff00"
    "c4a1c6ae3a20c0dabff8202b35303030302c20c0ceb1b820c1a6c7d120c7d8c1a60000000000000000000000"
    "0000000000000000000000000000000000000000c4a1c6ae3a20bafcb8a520bbfdbbea20c4d1c1fc00000000"
    "000000000000000000000000000000000000000000000000c4a1c6ae3a20bafcb8a520bbfdbbea20b2a8c1fc"
    ), (0x0, 0x80, 0x280, 0x400, 0x600, 0xA00, 0xAB0, 0xA80, 0x740, 0x40, 0x7E0)),          # v0.9065~v0.9072
    (bytes.fromhex(
    "60e8000000005d81ed0600000083ed0083bd280800000075198b7424288b4c242c0fb65c242485f674088d85"
    "00030000ffd06168e0074400c3000000000000000fb744240483f830740b83f83174066890494000c30fbe55"
    "0860e8000000005d81ed1f00000083ed408d8d90050000ffd161b001c2040000000000000000000060e80000"
    "00005d81ed0600000081ed8000000083bd28080000000f85000100008dbd80080000a1781a6e00aba1c01e50"
    "00abbee80fb400b905000000f3a5a1b412b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db58008"
    "0000b92c000000bbfe0000008d8500030000ffd083bd20080000000f85610100000fb605cc12b40069c0e011"
    "00000510797f0089c3bef4616e008dbd00090000b908000000f3a589debff4616e00b908000000f3a5c60513"
    "626e00008dbd40090000c7075553455266c74704735c83c70689deb91f000000acaa84c074064975f7c60700"
    "6a008d854009000050ff1584c24e008d850008000050b820914d00ffd083c4040fb6c08985240800008db500"
    "090000bff4616e00b908000000f3a5e9be000000c7852c080000ffffffff6a0068800000006a036a006a0168"
    "000000808d851008000050ff157cc24e0083f8ff0f848c00000089c66a008d85800900005068000020008d85"
    "001000005056ff1560c24e0056ff15acc14e0081bd00100000524b5031755bc78508100000000000008b8510"
    "100000a3c01e5000ff35f00fb4008db514100000bfe80fb400b905000000f3a58f05f00fb4008b8528100000"
    "a3781a6e008b850c100000a3b412b400c7852c080000000000008d85c0060000ffd0618b0da411b400c30000"
    "00000000000000000000000000000000000000000000000060e8000000005d81ed0600000081ed8002000083"
    "bd2808000000754c8d8580030000ffd08d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb4008943"
    "0889530c897b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c361b001c3"
    "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
    "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c300000000000000000000"
    "0000000000000000000000000000000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c2"
    "6bd21f0356126bd21f0fb7460e01c281c6380100004975dac300000000000000000000006a00ff3550a60601"
    "6a0850b8c0a94d00ffd083c410c3000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000060e8000000005d81ed0600000081ed0004000083bd2808000000750d615589e5"
    "83ec4068f67a4400c3a1b412b40031d2b905000000f7f185d275336a006a006a006a000fbf0d14f44f0083c1"
    "04516880f04e0068ff7f00006a00b9e80fb400b8109c4c00ffd08d8580040000ffd061c30000000000000000"
    "00000000000000008b3db412b4008b9d081000003b9d041000000f83a40000008d941d601000008b0239f80f"
    "87930000000fb74a068d410b83e0fc01c38b0239f872d10fb642043dfd000000754e5357528d8580030000ff"
    "d089d15aa1c01e50003b420c750c3b4a1475073b7a187502eb2383bd2c08000000751a898534080000898d38"
    "08000089bd3c0800005f5789bd2c0800005f5be978ffffff83f8080f836fffffff5357518d4a085150b8e007"
    "4400ffd083c40cff85300800005f5be950ffffff899d08100000be31000000bb21000000e81f000000be3200"
    "0000bb10000000e810000000be34000000bb08000000e801000000c356ff1550c34e006685c07906891db812"
    "b400c30000000000000000000000000083f831743a83e20769d2e01100008d8a6c817f00b004810150c30000"
    "83c104fec875f36681ba08797f00e8037d0966818208797f00e8038d85200f0000eb1f668335c812b400088d"
    "85600f000066f705c812b400080075068d85900f00008d8dc0030000ffe10000000000000000000060e80000"
    "00005d81ed0600000081ed0006000083bd2808000000743cc605cb12b40000803d8dff6d0002742cc6058dff"
    "6d0001fc8db500080000bff4626e00b909000000f3a48db500080000bff4616e00b909000000f3a4610fbe05"
    "8dff6d00c3000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000c605cb12b4000180bd401000000074208db5401000000fbe3dcc12b40069ffe0"
    "11000081c710797f00b908000000f3a5be705b7700bba50600000fbf460885c07e1366817e060410740b56b8"
    "f0694300ffd083c40481c6380100004b75dc66830dc812b40001b998569100b8e0914900ffd0c30000000000"
    "000000000000000060e8000000005d81ed0600000081ed400700008b7424248dbdb00e0000e854000000bb30"
    "00000085c0751b8dbdb80e0000e840000000bb3100000085c075076168704c4000c3803dcb12b40000740d53"
    "b810814400ffd083c404eb1189d80fbe15cc12b4008d8d90050000ffd161b801000000c2040031c98a040e8a"
    "140f3c4172063c5a77020c2038d0750d84d2740341ebe5b801000000c331c0c3000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000e8000000005881e8050000002d000a000083b82808000000744b80b840080000007401c3"
    "0fbf15d012b40085d27e3681faa60600007d2e69d2380100000fb692485a770083fa08731c0fb605cc12b400"
    "508815cc12b400b8203a4600ffd058a2cc12b400c368203a4600c30000000000000000000000000000000000"
    "00000000e8000000005881e8050000002d800a000083b82808000000740a80b840080000007401c368b0a346"
    "00c300000000000060e8000000005d81ed0600000081edb00a000083bd2808000000743e6a49ff1550c34e00"
    "6685c07809c6854108000000eb1780bd4108000000750ec685410800000180b5400800000180bd4008000000"
    "75088d85b00b0000ffd0616840444d00c3000000000000000000000000000000000000000000000000000000"
    "000000005589e56a00ff7508ff153cc04e00ff7518ff75148b451040508b450c4050ff7508ff1534c04e00ff"
    "751cff7508ff153cc04e00ff7518ff7514ff7510ff750cff7508ff1534c04e005dc218000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "81ec40010000a138c44e008b701885f60f8427020000c70424000000008d042450568b06ff504485c00f850e"
    "020000ff353cae0601ff742404ff1520c04e006a01ff742404ff1538c04e000fbf05e0a506012d7201000089"
    "442418c74424041e000000c7442408000000008b5c240869dbe011000081c308797f00f64306300f84980100"
    "008d7c24400fbf03500fbf430250ffb36c080000ffb370080000ffb368080000ffb3640800008d4308803800"
    "75068d85a00e0000508d85000e00005057b874e74d00ffd083c4248b4c24088b948d000f0000525057ff7424"
    "10ff742428ff7424148d85300b0000ffd08344240410c744240c00000000c7442410705b7700c744241ca506"
    "00008b7424100fbf460885c00f8eec00000066837e02000f84e10000000fb646103b4424080f85d30000000f"
    "b746068d95800e00003d0510000074188d95900e00003d06100000740b3d0a1000000f85aa00000089542420"
    "0fbf5e5085db0f8e9a00000081fbd20000000f8d8e000000d9464cdb5c24146bc31c8b8088cd4f0085c0741e"
    "0fbf482885c97e168b4424146bc06499f7f983f8647e09b864000000eb0231c08d7c24405069db8000000081"
    "c3ec38500053ff7424288d85600e00005057b874e74d00ffd083c4148b4c24088b948d000f0000525057ff74"
    "2410ff742428ff7424148d85300b0000ffd0834424040fff44240c837c240c067d128144241038010000ff4c"
    "241c0f85f2feffff8344240406ff442408837c2408080f8c3ffeffffa138c44e008b7018ff3424568b06ff50"
    "6881c440010000c30000000000000000000000002573202020b1dd2025642020b9b02025642020c4abb8a3b8"
    "b62025642020b1dbb7ceb8ae2025642020c0ceb1b82025642f25640000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000020202025732025732025642525000000"
    "00000000000000000000000000000000bbfdbbea000000000000000000000000bef7b1d7b7b9c0ccb5e50000"
    "00000000c4c4c7bbc5cd000000000000000000006d6f6e657900000073706565640000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000ff4848004090ff0040e04000ffff4000d060ff00ff902000f0f0f00060ffff00"
    "c4a1c6ae3a20c0dabff8202b35303030302c20c0ceb1b820c1a6c7d120c7d8c1a60000000000000000000000"
    "0000000000000000000000000000000000000000c4a1c6ae3a20bafcb8a520bbfdbbea20c4d1c1fc00000000"
    "000000000000000000000000000000000000000000000000c4a1c6ae3a20bafcb8a520bbfdbbea20b2a8c1fc"
    ), (0, 0x80, 0x280, 0x400, 0x600, 0xA00, 0xAB0, 0xA80, 0x740, 0x40)),                               # v0.9060~v0.9064
    (bytes.fromhex(
    "60e8000000005d81ed0600000083ed0083bd280800000075198b7424288b4c242c0fb65c242485f674088d85"
    "00030000ffd06168e0074400c300000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed8000000083bd28080000000f85000100008dbd80080000a1781a6e00aba1c01e50"
    "00abbee80fb400b905000000f3a5a1b412b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db58008"
    "0000b92c000000bbfe0000008d8500030000ffd083bd20080000000f85610100000fb605cc12b40069c0e011"
    "00000510797f0089c3bef4616e008dbd00090000b908000000f3a589debff4616e00b908000000f3a5c60513"
    "626e00008dbd40090000c7075553455266c74704735c83c70689deb91f000000acaa84c074064975f7c60700"
    "6a008d854009000050ff1584c24e008d850008000050b820914d00ffd083c4040fb6c08985240800008db500"
    "090000bff4616e00b908000000f3a5e9be000000c7852c080000ffffffff6a0068800000006a036a006a0168"
    "000000808d851008000050ff157cc24e0083f8ff0f848c00000089c66a008d85800900005068000020008d85"
    "001000005056ff1560c24e0056ff15acc14e0081bd00100000524b5031755bc78508100000000000008b8510"
    "100000a3c01e5000ff35f00fb4008db514100000bfe80fb400b905000000f3a58f05f00fb4008b8528100000"
    "a3781a6e008b850c100000a3b412b400c7852c080000000000008d85c0060000ffd0618b0da411b400c30000"
    "00000000000000000000000000000000000000000000000060e8000000005d81ed0600000081ed8002000083"
    "bd2808000000754c8d8580030000ffd08d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb4008943"
    "0889530c897b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c361b001c3"
    "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
    "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c300000000000000000000"
    "0000000000000000000000000000000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c2"
    "6bd21f0356126bd21f0fb7460e01c281c6380100004975dac300000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000060e8000000005d81ed0600000081ed0004000083bd2808000000750d615589e5"
    "83ec4068f67a4400c3a1b412b40031d2b905000000f7f185d275336a006a006a006a000fbf0d14f44f0083c1"
    "04516880f04e0068ff7f00006a00b9e80fb400b8109c4c00ffd08d8580040000ffd061c30000000000000000"
    "00000000000000008b3db412b4008b9d081000003b9d041000000f83a40000008d941d601000008b0239f80f"
    "87930000000fb74a068d410b83e0fc01c38b0239f872d10fb642043dfd000000754e5357528d8580030000ff"
    "d089d15aa1c01e50003b420c750c3b4a1475073b7a187502eb2383bd2c08000000751a898534080000898d38"
    "08000089bd3c0800005f5789bd2c0800005f5be978ffffff83f8080f836fffffff5357518d4a085150b8e007"
    "4400ffd083c40cff85300800005f5be950ffffff899d08100000be31000000bb21000000e81f000000be3200"
    "0000bb10000000e810000000be34000000bb08000000e801000000c356ff1550c34e006685c07906891db812"
    "b400c30000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed0006000083bd2808000000743cc605cb12b40000803d8dff6d0002742cc6058dff"
    "6d0001fc8db500080000bff4626e00b909000000f3a48db500080000bff4616e00b909000000f3a4610fbe05"
    "8dff6d00c3000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000c605cb12b4000180bd401000000074208db5401000000fbe3dcc12b40069ffe0"
    "11000081c710797f00b908000000f3a5be705b7700bba50600000fbf460885c07e1366817e060410740b56b8"
    "f0694300ffd083c40481c6380100004b75dc66830dc812b40001b998569100b8e0914900ffd0c30000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000e8000000005881e8050000002d000a000083b82808000000744b80b840080000007401c3"
    "0fbf15d012b40085d27e3681faa60600007d2e69d2380100000fb692485a770083fa08731c0fb605cc12b400"
    "508815cc12b400b8203a4600ffd058a2cc12b400c368203a4600c30000000000000000000000000000000000"
    "00000000e8000000005881e8050000002d800a000083b82808000000740a80b840080000007401c368b0a346"
    "00c300000000000060e8000000005d81ed0600000081edb00a000083bd2808000000743e6a49ff1550c34e00"
    "6685c07809c6854108000000eb1780bd4108000000750ec685410800000180b5400800000180bd4008000000"
    "75088d85b00b0000ffd0616840444d00c3000000000000000000000000000000000000000000000000000000"
    "000000005589e56a00ff7508ff153cc04e00ff7518ff75148b451040508b450c4050ff7508ff1534c04e00ff"
    "751cff7508ff153cc04e00ff7518ff7514ff7510ff750cff7508ff1534c04e005dc218000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "81ec40010000a138c44e008b701885f60f8427020000c70424000000008d042450568b06ff504485c00f850e"
    "020000ff353cae0601ff742404ff1520c04e006a01ff742404ff1538c04e000fbf05e0a506012d7201000089"
    "442418c74424041e000000c7442408000000008b5c240869dbe011000081c308797f00f64306300f84980100"
    "008d7c24400fbf03500fbf430250ffb36c080000ffb370080000ffb368080000ffb3640800008d4308803800"
    "75068d85a00e0000508d85000e00005057b874e74d00ffd083c4248b4c24088b948d000f0000525057ff7424"
    "10ff742428ff7424148d85300b0000ffd08344240410c744240c00000000c7442410705b7700c744241ca506"
    "00008b7424100fbf460885c00f8eec00000066837e02000f84e10000000fb646103b4424080f85d30000000f"
    "b746068d95800e00003d0510000074188d95900e00003d06100000740b3d0a1000000f85aa00000089542420"
    "0fbf5e5085db0f8e9a00000081fbd20000000f8d8e000000d9464cdb5c24146bc31c8b8088cd4f0085c0741e"
    "0fbf482885c97e168b4424146bc06499f7f983f8647e09b864000000eb0231c08d7c24405069db8000000081"
    "c3ec38500053ff7424288d85600e00005057b874e74d00ffd083c4148b4c24088b948d000f0000525057ff74"
    "2410ff742428ff7424148d85300b0000ffd0834424040fff44240c837c240c067d128144241038010000ff4c"
    "241c0f85f2feffff8344240406ff442408837c2408080f8c3ffeffffa138c44e008b7018ff3424568b06ff50"
    "6881c440010000c30000000000000000000000002573202020b1dd2025642020b9b02025642020c4abb8a3b8"
    "b62025642020b1dbb7ceb8ae2025642020c0ceb1b82025642f25640000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000020202025732025732025642525000000"
    "00000000000000000000000000000000bbfdbbea000000000000000000000000bef7b1d7b7b9c0ccb5e50000"
    "00000000c4c4c7bbc5cd00000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000ff4848004090ff0040e04000ffff4000d060ff00ff902000f0f0f00060ffff"
    ), (0, 0x80, 0x280, 0x400, 0x600, 0xA00, 0xAB0, 0xA80)),                                           # v0.9059
    (bytes.fromhex(
    "60e8000000005d81ed0600000083ed0083bd280800000075198b7424288b4c242c0fb65c242485f674088d85"
    "00030000ffd06168e0074400c300000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed8000000083bd28080000000f85000100008dbd80080000a1781a6e00aba1c01e50"
    "00abbee80fb400b905000000f3a5a1b412b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db58008"
    "0000b92c000000bbfe0000008d8500030000ffd083bd20080000000f85610100000fb605cc12b40069c0e011"
    "00000510797f0089c3bef4616e008dbd00090000b908000000f3a589debff4616e00b908000000f3a5c60513"
    "626e00008dbd40090000c7075553455266c74704735c83c70689deb91f000000acaa84c074064975f7c60700"
    "6a008d854009000050ff1584c24e008d850008000050b820914d00ffd083c4040fb6c08985240800008db500"
    "090000bff4616e00b908000000f3a5e9be000000c7852c080000ffffffff6a0068800000006a036a006a0168"
    "000000808d851008000050ff157cc24e0083f8ff0f848c00000089c66a008d85800900005068000020008d85"
    "001000005056ff1560c24e0056ff15acc14e0081bd00100000524b5031755bc78508100000000000008b8510"
    "100000a3c01e5000ff35f00fb4008db514100000bfe80fb400b905000000f3a58f05f00fb4008b8528100000"
    "a3781a6e008b850c100000a3b412b400c7852c080000000000008d85c0060000ffd0618b0da411b400c30000"
    "00000000000000000000000000000000000000000000000060e8000000005d81ed0600000081ed8002000083"
    "bd2808000000754c8d8580030000ffd08d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb4008943"
    "0889530c897b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c361b001c3"
    "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
    "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c300000000000000000000"
    "0000000000000000000000000000000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c2"
    "6bd21f0356126bd21f0fb7460e01c281c6380100004975dac300000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000060e8000000005d81ed0600000081ed0004000083bd2808000000750d615589e5"
    "83ec4068f67a4400c3a1b412b40031d2b905000000f7f185d275336a006a006a006a000fbf0d14f44f0083c1"
    "04516880f04e0068ff7f00006a00b9e80fb400b8109c4c00ffd08d8580040000ffd061c30000000000000000"
    "00000000000000008b3db412b4008b9d081000003b9d041000000f83a40000008d941d601000008b0239f80f"
    "87930000000fb74a068d410b83e0fc01c38b0239f872d10fb642043dfd000000754e5357528d8580030000ff"
    "d089d15aa1c01e50003b420c750c3b4a1475073b7a187502eb2383bd2c08000000751a898534080000898d38"
    "08000089bd3c0800005f5789bd2c0800005f5be978ffffff83f8080f836fffffff5357518d4a085150b8e007"
    "4400ffd083c40cff85300800005f5be950ffffff899d08100000be31000000bb21000000e81f000000be3200"
    "0000bb10000000e810000000be34000000bb08000000e801000000c356ff1550c34e006685c07906891db812"
    "b400c30000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed0006000083bd2808000000743cc605cb12b40000803d8dff6d0002742cc6058dff"
    "6d0001fc8db500080000bff4626e00b909000000f3a48db500080000bff4616e00b909000000f3a4610fbe05"
    "8dff6d00c3000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000c605cb12b4000180bd401000000074208db5401000000fbe3dcc12b40069ffe0"
    "11000081c710797f00b908000000f3a5be705b7700bba50600000fbf460885c07e1366817e060410740b56b8"
    "f0694300ffd083c40481c6380100004b75dc66830dc812b40001b998569100b8e0914900ffd0c30000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000e8000000005881e8050000002d000a000083b82808000000740a80b840080000007401c3"
    "68203a4600c3000000000000e8000000005881e8050000002d300a000083b82808000000740a80b840080000"
    "007401c368b0a34600c300000000000060e8000000005d81ed0600000081ed600a000083bd2808000000743e"
    "6a49ff1550c34e006685c07809c6854108000000eb1780bd4108000000750ec685410800000180b540080000"
    "0180bd400800000075088d85600b0000ffd0616840444d00c300000000000000000000000000000000000000"
    "0000000000000000000000005589e56a00ff7508ff153cc04e00ff7518ff75148b451040508b450c4050ff75"
    "08ff1534c04e00ff751cff7508ff153cc04e00ff7518ff7514ff7510ff750cff7508ff1534c04e005dc21800"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000081ec40010000a138c44e008b701885f60f8427020000c70424000000008d042450568b06"
    "ff504485c00f850e020000ff353cae0601ff742404ff1520c04e006a01ff742404ff1538c04e000fbf05e0a5"
    "06012d7201000089442418c74424041e000000c7442408000000008b5c240869dbe011000081c308797f00f6"
    "4306300f84980100008d7c24400fbf03500fbf430250ffb36c080000ffb370080000ffb368080000ffb36408"
    "00008d430880380075068d85a00e0000508d85000e00005057b874e74d00ffd083c4248b4c24088b948d000f"
    "0000525057ff742410ff742428ff7424148d85e00a0000ffd08344240410c744240c00000000c7442410705b"
    "7700c744241ca50600008b7424100fbf460885c00f8eec00000066837e02000f84e10000000fb646103b4424"
    "080f85d30000000fb746068d95800e00003d0510000074188d95900e00003d06100000740b3d0a1000000f85"
    "aa000000895424200fbf5e5085db0f8e9a00000081fbd20000000f8d8e000000d9464cdb5c24146bc31c8b80"
    "88cd4f0085c0741e0fbf482885c97e168b4424146bc06499f7f983f8647e09b864000000eb0231c08d7c2440"
    "5069db8000000081c3ec38500053ff7424288d85600e00005057b874e74d00ffd083c4148b4c24088b948d00"
    "0f0000525057ff742410ff742428ff7424148d85e00a0000ffd0834424040fff44240c837c240c067d128144"
    "241038010000ff4c241c0f85f2feffff8344240406ff442408837c2408080f8c3ffeffffa138c44e008b7018"
    "ff3424568b06ff506881c440010000c300000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000000002573202020b1dd2025642020b9b02025642020c4abb8a3b8"
    "b62025642020b1dbb7ceb8ae2025642020c0ceb1b82025642f25640000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000020202025732025732025642525000000"
    "00000000000000000000000000000000bbfdbbea000000000000000000000000bef7b1d7b7b9c0ccb5e50000"
    "00000000c4c4c7bbc5cd00000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000ff4848004090ff0040e04000ffff4000d060ff00ff902000f0f0f00060ffff"
    ), (0, 0x80, 0x280, 0x400, 0x600, 0xA00, 0xA60, 0xA30)),                                           # v0.9058
    (bytes.fromhex(
    "60e8000000005d81ed0600000083ed0083bd280800000075198b7424288b4c242c0fb65c242485f674088d85"
    "00030000ffd06168e0074400c300000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed8000000083bd28080000000f85000100008dbd80080000a1781a6e00aba1c01e50"
    "00abbee80fb400b905000000f3a5a1b412b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db58008"
    "0000b92c000000bbfe0000008d8500030000ffd083bd20080000000f85610100000fb605cc12b40069c0e011"
    "00000510797f0089c3bef4616e008dbd00090000b908000000f3a589debff4616e00b908000000f3a5c60513"
    "626e00008dbd40090000c7075553455266c74704735c83c70689deb91f000000acaa84c074064975f7c60700"
    "6a008d854009000050ff1584c24e008d850008000050b820914d00ffd083c4040fb6c08985240800008db500"
    "090000bff4616e00b908000000f3a5e9be000000c7852c080000ffffffff6a0068800000006a036a006a0168"
    "000000808d851008000050ff157cc24e0083f8ff0f848c00000089c66a008d85800900005068000020008d85"
    "001000005056ff1560c24e0056ff15acc14e0081bd00100000524b5031755bc78508100000000000008b8510"
    "100000a3c01e5000ff35f00fb4008db514100000bfe80fb400b905000000f3a58f05f00fb4008b8528100000"
    "a3781a6e008b850c100000a3b412b400c7852c080000000000008d85c0060000ffd0618b0da411b400c30000"
    "00000000000000000000000000000000000000000000000060e8000000005d81ed0600000081ed8002000083"
    "bd2808000000754c8d8580030000ffd08d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb4008943"
    "0889530c897b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c361b001c3"
    "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
    "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c300000000000000000000"
    "0000000000000000000000000000000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c2"
    "6bd21f0356126bd21f0fb7460e01c281c6380100004975dac300000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000060e8000000005d81ed0600000081ed0004000083bd2808000000750d615589e5"
    "83ec4068f67a4400c3a1b412b40031d2b905000000f7f185d275336a006a006a006a000fbf0d14f44f0083c1"
    "04516880f04e0068ff7f00006a00b9e80fb400b8109c4c00ffd08d8580040000ffd061c30000000000000000"
    "00000000000000008b3db412b4008b9d081000003b9d041000000f83a40000008d941d401000008b0239f80f"
    "87930000000fb74a068d410b83e0fc01c38b0239f872d10fb642043dfd000000754e5357528d8580030000ff"
    "d089d15aa1c01e50003b420c750c3b4a1475073b7a187502eb2383bd2c08000000751a898534080000898d38"
    "08000089bd3c0800005f5789bd2c0800005f5be978ffffff83f8080f836fffffff5357518d4a085150b8e007"
    "4400ffd083c40cff85300800005f5be950ffffff899d08100000be31000000bb21000000e81f000000be3200"
    "0000bb10000000e810000000be34000000bb08000000e801000000c356ff1550c34e006685c07906891db812"
    "b400c30000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed0006000083bd2808000000743cc605cb12b40000803d8dff6d0002742cc6058dff"
    "6d0001fc8db500080000bff4626e00b909000000f3a48db500080000bff4616e00b909000000f3a4610fbe05"
    "8dff6d00c3000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000c605cb12b40001be705b7700bba50600000fbf460885c07e1366817e06041074"
    "0b56b8f0694300ffd083c40481c6380100004b75dc66830dc812b40001b998569100b8e0914900ffd0c3"
    ), (0, 0x80, 0x280, 0x400, 0x600)),                                                                 # v0.9057
    (bytes.fromhex(
    "60e8000000005d81ed0600000083ed0083bd280800000075198b7424288b4c242c0fb65c242485f674088d85"
    "00030000ffd06168e0074400c300000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed8000000083bd28080000000f85000100008dbd80080000a1781a6e00aba1c01e50"
    "00abbee80fb400b905000000f3a5a1b412b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db58008"
    "0000b92c000000bbfe0000008d8500030000ffd083bd20080000000f85610100000fb605cc12b40069c0e011"
    "00000510797f0089c3bef4616e008dbd00090000b908000000f3a589debff4616e00b908000000f3a5c60513"
    "626e00008dbd40090000c7075553455266c74704735c83c70689deb91f000000acaa84c074064975f7c60700"
    "6a008d854009000050ff1584c24e008d850008000050b820914d00ffd083c4040fb6c08985240800008db500"
    "090000bff4616e00b908000000f3a5e9be000000c7852c080000ffffffff6a0068800000006a036a006a0168"
    "000000808d851008000050ff157cc24e0083f8ff0f848c00000089c66a008d85800900005068000020008d85"
    "001000005056ff1560c24e0056ff15acc14e0081bd00100000524b5031755bc78508100000000000008b8510"
    "100000a3c01e50008db514100000bfe80fb400b905000000f3a58b8528100000a3781a6e008b850c100000a3"
    "b412b400c7852c0800000000000066830dc812b40001b998569100b8e0914900ffd0618b0da411b400c30000"
    "00000000000000000000000000000000000000000000000060e8000000005d81ed0600000081ed8002000083"
    "bd2808000000754c8d8580030000ffd08d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb4008943"
    "0889530c897b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c361b001c3"
    "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
    "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c300000000000000000000"
    "0000000000000000000000000000000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c2"
    "6bd21f0356126bd21f0fb7460e01c281c6380100004975dac300000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000060e8000000005d81ed0600000081ed0004000083bd2808000000750d615589e5"
    "83ec4068f67a4400c3a1b412b40031d2b905000000f7f185d2750de80a0000008d8580040000ffd061c35589"
    "e583ec4068f67a4400c300000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000008b3db412b4008b9d081000003b9d041000000f83870000008d941d401000008b0239f877"
    "7a0fb74a068d410b83e0fc01c38b0239f872d50fb642043dfd00000075395357528d8580030000ffd089d15a"
    "a1c01e50003b420c750c3b4a1475073b7a187502eb115f5783bd2c08000000750689bd2c0800005f5beb9183"
    "f808738c5357518d4a085150b8e0074400ffd083c40cff85300800005f5be96dffffff899d08100000be3100"
    "0000bb21000000e81f000000be32000000bb10000000e810000000be34000000bb08000000e801000000c356"
    "ff1550c34e006685c07906891db812b400c30000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed0006000083bd2808000000742c803dcb12b400007523803d8dff6d0000751ac605"
    "8dff6d00018db500080000bff4626e00b909000000fcf3a4610fbe058dff6d00c3"
    ), (0, 0x80, 0x280, 0x400, 0x600)),                                                                 # v0.9056
    (bytes.fromhex(
    "60e8000000005d81ed0600000083ed0083bd280800000075198b7424288b4c242c0fb65c242485f674088d85"
    "00030000ffd06168e0074400c300000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000060e80000"
    "00005d81ed0600000081ed8000000083bd28080000000f85000100008dbd80080000a1781a6e00aba1c01e50"
    "00abbee80fb400b905000000f3a5a1b412b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db58008"
    "0000b92c000000bbfe0000008d8500030000ffd083bd20080000000f85610100000fb605cc12b40069c0e011"
    "00000510797f0089c3bef4616e008dbd00090000b908000000f3a589debff4616e00b908000000f3a5c60513"
    "626e00008dbd40090000c7075553455266c74704735c83c70689deb91f000000acaa84c074064975f7c60700"
    "6a008d854009000050ff1584c24e008d850008000050b820914d00ffd083c4040fb6c08985240800008db500"
    "090000bff4616e00b908000000f3a5e9be000000c7852c080000ffffffff6a0068800000006a036a006a0168"
    "000000808d851008000050ff157cc24e0083f8ff0f848c00000089c66a008d85800900005068000020008d85"
    "001000005056ff1560c24e0056ff15acc14e0081bd00100000524b5031755bc78508100000000000008b8510"
    "100000a3c01e50008db514100000bfe80fb400b905000000f3a58b8528100000a3781a6e008b850c100000a3"
    "b412b400c7852c0800000000000066830dc812b40001b998569100b8e0914900ffd0618b0da411b400c30000"
    "00000000000000000000000000000000000000000000000060e8000000005d81ed0600000081ed8002000083"
    "bd2808000000754c8d8580030000ffd08d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb4008943"
    "0889530c897b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c361b001c3"
    "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
    "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c300000000000000000000"
    "0000000000000000000000000000000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c2"
    "6bd21f0356126bd21f0fb7460e01c281c6380100004975dac300000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000060e8000000005d81ed0600000081ed0004000083bd2808000000750d615589e5"
    "83ec4068f67a4400c3a1b412b40031d2b905000000f7f185d2750de80a0000008d8580040000ffd061c35589"
    "e583ec4068f67a4400c300000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000008b3db412b4008b9d081000003b9d041000000f83870000008d941d401000008b0239f877"
    "7a0fb74a068d410b83e0fc01c38b0239f872d50fb642043dfd00000075395357528d8580030000ffd089d15a"
    "a1c01e50003b420c750c3b4a1475073b7a187502eb115f5783bd2c08000000750689bd2c0800005f5beb9183"
    "f808738c5357518d4a085150b8e0074400ffd083c40cff85300800005f5be96dffffff899d08100000be3100"
    "0000bb21000000e81f000000be32000000bb10000000e810000000be34000000bb08000000e801000000c356"
    "ff1550c34e006685c07906891db812b400c3"
    ), (0, 0x80, 0x280, 0x400)),                                                                        # v0.9055
    (bytes.fromhex(
        "60e8000000005d83ed068b7424288b4c242c81f900400000776385f6745f8d510b83e2fc8dbd001000008b47"
        "048d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001"
        "d08947040117ff470ca1b412b40089038a442424884304c643050066894b068d7b08fcf3a46168e0074400c3"), (0,)),   # v0.9053
    (bytes.fromhex(
        "60e8000000005d81ed060000008b7424288b4c242c0fb65c242485f674088d8500030000ffd06168e0074400"
        "c300000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "00000000000000000000000000000000000000000000000000000000000000000000000060e8000000005d81"
        "ed0600000081ed000100008dbd80080000a1781a6e00aba1c01e5000abbee80fb400b905000000f3a5a1b412"
        "b400ab0fb605cc12b400abbe88ff6d00b902000000f3a58db580080000b92c000000bbfe0000008d85000300"
        "00ffd083bd2008000000751a8d850008000050b820914d00ffd083c4040fb6c0898524080000618b0da411b4"
        "00c3000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000060e8000000005d81ed0600000081ed00"
        "02000031d231ffbe705b7700b9a50600000fbf460885c07e15476bd21f01c26bd21f0356126bd21f0fb7460e"
        "01c281c6380100004975da8d9dc0080000a1b412b4008903a1c01e5000894304a1f80fb40089430889530c89"
        "7b1089deb914000000bbfd0000008d8500030000ffd0615589e583ec446846a84400c3000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000081f900400000775d8d510b83e2fc8dbd001000008b470453"
        "8d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001d0"
        "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c3"), (0, 0x100, 0x200)),                                          # v0.9054
)


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _layout(data):
    if len(data) < 0x400 or data[:2] != b"MZ":
        raise ValueError("리플레이 기록 패치: PE 파일이 아닙니다.")
    nt = _u32(data, 0x3C)
    if data[nt:nt + 4] != b"PE\0\0":
        raise ValueError("리플레이 기록 패치: PE 헤더가 없습니다.")
    nsec = _u16(data, nt + 6)
    opt = nt + 24
    table = opt + _u16(data, nt + 20)
    secs = []
    for i in range(nsec):
        h = table + 40 * i
        vsize, va, rsize, rptr = struct.unpack_from("<IIII", data, h + 8)
        secs.append((bytes(data[h:h + 8]), va, vsize, rptr, rsize, h))
    return nt, nsec, table, _u32(data, opt + 32), _u32(data, opt + 36), opt + 56, secs


def _branch(site_off, section_va, target, kind, length):
    op = b"\xe8" if kind == "call" else b"\xe9"
    src = 0x400000 + site_off
    rel = (0x400000 + section_va + target) - (src + 5)
    return (op + struct.pack("<i", rel)).ljust(length, b"\x90")


def body(save: bool = False, play: bool = False) -> bytes:
    """save=False: 시작 저장 끄기(FLAGS +0 = 1, 실험 기능이라 기본). play=True: 재생 모드."""
    b = bytearray(CODE.ljust(CODE_SIZE, b"\0"))
    b[NAME_OFF:NAME_OFF + len(SAVE_NAME) + 1] = SAVE_NAME + b"\0"
    b[PLAY_NAME_OFF:PLAY_NAME_OFF + len(PLAY_FILE) + 1] = PLAY_FILE + b"\0"
    struct.pack_into("<I", b, FLAGS_OFF + F_NOSAVE, 0 if save else 1)
    struct.pack_into("<I", b, FLAGS_OFF + F_PLAY, 1 if play else 0)
    return bytes(b)


def _legacy_bodies():
    out = []
    for code, targets in LEGACY:
        base = bytearray(code.ljust(CODE_SIZE, b"\0"))
        out.append((bytes(base), targets))
        if len(targets) == 3:                              # v0.9054: 이름 + 저장 끄기 표시 0/1
            base[0x800:0x809] = b"RKREPLAY\0"
            for v in (0, 1):
                struct.pack_into("<I", base, 0x820, v)
                out.append((bytes(base), targets))
        if len(targets) >= 4:                              # v0.9055~: 이름 둘 + 저장 끄기 0/1 + 재생 0/1
            base[0x800:0x809] = SAVE_NAME + b"\0"
            base[0x810:0x81D] = PLAY_FILE + b"\0"
            for v in (0, 1):
                for w in (0, 1):
                    struct.pack_into("<I", base, 0x820, v)
                    struct.pack_into("<I", base, 0x828, w)
                    out.append((bytes(base), targets))
    return out


def _kind(data):
    """('new', 정보) | ('legacy', 정보) | (None, None)."""
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    name, va, vsize, rptr, rsize, h = secs[-1]
    if name != SECTION_NAME:
        return None, None
    raw = bytes(data[rptr:rptr + rsize])
    ok_hdr = (vsize == VIRTUAL_SIZE and rsize == CODE_SIZE and rptr + rsize == len(data)
              and _u32(data, soi) == va + VIRTUAL_SIZE and _u32(data, h + 36) == CHARACTERISTICS)
    if not ok_hdr:
        raise ValueError("리플레이 기록 패치가 불완전하거나 알 수 없는 변경이 있습니다.")
    mode = MODE_PLAY if _u32(raw, FLAGS_OFF + F_PLAY) == 1 else 0
    res = bytes(data[RES_OFF:RES_OFF + len(RES_800)])
    res_ok = res == RES_800 or (mode == MODE_PLAY and res == RES_1280)
    if raw in [body(s, p) for s in (False, True) for p in (False, True)] and data[MODE_OFF] == mode and res_ok and \
            all(data[o:o + len(b)] == _branch(o, va, t, k, len(b)) for o, b, t, k in SITES):
        return "new", (va, h, nsec)
    for legacy, targets in _legacy_bodies():
        n = len(targets)
        legacy_mode_ok = data[MODE_OFF] == 0 or (data[MODE_OFF] == MODE_PLAY and _u32(raw, FLAGS_OFF + F_PLAY) == 1)
        if raw == legacy and legacy_mode_ok and all(data[o:o + len(b)] == _branch(o, va, t, k, len(b))
                                 for (o, b, _, k), t in zip(SITES[:n], targets)) \
                and all(data[o:o + len(b)] == b for o, b, t, k in SITES[n:]):
            return "legacy", (va, h, nsec)
    raise ValueError("리플레이 기록 패치가 불완전하거나 알 수 없는 변경이 있습니다.")


def state(data) -> bool:
    """패치 여부 (단축키 섹션은 먼저 걷어낸 상태). 이전 판도 True. 알 수 없는 상태면 ValueError."""
    kind, _ = _kind(data)
    if kind:
        return True
    if data[MODE_OFF] == 0 and data[RES_OFF:RES_OFF + len(RES_800)] == RES_800 and \
            all(data[o:o + len(b)] == b for o, b, t, k in SITES):
        return False
    raise ValueError("리플레이 기록 패치: 지원하지 않는 게임 파일이거나 다른 패치와 충돌합니다.")


def _flag(data, off) -> int:
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    return _u32(data, secs[-1][3] + FLAGS_OFF + off)


def saves_at_start(data) -> bool:
    kind, _ = _kind(data)
    return kind == "new" and _flag(data, F_NOSAVE) == 0


def plays(data) -> bool:
    kind, _ = _kind(data)
    return kind == "new" and _flag(data, F_PLAY) == 1


def strip(data) -> bytes:
    kind, info = _kind(data)
    if not kind:
        state(data)
        return bytes(data)
    va, h, nsec = info
    nt, _, table, salign, falign, soi, secs = _layout(data)
    out = bytearray(data[:secs[-1][3]])
    for o, b, t, k in SITES:
        out[o:o + len(b)] = b
    out[MODE_OFF] = 0
    out[RES_OFF:RES_OFF + len(RES_800)] = RES_800
    out[h:h + 40] = bytes(40)
    struct.pack_into("<H", out, nt + 6, nsec - 1)
    struct.pack_into("<I", out, soi, va)
    return bytes(out)


def apply(data, enabled: bool = True, save: bool = False, play: bool = False) -> bytes:
    out = bytearray(strip(data))
    if not enabled:
        return bytes(out)
    nt, nsec, table, salign, falign, soi, secs = _layout(out)
    _, va, vsize, rptr, rsize, _ = secs[-1]
    new_va = (va + max(vsize, rsize) + salign - 1) // salign * salign
    if _u32(out, soi) != new_va:
        raise ValueError("리플레이 기록 패치: 이미지 크기가 예상과 다릅니다.")
    if len(out) % falign or len(out) != rptr + rsize:
        raise ValueError("리플레이 기록 패치: 파일 끝에 알 수 없는 데이터가 있습니다.")
    h = table + 40 * nsec
    if h + 40 > min(s[3] for s in secs) or any(out[h:h + 40]):
        raise ValueError("리플레이 기록 패치: 섹션 헤더를 추가할 공간이 없습니다.")
    out[h:h + 40] = SECTION_NAME + struct.pack("<IIIIIIHHI", VIRTUAL_SIZE, new_va, CODE_SIZE, len(out),
                                              0, 0, 0, 0, CHARACTERISTICS)
    struct.pack_into("<H", out, nt + 6, nsec + 1)
    struct.pack_into("<I", out, soi, new_va + VIRTUAL_SIZE)
    for o, b, t, k in SITES:
        out[o:o + len(b)] = _branch(o, new_va, t, k, len(b))
    if play:
        out[MODE_OFF] = MODE_PLAY
        if out[HIGHRES_MARK:HIGHRES_MARK + len(RES_1280)] == RES_1280:
            out[RES_OFF:RES_OFF + len(RES_1280)] = RES_1280
    out += body(save, play)
    return bytes(out)


# ---- 재생 자료 (.rkp) ----
def build_rkp(start: dict, records, name: str = "") -> bytes:
    """start: 기록의 시작 정보, records: [(프레임, 플레이어, 바이트)] (명령 0..7, 검사값 0xFD). 프레임 순서 유지."""
    body_ = bytearray()
    last = 0
    for frame, player, blob in records:
        body_ += struct.pack("<IBBH", frame, player, 0, len(blob)) + blob
        body_ += bytes((-len(blob)) % 4)
        last = max(last, frame)
    if RKP_HEAD + len(body_) > RING:
        raise ValueError("리플레이 기록이 너무 깁니다 (게임 안 재생 자료 2MB 초과).")
    head = bytearray(RKP_HEAD)
    head[0:4] = RKP_MAGIC
    struct.pack_into("<IIIII", head, 4, len(body_), 0, start["frame"], start["rand"] & 0xFFFFFFFF, 0)
    head[0x14:0x28] = bytes.fromhex(start["rng"])
    struct.pack_into("<II", head, 0x28, start["seed"] & 0xFFFFFFFF, last)
    raw = name.encode("cp949", "replace")[:31]
    head[RKP_NAME:RKP_NAME + len(raw)] = raw
    # 새 경기는 srand(시드) (0x4D7376) 바로 뒤에 격자를 만든다 → 격자 직전 rand = 시드. 예전 기록도 시드가 있다.
    grid = start.get("grid", start["seed"])
    if grid is not None:
        struct.pack_into("<II", head, RKP_GRID, grid & 0xFFFFFFFF, 1)
    return bytes(head) + bytes(body_)


# ---- 런처 쪽: 실행 중인 게임에서 읽기 ----
def find_section(read) -> int | None:
    head = read(0x400000, 0x1000)
    nt = _u32(head, 0x3C)
    nsec = _u16(head, nt + 6)
    table = nt + 24 + _u16(head, nt + 20)
    for i in range(nsec):
        h = table + 40 * i
        if head[h:h + 8] == SECTION_NAME:
            return 0x400000 + _u32(head, h + 12)
    return None


def read_flags(read, section_va) -> dict:
    raw = read(section_va + FLAGS_OFF, 0x20)
    nosave, saved, play, diverged, fed, a_rand, a_hash, a_count = struct.unpack("<8I", raw)
    return {"saved": saved, "play": play, "diverged": diverged, "fed": fed,
            "actual": (a_rand, a_hash, a_count)}


def parse_start(blob: bytes) -> dict:
    seed, rand, rng, frame, local, opts = struct.unpack(START_FMT, blob[:START_LEN])
    out = {"seed": seed, "rand": rand, "rng": rng.hex(), "frame": frame, "local": local, "options": opts.hex()}
    if len(blob) >= START_LEN2:
        grid, ok = struct.unpack_from("<II", blob, START_LEN)
        if ok == 1:
            out["grid"] = grid                  # 비 효과 격자를 만들기 직전 rand (v0.9065~ 기록)
    return out


def rand_back(state: int, n: int) -> int:
    """게임 rand (state = state * 0x343FD + 0x269EC3) 를 n 번 되돌린 값."""
    inv = pow(0x343FD, -1, 1 << 32)
    x = state & 0xFFFFFFFF
    for _ in range(n):
        x = ((x - 0x269EC3) * inv) & 0xFFFFFFFF
    return x


def parse_check(blob: bytes) -> list:
    return list(struct.unpack(CHECK_FMT, blob[:CHECK_LEN]))


class CommandReader:
    """링 버퍼에서 새 기록만 꺼낸다. (프레임, 플레이어, 바이트) 목록과 잃은 바이트 수."""

    def __init__(self, read, section_va):
        self.read = read
        self.buf = section_va + BUF
        self.total = None
        self.pos = 0

    def poll(self):
        head = self.read(self.buf, 0x10)
        total, pos = _u32(head, 0), _u32(head, 4)
        if head[:4] == RKP_MAGIC:                    # 재생 중: 링 아님
            return [], 0
        if self.total is None or total < self.total:
            self.total, self.pos = total, pos
            return [], 0
        new = total - self.total
        if new == 0:
            return [], 0
        if new > RING:
            lost = new - RING
            self.total, self.pos = total, pos
            return [], lost
        out = []
        start, end = self.pos, pos
        if start <= end and new <= end - start:
            chunks = [self.read(self.buf + 0x10 + start, end - start)]
        else:
            chunks = [self.read(self.buf + 0x10 + start, RING - start), self.read(self.buf + 0x10, end)]
        for blob in chunks:
            o = 0
            while o + 8 <= len(blob):
                frame = _u32(blob, o)
                if frame == WRAP:
                    break
                player, length = blob[o + 4], _u16(blob, o + 6)
                if o + 8 + length > len(blob):
                    break
                out.append((frame, player, bytes(blob[o + 8:o + 8 + length])))
                o += (8 + length + 3) & ~3
        self.total, self.pos = total, pos
        return out, 0
