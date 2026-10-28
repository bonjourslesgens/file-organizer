"""Native Windows/NTFS integration on synthetic profile-local files, never real media."""
import ctypes
import hashlib
import os
from pathlib import Path
import stat
import unittest

from file_organizer.paths import native_path
from file_organizer.safety import file_stat,identity,open_personal,SafetyError
from tests.test_core import Fixture,PNG


@unittest.skipUnless(os.name=='nt','Intégration native Windows requise')
class WindowsIntegrationTests(Fixture):
    def copy(self,name='voile.png'):
        source=self.write(name);self.scan();dest=self.base/'archives';dest.mkdir()
        plan=self.app.planner.simulate(str(dest));approval=self.app.transfers.prepare(plan['id'],all_files=True)
        job=self.app.transfers.start(approval['approval_id'],'COPIER');self.app.transfers.wait(timeout=90)
        copied=self.app.transfers.get(job['id']);self.assertEqual(copied['status'],'completed',copied)
        self.app.config.allow_cleanup(self.entry['id'],True)
        return source,copied

    def test_consistent_native_change_time_for_path_and_handle(self):
        for i in range(20):
            path=self.write(f'{i}.png')
            with path.open('rb') as stream:
                self.assertEqual(identity(file_stat(path=path)),identity(file_stat(fd=stream.fileno())))
            with open_personal(self.root,path) as (stream,st):self.assertEqual(stream.read(),PNG)

    def test_preserved_mtime_does_not_hide_a_content_change_in_cache(self):
        source=self.write('a.png');self.scan();old=source.stat().st_mtime_ns
        source.write_bytes(PNG[:-1]+b'z');os.utime(source,ns=(old,old))
        result=self.scan();self.assertEqual(result['cached'],0)
        self.assertEqual(self.app.db.files()['items'][0]['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())

    def test_real_sharing_violation_is_reported_not_ignored(self):
        from ctypes import wintypes as w
        path=self.write('locked.png');k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE];k.CreateFileW.restype=w.HANDLE
        k.CloseHandle.argtypes=[w.HANDLE]
        h=k.CreateFileW(native_path(path),0x80000000,0,None,3,0,None)
        self.assertNotEqual(h,w.HANDLE(-1).value)
        try:
            result=self.scan();self.assertEqual(result['status'],'completed_with_errors');self.assertEqual(result['files'],0)
        finally:k.CloseHandle(h)
        self.assertEqual(self.scan()['files'],1)

    def test_ntfs_deny_read_permission_is_reported(self):
        import win32api,win32security,ntsecuritycon
        path=self.write('restricted.png')
        descriptor=win32security.GetFileSecurity(str(path),win32security.DACL_SECURITY_INFORMATION)
        original=descriptor.GetSecurityDescriptorDacl()
        token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32security.TOKEN_QUERY)
        sid=win32security.GetTokenInformation(token,win32security.TokenUser)[0];token.Close()
        denied=win32security.ACL();denied.AddAccessDeniedAceEx(win32security.ACL_REVISION,0,ntsecuritycon.FILE_READ_DATA,sid)
        denied.AddAccessAllowedAceEx(win32security.ACL_REVISION,0,ntsecuritycon.FILE_ALL_ACCESS,sid)
        denied.AddAccessAllowedAceEx(win32security.ACL_REVISION,0,ntsecuritycon.FILE_ALL_ACCESS,win32security.CreateWellKnownSid(win32security.WinLocalSystemSid,None))
        restricted=win32security.SECURITY_DESCRIPTOR();restricted.SetSecurityDescriptorDacl(1,denied,0)
        try:
            win32security.SetFileSecurity(str(path),win32security.DACL_SECURITY_INFORMATION,restricted)
            result=self.scan();self.assertEqual(result['status'],'completed_with_errors');self.assertEqual(result['files'],0)
        finally:win32security.SetFileSecurity(str(path),win32security.DACL_SECURITY_INFORMATION,descriptor)
        self.assertEqual(path.read_bytes(),PNG)

    def test_native_recycle_only_after_verified_copy(self):
        source,copy=self.copy()
        proposal=self.app.cleanup.prepare(copy['id'],[copy['items'][0]['file_id']])
        self.assertEqual(proposal['items'][0]['method'],'windows_recycle_bin')
        job=self.app.cleanup.start(proposal['review_id'],'NETTOYER',True);self.app.cleanup.thread.join(timeout=90)
        result=self.app.cleanup.get(job['id']);self.assertEqual(result['status'],'completed',result)
        self.assertFalse(source.exists());self.assertEqual(Path(copy['items'][0]['destination']).read_bytes(),PNG)
        import json
        receipt=json.loads(result['items'][0]['receipt'])
        self.assertEqual(receipt['method'],'windows_recycle_bin');self.assertTrue(receipt['shell_item_confirmed'])
        if receipt['recycled_path']:
            self.assertEqual(Path(receipt['recycled_path']).read_bytes(),PNG)
        # Restore only this unique synthetic entry; never empty the user's Recycle Bin.
        restored=source.parent/receipt['staged_name']
        import win32com.client,time
        namespace=win32com.client.Dispatch('Shell.Application').NameSpace(10)
        entry=next((item for item in namespace.Items() if receipt['staged_name'][:40] in item.Name),None)
        self.assertIsNotNone(entry,receipt)
        entry.InvokeVerb('undelete')
        for _ in range(100):
            if restored.exists():break
            time.sleep(.1)
        self.assertTrue(restored.exists(),'Restauration Windows de la donnée synthétique non confirmée')
        self.assertEqual(restored.read_bytes(),PNG);restored.rename(source)

    def test_long_source_path_can_be_copied_and_reviewed_for_cleanup(self):
        name='/'.join('album-'+str(i)+'x'*45 for i in range(5))+'/été-photo.png'
        source,copy=self.copy(name)
        self.assertGreater(len(str(source)),300)
        candidates=self.app.cleanup.candidates(copy['id'])
        self.assertEqual(len(candidates['items']),1,candidates)
        self.assertEqual(source.read_bytes(),PNG)

    def test_native_recycle_veto_restores_exact_source_without_deletion(self):
        from unittest.mock import patch
        source,copy=self.copy()
        proposal=self.app.cleanup.prepare(copy['id'],[copy['items'][0]['file_id']])
        with patch('file_organizer.win_recycle.require_recycle_flag',side_effect=SafetyError('Permanent deletion vetoed by integration test')) as veto:
            job=self.app.cleanup.start(proposal['review_id'],'NETTOYER',True);self.app.cleanup.thread.join(timeout=90)
        result=self.app.cleanup.get(job['id']);self.assertTrue(veto.called,result);self.assertEqual(result['status'],'blocked',result)
        self.assertEqual(source.read_bytes(),PNG)
        self.assertEqual(Path(copy['items'][0]['destination']).read_bytes(),PNG)
