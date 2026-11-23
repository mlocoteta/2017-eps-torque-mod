import sys, struct
img=open(sys.argv[1],'rb').read()
# UARTA disp16 values per channel
chans={'U0':0xFA00,'U1':0xFA10,'U2':0xFA20}
regoff={'CTL0':0,'CTL1':1,'CTL2':2,'OPT0':3,'STR':4,'RX':6,'TX':8}
targets={}
for cn,base in chans.items():
    for rn,ro in regoff.items():
        targets[base+ro]=f"{cn}{rn}"
# also small offsets 0x06/0x08 (base-in-register form) are ambiguous; skip
allhits=[]
for disp,label in targets.items():
    b=struct.pack('<H',disp)
    s=0
    while True:
        idx=img.find(b,s)
        if idx<0: break
        # only plausible code (programmed, in/near code islands)
        if 0x09F80<=idx<0x21F80 or 0x2B880<=idx<0x2EF00 or 0x22580<=idx<0x23080:
            allhits.append((idx,label,disp))
        s=idx+1
allhits.sort()
print(f"UARTA register-displacement hits in code: {len(allhits)}")
print("addr        reg      disp")
prev=0
for idx,label,disp in allhits:
    gap='' if prev==0 or idx-prev>256 else f'   (+{idx-prev})'
    if prev and idx-prev>256: print("   ----")
    print(f"  0x{idx:06X}  {label:7} 0x{disp:04X}{gap}")
    prev=idx
# Also: find the init cluster -- a window where CTL0/CTL1/CTL2/OPT0 of one channel appear close
print("\nInit-cluster scan (>=3 distinct U?CTL*/OPT0 within 128 bytes):")
init={d:l for d,l in targets.items() if any(l.endswith(x) for x in ['CTL0','CTL1','CTL2','OPT0'])}
pts=sorted((idx,label) for idx,label,disp in allhits if label in init.values())
for i,(idx,lab) in enumerate(pts):
    near=[(j,l) for j,l in pts if 0<=j-idx<128]
    if len({l for _,l in near})>=3:
        print(f"   @0x{idx:06X}: "+', '.join(f'{l}@0x{j:06X}' for j,l in near))
