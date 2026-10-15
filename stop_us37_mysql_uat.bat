@echo off
chcp 65001 >nul
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_us37_mysql_uat.ps1"
if errorlevel 1 pause
