@echo off
REM find_python.bat - 実行に使う Python を解決する（Windows用）
REM
REM 目的: 利用者に開発環境の有無を意識させない。PropMap は標準ライブラリ
REM       のみで動くため、Python 3.10 以上が1つ見つかればよい。
REM
REM 使い方:  call "%~dp0find_python.bat"
REM   成功: 環境変数 PYTHON にコマンドが入る（例: "py -3" / "python"）
REM   失敗: PYTHON は未定義、ERRORLEVEL 1。案内を表示済み
REM
REM 解決順序:
REM   0. 環境変数 PROPMAP_PYTHON（明示指定の逃げ道）
REM   1. py -3   （python.org インストーラ付属のランチャー）
REM   2. python  （Microsoft Store のスタブは検証で自然に除外される。
REM                引数付き実行ではストアは開かないため検証は安全）
REM   3. python3
REM   4. uv      （スタンドアロンPythonを自動調達。開発環境不要）
REM   5. 見つからない場合: uv インストールを同意制で提案

setlocal EnableDelayedExpansion
set "_FOUND="

if defined PROPMAP_PYTHON (
    %PROPMAP_PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! == 0 ( set "_FOUND=%PROPMAP_PYTHON%" ) else (
        echo !!! PROPMAP_PYTHON は Python 3.10+ として実行できません 1>&2
    )
)

if not defined _FOUND (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! == 0 set "_FOUND=py -3"
)
if not defined _FOUND (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! == 0 set "_FOUND=python"
)
if not defined _FOUND (
    python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! == 0 set "_FOUND=python3"
)
if not defined _FOUND (
    where uv >nul 2>&1
    if !errorlevel! == 0 (
        set "_FOUND=uv run --no-project --python 3.12 python"
    ) else if exist "%USERPROFILE%\.local\bin\uv.exe" (
        set "PATH=%USERPROFILE%\.local\bin;!PATH!"
        set "_FOUND=uv run --no-project --python 3.12 python"
    )
)

if not defined _FOUND (
    echo. 1>&2
    echo Python 3.10 以上が見つかりませんでした。 1>&2
    echo PropMap の実行には Python が必要ですが、Visual Studio などの 1>&2
    echo 開発環境は不要です。次のいずれかで導入できます: 1>&2
    echo   A^) uv（推奨・自動）: このままインストールを続行できます 1>&2
    echo   B^) python.org 公式インストーラ: https://www.python.org/downloads/ 1>&2
    echo. 1>&2
    set /p _ans="uv をインストールして続行しますか? [y/N]: "
    if /i "!_ans!" == "y" (
        powershell -NoProfile -ExecutionPolicy ByPass -Command "$env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/install.ps1 | iex"
        set "PATH=%USERPROFILE%\.local\bin;!PATH!"
        where uv >nul 2>&1
        if !errorlevel! == 0 (
            set "_FOUND=uv run --no-project --python 3.12 python"
            echo uv をインストールしました。初回は Python 本体の取得のため 1>&2
            echo 起動に少し時間がかかります。 1>&2
        ) else (
            echo !!! uv のインストールに失敗しました 1>&2
        )
    )
)

if not defined _FOUND (
    endlocal
    set "PYTHON="
    exit /b 1
)

REM setlocal を抜けつつ PYTHON と PATH（uv導入時）を呼び出し元へ引き継ぐ
endlocal & set "PYTHON=%_FOUND%" & set "PATH=%PATH%"
exit /b 0
