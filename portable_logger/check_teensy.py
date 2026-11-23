"""
check_teensy.py -- is the board healthy? Answers PASS or FAIL in words.

Replaces "open the logger a few times and watch whether uptime_us climbs",
which asked you to eyeball a microsecond counter scrolling past. It opens the
port, reads the header, waits, opens it again, and compares for you.

What it is actually testing
  1. The firmware is alive and is the version we think it is.
  2. The board is NOT rebooting. The v3 watchdog is new and untested on
     hardware; if it is misconfigured the board resets every 0.5 s and the
     steering link dies with it. Uptime going UP across two reads proves it
     is not resetting. Uptime near zero twice proves it is.
  3. The reset cause the firmware latched at boot. "WATCHDOG_RESET" means it
     already rebooted once -- the watchdog must come out.

Usage:  python check_teensy.py [--port COM5] [--wait 6]
Exit code 0 = PASS, 1 = FAIL, 2 = could not test.
"""
import argparse, re, sys, time

import serial
from serial.tools import list_ports

BAUD = 921600


def find_port():
    for p in list_ports.comports():
        if p.vid == 0x16C0:
            return p.device
    return None


def human(us):
    s = us / 1e6
    if s < 90:
        return f"{s:.1f} seconds"
    if s < 5400:
        return f"{s/60:.1f} minutes"
    return f"{s/3600:.1f} hours"


def read_banner(port, settle=2.5):
    """Open the port and collect the header the firmware emits on attach."""
    with serial.serial_for_url(port, baudrate=BAUD, timeout=0.3) as ser:
        buf = b""
        t = time.time()
        while time.time() - t < settle:
            buf += ser.read(4096)
            if b"uptime_us=" in buf and buf.rstrip().endswith(b"\n"):
                break
    txt = buf.decode("ascii", "replace")
    info = {"raw": txt}
    m = re.search(r"accord17_tap (v\d+)", txt)
    info["version"] = m.group(1) if m else None
    m = re.search(r"uptime_us=(\d+)", txt)
    info["uptime"] = int(m.group(1)) if m else None
    m = re.search(r"wrsr=0x([0-9A-Fa-f]+)", txt)
    info["wrsr"] = int(m.group(1), 16) if m else None
    info["watchdog_reset"] = "WATCHDOG_RESET" in txt
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--wait", type=float, default=6.0)
    a = ap.parse_args()

    print()
    print("  Checking the Teensy. This takes about %d seconds." % (a.wait + 6))
    print()

    port = a.port or find_port()
    if not port:
        print("  CANNOT TEST -- no Teensy found on USB.")
        print("    - is it plugged in?")
        print("    - is the cable a DATA cable, not charge-only?")
        print()
        return 2

    print(f"  Found it on {port}.")

    try:
        first = read_banner(port)
    except Exception as e:
        print(f"  CANNOT TEST -- could not open {port}: {e}")
        print("    Is START_LOGGER.bat still running? Close it first.")
        print()
        return 2

    if first["uptime"] is None:
        print("  CANNOT TEST -- the board did not send its header.")
        print("    It may be running older firmware. Try FLASH_TEENSY.bat.")
        print()
        print("    what it did send:")
        for ln in (first["raw"] or "(nothing)").splitlines()[:6]:
            print("      " + ln)
        print()
        return 2

    print(f"  Firmware    : {first['version'] or 'unknown'}")
    print(f"  Running for : {human(first['uptime'])}")
    if first["wrsr"] is not None:
        cause = "power-on" if (first["wrsr"] & 0x10) else \
                "WATCHDOG" if (first["wrsr"] & 0x02) else \
                "software" if (first["wrsr"] & 0x01) else "unknown"
        print(f"  Last reset  : {cause}  (wrsr=0x{first['wrsr']:X})")
    print()
    print(f"  Waiting {a.wait:.0f}s, then checking again...")
    time.sleep(a.wait)

    try:
        second = read_banner(port)
    except Exception as e:
        print(f"  CANNOT TEST -- second read failed: {e}")
        print()
        return 2

    if second["uptime"] is None:
        print("  CANNOT TEST -- no header on the second read.")
        print()
        return 2

    grew = second["uptime"] - first["uptime"]
    print(f"  Running for : {human(second['uptime'])}")
    print()

    problems = []
    if first["watchdog_reset"] or second["watchdog_reset"]:
        problems.append("The board REBOOTED from a watchdog timeout.")
    if second["uptime"] < first["uptime"]:
        problems.append("Uptime went BACKWARDS - the board reset between reads.")
    elif grew < a.wait * 1e6 * 0.5:
        problems.append(
            f"Uptime only advanced {human(grew)} over {a.wait:.0f}s of waiting "
            "- the board is resetting.")

    print("  " + "=" * 52)
    if problems:
        print("   FAIL")
        print("  " + "=" * 52)
        for p in problems:
            print("    - " + p)
        print()
        print("    The 0.5s watchdog added in v3 is the likely cause and it")
        print("    is NOT safe to drive with: a board that reboots in a loop")
        print("    stops relaying, which the EPS sees as a dropped link.")
        print()
        print("    Send this output back and the watchdog gets removed.")
        print()
        return 1

    print("   PASS - the board is stable, not rebooting.")
    print("  " + "=" * 52)
    print()
    print(f"    Uptime advanced by {human(grew)} across the two reads,")
    print("    which is what it should do. Safe to drive.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
