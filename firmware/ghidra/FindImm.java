// Find instructions whose operand includes any of the given immediate values.
// Args = immediates (hex). Prints addr, instruction, containing function.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import java.util.*;

public class FindImm extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Set<Long> want = new HashSet<Long>();
        for (String a: args) want.add(Long.parseLong(a.replace("0x",""),16));
        FunctionManager fm = currentProgram.getFunctionManager();
        // tally hits per function to surface the UDS stack
        Map<String,Integer> byFunc = new TreeMap<String,Integer>();
        InstructionIterator it=currentProgram.getListing().getInstructions(true);
        List<String> lines = new ArrayList<String>();
        while(it.hasNext()){
            Instruction ins=it.next();
            for (int oi=0;oi<ins.getNumOperands();oi++)
                for (Object rep: ins.getOpObjects(oi))
                    if (rep instanceof Scalar){
                        long v=((Scalar)rep).getUnsignedValue()&0xffff;
                        if (want.contains(v)){
                            Function f=fm.getFunctionContaining(ins.getAddress());
                            String fn=f==null?"?":f.getName();
                            lines.add(String.format("  0x%06X  %-26s imm=0x%X  %s",
                                ins.getAddress().getOffset(), ins.toString(), v, fn));
                            byFunc.put(fn, byFunc.getOrDefault(fn,0)+1);
                        }
                    }
        }
        println("=== functions by UDS-SID immediate hit count (candidates = high count) ===");
        List<Map.Entry<String,Integer>> es=new ArrayList<Map.Entry<String,Integer>>(byFunc.entrySet());
        es.sort((x,y)->y.getValue()-x.getValue());
        for (Map.Entry<String,Integer> e: es) if (e.getValue()>=2) println(String.format("  %4d  %s", e.getValue(), e.getKey()));
        println("\n=== all hits ===");
        for (String l: lines) println(l);
        println("\nDONE");
    }
}
