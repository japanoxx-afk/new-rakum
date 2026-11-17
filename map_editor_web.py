"""라크무 웹 맵 에디터 연동 (런처 내장).

- 에디터(HTML + 타일 아틀라스)를 로컬 HTTP 서버(127.0.0.1:47231)로 띄우고 브라우저로 연다.
- 서버는 map_editor_web/editor 의 server.ps1 과 같은 API 를 제공한다:
    GET /api/ping, GET /api/maps, GET|PUT /api/map?name=<Data\\Maps 기준 상대경로>.rkm
  저장 시 기존 파일은 .bak 으로 백업한다.
- 상하대칭 언덕 입구 타일 모드(Data\\tile\\*.jtl / *_Bridge.brg) 설치·제거.
  게임은 Data\\tile 의 개별 파일을 FDB 보다 먼저 읽으므로 원본 FDB 는 건드리지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil
import tarfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PORT = 47231
EDITOR_PAGE = 'RhakMuMapEditor.html'
MOD_ARCHIVE = 'flip_ramp_tiles.tar.xz'
MOD_FILES = ('East.jtl', 'West.jtl', 'Savage.jtl', 'Dungeon.jtl',
             'E_Bridge.brg', 'W_Bridge.brg', 'S_Bridge.brg', 'D_Bridge.brg')
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8',
        '.txt': 'text/plain; charset=utf-8', '.png': 'image/png', '.json': 'application/json'}


def editor_dir(resource_dir: str | os.PathLike) -> Path:
    return Path(resource_dir) / 'map_editor_web' / 'editor'


def mod_archive(resource_dir: str | os.PathLike) -> Path:
    return Path(resource_dir) / 'map_editor_web' / 'mod' / MOD_ARCHIVE


def safe_map_path(maps_dir: Path, rel: str | None) -> Path | None:
    """'[2]Name.rkm' 또는 'Download/[2]Name.rkm' -> Data\\Maps 안의 경로. 바깥으로 나가는 경로는 거부."""
    if not rel or not rel.strip():
        return None
    rel = rel.replace('\\', '/').strip()
    if rel.startswith('/') or ':' in rel or '..' in rel.split('/') or not rel.lower().endswith('.rkm'):
        return None
    full = (maps_dir / rel).resolve()
    try:
        full.relative_to(maps_dir.resolve())
    except ValueError:
        return None
    return full


def _make_handler(root: Path, maps_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # 콘솔 없는 런처에서 stderr 출력 방지
            pass

        def _send(self, code, body=b'', ctype='text/plain; charset=utf-8'):
            if isinstance(body, str):
                body = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if body and self.command != 'HEAD':
                self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False), 'application/json; charset=utf-8')

        def _name(self):
            q = parse_qs(urlparse(self.path).query)
            return q.get('name', [None])[0]

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path == '/api/ping':
                return self._json({'ok': True})
            if path == '/api/maps':
                items = []
                if maps_dir.is_dir():
                    for f in sorted(maps_dir.rglob('*')):
                        if f.is_file() and f.suffix.lower() == '.rkm':
                            st = f.stat()
                            items.append({'name': str(f.relative_to(maps_dir)).replace('/', '\\'),
                                          'size': st.st_size, 'mtime': int(st.st_mtime * 1000)})
                return self._json({'folder': str(maps_dir), 'maps': items})
            if path == '/api/map':
                full = safe_map_path(maps_dir, self._name())
                if full is None:
                    return self._send(400, 'bad name')
                if not full.is_file():
                    return self._send(404, 'not found')
                return self._send(200, full.read_bytes(), 'application/octet-stream')
            if path in ('', '/'):
                path = '/' + EDITOR_PAGE
            rel = path.lstrip('/')
            full = (root / rel).resolve()
            try:
                full.relative_to(root.resolve())
            except ValueError:
                return self._send(404, 'not found')
            if not full.is_file():
                return self._send(404, 'not found')
            return self._send(200, full.read_bytes(), MIME.get(full.suffix.lower(), 'application/octet-stream'))

        do_HEAD = do_GET

        def do_PUT(self):
            if unquote(urlparse(self.path).path) != '/api/map':
                return self._send(404, 'not found')
            full = safe_map_path(maps_dir, self._name())
            if full is None:
                return self._send(400, 'bad name')
            n = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(n) if n > 0 else b''
            if len(body) < 76 or body[:3] != b'J2M':
                return self._send(400, 'not a J2M map')
            full.parent.mkdir(parents=True, exist_ok=True)
            if full.exists():
                shutil.copy2(full, str(full) + '.bak')
            tmp = full.with_name(full.name + '.tmp')
            tmp.write_bytes(body)
            os.replace(tmp, full)
            return self._json({'ok': True, 'path': str(full)})

        do_POST = do_PUT

    return Handler


class EditorServer:
    """런처 프로세스 안에서 도는 에디터용 로컬 웹 서버 (daemon 스레드)."""

    def __init__(self, resource_dir, port: int = PORT):
        self.root = editor_dir(resource_dir)
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        self.maps_dir: Path | None = None
        self.thread: threading.Thread | None = None

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}/{EDITOR_PAGE}'

    def running(self):
        return self.httpd is not None

    def start(self, game_dir):
        maps = Path(game_dir) / 'Data' / 'Maps'
        if self.httpd is not None and self.maps_dir == maps:
            return self.url
        self.stop()
        if not (self.root / EDITOR_PAGE).is_file():
            raise FileNotFoundError(f'에디터 파일이 없습니다: {self.root / EDITOR_PAGE}')
        self.httpd = ThreadingHTTPServer(('127.0.0.1', self.port), _make_handler(self.root, maps))
        self.httpd.daemon_threads = True
        self.maps_dir = maps
        self.thread = threading.Thread(target=self.httpd.serve_forever, name='map-editor-http', daemon=True)
        self.thread.start()
        return self.url

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.httpd = None
        self.maps_dir = None

    def open(self, game_dir):
        url = self.start(game_dir)
        webbrowser.open(url)
        return url


# ------------------------------------------------------------------ tile mod
def tile_dir(game_dir) -> Path:
    return Path(game_dir) / 'Data' / 'tile'


def mod_installed(game_dir) -> bool:
    d = tile_dir(game_dir)
    return all((d / f).is_file() for f in MOD_FILES)


def install_mod(game_dir, resource_dir) -> list[str]:
    """상하대칭 언덕 입구 모드 설치. 같은 이름의 기존 파일은 .bak 으로 보관."""
    arc = mod_archive(resource_dir)
    if not arc.is_file():
        raise FileNotFoundError(f'모드 파일이 없습니다: {arc}')
    dest = tile_dir(game_dir)
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    with tarfile.open(arc, 'r:xz') as tar:
        for m in tar.getmembers():
            name = Path(m.name).name
            if not m.isfile() or name not in MOD_FILES:
                continue
            data = tar.extractfile(m).read()
            out = dest / name
            if out.exists() and not (dest / (name + '.bak')).exists():
                shutil.copy2(out, str(out) + '.bak')
            tmp = out.with_name(name + '.tmp')
            tmp.write_bytes(data)
            os.replace(tmp, out)
            written.append(str(out))
    if len(written) != len(MOD_FILES):
        raise RuntimeError('모드 압축 파일이 손상되었습니다.')
    return written


def uninstall_mod(game_dir) -> list[str]:
    """모드 파일 제거 (설치 전 .bak 이 있으면 복원). 빈 Data\\tile 폴더는 지운다."""
    d = tile_dir(game_dir)
    removed = []
    for name in MOD_FILES:
        f = d / name
        bak = d / (name + '.bak')
        if bak.exists():
            os.replace(bak, f)
            removed.append(str(f))
        elif f.exists():
            f.unlink()
            removed.append(str(f))
    try:
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    except OSError:
        pass
    return removed
