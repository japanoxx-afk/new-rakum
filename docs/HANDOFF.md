# 인수인계 — 다른 PC에서 이어서 작업하기 (2026-11-22 기준)

이 문서 하나로 다른 PC에서 라크무 런처 작업을 이어 갈 수 있게 정리했다. 작업 기록·분석 메모는 `docs/notes/`,
리플레이 디버깅 도구는 `tools/replay_debug/` 에 있다.

## 0. 작업 방식 (사용자 요청 — 꼭 지킬 것)
- **결과 보고·설명은 항상 한국어로.** 코드·커밋 메시지는 저장소 관례(영어 커밋 제목)를 따른다.
- **실제 게임(Rhakmu.exe)을 띄우는 테스트는 먼저 사용자에게 묻는다.** 사용자가 게임 중일 수 있다.
  허락을 받으면 설치 폴더가 아닌 개인 게임 사본으로 테스트한다 (`tools/replay_debug/README.md`).
- 저장소는 **공개(public)** 다. 비밀값·개인 기록(경기 리플레이, 서버 로그 `server.log`, `matches.json`)은 올리지 않는다.

## 1. 저장소 (GitHub 계정 japanoxx-afk, 모두 public)
| 저장소 | 이 PC 폴더 | 내용 |
|---|---|---|
| [new-rakum](https://github.com/japanoxx-afk/new-rakum) | `Documents\claud\rhakmu` (+ 작업 폴더 여러 개) | **라크무 런처** (Python/tkinter, exe 빌드), 로컬 서버 `server.py`, 게임 exe 패치들, 웹 맵 에디터, 리플레이, NAS 서버(`nas-server/`) |
| [iop](https://github.com/japanoxx-afk/iop) | `Documents\claud\impact` | 임팩트 오브 파워 런처·밸런스 편집기·맵 에디터 (자체 README) |
| [rtsarena](https://github.com/japanoxx-afk/rtsarena) | `Documents\claud\rtsarena` | RTS 전적·리플레이 사이트 (자체 `HANDOFF.md`, `deploy/NAS_DEPLOY.md`) |
| [wanggun](https://github.com/japanoxx-afk/wanggun) | (이 PC엔 없음) | 태조왕건 런처·더미 서버 (리플레이 코드는 없음 — 아래 6절) |

2026-11-22 확인: 세 저장소 모두 커밋 안 한 코드 변경 없음, 모든 브랜치가 GitHub 에 올라가 있음.

### 새 PC 준비
```
git clone https://github.com/japanoxx-afk/new-rakum.git rhakmu
git clone https://github.com/japanoxx-afk/iop.git impact
git clone https://github.com/japanoxx-afk/rtsarena.git
```
- Python **3.12 (64비트)**. 테스트·패치 빌드에 필요:
  `pip install keystone-engine unicorn capstone pefile` (exe 빌드는 CI 가 하므로 pyinstaller 는 선택, 이 PC: 6.22.3)
- 게임: 라크무 1.000d 설치 (`C:\Program Files (x86)\TriggerSoft\RhakMu`). 원본 exe 는 저장소 `game_backup/Rhakmu.exe`.
- `gh` CLI 가 이 PC엔 없었다. 빌드 완료는 `git fetch` 로 `[skip ci]` 빌드 커밋이 생겼는지 보고 확인했다.
- 전적 사이트 업로드 토큰은 GitHub Secret `ARENA_UPLOAD_TOKEN` → 빌드 때 `arena_secret.py` 생성. 로컬에 둘 파일 없음.

## 2. 런처 릴리스 방법 (new-rakum)
1. `origin/main` 에서 `launcher-v0.90NN-<내용>` 브랜치를 만든다. 번호는 **origin 의 최신 번호 + 1** (먼저 `git fetch` 로 확인).
2. 함께 바꾼다: `launcher.py` 의 `APP_VERSION`, `RhakMuLauncher_v0.90NN.spec` (이전 spec 복사 후 번호만 바꿈, CRLF 유지),
   `release_notes.py` 맨 위에 한국어 노트.
3. 테스트: `.github/workflows/build-launcher.yml` 의 unittest 목록과 같은 명령 (`python -m unittest test_... -v`).
4. 브랜치를 push 하면 CI(windows-latest)가 exe 를 빌드해 `Build RhakMuLauncher_v….exe [skip ci]` 커밋을 덧붙인다.
5. 사용자가 머지하라고 하면 main 에 머지 (이 PC에선 `git commit-tree` 로 머지 커밋을 만들어 `main` 에 push).
   런처는 GitHub raw 의 `version.json` 으로 업데이트를 확인한다 — 머지 직후 몇 분은 CDN 캐시로 예전 버전이 보일 수 있다.

현재 main: **v0.9086** (같은 건물 여러 개로 생산·연구 나눠 맡기기·집결지 동시 지정 — `docs/notes/production-split.md`; v0.9085 치트키 map). main 에 안 들어간 브랜치: `launcher-v0.9031.1-compat`(예전 호환판), `launcher-v0.9061-nas-online`(NAS 서버, 아래),
`launcher-v0.9081-replay-full-reveal`(예전 맵 전체 밝힘 시도 — v0.9083 으로 대체, 쓰지 않음).

## 3. 게임 화면 리플레이 — 현재 상태와 다음 할 일
패치: `replay_record_patch.py` (exe 에 `.rkrec` 섹션; 기록·재생 코드는 keystone 어셈블리 → `CODE`, 예전 판은 `LEGACY`).
런처: `replay_recorder.py`(경기 중 기록 → `<런처 폴더>\replays\*.rkr`), `replay_model.py`, `launcher.py` `_play_replay_ingame`.

해결된 것
- v0.9070 경기 규칙(선택 한도·집결지 금광) 기록·재생, 서버/hosts 안 건드림, 커서 겹침
- v0.9073 어긋난 뒤에도 명령 계속 재생 (선택 명령에서 남의 유닛 제외)
- v0.9076 **지도 공개 치트가 유닛 시야를 바꿔 자동 공격이 달라지던 문제** (4분 44초 어긋남) → 공개 제거, 맵 자동 설치
- v0.9077 검사값 확대(태조왕건 방식): 전 칸 체력·죽은 프레임 + 플레이어 인구·자원. **v0.9077 이상으로 녹화한 경기만** 적용
- v0.9078 관전자 시점: 그리는 동안만 플레이어 비트 표[내 번호]=0xFF (시뮬레이션 시야는 그대로)
- v0.9080 v0.9078 재생 크래시: 비트 표가 읽기 전용 .rdata 에 있었음 → 재생 설치만 .rdata 쓰기 허용
- v0.9082 **죽은 유닛 처리 어긋남의 근본 원인** (버서커·일꾼 등, 5225/9765/8110 프레임 어긋남 모두):
  게임 저장(SaveGameData 0x4D93B2 `mov [ebp-0x118], 0x48`)이 유닛 종류 데이터를 종류마다 0x90 바이트만 담아
  +0x96('죽으면 시체로 남음') 등이 재생에서 사라졌다 → 재생에서만 죽은 유닛을 바로 지워 인구가 한 번 더 줄고 칸이 일찍 비었다.
  수정: 재생이면 LoadGAME 의 free(0x4D85F5)를 막아 자료 파일 종류 데이터를 보관하고, 불러온 뒤 저장의 앞 0x90 바이트만 덮어씀.
  확인: `20261122_052001` (12:29, 넓은 검사값) 처음부터 끝까지 원래 경기와 완전히 같음 (실제 게임, 개인 사본).
- v0.9083 **맵 전체 밝힘** (사용자 결정: 안개 없이 맵 전체): 그리는 동안만 표[내 번호]=0xFF, 유닛 시야 마스크 0xFF(섹션 +0x202000 에 보관),
  타일 안개 0x957D90 을 0, 미니맵 안개 그림(+0x1002C) = 지형 그림(+0x2C). overlay 에서 표·마스크를 되돌려 진행은 원래 시야 그대로.
  확인: 052001 을 밝힘 켠 채 끝까지 재생, 어긋남·ERR 없음, 화면·미니맵 안개 없음 (실제 게임, 개인 사본).

남은 일 (우선순위 순)
1. (끝남) 화면 시야는 v0.9083 맵 전체 밝힘으로 정해 main 에 머지.
2. 컴퓨터(AI) 상대 경기 재생 — 재생은 저장 불러오기로 시작해 AI 가 필요한 값(정상 시작 경로에서만 설정)이 없다.
   되면 혼자 테스트 가능.
3. (확인 필요) 녹화 800x600 / 재생 1280x720 처럼 화면 크기가 다를 때 날씨(비) rand 소비 차이.
   근거는 태조왕건 리플레이가 날씨 영역을 따로 맞추는 것뿐, 라크무에서 본 적은 없다. 실제 대전은 PC마다 같은 계산을 해야 하므로
   해상도가 다른 사람끼리 대전해도 문제없었다면 진행에는 영향 없음. 지금까지 확인한 리플레이 어긋남의 원인은 해상도가 아니었다.
4. 저장에서 빠지는 다른 상태가 더 있을 수 있음 — 어긋나면 `tools/replay_debug/diverge.py` → `hashbp.py` → `solve_wide.py` 순서로 찾는다.

리플레이 파일: 이 PC `%USERPROFILE%\Downloads\replays\*.rkr` (개인 경기 기록이라 공개 저장소에 올리지 않음 — 필요하면 직접 복사).
특히 `20261122_052001_[4](N4)_Fighting_Spirit.rkr`(넓은 검사값, v0.9082 로 끝까지 같음), `20261122_022438_[4](N4)_Fighting_Spirit1.1.rkr`, `20261121_205441_[4](N4)_Fighting_Spirit.rkr`.

## 4. 기타 진행 중·참고
- **NAS 서버 (Docker/Portainer)**: `nas-server/` (README, HANDOFF.txt), 브랜치 `launcher-v0.9061-nas-online`, 메모 `docs/notes/nas-server-deploy.md`.
  HANDOFF.txt 에 "main 을 머지하고 0.9063+ 로 올려야 함" 이 적혀 있다.
- 홀펀칭: `docs/notes/holepunch-analysis.md`, `rkp2p/` (C, CI 빌드). v0.9072 부터 인터넷 서버만 홀펀칭.
- 맵 에디터: `map_editor_web/`, 메모 `hill-min-size.md`, `map-editor-resource-pos.md`.
- 선택 한도 24: `selection-limit-analysis.md`. 집결지 생산: `rally-construct-spawn.md`.

## 5. 메모 목록 (`docs/notes/`)
| 파일 | 내용 |
|---|---|
| `ingame-replay-design.md` | 게임 화면 리플레이 설계·게임 루프 주소 |
| `replay-desync-v0.9073.md` | 5225프레임 어긋남(유닛 19 버서커) 조사, v0.9073 변경 |
| `replay-sync-test-20261122_022438.md` | 8525(지도 공개) / 9765(버서커) 원인 조사 |
| `wanggun-replay-comparison.md` | 태조왕건 WGReplay.dll 과 비교 |
| `nas-server-deploy.md`, `holepunch-analysis.md`, `hill-min-size.md`, `map-editor-resource-pos.md`, `selection-limit-analysis.md`, `rally-construct-spawn.md` | 각 기능 분석 |

## 6. 태조왕건 리플레이 참고
GitHub wanggun 저장소에는 리플레이 코드가 없다. 실제 리플레이는 사용자 PC 의 `Downloads\WangGunLauncher-v0.90074.exe`
(PyInstaller) 안 `runtime-patches.zip/<해상도>/WGReplay.dll`. `tools/replay_debug/wgx_extract.py` 로 꺼내 정적 분석만 했다.
