@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0

REM generate_all.bat
REM QSOペアCSV・RBNペアCSV・JSONを全コンテスト全年で再生成する
REM
REM 使い方:
REM   generate_all.bat            本実行
REM   generate_all.bat --dry-run  対象確認のみ（実際には実行しない）

set DRY_RUN=0
if "%1"=="--dry-run" (
    set DRY_RUN=1
    echo [dry-run モード: コマンドを表示するだけ]
)

set OK=0
set FAIL=0

echo ========================================
echo  QSO パイプライン (step4 -^> step5)
echo ========================================

for /l %%y in (2018,1,2025) do (
    echo --- iaru %%y ---
    call :run python "%SCRIPT_DIR%step4_crosscheck.py" --contest iaru --year %%y --max-call-dist 2 --band-fix-window 15 --annotate-logs
    call :run python "%SCRIPT_DIR%step5_aggregate.py"  --contest iaru --year %%y
)

for /l %%y in (2005,1,2025) do (
    echo --- cqww_cw %%y ---
    call :run python "%SCRIPT_DIR%step4_crosscheck.py" --contest cqww_cw --year %%y --max-call-dist 2 --band-fix-window 15 --annotate-logs
    call :run python "%SCRIPT_DIR%step5_aggregate.py"  --contest cqww_cw --year %%y
)

for /l %%y in (2005,1,2025) do (
    echo --- cqww_ssb %%y ---
    call :run python "%SCRIPT_DIR%step4_crosscheck.py" --contest cqww_ssb --year %%y --max-call-dist 2 --band-fix-window 15 --annotate-logs
    call :run python "%SCRIPT_DIR%step5_aggregate.py"  --contest cqww_ssb --year %%y
)

for /l %%y in (2008,1,2025) do (
    echo --- cqwpx_cw %%y ---
    call :run python "%SCRIPT_DIR%step4_crosscheck.py" --contest cqwpx_cw --year %%y --max-call-dist 2 --band-fix-window 15 --annotate-logs
    call :run python "%SCRIPT_DIR%step5_aggregate.py"  --contest cqwpx_cw --year %%y
)

for /l %%y in (2008,1,2025) do (
    echo --- cqwpx_ssb %%y ---
    call :run python "%SCRIPT_DIR%step4_crosscheck.py" --contest cqwpx_ssb --year %%y --max-call-dist 2 --band-fix-window 15 --annotate-logs
    call :run python "%SCRIPT_DIR%step5_aggregate.py"  --contest cqwpx_ssb --year %%y
)

echo ========================================
echo  RBN パイプライン (step4_rbn -^> step5_rbn)
echo ========================================

for %%y in (2018 2019 2020 2021 2022 2023 2024) do (
    echo --- iaru RBN %%y ---
    call :run python "%SCRIPT_DIR%step4_rbn.py" --contest iaru --year %%y
    call :run python "%SCRIPT_DIR%step5_rbn.py" --contest iaru --year %%y
)

for /l %%y in (2005,1,2024) do (
    echo --- cqww_cw RBN %%y ---
    call :run python "%SCRIPT_DIR%step4_rbn.py" --contest cqww_cw --year %%y
    call :run python "%SCRIPT_DIR%step5_rbn.py" --contest cqww_cw --year %%y
)

for /l %%y in (2008,1,2025) do (
    echo --- cqwpx_cw RBN %%y ---
    call :run python "%SCRIPT_DIR%step4_rbn.py" --contest cqwpx_cw --year %%y
    call :run python "%SCRIPT_DIR%step5_rbn.py" --contest cqwpx_cw --year %%y
)

echo ========================================
if %DRY_RUN%==1 (
    echo  dry-run 完了
) else (
    echo  完了: 成功=!OK! 失敗=!FAIL!
)
echo ========================================
goto :eof

:run
if %DRY_RUN%==1 (
    echo ^>^>^> %*
    exit /b 0
)
echo ^>^>^> %*
%*
if errorlevel 1 (
    echo !!! エラー: %*
    set /a FAIL+=1
) else (
    set /a OK+=1
)
exit /b 0
