@echo off
cd /d "%~dp0"

REM Resolve the Python to use (works with no dev environment installed;
REM see find_python.bat for details).
call "%~dp0find_python.bat"
if not defined PYTHON (
    echo Python was not found, so PropMap cannot start. Follow the guidance above to install it, then run this again.
    pause >nul
    exit /b 1
)

REM Stop any existing server
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765 " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo.
echo  Starting PropMap server  - python: %PYTHON%
echo  http://localhost:8765/heatmap.html
echo  Data update: http://localhost:8765/update.html
echo.
echo  Press Ctrl+C, or close this window, to stop the server.
echo.

REM Open the browser a couple seconds after the server starts, via a
REM short-lived hidden helper process. It exits on its own; there is
REM nothing to clean up when the server (below) stops.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:8765/heatmap.html'"

REM Run the server in the foreground (not backgrounded with start /b) so
REM Ctrl+C, or closing this window, stops it directly and cleanly. A
REM backgrounded server does not reliably receive Ctrl+C and can be left
REM running, keeping this console window open and unresponsive.
REM Static files + data-update API (falls back to http.server if
REM propmap_server.py is missing).
if exist propmap_server.py (
    %PYTHON% propmap_server.py --port 8765
) else (
    %PYTHON% -m http.server 8765
)
