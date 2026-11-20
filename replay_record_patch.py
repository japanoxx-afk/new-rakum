"""리플레이 명령 기록 패치 (Rhakmu.exe 1.000d) — 실제 게임 화면 리플레이 1단계.

대전은 모든 PC가 같은 명령을 같은 프레임에 실행하는 방식(lockstep)이다.
  Game_Multi (0x4D7A80) 매 프레임: 시뮬레이션 1단계, 프레임 번호 [0xB412B4] += 1
  5프레임마다 0x44A840: 턴이 다 모인 플레이어마다 0x4407E0(플레이어, 명령 묶음, 길이) 호출 (0x44AABC)
  난수: srand([0x6E1A78]) (0x4D7376, 대전 시작), 매 턴 묶음의 0x2000 명령에 rand 값이 실려 PC끼리 비교
그래서 시작 조건(시드·맵·플레이어)과 '몇 번째 프레임에 어느 플레이어의 어떤 명령 묶음이 실행됐는지'만
있으면 게임 엔진으로 경기를 다시 돌릴 수 있다 (2단계).

패치: 0x44AABC 의 call 0x4407E0 을 새 섹션 .rkrec 의 코드로 바꾼다. 코드는 기록을 링 버퍼에 덧붙인 뒤
원래 0x4407E0 으로 그대로 넘어간다 (게임 동작은 같음, 상대 PC가 이 패치를 안 써도 됨).
섹션 위치는 다른 패치 조합에 따라 달라지므로 코드는 위치 독립, 호출 주소는 적용할 때 계산한다.

링 버퍼 (섹션 + BUF):
  +0 total (지금까지 쓴 바이트, 줄지 않음)   +4 pos (다음 쓸 위치)   +8 'RKR1'   +0xC 기록 수
  +0x10.. 데이터 RING 바이트. 기록 = [u32 프레임][u8 플레이어][u8 0][u16 길이][명령 묶음] (4바이트 맞춤)
  끝에 안 들어가면 그 자리에 0xFFFFFFFF 를 쓰고 처음(0)부터 이어 쓴다.
"""
from __future__ import annotations

import struct

SECTION_NAME = b".rkrec\0\0"
SITE = 0x4AABC                        # 파일 오프셋 = VA 0x44AABC (call 0x4407E0)
SITE_VA = 0x44AABC
SITE_ORIGINAL = bytes.fromhex("e81f5dffff")
DISPATCH = 0x4407E0
FRAME = 0xB412B4
CODE_SIZE = 0x1000
BUF = 0x1000                          # 섹션 안 버퍼 머리 위치
DATA = BUF + 0x10
RING = 0x200000
VIRTUAL_SIZE = CODE_SIZE + 0x10 + RING + 0x1000
VIRTUAL_SIZE = (VIRTUAL_SIZE + 0xFFF) & ~0xFFF
CHARACTERISTICS = 0xE0000060
MAGIC = b"RKR1"
WRAP = 0xFFFFFFFF
MAX_BATCH = 0x4000

SOURCE = f"""
entry:
    pushad
    call here
here:
    pop ebp
    sub ebp, here - entry
    mov esi, dword ptr [esp+0x28]
    mov ecx, dword ptr [esp+0x2c]
    cmp ecx, {MAX_BATCH}
    ja done
    test esi, esi
    je done
    lea edx, [ecx+11]
    and edx, 0xfffffffc
    lea edi, [ebp+{BUF}]
    mov eax, dword ptr [edi+4]
    lea ebx, [eax+edx]
    cmp ebx, {RING}
    jbe fits
    mov ebx, {RING}
    sub ebx, eax
    cmp ebx, 4
    jb nomark
    mov dword ptr [edi+eax+0x10], {WRAP}
nomark:
    add dword ptr [edi], ebx
    xor eax, eax
    mov dword ptr [edi+4], eax
fits:
    lea ebx, [edi+eax+0x10]
    add eax, edx
    mov dword ptr [edi+4], eax
    add dword ptr [edi], edx
    inc dword ptr [edi+0xc]
    mov eax, dword ptr [{FRAME:#x}]
    mov dword ptr [ebx], eax
    mov al, byte ptr [esp+0x24]
    mov byte ptr [ebx+4], al
    mov byte ptr [ebx+5], 0
    mov word ptr [ebx+6], cx
    lea edi, [ebx+8]
    cld
    rep movsb
done:
    popad
    push {DISPATCH:#x}
    ret
"""


def assemble():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(SOURCE, addr=0x10000000)[0])


CODE = bytes.fromhex(
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


def _call(section_va):
    return b"\xe8" + struct.pack("<i", (0x400000 + section_va) - (SITE_VA + 5))


def body():
    return CODE.ljust(CODE_SIZE, b"\0")


def state(data) -> bool:
    """패치 여부 (단축키 섹션은 먼저 걷어낸 상태). 알 수 없는 상태면 ValueError."""
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    name, va, vsize, rptr, rsize, h = secs[-1]
    site = bytes(data[SITE:SITE + 5])
    if name == SECTION_NAME:
        if (site == _call(va) and vsize == VIRTUAL_SIZE and rsize == CODE_SIZE and rptr + rsize == len(data)
                and bytes(data[rptr:rptr + rsize]) == body() and _u32(data, soi) == va + VIRTUAL_SIZE
                and _u32(data, h + 36) == CHARACTERISTICS):
            return True
        raise ValueError("리플레이 기록 패치가 불완전하거나 알 수 없는 변경이 있습니다.")
    if site == SITE_ORIGINAL:
        return False
    raise ValueError("리플레이 기록 패치: 지원하지 않는 게임 파일입니다.")


def strip(data) -> bytes:
    if not state(data):
        return bytes(data)
    nt, nsec, table, salign, falign, soi, secs = _layout(data)
    name, va, vsize, rptr, rsize, h = secs[-1]
    out = bytearray(data[:rptr])
    out[SITE:SITE + 5] = SITE_ORIGINAL
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
    out[SITE:SITE + 5] = _call(new_va)
    out += body()
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
        if head[8:12] == b"\0\0\0\0":
            pass                                   # 아직 기록 없음 (MAGIC 은 쓰지 않음; 0 이면 처음)
        if self.total is None or total < self.total:
            self.total, self.pos = total, pos        # 처음 보거나 게임이 새로 켜짐: 지금부터
            return [], 0
        new = total - self.total
        if new == 0:
            return [], 0
        lost = 0
        if new > RING:
            lost = new - RING
            self.total, self.pos = total, pos
            return [], lost
        out = []
        start, end = self.pos, pos
        if start <= end and new <= end - start:
            chunks = [(start, self.read(self.buf + 0x10 + start, end - start))]
        else:
            chunks = [(start, self.read(self.buf + 0x10 + start, RING - start)), (0, self.read(self.buf + 0x10, end))]
        for _, blob in chunks:
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
        return out, lost
