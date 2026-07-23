#!/bin/bash
# find_python.sh - resolve the Python to use (macOS / Linux / WSL2)
#
# Purpose: let the user run PropMap without caring whether a development
# environment (Xcode / Command Line Tools / Homebrew) is installed.
# PropMap uses only the Python standard library, so all that's needed is
# one Python 3.10+ interpreter.
#
# Usage:  source /path/to/find_python.sh
#   Success: PYTHON holds a command (e.g. "python3" / "uv run --no-project --python 3.12 python")
#            Since it can be multiple words, callers must use $PYTHON
#            UNQUOTED.
#   Failure: PYTHON is empty. Guidance already printed. Caller should exit.
#
# Resolution order:
#   0. PROPMAP_PYTHON environment variable (explicit override)
#   1. python3 on PATH (macOS: the CLT stub is excluded; see note below)
#   2. Known locations: /opt/homebrew, /usr/local, python.org Framework
#   3. macOS's /usr/bin/python3 (only if Command Line Tools are installed)
#   4. uv (fetches a standalone Python automatically; no build, no dev env)
#   5. If nothing found: offer to install uv, with consent, in an
#      interactive terminal
#
# * Important macOS note:
#   When Command Line Tools aren't installed, /usr/bin/python3 is a
#   "stub" that pops up a GUI dialog prompting to install developer tools
#   when run. That's exactly the experience this script avoids, so
#   /usr/bin/python3 must never be run (not even to check its version)
#   until CLT presence is confirmed (xcode-select -p).

# ---- i18n -------------------------------------------------------------------
if [[ "${LANG:-}" == ja* ]] || [[ "${LC_ALL:-}" == ja* ]] || [[ "${LANGUAGE:-}" == ja* ]]; then
  _pm_L=ja
else
  _pm_L=en
fi
_pm_msg() { [[ "$_pm_L" == ja ]] && echo "$1" || echo "$2"; }
# -----------------------------------------------------------------------------

_pm_is_darwin() { [ "$(uname -s 2>/dev/null)" = "Darwin" ]; }

_pm_clt_installed() { xcode-select -p >/dev/null 2>&1; }

# Run it and confirm it's 3.10+ (this also checks it's actually runnable)
_pm_verify() {
  "$@" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' \
    >/dev/null 2>&1
}

# Whether a candidate resolves to /usr/bin/python3 (possibly a stub) on macOS
_pm_is_stub_path() {
  _pm_is_darwin || return 1
  local p
  p="$(command -v "$1" 2>/dev/null || echo "$1")"
  # Resolve symlinks (avoid depending on realpath, not always on macOS)
  while [ -L "$p" ]; do p="$(readlink "$p")"; done
  [ "$p" = "/usr/bin/python3" ]
}

_pm_try() {
  # $@: candidate command. Safety check -> verify runnable -> set PYTHON
  if _pm_is_stub_path "$1" && ! _pm_clt_installed; then
    return 1   # exclude /usr/bin/python3 without CLT; do not run it
  fi
  if _pm_verify "$@"; then
    PYTHON="$*"
    return 0
  fi
  return 1
}

PYTHON=""

# 0. Explicit override
if [ -n "${PROPMAP_PYTHON:-}" ]; then
  if _pm_try ${PROPMAP_PYTHON:-}; then :; else
    echo "$(_pm_msg "!!! PROPMAP_PYTHON (${PROPMAP_PYTHON:-}) は Python 3.10+ として実行できません" \
                    "!!! PROPMAP_PYTHON (${PROPMAP_PYTHON:-}) cannot run as Python 3.10+")" >&2
  fi
fi

# 1. python3 on PATH
[ -z "$PYTHON" ] && command -v python3 >/dev/null 2>&1 && _pm_try python3

# 2. Known install locations (catches python.org / Homebrew not on PATH)
if [ -z "$PYTHON" ]; then
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
    [ -x "$c" ] && _pm_try "$c" && break
  done
fi

# 3. macOS: /usr/bin/python3 is fine if CLT is installed
if [ -z "$PYTHON" ] && _pm_is_darwin && _pm_clt_installed && [ -x /usr/bin/python3 ]; then
  _pm_try /usr/bin/python3
fi

# 4. uv (if already installed, it fetches Python itself)
if [ -z "$PYTHON" ]; then
  for uvbin in uv "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if command -v "$uvbin" >/dev/null 2>&1 || [ -x "$uvbin" ]; then
      PYTHON="$uvbin run --no-project --python 3.12 python"
      break
    fi
  done
fi

# 5. Nothing found: guidance (offer to install automatically, with consent, if interactive)
if [ -z "$PYTHON" ]; then
  echo "" >&2
  echo "$(_pm_msg "Python 3.10 以上が見つかりませんでした。" \
                  "No Python 3.10+ was found.")" >&2
  if [ -t 0 ]; then
    printf "%s" "$(_pm_msg "Python を自動でインストールしますか? [y/N]: " \
                           "Install Python automatically? [y/N]: ")" >&2
    read -r _pm_ans
    if [ "$_pm_ans" = "y" ] || [ "$_pm_ans" = "Y" ]; then
      if curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh; then
        export PATH="$HOME/.local/bin:$PATH"
        if command -v uv >/dev/null 2>&1; then
          PYTHON="uv run --no-project --python 3.12 python"
          echo "$(_pm_msg "インストールしました。初回は少し時間がかかります。" \
                          "Installed. The first run may take a little longer.")" >&2
        fi
      else
        echo "$(_pm_msg "!!! インストールに失敗しました。https://www.python.org/downloads/ から手動でインストールしてください。" \
                        "!!! Install failed. Please install Python manually from https://www.python.org/downloads/")" >&2
      fi
    else
      echo "$(_pm_msg "手動でインストールする場合は https://www.python.org/downloads/ から" \
                      "To install manually, get it from https://www.python.org/downloads/")" >&2
    fi
  else
    echo "$(_pm_msg "https://www.python.org/downloads/ から Python をインストールしてください。" \
                    "Please install Python from https://www.python.org/downloads/")" >&2
  fi
fi

unset -f _pm_is_darwin _pm_clt_installed _pm_verify _pm_is_stub_path _pm_try _pm_msg 2>/dev/null
unset _pm_L _pm_ans 2>/dev/null
