@echo off
rem Launch the PyQt5 dashboard. It starts the engine itself.
rem
rem   scripts\dashboard.bat                 launch everything
rem   scripts\dashboard.bat --attach http://127.0.0.1:8777
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%"

if not exist "build\bin\vcc_engine.exe" (
  echo.
  echo The engine is not built yet. Run this first:
  echo     scripts\build.bat Release
  echo.
  popd & exit /b 1
)

set "PYTHON=experiments\whisper_initial_prompt\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo.
  echo Whisper dashboard environment is missing. Run:
  echo     powershell -ExecutionPolicy Bypass -File experiments\whisper_initial_prompt\setup.ps1 -DownloadModel
  echo.
  popd & exit /b 1
)

"%PYTHON%" dashboard\main.py %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
