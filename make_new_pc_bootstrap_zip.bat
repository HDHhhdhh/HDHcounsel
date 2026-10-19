@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_new_pc_bootstrap_zip.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo 5A Connect Log new computer real-use install ZIP creation completed.
) else (
  echo 5A Connect Log new computer real-use install ZIP creation failed.
)
pause
exit /b %EXIT_CODE%
