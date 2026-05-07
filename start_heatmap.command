#!/bin/bash
# このファイルをダブルクリックするとサーバーが起動してブラウザが開きます
cd "$(dirname "$0")"
PORT=8765
lsof -ti:$PORT | xargs kill -9 2>/dev/null
sleep 0.3
python3 -m http.server $PORT &
SERVER_PID=$!
sleep 0.8
open "http://localhost:$PORT/heatmap.html"
echo "Server running at http://localhost:$PORT"
echo "Close this window to stop."
trap "kill $SERVER_PID 2>/dev/null" INT TERM EXIT
wait $SERVER_PID
