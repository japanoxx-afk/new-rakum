# RhakMu 멀티플레이 안정 실행 순서

현재 안정 테스트 프로필 기준입니다.

- 서버 PC: `26.157.67.215`
- 원격 PC: `26.240.153.112`
- 네트워크: Radmin VPN `26.x`
- 더미서버 프로필: 방장 identity + 클라이언트 직접 시작 경로

## 이 프로필을 쓰는 이유

2026-06-07 01:24 로그에서는 더미서버가 시작 패킷을 끼워 넣지 않았습니다.

```text
Game start sync mode=none ... payload=02 00 00
Game start relay suppressed ...
```

이 상태에서는 서버 PC가 방장일 때 방장만 시작했습니다. 방장 클라이언트는 자기
로컬 상태로 바로 시작하지만, 게스트는 직접 UDP 경로만으로 카운트다운을 시작하지
못했습니다. 그래서 현재 안정 프로필은 방장 identity를 유지하면서 원본 Start
패킷만 게스트에게 릴레이합니다.

- 방 입장 응답 identity: 방장 계정
- Start 릴레이: 원본 `0x0FFF 02 00 00`만 전달
- 실험용 `02 01 00`, `02 08 00` 변형은 전달하지 않음

그래서 안정 프로필은 아래 값으로 고정합니다.

```text
RoomJoinIdentityMode: host
GameStartSyncMode: original-plus-sync-ok
StartTraceWindowSec: 20
ChannelUserListReplyMode: members
```

## 1. 양쪽 PC에서 게임 실행 전 패치

관리자 권한 PowerShell을 열고 실행합니다.

서버 PC:

```powershell
cd C:\Users\seo\Documents\라크무
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-RhakMuClientPatches.ps1
```

원격 PC:

```powershell
cd C:\Users\seo\Documents\rakmu-git
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-RhakMuClientPatches.ps1
```

마지막 줄이 아래처럼 나와야 합니다.

```text
RhakMu patch bundle version: 2026-06-07.0215
```

## 2. 양쪽 PC에서 캡처 시작

서버 PC:

```powershell
cd C:\Users\seo\Documents\라크무
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuUdpCapture.ps1
```

원격 PC:

```powershell
cd C:\Users\seo\Documents\rakmu-git
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuUdpCapture.ps1
```

## 3. 서버 PC에서만 더미서버 시작

서버 PC:

```powershell
cd C:\Users\seo\Documents\라크무
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuStableServer.ps1
```

시작 로그에 아래 3줄이 보여야 합니다.

```text
RoomJoinIdentityMode: host
GameStartSyncMode: original-plus-sync-ok
StartTraceWindowSec: 20
ChannelUserListReplyMode: members
```

## 4. 양쪽 PC에서 RhakMu 실행 및 테스트

1. 서로 다른 계정으로 로그인합니다. 예: `test1`, `test2`
2. 1차 테스트: 원격 PC가 방 생성 -> 서버 PC 입장 -> 원격 PC가 Start
3. 2차 테스트: 서버 PC가 방 생성 -> 원격 PC 입장 -> 서버 PC가 Start

Start 버튼을 누를 때 더미서버에는 아래처럼 나와야 정상입니다.

```text
Game start sync mode=original-plus-sync-ok ...
Room broadcast delivered ... reason=game-start-original
Room broadcast delivered ... reason=game-start-sync-ok
```

`original` 단독 비교가 필요하면 서버 PC에서 아래처럼 실행합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuStableServer.ps1 -GameStartSyncMode original
```

## Start Sync A/B Check

The current logs show that the dummy server writes `0x0FFF` start packets to the
other room member and that the target client later sends `0x11FF` leave-room.
That means the next useful split is client-side: confirm whether the battle
start client patch is forcing the host into the game while the peer rejects the
start packet.

Run this diagnostic mode on both PCs before launching RhakMu:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-RhakMuClientPatches.ps1 -RestoreBattleStartSyncPatch
```

Then start the server PC with the original relay mode:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-RhakMuStableServer.ps1 -GameStartSyncMode original
```

Test both directions:

1. Remote PC creates room, server PC joins, remote PC presses Start.
2. Server PC creates room, remote PC joins, server PC presses Start.

After that, restore the normal patched mode on both PCs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-RhakMuClientPatches.ps1
```

또는:

```powershell
.\Run-RhakMuStableServerOriginal.bat
```

Start 패킷을 받은 클라이언트가 곧바로 방을 나가면 아래 줄이 추가로 찍힙니다.

```text
Start trace target-left elapsedSec=... reason=game-start-original ...
```

`game-start-accept-variant` 또는 `game-start-stage8-variant`가 보이면 실험용
프로필로 실행된 것입니다. 정상 테스트에서는 `game-start-original`과
`game-start-sync-ok`만 확인합니다.

## 5. 테스트 후 양쪽 PC에서 캡처 종료

양쪽 PC에서 실행합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Stop-RhakMuUdpCapture.ps1
```

## 그래도 동시에 시작하지 않으면 확인할 것

다음 정보를 로그와 함께 알려주세요.

- 어느 PC가 방을 만들었는지
- 방장 계정명
- 입장 계정명
- 더미서버 시작 로그에 `RoomJoinIdentityMode: host`가 있었는지
- 방 입장 로그가 `Room join reply identity mode=host`였는지
- Start 후 약 13초 뒤 `0x11FF`가 찍혔는지
