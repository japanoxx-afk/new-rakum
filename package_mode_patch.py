"""패키지(오프라인) 모드의 CD 키 확인 건너뛰기 (Rhakmu.exe 1.000d) — 싱글 메뉴 실험 실행 때만 켠다.

레지스트리 Pack 이 0 이 아니면 게임은 패키지 모드로 시작하는데 (scenario_mode 머리말), 그때 0x4D9757 에서
0x425E90 (게임 폴더의 Rsk.dat 를 읽어 CD 키를 확인) 을 부르고, 0 을 돌려주면 'CD키를 입력해 주세요' 창을 띄운 뒤
Launcher.exe -cdkey 를 실행하고 끝낸다. 한게임 내려받기판의 Rsk.dat 는 빈 파일이라 늘 여기서 막힌다.
0x425E90 을 부르는 곳은 이 한 곳뿐이다.

패치: 0x4D9763 의 jne 0x4D981E (확인이 됐으면 계속) 을 무조건 jmp 로. 온라인(Pack == 0) 실행에서는 켜지 않는다.
"""
SITE = 0xD9763
ORIGINAL = bytes.fromhex("0f85b5000000")      # jne 0x4D981E
PATCHED = bytes.fromhex("90e9b5000000")       # nop; jmp 0x4D981E


def state(data) -> bool:
    value = bytes(data[SITE:SITE + len(ORIGINAL)])
    if value == PATCHED:
        return True
    if value == ORIGINAL:
        return False
    raise ValueError("패키지 모드 패치: 알 수 없는 변경이 있습니다.")


def transform(data, enabled=True) -> bytes:
    state(data)
    out = bytearray(data)
    out[SITE:SITE + len(ORIGINAL)] = PATCHED if enabled else ORIGINAL
    return bytes(out)
