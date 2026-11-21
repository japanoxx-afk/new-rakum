# 게임 화면 리플레이 디버깅 도구

리플레이 재생이 원래 경기와 어디서, 왜 어긋나는지 찾을 때 쓴 스크립트들이다.
(예전에는 세션 임시 폴더 `scratchpad` 에 있었다. `docs/notes/` 의 메모에서 'scratchpad' 는 이 폴더를 뜻한다.)

## 꼭 지킬 것
- **실제 게임(Rhakmu.exe)을 띄우기 전에 사용자에게 먼저 묻는다.** 사용자가 게임 중일 수 있다.
- 게임은 한 번에 하나만 뜬다. 다른 Rhakmu.exe 가 켜져 있으면 `probe_common.Play` 가 시작하지 않는다.
- 설치 폴더 게임을 건드리지 말고 **개인 게임 사본**을 쓴다:
  설치 폴더(`C:\Program Files (x86)\TriggerSoft\RhakMu`) 전체를 `tools/replay_debug/game/` 로 복사하거나
  환경변수 `RK_GAME` 에 사본 경로를 준다. (`game/` 은 저장소에 올리지 않는다.)
- 사본의 `Rhakmu.exe` 가 이상한 패치 상태가 되면 저장소의 `game_backup/Rhakmu.exe` 로 되돌린다.
- 프로세스는 자기가 띄운 pid 만 끈다 (`taskkill /IM` 금지).

## 준비
```
pip install keystone-engine unicorn capstone pefile
```
Python 3.12 (64비트), Windows. 스크립트 대부분은 첫 인자로 저장소 폴더, 둘째로 리플레이(.rkr) 경로를 받는다.
경로는 윈도 형식(`C:\...`)으로 준다 (Git Bash 의 `/c/...` 는 안 됨).

## 스크립트
| 파일 | 하는 일 |
|---|---|
| `probe_common.py` | 공통: 리플레이로 RKREPLAY.RKP·SAV 를 만들고 사본 게임을 재생 모드로 띄움 (`Play`). 리플레이 규칙(rules)·맵 자동 반영 |
| `diverge.py REPO RKR [ms]` | 빠르게 재생해 처음 어긋난 프레임과 그때 값을 출력. `NOREVEAL2=1` 이면 시작 때 지도 공개 코드를 뺀 실험판 (v0.9076 부터는 기본) |
| `hashbp.py REPO RKR F1 F2..` | 해시 루틴에 실행 중단점(디버거)을 걸어 검사값을 계산하는 순간의 유닛 표를 정확히 덤프 (`hashdump.json`, `raw_<frame>.bin`) |
| `solve2.py` ~ `solve5.py` | 덤프와 기록 해시로 "어느 유닛이 얼마나 다르면 해시가 맞는지" 역산 (`RK_REPLAY` 환경변수) |
| `watch.py REPO RKR ADDR FROM [HITS]` | 메모리 주소 쓰기 중단점 — 누가 그 값을 바꿨는지 호출 경로 출력 |
| `cmp_res.py REPO RKR A B` | 기록된 플레이어 자원·인구와 재생 값을 장면마다 비교 |
| `cmp_units.py REPO RKR F.. @F..` | 기록된 유닛 스냅샷과 재생 유닛 비교 / 덤프 |
| `typedump.py REPO RKR OUT` | 유닛 종류 표(0x4FCD88) 덤프 |
| `trace_pop.py`, `trace_slot.py` | 인구·칸 재사용 추적 (v0.9070 때) |
| `noreveal_prep.py` | 위 실험용 prepare (지도 공개 제거) |
| `rkdis.py EXE VA:N ..`, `scan.py`, `bytesref.py EXE ADDR`, `xref.py EXE ADDR`, `immscan.py` | 정적 분석 (capstone 역어셈블, 주소 참조·호출 찾기) |
| `wgx_extract.py EXE OUT`, `wgdis.py` | 태조왕건 런처 exe 에서 WGReplay.dll 꺼내기·분석 (`docs/notes/wanggun-replay-comparison.md`) |

## 지금까지 알아낸 것
`docs/HANDOFF.md` 의 "게임 화면 리플레이" 절과 `docs/notes/replay-*.md` 참고.
