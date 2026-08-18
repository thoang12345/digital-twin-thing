@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "SKIP_TESTS=0"
if /I "%~1"=="--no-tests" set "SKIP_TESTS=1"
set "PY_CMD="

where py >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    for %%V in (3.12 3.11 3.10 3) do (
        if not defined PY_CMD (
            py -%%V -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
            if !ERRORLEVEL! EQU 0 set "PY_CMD=py -%%V"
        )
    )
)
if not defined PY_CMD (
    where python >nul 2>nul
    if !ERRORLEVEL! EQU 0 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
        if !ERRORLEVEL! EQU 0 set "PY_CMD=python"
    )
)
if not defined PY_CMD (
    echo ERROR: Python 3.10 or newer was not found.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    call %PY_CMD% -m venv .venv
    if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!
".venv\Scripts\python.exe" -m pip install -r requirements-agent.txt
if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!
".venv\Scripts\python.exe" -m pip install -r requirements-dt-runner.txt
if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!

if "%SKIP_TESTS%"=="1" goto setup_complete
".venv\Scripts\python.exe" -m unittest tests.test_autonomous_runner tests.test_dt_runner_tool tests.test_udp_live_backend tests.test_tool_loop
if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!

:setup_complete
echo.
echo Setup complete.
echo Next: run_offline_smoke_test.bat
echo Then: start_assistant_gui.bat or run_matlab_comparison.bat
endlocal

