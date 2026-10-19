@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ========================================
echo Codex CLI installation check
echo ========================================
echo.

codex --version > nul 2>&1
if %errorlevel%==0 (
    echo Codex CLI is already installed.
    codex --version
    echo.
    echo Next: run codex login
    pause
    exit /b 0
)

echo Checking Node.js...
node --version > nul 2>&1
if not %errorlevel%==0 (
    echo Node.js is not installed.
    echo Node.js LTS installation will start.
    echo Use default options in the installer.
    echo.
    pause

    winget install -e --id OpenJS.NodeJS.LTS

    echo.
    echo After Node.js installation, close all black command windows.
    echo Then run install_codex_first.bat again.
    echo.
    pause
    exit /b 1
)

echo Node.js found.
node --version

echo.
echo Installing Codex CLI...
npm install -g @openai/codex

echo.
echo Checking Codex CLI:
codex --version

echo.
echo Next step:
echo Run this command in a new PowerShell window:
echo codex login
echo.
pause
