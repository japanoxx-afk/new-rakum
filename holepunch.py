"""Install / remove the rkp2p hole-punching proxy (rkp2p/rkp2p.c) in the game folder.

The game's TG_Net.dll is kept as TGNetOrg.dll and replaced by the proxy, which forwards
every export to it and only reroutes the game's UDP 11223 traffic (see rkp2p.c).
rkp2p.ini decides per launch whether it is active and which server UDP port it talks to.
"""
import ipaddress
import os
import pathlib

import game_address_patch

DLL = "TG_Net.dll"
ORG = "TGNetOrg.dll"
INI = "rkp2p.ini"
LOG = "rkp2p.log"
MARK = b"TGNetOrg.TGNet_"          # forwarder strings only the proxy contains
NAS_UDP_PORT = 30012               # NAS: external UDP 30012 -> container 47584
LOCAL_UDP_PORT = 47584             # server.py UDP_RELAY_PORT


VPN_PREFIXES = ("26.", "25.")      # Radmin VPN 26.x, Hamachi 25.x


def server_kind(server_ip, local_ips=()):
    """How the game reaches the other players for this lobby server.

    'internet' : a public address (the NAS 112.159.73.235, or another PC's server reached over
                 the internet) -> hole punching, and the game announces its internet address.
    'vpn'      : Radmin 26.x / Hamachi 25.x -> the players talk over the VPN directly.
    'lan'      : private / link-local address.
    'local'    : the launcher's own server on this PC (loopback or one of this PC's addresses).
    Only 'internet' uses the proxy; every other kind runs the game's original TG_Net.dll.
    """
    try:
        addr = ipaddress.IPv4Address(str(server_ip).strip())
    except ValueError:
        return "unknown"
    text = str(addr)
    if addr.is_loopback or text in set(local_ips):
        return "local"
    if text.startswith(VPN_PREFIXES):
        return "vpn"
    if addr.is_private or addr.is_link_local or addr.is_unspecified or addr.is_multicast or addr.is_reserved:
        return "lan"
    return "internet"


def server_udp_port(server_ip, nas_ip):
    return NAS_UDP_PORT if server_ip == nas_ip else LOCAL_UDP_PORT


def is_proxy(data: bytes) -> bool:
    return MARK in data


def _is_original(data: bytes) -> bool:
    if len(data) != game_address_patch.DLL_SIZE:
        return False
    try:
        return game_address_patch.pinned_ip(data[game_address_patch.OFFSET:game_address_patch.OFFSET + 80]) is None
    except ValueError:
        return False


def _write(path, data: bytes):
    tmp = str(path) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_ini(game_dir, enabled, server_ip="", port=0):
    text = "[rkp2p]\n" f"enabled={1 if enabled else 0}\n" f"server={server_ip}:{port}\n" "log=1\n"
    path = pathlib.Path(game_dir, INI)
    try:
        if path.read_text(encoding="ascii") == text:
            return
    except (OSError, ValueError):
        pass
    _write(path, text.encode("ascii"))


def state(game_dir):
    """'proxy', 'original' or 'unknown'."""
    try:
        data = pathlib.Path(game_dir, DLL).read_bytes()
    except OSError:
        return "unknown"
    if is_proxy(data):
        return "proxy"
    return "original" if _is_original(data) else "unknown"


def install(game_dir, proxy: bytes, enabled, server_ip="", port=0):
    """Put the proxy in place (keeping the original as TGNetOrg.dll) and write rkp2p.ini.

    Returns a short status string. Raises OSError (e.g. the game is running) or ValueError
    (TG_Net.dll is neither the original nor our proxy).
    """
    if not is_proxy(proxy):
        raise ValueError("홀펀칭 DLL 이 손상되었습니다.")
    dll = pathlib.Path(game_dir, DLL)
    org = pathlib.Path(game_dir, ORG)
    cur = dll.read_bytes()
    if not is_proxy(cur):
        if not _is_original(cur):
            raise ValueError(f"지원하지 않는 {DLL} 입니다 ({len(cur)}B).")
        if not org.exists() or org.read_bytes() != cur:
            _write(org, cur)
    elif not (org.exists() and _is_original(org.read_bytes())):
        raise ValueError(f"{ORG} (원래 {DLL}) 가 없거나 다릅니다. 게임 파일을 다시 설치하세요.")
    write_ini(game_dir, enabled, server_ip, port)
    if cur != proxy:
        _write(dll, proxy)
    return "켜짐" if enabled else "꺼짐"


def uninstall(game_dir):
    """Put the original TG_Net.dll back. Returns True when a file changed."""
    dll = pathlib.Path(game_dir, DLL)
    org = pathlib.Path(game_dir, ORG)
    try:
        cur = dll.read_bytes()
    except OSError:
        return False
    if not is_proxy(cur):
        return False
    data = org.read_bytes()
    if not _is_original(data):
        raise ValueError(f"{ORG} 가 원래 {DLL} 가 아닙니다.")
    _write(dll, data)
    return True
