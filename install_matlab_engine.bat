@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv was not found. Running setup first without tests...
    call "%~dp0setup_environment.bat" --no-tests
    if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!
)

set "MATLAB_ROOT=%MATLABROOT%"

if not defined MATLAB_ROOT (
    for %%R in (R2026b R2026a R2025b R2025a R2024b R2024a R2023b R2023a) do (
        if not defined MATLAB_ROOT (
            if exist "C:\Program Files\MATLAB\%%R\extern\engines\python" (
                set "MATLAB_ROOT=C:\Program Files\MATLAB\%%R"
            )
        )
    )
)

if not defined MATLAB_ROOT (
    echo.
    echo Could not auto-detect MATLAB.
    echo Enter the MATLAB root folder, for example:
    echo   C:\Program Files\MATLAB\R2024b
    set /p "MATLAB_ROOT=MATLAB root: "
)

set "MATLAB_ENGINE_DIR=%MATLAB_ROOT%\extern\engines\python"

if not exist "%MATLAB_ENGINE_DIR%" (
    echo.
    echo ERROR: MATLAB Engine Python folder was not found:
    echo   %MATLAB_ENGINE_DIR%
    echo.
    echo Check the MATLAB installation path and rerun this script.
    exit /b 1
)

echo.
echo Installing MATLAB Engine for Python from:
echo   %MATLAB_ENGINE_DIR%
echo.

".venv\Scripts\python.exe" -m pip install "%MATLAB_ENGINE_DIR%"
if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!

echo.
echo MATLAB Engine install complete.
echo You can test MATLAB Engine mode with a small run after MATLAB/Simulink dependencies are available.

endlocal
