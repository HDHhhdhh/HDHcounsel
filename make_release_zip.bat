@echo off
chcp 65001 > nul
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_release_zip.ps1"
set "RELEASE_EXIT_CODE=%ERRORLEVEL%"

echo.
pause
exit /b %RELEASE_EXIT_CODE%
