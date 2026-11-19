"""단축키 확장 패치 (Rhakmu.exe 1.000d).

  .            쉬는 일꾼 모두 선택 (최대 12기 — 게임 선택 한도)
  F2           모든 군사 유닛 선택 (일꾼 제외 이동 유닛, 최대 12기)
  Shift+숫자   지금 선택한 유닛을 그 번호 부대에 추가 (부대가 비어 있으면 새로 지정)

분석:
  0x42EF90 은 게임 화면의 WM_KEYDOWN 처리. 0x42EFCE 부터가 '반복 아님' 경로이며
  Ctrl+숫자 -> 0x4DC7F0 (부대 저장), Ctrl+F1~F4 / F1~F4 -> 화면 위치 저장/이동.
  숫자 키(WM_CHAR) -> 0x4DC940 (부대 불러오기).
  선택 목록: 0x80083C 개수, 0x80083E 유닛 번호 12칸, 0xB412E4 유닛별 선택 표시,
  0xB412D0 대표 유닛, 0xB412CE 현재 부대 번호. 선택이 바뀌면 0x447BD0 이 선택 명령(0x4002)을
  명령 큐에 넣고 0x4659E0 이 아래 정보 창을 갱신한다. 부대 불러오기와 같은 순서를 따른다.
  유닛: 0x775A38 + 번호*0x138 (+2 이동 유닛이면 0 아님, +6 현재 명령(2 = 대기), +8 체력,
  +0xE 종류, +0x10 소유자, +0x28 상위 바이트 = 건물/금광 안 등). 종류 정보 [0x4FCD88 + 종류*0x1C]
  +0x40 == 1 이면 일꾼 (0x473B80 이 일꾼 채취 판단에 쓰는 값).
  부대: 0x106A6C0 + 플레이어*0xD0 + 번호*0x1A (개수 바이트 + 유닛 번호 12칸). 로컬 전용.

패치:
  0x42EFCE (8바이트, push 0x11 / call GetKeyState) -> 새 섹션 .hotkey 로 점프.
  채팅 입력 중(IME 활성), 일시정지(0xB40749), 메뉴 창(0x801EAC) 이 있으면 원래 동작 그대로.
  Ctrl 을 함께 누르면 원래 동작 (Ctrl+F2 화면 위치 저장, Ctrl+숫자 부대 지정).
  선택은 게임 자체의 선택 명령으로 전달되므로 게임 진행 규칙은 바뀌지 않는다.
  (상대 PC 가 이 패치를 쓰지 않아도 멀티 동기화에 영향 없음.)

섹션은 미니맵 패치 섹션 뒤에 붙이며, 다른 패치의 검증 전에 strip() 으로 걷어낸다.
"""
from __future__ import annotations

import struct

SITE_VA = 0x42EFCE
SITE = 0x2EFCE                                   # 파일 오프셋 (.text: VA - 0x400000)
SITE_ORIGINAL = bytes.fromhex("6a11ff1550c34e00")
SECTION_NAME = b".hotkey\0"
SECTION_SIZE = 0x1000
CHARACTERISTICS = 0x60000020                     # code | execute | read
CODE = bytes.fromhex(
    "8b45083dbe000000742183f871743183e83083f809764b6a11ff1550c34e0068d6ef4200c36806f14200c3"
    "e86600000085c074e36a00e8b700000083c404ebe56a11ff1550c34e006685c078cae84400000085c074c1"
    "6a01e89500000083c404ebc36a10ff1550c34e006685c079a86a11ff1550c34e006685c0789be815000000"
    "85c074928b450883e83050e8a501000083c404eb8fb9d8666e00ff1520c54e0084c07521803d4907b40000"
    "7518833dac1e800000750f803dcc12b400087306b801000000c331c0c331c066837b08007e1f66837b0200"
    "74188a4b103a0dcc12b400750df64307107507807b2b00750140c35589e583ec1853565731ffbe01000000"
    "69de3801000081c3385a7700e8b6ffffff85c0743d0fb7430e6bc01c8b8088cd4f0085c0742c31c9668378"
    "40010f94c1837d0800750d85c9741866837b06027511eb0485c9750b6689747de84783ff0c73094681fea6"
    "06000072a585ff740d8d45e85750e80a00000083c4085f5e5b89ec5dc35589e55356578b75088b7d0c68a6"
    "0600006a0068e412b400b8f0e74d00ffd083c40c31c983f90c731c31c039f9730b0fb7044ec680e412b400"
    "016689044d3e08800041ebdf66893d3c088000c605ce12b400ffb8d07b4400ffd00fb7053e08800069d038"
    "010000668b92465a7700b90100000039f9731c0fb71c4d3e08800069db38010000663b93465a7700750341"
    "ebe231c066a3d012b40066c705c41e800000006a0169c03801000005385a770050b9581e8000b8e0594600"
    "ffd05f5e5b5dc35589e583ec185356570fbe05cc12b40069c0d00000008b4d086bc91a8db408c0a6060131"
    "ff31c983f90c730f0fb7444e0251e8490000005941ebec31c983f90c73120fb7044d3e08800051e8300000"
    "005941ebe931c983f90c731331c039f97305668b444de86689444e0241ebe889f88806c605ce12b400ff5f"
    "5e5b89ec5dc385c0743b3da6060000733483ff0c732f69d83801000081c3385a770050e8f1fdffff89c258"
    "85d2741631c939f9730a663b444de8740941ebf26689447de847c3"
)
assert len(CODE) <= SECTION_SIZE


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _layout(data):
    """(nt, n_sections, table_offset, section_alignment, file_alignment, size_of_image_offset, sections)."""
    if len(data) < 0x400 or data[:2] != b"MZ":
        raise ValueError("단축키 패치: PE 파일이 아닙니다.")
    nt = _u32(data, 0x3C)
    if data[nt:nt + 4] != b"PE\0\0":
        raise ValueError("단축키 패치: PE 헤더가 없습니다.")
    nsec = _u16(data, nt + 6)
    opt = nt + 24
    table = opt + _u16(data, nt + 20)
    secs = []
    for i in range(nsec):
        h = table + 40 * i
        name = bytes(data[h:h + 8])
        vsize, va, rsize, rptr = struct.unpack_from("<IIII", data, h + 8)
        secs.append((name, va, vsize, rptr, rsize, h))
    return nt, nsec, table, _u32(data, opt + 32), _u32(data, opt + 36), opt + 56, secs


def _jump(section_va):
    rel = (0x400000 + section_va) - (SITE_VA + 5)
    return b"\xe9" + struct.pack("<i", rel) + b"\x90\x90\x90"


def state(data) -> bool:
    """패치 적용 여부. 알 수 없는 상태면 ValueError."""
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    site = bytes(data[SITE:SITE + len(SITE_ORIGINAL)])
    name, va, vsize, rptr, rsize, _ = secs[-1]
    if name == SECTION_NAME:
        body = bytes(data[rptr:rptr + rsize])
        if (site == _jump(va) and rsize == SECTION_SIZE and vsize == SECTION_SIZE
                and rptr + rsize == len(data) and body == CODE + bytes(SECTION_SIZE - len(CODE))
                and _u32(data, soi) == va + SECTION_SIZE):
            return True
        raise ValueError("단축키 패치가 불완전하거나 알 수 없는 변경이 있습니다.")
    if site == SITE_ORIGINAL:
        return False
    raise ValueError("단축키 패치: 지원하지 않는 게임 파일입니다.")


def strip(data) -> bytes:
    """패치를 걷어낸 상태 (다른 패치들의 검증 전에 사용)."""
    if not state(data):
        return bytes(data)
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    name, va, vsize, rptr, rsize, h = secs[-1]
    out = bytearray(data[:rptr])
    out[SITE:SITE + len(SITE_ORIGINAL)] = SITE_ORIGINAL
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
        raise ValueError("단축키 패치: 이미지 크기가 예상과 다릅니다.")
    if len(out) % falign or len(out) != rptr + rsize:
        raise ValueError("단축키 패치: 파일 끝에 알 수 없는 데이터가 있습니다.")
    h = table + 40 * nsec
    if h + 40 > min(s[3] for s in secs) or any(out[h:h + 40]):
        raise ValueError("단축키 패치: 섹션 헤더를 추가할 공간이 없습니다.")
    raw = len(out)
    out[h:h + 40] = SECTION_NAME + struct.pack("<IIIIIIHHI", SECTION_SIZE, new_va, SECTION_SIZE, raw,
                                              0, 0, 0, 0, CHARACTERISTICS)
    struct.pack_into("<H", out, nt + 6, nsec + 1)
    struct.pack_into("<I", out, soi, new_va + SECTION_SIZE)
    out[SITE:SITE + len(SITE_ORIGINAL)] = _jump(new_va)
    out += CODE + bytes(SECTION_SIZE - len(CODE))
    return bytes(out)
