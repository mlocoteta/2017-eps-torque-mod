import sys
img=open(sys.argv[1],'rb').read()
DELTA=0x2E00
# find maximal byte-identical run with its copy +DELTA, scanning the data region 0x2E000..0x036000
best=None
a=0x2E000
while a<0x034000:
    if img[a]==img[a+DELTA]:
        n=0
        while a+n<0x036000 and img[a+n]==img[a+DELTA+n]:
            n+=1
        if n>=0x400 and (best is None or n>best[1]):
            best=(a,n)
        a+=max(n,1)
    else:
        a+=1
if best:
    a,n=best
    print(f"largest identical block: 0x{a:06X}..0x{a+n:06X} == 0x{a+DELTA:06X}..0x{a+DELTA+n:06X}")
    print(f"  length 0x{n:X} ({n} bytes)")
    import hashlib
    print(f"  bank A sha256[:16]: {hashlib.sha256(img[a:a+n]).hexdigest()[:16]}")
    print(f"  bank B sha256[:16]: {hashlib.sha256(img[a+DELTA:a+DELTA+n]).hexdigest()[:16]}")
# how many of the duplicate-pair tables are covered
pairs=[(0x02F7A6,0x0325A6),(0x030800,0x033600),(0x031502,0x034302),(0x02FE02,0x032C02),
       (0x02F582,0x032382),(0x030582,0x033382),(0x031202,0x034002),(0x030282,0x033082),
       (0x031C52,0x034A52),(0x031A00,0x034800),(0x02F100,None)]
print("\nverify each flagged pair is +0x2E00 and identical (first 64B):")
for x,y in pairs:
    if y is None: y=x+DELTA
    same = img[x:x+64]==img[y:y+64]
    print(f"  0x{x:06X} vs 0x{y:06X} (+0x{y-x:X}): identical64={same}")
