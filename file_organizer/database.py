from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid

SCHEMA = '''
CREATE TABLE IF NOT EXISTS files (
 id INTEGER PRIMARY KEY, root_id TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL, extension TEXT NOT NULL, size INTEGER NOT NULL,
 mtime REAL NOT NULL, created REAL, ctime_ns INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
 inode TEXT NOT NULL, device_id TEXT NOT NULL, device TEXT NOT NULL,
 category TEXT NOT NULL, mime TEXT NOT NULL, detected_by TEXT NOT NULL,
 themes TEXT NOT NULL, sha256 TEXT, status TEXT NOT NULL DEFAULT 'ok', seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS file_hash ON files(sha256, size);
CREATE INDEX IF NOT EXISTS file_root ON files(root_id);
CREATE INDEX IF NOT EXISTS file_category ON files(category);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, level TEXT NOT NULL,
 action TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
 id TEXT PRIMARY KEY, created REAL NOT NULL, destination TEXT NOT NULL,
 total_count INTEGER NOT NULL, total_bytes INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_items (
 plan_id TEXT NOT NULL, file_id INTEGER NOT NULL, source TEXT NOT NULL,
 destination TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT,
 reason TEXT NOT NULL, warning TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS plan_items_id ON plan_items(plan_id);
CREATE TABLE IF NOT EXISTS android_files (
 id INTEGER PRIMARY KEY, serial TEXT, root_id TEXT, path TEXT, name TEXT, size INTEGER, mtime REAL,
 sha256 TEXT, category TEXT, mime TEXT, detected_by TEXT, status TEXT, seen TEXT, UNIQUE(serial,path));
CREATE INDEX IF NOT EXISTS android_hash ON android_files(sha256,size);
CREATE VIEW IF NOT EXISTS inventory AS
 SELECT files.*, 'local' AS source_kind FROM files
 UNION ALL
 SELECT -id,root_id,path,name,'',size,mtime,NULL,CAST(mtime*1000000000 AS INTEGER),
 CAST(mtime*1000000000 AS INTEGER),'',serial,'Android '||serial,category,mime,detected_by,'[]',sha256,status,seen,'android' FROM android_files;
CREATE TABLE IF NOT EXISTS notification_dismissals(event_id INTEGER PRIMARY KEY);
'''


class Database:
    def __init__(self, path: Path):
        self.path = path
        existing_database = path.exists()
        with self.connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript(SCHEMA)
            columns = {row['name'] for row in conn.execute('PRAGMA table_info(plan_items)')}
            if 'snapshot' not in columns:
                if existing_database:
                    backup_path = path.with_name('inventory.before-0.2-' + uuid.uuid4().hex + '.sqlite3')
                    backup = sqlite3.connect(backup_path)
                    try:
                        conn.backup(backup)
                    finally:
                        backup.close()
                conn.execute("ALTER TABLE plan_items ADD COLUMN snapshot TEXT NOT NULL DEFAULT '{}'")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def event(self, action, message, level='info'):
        with self.connect() as c:
            c.execute('INSERT INTO events(timestamp,level,action,message) VALUES(?,?,?,?)',
                      (time.time(), level, action, message))

    def forget_root(self, root_id):
        with self.connect() as c:
            c.execute('DELETE FROM files WHERE root_id=?', (root_id,))

    def files(self, query='', category='', device='', theme='', limit=100, offset=0):
        where, args = ['1=1'], []
        for field, value in [('category', category), ('device', device)]:
            if value:
                where.append(f'{field}=?'); args.append(value)
        if query:
            where.append("(instr(lower(name),lower(?))>0 OR instr(lower(path),lower(?))>0)")
            args += [query, query]
        if theme:
            where.append('EXISTS (SELECT 1 FROM json_each(inventory.themes) WHERE value=?)')
            args.append(theme)
        sql = ' FROM inventory WHERE ' + ' AND '.join(where)
        with self.connect() as c:
            total = c.execute('SELECT count(*)' + sql, args).fetchone()[0]
            rows = c.execute('SELECT *' + sql + ' ORDER BY size DESC,id LIMIT ? OFFSET ?', args + [limit, offset]).fetchall()
        return {'total': total, 'items': [dict(r) | {'themes': json.loads(r['themes'])} for r in rows]}

    def duplicates(self, limit=100, offset=0):
        with self.connect() as c:
            hashes = c.execute('''SELECT sha256,size,count(*) AS copies FROM inventory
                WHERE sha256 IS NOT NULL AND status='ok' GROUP BY sha256,size HAVING count(*)>1
                ORDER BY size*(count(*)-1) DESC LIMIT ? OFFSET ?''', (limit, offset)).fetchall()
            groups = []
            for h in hashes:
                items = [dict(r) for r in c.execute('SELECT id,path,device,mtime,size,status FROM inventory WHERE sha256=? AND size=? AND status=\'ok\' ORDER BY mtime,id', (h['sha256'], h['size']))]
                groups.append(dict(h) | {'items': items, 'keep_id': items[0]['id'], 'recoverable': h['size'] * (h['copies'] - 1), 'similarity': 100})
            total = c.execute("SELECT count(*) FROM (SELECT 1 FROM inventory WHERE sha256 IS NOT NULL AND status='ok' GROUP BY sha256,size HAVING count(*)>1)").fetchone()[0]
        return {'total': total, 'items': groups}

    def stats(self):
        with self.connect() as c:
            count, size = c.execute('SELECT count(*),coalesce(sum(size),0) FROM inventory').fetchone()
            categories = [dict(r) for r in c.execute('SELECT category,count(*) AS count,sum(size) AS bytes FROM inventory GROUP BY category ORDER BY bytes DESC')]
            devices = [dict(r) for r in c.execute('SELECT device,count(*) AS count,sum(size) AS bytes FROM inventory GROUP BY device ORDER BY bytes DESC')]
            duplicate_groups, recoverable = c.execute("SELECT count(*),coalesce(sum(bytes),0) FROM (SELECT size*(count(*)-1) AS bytes FROM inventory WHERE sha256 IS NOT NULL AND status='ok' GROUP BY sha256,size HAVING count(*)>1)").fetchone()
            stale = c.execute("SELECT count(*) FROM inventory WHERE status!='ok'").fetchone()[0]
        return {'files': count, 'bytes': size, 'categories': categories, 'devices': devices,
                'duplicate_groups': duplicate_groups, 'potential_recoverable': recoverable, 'unverified_files': stale,
                'media_bytes': sum(x['bytes'] for x in categories if x['category'] in ('images', 'videos')),
                'largest': self.files(limit=8)['items']}

    def events(self, limit=100):
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,))]

    def notifications(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM events WHERE (level IN ('warning','error') OR action='transfer_completed') AND id NOT IN (SELECT event_id FROM notification_dismissals) ORDER BY id DESC LIMIT 100")]

    def dismiss_notification(self, event_id):
        if type(event_id) is not int:
            raise ValueError('Identifiant de notification invalide.')
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO notification_dismissals VALUES(?)',(event_id,))
