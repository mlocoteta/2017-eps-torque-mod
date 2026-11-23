@echo off
REM ====================================================================
REM  accord17_tap -- is the board healthy?
REM
REM  Run this once after flashing, before driving. It answers PASS or
REM  FAIL in words. Nothing to read, nothing to compare.
REM ====================================================================
REM trailing "." : %~dp0 ends in a backslash which would otherwise escape
REM the closing quote and break cd on a path containing spaces.
cd /d "%~dp0."

echo.
echo  ================================================
echo   Teensy health check
echo  ================================================

python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [X] Python was not found.
  echo       Install Python 3 from https://www.python.org/downloads/
  echo       and tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 2
)

python -c "import serial" >nul 2>&1
if errorlevel 1 (
  echo   [..] installing pyserial, one moment
  python -m pip install --quiet pyserial
)

python check_teensy.py
set RC=%ERRORLEVEL%

if "%RC%"=="1" (
  echo   ^>^> Copy the text above and send it over. ^<^<
  echo.
)
pause
exit /b %RC%
