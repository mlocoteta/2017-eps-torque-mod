@echo off
REM ====================================================================
REM  accord17_tap -- flash the Teensy 4.0 with the logger firmware
REM
REM  Fully self-contained. Needs NO Python, NO PlatformIO, NO Arduino,
REM  NO internet and NO driver install. Everything is in flash\.
REM
REM  Safe to run with the car off. Do NOT run it mid-drive: the Teensy
REM  reboots during programming and stops relaying for a second or two,
REM  which the EPS will see as a dropped link.
REM ====================================================================
REM trailing "." : %~dp0 ends in a backslash which would otherwise escape
REM the closing quote and break cd on a path containing spaces.
cd /d "%~dp0."

set HEX=flash\accord17_tap_v4.hex
set LOADER=flash\teensy_loader_cli.exe

echo.
echo  ================================================
echo   FLASH the Teensy 4.0  --  accord17_tap v4
echo  ================================================
echo.

if not exist "%LOADER%" (
  echo   [X] missing %LOADER%
  echo       Copy the WHOLE portable_logger folder, not just this file.
  pause
  exit /b 1
)
if not exist "%HEX%" (
  echo   [X] missing %HEX%
  echo       Copy the WHOLE portable_logger folder, not just this file.
  pause
  exit /b 1
)
echo   [ok] loader and firmware present
echo.
echo   This REPLACES whatever is on the Teensy.
echo   A Teensy 4.0 cannot be read back, so there is no undo.
echo   The firmware being written is a passive tap - it only listens.
echo.
set /p GO="  Type  yes  to flash, anything else to cancel: "
if /i not "%GO%"=="yes" (
  echo.
  echo   Cancelled. Nothing was written.
  echo.
  pause
  exit /b 0
)

echo.
echo   Step 1 of 2: asking the Teensy to enter program mode...
REM best effort - it just prints a notice if it cannot find a board.
REM -s on the loader is a no-op on Windows ("Soft reboot is not
REM implemented for Win32"), so this helper does that job instead.
flash\teensy_reboot.exe
echo.
echo   Step 2 of 2: programming.
echo.
echo   *** If it sits on "Waiting for Teensy device", PRESS THE   ***
echo   *** SMALL BUTTON ON THE TEENSY ONCE. That always works.    ***
echo.

"%LOADER%" --mcu=TEENSY40 -w -v "%HEX%"
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo  ================================================
  echo   DONE. Firmware flashed.
  echo.
  echo   Check it worked: run START_LOGGER.bat. It should
  echo   say  [ok] Teensy on COMx  and the log header
  echo   should read  accord17_tap v4
  echo  ================================================
) else (
  echo  ================================================
  echo   FAILED - exit code %RC%. Nothing may have changed.
  echo.
  echo   Try, in this order:
  echo     1. press the small button on the Teensy, run this again
  echo     2. different USB cable - it must be a DATA cable
  echo     3. different USB port
  echo  ================================================
)
echo.
pause
