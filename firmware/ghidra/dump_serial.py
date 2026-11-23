# Ghidra post-analysis script (Jython-compatible GhidraScript).
# Runs after headless auto-analysis of the T2F-L310 image. Dumps:
#   - function inventory
#   - decompilation of functions overlapping the UART driver region
#   - xrefs to the UARTA RX/TX/STR registers and the two cal banks
# No f-strings (Jython 2.7). Prints to stdout; headless captures it.

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

fm = currentProgram.getFunctionManager()
af = currentProgram.getAddressFactory()
sp = af.getDefaultAddressSpace()

def A(x):
    return sp.getAddress(x)

print("=" * 70)
print("FUNCTION INVENTORY: %d functions" % fm.getFunctionCount())
print("=" * 70)
for f in fm.getFunctions(True):
    e = f.getEntryPoint()
    print("  0x%08X  %s" % (e.getOffset(), f.getName()))

# --- UART driver region (from SERIAL-SUBSYSTEM note) ---
SER_LO, SER_HI = 0x01FE96, 0x021426
print("")
print("=" * 70)
print("DECOMPILE: functions overlapping UART driver 0x%06X-0x%06X" % (SER_LO, SER_HI))
print("=" * 70)
dec = DecompInterface()
dec.openProgram(currentProgram)
mon = ConsoleTaskMonitor()
seen = set()
for f in fm.getFunctions(True):
    e = f.getEntryPoint().getOffset()
    body = f.getBody()
    # overlap test
    lo = body.getMinAddress().getOffset()
    hi = body.getMaxAddress().getOffset()
    if hi < SER_LO or lo > SER_HI:
        continue
    if e in seen:
        continue
    seen.add(e)
    print("\n----- %s @0x%08X -----" % (f.getName(), e))
    res = dec.decompileFunction(f, 60, mon)
    if res and res.getDecompiledFunction():
        print(res.getDecompiledFunction().getC())
    else:
        print("  <decompile failed>")

# --- xrefs to key peripheral/cal addresses ---
print("")
print("=" * 70)
print("XREFS to UARTA registers and calibration banks")
print("=" * 70)
TARGETS = [
    ("U0RX", 0xFFFFFA06), ("U0TX", 0xFFFFFA08), ("U0STR", 0xFFFFFA04),
    ("U1RX", 0xFFFFFA16), ("U1TX", 0xFFFFFA18), ("U1STR", 0xFFFFFA14),
    ("U2RX", 0xFFFFFA26), ("U2TX", 0xFFFFFA28), ("U2STR", 0xFFFFFA24),
    ("CAL_BANK_A", 0x02F100), ("CAL_BANK_B", 0x031F00),
    ("TBL256_027200", 0x027200), ("TBL256_028000", 0x028000),
]
rm = currentProgram.getReferenceManager()
for name, addr in TARGETS:
    try:
        a = A(addr)
    except:
        print("  %-14s 0x%08X  <addr not in space>" % (name, addr))
        continue
    refs = rm.getReferencesTo(a)
    locs = []
    for r in refs:
        locs.append(r.getFromAddress().getOffset())
    if locs:
        locs = sorted(set(locs))
        s = " ".join(["0x%06X" % x for x in locs[:12]])
        print("  %-14s 0x%08X  <- %s" % (name, addr, s))
    else:
        print("  %-14s 0x%08X  <- (no refs; may need peripheral block defined)" % (name, addr))

print("\nDONE")
