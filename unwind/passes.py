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
# 
# Each instance of Block contains a list of Opcode instances. Split that list
# into non-overlapping BasicBlock instances, each of which contain a chunk of
# consecutive opcodes. The basic blocks are temporary and are only used to
# recover control structures.
################################################################################

_absolute_jumping_opcodes = [op.POP_JUMP_IF_TRUE, op.JUMP_IF_FALSE_OR_POP, op.POP_JUMP_IF_FALSE, op.JUMP_IF_TRUE_OR_POP, op.JUMP_ABSOLUTE]
_relative_jumping_opcodes = [op.JUMP_IF_FALSE, op.JUMP_IF_TRUE, op.JUMP_FORWARD]
_jumping_opcodes = _absolute_jumping_opcodes + _relative_jumping_opcodes
_exiting_opcodes = [op.RETURN_VALUE, op.RETURN_NONE, op.RAISE_EXCEPTION, op.RAISE_VARARGS]

class ComputeBasicBlocks(CloneVisitor):
    def run(self, node):
        return node.accept(self)

    def get_targets(self, o):
        targets = []
        if o.op in _jumping_opcodes:
            if o.op in _relative_jumping_opcodes:
                targets.append(o.arg.value + o.offset + o.size)
            else:
                targets.append(o.arg.value)
            targets.append(o.offset + o.size)
        return targets

    def create_basic_blocks(self, opcodes):
        # Compute all jump targets, which mark the beginning of basic blocks.
        # This assumes that node.nodes contains only Opcode instances.
        jump_targets = set()
        for o in opcodes:
            if not jump_targets:
                jump_targets.add(o.offset)
            jump_targets |= set(self.get_targets(o))
            if o.op in _exiting_opcodes:
                jump_targets.add(o.offset + o.size)

        # Construct the basic blocks using the jump targets
        bb_list = []
        start_to_bb = {}
        bb = None
        for o in opcodes:
            if o.offset in jump_targets:
                bb = BasicBlock(o.offset, [], [], None)
                start_to_bb[bb.start] = bb
                bb_list.append(bb)
            bb.nodes.append(o.accept(self))

        # Fill in the next field for all basic blocks, which contains a list of
        # the blocks that control flow will pass into. Blocks ending in
        # conditional jumps will have two next blocks (true then false), ones
        # ending in unconditional jumps will have one next block, and others
        # will have no next blocks.
        for bb in bb_list:
            last = bb.nodes[-1]
            bb.next = [start_to_bb[s] for s in self.get_targets(last)]
            if not bb.next and last.op not in _exiting_opcodes and last.offset + last.size in start_to_bb:
                bb.next.append(start_to_bb[last.offset + last.size])

        return bb_list

    # Compute dominators for all basic blocks in blocks starting from start.
    # Block A dominates block B if every path from start to B passes through A.
    def compute_dominators(self, blocks, start):
        # Temporarily add prev, the opposite of next, to each block
        for b in blocks:
            b.prev = []
        for b in blocks:
            for n in b.next:
                n.prev.append(b)

        # Set up dominators to initially contain all blocks
        start.dominators = set([start])
        pending = set(blocks) - set([start])
        for b in pending:
            b.dominators = set(blocks)

        # Iteratively refine dominators until convergence
        changed = True
        while changed:
            changed = False
            for b in pending:
                dominators = set(blocks)
                for prev in b.prev:
                    dominators &= prev.dominators
                dominators |= set([b])
                if dominators != b.dominators:
                    b.dominators = dominators
                    changed = True

        # Compute the immediate dominators
        for b in blocks:
            target_set = b.dominators - set([b])
            immediate_dominators = [x for x in b.dominators if x.dominators == target_set]
            b.dominator = immediate_dominators[0] if len(immediate_dominators) == 1 else None

        # Remove temporary attributes
        for b in blocks:
            delattr(b, 'prev')
            delattr(b, 'dominators')

    def visit_Block(self, node):
        nodes = self.create_basic_blocks(node.nodes)
        self.compute_dominators(nodes, nodes[0])
        return Block(*nodes)

# Temporary node added to the AST by ComputeBasicBlocks to store basic blocks.
# A basic block is a unit of control flow. Control flow only enters a basic
# block from the start and only leaves a basic block from the end.
class BasicBlock(Node):
    def __init__(self, start, nodes, next, dominator):
        self.start = start
        self.nodes = nodes if nodes else []
        self.next = next if next else []
        self.dominator = dominator

    def __str__(self):
        return 'BasicBlock(%d, [ # next = %s, dominator = %s\n%s\n])' % (
            self.start, str([n.start for n in self.next]), self.dominator.start if self.dominator else None,
            '\n'.join('    ' + line for line in ',\n'.join(map(str, self.nodes)).split('\n')))

################################################################################
# class DecompileControlStructures
# 
# Reconstruct control structures and remove temporary BasicBlock instances.
################################################################################

class DecompileControlStructures(CloneVisitor):
    def run(self, node):
        return node.accept(self)

    def visit_BasicBlock(self, node):
        return BasicBlock(node.start, [n.accept(self) for n in node.nodes], node.next, node.dominator)
