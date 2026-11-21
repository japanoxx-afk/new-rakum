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


class LockGameCursorTests(unittest.TestCase):
    """게임 화면 재생: 로그인 클릭이 없어 cnc-ddraw 가 커서를 숨기지 않던 문제 -> 첫 클릭(버튼 떼기)을 대신 보냄."""

    def run_lock(self, frames):
        t = [0.0]
        posted = []

        class W:
            def foreground(self):
                return frames[min(int(t[0] / 0.25), len(frames) - 1)]

            def client_size(self, hwnd):
                return (1280, 720)

            def post_button_up(self, hwnd, x, y):
                posted.append((hwnd, x, y))
                return True

        def sleep(dt):
            t[0] += dt
        ok = cg.lock_game_cursor(win=W(), timeout=10, settle=1.0, clock=lambda: t[0], sleep=sleep)
        return ok, posted, t[0]

    def test_posts_once_after_game_window_settles(self):
        other = (5, False, None, None)
        game = (7, True, MON, MON)
        ok, posted, when = self.run_lock([other] * 4 + [game] * 100)
        self.assertTrue(ok)
        self.assertEqual(posted, [(7, 640, 360)])           # 창 가운데, 한 번만
        self.assertGreaterEqual(when, 2.0)                  # 게임 창이 1초 이상 앞에 있은 뒤

    def test_gives_up_without_game_window(self):
        ok, posted, _ = self.run_lock([(5, False, None, None)])
        self.assertFalse(ok)
        self.assertEqual(posted, [])


if __name__ == '__main__':
    unittest.main()
