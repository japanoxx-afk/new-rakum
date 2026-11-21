"""editor/tiles/*_OBJ.js 의 장식물·자원 스프라이트 오프셋(ox, oy)을 게임 원본에서 다시 계산한다.

게임은 오브젝트를 (칸 x*32 + BLD dx + S16 프레임 left, 칸 y*32 + BLD dy + S16 프레임 top) 에 그린다.
아틀라스에는 프레임의 잘린 그림만 들어 있으므로 ox/oy 에 프레임 left/top 까지 더해야 게임과 같은 곳에 그려진다.
(이전 아틀라스는 BLD dx/dy 만 넣어 자원이 2~6px, 나무는 최대 80px 넘게 왼쪽 위로 그려졌다.)

사용: python map_editor_web/tools/obj_offsets.py [게임 Data 폴더]
"""
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from stb_tool import _iter_idx  # noqa: E402

TILES = ROOT / 'map_editor_web' / 'editor' / 'tiles'
SETS = ('EAST', 'WEST', 'SAVAGE', 'DUNGEON')


def read_asset(data_dir, name):
    archive = Path(data_dir) / 'Data000.FDB'
    offs = {o for o, n in _iter_idx((Path(data_dir) / 'Data000.IDX').read_bytes(), archive.stat().st_size) if n.upper() == name.upper()}
    if len(offs) != 1:
        raise ValueError('리소스 위치 확인 실패: ' + name)
    with archive.open('rb') as f:
        f.seek(offs.pop())
        size = struct.unpack('<I', f.read(4))[0]
        return f.read(size)


def frame_heads(s16):
    """S16 이미지 묶음: 그룹별 프레임 수, 프레임마다 (left, top, w, h)."""
    groups = struct.unpack_from('<H', s16, 16)[0]
    counts = struct.unpack_from('<%dH' % groups, s16, 18)
    pos = struct.unpack_from('<I', s16, 4)[0]
    frames = []
    for _ in range(sum(counts)):
        _, left, _, top, _, w, h = struct.unpack_from('<7h', s16, pos)
        pos += 14 + h * 4
        pos += 4 + struct.unpack_from('<I', s16, pos)[0]
        frames.append((left, top, w, h))
    return counts, frames


def bld_records(bld, count, groups):
    """BLD 오브젝트 정의를 앞에서부터: (dx, dy, 그룹, 칸 너비, 칸 높이). 그룹 번호는 계속 커진다."""
    out, p = [], 4
    while len(out) < count and p <= len(bld) - 24:
        dx, dy, zero, group, w, h = struct.unpack_from('<iiiIii', bld, p)
        last = out[-1][2] if out else -1
        if zero == 0 and -512 < dx < 512 and -512 < dy < 512 and 1 <= w <= 8 and 1 <= h <= 8 and last < group < groups:
            out.append((dx, dy, group, w, h))
            p += 24 + w * h
        else:
            p += 1
    if len(out) != count:
        raise ValueError('BLD 오브젝트 정의 수가 맞지 않습니다')
    return out


def game_offsets(data_dir, theme):
    prefix = 'EWSD'[theme]
    bld = read_asset(data_dir, 'DATA\\IMAGE\\%s_OBJECT.BLD' % prefix)
    s16 = read_asset(data_dir, 'DATA\\IMAGE\\%s_OBJECT.S16' % prefix)
    counts, frames = frame_heads(s16)
    out = []
    for dx, dy, group, w, h in bld_records(bld, struct.unpack_from('<I', bld)[0], len(counts)):
        left, top, fw, fh = frames[sum(counts[:group])]
        out.append({'ox': dx + left, 'oy': dy + top, 'w': fw, 'h': fh, 'fw': w, 'fh': h})
    return out


OBJ_RE = re.compile(r'("obj": \[)(.*?)(\])', re.S)
ENTRY_RE = re.compile(r'\{"x": (\d+), "y": (\d+), "w": (\d+), "h": (\d+), "ox": (-?\d+), "oy": (-?\d+), "fw": (\d+), "fh": (\d+)\}')


def rewrite(text, offsets):
    m = OBJ_RE.search(text)
    entries = list(ENTRY_RE.finditer(m.group(2)))
    if len(entries) != len(offsets):
        raise ValueError('아틀라스와 BLD 오브젝트 수가 다릅니다')
    parts, last = [], 0
    for e, g in zip(entries, offsets):
        x, y, w, h, _, _, fw, fh = map(int, e.groups())
        if (w, h, fw, fh) != (g['w'], g['h'], g['fw'], g['fh']):
            raise ValueError('아틀라스 그림 크기/칸 크기가 게임과 다릅니다')
        parts.append(m.group(2)[last:e.start()])
        parts.append(json.dumps({'x': x, 'y': y, 'w': w, 'h': h, 'ox': g['ox'], 'oy': g['oy'], 'fw': fw, 'fh': fh}))
        last = e.end()
    parts.append(m.group(2)[last:])
    return text[:m.start(2)] + ''.join(parts) + text[m.end(2):]


def main(data_dir=r'C:\Program Files (x86)\TriggerSoft\RhakMu\Data'):
    for theme, name in enumerate(SETS):
        path = TILES / (name + '_OBJ.js')
        raw = path.read_bytes()
        text = raw.decode('ascii')
        new = rewrite(text, game_offsets(data_dir, theme))
        if new != text:
            path.write_bytes(new.encode('ascii'))
        print(name, '변경' if new != text else '그대로')


if __name__ == '__main__':
    main(*sys.argv[1:])
