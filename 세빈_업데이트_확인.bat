@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"
echo counsel-note Sebin update check
echo Please close the counsel-note app and browser before updating.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sebin_check_and_apply_update.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Sebin update check completed.
) else (
  echo Sebin update check failed.
  echo If a diagnostic zip was created on the Desktop, please send it with a screenshot.
)
pause
exit /b %EXIT_CODE%
