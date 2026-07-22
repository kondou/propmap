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

REM Start the server in the background.
REM Static files + data-update API (falls back to http.server if
REM propmap_server.py is missing).
if exist propmap_server.py (
    start /b %PYTHON% propmap_server.py --port 8765
) else (
    start /b %PYTHON% -m http.server 8765
)
timeout /t 1 /nobreak >nul

REM Open the browser
start http://localhost:8765/heatmap.html

echo.
echo  PropMap server started  - python: %PYTHON%
echo  http://localhost:8765/heatmap.html
echo  Data update: http://localhost:8765/update.html
echo.
echo  Closing this window stops the server.
echo.
pause >nul
