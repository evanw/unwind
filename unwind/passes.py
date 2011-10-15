import unwind.op as op
import unwind.disasm as disasm
from unwind.ast import *

################################################################################
# class CodeObjectsToNodes
# 
# Converts disassembled output to an AST. This allows the disassembler to be a
# separate component without depending on the AST.
################################################################################

class CodeObjectsToNodes:
    def run(self, module):
        return self._convert(module.body)

    def _convert(self, value):
        if isinstance(value, disasm.Module):
            return self._covert(value.body)
        elif isinstance(value, disasm.CodeObject):
            return Block(*[self._convert(x) for x in value.opcodes])
        elif isinstance(value, disasm.Opcode):
            arg = value.argument
            if isinstance(arg, list): arg = List(*[self._convert(x) for x in arg])
            elif isinstance(arg, tuple): arg = Tuple(*[self._convert(x) for x in arg])
            elif isinstance(arg, set): arg = Call(Ident('set'), Tuple(*[self._convert(x) for x in arg]))
            elif isinstance(arg, frozenset): arg = Call(Ident('frozenset'), Tuple(*[self._convert(x) for x in arg]))
            else: arg = self._convert(arg)
            return Opcode(value.offset, value.size, value.opcode, arg if op.has_argument(value.opcode) else None)
        else:
            return Const(value)

################################################################################
# class ComputeBasicBlocks
################################################################################

_absolute_jumping_opcodes = [op.POP_JUMP_IF_TRUE, op.JUMP_IF_FALSE_OR_POP, op.POP_JUMP_IF_FALSE, op.JUMP_IF_TRUE_OR_POP, op.JUMP_ABSOLUTE]
_relative_jumping_opcodes = [op.JUMP_IF_FALSE, op.JUMP_IF_TRUE, op.JUMP_FORWARD]
_jumping_opcodes = _absolute_jumping_opcodes + _relative_jumping_opcodes

class ComputeBasicBlocks(CloneVisitor):
    def run(self, node):
        return node.accept(self)

    def visit_Block(self, node):
        # Compute all jump targets, which mark the beginning of basic blocks.
        # This assumes that node.nodes contains only Opcode instances.
        jump_targets = []
        for o in node.nodes:
            if not jump_targets:
                jump_targets.append(o.offset)
            elif o.op in _jumping_opcodes:
                jump_targets.append(o.offset + o.size)
                if o.op in _relative_jumping_opcodes:
                    jump_targets.append(o.arg.value + o.offset + o.size)
                else:
                    jump_targets.append(o.arg.value)

        # Construct the basic blocks using the jump targets
        bb_list = []
        bb = None
        for o in node.nodes:
            if o.offset in jump_targets:
                bb = BasicBlock(o.offset, [])
                bb_list.append(bb)
            bb.nodes.append(o.accept(self))

        return Block(*bb_list)

# Temporary node added to the AST by ComputeBasicBlocks to store basic blocks.
# A basic block is a unit of control flow. Control flow only enters a basic
# block from the start and leaves a basic block from the end.
class BasicBlock(Node):
    fields = ['start', 'nodes']

    def __str__(self):
        return 'BasicBlock(%d, [\n%s\n])' % (self.start, '\n'.join('    ' + line for line in ',\n'.join(map(str, self.nodes)).split('\n')))

################################################################################
# class DecompileControlStructures
################################################################################

class DecompileControlStructures(CloneVisitor):
    def run(self, node):
        return node.accept(self)

    def visit_BasicBlock(self, node):
        return BasicBlock(node.start, [n.accept(self) for n in node.nodes])
