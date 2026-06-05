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
```

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

This indicates that the channel or guild scene form may already be partially
torn down when the menu/base-data cleanup runs. `Patch-RhakMuMenuDeleteGuards.ps1`
now disables both the scalar `operator delete` path and the inherited
`class_form` cleanup call inside `CScenChannel` and `CScenGuild` destructors.

Apply it after replacing or restoring `Rhakmu.exe`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Patch-RhakMuMenuDeleteGuards.ps1
```

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
```

Apply this patch to every PC that will join multiplayer games:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Patch-RhakMuBattleStartSync.ps1
```
