@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\publish_sebin_update.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Sebin update publish completed.
) else (
  echo Sebin update publish failed.
)
pause
exit /b %EXIT_CODE%
