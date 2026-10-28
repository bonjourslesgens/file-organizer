"""Windows recycle-only operation with an identity-pinned staging name and fail-closed COM sink."""
import importlib.util
import os
from pathlib import Path
import time
import uuid

from .destination import directory
from .safety import SafetyError, identity, validate_file, is_link, file_stat


class RecoveryRequired(SafetyError):
    def __init__(self,message,recovery_path=None):
        super().__init__(message);self.recovery_path=recovery_path


def require_recycle_flag(flags):
    if not flags & 0x80:  # TSF_DELETE_RECYCLE_IF_POSSIBLE
        raise SafetyError('Windows ne propose pas de recyclage : suppression définitive refusée.')


class WindowsRecycleBin:
    def available(self):
        return os.name=='nt' and importlib.util.find_spec('pythoncom') is not None

    def can_recycle(self,snapshot):
        if not self.available():return False
        from .storage import windows_volume
        info=windows_volume(Path(snapshot['path']).parent)
        return info['filesystem']=='ntfs' and info.get('drive_type')==3 and not info['read_only']

    def recycle(self,snapshot,archive_guard,digest):
        if not self.can_recycle(snapshot):raise SafetyError('Corbeille garantie indisponible : utilisez une procédure manuelle contrôlée.')
        from ctypes import wintypes as w
        import ctypes
        import msvcrt
        path=Path(snapshot['path']);root=Path(snapshot['root']['path'])
        before=validate_file(root,path)
        stage=f'.FileOrganizer-retrait-{uuid.uuid4().hex[:12]}-{path.stem[:60]}{path.suffix[:15]}'
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
        k.CreateFileW.restype=w.HANDLE;k.CloseHandle.argtypes=[w.HANDLE]
        k.SetFileInformationByHandle.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD]
        class RenameInfo(ctypes.Structure):
            _fields_=[('ReplaceIfExists',w.BOOL),('RootDirectory',w.HANDLE),('FileNameLength',w.DWORD),('FileName',w.WCHAR*1)]
        with directory(root,path.parent.relative_to(root),create=False) as folder:
            handle=k.CreateFileW('\\\\?\\'+str(path),0x80010000,1,None,3,0x00200000,None)
            if handle==w.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
            try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
            except BaseException:k.CloseHandle(handle);raise
            staged=False
            try:
                with os.fdopen(fd,'rb') as source:
                    st=file_stat(fd=source.fileno())
                    if is_link(st) or st.st_nlink!=1 or identity(st)!=identity(before) or digest(source)!=snapshot['sha256']:
                        raise SafetyError('Source modifiée ou utilisée : aucun nettoyage.')
                    archive_guard()
                    def rename_to(target):
                        encoded=str(target).encode('utf-16-le')
                        # FILE_RENAME_INFO expects a terminated WCHAR string as well as its byte length.
                        buf=ctypes.create_string_buffer(RenameInfo.FileName.offset+len(encoded)+2)
                        info=RenameInfo.from_buffer(buf);info.ReplaceIfExists=False;info.RootDirectory=None;info.FileNameLength=len(encoded)
                        ctypes.memmove(ctypes.addressof(buf)+RenameInfo.FileName.offset,encoded,len(encoded))
                        if not k.SetFileInformationByHandle(msvcrt.get_osfhandle(source.fileno()),3,buf,len(buf)):
                            raise ctypes.WinError(ctypes.get_last_error())
                    rename_to(folder.path/stage)
                    k.GetFinalPathNameByHandleW.argtypes=[w.HANDLE,w.LPWSTR,w.DWORD,w.DWORD]
                    actual_buffer=ctypes.create_unicode_buffer(32768)
                    if not k.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(source.fileno()),actual_buffer,len(actual_buffer),0):
                        rename_to(path)
                        raise ctypes.WinError(ctypes.get_last_error())
                    actual=actual_buffer.value
                    if actual.startswith('\\\\?\\'):actual=actual[4:]
                    if os.path.normcase(actual)!=os.path.normcase(str(folder.path/stage)):
                        try:rename_to(path)
                        except Exception as e:raise RecoveryRequired('Renommage natif inattendu ; fichier conservé sous '+actual,actual) from e
                        raise SafetyError('Windows a renvoyé un chemin de retrait inattendu ; original remis en place.')
                    staged=True
                    source_inode=str(st.st_ino)
                def before_recycle():
                    archive_guard()
                    with folder.open(stage) as current:
                        st=os.fstat(current.fileno())
                        if str(st.st_ino)!=source_inode or st.st_size!=snapshot['size'] or digest(current)!=snapshot['sha256']:
                            raise SafetyError('Fichier de retrait remplacé ou modifié ; opération annulée.')
                    archive_guard()
                before_recycle()
                receipt=self._shell_recycle(folder.path/stage,before_recycle)
                return receipt|{'original_path':str(path),'staged_name':stage,'at':time.time(),
                                'restoration_note':'Dans la Corbeille, restaurer cette entrée puis lui redonner le nom original indiqué au journal.'}
            except Exception as e:
                if staged:
                    try:
                        with folder.open(stage):pass
                    except FileNotFoundError:
                        raise RecoveryRequired('État du retrait à contrôler dans la Corbeille Windows : '+str(e)) from e
                    try:folder.publish(stage,path.name)
                    except Exception as recovery:
                        raise RecoveryRequired('Retrait arrêté ; fichier conservé sous le nom de sécurité, sans écrasement : '+str(folder.path/stage),str(folder.path/stage)) from recovery
                raise

    def _shell_recycle(self,path,guard):
        import pythoncom
        from win32com.shell import shell, shellcon
        from win32com.server.util import wrap
        from win32com.server.exception import COMException
        class Sink:
            _com_interfaces_=[shell.IID_IFileOperationProgressSink]
            _public_methods_=['StartOperations','FinishOperations','PreRenameItem','PostRenameItem','PreMoveItem','PostMoveItem',
                              'PreCopyItem','PostCopyItem','PreDeleteItem','PostDeleteItem','PreNewItem','PostNewItem',
                              'UpdateProgress','ResetTimer','PauseTimer','ResumeTimer']
            def __init__(self):self.receipt=None;self.error=None
            def PreDeleteItem(self,flags,item):
                try:require_recycle_flag(flags);guard()
                except Exception as e:
                    self.error=str(e)
                    raise COMException(desc=str(e),scode=-2147467260)
            def PostDeleteItem(self,flags,item,result,newly_created):
                if result & 0x80000000 or newly_created is None:
                    self.error='Windows n’a pas confirmé une entrée de Corbeille.'
                else:
                    # A recycled Shell item is sometimes virtual: FILESYSPATH can fail after a successful move.
                    # Non-null psiNewlyCreated is the native receipt; display-name failure must not lose it.
                    self.receipt={'method':'windows_recycle_bin','shell_item_confirmed':True,'recycled_path':'','display_name':path.name}
                    for flag,key in ((0x80058000,'recycled_path'),(0x80028000,'shell_parsing_name'),(0,'display_name')):
                        try:self.receipt[key]=newly_created.GetDisplayName(flag)
                        except Exception:pass
            def __getattr__(self,name):
                if name in self._public_methods_:return lambda *args:None
                raise AttributeError(name)
        pythoncom.CoInitialize()
        operation=None;item=None;wrapped=None;sink=Sink()
        phase='création de l’opération Shell'
        try:
            operation=pythoncom.CoCreateInstance(shell.CLSID_FileOperation,None,pythoncom.CLSCTX_ALL,shell.IID_IFileOperation)
            # No fallback to permanent deletion: PreDeleteItem raises E_ABORT, rather than returning an ignored code.
            flags=shellcon.FOF_NOCONFIRMATION|shellcon.FOF_NOERRORUI|shellcon.FOF_SILENT|shellcon.FOFX_EARLYFAILURE|0x20000000|0x00080000
            operation.SetOperationFlags(flags)
            phase='création de l’élément Shell vérifié'
            item=shell.SHCreateItemFromParsingName(str(path),None,shell.IID_IShellItem)
            wrapped=wrap(sink,shell.IID_IFileOperationProgressSink)
            operation.DeleteItem(item,wrapped)
            phase='exécution du recyclage Windows'
            result=operation.PerformOperations();aborted=operation.GetAnyOperationsAborted()
            if sink.error or aborted or result or not sink.receipt:
                raise SafetyError(sink.error or 'Recyclage Windows annulé ou non confirmé.')
            return sink.receipt
        except Exception as e:
            raise SafetyError(phase+' : '+str(e)) from e
        finally:
            wrapped=None;item=None;operation=None
            pythoncom.CoUninitialize()
