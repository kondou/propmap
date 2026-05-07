@echo off
cd /d "%~dp0"

REM 既存のサーバーを停止
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765 " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM サーバーをバックグラウンドで起動
start /b python -m http.server 8765
timeout /t 1 /nobreak >nul

REM ブラウザを開く
start http://localhost:8765/heatmap.html

echo.
echo  PropMap サーバーが起動しました
echo  http://localhost:8765/heatmap.html
echo.
echo  このウィンドウを閉じるとサーバーが停止します。
echo.
pause >nul
