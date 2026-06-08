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

def rmpk_name(payload):
    """If payload looks like a TG_Net/RMPK packet, name it."""
    if len(payload) < 4:
        return None
    t = struct.unpack_from("<H", payload, 0)[0]
    if 0x1002 <= t <= 0x1011:
        return f"RMPK 0x{t:04X}"
    if (t & 0x00FF) == 0xFF or (t >> 8) == 0xFF:
        return f"TGNet 0x{t:04X}"
    return None

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
    flows = Counter()
    rmpk = Counter()
    shown = 0
    SHOW_MAX = 80
    try:
        while time.time() < end:
            try:
                data, _ = s.recvfrom(65535)
            except socket.timeout:
                continue
            if len(data) < 20:
                continue
            ihl = (data[0] & 0x0F) * 4
            proto = data[9]
            if proto != 17:  # UDP
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
            direction = "OUT" if src == local else "IN "
            flows[f"{direction} {src}:{sport}->{dst}:{dport}"] += 1
            name = rmpk_name(payload)
            if name:
                rmpk[f"{direction} {name}"] += 1
            if shown < SHOW_MAX:
                hexs = payload[:48].hex(" ")
                tag = f"  [{name}]" if name else ""
                print(f"{direction} {src}:{sport}->{dst}:{dport} len={len(payload)}{tag}")
                print(f"    {hexs}")
                shown += 1
    finally:
        try:
            s.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
        except Exception:
            pass
        s.close()

    print("=" * 64)
    print("Flow counts:")
    for k, v in flows.most_common():
        print(f"  {k}: {v}")
    print("RMPK/TGNet packet types seen (this is the key signal):")
    if not rmpk:
        print("  (NONE found in payloads - DP8 may encapsulate them, or no game packets)")
    for k, v in rmpk.most_common():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
