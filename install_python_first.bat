@echo off
chcp 65001 > nul
setlocal EnableExtensions

echo Checking Python...
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version
    echo Python launcher is already available.
    pause
    exit /b 0
)

where python >nul 2>&1
if not errorlevel 1 (
    python --version
    echo Python is already available.
    pause
    exit /b 0
)

where winget >nul 2>&1
if errorlevel 1 (
    echo winget was not found.
    echo Install Python 3.12 from https://www.python.org/downloads/windows/
    echo During installation, check "Add python.exe to PATH".
    pause
    exit /b 1
)

echo Python was not found.
choice /M "Install Python 3.12 with winget now"
if errorlevel 2 (
    echo Canceled.
    pause
    exit /b 1
)

winget install --id Python.Python.3.12 -e --source winget
if errorlevel 1 (
    echo Python installation failed.
    pause
    exit /b 1
)

echo.
echo Python installation finished.
echo Close this window, open a new PowerShell or File Explorer window, then run install_first.bat.
pause
endlocal
