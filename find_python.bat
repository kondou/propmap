@echo off
REM find_python.bat - resolve the Python to use (Windows)
REM
REM Purpose: let the user run PropMap without caring whether a development
REM environment is installed. PropMap uses only the Python standard library,
REM so all that's needed is one Python 3.10+ interpreter.
REM
REM Usage:  call "%~dp0find_python.bat"
REM   Success: environment variable PYTHON holds a command (e.g. "py -3" / "python")
REM   Failure: PYTHON is undefined, ERRORLEVEL 1. Guidance already printed.
REM
REM Resolution order:
REM   0. PROPMAP_PYTHON environment variable (explicit override)
REM   1. py -3   (the launcher bundled with the python.org installer)
REM   2. python  (the Microsoft Store stub is naturally excluded by the
REM                version check below; running it with arguments does not
REM                open the Store, so the check itself is safe)
REM   3. python3
REM   4. uv      (fetches a standalone Python automatically; no dev env needed)
REM   5. If nothing found: offer to install uv, with consent

setlocal EnableDelayedExpansion
set "_FOUND="

if defined PROPMAP_PYTHON (
    %PROPMAP_PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! == 0 ( set "_FOUND=%PROPMAP_PYTHON%" ) else (
        echo !!! PROPMAP_PYTHON is set to "%PROPMAP_PYTHON%" but cannot run as Python 3.10+ 1>&2
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
    echo No Python 3.10+ was found. 1>&2
    echo PropMap needs Python, but no development environment 1>&2
    echo such as Visual Studio is required. You can install it one of two ways: 1>&2
    echo   A^) uv - recommended, automatic: continue below to install it now 1>&2
    echo   B^) python.org official installer: https://www.python.org/downloads/ 1>&2
    echo. 1>&2
    set /p _ans="Install uv and continue? [y/N]: "
    if /i "!_ans!" == "y" (
        powershell -NoProfile -ExecutionPolicy ByPass -Command "$env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/install.ps1 | iex"
        set "PATH=%USERPROFILE%\.local\bin;!PATH!"
        where uv >nul 2>&1
        if !errorlevel! == 0 (
            set "_FOUND=uv run --no-project --python 3.12 python"
            echo uv installed. The first run may take a little longer 1>&2
            echo while it fetches the Python runtime itself. 1>&2
        ) else (
            echo !!! Failed to install uv 1>&2
        )
    )
)

if not defined _FOUND (
    endlocal
    set "PYTHON="
    exit /b 1
)

REM Exit setlocal while passing PYTHON and PATH (if uv was just installed)
REM back to the caller.
endlocal & set "PYTHON=%_FOUND%" & set "PATH=%PATH%"
exit /b 0
