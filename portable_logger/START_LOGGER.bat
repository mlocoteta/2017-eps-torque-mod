@echo off
REM ====================================================================
REM  accord17_tap -- PORTABLE LKAS/EPS serial logger
REM  Copy this WHOLE FOLDER to any Windows laptop and double-click here.
REM  Needs only: Python 3 installed and ticked "Add to PATH".
REM  Everything else it checks for and installs itself.
REM ====================================================================
REM the trailing "." matters: %~dp0 ends in a backslash, which would
REM otherwise escape the closing quote and break cd on a path with spaces.
cd /d "%~dp0."

echo.
echo  ================================================
echo   2017 Accord  LKAS/EPS  serial logger
echo  ================================================
echo.
echo   This only LISTENS. It cannot steer the car.
echo.

REM ---- 1. is Python there at all? ------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
  echo   [X] Python was not found.
  echo.
  echo       Install Python 3 from https://www.python.org/downloads/
  echo       IMPORTANT: tick "Add python.exe to PATH" in the installer.
  echo       Then run this file again.
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo   [ok] %%v

REM ---- 2. is pyserial there? install it if not ------------------------
python -c "import serial" >nul 2>&1
if errorlevel 1 (
  echo   [..] installing pyserial, one moment
  python -m pip install --quiet pyserial
  python -c "import serial" >nul 2>&1
  if errorlevel 1 (
    echo   [X] could not install pyserial. Are you online?
    pause
    exit /b 1
  )
)
echo   [ok] pyserial

REM ---- 3. can we see the Teensy? --------------------------------------
python -c "import sys;from serial.tools import list_ports;t=[p for p in list_ports.comports() if p.vid==0x16C0];print('  [ok] Teensy on '+t[0].device) if t else (sys.stdout.write('  [X] no Teensy found\n'),sys.exit(1))"
if errorlevel 1 (
  echo.
  echo       Nothing with the PJRC USB id is plugged in.
  echo       - is the USB cable a DATA cable, not charge-only?
  echo       - is the Teensy powered?
  echo       You can still continue; it will fail to open a port.
  echo.
)

echo.
set /p RUNNAME="  Name this run - e.g. baseline or lanedepart: "
if "%RUNNAME%"=="" set RUNNAME=run

echo.
python capture_tap.py --name "%RUNNAME%" --out "%~dp0logs"

echo.
echo  ================================================
echo   Done. Your file is in the  logs  folder
echo   next to this one. Send that file over.
echo  ================================================
echo.
pause
