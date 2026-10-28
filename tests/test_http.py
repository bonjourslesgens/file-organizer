import json
import re
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from file_organizer.server import make_server
from tests.test_core import Fixture, PNG


class HttpTests(Fixture):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(self, path, data=None, auth=True, headers=None, raw=None):
        h = {'X-Organizer-Token':self.app.token} if auth else {}
        if data is not None:
            h['Content-Type'] = 'application/json'
        h.update(headers or {})
        req = urllib.request.Request(self.url+path, data=raw if raw is not None else (json.dumps(data).encode() if data is not None else None), headers=h)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_shell_and_session_token_and_security_headers(self):
        code, headers, body = self.request('/', auth=False)
        self.assertEqual(code, 200)
        self.assertIn(self.app.token.encode(), body)
        self.assertNotIn(b'__SESSION_TOKEN__', body)
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_unauthorized_and_cross_origin_and_dns_rebinding_blocked(self):
        self.assertEqual(self.request('/api/state', auth=False)[0], 403)
        self.assertEqual(self.request('/', headers={'Host':'evil.example'})[0], 403)
        self.assertEqual(self.request('/api/scan', {}, headers={'Origin':'https://evil.example'})[0], 403)
        self.assertEqual(self.request('/api/scan', {}, auth=False)[0], 403)
        self.assertEqual(self.request('/api/scan', {}, headers={'Sec-Fetch-Site':'cross-site'})[0], 403)

    def test_scan_inventory_duplicates_simulation_and_report_end_to_end(self):
        self.write('a.png')
        self.write('b.png')
        self.assertEqual(self.request('/api/scan', {})[0], 200)
        self.assertEqual(self.app.scanner.wait()['status'], 'completed')
        self.assertEqual(json.loads(self.request('/api/files')[2])['total'], 2)
        self.assertEqual(json.loads(self.request('/api/duplicates')[2])['total'], 1)
        result = self.request('/api/simulate', {'destination':str(self.base/'destination')})
        self.assertEqual(result[0], 200)
        self.assertEqual(json.loads(result[2])['count'], 2)
        report = json.loads(self.request('/api/report')[2])
        self.assertEqual(report['stats']['files'], 2)
        self.assertEqual(report['stats']['potential_recoverable'], len(PNG))
        self.assertFalse((self.base/'destination').exists())

    def test_no_file_access_copy_or_deletion_routes(self):
        self.assertEqual(self.request('/api/delete', {'path':str(self.root)})[0], 404)
        self.assertEqual(self.request('/api/copy', {'path':str(self.root)})[0], 404)
        self.assertEqual(self.request('/../../etc/passwd')[0], 404)

    def test_bad_json_and_content_type_and_limits(self):
        self.assertEqual(self.request('/api/scan', raw=b'not-json', headers={'Content-Type':'application/json'})[0], 400)
        self.assertEqual(self.request('/api/scan', raw=b'{}', headers={'Content-Type':'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/scan', raw=b'x'*65537, headers={'Content-Type':'application/json'})[0], 413)
        self.assertEqual(self.request('/api/files?limit=not-a-number')[0], 400)

    def test_csv_protects_spreadsheet_formulas(self):
        self.write('=SUM(1).txt', b'text')
        self.scan()
        code, _, csv = self.request('/api/report?format=csv')
        self.assertEqual(code, 200)
        self.assertIn("'=SUM(1).txt", csv.decode('utf-8-sig'))

    def test_roots_api_rejects_system_and_removes_only_index(self):
        p = self.write('kept.png')
        self.scan()
        self.assertEqual(self.request('/api/roots/add', {'path':str(self.root/'AppData')})[0], 400)
        self.assertEqual(self.request('/api/roots/remove', {'id':self.entry['id']})[0], 200)
        self.assertEqual(self.app.db.stats()['files'], 0)
        self.assertEqual(p.read_bytes(), PNG)

    def test_active_scan_freezes_roots_rules_and_simulation(self):
        self.write('a.png')
        started, release = threading.Event(), threading.Event()
        original = self.app.scanner._read
        def paused(*args):
            started.set()
            release.wait(10)
            return original(*args)
        try:
            with patch.object(self.app.scanner, '_read', side_effect=paused):
                self.assertEqual(self.request('/api/scan', {})[0], 200)
                self.assertTrue(started.wait(5))
                self.assertEqual(self.request('/api/roots/remove', {'id':self.entry['id']})[0], 409)
                self.assertEqual(self.request('/api/simulate', {'destination':'E:\\Archives'})[0], 409)
                self.assertEqual(self.request('/api/scan', {})[0], 400)
                release.set()
                self.assertEqual(self.app.scanner.wait()['status'], 'completed')
        finally:
            release.set()

    def test_state_and_journal(self):
        state = json.loads(self.request('/api/state')[2])
        self.assertEqual(state['mode'], 'simulation')
        self.assertEqual(len(state['roots']), 1)
        self.app.db.event('test','Événement synthétique')
        self.assertEqual(json.loads(self.request('/api/events')[2])[0]['action'], 'test')

    def test_real_transfer_api_requires_specific_confirmation(self):
        self.write('photo.png');self.scan();dest=self.base/'archives';dest.mkdir()
        plan=json.loads(self.request('/api/simulate',{'destination':str(dest)})[2])
        code,_,body=self.request('/api/transfers/prepare',{'plan_id':plan['id'],'all_files':True})
        self.assertEqual(code,200,body);approval=json.loads(body)
        self.assertFalse(list(dest.iterdir()))
        self.assertEqual(self.request('/api/transfers/start',{'approval_id':approval['approval_id'],'confirmation':'oui'})[0],400)
        code,_,body=self.request('/api/transfers/start',{'approval_id':approval['approval_id'],'confirmation':'COPIER'})
        self.assertEqual(code,200,body);job=json.loads(body)
        self.app.transfers.wait()
        from pathlib import Path
        result=json.loads(self.request('/api/transfer?id='+job['id'])[2])
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(Path(result['items'][0]['destination']).read_bytes(),PNG)
        self.assertEqual((self.root/'photo.png').read_bytes(),PNG)
        self.assertTrue(json.loads(self.request('/api/transfers')[2]))

    def test_storage_diagnostic_is_read_only(self):
        dest=self.base/'archive';dest.mkdir();before=list(dest.iterdir())
        code,_,body=self.request('/api/storage/diagnose',{'path':str(dest)})
        self.assertEqual(code,200);data=json.loads(body)
        self.assertTrue(data['non_destructive'])
        self.assertTrue(data['filesystem']);self.assertGreater(data['capacity'],0)
        self.assertEqual(before,list(dest.iterdir()))
        missing=self.base/'nonexistent'
        data=json.loads(self.request('/api/storage/diagnose',{'path':str(missing)})[2])
        self.assertFalse(data['safe_to_write']);self.assertFalse(missing.exists())

    def test_preview_requires_auth_and_unchanged_whitelisted_image(self):
        image=self.write('image.png');self.scan();record=self.app.db.files()['items'][0]
        url='/api/preview?id='+str(record['id'])
        self.assertEqual(self.request(url,auth=False)[0],403)
        code,headers,body=self.request(url)
        self.assertEqual(code,200);self.assertEqual(headers['Content-Type'],'image/png');self.assertEqual(body,PNG)
        image.write_bytes(PNG+b'changed')
        self.assertEqual(self.request(url)[0],400)
        self.assertEqual(self.request('/api/preview?id=999999')[0],400)

    def test_automation_settings_and_onboarding_persist(self):
        self.assertEqual(self.request('/api/automation',{'enabled':False,'interval_seconds':60,'destination':''})[0],200)
        data=json.loads(self.request('/api/automation')[2]);self.assertFalse(data['settings']['enabled'])
        self.assertEqual(self.request('/api/automation',{'enabled':True,'interval_seconds':0,'destination':''})[0],400)
        self.assertEqual(self.request('/api/onboarding',{})[0],200)
        self.assertTrue(self.app.config.snapshot()['onboarding_completed'])

    def test_notification_routes_preserve_history(self):
        self.app.db.event('transfer_completed','Copie synthétique vérifiée')
        notes=json.loads(self.request('/api/notifications')[2]);self.assertTrue(notes)
        self.assertEqual(self.request('/api/notifications/dismiss',{'id':notes[0]['id']})[0],200)
        self.assertFalse(json.loads(self.request('/api/notifications')[2]))
        self.assertEqual(self.app.db.events()[0]['action'],'transfer_completed')

    def test_android_missing_tool_returns_actionable_status(self):
        with patch('file_organizer.android.shutil.which',return_value=None):
            code,_,body=self.request('/api/android/devices')
        self.assertEqual(code,200);self.assertIn('ADB absent',json.loads(body)['error'])
        self.assertEqual(self.request('/api/android/authorize',{'serial':'phone','path':'/data/data'})[0],400)
