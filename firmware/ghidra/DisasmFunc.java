// Disassemble (listing) the function containing each arg address, with gp set.
// Usage: -postScript DisasmFunc.java 0x3ff8000 0x23200
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.lang.Register;
import ghidra.program.model.address.Address;
import java.math.BigInteger;

public class DisasmFunc extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Register gp = currentProgram.getRegister("gp");
        long gpval = Long.parseLong(args[0].replace("0x",""),16);
        currentProgram.getProgramContext().setValue(gp, currentProgram.getMinAddress(),
                currentProgram.getMaxAddress(), BigInteger.valueOf(gpval));
        FunctionManager fm = currentProgram.getFunctionManager();
        Listing lst = currentProgram.getListing();
        for (int i=1;i<args.length;i++){
            long off=Long.parseLong(args[i].replace("0x",""),16);
            Address a=currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(off);
            Function f=fm.getFunctionContaining(a);
            if(f==null){ println("0x"+Long.toHexString(off)+" <no func>"); continue; }
            println("\n### "+f.getName()+" @0x"+Long.toHexString(f.getEntryPoint().getOffset())+" ###");
            InstructionIterator it=lst.getInstructions(f.getBody(),true);
            while(it.hasNext()){
                Instruction ins=it.next();
                String cmt="";
                // show any reference the instruction makes (resolved target)
                for (ghidra.program.model.symbol.Reference r : ins.getReferencesFrom()){
                    cmt += "  -> 0x"+Long.toHexString(r.getToAddress().getOffset());
                }
                println(String.format("  0x%06X  %-28s%s", ins.getAddress().getOffset(), ins.toString(), cmt));
            }
        }
        println("\nDONE");
    }
}
