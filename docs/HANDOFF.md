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

현재 main: **v0.9103** (2026-11-26 배포. 싱글플레이 = 오프라인 메인 메뉴, 미니맵 시야, 멀티 턴 길이 기본 3프레임(99ms), 계급 점수제(server 0.9021). **사용자 요청으로 실제 게임·2PC 대전 확인 전에 배포** — 멀티에서 느려짐·무승부 보고가 오면 `DEFAULT_TURN_FRAMES = 5` 부터, 싱글 메뉴 겹침이 남으면 `package_mode_patch` ③ 부터 볼 것. 그 전: v0.9097 마법 순차 시전 — 사용자 요청으로 실제 게임 확인 전에 배포, 문제 보고가 오면 `smart_cast_patch` 부터 볼 것; v0.9095 맵 에디터 기본 보기 = 게임 보기, 찍기 블록 = 셀 격자 방향 사각형. 사용자가 원한 '셀 한 칸 단위 찍기'는 맵 구조상 불가라고 설명하고 이 상태로 두기로 함; v0.9094 맵 에디터 정사각형 보기·리플레이 목록 수정·여러 건물 집결지 깃발, v0.9093 공식 패치(Patch1003) 내장 — 깃발·패치 내장은 실제 게임 확인 전; v0.9092 종족 이름 한글: 위국군/아스트리아/바르바로이 — 방 화면 그림·런처·맵 에디터, 실제 게임 확인은 사용자에게 부탁한 상태; v0.9091 게임 화면 리플레이: .rkr 더블클릭 재생·자원 표(U/I 키)·모든 참가자 시야·상대 클릭·경고음/생산 소리 끔 — 사용자 실제 게임 확인 끝; v0.9088 v0.9086 패치 상태 인식 수정; v0.9087 더블클릭 건물·유닛 구분 수정; v0.9086 같은 건물 여러 개로 생산·연구 나눠 맡기기·집결지 동시 지정 — `docs/notes/production-split.md`; v0.9085 치트키 map). main 에 안 들어간 브랜치: `launcher-v0.9031.1-compat`(예전 호환판), `launcher-v0.9061-nas-online`(NAS 서버, 아래),
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

- v0.9089 **모든 참가자 시야 합치기** (사용자 결정 변경: 전체 밝힘 -> 스타크래프트2 리플레이 방식): 그리는 동안만 표[내 번호]=0xFF,
  탐색 지도 0x915D50 보관 후 0, 타일 안개 0x957D90 = 시야 지도 0x999DD0 이 0 인 칸만 0xFF, 미니맵 = 지형 반 밝기 + 보는 칸 + 유닛 점(0x469030).
  유닛 시야 마스크는 건드리지 않음. 자원 표(아이콘·U/I 키), .rkr 더블클릭 재생(`replay_assoc.py`).
  섹션 코드가 2쪽(0x2000)으로 늘어 BUF 등이 0x1000 뒤로 밀림 (이전 판 섹션은 OLD_CODE_SIZE 로 인식).
  v0.9090: 합치는 시점을 그릴 목록 만들기(0x43E520, 자리 0x4D6669) 앞으로 옮김 — 사용자 확인: 상대 진영 잘 보임.
- v0.9091 재생 중 **클릭**: 마우스 입력 처리 0x430C00 을 감싸 그동안 표[내 번호]=0xFF·탐색 지도 0 (`pick`) — 상대 유닛·건물이
  녹화한 사람 시야 밖이어도 골라짐. **소리**: 0x49E5D0(알림, 건물 선택 0x372..0x375 만 통과)·0x49E2B0(생산 완료) 를 재생 중 막음
  (`snd1`/`snd2`). 에뮬레이터 테스트만 함 — 실제 게임 확인은 사용자.

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
- **v0.9100~v0.9102 싱글플레이 = 오프라인 메인 메뉴** (PR #23, v0.9103 으로 배포): `scenario_mode.py` (머리말에 분석). 게임은 레지스트리 HKLM `SOFTWARE\TriggerSoft\RhakMu` 의
  `Pack` 이 0 이면 TNet 로그인만, 0 이 아니면 오프라인 메인 메뉴로 시작한다 (0x4DD130/0x4DD1F0). [싱글플레이] 버튼(`_on_single_play`)이 Pack=1 로 바꿔
  서버·hosts 없이 실행하고 다음 보통 실행 때 되돌린다 (`cfg['package_mode_saved']`). `package_mode_patch.py` 는 이 실행에서만 켠다
  (`minimap_patch.build(..., package=True)`): ① CD 키 확인(0x4D9763) 건너뜀 ② 시계 0x465240 을 싱글에서도 (0x465298, 0x465344..)
  ③ 메인 메뉴(쪽 8) Init 0x413820·Draw 0x41437A 의 '대화 상자 0..5 숨기기' 를 '목록(폼 +0x30)의 모든 대화 상자 숨기기' 로 (v0.9102).
  경기 뒤 메인 메뉴로 돌아오면 빈 대화 상자 6개가 겹쳐 보이고 눌리지 않던 문제. GameCtrl 의 dlg_Active/GetDlg 는 목록 순번으로 찾는데
  Draw 가 상태 0 에서 매 프레임 0..4 를 숨기는데도 보였으므로 목록에 같은 대화 상자가 더 들어 있다고 판단 (어디서 두 번 읽는지는 미확인:
  0x423370 → 0x426F40 → 0x4275F0 이 유일한 읽기 경로). **사용자 확인 대기** — 안 되면 런처가 게임 메모리에서 폼 8 의 목록 길이를 읽어 확인할 것.
  v0.9100(경기 끝 0x4D5813)·v0.9101(점수 화면 0x411EC0)의 ExitProcess + 런처 재실행 우회는 재실행 뒤에도 같은 화면이라 걷어냄 (`RETIRED`).
  치트(`replay_record_patch` cheatx): 사람 수를 +6 & 0x20 (컴퓨터 0x10) 로 셈 — 싱글 커스텀의 컴퓨터는 이름이 있어 예전 기준(이름)으로는 늘 막혔다.
  시나리오 맵은 `DATA\Scenario\Scenario-단계-진영.rkm` (0x419B60) — 설치본에 없음 (대전 맵을 넣어 본 v0.9098 실험은 목표·유닛이 없어 진행 불가, 버튼 제거).
  게임 방식 [0x6E167E]: 0 커스텀, 1 시나리오, 2 랜, 3 TNet. 메뉴 객체 0x6E0CE0, 쪽 바꾸기 0x424160.
- **v0.9104** (브랜치 launcher-v0.9104-turn2-akey): `DEFAULT_TURN_FRAMES` 3 → 2 (사용자가 2프레임으로 대전해 보고 기본값으로 요청), `smart_cast_patch` CODE4
  (0x45CF82: A 칸이 비고 D 칸이 이동(3)인 유닛은 A 키를 D 로 — 공격 없는 유닛), server 0.9022 (로비 목록 0x12FF type 4 `build_enter_payload` 도 계급 등급값; 0.9021 은 빠뜨림).
- **v0.9103 계급 점수제 (server.py 0.9021)**: 게임 0x42CA20 은 서버가 보낸 등급값(원래 래더 순위)의 구간으로 계급 15개(MENUMSG 121..135: 신·초인·패왕…하수·초보)를 고르고,
  내공 < 1000(사용자 정보 0x4226E1)·< 1010(목록 0x42CCC0)이면 무조건 초보. 서버가 승수를 보내던 것을 `TIERS` (내공 구간 → 그 계급 구간의 등급값)로 바꿈.
  NAS 서버는 server.py 교체 + 컨테이너 재시작 필요 (사용자 작업).
- **v0.9101 멀티 턴 길이 (명령 전송 간격)**: `turn_length_patch.py` (머리말에 분석·근거). Game_Multi 의 턴 = 5프레임(0x4D7B97) → 기본 3프레임(99ms),
  속도 되돌림 기준 0x44A98D 3 → 2. 클릭→실행 ≈ (지연 턴 − 1 + 0.5) × 턴 길이. `cfg['turn_frames']` (기본 `DEFAULT_TURN_FRAMES` = 3), 규칙 파일·`/rules` 의
  `turn_frames` (없으면 5), 리플레이 규칙 `turn_frames` (없으면 5, 싱글 커스텀 경기는 1) → 재생은 `replay_record_patch.body(turn=)` 가 send 의 `% 5` 자리만 바꾼다.
  **실제 2PC 대전 확인 전** — 사용자 확인 대기. 문제가 나오면 `DEFAULT_TURN_FRAMES = 5` 로 되돌리면 원래 동작.
- **v0.9100 미니맵 시야 표시**: `smart_cast_patch` 의 CODE3 (.scast +0x400, 0x49BE70 의 call 0x469030 을 가로챔). 시야 계산 0x49B6A0 끝에서
  미니맵 그림(+0x1002C) = 지형(+0x2C) 반 밝기 + 내가 보는 칸(0x999DD0 & 표 0x4F02A0[내 번호])만 원래 밝기. 리플레이 재생은 그리기 직전 mmap 이 다시 덮는다(모든 참가자 시야).
  실제 화면은 사용자 확인 대기.
- **v0.9097 마법 순차 시전** (`smart_cast_patch.py`, 머리말에 분석): 0x447D60(대상 있는 명령 0x4009)·0x447E10(누르자마자 쓰는 마법 0x400D)
  머리를 맨 뒤 새 섹션 `.scast` 로. 유닛 마법(0x2021..0x2060)·2기 이상 선택이면 선택 명령 0x4002[한 기] → 마법 → 0x4002[전부].
  누르자마자 쓰는 것은 마나가 드는 마법만 (마나 0 인 변신류는 모두에게). v0.9096 시험판 상태는 `LEGACY` 로 인식.
  **단축키 A·S·D·F·G·Z·X·C·V·B 는 버튼 자리 순서**(표 0x4FCD28, 0x42F280)이고 유닛별 버튼은 `R1_DATA_MENU.STB` (R1_DATA_CHAR '한개선택메뉴' 열이 줄 번호).
  공격력이 없는 유닛(마령가마·나루·디거웜·네크로멘서·곤·라바)은 A 자리(공격)가 비어 있어 A 키가 안 먹는다 — 원래 게임 자료, 버그 아님.
  **섹션 순서**: 미니맵 꼬리 → .sel24 → .rkrec → .hotkey → .scast(항상). 걷어낼 때는 반대로 (`minimap_patch.underlying`, 런처 검증,
  시험의 `build()` 도우미). 마법 자료 표 0x500228 은 실행 중에 채워진다. 실제 게임 확인은 사용자.
- **v0.9095 맵 에디터**: 기본 보기 = 게임 보기(셀 격자 똑바로), 찍기 블록 = 셀 격자 방향 사각형 (사용자 요청 "타일찍기 기준을 셀격자로").
  정사각형 보기는 버튼으로. `map_editor_web/README.md` "보기와 찍기 블록".
- **v0.9094**: 맵 에디터 정사각형(평면) 보기 (`map_editor_web/README.md`), 리플레이 목록이 깨진 파일 하나로 비던 문제
  (`replay_model.READ_ERRORS` — zlib.error 를 따로 잡아야 함; 기록 파일은 `MatchWriter` 가 배타 생성 `xt`, 겹치면 `_2`),
  여러 건물 선택 때 집결지 깃발 (`production_split_patch.FLAG_SITE` 0x4D34E3 jne→jl, 그리기 0x4D34D0 은 선택 수 1 일 때만 그렸음).
- **공식 패치 내장 (v0.9093)**: 새 설치본에 따로 깔아야 했던 `Patch1003.exe` 가 하는 일은 Rhakmu.exe 1.000d 교체 +
  레지스트리 GameVer=1003 (+ 디버그 정보 Rhakmu.000, 안내문) 뿐이다 (설치 파일을 풀어 확인 — `game_version.py` 머리말).
  런처가 켤 때·게임 폴더를 바꿀 때·게임 실행 때 `game_version.apply_official_patch` 로 맞춘다. Rhakmu.000 은 넣지 않는다.
- **종족 이름 한글 (v0.9092)**: 위국군(무휼, 번호 0) / 아스트리아(아렌, 1) / 바르바로이(마르두크, 2) — 사용자 지정.
  게임 방 화면의 이름은 그림이다: `Data\Data002.FDB` 안 `DATA\MENUDATA\MENUCOMMON.S16` 31~36번. `race_name_patch.py` 가 게임 실행
  때 한글 그림으로 바꾼다 (원본은 `Data\MENUCOMMON.S16.orig`, 여섯 장 자리 말고는 한 바이트도 안 바뀜; S16 구조는 그 파일 머리말).
  그림은 `tools/make_race_name_sprites.py` (Noto Sans CJK KR Bold 13px — 14px 은 원본 자리를 넘는다). 런처·맵 에디터의
  이름은 `replay_model.py`·`replay_memory.py`·`map_editor_web/src/core.js`, 전적 사이트는 rtsarena `arena/games/rakmu.py`.
  DB(rtsarena SQLite)·리플레이·matches.json 에는 종족이 번호로만 들어 있어 바꿀 값이 없다.
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
