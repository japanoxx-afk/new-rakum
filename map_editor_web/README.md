# 라크무 웹 맵 에디터

런처 v0.9034 부터 **맵 에디터** 탭에 내장된다. 런처가 `127.0.0.1:47231` 에 로컬 서버를 띄우고
브라우저로 에디터를 연다. 게임 폴더의 `Data\Maps` 를 바로 열고 저장한다 (저장 시 `.bak` 백업).

## 폴더
| 경로 | 내용 |
|---|---|
| `editor/RhakMuMapEditor.html` | 빌드된 단일 파일 에디터 |
| `editor/tiles/*.js` | 타일셋별 지형 타일 아틀라스, `*_OBJ.js` 는 오브젝트·언덕 입구 스프라이트 |
| `editor/server.ps1`, `맵에디터 실행.bat` | 런처 없이 쓸 때: `editor` 폴더를 게임 폴더 안 `MapEditor` 로 복사 후 bat 실행 |
| `src/` | 에디터 소스 (`core.js` 맵 포맷·지형, `app.js` UI, `index.html`). `python map_editor_web/src/build.py` 로 빌드 |
| `mod/flip_ramp_tiles.tar.xz` | 상하대칭 언덕 입구 타일 모드 (`Data\tile\*.jtl`, `*_Bridge.brg`, 4개 맵 속성) |
| `tools/` | 모드 생성 스크립트 (`flipmod.py`: 뒤집은 타일·BRG 항목 추가, `ramp9/`: 입구 그림 다듬기) |

## 상하대칭 언덕 입구 모드
- 게임은 언덕 입구를 BRG 표에 따라 맵 타일을 바꿔 끼워 그린다 (`0x40bdd0`, 타일 = BRG base + piece).
- `Data\tile` 의 개별 파일이 `Data000.FDB` 보다 우선하므로 원본은 그대로 두고 파일만 추가한다.
- BRG 항목 8–11 = 2–5 를 상하대칭한 입구. 타일 수(JTL u16@16)는 파일에서 읽으므로 실행 파일 수정 없음.
- 이 입구를 쓴 맵은 함께 하는 모든 PC 에 모드가 있어야 한다. 런처에서 설치/제거 가능.
- 통행 불가 칸(BRG 셀 byte 3)은 새 기둥 6개 위치로 옮겼다 (`tools/ramp9/blockfix.py`). 계단 통로는 열려 있다.

## 테스트
`python -m unittest test_map_editor_web`
- `tools/` 스크립트는 작업 당시 경로(`/home/claude/re`) 기준이라, 다시 돌릴 때는 원본 JTL/BRG/S16 경로를 맞춰야 한다.
- exe 는 `.github/workflows/build-launcher.yml` 이 Windows 에서 빌드해 브랜치에 커밋하고 `version.json` 을 갱신한다.
