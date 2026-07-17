@echo off
cd /d "%~dp0"

REM 実行に使う Python を解決（開発環境が無くても動くようにする。詳細は find_python.bat）
call "%~dp0find_python.bat"
if not defined PYTHON (
    echo Python が見つからないため起動できません。案内に従って導入後、再度実行してください。
    pause >nul
    exit /b 1
)

REM 既存のサーバーを停止
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765 " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM サーバーをバックグラウンドで起動
REM 静的配信 + データ更新API（propmap_server.py が無ければ従来の http.server）
if exist propmap_server.py (
    start /b %PYTHON% propmap_server.py --port 8765
) else (
    start /b %PYTHON% -m http.server 8765
)
timeout /t 1 /nobreak >nul

REM ブラウザを開く
start http://localhost:8765/heatmap.html

echo.
echo  PropMap サーバーが起動しました  (python: %PYTHON%)
echo  http://localhost:8765/heatmap.html
echo  データ更新: http://localhost:8765/update.html
echo.
echo  このウィンドウを閉じるとサーバーが停止します。
echo.
pause >nul
