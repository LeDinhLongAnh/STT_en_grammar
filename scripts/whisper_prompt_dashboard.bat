@echo off
setlocal
set "ROOT=%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\experiments\whisper_initial_prompt\launch_dashboard.ps1"
if errorlevel 1 pause
endlocal
