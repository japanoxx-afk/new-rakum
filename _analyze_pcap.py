"""
Analyze pcapng files for DP8 (port 11223) traffic.
Usage: python _analyze_pcap.py <file.pcapng>
"""
import struct, sys, os

def parse_pcapng(path):
    data = open(path, "rb").read()
    pos = 0
    packets = []
    ifaces = []

    while pos < len(data):
        if pos + 8 > len(data):
            break
        block_type, block_len = struct.unpack_from("<II", data, pos)
        if block_len < 12 or pos + block_len > len(data):
            break

        # Section Header Block
        if block_type == 0x0A0D0D0A:
            pass
        # Interface Description Block
        elif block_type == 0x00000001:
            link_type = struct.unpack_from("<H", data, pos+8)[0]
            ifaces.append(link_type)
        # Enhanced Packet Block
        elif block_type == 0x00000006:
            iface_id = struct.unpack_from("<I", data, pos+8)[0]
            ts_high, ts_low = struct.unpack_from("<II", data, pos+12)
            cap_len, orig_len = struct.unpack_from("<II", data, pos+20)
            pkt_data = data[pos+28 : pos+28+cap_len]
            link = ifaces[iface_id] if iface_id < len(ifaces) else 1
            packets.append((link, pkt_data))
        # Simple Packet Block
        elif block_type == 0x00000003:
            orig_len = struct.unpack_from("<I", data, pos+8)[0]
            cap_len = min(orig_len, block_len - 16)
            pkt_data = data[pos+12 : pos+12+cap_len]
            link = ifaces[0] if ifaces else 1
            packets.append((link, pkt_data))

        pos += block_len

    return packets

def parse_ip_udp(link, pkt):
    """Return (src_ip, dst_ip, src_port, dst_port, payload) or None."""
    # Skip link layer
    if link == 1:   # Ethernet
        if len(pkt) < 14: return None
        eth_type = struct.unpack_from(">H", pkt, 12)[0]
        if eth_type == 0x0800:
            ip_start = 14
        elif eth_type == 0x8100:  # VLAN
            ip_start = 18
        else:
            return None
    elif link == 101:  # Raw IP
        ip_start = 0
    else:
        ip_start = 14  # assume ethernet

    if ip_start + 20 > len(pkt): return None
    ver_ihl = pkt[ip_start]
    proto = pkt[ip_start + 9]
    src_ip = ".".join(str(b) for b in pkt[ip_start+12:ip_start+16])
    dst_ip = ".".join(str(b) for b in pkt[ip_start+16:ip_start+20])
    ihl = (ver_ihl & 0x0F) * 4
    udp_start = ip_start + ihl

    if proto != 17:  # not UDP
        return None
    if udp_start + 8 > len(pkt): return None
    src_port, dst_port = struct.unpack_from(">HH", pkt, udp_start)
    payload = pkt[udp_start+8:]
    return src_ip, dst_ip, src_port, dst_port, payload

def analyze(path):
    print(f"\n=== {os.path.basename(path)} ===")
    packets = parse_pcapng(path)
    print(f"Total packets: {len(packets)}")

    dp8_packets = []
    all_udp_ports = {}

    for link, pkt in packets:
        r = parse_ip_udp(link, pkt)
        if r is None: continue
        src_ip, dst_ip, sp, dp, payload = r
        # Count all UDP ports
        for port in [sp, dp]:
            all_udp_ports[port] = all_udp_ports.get(port, 0) + 1
        # Filter port 11223
        if sp == 11223 or dp == 11223:
            dp8_packets.append((src_ip, dst_ip, sp, dp, payload))

    print(f"\nTop UDP ports seen:")
    for port, cnt in sorted(all_udp_ports.items(), key=lambda x: -x[1])[:15]:
        print(f"  port {port:5d} : {cnt} packets")

    print(f"\nDP8 (port 11223) packets: {len(dp8_packets)}")
    if dp8_packets:
        for i, (si, di, sp, dp, pay) in enumerate(dp8_packets[:30]):
            hex_pay = pay[:32].hex() if pay else ""
            print(f"  [{i+1}] {si}:{sp} -> {di}:{dp}  payload({len(pay)}): {hex_pay}")
    else:
        print("  ** NO port 11223 traffic found! **")
        print("  DP8 packets are NOT reaching this interface.")

for path in sys.argv[1:]:
    analyze(path)

if len(sys.argv) < 2:
    # auto-find
    for p in [
        r"C:\Users\seo\Downloads\서버pc-test2.pcapng",
        r"C:\Users\seo\Downloads\원격pc-test1.pcapng",
    ]:
        if os.path.exists(p):
            analyze(p)
