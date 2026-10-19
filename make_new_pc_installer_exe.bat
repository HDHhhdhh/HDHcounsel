@echo off
chcp 65001 > nul
setlocal EnableExtensions

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_new_pc_installer_exe.ps1" %*
if errorlevel 1 (
  echo.
  echo 5A Connect Log installer EXE creation failed.
  pause
  exit /b 1
)

echo.
echo 5A Connect Log installer EXE creation completed.
pause
endlocal
