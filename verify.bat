@echo off
REM verify.bat - PropMap 変更後の一括検証（Windows）
REM
REM 使い方:
REM   cd %USERPROFILE%\heatmap
REM   verify.bat
REM
REM 出力: 各項目の PASS/FAIL と末尾の SUMMARY。
REM       作業者（人間/AI）は SUMMARY を原文のまま報告すること。
REM       FAIL が1つでもあれば ERRORLEVEL 1。
REM
REM 本スクリプト自体を変更する場合は事前にユーザーの承認を得ること。
REM （サーバーAPIの検証は verify.sh のみ。Windows では W1〜W4 の基本検証を行う）

setlocal
cd /d "%~dp0"
set PASSN=0
set FAILN=0
set "FAILED="

echo ==== PropMap verify (Windows) ====

REM ---- W1: Python 解決 --------------------------------------------------------
call "%~dp0find_python.bat"
if not defined PYTHON (
    call :ng "W1 python resolution"
    echo 以降の検証は Python が必要なため中断します。
    goto :summary
)
call :ok "W1 python resolved: [%PYTHON%]"

REM ---- W2: Python 構文 --------------------------------------------------------
%PYTHON% -m py_compile propmap_server.py contest_logs\check_new_logs.py contest_logs\contest_utils.py contest_logs\step1_collect_logs_fast.py contest_logs\download_rbn.py >nul 2>&1
if errorlevel 1 ( call :ng "W2 py_compile" ) else ( call :ok "W2 py_compile main python files" )

REM ---- W3: contest_utils --list -----------------------------------------------
%PYTHON% contest_logs\contest_utils.py --list > "%TEMP%\pm_list.txt" 2>&1
set W3=1
findstr /r /c:"^iaru .* 1$" "%TEMP%\pm_list.txt" >nul || set W3=0
findstr /r /c:"^cqww_ssb .* 0$" "%TEMP%\pm_list.txt" >nul || set W3=0
if "%W3%"=="1" ( call :ok "W3 contest_utils --list (iaru rbn=1, cqww_ssb rbn=0)" ) else ( call :ng "W3 contest_utils --list" )

REM ---- W4: pipeline_steps の契約 ------------------------------------------------
cd contest_logs
%PYTHON% -c "import check_new_logs as c; a=c.pipeline_steps('cqwpx_cw',2099); b=c.pipeline_steps('cqww_ssb',2099); assert (len(a),len(b))==(12,6)" >nul 2>&1
if errorlevel 1 ( cd .. & call :ng "W4 pipeline_steps contract" ) else ( cd .. & call :ok "W4 pipeline_steps contract (12/6)" )

:summary
echo.
echo ==== SUMMARY ====
echo PASS=%PASSN% FAIL=%FAILN%
if defined FAILED echo failed:%FAILED%
if %FAILN% gtr 0 exit /b 1
exit /b 0

:ok
set /a PASSN+=1
echo   PASS: %~1
exit /b 0

:ng
set /a FAILN+=1
set "FAILED=%FAILED% [%~1]"
echo   FAIL: %~1
exit /b 0
