@echo off
set "PATH=C:\Program Files\nodejs;%PATH%"
echo ===================================================
echo     KHOI DONG HE THONG QUAN LY THUC TAP SINH
echo ===================================================
echo Dang khoi dong Backend FastAPI tai http://127.0.0.1:8000 ...
start "Backend FastAPI" cmd /k ".\backend\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

echo Dang khoi dong Frontend React tai http://127.0.0.1:3000 ...
cd frontend
start "Frontend React" cmd /k "npm run dev -- --host 127.0.0.1 --port 3000"

echo.
echo Da bat ca 2 server:
echo - Frontend: http://127.0.0.1:3000
echo - Backend API Docs: http://127.0.0.1:8000/docs
echo ===================================================
pause
