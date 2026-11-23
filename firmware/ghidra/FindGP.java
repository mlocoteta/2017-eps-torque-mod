// Find the V850 global pointer (gp) value: list instructions that write gp,
// with constant-propagated results, and report the program-context gp at a few
// handler addresses where Ghidra already resolved a gp-relative access.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.lang.Register;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.RefType;
import java.math.BigInteger;

public class FindGP extends GhidraScript {
    public void run() throws Exception {
        Register gp = currentProgram.getRegister("gp");
        if (gp == null) gp = currentProgram.getRegister("r4");
        println("gp register = " + gp);

        println("\n=== instructions that WRITE gp ===");
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        int n = 0;
        while (it.hasNext()) {
            Instruction ins = it.next();
            for (Object o : ins.getResultObjects()) {
                if (o.equals(gp)) {
                    println(String.format("  0x%08X  %s", ins.getAddress().getOffset(), ins.toString()));
                    n++;
                }
            }
        }
        println("  (" + n + " gp-writes)");

        println("\n=== program-context gp value at sample addresses ===");
        long[] probes = {0x214a0L, 0x23610L, 0x23200L, 0x2338cL, 0x128a8L};
        for (long p : probes) {
            Address a = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(p);
            BigInteger v = currentProgram.getProgramContext().getValue(gp, a, false);
            println(String.format("  @0x%06X  gp = %s", p, v == null ? "<unset>" : "0x" + v.toString(16)));
        }

        // Also report any gp-relative reference targets Ghidra resolved near the parser,
        // which pin gp = target - displacement.
        println("\nDONE");
    }
}
