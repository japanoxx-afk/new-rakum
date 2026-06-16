@echo off
chcp 65001 > nul
setlocal

:: ── 설정 ──────────────────────────────────────────────
set GAME_HOST=rhakmugame.hangame.naver.com
set GAME_EXE=C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe
set SCRIPT_DIR=%~dp0
set SERVER_CFG=%SCRIPT_DIR%server.txt
set SERVER_EXE=%SCRIPT_DIR%RhakMuServer.exe
set PATCH_SCRIPT=%SCRIPT_DIR%Apply-RhakMuStable.ps1
set PATCH_DONE=%SCRIPT_DIR%.patched
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

:: 최초 1회 패치 적용
if not exist "%PATCH_DONE%" (
    if exist "%PATCH_SCRIPT%" (
        echo [최초 설정] 게임 패치를 적용합니다. 잠시 기다려주세요...
        powershell -ExecutionPolicy Bypass -File "%PATCH_SCRIPT%" -GameDir "C:\Program Files (x86)\TriggerSoft\RhakMu"
        if %errorlevel% equ 0 (
            echo. > "%PATCH_DONE%"
            echo [OK] 패치 완료
        ) else (
            echo [경고] 패치 중 오류가 발생했습니다. 계속 진행합니다.
        )
    )
)

:: hosts 파일 업데이트
powershell -Command "(Get-Content '%HOSTS%') | Where-Object { $_ -notmatch '%GAME_HOST%' } | Set-Content '%HOSTS%'"
echo %SERVER_IP%  %GAME_HOST% >> "%HOSTS%"
echo [OK] 서버 설정 완료: %SERVER_IP%

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
