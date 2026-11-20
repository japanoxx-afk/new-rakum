"""리플레이 기록 패치 (Rhakmu.exe 1.000d) — 실제 게임 화면 리플레이용 기록.

대전은 모든 PC가 같은 명령을 같은 프레임에 실행하는 방식(lockstep)이다.
  Game_Loop 0x4D7310: 대전 준비(srand([0x6E1A78]) @0x4D7376 …) 뒤 0x4D7554 에서 게임 루프를 고른다.
  게임 루프 매 프레임: 시뮬레이션 1단계, 프레임 번호 [0xB412B4] += 1
  5프레임마다 0x44A840: 턴이 다 모인 플레이어마다 0x4407E0(플레이어, 명령 묶음, 길이) 호출 (0x44AABC)
  난수: CRT rand 상태 [0x501EC0] (srand 0x4DE7C6), 엔진 난수 객체 0xB40FE8 (+0x10 LCG)
  게임 저장: SaveGameData(이름) 0x4D9120 -> <게임>\\USERs\\<내 계정>\\<이름>.SAV, 불러오기 0x4D8220
WangGun 리플레이(WGReplay.dll)와 같은 방식: 시작 상태는 게임 자체 저장으로, 그 뒤는 프레임별 명령과 검사값.

패치 (새 섹션 .rkrec, 위치 독립 코드; 게임 동작은 같고 상대 PC가 이 패치를 안 써도 됨):
  1) 0x44AABC call 0x4407E0 -> 기록 후 원래 함수 (플레이어 0..7: 명령 묶음)
  2) 0x4D7554 (게임 루프 직전, mov ecx,[0xB411A4]) -> 시작 기록(플레이어 0xFE) + SaveGameData("RKREPLAY")
  3) 0x44A840 (턴 처리 시작) -> 검사값 기록(플레이어 0xFD): 프레임, rand, LCG, 유닛 해시, 유닛 수

링 버퍼 (섹션 + BUF):
  +0 total (지금까지 쓴 바이트, 줄지 않음)   +4 pos (다음 쓸 위치)   +0xC 기록 수
  +0x10.. 데이터 RING 바이트. 기록 = [u32 프레임][u8 플레이어][u8 0][u16 길이][내용] (4바이트 맞춤)
  끝에 안 들어가면 그 자리에 0xFFFFFFFF 를 쓰고 처음(0)부터 이어 쓴다.
설정 (섹션 + FLAGS_OFF): +0 시작 저장 끄기(1 = 안 함; 재생할 때 런처가 씀), +4 마지막 저장 결과.
"""
from __future__ import annotations

import struct

SECTION_NAME = b".rkrec\0\0"
DISPATCH = 0x4407E0
FRAME = 0xB412B4
CODE_SIZE = 0x1000
BUF = 0x1000                          # 섹션 안 버퍼 머리 위치
DATA = BUF + 0x10
RING = 0x200000
VIRTUAL_SIZE = (CODE_SIZE + 0x10 + RING + 0x1000 + 0xFFF) & ~0xFFF
CHARACTERISTICS = 0xE0000060
WRAP = 0xFFFFFFFF
MAX_BATCH = 0x4000
P_START, P_CHECK = 0xFE, 0xFD
SAVE_NAME = b"RKREPLAY"
OFF = {"dispatch": 0x000, "start": 0x100, "turn": 0x200, "put": 0x300}
NAME_OFF, FLAGS_OFF, SCR_OFF = 0x800, 0x820, 0x880
START_FMT = "<II20sIB3x8s"            # 시드, rand, 난수 객체 0x14, 프레임, 내 번호, 대전 설정 8
START_LEN = struct.calcsize(START_FMT)
CHECK_FMT = "<IIIII"                  # 프레임, rand, LCG, 유닛 해시, 유닛 수
CHECK_LEN = struct.calcsize(CHECK_FMT)

# (파일 오프셋, 원래 바이트, 섹션 안 대상, 'call' | 'jmp')
SITES = (
    (0x4AABC, bytes.fromhex("e81f5dffff"), OFF["dispatch"], "call"),
    (0xD7554, bytes.fromhex("8b0da411b400"), OFF["start"], "call"),
    (0x4A840, bytes.fromhex("558bec83ec44"), OFF["turn"], "jmp"),
)
SITE, SITE_VA, SITE_ORIGINAL = 0x4AABC, 0x44AABC, SITES[0][1]      # (v0.9053 이름 호환)

SOURCES = {
    "dispatch": f"""
    pushad
    call L_b
L_b:
    pop ebp
    sub ebp, L_b - {0x10000000 + OFF['dispatch']:#x}
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
    "start": f"""
    pushad
    call L_b
L_b:
    pop ebp
    sub ebp, L_b - {0x10000000 + OFF['start']:#x}
    sub ebp, {OFF['start']:#x}
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
    lea esi, [ebp+{SCR_OFF:#x}]
    mov ecx, {START_LEN}
    mov ebx, {P_START}
    lea eax, [ebp+{OFF['put']:#x}]
    call eax
    cmp dword ptr [ebp+{FLAGS_OFF:#x}], 0
    jne L_s
    lea eax, [ebp+{NAME_OFF:#x}]
    push eax
    mov eax, 0x4d9120
    call eax
    add esp, 4
    movzx eax, al
    mov dword ptr [ebp+{FLAGS_OFF + 4:#x}], eax
L_s:
    popad
    mov ecx, dword ptr [0xb411a4]
    ret
""",
    "turn": f"""
    pushad
    call L_b
L_b:
    pop ebp
    sub ebp, L_b - {0x10000000 + OFF['turn']:#x}
    sub ebp, {OFF['turn']:#x}
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
""",
    # put: ebx = 플레이어(0..0xFF), esi = 내용, ecx = 길이; ebp = 섹션 시작. eax, edx, edi 사용.
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
}


def assemble() -> bytes:
    """섹션 코드 영역 (NAME_OFF 바이트). 각 진입점은 OFF 위치; 서로 부를 땐 ebp(섹션 시작) 기준이라 위치 독립."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    out = bytearray(NAME_OFF)
    for name, src in SOURCES.items():
        code = bytes(ks.asm(src, addr=0x10000000 + OFF[name])[0])
        nxt = min([o for o in OFF.values() if o > OFF[name]] + [NAME_OFF])
        assert len(code) <= nxt - OFF[name], (name, len(code))
        out[OFF[name]:OFF[name] + len(code)] = code
    return bytes(out)


CODE = bytes.fromhex(
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
    "8947040117ff470ca1b412b400890358884304c643050066894b068d7b08fcf3a4c3"
)
# v0.9053 의 첫 판 (호출 한 곳만 바꿈) — 이미 설치된 파일을 걷어낼 때 인식
LEGACY_CODE = bytes.fromhex(
    "60e8000000005d83ed068b7424288b4c242c81f900400000776385f6745f8d510b83e2fc8dbd001000008b47"
    "048d1c1081fb00002000761bbb0000200029c383fb047208c7440710ffffffff011f31c08947048d5c071001"
    "d08947040117ff470ca1b412b40089038a442424884304c643050066894b068d7b08fcf3a46168e0074400c3"
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


def body(save: bool = False) -> bytes:
    """save=False: 시작 저장 끄기 표시(FLAGS +0 = 1). 저장은 실험 기능이라 기본은 끔."""
    b = bytearray(CODE.ljust(CODE_SIZE, b"\0"))
    b[NAME_OFF:NAME_OFF + len(SAVE_NAME) + 1] = SAVE_NAME + b"\0"
    struct.pack_into("<I", b, FLAGS_OFF, 0 if save else 1)
    return bytes(b)


def _legacy_body() -> bytes:
    return LEGACY_CODE.ljust(CODE_SIZE, b"\0")


def _kind(data):
    """('new' | 'legacy' | None, 섹션 정보)."""
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    name, va, vsize, rptr, rsize, h = secs[-1]
    if name != SECTION_NAME:
        return None, None
    raw = bytes(data[rptr:rptr + rsize])
    ok_hdr = (vsize == VIRTUAL_SIZE and rsize == CODE_SIZE and rptr + rsize == len(data)
              and _u32(data, soi) == va + VIRTUAL_SIZE and _u32(data, h + 36) == CHARACTERISTICS)
    if not ok_hdr:
        raise ValueError("리플레이 기록 패치가 불완전하거나 알 수 없는 변경이 있습니다.")
    if raw in (body(False), body(True)) and all(data[o:o + len(b)] == _branch(o, va, t, k, len(b)) for o, b, t, k in SITES):
        return "new", (va, h, nsec)
    if (raw == _legacy_body() and data[SITES[0][0]:SITES[0][0] + 5] == _branch(SITES[0][0], va, 0, "call", 5)
            and all(data[o:o + len(b)] == b for o, b, t, k in SITES[1:])):
        return "legacy", (va, h, nsec)
    raise ValueError("리플레이 기록 패치가 불완전하거나 알 수 없는 변경이 있습니다.")


def state(data) -> bool:
    """패치 여부 (단축키 섹션은 먼저 걷어낸 상태). 이전 판(v0.9053)도 True. 알 수 없는 상태면 ValueError."""
    kind, _ = _kind(data)
    if kind:
        return True
    if all(data[o:o + len(b)] == b for o, b, t, k in SITES):
        return False
    raise ValueError("리플레이 기록 패치: 지원하지 않는 게임 파일이거나 다른 패치와 충돌합니다.")


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
    out[h:h + 40] = bytes(40)
    struct.pack_into("<H", out, nt + 6, nsec - 1)
    struct.pack_into("<I", out, soi, va)
    return bytes(out)


def saves_at_start(data) -> bool:
    """패치된 파일이 경기 시작에 게임 저장을 하는지 (단축키 섹션은 먼저 걷어낸 상태)."""
    kind, info = _kind(data)
    if kind != "new":
        return False
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    return _u32(data, secs[-1][3] + FLAGS_OFF) == 0


def apply(data, enabled: bool = True, save: bool = False) -> bytes:
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
    out += body(save)
    return bytes(out)


# ---- 런처 쪽: 실행 중인 게임에서 링 버퍼 읽기 ----
def find_section(read) -> int | None:
    """read(addr, size) 로 실행 중인 게임의 PE 머리를 읽어 .rkrec 섹션 VA 를 찾는다."""
    head = read(0x400000, 0x1000)
    nt = _u32(head, 0x3C)
    nsec = _u16(head, nt + 6)
    table = nt + 24 + _u16(head, nt + 20)
    for i in range(nsec):
        h = table + 40 * i
        if head[h:h + 8] == SECTION_NAME:
            return 0x400000 + _u32(head, h + 12)
    return None


def parse_start(blob: bytes) -> dict:
    seed, rand, rng, frame, local, opts = struct.unpack(START_FMT, blob[:START_LEN])
    return {"seed": seed, "rand": rand, "rng": rng.hex(), "frame": frame, "local": local, "options": opts.hex()}


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
        if self.total is None or total < self.total:
            self.total, self.pos = total, pos        # 처음 보거나 게임이 새로 켜짐: 지금부터
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
