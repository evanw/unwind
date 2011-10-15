'''
disasm.disassemble(path)
    Disassemble a python module from a *.pyc file. Returns a disasm.Module with
    the disassembly or raises a disasm.DisassemblerException if there was an
    error.

disasm.Module, disasm.CodeObject, disasm.Opcode
    Used to represent the disassembled module. Constant values are
    represented using native Python objects.

disasm.DisassemblerException
    Thrown by disasm.disassemble() when there was a problem with the
    disassembly. Apply str() to an exception to get a detailed description
    of the error.
'''

import unwind.op as op
import sys
import time
import struct

def disassemble(path):
    '''
    Disassemble a python module from file_object, an open file object
    containing a *.pyc file. Returns a disasm.Module with the disassembly
    or raises a disasm.DisassemblerException if there was an error.
    '''
    return _Disassembler().disassemble(open(path, 'rb'))

class DisassemblerException(Exception):
    '''
    Thrown by disasm.disassemble() when there was a problem with the
    disassembly. Apply str() to an exception to get a detailed description
    of the error.
    '''

class Opcode:
    '''
    Represents a disassembled opcode.

        self.offset = number of bytes from start of code object
        self.size = number of bytes used by this opcode
        self.opcode = string with opcode name
        self.argument = Python object with argument, will be None for
                        opcodes without arguments
    '''

    def __init__(self, offset, size, opcode, argument):
        self.offset = offset
        self.size = size
        self.opcode = opcode
        self.argument = argument

    def __repr__(self):
        return 'Opcode(offset = %s, size = %s, opcode = %s, argument = %s)' % (repr(self.offset), repr(self.size), repr(self.opcode), repr(self.argument))

class CodeObject:
    '''
    Represents a disassembled Python code object.

        self.co_argcount = number of arguments (not including * or ** args)
        self.co_kwonlyargcount = number of keyword arguments
        self.co_nlocals = number of local variables
        self.co_stacksize = virtual machine stack space required
        self.co_flags = bitmap: 1=optimized | 2=newlocals | 4=*arg | 8=**arg
        self.co_code = list of raw compiled bytecode
        self.co_consts = tuple of constants used in the bytecode
        self.co_names = tuple of names of local variables
        self.co_varnames = tuple of names of arguments and local variables
        self.co_freevars = tuple of names of variables used by parent scope
        self.co_cellvars = tuple of names of variables used by child scopes
        self.co_filename = file in which this code object was created
        self.co_name = name with which this code object was defined
        self.co_firstlineno = number of first line in Python source code
        self.co_lnotab = encoded mapping of line numbers to bytecode indices
        self.opcodes = list of disasm.Opcode instances
    '''

    def __init__(self, co_argcount=None, co_kwonlyargcount=None, co_nlocals=None, co_stacksize=None,
                 co_flags=None, co_code=None, co_consts=None, co_names=None, co_varnames=None,
                 co_freevars=None, co_cellvars=None, co_filename=None, co_name=None,
                 co_firstlineno=None, co_lnotab=None, opcodes=None):
        self.co_argcount = co_argcount
        self.co_kwonlyargcount = co_kwonlyargcount
        self.co_nlocals = co_nlocals
        self.co_stacksize = co_stacksize
        self.co_flags = co_flags
        self.co_code = co_code
        self.co_consts = co_consts
        self.co_names = co_names
        self.co_varnames = co_varnames
        self.co_freevars = co_freevars
        self.co_cellvars = co_cellvars
        self.co_filename = co_filename
        self.co_name = co_name
        self.co_firstlineno = co_firstlineno
        self.co_lnotab = co_lnotab
        self.opcodes = opcodes if opcodes else []

    def __repr__(self):
        global _indent
        result = 'CodeObject(\n'
        _indent += 1
        indent = _indent * _INDENT
        for f in ['co_argcount', 'co_kwonlyargcount', 'co_nlocals', 'co_stacksize',
                  'co_flags', 'co_filename', 'co_name', 'co_firstlineno']:
            result += indent + f + ' = %s,\n' % repr(getattr(self, f))
        _indent += 1
        result += indent + 'opcodes = [%s])' % ','.join('\n' + _indent * _INDENT + repr(o) for o in self.opcodes)
        _indent -= 2
        return result + ')'

class Module:
    '''
    Represents a disassembled Python module.

        self.magic = 32-bit magic number from marshal format
        self.timestamp = unix timestamp when the file was compiled
        self.python_version = interpreter version as a string
        self.body = disassembled code in a disasm.CodeObject
    '''

    def __init__(self, magic, timestamp, python_version, body):
        self.magic = magic
        self.timestamp = timestamp
        self.python_version = python_version
        self.body = body

    def __repr__(self):
        global _indent
        result = 'Module(\n'
        _indent += 1
        indent = _indent * _INDENT
        result += indent + 'magic = %s,\n' % repr(self.magic)
        result += indent + 'timestamp = %s,\n' % repr(self.timestamp)
        result += indent + 'python_version = %s,\n' % repr(self.python_version)
        result += indent + 'body = %s' % repr(self.body)
        _indent -= 1
        return result + ')'

# Used by __repr__() for disassembled objects
_indent = 0
_INDENT = '    '

# Indicates the type of object to unmarshal
_TYPE_NULL = ord('0')
_TYPE_NONE = ord('N')
_TYPE_FALSE = ord('F')
_TYPE_TRUE = ord('T')
_TYPE_STOP_ITER = ord('S')
_TYPE_ELLIPSIS = ord('.')
_TYPE_INT = ord('i')
_TYPE_INT64 = ord('I')
_TYPE_FLOAT = ord('f')
_TYPE_BINARY_FLOAT = ord('g')
_TYPE_COMPLEX = ord('x')
_TYPE_BINARY_COMPLEX = ord('y')
_TYPE_LONG = ord('l')
_TYPE_STRING = ord('s')
_TYPE_INTERNED = ord('t')
_TYPE_STRING_REF = ord('R')
_TYPE_TUPLE = ord('(')
_TYPE_LIST = ord('[')
_TYPE_DICT = ord('{')
_TYPE_CODE = ord('c')
_TYPE_UNICODE = ord('u')
_TYPE_SET = ord('<')
_TYPE_FROZEN_SET = ord('>')

# Holds intermediate state useful during disassembly. Only the disassemble()
# method is meant to be called directly.
class _Disassembler:
    def __init__(self):
        self.magic = None
        self.string_table = None
        self.file = None

    def disassemble(self, file):
        self.magic, timestamp = struct.unpack('=II', file.read(8))
        self.string_table = []
        self.file = file

        version = op.python_version_from_magic(self.magic)
        if not version:
            raise DisassemblerException('Unknown magic header number %d' % self.magic)

        return Module(self.magic, timestamp, 'Python ' + version, self.unmarshal_node())

    def unmarshal_collection(self, type):
        count = self.read_int32()
        nodes = [self.unmarshal_node() for i in range(count)]
        return type(nodes)

    def read_byte_array(self):
        count = self.read_int32()
        return list(struct.unpack('=' + 'B' * count, self.file.read(count)))

    def read_string_ascii(self):
        return ''.join(chr(c) for c in self.read_byte_array())

    def read_string_utf8(self):
        count = self.read_int32()
        return self.file.read(count).decode('utf8')

    def read_int8(self):
        return struct.unpack('=b', self.file.read(1))[0]

    def read_int16(self):
        return struct.unpack('=h', self.file.read(2))[0]

    def read_int32(self):
        return struct.unpack('=i', self.file.read(4))[0]

    def unmarshal_node(self):
        type = self.read_int8()

        # Global singletons
        if type == _TYPE_NONE: return None
        elif type == _TYPE_TRUE: return True
        elif type == _TYPE_FALSE: return False

        # Collections
        elif type == _TYPE_TUPLE: return self.unmarshal_collection(tuple)
        elif type == _TYPE_LIST: return self.unmarshal_collection(list)
        elif type == _TYPE_SET: return self.unmarshal_collection(set)
        elif type == _TYPE_FROZEN_SET: return self.unmarshal_collection(frozenset)

        # Numbers
        elif type == _TYPE_INT: return self.read_int32()
        elif type == _TYPE_INT64: return struct.unpack('=q', self.file.read(8))[0]
        elif type == _TYPE_BINARY_FLOAT: return struct.unpack('=d', self.file.read(8))[0]
        elif type == _TYPE_BINARY_COMPLEX: return complex(*struct.unpack('=dd', self.file.read(16)))
        elif type == _TYPE_LONG:
            nbits = self.read_int32()
            if not nbits:
                return 0
            n = 0
            for i in range(abs(nbits)):
                digit = self.read_int16()
                n |= digit << (i * 15)
            return n if nbits > 0 else -n

        # Strings
        elif type == _TYPE_STRING: return self.read_string_ascii()
        elif type == _TYPE_UNICODE: return self.read_string_utf8()
        elif type == _TYPE_INTERNED:
            data = self.read_string_ascii()
            self.string_table.append(data)
            return data
        elif type == _TYPE_STRING_REF:
            index = self.read_int32()
            if index < 0 or index >= len(self.string_table):
                raise DisassemblerException('String index %d is outside string table' % index)
            return self.string_table[index]

        # Code objects
        elif type == _TYPE_CODE:
            co = CodeObject()
            co.co_argcount = self.read_int32()
            co.co_kwonlyargcount = self.read_int32() if op.has_kwonlyargcount(self.magic) else 0
            co.co_nlocals = self.read_int32()
            co.co_stacksize = self.read_int32()
            co.co_flags = self.read_int32()
            type = self.read_int8()
            if type != _TYPE_STRING:
                raise DisassemblerException('Bytecode was not marshalled as a string (type was 0x%02X instead of 0x%02X)' % (type, _TYPE_STRING))
            co.co_code = self.read_byte_array()
            co.co_consts = self.unmarshal_node()
            co.co_names = self.unmarshal_node()
            co.co_varnames = self.unmarshal_node()
            co.co_freevars = self.unmarshal_node()
            co.co_cellvars = self.unmarshal_node()
            co.co_filename = self.unmarshal_node()
            co.co_name = self.unmarshal_node()
            co.co_firstlineno = self.read_int32()
            co.co_lnotab = self.unmarshal_node()

            # Start disassembly
            argument = 0
            i = 0
            while i < len(co.co_code):
                offset = i
                opcode = op.from_bytecode(co.co_code[i], self.magic)
                if opcode is None:
                    raise DisassemblerException('Unknown bytecode 0x%02X' % co.co_code[i])
                i += 1

                if op.has_argument(opcode):
                    lo, hi = co.co_code[i:i + 2]
                    argument |= (lo | (hi << 8))
                    i += 2

                # The upper 16 bits of 32-bit arguments are stored in a fake
                # EXTENDED_ARG opcode that precedes the actual opcode
                if opcode == op.EXTENDED_ARG:
                    argument <<= 16
                    continue

                # Decode the opcode argument if present
                arg = None
                if op.has_argument(opcode):
                    if opcode == op.LOAD_CONST:
                        if argument >= len(co.co_consts):
                            raise DisassemblerException('Invalid argument %d for opcode %s' % (argument, opcode))
                        arg = co.co_consts[argument]
                    elif opcode in [op.LOAD_NAME, op.STORE_NAME, op.DELETE_NAME,
                                op.LOAD_ATTR, op.STORE_ATTR, op.DELETE_ATTR,
                                op.LOAD_GLOBAL, op.STORE_GLOBAL, op.DELETE_GLOBAL,
                                op.IMPORT_NAME, op.IMPORT_FROM]:
                        if argument >= len(co.co_names):
                            raise DisassemblerException('Invalid argument %d for opcode %s' % (argument, opcode))
                        arg = co.co_names[argument]
                    elif opcode in [op.LOAD_FAST, op.STORE_FAST, op.DELETE_FAST]:
                        if argument >= len(co.co_varnames):
                            raise DisassemblerException('Invalid argument %d for opcode %s' % (argument, opcode))
                        arg = co.co_varnames[argument]
                    else:
                        arg = argument

                # Record disassembled opcode
                co.opcodes.append(Opcode(offset, i - offset, opcode, arg))
                argument = 0

            return co

        else:
            raise DisassemblerException('Cannot unmarshal unknown type 0x%02X' % type)
