"""
Re-assemble frames from an accord17_tap log, offline, with a configurable
idle-gap threshold.

WHY THIS EXISTS
  The v2/v3 firmware closes a frame after FRAME_GAP_US = 2000 us of idle. On
  the real car the INTER-BYTE gap is ~2.3 ms, which is LONGER than that, so
  every frame got chopped into 1-2 byte fragments. The bytes were all captured
  correctly -- only the grouping was wrong.

  This re-frames from the raw bytes in the log so the fix can be proven
  against real data BEFORE changing the firmware and asking for another drive.

Usage: python reframe_tap.py <log.csv> [--gap US]
"""
import sys, os, argparse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from honda_serial_model import chksm, wire_fields_to_value


def load_bytes(path):
    """Flatten the log back into two time-ordered byte streams."""
    streams = {"L": [], "E": []}
    for ln in open(path, errors="replace"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        f = ln.split(",")
        if len(f) < 11 or f[1] not in ("L", "E"):
            continue
        try:
            t = int(f[0]); n = int(f[4])
        except ValueError:
            continue
        bs = []
        for x in f[5:10]:
            if x == "na":
                continue
            try:
                bs.append(int(x, 16))
            except ValueError:
                pass
        # The record's span covers n bytes; spread them across it so each byte
        # carries its own approximate arrival time.
        try:
            span = int(f[3])
        except ValueError:
            span = 0
        step = (span // max(1, len(bs) - 1)) if len(bs) > 1 else 0
        for i, b in enumerate(bs[:n]):
            streams[f[1]].append((t + i * step, b))
    for k in streams:
        streams[k].sort()
    return streams


def reframe(stream, gap_us):
    """Same rule as the firmware: a frame starts on top-nibble<4, or after an
    idle longer than gap_us."""
    frames, cur, t0 = [], [], None
    for t, b in stream:
        boundary = (b >> 4) < 4 or (cur and (t - t0) > gap_us) or len(cur) >= 8
        if boundary and cur:
            frames.append((t0, cur))
            cur = []
        if not cur:
            t0 = t
        cur.append(b)
    if cur:
        frames.append((t0, cur))
    return frames


def score(frames, direction):
    lens = Counter(len(b) for _, b in frames)
    ok = bad = 0
    for _, b in frames:
        if direction == "L" and len(b) == 4:
            (ok, bad) = (ok + 1, bad) if chksm(b[0], b[1], b[2]) == b[3] else (ok, bad + 1)
        elif direction == "E" and len(b) == 5:
            (ok, bad) = (ok + 1, bad) if chksm(b[0], b[1], b[2], b[3]) == b[4] else (ok, bad + 1)
    return lens, ok, bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--gap", type=int, default=None)
    a = ap.parse_args()

    st = load_bytes(a.log)
    print(f"  bytes recovered:  L={len(st['L'])}  E={len(st['E'])}")
    print()

    gaps = [a.gap] if a.gap else [2000, 3000, 4000, 5000, 6000, 8000]
    print("  gap_us |  L frames (len histogram)      chk ok/bad |  E frames            chk ok/bad")
    print("  -------+---------------------------------------------------------------------------")
    for g in gaps:
        fl = reframe(st["L"], g); fe = reframe(st["E"], g)
        ll, lok, lbad = score(fl, "L")
        le, eok, ebad = score(fe, "E")
        print(f"  {g:6d} | {str(dict(sorted(ll.items()))):28s} {lok:6d}/{lbad:<5d}| "
              f"{str(dict(sorted(le.items()))):20s} {eok:6d}/{ebad}")

    g = a.gap or 4000
    print()
    print(f"  === decoded at gap={g} us ===")
    fl = reframe(st["L"], g)
    fe = reframe(st["E"], g)
    good = [(t, b) for t, b in fl if len(b) == 4 and chksm(b[0], b[1], b[2]) == b[3]]
    print(f"  LKAS->EPS frames with valid checksum: {len(good)}")
    if good:
        steers = [wire_fields_to_value(b[0] & 0x0F, b[1] & 0x1F) for _, b in good]
        print(f"    steer min/max : {min(steers)} / {max(steers)}")
        print(f"    lkasOn frames : {sum((b[1] >> 5) & 1 for _, b in good)} / {len(good)}")
        print(f"    byte2 census  : {dict(Counter(b[2] for _, b in good))}")
        print(f"    byte0 census  : {dict(Counter(b[0] for _, b in good))}")
        print(f"    byte1 census  : {dict(Counter(b[1] for _, b in good))}")
    gE = [(t, b) for t, b in fe if len(b) == 5 and chksm(b[0], b[1], b[2], b[3]) == b[4]]
    print(f"  EPS->LKAS frames with valid checksum: {len(gE)}")
    if gE:
        for i, col in enumerate(["b0", "b1", "b2", "b3"]):
            c = Counter(b[i] for _, b in gE)
            print(f"    {col} census    : {dict(sorted(c.items()))}")
