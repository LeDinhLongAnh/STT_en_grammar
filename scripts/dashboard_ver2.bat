@echo off
rem Launch Whisper Initial Prompt + Logit Bias Dashboard
rem
rem   scripts\dashboard_ver2.bat            -- launch with .venv (recommended)
rem   scripts\dashboard_ver2.bat --sys      -- force use system Python
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

rem --- Kiem tra logit_bias.py ---
set "LOGIT_BIAS=experiments\whisper_initial_prompt\logit_bias.py"
if not exist "%LOGIT_BIAS%" (
  echo.
  echo [LOI] Khong tim thay %LOGIT_BIAS%
  echo   Vui long kiem tra lai cai dat.
  echo.
  popd & exit /b 1
)

rem --- Kiem tra logit_bias.json ---
set "LOGIT_CFG=experiments\whisper_initial_prompt\logit_bias.json"
if not exist "%LOGIT_CFG%" (
  echo.
  echo [CANH BAO] Khong tim thay %LOGIT_CFG%
  echo   Logit bias se bi tat khi chay.
  echo.
)

rem --- Kiem tra file dashboard ver 2 ---
set "DASHBOARD=experiments\whisper_initial_prompt\dashboard_ver2.py"
if not exist "%DASHBOARD%" (
  echo.
  echo [LOI] Khong tim thay %DASHBOARD%
  echo.
  popd & exit /b 1
)

echo.
echo ============================================
echo  Whisper Initial Prompt + Logit Bias Lab
echo  Python   : %PYTHON%
echo  Dashboard: %DASHBOARD%
echo  Logit Bias Config: %LOGIT_CFG%
echo ============================================
echo.
echo  Mode 1: Khong prompt (baseline)
echo  Mode 2: Global Initial Prompt
echo  Mode 3: Global Prompt + Logit Bias  ^<-- DIEM CHINH
echo ============================================
echo.

"%PYTHON%" "%DASHBOARD%" %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
