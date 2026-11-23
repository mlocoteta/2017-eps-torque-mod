"""
What gates the high-torque plateau in the STOCK LKAS->EPS stream?

The aggregate histogram shows two sustained plateaus (159/160 and 239/240, each
pair being one value with the wiggle bit toggling) plus sparse ramp samples in
between. If the EPS only honours the upper plateau when the camera also raises a
flag, that flag is what the fork is missing -- and it would explain a ceiling
somewhere below 240 when the fork hardcodes byte2 = 0x80.
"""
import sys, os, re, glob
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_capture import decode

logs = sorted(glob.glob(sys.argv[1]))
rows = []
for p in logs:
    r, _, _ = decode(p)
    for x in r:
        x['src'] = os.path.basename(p)
    rows += r

print("=" * 74)
print("A. byte2 bit census  (fork hardcodes msg[2] = 0x80)")
print("=" * 74)
b2 = Counter(r['b2'] for r in rows)
for v, n in sorted(b2.items()):
    print(f"   0x{v:02X} = {v:3d} = {v>>4:04b} {v&0xF:04b}   x{n}")
print("   bit7 = always 1. bit6 = the variable one. bits5:4 = the fork's")
print("   'ldw_enable' field -- NEVER SET in any of these captures.")

print()
print("=" * 74)
print("B. Does reaching the HIGH plateau require a different byte2 / lkasOn?")
print("=" * 74)
print(f"   {'|steer| band':>16}  {'frames':>7}  {'byte2 values':>26}  {'lkasOn=1':>9}")
bands = [(0, 0), (1, 100), (101, 158), (159, 160), (161, 238), (239, 240), (241, 999)]
for lo, hi in bands:
    sel = [r for r in rows if lo <= abs(r['steer']) <= hi]
    if not sel:
        continue
    bs = Counter(r['b2'] for r in sel)
    on = sum(r['lkasOn'] for r in sel)
    label = f"{lo}" if lo == hi else f"{lo}..{hi}"
    print(f"   {label:>16}  {len(sel):7d}  {str(dict(bs)):>26}  {on:9d}")

print()
print("=" * 74)
print("C. Which capture produces which plateau?")
print("=" * 74)
per = defaultdict(Counter)
for r in rows:
    per[r['src']][abs(r['steer'])] += 1
for src, c in per.items():
    hi = max(c)
    plateau = [v for v in sorted(c) if c[v] > 20]
    print(f"   {src[:52]:52s} max={hi:4d}")
    print(f"       sustained values (>20 frames): {plateau[-6:]}")

print()
print("=" * 74)
print("D. The ramp into the 240 plateau -- sequence of |steer| over time")
print("=" * 74)
tgt = [r for r in rows if 'lane departure at end reformat' in r['src']]
mags = [abs(r['steer']) for r in tgt]
peak = max(range(len(mags)), key=lambda i: mags[i])
lo = max(0, peak - 60)
print(f"   frames {lo}..{peak+20} of the lane-departure capture")
print("   (idx: |steer| byte2 lkasOn)")
line = []
for i in range(lo, min(len(tgt), peak + 20)):
    r = tgt[i]
    line.append(f"{abs(r['steer'])}/{r['b2']:#x}/{r['lkasOn']}")
for i in range(0, len(line), 6):
    print("     " + "   ".join(line[i:i+6]))

print()
print("=" * 74)
print("E. Driver-torque at the moment of the 240 plateau")
print("=" * 74)
hi_rows = [r for r in rows if abs(r['steer']) >= 239]
if hi_rows:
    dv = [r['driver'] for r in hi_rows if r['driver'] is not None]
    print(f"   frames at |steer|>=239 : {len(hi_rows)}")
    print(f"   driver raw min/max     : {min(dv)} / {max(dv)}")
    print(f"   driver raw mean        : {sum(dv)//len(dv)}")
    print("   (SECTION 4 of the model: this signal is [0,511], centred ~256)")
