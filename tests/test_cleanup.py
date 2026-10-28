import json
import os
from pathlib import Path
import uuid
from unittest.mock import patch

from file_organizer.cleanup import Cleanup
from file_organizer.safety import SafetyError,open_personal
from file_organizer.win_recycle import require_recycle_flag
from tests.test_core import Fixture,PNG


class SyntheticRecycle:
    """A fixture-only bin; this is never selected by production application code."""
    def __init__(self,folder):self.folder=folder;folder.mkdir();self.calls=[]
    def available(self):return True
    def recycle(self,snapshot,guard,digest):
        guard()
        with open_personal(Path(snapshot['root']['path']),Path(snapshot['path'])) as (stream,_):
            if digest(stream)!=snapshot['sha256']:raise SafetyError('source changed')
        guard();source=Path(snapshot['path']);target=self.folder/(uuid.uuid4().hex+'-'+source.name)
        source.rename(target);self.calls.append(snapshot['path'])
        return {'method':'synthetic_recycle_bin','recycled_path':str(target)}


class CleanupTests(Fixture):
    def setUp(self):
        super().setUp()
        self.dest=self.base/'archives';self.dest.mkdir()
        self.bin=SyntheticRecycle(self.base/'fixture-bin')
        self.app.cleanup.recycler=self.bin

    def copy(self,name='image.png',data=PNG):
        source=self.write(name,data);self.scan()
        plan=self.app.planner.simulate(str(self.dest))
        review=self.app.transfers.prepare(plan['id'],all_files=True)
        job=self.app.transfers.start(review['approval_id'],'COPIER');self.app.transfers.wait()
        result=self.app.transfers.get(job['id']);self.assertEqual(result['status'],'completed',result)
        self.app.config.allow_cleanup(self.entry['id'],True)
        return source,result

    def prepare(self,job):
        proposals=self.app.cleanup.candidates(job['id'])
        return self.app.cleanup.prepare(job['id'],[i['file_id'] for i in proposals['items']])

    def execute(self,review):
        job=self.app.cleanup.start(review['review_id'],'NETTOYER',True)
        self.app.cleanup.thread.join(timeout=10)
        self.assertFalse(self.app.cleanup.busy())
        return self.app.cleanup.get(job['id'])

    def test_inventory_to_copy_to_cleanup_requires_two_distinct_confirmations(self):
        source,copy=self.copy();archive=Path(copy['items'][0]['destination'])
        before=source.read_bytes(),archive.read_bytes()
        proposals=self.app.cleanup.candidates(copy['id']);self.assertEqual(len(proposals['items']),1)
        self.assertEqual(before,(source.read_bytes(),archive.read_bytes()))
        review=self.prepare(copy)
        for text,ack in (('COPIER',True),('NETTOYER',False),('',True)):
            with self.assertRaises(SafetyError):self.app.cleanup.start(review['review_id'],text,ack)
        self.assertTrue(source.exists());self.assertFalse(self.bin.calls)
        result=self.execute(review)
        self.assertEqual(result['status'],'completed',result)
        self.assertFalse(source.exists());self.assertEqual(archive.read_bytes(),PNG)
        receipt=json.loads(result['items'][0]['receipt'])
        self.assertEqual(Path(receipt['recycled_path']).read_bytes(),PNG)
        self.assertFalse(self.app.transfers.get(copy['id'])['originals_preserved'])
        self.assertEqual(self.app.db.stats()['files'],0)
        self.assertTrue(any(e['action']=='source_recycled' for e in self.app.db.events()))

    def test_source_root_cleanup_permission_is_opt_in_and_revocable(self):
        source,copy=self.copy();self.app.config.allow_cleanup(self.entry['id'],False)
        proposals=self.app.cleanup.candidates(copy['id'])
        self.assertFalse(proposals['items']);self.assertIn('autonome',proposals['excluded'][0]['reason'])
        self.app.config.allow_cleanup(self.entry['id'],True);review=self.prepare(copy)
        self.app.config.allow_cleanup(self.entry['id'],False)
        with self.assertRaises(SafetyError):self.execute(review)
        self.assertTrue(source.exists())

    def test_changed_source_after_review_blocks_all_mutation(self):
        source,copy=self.copy();review=self.prepare(copy);source.write_bytes(PNG+b'new content')
        with self.assertRaises(SafetyError):self.execute(review)
        self.assertTrue(source.exists());self.assertFalse(self.bin.calls)

    def test_changed_archive_after_review_blocks_all_mutation(self):
        source,copy=self.copy();review=self.prepare(copy)
        Path(copy['items'][0]['destination']).write_bytes(b'corrupted')
        with self.assertRaises(SafetyError):self.execute(review)
        self.assertEqual(source.read_bytes(),PNG);self.assertFalse(self.bin.calls)

    def test_inaccessible_or_replaced_destination_blocks_proposals(self):
        source,copy=self.copy()
        with patch.object(self.app.storage,'diagnose',return_value={'safe_to_write':False}):
            self.assertFalse(self.app.cleanup.candidates(copy['id'])['items'])
        self.dest.rename(self.base/'unplugged');self.dest.mkdir()
        self.assertFalse(self.app.cleanup.candidates(copy['id'])['items'])
        self.assertEqual(source.read_bytes(),PNG)

    def test_read_only_review_never_recreates_a_missing_archive_directory(self):
        source,copy=self.copy();archive=Path(copy['items'][0]['destination'])
        archive.unlink();archive.parent.rmdir()
        self.assertFalse(self.app.cleanup.candidates(copy['id'])['items'])
        self.assertFalse(archive.parent.exists());self.assertTrue(source.exists())

    def test_unverified_and_ambiguous_files_never_offered(self):
        source,copy=self.copy()
        with self.app.db.connect() as c:c.execute("UPDATE transfer_items SET status='error' WHERE job_id=?",(copy['id'],))
        self.assertFalse(self.app.cleanup.candidates(copy['id'])['items'])
        with self.app.db.connect() as c:
            item=c.execute('SELECT snapshot FROM transfer_items WHERE job_id=?',(copy['id'],)).fetchone()
            snapshot=json.loads(item['snapshot']);snapshot['detected_by']='extension (type non confirmé)'
            c.execute("UPDATE transfer_items SET status='verified',snapshot=? WHERE job_id=?",(json.dumps(snapshot),copy['id']))
        self.assertFalse(self.app.cleanup.candidates(copy['id'])['items']);self.assertTrue(source.exists())

    def test_sensitive_and_protected_sources_never_offered(self):
        source,copy=self.copy()
        cfg=self.app.config.snapshot();self.app.config.update_rules(cfg['keyword_categories'],cfg['archive_rules'],['*image*'])
        self.assertFalse(self.app.cleanup.candidates(copy['id'])['items'])
        self.assertTrue(source.exists())

    def test_symlink_source_and_hardlinked_archive_rejected(self):
        source,copy=self.copy();archive=Path(copy['items'][0]['destination'])
        os.link(archive,self.base/'archive-link')
        self.assertFalse(self.app.cleanup.candidates(copy['id'])['items'])
        (self.base/'archive-link').unlink()
        other=self.base/'other.png';source.rename(other)
        try:source.symlink_to(other)
        except OSError:self.skipTest('Création de liens indisponible')
        self.assertFalse(self.app.cleanup.candidates(copy['id'])['items'])
        self.assertEqual(other.read_bytes(),PNG)

    def test_review_expiration_and_replay_rejected(self):
        source,copy=self.copy();review=self.prepare(copy)
        with self.app.db.connect() as c:c.execute('UPDATE cleanup_reviews SET created=0 WHERE id=?',(review['review_id'],))
        with self.assertRaises(SafetyError):self.execute(review)
        review=self.prepare(copy);self.execute(review)
        with self.assertRaises(SafetyError):self.execute(review)
        self.assertEqual(len(self.bin.calls),1)

    def test_worker_rechecks_source_and_archive_before_each_recycle(self):
        source,copy=self.copy();review=self.prepare(copy)
        with patch.object(self.app.cleanup,'_run'):
            job=self.app.cleanup.start(review['review_id'],'NETTOYER',True)
            self.app.cleanup.thread.join(timeout=10)
        Path(copy['items'][0]['destination']).write_bytes(b'changed after confirmation')
        self.app.cleanup._run(job['id'])
        result=self.app.cleanup.get(job['id']);self.assertEqual(result['status'],'blocked')
        self.assertEqual(source.read_bytes(),PNG);self.assertFalse(self.bin.calls)

    def test_native_failure_never_claims_cleanup_success(self):
        source,copy=self.copy();review=self.prepare(copy)
        with patch.object(self.bin,'recycle',side_effect=PermissionError('file locked')):result=self.execute(review)
        self.assertEqual(result['status'],'blocked');self.assertTrue(source.exists())
        self.assertEqual(self.app.db.stats()['files'],1)

    def test_manual_procedure_checks_absence_and_archive(self):
        source,copy=self.copy()
        with patch.object(self.bin,'available',return_value=False):review=self.prepare(copy)
        result=self.execute(review)
        self.assertEqual(result['status'],'manual_required');self.assertTrue(source.exists())
        with self.assertRaises(SafetyError):self.app.cleanup.confirm_manual(result['id'],'RETRAIT EFFECTUÉ')
        source.rename(self.bin.folder/'manual-user-choice.png')
        done=self.app.cleanup.confirm_manual(result['id'],'RETRAIT EFFECTUÉ')
        self.assertEqual(done['status'],'completed')
        self.assertEqual(done['items'][0]['status'],'manual_removed')
        self.assertEqual(Path(copy['items'][0]['destination']).read_bytes(),PNG)

    def test_manual_receipt_rejected_when_archive_has_since_disappeared(self):
        source,copy=self.copy()
        with patch.object(self.bin,'available',return_value=False):review=self.prepare(copy)
        result=self.execute(review);source.rename(self.bin.folder/'manual.png')
        self.dest.rename(self.base/'disconnected')
        with self.assertRaises((SafetyError,OSError)):self.app.cleanup.confirm_manual(result['id'],'RETRAIT EFFECTUÉ')
        self.assertEqual(self.app.cleanup.get(result['id'])['items'][0]['status'],'manual_required')

    def test_permanent_delete_flag_is_vetoed(self):
        with self.assertRaises(SafetyError):require_recycle_flag(0)
        with self.assertRaises(SafetyError):require_recycle_flag(0x40)
        require_recycle_flag(0x80)

    def test_interrupted_cleanup_is_never_resumed_automatically(self):
        source,copy=self.copy();review=self.prepare(copy)
        with patch.object(self.app.cleanup,'_run'):
            result=self.app.cleanup.start(review['review_id'],'NETTOYER',True)
            self.app.cleanup.thread.join(timeout=10)
        fresh=Cleanup(self.app.config,self.app.db,self.app.transfers,self.bin)
        self.assertEqual(fresh.get(result['id'])['status'],'interrupted');self.assertTrue(source.exists())

    def test_text_false_cannot_be_interpreted_as_cleanup_consent(self):
        source,copy=self.copy();self.app.config.data['roots'][0]['cleanup_allowed']='false'
        self.assertFalse(self.app.cleanup.candidates(copy['id'])['items'])
        with self.assertRaises(ValueError):self.app.config.validate(self.app.config.snapshot())
        self.assertTrue(source.exists());self.assertFalse(self.bin.calls)
