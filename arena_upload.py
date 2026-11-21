"""라크무 런처용: 경기 리플레이(.rkr)를 RTS ARENA(NAS) 로 자동 업로드.

new-rakum 저장소의 launcher.py 옆에 이 파일을 그대로 복사해서 쓴다 (표준 라이브러리만 사용).
붙이는 방법은 docs/LAUNCHER_INTEGRATION.md 참고.

규칙
  - 사람 2명 이상 경기만 올린다. 나 + 컴퓨터만 있는 싱글 경기는 올리지 않는다(skipped 로 기록).
    판정: 리플레이 머리 'slots' 에서 0x20(사람) 개수 (0x10 = 컴퓨터). slots 가 없으면 이름 있는 참가자 수.
  - 기록 중인 파일(아직 gzip 이 닫히지 않음)은 건너뛰고 다음에 다시 본다.
  - 한 번 올렸거나(uploaded/duplicate) 서버가 거절한(rejected) 파일은 다시 올리지 않는다.
    네트워크 오류는 다음 주기에 다시 시도한다.
  - 상태는 <런처 폴더>/arena_upload.json 에 sha256 별로 남는다.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SLOT_HUMAN = 0x20
STATE_FILE = "arena_upload.json"
SETTLE_SECONDS = 15          # 마지막 수정 후 이만큼 지난 파일만 (기록 끝난 파일)
INTERVAL = 30
MAX_BYTES = 20 * 1024 * 1024


def local_name(data: bytes) -> str:
    """리플레이 머리의 '내 번호'(local) 플레이어 이름 = 올린 사람."""
    try:
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as g:
            head = json.loads(g.readline().decode("utf-8"))
        me = head.get("local")
        return next((p.get("name", "") for p in head.get("players") or [] if p.get("index") == me), "")
    except Exception:  # noqa: BLE001
        return ""


def replay_kind(path: Path) -> tuple[str, str]:
    """('upload' | 'skip' | 'wait', 이유)."""
    try:
        with gzip.open(path, "rb") as g:
            head = json.loads(g.readline().decode("utf-8"))
            while g.read(1 << 20):             # 끝까지 읽어 파일이 온전한지(기록이 끝났는지) 확인
                pass
    except (EOFError, gzip.BadGzipFile, OSError) as e:
        return "wait", f"기록 중이거나 손상: {e}"
    except ValueError as e:
        return "skip", f"머리를 읽을 수 없음: {e}"
    slots = head.get("slots")
    if slots:
        humans = sum(1 for s in slots if s == SLOT_HUMAN)
    else:
        humans = sum(1 for p in head.get("players") or [] if (p or {}).get("name"))
    if humans < 2:
        return "skip", "싱글 경기(나 + 컴퓨터) — 전적·리플레이 저장 안 함"
    return "upload", f"사람 {humans}명 대전"


class ArenaUploader:
    def __init__(self, base_dir, replay_dir, server_url: str, token: str = "", account_fn=None, log_fn=None,
                 game: str = "rakmu"):
        self.base_dir = Path(base_dir)
        self.replay_dir = Path(replay_dir)
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.account_fn = account_fn or (lambda: "")
        self.log_fn = log_fn or (lambda msg: None)
        self.game = game
        self.state_path = self.base_dir / STATE_FILE
        self.state = self._load()
        self.status = "대기"
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    # ---- 상태 파일 ----
    def _load(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.state_path)
        except OSError:
            pass

    def file_status(self, path: Path) -> str:
        """런처 리플레이 목록에 보여 줄 상태 문자열."""
        for v in self.state.values():
            if v.get("file") == path.name:
                return {"uploaded": "업로드됨", "duplicate": "업로드됨", "skipped": "싱글(안 올림)",
                        "rejected": "거절됨"}.get(v.get("status"), v.get("status", ""))
        return ""

    # ---- 한 번 훑기 (테스트에서 직접 부름) ----
    def scan_once(self, now: float | None = None) -> list[tuple[str, str, str]]:
        """올릴 파일을 찾아 올린다. [(파일명, 상태, 메시지)] 를 돌려준다."""
        now = time.time() if now is None else now
        out = []
        with self._lock:
            if not self.replay_dir.is_dir():
                return out
            done_names = {v.get("file") for v in self.state.values()}
            for path in sorted(self.replay_dir.glob("*.rkr")):
                try:
                    st = path.stat()
                except OSError:
                    continue
                if path.name in done_names or now - st.st_mtime < SETTLE_SECONDS or st.st_size > MAX_BYTES:
                    continue
                kind, why = replay_kind(path)
                if kind == "wait":
                    continue
                data = path.read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                if sha in self.state:
                    continue
                if kind == "skip":
                    self.state[sha] = {"file": path.name, "status": "skipped", "message": why, "at": int(now)}
                    out.append((path.name, "skipped", why))
                    continue
                status, msg = self._post(path.name, data)
                if status == "retry":
                    out.append((path.name, "retry", msg))
                    self.status = f"업로드 대기(서버 연결 실패): {msg}"
                    break                                   # 서버가 안 되면 이번 주기는 그만
                if status == "auth":
                    out.append((path.name, "auth", msg))
                    self.status = msg
                    break
                self.state[sha] = {"file": path.name, "status": status, "message": msg, "at": int(now)}
                out.append((path.name, status, msg))
                self.log_fn(f"[전적] {path.name}: {msg}")
            if out:
                self._save()
            if out and all(s not in ("retry", "auth") for _, s, _ in out):
                self.status = f"전적 업로드: {out[-1][2]}"
        return out

    def _post(self, filename: str, data: bytes) -> tuple[str, str]:
        url = f"{self.server_url}/api/{self.game}/replays"
        headers = {"Content-Type": "application/octet-stream",
                   "X-Filename": urllib.parse.quote(filename),
                   "X-Uploader": urllib.parse.quote(self.account_fn() or local_name(data))}
        if self.token:
            headers["X-Arena-Token"] = self.token
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode("utf-8"))
            return _ok_status(body), body.get("message", "")
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except (OSError, ValueError):
                body = {}
            if e.code == 401:
                return "auth", body.get("message", "업로드 토큰 오류")
            if e.code in (413, 422):
                return "rejected", body.get("message", f"서버가 거절함({e.code})")
            return "retry", f"HTTP {e.code}"
        except (urllib.error.URLError, OSError, ValueError) as e:
            return "retry", str(getattr(e, "reason", e))

    # ---- 백그라운드 ----
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="arena-upload", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as e:  # noqa: BLE001 - 업로드 실패가 런처를 멈추면 안 됨
                self.status = f"전적 업로드 오류: {e}"
            self._stop.wait(INTERVAL)


def _ok_status(body: dict) -> str:
    return "duplicate" if body.get("status") == "duplicate" else "uploaded"


if __name__ == "__main__":   # 수동 시험: python arena_upload.py <리플레이폴더> <서버주소> [토큰]
    import sys
    up = ArenaUploader(Path.cwd(), sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "",
                       log_fn=print)
    for row in up.scan_once(now=time.time() + SETTLE_SECONDS):
        print(*row)
