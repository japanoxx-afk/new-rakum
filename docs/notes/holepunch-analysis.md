# RhakMu P2P / NAT hole-punching analysis (2026-11-21)

## Network path (Rhakmu.exe 1.000d, online mode [0x6e167e]==3)
- Lobby: TG_Net.dll TCP -> server 11223.
- Room join + in-game lockstep: TG_Net.dll **UDP**, one socket bound to local 11223
  (0x423b6a/0x423c1b push 0x2bd7 -> 0x448800 -> TGNet_CreateUDPSocket).
- Every send uses a sockaddr built with **fixed port 11223** and a peer IP:
  - joiner after 0x10FF: 0x445141 InitSockAddr(&sa, 11223, host_ip) -> Send2UDP 0x445184
  - host replies to the join request at 0x4451b0: dest = 0x444b10(sender IP) -> port 11223 again
    (codes 2/3/4 = refuse/version/etc, 0x4452a7 version compare)
  - in-game per-player send 0x448de0 (cached per-player sockaddr), fallback 0x448eb0 (0x8813)
- Receive dispatcher 0x449d80.. identifies the sender by **source IP** vs the 8 player IPs and
  candidate lists; unknown source -> 0x8813/0x8814 path (see PEER_ADDRESS_ANALYSIS.txt).
- WG_IPX.dll (DirectPlay8 wrapper) is used in mode 2 (0x445921 cmp 2) — LAN mode. Online mode
  appears not to rely on it (SYNC_PORT_ANALYSIS.txt also says the DP8 assumption was unproven).
- No local C compiler on this PC (gcc/cl/clang/zig absent) -> build a DLL on CI windows-latest.

## Why joins die after 10 s
Joiner's UDP to host_public:11223 is dropped by host's NAT (no inbound mapping) -> no reply ->
timeout -> lobby. Same for in-game traffic.

## NAT check on this PC (STUN, google x2 + cloudflare)
local 41223 -> mapped 41223 on all three; 41224 -> 41224. Port-preserving, endpoint-independent
mapping = hole-punch friendly. Other players' NATs unknown.

## Proposed design: wrap the socket layer, don't patch the game logic
TG_Net.dll imports sendto/recvfrom from WSOCK32. Hook those two (proxy TG_Net.dll forwarding
all 23 exports to the renamed original, or redirect TG_Net's IAT to a small rkp2p.dll).
- On start: send REGISTER(account) from the game's own 11223 socket to NAS UDP rendezvous port
  -> server learns the player's real public ip:port (same NAT mapping the peers will use).
- Server pushes to room members: peer_ip(as given to the game) -> public endpoint.
- sendto(peer_ip:11223) -> rewrite to learned endpoint; send punch packets both ways on join.
- recvfrom: rewrite source endpoint back to peer_ip:11223 so the game's IP matching still works.
- Fallback: if no reply within ~2 s, wrap packets and send via NAS UDP relay.
- Game code untouched; works even if NAT changes the port; relay covers symmetric NAT.
Needs: NAS UDP port forward (new), server rendezvous+relay (~150 lines py), hook DLL (~400 lines C,
built on CI), launcher installs/uninstalls DLL, two-network live test (e.g. phone hotspot).
Edge: two players behind one public IP -> server must hand out distinct virtual IPs.
