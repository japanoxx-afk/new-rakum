라크무(RhakMu) 서버 — NAS(Docker/Portainer) 운영 안내
=====================================================
작성: 2026-11-21 / 저장소 폴더: nas-server/ / 브랜치: nas-server-deploy
비밀번호·토큰은 이 문서와 저장소 어디에도 적지 않는다. (현재 서버는 비밀값이 필요 없다)

0. 한눈에 보기
--------------
- 런처가 로컬(127.0.0.1)에서 띄우던 server.py 를 그대로 NAS VM 의 Docker 에서 실행한다.
- 이미지 빌드 없음: 공개 이미지 python:3.12-slim 을 쓰고, 코드는 NAS 폴더에서 읽는다.
  (File Station 에 Dockerfile 을 올려도 Portainer 가 자동 빌드하지 않는다. 그래서 빌드가
   필요 없는 방식을 골랐다. server.py 는 표준 라이브러리만 써서 추가 설치가 없다.)
- 데이터(전적 matches.json, server.log, 선택 game_rules.json)는 NAS 의 game-servers/rakmu/data 에 남는다.
  컨테이너를 지우거나 새로 만들어도 데이터는 그대로다.
- 메모리 제한 128MB (실사용 약 30~40MB), CPU 0.5개, 도커 로그 5MB×3, server.log 1MB×6 으로 제한.
- 기본 포트는 rakmu-test 와 겹치지 않는 TCP 30010, TCP 30011, UDP 30012.
  rakmu-test 를 대체하려면 rakmu-test 를 먼저 중지하고 30000/30001/30002 로 바꾼다 (5장).

!! 먼저 읽을 것 — 지금 상태로 가능한 것과 아직 안 되는 것 (6장 자세히)
- 가능: 서버 실행, 전적/랭킹/버전 HTTP 를 인터넷에서 조회, 로비 TCP 접속.
- 아직 안 됨(추가 작업 필요): 게임(Rhakmu.exe)은 로비 포트 11223, 런처는 HTTP 11225 를 고정으로 쓰는데
  공유기는 30000~30999 만 전달한다 → 지금 런처/게임으로는 NAS 로비에 바로 못 들어간다.
  또 이 서버는 원래 Radmin/Hamachi 같은 VPN 안에서 쓰도록 만들어져서, 인터넷 너머(NAS)에 두면
  방 참가 시 상대에게 알려주는 주소가 VPN 주소가 아닌 공인 IP 가 된다 → 실제 대전 시작은 시험 전까지 장담 못 한다.

1. NAS·VM·컨테이너 경로 대응
-----------------------------
NAS File Station            VM 경로                               컨테이너 안 경로
game-servers/               /mnt/game-servers                     /mnt/game-servers   (외부 볼륨 game_servers_data)
game-servers/rakmu/app/     /mnt/game-servers/rakmu/app           /mnt/game-servers/rakmu/app    서버 코드
game-servers/rakmu/data/    /mnt/game-servers/rakmu/data          /mnt/game-servers/rakmu/data   전적·로그 (작업 폴더)
game-servers/rakmu/backups/ /mnt/game-servers/rakmu/backups       (서버는 쓰지 않음, 사람이 백업 보관용)
game-servers/rakmu-test/    (기존 프로젝트 — 읽지도 쓰지도 않음. nas_entry.py 가 rakmu-test 경로를 데이터 폴더로 쓰는 것을 거부함)

볼륨 주의: 외부 볼륨 game_servers_data 를 그대로 참조한다(compose 의 external: true).
"rakmu_game_servers_data" 처럼 스택 이름이 붙은 새 볼륨이 생기면 잘못 연결된 것이다 → 7장 문제 해결.

2. 준비 (내 PC)
---------------
1) 저장소에서 nas-server-deploy 브랜치를 받는다.
2) PowerShell 에서 업로드 폴더를 만든다:
     .\nas-server\Prepare-NasUpload.ps1
   → nas-server\upload\rakmu\ 아래에 올릴 파일이 모인다.
     app\server.py          (저장소 루트 server.py 복사본 = 런처가 쓰는 서버와 같음)
     app\nas_entry.py       (NAS 실행용 래퍼)
     app\DEPLOYED_VERSION.txt (서버 버전·커밋 기록)
     compose.yaml, ports.txt, README.txt, HANDOFF.txt
   업로드 폴더에는 data\ 가 없다 → 올려도 NAS 의 전적이 덮어써지지 않는다.

3. 첫 배포 (File Station → Portainer 클릭 순서)
-----------------------------------------------
[File Station]  https://akansas.synology.me:5001/  → File Station
1) game-servers 를 연다. rakmu-test 폴더는 열거나 바꾸지 않는다.
2) "생성 > 새 폴더 만들기" 로 rakmu 폴더를 만들고, 그 안에 app, data, backups 폴더를 만든다.
3) rakmu 폴더에 compose.yaml, ports.txt, README.txt, HANDOFF.txt 를 올린다 ("업로드 > 업로드 - 덮어쓰기").
4) rakmu/app 폴더에 server.py, nas_entry.py, DEPLOYED_VERSION.txt 를 올린다.
   최종 모양:
     game-servers/rakmu/compose.yaml ...
     game-servers/rakmu/app/server.py
     game-servers/rakmu/app/nas_entry.py
     game-servers/rakmu/data/        (비어 있음 — 서버가 채움)
     game-servers/rakmu/backups/     (비어 있음)

[Portainer]  https://akansas.synology.me:9443/
5) 로그인 → 환경 목록에서 게임 서버 Docker 환경(rakmu-test 가 보이는 환경)을 고른다.
6) 왼쪽 "Volumes" 에서 game_servers_data 가 있는지 확인한다. (없으면 배포하지 말고 7장)
7) 왼쪽 "Containers" 에서 Published Ports 열을 보고 30010, 30011, 30012 를 쓰는 컨테이너가 없는지 확인한다.
8) 왼쪽 "Stacks" → "+ Add stack".
9) Name: rakmu   (소문자)
10) Build method: "Web editor" → nas-server\compose.yaml 내용 전체를 붙여 넣는다.
11) (포트를 바꿀 때만) 아래 "Environment variables" → "+ Add an environment variable":
      LOBBY_PORT / HTTP_PORT / RELAY_PORT  (안 넣으면 30010 / 30011 / 30012)
12) "Deploy the stack" 클릭. 처음에는 python:3.12-slim 이미지를 받느라 1~2분 걸릴 수 있다.
13) Containers → rakmu-server 의 상태가 running, 1분쯤 뒤 healthy 인지 확인.
14) rakmu-server → "Logs" 에 아래 줄이 보이면 정상:
      [nas_entry] data=/mnt/game-servers/rakmu/data ...
      [nas_entry] RhakMu server 0.9012 로비 TCP 0.0.0.0:11223 준비 완료
15) File Station 에서 rakmu/data 에 server.log 가 생겼는지 확인 (= NAS 저장 확인).

4. 동작 확인 (내 PC, 외부에서)
------------------------------
1) 브라우저:  http://akansas.synology.me:30011/version
   → {"server_version": "0.9012"} 가 보이면 HTTP(전적) 포트까지 외부에서 열린 것.
   http://akansas.synology.me:30011/matches.json  → 처음엔 []
2) PowerShell (로비 TCP):
     Test-NetConnection akansas.synology.me -Port 30010
   → TcpTestSucceeded : True
3) UDP 30012 는 브라우저/Test-NetConnection 으로 확인할 수 없다. 실제 게임으로만 시험 가능.
4) 컨테이너 교체 후 데이터 유지 확인: Stacks → rakmu → Stop → Start 후 rakmu/data 의 파일이 그대로인지 본다.
주의: 위 확인은 "서버가 떠 있고 포트가 열림" 까지다. 실제 멀티플레이 성공과는 다르다(6장).

5. 운영 — 시작·중지·업데이트·복구·로그·백업
------------------------------------------
[시작/중지/재시작]  Portainer → Stacks → rakmu → Start / Stop
                   (또는 Containers → rakmu-server → Start / Stop / Restart)
                   restart: unless-stopped 이므로 VM 재부팅 후 자동 시작, 직접 Stop 하면 꺼진 채로 유지.

[서버 코드 업데이트] (server.py 가 바뀌었을 때 — 가장 흔한 경우)
 1) 백업: File Station 에서 rakmu/app 폴더를 rakmu/backups/app-YYYYMMDD 로 "복사".
 2) PC 에서 Prepare-NasUpload.ps1 실행 → upload\rakmu\app\ 의 파일을 rakmu/app 에 "덮어쓰기" 업로드.
 3) Portainer → Containers → rakmu-server → Restart.
 4) Logs 에서 "준비 완료" 와 새 서버 버전 확인. /version 확인.

[스택 설정(compose.yaml) 변경]
 Portainer → Stacks → rakmu → Editor 탭 → 수정 → "Update the stack".
 (이미지 갱신까지 원하면 "Re-pull image and redeploy" 켬). 바꾼 compose.yaml 은 NAS rakmu/ 와 저장소에도 반영.

[이전 버전으로 복구 (롤백)]
 1) Stacks → rakmu → Stop.
 2) File Station 에서 rakmu/backups/app-YYYYMMDD 안의 파일을 rakmu/app 으로 덮어쓰기 복사.
 3) Stacks → rakmu → Start. Logs 확인.
 compose 를 되돌릴 때는 저장소의 이전 커밋 compose.yaml 을 Editor 에 붙여 넣고 Update the stack.

[로그 보기]
 - Portainer → Containers → rakmu-server → Logs (최근 출력. 도커 로그는 5MB×3 까지만 보관)
 - File Station → rakmu/data/server.log (+ server.log.1~5). 다운로드해서 문제 보고에 첨부.
   (로그에는 접속한 플레이어 IP 와 계정 이름이 들어 있으니 공개 게시하지 않는다)

[백업]
 대상: rakmu/data/matches.json (전적, 최근 500판), rakmu/data/game_rules.json (있을 때), rakmu/app/, rakmu/compose.yaml
 방법: File Station 에서 rakmu/data 를 rakmu/backups/data-YYYYMMDD 로 복사 (가끔 PC 로도 다운로드).
 서버가 켜진 상태에서 복사해도 되지만, 게임이 끝나는 순간과 겹치지 않게 한가할 때 한다.
 오래된 백업은 직접 지운다 (1TB 는 모든 프로젝트 공용).

[복원]
 1) Stacks → rakmu → Stop.
 2) rakmu/backups/data-YYYYMMDD/matches.json 을 rakmu/data/ 로 덮어쓰기 복사.
 3) Stacks → rakmu → Start. http://akansas.synology.me:30011/matches.json 로 확인.

[rakmu-test 를 대체할 때 (사용자 결정 필요 — 아직 하지 않음)]
 영향: rakmu-test 를 중지하는 동안 30000~30002 를 쓰는 기존 서버가 멈춘다. rakmu-test/data 는 그대로 둔다.
 1) Portainer 에서 rakmu-test 의 현재 설정(Stacks → rakmu-test → Editor, 또는 컨테이너 Inspect)을 PC 에 복사해 둔다(복구용).
 2) rakmu-test → Stop (Delete 하지 않는다).
 3) Stacks → rakmu → Editor → Environment variables: LOBBY_PORT=30000, HTTP_PORT=30001, RELAY_PORT=30002 → Update the stack.
 4) 4장 확인을 30000/30001 로 반복.
 되돌리기: rakmu 의 변수를 지우거나 30010~30012 로 되돌려 Update → rakmu-test → Start.
 참고: rakmu-test 는 host 네트워크, 이 스택은 bridge 네트워크 + 포트 게시. 둘이 같은 포트를 동시에 쓰면
 나중에 시작한 쪽이 "port is already allocated / address already in use" 로 실패한다.

6. 런처/게임에서 접속하는 방법 (중요 — 아직 미완성)
----------------------------------------------------
고정 포트 문제:
 - Rhakmu.exe 는 로비에 TCP 11223 으로 접속한다(실행파일 고정). 주소는 런처가 hosts 의 rhakmugame 으로 지정.
 - 런처는 전적/규칙을 http://<서버IP>:11225 로 조회한다(launcher.py 고정).
 - 공유기는 30000~30999 만 VM 에 같은 번호로 전달한다. → 11223/11225 로는 NAS 에 닿지 않는다.
해결 방법 (둘 중 하나 — 아직 둘 다 하지 않음):
 A) 서버 소유자에게 추가 포트 전달 요청 (코드 수정 없음):
      외부 TCP 11223 → VM TCP 30010,  외부 TCP 11225 → VM TCP 30011,  외부 UDP 47584 → VM UDP 30012
    그 뒤 런처 멀티플레이 서버 IP 에 112.159.73.235 입력 (hosts 는 IP 만 받으므로 도메인 대신 IP).
    단, 운영안내상 허용 범위(30000~30999) 밖이므로 소유자 판단이 필요하다.
 B) 런처 변경 (선택 사항, 미구현 — 설계는 HANDOFF.txt "런처 변경안"):
    런처에 "NAS 서버" 항목을 추가해, 내 PC 의 127.0.0.1:11223 을 akansas.synology.me:30010 으로 이어 주는
    작은 TCP 중계를 띄우고 hosts 의 rhakmugame 을 127.0.0.1 로 둔다. 전적 조회는 akansas.synology.me:30011.
공통 한계 (A, B 모두):
 - 이 서버는 방 참가자에게 "서버가 본 상대의 접속 주소"를 알려 준다. VPN 안에서는 그게 Radmin/Hamachi 주소라
   P2P 가 되지만, NAS 에서는 각 플레이어의 공인 IP(공유기 주소)가 된다 → 게임 중 P2P(UDP 11223)가 공유기에
   막혀 대전 시작/동기화가 실패할 가능성이 높다.
 - 방 찾기 UDP 릴레이(47584)는 VPN 브로드캐스트를 받아 중계하는 구조라, 인터넷 너머 NAS 에는 브로드캐스트가 오지 않는다.
 → 실제 대전까지 하려면 서버+런처에 "VPN 주소 알림" 기능을 추가하는 후속 작업이 필요하다 (HANDOFF.txt 다음 작업).

7. 문제 해결
------------
- Deploy 시 "volume game_servers_data ... not found / declared as external, but could not be found":
  환경을 잘못 골랐거나 볼륨 이름이 다르다. Volumes 목록의 정확한 이름을 확인하고, 다르면 compose 의
  두 군데(volumes: 아래 이름, 서비스의 game_servers_data:)를 같이 고친다. 새 볼륨을 만들지 않는다.
- "port is already allocated" / "address already in use": 다른 컨테이너(예: rakmu-test)가 그 포트를 사용 중.
  다른 번호로 바꾸거나 5장의 대체 절차를 따른다.
- 로그에 "can't open file '/mnt/game-servers/rakmu/app/nas_entry.py'": app 폴더 위치/파일 이름 확인.
- 로그에 PermissionError (data 폴더에 쓸 수 없음): 전체 공개 권한으로 풀지 말고, 오류 문장을 그대로
  서버 소유자에게 전달해 NAS 폴더 권한 확인을 요청한다.
- unhealthy: Logs 에서 HTTP 시작 실패(포트 11225) 메시지를 확인.
- 문제 보고 시: 접속 주소/포트, 증상 시각, 바꾼 파일, Portainer 로그(비밀값 제거).

8. 저장소 파일
--------------
nas-server/compose.yaml           Portainer 스택 설정 (Web editor 에 붙여 넣기)
nas-server/app/nas_entry.py       NAS 실행 래퍼 (데이터 폴더·로그 회전·포트 환경 변수)
nas-server/Prepare-NasUpload.ps1  업로드 폴더 생성 (server.py 를 루트에서 복사)
nas-server/test_nas_entry.py      PC 에서 Docker 없이 래퍼를 시험 (python nas-server\test_nas_entry.py)
nas-server/ports.txt              포트 목록
nas-server/HANDOFF.txt            인수인계 (현재 상태·다음 작업)
