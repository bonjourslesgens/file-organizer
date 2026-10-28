"""Conservative whitelist checks. No traversal through symbolic links or reparse points."""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import stat


class SafetyError(ValueError):
    pass


BLOCKED_NAMES = frozenset(x.casefold() for x in (
    'Windows', 'Program Files', 'Program Files (x86)', 'ProgramData', 'AppData',
    'Android', 'Steam', 'SteamLibrary', 'steamapps', 'Epic Games', 'Games', 'Jeux',
    'GOG Games', 'XboxGames', 'WindowsApps', '$Recycle.Bin', 'System Volume Information',
    '.git', '.svn', '.hg', '.venv', 'venv', 'env', 'node_modules', 'vendor',
    '__pycache__', 'site-packages', '.gradle', '.android', '.vscode', '.idea',
    'build', 'dist', 'target', 'bin', 'sbin', 'lib', 'lib64', 'etc', 'proc', 'sys',
    'dev', 'boot', 'run', 'var', 'usr', 'opt', 'snap', 'lost+found', '.config',
    '.local', '.cache', '.ssh', '.aws', '.codex', '.agents', 'Applications', 'Library',
))
BLOCKED_SUFFIXES = frozenset((
    '.exe', '.dll', '.sys', '.msi', '.apk', '.aab', '.so', '.dylib', '.app',
    '.db', '.sqlite', '.sqlite3', '.ini', '.reg', '.lnk', '.url', '.bat', '.cmd',
    '.ps1', '.sh', '.py', '.pyc', '.js', '.ts', '.class', '.jar', '.vhd', '.vhdx',
))
PROJECT_MARKERS = ('pyproject.toml', 'package.json', 'Cargo.toml', 'go.mod', '.project')
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)


def is_link(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & REPARSE)


def check_components(path: Path) -> Path:
    """Check lexical ancestors *before* resolve; reject junctions and aliases too."""
    if not path.is_absolute() or '..' in path.parts:
        raise SafetyError('Choisissez un chemin absolu sans « .. ».')
    if os.name == 'nt':
        win = PureWindowsPath(str(path))
        if str(path).startswith(('\\\\', '//')) or any(':' in p for p in win.parts[1:]):
            raise SafetyError('Les chemins réseau, chemins de périphérique et flux NTFS sont exclus.')
    for part in path.parts[1:]:
        if part.rstrip(' .').casefold() in BLOCKED_NAMES:
            raise SafetyError(f'Emplacement protégé ou applicatif : {part}')
    # Walk from the volume down so lstat never follows an unchecked ancestor.
    for ancestor in reversed((path, *path.parents)):
        st = ancestor.lstat()
        if is_link(st):
            raise SafetyError('Lien symbolique ou jonction exclu.')
    resolved = path.resolve(strict=True)
    if os.path.normcase(str(resolved)) != os.path.normcase(str(path)):
        raise SafetyError('Chemin équivalent ou redirigé exclu.')
    return resolved


def is_project(path: Path) -> bool:
    return (path / '.git').is_file() or (path / '.git' / 'HEAD').exists() or any((path / marker).exists() for marker in PROJECT_MARKERS)


def validate_root(raw: str, state_dir: Path | None = None) -> Path:
    path = check_components(Path(raw).expanduser())
    if not path.is_dir():
        raise SafetyError('Le dossier doit exister et être accessible.')
    if path == Path(path.anchor) or path == Path.home().resolve():
        raise SafetyError('Autorisez un dossier personnel précis, pas un disque ni le profil entier.')
    if state_dir:
        state = state_dir.resolve()
        if path == state or path in state.parents or state in path.parents:
            raise SafetyError('Le stockage interne de l’application ne peut pas être analysé.')
    if any(is_project(p) for p in (path, *path.parents) if p != Path(p.anchor)):
        raise SafetyError('Dossier de développement ou dépendances exclus.')
    return path



def file_stat(path=None,fd=None):
    """Consistent NTFS ChangeTime: Python 3.12 stat/ fstat disagree about st_ctime."""
    raw=os.fstat(fd) if fd is not None else Path(path).lstat()
    if os.name!='nt':return raw
    import ctypes
    from ctypes import wintypes as w
    import msvcrt
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    class BasicInfo(ctypes.Structure):
        _fields_=[('CreationTime',ctypes.c_longlong),('LastAccessTime',ctypes.c_longlong),
                  ('LastWriteTime',ctypes.c_longlong),('ChangeTime',ctypes.c_longlong),('FileAttributes',w.DWORD)]
    k.GetFileInformationByHandleEx.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD]
    owned=False
    if fd is None:
        k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
        k.CreateFileW.restype=w.HANDLE;k.CloseHandle.argtypes=[w.HANDLE]
        handle=k.CreateFileW('\\\\?\\'+str(Path(path)),0x80,7,None,3,0x02200000,None)
        if handle==w.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        owned=True
    else:handle=msvcrt.get_osfhandle(fd)
    info=BasicInfo()
    try:
        if not k.GetFileInformationByHandleEx(handle,0,ctypes.byref(info),ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if owned:k.CloseHandle(handle)
    class ConsistentStat:
        st_ctime_ns=(info.ChangeTime-116444736000000000)*100
        st_ctime=st_ctime_ns/1_000_000_000
        st_mtime_ns=(info.LastWriteTime-116444736000000000)*100
        st_mtime=st_mtime_ns/1_000_000_000
        st_birthtime=(info.CreationTime-116444736000000000)/10_000_000
        st_file_attributes=info.FileAttributes
        def __getattr__(self,name):return getattr(raw,name)
    return ConsistentStat()

def validate_file(root: Path, path: Path) -> os.stat_result:
    checked_root = validate_root(str(root))
    checked = check_components(path)
    if checked == checked_root or not checked.is_relative_to(checked_root):
        raise SafetyError('Fichier hors de la liste blanche.')
    if path.suffix.casefold() in BLOCKED_SUFFIXES or path.name.startswith('.'):
        raise SafetyError('Fichier applicatif ou caché exclu.')
    for folder in path.parents:
        if is_project(folder):
            raise SafetyError('Dossier de développement exclu.')
        if folder == checked_root:
            break
    st = file_stat(path=path)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
        raise SafetyError('Seuls les fichiers ordinaires sans liens physiques sont autorisés.')
    return st


def identity(st: os.stat_result) -> tuple:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


from contextlib import contextmanager


@contextmanager
def open_personal(root: Path, path: Path):
    """Hold ancestor descriptors/handles to prevent symlink/junction substitution."""
    before = validate_file(root, path)
    descriptors = []
    windows_handles = []
    stream = None
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            create = kernel.CreateFileW
            create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
            create.restype = wintypes.HANDLE
            close = kernel.CloseHandle
            close.argtypes = (wintypes.HANDLE,)
            # No FILE_SHARE_DELETE: ancestors cannot be replaced while hashing.
            for directory in reversed(path.parents):
                h = create('\\\\?\\' + str(directory), 0x80, 3, None, 3, 0x02200000, None)
                if h == wintypes.HANDLE(-1).value:
                    raise OSError(ctypes.get_last_error(), 'Impossible de verrouiller le chemin')
                windows_handles.append(h)
                check_components(directory)
            h = create('\\\\?\\' + str(path), 0x80000000, 3, None, 3, 0x00200000, None)
            if h == wintypes.HANDLE(-1).value:
                raise OSError(ctypes.get_last_error(), 'Fichier inaccessible')
            try:
                fd = msvcrt.open_osfhandle(h, os.O_RDONLY | os.O_BINARY)
            except BaseException:
                close(h)
                raise
        else:
            # Open each path component relative to a held directory descriptor.
            fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
            descriptors.append(fd)
            for part in path.parts[1:-1]:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                descriptors.append(fd)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        stream = os.fdopen(fd, 'rb')
        current = file_stat(fd=stream.fileno())
        if not stat.S_ISREG(current.st_mode) or is_link(current) or current.st_nlink != 1 or identity(current) != identity(before):
            raise SafetyError('Fichier remplacé pendant son ouverture.')
        yield stream, current
        if identity(file_stat(fd=stream.fileno())) != identity(current) or identity(validate_file(root, path)) != identity(current):
            raise SafetyError('Fichier modifié pendant la lecture ; résultat écarté.')
    finally:
        if stream is not None:
            stream.close()
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        if windows_handles:
            for handle in reversed(windows_handles):
                close(handle)


def is_sensitive(relative, patterns):
    import fnmatch
    value=str(relative).replace('\\','/').casefold()
    return any(fnmatch.fnmatchcase(value, pattern.casefold()) or fnmatch.fnmatchcase(Path(value).name,pattern.casefold()) for pattern in patterns)
