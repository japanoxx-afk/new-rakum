@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-RhakMuClientPatches.ps1" %*
echo.
pause
