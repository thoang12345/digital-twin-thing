@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call "%~dp0setup_environment.bat"
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
if not exist "logs" mkdir logs
".venv\Scripts\python.exe" run_dt_runner.py ^
  --backend mock ^
  --policy heuristic ^
  --tick-seconds 1 ^
  --startup-grace-seconds 0 ^
  --max-sim-seconds 5 ^
  --success-hold-seconds 999 ^
  --bus-nominal 400 ^
  --max-p-batt 500 ^
  --max-p-batt-step 500 ^
  --csv ".\logs\dt_runner_mock_smoke.csv" ^
  --report ".\logs\dt_runner_mock_smoke_report.md"
echo Report: %CD%\logs\dt_runner_mock_smoke_report.md
endlocal

