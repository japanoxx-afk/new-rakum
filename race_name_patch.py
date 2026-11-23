"""방 화면 종족 이름 한글화: Mu hŭl / Aren / Marduke -> 위국군 / 아스트리아 / 바르바로이.

종족 이름은 글자가 아니라 그림이다: Data\\Data002.FDB 안 DATA\\MENUDATA\\MENUCOMMON.S16 의 31~36번
(이름마다 보통(흰색)·고른 것(주황) 두 장. 방의 종족 칸과 종족 고르는 메뉴가 같은 그림을 쓴다).
이 그림 여섯 장만 한글 그림으로 바꾼다. Random / View 는 그대로.

S16 파일 (iCARUS _iCARUS_LoadImageSet@24 가 읽는 순서로 확인):
  +0x00 dword 4개: [0]=머리 크기(0x12+묶음 수*2), [1..3]=화소 형식별 그림 구역 시작 (565, 555, 565)
  +0x10 word 묶음 수, +0x12 word*묶음 수 = 묶음마다 장 수 (합 = 전체 장 수)
  그 뒤 [1] 까지: 만든 도구가 남긴 메모리 찌꺼기 — 게임은 읽지 않고 [화소 형식] 구역으로 바로 건너뛴다
  구역: 장마다 [14바이트 머리: +0xA 너비, +0xC 높이] [줄 시작 dword*높이, word 단위] [dword 크기] [RLE]
  RLE 한 줄: (건너뛸 칸 word, 그릴 칸 word, 화소 word*그릴 칸) 반복, (0,0) 으로 끝.
  (머리와 구역 사이에는 장마다 [머리 14][dword][줄 표] 가 든 표가 있다 — 만든 도구가 남긴 것으로 줄 표 값은
   쓰레기이고 게임은 읽지 않는다. 건드리지 않는다.)
게임은 장을 차례로 읽으므로 장 크기는 달라져도 된다. 다만 다른 장·구역·FDB 안 다른 파일의 위치가 하나도
바뀌지 않도록, 구역마다 여섯 장의 바이트 합을 원본과 똑같이 맞춘다 (한글 그림이 더 작고, 남는 만큼 마지막
장의 RLE 뒤에 0 을 채움). 그래서 바뀌는 것은 FDB 안 여섯 장 자리(구역 셋)뿐이다.

원본 그림은 저장소에 넣지 않는다 (게임 자산). 처음 바꿀 때 원본 S16 을 Data\\MENUCOMMON.S16.orig 로 남겨 두고,
한글 그림을 다시 고칠 때는 그 원본에서 새로 만든다. 한글 그림은 tools/make_race_name_sprites.py 가 만든 값.
"""
import base64
import hashlib
import os
import struct
import zlib
from pathlib import Path

NAME = "DATA\\MENUDATA\\MENUCOMMON.S16"
FIRST = 31                                   # 31·32 Mu hŭl, 33·34 Aren, 35·36 Marduke (보통, 고른 것)
# 원본 1.000d 의 31~36번 (너비, 높이, sha256(줄 표+크기+RLE, 565 구역) 앞 32자) — 이 그림일 때만 바꾼다
ORIGINAL = (
    (51, 15, "b781bf9090401e6dca9a21b6a97f5e40"), (51, 15, "10d3224b159670fd91878e562db8d597"), (37, 12, "4d923c24a9834cca732fa4d5227403eb"), (37, 12, "6bac6effdb787aee8783d52e820236dd"), (69, 15, "ecbc34c2b50ac954a546c42b78494f8b"), (69, 15, "893728ff9a74a219525e1ac4a5ec6c77"),
)
BACKUP = "MENUCOMMON.S16.orig"

# tools/make_race_name_sprites.py 가 만든 값 (Noto Sans CJK KR Bold 13px). 고치려면 그 도구를 다시 돌린다.
SPRITES = (
    (36, 14, "eNpjYACB11XruhmgwOb9pTUQ1rnJqBCmApf4rHv7/4Pg97Mg3v7/Jlsh4hBRBISpxy7+ecv+//xzGBgurdn///1kZHOQgchWhDnIQBguvu3ovu8wezatwWVO6V7s5oTAxd9N3v/f4lrhkln39n1/XYXLHItrdd+xmXMd7goGBoM5t5/N+z7rXm83InwKl6CHAggazEEP5d/P6r4jQhoaZ5MnLuGuhrmHfw4E1r6XeQ5j4zb/3GRk/rzv6yaj+8vm/ax72Hw0657Ne2T+e6DrQKFVuAQW2jBz1k0Gwdj3v59BWPjNgZi1/39vN6o5qC5FTT+geCXWHFQASmWo5mADpJrz/ez7yQiIUMXdPO3oqSrizUGFvd0MVAMAmL9HRQ=="),
    (36, 14, "eNqlkzEShCAMRR2O4lE4CkewtJOSktKt0NKS0o6x3JKSypNssmxEHNhxZ/MLYwbfJJ/YNBisE7L5hPBsjplUuehErc42E1DTim8m8CXWYzWJzpfr7QwEDTR4IjtxzsHnxDlHe9SlpcwE9qhxxFLm8KMulQlu3UecjnU1jluHImeyie90+xwC26LXkeP01YW3g/rqMocvk9PxzqSCrnrqZ1JRg+ee8jofp0pC9nUu2IOtNBH077MJsTtwax/JbeIIhcJ+YvadQ17TJhIn7zTfH7zXu5zanhCnFL9yJlv6L+BULy3uzl1OrvRv/h8vGoURQQ=="),
    (60, 14, "eNq9kyFvwkAUx/EIxMQM32AIPgAfAbNkS4bgG2wCgWBJZyobVBMEaaoqG8SSIZq0VZUgELdkTU52YuIE4glEt9eXphzXYyyQvSfa/nP3+/e9e9doyAGrlDcuEhFsfFXd59+HQzHnNya+T5gB8so4/+CHipykBrz8Djit2vrH+OMwzlmyy1zQ+bqKcr0WdpWkTq2Wg2mA7KvjRzAOad3Vm+o78rCCvin7bn19f3tC9q3n9804n1r4lmYPTPU1IOWG2GX6PvcEqX1zYWPK9er4wo7zZlHNgCF9wpDFElRazgu48PWMa9qCdhPxfTW1ynyyjp2vjv9oxTntDPik+B8XWg721RBYS6fY03VcKHlIhBXVRln6DoV6Gnp+BHchnQM+qz6PvFtvn/Pqr+36eaZ66n31/GUSwSxJs0gzz6dGwF3oOiNv4y+TOa989fxxcb865rm+0c80GKL9OWCzpGlWU38Kv9Tp/hwm1lOvq6T62/abL06zmsf0S/meG3/z/a/4BkbR3II="),
    (60, 14, "eNq9VDuWhCAQ9HEUj8JROMKGZnRISLgbiaEh4WZqaEhI5Em2W4bHyGdm9vO2OxBLqGrKhq67hrH93v1JjJ5NJXrPL2bh2NYPNGab9Pn6vJLRXzOg/R7fw3x8To/4xTx6Y7kL62u6JbJ8gkp54wGjKGWm2+IfvZjTvFx30bQDDpkDU9tf4a66df5+QByCT8da6lL10vG97bNwAeUgFOV1vy1+UPj9dP5YiZ1txGXs2QNa4pi9GUXsApKusQJiRi/q/7fFzyG6GOtBVHOcKR2phTWhgthfp65KGXXBlX+jzY/4zX96Jp+P90Xf87CP2EF5P4fa6rptfrCjB0su1fv51cA+wJ0cmk1g2ZZ02/yPz+/rurR37EF3rKgzPDu/14h4OD95Gt3Ca/dV7bQ906VeKvPEVZn1e/Jnur+/n7+j+1/xBYmckZI="),
    (59, 14, "eNpjYEAF4udu3WMgAZCqnoHB5n3hEgaGed9NtoJ4td+/n2VgqLxW+x0i+7pq/39UCBEnVT0DQ8Cc389+PwPZBQL7/29aAyJD9oJ4+75LnEM2hYGBfw4Cfj8LMwW3+veTERCh/tzk/f8rr0Vc2/+ffw4xtiKDTWsI24pd/a57v58h0zBbYRDVFFwhRqr6fd9Dwa4U3goRgdlqca63u7cb5naQ+mtHIaZsO7puMgLCbCVV/ectIHriElRbUUNs3neDOT7NMFPOTUZA7CFMSD3Mr5+34LMVd4hBUiGp6nHFq8U1kMvwpw4EIKTe5v0slBwMSsOR1yyAMWEwh3Bqwm0rfvXotkLyq8xz1PyKCmCmFC5BDy8QhLiWEvX4bUUtI2AQ0wxS1ROylThAqnrsttIHAABLOxSR"),
    (59, 14, "eNq9lDGuhCAQhiccxaN4FI7wbiAlJeVuBVtuaUnHbmlpScVJniwSAUeUbLIziQb98v84MwiQh9HdBA3RygPQ2QiAwfZPvxqs0gDkPdjwlvxJm2d43sovOxP91M/uFlbSkru/BhVpTaYCoHiSOqoc84xvqcbIMy6te7mXtEpccU2D3M9dcb5bvnO9T6lrTHOpYu08/eyye4Qn0dVoyiiLKp5XY1BhI+VbRpVWvnv4u7vlrnnFfP17FlXSXuEVPufxb8X7tK+YEbW+HvGxn2VfnfY7q0/HFmc8nck7Xa8zrMsZxqfj2LXOl674eS0mflUxoqzXZ2rEt3zddflHiH0i53Lj+T7xWtVcr0Urj7v+Jv4BthnPKw=="),
)


class FormatError(ValueError):
    pass


def _encode(width, height, pixels):
    """화소(0=빈 칸) -> (줄 표, RLE)."""
    rows, blob = [], bytearray()
    for y in range(height):
        rows.append(len(blob) // 2)
        line = pixels[y * width:(y + 1) * width]
        x = at = 0
        while x < width:
            while x < width and not line[x]:
                x += 1
            end = x
            while end < width and line[end]:
                end += 1
            if end > x:
                blob += struct.pack(f"<HH{end - x}H", x - at, end - x, *line[x:end])
                at = end
            x = end
        blob += b"\0\0\0\0"
    return struct.pack(f"<{height}I", *rows), bytes(blob)


def _to555(value):
    return ((value >> 1) & 0x7FE0) | (value & 0x1F) if value else 0


def new_frames(total=None):
    """구역(565, 555, 565)마다 여섯 장의 (너비, 높이, 줄 표+크기+RLE).
    total 을 주면 여섯 장의 합이 그 바이트가 되도록 마지막 장 RLE 뒤에 0 을 채운다 (넘치면 FormatError)."""
    out = ([], [], [])
    for width, height, packed in SPRITES:
        pixels = struct.unpack(f"<{width * height}H", zlib.decompress(base64.b64decode(packed)))
        for section, convert in enumerate((None, _to555, None)):
            rows, blob = _encode(width, height, [convert(p) for p in pixels] if convert else pixels)
            out[section].append([width, height, rows, blob])
    result = []
    for frames in out:
        if total is not None:
            pad = total - sum(len(rows) + 4 + len(blob) for _, _, rows, blob in frames)
            if pad < 0 or pad % 2:
                raise FormatError("한글 그림이 원본 자리보다 큼")
            frames[-1][3] += b"\0" * pad
        result.append([(w, h, rows + struct.pack("<I", len(blob)) + blob) for w, h, rows, blob in frames])
    return result


def parse(data):
    """-> (구역 시작 세 개, 구역마다 [(머리 14바이트, 줄 표+크기+RLE)])."""
    if len(data) < 0x20:
        raise FormatError("S16 이 너무 짧음")
    starts = struct.unpack_from("<3I", data, 4)
    groups = struct.unpack_from("<H", data, 16)[0]
    if not 0 < groups <= 4096 or struct.unpack_from("<I", data, 0)[0] != 18 + 2 * groups:
        raise FormatError("S16 머리가 다름")
    count = sum(struct.unpack_from(f"<{groups}H", data, 18))
    if count <= FIRST + len(ORIGINAL) or not 18 + 2 * groups <= starts[0] < starts[1] < starts[2] < len(data):
        raise FormatError("S16 구역 위치가 다름")
    sections = []
    for number, start in enumerate(starts):
        pos, frames = start, []
        for _ in range(count):
            if pos + 18 > len(data):
                raise FormatError("S16 이 잘림")
            width, height = struct.unpack_from("<2h", data, pos + 10)
            if not (0 < width <= 4096 and 0 < height <= 4096) or pos + 18 + 4 * height > len(data):
                raise FormatError("S16 그림 크기가 다름")
            size = struct.unpack_from("<I", data, pos + 14 + 4 * height)[0]
            end = pos + 18 + 4 * height + size
            if end > len(data):
                raise FormatError("S16 이 잘림")
            frames.append((pos, data[pos:pos + 14], data[pos + 14:end]))
            pos = end
        if pos != (starts[number + 1] if number < 2 else len(data)):
            raise FormatError("S16 구역 끝이 다름")
        sections.append(frames)
    return starts, sections


def _targets(frames):
    return frames[FIRST:FIRST + len(ORIGINAL)]


def _planned(sections):
    """지금 여섯 장이 차지한 자리에 넣을 한글 그림 (구역마다)."""
    totals = {sum(len(body) for _, _, body in _targets(frames)) for frames in sections}
    if len(totals) != 1:
        raise FormatError("구역마다 그림 크기가 다름")
    return new_frames(totals.pop())


def state(data):
    """'original' (영문 원본) / 'patched' (지금 한글 그림) / 'unknown' (모르는 그림 — 건드리지 않음)."""
    try:
        sections = parse(data)[1]
    except (FormatError, struct.error):
        return "unknown"
    if all((*struct.unpack_from("<2h", head, 10), hashlib.sha256(body).hexdigest()[:32]) == want
           for (_, head, body), want in zip(_targets(sections[0]), ORIGINAL)):
        return "original"
    try:
        new = _planned(sections)
    except FormatError:
        return "unknown"
    if all((*struct.unpack_from("<2h", head, 10), body) == want
           for s in range(3) for (_, head, body), want in zip(_targets(sections[s]), new[s])):
        return "patched"
    return "unknown"


def transform(data):
    """원본 S16 -> 한글 그림 S16. 여섯 장 자리(구역 셋) 말고는 한 바이트도 바뀌지 않는다."""
    if state(data) != "original":
        raise FormatError("원본 종족 이름 그림이 아님")
    sections = parse(data)[1]
    new = _planned(sections)
    out = bytearray(data)
    for frames, replacement in zip(sections, new):
        at = _targets(frames)[0][0]
        for (_, head, _), (width, height, body) in zip(_targets(frames), replacement):
            piece = head[:10] + struct.pack("<2h", width, height) + body
            out[at:at + len(piece)] = piece
            at += len(piece)
        if at != frames[FIRST + len(ORIGINAL)][0]:
            raise FormatError("만든 그림 크기가 다름")
    out = bytes(out)
    if len(out) != len(data) or state(out) != "patched":
        raise FormatError("만든 S16 검증 실패")
    return out


def _find(index, fdb_size):
    """IDX 에서 MENUCOMMON.S16 의 FDB 위치 ([dword ?][dword 위치][이름\\0] 항목)."""
    key = NAME.encode("ascii")
    upper = index.upper()
    found = set()
    at = upper.find(key)
    while at >= 0:
        if at >= 4 and upper[at + len(key):at + len(key) + 1] == b"\0":
            found.add(struct.unpack_from("<I", index, at - 4)[0])
        at = upper.find(key, at + 1)
    if len(found) != 1:
        raise FormatError("IDX 에서 MENUCOMMON.S16 을 찾지 못함")
    offset = found.pop()
    if not 0 < offset < fdb_size - 4:
        raise FormatError("IDX 위치가 다름")
    return offset


def apply(data_dir):
    """게임 Data 폴더의 종족 이름 그림을 한글로. -> '' (이미 됨 / 못 함) 또는 한 일 설명.
    모르는 그림이면 건드리지 않는다. 쓰는 중 끊겨도 원본 사본(.orig)에서 다시 만든다."""
    data_dir = Path(data_dir)
    fdb_path, backup = data_dir / "Data002.FDB", data_dir / BACKUP
    index = (data_dir / "Data002.IDX").read_bytes()
    offset = _find(index, fdb_path.stat().st_size)
    with open(fdb_path, "rb") as fdb:
        fdb.seek(offset)
        size = struct.unpack("<I", fdb.read(4))[0]
        if not 0x20 <= size <= 64 * 1024 * 1024:
            raise FormatError("FDB 안 파일 크기가 다름")
        current = fdb.read(size)
    if len(current) != size:
        raise FormatError("FDB 가 잘림")
    now = state(current)
    if now == "patched":
        return ""
    if now == "original":
        source = current
        if not backup.is_file() or backup.read_bytes() != current:
            temp = backup.with_name(backup.name + ".tmp")
            temp.write_bytes(current)
            os.replace(temp, backup)
    else:                                        # 예전 한글 그림이거나 쓰다 끊긴 것: 원본 사본이 있을 때만 다시 만든다
        if not backup.is_file():
            return ""
        source = backup.read_bytes()
        if len(source) != size or state(source) != "original":
            return ""
    new = transform(source)
    with open(fdb_path, "r+b") as fdb:
        fdb.seek(offset + 4)
        fdb.write(new)
        fdb.flush()
        os.fsync(fdb.fileno())
    return "방 화면 종족 이름을 한글로 바꿨습니다."


def restore(data_dir):
    """원본 사본이 있으면 영문 그림으로 되돌린다. -> 되돌렸으면 True."""
    data_dir = Path(data_dir)
    fdb_path, backup = data_dir / "Data002.FDB", data_dir / BACKUP
    if not backup.is_file():
        return False
    source = backup.read_bytes()
    offset = _find((data_dir / "Data002.IDX").read_bytes(), fdb_path.stat().st_size)
    with open(fdb_path, "r+b") as fdb:
        fdb.seek(offset)
        if struct.unpack("<I", fdb.read(4))[0] != len(source) or state(source) != "original":
            return False
        fdb.write(source)
    return True
