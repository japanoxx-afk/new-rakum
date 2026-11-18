"""Pin the game's own IP (TG_Net.dll TGNet_Get_MyIPaddress) to the VPN address used toward the server.

Why: TGNet_Get_MyIPaddress returns the FIRST gethostname() address. With Hamachi
that usually is the 25.x adapter; with Radmin it is usually the physical LAN
(192.168.x). The game stores that address in its player table and its UDP receive
dispatcher (Rhakmu.exe 0x449d80) drops game data whose source does not match, so
on Radmin the peers stop syncing -> immediate disconnect -> the match ends as a draw.

Fix: before every launch the launcher writes a tiny cdecl routine into the 80-byte
function that returns the local IPv4 the OS uses to reach the selected server
(26.x on Radmin, 25.x on Hamachi, the LAN IP on LAN). Single play restores the
original bytes. Only that function (RVA 0x2010, file offset 0x2010) changes.
"""
import base64
import os
import socket
import ipaddress

DLL_NAME = "TG_Net.dll"
DLL_SIZE = 81979
OFFSET = 0x2010
ORIGINAL = base64.b64decode(
    "gewAAQAAjUQkAGgAAQAAUOg/qAAAg/j/dQkywIHEAAEAAMOLjCQIAQAAi5QkBAEAAFGNRCQEUlDo"
    "M////4PEDIHEAAEAAMOQkJCQkJCQkJA=")
assert len(ORIGINAL) == 80
# mov edx,[esp+4]; test edx,edx; jz fail; movzx ecx,word [esp+8]; cmp ecx,16; jb fail
HEAD = bytes((0x8b, 0x54, 0x24, 0x04, 0x85, 0xd2, 0x74, 0x2b,
              0x0f, 0xb7, 0x4c, 0x24, 0x08, 0x83, 0xf9, 0x10, 0x72, 0x21))
TAIL = bytes((0xb8, 1, 0, 0, 0, 0xc3, 0x31, 0xc0, 0xc3))


def code_for(ip: str) -> bytes:
    """80-byte replacement returning `ip` as a NUL-terminated string (same as radmin_address.ps1)."""
    addr = ipaddress.IPv4Address(ip)
    data = str(addr).encode("ascii").ljust(16, b"\0")
    code = bytearray(HEAD)
    for n in range(4):
        code += b"\xc7\x02" if n == 0 else bytes((0xc7, 0x42, n * 4))
        code += data[n * 4:n * 4 + 4]
    code += TAIL
    return bytes(code.ljust(80, b"\x90"))


def pinned_ip(func: bytes):
    """IP pinned by our code, None for the original function. Raises on unknown bytes."""
    if func == ORIGINAL:
        return None
    if len(func) == 80 and func.startswith(HEAD):
        try:
            data = b"".join(func[20 + i * 7:24 + i * 7] if i else func[20:24] for i in range(4))
        except IndexError:
            data = b""
        # Rebuild via the generator and compare to be strict.
        text = data.split(b"\0", 1)[0].decode("ascii", "replace")
        try:
            if code_for(text) == func:
                return text
        except ValueError:
            pass
    raise ValueError("지원하지 않는 TG_Net.dll 입니다 (주소 함수가 다릅니다).")


def state(game_dir: str):
    """Currently pinned IP (None = original). Raises on unsupported DLL."""
    path = os.path.join(game_dir, DLL_NAME)
    data = open(path, "rb").read()
    if len(data) != DLL_SIZE:
        raise ValueError(f"지원하지 않는 TG_Net.dll 크기입니다 ({len(data)}B).")
    return pinned_ip(data[OFFSET:OFFSET + 80])


def apply(game_dir: str, ip):
    """Pin `ip` (str) or restore the original (None). Returns True when the file changed."""
    path = os.path.join(game_dir, DLL_NAME)
    data = bytearray(open(path, "rb").read())
    if len(data) != DLL_SIZE:
        raise ValueError(f"지원하지 않는 TG_Net.dll 크기입니다 ({len(data)}B).")
    current = pinned_ip(bytes(data[OFFSET:OFFSET + 80]))
    if current == ip:
        return False
    backup = path + ".orig"
    if current is None and not os.path.exists(backup):
        with open(backup, "wb") as f:
            f.write(data)
    data[OFFSET:OFFSET + 80] = ORIGINAL if ip is None else code_for(ip)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return True


def _local_ipv4s():
    try:
        return [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        return []


def local_ip_toward(server_ip: str, prefer_radmin=False):
    """Local IPv4 the OS uses to reach server_ip, or None (loopback / unreachable).

    A connected UDP socket sends nothing; it only resolves the route.
    """
    try:
        addr = ipaddress.IPv4Address(server_ip)
    except ValueError:
        return None
    local = _local_ipv4s()
    if addr.is_loopback or str(addr) in local:
        # Server runs on this PC: its own address is what peers use. For loopback,
        # use the single Radmin address when Radmin is preferred.
        if not addr.is_loopback:
            return str(addr)
        rad = sorted({ip for ip in local if ip.startswith("26.")})
        return rad[0] if prefer_radmin and len(rad) == 1 else None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((str(addr), 11223))
            ip = s.getsockname()[0]
    except OSError:
        ip = None
    if ip and not ip.startswith(("127.", "0.")):
        return ip
    # Route lookup failed: same VPN prefix (26.x / 25.x) as the server.
    pref = str(addr).split(".")[0] + "."
    same = [i for i in local if i.startswith(pref)]
    return same[0] if len(same) == 1 else None
