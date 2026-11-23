// Ghidra Java post-script (headless-safe; no PyGhidra needed).
// Dumps function inventory, decompiles the UART driver region, lists xrefs to
// the UARTA registers and the two calibration banks.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.util.task.ConsoleTaskMonitor;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import java.util.TreeSet;

public class DumpSerial extends GhidraScript {
    public void run() throws Exception {
        FunctionManager fm = currentProgram.getFunctionManager();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();

        println("====== FUNCTION INVENTORY: " + fm.getFunctionCount() + " functions ======");
        for (Function f : fm.getFunctions(true)) {
            println(String.format("  0x%08X  %s", f.getEntryPoint().getOffset(), f.getName()));
        }

        long LO = 0x01FE96L, HI = 0x021426L;
        println("");
        println("====== DECOMPILE: functions overlapping UART driver 0x" +
                Long.toHexString(LO) + "-0x" + Long.toHexString(HI) + " ======");
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        ConsoleTaskMonitor mon = new ConsoleTaskMonitor();
        TreeSet<Long> done = new TreeSet<Long>();
        for (Function f : fm.getFunctions(true)) {
            long lo = f.getBody().getMinAddress().getOffset();
            long hi = f.getBody().getMaxAddress().getOffset();
            if (hi < LO || lo > HI) continue;
            long e = f.getEntryPoint().getOffset();
            if (!done.add(e)) continue;
            println("\n----- " + f.getName() + " @0x" + Long.toHexString(e) +
                    "  body 0x" + Long.toHexString(lo) + "-0x" + Long.toHexString(hi) + " -----");
            DecompileResults r = dec.decompileFunction(f, 90, mon);
            if (r != null && r.getDecompiledFunction() != null) {
                println(r.getDecompiledFunction().getC());
            } else {
                println("  <decompile failed>");
            }
        }

        println("");
        println("====== XREFS to UARTA registers and calibration banks ======");
        long[] addrs = {
            0xFFFFFA06L, 0xFFFFFA08L, 0xFFFFFA04L,   // U0 RX/TX/STR
            0xFFFFFA16L, 0xFFFFFA18L, 0xFFFFFA14L,   // U1
            0xFFFFFA26L, 0xFFFFFA28L, 0xFFFFFA24L,   // U2
            0x02F100L, 0x031F00L,                    // cal bank A/B
            0x027200L, 0x028000L                     // 256-entry tables
        };
        String[] names = {
            "U0RX","U0TX","U0STR","U1RX","U1TX","U1STR","U2RX","U2TX","U2STR",
            "CAL_BANK_A","CAL_BANK_B","TBL256_027200","TBL256_028000"
        };
        ReferenceManager rm = currentProgram.getReferenceManager();
        for (int i = 0; i < addrs.length; i++) {
            Address a = sp.getAddress(addrs[i]);
            TreeSet<Long> locs = new TreeSet<Long>();
            for (Reference r : rm.getReferencesTo(a)) {
                locs.add(r.getFromAddress().getOffset());
            }
            StringBuilder sb = new StringBuilder();
            int n = 0;
            for (Long l : locs) {
                if (n++ >= 16) { sb.append(" ..."); break; }
                sb.append(String.format(" 0x%06X", l));
            }
            println(String.format("  %-14s 0x%08X <-%s", names[i], addrs[i],
                    locs.isEmpty() ? " (none)" : sb.toString()));
        }
        println("\nDONE");
    }
}
