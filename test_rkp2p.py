"""rkp2p (TG_Net.dll 홀펀칭 프록시) + server.py P2PRendezvous 실제 동작 시험.

두 개의 시험용 '게임'(rkp2p/test/harness.exe)이 각자 프록시 TG_Net.dll 을 불러
127.0.0.2 / 127.0.0.3 의 UDP 11223 에서 서로 메시지를 주고받는다. 서버는 진짜
server.py 의 UDP 처리부를 쓴다. 빌드된 파일이 없거나 Windows 가 아니면 건너뛴다.
"""
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

import server

HERE = os.path.dirname(os.path.abspath(__file__))
TEST_BIN = os.path.join(HERE, "rkp2p", "test")
FILES = ("harness.exe", "TGNetOrg.dll", "TG_Net.dll")
GAME_DIR = r"C:\Program Files (x86)\TriggerSoft\RhakMu"
HAVE_BIN = sys.platform == "win32" and all(os.path.isfile(os.path.join(TEST_BIN, f)) for f in FILES)


class Stub:
    def __init__(self, ip, account, room):
        self.peer_ip, self.account, self.room_title = ip, account, room

    def address_for(self, viewer=None):
        return self.peer_ip


class UdpServer:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        ready = threading.Event()

        def run():
            asyncio.set_event_loop(self.loop)
            self.transport, self.proto = self.loop.run_until_complete(self.loop.create_datagram_endpoint(
                lambda: server.DP8RelayProtocol(server.STATE), local_addr=("127.0.0.1", 0)))
            self.port = self.transport.get_extra_info("sockname")[1]
            ready.set()
            self.loop.run_forever()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(5)

    def close(self):
        self.loop.call_soon_threadsafe(self.transport.close)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)


@unittest.skipUnless(HAVE_BIN, "rkp2p 시험 파일 없음 (python rkp2p/build.py)")
class Rkp2pLiveTests(unittest.TestCase):
    def setUp(self):
        server.STATE.clients[:] = []
        server.STATE.rooms[:] = []
        self.srv = UdpServer()
        self.tmp = tempfile.mkdtemp(prefix="rkp2p_")

    def tearDown(self):
        self.srv.close()
        server.STATE.clients[:] = []
        shutil.rmtree(self.tmp, ignore_errors=True)

    def game_dir(self, name, **ini):
        d = os.path.join(self.tmp, name)
        os.makedirs(d)
        for f in FILES:
            shutil.copy(os.path.join(TEST_BIN, f), d)
        conf = {"enabled": 1, "server": f"127.0.0.1:{self.srv.port}", "allow_loopback": 1}
        conf.update(ini)
        with open(os.path.join(d, "rkp2p.ini"), "w") as fh:
            fh.write("[rkp2p]\n" + "".join(f"{k}={v}\n" for k, v in conf.items()))
        return d

    def play(self, a_ini=None, b_ini=None, count=6, ms=8000):
        a = self.game_dir("a", **(a_ini or {}))
        b = self.game_dir("b", **(b_ini or {}))
        pa = subprocess.Popen([os.path.join(a, "harness.exe"), "127.0.0.2", "127.0.0.3", str(count), str(ms)],
                              cwd=a, stdout=subprocess.PIPE, text=True)
        pb = subprocess.Popen([os.path.join(b, "harness.exe"), "127.0.0.3", "127.0.0.2", str(count), str(ms)],
                              cwd=b, stdout=subprocess.PIPE, text=True)
        out_a, _ = pa.communicate(timeout=30)
        out_b, _ = pb.communicate(timeout=30)

        def log(d):
            p = os.path.join(d, "rkp2p.log")
            if not os.path.exists(p):
                return ""
            with open(p, encoding="latin-1") as fh:
                return fh.read()
        return out_a, out_b, log(a), log(b)

    @staticmethod
    def got(out, src):
        return sorted(int(n) for n in re.findall(rf"recv {re.escape(src)} msg (\d+)", out))

    def test_direct_after_punch(self):
        server.STATE.clients[:] = [Stub("127.0.0.2", "aa", "r"), Stub("127.0.0.3", "bb", "r")]
        out_a, out_b, log_a, log_b = self.play()
        self.assertEqual(self.got(out_b, "127.0.0.2:11223"), list(range(6)), out_b + log_b)
        self.assertEqual(self.got(out_a, "127.0.0.3:11223"), list(range(6)), out_a + log_a)
        self.assertIn("-> direct", log_a)
        self.assertIn("-> direct", log_b)
        self.assertNotIn("relay", log_a + log_b)
        self.assertNotIn("RKP2", out_a + out_b)          # 제어 패킷은 게임에 보이지 않는다

    def test_relay_when_peers_cannot_reach_each_other(self):
        server.STATE.clients[:] = [Stub("127.0.0.2", "aa", "r"), Stub("127.0.0.3", "bb", "r")]
        out_a, out_b, log_a, log_b = self.play({"test_block_peers": 1}, {"test_block_peers": 1})
        self.assertEqual(self.got(out_b, "127.0.0.2:11223"), list(range(6)), out_b + log_b)
        self.assertEqual(self.got(out_a, "127.0.0.3:11223"), list(range(6)), out_a + log_a)
        self.assertIn("punch -> relay", log_a)
        self.assertIn("punch -> relay", log_b)

    def test_not_in_same_room_sends_as_before(self):
        server.STATE.clients[:] = [Stub("127.0.0.2", "aa", "r1"), Stub("127.0.0.3", "bb", "r2")]
        out_a, out_b, log_a, log_b = self.play()
        self.assertEqual(self.got(out_b, "127.0.0.2:11223"), list(range(6)), out_b + log_b)
        self.assertIn("query -> pass", log_a)
        self.assertNotIn("direct", log_a)

    @unittest.skipUnless(os.path.isfile(os.path.join(GAME_DIR, "TG_Net.dll")), "게임 미설치")
    def test_real_tg_net_dll(self):
        """A 는 게임의 진짜 TG_Net.dll 을 게임과 같은 순서로 부른다 (소켓 메시지 -> TGNet_WndProc -> Peek)."""
        server.STATE.clients[:] = [Stub("127.0.0.1", "aa", "r"), Stub("127.0.0.3", "bb", "r")]
        a = self.game_dir("a")
        b = self.game_dir("b")
        src = os.path.join(GAME_DIR, "TGNetOrg.dll" if os.path.isfile(os.path.join(GAME_DIR, "TGNetOrg.dll")) else "TG_Net.dll")
        with open(src, "rb") as fh:
            data = fh.read()
        if b"TGNetOrg.TGNet_" in data:
            self.skipTest("게임 폴더에 원래 TG_Net.dll 이 없음")
        with open(os.path.join(a, "TGNetOrg.dll"), "wb") as fh:
            fh.write(data)
        shutil.copy(os.path.join(GAME_DIR, "iCARUS.dll"), a)
        shutil.copy(os.path.join(TEST_BIN, "realharness.exe"), a)
        pa = subprocess.Popen([os.path.join(a, "realharness.exe"), "127.0.0.3", "6", "8000"],
                              cwd=a, stdout=subprocess.PIPE, text=True)
        pb = subprocess.Popen([os.path.join(b, "harness.exe"), "127.0.0.3", "127.0.0.1", "6", "8000"],
                              cwd=b, stdout=subprocess.PIPE, text=True)
        out_a, _ = pa.communicate(timeout=30)
        out_b, _ = pb.communicate(timeout=30)
        with open(os.path.join(a, "rkp2p.log"), encoding="latin-1") as fh:
            log_a = fh.read()
        self.assertEqual(self.got(out_b, "127.0.0.1:11223"), list(range(6)), out_b)
        self.assertEqual(self.got(out_a, "127.0.0.3:11223"), list(range(6)), out_a + log_a)
        self.assertIn("-> direct", log_a)

    def test_host_reports_the_address_the_server_sees(self):
        """방장이 자기 슬롯에 넣어 참가자에게 알려주는 주소: Radmin 26.x 대신 서버가 보는 주소."""
        server.STATE.clients[:] = [Stub("127.0.0.2", "aa", "r"), Stub("127.0.0.3", "bb", "r")]
        out_a, out_b, log_a, log_b = self.play(count=1, ms=2000)
        self.assertIn("myip 127.0.0.2", out_a, out_a + log_a)
        self.assertIn("myip 127.0.0.3", out_b, out_b + log_b)
        self.assertIn("game address 26.9.9.9 -> 127.0.0.2", log_a)

    def test_address_unchanged_without_hole_punching(self):
        out_a, out_b, log_a, log_b = self.play({"enabled": 0}, {"enabled": 0}, count=1, ms=2000)
        self.assertIn("myip 26.9.9.9", out_a)
        self.assertIn("myip 26.9.9.9", out_b)

    def test_disabled_proxy_is_transparent(self):
        out_a, out_b, log_a, log_b = self.play({"enabled": 0}, {"enabled": 0})
        self.assertEqual(self.got(out_b, "127.0.0.2:11223"), list(range(6)))
        self.assertEqual(self.got(out_a, "127.0.0.3:11223"), list(range(6)))
        self.assertNotIn("direct", log_a + log_b)


class RendezvousUnitTests(unittest.TestCase):
    """서버 쪽만: 같은 방이 아니면 알려주지 않고, 중계도 하지 않는다."""

    class T:
        def __init__(self):
            self.sent = []

        def sendto(self, data, addr):
            self.sent.append((data, addr))

    def setUp(self):
        server.STATE.clients[:] = [Stub("1.1.1.1", "aa", "r"), Stub("2.2.2.2", "bb", "r"), Stub("3.3.3.3", "cc", "x")]
        self.r = server.P2PRendezvous(server.STATE)
        self.t = self.T()
        for ip, port in (("1.1.1.1", 5001), ("2.2.2.2", 6002), ("3.3.3.3", 7003)):
            self.r.handle(self.t, b"RKP2\x01\x01", (ip, port))
        self.t.sent.clear()

    def tearDown(self):
        server.STATE.clients[:] = []

    def test_query_same_room(self):
        self.r.handle(self.t, b"RKP2\x02" + bytes([2, 2, 2, 2]), ("1.1.1.1", 5001))
        (ep, to1), (req, to2) = self.t.sent
        self.assertEqual(ep, b"RKP2\x82" + bytes([2, 2, 2, 2, 2, 2, 2, 2]) + (6002).to_bytes(2, "big"))
        self.assertEqual(to1, ("1.1.1.1", 5001))
        self.assertEqual(req, b"RKP2\x83" + bytes([1, 1, 1, 1, 1, 1, 1, 1]) + (5001).to_bytes(2, "big"))
        self.assertEqual(to2, ("2.2.2.2", 6002))

    def test_query_other_room_unknown(self):
        self.r.handle(self.t, b"RKP2\x02" + bytes([3, 3, 3, 3]), ("1.1.1.1", 5001))
        self.assertEqual(self.t.sent, [(b"RKP2\x84" + bytes([3, 3, 3, 3]), ("1.1.1.1", 5001))])

    def test_relay_only_within_room(self):
        self.r.handle(self.t, b"RKP2\x10" + bytes([2, 2, 2, 2]) + b"game", ("1.1.1.1", 5001))
        self.assertEqual(self.t.sent, [(b"RKP2\x11" + bytes([1, 1, 1, 1]) + b"game", ("2.2.2.2", 6002))])
        self.t.sent.clear()
        self.r.handle(self.t, b"RKP2\x10" + bytes([3, 3, 3, 3]) + b"game", ("1.1.1.1", 5001))
        self.assertEqual(self.t.sent, [])

    def test_unregistered_sender_gets_nothing_relayed(self):
        self.r.handle(self.t, b"RKP2\x10" + bytes([2, 2, 2, 2]) + b"game", ("9.9.9.9", 1234))
        self.assertEqual(self.t.sent, [])


if __name__ == "__main__":
    unittest.main()
