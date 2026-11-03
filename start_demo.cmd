@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_demo.ps1" %*
exit /b %ERRORLEVEL%
