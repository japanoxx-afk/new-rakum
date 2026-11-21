"""NAS 진입점(nas_entry.py) 시험 — Docker 없이 같은 코드를 임시 폴더·임시 포트로 실행한다.

실행: 저장소 루트에서  python -m unittest nas-server/test_nas_entry.py  (또는 이 폴더에서 python test_nas_entry.py)
upload 폴더와 같은 구성을 만들기 위해 저장소 루트의 server.py 를 임시 app/ 폴더로 복사해 쓴다.
"""
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class NasEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rakmu-nas-")
        self.app = os.path.join(self.tmp, "rakmu", "app")
        self.data = os.path.join(self.tmp, "rakmu", "data")
        os.makedirs(self.app)
        shutil.copy(os.path.join(REPO, "server.py"), self.app)
        shutil.copy(os.path.join(HERE, "app", "nas_entry.py"), self.app)
        self.proc = None

    def tearDown(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(5)
        if self.proc:
            self.proc.stdout.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self, **extra):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", **extra)
        self.proc = subprocess.Popen(
            [sys.executable, "-u", os.path.join(self.app, "nas_entry.py")],
            cwd=self.tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return self.proc

    def test_serves_lobby_http_and_udp_on_configured_ports(self):
        lobby, http, relay = free_port(), free_port(), free_port(socket.SOCK_DGRAM)
        self.start(RAKMU_DATA_DIR=self.data, RAKMU_LOBBY_PORT=str(lobby),
                   RAKMU_HTTP_PORT=str(http), RAKMU_RELAY_PORT=str(relay))
        deadline = time.time() + 15
        while True:
            self.assertIsNone(self.proc.poll(), "server exited early")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{http}/version", timeout=1) as r:
                    version = json.load(r)
                break
            except OSError:
                if time.time() > deadline:
                    self.fail("HTTP did not come up")
                time.sleep(0.2)
        self.assertIn("server_version", version)
        with urllib.request.urlopen(f"http://127.0.0.1:{http}/matches.json", timeout=2) as r:
            self.assertEqual(json.load(r), [])

        # 로비 TCP: 실제 게임과 같은 0x01FF 핸드셰이크 → 4바이트 OK 응답
        with socket.create_connection(("127.0.0.1", lobby), timeout=3) as s:
            payload = b"RHAK" + struct.pack("<I", 1000)
            s.sendall(struct.pack("<HH", 0x01FF, 4 + len(payload)) + payload)
            reply = s.recv(64)
        self.assertEqual(reply[:8], struct.pack("<HH", 0x01FF, 8) + struct.pack("<I", 0))

        # UDP 방 찾기 포트가 열려 있고 이상한 패킷에도 죽지 않는다
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.sendto(b"\x00" * 16, ("127.0.0.1", relay))
        time.sleep(0.3)
        self.assertIsNone(self.proc.poll())

        # 로그는 데이터 폴더에 생긴다 (app 폴더가 아님)
        self.assertTrue(os.path.exists(os.path.join(self.data, "server.log")))
        self.assertFalse(os.path.exists(os.path.join(self.app, "server.log")))
        with open(os.path.join(self.data, "server.log"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("[nas_entry] RhakMu server", text)
        self.assertIn("handshake", text)

    def test_refuses_rakmu_test_data_dir(self):
        protected = os.path.join(self.tmp, "rakmu-test", "data")
        self.start(RAKMU_DATA_DIR=protected)
        out = self.proc.communicate(timeout=15)[0].decode("utf-8", "replace")
        self.assertNotEqual(self.proc.returncode, 0)
        self.assertIn("rakmu-test", out)
        self.assertFalse(os.path.exists(protected))


class RotatingLogTests(unittest.TestCase):
    def test_plain_file_handler_is_replaced(self):
        import logging
        import logging.handlers
        sys.path.insert(0, os.path.join(HERE, "app"))
        try:
            import nas_entry
        finally:
            sys.path.pop(0)
        tmp = tempfile.mkdtemp()
        cwd = os.getcwd()
        root = logging.getLogger()
        try:
            os.chdir(tmp)
            plain = logging.FileHandler("server.log", encoding="utf-8")
            root.addHandler(plain)
            nas_entry.use_rotating_log(1000, 2)
            mine = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
            self.assertNotIn(plain, root.handlers)
            self.assertEqual(len(mine), 1)
            self.assertEqual(mine[0].maxBytes, 1000)
            self.assertEqual(mine[0].backupCount, 2)
        finally:
            for h in [h for h in root.handlers if isinstance(h, logging.FileHandler)]:
                root.removeHandler(h)
                h.close()
            os.chdir(cwd)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
