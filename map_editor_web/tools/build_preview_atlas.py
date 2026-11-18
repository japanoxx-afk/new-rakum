"""런처 '맵 미리보기'용 타일·스프라이트 아틀라스(PNG) 생성.

입력: 게임 타일(JTL, 상하대칭 모드 포함 파일), 에디터 스프라이트 아틀라스(tiles/*_OBJ.js)
출력: map_preview_tiles/<TILESET>_<scale>.png, map_preview_tiles/atlas.json
사용: python build_preview_atlas.py <JTL 폴더> <저장소 루트>
"""
import base64, io, json, re, struct, sys
from pathlib import Path
import numpy as np
from PIL import Image

ROWS = [((256 - (2 + 4 * k)) // 2, 2 + 4 * k) for k in range(64)]
ROWS += ROWS[::-1]
SETS = [('East', 'EAST'), ('West', 'WEST'), ('Savage', 'SAVAGE'), ('Dungeon', 'DUNGEON')]


def tiles_of(jtl):
    J = jtl.read_bytes(); T, = struct.unpack_from('<I', J, 4); cnt, = struct.unpack_from('<H', J, 16); rec = 32784
    for i in range(cnt):
        px = np.frombuffer(J[T + i * rec + 16:T + (i + 1) * rec], dtype='<u2').astype(np.uint32)
        img = np.zeros((128, 256, 4), np.uint8); p = 0
        for y, (x0, w) in enumerate(ROWS):
            v = px[p:p + w]; p += w
            img[y, x0:x0 + w, 0] = ((v >> 11) & 31) * 255 // 31
            img[y, x0:x0 + w, 1] = ((v >> 5) & 63) * 255 // 63
            img[y, x0:x0 + w, 2] = (v & 31) * 255 // 31
            img[y, x0:x0 + w, 3] = 255
        yield Image.fromarray(img)


def build(jtl_dir, root, scales=(4, 8)):
    root = Path(root); out_dir = root / 'map_preview_tiles'; out_dir.mkdir(exist_ok=True)
    meta_all = {}
    for ts, (n, E) in enumerate(SETS):
        full_tiles = list(tiles_of(Path(jtl_dir) / f'{n}.jtl'))
        s = (root / 'map_editor_web/editor/tiles' / f'{E}_OBJ.js').read_text()
        meta = json.loads(re.search(r'meta:(\{.*?\}),img:', s).group(1))
        i = s.find('base64,') + 7; j = s.find('"', i)
        atlas = Image.open(io.BytesIO(base64.b64decode(s[i:j]))).convert('RGBA')
        per_scale = {}
        for SC in scales:
            TW, TH = 256 // SC, 128 // SC; CW, CH = TW + 2, TH + 2
            cells = []
            for t in full_tiles:
                a = np.asarray(t.resize((TW, TH), Image.BOX)).copy()
                a[..., 3] = np.where(a[..., 3] >= 96, 255, 0)
                big = np.zeros((CH, CW, 4), np.uint8); big[1:-1, 1:-1] = a
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):     # 1px 번짐으로 이음새 제거
                    sh = np.roll(np.roll(big, dy, 0), dx, 1); m = (big[..., 3] == 0) & (sh[..., 3] > 0); big[m] = sh[m]
                cells.append(Image.fromarray(big))

            def shrink(e):
                im = atlas.crop((e['x'], e['y'], e['x'] + e['w'], e['y'] + e['h']))
                return im.resize((max(1, round(e['w'] / SC)), max(1, round(e['h'] / SC))), Image.LANCZOS)
            subs = [shrink(e) for e in meta['sub']]; objs = [shrink(e) for e in meta['obj']]
            per = 16; W = per * CW; y = ((len(cells) + per - 1) // per) * CH; x = 0; rowh = 0; ps, po = [], []
            for lst, ims in ((ps, subs), (po, objs)):
                for im in ims:
                    if x + im.width > W: x = 0; y += rowh; rowh = 0
                    lst.append((x, y, im.width, im.height)); x += im.width + 1; rowh = max(rowh, im.height + 1)
            out = Image.new('RGBA', (W, y + rowh), (0, 0, 0, 0))
            for k, c in enumerate(cells): out.paste(c, ((k % per) * CW, (k // per) * CH))
            for im, p in zip(subs, ps): out.paste(im, p[:2])
            for im, p in zip(objs, po): out.paste(im, p[:2])
            name = f'{E}_{SC}.png'; out.save(out_dir / name, optimize=True)
            per_scale[str(SC)] = {'file': name, 'count': len(cells), 'per': per, 'cw': CW, 'ch': CH, 'sub': ps,
                                  'obj': [list(p) + [round(e['ox'] / SC), round(e['oy'] / SC)] for p, e in zip(po, meta['obj'])]}
            print(name, out.size)
        meta_all[str(ts)] = per_scale
    (out_dir / 'atlas.json').write_text(json.dumps({'tilesets': meta_all}, separators=(',', ':')))


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
