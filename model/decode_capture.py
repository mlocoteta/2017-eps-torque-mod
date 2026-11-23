"""
Decode the reddn/AccordManualSteering stock LKAS captures using the byte-exact
protocol mirror in honda_serial_model.py.

Log format (one frame per line):
    <4 LKAS->EPS bytes as "nnnn nnnn" groups> [^] <5 EPS->LKAS bytes> [trailing 0]
optionally prefixed by a quoted timestamp.

Purpose: answer, from STOCK data, what magnitudes the factory camera ever
commands -- which is the cheapest possible test of the "~230 errors" ceiling.
"""
import sys, os, re, glob
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from honda_serial_model import chksm, wire_fields_to_value, calculate_steer_torque


def parse_line(line):
    line = line.strip()
    if not line:
        return None
    line = re.sub(r'^"[^"]*",', '', line)          # drop timestamp column
    line = line.replace('^', ' ')                   # drop the reformat separator
    bits = re.findall(r'[01]{4}', line)
    if len(bits) < 8:
        return None
    by = [int(bits[i] + bits[i + 1], 2) for i in range(0, len(bits) - 1, 2)]
    lkas = by[0:4]
    eps = by[4:9] if len(by) >= 9 else None
    return lkas, eps


def decode(path):
    rows = []
    bad_sync = bad_chk = 0
    with open(path, 'r', errors='replace') as f:
        for line in f:
            p = parse_line(line)
            if not p:
                continue
            lkas, eps = p
            if (lkas[0] >> 4) >= 4:
                bad_sync += 1
                continue
            if chksm(lkas[0], lkas[1], lkas[2]) != lkas[3]:
                bad_chk += 1
            steerB1 = lkas[0] & 0x0F
            steerB0 = lkas[1] & 0x1F
            rows.append({
                'counter': lkas[0] >> 5,
                'steer':   wire_fields_to_value(steerB1, steerB0),
                'lkasOn':  (lkas[1] >> 5) & 1,
                'b2':      lkas[2],
                'driver':  calculate_steer_torque(eps[0], eps[1]) if eps else None,
                'eps':     eps,
            })
    return rows, bad_sync, bad_chk


if __name__ == "__main__":
    logs = sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "*.txt"))
    all_steer = Counter()
    all_b2 = Counter()
    for path in logs:
        rows, bad_sync, bad_chk = decode(path)
        if not rows:
            continue
        steers = [r['steer'] for r in rows]
        drivers = [r['driver'] for r in rows if r['driver'] is not None]
        all_steer.update(steers)
        all_b2.update(r['b2'] for r in rows)
        print("=" * 70)
        print(os.path.basename(path))
        print("=" * 70)
        print(f"  frames            : {len(rows)}")
        print(f"  checksum FAILURES : {bad_chk}   (bad sync skipped: {bad_sync})")
        print(f"  LKAS-on frames    : {sum(r['lkasOn'] for r in rows)}")
        print(f"  byte2 values seen : {sorted(set(r['b2'] for r in rows))}")
        print(f"  steer  min/max    : {min(steers)} / {max(steers)}")
        print(f"  |steer| max       : {max(abs(s) for s in steers)}")
        if drivers:
            print(f"  driver raw min/max: {min(drivers)} / {max(drivers)}")
        # counter sequence sanity
        cs = [r['counter'] for r in rows]
        alt = sum(1 for a, b in zip(cs, cs[1:]) if a == b)
        print(f"  counter non-alternating transitions: {alt}/{len(cs)-1}")
        print()

    print("=" * 70)
    print("AGGREGATE -- what does the STOCK camera ever command?")
    print("=" * 70)
    mags = Counter()
    for v, n in all_steer.items():
        mags[abs(v)] += n
    total = sum(mags.values())
    print(f"  total frames            : {total}")
    print(f"  max |steer| EVER seen   : {max(mags)}")
    print(f"  distinct |steer| values : {len(mags)}")
    print(f"  byte2 census            : {dict(all_b2)}")
    print()
    print("  |steer| distribution (top 20 by frequency):")
    for v, n in mags.most_common(20):
        print(f"    {v:4d}  {n:6d}  {100.0*n/total:5.1f}%  {'#' * min(40, n * 40 // max(mags.values()))}")
    print()
    print("  largest |steer| values observed:")
    for v in sorted(mags)[-12:]:
        print(f"    {v:4d}  x{mags[v]}")
