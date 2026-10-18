@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_hrm_sandbox.ps1"
if errorlevel 1 pause
exit /b %ERRORLEVEL%
