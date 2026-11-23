"""
capture_tap.py -- save the accord17_tap stream from the Teensy 4.0 to a file.

In-car usage (nothing to configure):

    python analysis-2017accord/tools/capture_tap.py

It finds the Teensy, opens a timestamped log under analysis-2017accord/logs/,
writes every line straight through, and shows a live one-line status so you can
tell at a glance that the tap is healthy while you drive.

    --port COM7     pick the port explicitly
    --name baseline label the file (becomes 2026-11-12_143052_baseline.csv)
    --raw           no live stats, just dump (lowest possible overhead)

While it runs, press ENTER to drop a MARK into the log from the keyboard --
same effect as PB1-PB4 on the debug board, for when the buttons are out of
reach. Ctrl-C stops cleanly and prints a summary.

The file is flushed every FLUSH_SEC seconds AND fsync'd, so yanking the USB
cable loses at most that much data.
"""
import argparse, os, sys, time, threading, queue
from datetime import datetime

import serial
from serial.tools import list_ports

HERE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.normpath(os.path.join(HERE, "..", "logs"))
FLUSH_SEC = 2.0


def find_port():
    """Teensy enumerates as VID 0x16C0 (PJRC). Fall back to anything plausible."""
    cands = list(list_ports.comports())
    for p in cands:
        if p.vid == 0x16C0:
            return p.device
    for p in cands:
        d = (p.description or "").lower()
        if "teensy" in d or "usb serial" in d:
            return p.device
    if len(cands) == 1:
        return cands[0].device
    print("Could not pick a port automatically. Candidates:")
    for p in cands:
        print(f"   {p.device:12s} vid={p.vid} {p.description}")
    print("Re-run with --port COMx")
    return None


class Stats:
    """Running health summary. Deliberately cheap -- this runs in the car."""
    def __init__(self):
        self.lines = self.L = self.E = self.marks = 0
        self.dropped = self.overruns = 0
        self.max_mag = 0
        self.last_steer = 0
        self.bad_chk = 0
        self.t_start = time.time()
        self.gaps = []

    def feed(self, line):
        self.lines += 1
        if line.startswith("#"):
            return
        f = line.split(",")
        if len(f) < 12:
            return
        d = f[1]
        if d == "MARK":
            self.marks += 1
            return
        if d == "L":
            self.L += 1
            try:
                b0 = int(f[5], 16); b1 = int(f[6], 16)
                b2 = int(f[7], 16); b3 = int(f[8], 16)
            except ValueError:
                return
            v = ((b0 & 0x07) << 5) | (b1 & 0x1F)
            if (b0 >> 3) & 1:
                v -= 256
            self.last_steer = v
            self.max_mag = max(self.max_mag, abs(v))
            ck = (256 - ((b0 + b1 + b2) & 0xFF)) & 0xFF
            ck = ck % 128 + 128
            if ck != b3:
                self.bad_chk += 1
            if len(self.gaps) < 4000:
                try:
                    g = int(f[2])
                    if g:
                        self.gaps.append(g)
                except ValueError:
                    pass
        elif d == "E":
            self.E += 1
        try:
            self.overruns = max(self.overruns, int(f[10]))
            self.dropped = max(self.dropped, int(f[11]))
        except (ValueError, IndexError):
            pass

    def line(self):
        el = max(1e-6, time.time() - self.t_start)
        hz = self.L / el
        med = 0
        if self.gaps:
            g = sorted(self.gaps)
            med = g[len(g) // 2]
        warn = ""
        if self.dropped:
            warn += f"  DROPPED {self.dropped}"
        if self.overruns:
            warn += f"  OVERRUN {self.overruns}"
        if self.bad_chk:
            warn += f"  BADCHK {self.bad_chk}"
        return (f"\r{el:6.1f}s  L={self.L:<7d} E={self.E:<7d} {hz:5.1f}Hz "
                f"(period {med}us)  steer={self.last_steer:+4d} "
                f"peak|{self.max_mag}|  marks={self.marks}{warn}   ")

    def summary(self):
        el = max(1e-6, time.time() - self.t_start)
        return (f"\n  duration        : {el:.1f}s\n"
                f"  LKAS->EPS frames: {self.L}\n"
                f"  EPS->LKAS frames: {self.E}\n"
                f"  marks           : {self.marks}\n"
                f"  peak |steer|    : {self.max_mag}\n"
                f"  checksum bad    : {self.bad_chk}\n"
                f"  dropped records : {self.dropped}   (ring overflow on the Teensy)\n"
                f"  frame overruns  : {self.overruns}   (desync on the link)\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--name", default="")
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--out", default=None,
                    help="directory for the log file (default: ../logs). The "
                         "portable copy passes its own folder, so this script "
                         "works both inside the repo and standalone.")
    a = ap.parse_args()

    global LOGDIR
    if a.out:
        LOGDIR = os.path.abspath(a.out)

    port = a.port or find_port()
    if not port:
        return 2

    os.makedirs(LOGDIR, exist_ok=True)
    tag = ("_" + a.name) if a.name else ""
    path = os.path.join(LOGDIR, datetime.now().strftime("%Y-%m-%d_%H%M%S") + tag + ".csv")

    try:
        # serial_for_url accepts a plain COM name exactly like Serial() does,
        # and additionally accepts test URLs such as loop:// -- which is how
        # this script gets exercised when no Teensy is plugged in.
        ser = serial.serial_for_url(port, baudrate=921600, timeout=0.2)
    except (serial.SerialException, ValueError) as e:
        print(f"could not open {port}: {e}")
        return 2

    print(f"port   : {port}")
    print(f"saving : {path}")
    print("ENTER = mark    q+ENTER or Ctrl-C = stop\n")

    marks = queue.Queue()

    stop = threading.Event()

    def keywatch():
        """ENTER drops a mark; 'q'+ENTER stops. Ctrl-C also works, but a
        plain 'q' is easier to hit reliably from the driver's seat."""
        try:
            for ln in sys.stdin:
                if ln.strip().lower() in ("q", "quit", "stop"):
                    stop.set()
                    return
                marks.put(b"m")
        except Exception:
            pass

    threading.Thread(target=keywatch, daemon=True).start()

    st = Stats()
    last_flush = last_draw = time.time()
    buf = b""

    with open(path, "wb") as fh:
        fh.write(f"# captured {datetime.now().isoformat()} from {port}\n".encode())
        try:
            while not stop.is_set():
                chunk = ser.read(4096)
                if chunk:
                    fh.write(chunk)
                    if not a.raw:
                        buf += chunk
                        while b"\n" in buf:
                            ln, buf = buf.split(b"\n", 1)
                            st.feed(ln.decode("ascii", "replace").strip())

                while not marks.empty():
                    marks.get()
                    ser.write(b"m")

                now = time.time()
                if now - last_flush > FLUSH_SEC:
                    fh.flush()
                    os.fsync(fh.fileno())
                    last_flush = now
                if not a.raw and now - last_draw > 0.25:
                    sys.stdout.write(st.line())
                    sys.stdout.flush()
                    last_draw = now
        except KeyboardInterrupt:
            pass
        finally:
            fh.flush()
            os.fsync(fh.fileno())
            ser.close()

    print("\n\nsaved:", path)
    if not a.raw:
        print(st.summary())
    print("decode with:")
    print(f"  python analysis-2017accord/model/decode_tap_csv.py \"{path}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
