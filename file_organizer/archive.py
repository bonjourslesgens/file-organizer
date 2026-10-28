"""Pure planning. No destination writes: real copies require a separate approval."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path, PureWindowsPath
import re
import time
import uuid

from .safety import BLOCKED_NAMES, SafetyError, validate_file


WARNING = 'Lors de la simulation : aucune écriture, destination non contrôlée. Chaque copie nécessite un diagnostic et une validation distincts.'


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:160]
    if value.rstrip(' .').casefold() in BLOCKED_NAMES:
        value = '_' + value
    if not value or value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        value = '_' + (value or 'sans-nom')
    return value


def destination_path(raw):
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 1000:
        raise ValueError('Indiquez un dossier de destination absolu pour la simulation.')
    path = PureWindowsPath(raw) if re.match(r'^[A-Za-z]:[\\/]', raw) else Path(raw)
    if not path.is_absolute() or '..' in path.parts or str(path).startswith(('\\\\', '//')):
        raise ValueError('Destination absolue locale requise, sans « .. » ni chemin réseau.')
    if any(p.rstrip(' .').casefold() in BLOCKED_NAMES for p in path.parts[1:]):
        raise SafetyError('Une destination système ou applicative est interdite, même en simulation.')
    return path


class Planner:
    def __init__(self, config, db):
        self.config, self.db = config, db

    def simulate(self, raw_destination, now=None):
        destination = destination_path(raw_destination)
        cfg = self.config.snapshot()
        roots = {r['id']: r for r in cfg['roots']}
        now = now if now is not None else time.time()
        plan_id = uuid.uuid4().hex
        total, total_bytes, skipped = 0, 0, 0
        names = set()
        with self.db.connect() as c:
            # Fetch batches; plans are persisted and paginated rather than returned in one huge response.
            cursor = c.execute("SELECT * FROM files WHERE status='ok' ORDER BY id")
            while rows := cursor.fetchmany(250):
                for row in rows:
                    rule = next((r for r in cfg['archive_rules'] if r['enabled'] and r['category'] == row['category'] and now - row['mtime'] >= r['older_than_days'] * 86400), None)
                    if not rule:
                        continue
                    entry = roots.get(row['root_id'])
                    if not entry:
                        skipped += 1
                        continue
                    try:
                        from .safety import is_sensitive
                        if is_sensitive(Path(row['path']).relative_to(Path(entry['path'])),cfg.get('sensitive_patterns',[])):
                            raise SafetyError('Fichier sensible exclu.')
                        st = validate_file(Path(entry['path']), Path(row['path']))
                        if (st.st_size, st.st_mtime_ns, st.st_ctime_ns, str(st.st_ino), str(st.st_dev)) != (row['size'], row['mtime_ns'], row['ctime_ns'], row['inode'], row['device_id']):
                            skipped += 1
                            continue
                    except (OSError, ValueError):
                        skipped += 1
                        continue
                    # Use mtime explicitly; capture dates/EXIF are not claimed in phase 1.
                    date = datetime.fromtimestamp(row['mtime'], timezone.utc)
                    category = 'DJI' if row['category'] == 'videos' and row['name'].upper().startswith('DJI') else row['category']
                    base = destination / safe_name(entry['device']) / safe_name(entry['label']) / category / f'{date.year:04}' / f'{date.month:02}'
                    name = safe_name(row['name'])
                    target = base / name
                    index = 1
                    while str(target).casefold() in names:
                        stem = Path(name).stem[:120]
                        target = base / f'{stem}__{row["id"]}_{index}{Path(name).suffix}'
                        index += 1
                    names.add(str(target).casefold())
                    warn = WARNING
                    if not row['detected_by'].startswith('signature'):
                        warn += ' Type réel non confirmé : contrôle manuel requis.'
                    c.execute('INSERT INTO plan_items(plan_id,file_id,source,destination,size,sha256,reason,warning,snapshot) VALUES(?,?,?,?,?,?,?,?,?)',
                              (plan_id, row['id'], row['path'], str(target), row['size'], row['sha256'], rule['name'], warn, json.dumps(dict(row) | {'root':entry, 'kind':'local'}, ensure_ascii=False)))
                    total += 1
                    total_bytes += row['size']
            c.execute('INSERT INTO plans VALUES(?,?,?,?,?)', (plan_id, now, str(destination), total, total_bytes))
        self.db.event('archive_simulated', f'{total} fichiers proposés, {total_bytes} octets ; {skipped} fichiers périmés ou exclus. Aucune copie.')
        return {'id': plan_id, 'count': total, 'bytes': total_bytes, 'skipped': skipped, 'warning': WARNING,
                'mode': 'simulation', 'destination_verified': False, 'items': self.items(plan_id)['items']}

    def items(self, plan_id, limit=100, offset=0):
        with self.db.connect() as c:
            plan = c.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
            if not plan:
                raise ValueError('Simulation introuvable.')
            rows = c.execute('SELECT * FROM plan_items WHERE plan_id=? ORDER BY file_id LIMIT ? OFFSET ?', (plan_id, limit, offset)).fetchall()
        return dict(plan) | {'items': [dict(r) for r in rows]}
