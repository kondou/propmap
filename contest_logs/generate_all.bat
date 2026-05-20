@echo off
setlocal enabledelayedexpansion

REM generate_all.bat
REM fetch_cty から始めて全コンテスト・全年を一気通貫で構築する
REM
REM 使い方:
REM   generate_all.bat [--dry-run] [--force]
REM
REM オプション:
REM   --dry-run   実際には実行せず対象コマンドを表示するだけ
REM   --force     既存ファイルを無視して全ステップを強制実行
REM
REM ログ: generate_all.log（追記モード）
REM       各ステップ開始・終了日時を記録
REM
REM スキップ判定:
REM   step1       raw\{contest}_{year}\ に .txt があればスキップ
REM   その他      出力ファイルが存在すればスキップ
REM   download_rbn は内部スキップのため常に呼ぶ
REM
REM 注意: Python が PATH にある必要があります

set "SCRIPT_DIR=%~dp0"
set "HEATMAP_DIR=%SCRIPT_DIR%.."
set "LOG_FILE=%SCRIPT_DIR%generate_all.log"

REM ---- Language detection --------------------------------------------------
set _L=en
for /f "tokens=3" %%a in ('reg query "HKCU\Control Panel\International" /v LocaleName 2^>nul') do (
    echo %%a | findstr /i "^ja" >nul 2>&1 && set _L=ja
)
if defined LANG (
    echo %LANG% | findstr /i "^ja" >nul 2>&1 && set _L=ja
)

if "!_L!"=="ja" (
    set "MSG_DRYRUN=[dry-run モード: コマンドを表示するだけ]"
    set "MSG_FORCE=[--force: 既存ファイルを無視して全ステップを強制実行]"
    set "MSG_DRYRUN_DONE= dry-run 完了"
    set "MSG_DONE_PRE= 完了: 成功="
    set "MSG_DONE_SKIP= スキップ="
    set "MSG_DONE_FAIL= 失敗="
    set "MSG_ERR=  !!! エラー:"
    set "MSG_SKIP=  [スキップ]"
    set "MSG_RUN=  [実行]"
) else (
    set "MSG_DRYRUN=[dry-run mode: showing commands only]"
    set "MSG_FORCE=[--force: re-run all steps regardless of existing files]"
    set "MSG_DRYRUN_DONE= dry-run complete"
    set "MSG_DONE_PRE= Done: ok="
    set "MSG_DONE_SKIP= skip="
    set "MSG_DONE_FAIL= fail="
    set "MSG_ERR=  !!! Error:"
    set "MSG_SKIP=  [SKIP]"
    set "MSG_RUN=  [RUN]"
)
REM -------------------------------------------------------------------------

set DRY_RUN=0
set FORCE=0
for %%a in (%1 %2) do (
    if /i "%%a"=="--dry-run" (
        set DRY_RUN=1
        echo !MSG_DRYRUN!
    )
    if /i "%%a"=="--force" (
        set FORCE=1
        echo !MSG_FORCE!
    )
)

set OK=0
set FAIL=0
set SKIP=0

REM ---- Log start -----------------------------------------------------------
call :get_ts
echo. >> "%LOG_FILE%"
if %FORCE%==1 (
    echo !_TS!  ======== generate_all.bat START --force ======== >> "%LOG_FILE%"
) else (
    echo !_TS!  ======== generate_all.bat START ======== >> "%LOG_FILE%"
)

REM ---- fetch_cty (一度だけ; 内部でバージョンチェックとスキップを管理) ----
echo.
if "!_L!"=="ja" (echo ==== cty.dat 取得 ====) else (echo ==== Fetch cty.dat ====)
call :get_ts
echo. >> "%LOG_FILE%"
echo !_TS!  ==== fetch_cty ==== >> "%LOG_FILE%"

if %FORCE%==1 (
    echo   ^>^>^> python "%HEATMAP_DIR%\fetch_cty.py" --force
) else (
    echo   ^>^>^> python "%HEATMAP_DIR%\fetch_cty.py"
)
if %DRY_RUN%==0 (
    if %FORCE%==1 (
        python "%HEATMAP_DIR%\fetch_cty.py" --force > "%TEMP%\gall_step.txt" 2>&1
    ) else (
        python "%HEATMAP_DIR%\fetch_cty.py" > "%TEMP%\gall_step.txt" 2>&1
    )
    set _RC=!ERRORLEVEL!
    type "%TEMP%\gall_step.txt"
    type "%TEMP%\gall_step.txt" >> "%LOG_FILE%"
    del "%TEMP%\gall_step.txt" 2>nul
    call :get_ts
    echo !_TS!  fetch_cty rc=!_RC! >> "%LOG_FILE%"
    if !_RC! neq 0 (
        echo !MSG_ERR! fetch_cty.py
        set /a FAIL+=1
    ) else (
        set /a OK+=1
    )
)

REM ---- Main loops ----------------------------------------------------------

for /l %%y in (2018,1,2025) do (
    echo.
    echo ======== iaru %%y ========
    call :run_contest iaru %%y 1
)

for /l %%y in (2005,1,2025) do (
    echo.
    echo ======== cqww_cw %%y ========
    call :run_contest cqww_cw %%y 1
)

for /l %%y in (2005,1,2025) do (
    echo.
    echo ======== cqww_ssb %%y ========
    call :run_contest cqww_ssb %%y 0
)

for /l %%y in (2008,1,2025) do (
    echo.
    echo ======== cqwpx_cw %%y ========
    call :run_contest cqwpx_cw %%y 1
)

for /l %%y in (2008,1,2025) do (
    echo.
    echo ======== cqwpx_ssb %%y ========
    call :run_contest cqwpx_ssb %%y 0
)

REM ---- Done ----------------------------------------------------------------
echo.
echo ========================================
call :get_ts
echo. >> "%LOG_FILE%"
echo !_TS!  ======================================== >> "%LOG_FILE%"
if %DRY_RUN%==1 (
    echo !MSG_DRYRUN_DONE!
    echo !_TS!  dry-run complete >> "%LOG_FILE%"
) else (
    echo !MSG_DONE_PRE!!OK!!MSG_DONE_SKIP!!SKIP!!MSG_DONE_FAIL!!FAIL!
    echo !_TS!  Done: ok=!OK! skip=!SKIP! fail=!FAIL! >> "%LOG_FILE%"
)
echo ========================================
goto :eof

REM ==========================================================================
REM Subroutines
REM ==========================================================================

REM :run_contest  contest  year  has_rbn(0|1)
:run_contest
set _C=%1
set _Y=%2
set _HAS_RBN=%3

call :get_ts
echo. >> "%LOG_FILE%"
echo !_TS!  ======== !_C! !_Y! ======== >> "%LOG_FILE%"

REM --- step1: ログ収集 ---
set "_LABEL=step1 !_C! !_Y!"
set "_OUTCHECK=%SCRIPT_DIR%raw\!_C!_!_Y!"
set _OUTTYPE=dir
set "_CMD=python "%SCRIPT_DIR%step1_collect_logs_fast.py" --contest !_C! --year !_Y!"
call :run_step

REM --- download_rbn: 内部スキップあり（RBNあり時のみ）---
if "!_HAS_RBN!"=="1" (
    set "_LABEL=download_rbn !_C! !_Y!"
    set _OUTCHECK=
    set _OUTTYPE=file
    set "_CMD=python "%SCRIPT_DIR%download_rbn.py" --contest !_C! --year !_Y!"
    call :run_step
)

REM --- make_spotted_grids（RBNあり時のみ）---
if "!_HAS_RBN!"=="1" (
    set "_LABEL=make_spotted_grids !_C! !_Y!"
    set "_OUTCHECK=%SCRIPT_DIR%rbn\!_C!_!_Y!_spotted_grids.csv"
    set _OUTTYPE=file
    set "_CMD=python "%SCRIPT_DIR%make_spotted_grids.py" --contest !_C! --year !_Y!"
    call :run_step
)

REM --- make_spotted_grids_approx（全コンテスト: step4_crosscheck_approx が必要とする）---
set "_LABEL=make_spotted_grids_approx !_C! !_Y!"
set "_OUTCHECK=%SCRIPT_DIR%rbn\!_C!_!_Y!_spotted_grids_approx.csv"
set _OUTTYPE=file
set "_CMD=python "%SCRIPT_DIR%make_spotted_grids_approx.py" --contest !_C! --year !_Y!"
call :run_step

REM --- QSO クロスチェック → JSON ---
set "_LABEL=step4_crosscheck !_C! !_Y!"
set "_OUTCHECK=%SCRIPT_DIR%csv\!_C!_!_Y!_qso_pairs.csv"
set _OUTTYPE=file
set "_CMD=python "%SCRIPT_DIR%step4_crosscheck.py" --contest !_C! --year !_Y! --max-call-dist 2 --band-fix-window 15 --annotate-logs"
call :run_step

set "_LABEL=step5_aggregate !_C! !_Y!"
set "_OUTCHECK=%HEATMAP_DIR%\data\!_C!_!_Y!.json"
set _OUTTYPE=file
set "_CMD=python "%SCRIPT_DIR%step5_aggregate.py" --contest !_C! --year !_Y!"
call :run_step

REM --- approx クロスチェック → JSON ---
set "_LABEL=step4_crosscheck_approx !_C! !_Y!"
set "_OUTCHECK=%SCRIPT_DIR%csv\!_C!_!_Y!_qso_pairs_approx.csv"
set _OUTTYPE=file
set "_CMD=python "%SCRIPT_DIR%step4_crosscheck_approx.py" --contest !_C! --year !_Y! --max-call-dist 2 --band-fix-window 15 --annotate-logs"
call :run_step

set "_LABEL=step5_aggregate_approx !_C! !_Y!"
set "_OUTCHECK=%HEATMAP_DIR%\data\!_C!_!_Y!_approx.json"
set _OUTTYPE=file
set "_CMD=python "%SCRIPT_DIR%step5_aggregate.py" --contest !_C! --year !_Y! --input "%SCRIPT_DIR%csv\!_C!_!_Y!_qso_pairs_approx.csv" --output "%HEATMAP_DIR%\data\!_C!_!_Y!_approx.json""
call :run_step

REM --- RBN → JSON / RBN approx → JSON（RBNあり時のみ）---
if "!_HAS_RBN!"=="1" (
    set "_LABEL=step4_rbn !_C! !_Y!"
    set "_OUTCHECK=%SCRIPT_DIR%csv\!_C!_!_Y!_rbn_pairs.csv"
    set _OUTTYPE=file
    set "_CMD=python "%SCRIPT_DIR%step4_rbn.py" --contest !_C! --year !_Y!"
    call :run_step

    set "_LABEL=step5_rbn !_C! !_Y!"
    set "_OUTCHECK=%HEATMAP_DIR%\data\!_C!_!_Y!_rbn.json"
    set _OUTTYPE=file
    set "_CMD=python "%SCRIPT_DIR%step5_rbn.py" --contest !_C! --year !_Y!"
    call :run_step

    set "_LABEL=step4_rbn_approx !_C! !_Y!"
    set "_OUTCHECK=%SCRIPT_DIR%csv\!_C!_!_Y!_rbn_pairs_approx.csv"
    set _OUTTYPE=file
    set "_CMD=python "%SCRIPT_DIR%step4_rbn_approx.py" --contest !_C! --year !_Y!"
    call :run_step

    set "_LABEL=step5_rbn_approx !_C! !_Y!"
    set "_OUTCHECK=%HEATMAP_DIR%\data\!_C!_!_Y!_rbn_approx.json"
    set _OUTTYPE=file
    set "_CMD=python "%SCRIPT_DIR%step5_rbn.py" --contest !_C! --year !_Y! --input "%SCRIPT_DIR%csv\!_C!_!_Y!_rbn_pairs_approx.csv" --output "%HEATMAP_DIR%\data\!_C!_!_Y!_rbn_approx.json""
    call :run_step
)
exit /b 0

REM --------------------------------------------------------------------------
REM :run_step
REM  Reads globals : _LABEL, _CMD, _OUTCHECK, _OUTTYPE, FORCE, DRY_RUN
REM  Updates globals: OK, FAIL, SKIP
REM --------------------------------------------------------------------------
:run_step
set _DO_SKIP=0

if not "!_OUTCHECK!"=="" (
    if "!_OUTTYPE!"=="dir" (
        dir /b /a-d "!_OUTCHECK!\*.txt" >nul 2>&1
        if not errorlevel 1 (
            if %FORCE%==0 set _DO_SKIP=1
        )
    ) else (
        if exist "!_OUTCHECK!" (
            if %FORCE%==0 (
                set _DO_SKIP=1
                REM JSON ファイルで grids が空（実データなし）なら再実行
                echo !_OUTCHECK! | findstr /i "\.json$" >nul 2>&1
                if not errorlevel 1 (
                    findstr /c:"\"grids\":{}" "!_OUTCHECK!" >nul 2>&1
                    if not errorlevel 1 set _DO_SKIP=0
                )
            )
        )
    )
)

if !_DO_SKIP!==1 (
    echo !MSG_SKIP! !_LABEL!
    call :get_ts
    echo !_TS!  [SKIP] !_LABEL! >> "%LOG_FILE%"
    set /a SKIP+=1
    exit /b 0
)

echo !MSG_RUN! !_LABEL!
call :get_ts
echo. >> "%LOG_FILE%"
echo !_TS!  [START] !_LABEL! >> "%LOG_FILE%"
echo   CMD: !_CMD! >> "%LOG_FILE%"
echo   ^>^>^> !_CMD!

if %DRY_RUN%==1 (
    echo !_TS!  [DRYRUN] !_LABEL! >> "%LOG_FILE%"
    exit /b 0
)

!_CMD! > "%TEMP%\gall_step.txt" 2>&1
set _RC=!ERRORLEVEL!
type "%TEMP%\gall_step.txt"
type "%TEMP%\gall_step.txt" >> "%LOG_FILE%"
del "%TEMP%\gall_step.txt" 2>nul

call :get_ts
echo !_TS!  [END rc=!_RC!] !_LABEL! >> "%LOG_FILE%"

if !_RC! neq 0 (
    echo !MSG_ERR! (rc=!_RC!) !_LABEL!
    set /a FAIL+=1
) else (
    set /a OK+=1
)
exit /b 0

REM --------------------------------------------------------------------------
REM :get_ts  — sets _TS to current timestamp (YYYY-MM-DD HH:MM:SS)
REM --------------------------------------------------------------------------
:get_ts
for /f "tokens=*" %%t in ('python -c "from datetime import datetime; print(datetime.now().strftime(\"%%Y-%%m-%%d %%H:%%M:%%S\"))"') do set _TS=%%t
exit /b 0
