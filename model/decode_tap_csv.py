"""
Decode a capture from the accord17_tap Teensy logger.

Usage:  python decode_tap_csv.py <log.csv> [--frames N]

Input columns: t_us,dir,gap_us,span_us,n,b0,b1,b2,b3,b4,parity_err,overruns
All interpretation is done here, against the byte-exact mirror, so the logger
firmware and the analysis can never silently diverge.
"""
import sys, os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from honda_serial_model import chksm, wire_fields_to_value, calculate_steer_torque


def load(path):
    L, E, marks = [], [], []
    for ln in open(path, errors='replace'):
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        f = ln.split(',')
        if len(f) < 12:
            continue
        if f[1] == 'MARK':
            marks.append((int(f[0]), f[12] if len(f) > 12 else '?'))
            continue
        try:
            rec = dict(t=int(f[0]), dir=f[1], gap=int(f[2]), span=int(f[3]),
                       n=int(f[4]),
                       b=[int(x, 16) for x in f[5:10] if x != 'na'],
                       perr=int(f[10]), ovr=int(f[11]))
        except ValueError:
            continue
        (L if rec['dir'] == 'L' else E).append(rec)
    return L, E, marks


def is_fragmented(L):
    """v2/v3 firmware used FRAME_GAP_US=2000, shorter than the car's real
    ~2.0 ms inter-byte gap, so frames arrive chopped into 1-2 byte pieces.
    The BYTES are all correct -- only the grouping is wrong -- so such a log
    is fully recoverable offline and needs no re-drive."""
    if not L:
        return False
    short = sum(1 for r in L if r["n"] < 4)
    return short > len(L) * 0.25


def report(path, nframes=None):
    L, E, marks = load(path)

    if is_fragmented(L):
        print("  NOTE: this log came from firmware whose frame-gap timeout was")
        print("        shorter than the car's inter-byte gap, so frames are")
        print("        split. Re-assembling from the raw bytes - nothing is lost.")
        print()
        from reframe_tap import load_bytes, reframe
        st = load_bytes(path)
        rebuilt = {"L": [], "E": []}
        for d in ("L", "E"):
            prev_t = None
            for t0, b in reframe(st[d], 50000):
                rebuilt[d].append({"t": t0, "dir": d,
                                   "gap": 0 if prev_t is None else t0 - prev_t,
                                   "span": 0, "n": len(b), "b": b,
                                   "perr": 0, "ovr": 0})
                prev_t = t0
        L, E = rebuilt["L"], rebuilt["E"]
    print("=" * 72)
    print(os.path.basename(path))
    print("=" * 72)
    print(f"  LKAS->EPS frames : {len(L)}")
    print(f"  EPS->LKAS frames : {len(E)}")
    print(f"  marks            : {len(marks)}")

    if L:
        lens = Counter(r['n'] for r in L)
        gaps = sorted(r['gap'] for r in L if r['gap'])
        bad = sum(1 for r in L if r['n'] >= 4 and
                  chksm(r['b'][0], r['b'][1], r['b'][2]) != r['b'][3])
        steers, b2s, ons = [], Counter(), 0
        for r in L:
            if r['n'] < 4:
                continue
            steers.append(wire_fields_to_value(r['b'][0] & 0x0F, r['b'][1] & 0x1F))
            b2s[r['b'][2]] += 1
            ons += (r['b'][1] >> 5) & 1
        print()
        print("  --- LKAS -> EPS ---")
        print(f"  frame lengths     : {dict(lens)}   (expect {{4: n}})")
        print(f"  checksum FAILURES : {bad}")
        print(f"  parity errors     : {max((r['perr'] for r in L), default=0)}")
        print(f"  overruns          : {max((r['ovr'] for r in L), default=0)}")
        if gaps:
            print(f"  frame period us   : min {gaps[0]}  median {gaps[len(gaps)//2]}  max {gaps[-1]}")
            print(f"  => rate           : {1e6/gaps[len(gaps)//2]:.1f} Hz")
        if steers:
            print(f"  steer min/max     : {min(steers)} / {max(steers)}")
            print(f"  |steer| max       : {max(abs(s) for s in steers)}")
            print(f"  lkasOn frames     : {ons}/{len(steers)}")
            print(f"  byte2 census      : {dict(b2s)}")
            mags = Counter(abs(s) for s in steers)
            print("  sustained |steer| plateaus (>20 frames):")
            for v in sorted(m for m in mags if mags[m] > 20):
                print(f"     {v:4d}  x{mags[v]}")

    if E:
        lens = Counter(r['n'] for r in E)
        drv = [calculate_steer_torque(r['b'][0], r['b'][1]) for r in E if r['n'] >= 2]
        print()
        print("  --- EPS -> LKAS ---")
        print(f"  frame lengths     : {dict(lens)}   (expect {{5: n}})")
        if drv:
            print(f"  driver raw min/max: {min(drv)} / {max(drv)}")
        b4 = Counter(r['b'][4] for r in E if r['n'] >= 5)
        print(f"  byte4 distinct    : {len(b4)}  most common {b4.most_common(5)}")

    if marks:
        print()
        print("  --- MARKS (press a button at the moment of interest) ---")
        for t, w in marks:
            near = [r for r in L if abs(r['t'] - t) < 200000 and r['n'] >= 4]
            if near:
                sm = max(abs(wire_fields_to_value(r['b'][0] & 0x0F, r['b'][1] & 0x1F))
                         for r in near)
                print(f"    t={t/1e6:8.3f}s  {w}   max|steer| within +/-0.2s = {sm}")
            else:
                print(f"    t={t/1e6:8.3f}s  {w}")

    if nframes:
        print()
        print(f"  --- first {nframes} LKAS frames ---")
        for r in L[:nframes]:
            if r['n'] < 4:
                continue
            v = wire_fields_to_value(r['b'][0] & 0x0F, r['b'][1] & 0x1F)
            print(f"    {r['t']/1e6:9.4f}s gap={r['gap']:6d} "
                  f"{' '.join(f'{x:02X}' for x in r['b'])}  steer={v:5d} "
                  f"on={(r['b'][1]>>5)&1}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    n = None
    if '--frames' in sys.argv:
        n = int(sys.argv[sys.argv.index('--frames') + 1])
    report(sys.argv[1], n)
