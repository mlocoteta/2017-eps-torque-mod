// Find every instruction that accesses a given gp-relative variable (disp[gp]).
// Args = gp-relative displacements (hex). Prints addr, instruction, containing func,
// and whether it's a read or write (st = write).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.lang.Register;
import ghidra.program.model.scalar.Scalar;

public class FindAccess extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Register gp = currentProgram.getRegister("gp");
        FunctionManager fm = currentProgram.getFunctionManager();
        long[] targets = new long[args.length];
        for (int i=0;i<args.length;i++) targets[i]=Long.parseLong(args[i].replace("0x",""),16);

        for (int t=0;t<targets.length;t++){
            println(String.format("\n==== disp 0x%X  (gp+disp = 0x%X) ====", targets[t], 0x03FF8000L+targets[t]));
            InstructionIterator it=currentProgram.getListing().getInstructions(true);
            while(it.hasNext()){
                Instruction ins=it.next();
                boolean usesGp=false;
                for (Object o: ins.getInputObjects()) if (o.equals(gp)) usesGp=true;
                for (Object o: ins.getResultObjects()) if (o.equals(gp)) usesGp=true;
                if(!usesGp) continue;
                boolean hit=false;
                for (int oi=0; oi<ins.getNumOperands(); oi++)
                    for (Object rep: ins.getOpObjects(oi))
                        if (rep instanceof Scalar && (((Scalar)rep).getUnsignedValue()&0xffff)==targets[t]) hit=true;
                if(!hit) continue;
                Function f=fm.getFunctionContaining(ins.getAddress());
                String m=ins.getMnemonicString();
                String rw = (m.startsWith("st")||m.startsWith("sst")) ? "WRITE" : "read ";
                println(String.format("  0x%06X  %-26s %s  in %s", ins.getAddress().getOffset(),
                        ins.toString(), rw, f==null?"?":f.getName()));
            }
        }
        println("\nDONE");
    }
}
