#!/bin/bash
# verify.sh - PropMap 変更後の一括検証（macOS / Linux / WSL2）
#
# 使い方:
#   cd ~/heatmap
#   bash verify.sh              # 標準検証（ネットワーク不使用、1分以内）
#   bash verify.sh --network    # 追加で check_new_logs --dry-run の実地確認（数十秒〜）
#
# 出力: 各項目の PASS/FAIL と、末尾の SUMMARY ブロック。
#       作業者（人間/AI）は SUMMARY を**原文のまま**報告すること。
#       FAIL が1つでもあれば exit 1。
#
# 本スクリプト自体を変更する場合は事前にユーザーの承認を得ること。

cd "$(dirname "$0")" || exit 1
NETWORK=0
[ "${1:-}" = "--network" ] && NETWORK=1

PASS=0; FAIL=0; SKIP=0; FAILED_LIST=""
TESTPORT=18799
TMPD="$(mktemp -d)"
SRV_PID=""
cleanup() { [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null; rm -rf "$TMPD"; }
trap cleanup EXIT INT TERM

ok()  { PASS=$((PASS+1)); echo "  PASS: $1"; }
ng()  { FAIL=$((FAIL+1)); FAILED_LIST="$FAILED_LIST
  - $1"; echo "  FAIL: $1"; [ -n "${2:-}" ] && echo "        detail: $2"; }
sk()  { SKIP=$((SKIP+1)); echo "  SKIP: $1"; [ -n "${2:-}" ] && echo "        reason: $2"; }

echo "==== PropMap verify ($(date '+%Y-%m-%d %H:%M:%S')) ===="

# ---- R1: シェルスクリプト構文 -------------------------------------------------
if bash -n find_python.sh start_heatmap.command contest_logs/generate_all.sh verify.sh 2>"$TMPD/e"; then
  ok "R1 sh syntax (find_python.sh / start_heatmap.command / generate_all.sh / verify.sh)"
else
  ng "R1 sh syntax" "$(cat "$TMPD/e")"
fi

# ---- R2: Python 解決（通常） --------------------------------------------------
PYTHON=""
source ./find_python.sh
if [ -n "$PYTHON" ] && $PYTHON -c 'import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
  ok "R2 python resolved: [$PYTHON]"
else
  ng "R2 python resolution" "PYTHON=[$PYTHON]"
  echo "以降の検証は Python が必要なため中断します。"
  echo ""
  echo "==== SUMMARY ===="
  echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP$FAILED_LIST"
  exit 1
fi

# ---- R3: 解決器の分岐（不正指定フォールバック / 不在時案内） --------------------
out="$(bash -c 'PROPMAP_PYTHON=/bin/false source ./find_python.sh 2>&1; echo "[$PYTHON]"')"
if echo "$out" | grep -q "実行できません" && echo "$out" | grep -qv "^\[\]$"; then
  ok "R3a bad PROPMAP_PYTHON falls back with warning"
else
  ng "R3a bad PROPMAP_PYTHON fallback" "$out"
fi
# R3b は「Python 不在」を PATH 潰しで模擬するが、解決器は既知の場所を
# 絶対パスで探索するため、そこに Python/uv が実在する環境では不在状況を
# 再現できない（環境依存テスト）。実在する場合は SKIP とする（仕様）。
_r3b_bypass=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
         "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
  [ -x "$c" ] && _r3b_bypass="$c" && break
done
if [ -z "$_r3b_bypass" ] && [ "$(uname -s 2>/dev/null)" = "Darwin" ] \
   && xcode-select -p >/dev/null 2>&1 && [ -x /usr/bin/python3 ]; then
  _r3b_bypass="/usr/bin/python3 (CLT導入済み)"
fi
if [ -n "$_r3b_bypass" ]; then
  sk "R3b absent python guidance" "known location exists: $_r3b_bypass （不在状況を再現不能。仕様）"
else
  out="$(bash -c 'PATH=/nonexistent_pm source ./find_python.sh </dev/null 2>&1; echo "[${PYTHON:-EMPTY}]"')"
  if echo "$out" | grep -q "python.org" && echo "$out" | grep -q "\[EMPTY\]"; then
    ok "R3b absent python -> guidance + empty PYTHON"
  else
    ng "R3b absent python guidance" "$out"
  fi
fi

# ---- R4: set -u 互換（generate_all.sh dry-run） -------------------------------
( cd contest_logs && bash generate_all.sh --dry-run ) >"$TMPD/g" 2>&1
if ! grep -q "unbound variable" "$TMPD/g" && grep -q ">>>" "$TMPD/g"; then
  ok "R4 generate_all.sh --dry-run runs under set -u"
else
  ng "R4 generate_all.sh dry-run" "$(head -3 "$TMPD/g")"
fi

# ---- D1: Python 構文 -----------------------------------------------------------
if $PYTHON -m py_compile propmap_server.py contest_logs/*.py 2>"$TMPD/e"; then
  ok "D1 py_compile all python files"
else
  ng "D1 py_compile" "$(cat "$TMPD/e")"
fi

# ---- D2: contest_utils --list の妥当性 -----------------------------------------
$PYTHON contest_logs/contest_utils.py --list >"$TMPD/l" 2>&1
if [ "$(awk '{print $1}' "$TMPD/l" | sort -u | wc -l)" -eq 7 ] \
   && grep -q "^iaru .* 1$" "$TMPD/l" \
   && grep -q "^cqww_ssb .* 0$" "$TMPD/l" \
   && ! awk -v y="$(date +%Y)" '$2 > y {found=1} END {exit !found}' "$TMPD/l"; then
  ok "D2 contest_utils --list (7 contests, has_rbn flags, no future years)"
else
  ng "D2 contest_utils --list" "$(head -3 "$TMPD/l")"
fi

# ---- D3: pipeline_steps の契約（RBNあり12 / なし6、順序） ----------------------
if ( cd contest_logs && $PYTHON -c "
import check_new_logs as c
a = c.pipeline_steps('cqwpx_cw', 2099)
b = c.pipeline_steps('cqww_ssb', 2099)
assert (len(a), len(b)) == (12, 6), (len(a), len(b))
labels = [l.split()[0] for l, _ in a]
assert labels == ['step1','download_rbn','make_spotted_grids',
 'make_spotted_grids_approx','step4_crosscheck','step5_aggregate',
 'step4_crosscheck_approx','step5_aggregate_approx',
 'step4_rbn','step5_rbn','step4_rbn_approx','step5_rbn_approx'], labels
" 2>"$TMPD/e" ); then
  ok "D3 pipeline_steps contract (12/6, order = run_contest)"
else
  ng "D3 pipeline_steps contract" "$(cat "$TMPD/e")"
fi

# ---- D4: サーバー起動・静的配信・API・Hostガード --------------------------------
$PYTHON propmap_server.py --port $TESTPORT >"$TMPD/srv" 2>&1 &
SRV_PID=$!
sleep 1.2
d4_ok=1
for pth in /heatmap.html /update.html; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$TESTPORT$pth")"
  [ "$code" = "200" ] || { d4_ok=0; d4_detail="$pth -> $code"; }
done
code="$(curl -s "http://127.0.0.1:$TESTPORT/api/datasets")"
echo "$code" | grep -q '"iaru"' || { d4_ok=0; d4_detail="datasets: $code"; }
code="$(curl -s -H 'Host: evil.example.com' -o /dev/null -w '%{http_code}' "http://127.0.0.1:$TESTPORT/api/datasets")"
[ "$code" = "403" ] || { d4_ok=0; d4_detail="host-guard -> $code"; }
kill "$SRV_PID" 2>/dev/null; SRV_PID=""
if [ "$d4_ok" = "1" ]; then
  ok "D4 server: static 200 / datasets json / host-guard 403"
else
  ng "D4 server" "${d4_detail:-unknown} (server log: $(head -2 "$TMPD/srv"))"
fi

# ---- N1: (--network 時のみ) check_new_logs 実地ドライラン ------------------------
if [ "$NETWORK" = "1" ]; then
  if ( cd contest_logs && $PYTHON check_new_logs.py --dry-run ) >"$TMPD/n" 2>&1; then
    ok "N1 check_new_logs --dry-run (live network)"
    grep -E "公開済み|available|未公開|not published" "$TMPD/n" | sed 's/^/        /'
  else
    ng "N1 check_new_logs --dry-run" "$(tail -3 "$TMPD/n")"
  fi
fi

echo ""
echo "==== SUMMARY ===="
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP$FAILED_LIST"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
