"""집결지(랠리 포인트) 금광·우물 인식 범위 확장 패치 (Rhakmu.exe 1.000d).

원인 (분석):
  0x473410 은 일꾼에게 대상 유닛 없이 '지점' 명령(우클릭 / 생산 후 집결지 이동)이 들어왔을 때
  주문을 고른다. 지점을 칸(>>5)으로 바꾼 뒤 그 '한 칸'의 지형 그리드 0xB4198A 값에
  자원 비트(2)가 있을 때만 채취(0x2006), 아니면 이동(0x2003)이다. 금광 그림은 실제
  자원 칸보다 1~2칸 넓게 그려져 그림 가장자리에 집결지를 찍으면 이동으로 처리된다.

패치:
  0x473425 (7바이트) -> 코드 동굴 0x4EBA20 로 점프.
  동굴: 원래처럼 칸을 계산해 [ebp-4]/[ebp-2] 에 저장하고, 그 칸이 자원이면 원래 경로
  (0x47345D) 로 돌아간다. 아니면 반경 1, 2 칸 순서로 주변을 찾아 칸 값이 정확히
  0x53(금광) 또는 0x63(우물) 인 칸이 있으면, 호출자(0x473B80) 인자의 지점을 그 칸 중심으로
  바꾸고 채취(0x2006) 를 돌려준다. 그래서 이후 0x4736E0 이 그 금광/우물을 정확히 대상으로 잡는다.
  나무 등 다른 장식, 3칸 이상 떨어진 곳은 원래처럼 이동.

게임 진행(시뮬레이션) 코드이므로 멀티플레이는 모든 참가자가 같은 패치 상태여야 한다.
"""
from __future__ import annotations

SITE = 0x73425                       # 파일 오프셋 (= VA - 0x400000)
SITE_ORIGINAL = bytes.fromhex("0fbf4d14c1f905")
SITE_PATCHED = bytes.fromhex("e9f68507009090")
CAVE = 0xEBA20
CODE = bytes.fromhex(
    "0fbf4d14c1f90566894dfc0fbf5516c1fa05668955fe69c208020000f684088a19b400020f85137af8ff"
    "bb0100000089dff7df89def7de8d043a69c00802000001c80fb684308a19b4003c5374193c6374154639"
    "de7ee04739df7ed74383fb027ecde9607af8ff01f101fac1e10583c110c1e20583c2108b450066894814"
    "6689501666894d1466895516e92f7af8ff"
)
RADIUS = 2


def state(data) -> bool:
    """패치 적용 여부. 알 수 없는 바이트면 ValueError."""
    site = bytes(data[SITE:SITE + len(SITE_ORIGINAL)])
    cave = bytes(data[CAVE:CAVE + len(CODE)])
    if site == SITE_PATCHED and cave == CODE:
        return True
    if site == SITE_ORIGINAL and cave == bytes(len(CODE)):
        return False
    raise ValueError("집결지 금광 인식 패치: 지원하지 않는 게임 파일이거나 패치가 불완전합니다.")


def strip(data) -> bytes:
    """패치를 걷어낸 원본 상태 (다른 패치들의 전체 검증 전에 사용)."""
    out = bytearray(data)
    if state(out):
        out[SITE:SITE + len(SITE_ORIGINAL)] = SITE_ORIGINAL
        out[CAVE:CAVE + len(CODE)] = bytes(len(CODE))
    return bytes(out)


def apply(data, enabled: bool = True) -> bytes:
    out = bytearray(strip(data))
    if enabled:
        out[SITE:SITE + len(SITE_PATCHED)] = SITE_PATCHED
        out[CAVE:CAVE + len(CODE)] = CODE
    return bytes(out)
