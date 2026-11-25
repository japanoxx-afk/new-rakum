"""싱글(패키지·오프라인) 실행용 수정 (Rhakmu.exe 1.000d) — 런처의 '싱글플레이' 로 실행할 때만 켠다.

레지스트리 Pack 이 0 이 아니면 게임은 패키지 모드(오프라인 메인 메뉴)로 시작한다 (scenario_mode 머리말).

(1) CD 키 확인 건너뛰기. 0x4D9757 에서 0x425E90 (게임 폴더의 Rsk.dat 를 읽어 CD 키 확인) 을 부르고, 0 이면
    'CD키를 입력해 주세요' 창 뒤 Launcher.exe -cdkey 를 실행하고 끝낸다. 한게임 내려받기판의 Rsk.dat 는 빈 파일이라
    늘 여기서 막힌다. 0x4D9763 의 jne 0x4D981E (확인이 됐으면 계속) 을 무조건 jmp 로.
(2) 경기 시간 표시. 화면 위 시계(0x465240)는 트리거 카운트다운이 없고 멀티플레이([0xB412CB])가 아니면 그리지 않는다.
    0x465298 의 jne 를 jmp 로 (늘 그림), 0x465344..0x4653AC (분·초 계산) 를 다시 짬:
    멀티플레이이거나 카운트다운이 없으면([ebp-8] == 100) 경기 시간 [0xB4074C] (싱글에서도 0x4D5ADD 가 올린다), 아니면 카운트다운.
    멀티플레이에서의 표시는 원래와 같다.
(3) 메인 메뉴의 겹친 창 없애기. 경기 뒤 점수 화면에서 메인 메뉴(쪽 8)로 돌아오면 (게임을 다시 실행해도) 빈 대화 상자
    (로그인·비밀번호 바꾸기 등)가 모두 겹쳐 나오고 눌리지 않았다.
    메인 메뉴 폼은 대화 상자 6개(MainMenu.stb dialogbox 0..5)를 쓰고, 열 때(Init 0x413800)와 그릴 때(Draw 0x414360, 상태
    [0x6E0BC0] == 0 이면 매 프레임) GameCtrl 의 dlg_Active(번호, 0) 으로 숨긴다. dlg_Active/GetDlg 는 폼의 대화 상자 목록
    (폼 +0x30, 이중 연결)에서 '앞에서 몇 번째' 로 찾으므로 0..5 번째만 숨는다. 매 프레임 숨기는데도 3번(비밀번호 바꾸기) 모양이
    보인다는 것은 목록에 같은 대화 상자가 더 들어 있다는 뜻 (6번째 뒤 — 폼 파일이 두 번 읽힘; 어디서인지는 미확인).
    그래서 두 곳의 '0..5 번 숨기기' 를 '목록의 모든 대화 상자 숨기기' 로 바꾼다 (대화 상자 +4 = 0, +0x60 = 0 — dlg_Active(…, 0) 과 같음).
    필요한 대화 상자는 게임이 원래대로 번호로 켠다 (앞의 것). 0x413820..0x413886, 0x41437A..0x4143CF.
    (v0.9100 시험판은 경기 끝 0x4D5813, v0.9101 시험판은 점수 화면 [확인] 0x411EC0 에서 ExitProcess(EXIT_CODE) 로 끝내고
     런처가 다시 실행했다 — 다시 실행해도 같은 화면이라 걷어냄.)

온라인(Pack == 0) 실행에서는 켜지 않는다. 이전 시험판(v0.9099: (1) 만, v0.9100·v0.9101: 종료 방식)은 state() 가 알아보고 transform() 이 맞춘다.
"""
EXIT_CODE = 0x52A1                                 # 예전 시험판(v0.9100·v0.9101)의 끝냄 코드 — 지금은 쓰지 않음

SITE = 0xD9763
ORIGINAL = bytes.fromhex("0f85b5000000")           # jne 0x4D981E
PATCHED = bytes.fromhex("90e9b5000000")            # nop; jmp 0x4D981E

TIMER_SHOW = (0x65298, bytes.fromhex("75"), bytes.fromhex("eb"))
TIMER_VALUE = (0x65344,
               bytes.fromhex("8b45f899b93c000000f7f98945ec8b45f899b93c000000f7f98955e833d28a15cb12b40085d27424"
                             "a14c07b40033d2b93c000000f7f18945eca14c07b40033d2b93c000000f7f18955e8eb1c"
                             "8b45f899b93c000000f7f98945ec8b45f899b93c000000f7f98955e8"),
               bytes.fromhex("8b45f883f8647409803dcb12b400007405a14c07b40031d2b93c000000f7f18945ec8955e8eb41")
               .ljust(0x68, b"\x90"))
TIMER_SOURCE = """
    mov eax, dword ptr [ebp-8]
    cmp eax, 0x64
    je gt
    cmp byte ptr [0xb412cb], 0
    je cd
gt:
    mov eax, dword ptr [0xb4074c]
cd:
    xor edx, edx
    mov ecx, 0x3c
    div ecx
    mov dword ptr [ebp-0x14], eax
    mov dword ptr [ebp-0x18], edx
    jmp 0x4653ac
"""
_HIDE_ALL = "8b4dfc8b51308b0239d074138b480885c9740883610400c64160008b00ebe9"     # 아래 MENU_SOURCE (끝의 jmp 만 자리마다 다름)
MENU_SOURCE = """
    mov ecx, dword ptr [ebp-4]
    mov edx, dword ptr [ecx+0x30]
    mov eax, dword ptr [edx]
L:
    cmp eax, edx
    je D
    mov ecx, dword ptr [eax+8]
    test ecx, ecx
    je N
    and dword ptr [ecx+4], 0
    mov byte ptr [ecx+0x60], 0
N:
    mov eax, dword ptr [eax]
    jmp L
D:
    jmp {end}
"""
_HIDE_CALLS = "6a006a{n:02x}6a088b0de00c6e00e8{rel}"                             # push 0; push n; push 8; mov ecx,[menu]; call 0x428890


def _hide_calls(site, count):
    out = b""
    for n in range(count):
        at = 0x400000 + site + len(out) + 12
        out += bytes.fromhex(_HIDE_CALLS.format(n=n, rel=(0x428890 - (at + 5) & 0xFFFFFFFF).to_bytes(4, "little").hex()))
    return out


MENU_INIT = (0x13820, _hide_calls(0x13820, 6), (bytes.fromhex(_HIDE_ALL) + b"\xeb\x45").ljust(0x66, b"\x90"))
MENU_DRAW = (0x1437A, _hide_calls(0x1437A, 5), (bytes.fromhex(_HIDE_ALL) + b"\xeb\x34").ljust(0x55, b"\x90"))
MENU_ENDS = (0x413886, 0x4143CF)

_EXIT = b"\x68" + EXIT_CODE.to_bytes(4, "little") + bytes.fromhex("ff156cc24e00")   # push EXIT_CODE; call [ExitProcess] (예전 판)
SCORE_EXIT = (0x11EC0, bytes.fromhex("6a08b9e00c6e00e894220100e988000000"), _EXIT.ljust(17, b"\x90"))    # v0.9101 시험판만
GAME_END = (0xD5813, bytes.fromhex("8b0d30ae060151b9e00c6e00e82ce0f4ff"), _EXIT.ljust(17, b"\x90"))    # v0.9100 시험판만

# (파일 오프셋, 원래, 바꾼 것)
SITES = ((SITE, ORIGINAL, PATCHED), TIMER_SHOW, TIMER_VALUE, MENU_INIT, MENU_DRAW)
RETIRED = (SCORE_EXIT, GAME_END)                   # 예전 판만 바꾸던 자리 — 늘 원래대로 돌린다
LEGACY = ((0,), (0, 1, 2, 6), (0, 1, 2, 5))        # 예전 판이 바꿔 둔 자리 묶음 (SITES + RETIRED 번호): v0.9099, v0.9100, v0.9101


def _marks(data):
    marks = []
    for site, original, patched in SITES + RETIRED:
        value = bytes(data[site:site + len(original)])
        if value not in (original, patched):
            raise ValueError("싱글 모드 패치: 알 수 없는 변경이 있습니다.")
        marks.append(value == patched)
    return marks


def state(data) -> bool:
    """켜져 있으면 True (예전 판 상태도 True). 알 수 없는 상태면 ValueError."""
    marks = _marks(data)
    if all(marks[:len(SITES)]) and not any(marks[len(SITES):]):
        return True
    if not any(marks):
        return False
    if tuple(k for k, on in enumerate(marks) if on) in LEGACY:
        return True
    raise ValueError("싱글 모드 패치: 알 수 없는 변경이 있습니다.")


def current(data) -> bool:
    """지금 판 그대로 켜져 있으면 True."""
    marks = _marks(data)
    return all(marks[:len(SITES)]) and not any(marks[len(SITES):])


def transform(data, enabled=True) -> bytes:
    state(data)
    out = bytearray(data)
    for site, original, patched in SITES:
        out[site:site + len(original)] = patched if enabled else original
    for site, original, patched in RETIRED:
        out[site:site + len(original)] = original
    return bytes(out)
