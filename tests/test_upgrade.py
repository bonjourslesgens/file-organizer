import json
import sqlite3
from pathlib import Path

from file_organizer.config import Config
from file_organizer.database import Database
from file_organizer.safety import SafetyError
from tests.test_core import Fixture


class UpgradeTests(Fixture):
    def test_legacy_index_is_preserved_and_backed_up_before_migration(self):
        path=self.base/'legacy.sqlite3'
        with sqlite3.connect(path) as c:
            c.execute('CREATE TABLE plan_items(plan_id TEXT,file_id INTEGER,source TEXT,destination TEXT,size INTEGER,sha256 TEXT,reason TEXT,warning TEXT)')
            c.execute("INSERT INTO plan_items VALUES('old-plan',1,'source','destination',4,'abcd','old rule','old warning')")
        c.close()
        db=Database(path)
        with db.connect() as c:
            row=c.execute('SELECT * FROM plan_items').fetchone()
            self.assertEqual(row['source'],'source');self.assertEqual(row['snapshot'],'{}')
        backups=list(self.base.glob('inventory.before-0.2-*.sqlite3'))
        self.assertEqual(len(backups),1)
        with sqlite3.connect(backups[0]) as c:
            self.assertEqual(len(c.execute('PRAGMA table_info(plan_items)').fetchall()),8)
            self.assertEqual(c.execute('SELECT source FROM plan_items').fetchone()[0],'source')
        c.close()

    def test_legacy_configuration_gets_safe_defaults_without_losing_roots(self):
        cfg=self.app.config.snapshot()
        for key in ('android_roots','adb_path','automation','onboarding_completed','sensitive_patterns'):cfg.pop(key)
        self.app.config.path.write_text(json.dumps(cfg),encoding='utf-8')
        upgraded=Config(self.base/'state').snapshot()
        self.assertEqual(upgraded['roots'],cfg['roots'])
        self.assertFalse(upgraded['automation']['enabled']);self.assertEqual(upgraded['android_roots'],[])
        self.assertTrue(upgraded['sensitive_patterns'])

    def test_sensitive_files_excluded_from_scan_and_existing_plans(self):
        self.write('passwords.png');self.write('normal.png');self.scan()
        self.assertEqual(self.app.db.files()['total'],1)
        dest=self.base/'archives';dest.mkdir();plan=self.app.planner.simulate(str(dest))
        cfg=self.app.config.snapshot()
        self.app.config.update_rules(cfg['keyword_categories'],cfg['archive_rules'],['*normal*'])
        with self.assertRaises(SafetyError):self.app.transfers.prepare(plan['id'],all_files=True)
        self.assertFalse(list(dest.iterdir()))
