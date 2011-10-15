from unwind.disasm import disassemble
import unwind.passes as _passes

def decompile(path):
    passes = [
        _passes.CodeObjectsToNodes(),
        _passes.ComputeBasicBlocks(),
        _passes.DecompileControlStructures(),
    ]
    result = disassemble(path)
    for p in passes:
        result = p.run(result)
    return result
