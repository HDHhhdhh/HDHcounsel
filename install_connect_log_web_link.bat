@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\install_connect_log_protocol.ps1" -AppRoot "%CD%"
if errorlevel 1 (
    echo.
    echo Connect Log 실행 연결 설치에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo Connect Log 실행 연결이 설치되었습니다.
echo Chrome 확장 프로그램 폴더:
echo %CD%\browser_extension\connect_log_launcher
echo.
echo Chrome 확장 프로그램 화면에서 위 폴더를 압축해제된 확장 프로그램으로 한 번만 불러오세요.
start "" chrome://extensions
pause

endlocal
exit /b 0
