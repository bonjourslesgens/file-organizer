import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from unittest.mock import patch

from file_organizer.android import Android, PUBLIC_ROOTS, ProcessStream, validate_path
from file_organizer.safety import SafetyError
from tests.test_core import Fixture, PNG, MP4


class FakeAndroid(Android):
    """Emulates only read-only ADB replies; never touches a real USB device."""
    def __init__(self,*args):
        super().__init__(*args)
        self.contents={PUBLIC_ROOTS[0]+'/voile.png':PNG, PUBLIC_ROOTS[0]+'/movie.mp4':MP4}
        self.redirects={};self.private=set();self.available=True;self.commands=[]

    def adb(self):return 'FAKE_ADB'

    def _run(self,args,timeout=30):
        self.commands.append(args)
        if not self.available:raise OSError('device offline')
        if args[0]=='devices':return b'List of devices attached\nSYNTHETIC device usb:1 model:Oukitel_Test\n'
        command=shlex.split(args[-1]);path=command[-1]
        if command[0]=='test':return b'OK'
        if command[0]=='find':return b''.join(p.encode()+b'\0' for p in self.contents)
        if command[0]=='readlink':return self.redirects.get(path,path).encode()
        if command[0]=='for':return b'BLOCKED' if any(p in args[-1] for p in self.private) else b''
        if command[0]=='stat':
            if path not in self.contents:raise OSError('file missing')
            return f'{len(self.contents[path])}|1600000000|1|regular file'.encode()
        if command[0]=='head':return self.contents[path][:8192]
        if command[0]=='sha256sum':return (hashlib.sha256(self.contents[path]).hexdigest()+'  '+path).encode()
        raise AssertionError(command)


class AndroidTests(Fixture):
    def setUp(self):
        super().setUp()
        self.phone=FakeAndroid(self.app.config,self.app.db)
        self.app.android=self.phone;self.app.transfers.android=self.phone
        self.entry_android=self.phone.authorize('SYNTHETIC',PUBLIC_ROOTS[0],'Oukitel synthétique')

    def scan_phone(self):
        self.phone.start_scan(self.entry_android['id']);self.phone.thread.join(timeout=10)
        self.assertFalse(self.phone.thread.is_alive())
        return self.phone.job

    def test_public_media_inventory_and_cross_device_duplicates(self):
        self.write('copy.png');self.scan()
        self.assertEqual(self.scan_phone()['status'],'completed')
        self.assertEqual(self.phone.files()['total'],2)
        self.assertEqual(self.app.db.stats()['files'],3)
        duplicate=self.app.db.duplicates()['items'][0]
        self.assertEqual(duplicate['copies'],2)
        self.assertEqual(len({i['id'] for i in duplicate['items']}),2)
        self.assertTrue(any(i['id']<0 for i in duplicate['items']))
        self.assertEqual(self.app.db.files(category='videos')['total'],1)

    def test_android_app_system_hidden_and_equivalent_paths_rejected(self):
        for p in ('/storage/emulated/0/Android/data/photo.jpg','/data/data/private.png','/sdcard/DCIM/photo.png',PUBLIC_ROOTS[0]+'/../Android/private.png',PUBLIC_ROOTS[0]+'/.hidden/a.png',PUBLIC_ROOTS[0]+'/com.whatsapp/a.png'):
            with self.subTest(path=p),self.assertRaises(SafetyError):validate_path(p)

    def test_link_and_private_project_directories_excluded(self):
        path=PUBLIC_ROOTS[0]+'/voile.png'
        self.phone.redirects[path]='/data/data/private/photo.png'
        self.phone.private.add(PUBLIC_ROOTS[0])
        result=self.scan_phone()
        self.assertEqual(result['files'],0)
        self.assertEqual(self.phone.files()['total'],0)

    def test_non_media_and_extension_only_guesses_excluded(self):
        self.phone.contents={PUBLIC_ROOTS[0]+'/fake.jpg':b'not an image',PUBLIC_ROOTS[0]+'/app.apk':b'PK\x03\x04'}
        self.assertEqual(self.scan_phone()['files'],0)

    def test_disconnect_retains_unverified_inventory(self):
        self.scan_phone();self.phone.available=False
        self.assertEqual(self.scan_phone()['status'],'blocked')
        self.assertEqual(self.phone.files()['total'],2)
        self.assertEqual(self.app.db.duplicates()['total'],0)
        with self.assertRaises(OSError):self.phone.simulate(self.entry_android['id'],str(self.base/'archive'))

    def test_android_plan_and_direct_verified_stream(self):
        self.scan_phone();dest=self.base/'archives';dest.mkdir()
        plan=self.phone.simulate(self.entry_android['id'],str(dest))
        a=self.app.transfers.prepare(plan['id'],all_files=True)
        native=subprocess.Popen
        observed=[]
        def fake_popen(args,**kw):
            if args[0]!='FAKE_ADB':return native(args,**kw)
            observed.append(args)
            path=shlex.split(args[-1])[-1]
            content=self.phone.contents[path]
            return native([sys.executable,'-c','import sys;sys.stdout.buffer.write(bytes.fromhex(sys.argv[1]))',content.hex()],**kw)
        with patch('file_organizer.android.subprocess.Popen',side_effect=fake_popen):
            j=self.app.transfers.start(a['approval_id'],'COPIER');self.app.transfers.wait()
        result=self.app.transfers.get(j['id'])
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(result['verified'],2)
        for item in result['items']:
            self.assertEqual(Path(item['destination']).read_bytes(),self.phone.contents[item['source']])
        self.assertTrue(all('exec-out' in args and args[-1].startswith('cat ') for args in observed))
        for command in self.phone.commands:
            self.assertFalse(any(token in command for token in ('push','rm','remount','root','connect','tcpip')))

    def test_android_changed_before_copy_blocked(self):
        self.scan_phone();dest=self.base/'archives';dest.mkdir()
        p=self.phone.simulate(self.entry_android['id'],str(dest))
        self.phone.contents[PUBLIC_ROOTS[0]+'/voile.png']+=b'changed'
        with self.assertRaises(SafetyError):self.app.transfers.prepare(p['id'],all_files=True)
        self.assertEqual(list(dest.iterdir()),[])

    def test_removed_android_authorization_blocks_copy(self):
        self.scan_phone();dest=self.base/'archives';dest.mkdir()
        p=self.phone.simulate(self.entry_android['id'],str(dest))
        self.app.config.data['android_roots']=[]
        with self.assertRaises(SafetyError):self.app.transfers.prepare(p['id'],all_files=True)

    def test_pipe_stream_handles_binary_and_eof(self):
        content=b'\0\xff'*900000
        process=subprocess.Popen([sys.executable,'-c','import sys;sys.stdout.buffer.write(b"\\x00\\xff"*900000)'],stdout=subprocess.PIPE)
        stream=ProcessStream(process)
        try:
            data=stream.read(500000)+stream.read(2000000)
            self.assertEqual(data,content);self.assertEqual(stream.read(100),b'')
        finally:stream.close()

    def test_missing_adb_is_an_explicit_prerequisite(self):
        connector=Android(self.app.config,self.app.db)
        with patch('file_organizer.android.shutil.which',return_value=None),self.assertRaisesRegex(SafetyError,'ADB absent'):
            connector.devices()


class AutomationTests(Fixture):
    def cycle(self,now):
        started=self.app.automation.tick(now=now)
        if started:self.app.automation.worker.join(timeout=10)
        return started

    def test_disabled_by_default_and_settings_persist(self):
        self.assertFalse(self.app.config.snapshot()['automation']['enabled'])
        self.assertFalse(self.cycle(time.time()))
        self.app.config.settings(automation={'enabled':True,'interval_seconds':60,'destination':''})
        from file_organizer.config import Config
        self.assertEqual(Config(self.base/'state').snapshot()['automation']['interval_seconds'],60)
        with self.assertRaises(ValueError):self.app.config.settings(automation={'enabled':True,'interval_seconds':1,'destination':''})

    def test_periodic_new_files_classification_and_simulation_never_copy(self):
        self.write('voile.png')
        target=self.base/'not-created'
        self.app.config.settings(automation={'enabled':True,'interval_seconds':30,'destination':str(target)})
        now=time.time()
        with patch.object(self.app.transfers,'start',side_effect=AssertionError('No automatic copy')):
            self.assertTrue(self.cycle(now))
            self.assertEqual(self.app.db.stats()['files'],1)
            self.assertFalse(self.cycle(now+10))
            self.write('new.png')
            self.assertTrue(self.cycle(now+31))
        self.assertEqual(self.app.db.stats()['files'],2)
        self.assertFalse(target.exists())
        history=self.app.automation.history()
        self.assertEqual(len(history),2)
        self.assertTrue(history[0]['plan_id'])
        self.assertEqual(self.app.db.files(theme='Voile')['total'],1)

    def test_busy_transfer_prevents_background_scan(self):
        self.write('a.png')
        self.app.config.settings(automation={'enabled':True,'interval_seconds':30,'destination':''})
        with patch.object(self.app.transfers,'busy',return_value=True):
            self.assertFalse(self.cycle(time.time()))
        self.assertEqual(self.app.db.stats()['files'],0)

    def test_unavailable_roots_report_errors_without_simulated_success(self):
        self.root.rename(self.base/'disconnected')
        self.app.config.settings(automation={'enabled':True,'interval_seconds':30,'destination':str(self.base/'archives')})
        self.assertTrue(self.cycle(time.time()))
        self.assertEqual(self.app.automation.history()[0]['status'],'completed_with_errors')
        self.assertIsNone(self.app.automation.history()[0]['plan_id'])

    def test_notification_dismissal_keeps_audit_log(self):
        self.app.db.event('test_failure','Synthetic failure','warning')
        notes=self.app.db.notifications();self.assertTrue(notes)
        self.app.db.dismiss_notification(notes[0]['id'])
        self.assertEqual(self.app.db.notifications(),[])
        self.assertEqual(self.app.db.events()[0]['action'],'test_failure')
