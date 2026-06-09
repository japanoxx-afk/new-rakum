#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RhakMu DP8 payload sniffer.

The game's actual multiplayer runs over DirectPlay8 on UDP 11223. This raw
socket sniffer captures the real UDP payloads to/from the peer on port 11223
and dumps them as hex, so we can see whether the in-game RMPK sync packets
(room-master types 0x1002..0x1011, little-endian e.g. "02 10 ..") are actually
flowing during the "connecting" phase, in which direction, and what they carry.

Run as Administrator on ONE PC during the stuck "connecting" screen:
    python Sniff-RhakMuDP8.py <PEER_RADMIN_IP> [seconds]

It auto-detects this PC's Radmin (26.x) IP to bind the raw socket.
"""
import socket
import struct
import sys
import time
from collections import Counter

def get_local_radmin_ip():
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = info[4][0]
        if ip.startswith("26.") or ip.startswith("25."):
            return ip
    # fallback: first non-loopback
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = info[4][0]
        if not ip.startswith("127."):
            return ip
    return "0.0.0.0"

def pkt_name(payload):
    """Name the in-game packet by its TG_Net type word (first 2 bytes, LE)."""
    if len(payload) < 4:
        return f"short({len(payload)})"
    t = struct.unpack_from("<H", payload, 0)[0]
    names = {
        0x8811: "0x8811 REQ(packet-request)",
        0x8813: "0x8813 READY/state",
        0x8814: "0x8814 DATA?",
        0x8810: "0x8810 GAMEDATA",
        0x8800: "0x8800 GAMEDATA2",
        0x8812: "0x8812",
    }
    if t in names:
        return names[t]
    if 0x1002 <= t <= 0x1011:
        return f"RMPK 0x{t:04X}"
    return f"type 0x{t:04X}"

def main():
    if len(sys.argv) < 2:
        print("Usage: python Sniff-RhakMuDP8.py <PEER_RADMIN_IP> [seconds]")
        return
    peer = sys.argv[1]
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    local = get_local_radmin_ip()
    print(f"Local bind IP : {local}")
    print(f"Peer IP       : {peer}")
    print(f"Duration      : {secs}s  (do the game start / stay on 'connecting')")
    print("=" * 64)

    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
    s.bind((local, 0))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    s.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
    s.settimeout(1.0)

    end = time.time() + secs
    types_out = Counter()   # type counts, OUT (this PC -> peer)
    types_in = Counter()    # type counts, IN  (peer -> this PC)
    first_seen = {}         # type -> first payload hex (per direction)
    total_out = total_in = 0

    def summary():
        print("=" * 64)
        print(f"OUT (this PC {local} -> peer {peer}):  {total_out} pkts")
        for k, v in types_out.most_common():
            print(f"   {k:28s} x{v}")
        print(f"IN  (peer {peer} -> this PC):  {total_in} pkts")
        for k, v in types_in.most_common():
            print(f"   {k:28s} x{v}")
        print("-- first payload sample per (dir,type) --")
        for key, hx in first_seen.items():
            print(f"   {key}: {hx}")
        print("KEY QUESTION: does GAMEDATA (0x8810/0x8800) ever flow, and both ways?")

    try:
        while time.time() < end:
            try:
                data, _ = s.recvfrom(65535)
            except socket.timeout:
                continue
            if len(data) < 20:
                continue
            ihl = (data[0] & 0x0F) * 4
            if data[9] != 17:  # UDP
                continue
            src = socket.inet_ntoa(data[12:16])
            dst = socket.inet_ntoa(data[16:20])
            if peer not in (src, dst):
                continue
            if ihl + 8 > len(data):
                continue
            sport, dport, ulen = struct.unpack_from(">HHH", data, ihl)
            if 11223 not in (sport, dport):
                continue
            payload = data[ihl + 8: ihl + ulen]
            name = pkt_name(payload)
            out = (src == local)
            d = "OUT" if out else "IN "
            if out:
                types_out[name] += 1; total_out += 1
            else:
                types_in[name] += 1; total_in += 1
            key = f"{d} {name}"
            if key not in first_seen:
                first_seen[key] = payload[:32].hex(" ")
    except KeyboardInterrupt:
        print("\n(interrupted)")
    finally:
        try:
            s.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
        except Exception:
            pass
        s.close()
    summary()

if __name__ == "__main__":
    main()
