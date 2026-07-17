#!/bin/bash
# generate_all.sh
# fetch_cty から始めてゼロから全コンテスト・全年を一気通貫で構築する
#
# 使い方:
#   cd ~/heatmap/contest_logs
#   bash generate_all.sh [--dry-run] [--force]
#
# オプション:
#   --dry-run   実際には実行せず対象コマンドを表示するだけ
#   --force     既存ファイルを無視して全ステップを強制実行
#
# ログ: generate_all.log（追記モード）
#       各ステップ開始・終了日時を記録
#
# スキップ判定:
#   step1       raw/{contest}_{year}/ に .txt ファイルが存在すればスキップ
#   その他      出力ファイルが存在すればスキップ
#   download_rbn は内部でスキップを管理するため常に呼ぶ
#
# 注意: step4_crosscheck(_approx).py の曖昧検索はコンテスト規模によっては
#       数時間かかる。全コンテストを --force で実行すると長時間を要する。

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HEATMAP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$SCRIPT_DIR/generate_all.log"

# ---- Python 解決 -------------------------------------------------------------
# 開発環境の有無を意識せずに実行できるよう、find_python.sh で解決する。
# $PYTHON は複数語になり得るため、以降は必ずクォート無しの $PYTHON で使う。
source "$HEATMAP_DIR/find_python.sh"
if [ -z "${PYTHON:-}" ]; then
  echo "!!! Python が見つかりません。案内に従って導入後、再度実行してください。" >&2
  exit 1
fi

# ---- i18n -------------------------------------------------------------------
if [[ "${LANG:-}" == ja* ]] || [[ "${LC_ALL:-}" == ja* ]] || [[ "${LANGUAGE:-}" == ja* ]]; then
  _L=ja
else
  _L=en
fi
_msg() { [[ "$_L" == ja ]] && echo "$1" || echo "$2"; }
_err() { [[ "$_L" == ja ]] && echo "$1" >&2 || echo "$2" >&2; }
# -----------------------------------------------------------------------------

DRY_RUN=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1   ;;
  esac
done

if [[ $DRY_RUN -eq 1 ]]; then
  _msg "[dry-run モード: コマンドを表示するだけ]" "[dry-run mode: showing commands only]"
fi
if [[ $FORCE -eq 1 ]]; then
  _msg "[--force: 既存ファイルを無視して全ステップを強制実行]" \
       "[--force: re-run all steps regardless of existing files]"
fi

ok=0; fail=0; skip_count=0

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# should_skip: 0=skip, 1=run
#   ディレクトリなら *.txt が存在すればスキップ
#   ファイルなら存在すればスキップ
#   空文字なら常に実行
should_skip() {
  local out="${1:-}"
  [[ $FORCE -eq 1 ]] && return 1
  [[ -z "$out" ]]    && return 1
  if [[ -d "$out" ]]; then
    ls "$out"/*.txt &>/dev/null && return 0 || return 1
  fi
  [[ -e "$out" ]] || return 1
  # JSON ファイルで grids が空（実データなし）なら再実行
  if [[ "$out" == *.json ]] && grep -q '"grids":{}' "$out" 2>/dev/null; then
    return 1
  fi
  return 0
}

# run_step LABEL OUT_CHECK CMD [ARGS...]
run_step() {
  local label="$1"
  local out="${2:-}"
  shift 2

  if should_skip "$out"; then
    _msg "  [スキップ] $label" "  [SKIP] $label"
    { echo "$(ts)  [SKIP] $label"; } >> "$LOG_FILE"
    skip_count=$((skip_count+1))
    return 0
  fi

  _msg "  [実行] $label" "  [RUN] $label"
  { echo; echo "$(ts)  [START] $label"; printf '  CMD:'; printf ' %s' "$@"; echo; } >> "$LOG_FILE"
  echo "  >>> $*"

  if [[ $DRY_RUN -eq 1 ]]; then
    { echo "$(ts)  [DRYRUN] $label"; } >> "$LOG_FILE"
    return 0
  fi

  "$@" 2>&1 | tee -a "$LOG_FILE"
  local rc=${PIPESTATUS[0]}

  { echo "$(ts)  [END rc=$rc] $label"; } >> "$LOG_FILE"

  if [[ $rc -ne 0 ]]; then
    _err "  !!! エラー (rc=$rc): $label" "  !!! Error (rc=$rc): $label"
    fail=$((fail+1))
  else
    ok=$((ok+1))
  fi
}

# ---- ログ開始 ----------------------------------------------------------------
{
  echo
  if [[ $FORCE -eq 1 ]]; then
    echo "$(ts)  ======== generate_all.sh START --force ========"
  else
    echo "$(ts)  ======== generate_all.sh START ========"
  fi
} >> "$LOG_FILE"

# ---- fetch_cty (一度だけ実行; 内部でバージョンチェックとスキップを管理) ----
echo ""
_msg "==== cty.dat 取得 ====" "==== Fetch cty.dat ===="
{ echo; echo "$(ts)  ==== fetch_cty ===="; } >> "$LOG_FILE"

if [[ $DRY_RUN -eq 0 ]]; then
  if [[ $FORCE -eq 1 ]]; then
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_cty.py --force"
    $PYTHON "$HEATMAP_DIR/fetch_cty.py" --force 2>&1 | tee -a "$LOG_FILE"
  else
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_cty.py"
    $PYTHON "$HEATMAP_DIR/fetch_cty.py" 2>&1 | tee -a "$LOG_FILE"
  fi
  frc=${PIPESTATUS[0]}
  { echo "$(ts)  fetch_cty rc=$frc"; } >> "$LOG_FILE"
  if [[ $frc -ne 0 ]]; then
    _err "  !!! エラー: fetch_cty.py" "  !!! Error: fetch_cty.py"
    fail=$((fail+1))
  else
    ok=$((ok+1))
  fi
else
  if [[ $FORCE -eq 1 ]]; then
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_cty.py --force"
  else
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_cty.py"
  fi
fi

# ---- fetch_ssn (一度だけ実行; 内部でレコード数比較とスキップを管理) -----------
echo ""
_msg "==== SSN データ取得 ====" "==== Fetch SSN data ===="
{ echo; echo "$(ts)  ==== fetch_ssn ===="; } >> "$LOG_FILE"

if [[ $DRY_RUN -eq 0 ]]; then
  if [[ $FORCE -eq 1 ]]; then
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_ssn.py --force"
    $PYTHON "$HEATMAP_DIR/fetch_ssn.py" --force 2>&1 | tee -a "$LOG_FILE"
  else
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_ssn.py"
    $PYTHON "$HEATMAP_DIR/fetch_ssn.py" 2>&1 | tee -a "$LOG_FILE"
  fi
  frc=${PIPESTATUS[0]}
  { echo "$(ts)  fetch_ssn rc=$frc"; } >> "$LOG_FILE"
  if [[ $frc -ne 0 ]]; then
    _err "  !!! エラー: fetch_ssn.py" "  !!! Error: fetch_ssn.py"
    fail=$((fail+1))
  else
    ok=$((ok+1))
  fi
else
  if [[ $FORCE -eq 1 ]]; then
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_ssn.py --force"
  else
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_ssn.py"
  fi
fi

# ---- fetch_rbn_nodes (差分更新; --force 時は全再取得) -------------------------
echo ""
_msg "==== RBN ノードリスト更新 ====" "==== Update RBN node list ===="
{ echo; echo "$(ts)  ==== fetch_rbn_nodes ===="; } >> "$LOG_FILE"

if [[ $DRY_RUN -eq 0 ]]; then
  if [[ $FORCE -eq 1 ]]; then
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_rbn_nodes.py --force"
    $PYTHON "$HEATMAP_DIR/fetch_rbn_nodes.py" --force 2>&1 | tee -a "$LOG_FILE"
  else
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_rbn_nodes.py"
    $PYTHON "$HEATMAP_DIR/fetch_rbn_nodes.py" 2>&1 | tee -a "$LOG_FILE"
  fi
  frc=${PIPESTATUS[0]}
  { echo "$(ts)  fetch_rbn_nodes rc=$frc"; } >> "$LOG_FILE"
  if [[ $frc -ne 0 ]]; then
    _err "  !!! エラー: fetch_rbn_nodes.py" "  !!! Error: fetch_rbn_nodes.py"
    fail=$((fail+1))
  else
    ok=$((ok+1))
  fi
else
  if [[ $FORCE -eq 1 ]]; then
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_rbn_nodes.py --force"
  else
    echo "  >>> $PYTHON $HEATMAP_DIR/fetch_rbn_nodes.py"
  fi
fi

# ---- run_contest contest year has_rbn(0|1) ----------------------------------
run_contest() {
  local contest=$1 year=$2 has_rbn=$3
  local CSV="$SCRIPT_DIR/csv"
  local RBN_DIR="$SCRIPT_DIR/rbn"
  local DATA="$HEATMAP_DIR/data"
  local RAW="$SCRIPT_DIR/raw/${contest}_${year}"

  echo ""
  echo "======== $contest $year ========"
  { echo; echo "$(ts)  ======== $contest $year ========"; } >> "$LOG_FILE"

  # step1: ログ収集（raw ディレクトリに .txt があればスキップ）
  run_step \
    "step1 $contest $year" \
    "$RAW" \
    $PYTHON "$SCRIPT_DIR/step1_collect_logs_fast.py" \
      --contest "$contest" --year "$year"

  # download_rbn: 内部スキップあり・常に呼ぶ（RBNあり時のみ）
  if [[ $has_rbn -eq 1 ]]; then
    run_step \
      "download_rbn $contest $year" \
      "" \
      $PYTHON "$SCRIPT_DIR/download_rbn.py" \
        --contest "$contest" --year "$year"
  fi

  # make_spotted_grids（RBNあり時のみ）
  if [[ $has_rbn -eq 1 ]]; then
    run_step \
      "make_spotted_grids $contest $year" \
      "$RBN_DIR/${contest}_${year}_spotted_grids.csv" \
      $PYTHON "$SCRIPT_DIR/make_spotted_grids.py" \
        --contest "$contest" --year "$year"
  fi

  # make_spotted_grids_approx（全コンテスト: step4_crosscheck_approx が必要とする）
  run_step \
    "make_spotted_grids_approx $contest $year" \
    "$RBN_DIR/${contest}_${year}_spotted_grids_approx.csv" \
    $PYTHON "$SCRIPT_DIR/make_spotted_grids_approx.py" \
      --contest "$contest" --year "$year"

  # QSO クロスチェック → JSON
  run_step \
    "step4_crosscheck $contest $year" \
    "$CSV/${contest}_${year}_qso_pairs.csv" \
    $PYTHON "$SCRIPT_DIR/step4_crosscheck.py" \
      --contest "$contest" --year "$year" \
      --max-call-dist 2 --band-fix-window 15 --annotate-logs

  run_step \
    "step5_aggregate $contest $year" \
    "$DATA/${contest}_${year}.json" \
    $PYTHON "$SCRIPT_DIR/step5_aggregate.py" \
      --contest "$contest" --year "$year"

  # approx グリッドDB → QSO approx クロスチェック → JSON
  run_step \
    "step4_crosscheck_approx $contest $year" \
    "$CSV/${contest}_${year}_qso_pairs_approx.csv" \
    $PYTHON "$SCRIPT_DIR/step4_crosscheck_approx.py" \
      --contest "$contest" --year "$year" \
      --max-call-dist 2 --band-fix-window 15 --annotate-logs

  run_step \
    "step5_aggregate_approx $contest $year" \
    "$DATA/${contest}_${year}_approx.json" \
    $PYTHON "$SCRIPT_DIR/step5_aggregate.py" \
      --contest "$contest" --year "$year" \
      --input "$CSV/${contest}_${year}_qso_pairs_approx.csv" \
      --output "$DATA/${contest}_${year}_approx.json"

  # RBN → JSON / RBN approx → JSON（RBNあり時のみ）
  if [[ $has_rbn -eq 1 ]]; then
    run_step \
      "step4_rbn $contest $year" \
      "$CSV/${contest}_${year}_rbn_pairs.csv" \
      $PYTHON "$SCRIPT_DIR/step4_rbn.py" \
        --contest "$contest" --year "$year"

    run_step \
      "step5_rbn $contest $year" \
      "$DATA/${contest}_${year}_rbn.json" \
      $PYTHON "$SCRIPT_DIR/step5_rbn.py" \
        --contest "$contest" --year "$year"

    run_step \
      "step4_rbn_approx $contest $year" \
      "$CSV/${contest}_${year}_rbn_pairs_approx.csv" \
      $PYTHON "$SCRIPT_DIR/step4_rbn_approx.py" \
        --contest "$contest" --year "$year"

    run_step \
      "step5_rbn_approx $contest $year" \
      "$DATA/${contest}_${year}_rbn_approx.json" \
      $PYTHON "$SCRIPT_DIR/step5_rbn.py" \
        --contest "$contest" --year "$year" \
        --input "$CSV/${contest}_${year}_rbn_pairs_approx.csv" \
        --output "$DATA/${contest}_${year}_rbn_approx.json"
  fi
}

# ---- コンテスト一覧 ---------------------------------------------------------
# コンテスト×年の一覧は contest_utils.py --list から取得する
# （first_year と開催日程から自動導出。年のハードコードはしない）

CONTEST_LIST="$($PYTHON "$SCRIPT_DIR/contest_utils.py" --list)"
if [[ -z "$CONTEST_LIST" ]]; then
  _err "!!! contest_utils.py --list の出力が空です" \
       "!!! Empty output from contest_utils.py --list"
  exit 1
fi

while read -r contest year has_rbn; do
  [[ -z "$contest" ]] && continue
  run_contest "$contest" "$year" "$has_rbn"
done <<< "$CONTEST_LIST"

# ---- 完了 -------------------------------------------------------------------
echo ""
echo "========================================"
{ echo; echo "$(ts)  ========================================"; } >> "$LOG_FILE"
if [[ $DRY_RUN -eq 1 ]]; then
  _msg " dry-run 完了" " dry-run complete"
  { echo "$(ts)  dry-run complete"; } >> "$LOG_FILE"
else
  _msg " 完了: 成功=${ok}  スキップ=${skip_count}  失敗=${fail}" \
       " Done: ok=${ok}  skip=${skip_count}  fail=${fail}"
  { echo "$(ts)  Done: ok=${ok} skip=${skip_count} fail=${fail}"; } >> "$LOG_FILE"
fi
echo "========================================"
