# 실제 게임 화면 리플레이 (RhakMu) — 분석·설계 메모

## 참고: WangGun 런처 v0.90074 (사용자 소유, Downloads\WangGunLauncher-v0.90074.exe, PyInstaller py3.14)
- runtime-patches.zip/<res>/WGReplay.dll (네이티브, export WGReplayMainMenu), WangGun-Replay-Trial.json(엑스 패치 314곳),
  ddraw.ini(maxfps). exe 패치 중 'opt-in replay bridge menu bootstrap' 한 곳이 메인 메뉴에서 DLL 호출.
- DLL 모드: 환경변수 WG_REPLAY_MODE(record|play), WG_REPLAY_SESSION(폴더), WG_REPLAY_SPEED(1|2|4), WG_REPLAY_TOTAL_MS.
- 기록 파일: 000001.initial.sav (게임 자체 저장 = 시작 상태), 000001.map.wgm, 000001.events.bin ('WGEVENT2', 프레임별 네이티브 패킷),
  state 해시 'WGDSYNC1' (프레임별 체크섬; 재생 중 다르면 "diverged at frame %u").
- 재생: 저장 불러오기 → 패킷 주입, 옵저버 키보드(1/2/4), 시계 오버레이, 끝/ESC.
- 런처: replay_runtime.start_session → LOCALAPPDATA\WGReplay\sessions\<uuid>\request.json, '--replay-worker' 감독 프로세스.

## RhakMu 대응 (Rhakmu.exe 1.000d; 엑스 안에 'D:\WangGun\STB' 문자열 — 같은 엔진)
- 루프: Game_Loop 0x4D7310 → Game_Multi 0x4D7A80 / 0x4D78E0 / 0x4D7CD0. 매 프레임 sim(0x4A1860, 0x43D970), 프레임 [0xB412B4]++,
  5프레임마다 0x447AF0(내 턴 전송) + 0x44A840(턴 디스패치 → 0x4407E0(p, batch, len) @0x44AABC) + 0x449AB0(난수 비교).
  프레임 시간 ms [0xB412B8] (0x21..0x42) — 배속 조절 지점.
- 난수: CRT srand([0x6E1A78]) @0x4D7376 (대전 시작), 매 턴 0x2000 명령에 rand 값 → PC끼리 비교. 객체 0xB40FE8 (+0x10 LCG).
- 저장/불러오기: Game_Loop 싱글 경로 — [0x6DFF8D]==1 && ![0xB412CB] → 0x4D75A0, 0x4D8220(경로 0x6E62F4 = 불러오기), 0x4D7880.
  저장 함수: 'SaveGame [%s]::[%s]' 0x4D82CD/0x4D91B5 (함수 0x4D8220 근처/0x4D9xxx), 'SaveGameData' 오류 0x4D91DF. USERs\%s\%s.SAV.
- 이미 있음 (v0.9053): .rkrec 섹션이 0x44AABC 를 감싸 [프레임][플레이어][길이][묶음] 링 버퍼 기록, 런처가 리플레이 파일에 저장.

## 계획
A. 기록: 대전 시작 직후 게임 저장 함수로 initial.sav 쓰기 + 프레임별 체크섬(rand 상태·유닛 합) 기록. (.rkrec 확장 또는 DLL)
B. 재생: 런처가 [0x6DFF8D]=1 + 경로로 '저장 불러오기' 시작 → 0x44A840 대신 기록 묶음을 프레임에 맞춰 주입, 0x447AF0·0x449AB0 끔,
   안개 끔, [0xB412B8] 로 1/2/4배, ESC 종료, 체크섬 비교로 어긋남 표시.
C. 도구: 이 PC엔 C 컴파일러 없음 → GitHub Actions(windows-latest MSVC x86)로 DLL 빌드하거나 keystone 어셈블리 섹션.
D. 시험: 싱글플레이(컴퓨터 상대)도 같은 0x44A840 경로를 쓰므로 이 PC에서 기록·재생 반복 시험 가능.
