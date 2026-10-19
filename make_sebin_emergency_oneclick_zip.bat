@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_sebin_emergency_oneclick_zip.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Sebin emergency oneclick zip creation completed.
) else (
  echo Sebin emergency oneclick zip creation failed.
)
pause
exit /b %EXIT_CODE%
