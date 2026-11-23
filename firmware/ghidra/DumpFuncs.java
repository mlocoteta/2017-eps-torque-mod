// Decompile the function containing each address passed as a script arg (hex),
// and list its callers and callees. Headless-safe Java (no PyGhidra).
// Usage: -postScript DumpFuncs.java 0x23610 0x1dc68 0x12ec4 ...
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.address.Address;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.util.task.ConsoleTaskMonitor;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import java.util.TreeSet;

public class DumpFuncs extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        FunctionManager fm = currentProgram.getFunctionManager();
        ReferenceManager rm = currentProgram.getReferenceManager();
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        ConsoleTaskMonitor mon = new ConsoleTaskMonitor();

        for (String a : args) {
            long off = Long.parseLong(a.replace("0x", ""), 16);
            Address ad = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(off);
            Function f = fm.getFunctionContaining(ad);
            println("\n################ 0x" + Long.toHexString(off) +
                    (f == null ? "  <no function>" : "  -> " + f.getName() + " @0x" +
                     Long.toHexString(f.getEntryPoint().getOffset())) + " ################");
            if (f == null) continue;

            // callers
            TreeSet<String> callers = new TreeSet<String>();
            for (Reference r : rm.getReferencesTo(f.getEntryPoint())) {
                Function c = fm.getFunctionContaining(r.getFromAddress());
                callers.add(c == null ? ("0x" + Long.toHexString(r.getFromAddress().getOffset()))
                                      : (c.getName() + "@0x" + Long.toHexString(c.getEntryPoint().getOffset())));
            }
            println("CALLERS: " + (callers.isEmpty() ? "(none found — may be via function pointer)" : callers.toString()));

            // callees
            TreeSet<String> callees = new TreeSet<String>();
            for (Function c : f.getCalledFunctions(mon)) {
                callees.add(c.getName() + "@0x" + Long.toHexString(c.getEntryPoint().getOffset()));
            }
            println("CALLEES: " + callees.toString());

            DecompileResults r = dec.decompileFunction(f, 120, mon);
            if (r != null && r.getDecompiledFunction() != null) {
                println(r.getDecompiledFunction().getC());
            } else {
                println("  <decompile failed>");
            }
        }
        println("\nDONE");
    }
}
