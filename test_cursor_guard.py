import unittest

import cursor_guard as cg

MON = (0, 0, 2560, 1440)


class FakeWin:
    def __init__(self):
        self.fg = (1, True, MON, MON)
        self.clip_rect = None
        self.calls = []

    def foreground(self):
        return self.fg

    def clip(self, rect):
        self.calls.append(rect)
        self.clip_rect = rect

    def current_clip(self):
        return self.clip_rect or (0, 0, 4480, 1440)


class CursorGuardTests(unittest.TestCase):
    def test_decide(self):
        self.assertEqual(cg.decide(True, True, MON, MON), MON)
        self.assertEqual(cg.decide(True, True, (-8, -8, 2568, 1448), MON), MON)   # 테두리 밖으로 나간 최대화
        self.assertIsNone(cg.decide(True, True, (100, 100, 1380, 820), MON))       # 창모드는 cnc-ddraw 에 맡김
        self.assertIsNone(cg.decide(False, True, MON, MON))                        # 설정 꺼짐
        self.assertIsNone(cg.decide(True, False, MON, MON))                        # 다른 프로그램이 앞

    def test_clip_then_release_on_alt_tab(self):
        w = FakeWin()
        g = cg.CursorGuard(win=w)
        g.step()
        self.assertEqual(w.calls, [MON])
        g.step()
        self.assertEqual(w.calls, [MON])                    # 이미 걸려 있으면 다시 안 부름
        w.clip_rect = None                                  # Windows 가 풀어 버림 → 다시 건다
        g.step()
        self.assertEqual(w.calls, [MON, MON])
        w.fg = (2, False, None, None)                        # Alt+Tab
        g.step()
        self.assertEqual(w.calls[-1], None)
        g.step()
        self.assertEqual(len(w.calls), 3)                   # 우리가 건 게 없으면 건드리지 않음

    def test_disabled_and_stop(self):
        w = FakeWin()
        g = cg.CursorGuard(enabled=False, win=w)
        g.step()
        self.assertEqual(w.calls, [])
        g.enabled = True
        g.step()
        g.stop()
        self.assertEqual(w.calls, [MON, None])


if __name__ == '__main__':
    unittest.main()
