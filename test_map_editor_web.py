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


if __name__ == '__main__':
    unittest.main()
