from __future__ import annotations

import csv
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import secrets
import shutil
from urllib.parse import parse_qs, urlsplit

from .archive import Planner
from .config import Config
from .database import Database
from .scanner import Scanner
from .storage import Storage
from .transfers import Transfers
from .android import Android, PUBLIC_ROOTS
from .automation import Automation
from . import __version__
import threading

STATIC = Path(__file__).parent / 'static'


class Application:
    def __init__(self, state_dir):
        self.config = Config(Path(state_dir))
        self.db = Database(self.config.state_dir / 'inventory.sqlite3')
        self.scanner = Scanner(self.config, self.db)
        self.planner = Planner(self.config, self.db)
        self.token = secrets.token_urlsafe(32)
        self.operation_lock = threading.RLock()
        self.storage = Storage(self.config.state_dir)
        self.android = Android(self.config, self.db)
        self.transfers = Transfers(self.config, self.db, self.storage, self.android)
        self.automation = Automation(self)

    def busy(self, ignore_automation=False):
        return bool((self.scanner.thread and self.scanner.thread.is_alive()) or self.transfers.busy() or self.android.busy() or
                    (not ignore_automation and self.automation.worker and self.automation.worker.is_alive()))

    def close(self):
        self.automation.stop.set()
        self.scanner.cancel(); self.transfers.pause(); self.android.stop.set()
        self.scanner.wait(10); self.transfers.wait(10)
        if self.android.thread: self.android.thread.join(timeout=5)
        self.automation.close()

    def preview(self, file_id):
        from .safety import SafetyError, open_personal
        from .scanner import detect_type
        with self.db.connect() as c:
            row=c.execute("SELECT * FROM inventory WHERE id=? AND status='ok'",(file_id,)).fetchone()
        if not row or row['category']!='images' or row['size']>10*1024*1024:
            raise ValueError('Aperçu réservé aux images indexées de 10 Mio au maximum.')
        if row['source_kind']=='local':
            entry=next((r for r in self.config.snapshot()['roots'] if r['id']==row['root_id']),None)
            if entry is None:raise SafetyError('Dossier retiré de la liste blanche.')
            from .safety import is_sensitive
            if is_sensitive(Path(row['path']).relative_to(entry['path']),self.config.snapshot()['sensitive_patterns']):
                raise SafetyError('Fichier sensible exclu.')
            with open_personal(Path(entry['path']),Path(row['path'])) as (stream,_):
                content=stream.read(10*1024*1024+1)
        else:
            entry=next((r for r in self.config.snapshot()['android_roots'] if r['id']==row['root_id']),None)
            if entry is None:raise SafetyError('Autorisation Android retirée.')
            meta=self.android.metadata(entry,row['path'])
            snapshot=dict(row)|meta|{'root':entry,'kind':'android'}
            with self.android.open_source(snapshot) as stream:content=stream.read(10*1024*1024+1)
        category,mime,source=detect_type(content[:8192],Path(row['path']))
        if len(content)>10*1024*1024 or mime not in ('image/jpeg','image/png','image/gif','image/webp') or source!='signature' or hashlib.sha256(content).hexdigest()!=row['sha256']:
            raise SafetyError('Image modifiée ou format non pris en charge. Relancez l’analyse.')
        return content,mime

    def roots(self):
        result = []
        for root in self.config.snapshot()['roots']:
            try:
                from .safety import validate_root
                path = validate_root(root['path'], self.config.state_dir)
                usage = shutil.disk_usage(path)
                # Volume capacity is repeated per root; UI must not sum it.
                result.append(root | {'online': True, 'storage': dict(total=usage.total, free=usage.free, used=usage.used)})
            except (OSError, ValueError) as e:
                result.append(root | {'online': False, 'error': str(e), 'storage': None})
        return result


def make_server(app: Application, port=8765):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'FileOrganizer/0.2'

        def log_message(self, format, *args):
            pass  # Do not log request credentials or tokens.

        def reply(self, status, body, content_type='application/json; charset=utf-8', extra=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; connect-src 'self'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def authorized(self):
            supplied = self.headers.get('X-Organizer-Token', '')
            return hmac.compare_digest(supplied.encode('utf-8'), app.token.encode('ascii'))

        def do_GET(self):
            if not self.allowed_host():
                return self.reply(403, {'error': 'Hôte interdit.'})
            try:
                self.get()
            except (ValueError, KeyError, TypeError) as e:
                self.reply(400, {'error': str(e)})
            except (ConnectionError, BrokenPipeError):
                pass
            except Exception as e:
                app.db.event('http_error', type(e).__name__, 'error')
                self.reply(500, {'error': 'Erreur interne ; consultez le journal local.'})

        def get(self):
            parsed = urlsplit(self.path)
            path = parsed.path
            if not path.startswith('/api/'):
                files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
                if path not in files:
                    return self.reply(404, {'error': 'Ressource introuvable.'})
                filename, kind = files[path]
                data = (STATIC / filename).read_bytes()
                if path == '/':
                    data = data.replace(b'__SESSION_TOKEN__', app.token.encode('ascii'))
                return self.reply(200, data, kind)
            if not self.authorized():
                return self.reply(403, {'error': 'Session locale requise. Rechargez la page.'})
            q = parse_qs(parsed.query)
            value = lambda key, default='': q.get(key, [default])[0]
            limit = min(200, max(1, int(value('limit', '100'))))
            offset = max(0, int(value('offset', '0')))
            if path == '/api/state':
                return self.reply(200, {'config': app.config.snapshot(), 'roots': app.roots(), 'scan': app.scanner.snapshot(), 'stats': app.db.stats(), 'mode': 'simulation', 'version': __version__, 'transfers': app.transfers.list(), 'automation': app.automation.snapshot(), 'android_scan': dict(app.android.job), 'notifications_count': len(app.db.notifications())})
            if path == '/api/preview':
                content,mime=app.preview(int(value('id')))
                return self.reply(200,content,mime)
            if path == '/api/transfers':
                return self.reply(200, app.transfers.list())
            if path == '/api/transfer':
                return self.reply(200, app.transfers.get(value('id'), limit, offset))
            if path == '/api/plans':
                with app.db.connect() as c:
                    return self.reply(200, [dict(r) for r in c.execute('SELECT * FROM plans ORDER BY created DESC LIMIT 30')])
            if path == '/api/notifications':
                return self.reply(200, app.db.notifications())
            if path == '/api/automation':
                return self.reply(200, app.automation.snapshot() | {'history': app.automation.history()})
            if path == '/api/android/devices':
                try:
                    return self.reply(200, {'devices': app.android.devices(), 'roots': PUBLIC_ROOTS})
                except (OSError, ValueError) as e:
                    return self.reply(200, {'devices': [], 'roots': PUBLIC_ROOTS, 'error': str(e)})
            if path == '/api/android/files':
                return self.reply(200, app.android.files(value('root_id'), limit, offset))
            if path == '/api/files':
                return self.reply(200, app.db.files(value('q'), value('category'), value('device'), value('theme'), limit, offset))
            if path == '/api/duplicates':
                return self.reply(200, app.db.duplicates(limit, offset))
            if path == '/api/events':
                return self.reply(200, app.db.events(limit))
            if path == '/api/plan':
                return self.reply(200, app.planner.items(value('id'), limit, offset))
            if path == '/api/report':
                fmt = value('format', 'json')
                if fmt == 'json':
                    return self.reply(200, {'stats': app.db.stats(), 'scan': app.scanner.snapshot(), 'roots': app.roots(), 'notice': 'Inventaire local et Android ; copies uniquement après validation explicite, aucune suppression.', 'transfers': app.transfers.list()}, extra={'Content-Disposition': 'attachment; filename="rapport.json"'})
                if fmt != 'csv':
                    raise ValueError('Format inconnu.')
                output = io.StringIO(newline='')
                writer = csv.writer(output)
                writer.writerow(['Nom', 'Chemin', 'Appareil', 'Catégorie', 'Octets', 'MIME', 'Détection', 'SHA256', 'État'])
                with app.db.connect() as c:
                    for row in c.execute('SELECT * FROM inventory ORDER BY id'):
                        # Prevent spreadsheet formula injection from untrusted filenames.
                        cells = [row[k] for k in ('name', 'path', 'device', 'category', 'size', 'mime', 'detected_by', 'sha256', 'status')]
                        writer.writerow([("'" + v) if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else v for v in cells])
                return self.reply(200, output.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="inventaire.csv"'})
            self.reply(404, {'error': 'Route inconnue.'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            allowed_origins = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
            if not self.allowed_host() or not self.authorized() or (origin and origin not in allowed_origins) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.reply(403, {'error': 'Requête locale authentifiée requise.'})
            try:
                if self.headers.get_content_type() != 'application/json':
                    return self.reply(415, {'error': 'JSON requis.'})
                length = int(self.headers.get('Content-Length', '0'))
                if length < 2 or length > 65536:
                    return self.reply(413, {'error': 'Requête trop volumineuse ou vide.'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Objet JSON attendu.')
                path = urlsplit(self.path).path
                # Serialize config mutations with scan starts; freeze roots throughout scans.
                with app.operation_lock:
                    busy = app.busy()
                    if busy and path in ('/api/roots/add', '/api/roots/remove', '/api/rules', '/api/simulate', '/api/transfers/prepare', '/api/transfers/start', '/api/transfers/resume', '/api/android/authorize', '/api/android/remove', '/api/android/settings', '/api/android/scan', '/api/android/simulate'):
                        return self.reply(409, {'error': 'Une opération est en cours. Attendez sa fin ou mettez-la en pause.'})
                    if path == '/api/storage/diagnose':
                        result = app.storage.diagnose(body['path'])
                        app.db.event('storage_diagnosed', 'Diagnostic non destructif : '+str(body['path']) + (' : accessible' if result['safe_to_write'] else ' : écritures bloquées'), 'info' if result['safe_to_write'] else 'warning')
                    elif path == '/api/transfers/prepare':
                        result = app.transfers.prepare(body['plan_id'], body.get('file_ids'), body.get('all_files',False))
                    elif path == '/api/transfers/start':
                        result = app.transfers.start(body['approval_id'],body.get('confirmation',''))
                    elif path == '/api/transfers/pause':
                        app.transfers.pause(); result = {'ok':True}
                    elif path == '/api/transfers/resume':
                        result = app.transfers.resume(body['id'],body.get('confirmation',''))
                    elif path == '/api/automation':
                        result = app.automation.configure(body)
                    elif path == '/api/automation/run':
                        result = {'started':app.automation.tick(force=True)}
                    elif path == '/api/notifications/dismiss':
                        app.db.dismiss_notification(body['id']); result = {'ok':True}
                    elif path == '/api/onboarding':
                        app.config.settings(onboarding_completed=True); result = {'ok':True}
                    elif path == '/api/android/settings':
                        app.config.settings(adb_path=str(body['adb_path'])); result = {'ok':True}
                    elif path == '/api/android/authorize':
                        result = app.android.authorize(body['serial'],body['path'],body.get('label','Android'))
                    elif path == '/api/android/remove':
                        with app.config.lock:
                            app.config.data['android_roots'] = [r for r in app.config.data['android_roots'] if r['id']!=body['id']]
                            app.config.save()
                        with app.db.connect() as c: c.execute('DELETE FROM android_files WHERE root_id=?',(body['id'],))
                        result = {'ok':True}
                    elif path == '/api/android/scan':
                        result = app.android.start_scan(body['root_id'])
                    elif path == '/api/android/simulate':
                        result = app.android.simulate(body['root_id'],body['destination'])
                    elif path == '/api/roots/add':
                        result = app.config.add_root(str(body['path']), str(body.get('label', '')), str(body.get('device', '')))
                        app.db.event('root_added', f"Dossier autorisé : {result['path']}")
                    elif path == '/api/roots/remove':
                        app.config.remove_root(body['id'])
                        app.db.forget_root(body['id'])
                        app.db.event('root_removed', 'Dossier retiré de la liste blanche et de l’index. Fichiers personnels inchangés.')
                        result = {'ok': True}
                    elif path == '/api/rules':
                        app.config.update_rules(body['keyword_categories'], body['archive_rules'], body.get('sensitive_patterns'))
                        app.db.event('rules_updated', 'Règles et catégories modifiées ; relancez une analyse pour les étiquettes.')
                        result = {'ok': True}
                    elif path == '/api/simulate':
                        result = app.planner.simulate(body['destination'])
                    elif path == '/api/scan/cancel':
                        app.scanner.cancel()
                        result = {'ok': True}
                    elif path == '/api/scan':
                        # start acquires the lock itself; use RLock to serialize this path.
                        if busy: raise ValueError('Une opération est déjà en cours.')
                        result = app.scanner.start(force=body.get('force_hash', False))
                    else:
                        return self.reply(404, {'error': 'Route inconnue. Aucune suppression disponible.'})
                self.reply(200, result)
            except (ValueError, KeyError, TypeError, OSError) as e:
                app.db.event('operation_blocked',str(e),'warning')
                self.reply(400, {'error': str(e)})
            except Exception as e:
                app.db.event('http_error', type(e).__name__, 'error')
                self.reply(500, {'error': 'Erreur interne ; consultez le journal local.'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server
