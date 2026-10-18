@echo off
chcp 65001 >nul
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_us37_mysql_uat.ps1"
if errorlevel 1 (
  echo.
  echo US37 MySQL UAT could not be started. Review the message above.
  pause
  exit /b 1
)
echo.
echo Open http://127.0.0.1:3000 to test.
pause
