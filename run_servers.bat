@echo off
setlocal
set "IMS_ROOT=%~dp0"
call "%IMS_ROOT%run_server.bat" %*
exit /b %ERRORLEVEL%
