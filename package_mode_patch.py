"""싱글(패키지·오프라인) 실행용 수정 (Rhakmu.exe 1.000d) — 런처의 '싱글플레이' 로 실행할 때만 켠다.

레지스트리 Pack 이 0 이 아니면 게임은 패키지 모드(오프라인 메인 메뉴)로 시작한다 (scenario_mode 머리말).

(1) CD 키 확인 건너뛰기. 0x4D9757 에서 0x425E90 (게임 폴더의 Rsk.dat 를 읽어 CD 키 확인) 을 부르고, 0 이면
    'CD키를 입력해 주세요' 창 뒤 Launcher.exe -cdkey 를 실행하고 끝낸다. 한게임 내려받기판의 Rsk.dat 는 빈 파일이라
    늘 여기서 막힌다. 0x4D9763 의 jne 0x4D981E (확인이 됐으면 계속) 을 무조건 jmp 로.
(2) 경기 시간 표시. 화면 위 시계(0x465240)는 트리거 카운트다운이 없고 멀티플레이([0xB412CB])가 아니면 그리지 않는다.
    0x465298 의 jne 를 jmp 로 (늘 그림), 0x465344..0x4653AC (분·초 계산) 를 다시 짬:
    멀티플레이이거나 카운트다운이 없으면([ebp-8] == 100) 경기 시간 [0xB4074C] (싱글에서도 0x4D5ADD 가 올린다), 아니면 카운트다운.
    멀티플레이에서의 표시는 원래와 같다.
(3) 경기가 끝나면 게임을 끝낸다 (끝냄 코드 EXIT_CODE). 원래는 0x4D581F 에서 0x423850 (메뉴 다시 만들기) 을 부르는데,
    이 판에서는 그 뒤 메인 메뉴의 대화 상자(로그인 등)가 모두 겹쳐 나오고 눌리지 않는다 (원인 미확인).
    0x4D5813..0x4D5824 를 push EXIT_CODE; call [ExitProcess] 로. 런처가 이 끝냄 코드를 보면 싱글 메뉴로 다시 실행한다.

온라인(Pack == 0) 실행에서는 켜지 않는다. v0.9099 시험판은 (1) 만 넣었다 — state() 가 알아보고 transform() 이 맞춘다.
"""
EXIT_CODE = 0x52A1                                 # 경기 끝 -> 런처가 싱글 메뉴로 다시 실행

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
GAME_END = (0xD5813, bytes.fromhex("8b0d30ae060151b9e00c6e00e82ce0f4ff"),
            (b"\x68" + EXIT_CODE.to_bytes(4, "little") + bytes.fromhex("ff156cc24e00")).ljust(17, b"\x90"))

# (파일 오프셋, 원래, 바꾼 것)
SITES = ((SITE, ORIGINAL, PATCHED), TIMER_SHOW, TIMER_VALUE, GAME_END)
LEGACY = ((0,),)                                   # 예전 판이 바꿔 둔 자리 묶음 (v0.9099: CD 키만)


def _marks(data):
    marks = []
    for site, original, patched in SITES:
        value = bytes(data[site:site + len(original)])
        if value not in (original, patched):
            raise ValueError("싱글 모드 패치: 알 수 없는 변경이 있습니다.")
        marks.append(value == patched)
    return marks


def state(data) -> bool:
    """켜져 있으면 True (예전 판 상태도 True). 알 수 없는 상태면 ValueError."""
    marks = _marks(data)
    if all(marks):
        return True
    if not any(marks):
        return False
    if tuple(k for k, on in enumerate(marks) if on) in LEGACY:
        return True
    raise ValueError("싱글 모드 패치: 알 수 없는 변경이 있습니다.")


def current(data) -> bool:
    """지금 판 그대로 켜져 있으면 True."""
    return all(_marks(data))


def transform(data, enabled=True) -> bytes:
    state(data)
    out = bytearray(data)
    for site, original, patched in SITES:
        out[site:site + len(original)] = patched if enabled else original
    return bytes(out)
