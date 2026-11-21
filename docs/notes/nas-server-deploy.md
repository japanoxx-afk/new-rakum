# NAS server deploy — hand-over note

- Worktree: %USERPROFILE%\Documents\claud\rhakmu-nas, branch `nas-server-deploy` (from origin/main fbc8c2a), commits 55db87c, 8517069. Not pushed.
- Folder nas-server/: compose.yaml (python:3.12-slim, no build, bridge, external volume game_servers_data), app/nas_entry.py (wraps unchanged server.py), Prepare-NasUpload.ps1, test_nas_entry.py (3 pass), ports.txt, README.txt, HANDOFF.txt.
- Default ports 30010/30011/30012 (side by side with rakmu-test). Replacing rakmu-test (30000-30002) = user decision, not done.
- Nothing deployed. No passwords written anywhere.
- Key finding: game exe hardcodes lobby TCP 11223, launcher hardcodes HTTP 11225; router forwards only 30000-30999 -> needs owner port forward or a launcher local TCP relay. Also server hands out observed IPs to peers -> over internet these are public IPs, not Radmin IPs, so P2P match start likely fails until a "VPN address announce" server+launcher change.

(2026-11-22 확인: 커밋 55db87c·8517069 는 main 에 들어가 있고, 브랜치 nas-server-deploy 도 GitHub 에 있음.)
