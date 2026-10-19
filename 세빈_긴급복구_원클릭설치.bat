@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PAYLOAD=%SCRIPT_DIR%payload"
set "INSTALL_SCRIPT=%PAYLOAD%\scripts\sebin_emergency_oneclick_install.ps1"

echo counsel-note Sebin emergency oneclick restore
echo.

if not exist "%INSTALL_SCRIPT%" (
  echo Restore payload was not found.
  echo Please unzip the emergency package again, then run this file from the unzipped folder.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALL_SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Sebin emergency restore completed.
) else (
  echo Sebin emergency restore failed.
  echo If a diagnostic zip was created on the Desktop, please send that zip with a screenshot.
)
pause
exit /b %EXIT_CODE%
