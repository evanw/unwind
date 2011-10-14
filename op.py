'''
op.opcodes
    A set of strings of opcode names. This set contains all opcodes from
    every revision of Python, which are extracted directly from the official
    Python Mercurial repository.

    These opcodes are normalized, which means a given opcode name will
    behave identically across all revisions but will not necessarily have
    the same official names. For example, the SET_ADD and LIST_APPEND
    opcodes have no argument in some revisions of the interpreter and take
    an argument in other revisions. This is handled by creating the separate
    SET_ADD_ARG and LIST_APPEND_ARG opcodes and decoding to those instead
    for the affected revisions.

    Pseudo-opcodes like STOP_CODE, HAVE_ARGUMENT, and EXCEPT_HANDLER (which
    will never be found in compiled bytecode) are removed. Also, slice
    opcodes like SLICE, STORE_SLICE, and DELETE_SLICE actually represent
    four opcodes and are suffixed with _0, _1, _2, and _3.

op.has_argument(opcode)
    Returns True if opcode takes an argument when represented in bytecode,
    otherwise returns False.

op.has_kwonlyargcount(magic)
    Returns True if the code objects in *.pyc files with the given magic
    number will have the co_kwonlyargcount property, otherwise returns
    False.

op.from_bytecode(bytecode, magic)
    Given bytecode, an 8-bit integer, and magic, the 32-bit magic number
    from a marshalled *.pyc file, produce a string with the name of the
    opcode or None for an invalid bytecode.

op.python_version_from_magic(magic)
    Returns a string with the Python interpreter version ("2.7b2+" for
    example). Note that there isn't a one-to-one mapping between magic
    number and version string. It is most useful for obtaining a human
    readable interpretation of a magic number.

op.LOAD_NAME, op.STORE_NAME, ...
    All opcodes are available as global names so typos result in runtime
    failures instead of silently failing string comparisons.
'''

import os
import re
import pickle
import tempfile

# Helper to run a command, also prints it for debugging
def _run(command):
    print('> ' + command)
    os.system(command)

# Helper to run a command and return the output as a string,
# also prints it for debugging
def _run_output(command):
    print('> ' + command)
    return os.popen(command).read()

# Helper to compile and run the provided C code
def _run_c_code(code):
    temp = tempfile.NamedTemporaryFile(suffix='.c', delete=False)
    temp.close()
    open(temp.name, 'w').write(code)
    _run('gcc -w %s' % temp.name)
    os.remove(temp.name)
    result = _run_output('./a.out')
    os.remove('a.out')
    return result

# Represents a clone of the official CPython repo, can return
# different versions of a given file
class _PythonRepo:
    def __init__(self, path):
        self.path = path

    def ensure_cloned(self):
        if not os.path.exists(self.path):
            _run('cd "%s" && hg clone http://hg.python.org/cpython "%s"' % os.path.split(self.path))

    def revisions_for_file(self, file):
        self.ensure_cloned()
        lines = _run_output('cd "%s" && hg log %s' % (self.path, file)).split('\n')
        regex = re.compile(r'^changeset:\s+(\d+):')
        revisions = []
        for line in lines:
            match = regex.match(line)
            if match:
                revisions.append(int(match.group(1)))
        return list(reversed(revisions))

    def revision_of_file(self, file, revision):
        self.ensure_cloned()
        return _run_output('cd "%s" && hg cat -r %d "%s"' % (self.path, revision, file))

# Step 1: Create a list of mercurial revision numbers, python marshal format
# magic numbers, and python version names, returned as a list of 3-tuples
def _gen_magic_info(repo):
    def extract_magic(data):
        code = '''
        #include <stdio.h>
        int main()
        {
            printf("%u", (unsigned int)(MAGIC));
            return 0;
        }
        '''
        magic = re.search(r'(#define\s+MAGIC[^\n]+)\n', data).group(0)
        return int(_run_c_code(magic + code))

    def extract_python_version(data):
        code = '''
        #define PATCHLEVEL "?"
        #define PY_VERSION PATCHLEVEL
        %s
        #include <stdio.h>
        int main()
        {
            puts(PY_VERSION);
            return 0;
        }
        '''
        return _run_c_code(code % data).strip()

    # Generate (mercurial revision, magic number, python version) tuples
    results = []
    revisions = repo.revisions_for_file('Python/import.c')
    for rev in revisions:
        data = repo.revision_of_file('Python/import.c', rev)
        if '#define MAGIC' in data:
            magic = extract_magic(data)
            version = extract_python_version(repo.revision_of_file('Include/patchlevel.h', rev))
            results.append((rev, magic, version))

    return results

# Step 2: For each revision, find all the opcodes that are understood by that
# revision, returned as a list of maps of bytecode values to opcode strings
def _gen_opcodes(repo, magic_info):
    def extract_opcodes(data):
        lines = data.split('\n')
        regex = re.compile(r'^#define\s+(\w+)\s+(\d+)')
        opcodes = {}
        for line in lines:
            match = regex.match(line)
            if match:
                name, value = match.group(1, 2)
                opcodes[name] = int(value)
        return opcodes

    # Extract all opcodes for each revision
    opcodes = []
    for rev, magic, version in magic_info:
        opcodes.append(extract_opcodes(repo.revision_of_file('Include/opcode.h', rev)))

    return opcodes

# Step 3: Find all revisions in which code objects have the co_kwonlyargcount
# property, which changes the way *.pyc files are unmarshalled
def _gen_has_kwonlyargcount(repo, magic_info):
    has_kwonlyargcount = []
    for rev, magic, version in magic_info:
        data = repo.revision_of_file('Python/marshal.c', rev)
        has_kwonlyargcount.append('co_kwonlyargcount' in data)
    return has_kwonlyargcount

# Represents a revision of the Python interpreter
class _Revision:
    def __init__(self, magic_info, opcodes, has_kwonlyargcount):
        self.mercurial_revision, self.magic, self.python_version = magic_info
        self.has_kwonlyargcount = has_kwonlyargcount

        # Note that self.name_to_opcode contains a superset of the information
        # available in self.opcode_to_name. For example, it will contain the
        # HAVE_ARGUMENT marker, which isn't actually an opcode. All opcodes in
        # self.opcode_to_name are the ones that will appear in compiled *.pyc
        # bytecode.
        self.name_to_opcode = opcodes

        # Given a map of opcode names to opcode integers, create a reverse mapping
        # that removes pseudo-opcodes and adds missing opcodes
        self.opcode_to_name = {}
        for name in list(self.name_to_opcode.keys()):
            opcode = self.name_to_opcode[name]
            if name in ['SLICE', 'STORE_SLICE', 'DELETE_SLICE']:
                del self.name_to_opcode[name]
                for i in range(4):
                    n = name + '_%d' % i
                    o = opcode + i
                    self.name_to_opcode[n] = o
                    self.opcode_to_name[o] = n
            elif name not in ['STOP_CODE', 'HAVE_ARGUMENT', 'EXCEPT_HANDLER']:
                self.opcode_to_name[opcode] = name

    def has_argument(self, name):
        return self.name_to_opcode[name] >= self.name_to_opcode['HAVE_ARGUMENT']

# The meaning of some opcodes have changed from < HAVE_ARGUMENT to
# >= HAVE_ARGUMENT. In that case, append _ARG to ones with >= HAVE_ARGUMENT.
# Returns a tuple of the set of all opcode names and the set of all opcode
# names whose values are >= HAVE_ARGUMENT.
def _differentiate_opcodes_by_argument(revisions):
    opcode_names = set()
    for rev in revisions:
        opcode_names |= set(rev.opcode_to_name.values())
    for name in list(opcode_names):
        has_arg = [rev.has_argument(name) for rev in revisions if name in rev.name_to_opcode]
        if any(has_arg) and not all(has_arg):
            for rev in revisions:
                opcode = rev.name_to_opcode.get(name)
                if opcode is not None and rev.has_argument(name):
                    del rev.name_to_opcode[name]
                    del rev.opcode_to_name[opcode]
                    name_arg = name + '_ARG'
                    rev.name_to_opcode[name_arg] = opcode
                    rev.opcode_to_name[opcode] = name_arg
                    opcode_names.add(name_arg)

    # Now that the argument status of each name is consistent across all
    # revisions, we can make one set where membership means that opcode
    # has an argument in all revisions
    has_argument = set()
    for rev in revisions:
        has_argument |= set(name for name in rev.opcode_to_name.values() if rev.has_argument(name))

    return opcode_names, has_argument

# Return gen() but cache the results in the file named cache
def _get_cached(cache, gen):
    try:
        return pickle.load(open(cache, 'rb'))
    except:
        print('generating ' + cache)
        result = gen()
        pickle.dump(result, open(cache, 'wb'))
        return result

# Load the revision info from the cache, or compute it on the first run
_dir = os.path.dirname(os.path.abspath(__file__))
_repo = _PythonRepo(os.path.join(_dir, '.repo'))
_magic_info = _get_cached(os.path.join(_dir, 'magic_info.pickle'), lambda: _gen_magic_info(_repo))
_opcodes = _get_cached(os.path.join(_dir, 'opcodes.pickle'), lambda: _gen_opcodes(_repo, _magic_info))
_has_kwonlyargcount = _get_cached(os.path.join(_dir, 'has_kwonlyargcount.pickle'), lambda: _gen_has_kwonlyargcount(_repo, _magic_info))
_revisions = sorted([_Revision(_m, _o, _h) for _m, _o, _h in zip(_magic_info, _opcodes, _has_kwonlyargcount)], key=lambda x: x.magic)
opcodes, _has_argument = _differentiate_opcodes_by_argument(_revisions)

# Return the revision with the given magic number. Just in case we try to
# disassemble a *.pyc file with a magic version that doesn't match any ever
# committed to the official repo, we return the revision with the smallest
# magic number above magic.
def _magic_to_revision(magic):
    for rev in _revisions:
        if rev.magic >= magic:
            return rev

def has_argument(opcode):
    '''
    Returns True if opcode takes an argument when represented in bytecode,
    otherwise returns False.
    '''
    return opcode in _has_argument

def has_kwonlyargcount(magic):
    '''
    Returns True if the code objects in *.pyc files with the given magic
    number will have the co_kwonlyargcount property, otherwise returns
    False.
    '''
    revision = _magic_to_revision(magic)
    return revision and revision.has_kwonlyargcount

def from_bytecode(bytecode, magic):
    '''
    Given bytecode, an 8-bit integer, and magic, the 32-bit magic number
    from a marshalled *.pyc file, produce a string with the name of the
    opcode or None for an invalid bytecode.
    '''
    revision = _magic_to_revision(magic)
    if revision and bytecode in revision.opcode_to_name:
        return revision.opcode_to_name[bytecode]

def python_version_from_magic(magic):
    '''
    Returns a string with the Python interpreter version ("2.7b2+" for
    example). Note that there isn't a one-to-one mapping between magic
    number and version string. It is most useful for obtaining a human
    readable interpretation of a magic number.
    '''
    revision = _magic_to_revision(magic)
    if revision:
        return revision.python_version

# Add a global name for each opcode to allow the syntax "op.OPCODE"
for _name in opcodes:
    globals()[_name] = _name
