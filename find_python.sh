#!/bin/bash
# find_python.sh - 実行に使う Python を解決する（macOS / Linux / WSL2 共通）
#
# 目的: 利用者に開発環境（Xcode / Command Line Tools / Homebrew）の有無を
#       意識させない。PropMap は標準ライブラリのみで動くため、
#       「Python 3.10 以上のインタプリタが1つ見つかればよい」。
#
# 使い方:  source /path/to/find_python.sh
#   成功: 変数 PYTHON にコマンドが入る（例: "python3" / "uv run --no-project --python 3.12 python"）
#         ※ 複数語になり得るため、呼び出し側は $PYTHON を「クォートせずに」使うこと
#   失敗: PYTHON は空。案内を表示済み。呼び出し側で終了すること
#
# 解決順序:
#   0. 環境変数 PROPMAP_PYTHON（明示指定の逃げ道）
#   1. PATH 上の python3（macOSでは CLT スタブを除外。下記注意参照）
#   2. 既知の場所: /opt/homebrew, /usr/local, python.org Framework
#   3. macOS の /usr/bin/python3（CLT がインストール済みの場合のみ）
#   4. uv（スタンドアロンPythonを自動調達。ビルド不要・開発環境不要）
#   5. 見つからない場合: 対話端末なら uv のインストールを提案（同意制）
#
# ★ macOS の重要な注意:
#   CLT 未インストール時の /usr/bin/python3 は「スタブ」で、実行すると
#   開発者ツールのインストールを促す GUI ダイアログが出る。これがまさに
#   避けたい体験なので、CLT の有無（xcode-select -p）を確認するまで
#   /usr/bin/python3 を実行してはならない（バージョン確認の実行も不可）。

_pm_is_darwin() { [ "$(uname -s 2>/dev/null)" = "Darwin" ]; }

_pm_clt_installed() { xcode-select -p >/dev/null 2>&1; }

# 実行して 3.10+ であることを確認（実行可能性の検査を兼ねる）
_pm_verify() {
  "$@" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' \
    >/dev/null 2>&1
}

# macOS で候補が /usr/bin/python3（スタブの可能性）かどうか
_pm_is_stub_path() {
  _pm_is_darwin || return 1
  local p
  p="$(command -v "$1" 2>/dev/null || echo "$1")"
  # シンボリックリンクを解決（realpath は macOS 標準に無い場合があるので python 非依存で）
  while [ -L "$p" ]; do p="$(readlink "$p")"; done
  [ "$p" = "/usr/bin/python3" ]
}

_pm_try() {
  # $@: 候補コマンド。安全確認 → 実行検証 → PYTHON 設定
  if _pm_is_stub_path "$1" && ! _pm_clt_installed; then
    return 1   # CLT 無しの /usr/bin/python3 は実行せず除外
  fi
  if _pm_verify "$@"; then
    PYTHON="$*"
    return 0
  fi
  return 1
}

PYTHON=""

# 0. 明示指定
if [ -n "${PROPMAP_PYTHON:-}" ]; then
  if _pm_try ${PROPMAP_PYTHON:-}; then :; else
    echo "!!! PROPMAP_PYTHON (${PROPMAP_PYTHON:-}) は Python 3.10+ として実行できません" >&2
  fi
fi

# 1. PATH 上の python3
[ -z "$PYTHON" ] && command -v python3 >/dev/null 2>&1 && _pm_try python3

# 2. 既知のインストール場所（PATH 未通しの python.org / Homebrew を拾う）
if [ -z "$PYTHON" ]; then
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
    [ -x "$c" ] && _pm_try "$c" && break
  done
fi

# 3. macOS: CLT が入っているなら /usr/bin/python3 も可
if [ -z "$PYTHON" ] && _pm_is_darwin && _pm_clt_installed && [ -x /usr/bin/python3 ]; then
  _pm_try /usr/bin/python3
fi

# 4. uv（インストール済みなら、Pythonはuvが自動調達する）
if [ -z "$PYTHON" ]; then
  for uvbin in uv "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if command -v "$uvbin" >/dev/null 2>&1 || [ -x "$uvbin" ]; then
      PYTHON="$uvbin run --no-project --python 3.12 python"
      break
    fi
  done
fi

# 5. 何も無い: 案内（対話端末なら uv インストールを同意制で提案）
if [ -z "$PYTHON" ]; then
  echo "" >&2
  echo "Python 3.10 以上が見つかりませんでした。" >&2
  echo "PropMap の実行には Python が必要ですが、Xcode や Command Line Tools" >&2
  echo "などの開発環境は不要です。次のいずれかで導入できます:" >&2
  echo "  A) uv（推奨・自動）: このままインストールを続行できます" >&2
  echo "  B) python.org 公式インストーラ: https://www.python.org/downloads/" >&2
  echo "" >&2
  if [ -t 0 ]; then
    printf "uv をインストールして続行しますか? [y/N]: " >&2
    read -r _ans
    if [ "$_ans" = "y" ] || [ "$_ans" = "Y" ]; then
      if curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh; then
        export PATH="$HOME/.local/bin:$PATH"
        if command -v uv >/dev/null 2>&1; then
          PYTHON="uv run --no-project --python 3.12 python"
          echo "uv をインストールしました。初回は Python 本体の取得のため" >&2
          echo "起動に少し時間がかかります。" >&2
        fi
      else
        echo "!!! uv のインストールに失敗しました" >&2
      fi
    fi
  fi
fi

unset -f _pm_is_darwin _pm_clt_installed _pm_verify _pm_is_stub_path _pm_try 2>/dev/null
