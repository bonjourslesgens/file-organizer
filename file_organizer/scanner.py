from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path
import stat
import threading
import time
import uuid

from .safety import (BLOCKED_NAMES, SafetyError, identity, is_link, is_project,
                     open_personal, validate_root)

CATEGORIES = {'image': 'images', 'video': 'videos', 'audio': 'audio', 'text': 'documents'}
DOCUMENT_EXTS = {'.pdf', '.doc', '.docx', '.odt', '.xls', '.xlsx', '.ods', '.ppt', '.pptx', '.odp', '.csv', '.rtf', '.epub'}
ARCHIVE_EXTS = {'.zip', '.7z', '.rar', '.tar', '.gz', '.bz2', '.xz'}


def detect_type(header: bytes, path: Path):
    """Signatures first; report extension-only guesses honestly."""
    signatures = [(b'\x89PNG\r\n\x1a\n', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'),
                  (b'GIF87a', 'image/gif'), (b'GIF89a', 'image/gif'),
                  (b'%PDF-', 'application/pdf'), (b'\x1f\x8b', 'application/gzip'),
                  (b'7z\xbc\xaf\x27\x1c', 'application/x-7z-compressed'),
                  (b'Rar!\x1a\x07', 'application/vnd.rar'), (b'ID3', 'audio/mpeg'),
                  (b'fLaC', 'audio/flac'), (b'OggS', 'audio/ogg')]
    mime, source = None, 'signature'
    for sig, kind in signatures:
        if header.startswith(sig):
            mime = kind
            break
    if header.startswith(b'RIFF') and len(header) >= 12:
        mime = {b'WEBP': 'image/webp', b'WAVE': 'audio/wav', b'AVI ': 'video/x-msvideo'}.get(header[8:12])
    if header[4:8] == b'ftyp':
        mime = 'image/heic' if header[8:12] in (b'heic', b'heix', b'hevc', b'mif1', b'avif') else 'video/mp4'
    if header.startswith(b'PK\x03\x04'):
        mime = 'application/zip'
        # Office/ODF containers need a deeper parser: extension is only a hint.
        if path.suffix.lower() in DOCUMENT_EXTS:
            return 'documents', mimetypes.guess_type(path.name)[0] or mime, 'extension (conteneur ZIP confirmé)'
    if mime is None:
        try:
            header.decode('utf-8')
            if header and not any(b < 9 or 13 < b < 32 for b in header):
                mime = 'text/plain'
        except UnicodeDecodeError:
            pass
    if mime is None:
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        source = 'extension (type non confirmé)'
    category = CATEGORIES.get(mime.split('/')[0], 'other')
    if mime == 'application/pdf':
        category = 'documents'
    elif mime in ('application/zip', 'application/gzip', 'application/x-7z-compressed', 'application/vnd.rar'):
        category = 'archives'
    elif source.startswith('extension'):
        if path.suffix.lower() in DOCUMENT_EXTS:
            category = 'documents'
        elif path.suffix.lower() in ARCHIVE_EXTS:
            category = 'archives'
    return category, mime, source


class Cancelled(Exception):
    pass


class Scanner:
    def __init__(self, config, db):
        self.config, self.db = config, db
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        with db.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, updated REAL, data TEXT)')
            last = c.execute('SELECT data FROM scans ORDER BY updated DESC LIMIT 1').fetchone()
        self.job = json.loads(last['data']) if last else {'status': 'idle'}
        if self.job['status'] in ('running', 'cancelling'):
            self.job['status'] = 'interrupted'
            self.persist()
            db.event('scan_interrupted', 'Analyse interrompue : relancez-la pour reprendre depuis le cache.', 'warning')

    def snapshot(self):
        with self.lock:
            return dict(self.job)

    def persist(self):
        if 'id' in self.job:
            with self.db.connect() as c:
                c.execute('INSERT OR REPLACE INTO scans VALUES(?,?,?)', (self.job['id'], time.time(), json.dumps(self.job)))

    def start(self, force=False):
        if type(force) is not bool:
            raise ValueError('Le recalcul complet doit être activé ou désactivé.')
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Une analyse est déjà en cours.')
            roots = self.config.snapshot()['roots']
            if not roots:
                raise ValueError('Ajoutez au moins un dossier autorisé.')
            self.stop_event.clear()
            self.job = dict(id=uuid.uuid4().hex, status='running', force_hash=force, started=time.time(), files=0,
                            bytes=0, cached=0, skipped=0, errors=0, current='', message='Analyse en cours')
            self.persist()
            self.db.event('scan_started', 'Analyse des dossiers autorisés démarrée.')
            self.thread = threading.Thread(target=self._run, args=(roots,), daemon=True)
            self.thread.start()
            return dict(self.job)

    def cancel(self):
        self.stop_event.set()

    def wait(self, timeout=30):
        if self.thread:
            self.thread.join(timeout)
        return self.snapshot()

    def _update(self, **changes):
        with self.lock:
            self.job.update(changes)

    def _increment(self, key, amount=1):
        with self.lock:
            self.job[key] += amount

    def _check_cancel(self):
        if self.stop_event.is_set():
            raise Cancelled()

    def _read(self, root: Path, path: Path, old, config):
        from .safety import is_sensitive
        if is_sensitive(path.relative_to(root),config.get('sensitive_patterns',[])):
            raise SafetyError('Fichier sensible exclu par les règles.')
        with open_personal(root, path) as (stream, st):
            fingerprint = (str(st.st_dev), str(st.st_ino), st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            previous = (old['device_id'], old['inode'], old['size'], old['mtime_ns'], old['ctime_ns']) if old else None
            if not config.get('force_hash', False) and previous == fingerprint and old['sha256']:
                digest = old['sha256']
                category, mime, source = old['category'], old['mime'], old['detected_by']
                self._increment('cached')
            else:
                h = hashlib.sha256()
                header = stream.read(8192)
                h.update(header)
                while True:
                    self._check_cancel()
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
                digest = h.hexdigest()
                category, mime, source = detect_type(header, path)
        themes = [name for name, words in config['keyword_categories'].items()
                  if any(word.casefold() in str(path.relative_to(root)).casefold() for word in words)]
        created = getattr(st, 'st_birthtime', st.st_ctime if os.name == 'nt' else None)
        return dict(path=str(path), name=path.name, extension=path.suffix.lower(), size=st.st_size,
                    mtime=st.st_mtime, created=created, ctime_ns=st.st_ctime_ns, mtime_ns=st.st_mtime_ns,
                    inode=str(st.st_ino), device_id=str(st.st_dev), category=category, mime=mime,
                    detected_by=source, themes=json.dumps(themes, ensure_ascii=False), sha256=digest, status='ok')

    def _run(self, roots):
        config = self.config.snapshot()
        config['force_hash'] = self.job.get('force_hash', False)
        try:
            for entry in roots:
                self._check_cancel()
                root_id = entry['id']
                try:
                    root = validate_root(entry['path'], self.config.state_dir)
                except (OSError, ValueError) as e:
                    with self.db.connect() as c:
                        c.execute("UPDATE files SET status='offline',sha256=NULL WHERE root_id=?", (root_id,))
                    self._increment('errors')
                    self.db.event('root_unavailable', f"{entry['label']} : {e}", 'warning')
                    continue
                with self.db.connect() as c:
                    c.execute("UPDATE files SET status='unverified' WHERE root_id=?", (root_id,))
                root_incomplete = False
                def walk_error(error):
                    nonlocal root_incomplete
                    root_incomplete = True
                    self._increment('errors')
                    self.db.event('read_error', str(error), 'warning')
                for folder, dirs, names in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
                    self._check_cancel()
                    directory = Path(folder)
                    # Recheck before descending, including the root itself.
                    try:
                        from .safety import check_components
                        check_components(directory)
                        if is_project(directory):
                            dirs[:] = []
                            self._increment('skipped', len(names))
                            continue
                        safe_dirs = []
                        for name in dirs:
                            child = directory / name
                            if name.casefold() in BLOCKED_NAMES or name.startswith('.') or is_link(child.lstat()) or is_project(child):
                                self._increment('skipped')
                            else:
                                safe_dirs.append(name)
                        dirs[:] = safe_dirs
                    except (OSError, ValueError) as e:
                        dirs[:] = []
                        walk_error(e)
                        continue
                    for name in names:
                        self._check_cancel()
                        path = directory / name
                        self._update(current=str(path))
                        with self.db.connect() as c:
                            old = c.execute('SELECT * FROM files WHERE path=?', (str(path),)).fetchone()
                        try:
                            record = self._read(root, path, old, config)
                            record.update(root_id=root_id, device=entry['device'], seen=self.job['id'])
                            keys = list(record)
                            with self.db.connect() as c:
                                c.execute('INSERT INTO files (' + ','.join(keys) + ') VALUES (' + ','.join('?' for _ in keys) + ') ON CONFLICT(path) DO UPDATE SET ' + ','.join(f'{k}=excluded.{k}' for k in keys), list(record.values()))
                            self._increment('files')
                            self._increment('bytes', record['size'])
                        except SafetyError as e:
                            self._increment('skipped')
                            if old:
                                with self.db.connect() as c:
                                    c.execute('DELETE FROM files WHERE path=?', (str(path),))
                            self.db.event('file_excluded', f'{path} : {e}', 'warning')
                        except OSError as e:
                            root_incomplete = True
                            self._increment('errors')
                            self.db.event('read_error', f'{path} : {e}', 'warning')
                        if (self.job['files'] + self.job['skipped']) % 25 == 0:
                            self.persist()
                with self.db.connect() as c:
                    if not root_incomplete:
                        c.execute('DELETE FROM files WHERE root_id=? AND seen!=?', (root_id, self.job['id']))
                self.persist()
            self._update(status='completed' if not self.job['errors'] else 'completed_with_errors',
                         message='Analyse terminée' if not self.job['errors'] else 'Analyse terminée avec des dossiers ou fichiers inaccessibles')
        except Cancelled:
            self._update(status='cancelled', message='Analyse arrêtée. Relancez-la pour reprendre depuis le cache.')
        except Exception as e:
            self._increment('errors')
            self._update(status='failed', message=str(e))
            self.db.event('scan_failed', str(e), 'error')
        finally:
            self._update(finished=time.time(), current='')
            self.persist()
            self.db.event('scan_finished', f"{self.job['status']} : {self.job['files']} fichiers, {self.job['errors']} erreurs.")
