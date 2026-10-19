@echo off
chcp 65001 >nul
setlocal EnableExtensions

echo counsel-note diagnostic bundle
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_diagnostic_bundle.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Diagnostic bundle creation completed.
) else (
  echo Diagnostic bundle creation failed. Please capture this console screen.
)
pause
exit /b %EXIT_CODE%
