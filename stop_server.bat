@echo off
chcp 65001 >nul
setlocal
set "IMS_ROOT=%~dp0"
if defined IMS_ACTIVE_SOURCE if exist "%IMS_ACTIVE_SOURCE%\scripts\launcher.py" set "IMS_ROOT=%IMS_ACTIVE_SOURCE%\"
if not defined IMS_CONFIG_ROOT set "IMS_CONFIG_ROOT=%~dp0"
cd /d "%IMS_ROOT%"

set "IMS_PYTHON=%IMS_ROOT%backend\.venv\Scripts\python.exe"
if not exist "%IMS_PYTHON%" (
    where python.exe >nul 2>&1
    if not errorlevel 1 (
        set "IMS_PYTHON=python.exe"
    ) else (
        echo Khong tim thay Python de thuc hien dung server.
        pause
        exit /b 1
    )
)

"%IMS_PYTHON%" "%IMS_ROOT%scripts\launcher.py" stop %*
set "EXIT_CODE=%ERRORLEVEL%"

if "%~1"=="--no-pause" goto finish
if "%~2"=="--no-pause" goto finish
echo.
echo Nhan phim bat ky de dong cua so...
pause >nul

:finish
exit /b %EXIT_CODE%
