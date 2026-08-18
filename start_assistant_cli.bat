@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call "%~dp0setup_environment.bat"
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
".venv\Scripts\python.exe" assistant_cli.py %*
endlocal

