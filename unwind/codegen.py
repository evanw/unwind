from unwind.ast import *

# Helper function to indent a chunk of text
def _indent(text, indent):
    return '\n'.join(indent + line for line in text.split('\n'))

# A node visitor that generates Python source code
class SourceCodeGenerator:
    def __init__(self, indent='    '):
        self.indent = indent

    def visit_Block(self, node):
        return '\n'.join(n.accept(self) for n in node.nodes)

    def visit_Tuple(self, node):
        if len(node.nodes) == 1: return '(%s,)' % node.nodes[0].accept(self)
        return '(%s)' % ', '.join(n.accept(self) for n in node.nodes)

    def visit_List(self, node):
        return '[%s]' % ', '.join(n.accept(self) for n in node.nodes)

    def visit_Print(self, node):
        return 'print ' + ', '.join(n.accept(self) for n in node.nodes) if node.nodes else 'print'

    def visit_PrintNoNewline(self, node):
        return 'print' + ''.join(' %s,' % n.accept(self) for n in node.nodes) if node.nodes else 'print'

    def visit_Global(self, node):
        return 'global ' + ', '.join(n.accept(self) for n in node.nodes)

    def visit_Dict(self, node):
        assert all(isinstance(n, DictItem) for n in node.nodes)
        return '{%s}' % ', '.join(n.accept(self) for n in node.nodes)

    def visit_DictItem(self, node):
        return '%s: %s' % (node.key.accept(self), node.value.accept(self))

    def visit_Opcode(self, node):
        return '__asm__(%s, %s, %s, %s)' % (repr(node.offset), repr(node.size), repr(node.op), repr(node.arg))

    def visit_Const(self, node):
        return repr(node.value)

    def visit_Docstr(self, node):
        return "'''%s'''" % node.value.replace("'''", r"\'\'\'")

    def visit_Comment(self, node):
        return _indent(node.value, '# ')

    def visit_Ident(self, node):
        return node.name

    def visit_Del(self, node):
        return 'del ' + node.child.accept(self)

    def visit_Pass(self, node):
        return 'pass'

    def visit_Return(self, node):
        return 'return ' + node.child.accept(self) if node.child else 'return'

    def visit_If(self, node):
        text = 'if %s:\n%s' % (
            node.cond.accept(self),
            _indent(node.true.accept(self), self.indent),
        )
        if node.false:
            text += '\n' + ('el' if isinstance(node.false, If) else '')
            text += node.false.accept(self)
        return text

    def visit_Else(self, node):
        return 'else:\n' + _indent(node.body.accept(self), self.indent)

    def visit_Unary(self, node):
        assert node.op in Unary.ops
        format = { '`': '`%s`', 'not': 'not ' }
        child = node.child.accept(self)
        return format[node.op] % child if node.op in format else '%s%s' % (node.op, child)

    def visit_Binary(self, node):
        assert node.op in Binary.ops
        format = { '.': '%s.%s', '[]': '%s[%s]' }
        left, right = node.left.accept(self), node.right.accept(self)
        return format[node.op] % (left, right) if node.op in format else '%s %s %s' % (left, node.op, right)

    def visit_Slice(self, node):
        return '%s[%s:%s]' % (
            node.target.accept(self),
            node.lower.accept(self) if node.lower else '',
            node.upper.accept(self) if node.upper else '',
        )

    def visit_Call(self, node):
        assert isinstance(node.args, Tuple) and isinstance(node.kwargs, Dict)
        args = [n.accept(self) for n in node.args.nodes]
        if all(isinstance(n.key, Ident) for n in node.kwargs.nodes):
            args += ['%s=%s' % (n.key.name, n.value.accept(self)) for n in node.kwargs.nodes]
        else:
            args.append('**' + node.kwargs.accept(self))
        return '%s(%s)' % (node.func.accept(self), ', '.join(args))

    def visit_Raise(self, node):
        return 'raise ' + node.exception.accept(self)

    def visit_SliceRange(self, node):
        return 'slice(%s, %s, %s)' % (
            node.start.accept(self),
            node.stop.accept(self),
            node.step.accept(self),
        )

    def visit_Assign(self, node):
        return '%s = %s' % (
            node.left.accept(self),
            node.right.accept(self),
        )

    def visit_Attr(self, node):
        assert isinstance(node.right, Const)
        return '%s.%s' % (
            node.left.accept(self),
            node.right.value,
        )
