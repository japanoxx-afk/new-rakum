# 선택 한도 12 → 24 (Rhakmu.exe 1.000d) — 구현 완료, 미커밋

## 분석
- 12칸 목록 4곳: 내 선택 0x80083E(89곳) / 드래그 임시 0x7668F8(30곳) / 플레이어별 0x7F793E+p*0x11E0(41곳) / 부대 0x106A6C0+p*0xD0+g*0x1A(17곳). 바로 뒤를 다른 변수가 써서 제자리 확장 불가.
- 선택 명령 0x4002 는 가변 길이(개수 byte). 수신 0x4407E0 은 개수 검사 없이 복사 → 패치 안 한 PC가 13기 이상 받으면 0x7F7958.. 덮어씀 (테스트로 확인).
- 정보 창 초상화 위치표 0x4FF5B0 + layout*0x30 = 12칸 → 0x4582B0(그리기), 0x454220(클릭 판정)만 12로 제한.
- 0x47C550(같이 이동 대형) 스택 배열 [ebp-0x18](12 word)/[ebp-0x24](12 byte) → [ebp-0x78]/[ebp-0x18] (프레임 0x80 안 빈 곳).

## 구현
- selection_patch.py: 새 섹션 .sel24 (RVA 0xC77000, raw 0x1000 = 클램프 스텁, virtual 0xD000), 322곳 수정. build_selection_patch.py 가 원본에서 표 생성 (--check).
- 부대: 플레이어당 10개 * 0x32. 정리 루프 8→10.
- hotkey_patch: CODE24 (build_hotkey_code.assemble(n=24)), 아래 섹션이 .sel24 면 자동 선택.
- minimap_patch.build(..., select24) / underlying 에서 strip.
- launcher: cfg select_24 (기본 켬), game_rules.json 'select_24', 접속 PC는 서버 PC 값을 따르고 키가 없으면(구버전 서버) 12.
- test_selection_patch.py 10개 통과 (부대 저장/불러오기 20기+전송 패킷, 수신 22기, 초상화 제외, 드래그 확정 24, 대형 20기, 패널 12 제한, '.' 24기).

## 기존 환경 문제 (변경과 무관)
- test_panel_guard/test_peer_address/test_auto_game_launch: 설치된(이미 패치된) Program Files exe 사용.
- test_minimap_release/test_viewport_patch/test_crash_guards: research/runtime 파일 없음.
- test_launch_pipeline.test_multiplayer_...: HEAD 에서도 messagebox 로 멈춤.

## 남은 것
- 버전(v0.9045?) 결정, 실제 게임에서 1:1 대전 동기화 확인.
