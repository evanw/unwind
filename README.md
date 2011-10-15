# unwind - A disassembler for Python bytecode

This module provides a universal disassembler that is able to disassemble *.pyc files from both Python 2 and Python 3. Example usage:

    import unwind
    print(unwind.disassemble('example.pyc'))

The disassembler allows one version of Python to unmarshal code compiled by all other versions of Python. This is made possible by scraping information from the official Python repository at http://hg.python.org/cpython. In the example below, the code `print('Hello, World')` is compiled and disassembled from both Python 2.5 and Python 3.1. Notice how Python 2.5 uses the `PRINT_ITEM` opcode but Python 3.1 uses the `CALL_FUNCTION` opcode, since the print statement was removed in Python 3.

    $ cat > example.py
    print('Hello, World')
    $ python2.5 -m py_compile example.py
    $ python -c 'import unwind; print unwind.disassemble("example.pyc")'
    Module(
        magic = 168686259,
        timestamp = 1318574250,
        python_version = 'Python 2.6a0',
        body = CodeObject(
            co_argcount = 0,
            co_kwonlyargcount = 0,
            co_nlocals = 0,
            co_stacksize = 1,
            co_flags = 64,
            co_filename = 'example.py',
            co_name = '<module>',
            co_firstlineno = 1,
            opcodes = [
                Opcode(offset = 0, opcode = 'LOAD_CONST', argument = 'Hello, World'),
                Opcode(offset = 3, opcode = 'PRINT_ITEM', argument = None),
                Opcode(offset = 4, opcode = 'PRINT_NEWLINE', argument = None),
                Opcode(offset = 5, opcode = 'LOAD_CONST', argument = None),
                Opcode(offset = 8, opcode = 'RETURN_VALUE', argument = None)])))
    $ python3.1 -m py_compile example.py
    $ python -c 'import unwind; print unwind.disassemble("example.pyc")'
    Module(
        magic = 168627279,
        timestamp = 1318574250,
        python_version = 'Python 3.2a0',
        body = CodeObject(
            co_argcount = 0,
            co_kwonlyargcount = 0,
            co_nlocals = 0,
            co_stacksize = 2,
            co_flags = 64,
            co_filename = u'example.py',
            co_name = u'<module>',
            co_firstlineno = 1,
            opcodes = [
                Opcode(offset = 0, opcode = 'LOAD_NAME', argument = u'print'),
                Opcode(offset = 3, opcode = 'LOAD_CONST', argument = u'Hello, World'),
                Opcode(offset = 6, opcode = 'CALL_FUNCTION', argument = 1),
                Opcode(offset = 9, opcode = 'POP_TOP', argument = None),
                Opcode(offset = 10, opcode = 'LOAD_CONST', argument = None),
                Opcode(offset = 13, opcode = 'RETURN_VALUE', argument = None)])))
