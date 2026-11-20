"""원본 Launcher.exe 의 '최신버젼 확인 실패' 창 자동 [확인] (실제 메시지 상자로 확인)."""
import os
import subprocess
import sys
import unittest

import launcher


def message_box(title):
    code = ("import ctypes,sys; sys.exit(ctypes.windll.user32.MessageBoxW("
            f"None, 'msg', {title!r}, 0x30))")
    return subprocess.Popen([sys.executable, '-c', code])


@unittest.skipUnless(os.name == 'nt', 'Windows 전용')
class VersionWarningTests(unittest.TestCase):
    def test_clicks_ok_on_the_warning(self):
        p = message_box(launcher.VERSION_WARNING_TITLE)
        try:
            self.assertTrue(launcher.dismiss_version_warning(p, timeout=10))
            self.assertEqual(p.wait(timeout=10), 1)          # IDOK
        finally:
            if p.poll() is None:
                p.kill()

    def test_leaves_other_windows_alone(self):
        p = message_box('다른 창')
        try:
            self.assertFalse(launcher.dismiss_version_warning(p, timeout=1.5))
            self.assertIsNone(p.poll())
        finally:
            p.kill()


if __name__ == '__main__':
    unittest.main()
