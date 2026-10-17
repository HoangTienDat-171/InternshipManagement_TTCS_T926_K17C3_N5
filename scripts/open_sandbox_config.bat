@echo off
chcp 65001 >nul
setlocal
if not defined IMS_CONFIG_ROOT set "IMS_CONFIG_ROOT=%~dp0.."
for %%I in ("%IMS_CONFIG_ROOT%") do set "IMS_CONFIG_ROOT=%%~fI"
set "ENV_FILE=%IMS_CONFIG_ROOT%\backend\.env"
if not exist "%ENV_FILE%" (
    echo Khong tim thay file cau hinh local: %ENV_FILE%
    exit /b 1
)
where code >nul 2>&1
if not errorlevel 1 (
    start "" code --reuse-window "%ENV_FILE%"
) else (
    start "" notepad.exe "%ENV_FILE%"
)
exit /b 0
