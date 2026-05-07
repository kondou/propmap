#!/bin/bash
# regenerate_all.sh
# QSOペアCSV・RBNペアCSV・JSONを全コンテスト全年で再生成する
# iaru 2025 / cqww_cw 2025 は完了済みのためスキップ
#
# 使い方:
#   cd ~/heatmap/contest_logs   # step*.py と同じディレクトリ
#   bash regenerate_all.sh [--dry-run]
#
# オプション:
#   --dry-run   実際には実行せず対象の一覧を表示するだけ

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  echo "[dry-run モード: コマンドを表示するだけ]"
fi

ok=0; fail=0; skip=0

run() {
  echo ">>> $*"
  if [[ $DRY_RUN -eq 1 ]]; then
    return 0
  fi
  if "$@"; then
    ok=$((ok+1))
  else
    echo "!!! エラー: $*" >&2
    fail=$((fail+1))
  fi
}

# ------------------------------------------------------------
# QSO: step4_crosscheck → step5_aggregate
# ------------------------------------------------------------
echo "========================================"
echo " QSO パイプライン (step4 → step5)"
echo "========================================"

# iaru: 2018〜2025
for year in $(seq 2018 2025); do
  echo "--- iaru $year ---"
  run python3 "$SCRIPT_DIR/step4_crosscheck.py" --contest iaru --year $year --max-call-dist 2 --band-fix-window 15 --annotate-logs
  run python3 "$SCRIPT_DIR/step5_aggregate.py"  --contest iaru --year $year
done

# cqww_cw: 2005〜2025
for year in $(seq 2005 2025); do
  echo "--- cqww_cw $year ---"
  run python3 "$SCRIPT_DIR/step4_crosscheck.py" --contest cqww_cw --year $year --max-call-dist 2 --band-fix-window 15 --annotate-logs
  run python3 "$SCRIPT_DIR/step5_aggregate.py"  --contest cqww_cw --year $year
done

# cqww_ssb: 2005〜2025
for year in $(seq 2005 2025); do
  echo "--- cqww_ssb $year ---"
  run python3 "$SCRIPT_DIR/step4_crosscheck.py" --contest cqww_ssb --year $year --max-call-dist 2 --band-fix-window 15 --annotate-logs
  run python3 "$SCRIPT_DIR/step5_aggregate.py"  --contest cqww_ssb --year $year
done

# cqwpx_cw: 2008〜2025
for year in $(seq 2008 2025); do
  echo "--- cqwpx_cw $year ---"
  run python3 "$SCRIPT_DIR/step4_crosscheck.py" --contest cqwpx_cw --year $year --max-call-dist 2 --band-fix-window 15 --annotate-logs
  run python3 "$SCRIPT_DIR/step5_aggregate.py"  --contest cqwpx_cw --year $year
done

# cqwpx_ssb: 2008〜2025
for year in $(seq 2008 2025); do
  echo "--- cqwpx_ssb $year ---"
  run python3 "$SCRIPT_DIR/step4_crosscheck.py" --contest cqwpx_ssb --year $year --max-call-dist 2 --band-fix-window 15 --annotate-logs
  run python3 "$SCRIPT_DIR/step5_aggregate.py"  --contest cqwpx_ssb --year $year
done

# ------------------------------------------------------------
# RBN: step4_rbn → step5_rbn  (has_rbn=True のみ)
# ------------------------------------------------------------
echo "========================================"
echo " RBN パイプライン (step4_rbn → step5_rbn)"
echo "========================================"

# iaru RBN: 2018〜2024 (2025は完了済み)
for year in 2018 2019 2020 2021 2022 2023 2024; do
  echo "--- iaru RBN $year ---"
  run python3 "$SCRIPT_DIR/step4_rbn.py" --contest iaru --year $year
  run python3 "$SCRIPT_DIR/step5_rbn.py" --contest iaru --year $year
done

# cqww_cw RBN: 2005〜2024 (2025は完了済み)
for year in $(seq 2005 2024); do
  echo "--- cqww_cw RBN $year ---"
  run python3 "$SCRIPT_DIR/step4_rbn.py" --contest cqww_cw --year $year
  run python3 "$SCRIPT_DIR/step5_rbn.py" --contest cqww_cw --year $year
done

# cqwpx_cw RBN: 2008〜2025
for year in $(seq 2008 2025); do
  echo "--- cqwpx_cw RBN $year ---"
  run python3 "$SCRIPT_DIR/step4_rbn.py" --contest cqwpx_cw --year $year
  run python3 "$SCRIPT_DIR/step5_rbn.py" --contest cqwpx_cw --year $year
done

# ------------------------------------------------------------
echo "========================================"
if [[ $DRY_RUN -eq 1 ]]; then
  echo " dry-run 完了"
else
  echo " 完了: 成功=${ok} 失敗=${fail} スキップ=${skip}"
fi
echo "========================================"
