"""
Bit-by-bit reverse engineering of both directions of the 2017 Accord
LKAS<->EPS serial link, from the operator's own drives.

Method, for every bit of every byte:
  1. usage rate, healthy vs the errored capture (the only two states we have)
  2. is it CONSTANT, a per-frame TOGGLE, or data?
  3. mutual information against every signal we already understand
  4. behaviour around LKAS engage / disengage

Nothing here is taken from the C. The C is wrong about at least one field
(motor torque sign) and unaware of several others.
"""
import sys, os, glob, bisect, math
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from honda_serial_model import (chksm, wire_fields_to_value,
                                calculate_steer_torque, calculate_motor_torque)
from reframe_tap import load_bytes, reframe


def frames(paths):
    L, E = [], []
    for p in paths:
        st = load_bytes(p)
        L += [(t, b) for t, b in reframe(st["L"], 50000)
              if len(b) == 4 and chksm(b[0], b[1], b[2]) == b[3]]
        E += [(t, b) for t, b in reframe(st["E"], 50000)
              if len(b) == 5 and chksm(b[0], b[1], b[2], b[3]) == b[4]]
    L.sort(); E.sort()
    return L, E


def steer(b):   return wire_fields_to_value(b[0] & 0x0F, b[1] & 0x1F)
def lkason(b):  return (b[1] >> 5) & 1


def mutual_info(xs, ys):
    """bits of information a binary x carries about a binned y."""
    n = len(xs)
    if n == 0: return 0.0
    jx = Counter(xs); jy = Counter(ys); jxy = Counter(zip(xs, ys))
    mi = 0.0
    for (a, b), c in jxy.items():
        pxy = c / n; px = jx[a] / n; py = jy[b] / n
        if pxy > 0:
            mi += pxy * math.log2(pxy / (px * py))
    return mi


def bitprofile(frames_, nbytes, label, signals):
    print("=" * 76)
    print(f"{label}")
    print("=" * 76)
    n = len(frames_)
    for byi in range(nbytes):
        vals = Counter(b[byi] for _, b in frames_)
        print(f"\n  byte {byi}:  {len(vals)} distinct, "
              f"0x{min(vals):02X}..0x{max(vals):02X}   "
              f"top {[(hex(v), c) for v, c in vals.most_common(4)]}")
        for bit in range(7, -1, -1):
            col = [(b[byi] >> bit) & 1 for _, b in frames_]
            ones = sum(col)
            pct = 100.0 * ones / n
            if ones == 0:
                print(f"     bit{bit}  always 0")
                continue
            if ones == n:
                print(f"     bit{bit}  always 1")
                continue
            flips = sum(1 for a, c in zip(col, col[1:]) if a != c)
            fl = 100.0 * flips / max(1, n - 1)
            best = []
            for sname, sv in signals.items():
                mi = mutual_info(col, sv)
                if mi > 0.02:
                    best.append((mi, sname))
            best.sort(reverse=True)
            tag = "TOGGLE every frame" if fl > 95 else ""
            bs = "  ".join(f"{s}({m:.2f}b)" for m, s in best[:3])
            print(f"     bit{bit}  set {pct:5.1f}%  flips {fl:5.1f}%  {tag}{bs}")


def main():
    drives = sorted(glob.glob("Logs/*.csv"))
    L, E = frames(drives)
    print(f"  healthy drives: {len(L)} LKAS, {len(E)} EPS frames "
          f"(all checksum-valid)\n")

    # ---- signals we already understand, for correlating against ---------
    sL = [steer(b) for _, b in L]
    def band(v, step):
        return max(-6, min(6, v // step))
    sigL = {
        "lkasOn":     [lkason(b) for _, b in L],
        "steerSign":  [(1 if v > 0 else (-1 if v < 0 else 0)) for v in sL],
        "|steer|band":[min(5, abs(v) // 50) for v in sL],
        "steerZero":  [1 if v == 0 else 0 for v in sL],
    }
    bitprofile(L, 3, "LKAS -> EPS   (byte 3 is the checksum, omitted)", sigL)

    # pair EPS frames with the command that preceded them
    Lt = [t for t, _ in L]
    cmd, on = [], []
    for t, b in E:
        j = bisect.bisect_right(Lt, t - 3000) - 1
        cmd.append(sL[j] if j >= 0 else 0)
        on.append(lkason(L[j][1]) if j >= 0 else 0)
    mot = [calculate_motor_torque(b[2], b[3]) for _, b in E]
    drv = [calculate_steer_torque(b[0], b[1]) for _, b in E]
    sigE = {
        "lkasOn":     on,
        "cmdSign":    [(1 if v > 0 else (-1 if v < 0 else 0)) for v in cmd],
        "|cmd|band":  [min(5, abs(v) // 50) for v in cmd],
        "motorSign":  [(1 if v > 0 else (-1 if v < 0 else 0)) for v in mot],
        "|motor|band":[min(5, abs(v) // 25) for v in mot],
        "driverBand": [min(7, v // 64) for v in drv],
    }
    print()
    bitprofile(E, 4, "EPS -> LKAS   (byte 4 is the checksum, omitted)", sigE)

    # ---- healthy vs errored --------------------------------------------
    err = ["C:/Users/mloco/OneDrive/Desktop/2026-11-13_002058_base.csv"]
    if os.path.exists(err[0]):
        Le, Ee = frames(err)
        print()
        print("=" * 76)
        print("HEALTHY vs ERRORED  --  which bits differ?")
        print("=" * 76)
        for nm, a, bset, nb in (("LKAS->EPS", L, Le, 3), ("EPS->LKAS", E, Ee, 4)):
            print(f"\n  {nm}")
            for byi in range(nb):
                for bit in range(8):
                    pa = 100.0 * sum((x[1][byi] >> bit) & 1 for x in a) / len(a)
                    pb = 100.0 * sum((x[1][byi] >> bit) & 1 for x in bset) / len(bset)
                    if abs(pa - pb) > 25:
                        print(f"     byte{byi} bit{bit}:  healthy {pa:5.1f}%   "
                              f"errored {pb:5.1f}%   <-- DIFFERS")


if __name__ == "__main__":
    main()
