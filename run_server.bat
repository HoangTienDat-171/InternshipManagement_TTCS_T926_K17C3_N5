@echo off
chcp 65001 >nul
setlocal
set "IMS_ROOT=%~dp0"
cd /d "%IMS_ROOT%"

set "IMS_PYTHON=%IMS_ROOT%backend\.venv\Scripts\python.exe"
if not exist "%IMS_PYTHON%" (
    where python.exe >nul 2>&1
    if not errorlevel 1 (
        set "IMS_PYTHON=python.exe"
    ) else (
        echo =========================================
        echo  INTERNSHIP MANAGEMENT - SERVER STARTUP
        echo =========================================
        echo [1/5] Checking environment...     FAILED
        echo =========================================
        echo  ERROR: KHONG TIM THAY PYTHON
        echo =========================================
        echo Khong tim thay Python tai backend\.venv\Scripts\python.exe va trong PATH.
        echo Vui long cai dat Python 3.10+ va tao virtualenv truoc khi khoi dong.
        echo =========================================
        echo.
        pause
        exit /b 1
    )
)

"%IMS_PYTHON%" "%IMS_ROOT%scripts\launcher.py" start %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Nhan phim bat ky de thoat...
    pause >nul
    exit /b %EXIT_CODE%
)

echo.
echo [Tip] De dung he thong an toan, hay chay: stop_server.bat
if "%~1"=="--no-pause" goto finish
if "%~2"=="--no-pause" goto finish
echo Nhan phim bat ky de dong launcher (server van tiep tuc chay ngam)...
pause >nul

:finish
exit /b 0
