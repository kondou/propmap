#!/bin/bash
# このファイルをダブルクリックするとサーバーが起動してブラウザが開きます
cd "$(dirname "$0")"
PORT=8765

# 実行に使う Python を解決（開発環境が無くても動くようにする。詳細は find_python.sh）
source ./find_python.sh
if [ -z "$PYTHON" ]; then
  echo "Python が見つからないため起動できません。上記の案内に従って導入後、再度実行してください。"
  read -r -p "Enterで終了します..." _
  exit 1
fi

lsof -ti:$PORT | xargs kill -9 2>/dev/null
sleep 0.3
# 静的配信 + データ更新API（propmap_server.py が無い環境では従来の http.server に自動フォールバック）
if [ -f propmap_server.py ]; then
  $PYTHON propmap_server.py --port $PORT &
else
  $PYTHON -m http.server $PORT &
fi
SERVER_PID=$!
sleep 0.8
open "http://localhost:$PORT/heatmap.html"
echo "Server running at http://localhost:$PORT  (python: $PYTHON)"
echo "Close this window to stop."
trap "kill $SERVER_PID 2>/dev/null" INT TERM EXIT
wait $SERVER_PID
