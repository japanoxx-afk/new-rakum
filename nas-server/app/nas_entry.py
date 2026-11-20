#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NAS(Docker) 실행용 진입점 — 저장소 루트의 server.py 를 수정 없이 감싸서 실행한다.

server.py 는 런처가 로컬(127.0.0.1)에서 띄우는 것과 같은 파일이다. 이 래퍼는:
  1) 데이터 폴더(RAKMU_DATA_DIR)로 이동한 뒤 server 를 import 한다.
     → matches.json / server.log / game_rules.json 이 NAS 데이터 폴더에 생긴다.
  2) server.log 를 크기 제한 로그(RotatingFileHandler)로 바꿔 NAS 용량이 끝없이 늘지 않게 한다.
  3) 수신 포트를 환경 변수로 바꿀 수 있게 한다(기본값은 server.py 와 동일).
     UDP 릴레이가 "보내는" 목적지 포트는 클라이언트(WG_IPX.dll)가 고정으로 쓰는
     47584 그대로 둔다 — 수신 포트만 바뀐다.

환경 변수 (모두 선택):
  RAKMU_DATA_DIR      데이터 폴더 (기본 /mnt/game-servers/rakmu/data)
  RAKMU_LOBBY_PORT    로비 TCP 수신 포트 (기본 11223)
  RAKMU_HTTP_PORT     전적·버전 HTTP 수신 포트 (기본 11225)
  RAKMU_RELAY_PORT    방 찾기 UDP 수신 포트 (기본 47584)
  RAKMU_LOG_MAX_BYTES server.log 1개 최대 크기 (기본 1048576 = 1MB)
  RAKMU_LOG_BACKUPS   보관할 이전 로그 개수 (기본 5)
"""
import asyncio
import logging
import logging.handlers
import os
import sys
import threading
from http.server import ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = "/mnt/game-servers/rakmu/data"
PROTECTED = ("rakmu-test",)  # 기존 프로젝트 데이터는 절대 쓰지 않는다


def _env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    value = int(raw)
    if not 1 <= value <= 65535 and name.endswith("_PORT"):
        raise ValueError(f"{name}={raw} 는 올바른 포트가 아닙니다.")
    return value


def prepare_data_dir():
    data_dir = os.path.abspath(os.environ.get("RAKMU_DATA_DIR", "").strip() or DEFAULT_DATA_DIR)
    parts = data_dir.replace("\\", "/").split("/")
    for name in PROTECTED:
        if name in parts:
            raise SystemExit(f"[nas_entry] 보호된 폴더({name})는 데이터 폴더로 쓸 수 없습니다: {data_dir}")
    os.makedirs(data_dir, exist_ok=True)
    os.chdir(data_dir)
    return data_dir


def load_server():
    """데이터 폴더에서 server.py 를 import (server.log 가 데이터 폴더에 생김)."""
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    import server  # noqa: E402  (cwd 이동 후 import 해야 함)
    return server


def use_rotating_log(max_bytes, backups):
    root = logging.getLogger()
    for h in list(root.handlers):
        if type(h) is logging.FileHandler:  # server.py 가 붙인 무제한 server.log
            fmt = h.formatter
            root.removeHandler(h)
            h.close()
            rh = logging.handlers.RotatingFileHandler(
                "server.log", maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
            rh.setFormatter(fmt)
            root.addHandler(rh)


def start_http(server, port):
    httpd = ThreadingHTTPServer((server.HOST, port), server._HistoryHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    server.log.info(f"전적/랭킹 HTTP on http://{server.HOST}:{port}/matches.json")
    return httpd


async def run(server, lobby_port, http_port, relay_port, ready=None):
    httpd = start_http(server, http_port)
    loop = asyncio.get_running_loop()
    relay_transport, _ = await loop.create_datagram_endpoint(
        lambda: server.DP8RelayProtocol(server.STATE),
        local_addr=(server.HOST, relay_port),
        allow_broadcast=True,
    )
    server.log.info(f"[nas_entry] UDP 방 찾기 수신 {relay_port} (릴레이 목적지 포트 {server.UDP_RELAY_PORT})")
    try:
        lobby = await asyncio.start_server(
            lambda r, w: server.ClientSession(r, w).run(), server.HOST, lobby_port)
        server.log.info(f"[nas_entry] RhakMu server {server.SERVER_VERSION} 로비 TCP {server.HOST}:{lobby_port} 준비 완료")
        if ready is not None:
            ready.set()
        async with lobby:
            await lobby.serve_forever()
    finally:
        relay_transport.close()
        httpd.shutdown()


def main():
    data_dir = prepare_data_dir()
    server = load_server()
    use_rotating_log(_env_int("RAKMU_LOG_MAX_BYTES", 1024 * 1024), _env_int("RAKMU_LOG_BACKUPS", 5))
    lobby = _env_int("RAKMU_LOBBY_PORT", server.PORT)
    http = _env_int("RAKMU_HTTP_PORT", server.HTTP_PORT)
    relay = _env_int("RAKMU_RELAY_PORT", server.UDP_RELAY_PORT)
    server.log.info(f"[nas_entry] data={data_dir} python={sys.version.split()[0]}")
    asyncio.run(run(server, lobby, http, relay))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
