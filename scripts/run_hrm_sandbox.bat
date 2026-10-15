@echo off
setlocal
set "BACKEND_DIR=%~dp0..\backend"
if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  echo [HRM Sandbox] Missing backend virtual environment: %BACKEND_DIR%\.venv
  echo Create it and install backend\requirements.txt first.
  pause
  exit /b 1
)
pushd "%BACKEND_DIR%"
".venv\Scripts\python.exe" -m app.hrm_sandbox
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" echo [HRM Sandbox] Service stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
