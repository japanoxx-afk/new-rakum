import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

import map_editor_web as mew

HERE = Path(__file__).resolve().parent


def _req(url, data=None, method=None):
    r = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class EditorBuildTests(unittest.TestCase):
    """배포되는 editor/RhakMuMapEditor.html 이 src 로 다시 만든 것과 같고, 벽(최소 경계) 모드가 들어 있는지."""

    def test_built_page_matches_sources_and_has_wall_mode(self):
        src = HERE / 'map_editor_web' / 'src'
        rd = lambda name: (src / name).read_text(encoding='utf-8').replace('\r\n', '\n')
        core = rd('core.js').replace('__SEC6__', (src / 'sec6_default.b64').read_text().strip())
        page = rd('index.html').replace('/*__CORE__*/', core).replace('/*__APP__*/', rd('app.js'))
        built = (HERE / 'map_editor_web' / 'editor' / mew.EDITOR_PAGE).read_text(encoding='utf-8').replace('\r\n', '\n')
        self.assertEqual(built, page, 'python map_editor_web/src/build.py 로 다시 빌드하세요')
        self.assertIn('id="brushSize" min="0"', page)                 # 크기 0 = 벽
        self.assertIn('const WALL_BAND = { 5: 4, 7: 6, 8: 6 };', page)  # 언덕/높은 언덕/고지대 물 -> 경계 절벽
        # 벽 모드로 좌·우·위로 이어 그릴 때 체크무늬를 꼭짓점 하나로만 메워 2x2 가 되지 않게
        # (브라우저에서 확인: 이어 그린 두 점 사이 4 -> 3 꼭짓점, 남는 체크무늬 0)
        self.assertIn('R.smoothDiagonals(m, ch, brush, S.brushSize === 0)', page)
        self.assertIn('thin && tt === T ? [pickThin(m, other, T)] : other', page)


def _obj_meta(tileset):
    s = (HERE / 'map_editor_web' / 'editor' / 'tiles' / (tileset + '_OBJ.js')).read_text(encoding='ascii')
    a = s.index('[', s.index('"obj"'))
    return json.loads(s[a:s.index(']', a) + 1])


class ObjectPlacementTests(unittest.TestCase):
    """에디터의 자원·장식물·시작 위치가 게임과 같은 칸에 그려지는지.

    게임: 지형 레코드 (col,row) 는 칸 X..X+7, Y..Y+3 (X = col*8 + (row&1)*4, Y = row*2) 을 덮고 (0040B6F0),
    오브젝트는 칸 (x,y) 의 픽셀 (x*32, y*32) 에 BLD dx + S16 프레임 left 를 더해 그린다 (00439E60).
    에디터는 지형 다이아몬드 중심을 (X*32, Y*32) 에 그리므로 오브젝트 칸은 (-128, -64) 만큼 옮겨 그려야 한다.
    """

    def page(self):
        return (HERE / 'map_editor_web' / 'editor' / mew.EDITOR_PAGE).read_text(encoding='utf-8')

    def test_object_cells_are_shifted_to_the_game_grid(self):
        page = self.page()
        self.assertIn('const CELL_OX = -128, CELL_OY = -64;', page)
        self.assertIn('tileAtWorld(m, cellX(cx) + 16, cellY(cy) + 16)', page)      # 물/절벽·본진 검사도 게임 칸 기준
        self.assertIn("o.kind === R.KIND.SUB ? [o.x * 32, o.y * 32] : [R.cellX(o.x), R.cellY(o.y)]", page)
        self.assertIn('return R.worldCell(wx, wy);', page)                          # 클릭한 칸 = 저장되는 칸
        self.assertIn('const px = R.cellX(p.x) + 16, py = R.cellY(p.y) + 16', page)  # 시작 위치
        for old in ('o.x * 32 + e.ox', 'p.x * 32 + 16', 'Math.floor(w.x / 32)', 'strokeRect(128, 128,'):
            self.assertNotIn(old, page)

    def test_resource_sprite_offsets_include_s16_frame_origin(self):
        # (BLD dx + 프레임 left, BLD dy + 프레임 top) — 우물, 금광. 예전 값은 BLD dx/dy 만 사용.
        expected = {'EAST': [(23, 20), (-30, -12)], 'WEST': [(23, 19), (-29, -14)],
                    'SAVAGE': [(22, 21), (-29, -12)], 'DUNGEON': [(20, 13), (-28, -13)]}
        for name, want in expected.items():
            meta = _obj_meta(name)
            self.assertEqual([(e['ox'], e['oy']) for e in meta[-2:]], want, name)
            self.assertEqual([(e['fw'], e['fh']) for e in meta[-2:]], [(3, 2), (3, 1)], name)

    def test_sprite_offsets_match_installed_game(self):
        data = Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Data')
        if not (data / 'Data000.FDB').exists():
            self.skipTest('게임 설치본 없음')
        import importlib.util
        spec = importlib.util.spec_from_file_location('obj_offsets', HERE / 'map_editor_web' / 'tools' / 'obj_offsets.py')
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        for theme, name in enumerate(tool.SETS):
            game = tool.game_offsets(data, theme)
            meta = _obj_meta(name)
            self.assertEqual([(e['ox'], e['oy'], e['w'], e['h']) for e in meta],
                             [(g['ox'], g['oy'], g['w'], g['h']) for g in game], name)


def _sub_tpl():
    src = (HERE / 'map_editor_web' / 'src' / 'core.js').read_text(encoding='utf-8')
    a = src.index('const SUB_TPL = ') + len('const SUB_TPL = ')
    return {int(k): v for k, v in json.loads(src[a:src.index(';', a)]).items()}


def _to_ab(u, v):
    return (u + v - 1) >> 1, (u - v - 1) >> 1


class BridgeTests(unittest.TestCase):
    """왼편·오른편 다리 한 번 클릭 배치 (core.js planBridge). 브라우저에서 원본 다리 40개 중 38개를 같은 앵커에 다시 놓는 것 확인."""

    def anchor_parity(self, tpl):
        dx, dy = tpl[0][:2]
        return 1 - ((dx // 128 + dy // 64) & 1)

    def test_bridge_templates_are_two_wide_channels_between_two_banks(self):
        tpl = _sub_tpl()
        for sid, axis in ((0, 1), (1, 0)):           # 0: B 방향으로 건넌다, 1: A 방향
            u0 = 10 + self.anchor_parity(tpl[sid])     # v0 = 10 -> u0 + v0 parity = anchor parity
            pts = [(_to_ab(u0 + dx // 128, 10 + dy // 64), c) for dx, dy, c in tpl[sid]]
            water = sorted({p[axis] for p, c in pts if c == 0})
            self.assertEqual(len(water), 2, sid)       # 물길 폭 2 꼭짓점 = 다리 길이 고정
            ground = [p[axis] for p, c in pts if c == 1]
            self.assertTrue(any(g < water[0] for g in ground) and any(g > water[-1] for g in ground), sid)
            self.assertEqual({c for _, c in pts}, {0, 1}, sid)

    def test_anchor_parity_matches_shipped_maps(self):
        maps = Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Data\Maps')
        files = sorted(maps.glob('*.rkm')) if maps.exists() else []
        if not files:
            self.skipTest('게임 설치본 없음')
        from rkm_format import RkmMap
        import struct
        tpl, seen = _sub_tpl(), {}
        for f in files:
            m = RkmMap(f.read_bytes())
            for r in m.objects()[m.object_counts[0]:]:
                if r[2] != 3:
                    continue
                sid = struct.unpack_from('<H', r, 4)[0]
                x, y = struct.unpack_from('<II', r, 8)
                if sid in tpl:
                    self.assertEqual(((x // 4) + (y // 2)) & 1, self.anchor_parity(tpl[sid]), (f.name, sid, x, y))
                    seen[sid] = seen.get(sid, 0) + 1
        self.assertGreaterEqual(seen.get(0, 0) + seen.get(1, 0), 40)

    def test_page_places_bridges_with_one_click(self):
        page = (HERE / 'map_editor_web' / 'editor' / mew.EDITOR_PAGE).read_text(encoding='utf-8')
        self.assertIn('function planBridge(m, id, wx, wy, ignore)', page)
        self.assertIn("if (S.tool === 'sub' && isBridge(S.subSel)) { placeBridge(wx, wy); return; }", page)
        self.assertIn('const BRIDGE_MAX_RUN = 12;', page)
        self.assertIn("return { error: '다리는 물 위를 클릭해 놓으세요' }", page)
        self.assertIn('강이 너무 넓습니다', page)
        # 예전에는 홀수 앵커만 찾아 왼편 다리·폭포(짝수 앵커)는 어디에도 놓을 수 없었다
        self.assertEqual(page.count('if (((u + v) & 1) !== par) continue;'), 2)   # findSubAnchor, planBridge


class EditorServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = Path(self.tmp.name)
        (self.game / 'Data' / 'Maps' / 'Download').mkdir(parents=True)
        self.sample = b'J2M\0' + bytes(200)
        (self.game / 'Data' / 'Maps' / '[2]A.rkm').write_bytes(self.sample)
        self.srv = mew.EditorServer(HERE, port=0)
        self.srv.port = 0
        url = self.srv.start(self.game)
        self.base = 'http://127.0.0.1:%d' % self.srv.httpd.server_address[1]
        self.assertIn(mew.EDITOR_PAGE, url)

    def tearDown(self):
        self.srv.stop()
        self.tmp.cleanup()

    def test_page_and_tiles_served(self):
        code, body = _req(self.base + '/')
        self.assertEqual(code, 200)
        self.assertIn('라크무 맵 에디터'.encode(), body)
        code, body = _req(self.base + '/tiles/EAST_OBJ.js')
        self.assertEqual(code, 200)
        self.assertEqual(_req(self.base + '/../launcher.py')[0], 404)

    def test_list_open_save(self):
        code, body = _req(self.base + '/api/maps')
        names = [m['name'] for m in json.loads(body)['maps']]
        self.assertEqual(names, ['[2]A.rkm'])
        code, body = _req(self.base + '/api/map?name=%5B2%5DA.rkm')
        self.assertEqual((code, body), (200, self.sample))
        new = b'J2M\0' + bytes(300)
        code, _ = _req(self.base + '/api/map?name=Download/%5B2%5DB.rkm', new, 'PUT')
        self.assertEqual(code, 200)
        self.assertEqual((self.game / 'Data/Maps/Download/[2]B.rkm').read_bytes(), new)
        code, _ = _req(self.base + '/api/map?name=%5B2%5DA.rkm', new, 'PUT')
        self.assertEqual((self.game / 'Data/Maps/[2]A.rkm.bak').read_bytes(), self.sample)

    def test_rejects_bad_names_and_data(self):
        for name in ('../x.rkm', 'C:/x.rkm', 'a.txt', ''):
            code, _ = _req(self.base + '/api/map?name=' + name, b'J2M\0' + bytes(100), 'PUT')
            self.assertEqual(code, 400, name)
        code, _ = _req(self.base + '/api/map?name=x.rkm', b'XXXX' + bytes(100), 'PUT')
        self.assertEqual(code, 400)


class TileModTests(unittest.TestCase):
    def test_install_and_uninstall_restores_previous(self):
        with tempfile.TemporaryDirectory() as t:
            game = Path(t)
            tile = game / 'Data' / 'tile'
            tile.mkdir(parents=True)
            (tile / 'East.jtl').write_bytes(b'old')
            self.assertFalse(mew.mod_installed(game))
            mew.install_mod(game, HERE)
            self.assertTrue(mew.mod_installed(game))
            self.assertEqual((tile / 'East.jtl.bak').read_bytes(), b'old')
            mew.uninstall_mod(game)
            self.assertEqual((tile / 'East.jtl').read_bytes(), b'old')
            self.assertEqual(sorted(p.name for p in tile.iterdir()), ['East.jtl'])

    def test_uninstall_removes_empty_folder(self):
        with tempfile.TemporaryDirectory() as t:
            game = Path(t)
            (game / 'Data').mkdir()
            mew.install_mod(game, HERE)
            mew.uninstall_mod(game)
            self.assertFalse((game / 'Data' / 'tile').exists())


class EnsureModTests(unittest.TestCase):
    def test_ensure_installs_then_ok_then_updates(self):
        with tempfile.TemporaryDirectory() as t:
            game = Path(t)
            self.assertEqual(mew.ensure_mod(game, HERE), 'no-game')
            (game / 'Data').mkdir()
            self.assertEqual(mew.ensure_mod(game, HERE), 'installed')
            self.assertEqual(mew.ensure_mod(game, HERE), 'ok')
            (game / 'Data' / 'tile' / 'S_Bridge.brg').write_bytes(b'stale')
            self.assertFalse(mew.mod_up_to_date(game, HERE))
            self.assertEqual(mew.ensure_mod(game, HERE), 'updated')
            self.assertTrue(mew.mod_up_to_date(game, HERE))
            self.assertFalse((game / 'Data' / 'tile' / 'S_Bridge.brg.bak').exists())
            mew.uninstall_mod(game)
            self.assertFalse((game / 'Data' / 'tile').exists())


if __name__ == '__main__':
    unittest.main()
