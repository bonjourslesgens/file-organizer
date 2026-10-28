import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from file_organizer.safety import SafetyError
from file_organizer.storage import Storage
from file_organizer.transfers import Transfers
from tests.test_core import Fixture, PNG


class CopyTests(Fixture):
    def setUp(self):
        super().setUp()
        self.dest=self.base/'archives'
        self.dest.mkdir()
        self.t=Transfers(self.app.config,self.app.db)

    def tearDown(self):
        self.t.pause();self.t.wait()
        super().tearDown()

    def plan(self,data=PNG):
        self.source=self.write('voile.png',data)
        self.scan()
        return self.app.planner.simulate(str(self.dest))

    def approve(self,plan):
        return self.t.prepare(plan['id'],all_files=True)

    def run_copy(self,plan):
        a=self.approve(plan);j=self.t.start(a['approval_id'],'COPIER');self.t.wait()
        return self.t.get(j['id'])

    def paused_job(self):
        p=self.plan(PNG+b'a'*(3*1024*1024))
        original=self.t._update
        def update(*args,**kwargs):
            original(*args,**kwargs)
            if kwargs.get('status')=='copying' and kwargs.get('bytes_done',0)>=1024*1024:
                self.t.pause()
        with patch.object(self.t,'_update',side_effect=update):
            result=self.run_copy(p)
        self.assertEqual(result['status'],'paused')
        return result

    def test_verified_copy_keeps_original_and_timestamp(self):
        p=self.plan();before=self.source.read_bytes(),self.source.stat().st_mtime_ns
        j=self.run_copy(p)
        self.assertEqual(j['status'],'completed',j)
        self.assertEqual(j['verified'],1)
        final=Path(j['items'][0]['destination'])
        self.assertEqual(final.read_bytes(),PNG)
        self.assertEqual(hashlib.sha256(final.read_bytes()).hexdigest(),p['items'][0]['sha256'])
        self.assertEqual(before,(self.source.read_bytes(),self.source.stat().st_mtime_ns))
        self.assertAlmostEqual(final.stat().st_mtime,self.source.stat().st_mtime,places=3)

    def test_prepare_is_read_only_on_destination_and_confirm_is_required(self):
        p=self.plan();a=self.approve(p)
        self.assertEqual(list(self.dest.iterdir()),[])
        with self.assertRaises(SafetyError):self.t.start(a['approval_id'],'oui')
        self.assertEqual(list(self.dest.iterdir()),[])

    def test_approval_single_use_and_expiry(self):
        p=self.plan();a=self.approve(p)
        self.t.start(a['approval_id'],'COPIER');self.t.wait()
        with self.assertRaises(SafetyError):self.t.start(a['approval_id'],'COPIER')
        b=self.approve(p)
        with self.app.db.connect() as c:c.execute('UPDATE approvals SET created=0 WHERE id=?',(b['approval_id'],))
        with self.assertRaises(SafetyError):self.t.start(b['approval_id'],'COPIER')

    def test_selection_only_copies_selected_files(self):
        self.write('a.png');self.write('b.png');self.scan()
        p=self.app.planner.simulate(str(self.dest))
        a=self.t.prepare(p['id'],file_ids=[p['items'][0]['file_id']])
        j=self.t.start(a['approval_id'],'COPIER');self.t.wait()
        self.assertEqual(self.t.get(j['id'])['verified'],1)
        with self.assertRaises(ValueError):self.t.prepare(p['id'],file_ids=[999999])

    def test_collision_preserves_existing_file(self):
        p=self.plan();existing=Path(p['items'][0]['destination']);existing.parent.mkdir(parents=True)
        existing.write_bytes(b'important existing content')
        j=self.run_copy(p)
        self.assertEqual(j['status'],'completed',j)
        self.assertNotEqual(j['items'][0]['destination'],str(existing))
        self.assertEqual(existing.read_bytes(),b'important existing content')

    def test_identical_existing_file_is_verified_and_reused(self):
        p=self.plan();existing=Path(p['items'][0]['destination']);existing.parent.mkdir(parents=True);existing.write_bytes(PNG)
        inode=existing.stat().st_ino
        j=self.run_copy(p)
        self.assertEqual(j['items'][0]['status'],'already_present')
        self.assertEqual(existing.stat().st_ino,inode)
        self.assertFalse(list(self.dest.rglob('*.partial')))

    def test_pause_resume_after_application_restart_checks_prefix(self):
        j=self.paused_job()
        self.t=Transfers(self.app.config,self.app.db)
        self.t.resume(j['id'],'REPRENDRE');self.t.wait()
        done=self.t.get(j['id'])
        self.assertEqual(done['status'],'completed',done)
        self.assertEqual(Path(done['items'][0]['destination']).read_bytes(),self.source.read_bytes())

    def test_corrupted_partial_is_not_overwritten_or_published(self):
        j=self.paused_job();part=next(self.dest.rglob('*.partial'))
        with part.open('r+b') as f:f.write(b'corrupted')
        self.t.resume(j['id'],'REPRENDRE');self.t.wait()
        self.assertEqual(self.t.get(j['id'])['status'],'blocked')
        self.assertTrue(part.read_bytes().startswith(b'corrupted'))
        self.assertFalse(Path(j['items'][0]['destination']).exists())

    def test_source_changed_after_plan_is_blocked(self):
        p=self.plan();self.source.write_bytes(b'changed')
        with self.assertRaises(SafetyError):self.approve(p)
        self.assertFalse(list(self.dest.iterdir()))

    def test_source_changed_while_copying_does_not_publish(self):
        p=self.plan(PNG+b'x'*(2*1024*1024));update=self.t._update
        def change(*a,**kw):
            update(*a,**kw)
            if kw.get('bytes_done',0)>=1024*1024:
                with self.source.open('ab') as f:f.write(b'modified')
        with patch.object(self.t,'_update',side_effect=change):j=self.run_copy(p)
        self.assertEqual(j['status'],'blocked')
        self.assertFalse(Path(j['items'][0]['destination']).exists())

    def test_corrupted_copy_hash_blocks_publication(self):
        p=self.plan()
        with patch.object(self.t,'_digest',return_value='0'*64):j=self.run_copy(p)
        self.assertEqual(j['status'],'blocked')
        self.assertFalse(Path(j['items'][0]['destination']).exists())
        self.assertEqual(self.source.read_bytes(),PNG)

    def test_unknown_readonly_and_inaccessible_volumes_block_writes(self):
        p=self.plan()
        for info in ({'safe_to_write':False,'anomalies':['unknown']},{'safe_to_write':False,'anomalies':['read only']},{'safe_to_write':False,'anomalies':['disconnected']}):
            with self.subTest(info=info),patch.object(self.t.storage,'diagnose',return_value=info),self.assertRaises(SafetyError):
                self.approve(p)
        self.assertEqual(list(self.dest.iterdir()),[])

    def test_low_space_blocks_before_writing(self):
        p=self.plan();info=self.t.storage.diagnose(str(self.dest));info['free']=1
        with patch.object(self.t.storage,'diagnose',return_value=info),self.assertRaises(SafetyError):self.approve(p)
        self.assertEqual(list(self.dest.iterdir()),[])

    def test_destination_identity_changed_after_approval(self):
        p=self.plan();a=self.approve(p)
        self.dest.rename(self.base/'detached');self.dest.mkdir()
        with self.assertRaises(SafetyError):self.t.start(a['approval_id'],'COPIER')
        self.assertEqual(list(self.dest.iterdir()),[])

    def test_disconnect_during_copy_then_reconnect_and_resume(self):
        p=self.plan(PNG+b'a'*(2*1024*1024));original=self.t._update;moved=self.base/'detached'
        def disconnect(*args,**kw):
            original(*args,**kw)
            if kw.get('bytes_done',0)>=1024*1024 and self.dest.exists():self.dest.rename(moved)
        if os.name=='nt':
            # Windows directory handles intentionally prohibit renaming pinned ancestors.
            with patch.object(self.t.storage,'guard',side_effect=OSError('USB disconnected')):j=self.run_copy(p)
        else:
            with patch.object(self.t,'_update',side_effect=disconnect):j=self.run_copy(p)
            moved.rename(self.dest)
        self.assertEqual(j['status'],'blocked')
        self.t.resume(j['id'],'REPRENDRE');self.t.wait()
        self.assertEqual(self.t.get(j['id'])['status'],'completed')

    def test_permission_error_preserves_sources(self):
        p=self.plan()
        with patch('file_organizer.transfers.directory',side_effect=PermissionError('Droits insuffisants')):j=self.run_copy(p)
        self.assertEqual(j['status'],'blocked')
        self.assertEqual(self.source.read_bytes(),PNG)

    def test_removed_authorization_and_overlapping_destination_rejected(self):
        p=self.plan();self.app.config.remove_root(self.entry['id'])
        with self.assertRaises(SafetyError):self.approve(p)
        self.app.config.data['roots'].append(self.entry)
        child=self.root/'archives';child.mkdir();plan=self.app.planner.simulate(str(child))
        with self.assertRaises(SafetyError):self.approve(plan)

    def test_destination_symlink_never_followed(self):
        p=self.plan();target=Path(p['items'][0]['destination'])
        outside=self.base/'outside';outside.mkdir()
        first=self.dest/target.relative_to(self.dest).parts[0]
        try:first.symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Liens indisponibles sur ce système')
        j=self.run_copy(p)
        self.assertEqual(j['status'],'blocked')
        self.assertEqual(list(outside.iterdir()),[])

    def test_interrupted_job_is_marked_on_restart(self):
        p=self.plan();a=self.approve(p)
        with patch.object(self.t,'_launch'):
            j=self.t.start(a['approval_id'],'COPIER')
        fresh=Transfers(self.app.config,self.app.db)
        self.assertEqual(fresh.get(j['id'])['status'],'interrupted')

    def test_missing_destination_diagnostic_does_not_create_it(self):
        missing=self.base/'missing'
        info=self.t.storage.diagnose(str(missing))
        self.assertFalse(info['safe_to_write'])
        self.assertFalse(missing.exists())

    def test_full_disk_during_write_is_blocked_and_resumable(self):
        p=self.plan(PNG+b'x'*(2*1024*1024))
        original=self.t._update
        def full_disk(*args,**kw):
            original(*args,**kw)
            if kw.get('bytes_done',0)>=1024*1024:
                raise OSError(28,'No space left on device')
        with patch.object(self.t,'_update',side_effect=full_disk):j=self.run_copy(p)
        self.assertEqual(j['status'],'blocked')
        self.assertFalse(Path(j['items'][0]['destination']).exists())
        self.t.resume(j['id'],'REPRENDRE');self.t.wait()
        self.assertEqual(self.t.get(j['id'])['status'],'completed')

    def test_long_destination_paths(self):
        self.source=self.write('a.png');self.scan()
        dest=self.dest
        try:
            for i in range(5):
                dest=dest/('album-'+str(i)+'a'*42);dest.mkdir()
        except OSError:
            if os.name=='nt':self.skipTest('Chemins longs désactivés sur cette machine Windows')
            raise
        plan=self.app.planner.simulate(str(dest))
        self.assertGreater(len(plan['items'][0]['destination']),300)
        approval=self.t.prepare(plan['id'],all_files=True)
        j=self.t.start(approval['approval_id'],'COPIER');self.t.wait()
        result=self.t.get(j['id']);self.assertEqual(result['status'],'completed',result)
        self.assertEqual(Path(result['items'][0]['destination']).read_bytes(),PNG)

    def test_windows_destination_junction(self):
        if os.name!='nt':self.skipTest('Jonction NTFS réelle : Windows requis')
        import subprocess
        plan=self.plan();target=Path(plan['items'][0]['destination']);outside=self.base/'outside';outside.mkdir()
        link=self.dest/target.relative_to(self.dest).parts[0]
        result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
        if result.returncode:self.skipTest('Jonctions indisponibles sur ce volume')
        try:
            job=self.run_copy(plan)
            self.assertEqual(job['status'],'blocked')
            self.assertEqual(list(outside.iterdir()),[])
        finally:link.rmdir()

    def test_directory_at_target_name_is_a_collision_not_an_overwrite(self):
        plan=self.plan();existing=Path(plan['items'][0]['destination'])
        existing.mkdir(parents=True);(existing/'keep.txt').write_text('preserve')
        job=self.run_copy(plan)
        self.assertEqual(job['status'],'completed',job)
        self.assertNotEqual(job['items'][0]['destination'],str(existing))
        self.assertEqual((existing/'keep.txt').read_text(),'preserve')
