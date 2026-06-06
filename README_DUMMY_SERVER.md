# RhakMu Dummy Server

This dummy server is for local restoration/debugging of the RhakMu client.
It listens on multiple TCP/UDP ports, logs incoming packets, replies to HTTP launcher requests, and can send simple guessed TG_Net replies.

## Start

Open PowerShell in the workspace folder and run:

```powershell
cd "C:\Users\seo\Documents\라크무"
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none
```

Keep that PowerShell window open while running `Launcher.exe` or `Rhakmu.exe`.

Log files are written to:

```text
.\rhakmu_packet_logs
.\rhakmu_dummy_server_events.log
.\rhakmu_dummy_server_terminal.log
```

By default the dummy server skips UDP `11223`. When the server PC also runs a
RhakMu client, that client needs UDP `11223` for room peer checks, so the dummy
server must not bind it.

Room members can still be removed after 10-20 seconds if Windows blocks direct
client-to-client UDP. Run `Install-RhakMuClientPatches.ps1` as administrator on
both PCs after pulling the latest files so the strengthened inbound/outbound
RhakMu firewall rules are installed.

The 2026-06-06 UDP capture showed a more specific failure mode: the clients
initially exchanged UDP on the Radmin VPN addresses, then the server-side
client started sending repeated UDP keepalives from `192.168.0.22` to
`192.168.56.1`. That `192.168.56.1` address is a virtual/host-only adapter on
the other PC, not the Radmin peer address, so the room peer check times out
after roughly 10-20 seconds.

Run this on both PCs before multiplayer tests:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-RhakMuClientPatches.ps1
```

For restoration tests that must behave like remote PCs, force RhakMu peer UDP to
use Radmin VPN instead of the local LAN:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-RhakMuClientPatches.ps1 -RadminOnly -EnableFirewallProfiles
```

`-RadminOnly` allows RhakMu UDP `11223` to Radmin's `26.0.0.0/8` range and
blocks RhakMu UDP `11223` to private LAN ranges (`192.168.*`, `10.*`,
`172.16-31.*`). Run it on every PC before testing. This is the preferred
multiplayer test mode because distant PCs will not share a `192.168.*` LAN.
The block rules only work when Windows Firewall is enabled; use
`-EnableFirewallProfiles` or enable the firewall manually.

If the same timeout continues, temporarily disable VMware/VirtualBox/Hyper-V
host-only adapters for the RhakMu test:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-RhakMuClientPatches.ps1 -DisableVirtualAdapters
```

After testing, restore disabled virtual adapters:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Set-RhakMuNetworkPreference.ps1 -RestoreVirtualAdapters
```

If members are still removed after 10-20 seconds, capture UDP `11223` on both
PCs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuUdpCapture.ps1
# reproduce the room join timeout
powershell -NoProfile -ExecutionPolicy Bypass -File .\Stop-RhakMuUdpCapture.ps1
```

Capture file names now include the detected local IP address, preferring the
Radmin `26.*` address. When `Stop-RhakMuUdpCapture.ps1` runs, it copies the
capture files plus dummy-server logs into:

```text
.\logs\<ip>\<capture-session>
```

If the folder is a git repository, the stop script also commits and pushes that
session folder to GitHub. Use `-NoGitUpload` to save locally only.
If GitHub rejects the push with `fetch first`, the stop script now runs
`git pull --rebase origin main` before pushing. For an older script that already
created a local log commit but failed to push, run this once in that PC's repo:

```powershell
git pull --rebase origin main
git push origin main
```

To download all uploaded analysis logs from GitHub into a local helper folder,
run:

```text
Download-RhakMuAnalysisLogs.bat
```

The downloaded files are copied to:

```text
.\downloaded_analysis_logs\logs
```

## Room Join Network Watch

When two PCs can see a room but cannot enter it, run this on both PCs before
the join test:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Watch-RhakMuNetwork.ps1
```

Keep the watch running, create a room, try to enter it from the other PC, then
send the generated `rhakmu_network_watch_*.log` files with the dummy server
terminal log. The important lines are RhakMu UDP endpoints and whether both
players are visible on UDP port `11223`.

Each received packet creates:

- `.bin`: raw packet bytes
- `.txt`: decoded header, ASCII strings, hex dump

## Modes

```powershell
-AutoReply none
```

Logs packets only. Safest for discovering the first client packet. HTTP launcher requests still receive a simple `200 OK` reply.

```powershell
-AutoReply empty
```

Replies with the same packet type and zero-length payload.

```powershell
-AutoReply guess
```

Replies with several guessed TG_Net reply shapes:

- same type + `uint32 1`
- request type + 1 + `uint32 1`
- request type OR `0x8000` + `uint32 1`
- same type + `uint32 0`

Use `guess` only after capturing the first packet.

## Observed Check Client Packet

Observed first packet:

```text
FF 01 0C 00 52 48 41 4B E8 03 00 00
```

Decoded:

```text
type=0x01FF
size=12
payload="RHAK" + uint32 1000
```

The server now replies to this automatically:

```text
FF 01 08 00 00 00 00 00
```

If the client still stays on "checking client", try:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -CheckClientReplyType plus1
```

If it says patch/version error, try:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -CheckClientResult 1
```

## Observed Announcement Packets

After check-client succeeds, the client sends:

```text
FF 03 04 00
```

Decoded:

```text
type=0x03FF
size=4
likely TNPacket_ReqAnnounceMent
```

The server now replies with:

```text
FF 03 08 00 00 00 00 00
```

The client also sends:

```text
FF 02 06 00 03 00
```

The server now replies with:

```text
FF 02 08 00 00 00 00 00
```

If announcement still hangs, try:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -AnnouncementReplyMode empty
```

or:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -AnnouncementReplyMode multi
```

## Default Ports

```text
80, 11223, 2000, 2300, 2301, 2302, 2303, 2304, 2400, 3000, 4000, 47624, 5000, 7000, 7777, 8000, 8080, 9000, 10000, 10001, 10262, 11000, 12000, 20000, 21000, 28000
```

Custom example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -Ports 80,11223,7000,7777,9000,10000 -AutoReply none
```

## Hosts Entries

If the client still goes to the old domains, map them to localhost:

```text
127.0.0.1 www.rhakmuonline.com
127.0.0.1 rhakmuonline.com
127.0.0.1 www.trigger.co.kr
127.0.0.1 trigger.co.kr
127.0.0.1 wanggun.trigger.co.kr
127.0.0.1 king.trigger.co.kr
127.0.0.1 rhakmugame.hangame.naver.com
127.0.0.1 rhakmu.trigger.co.kr
```

Hosts file:

```text
C:\Windows\System32\drivers\etc\hosts
```

## Workflow

1. Start dummy server with `-AutoReply none`.
2. Start `Launcher.exe` or `Rhakmu.exe`.
3. Try the online/free-battlenet menu.
4. Check `rhakmu_packet_logs`.
5. If first packets are captured, switch to `-AutoReply empty` or `-AutoReply guess`.
6. Use the logged packet types to implement real replies one by one.

## Test Account

Built-in test account:

```text
id: test
password: test1234
```

Additional local multiplayer test accounts:

```text
test1 / 1111
test2 / 1111
test3 / 1111
test4 / 1111
test5 / 1111
test6 / 1111
test7 / 1111
test8 / 1111
test9 / 1111
test10 / 1111
```

Lobby chat:

- Observed request type: `0x12FF`
- Payload shape: `<message>\0<account>\0`
- The dummy server echoes the packet back to the sender and broadcasts it to other logged-in TCP clients on the same port.

For login/create-account testing, start the server with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -AcceptLikelyAccountPackets
```

Then enter:

```text
test
test1234
```

This mode replies to account-looking packets with several success candidates. Once the exact login packet type is known from the log, replace this heuristic with a precise reply.

## Multiplayer Start Notes

Current default:

```powershell
.\Start-RhakMuDummyServer.ps1 -AutoReply none -GameStartSyncMode original
```

`GameStartSyncMode original` relays the host's exact `0x0FFF` start packet to
the other clients in the same room. The 2026-06-06 04:29 test proved the
direct room UDP path can keep both members present, but the guest still did not
start because the dummy server logged `Game start relay suppressed` for the
host's `0x0FFF` packet.

If a future test shows duplicate countdowns or a regression, temporarily start
the server with:

```powershell
.\Start-RhakMuDummyServer.ps1 -AutoReply none -GameStartSyncMode none
```

Start relay diagnostics are now written both to the terminal and to
`.\rhakmu_dummy_server_events.log`. Look for these lines:

```text
Game start sync mode=...
Room broadcast room=... type=0x0FFF reason=game-start-original
Room broadcast delivered ... targets=1
Room broadcast skipped no-room ...
Room broadcast no-target ...
```

If the `0x0FFF` packet arrives on a TCP connection whose `RoomTitle` is empty,
the server now infers the room from the logged-in account before broadcasting.
This covers the case where the client sends the start packet after switching
connection state.

If one host direction starts both clients but the other direction starts only the host, check the room host IP printed by the server:

```text
Room registered id=... owner=test2 host=26.x.x.x
```

That `host=` value is what the guest receives in the battlefield list and room join reply. The guest PC must be able to connect back to that address for the direct countdown/start path. If the automatic address is wrong, start the server with an explicit host address:

```powershell
.\Start-RhakMuDummyServer.ps1 -AutoReply none -RoomJoinHost 26.x.x.x
```

When UDP capture shows the clients are actually exchanging peer packets on LAN
addresses instead of Radmin VPN addresses, first run the client setup with
`-RadminOnly` on both PCs. Then start the server with Radmin per-account room
host addresses:

```powershell
.\Start-RhakMuDummyServer.ps1 -AutoReply none -RoomHostOverrides "test1=26.240.153.112","test2=26.157.67.215"
```

The server prints `RoomHostOverrides:` at startup and applies these addresses
to room-list, room-join, and room-member payloads for the matching accounts.
Comma-separated override text is also accepted, which is useful when copying a
single command line:

```powershell
.\Start-RhakMuDummyServer.ps1 -AutoReply none -RoomHostOverrides "test1=26.240.153.112,test2=26.157.67.215"
```

If the log shows a combined host such as
`26.240.153.112,test2=26.157.67.215`, pull the latest scripts and restart the
server. The host field must be only one IP address.

LAN overrides such as `test1=192.168.0.8` are useful only as a short local
diagnostic. Do not use them for restoration validation because distant PCs will
not have that route.

The 2026-06-05 21:24-21:26 test showed:

- `test2` local host -> `test1` remote guest: guest entered the room, but only the host counted down.
- `test1` remote host -> `test2` local guest: both clients counted down.

That points to a direct connectivity/NAT/firewall difference between the two host directions, not to the dummy server's TCP start reply.

Room join reply detail:

- `0x10FF` success replies now send the room owner/host account plus the host IP.
- Earlier builds sent the joining account in that field, which can let both clients enter the room but misalign the local player slot/race when the RTS match starts.
- Stale rooms are removed when the owner logs in again, creates a new room, or sends a crash report. Old room entries can otherwise leave stale player counts/room metadata visible in the battlefield list.

One-step client setup:

```powershell
cd "C:\Users\seo\Documents\라크무"
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-RhakMuClientPatches.ps1
```

Or double-click:

```text
Install-RhakMuClientPatches.bat
```

Run it from an elevated/admin PowerShell window, or start the `.bat` as
administrator. It pulls the latest scripts when possible, installs firewall
rules, applies the required client patches, and runs the final verifier.

Firewall-only setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Configure-RhakMuFirewall.ps1
```

Run this on every PC. If a PC can connect to the lobby but cannot receive countdown/game packets when it hosts, Windows firewall or the selected host IP is the first thing to check.

Radmin-only firewall setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Configure-RhakMuFirewall.ps1 -RadminOnly -EnableFirewallProfiles
```

Room presence/timeout notes:

- The server skips UDP `11223` by default. When the server PC also runs a
  RhakMu client, that client must own UDP `11223` for direct room peer checks.
- `0x1FFF` channel-user-list requests return the current lobby/member list by
  default. Room-specific member-list broadcasts are also sent when a user joins
  a room, but they do not replace the client's direct UDP peer check.
- If a room member disappears after 10-20 seconds, inspect UDP capture output
  first. Any repeated traffic to `192.168.*`, `172.16.*`, `10.*`, VMware,
  VirtualBox, Hyper-V, or host-only adapter addresses means the client picked
  the wrong network interface for peer checks.

## Client Patch Verification

Run this on each PC after copying the latest scripts:

```powershell
cd "C:\Users\seo\Documents\라크무"
powershell -NoProfile -ExecutionPolicy Bypass -File .\Verify-RhakMuClientPatches.ps1
```

All rows should show `OK`. If `CPannelMgr menu vtable guard` is missing, apply:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Patch-RhakMuPanelMenuGuards.ps1
```

This guard fixes a crash seen during the countdown-to-game transition at:

```text
CPannelMgr::ProcessMenu()+0095
```

where the client called through a half-destroyed menu object's vtable.

Observed login packet:

```text
type=0x05FF
payload="test\0test1234\0..."
```

The server now replies automatically:

```text
FF 05 08 00 00 00 00 00
```

If login still hangs, try:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -LoginReplyType plus1
```

or:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -LoginReplyType multi
```

## Observed Channel Join Packet

Observed after login:

```text
type=0x07FF
payload="<channel name>\0"
```

The server now replies automatically:

```text
FF 07 08 00 00 00 00 00
```

If channel join still hangs, try:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -ChannelJoinReplyType plus1
```

or:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -ChannelJoinReplyType multi
```

## Observed Guild List Packets

Observed in lobby:

```text
type=0x15FF
type=0x18FF
```

These appear while the UI says it is requesting guild lists.

Important: replying with the same type to `0x15FF` or `0x18FF` can crash the client inside `TNPacket_ReplyRankList()`.

The server now replies to `0x15FF` with a plus-one candidate and ignores `0x18FF` by default:

```text
00 16 08 00 00 00 00 00
```

If guild list still hangs, try:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -GuildReplyMode plus1empty
```

or:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -GuildReplyMode multi
```

To avoid guild/rank replies entirely while testing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuDummyServer.ps1 -AutoReply none -GuildReplyMode ignore -RankListReplyMode ignore
```

## Client Exit Crash Guards

Observed when pressing the in-game exit button:

```text
GameCtrl.dll, class_form::DeleteAllControls()+0008
Rhakmu.exe, CScenChannel::~CScenChannel()+0029
```

This indicates that a menu scene form may already be partially torn down when
the menu/base-data cleanup runs. `Patch-RhakMuMenuDeleteGuards.ps1` now disables
both the scalar `operator delete` path and the inherited `class_form` cleanup
call inside `CScenChannel`, `CScenGuild`, and `CScenRanking` destructors.

Apply it after replacing or restoring `Rhakmu.exe`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Patch-RhakMuMenuDeleteGuards.ps1
```

To confirm the client patch state on any PC:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Verify-RhakMuClientPatches.ps1
```

Every row should show `OK`. If the guest PC does not show `OK` for
`Battle start countdown sync`, it can receive the server start packet but still
ignore the countdown/start transition.

## Match Cleanup Packet Notes

Observed during or immediately after a match:

```text
client -> server: FF 27 04 00
old reply:        FF 26 06 00 02 00
```

The old `0x26FF` cleanup reply can be interpreted by the client as a battle
request reply and route through `TNPacket_ReplyBattleReqReply()` into
`TNPacket_ReqRoomJoin()`. That can crash in:

```text
iCARUS.dll, classSTB::SetIndexPosition()
Rhakmu.exe, TNPacket_ReqRoomJoin()
Rhakmu.exe, TNPacket_ReplyBattleReqReply()
```

The dummy server now suppresses replies to `0x27FF`. It also ignores the
post-game `0x10FF 00 30 00` room reentry probe instead of treating it as a
normal battlefield room join.

## Remote Start Countdown Sync

Observed when a host starts a two-player room:

```text
host -> server:       FF 0F 07 00 02 00 00
server -> participant FF 0F 07 00 02 00 00
```

The participant receives the packet, but the stock `TNPacket_ReplyBattleReqReply`
handler switches on `packet[5] - 1`. Because `packet[5]` is `0`, it falls into a
default debug branch and returns without starting the participant countdown.

`Patch-RhakMuBattleStartSync.ps1` changes that default branch to set the same
local countdown/game-start state used by `classRoomNetMGR::RMPKRecv_GameStart`:

```text
byte [0x006DFC74] = 5
DWORD [0x006E0970] = 0
```

Apply this patch to every PC that will join multiplayer games:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Patch-RhakMuBattleStartSync.ps1
```

The dummy server also relays unhandled raw UDP datagrams between peers seen on
the same UDP port. This is enabled by default with `-EnableUdpRelay $true`.
Room/game synchronization often appears on UDP port `7000` as raw one-byte
datagrams, so relaying them helps when direct peer-to-peer room traffic is not
passing between clients.

The server also has `-GameStartSyncMode`, defaulting to `none`. In the
2026-06-04 23:55 working-ish two-PC trace, both clients reached the game without
the dummy server broadcasting `0x0FFF`; the start appears to have traveled over
the clients' direct room/game path instead. Because later server-side `0x0FFF`
variants did not start the guest and could destabilize the host, the dummy
server no longer relays start packets by default.

When experimenting, `-GameStartSyncMode original-plus-variants` makes the host
packet:

```text
FF 0F 07 00 02 00 00
```

relay as the original packet plus several narrow status/action variants:

```text
FF 0F 07 00 02 01 00
FF 0F 07 00 01 00 00
FF 0F 07 00 01 01 00
FF 0F 07 00 00 01 00
```

This tests the stock `TNPacket_ReplyBattleReqReply` branches that key off the
small action/status fields without requiring another client binary change. Use
it only for controlled diagnosis. The server log then shows:

```text
reason=game-start-original
reason=game-start-accept-variant
reason=game-start-action1-status0
reason=game-start-action1-status1
reason=game-start-action0-status1
```

With the default `none` mode, the log shows:

```text
Game start relay suppressed
```

## Room Member Tracking

Observed in the two-PC start-sync failure:

```text
test1 -> server:  FF 10 ... "test2\0..."
server -> test1:  FF 10 ... "test1\0<host-ip>\0"
host starts:      FF 0F 07 00 02 00 00
server -> test1:  FF 0F 07 00 02 00 00
```

The server acknowledges the join to the joining client. A direct experiment that
also sent `0x10FF` to the room host was rejected by the host client: it
immediately sent `0x11FF` room leave and both clients returned to the lobby.
That means `0x10FF` is not a safe host-side member notification packet.

When a client joins an existing room, the server now only:

1. Tracks the room member in memory.
2. Reports the updated current-player count in battlefield room-list items.

During multiplayer tests, the log must not contain:

```text
TCP-ROOM-JOIN-NOTIFY ... type=0x10FF
```
