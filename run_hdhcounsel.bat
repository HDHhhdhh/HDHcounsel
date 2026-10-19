@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Install HDHcounsel using README.md first.
  exit /b 1
)
".venv\Scripts\python.exe" -I -m hdhcounsel.cli ui
