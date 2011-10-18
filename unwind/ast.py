# Helper function to indent a chunk of text
def _indent(text, indent):
    return '\n'.join(indent + line for line in text.split('\n'))

# Abstract base class for all nodes
class Node:
    def __init__(self, *args):
        assert len(self.fields) == len(args)
        for f, arg in zip(self.fields, args):
            setattr(self, f, arg)

    def children(self):
        fields = [getattr(self, f) for f in self.fields]
        return [c for c in fields if isinstance(c, Node)]

    def __str__(self):
        fields = ', '.join(repr(getattr(self, f)) for f in self.fields)
        return self.__class__.__name__ + '(%s)' % fields

    def __repr__(self):
        return str(self)

    def accept(self, visitor):
        return getattr(visitor, 'visit_' + self.__class__.__name__)(self)

    def __hash__(self):
        # Note: this means separate nodes with equivalent contents will *not*
        # likely fall in the same bin and so cannot be used in sets
        return id(self)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
            all(getattr(self, f) == getattr(other, f) for f in self.fields)

class _Collection(Node):
    def __init__(self, *nodes):
        self.nodes = list(nodes)

    def children(self):
        return self.nodes

    def __str__(self):
        fields = ',\n'.join(str(n) for n in self.nodes)
        return self.__class__.__name__ + ('(\n%s\n)' % _indent(fields, '    ') if fields else '()')

    def __hash__(self):
        # Note: this means separate nodes with equivalent contents will *not*
        # likely fall in the same bin and so cannot be used in sets
        return id(self)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.nodes == other.nodes

class Block(_Collection):
    pass

class Tuple(_Collection):
    pass

class List(_Collection):
    pass

class Print(_Collection):
    pass

class PrintNoNewline(_Collection):
    pass

class Global(_Collection):
    pass

class Dict(_Collection):
    pass

class DictItem(Node):
    fields = ['key', 'value']

class Opcode(Node):
    fields = ['offset', 'size', 'op', 'arg']

class Const(Node):
    fields = ['value']

class Docstr(Node):
    fields = ['value']

class Comment(Node):
    fields = ['value']

class Ident(Node):
    fields = ['name']

class Del(Node):
    fields = ['child']

class Pass(Node):
    fields = []

class Return(Node):
    fields = ['child']

class If(Node):
    fields = ['cond', 'true', 'false']

class Else(Node):
    fields = ['body']

class Unary(Node):
    fields = ['op', 'child']
    ops = ['+', '-', '`', '~', 'not']

class Binary(Node):
    fields = ['op', 'left', 'right']
    ops = [
        '+', '-', '*', '/', '%', '**', '//', '&', '|', '^', '<<', '>>',
        'and', 'or', 'is', 'is not', 'in', 'not in',
        '<', '<=', '==', '!=', '>', '>=',
        '[]',
    ]

class Slice(Node):
    fields = ['target', 'lower', 'upper']

class Call(Node):
    fields = ['func', 'args', 'kwargs']

class Raise(Node):
    fields = ['exception']

class SliceRange(Node):
    fields = ['start', 'stop', 'step']

class Assign(Node):
    fields = ['left', 'right']

class Attr(Node):
    fields = ['left', 'right']

# A node visitor that visits all nodes but does nothing
class DefaultVisitor:
    def visit_children(self, node):
        for c in node.children():
            c.accept(self)

    def visit_Block(self, node): return self.visit_children(node)
    def visit_Tuple(self, node): return self.visit_children(node)
    def visit_List(self, node): return self.visit_children(node)
    def visit_Print(self, node): return self.visit_children(node)
    def visit_PrintNoNewline(self, node): return self.visit_children(node)
    def visit_Global(self, node): return self.visit_children(node)
    def visit_Dict(self, node): return self.visit_children(node)
    def visit_DictItem(self, node): return self.visit_children(node)
    def visit_Opcode(self, node): return self.visit_children(node)
    def visit_Const(self, node): return self.visit_children(node)
    def visit_Docstr(self, node): return self.visit_children(node)
    def visit_Comment(self, node): return self.visit_children(node)
    def visit_Ident(self, node): return self.visit_children(node)
    def visit_Del(self, node): return self.visit_children(node)
    def visit_Pass(self, node): return self.visit_children(node)
    def visit_Return(self, node): return self.visit_children(node)
    def visit_If(self, node): return self.visit_children(node)
    def visit_Else(self, node): return self.visit_children(node)
    def visit_Unary(self, node): return self.visit_children(node)
    def visit_Binary(self, node): return self.visit_children(node)
    def visit_Slice(self, node): return self.visit_children(node)
    def visit_Call(self, node): return self.visit_children(node)
    def visit_Raise(self, node): return self.visit_children(node)
    def visit_SliceRange(self, node): return self.visit_children(node)
    def visit_Assign(self, node): return self.visit_children(node)
    def visit_Attr(self, node): return self.visit_children(node)

# A node visitor where each visit method returns the node, allowing subclasses
# to replace nodes easily
class ReplacementVisitor:
    def replace_collection(self, node):
        node.nodes = [n.accept(self) for n in node.nodes]
        return node

    def visit_Block(self, node): return self.replace_collection(node)
    def visit_Tuple(self, node): return self.replace_collection(node)
    def visit_List(self, node): return self.replace_collection(node)
    def visit_Print(self, node): return self.replace_collection(node)
    def visit_PrintNoNewline(self, node): return self.replace_collection(node)
    def visit_Global(self, node): return self.replace_collection(node)
    def visit_Dict(self, node): return self.replace_collection(node)

    def replace_fields(self, node):
        for f in node.fields:
            n = getattr(node, f)
            if isinstance(n, Node):
                setattr(node, f, n.accept(self))
        return node

    def visit_DictItem(self, node): return self.replace_fields(node)
    def visit_Opcode(self, node): return self.replace_fields(node)
    def visit_Const(self, node): return self.replace_fields(node)
    def visit_Docstr(self, node): return self.replace_fields(node)
    def visit_Comment(self, node): return self.replace_fields(node)
    def visit_Ident(self, node): return self.replace_fields(node)
    def visit_Del(self, node): return self.replace_fields(node)
    def visit_Pass(self, node): return self.replace_fields(node)
    def visit_Return(self, node): return self.replace_fields(node)
    def visit_If(self, node): return self.replace_fields(node)
    def visit_Else(self, node): return self.replace_fields(node)
    def visit_Unary(self, node): return self.replace_fields(node)
    def visit_Binary(self, node): return self.replace_fields(node)
    def visit_Slice(self, node): return self.replace_fields(node)
    def visit_Call(self, node): return self.replace_fields(node)
    def visit_Raise(self, node): return self.replace_fields(node)
    def visit_SliceRange(self, node): return self.replace_fields(node)
    def visit_Assign(self, node): return self.replace_fields(node)
    def visit_Attr(self, node): return self.replace_fields(node)

# A node visitor that clones all visited nodes, can be used as a base for other
# visitor subclasses
class CloneVisitor:
    def clone_collection(self, node):
        return node.__class__(*[n.accept(self) for n in node.nodes])

    def visit_Block(self, node): return self.clone_collection(node)
    def visit_Tuple(self, node): return self.clone_collection(node)
    def visit_List(self, node): return self.clone_collection(node)
    def visit_Print(self, node): return self.clone_collection(node)
    def visit_PrintNoNewline(self, node): return self.clone_collection(node)
    def visit_Global(self, node): return self.clone_collection(node)
    def visit_Dict(self, node): return self.clone_collection(node)

    def clone(self, node):
        fields = [getattr(node, f) for f in node.__class__.fields]
        return node.__class__(*[f.accept(self) if isinstance(f, Node) else f for f in fields])

    def visit_DictItem(self, node): return self.clone(node)
    def visit_Opcode(self, node): return self.clone(node)
    def visit_Const(self, node): return self.clone(node)
    def visit_Docstr(self, node): return self.clone(node)
    def visit_Comment(self, node): return self.clone(node)
    def visit_Ident(self, node): return self.clone(node)
    def visit_Del(self, node): return self.clone(node)
    def visit_Pass(self, node): return self.clone(node)
    def visit_Return(self, node): return self.clone(node)
    def visit_If(self, node): return self.clone(node)
    def visit_Else(self, node): return self.clone(node)
    def visit_Unary(self, node): return self.clone(node)
    def visit_Binary(self, node): return self.clone(node)
    def visit_Slice(self, node): return self.clone(node)
    def visit_Call(self, node): return self.clone(node)
    def visit_Raise(self, node): return self.clone(node)
    def visit_SliceRange(self, node): return self.clone(node)
    def visit_Assign(self, node): return self.clone(node)
    def visit_Attr(self, node): return self.clone(node)
