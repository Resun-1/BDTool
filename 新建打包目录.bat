@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HERE=%~dp0"
set "MAIN=%HERE%_core\NewPackFolder.py"

rem ==================================================================
rem  NewPackFolder launcher
rem  NOTE: keep this file ASCII-only. Chinese text is printed by the
rem        Python script (UTF-8 console), never by this batch file,
rem        otherwise cmd may garble it on a GBK system.
rem ==================================================================

if not exist "%MAIN%" (
  echo.
  echo [X] Missing file: %MAIN%
  echo     Keep the "_core" folder next to this .bat file.
  echo.
  pause
  exit /b 1
)

rem ---- locate Python 3 -------------------------------------------------
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY (
  for %%D in (
      "D:\Python3.14.7\python.exe"
      "D:\Python3.13\python.exe"
      "D:\Python3.12\python.exe"
      "C:\Python313\python.exe"
      "C:\Python312\python.exe"
      "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
      "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  ) do (
    if not defined PY if exist %%D set "PY=%%~D"
  )
)
if not defined PY (
  echo.
  echo [X] Python 3 not found.
  echo     Install Python 3 with "Add python.exe to PATH" checked, then retry.
  echo.
  pause
  exit /b 1
)

rem ---- dependency: pypinyin --------------------------------------------
%PY% -c "import pypinyin" >nul 2>nul
if errorlevel 1 (
  echo.
  echo [i] Installing dependency "pypinyin" for the first time ...
  %PY% -m pip install pypinyin
  echo.
)

rem ---- run --------------------------------------------------------------
%PY% "%MAIN%" %*
echo.
pause
