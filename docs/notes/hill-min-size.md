# 언덕 브러시 최소 크기 (웹 에디터)

- 원인: map_editor_web/src/app.js `minSize()` 가 브러시 5/7/8(언덕·높은 언덕·고지대 물)을 크기 3 이상으로 강제. v0.9034 최초 커밋부터 있었고 이후 줄인 커밋 없음.
- 수정(미커밋, 브랜치 launcher-v0.9044-hotkeys 작업 트리): minSize 제거 → 슬라이더 1부터 그대로 적용. editor/RhakMuMapEditor.html 은 build.py 로 재생성.
- 검증: 브라우저에서 실제 core.js로 크기 1/2/3 × 원/사각, 언덕 위 높은 언덕, 고지대 물 테스트 → 잘못된 타일 0, 대각 타일 0, 3종 브러시 타일 0, serialize/parse 왕복 동일.
- 순정 맵에도 꼭짓점 1개짜리 언덕 꼭대기(Nightmare, Rival, X-ice)와 9꼭짓점(3x3) 고지대(North and South)가 있음 → 크기 1 언덕(꼭대기 1 + 절벽 고리 8 = 3x3) 은 순정 범위 안.
- 구조적 한계: 언덕은 꼭대기(5) 주변에 절벽 띠(4) 한 겹이 반드시 생기므로 크기 1도 실제 고지대는 3x3 꼭짓점 = 타일 2x2 정도.
- 테스트: unittest 18개 중 17 통과, 1개는 PIL 미설치로 map_editor.py import 실패(환경 문제, 변경과 무관).
