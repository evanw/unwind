'''
Provides a universal disassembler that is able to disassemble *.pyc files
from both Python 2 and Python 3. Example usage:

    import pydis
    print(pydis.dis('example.pyc'))
'''

from pydis.disasm import *
