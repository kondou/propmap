@echo off
setlocal enabledelayedexpansion

REM generate_all.bat
REM Build all contests and all years end-to-end, starting from fetch_cty.
REM
REM Usage:
REM   generate_all.bat [--dry-run] [--force]
REM
REM Options:
REM   --dry-run   Show the commands that would run, without running them
REM   --force     Ignore existing files and re-run every step
REM
REM Log: generate_all.log (append mode)
REM      Records the start/end time of each step
REM
REM Skip rules:
REM   step1         Skipped if raw\{contest}_{year}\ already has .txt files
REM   everything else  Skipped if the output file already exists
REM   download_rbn  Manages its own skip logic internally, so it is always called
REM
set "SCRIPT_DIR=%~dp0"
set "HEATMAP_DIR=%SCRIPT_DIR%.."
set "LOG_FILE=%SCRIPT_DIR%generate_all.log"

REM ---- Resolve Python ---------------------------------------------------------
REM Resolved via find_python.bat so this runs without caring whether a
REM development environment is installed.
call "%HEATMAP_DIR%\find_python.bat"
if not defined PYTHON (
    echo !!! Python was not found. Follow the guidance above to install it, then run this again. 1>&2
    exit /b 1
)

set DRY_RUN=0
set FORCE=0
for %%a in (%1 %2) do (
    if /i "%%a"=="--dry-run" (
        set DRY_RUN=1
        echo [dry-run mode: showing commands only]
    )
    if /i "%%a"=="--force" (
        set FORCE=1
        echo [--force: re-run all steps regardless of existing files]
    )
)

set OK=0
set FAIL=0
set SKIP=0

REM ---- Log start -------------------------------------------------------------
call :get_ts
echo. >> "%LOG_FILE%"
if %FORCE%==1 (
    echo !_TS!  ======== generate_all.bat START --force ======== >> "%LOG_FILE%"
) else (
    echo !_TS!  ======== generate_all.bat START ======== >> "%LOG_FILE%"
)

REM ---- fetch_cty (run once; manages its own version check and skip logic) ----
echo.
echo ==== Fetch cty.dat ====
call :get_ts
echo. >> "%LOG_FILE%"
echo !_TS!  ==== fetch_cty ==== >> "%LOG_FILE%"

if %FORCE%==1 (
    echo   ^>^>^> %PYTHON% "%HEATMAP_DIR%\fetch_cty.py" --force
) else (
    echo   ^>^>^> %PYTHON% "%HEATMAP_DIR%\fetch_cty.py"
)
if %DRY_RUN%==0 (
    if %FORCE%==1 (
        %PYTHON% "%HEATMAP_DIR%\fetch_cty.py" --force > "%TEMP%\gall_step.txt" 2>&1
    ) else (
        %PYTHON% "%HEATMAP_DIR%\fetch_cty.py" > "%TEMP%\gall_step.txt" 2>&1
    )
    set _RC=!ERRORLEVEL!
    type "%TEMP%\gall_step.txt"
    type "%TEMP%\gall_step.txt" >> "%LOG_FILE%"
    del "%TEMP%\gall_step.txt" 2>nul
    call :get_ts
    echo !_TS!  fetch_cty rc=!_RC! >> "%LOG_FILE%"
    if !_RC! neq 0 (
        echo   !!! Error: fetch_cty.py
        set /a FAIL+=1
    ) else (
        set /a OK+=1
    )
)

REM ---- Main loops --------------------------------------------------------------
REM The contest x year list comes from contest_utils.py --list (derived
REM automatically from first_year and each contest's schedule; years are
REM never hardcoded here).

for /f "usebackq tokens=1,2,3" %%a in (`%PYTHON% "%SCRIPT_DIR%contest_utils.py" --list`) do (
    echo.
    echo ======== %%a %%b ========
    call :run_contest %%a %%b %%c
)

REM ---- Done --------------------------------------------------------------------
echo.
echo ========================================
call :get_ts
echo. >> "%LOG_FILE%"
echo !_TS!  ======================================== >> "%LOG_FILE%"
if %DRY_RUN%==1 (
    echo  dry-run complete
    echo !_TS!  dry-run complete >> "%LOG_FILE%"
) else (
    echo  Done: ok=!OK!  skip=!SKIP!  fail=!FAIL!
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

REM --- step1: collect logs ---
set "_LABEL=step1 !_C! !_Y!"
set "_OUTCHECK=%SCRIPT_DIR%raw\!_C!_!_Y!"
set _OUTTYPE=dir
set "_CMD=%PYTHON% "%SCRIPT_DIR%step1_collect_logs_fast.py" --contest !_C! --year !_Y!"
call :run_step

REM --- download_rbn: manages its own skip logic (RBN contests only) ---
if "!_HAS_RBN!"=="1" (
    set "_LABEL=download_rbn !_C! !_Y!"
    set _OUTCHECK=
    set _OUTTYPE=file
    set "_CMD=%PYTHON% "%SCRIPT_DIR%download_rbn.py" --contest !_C! --year !_Y!"
    call :run_step
)

REM --- make_spotted_grids (RBN contests only) ---
if "!_HAS_RBN!"=="1" (
    set "_LABEL=make_spotted_grids !_C! !_Y!"
    set "_OUTCHECK=%SCRIPT_DIR%rbn\!_C!_!_Y!_spotted_grids.csv"
    set _OUTTYPE=file
    set "_CMD=%PYTHON% "%SCRIPT_DIR%make_spotted_grids.py" --contest !_C! --year !_Y!"
    call :run_step
)

REM --- make_spotted_grids_approx (all contests: required by step4_crosscheck_approx) ---
set "_LABEL=make_spotted_grids_approx !_C! !_Y!"
set "_OUTCHECK=%SCRIPT_DIR%rbn\!_C!_!_Y!_spotted_grids_approx.csv"
set _OUTTYPE=file
set "_CMD=%PYTHON% "%SCRIPT_DIR%make_spotted_grids_approx.py" --contest !_C! --year !_Y!"
call :run_step

REM --- QSO cross-check -> JSON ---
set "_LABEL=step4_crosscheck !_C! !_Y!"
set "_OUTCHECK=%SCRIPT_DIR%csv\!_C!_!_Y!_qso_pairs.csv"
set _OUTTYPE=file
set "_CMD=%PYTHON% "%SCRIPT_DIR%step4_crosscheck.py" --contest !_C! --year !_Y! --max-call-dist 2 --band-fix-window 15 --annotate-logs"
call :run_step

set "_LABEL=step5_aggregate !_C! !_Y!"
set "_OUTCHECK=%HEATMAP_DIR%\data\!_C!_!_Y!.json"
set _OUTTYPE=file
set "_CMD=%PYTHON% "%SCRIPT_DIR%step5_aggregate.py" --contest !_C! --year !_Y!"
call :run_step

REM --- approx cross-check -> JSON ---
set "_LABEL=step4_crosscheck_approx !_C! !_Y!"
set "_OUTCHECK=%SCRIPT_DIR%csv\!_C!_!_Y!_qso_pairs_approx.csv"
set _OUTTYPE=file
set "_CMD=%PYTHON% "%SCRIPT_DIR%step4_crosscheck_approx.py" --contest !_C! --year !_Y! --max-call-dist 2 --band-fix-window 15 --annotate-logs"
call :run_step

set "_LABEL=step5_aggregate_approx !_C! !_Y!"
set "_OUTCHECK=%HEATMAP_DIR%\data\!_C!_!_Y!_approx.json"
set _OUTTYPE=file
set "_CMD=%PYTHON% "%SCRIPT_DIR%step5_aggregate.py" --contest !_C! --year !_Y! --input "%SCRIPT_DIR%csv\!_C!_!_Y!_qso_pairs_approx.csv" --output "%HEATMAP_DIR%\data\!_C!_!_Y!_approx.json""
call :run_step

REM --- RBN -> JSON / RBN approx -> JSON (RBN contests only) ---
if "!_HAS_RBN!"=="1" (
    set "_LABEL=step4_rbn !_C! !_Y!"
    set "_OUTCHECK=%SCRIPT_DIR%csv\!_C!_!_Y!_rbn_pairs.csv"
    set _OUTTYPE=file
    set "_CMD=%PYTHON% "%SCRIPT_DIR%step4_rbn.py" --contest !_C! --year !_Y!"
    call :run_step

    set "_LABEL=step5_rbn !_C! !_Y!"
    set "_OUTCHECK=%HEATMAP_DIR%\data\!_C!_!_Y!_rbn.json"
    set _OUTTYPE=file
    set "_CMD=%PYTHON% "%SCRIPT_DIR%step5_rbn.py" --contest !_C! --year !_Y!"
    call :run_step

    set "_LABEL=step4_rbn_approx !_C! !_Y!"
    set "_OUTCHECK=%SCRIPT_DIR%csv\!_C!_!_Y!_rbn_pairs_approx.csv"
    set _OUTTYPE=file
    set "_CMD=%PYTHON% "%SCRIPT_DIR%step4_rbn_approx.py" --contest !_C! --year !_Y!"
    call :run_step

    set "_LABEL=step5_rbn_approx !_C! !_Y!"
    set "_OUTCHECK=%HEATMAP_DIR%\data\!_C!_!_Y!_rbn_approx.json"
    set _OUTTYPE=file
    set "_CMD=%PYTHON% "%SCRIPT_DIR%step5_rbn.py" --contest !_C! --year !_Y! --input "%SCRIPT_DIR%csv\!_C!_!_Y!_rbn_pairs_approx.csv" --output "%HEATMAP_DIR%\data\!_C!_!_Y!_rbn_approx.json""
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
                REM Re-run if it's a JSON file with empty grids (no real data)
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
    echo   [SKIP] !_LABEL!
    call :get_ts
    echo !_TS!  [SKIP] !_LABEL! >> "%LOG_FILE%"
    set /a SKIP+=1
    exit /b 0
)

echo   [RUN] !_LABEL!
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
    echo   !!! Error rc=!_RC!: !_LABEL!
    set /a FAIL+=1
) else (
    set /a OK+=1
)
exit /b 0

REM --------------------------------------------------------------------------
REM :get_ts  -- sets _TS to current timestamp (YYYY-MM-DD HH:MM:SS)
REM --------------------------------------------------------------------------
:get_ts
for /f "tokens=*" %%t in ('%PYTHON% -c "from datetime import datetime; print(datetime.now().strftime(\"%%Y-%%m-%%d %%H:%%M:%%S\"))"') do set _TS=%%t
exit /b 0
