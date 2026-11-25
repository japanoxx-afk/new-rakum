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

SERVER_VERSION = "0.9021"
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
P_CHAN_SEL      = 0x07FF   # 채널 입장: client -> [word idx|0x8000][name\0]; server -> [result 0=OK][name\0]
P_CHAN_LIST     = 0x08FF   # 채널 목록: client -> [start i16][end i16]; server -> {users i16, no i16, name\0}...
P_CHAN_LIST_BEG = 0x09FF   # 채널 목록 시작 (클라 목록 비움, Rhakmu.exe 0x44CC30)
P_CHAN_LIST_END = 0x0AFF   # 채널 목록 끝 ('채널리스트를 요청중입니다' 창 닫힘, 0x44CD40)
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
    except OSError:
        return []
    except ValueError:
        # 깨진 파일을 빈 목록으로 덮어쓰면 전체 기록을 잃는다 → 따로 보관해 두고 새로 시작
        try:
            os.replace(MATCH_LOG, f"{MATCH_LOG}.bad-{_time.strftime('%Y%m%d_%H%M%S')}")
        except OSError:
            pass
        return []

def _save_matches(matches: list) -> None:
    """전체 기록을 보관한다 (예전에는 최근 500판만 남겨 랭킹이 오래된 경기를 잊었다).
    전적 사이트(rtsarena)가 이 파일을 읽어 같은 랭킹을 만들므로, 임시 파일에 다 쓴 뒤 바꿔 끼워
    읽는 쪽이 반쯤 쓰인 파일을 보지 않게 한다."""
    tmp = MATCH_LOG + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(matches, f, ensure_ascii=False, indent=1)
        os.replace(tmp, MATCH_LOG)
    except OSError:
        pass

def record_match_start(map_name: str, players: list, room_title: str) -> None:
    """게임 시작 시 [시간·맵·플레이어]를 기록. id 는 전적 사이트가 경기를 구분하는 키."""
    import uuid
    matches = _load_matches()
    matches.append({
        "id": uuid.uuid4().hex,
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
# 관전자(플레이어 +6 참가 표시 0x80, 방 슬롯 종류 4)는 게임이 항상 3 을 보낸다(0x41A9D5) -> 무승부로 집계.
# 컴퓨터(Computer 슬롯, +4 == 2)가 낀 경기도 모든 사람이 3 을 보낸다.
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

# ── 계급 (점수제) ──
# 게임(Rhakmu.exe 0x42CA20)은 서버가 보낸 '등급값'(원래는 래더 순위)의 구간으로 계급 이름·아이콘을 고른다:
#   0 이하 신 / 1~10 초인 / ~50 패왕 / ~190 지존 / ~450 영웅 / ~900 명장 / ~1600 달인 / ~2500 대가 / ~3500 고수 /
#   ~4700 투사 / ~5900 중수 / ~7200 용사 / ~8200 평민 / ~10000 하수 / 그 위 초보.
# 또 내공이 1000 미만(사용자 정보 0x4226E1) 또는 1010 미만(목록 0x42CCC0)이면 등급값과 상관없이 초보로 그린다.
# 접속자가 적은 서버에서 순위를 그대로 보내면 거의 모두 '초인'(10위 안)이 되므로, 내공(점수) 구간으로 계급을 정하고
# 그 계급 구간의 등급값을 보낸다. 내공 = 1000 + 10 x 승 - 10 x 패 이므로 아래 기준은 '승 - 패' 로 1, 3, 6, 10, 15 … 120 이다
# (위로 갈수록 간격이 넓어짐). '신'(등급값 0 이하)은 쓰지 않는다.
# (계급 이름, 필요한 내공, 게임에 보낼 등급값) — 높은 계급부터
TIERS = (("초인", 2200, 1), ("패왕", 1900, 11), ("지존", 1700, 51), ("영웅", 1550, 191), ("명장", 1450, 451),
         ("달인", 1360, 901), ("대가", 1280, 1601), ("고수", 1210, 2501), ("투사", 1150, 3501), ("중수", 1100, 4701),
         ("용사", 1060, 5901), ("평민", 1030, 7201), ("하수", 1010, 8201), ("초보", 0, 10001))

def tier_for_points(points: int) -> tuple:
    """내공 -> (계급 이름, 게임에 보낼 등급값)."""
    for name, need, grade in TIERS:
        if points >= need:
            return name, grade
    return TIERS[-1][0], TIERS[-1][2]

def grade_value(row: dict) -> int:
    return tier_for_points(int(row.get("points", BASE_POINTS)))[1]

def _i32(v: int) -> int:
    return max(-2**31, min(2**31 - 1, int(v)))

def build_rank_record(row: dict) -> bytes:
    """0x15FF 한 줄: 22바이트 {순위, 내공, 승, 패, 무 (int32), 등급점수 int16} + 마지막칸 문자열 + 이름."""
    grade = grade_value(row)                    # 계급(0x42CA20)은 이 값의 구간으로 정해짐 — 내공 기준 (TIERS)
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
    grade = grade_value(row)
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


CHANNEL_NAME = "자유채널".encode("cp949").decode("latin-1")   # 패킷 문자열은 CP949 바이트를 latin-1 로 보관


# ── 로비 접속자 목록: 0x12FF 서버메시지 타입 (Rhakmu.exe 0x44C2B0 switch) ──
# 로비 오른쪽 목록(로비 폼 [[0x6E0CE0]+8] 의 리스트 0xC)은 0x1FFF 가 아니라 0x12FF 타입으로 채워진다.
#   type 4 (13 도 같음) 입장: [4][0][0] name\0 + 18바이트 {내공 i32, 승 i32, 패 i32, 무 i32, 등급값 i16} + str\0
#          (0x42CBF0 이 목록에 추가. 이름이 '나'면 내 정보로 저장하고 대기창을 닫은 뒤 '/status' 를 보낸다)
#   type 5 퇴장: [5][0][0] name\0                      (0x42CEF0 이 목록에서 지움)
#   type 14 상태: [14][0][0] \0 + {접속인원 i16, 개설된채널 i16, 개설된방 i16}  ('/status' 응답, 채팅창에 표시)
# (0x1FFF 는 방 폼 [+0x20] 의 멤버 목록 9번용이라 로비 목록에는 쓰지 않는다)
MSG_CHAT, MSG_ENTER, MSG_LEAVE, MSG_STATUS = 1, 4, 5, 14


def _stats(name: str, rows: Optional[list] = None) -> dict:
    rows = ranking_rows() if rows is None else rows
    return next((r for r in rows if r["name"] == name), None) or         {"points": BASE_POINTS, "win": 0, "lose": 0, "draw": 0}


def build_enter_payload(name: str, rows: Optional[list] = None) -> bytes:
    r = _stats(name, rows)
    info = struct.pack("<iiiih", _i32(r["points"]), _i32(r["win"]), _i32(r["lose"]), _i32(r["draw"]),
                       max(0, min(32767, r["win"])))
    return bytes([MSG_ENTER, 0, 0]) + nul(name) + info + nul("")


def build_leave_payload(name: str) -> bytes:
    return bytes([MSG_LEAVE, 0, 0]) + nul(name)


def build_status_payload() -> bytes:
    users = sum(1 for c in STATE.clients if c.account)
    return bytes([MSG_STATUS, 0, 0]) + nul("") + struct.pack("<hhh", min(users, 32767), 1, min(len(STATE.rooms), 32767))


def lobby_viewers(exclude=None) -> list:
    """로비 목록 메시지를 받아도 되는 사람: 채널에 들어온 뒤(로비 폼이 있음), 게임 중이 아님(게임 중엔 폼이 없어 크래시)."""
    return [c for c in STATE.clients if c is not exclude and c.account and c.in_channel and not c.in_game]


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

    def prune_rooms(self):
        """방장이 접속해 있지 않은 방은 지운다 (끊긴 접속 정리가 늦거나 방장 이름이 어긋난 경우)."""
        online = {c.account for c in self.clients if c.account}
        for r in list(self.rooms):
            if r.owner not in online:
                self.rooms.remove(r)
                log.info(f"Room removed (owner not connected) id={r.id} title={r.title!r} owner={r.owner!r}")
            else:
                r.members = [m for m in r.members if m in online]

    def clients_in_room(self, room_title: str) -> List["ClientSession"]:
        return [c for c in self.clients if c.room_title == room_title]


STATE = ServerState()


# 끊긴 줄 모르는 접속 찾기 + 공유기(NAT)가 조용한 접속을 끊지 않게: TCP keepalive.
# 게임은 로비에서 아무 것도 안 보내고 가만히 있을 수 있다. 그러면 중간 공유기가 몇 분 뒤 접속을 잊어
# 플레이어가 튕기고, 게임을 강제로 끈 사람의 접속은 서버에 영원히 남아 빈 방이 로비에 보인다.
# 60초 조용하면 10초 간격으로 확인 패킷(데이터 없음, 게임은 모름), 6번 무응답이면 끊긴 것으로 정리.
KEEPALIVE_IDLE, KEEPALIVE_INTERVAL, KEEPALIVE_COUNT = 60, 10, 6


def enable_keepalive(sock) -> bool:
    if sock is None:
        return False
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "TCP_KEEPIDLE"):            # Linux (NAS), 최근 Windows
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_IDLE)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_INTERVAL)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, KEEPALIVE_COUNT)
        elif hasattr(socket, "SIO_KEEPALIVE_VALS"):    # 예전 Windows
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, KEEPALIVE_IDLE * 1000, KEEPALIVE_INTERVAL * 1000))
        return True
    except (OSError, AttributeError, ValueError):
        return False


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
        self.in_channel = False        # 채널 입장(0x07FF) 완료 → 로비 폼이 있어 로비 목록 메시지를 받아도 안전
        self._buf = b""
        self.connected_at = _time.monotonic()
        self.room_since = 0.0          # 방을 만들거나 들어간 때 (바로 직후의 로비 요청은 무시)
        self.close_reason = "연결 종료(EOF)"
        enable_keepalive(writer.get_extra_info("socket"))

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
        except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError) as e:
            self.close_reason = type(e).__name__
        except TimeoutError as e:                       # keepalive 무응답 (상대 PC/공유기가 사라짐)
            self.close_reason = f"응답 없음(keepalive) {e}"
        except OSError as e:
            self.close_reason = f"{type(e).__name__} {e}"
        except Exception as e:
            self.close_reason = f"오류 {e}"
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
        log.info(f"Disconnected: {self.peer} account={self.account!r} "
                 f"after {int(_time.monotonic() - self.connected_at)}s reason={self.close_reason}")
        if self.account and self.in_channel and not any(c.account == self.account for c in STATE.clients):
            pkt = pack_pkt(P_CHAT, build_leave_payload(self.account))   # 로비 목록에서 지움 (type 5)
            for c in lobby_viewers(exclude=self):
                c.writer.write(pkt)

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
            try:
                await self._handle(ptype, payload)
            except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError, TimeoutError):
                raise
            except Exception as e:
                # 한 패킷 처리 오류로 로비 접속을 끊지 않는다. 끊기면 게임이 끝난 뒤 로비가 먹통이 된다
                # (0.9017~0.9019 런처 내장 서버: 게임 시작 때 uuid 모듈이 없어 방장이 끊겼음).
                log.error(f"{self.peer}: 0x{ptype:04X} 처리 오류 (접속 유지): {e}", exc_info=True)

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
            # 채널은 하나뿐 — 어떤 이름이 와도 성공(0)으로 답하고 그 이름을 돌려준다.
            names = read_cstrings(payload[2:]) if len(payload) > 2 else []
            self._back_in_lobby("channel join")
            self.send(P_CHAN_SEL, bytes([0]) + nul(names[0] if names else CHANNEL_NAME))
            if self.account:
                # 로비 접속자 목록: 나에게 다른 사람 전원 → 마지막에 나 자신(클라가 내 정보 저장 후 '/status' 요청),
                # 로비에 있는 다른 사람에게는 내 입장. (게임은 0x1FFF 가 아니라 0x12FF type 4/5 로 목록을 채운다)
                rows = ranking_rows()
                first_join = not self.in_channel
                self.in_channel = True
                others = sorted({c.account for c in STATE.clients
                                 if c.account and c.in_channel and c.account != self.account})
                for name in others:
                    self.send(P_CHAT, build_enter_payload(name, rows))
                mine = pack_pkt(P_CHAT, build_enter_payload(self.account, rows))
                self.writer.write(mine)
                if first_join:
                    for c in lobby_viewers(exclude=self):
                        if c.account != self.account:
                            c.writer.write(mine)
                log.info(f"  Channel join {_kr(self.account)!r}: lobby list {len(others) + 1} users")

        elif ptype == P_CHAN_LIST:
            # 'Channel' 버튼 (Rhakmu.exe 0x44E5B0 요청 / 0x44CC60 응답 파서)
            users = sum(1 for c in STATE.clients if c.account)
            log.info(f"  Channel list -> 1 channel, {users} users")
            self.send(P_CHAN_LIST_BEG, b"")
            self.send(P_CHAN_LIST, struct.pack("<hh", min(users, 32767), 1) + nul(CHANNEL_NAME))
            self.send(P_CHAN_LIST_END, b"")

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
            self._back_in_lobby("room list")
            STATE.prune_rooms()
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
                try:
                    record_match_result(self.account, code, score)
                except Exception as e:                # 기록 실패해도 결과 응답(0x25FF)은 보낸다
                    log.error(f"  Match result record failed: {e}", exc_info=True)
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
        # 방장 = 방을 만든 접속의 계정. (글자열 추출은 ASCII 만 읽어 한글 방 제목/계정이면 어긋나,
        # 방장이 나가도 방이 지워지지 않았다)
        owner = self.account or (strings[2] if len(strings) > 2 else "")

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
        self.room_since = _time.monotonic()
        log.info(f"Room created id={room.id} title={title!r} map={map_name!r} owner={owner} host={host_ip} maxP={max_players}")

        self.send(P_CREATE_ROOM, struct.pack("<I", 0))

    async def _handle_user_list(self):
        # Send room/channel user list: start(0x20FF), [entries 0x1FFF], end(0x21FF).
        # 이 목록은 방 폼([+0x20])의 멤버 목록용. 로비 접속자 목록은 0x12FF type 4/5 (채널 입장 때 보냄).
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
        self.room_since = _time.monotonic()
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

    def _back_in_lobby(self, why: str):
        """로비 폼만 보내는 요청(방 목록 0x0BFF, 채널 입장 0x07FF)이 왔다 = 방/게임에서 나와 로비에 있다.
        게임이 끝난 뒤나 게임이 튕긴 뒤 방 나가기(0x11FF) 없이 로비로 돌아오면 서버에는 방이 그대로 남았다."""
        if self.room_title and _time.monotonic() - self.room_since < 3:
            return                     # 방 만들기/들어가기 직전에 눌린 로비 요청이 늦게 온 것
        if self.room_title or self.in_game:
            log.info(f"  {_kr(self.account)!r} is back in the lobby ({why}): leaving room {self.room_title!r}")
            self._handle_leave_room()
        self.in_game = False

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
            try:
                record_match_start(room.map_name, players, room.title)
                log.info(f"  Match recorded: map={room.map_name!r} players={players}")
            except Exception as e:                    # 기록 실패가 게임 시작을 막으면 안 된다
                log.error(f"  Match record failed: {e}", exc_info=True)

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
        if message == "/status":
            # 채널 입장 때 자기 입장(type 4)을 받으면 클라가 자동으로 보냄 → type 14 (접속인원·채널·방 수)
            self.send(P_CHAT, build_status_payload())
            return
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


P2P_MAGIC = b"RKP2"
P2P_HELLO, P2P_QUERY, P2P_RELAY, P2P_DELIVER = 0x01, 0x02, 0x10, 0x11
P2P_HELLO_ACK, P2P_ENDPOINT, P2P_PUNCH_REQ, P2P_UNKNOWN = 0x81, 0x82, 0x83, 0x84
P2P_EP_TTL = 60.0          # 런처 DLL(rkp2p)은 10초마다 HELLO 를 보낸다
P2P_MAX_PAYLOAD = 1100


class P2PRendezvous:
    """NAT 홀펀칭 중개 (런처 0.9066 의 TG_Net.dll 프록시 rkp2p 와 짝).

    각 PC 의 게임 UDP 11223 소켓이 이 UDP 포트로 HELLO 를 보내면, 공유기가 붙인 실제
    공인 주소:포트(endpoint)를 기억한다. 게임이 같은 방 상대에게 처음 보내려 할 때
    QUERY 가 오면 양쪽에 서로의 endpoint 를 알려 동시에 구멍을 뚫게 하고(ENDPOINT /
    PUNCH_REQ), 끝내 안 뚫리면 RELAY 로 받은 게임 패킷을 상대에게 DELIVER 한다.
    게임이 쓰는 상대 주소(로비가 알려준 주소)와 endpoint 는 다를 수 있어 둘 다 싣는다.
    같은 방에 있는 로비 접속끼리만 중개한다.
    """

    def __init__(self, state: "ServerState"):
        self._state = state
        self.endpoints: Dict[str, tuple] = {}     # UDP 출발 IP -> ((ip, port), 마지막 HELLO 시각)
        self._seen: set = set()

    @staticmethod
    def _pack_ep(ep: tuple) -> bytes:
        return socket.inet_aton(ep[0]) + struct.pack("!H", ep[1])

    def _endpoint(self, ip: str):
        e = self.endpoints.get(ip)
        if e and _time.monotonic() - e[1] <= P2P_EP_TTL:
            return e[0]
        return None

    def _client_at(self, ip: str):
        found = [c for c in self._state.clients if c.peer_ip == ip and c.account]
        return found[0] if len(found) == 1 else None

    def _room_peer(self, me: "ClientSession", game_ip: str):
        """`me` 와 같은 방에서, me 의 게임이 game_ip 로 알고 있는 플레이어."""
        if not me.room_title:
            return None
        found = [c for c in self._state.clients_in_room(me.room_title)
                 if c is not me and c.address_for(me) == game_ip]
        return found[0] if len(found) == 1 else None

    def _note(self, key, msg):
        if key not in self._seen:
            self._seen.add(key)
            log.info(msg)

    def handle(self, transport, data: bytes, addr: tuple):
        if len(data) < 5:
            return
        kind, body = data[4], data[5:]
        src_ip = addr[0]
        if kind == P2P_HELLO:
            first = self._endpoint(src_ip) != addr
            self.endpoints[src_ip] = (addr, _time.monotonic())
            if first:
                me = self._client_at(src_ip)
                log.info(f"P2P: {src_ip} endpoint {addr[0]}:{addr[1]} "
                         f"(account={_kr(me.account) if me else None!r})")
            transport.sendto(P2P_MAGIC + bytes([P2P_HELLO_ACK]) + self._pack_ep(addr), addr)
            return
        if kind not in (P2P_QUERY, P2P_RELAY) or len(body) < 4:
            return
        if self._endpoint(src_ip) != addr:
            self.endpoints[src_ip] = (addr, _time.monotonic())
        game_ip = socket.inet_ntoa(body[:4])
        me = self._client_at(src_ip)
        other = self._room_peer(me, game_ip) if me else None
        other_ep = self._endpoint(other.peer_ip) if other else None
        if kind == P2P_QUERY:
            if other_ep is None:
                self._note(("unknown", src_ip, game_ip),
                           f"P2P: {src_ip} asked for {game_ip} -- not a hole-punching peer in the same room "
                           f"(me={_kr(me.account) if me else None!r}, peer={_kr(other.account) if other else None!r})")
                transport.sendto(P2P_MAGIC + bytes([P2P_UNKNOWN]) + body[:4], addr)
                return
            transport.sendto(P2P_MAGIC + bytes([P2P_ENDPOINT]) + body[:4] + self._pack_ep(other_ep), addr)
            transport.sendto(P2P_MAGIC + bytes([P2P_PUNCH_REQ]) + socket.inet_aton(me.address_for(other))
                             + self._pack_ep(addr), other_ep)
            log.info(f"P2P punch: {_kr(me.account)!r} {addr[0]}:{addr[1]} <-> "
                     f"{_kr(other.account)!r} {other_ep[0]}:{other_ep[1]}")
            return
        # RELAY
        payload = body[4:]
        if other_ep is None or not payload or len(payload) > P2P_MAX_PAYLOAD:
            return
        transport.sendto(P2P_MAGIC + bytes([P2P_DELIVER]) + socket.inet_aton(me.address_for(other)) + payload,
                         other_ep)
        self._note(("relay", src_ip, other.peer_ip),
                   f"P2P relay: {_kr(me.account)!r} -> {_kr(other.account)!r} (홀펀칭 실패, 서버가 중계)")


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
        self._p2p = P2PRendezvous(state)

    def connection_made(self, transport: asyncio.DatagramTransport):
        self._transport = transport
        sock = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        log.info(f"DP8 broadcast relay listening on UDP 0.0.0.0:{UDP_RELAY_PORT}")

    def datagram_received(self, data: bytes, addr: tuple):
        if data[:4] == P2P_MAGIC:
            try:
                self._p2p.handle(self._transport, data, addr)
            except Exception as e:
                log.warning(f"P2P error from {addr}: {e}")
            return
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
            self._json({"server_version": SERVER_VERSION, "p2p": 1})
        elif self.path.startswith("/rules"):
            try:
                with open(RULES_FILE, "r", encoding="utf-8") as f:
                    rules = json.load(f)
            except (OSError, ValueError):
                rules = {}
            self._json({"server_version": SERVER_VERSION, **rules, "p2p": 1})
        else:  # /matches.json, /matches, /   (승/패는 결과코드로 다시 판정해 보여 줌)
            matches = _load_matches()
            for rec in matches:
                _recompute_winloss(rec)
            self._json(matches)

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
