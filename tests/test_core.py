import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
import unittest
from unittest.mock import patch

from file_organizer.archive import destination_path
from file_organizer.safety import SafetyError, is_link, open_personal, validate_file, validate_root
from file_organizer.scanner import detect_type
from file_organizer.server import Application

PNG = b'\x89PNG\r\n\x1a\n' + b'photo synthetique' * 7
MP4 = b'\x00\x00\x00\x18ftypmp42' + b'video synthetique' * 9


class Fixture(unittest.TestCase):
    def setUp(self):
        # Windows TEMP lives in protected AppData: use an isolated directory in the profile.
        self.tmp = tempfile.TemporaryDirectory(prefix='FileOrganizer-Test-', dir=Path.home() if os.name == 'nt' else None)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / 'personal'
        self.root.mkdir()
        self.app = Application(self.base / 'state')
        self.entry = self.app.config.add_root(str(self.root), 'Photos', 'PC test')

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def write(self, name, data=PNG, age=500):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        old = time.time() - age * 86400
        os.utime(path, (old, old))
        return path

    def scan(self):
        self.app.scanner.start()
        result = self.app.scanner.wait()
        self.assertNotEqual(result['status'], 'running')
        return result


class SafetyTests(Fixture):
    def test_only_explicit_existing_absolute_roots(self):
        for bad in ('relative/path', str(self.root / '..' / 'personal'), str(self.base / 'missing'), str(Path.home()), self.root.anchor):
            with self.subTest(bad=bad), self.assertRaises((SafetyError, OSError)):
                validate_root(bad)

    def test_system_and_app_roots_blocked_case_insensitively(self):
        for name in ('Windows', 'PROGRAM FILES', 'AppData', 'Android', 'SteamLibrary', 'node_modules', '.venv'):
            folder = self.root / name
            folder.mkdir()
            with self.subTest(name=name), self.assertRaises(SafetyError):
                validate_root(str(folder))

    def test_no_state_directory_or_overlap(self):
        with self.assertRaises(SafetyError):
            self.app.config.add_root(str(self.base), '', '')
        with self.assertRaises(SafetyError):
            self.app.config.add_root(str(self.app.config.state_dir), '', '')
        child = self.root / 'child'
        child.mkdir()
        with self.assertRaises(SafetyError):
            self.app.config.add_root(str(child), '', '')

    def test_development_folder_and_descendants_excluded(self):
        self.write('project/package.json', b'{}')
        self.write('project/sub/photo.png')
        with self.assertRaises(SafetyError):
            validate_root(str(self.root / 'project' / 'sub'))
        self.assertEqual(self.scan()['files'], 0)

    def test_protected_nested_files_and_binary_scripts_skipped(self):
        self.write('AppData/personal.png')
        self.write('Android/media/photo.png')
        self.write('games/save.png')
        self.write('program.exe', b'MZ')
        self.write('.hidden.png')
        self.write('keep.png')
        self.assertEqual(self.scan()['files'], 1)
        self.assertEqual(self.app.db.files()['items'][0]['name'], 'keep.png')

    def test_outside_root_rejected(self):
        outside = self.base / 'outside.png'
        outside.write_bytes(PNG)
        with self.assertRaises(SafetyError):
            validate_file(self.root, outside)

    def test_symlink_file_and_directory_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'secret.png').write_bytes(PNG)
        try:
            (self.root / 'link').symlink_to(outside, target_is_directory=True)
            (self.root / 'alias.png').symlink_to(outside / 'secret.png')
        except OSError:
            self.skipTest('Création de liens indisponible sans privilèges sur cette machine')
        with self.assertRaises(SafetyError):
            validate_root(str(self.root / 'link'))
        self.assertEqual(self.scan()['files'], 0)

    def test_hardlinks_excluded(self):
        src = self.write('one.png')
        os.link(src, self.root / 'two.png')
        self.assertEqual(self.scan()['files'], 0)

    def test_reparse_point_detected(self):
        class FakeStat:
            st_mode = stat.S_IFDIR
            st_file_attributes = 0x400
        self.assertTrue(is_link(FakeStat()))

    def test_source_modified_during_read_rejected(self):
        path = self.write('changing.png')
        with self.assertRaises(SafetyError):
            with open_personal(self.root, path) as (stream, _):
                stream.read(4)
                path.write_bytes(b'changed')

    @unittest.skipIf(os.name == 'nt', 'Test POSIX des descripteurs ; handles Windows testés dans CI')
    def test_ancestor_swapped_after_validation_rejected(self):
        path = self.write('album/image.png')
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'image.png').write_bytes(b'secret')
        original = validate_file
        def swap(root, file):
            result = original(root, file)
            (self.root / 'album').rename(self.root / 'old-album')
            (self.root / 'album').symlink_to(outside, target_is_directory=True)
            return result
        with patch('file_organizer.safety.validate_file', side_effect=swap):
            with self.assertRaises(OSError):
                with open_personal(self.root, path):
                    self.fail('Le lien ne doit jamais être ouvert')

    def test_windows_junction_rejected(self):
        if os.name != 'nt':
            self.skipTest('Jonction NTFS : uniquement Windows')
        import subprocess
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'secret.png').write_bytes(PNG)
        link = self.root / 'junction'
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
        if result.returncode:
            self.skipTest('Jonctions non disponibles sur ce volume')
        try:
            with self.assertRaises(SafetyError):
                validate_root(str(link))
            self.assertEqual(self.scan()['files'], 0)
        finally:
            link.rmdir()


class InventoryTests(Fixture):
    def test_inventory_exact_hashes_types_and_themes(self):
        self.write('voile.png')
        self.write('renamed.jpg', PNG)
        self.write('cours-voile.txt', 'Cours de voile'.encode())
        result = self.scan()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['files'], 3)
        stats = self.app.db.stats()
        self.assertEqual(stats['files'], 3)
        self.assertEqual(stats['duplicate_groups'], 1)
        self.assertEqual(stats['potential_recoverable'], len(PNG))
        group = self.app.db.duplicates()['items'][0]
        self.assertEqual(group['sha256'], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(group['similarity'], 100)
        self.assertEqual(len(self.app.db.files(theme='Voile')['items']), 2)
        record = self.app.db.files(query='renamed')['items'][0]
        self.assertEqual(record['mime'], 'image/png')
        self.assertEqual(record['detected_by'], 'signature')

    def test_same_size_different_contents_not_duplicates(self):
        self.write('a.txt', b'12345')
        self.write('b.txt', b'54321')
        self.scan()
        self.assertEqual(self.app.db.duplicates()['total'], 0)

    def test_cache_survives_restart_and_rehashes_changes(self):
        a = self.write('a.png')
        self.write('b.png')
        self.scan()
        self.app = Application(self.base / 'state')
        self.assertEqual(self.scan()['cached'], 2)
        a.write_bytes(PNG + b'changed')
        result = self.scan()
        self.assertEqual(result['cached'], 1)
        self.assertEqual(self.app.db.duplicates()['total'], 0)

    def test_deleted_files_removed_after_complete_scan(self):
        f = self.write('gone.png')
        self.scan()
        f.unlink()
        self.scan()
        self.assertEqual(self.app.db.stats()['files'], 0)

    def test_disconnected_device_keeps_index_but_disables_candidates(self):
        self.write('a.png')
        self.write('b.png')
        self.scan()
        self.root.rename(self.base / 'disconnected')
        result = self.scan()
        self.assertEqual(result['status'], 'completed_with_errors')
        self.assertEqual(self.app.db.stats()['files'], 2)
        self.assertEqual(self.app.db.duplicates()['total'], 0)
        self.assertEqual(self.app.planner.simulate(str(self.base / 'destination'))['count'], 0)
        self.assertFalse(self.app.roots()[0]['online'])

    def test_read_errors_are_visible_and_old_hashes_not_confirmed(self):
        self.write('a.png')
        self.write('b.png')
        self.scan()
        with patch.object(self.app.scanner, '_read', side_effect=PermissionError('Fichier verrouillé')):
            result = self.scan()
        self.assertEqual(result['errors'], 2)
        self.assertEqual(result['status'], 'completed_with_errors')
        self.assertEqual(self.app.db.duplicates()['total'], 0)
        self.assertEqual(self.app.db.stats()['unverified_files'], 2)

    def test_cancel_then_restart_reuses_validated_files(self):
        for i in range(5):
            self.write(f'{i}.png', PNG + bytes([i]))
        original = self.app.scanner._read
        def cancel_after_first(*args):
            record = original(*args)
            self.app.scanner.cancel()
            return record
        with patch.object(self.app.scanner, '_read', side_effect=cancel_after_first):
            self.assertEqual(self.scan()['status'], 'cancelled')
        self.assertEqual(self.app.db.stats()['files'], 1)
        result = self.scan()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['cached'], 1)
        self.assertEqual(result['files'], 5)

    def test_interrupted_run_is_recovered_from_disk(self):
        self.app.scanner.job = {'id': 'interrupted-test', 'status': 'running', 'files': 2}
        self.app.scanner.persist()
        fresh = Application(self.base / 'state')
        self.assertEqual(fresh.scanner.snapshot()['status'], 'interrupted')

    def test_pagination_filters_and_unicode(self):
        for i in range(12):
            self.write(f'voile-été-{i}.png')
        self.scan()
        result = self.app.db.files(query='été', category='images', device='PC test', limit=5, offset=5)
        self.assertEqual(result['total'], 12)
        self.assertEqual(len(result['items']), 5)
        self.assertEqual(len({f['id'] for f in result['items']}), 5)

    def test_force_hash_recalculates_unchanged_files(self):
        self.write('a.png')
        self.scan()
        with self.app.db.connect() as c:
            c.execute('UPDATE files SET sha256=?', ('0' * 64,))
        self.app.scanner.start(force=True)
        result = self.app.scanner.wait()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['cached'], 0)
        self.assertEqual(self.app.db.files()['items'][0]['sha256'], hashlib.sha256(PNG).hexdigest())

    def test_long_paths(self):
        name = '/'.join(('album-' + 'a' * 45 for _ in range(6))) + '/photo.png'
        try:
            path = self.write(name)
        except OSError:
            if os.name == 'nt':
                self.skipTest('Chemins longs non activés sur ce Windows')
            raise
        self.assertGreater(len(str(path)), 300)
        self.assertEqual(self.scan()['files'], 1)
        self.assertEqual(self.app.db.files()['items'][0]['sha256'], hashlib.sha256(PNG).hexdigest())

    def test_type_signature_overrides_extension_and_fallback_label(self):
        self.assertEqual(detect_type(b'%PDF-1.4', Path('fake.jpg'))[:2], ('documents', 'application/pdf'))
        self.assertEqual(detect_type(b'\x00\xff\x00', Path('unknown.jpg'))[2], 'extension (type non confirmé)')
        self.assertEqual(detect_type(MP4, Path('video.txt'))[0], 'videos')

    def test_configuration_rules_persist_and_validate(self):
        self.app.config.update_rules({'Voile': ['mer']}, [{'name':'Films','category':'videos','older_than_days':42,'enabled':False}])
        self.assertEqual(Application(self.base / 'state').config.snapshot()['keyword_categories'], {'Voile':['mer']})
        with self.assertRaises(ValueError):
            self.app.config.update_rules({}, [{'name':'Bad','category':'videos','older_than_days':-1,'enabled':True}])

    def test_removed_root_forgets_index_without_touching_files(self):
        f = self.write('personal.png')
        self.scan()
        self.app.config.remove_root(self.entry['id'])
        self.app.db.forget_root(self.entry['id'])
        self.assertEqual(self.app.db.stats()['files'], 0)
        self.assertEqual(f.read_bytes(), PNG)


class ArchiveTests(Fixture):
    def test_plan_no_write_no_deletion_age_and_dji(self):
        old = self.write('DJI_old.mp4', MP4)
        recent = self.write('recent.png', PNG, age=1)
        doc = self.write('cours.txt', b'active work', age=600)
        self.scan()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (old, recent, doc)}
        destination = self.base / 'seagate-not-mounted'
        plan = self.app.planner.simulate(str(destination))
        self.assertEqual(plan['count'], 1)
        self.assertIn('DJI', plan['items'][0]['destination'])
        self.assertFalse(plan['destination_verified'])
        self.assertFalse(destination.exists())
        self.assertEqual(before, {p:(p.read_bytes(),p.stat().st_mtime_ns) for p in before})
        self.assertTrue(self.app.db.events())

    def test_name_collisions_never_share_a_destination(self):
        self.write('album1/photo.png')
        self.write('album2/photo.png')
        self.scan()
        plan = self.app.planner.simulate(str(self.base / 'archive-output'))
        names = [i['destination'].casefold() for i in plan['items']]
        self.assertEqual(len(set(names)), 2)

    def test_changed_and_replaced_sources_not_planned(self):
        p = self.write('old.png')
        self.scan()
        p.write_bytes(PNG + b'changed')
        result = self.app.planner.simulate(str(self.base / 'archive-output'))
        self.assertEqual(result['count'], 0)
        self.assertEqual(result['skipped'], 1)

    def test_missing_source_and_symlinks_not_planned(self):
        p = self.write('gone.png')
        self.scan()
        p.unlink()
        self.assertEqual(self.app.planner.simulate(str(self.base / 'archive-output'))['skipped'], 1)

    def test_disabled_rules_are_not_applied(self):
        self.write('photo.png')
        self.scan()
        cfg = self.app.config.snapshot()
        for rule in cfg['archive_rules']:
            rule['enabled'] = False
        self.app.config.update_rules(cfg['keyword_categories'], cfg['archive_rules'])
        self.assertEqual(self.app.planner.simulate(str(self.base / 'archive-output'))['count'], 0)

    def test_windows_destination_supported_without_disk_access(self):
        self.write('photo.png')
        self.scan()
        plan = self.app.planner.simulate('E:\\Archives')
        self.assertEqual(plan['count'], 1)
        self.assertTrue(plan['items'][0]['destination'].startswith('E:\\Archives\\'))

    def test_unsafe_destinations_rejected(self):
        for value in ('relative', '/tmp/../etc', 'C:\\Windows\\archive', '\\\\server\\share'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                destination_path(value)

    def test_plan_paginated_and_persisted(self):
        for i in range(4):
            self.write(f'{i}.png')
        self.scan()
        plan = self.app.planner.simulate(str(self.base / 'archive-output'))
        restarted = Application(self.base / 'state')
        result = restarted.planner.items(plan['id'], limit=2, offset=2)
        self.assertEqual(result['total_count'], 4)
        self.assertEqual(len(result['items']), 2)
