"""전적 사이트 자동 업로드(arena_upload.py) 시험: 싱글 경기는 안 올리고, 대전만 올린다."""
import gzip
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import arena_upload


def rkr(players, slots, local=0):
    head = {"format": 3, "date": "2026-11-21T20:00:00", "map": "DATA\\MAPS\\[2]Distant.rkm", "local": local,
            "players": [{"index": i, "name": n, "race": 0} for i, n in players], "slots": slots,
            "races": [0, 1, 3, 3, 3, 3, 3, 3]}
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as g:
        g.write((json.dumps(head) + "\n" + json.dumps({"t": 1.0}) + "\n").encode())
    return buf.getvalue()


class _Sink(BaseHTTPRequestHandler):
    got = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Sink.got.append((self.path, self.headers.get("X-Arena-Token"), self.headers.get("X-Uploader"), body))
        out = json.dumps({"ok": True, "status": "created", "message": "새 경기로 저장했습니다"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class ArenaUploadTests(unittest.TestCase):
    def setUp(self):
        _Sink.got = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Sink)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.base = Path(tempfile.mkdtemp())
        self.rdir = self.base / "replays"
        self.rdir.mkdir()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_single_skipped_multiplayer_uploaded_once(self):
        (self.rdir / "single.rkr").write_bytes(rkr([(0, "aa")], [32, 16, 0, 0, 0, 0, 0, 0]))
        multi = rkr([(0, "aa"), (1, "bb")], [32, 32, 0, 0, 0, 0, 0, 0], local=1)
        (self.rdir / "multi.rkr").write_bytes(multi)
        (self.rdir / "recording.rkr").write_bytes(multi[:-12])          # 아직 기록 중(잘린 gzip)
        up = arena_upload.ArenaUploader(self.base, self.rdir, self.url, "tok")
        rows = {n: s for n, s, _ in up.scan_once(now=time.time() + 60)}
        self.assertEqual(rows, {"single.rkr": "skipped", "multi.rkr": "uploaded"})
        self.assertEqual(len(_Sink.got), 1)
        path, token, uploader, body = _Sink.got[0]
        self.assertEqual((path, token, uploader, body), ("/api/rakmu/replays", "tok", "bb", multi))
        self.assertEqual(up.scan_once(now=time.time() + 60), [])
        self.assertEqual(up.file_status(self.rdir / "multi.rkr"), "업로드됨")
        self.assertEqual(up.file_status(self.rdir / "single.rkr"), "싱글(안 올림)")
        again = arena_upload.ArenaUploader(self.base, self.rdir, self.url, "tok")   # 상태 파일 유지
        self.assertEqual(again.scan_once(now=time.time() + 60), [])

    def test_fresh_file_waits(self):
        (self.rdir / "m.rkr").write_bytes(rkr([(0, "aa"), (1, "bb")], [32, 32, 0, 0, 0, 0, 0, 0]))
        up = arena_upload.ArenaUploader(self.base, self.rdir, self.url)
        self.assertEqual(up.scan_once(), [])                             # 방금 쓴 파일은 15초 기다림

    def test_server_down_retries_later(self):
        (self.rdir / "m.rkr").write_bytes(rkr([(0, "aa"), (1, "bb")], [32, 32, 0, 0, 0, 0, 0, 0]))
        up = arena_upload.ArenaUploader(self.base, self.rdir, "http://127.0.0.1:9")
        self.assertEqual(up.scan_once(now=time.time() + 60)[0][1], "retry")
        self.assertEqual(up.state, {})


if __name__ == "__main__":
    unittest.main()
