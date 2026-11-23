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
| `tools/` | 모드 생성 스크립트 (`flipmod.py`: 뒤집은 타일·BRG 항목 추가, `ramp9/`: 입구 그림 다듬기), `obj_offsets.py`: 장식물·자원 스프라이트 오프셋 재계산 |

## 좌표 (자원·장식물·시작 위치)
- 게임은 지형 레코드 (col,row) 로 칸 X..X+7, Y..Y+3 을 덮는다 (X = col*8 + (row&1)*4, Y = row*2, `0x40b6f0`). 다이아몬드 중심은 칸 (X+4, Y+2).
- 오브젝트·시작 위치는 칸 (x,y) 의 픽셀 (x*32, y*32) 에 놓이고 (`0x439e60`), 그림은 BLD dx + S16 프레임 left/top 만큼 옮겨 그린다.
- 에디터는 지형 다이아몬드 중심을 월드 (X*32, Y*32) 에 그리므로 오브젝트 칸 (x,y) 은 월드 (x*32-128, y*32-64) 에 그린다 (`core.js` `cellX/cellY/worldCell`).
  파일의 좌표 값은 바꾸지 않는다. 언덕 입구·다리(kind 3)는 원본 맵에서 배운 템플릿 기준이라 따로 옮기지 않는다.

## 정사각형(평면) 보기 (v0.9094, 기본)
- 도구줄 **정사각형 보기**: 타일 모서리 방향 (p, q) 를 화면 가로·세로로 돌려 그린다. `x' = wx/2 + wy`, `y' = wy − wx/2`
  (256×128 마름모 타일 → 128×128 정사각형). 끄면 게임 화면과 같은 마름모 보기. 고른 값은 브라우저에 저장(`rkm-flat-view`).
- 맵 자료·월드 좌표는 그대로이고 그릴 때(`render` 의 `setTransform`)와 마우스 위치(`s2w`/`w2s`), 미니맵, 붓 미리보기·팔레트만 바뀐다.
- 타일·격자·칸 표시·언덕 입구/다리는 변환해서 눕혀 그리고, 자원·장식물·시작 위치 표식·글자는 `upright()` 로 제자리에 똑바로 그린다
  (고를 때는 `uprightPoint()`). 게임 맵의 가장자리(칸 직사각형)는 이 보기에서 기울어진 직사각형으로 보인다.
- 찍기·스포이드 N×N 블록은 원래 (p, q) 칸이라 이 보기에서 화면에 똑바로 놓인 정사각형이 된다.

## 타일 직접 배치 (블록·즐겨찾기)
- 타일 찍기·스포이드 크기 1×1~8×8 (`[` `]`). 블록은 타일 모서리를 따라 놓인 마름모: 칸 (p+i, q+j),
  타일 (x,y) ↔ u = 2x+(y&1), v = y, p = (u+v)/2, q = (v−u)/2. 스포이드는 [타일, a, b, c] 를 그대로 복사한다.
- 즐겨찾기 템플릿은 `GET|PUT /api/templates` 로 `%LOCALAPPDATA%\RhakMu\map_editor_templates.json` 에 저장
  (런처 없이 `server.ps1` 로 열면 브라우저 localStorage 에만 저장).

## 상하대칭 언덕 입구 모드
- 게임은 언덕 입구를 BRG 표에 따라 맵 타일을 바꿔 끼워 그린다 (`0x40bdd0`, 타일 = BRG base + piece).
- `Data\tile` 의 개별 파일이 `Data000.FDB` 보다 우선하므로 원본은 그대로 두고 파일만 추가한다.
- BRG 항목 8–11 = 2–5 를 상하대칭한 입구. 타일 수(JTL u16@16)는 파일에서 읽으므로 실행 파일 수정 없음.
- 이 입구를 쓴 맵은 함께 하는 모든 PC 에 모드가 있어야 한다. 런처 v0.9037 부터 실행 시 자동 설치·갱신(설정 `tile_mod_auto`, 기본 켜짐).
- 통행 불가 칸(BRG 셀 byte 3)은 새 기둥 6개 위치로 옮겼다 (`tools/ramp9/blockfix.py`). 계단 통로는 열려 있다.

## 테스트
`python -m unittest test_map_editor_web`
- `tools/` 스크립트는 작업 당시 경로(`/home/claude/re`) 기준이라, 다시 돌릴 때는 원본 JTL/BRG/S16 경로를 맞춰야 한다.
- exe 는 `.github/workflows/build-launcher.yml` 이 Windows 에서 빌드해 브랜치에 커밋하고 `version.json` 을 갱신한다.
