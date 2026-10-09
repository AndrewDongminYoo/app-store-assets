"""Python child loader for an anonymous, reviewed provider source capture."""

BOOTSTRAP = r'''
import _io, builtins, importlib.abc, importlib.util, io, json, os, struct, sys
fd = int(sys.argv.pop(1))
length = struct.unpack('>Q', os.pread(fd, 8, 0))[0]
bundle = json.loads(os.pread(fd, length, 8))
files = bundle['files']
def captured(path):
    item = files[os.path.abspath(os.fspath(path))]
    return os.pread(fd, item['size'], item['offset'])
native_getcwd = os.getcwd
directories = bundle['directories']
initial = os.stat('.')
directories.setdefault(str(initial.st_dev) + ':' + str(initial.st_ino), native_getcwd())
def captured_getcwd():
    info = os.stat('.')
    key = str(info.st_dev) + ':' + str(info.st_ino)
    return directories[key] if key in directories else native_getcwd()
os.getcwd = captured_getcwd
trusted_paths = tuple(sys.path)
roots = bundle['roots']
entry = bundle['entry']
sys.argv[0] = entry

def staged(path):
    path = os.path.abspath(os.fsdecode(path))
    return any(path == root or path.startswith(root + os.sep) for root in roots)

original_open = builtins.open
def captured_open(path, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    if isinstance(path, int) or not staged(path):
        return original_open(path, mode, buffering, encoding, errors, newline, closefd, opener)
    if any(option in mode for option in 'wax+') or opener is not None:
        raise PermissionError('captured provider files are read-only')
    name = os.path.abspath(os.fspath(path))
    if name not in files:
        raise FileNotFoundError('file is outside approved provider capture')
    stream = io.BytesIO(captured(name))
    stream.name = name
    return stream if 'b' in mode else io.TextIOWrapper(stream, encoding=encoding or 'UTF-8', errors=errors, newline=newline)
builtins.open = io.open = captured_open

native_open_code = _io.open_code
def captured_open_code(path):
    return captured_open(path, 'rb') if staged(path) else native_open_code(path)
_io.open_code = io.open_code = captured_open_code
def reject_native_staged_code(event, args):
    if event in ('open', 'ctypes.dlopen') and args and isinstance(args[0], (str, bytes)) and staged(args[0]):
        raise PermissionError('native staged file access must use the reviewed capture')
sys.addaudithook(reject_native_staged_code)

class CapturedLoader(importlib.abc.Loader):
    def __init__(self, path):
        self.path = path
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        module.__file__ = self.path
        exec(compile(captured(self.path), self.path, 'exec'), module.__dict__)

class CapturedFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        name = fullname.rsplit('.', 1)[-1]
        directories = path if path is not None else sys.path
        for directory in directories:
            if not staged(directory):
                continue
            stem = os.path.abspath(os.path.join(directory, name))
            for candidate, package in ((stem + '/__init__.py', True), (stem + '.py', False)):
                if candidate in files:
                    return importlib.util.spec_from_file_location(fullname, candidate,
                        loader=CapturedLoader(candidate),
                        submodule_search_locations=[stem] if package else None)
        # Never let PathFinder reopen any staged path, including new pyc/native code.
        outside = [directory for directory in directories if not staged(directory) and
                   any(directory == trusted or directory.startswith(trusted + os.sep) for trusted in trusted_paths)]
        return importlib.machinery.PathFinder.find_spec(fullname, outside, target)

sys.meta_path = [importlib.machinery.BuiltinImporter, importlib.machinery.FrozenImporter, CapturedFinder()]
sys.path.insert(0, os.path.dirname(entry))
exec(compile(captured(entry), entry, 'exec'),
     {'__name__': '__main__', '__file__': entry, '__package__': None, '__builtins__': __builtins__})
'''
