@echo off
rem Launch Whisper Initial Prompt Dashboard (PyQt5)
rem
rem   scripts\dashboard.bat            -- launch with .venv (recommended)
rem   scripts\dashboard.bat --sys      -- force use system Python
setlocal

set "ROOT=%~dp0.."
pushd "%ROOT%"

rem --- Chon Python ---
set "VENV_PYTHON=experiments\whisper_initial_prompt\.venv\Scripts\python.exe"
if "%1"=="--sys" (
  set "PYTHON=python"
) else if exist "%VENV_PYTHON%" (
  set "PYTHON=%VENV_PYTHON%"
) else (
  echo.
  echo [CANH BAO] Khong tim thay .venv. Dung system Python.
  echo   Neu can cai dat: powershell -File experiments\whisper_initial_prompt\setup.ps1
  echo.
  set "PYTHON=python"
)

rem --- Kiem tra file dashboard chinh ---
set "DASHBOARD=experiments\whisper_initial_prompt\dashboard.py"
if not exist "%DASHBOARD%" (
  echo.
  echo [LOI] Khong tim thay %DASHBOARD%
  echo.
  popd & exit /b 1
)

echo.
echo ============================================
echo  Whisper Initial Prompt Dashboard
echo  Python : %PYTHON%
echo  File   : %DASHBOARD%
echo ============================================
echo.

"%PYTHON%" "%DASHBOARD%" %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
