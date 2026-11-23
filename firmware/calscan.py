import sys, struct
img=open(sys.argv[1],'rb').read()
# data/calibration regions (from orientation, excluding code islands)
DATA=[(0x001820,0x07C80),(0x026180,0x02A880),(0x02F080,0x030780),
      (0x030800,0x033580),(0x033600,0x036180),(0x037400,0x037600)]

def i16(o): 
    v=struct.unpack('<h',img[o:o+2])[0]; return v

def monoruns(a,b,step=2):
    """find maximal monotonic (non-strict) runs of int16 LE, len>=6"""
    runs=[]; o=a
    while o< b-step*2:
        # try start a run
        s=o; vals=[i16(o)]; d=0
        p=o+step
        while p<b-1:
            v=i16(p); pv=vals[-1]
            nd = 1 if v>pv else (-1 if v<pv else 0)
            if d==0: d=nd
            if nd!=0 and d!=0 and nd!=d: break
            vals.append(v); p+=step
        if len(vals)>=8:
            runs.append((s,len(vals),d,vals[0],vals[-1]))
            o=p
        else:
            o+=step
    return runs

print("MONOTONIC int16 runs (len>=8) — candidate lookup curves / breakpoint axes:")
print(f"{'addr':>9} {'pts':>4} {'dir':>4} {'first':>7} {'last':>7}  span")
allr=[]
for a,b in DATA:
    for s,n,d,f,l in monoruns(a,b):
        allr.append((s,n,d,f,l))
allr.sort(key=lambda r:-r[1])
for s,n,d,f,l in allr[:40]:
    dirs='UP' if d>0 else 'DN'
    print(f"  0x{s:06X} {n:4} {dirs:>4} {f:7} {l:7}  [{min(f,l)}..{max(f,l)}]")
print(f"  ...{len(allr)} monotonic runs total")

# detect uniform-stride breakpoint axes (common x-axis: evenly spaced increasing)
print("\nEvenly-spaced increasing int16 runs (likely X-axis breakpoints):")
for s,n,d,f,l in allr:
    if d>0 and n>=8:
        vals=[i16(s+2*k) for k in range(n)]
        diffs=[vals[k+1]-vals[k] for k in range(n-1)]
        if len(set(diffs))<=2 and max(diffs)-min(diffs)<=2 and diffs[0]>0:
            print(f"  0x{s:06X}  {n} pts  step~{diffs[0]}  {vals[0]}..{vals[-1]}")
