from unwind.disasm import disassemble
import unwind.codegen as codegen
import unwind.passes as passes

def decompile(path):
    passes_to_run = [
        passes.CodeObjectsToNodes(),
        passes.ComputeBasicBlocks(),
        passes.DecompileControlStructures(),
    ]
    result = disassemble(path)
    for p in passes_to_run:
        result = p.run(result)
    result = passes.Context().decompile(result)
    return result.accept(codegen.SourceCodeGenerator())
