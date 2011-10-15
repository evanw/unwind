import unwind.disasm as disasm
from unwind.passes import *

def decompile(path):
    passes = [
        CodeObjectsToNodes(),
        ComputeBasicBlocks(),
        DecompileControlStructures(),
    ]
    result = disasm.dis(path)
    for p in passes:
        result = p.run(result)
    return result

print decompile('temp.pyc')
