#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RhakMu Private Server
TCP port 11223

TG_Net packet format: [uint16_le type][uint16_le size][payload...]
All game command types have the pattern 0xXXFF.

Confirmed protocol flow (from packet captures):
  0x01FF  Handshake    : client -> "RHAK"+version1000, server -> 4-byte ok
  0x03FF  Announcement : server -> uint32(0) (no announcement)
  0x02FF  Account info : client -> [flag][account\0]; server -> [3][내공,승,패,무 int32][등급점수 int16]
                         + 3 strings (Rhakmu.exe 0x44BB60, '승/패:%d/%d 내공:%d ...')
  0x05FF  Login        : payload=account\0password\0hash; server -> uint32(result)
  0x07FF  Channel sel  : server -> uint32(result)
  0x15FF  Rank list    : client -> [sort][start int32][end int32]; server -> 0x16FF(start),
                         0x15FF [sort] + N x {22B record + str\0 + name\0}, 0x17FF(end)  (Rhakmu.exe 0x44D0B0)
  0x14FF  Rank search  : client -> name\0; server -> [sort][rank int32][name\0]     (Rhakmu.exe 0x44D270)
  0x18FF  Guild list   : server -> 0x19FF + 0x1AFF (empty)
  0x0BFF  Room list    : server -> 0x0CFF, [0x0BFF entries], 0x0DFF
  0x0EFF  Create room  : server -> uint32(0)
  0x1FFF  User list    : server -> 0x20FF, [0x1FFF entries], 0x21FF
  0x10FF  Join room    : server -> [0x00, account\0, host_ip\0]
  0x11FF  Leave room   : remove room/member
  0x0FFF  Game start   : relay to all in room + send sync-ok
  0x12FF  Chat         : client -> message\0 account\0; server -> 0x12FF [1,0,0] sender\0 message\0
                         (the client has no 0x13FF case; type byte 1 = lobby chat, Rhakmu.exe 0x44C2B0)
  0x24FF  Post-game    : client -> [code][score int32]; code&0x7F 1=win 2=lose 3/4=draw/no contest
                         (0x8x = ladder); server -> 0x25FF [02 00]
  0x27FF  Post-game2   : suppress (no reply)
  0xFEFE  Crash report : log only
"""

import asyncio
import json
import logging
import os
import socket
import struct
import sys
import threading
import time as _time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rhakmu")

# 서버 로그를 파일(server.log)로도 남긴다 — 진단 시 이 파일만 공유하면 됨.
try:
    _fh = logging.FileHandler("server.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(_fh)
except OSError:
    pass

SERVER_VERSION = "0.9013"
HOST = "0.0.0.0"
PORT = 11223
UDP_RELAY_PORT = 47584  # WG_IPX.dll EnumHosts broadcast port

# Default accounts (any login accepted if account not in list, just track it)
# Add real accounts here: "account": "password"
ACCOUNTS: Dict[str, str] = {
    "test": "test1234",
    "nyai": "1111",
    "japanox": "1111",
    **{f"test{i}": "1111" for i in range(1, 11)},
}
# Set True to accept any account/password (open server)
OPEN_LOGIN = True

# Packet types
P_CONNECT       = 0x01FF
P_USERNAME      = 0x02FF
P_ANNOUNCE      = 0x03FF
P_LOGIN         = 0x05FF
P_CHAN_SEL      = 0x07FF
P_ROOM_LIST_REQ = 0x0BFF
P_ROOM_LIST_ACK = 0x0CFF
P_ROOM_LIST_END = 0x0DFF
P_CREATE_ROOM   = 0x0EFF
P_GAME_START    = 0x0FFF
P_BATTLE_START  = 0x1EFF   # server->client battle start (ReplyBattleReqReply)
P_JOIN_ROOM     = 0x10FF
P_LEAVE_ROOM    = 0x11FF
P_CHAT          = 0x12FF
P_CHAT_REPLY    = 0x13FF
P_RANK_SEARCH   = 0x14FF
P_RANK_LIST     = 0x15FF
P_RANK_ACK1     = 0x16FF
P_RANK_ACK2     = 0x17FF
P_GUILD_LIST    = 0x18FF
P_GUILD_ACK1    = 0x19FF
P_GUILD_ACK2    = 0x1AFF
P_USER_LIST_REQ = 0x1FFF
P_USER_LIST_ACK = 0x20FF
P_USER_LIST_END = 0x21FF
P_POST_GAME     = 0x24FF
P_POST_GAME_ACK = 0x25FF
P_POST_GAME2    = 0x27FF
P_CRASH         = 0xFEFE

MAX_PACKET      = 8192


# ── 전적 기록 (matches.json) ──────────────────────────────
MATCH_LOG = "matches.json"
# 서버 PC 런처가 쓰는 대전 규칙(명령 지연 턴, 집결지 금광 인식). 접속 PC 런처가 받아 똑같이 맞춘다.
RULES_FILE = "game_rules.json"

def _load_matches() -> list:
    try:
        with open(MATCH_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []

def _save_matches(matches: list) -> None:
    try:
        with open(MATCH_LOG, "w", encoding="utf-8") as f:
            json.dump(matches[-500:], f, ensure_ascii=False, indent=1)
    except OSError:
        pass

def record_match_start(map_name: str, players: list, room_title: str) -> None:
    """게임 시작 시 [시간·맵·플레이어]를 기록."""
    matches = _load_matches()
    matches.append({
        "time": _time.strftime("%Y-%m-%d %H:%M:%S"),
        "map": map_name,
        "players": list(players),
        "room": room_title,
        "results": {},   # {account: "win"/"lose"/raw} — post-game에서 채움
    })
    _save_matches(matches)

def record_match_result(account: str, code: int, score: int) -> None:
    """post-game 0x24FF: 해당 플레이어의 결과코드·점수를 가장 최근 매치에 기록.
    승/패는 결과코드로 판정(result_wl), 코드를 모를 때만 점수 비교."""
    matches = _load_matches()
    for rec in reversed(matches):
        if account in rec.get("players", []) and account not in rec.get("results", {}):
            rec.setdefault("results", {})[account] = {"code": code, "score": score}
            _recompute_winloss(rec)
            _save_matches(matches)
            return

# 0x24FF 결과코드 (Rhakmu.exe 0x41A9B0 에서 확인): 일반전 1=승 2=패 3=무승부(중도 이탈 포함) 4=기타 무효,
# 래더전은 같은 값에 0x80 이 더해진다(0x81 승, 0x82 패 ...). 점수는 대부분 0 이라 승패 판정에 쓰지 않는다.
RESULT_WL = {1: "win", 2: "lose", 3: "draw", 4: "draw"}

def result_wl(code) -> Optional[str]:
    try:
        return RESULT_WL.get(int(code) & 0x7F)
    except (TypeError, ValueError):
        return None

def _recompute_winloss(rec: dict) -> None:
    """결과코드로 win/lose/draw 판정. 코드를 모르면 예전처럼 점수 비교(동점이면 무승부)."""
    res = rec.get("results", {})
    if not res:
        return
    unknown = {}
    for a, v in res.items():
        if not isinstance(v, dict):
            continue
        wl = result_wl(v.get("code"))
        if wl:
            v["wl"] = wl
        else:
            unknown[a] = v
    if not unknown:
        return
    scores = {a: v.get("score", 0) for a, v in unknown.items()}
    top = max(scores.values())
    n_top = sum(1 for s in scores.values() if s == top)
    for a, v in unknown.items():
        if n_top > 1 and v.get("score", 0) == top:
            v["wl"] = "draw"
        else:
            v["wl"] = "win" if v.get("score", 0) == top else "lose"

def compute_ranking() -> dict:
    """matches.json에서 계정별 승/패/무 집계.

    - 기록마다 결과코드로 다시 판정한다(예전 버전이 점수로 잘못 매긴 기록도 바로잡힘).
    - 혼자 한 게임(플레이어 1명)은 랭킹에 넣지 않는다.
    """
    tally = {}
    for rec in _load_matches():
        if len(set(rec.get("players", []))) < 2:
            continue
        _recompute_winloss(rec)
        for a, v in rec.get("results", {}).items():
            wl = v.get("wl") if isinstance(v, dict) else None
            if wl not in ("win", "lose", "draw"):
                continue
            t = tally.setdefault(a, {"win": 0, "lose": 0, "draw": 0})
            t[wl] += 1
            t["last"] = rec.get("time", "")
    return tally

BASE_POINTS = 1000          # 내공 시작값 (게임은 1000 미만이면 등급 아이콘을 '없음'으로 그림)
WIN_POINTS, LOSE_POINTS = 10, 10
RANK_PAGE = 17              # 게임 랭킹 창 한 페이지 줄 수 (Rhakmu.exe 0x42CFA0: index < 0x11)

def ranking_rows() -> list:
    """게임 랭킹 창용 정렬 목록: [{rank, name, points, win, lose, draw, last}] (내공 → 승 → 이름 순)."""
    rows = []
    for name, t in compute_ranking().items():
        if not name:
            continue
        points = max(0, BASE_POINTS + WIN_POINTS * t["win"] - LOSE_POINTS * t["lose"])
        rows.append({"name": name, "points": points, "win": t["win"], "lose": t["lose"],
                     "draw": t["draw"], "last": t.get("last", "")})
    rows.sort(key=lambda r: (-r["points"], -r["win"], r["lose"], r["name"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows

def _i32(v: int) -> int:
    return max(-2**31, min(2**31 - 1, int(v)))

def build_rank_record(row: dict) -> bytes:
    """0x15FF 한 줄: 22바이트 {순위, 내공, 승, 패, 무 (int32), 등급점수 int16} + 마지막칸 문자열 + 이름."""
    grade = max(0, min(32767, row["win"]))      # 등급 아이콘(0x42CA20)은 이 값의 구간으로 정해짐
    rec = struct.pack("<iiiiih", _i32(row["rank"]), _i32(row["points"]), _i32(row["win"]),
                      _i32(row["lose"]), _i32(row["draw"]), grade)
    return rec + nul(row["last"][:10]) + nul(row["name"])

def build_rank_list(sort: int, start: int, end: int, rows: Optional[list] = None) -> bytes:
    """0x15FF 응답 payload. 클라는 [start, end) 순위를 요청한다(보통 end = start + 17)."""
    rows = ranking_rows() if rows is None else rows
    first = max(1, int(start))
    count = int(end) - int(start)
    count = RANK_PAGE if count <= 0 else min(count, RANK_PAGE)
    page = [r for r in rows if first <= r["rank"] < first + count]
    return bytes([sort & 0xFF]) + b"".join(build_rank_record(r) for r in page)

def build_account_info(account: str, rows: Optional[list] = None) -> bytes:
    """0x02FF 응답 type 3: 사용자 정보 창 '승/패:%d/%d 내공:%d 승률 로그인시간:%s'."""
    rows = ranking_rows() if rows is None else rows
    row = next((r for r in rows if r["name"] == account), None) or \
        {"rank": 0, "points": BASE_POINTS, "win": 0, "lose": 0, "draw": 0, "last": ""}
    grade = max(0, min(32767, row["win"]))
    return (bytes([3]) + struct.pack("<iiiih", _i32(row["points"]), _i32(row["win"]), _i32(row["lose"]),
                                     _i32(row["draw"]), grade)
            + nul(account) + nul(f"#{row['rank']}" if row["rank"] else "") + nul(row["last"]))


def pack_pkt(ptype: int, payload: bytes = b"") -> bytes:
    size = 4 + len(payload)
    return struct.pack("<HH", ptype, size) + payload


def nul(s: str) -> bytes:
    return s.encode("latin-1") + b"\x00"


def _kr(s: str) -> str:
    """패킷 문자열(latin-1 로 그대로 보관한 CP949 바이트)을 로그용 한글로."""
    try:
        return s.encode("latin-1").decode("cp949")
    except (UnicodeError, AttributeError):
        return s


def build_chat_payload(sender: str, message: str) -> bytes:
    """로비 채팅 0x12FF 응답 payload: [type=1][0][0] sender\\0 message\\0."""
    return bytes([1, 0, 0]) + nul(sender) + nul(message)


def build_user_entry(account: str, ip: str, index: int = 1) -> bytes:
    """Build a 0x1FFF channel/room user-list entry.

    The client parser (Rhakmu.exe 0x44CF80) reads each entry as:
      payload[0]      = flag byte (1 => end-of-list; 0 => normal entry)
      payload[1..2]   = uint16 value (player index; fed to the connect manager)
      then            = account\0, ip\0
    We previously sent only account\0 ip\0, which made the client misparse the
    account (treating its first char as the flag and the next 2 bytes as the
    value), so the peer's account/ip never registered correctly.
    """
    return bytes([0x00]) + struct.pack("<H", index) + nul(account) + nul(ip)


def read_cstrings(data: bytes) -> List[str]:
    """Extract all null-terminated strings from bytes."""
    result = []
    start = 0
    for i, b in enumerate(data):
        if b == 0:
            if i > start:
                try:
                    result.append(data[start:i].decode("latin-1"))
                except Exception:
                    result.append(data[start:i].decode("ascii", errors="replace"))
            start = i + 1
    if start < len(data):
        try:
            result.append(data[start:].decode("latin-1"))
        except Exception:
            pass
    return result


def get_preferred_ip() -> str:
    """Get best local IP: Radmin/Hamachi VPN (26.x/25.x) > LAN > default route."""
    try:
        all_ips: List[str] = []
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip: str = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                all_ips.append(ip)

        # Prefer VPN ranges: Radmin VPN 26.x, Hamachi 25.x
        for ip in all_ips:
            if ip.startswith("26.") or ip.startswith("25."):
                return ip

        # Fall back to first non-loopback
        if all_ips:
            return all_ips[0]
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def extract_ascii_strings(data: bytes, min_len: int = 2) -> List[str]:
    """Extract printable ASCII strings (min_len chars) separated by non-ASCII bytes.
    Used for parsing create-room payload where binary fields sit between string fields."""
    result = []
    buf = bytearray()
    for b in data:
        if 0x20 <= b <= 0x7E:
            buf.append(b)
        else:
            if len(buf) >= min_len:
                result.append(buf.decode("ascii"))
            buf.clear()
    if len(buf) >= min_len:
        result.append(buf.decode("ascii"))
    return result


@dataclass
class Room:
    id: int
    title: str
    map_name: str
    owner: str
    host_ip: str
    max_players: int
    members: List[str] = field(default_factory=list)
    in_game: bool = False   # battle started; lobby packets must not reach its players

    @property
    def player_count(self) -> int:
        return 1 + len(self.members)

    def build_list_entry(self, host_ip: str = "") -> bytes:
        """Build the room list payload for 0x0BFF (host_ip: address as seen by the viewer)."""
        host_b = nul(host_ip or self.host_ip)
        room_data = (
            bytes([0x00, 0x88, 0x00, 0x88, 0x00, 0x00,
                   min(self.player_count, 8),
                   min(self.max_players, 8), 0x00])
            + host_b
        )
        header = struct.pack("<HHHH",
            0,                   # unknown
            1,                   # flags (always 1)
            self.player_count,
            self.max_players,
        ) + struct.pack("<H", len(room_data))
        return header + nul(self.title) + room_data


LOOPBACK = ("127.0.0.1", "::1")


_own_cache = (0.0, frozenset())


def own_addresses() -> frozenset:
    """IPv4 addresses of this (server) PC, cached for 30 s."""
    global _own_cache
    now = _time.monotonic()
    if now - _own_cache[0] > 30:
        try:
            ips = frozenset(i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
        except OSError:
            ips = frozenset()
        _own_cache = (now, ips)
    return _own_cache[1]


def on_server_pc(ip: str) -> bool:
    return ip in LOOPBACK or ip.startswith("127.") or ip in own_addresses()


def local_ip_toward(remote_ip: str) -> str:
    """Local IPv4 this PC uses to reach remote_ip (Radmin 26.x -> our 26.x, Hamachi 25.x -> our 25.x).

    A connected UDP socket sends nothing; the OS just picks the route/interface.
    """
    if remote_ip and remote_ip not in LOOPBACK and not remote_ip.startswith("0."):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((remote_ip, 11223))
                ip = s.getsockname()[0]
                if ip and not ip.startswith(("127.", "0.")):
                    return ip
        except OSError:
            pass
        # Fallback: a local address on the same VPN / network prefix
        try:
            local = [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
        except OSError:
            local = []
        for n in (2, 1):
            pref = ".".join(remote_ip.split(".")[:n]) + "."
            for ip in local:
                if ip.startswith(pref):
                    return ip
    return STATE.server_ip


class ServerState:
    def __init__(self):
        self.rooms: List[Room] = []
        self.clients: List["ClientSession"] = []
        self._next_room_id = 1
        self.server_ip = get_preferred_ip()
        log.info(f"Server IP detected: {self.server_ip}")

    def next_room_id(self) -> int:
        rid = self._next_room_id
        self._next_room_id += 1
        return rid

    def find_room_by_title(self, title: str) -> Optional[Room]:
        for r in self.rooms:
            if r.title == title:
                return r
        return None

    def find_room_for_account(self, account: str) -> Optional[Room]:
        for r in self.rooms:
            if r.owner == account or account in r.members:
                return r
        return None

    def remove_rooms_for(self, account: str, host_ip: str = ""):
        to_remove = []
        for r in self.rooms:
            if r.owner == account or (host_ip and r.host_ip == host_ip):
                to_remove.append(r)
        for r in to_remove:
            self.rooms.remove(r)
            log.info(f"Room removed id={r.id} title={r.title!r} owner={r.owner}")

    def clients_in_room(self, room_title: str) -> List["ClientSession"]:
        return [c for c in self.clients if c.room_title == room_title]


STATE = ServerState()


class ClientSession:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        addr = writer.get_extra_info("peername") or ("0.0.0.0", 0)
        self.peer_ip: str = addr[0]
        self.peer_port: int = addr[1]
        self.account: str = ""
        self.room_title: str = ""
        self.in_game = False
        self.game_version = 0          # handshake 0x01FF: Rhakmu.exe 1.000d -> 1003, older 1.000 -> 1000
        self._buf = b""

    @property
    def peer(self) -> str:
        return f"{self.peer_ip}:{self.peer_port}"

    @property
    def advertised_ip(self) -> str:
        """IP other peers should use to reach this client (Radmin/VPN, not loopback)."""
        if self.peer_ip in LOOPBACK:
            return STATE.server_ip
        return self.peer_ip

    def address_for(self, viewer: "ClientSession" = None) -> str:
        """Address `viewer` must use to reach this client.

        Remote clients: their observed connection address. The client on the server PC
        connects via 127.0.0.1, so pick this PC's address on the same network as the viewer
        (Radmin player -> our Radmin IP, Hamachi player -> our Hamachi IP).
        """
        # A player on the server PC may connect via 127.0.0.1 OR via one of its own VPN
        # addresses (e.g. Radmin 26.x while the opponent uses Hamachi 25.x).
        if not on_server_pc(self.peer_ip):
            return self.peer_ip
        if viewer is not None and not on_server_pc(viewer.peer_ip):
            return local_ip_toward(viewer.peer_ip)
        return self.peer_ip if self.peer_ip not in LOOPBACK else STATE.server_ip

    def send(self, ptype: int, payload: bytes = b""):
        self.writer.write(pack_pkt(ptype, payload))

    async def flush(self):
        await self.writer.drain()

    async def run(self):
        STATE.clients.append(self)
        log.info(f"Connected: {self.peer}")
        try:
            while True:
                chunk = await self.reader.read(4096)
                if not chunk:
                    break
                self._buf += chunk
                await self._process()
        except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError):
            pass
        except Exception as e:
            log.error(f"{self.peer}: {e}", exc_info=True)
        finally:
            self._cleanup()

    def _cleanup(self):
        if self in STATE.clients:
            STATE.clients.remove(self)
        # Remove member from rooms
        if self.room_title:
            room = STATE.find_room_by_title(self.room_title)
            if room and self.account in room.members:
                room.members.remove(self.account)
        # Remove owned rooms on disconnect
        if self.account:
            for r in list(STATE.rooms):
                if r.owner == self.account:
                    STATE.rooms.remove(r)
                    log.info(f"Room removed (disconnect) id={r.id} title={r.title!r}")
        log.info(f"Disconnected: {self.peer} account={self.account!r}")

    async def _process(self):
        while len(self._buf) >= 4:
            ptype, psize = struct.unpack_from("<HH", self._buf, 0)

            # Crash packets can be large; treat oversized as crash
            if psize < 4 or psize > MAX_PACKET:
                if ptype == P_CRASH:
                    self._handle_crash(self._buf[4:])
                    self._buf = b""
                    return
                log.warning(f"{self.peer}: bad psize={psize} type=0x{ptype:04X}, dropping buffer")
                self._buf = b""
                return

            if len(self._buf) < psize:
                return

            payload = self._buf[4:psize]
            self._buf = self._buf[psize:]
            await self._handle(ptype, payload)

    async def _handle(self, ptype: int, payload: bytes):
        log.debug(f"{self.peer} -> 0x{ptype:04X} payload_len={len(payload)}")

        if ptype == P_CONNECT:
            magic = payload[:4]
            version = struct.unpack_from("<I", payload, 4)[0] if len(payload) >= 8 else 0
            log.info(f"{self.peer}: handshake magic={magic} version={version}")
            self.game_version = version
            self.send(P_CONNECT, struct.pack("<I", 0))

        elif ptype == P_ANNOUNCE:
            self.send(P_ANNOUNCE, struct.pack("<I", 0))

        elif ptype == P_USERNAME:
            # 0x02FF "Check Account Info" (Rhakmu.exe 0x44E890): payload = 1 byte flag + account\0.
            # 응답 type 3 이면 사용자 정보 창에 승/패·내공·승률을 보여 준다(0x44BB60).
            strings = read_cstrings(payload[1:] if payload else b"")
            target = strings[0] if strings else self.account
            log.info(f"{self.peer}: account info {_kr(target)!r}")
            self.send(P_USERNAME, build_account_info(target or ""))

        elif ptype == P_LOGIN:
            strings = read_cstrings(payload)
            account = strings[0] if len(strings) > 0 else ""
            password = strings[1] if len(strings) > 1 else ""
            result = self._check_login(account, password)
            if result == 0:
                self.account = account
                # Remove stale rooms from previous sessions
                STATE.remove_rooms_for(account)
                log.info(f"Login OK: {self.peer} account={account!r}")
            else:
                log.info(f"Login FAIL: {self.peer} account={account!r} result={result}")
            self.send(P_LOGIN, struct.pack("<I", result))

        elif ptype == P_CHAN_SEL:
            self.send(P_CHAN_SEL, struct.pack("<I", 0))

        elif ptype == P_RANK_LIST:
            # 랭킹 목록 요청 (Rhakmu.exe 0x44EDC0): [sort][start int32][end int32]
            sort = payload[0] if payload else 0
            start, end = struct.unpack_from("<ii", payload, 1) if len(payload) >= 9 else (1, 1 + RANK_PAGE)
            body = build_rank_list(sort, start, end)
            log.info(f"  Rank list sort={sort} start={start} end={end} -> {(len(body) - 1) // 22 if len(body) > 1 else 0} rows")
            self.send(P_RANK_ACK1, b"")              # 0x16FF: 목록 비우기
            if len(body) > 1:
                self.send(P_RANK_LIST, body)         # 0x15FF: 줄들
            self.send(P_RANK_ACK2, b"")              # 0x17FF: 화면 갱신

        elif ptype == P_RANK_SEARCH:
            # 랭킹 검색 (Rhakmu.exe 0x44ED30): name\0 -> [sort][rank int32][name\0], 클라가 그 페이지를 다시 요청
            strings = read_cstrings(payload)
            name = strings[0] if strings else ""
            row = next((r for r in ranking_rows() if r["name"] == name), None)
            log.info(f"  Rank search {_kr(name)!r} -> {row['rank'] if row else 'not found'}")
            if row:
                self.send(P_RANK_SEARCH, bytes([0]) + struct.pack("<i", row["rank"]) + nul(name))
            else:
                self.send(P_RANK_ACK1, b"")
                self.send(P_RANK_ACK2, b"")

        elif ptype == P_GUILD_LIST:
            self.send(P_GUILD_ACK1, b"")
            self.send(P_GUILD_ACK2, b"")

        elif ptype == P_ROOM_LIST_REQ:
            self.send(P_ROOM_LIST_ACK, b"")
            for room in STATE.rooms:
                owner_conn = next((c for c in STATE.clients if c.account == room.owner), None)
                self.send(P_ROOM_LIST_REQ, room.build_list_entry(
                    owner_conn.address_for(self) if owner_conn else room.host_ip))
            self.send(P_ROOM_LIST_END, b"")

        elif ptype == P_CREATE_ROOM:
            await self._handle_create_room(payload)

        elif ptype == P_USER_LIST_REQ:
            await self._handle_user_list()

        elif ptype == P_JOIN_ROOM:
            await self._handle_join_room(payload)

        elif ptype == P_LEAVE_ROOM:
            self._handle_leave_room()

        elif ptype == P_GAME_START:
            await self._handle_game_start(payload)

        elif ptype == P_CHAT:
            await self._handle_chat(payload)

        elif ptype == P_POST_GAME:
            # 0x24FF = SendGameReport: byte[0]=결과코드, byte[1..4]=점수(uint32)
            code = payload[0] if len(payload) >= 1 else 0
            score = struct.unpack_from("<i", payload, 1)[0] if len(payload) >= 5 else 0   # 래더 패배는 음수
            log.info(f"  Post-game 0x24FF from {self.account!r}: code={code} score={score} raw={payload.hex()}")
            if self.account:
                record_match_result(self.account, code, score)
            self._end_game()
            self.send(P_POST_GAME_ACK, bytes([2, 0]))

        elif ptype == P_POST_GAME2:
            pass  # suppress

        elif ptype == P_CRASH:
            self._handle_crash(payload)

        else:
            if self.room_title:
                # In-game: relay unknown packets to all other room members.
                # The game may use the lobby TCP connection to relay in-game data.
                others = [c for c in STATE.clients_in_room(self.room_title) if c is not self]
                if others:
                    raw = pack_pkt(ptype, payload)
                    for c in others:
                        c.writer.write(raw)
                    log.info(f"{self.peer}: relayed in-game 0x{ptype:04X} len={len(payload)} to {[c.account for c in others]}")
                else:
                    log.info(f"{self.peer}: in-game UNHANDLED 0x{ptype:04X} len={len(payload)} payload={payload.hex()}")
            else:
                log.info(f"{self.peer}: UNHANDLED 0x{ptype:04X} len={len(payload)} payload={payload.hex()}")

        await self.flush()

    def _check_login(self, account: str, password: str) -> int:
        if OPEN_LOGIN:
            return 0 if account else 1
        if account not in ACCOUNTS:
            return 1
        if ACCOUNTS[account] != password:
            return 2
        return 0

    async def _handle_create_room(self, payload: bytes):
        self.in_game = False
        # payload structure (45 bytes for standard room):
        #   [0:2]  unknown
        #   [2:4]  mode
        #   [4:6]  max_players
        #   [6:8]  time_limit
        #   [8..]  binary fields interspersed with title, map_name, owner strings
        # Use ASCII extraction (min 2 chars) to skip binary fields between strings.
        # Expected order: title, map_name, owner
        strings = extract_ascii_strings(payload[8:] if len(payload) > 8 else b"")
        title = strings[0] if strings else self.account
        map_name = strings[1] if len(strings) > 1 else ""
        owner = strings[2] if len(strings) > 2 else self.account
        if not owner:
            owner = self.account

        max_players = 4
        if len(payload) >= 6:
            mp = struct.unpack_from("<H", payload, 4)[0]
            if 1 <= mp <= 8:
                max_players = mp

        # Use peer IP; for localhost use server_ip (Radmin/Hamachi VPN IP preferred)
        host_ip = self.peer_ip if self.peer_ip not in ("127.0.0.1", "::1") else STATE.server_ip

        # Remove any existing room owned by this client
        STATE.remove_rooms_for(self.account, host_ip)

        room = Room(
            id=STATE.next_room_id(),
            title=title,
            map_name=map_name,
            owner=owner,
            host_ip=host_ip,
            max_players=max_players,
        )
        STATE.rooms.append(room)
        self.room_title = title
        log.info(f"Room created id={room.id} title={title!r} map={map_name!r} owner={owner} host={host_ip} maxP={max_players}")

        self.send(P_CREATE_ROOM, struct.pack("<I", 0))

    async def _handle_user_list(self):
        # Send channel user list: start, [members], end
        self.send(P_USER_LIST_ACK, b"")
        room = STATE.find_room_by_title(self.room_title) if self.room_title else None
        if room:
            # Send owner
            owner_client = next((c for c in STATE.clients if c.account == room.owner), None)
            owner_ip = owner_client.address_for(self) if owner_client else room.host_ip
            self.send(P_USER_LIST_REQ, build_user_entry(room.owner, owner_ip, 1))
            # Send members
            for i, member in enumerate(room.members):
                mc = next((c for c in STATE.clients if c.account == member), None)
                member_ip = mc.address_for(self) if mc else self.peer_ip
                self.send(P_USER_LIST_REQ, build_user_entry(member, member_ip, 2 + i))
        elif self.account:
            self.send(P_USER_LIST_REQ, build_user_entry(self.account, self.peer_ip, 1))
        self.send(P_USER_LIST_END, b"")

    async def _broadcast_member_list(self, room: "Room", exclude: "ClientSession" = None):
        """Send updated member list to all room members except the excluded client.

        Built per recipient: the host on the server PC is advertised with the address on
        the recipient's own network (Radmin / Hamachi / LAN).
        """
        owner_conn = next((c for c in STATE.clients if c.account == room.owner), None)
        for viewer in STATE.clients_in_room(room.title):
            if viewer is exclude or viewer.in_game:
                # In battle the client's lobby form is gone: a user list (0x?? START,
                # handler 0x44dbe0 -> class_form::GetControl on NULL) crashes the game.
                continue
            pkts = [pack_pkt(P_USER_LIST_ACK, b"")]
            owner_ip = owner_conn.address_for(viewer) if owner_conn else room.host_ip
            pkts.append(pack_pkt(P_USER_LIST_REQ, build_user_entry(room.owner, owner_ip, 1)))
            for i, member in enumerate(room.members):
                mc = next((c for c in STATE.clients if c.account == member), None)
                member_ip = mc.address_for(viewer) if mc else STATE.server_ip
                pkts.append(pack_pkt(P_USER_LIST_REQ, build_user_entry(member, member_ip, 2 + i)))
            pkts.append(pack_pkt(P_USER_LIST_END, b""))
            viewer.writer.write(b"".join(pkts))
            await viewer.flush()

    async def _handle_join_room(self, payload: bytes):
        strings = read_cstrings(payload)
        wanted = strings[0] if strings else ""

        room = None
        for r in STATE.rooms:
            if r.title == wanted or r.owner == wanted:
                room = r
                break
        if not room and STATE.rooms:
            room = STATE.rooms[-1]

        if room is None:
            self.send(P_JOIN_ROOM, struct.pack("<I", 1))
            return
        if room.in_game:
            log.info(f"Room join refused (game in progress): {self.peer} account={self.account!r} room={room.title!r}")
            self.send(P_JOIN_ROOM, struct.pack("<I", 1))
            return
        owner_conn = next((c for c in STATE.clients if c.account == room.owner), None)
        if owner_conn and owner_conn.game_version and self.game_version and owner_conn.game_version != self.game_version:
            # The host's game compares versions on the P2P join (Rhakmu.exe 0x4452A7) and answers
            # code 3: the joiner is bounced to the lobby while the server would still list it as a
            # member. Refuse here instead so neither side keeps a ghost member.
            log.warning(f"Room join refused (game version {self.game_version} != host {owner_conn.game_version}): "
                        f"{self.peer} account={self.account!r} room={room.title!r} host={room.owner!r} -- "
                        f"모든 PC가 같은 Rhakmu.exe (1.000d = 1003) 를 써야 합니다")
            self.send(P_JOIN_ROOM, struct.pack("<I", 1))
            return

        self.room_title = room.title
        self.in_game = False
        if self.account not in room.members and self.account != room.owner:
            room.members.append(self.account)

        joiner_ip = self.peer_ip if self.peer_ip not in LOOPBACK else STATE.server_ip
        owner_conn = next((c for c in STATE.clients if c.account == room.owner), None)
        host_ip = owner_conn.address_for(self) if owner_conn else room.host_ip

        # Reply to joiner: [0x00][host_account\0][host_ip\0]
        # Client uses host_account to identify the P2P peer and host_ip to connect.
        self.send(P_JOIN_ROOM, bytes([0]) + nul(room.owner) + nul(host_ip))

        log.info(f"Room join: {self.peer} account={self.account!r} room={room.title!r} host={host_ip} joiner_ip={joiner_ip}")

        # Broadcast updated member list to ALL room members (owner + joiner).
        # The owner needs to see the joiner in the lobby player list before game start.
        # Do NOT send 0x10FF to the owner — the owner's client interprets it as a join
        # directive for itself and immediately leaves the room.
        await self._broadcast_member_list(room, exclude=None)

    def _end_game(self):
        self.in_game = False
        room = STATE.find_room_by_title(self.room_title) if self.room_title else None
        if room and not any(c.in_game for c in STATE.clients_in_room(room.title)):
            room.in_game = False

    def _handle_leave_room(self):
        self._end_game()
        if self.room_title:
            # Remove as member
            room = STATE.find_room_by_title(self.room_title)
            if room:
                if self.account == room.owner:
                    STATE.rooms.remove(room)
                    log.info(f"Room removed (owner left) id={room.id} title={room.title!r}")
                elif self.account in room.members:
                    room.members.remove(self.account)
                    log.info(f"Room member left: account={self.account!r} room={room.title!r}")
            self.room_title = ""

    async def _handle_game_start(self, payload: bytes):
        if not self.room_title:
            log.warning(f"{self.peer}: game start with no room")
            return

        log.info(f"Game start: {self.peer} account={self.account!r} room={self.room_title!r} payload={payload.hex()}")

        # 전적 기록: 방장이 시작할 때 한 번만 (시간·맵·플레이어)
        room = STATE.find_room_by_title(self.room_title)
        if room and self.account == room.owner:
            players = [room.owner] + list(room.members)
            record_match_start(room.map_name, players, room.title)
            log.info(f"  Match recorded: map={room.map_name!r} players={players}")

        all_in_room = STATE.clients_in_room(self.room_title)

        # Battle-start only. Re-sending 0x10FF at game start makes the guest
        # re-process the join and leave the room, so we must NOT do that here.
        # The DP8 connect was already triggered for the guest at join time.
        # The client's lobby dispatcher routes the battle-start handler
        # (ReplyBattleReqReply) from type 0x1EFF, NOT 0x0FFF.
        start_pkt = pack_pkt(P_BATTLE_START, payload if payload else bytes([0x02, 0x00, 0x00]))
        if room:
            room.in_game = True
        for c in all_in_room:
            c.in_game = True
            c.writer.write(start_pkt)
            await c.flush()
            log.info(f"  Sent 0x1EFF battle-start to {c.account!r}")

    async def _handle_chat(self, payload: bytes):
        strings = read_cstrings(payload)
        message = strings[0] if strings else ""
        account = strings[1] if len(strings) > 1 else self.account
        if not account:
            account = self.account

        log.info(f"Chat from={_kr(account)!r}: {_kr(message)!r}")

        # 클라가 자동/명령으로 보내는 '/status', '/whereis x', '/ignore x' 등은 방송하지 않는다.
        if not message or message.startswith("/"):
            return

        # 클라 수신 형식 (Rhakmu.exe 0x44C2B0): 0x12FF [type=1][0][0] sender\0 message\0
        # → 로비 채팅창에 "sender>>message" 로 표시. (0x13FF 는 클라 디스패처에 없어 무시됨)
        chat_pkt = pack_pkt(P_CHAT, build_chat_payload(account, message))

        # 로그인한 로비 사용자에게만 (게임 중인 사람에게 로비 패킷을 보내지 않는다)
        for c in list(STATE.clients):
            if c.account and not c.in_game:
                c.writer.write(chat_pkt)
                await c.flush()

    def _handle_crash(self, payload: bytes):
        try:
            text = payload.decode("latin-1", errors="replace")
            log.error(f"CRASH from {self.peer} account={self.account!r}: {text[:300]}")
        except Exception:
            pass
        STATE.remove_rooms_for(self.account)


class DP8RelayProtocol(asyncio.DatagramProtocol):
    """Forward WG_IPX.dll EnumHosts broadcasts (UDP 47584) to known room peers.

    Radmin VPN does not relay broadcast packets between peers, so the
    guest never receives the host's EnumHosts announcement and DP8 never
    connects.  This relay runs on the lobby server (which already knows
    every player's IP from the TCP connection) and unicasts each broadcast
    to the other members of the same room.
    """

    def __init__(self, state: ServerState):
        self._state = state
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._seen: set = set()   # 진단 로그 중복 방지

    def connection_made(self, transport: asyncio.DatagramTransport):
        self._transport = transport
        sock = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        log.info(f"DP8 broadcast relay listening on UDP 0.0.0.0:{UDP_RELAY_PORT}")

    def datagram_received(self, data: bytes, addr: tuple):
        src_ip, src_port = addr

        # 이 브로드캐스트 출발IP와 일치하는 TCP 접속 찾기
        client = next(
            (c for c in self._state.clients if c.peer_ip == src_ip), None
        )
        if client is None:
            # 라드민에서 흔한 실패: UDP 출발IP != 로비 TCP 접속IP.
            # 예전엔 여기서 버려서 발견 실패 → 이제 접속한 다른 모든 피어로 폴백 릴레이.
            targets = [c for c in self._state.clients
                       if c.peer_ip not in (src_ip, "127.0.0.1", "::1")]
            key = ("nomatch", src_ip)
            if key not in self._seen:
                self._seen.add(key)
                peers = [c.peer_ip for c in self._state.clients]
                log.info(f"DP8: UDP {src_ip}:{src_port} 출발IP가 로비 접속IP와 불일치(접속IP들={peers}) "
                         f"→ 전체 피어 {[c.peer_ip for c in targets]}로 폴백 릴레이")
            for other in targets:
                try:
                    self._transport.sendto(data, (other.peer_ip, UDP_RELAY_PORT))
                except Exception as e:
                    log.warning(f"DP8 fallback relay error -> {other.peer_ip}: {e}")
            return
        if not client.room_title:
            key = ("noroom", src_ip)
            if key not in self._seen:
                self._seen.add(key)
                log.info(f"DP8: {src_ip}(account={client.account}) 브로드캐스트 수신했으나 방에 없음.")
            return

        others = [
            c for c in self._state.clients_in_room(client.room_title)
            if c.peer_ip != src_ip and c.peer_ip not in ("127.0.0.1", "::1")
        ]
        if not others:
            key = ("noother", src_ip, client.room_title)
            if key not in self._seen:
                self._seen.add(key)
                log.info(f"DP8: {src_ip}({client.account}) room={client.room_title} 릴레이 대상 피어 없음.")
            return

        for other in others:
            try:
                self._transport.sendto(data, (other.peer_ip, UDP_RELAY_PORT))
                key = ("relay", src_ip, other.peer_ip)
                if key not in self._seen:
                    self._seen.add(key)
                    log.info(f"DP8 relay OK: {src_ip} -> {other.peer_ip}:{UDP_RELAY_PORT} (첫 릴레이, {len(data)}B)")
            except Exception as e:
                log.warning(f"DP8 relay send error -> {other.peer_ip}: {e}")

    def error_received(self, exc):
        log.warning(f"DP8 relay UDP error: {exc}")

    def connection_lost(self, exc):
        pass


# ── 전적/랭킹 HTTP 제공 (클라이언트 런처가 조회) ──────────────
HTTP_PORT = 11225

class _HistoryHandler(BaseHTTPRequestHandler):
    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/ranking"):
            self._json(compute_ranking())
        elif self.path.startswith("/version"):
            self._json({"server_version": SERVER_VERSION})
        elif self.path.startswith("/rules"):
            try:
                with open(RULES_FILE, "r", encoding="utf-8") as f:
                    rules = json.load(f)
            except (OSError, ValueError):
                rules = {}
            self._json({"server_version": SERVER_VERSION, **rules})
        else:  # /matches.json, /matches, /
            self._json(_load_matches())

    def log_message(self, *a):
        pass  # quiet

def start_history_http():
    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), _HistoryHandler)
    except OSError as e:
        log.warning(f"전적 HTTP 서버 시작 실패(포트 {HTTP_PORT}): {e}")
        return
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    log.info(f"전적/랭킹 HTTP on http://0.0.0.0:{HTTP_PORT}/matches.json")


async def main():
    start_history_http()
    print("=" * 60)
    print("  RhakMu Private Server")
    print(f"  Listening on TCP {HOST}:{PORT}")
    print(f"  DP8 relay  on UDP {HOST}:{UDP_RELAY_PORT}")
    print(f"  Server IP: {STATE.server_ip}")
    print(f"  Open login: {OPEN_LOGIN}")
    print(f"  Known accounts: {', '.join(ACCOUNTS.keys())}")
    print("=" * 60)
    print()

    loop = asyncio.get_running_loop()

    # UDP broadcast relay for WG_IPX.dll EnumHosts (port 47584)
    relay_transport, _ = await loop.create_datagram_endpoint(
        lambda: DP8RelayProtocol(STATE),
        local_addr=(HOST, UDP_RELAY_PORT),
        allow_broadcast=True,
    )

    try:
        server = await asyncio.start_server(
            lambda r, w: ClientSession(r, w).run(),
            HOST,
            PORT,
        )
        async with server:
            await server.serve_forever()
    finally:
        relay_transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
