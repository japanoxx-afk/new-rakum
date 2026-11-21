# 태조왕건 리플레이(WGReplay.dll)와 라크무 재생 비교 (2026-11-22)

출처: github.com/japanoxx-afk/wanggun 저장소에는 리플레이 코드가 없음(런처·더미 서버뿐, 92커밋 전체 확인).
실제 리플레이는 Downloads\WangGunLauncher-v0.90074.exe (PyInstaller) 안 runtime-patches.zip 의
<해상도>/WGReplay.dll + WangGun-Replay-Trial.json(exe 패치 314곳, 대부분 화면 확장용) — 실행하지 않고 정적 분석.
추출본: scratchpad\wgx\ (WGReplay.dll, WangGun-Replay-Trial.json, ddraw.ini)

## 왕건이 하는 것
- 기록 파일: .initial.sav(게임 저장) + .state.bin('WGSTATE1': rand·난수 객체 등 0x14바이트 + 8바이트) + .map.wgm(맵) + .events.bin
- 검사 1 (0x1000a5d0): 유닛 표 0x7EB548, 칸 0x104바이트 x 0x6A6칸(라크무와 같은 칸 수) **전 칸**(죽은 칸 포함)의
  바이트 오프셋 2,3,4,5,10,11,15,28,29,30,31 을 FNV-1a 로 해시. 다르면 "Replay simulation diverged at frame %u".
- 검사 2 (0x10009630): 플레이어 표 0x857640 (0x640 간격, 9명)의 자원·인구 필드 FNV-1a.
  다르면 "Replay resource or population state diverged."
- 실제 멀티 경기 중에도 플레이어별 체크섬을 비교해 multiplayer-desync.txt/.bin 남김.
- 재생 중 보는 사람 조작(선택 배열 0x8B8A06, 카메라 0x85AEA8, 0x7CF7A0 블록)을 저장/복원.
- 날씨 "viewport" 를 따로 설정 (Unsupported weather viewport) — 날씨 rand 소비가 화면 크기에 따라 다를 수 있음.
- 오류 시 crash.txt (frame, eip, 레지스터), performance.txt.
- 실험 기능 환경변수: WG_BUILD_RESERVATIONS, WG_BUILDER_VEHICLE, WG_WORKER_PHASING, WG_ADJACENT_SPAWN.

## 라크무와 차이·개선 후보
1. 검사값: 라크무는 hp>0 유닛의 hp·위치·종류만 해시. 죽은 칸 상태(죽은 프레임 +0x24 등)·인구·자원은 안 봄
   -> 20261122_022438 버서커 문제는 9048에 이미 갈라졌는데 9765에야 잡힘. 왕건처럼 전 칸 + 인구·자원을 넣으면 첫 원인 지점에서 잡힘.
   (새 녹화부터만 적용, 예전 리플레이는 지금 검사 유지)
2. 맵 보관: 라크무도 v0.9076 부터 재생 때 맵을 넣음 (기록에는 이미 map_rkm).
3. 보는 사람 클릭: 라크무의 플레이어 선택 배열(0x7F793E)은 명령 처리(0x4407E0)와 0x43BAB0·0x44F6xx 만 씀,
   UI 는 읽기만 -> 재생 중 클릭이 경기에 영향 없음 (확인).
4. 날씨·화면 크기: 녹화(800x600)와 재생(고해상도 1280x720) 화면 크기가 다르면 비 효과 rand 소비가 다를 가능성 -> 확인 필요.
5. 멀티 경기 중 PC끼리 체크섬 비교(desync 기록) — 버서커처럼 원래 경기 자체가 PC마다 달랐는지 확인하는 데 유용.
