// Set the V850 gp context register program-wide, then decompile target functions.
// Usage: -postScript SetGPDecomp.java 0x3ff8000 0x23610 0x23200 0x2338c 0x128a8
// arg0 = gp value (hex); remaining args = addresses whose containing function to decompile.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.lang.Register;
import ghidra.program.model.address.Address;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.util.task.ConsoleTaskMonitor;
import ghidra.program.model.scalar.Scalar;
import java.math.BigInteger;

public class SetGPDecomp extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Register gp = currentProgram.getRegister("gp");
        long gpval = Long.parseLong(args[0].replace("0x", ""), 16);

        // report gp-relative displacement range (sanity bound on gp)
        long dmin = Long.MAX_VALUE, dmax = Long.MIN_VALUE; int cnt = 0;
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext()) {
            Instruction ins = it.next();
            boolean usesGp = false;
            for (Object o : ins.getInputObjects()) if (o.equals(gp)) usesGp = true;
            if (!usesGp) continue;
            for (int oi = 0; oi < ins.getNumOperands(); oi++) {
                for (Object rep : ins.getOpObjects(oi)) {
                    if (rep instanceof Scalar) {
                        long d = ((Scalar) rep).getSignedValue();
                        if (d > -0x10000 && d < 0x10000) { dmin = Math.min(dmin, d); dmax = Math.max(dmax, d); cnt++; }
                    }
                }
            }
        }
        println(String.format("gp-relative disp range: [0x%X .. 0x%X] over %d accesses", dmin, dmax, cnt));
        println(String.format("=> gp=0x%X maps them to 0x%X .. 0x%X", gpval, gpval + dmin, gpval + dmax));

        // set gp context over the whole address space
        Address min = currentProgram.getMinAddress();
        Address max = currentProgram.getMaxAddress();
        currentProgram.getProgramContext().setValue(gp, min, max, BigInteger.valueOf(gpval));
        println("set gp = 0x" + Long.toHexString(gpval) + " over " + min + ".." + max);

        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        ConsoleTaskMonitor mon = new ConsoleTaskMonitor();
        FunctionManager fm = currentProgram.getFunctionManager();
        for (int i = 1; i < args.length; i++) {
            long off = Long.parseLong(args[i].replace("0x", ""), 16);
            Address a = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(off);
            Function f = fm.getFunctionContaining(a);
            println("\n################ " + (f==null?("0x"+Long.toHexString(off)+" <none>"):(f.getName()+" @0x"+Long.toHexString(f.getEntryPoint().getOffset()))) + " ################");
            if (f == null) continue;
            DecompileResults r = dec.decompileFunction(f, 120, mon);
            if (r != null && r.getDecompiledFunction() != null) println(r.getDecompiledFunction().getC());
            else println("  <decompile failed>");
        }
        println("\nDONE");
    }
}
