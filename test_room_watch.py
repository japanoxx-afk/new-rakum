"""방 생성 알림 (room_watch + server /rooms)."""
import io
import json
import unittest
from unittest import mock

import room_watch
import server


def room(i, title, owner, mine=False, in_game=False):
    return {"id": i, "title": title, "owner": owner, "map": "m.rkm", "players": 1, "max": 4,
            "in_game": in_game, "mine": mine}


class WatcherTests(unittest.TestCase):
    def test_only_new_rooms_of_other_people(self):
        w = room_watch.RoomWatcher()
        self.assertEqual(w.update(None), [])                                   # 서버가 모르거나 접속 안 됨
        self.assertEqual(w.update([]), [])
        a, mine, playing = room(1, "1:1", "nyai"), room(2, "내 방", "seo", mine=True), room(3, "x", "kk", in_game=True)
        self.assertEqual(w.update([a, mine, playing]), [a])                    # 런처를 켰을 때 이미 있던 남의 방도 알림
        self.assertEqual(w.update([a, mine, playing]), [])                     # 같은 방은 한 번만
        b = room(4, "2:2", "aa")
        self.assertEqual(w.update([a, b]), [b])
        self.assertEqual(w.update(None), [])                                   # 잠깐 끊겨도 기억은 그대로
        self.assertEqual(w.update([a, b]), [])
        self.assertEqual(w.update([b]), [])                                    # a 가 없어짐
        self.assertEqual(w.update([a, b]), [a])                                # 다시 만들면 또 알림
        self.assertEqual(room_watch.describe(a), "1:1 (방장 nyai 1/4)")

    def test_my_room_is_told_by_account_not_address(self):
        """같은 공유기를 쓰는 두 PC는 서버가 보는 주소가 같아 서로의 방에 mine 이 붙는다 (v0.9105 에서 알림이 안 온 경우).
        이 PC의 게임 계정을 알면 방장 이름으로 내 방인지 본다."""
        w = room_watch.RoomWatcher()
        theirs, own = room(1, "1:1", "nyai", mine=True), room(2, "내 방", "Seo", mine=True)
        self.assertEqual(w.update([theirs, own], "seo"), [theirs])
        w = room_watch.RoomWatcher()
        self.assertEqual(w.update([theirs, own], ""), [])                      # 계정을 모르면 서버의 mine 표시대로
        w = room_watch.RoomWatcher()
        self.assertEqual(w.update([room(3, "x", "seo", mine=False)], " SEO "), [])

    def test_last_user_from_registry(self):
        class Key:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        class Reg:
            HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_32KEY = 1, 2, 0x200
            value = ("seo ", 1)
            def OpenKey(self, root, path, reserved, access):
                assert (root, path, access) == (1, r"SOFTWARE\TriggerSoft\RhakMu", 0x202)
                return Key()
            def QueryValueEx(self, key, name):
                assert name == "LastUser"
                if self.value is None:
                    raise FileNotFoundError(name)
                return self.value
        reg = Reg()
        self.assertEqual(room_watch.last_user(reg), "seo")
        reg.value = None
        self.assertEqual(room_watch.last_user(reg), "")
        reg.value = (7, 4)
        self.assertEqual(room_watch.last_user(reg), "")

    def test_status_tells_why_there_is_no_alert(self):
        for body, want in (({"rooms": [room(1, "a", "b")]}, ("ok", [room(1, "a", "b")])), ([{"time": "x"}], ("old", None))):
            resp = io.BytesIO(json.dumps(body).encode())
            resp.__enter__ = lambda *a, r=resp: r
            resp.__exit__ = lambda *a: False
            with mock.patch("urllib.request.urlopen", return_value=resp):
                self.assertEqual(room_watch.fetch_status("1.2.3.4"), want)
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertEqual(room_watch.fetch_status("1.2.3.4"), ("down", None))

    def fetch(self, body):
        resp = io.BytesIO(json.dumps(body).encode())
        resp.__enter__ = lambda *a: resp
        resp.__exit__ = lambda *a: False
        with mock.patch("urllib.request.urlopen", return_value=resp) as u:
            out = room_watch.fetch_rooms("1.2.3.4")
            self.assertEqual(u.call_args.args[0], "http://1.2.3.4:11225/rooms")
        return out

    def test_fetch_tells_old_servers_apart(self):
        self.assertEqual(self.fetch({"server_version": "0.9023", "rooms": [room(1, "a", "b")]}), [room(1, "a", "b")])
        self.assertEqual(self.fetch({"server_version": "0.9023", "rooms": []}), [])
        self.assertIsNone(self.fetch([{"time": "…", "players": []}]))            # 예전 서버: 어떤 경로든 전적 목록
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertIsNone(room_watch.fetch_rooms("1.2.3.4"))

    def test_toast_sits_above_the_taskbar_at_the_bottom_right(self):
        self.assertEqual(room_watch.toast_position(300, 80, (0, 0, 1920, 1040), (1920, 1080)), (1604, 944))
        self.assertEqual(room_watch.toast_position(300, 80, None, (1920, 1080)), (1604, 936))     # 영역을 모르면 아래 48 을 비움
        self.assertEqual(room_watch.toast_position(300, 80, (1920, 0, 3840, 1040), (3840, 1080)), (3524, 944))
        self.assertEqual(room_watch.toast_position(900, 700, (0, 0, 800, 600), (800, 600)), (0, 0))  # 화면보다 커도 밖으로 안 나감
        import sys
        if sys.platform != "win32":
            self.assertIsNone(room_watch.work_area())
            self.assertFalse(room_watch.keep_inactive(1234))

    def test_flash_is_harmless_off_windows(self):
        import sys
        if sys.platform != "win32":
            self.assertFalse(room_watch.flash_taskbar(1234))


class ServerRoomsTests(unittest.TestCase):
    def setUp(self):
        self.saved = list(server.STATE.rooms)
        server.STATE.rooms.clear()
        self.addCleanup(lambda: (server.STATE.rooms.clear(), server.STATE.rooms.extend(self.saved)))

    def test_snapshot_hides_addresses_and_marks_my_room(self):
        korean = "초보만".encode("cp949").decode("latin-1")                    # 패킷 문자열 보관 방식
        server.STATE.rooms.append(server.Room(7, korean, "[2]A.rkm", "seo", "26.1.1.1", 4, members=["nyai"]))
        server.STATE.rooms.append(server.Room(8, "go", "m.rkm", "aa", "26.2.2.2", 2, in_game=True))
        snap = server.rooms_snapshot("26.1.1.1")
        self.assertEqual(snap, [
            {"id": 7, "title": "초보만", "owner": "seo", "map": "[2]A.rkm", "players": 2, "max": 4, "in_game": False, "mine": True},
            {"id": 8, "title": "go", "owner": "aa", "map": "m.rkm", "players": 1, "max": 2, "in_game": True, "mine": False}])
        self.assertNotIn("26.", json.dumps(snap))
        self.assertFalse(any(r["mine"] for r in server.rooms_snapshot("")))
        fresh = room_watch.RoomWatcher().update(server.rooms_snapshot("26.9.9.9"))
        self.assertEqual([r["id"] for r in fresh], [7])

    def test_http_endpoint(self):
        server.STATE.rooms.append(server.Room(1, "t", "m.rkm", "seo", "10.0.0.5", 4))
        h = server._HistoryHandler.__new__(server._HistoryHandler)
        h.path, h.client_address, sent = "/rooms", ("10.0.0.5", 5555), []
        h._json = sent.append
        h.do_GET()
        self.assertEqual(sent[0]["server_version"], server.SERVER_VERSION)
        self.assertEqual([(r["title"], r["mine"]) for r in sent[0]["rooms"]], [("t", True)])


if __name__ == '__main__':
    unittest.main()
