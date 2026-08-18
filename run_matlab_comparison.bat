@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call "%~dp0setup_environment.bat" --no-tests
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
where matlab >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: matlab.exe is not on PATH.
    exit /b 1
)
matlab -batch "cd(fullfile('%CD%','Modules','Digital_Twins','comparison_experiment')); run_full_comparison"
endlocal

