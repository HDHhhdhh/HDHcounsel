@echo off
chcp 65001 > nul
setlocal EnableExtensions

cd /d "%~dp0"
set "PATH=%CD%\tools\ffmpeg\bin;%APPDATA%\npm;C:\Program Files\nodejs;%PATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "requirements.txt" (
    echo requirements.txt was not found. Creating a minimal requirements.txt.
    > requirements.txt echo streamlit
    >> requirements.txt echo faster-whisper
    >> requirements.txt echo pyperclip
    >> requirements.txt echo send2trash
    >> requirements.txt echo requests
)

call :FindPython
if errorlevel 1 (
    echo.
    echo Python was not found.
    echo Run install_python_first.bat first, then run this file again.
    echo If Python is already installed, close this window and restart PowerShell or Windows.
    if not "%COUNSEL_NOTE_NO_PAUSE%"=="1" pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if errorlevel 1 (
        for /f %%i in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
        echo Existing .venv is broken. Renaming it to .venv_broken_%TS%.
        ren ".venv" ".venv_broken_%TS%"
        if errorlevel 1 (
            echo Failed to rename the broken .venv folder.
            echo Close apps using this folder and try again.
            if not "%COUNSEL_NOTE_NO_PAUSE%"=="1" pause
            exit /b 1
        )
    ) else (
        echo Existing .venv looks usable.
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv.
        echo Check Python installation, then run this file again.
        if not "%COUNSEL_NOTE_NO_PAUSE%"=="1" pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate .venv.
    if not "%COUNSEL_NOTE_NO_PAUSE%"=="1" pause
    exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    if not "%COUNSEL_NOTE_NO_PAUSE%"=="1" pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.txt.
    if not "%COUNSEL_NOTE_NO_PAUSE%"=="1" pause
    exit /b 1
)

python -c "import streamlit, faster_whisper, pyperclip, requests, send2trash; print('Required Python packages: OK')"
if errorlevel 1 (
    echo Package import check failed.
    if not "%COUNSEL_NOTE_NO_PAUSE%"=="1" pause
    exit /b 1
)

echo.
echo Install finished.
echo Run run_app.bat to start the app.
if not "%COUNSEL_NOTE_NO_PAUSE%"=="1" pause
endlocal
exit /b 0

:FindPython
set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD exit /b 1
echo Python command: %PYTHON_CMD%
exit /b 0
