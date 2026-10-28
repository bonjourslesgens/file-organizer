from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from file_organizer.safety import SafetyError
from tests.test_core import Fixture,PNG


class SetupTests(Fixture):
    def body(self,destination=''):
        return {'roots':[{'path':str(self.root),'label':'Mes photos','device':'PC fixe'}],
                'destination':destination,'protected_ack':True,'automation':{'enabled':False,'interval_seconds':300,'destination':destination}}

    def test_complete_first_use_is_read_only_on_sources_and_destination(self):
        one=self.write('voile.png');two=self.write('copy.png')
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (one,two)}
        dest=self.base/'archives';dest.mkdir()
        result=self.app.setup.apply(self.body(str(dest)));self.app.scanner.wait()
        ready=self.app.setup.finish(result['id'])
        self.assertTrue(ready['ready']);self.assertEqual(ready['stats']['files'],2)
        self.assertEqual(ready['stats']['duplicate_groups'],1);self.assertTrue(ready['plan_id'])
        self.assertEqual(self.app.transfers.list(),[]);self.assertEqual(self.app.cleanup.list(),[])
        self.assertEqual(list(dest.iterdir()),[])
        self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (one,two)})
        self.assertTrue(self.app.config.snapshot()['onboarding_completed'])
        self.assertEqual(self.app.setup.finish(result['id'])['plan_id'],ready['plan_id'])

    def test_read_only_discovery_and_source_check_do_not_authorize_or_copy(self):
        before=self.app.config.snapshot()
        discovery=self.app.setup.discover()
        self.assertFalse(discovery['destructive_operations']);self.assertIn('windows',discovery['protected_names'])
        self.assertEqual(self.app.setup.validate_source(str(self.root))['path'],str(self.root))
        self.assertEqual(self.app.config.snapshot(),before);self.assertEqual(self.app.transfers.list(),[])

    def test_unsafe_sources_and_missing_ack_leave_settings_unchanged(self):
        original=self.app.config.snapshot()
        for body in (self.body()|{'protected_ack':False},self.body()|{'roots':[{'path':'relative'}]},self.body()|{'roots':[]}):
            with self.subTest(body=body),self.assertRaises((ValueError,OSError)):self.app.setup.apply(body)
            self.assertEqual(self.app.config.snapshot(),original)

    def test_unknown_destination_blocks_before_applying_settings(self):
        dest=self.base/'archives';dest.mkdir();before=self.app.config.snapshot()
        with patch.object(self.app.storage,'diagnose',return_value={'safe_to_write':False,'anomalies':['Unknown']}),self.assertRaises(SafetyError):
            self.app.setup.apply(self.body(str(dest)))
        self.assertEqual(self.app.config.snapshot(),before);self.assertEqual(list(dest.iterdir()),[])

    def test_overlapping_destination_is_rejected_without_configuration_loss(self):
        dest=self.root/'archive';dest.mkdir();before=self.app.config.snapshot()
        with self.assertRaises(SafetyError):self.app.setup.apply(self.body(str(dest)))
        self.assertEqual(self.app.config.snapshot(),before)

    def test_inventory_only_setup_needs_no_destination(self):
        self.write('image.png')
        result=self.app.setup.apply(self.body());self.app.scanner.wait()
        ready=self.app.setup.finish(result['id'])
        self.assertTrue(ready['ready']);self.assertIsNone(ready['plan_id'])
        self.assertEqual(self.app.config.snapshot()['archive_destination'],'')

    def test_setup_cannot_enable_cleanup_and_keeps_existing_user_settings(self):
        self.app.config.data['keyword_categories']={'Mes cours':['cours']};self.app.config.save()
        added=self.base/'new-personal';added.mkdir()
        body=self.body()|{'roots':[{'path':str(added),'cleanup_allowed':True}]}
        result=self.app.setup.apply(body);self.app.scanner.wait()
        config=self.app.config.snapshot()
        self.assertEqual(len(config['roots']),2);self.assertEqual(config['keyword_categories'],{'Mes cours':['cours']})
        self.assertFalse(next(r for r in config['roots'] if r['path']==str(added))['cleanup_allowed'])

    def test_destination_changed_before_final_suggestions_blocks_finish(self):
        self.write('a.png');dest=self.base/'archives';dest.mkdir()
        result=self.app.setup.apply(self.body(str(dest)));self.app.scanner.wait()
        dest.rename(self.base/'disconnected');dest.mkdir()
        with self.assertRaises(SafetyError):self.app.setup.finish(result['id'])
        self.assertFalse(list(dest.iterdir()))
