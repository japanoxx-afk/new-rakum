@echo off
setlocal
cd /d "%~dp0"

set "REPO_URL=https://github.com/japanoxx-afk/rakmu.git"
set "OUT_DIR=%CD%\downloaded_analysis_logs"
set "WORK_REPO=%OUT_DIR%\repo"

set "GIT_EXE=git"
where git >nul 2>nul
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\GitHubDesktop\app-3.5.12\resources\app\git\cmd\git.exe" (
    set "GIT_EXE=%LOCALAPPDATA%\GitHubDesktop\app-3.5.12\resources\app\git\cmd\git.exe"
  ) else if exist "%ProgramFiles%\Git\cmd\git.exe" (
    set "GIT_EXE=%ProgramFiles%\Git\cmd\git.exe"
  ) else (
    echo Git executable was not found.
    echo Install Git or GitHub Desktop, then run this file again.
    pause
    exit /b 1
  )
)

mkdir "%OUT_DIR%" >nul 2>nul

if exist ".git" (
  echo Pulling latest logs in current repository...
  "%GIT_EXE%" pull origin main
  if errorlevel 1 goto :error
  if exist "logs" (
    robocopy "logs" "%OUT_DIR%\logs" /E >nul
    if errorlevel 8 goto :error
  )
) else (
  if exist "%WORK_REPO%\.git" (
    echo Pulling latest logs in downloaded repository...
    "%GIT_EXE%" -C "%WORK_REPO%" pull origin main
    if errorlevel 1 goto :error
  ) else (
    echo Cloning analysis repository...
    "%GIT_EXE%" clone "%REPO_URL%" "%WORK_REPO%"
    if errorlevel 1 goto :error
  )
  if exist "%WORK_REPO%\logs" (
    robocopy "%WORK_REPO%\logs" "%OUT_DIR%\logs" /E >nul
    if errorlevel 8 goto :error
  )
)

echo.
echo Analysis logs are ready:
echo %OUT_DIR%\logs
pause
exit /b 0

:error
echo.
echo Failed to download analysis logs.
pause
exit /b 1
