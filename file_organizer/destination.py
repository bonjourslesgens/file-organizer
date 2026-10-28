"""Scoped destination writes, pinned ancestors and atomic publish without replacement."""
from contextlib import contextmanager
import ctypes
import errno
import os
from pathlib import Path
import stat

from .safety import SafetyError, check_components, is_link


@contextmanager
def directory(base, relative):
    if relative.is_absolute() or '..' in relative.parts:
        raise SafetyError('Destination hors du dossier approuvé.')
    held, handles = [], []
    try:
        if os.name != 'nt':
            fd = os.open(base.anchor, os.O_RDONLY | os.O_DIRECTORY)
            held.append(fd)
            for part in base.parts[1:]:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                held.append(fd)
            for part in relative.parts:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                held.append(fd)
            yield Folder(base / relative, fd)
        else:
            from ctypes import wintypes as w
            k = ctypes.WinDLL('kernel32', use_last_error=True)
            create = k.CreateFileW
            create.argtypes = [w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
            create.restype = w.HANDLE
            k.CloseHandle.argtypes = [w.HANDLE]
            path = Path(base.anchor)
            for i, part in enumerate((*base.parts[1:], *relative.parts)):
                path = path / part
                if i >= len(base.parts)-1:
                    try:
                        path.mkdir()
                    except FileExistsError:
                        pass
                h = create('\\\\?\\'+str(path),0x80,3,None,3,0x02200000,None)
                if h == w.HANDLE(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                handles.append(h)
                check_components(path)
            yield Folder(path, None)
    finally:
        for fd in reversed(held):
            os.close(fd)
        if handles:
            for h in reversed(handles):
                k.CloseHandle(h)


class Folder:
    def __init__(self, path, fd):
        self.path, self.fd = path, fd

    def open(self, name, new=False, writable=False):
        if Path(name).name != name or name in ('.','..'):
            raise SafetyError('Nom de destination invalide.')
        flags = os.O_RDWR if writable else os.O_RDONLY
        if new:
            flags |= os.O_CREAT | os.O_EXCL
        if os.name != 'nt':
            flags |= os.O_NOFOLLOW | os.O_NONBLOCK
            fd = os.open(name, flags, mode=0o600, dir_fd=self.fd)
        else:
            # Reparse point opens are handled via CreateFileW before converting to a CRT fd.
            from ctypes import wintypes as w
            import msvcrt
            k=ctypes.WinDLL('kernel32',use_last_error=True)
            f=k.CreateFileW
            f.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
            f.restype=w.HANDLE
            h=f('\\\\?\\'+str(self.path/name),0xC0000000 if writable else 0x80000000,1,None,1 if new else 3,0x00200000,None)
            if h==w.HANDLE(-1).value:
                code=ctypes.get_last_error()
                if code in (80,183):raise FileExistsError(code,'Fichier déjà présent')
                if code in (2,3):raise FileNotFoundError(code,'Fichier absent')
                raise ctypes.WinError(code)
            try:
                fd=msvcrt.open_osfhandle(h,(os.O_RDWR if writable else os.O_RDONLY)|os.O_BINARY)
            except BaseException:
                k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle(h)
                raise
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or is_link(st) or st.st_nlink!=1:
            os.close(fd)
            raise SafetyError('Destination non ordinaire, liée ou ambiguë.')
        return os.fdopen(fd,'r+b' if writable else 'rb')

    def publish(self, partial, final):
        if os.name=='nt':
            # Windows rename fails if destination exists; unlike POSIX rename it never replaces.
            try:
                os.rename('\\\\?\\'+str(self.path/partial),'\\\\?\\'+str(self.path/final))
            except OSError as e:
                if getattr(e,'winerror',None) in (80,183):
                    raise FileExistsError(str(e)) from e
                if getattr(e,'winerror',None)==5:
                    try:(self.path/final).lstat()
                    except OSError:raise e
                    raise FileExistsError(str(e)) from e
                raise
        else:
            libc=ctypes.CDLL(None,use_errno=True)
            if hasattr(libc,'renameat2'):
                fn=libc.renameat2
                fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
                if fn(self.fd,os.fsencode(partial),self.fd,os.fsencode(final),1)==0:
                    os.fsync(self.fd)
                    return
                code=ctypes.get_errno()
                if code not in (errno.ENOSYS,errno.EINVAL,errno.EOPNOTSUPP):
                    raise OSError(code,os.strerror(code),final)
            # Portable fallback, atomic fail-if-exists; no exists()+rename race.
            os.link(partial,final,src_dir_fd=self.fd,dst_dir_fd=self.fd,follow_symlinks=False)
            os.unlink(partial,dir_fd=self.fd)
            os.fsync(self.fd)

    def remove_partial(self, name, expected_inode):
        # Only our recorded temporary copy, never an original or arbitrary destination file.
        with self.open(name) as f:
            if str(os.fstat(f.fileno()).st_ino)!=expected_inode:
                raise SafetyError('Le fichier temporaire a changé.')
        if self.fd is None:
            (self.path/name).unlink()
        else:
            os.unlink(name,dir_fd=self.fd)


def set_timestamp(stream, timestamp):
    if os.name!='nt':
        os.utime(stream.fileno(),(timestamp,timestamp))
    else:
        import msvcrt
        from ctypes import wintypes as w
        value=int(timestamp*10_000_000)+116444736000000000
        ft=w.FILETIME(value & 0xffffffff,value >> 32)
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.SetFileTime.argtypes=[w.HANDLE,ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME)]
        if not k.SetFileTime(msvcrt.get_osfhandle(stream.fileno()),None,ctypes.byref(ft),ctypes.byref(ft)):
            raise ctypes.WinError(ctypes.get_last_error())
