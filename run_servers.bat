@echo off
setlocal
set "IMS_ROOT=%~dp0"
cd /d "%IMS_ROOT%" || goto root_error

set "IMS_PYTHON=%IMS_ROOT%backend\.venv\Scripts\python.exe"
set "IMS_RETRIES=0"

echo ===================================================
echo     KHOI DONG HE THONG QUAN LY THUC TAP SINH
echo ===================================================

if not exist "%IMS_PYTHON%" goto python_error
if not exist "%IMS_ROOT%backend\.env" goto env_error
where node.exe >nul 2>&1
if errorlevel 1 goto node_error
where npm.cmd >nul 2>&1
if errorlevel 1 goto npm_error

if not exist "%IMS_ROOT%frontend\node_modules\vite\bin\vite.js" (
    echo Dang cai cac goi Frontend lan dau...
    pushd "%IMS_ROOT%frontend"
    call npm install --no-audit --no-fund
    if errorlevel 1 goto frontend_install_error
    popd
)

"%IMS_PYTHON%" -c "import fastapi, uvicorn, pymysql, cryptography, bcrypt, multipart"
if errorlevel 1 (
    echo Dang cai cac goi Backend theo requirements.txt...
    "%IMS_PYTHON%" -m pip install -r "%IMS_ROOT%backend\requirements.txt"
    if errorlevel 1 goto backend_install_error
)

echo Kiem tra MySQL service neu co...
powershell -NoProfile -Command "$svc = Get-Service -Name 'MySQL*' -ErrorAction SilentlyContinue | Select-Object -First 1; if ($svc -and $svc.Status -ne 'Running') { Start-Service -Name $svc.Name -ErrorAction Stop }; if ($svc -and (Get-Service -Name $svc.Name).Status -ne 'Running') { exit 1 }"
if errorlevel 1 goto mysql_service_error

echo Kiem tra ket noi database MySQL read-only...
"%IMS_PYTHON%" -c "from backend.app.database import get_db_connection; db=get_db_connection(); db.execute('SELECT 1').fetchone(); db.close(); print('MySQL connection OK')"
if errorlevel 1 goto mysql_connection_error

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if not errorlevel 1 goto backend_port_error
netstat -ano | findstr /R /C:":3000 .*LISTENING" >nul
if not errorlevel 1 goto frontend_port_error

echo Dang khoi dong Backend FastAPI tai http://127.0.0.1:8000 ...
start "IMS Backend - 8000" /D "%IMS_ROOT%" cmd /k ""%IMS_PYTHON%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

echo Dang khoi dong Frontend React tai http://127.0.0.1:3000 ...
start "IMS Frontend - 3000" /D "%IMS_ROOT%frontend" cmd /k "npm run dev -- --host 127.0.0.1 --port 3000 --strictPort"

echo Dang doi Backend khoi dong va khoi tao schema MySQL...
:wait_backend
"%IMS_PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2).read()" >nul 2>&1
if not errorlevel 1 goto backend_ready
set /a IMS_RETRIES+=1
if %IMS_RETRIES% GEQ 60 goto backend_start_error
timeout /t 1 /nobreak >nul
goto wait_backend

:backend_ready
echo Backend san sang. Frontend: http://127.0.0.1:3000
echo API docs: http://127.0.0.1:8000/docs
start "" "http://127.0.0.1:3000"
echo Cua so Backend va Frontend dang mo rieng; dong cua so se dung server tuong ung.
exit /b 0

:root_error
echo Khong the chuyen den thu muc du an: %~dp0
goto fail

:python_error
echo Thieu backend\.venv\Scripts\python.exe. Hay tao virtualenv va cai backend\requirements.txt.
goto fail

:env_error
echo Thieu backend\.env. Hay tao file nay tu backend\.env.example va dien cau hinh MySQL local.
goto fail

:node_error
echo Khong tim thay Node.js. Hay cai Node.js LTS va mo lai launcher.
goto fail

:npm_error
echo Khong tim thay npm. Kiem tra lai Node.js va PATH cua Windows.
goto fail

:frontend_install_error
popd
echo Khong cai duoc frontend dependencies. Kiem tra Node.js, npm va ket noi mang.
goto fail

:backend_install_error
echo Khong cai duoc backend dependencies. Kiem tra pip va ket noi mang.
goto fail

:mysql_service_error
echo Khong the khoi dong Windows service MySQL. Hay mo Services hoac chay launcher bang quyen Administrator.
goto fail

:mysql_connection_error
echo Backend khong ket noi duoc MySQL. Kiem tra backend\.env, MySQL service, user/password va database.
goto fail

:backend_port_error
echo Cong 8000 dang duoc su dung. Dong backend cu hoac giai phong cong truoc khi chay lai.
goto fail

:frontend_port_error
echo Cong 3000 dang duoc su dung. Dong frontend cu hoac giai phong cong truoc khi chay lai.
goto fail

:backend_start_error
echo Backend khong san sang sau 60 giay. Xem thong bao trong cua so IMS Backend - 8000.
goto fail

:fail
echo.
pause
exit /b 1
