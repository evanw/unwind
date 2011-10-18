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

class ComputeBasicBlocks(ReplacementVisitor):
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
        node.nodes = self.create_basic_blocks(node.nodes)
        self.compute_dominators(node.nodes, node.nodes[0])
        return node

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

class DecompileControlStructures(ReplacementVisitor):
    def run(self, node):
        return node.accept(self)

    def build_if_statements(self, block):
        pass

    def visit_Block(self, node):
        self.replace_collection(node)
        self.build_if_statements(node)

        # Remove temporary BasicBlock instances
        node.nodes = sum([n.nodes for n in node.nodes], [])

        return node

    def visit_BasicBlock(self, node):
        return self.replace_collection(node)

################################################################################
# Old stuff
################################################################################

import re

opcode_to_binary = {
    'BINARY_SUBSCR': '[]',

    'BINARY_ADD': '+',
    'BINARY_SUBTRACT': '-',
    'BINARY_MULTIPLY': '*',
    'BINARY_DIVIDE': '/',
    'BINARY_MODULO': '%',
    'BINARY_TRUE_DIVIDE': '/',
    'BINARY_FLOOR_DIVIDE': '//',
    'BINARY_POWER': '**',
    'BINARY_LSHIFT': '<<',
    'BINARY_RSHIFT': '<<',
    'BINARY_OR': '|',
    'BINARY_AND': '&',
    'BINARY_XOR': '^',
}

compare_to_binary = [
    '<',
    '<=',
    '==',
    '!=',
    '>',
    '>=',
    'in',
    'not in',
    'is',
    'is not',
]

class Context:
    def __init__(self):
        self.global_vars = set()
        self.local_vars = set()
        self.generated_vars = set()

    # TODO: what if there's a global AND a local with the same name?
    # this is possible in bytecode, should rename the local...
    def vars(self):
        return self.global_vars | self.local_vars | self.generated_vars

    def decompile(self, node):
        assert isinstance(node, Block)

        # perform all transformations (order matters)
        node = node.accept(StackBasedOpcodeRemover(self))
        node = node.accept(CombinePrintStatements())
        node = node.accept(InlineVariables(self, node))
        node = node.accept(ReconstructDictLiterals(self, node))
        node = node.accept(InlineVariables(self, node))
        node = node.accept(CombinePrintStatements())
        node = node.accept(MakeIdentifiersValid(self, node))

        # add global statements
        if self.global_vars:
            node.nodes.insert(0, Global(*[Ident(v) for v in self.global_vars]))

        return node

# run all opcodes through a miniature virtual machine that assigns temporary results to generated variables
class StackBasedOpcodeRemover(CloneVisitor):
    def __init__(self, context):
        self.stack = []
        self.next_id = 0
        self.context = context

    def new_name(self):
        while True:
            name = '$%d' % self.next_id
            self.next_id += 1
            if name not in self.context.vars():
                break
        self.context.generated_vars.add(name)
        return name

    def assign(self, node):
        name = self.new_name()
        self.stack.append(name)
        return Assign(Ident(name), node)

    def visit_Block(self, node):
        block = Block()
        for n in node.nodes:
            new_n = n.accept(self)
            if new_n:
                block.nodes.append(new_n)
        return block

    def visit_Opcode(self, node):
        if node.op == op.LOAD_CONST:
            return self.assign(node.arg)
        elif node.op in [op.LOAD_GLOBAL, op.LOAD_NAME, op.LOAD_FAST]:
            if node.op == op.LOAD_GLOBAL:
                self.context.global_vars.add(node.arg.value)
            else:
                self.context.local_vars.add(node.arg.value)
            return self.assign(Ident(node.arg.value))
        elif node.op in [op.STORE_GLOBAL, op.STORE_NAME, op.STORE_FAST]:
            if node.op == op.STORE_GLOBAL:
                self.context.global_vars.add(node.arg.value)
            else:
                self.context.local_vars.add(node.arg.value)
            return Assign(Ident(node.arg.value), Ident(self.stack.pop()))
        elif node.op.startswith('BINARY_') or node.op.startswith('INPLACE_'):
            b = self.stack.pop()
            a = self.stack.pop()
            o = opcode_to_binary[node.op.replace('INPLACE_', 'BINARY_')]
            return self.assign(Binary(o, Ident(a), Ident(b)))
        elif node.op == op.COMPARE_OP:
            b = self.stack.pop()
            a = self.stack.pop()
            o = compare_to_binary[node.arg.value]
            return self.assign(Binary(o, Ident(a), Ident(b)))
        elif node.op == op.LOAD_ATTR:
            return self.assign(Attr(Ident(self.stack.pop()), Const(node.arg.value)))
        elif node.op == op.POP_TOP:
            self.stack.pop()
        elif node.op == op.DUP_TOP:
            self.stack.append(self.stack[-1])
        elif node.op == op.DUP_TOPX:
            self.stack += self.stack[-node.arg.value:]
        elif node.op == op.BUILD_MAP:
            return self.assign(Dict())
        elif node.op == op.STORE_MAP:
            key = self.stack.pop()
            value = self.stack.pop()
            dict = self.stack[-1]
            return Assign(Binary('[]', Ident(dict), Ident(key)), Ident(value))
        elif node.op == op.BUILD_SLICE:
            assert node.arg.value in [2, 3]
            names, self.stack = [Ident(name) for name in self.stack[-node.arg.value:]], self.stack[:-node.arg.value]
            if len(names) == 2:
                names.append(Const(None))
            return self.assign(SliceRange(*names))
        elif node.op == op.BUILD_LIST:
            names, self.stack = self.stack[-node.arg.value:], self.stack[:-node.arg.value]
            return self.assign(List(*[Ident(name) for name in names]))
        elif node.op == op.RAISE_VARARGS:
            if node.arg.value == 1:
                return Raise(Ident(self.stack.pop()))
            else:
                return node
        elif node.op == op.CALL_FUNCTION:
            kwarg_count = node.arg.value >> 8
            kwargs = Dict()
            for i in range(kwarg_count):
                value = Ident(self.stack.pop())
                key = Ident(self.stack.pop())
                kwargs.nodes.insert(0, DictItem(key, value))
            arg_count = node.arg.value & 0xFF
            args = Tuple()
            for i in range(arg_count):
                args.nodes.insert(0, Ident(self.stack.pop()))
            return self.assign(Call(Ident(self.stack.pop()), args, kwargs))
        elif node.op == op.PRINT_ITEM:
            return PrintNoNewline(Ident(self.stack.pop()))
        elif node.op == op.PRINT_NEWLINE:
            return Print()
        elif node.op == op.RETURN_VALUE:
            return Return(Ident(self.stack.pop()))
        elif node.op == op.ROT_TWO:
            items = self.stack
            items[-1], items[-2] = items[-2], items[-1]
        elif node.op == op.ROT_THREE:
            items = self.stack
            items[-1], items[-2], items[-3] = items[-2], items[-3], items[-1]
        elif node.op == op.BUILD_TUPLE:
            items = self.stack
            names, self.stack = items[-node.arg.value:], items[:-node.arg.value]
            return self.assign(Tuple(*(Ident(n) for n in names)))
        elif node.op == op.UNPACK_SEQUENCE:
            names = [self.new_name() for i in range(node.arg.value)]
            name = self.stack.pop()
            self.stack += reversed(names)
            return Assign(Tuple(*(Ident(n) for n in names)), Ident(name))
        elif node.op == op.SET_LINENO:
            pass
        else:
            return node

    def visit_If(self, node):
        cond = node.cond.accept(self)

        # process true branch
        old_stack = list(self.stack)
        true = node.true.accept(self)
        true_stack = list(self.stack)

        # process false branch
        if node.false:
            self.stack = old_stack
            false = node.false.accept(self)
            false_stack = list(self.stack)

            # stack depth cannot change across an if statement
            assert len(true_stack) == len(false_stack)

            # helper class
            class RenameVisitor(DefaultVisitor):
                def __init__(self, new_names, old_names):
                    self.mapping = dict(zip(old_names, new_names))

                def visit_Ident(self, node):
                    node.name = self.mapping.get(node.name, node.name)

            # merge true_stack and false_stack
            self.stack = [self.new_name() for i in true_stack]
            true.accept(RenameVisitor(self.stack, true_stack))
            false.accept(RenameVisitor(self.stack, false_stack))
        else:
            false = None

            # stack depth cannot change across an if statement
            assert len(old_stack) == len(true_stack)

        return If(cond, true, false)

# find the number of times every identifier is read from and written to
class FindUses(DefaultVisitor):
    def __init__(self):
        self.read_counts = {}
        self.write_counts = {}

    def visit_Block(self, node):
        for n in node.nodes:
            if isinstance(n, Assign) and isinstance(n.left, Ident):
                self.write_counts[n.left.name] = self.write_counts.get(n.left.name, 0) + 1
                n.right.accept(self)
            else:
                n.accept(self)

    def visit_Ident(self, node):
        self.read_counts[node.name] = self.read_counts.get(node.name, 0) + 1

# rename identifiers according to the provided map
class IdentReplacer(CloneVisitor):
    def __init__(self, map):
        self.map = map

    def replaced_everything(self):
        return not self.map

    def visit_Ident(self, node):
        if node.name in self.map:
            return self.map[node.name].accept(self)
        return Ident(node.name)

# generate a list of identifiers and constants that can be used to
# compare evaluation order of the contents of two sets of nodes
class EvaluationOrder(DefaultVisitor):
    def __init__(self, names_to_ignore):
        self.order = []
        self.names_to_ignore = names_to_ignore

    def visit_Ident(self, node):
        if node.name not in self.names_to_ignore:
            self.order.append(node)

    def visit_Const(self, node):
        self.order.append(node)

    def visit_Assign(self, node):
        # different order on assignment
        node.right.accept(self)
        node.left.accept(self)

    @staticmethod
    def get_order(nodes, names_to_ignore):
        gen = EvaluationOrder(names_to_ignore)
        for n in nodes:
            n.accept(gen)
        return gen.order

# combine "print x,; print y,; print" to "print x, y"
class CombinePrintStatements(CloneVisitor):
    def visit_Block(self, node):
        node = CloneVisitor.visit_Block(self, node)
        i = 0
        while i + 1 < len(node.nodes):
            a, b = node.nodes[i:i + 2]
            if isinstance(a, PrintNoNewline) and (isinstance(b, Print) or isinstance(b, PrintNoNewline)):
                b.nodes = a.nodes + b.nodes
                del node.nodes[i]
            else:
                i += 1
        return node

# reconstruct a dict literal from the series of assignments that
# are generated by a BUILD_MAP followed by a series of STORE_MAPs
# note: must be run after an inlining pass for the pattern to match things correctly
class ReconstructDictLiterals(CloneVisitor):
    def __init__(self, context, node):
        self.context = context

        # find all generated variables with exactly one read and one write
        self.one_read_one_write = set()
        uses = FindUses()
        node.accept(uses)
        for name in self.context.generated_vars:
            reads = uses.read_counts.get(name, 0)
            writes = uses.write_counts.get(name, 0)
            if reads == 1 and writes == 1:
                self.one_read_one_write.add(name)

    def visit_Block(self, node):
        nodes = [n.accept(self) for n in node.nodes]
        block = Block()
        i = 0
        while i < len(nodes):
            n = nodes[i]
            block.nodes.append(n)
            i += 1

            # is this the assignment of a dictionary to a generated variable?
            if isinstance(n, Assign) and isinstance(n.left, Ident) and n.left.name in self.context.generated_vars and isinstance(n.right, Dict):
                # find a run of consecutive stores to the dictionary
                while i + 3 <= len(nodes):
                    value, key, store = nodes[i:i + 3]
                    if (
                            # match this pattern:
                            # $0 = x
                            # $1 = y
                            # $2[$1] = $0
                            not isinstance(value, Assign) or not isinstance(value.left, Ident) or value.left.name not in self.context.generated_vars or
                            not isinstance(key, Assign) or not isinstance(key.left, Ident) or key.left.name not in self.context.generated_vars or
                            not isinstance(store, Assign) or not isinstance(store.left, Binary) or store.left.op != '[]' or
                            not isinstance(store.left.left, Ident) or store.left.left.name != n.left.name or
                            not isinstance(store.left.right, Ident) or store.left.right.name != key.left.name or
                            not isinstance(store.right, Ident) or store.right.name != value.left.name or

                            # it's also important that $0 and $1 aren't used anywhere else because we are removing the definition of both $0 and $1
                            key.left.name not in self.one_read_one_write or value.left.name not in self.one_read_one_write
                        ):
                        break
                    n.right.nodes.append(DictItem(key.right, value.right))
                    i += 3

        return block

# make new names for all identifiers that aren't valid python identifiers
class MakeIdentifiersValid(CloneVisitor):
    def __init__(self, context, node):
        # start naming with a-z, then go to var#
        def gen_name():
            for i in range(26):
                yield chr(i + ord('a'))
            i = 0
            while True:
                i += 1
                yield 'var%d' % i

        # find all names in node
        self.context = context
        self.name_iter = iter(gen_name())
        self.name_map = {}

    def visit_Ident(self, node):
        old_name = node.name
        is_valid = re.match(r'^[^\d\W]\w*$', old_name)

        if is_valid:
            # don't remap valid names
            self.name_map[old_name] = old_name
        elif old_name not in self.name_map:
            # map invalid names to valid ones
            while True:
                try:
                    new_name = self.name_iter.next()
                except:
                    new_name = self.name_iter.__next__()
                if new_name not in self.context.vars():
                    break
            self.context.generated_vars.add(new_name)
            self.name_map[old_name] = new_name

        return Ident(self.name_map[old_name])

# inline variables that are only used and defined once (most often generated variables)
# note: the inliner is a huge and tricky piece of code because we don't want to change evaluation order
# - example 1:
#     $0 = 1
#     $1 = a + b
#     a = $0
#     b = $1
#   the inlining "a = 1; b = a + b" is incorrect because it has different results
# - example 2:
#     x = d()
#     y = c()
#     return y + x
#   the inlining "return c() + d()" is incorrect because of evaluation order (although "x = d(); return c() + x" is correct)
class InlineVariables(CloneVisitor):
    def __init__(self, context, node):
        # find all reads and writes of all variables within node
        self.context = context
        self.uses = FindUses()
        node.accept(self.uses)

        # pick candidates for inlining
        self.inline_candidates = set()
        for v in self.context.local_vars | self.context.generated_vars:
            reads = self.uses.read_counts.get(v, 0)
            writes = self.uses.write_counts.get(v, 0)
            if reads == 1 and writes == 1:
                self.inline_candidates.add(v)

    def visit_Block(self, node):
        while True:
            is_changed = False

            block = Block()
            i = 0
            while i < len(node.nodes):
                # find a run of writes to names in self.inline_candidates
                j = i
                names = []
                values = []
                while j < len(node.nodes):
                    n = node.nodes[j]
                    if not isinstance(n, Assign) or not isinstance(n.left, Ident) or n.left.name not in self.inline_candidates:
                        break # n is not a write to a name in self.inline_candidates
                    uses = FindUses()
                    n.right.accept(uses)
                    if any(name in uses.read_counts for name in names):
                        break # n reads a variable in names, and we might be able to inline this
                    names.append(n.left.name)
                    values.append(n.right)
                    j += 1

                # # find a run of reads of all the names found in the run of writes
                remaining = set(names)
                while remaining and j < len(node.nodes):
                    n = node.nodes[j]
                    uses = FindUses()
                    n.accept(uses)
                    remaining -= set(uses.read_counts.keys())
                    j += 1

                # if there's a potential inlining opportunity, try to inline but only accept the inline if evaluation order doesn't change
                if names and not remaining:
                    # perform the inlining
                    replacer = IdentReplacer(dict(zip(names, values)))
                    results = [n.accept(replacer) for n in node.nodes[i + len(names):j]]

                    # convert to parallel assignment if possible
                    if len(results) >= 2 and all(isinstance(n, Assign) and isinstance(n.left, Ident) for n in results):
                        results = [Assign(
                            Tuple(*[n.left for n in results]),
                            Tuple(*[n.right for n in results]),
                        )]

                    # check that the evaluation order didn't change
                    before = EvaluationOrder.get_order(node.nodes[i:j], names)
                    after = EvaluationOrder.get_order(results, names)

                    # only accept the inline if the evaluation order is the same
                    if before == after:
                        block.nodes += results
                        i = j
                        is_changed = True
                        continue

                # it didn't work, clone the node as usual
                block.nodes.append(node.nodes[i].accept(self))
                i += 1

            # do another inlining pass if we changed things on this pass
            if is_changed:
                node = block
            else:
                break

        return block
