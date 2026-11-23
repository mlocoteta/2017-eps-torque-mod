import sys, re, struct
from collections import Counter
img=open(sys.argv[1],'rb').read()
N=len(img)
BLOCKS=[(0x1800,0x6480),(0x7F80,0x1380),(0x9F80,0x18000),(0x22580,0xB00),(0x23180,0x2780),
(0x26180,0xB80),(0x26F80,0x3900),(0x2A900,0x100),(0x2AA80,0x180),(0x2AC80,0x380),
(0x2B080,0x780),(0x2B880,0x3680),(0x2F080,0x1700),(0x30800,0x2D80),(0x33600,0x2B80),
(0x36480,0xE00),(0x37300,0x80),(0x37400,0x200),(0x37B00,0x200),(0x37D80,0x180),(0x37F80,0x80)]

def programmed(off):
    return any(s<=off<s+l for s,l in BLOCKS)

print("="*70); print("  1. ASCII STRINGS (>=5 chars, in programmed regions)"); print("="*70)
seen=set(); nstr=0
for m in re.finditer(rb'[\x20-\x7e]{5,}', img):
    if not programmed(m.start()): continue
    s=m.group().decode()
    nstr+=1
    key=s
    if key in seen: continue
    seen.add(key)
    print(f"   0x{m.start():06X}  {s}")
print(f"   ...{nstr} string hits total, {len(seen)} unique")

print("\n"+"="*70); print("  2. POINTER TABLES (runs of >=4 consecutive LE32 in valid ranges)"); print("="*70)
# valid targets: code flash 0x0..0x3BFFF, or RAM 0x03FF8000..0x03FFFFFF
def valid_ptr(v):
    return (0x1000<=v<0x3C000) or (0x03FF8000<=v<=0x03FFFFFF)
runs=[]; i=0
while i<N-4:
    if programmed(i):
        v=struct.unpack('<I',img[i:i+4])[0]
        if valid_ptr(v):
            j=i; cnt=0; tgts=[]
            while j<N-4 and programmed(j):
                vv=struct.unpack('<I',img[j:j+4])[0]
                if valid_ptr(vv): cnt+=1; tgts.append(vv); j+=4
                else: break
            if cnt>=4:
                runs.append((i,cnt,tgts[:3]))
                i=j; continue
    i+=4
runs.sort(key=lambda r:-r[1])
for off,cnt,sample in runs[:25]:
    code=sum(1 for v in sample if v<0x3C000); 
    kind="code-ptrs" if all(v<0x3C000 for v in sample) else ("ram-ptrs" if all(v>=0x03FF8000 for v in sample) else "mixed")
    print(f"   0x{off:06X}  {cnt:4} entries  {kind}  e.g. {['0x%X'%v for v in sample]}")
print(f"   ...{len(runs)} pointer-table runs >=4 total")

print("\n"+"="*70); print("  3. CODE vs DATA by block (80_07/KB, entropy)"); print("="*70)
import math
def ent(b):
    if not b: return 0
    c=Counter(b); n=len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())
for s,l in BLOCKS:
    d=img[s:s+l]
    pairs=sum(1 for j in range(0,len(d)-1,2) if d[j]==0x80 and d[j+1]==0x07)
    perkb=pairs/(len(d)/1024)
    e=ent(d)
    ffp=100*d.count(0xFF)/len(d)
    cls="CODE" if perkb>2.0 else ("sparse/pad" if ffp>50 else "DATA")
    print(f"   0x{s:06X} len 0x{l:5X}  80_07/KB={perkb:6.2f}  ent={e:.2f}  ff%={ffp:5.1f}  -> {cls}")
