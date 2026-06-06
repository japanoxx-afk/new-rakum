@echo off
cd /d "%~dp0"
echo Stopping existing RhakMu dummy server processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*Start-RhakMuDummyServer.ps1*' -or $_.CommandLine -like '*Start-RhakMuStableServer.ps1*') -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Starting RhakMu dummy server with original-only start relay...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Start-RhakMuStableServer.ps1" -GameStartSyncMode original
pause
