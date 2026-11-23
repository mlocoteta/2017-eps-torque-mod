accord17_tap -- portable LKAS/EPS serial logger
2016/2017 Honda Accord

WHAT THIS IS
  A passive wire tap. It copies every byte between the LKAS camera and the
  power steering, in both directions, and writes a note about each one.
  It cannot steer the car. There is exactly one write to a car-facing wire
  in the whole firmware, and the thing it writes is the byte the car itself
  just sent.

====================================================================
 TWO BUTTONS. THAT IS THE WHOLE INTERFACE.
====================================================================

  START_LOGGER.bat    record a drive        <-- the one you use
  CHECK_TEENSY.bat    is the board OK?      <-- run once after flashing
  FLASH_TEENSY.bat    put firmware on the Teensy (rarely)

--------------------------------------------------------------------
 START_LOGGER.bat -- record a drive
--------------------------------------------------------------------
  1. Plug the Teensy into the laptop with a DATA usb cable.
  2. Double-click START_LOGGER.bat
  3. Type a name for the run, press Enter.
  4. Watch the numbers. L= and E= should both climb at ~100Hz.
       both 0        -> nothing reaching the tap, check wiring
       DROPPED       -> laptop too slow, log has gaps
       OVERRUN       -> the serial link desynced
       BADCHK        -> corrupt frames
     Any of those three and the log is unreliable.
  5. Press Enter any time something happens - it stamps that exact
     moment into the log so it can be found later.
  6. Type  q  then Enter to stop.
  7. Send the file from the  logs  folder.

  Needs Python 3 installed with "Add python.exe to PATH" ticked.
  pyserial installs itself on first run.

--------------------------------------------------------------------
 CHECK_TEENSY.bat -- is the board OK?
--------------------------------------------------------------------
  Run this ONCE after flashing, before driving. Takes ~12 seconds
  and answers PASS or FAIL in plain words. Nothing to read or
  compare yourself.

  It checks that the board is not rebooting. The 0.5s watchdog added
  in v3 is new; if it were misconfigured the board would reset over
  and over, stop relaying, and the EPS would see a dropped link.

  PASS -> safe to drive.
  FAIL -> do not drive. Copy the text and send it over; the
          watchdog comes back out.

  Close START_LOGGER.bat first - only one program can hold the
  port at a time.

--------------------------------------------------------------------
 FLASH_TEENSY.bat -- put firmware on the Teensy
--------------------------------------------------------------------
  Only needed to install or update the logger firmware.
  Needs NOTHING installed - no Python, no internet, no driver.

  1. Car OFF. Do not flash mid-drive: the Teensy reboots while
     programming and stops relaying for a second or two, which the
     EPS sees as a dropped link.
  2. Plug the Teensy into the laptop.
  3. Double-click FLASH_TEENSY.bat, type  yes
  4. If it sits on "Waiting for Teensy device", PRESS THE SMALL
     BUTTON ON THE TEENSY ONCE. That always works.
  5. Confirm: run CHECK_TEENSY.bat. It should say PASS.

  A Teensy 4.0 CANNOT be read back, so flashing has no undo. The
  firmware source lives in the accord-eps-torque-mod repo under
  analysis-2017accord/teensy_logger/ - that is the only backup.

====================================================================

WHAT IS IN HERE
  START_LOGGER.bat   record a drive
  CHECK_TEENSY.bat   health check, says PASS or FAIL
  FLASH_TEENSY.bat   flash the Teensy
  capture_tap.py     the logger (copy of analysis-2017accord/tools/)
  check_teensy.py    the health check
  flash/             loader + firmware image, self-contained
  logs/              your captures land here
  README.txt         this file

FIRMWARE ON THE BOARD
  accord17_tap v3    flash/accord17_tap_v3.hex
                     sha256 d5d139d4a01a6a0511ef40f51c2e137c0be19dac
                            64d48ad0feba68ee35c420f8

  v3 fixed three ways the relay could stall: a 2ms delay in the main
  loop on host attach, an unguarded blocking print of the log header,
  and a 300ms delay at boot while the UARTs were already receiving.
  v3 also adds a 0.5s hardware watchdog so a hang reboots instead of
  killing the link for the rest of the drive, and reports the reset
  cause in the log header ("WATCHDOG_RESET" if it rebooted).

SOURCE OF TRUTH
  capture_tap.py here is a COPY for portability. The maintained
  original is analysis-2017accord/tools/capture_tap.py in the
  accord-eps-torque-mod repo. If you change one, change both.
