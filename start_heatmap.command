#!/bin/bash
# Double-click this file to start the server and open the browser
cd "$(dirname "$0")"
PORT=8765

# ---- i18n -------------------------------------------------------------------
if [[ "${LANG:-}" == ja* ]] || [[ "${LC_ALL:-}" == ja* ]] || [[ "${LANGUAGE:-}" == ja* ]]; then
  _sh_L=ja
else
  _sh_L=en
fi
_sh_msg() { [[ "$_sh_L" == ja ]] && echo "$1" || echo "$2"; }
# -----------------------------------------------------------------------------

# Resolve the Python to use (works with no dev environment installed;
# see find_python.sh for details)
source ./find_python.sh
if [ -z "$PYTHON" ]; then
  echo "$(_sh_msg "Python が見つからないため起動できません。上記の案内に従って導入後、再度実行してください。" \
                  "Python was not found, so PropMap cannot start. Follow the guidance above to install it, then run this again.")"
  read -r -p "$(_sh_msg "Enterで終了します..." "Press Enter to exit...")" _
  exit 1
fi

lsof -ti:$PORT | xargs kill -9 2>/dev/null
sleep 0.3
# Static files + data-update API (falls back to the traditional
# http.server if propmap_server.py is missing)
if [ -f propmap_server.py ]; then
  $PYTHON propmap_server.py --port $PORT &
else
  $PYTHON -m http.server $PORT &
fi
SERVER_PID=$!
sleep 0.8
URL="http://localhost:$PORT/heatmap.html"
# open: macOS. wslview: WSL2 (opens the Windows-side default browser, if
# wslu is installed). xdg-open: typical Linux desktop. If none are
# available, just print the URL.
if command -v open >/dev/null 2>&1; then
  open "$URL"
elif command -v wslview >/dev/null 2>&1; then
  wslview "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1
else
  echo "$(_sh_msg "ブラウザを自動で開けませんでした。以下のURLを手動で開いてください:" \
                  "Could not open a browser automatically. Please open this URL manually:")"
fi
echo "$(_sh_msg "サーバーが起動しました: http://localhost:$PORT  (python: $PYTHON)" \
                "Server running at http://localhost:$PORT  (python: $PYTHON)")"
echo "$(_sh_msg "このウィンドウを閉じるとサーバーが停止します。" \
                "Close this window to stop the server.")"
unset -f _sh_msg 2>/dev/null
unset _sh_L 2>/dev/null
trap "kill $SERVER_PID 2>/dev/null" INT TERM EXIT
wait $SERVER_PID
