@echo off
cd /d "%~dp0"
title Ledger-App

echo Step 1/2: Clean up old process...
powershell -Command "$p = netstat -ano | findstr '127.0.0.1:5000' | findstr 'LISTENING'; if ($p) { $portPid = $p.Trim().Split()[-1]; taskkill /F /PID $portPid >$null 2>&1 }"

echo Step 2/2: Starting app...

if "%1"=="--fg" goto :fg

:: 后台模式（默认）：双击即用，静默启动
start /B "" "D:\ProgramData\anaconda3\envs\app\python.exe" main.py
timeout /t 3 >nul
echo.
echo Done! Browser should open automatically.
echo If not, visit http://127.0.0.1:5000
echo.
pause
exit /b

:fg
:: 前台模式：日志实时显示，方便查错
echo Starting in foreground mode — real-time logs below.
echo Close this window or press Ctrl+C to stop.
echo.
"D:\ProgramData\anaconda3\envs\app\python.exe" main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo App exited with error code %ERRORLEVEL%.
    pause
)
