@echo off
cd /d "%~dp0"
echo Stopping existing RhakMu dummy server processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*Start-RhakMuDummyServer.ps1*' -or $_.CommandLine -like '*Start-RhakMuStableServer.ps1*') -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Starting RhakMu dummy server with the stable multiplayer profile...
echo Profile: host identity, original start relay plus delayed stage8, member list broadcast
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Start-RhakMuDummyServer.ps1" -AutoReply none -RoomJoinIdentityMode host -GameStartSyncMode original-plus-delayed-stage8 -DelayedStartStage8Ms 12000 -ChannelUserListReplyMode members
pause
