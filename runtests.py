import os
import unwind

def test_file(path, versions):
    for version in versions:
        os.system('%s -m py_compile "%s"' % (version, path))
        print(unwind.disassemble(path + 'c'))

versions = ['python2.6', 'python3.1']
test_file('tests/datatypes.py', versions)
test_file('tests/operators.py', versions)
test_file('tests/controlstructures.py', versions)
