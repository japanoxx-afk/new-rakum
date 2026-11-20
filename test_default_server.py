"""v0.9061: official NAS server is the default once; the user's later choice is kept."""
import unittest

import launcher


class DefaultServerTests(unittest.TestCase):
    def test_applied_once_then_user_choice_kept(self):
        cfg = {'last_server_ip': '26.1.2.3'}
        self.assertTrue(launcher.apply_default_server(cfg))
        self.assertEqual(cfg['last_server_ip'], launcher.DEFAULT_SERVER_IP)
        cfg['last_server_ip'] = '26.9.9.9'            # user changes it later
        self.assertFalse(launcher.apply_default_server(cfg))
        self.assertEqual(cfg['last_server_ip'], '26.9.9.9')

    def test_fresh_config(self):
        cfg = {}
        launcher.apply_default_server(cfg)
        self.assertEqual(cfg['last_server_ip'], '112.159.73.235')

    def test_display_name_decodes_cp949_ids(self):
        raw = '라크무'.encode('cp949').decode('latin-1')
        self.assertEqual(launcher.display_name(raw), '라크무')
        self.assertEqual(launcher.display_name('abc'), 'abc')


if __name__ == '__main__':
    unittest.main()
