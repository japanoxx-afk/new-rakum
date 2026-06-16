@echo off
chcp 65001 > nul
setlocal

:: ── 설정 ──────────────────────────────────────────────
set GAME_HOST=rhakmugame.hangame.naver.com
set GAME_EXE=C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe
set SCRIPT_DIR=%~dp0
set SERVER_CFG=%SCRIPT_DIR%server.txt
set SERVER_EXE=%SCRIPT_DIR%RhakMuServer.exe
set HOSTS=%SystemRoot%\System32\drivers\etc\hosts
:: ──────────────────────────────────────────────────────

:: 관리자 권한 확인
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 관리자 권한으로 다시 실행합니다...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: server.txt 에서 서버 주소 읽기 (없으면 127.0.0.1)
set SERVER_IP=127.0.0.1
if exist "%SERVER_CFG%" (
    set /p SERVER_IP=<"%SERVER_CFG%"
)
set SERVER_IP=%SERVER_IP: =%

echo.
echo  ┌─────────────────────────────┐
echo  │   라크무 런처               │
echo  │   서버: %SERVER_IP%
echo  └─────────────────────────────┘
echo.

:: hosts 파일 업데이트 (기존 항목 제거 후 추가)
powershell -Command "(Get-Content '%HOSTS%') | Where-Object { $_ -notmatch '%GAME_HOST%' } | Set-Content '%HOSTS%'"
echo %SERVER_IP%  %GAME_HOST% >> "%HOSTS%"
echo [OK] hosts 파일 설정 완료: %SERVER_IP% → %GAME_HOST%

:: 로컬 서버 실행 (127.0.0.1 일 때만)
if "%SERVER_IP%"=="127.0.0.1" (
    tasklist /fi "imagename eq RhakMuServer.exe" 2>nul | find /i "RhakMuServer.exe" >nul
    if errorlevel 1 (
        if exist "%SERVER_EXE%" (
            start "" /B "%SERVER_EXE%"
            echo [OK] 로컬 서버 시작
            timeout /t 2 /nobreak > nul
        ) else (
            echo [오류] RhakMuServer.exe 를 찾을 수 없습니다.
            pause
            exit /b 1
        )
    ) else (
        echo [OK] 서버 이미 실행 중
    )
)

:: 게임 실행
if not exist "%GAME_EXE%" (
    echo [오류] 게임을 찾을 수 없습니다: %GAME_EXE%
    pause
    exit /b 1
)

echo [OK] 게임 실행 중...
start "" "%GAME_EXE%"
exit /b 0
