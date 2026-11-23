import sys, struct, re
dev=open(sys.argv[1],'rb').read()
img=open(sys.argv[2],'rb').read()
BASE=0xFFFFF000
# serial register names of interest
names=['U0CTL0','U0CTL1','U0CTL2','U0OPT0','U0STR','U0RX','U0TX',
       'U1CTL0','U1STR','U1RX','U1TX','U2CTL0','U2STR','U2RX','U2TX',
       'S0CTL0','S0STR','S0RX','S0TX','S1CTL0','S1RX','S1TX',
       'SBRG0CTL','SBRG1CTL']
regs={}
for nm in names:
    i=dev.find(nm.encode()+b'\x00')
    if i<0: continue
    off=struct.unpack('<H',dev[i+0x16:i+0x18])[0]
    addr=BASE+off
    regs[nm]=addr
print("SERIAL REGISTER MAP (base 0xFFFFF000, offset from device file +0x16):")
for nm,a in regs.items():
    print(f"   {nm:9} = 0x{a:08X}   disp16=0x{a&0xFFFF:04X}")

def count_hw(disp):
    """count aligned+unaligned occurrences of 2-byte LE disp in code islands"""
    b=struct.pack('<H',disp)
    CODE=[(0x09F80,0x21F80),(0x22580,0x23080),(0x2B880,0x2EF00)]
    locs=[]
    for a,bb in CODE:
        s=a
        while True:
            idx=img.find(b,s,bb)
            if idx<0: break
            locs.append(idx); s=idx+1
    return locs

print("\nUART/CSI RX & TX DATA-REGISTER DISPLACEMENTS found in firmware code:")
for nm,a in regs.items():
    if not (nm.endswith('RX') or nm.endswith('TX')): continue
    disp=a&0xFFFF
    locs=count_hw(disp)
    tag=''
    if locs: tag='  <== '+' '.join(f'0x{x:06X}' for x in locs[:8])
    print(f"   {nm:7} disp 0x{disp:04X}: {len(locs)} hits{tag}")
