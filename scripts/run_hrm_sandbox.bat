@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_hrm_sandbox.ps1"
exit /b %ERRORLEVEL%
