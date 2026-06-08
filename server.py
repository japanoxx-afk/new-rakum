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
  0x02FF  Username     : server -> uint32(0)
  0x05FF  Login        : payload=account\0password\0hash; server -> uint32(result)
  0x07FF  Channel sel  : server -> uint32(result)
  0x15FF  Rank list    : server -> 0x16FF + 0x17FF (empty)
  0x18FF  Guild list   : server -> 0x19FF + 0x1AFF (empty)
  0x0BFF  Room list    : server -> 0x0CFF, [0x0BFF entries], 0x0DFF
  0x0EFF  Create room  : server -> uint32(0)
  0x1FFF  User list    : server -> 0x20FF, [0x1FFF entries], 0x21FF
  0x10FF  Join room    : server -> [0x00, account\0, host_ip\0]
  0x11FF  Leave room   : remove room/member
  0x0FFF  Game start   : relay to all in room + send sync-ok
  0x12FF  Chat         : broadcast as 0x13FF
  0x24FF  Post-game    : server -> 0x25FF [02 00]
  0x27FF  Post-game2   : suppress (no reply)
  0xFEFE  Crash report : log only
"""

import asyncio
import logging
import socket
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rhakmu")

HOST = "0.0.0.0"
PORT = 11223

# Default accounts (any login accepted if account not in list, just track it)
# Add real accounts here: "account": "password"
ACCOUNTS: Dict[str, str] = {
    "test": "test1234",
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


def pack_pkt(ptype: int, payload: bytes = b"") -> bytes:
    size = 4 + len(payload)
    return struct.pack("<HH", ptype, size) + payload


def nul(s: str) -> bytes:
    return s.encode("latin-1") + b"\x00"


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

    @property
    def player_count(self) -> int:
        return 1 + len(self.members)

    def build_list_entry(self) -> bytes:
        """Build the room list payload for 0x0BFF."""
        host_b = nul(self.host_ip)
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
        self._buf = b""

    @property
    def peer(self) -> str:
        return f"{self.peer_ip}:{self.peer_port}"

    @property
    def advertised_ip(self) -> str:
        """IP other peers should use to reach this client (Radmin/VPN, not loopback)."""
        if self.peer_ip in ("127.0.0.1", "::1"):
            return STATE.server_ip
        return self.peer_ip

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
            self.send(P_CONNECT, struct.pack("<I", 0))

        elif ptype == P_ANNOUNCE:
            self.send(P_ANNOUNCE, struct.pack("<I", 0))

        elif ptype == P_USERNAME:
            # payload: 1 byte flag + account\0
            strings = read_cstrings(payload[1:] if payload else b"")
            if strings:
                log.info(f"{self.peer}: username={strings[0]!r}")
            self.send(P_USERNAME, struct.pack("<I", 0))

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
            self.send(P_RANK_ACK1, b"")
            self.send(P_RANK_ACK2, b"")

        elif ptype == P_GUILD_LIST:
            self.send(P_GUILD_ACK1, b"")
            self.send(P_GUILD_ACK2, b"")

        elif ptype == P_ROOM_LIST_REQ:
            self.send(P_ROOM_LIST_ACK, b"")
            for room in STATE.rooms:
                self.send(P_ROOM_LIST_REQ, room.build_list_entry())
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
                    log.debug(f"{self.peer}: in-game unhandled 0x{ptype:04X} (no peers)")
            else:
                log.debug(f"{self.peer}: unhandled 0x{ptype:04X}")

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
            owner_ip = owner_client.peer_ip if owner_client else STATE.server_ip
            self.send(P_USER_LIST_REQ, nul(room.owner) + nul(owner_ip))
            # Send members
            for member in room.members:
                mc = next((c for c in STATE.clients if c.account == member), None)
                member_ip = mc.peer_ip if mc else self.peer_ip
                self.send(P_USER_LIST_REQ, nul(member) + nul(member_ip))
        elif self.account:
            self.send(P_USER_LIST_REQ, nul(self.account) + nul(self.peer_ip))
        self.send(P_USER_LIST_END, b"")

    async def _broadcast_member_list(self, room: "Room", exclude: "ClientSession" = None):
        """Send updated member list to all room members except the excluded client."""
        pkts = [pack_pkt(P_USER_LIST_ACK, b"")]
        # Owner entry
        owner_conn = next((c for c in STATE.clients if c.account == room.owner), None)
        owner_ip = owner_conn.peer_ip if owner_conn and owner_conn.peer_ip != "127.0.0.1" else room.host_ip
        pkts.append(pack_pkt(P_USER_LIST_REQ, nul(room.owner) + nul(owner_ip)))
        # Member entries
        for member in room.members:
            mc = next((c for c in STATE.clients if c.account == member), None)
            if mc:
                member_ip = mc.peer_ip if mc.peer_ip not in ("127.0.0.1", "::1") else STATE.server_ip
            else:
                member_ip = STATE.server_ip
            pkts.append(pack_pkt(P_USER_LIST_REQ, nul(member) + nul(member_ip)))
        pkts.append(pack_pkt(P_USER_LIST_END, b""))

        data = b"".join(pkts)
        for c in STATE.clients_in_room(room.title):
            if c is exclude:
                continue
            c.writer.write(data)
            await c.flush()

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

        self.room_title = room.title
        if self.account not in room.members and self.account != room.owner:
            room.members.append(self.account)

        joiner_ip = self.peer_ip if self.peer_ip not in ("127.0.0.1", "::1") else STATE.server_ip

        # Reply to joiner: [0x00][host_account\0][host_ip\0]
        # Client uses host_account to identify the P2P peer and host_ip to connect.
        self.send(P_JOIN_ROOM, bytes([0]) + nul(room.owner) + nul(room.host_ip))

        log.info(f"Room join: {self.peer} account={self.account!r} room={room.title!r} host={room.host_ip} joiner_ip={joiner_ip}")

        # Broadcast updated member list to ALL room members (owner + joiner).
        # The owner needs to see the joiner in the lobby player list before game start.
        # Do NOT send 0x10FF to the owner — the owner's client interprets it as a join
        # directive for itself and immediately leaves the room.
        await self._broadcast_member_list(room, exclude=None)

    def _handle_leave_room(self):
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

        all_in_room = STATE.clients_in_room(self.room_title)

        # Battle-start only. Re-sending 0x10FF at game start makes the guest
        # re-process the join and leave the room, so we must NOT do that here.
        # The DP8 connect was already triggered for the guest at join time.
        # The client's lobby dispatcher routes the battle-start handler
        # (ReplyBattleReqReply) from type 0x1EFF, NOT 0x0FFF.
        start_pkt = pack_pkt(P_BATTLE_START, payload if payload else bytes([0x02, 0x00, 0x00]))
        for c in all_in_room:
            c.writer.write(start_pkt)
            await c.flush()
            log.info(f"  Sent 0x1EFF battle-start to {c.account!r}")

    async def _handle_chat(self, payload: bytes):
        strings = read_cstrings(payload)
        message = strings[0] if strings else ""
        account = strings[1] if len(strings) > 1 else self.account
        if not account:
            account = self.account

        log.info(f"Chat from={account!r}: {message!r}")

        # Build server message: [0x00 0x00 0x00][account\0][message\0]
        msg_payload = bytes([0, 0, 0]) + nul(account) + nul(message)
        chat_pkt = pack_pkt(P_CHAT_REPLY, msg_payload)

        # Broadcast to all connected clients with accounts
        for c in STATE.clients:
            if c.account:
                c.writer.write(chat_pkt)
                await c.flush()

    def _handle_crash(self, payload: bytes):
        try:
            text = payload.decode("latin-1", errors="replace")
            log.error(f"CRASH from {self.peer} account={self.account!r}: {text[:300]}")
        except Exception:
            pass
        STATE.remove_rooms_for(self.account)


async def main():
    print("=" * 60)
    print("  RhakMu Private Server")
    print(f"  Listening on TCP {HOST}:{PORT}")
    print(f"  Server IP: {STATE.server_ip}")
    print(f"  Open login: {OPEN_LOGIN}")
    print(f"  Known accounts: {', '.join(ACCOUNTS.keys())}")
    print("=" * 60)
    print()

    server = await asyncio.start_server(
        lambda r, w: ClientSession(r, w).run(),
        HOST,
        PORT,
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
