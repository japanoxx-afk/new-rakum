@echo off
chcp 437 > nul
setlocal

:: ── Config ────────────────────────────────────────────
set GAME_HOST=rhakmugame.hangame.naver.com
set GAME_EXE=C:\Program Files (x86)\TriggerSoft\RhakMu\Launcher.exe
set SCRIPT_DIR=%~dp0
set SERVER_CFG=%SCRIPT_DIR%server.txt
set SERVER_EXE=%SCRIPT_DIR%RhakMuServer.exe
set PATCH_SCRIPT=%SCRIPT_DIR%Apply-RhakMuStable.ps1
set PATCH_DONE=%SCRIPT_DIR%.patched
set HOSTS=%SystemRoot%\System32\drivers\etc\hosts
:: ──────────────────────────────────────────────────────

:: Check administrator rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Read server IP from server.txt (default: 127.0.0.1)
set SERVER_IP=127.0.0.1
if exist "%SERVER_CFG%" (
    set /p SERVER_IP=<"%SERVER_CFG%"
)
set SERVER_IP=%SERVER_IP: =%

echo.
echo  RhakMu Launcher
echo  Server: %SERVER_IP%
echo.

:: Apply patches on first run only
if not exist "%PATCH_DONE%" (
    if exist "%PATCH_SCRIPT%" (
        echo [Setup] Applying game patches, please wait...
        powershell -ExecutionPolicy Bypass -File "%PATCH_SCRIPT%" -GameDir "C:\Program Files (x86)\TriggerSoft\RhakMu"
        if %errorlevel% equ 0 (
            echo. > "%PATCH_DONE%"
            echo [OK] Patches applied
        ) else (
            echo [Warning] Patch error, continuing anyway
        )
    )
)

:: Update hosts file
powershell -Command "(Get-Content '%HOSTS%') | Where-Object { $_ -notmatch '%GAME_HOST%' } | Set-Content '%HOSTS%'"
echo %SERVER_IP%  %GAME_HOST%>> "%HOSTS%"
echo [OK] Hosts: %SERVER_IP% ^> %GAME_HOST%

:: Start local server only if server IP is 127.0.0.1
if "%SERVER_IP%"=="127.0.0.1" (
    tasklist /fi "imagename eq RhakMuServer.exe" 2>nul | find /i "RhakMuServer.exe" >nul
    if errorlevel 1 (
        if exist "%SERVER_EXE%" (
            start "" /B "%SERVER_EXE%"
            echo [OK] Local server started
            timeout /t 2 /nobreak > nul
        ) else (
            echo [Error] RhakMuServer.exe not found
            pause
            exit /b 1
        )
    ) else (
        echo [OK] Server already running
    )
)

:: Launch game
if not exist "%GAME_EXE%" (
    echo [Error] Game not found: %GAME_EXE%
    pause
    exit /b 1
)

echo [OK] Launching game...
start "" "%GAME_EXE%"
exit /b 0
