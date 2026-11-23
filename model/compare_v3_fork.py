"""
Deep dive: what the STOCK 2017 Accord camera actually does on the LKAS->EPS
link, measured from the operator's own drive logs, compared against what
LKAS_EPS_V3 (the STM32 fork) does.

Every number here is measured from the logs. Nothing is assumed from the C.
"""
import sys, os, glob
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from honda_serial_model import chksm, wire_fields_to_value, calculate_steer_torque
from reframe_tap import load_bytes, reframe


def frames(path):
    st = load_bytes(path)
    L = [(t, b) for t, b in reframe(st["L"], 50000)
         if len(b) == 4 and chksm(b[0], b[1], b[2]) == b[3]]
    E = [(t, b) for t, b in reframe(st["E"], 50000)
         if len(b) == 5 and chksm(b[0], b[1], b[2], b[3]) == b[4]]
    return L, E


def steer_of(b):
    return wire_fields_to_value(b[0] & 0x0F, b[1] & 0x1F)


def main(paths):
    allL, allE = [], []
    for p in paths:
        L, E = frames(p)
        for t, b in L:
            allL.append((os.path.basename(p), t, b))
        for t, b in E:
            allE.append((os.path.basename(p), t, b))
    print(f"  pooled: {len(allL)} LKAS frames, {len(allE)} EPS frames, "
          f"all checksum-valid\n")

    # ---------------------------------------------------------------- A
    print("=" * 74)
    print("A. PEAK TORQUE  --  fork clips at steerMax 239")
    print("=" * 74)
    steers = [steer_of(b) for _, _, b in allL]
    mags = Counter(abs(s) for s in steers)
    print(f"   stock max  +{max(steers)} / {min(steers)}")
    top = sorted(m for m in mags if m >= 150)
    print(f"   |steer| >=150 seen: {[(m, mags[m]) for m in top]}")
    print(f"   frames at |steer| == 240 : {mags.get(240,0)}")
    print(f"   frames at |steer| == 239 : {mags.get(239,0)}")
    print(f"   => fork's steerMax=239 is BELOW stock's 240, and the wiggle bit")
    print(f"      forces even values, so commanding 239 delivers 238/239.")

    # ---------------------------------------------------------------- B
    print()
    print("=" * 74)
    print("B. THE WIGGLE BIT  --  does stock really alternate bit0?")
    print("=" * 74)
    alt = same = 0
    prev = None
    for _, _, b in allL:
        lsb = b[1] & 1
        if prev is not None:
            if lsb != prev: alt += 1
            else: same += 1
        prev = lsb
    print(f"   consecutive frames where bit0 FLIPPED : {alt}")
    print(f"   consecutive frames where it did NOT   : {same}")
    print(f"   => {100.0*alt/max(1,alt+same):.1f}% alternating")
    # does it alternate even when steer is 0?
    z = [(b[1] & 1) for _, _, b in allL if steer_of(b) == 0]
    zc = Counter(z)
    print(f"   at steer==0, bit0 values: {dict(zc)}")
    print(f"   fork only wiggles when (steerB1>0 || steerB0>0) -- i.e. NOT at")
    print(f"   zero. Stock at zero: {'also parks bit0' if len(zc)==1 else 'KEEPS WIGGLING'}")

    # ---------------------------------------------------------------- C
    print()
    print("=" * 74)
    print("C. BYTE 2  --  fork hardcodes 0x80 | ldw(bits5:4)")
    print("=" * 74)
    b2 = Counter(b[2] for _, _, b in allL)
    for v, n in sorted(b2.items()):
        on = sum(1 for _, _, b in allL if b[2] == v and ((b[1] >> 5) & 1))
        pk = max((abs(steer_of(b)) for _, _, b in allL if b[2] == v), default=0)
        print(f"   0x{v:02X}  {v>>4:04b} {v&0xF:04b}  x{n:<6d} lkasOn={on:<6d} peak|steer|={pk}")
    print()
    bits = defaultdict(int)
    for _, _, b in allL:
        for i in range(8):
            if b[2] & (1 << i): bits[i] += 1
    print(f"   bit usage across {len(allL)} frames:")
    for i in range(7, -1, -1):
        print(f"     bit{i}: {bits[i]:6d}  ({100.0*bits[i]/len(allL):5.1f}%)")

    # ---------------------------------------------------------------- D
    print()
    print("=" * 74)
    print("D. THE COUNTER  --  fork's verifyCounter does (old+1) & 0b11")
    print("=" * 74)
    cs = [b[0] >> 5 for _, _, b in allL]
    print(f"   distinct counter values seen: {sorted(set(cs))}")
    trans = Counter((a, b) for a, b in zip(cs, cs[1:]))
    print(f"   transitions: {dict(trans)}")
    print(f"   => counter is MOD {len(set(cs))}, fork verifies mod 4")

    # ---------------------------------------------------------------- E
    print()
    print("=" * 74)
    print("E. RATE OF CHANGE  --  fork limits steerDeltaUp/Down = 100")
    print("=" * 74)
    deltas = []
    for (f1, t1, b1), (f2, t2, b2_) in zip(allL, allL[1:]):
        if f1 != f2 or t2 - t1 > 30000:
            continue
        deltas.append(steer_of(b2_) - steer_of(b1))
    ad = sorted(abs(d) for d in deltas)
    print(f"   frame-to-frame |delta| : median {ad[len(ad)//2]}  "
          f"p99 {ad[int(len(ad)*0.99)]}  MAX {ad[-1]}")
    over = sum(1 for d in ad if d > 100)
    print(f"   deltas exceeding the fork's limit of 100: {over} "
          f"({100.0*over/len(ad):.2f}%)")

    # ---------------------------------------------------------------- F
    print()
    print("=" * 74)
    print("F. LKAS ENGAGE  --  fork sends 5 frames of zero (sendFrameDelay)")
    print("=" * 74)
    runs = []
    prev_on = None
    for i, (_, _, b) in enumerate(allL):
        on = (b[1] >> 5) & 1
        if prev_on == 0 and on == 1:
            runs.append(i)
        prev_on = on
    print(f"   LKAS off->on transitions: {len(runs)}")
    shown = 0
    for i in runs:
        seq = [steer_of(b) for _, _, b in allL[i:i+10]]
        if shown < 6:
            print(f"     first 10 steer values after engage: {seq}")
            shown += 1
    lead = []
    for i in runs:
        n = 0
        for _, _, b in allL[i:i+12]:
            if steer_of(b) != 0: break
            n += 1
        lead.append(n)
    if lead:
        print(f"   zero-frames before the first non-zero command: {Counter(lead)}")

    # ---------------------------------------------------------------- G
    print()
    print("=" * 74)
    print("G. DRIVER TORQUE  --  fork does int8_t driver_torque = raw >> 1")
    print("=" * 74)
    raw = [calculate_steer_torque(b[0], b[1]) for _, _, b in allE]
    rs = sorted(raw)
    print(f"   raw min {rs[0]}  p1 {rs[len(rs)//100]}  median {rs[len(rs)//2]}"
          f"  p99 {rs[-len(rs)//100]}  max {rs[-1]}")
    bad = sum(1 for r in raw if 200 <= r <= 300)
    print(f"   frames in the int8_t sign-flip danger band (raw 200..300): "
          f"{bad} ({100.0*bad/len(raw):.2f}%)")
    print(f"   (raw>>1 >= 128, i.e. raw >= 256, wraps to negative as int8_t)")
    neg = sum(1 for r in raw if r >= 256)
    print(f"   frames with raw >= 256 -> driver_torque NEGATIVE: {neg} "
          f"({100.0*neg/len(raw):.1f}%)")


if __name__ == "__main__":
    ps = []
    for a in sys.argv[1:]:
        ps += sorted(glob.glob(a))
    main(ps)
