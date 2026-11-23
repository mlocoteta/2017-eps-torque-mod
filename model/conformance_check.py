"""
Conformance checker: does what YOUR BOARD sends look like what the FACTORY
CAMERA sends?

The question this answers: "is the data we're transmitting to the EPS correct?"
It is answered entirely from wire captures. No chip access, no firmware dump,
nothing on the car beyond the passive tap you already have.

HOW TO USE IT
  1. Capture stock traffic with the board OUT of the loop (or passive).
     -> that is the baseline. Logs/*.csv already contains 39 040 such frames.
  2. Capture again with YOUR BOARD ACTIVE and openpilot commanding steering.
  3. Run:  python conformance_check.py <your_capture.csv>

  Every field is scored against the stock distribution. A field that the
  factory camera varies but your board holds constant -- or vice versa -- is
  a deviation, and deviations are the candidate explanations for the EPS
  rejecting or mishandling your commands.

WHY THIS IS THE RIGHT FIRST TEST
  The EPS is a black box that accepts or rejects what it is given. Stock
  traffic is a known-accepted sample of that input space, 39 040 frames
  deep. Anything your board does that stock never does is, by definition,
  untested input to a safety-critical actuator.

Baseline is recomputed from Logs/*.csv on every run, so it stays honest.
"""
import sys, os, glob
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from honda_serial_model import (chksm, wire_fields_to_value,
                                calculate_motor_torque, calculate_steer_torque)
from reframe_tap import load_bytes, reframe

BASELINE_GLOB = "Logs/*.csv"


def load_frames(paths):
    L, E = [], []
    for p in paths:
        st = load_bytes(p)
        L += [b for _, b in reframe(st["L"], 50000)
              if len(b) == 4 and chksm(b[0], b[1], b[2]) == b[3]]
        E += [b for _, b in reframe(st["E"], 50000)
              if len(b) == 5 and chksm(b[0], b[1], b[2], b[3]) == b[4]]
    return L, E


def steer(b):  return wire_fields_to_value(b[0] & 0x0F, b[1] & 0x1F)


# Each check: (name, why it matters, extractor, comparison kind)
# kind "set"  -> compare the SET of values seen
# kind "rate" -> compare how often a bit is set
# kind "span" -> compare min/max
CHECKS = [
    ("byte2 states", "The camera uses six; the fork hardcodes 0x80. Byte 2 "
     "carries the LKAS-active mirror, both LDW bits and the fault bit.",
     lambda b: b[2], "set"),

    ("byte2 bit6 == NOT lkasOn", "100.00% true in stock. If your board breaks "
     "this pairing it emits a self-contradictory frame stock never produces.",
     lambda b: 1 if ((b[2] >> 6) & 1) == (1 - ((b[1] >> 5) & 1)) else 0, "rate"),

    # Conditioned on steer != 0 deliberately. Stock parks bit0 at zero steer
    # and so does the fork, so an unconditional flip rate washes the two
    # together (39.2% vs 56.7% -- under a naive threshold). Restricted to
    # non-zero frames the gap is unmissable: data ~70%, forced toggle ~100%.
    ("byte1 bit0 flip, steer!=0", "Stock varies it as the real steer LSB. A "
     "forced per-frame toggle pins this near 100% and throws away a bit of "
     "command resolution.",
     lambda b: (b[1] & 1) if steer(b) != 0 else None, "rate"),

    ("byte0 bit5 (counter)", "Must alternate every frame. This is the most "
     "likely liveness signal the EPS watches.",
     lambda b: (b[0] >> 5) & 1, "rate"),

    ("reserved bits b0.7/6/4", "Always 0 in stock. Anything set here is "
     "malformed.",
     lambda b: 1 if (b[0] & 0b11010000) else 0, "rate"),

    ("byte1 bit6", "Always 0 in stock.", lambda b: (b[1] >> 6) & 1, "rate"),

    # Signed, NOT abs(). The fork clips to +/-239, but its forced LSB toggle
    # can clear bit0 of a negative command and push -239 back out to -240 --
    # abs() hides that by folding the two sides together.
    ("steer range (signed)", "Stock spans exactly -240..+240. Going beyond it "
     "is input the EPS has never been given; falling short means you cannot "
     "reach what the car itself commands.",
     steer, "span"),
]


def flip_rate(seq):
    if len(seq) < 2:
        return 0.0
    return 100.0 * sum(1 for a, b in zip(seq, seq[1:]) if a != b) / (len(seq) - 1)


def report(base, test, label):
    print("=" * 76)
    print(f"  {label}")
    print("=" * 76)
    print(f"  baseline frames: {len(base)}     capture frames: {len(test)}")
    if not test:
        print("  !! no valid frames in the capture -- nothing to score")
        return
    print()
    verdicts = []
    for name, why, fn, kind in CHECKS:
        bv = [fn(b) for b in base]
        tv = [fn(b) for b in test]
        if kind == "set":
            bs, ts = set(bv), set(tv)
            missing = bs - ts
            extra = ts - bs
            # Only a NEVER-IN-STOCK value is a conformance failure. A short or
            # LKAS-off capture legitimately won't exercise every stock state,
            # so "unused" is reported, not failed.
            ok = not extra
            detail = (f"stock={sorted(hex(x) for x in bs)}  "
                      f"yours={sorted(hex(x) for x in ts)}")
            if extra:
                detail += f"  NEVER-IN-STOCK={sorted(hex(x) for x in extra)}"
            if missing:
                detail += f"  unused={sorted(hex(x) for x in missing)}"
        elif kind == "rate":
            bv = [x for x in bv if x is not None]   # extractor may filter
            tv = [x for x in tv if x is not None]
            if not bv or not tv:
                verdicts.append((True, name, why, "no applicable frames"))
                continue
            br, tr = 100.0 * sum(bv) / len(bv), 100.0 * sum(tv) / len(tv)
            bf, tf = flip_rate(bv), flip_rate(tv)
            ok = abs(br - tr) < 10 and abs(bf - tf) < 10
            detail = (f"stock set {br:5.1f}% flip {bf:5.1f}%   "
                      f"yours set {tr:5.1f}% flip {tf:5.1f}%")
        else:  # span -- signed, both ends
            ok = (min(tv) >= min(bv)) and (max(tv) <= max(bv))
            detail = (f"stock {min(bv):+d}..{max(bv):+d}   "
                      f"yours {min(tv):+d}..{max(tv):+d}")
            if min(tv) < min(bv) or max(tv) > max(bv):
                detail += "  <-- EXCEEDS what stock ever sends"
        verdicts.append((ok, name, why, detail))

    for ok, name, why, detail in verdicts:
        print(f"  [{'OK  ' if ok else 'DIFF'}]  {name}")
        print(f"          {detail}")
        if not ok:
            print(f"          why it matters: {why}")
        print()

    nd = sum(1 for ok, *_ in verdicts if not ok)
    print("  " + "-" * 72)
    if nd == 0:
        print("  Your frames are indistinguishable from stock on every checked field.")
        print("  If the EPS still misbehaves, the cause is NOT frame conformance.")
    else:
        print(f"  {nd} field(s) differ from stock.")
        print("  Each is untested input to the EPS: stock never sends it, so")
        print("  nothing guarantees the EPS handles it the way you expect.")
        print("  Fix these before concluding anything about a torque ceiling.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n  Running in BASELINE-ONLY mode: characterising stock.\n")
        base, baseE = load_frames(sorted(glob.glob(BASELINE_GLOB)))
        if not base:
            print(f"  no baseline frames found under {BASELINE_GLOB}")
            return 2
        print("=" * 76)
        print("  STOCK BASELINE -- what the factory camera does")
        print("=" * 76)
        print(f"  LKAS->EPS frames: {len(base)}   EPS->LKAS frames: {len(baseE)}")
        for name, _why, fn, kind in CHECKS:
            v = [fn(b) for b in base]
            if kind == "set":
                print(f"    {name:28s} {sorted(hex(x) for x in set(v))}")
            elif kind == "rate":
                v = [x for x in v if x is not None]
                print(f"    {name:28s} set {100.0*sum(v)/len(v):5.1f}%   "
                      f"flip {flip_rate(v):5.1f}%")
            else:
                print(f"    {name:28s} {min(v):+d}..{max(v):+d}")
        print()
        print("  To score your board, capture it transmitting and run:")
        print("    python conformance_check.py <your_capture.csv>")
        return 0

    base, _ = load_frames(sorted(glob.glob(BASELINE_GLOB)))
    if not base:
        print(f"  no baseline frames under {BASELINE_GLOB} -- cannot score")
        return 2
    test, _ = load_frames([sys.argv[1]])
    report(base, test, os.path.basename(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
