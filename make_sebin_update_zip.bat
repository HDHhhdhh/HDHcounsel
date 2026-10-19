@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_sebin_update_zip.ps1"
if errorlevel 1 (
  echo.
  echo sebin update zip creation failed.
  pause
  exit /b 1
)
echo.
echo sebin update zip creation completed.
pause
exit /b 0
