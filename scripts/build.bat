@echo off
rem ---------------------------------------------------------------------------
rem  build.bat - configure and build on Windows with MSVC.
rem
rem    scripts\build.bat              Release
rem    scripts\build.bat Debug
rem    scripts\build.bat Release test    build then run the unit tests
rem
rem  Needs Visual Studio 2022 (Build Tools are enough). The script locates
rem  vcvars64.bat itself via vswhere, so it works from a plain cmd prompt.
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion

set "CONFIG=%~1"
if "%CONFIG%"=="" set "CONFIG=Release"
set "RUN_TESTS=%~2"

set "ROOT=%~dp0.."
pushd "%ROOT%"

if not exist "third_party\sherpa-onnx\include\sherpa-onnx\c-api\c-api.h" (
  echo.
  echo sherpa-onnx is not installed yet. Run this first:
  echo     bash scripts/fetch_sherpa_onnx.sh
  echo.
  popd & exit /b 1
)

where cl.exe >nul 2>&1
if errorlevel 1 (
  set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
  if not exist "!VSWHERE!" (
    echo Cannot find vswhere.exe -- is Visual Studio 2022 installed?
    popd & exit /b 1
  )
  for /f "usebackq tokens=*" %%i in (`"!VSWHERE!" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSPATH=%%i"
  if "!VSPATH!"=="" (
    echo Visual Studio is installed but without the C++ toolset.
    echo Install "Desktop development with C++" and try again.
    popd & exit /b 1
  )
  call "!VSPATH!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 ( echo vcvars64.bat failed & popd & exit /b 1 )
)

cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=%CONFIG% 2>nul
if errorlevel 1 (
  echo Ninja not available, falling back to the Visual Studio generator.
  cmake -S . -B build -G "Visual Studio 17 2022" -A x64
  if errorlevel 1 ( popd & exit /b 1 )
  cmake --build build --config %CONFIG% --parallel
) else (
  cmake --build build --parallel
)
if errorlevel 1 ( popd & exit /b 1 )

echo.
echo Binaries in build\bin
if /i "%RUN_TESTS%"=="test" (
  echo.
  build\bin\vcc_tests.exe
  if errorlevel 1 ( popd & exit /b 1 )
)

popd
exit /b 0
