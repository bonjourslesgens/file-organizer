"""USB ADB connector: opt-in public media roots, read-only on the phone, direct streams."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid

from .archive import WARNING, destination_path, safe_name
from .safety import BLOCKED_NAMES, BLOCKED_SUFFIXES, SafetyError
from .scanner import detect_type

PUBLIC_ROOTS = ('/storage/emulated/0/DCIM','/storage/emulated/0/Pictures','/storage/emulated/0/Movies','/storage/emulated/0/Download')
SCHEMA='''CREATE TABLE IF NOT EXISTS android_files (
 id INTEGER PRIMARY KEY, serial TEXT, root_id TEXT, path TEXT, name TEXT, size INTEGER, mtime REAL,
 sha256 TEXT, category TEXT, mime TEXT, detected_by TEXT, status TEXT, seen TEXT,
 UNIQUE(serial,path));
 CREATE INDEX IF NOT EXISTS android_hash ON android_files(sha256,size);
'''


def validate_path(raw):
    p=PurePosixPath(raw)
    if not isinstance(raw,str) or not p.is_absolute() or '..' in p.parts or str(p)!=raw or not any(p==PurePosixPath(r) or PurePosixPath(r) in p.parents for r in PUBLIC_ROOTS):
        raise SafetyError('Android : seuls DCIM, Pictures, Movies et Download sont autorisables.')
    for part in p.parts[1:]:
        if part.casefold() in BLOCKED_NAMES or part.startswith('.'):
            raise SafetyError('Android : dossier applicatif, caché ou système exclu.')
    if any(re.fullmatch(r'(com|org|net)\.[A-Za-z0-9_.]+', part) for part in p.parts):
        raise SafetyError('Android : dossier de paquet applicatif exclu.')
    if p.suffix.lower() in BLOCKED_SUFFIXES:
        raise SafetyError('Android : fichier applicatif exclu.')
    return p


class ProcessStream:
    """Bounded pipe reader with a timeout; never stages a large transfer on the PC SSD."""
    def __init__(self, process, timeout=30, cancel_event=None):
        self.cancel_event=cancel_event
        self.process=process;self.timeout=timeout;self.q=queue.Queue(2);self.buffer=b'';self.eof=False
        self.stopped=threading.Event()
        self.thread=threading.Thread(target=self._pump,daemon=True);self.thread.start()

    def _pump(self):
        try:
            while not self.stopped.is_set():
                chunk=self.process.stdout.read(1024*1024)
                while not self.stopped.is_set():
                    try:self.q.put(chunk,timeout=.2);break
                    except queue.Full:pass
                if not chunk:break
        except OSError:
            try:self.q.put_nowait(b'')
            except queue.Full:pass

    def read(self,size):
        deadline=time.monotonic()+self.timeout
        while len(self.buffer)<size and not self.eof:
            if self.cancel_event and self.cancel_event.is_set():raise OSError('Android : lecture mise en pause.')
            try:chunk=self.q.get(timeout=.2)
            except queue.Empty:
                if time.monotonic()<deadline:continue
                raise OSError('Android : délai de lecture dépassé ; reprise manuelle nécessaire.')
            if not chunk:self.eof=True
            else:self.buffer+=chunk
        result,self.buffer=self.buffer[:size],self.buffer[size:]
        return result

    def close(self):
        self.stopped.set()
        if self.process.poll() is None:self.process.terminate()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        self.process.stdout.close();self.thread.join(timeout=2)


class Android:
    def __init__(self, config, db):
        self.config,self.db=config,db
        self.lock=threading.RLock();self.thread=None;self.stop=threading.Event()
        self.job={'status':'idle'}
        with db.connect() as c:
            c.executescript(SCHEMA)
            # Phone files must be rechecked after restarting the host.
            c.execute("UPDATE android_files SET status='unverified'")

    def adb(self):
        configured=self.config.snapshot().get('adb_path','')
        executable=configured or shutil.which('adb')
        if not executable or not Path(executable).is_file():
            raise SafetyError('ADB absent. Installez les Platform Tools officiels puis indiquez le chemin de adb.exe dans Appareils.')
        return str(executable)

    def _serial(self,serial):
        if not isinstance(serial,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',serial):
            raise SafetyError('Identifiant USB Android invalide ; ADB réseau n’est pas activé.')
        return serial

    def _run(self,args,timeout=30):
        try:
            p=subprocess.run([self.adb(),*args],capture_output=True,timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise OSError('ADB : délai dépassé, téléphone peut-être déconnecté.') from e
        if p.returncode:
            raise OSError('ADB : '+p.stderr.decode('utf-8','replace')[:250])
        return p.stdout

    def devices(self):
        output=self._run(['devices','-l']).decode('utf-8','replace')
        result=[]
        for line in output.splitlines()[1:]:
            fields=line.split()
            if len(fields)<2 or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',fields[0]):continue
            result.append({'serial':fields[0],'state':fields[1], 'model':next((f[6:] for f in fields if f.startswith('model:')),'Android')})
        return result

    def shell(self,serial,command):
        return self._run(['-s',self._serial(serial),'shell','-T',command]).decode('utf-8','strict').strip()

    def metadata(self,entry,path):
        p=validate_path(path);root=validate_path(entry['path'])
        if p==root or not p.is_relative_to(root):raise SafetyError('Android : fichier hors de la liste blanche.')
        from .safety import is_sensitive
        if is_sensitive(p.relative_to(root),self.config.snapshot().get('sensitive_patterns',[])):
            raise SafetyError('Android : fichier sensible exclu.')
        serial=self._serial(entry['serial'])
        canonical_root=self.shell(serial,'readlink -f '+shlex.quote(str(root)))
        canonical=self.shell(serial,'readlink -f '+shlex.quote(path))
        if canonical!=str(PurePosixPath(canonical_root)/p.relative_to(root)):
            raise SafetyError('Android : lien ou chemin redirigé exclu.')
        ancestors=[str(parent) for parent in p.parents if parent==root or root in parent.parents]
        command='for folder in '+' '.join(shlex.quote(a) for a in ancestors)+'; do for marker in .nomedia .git package.json pyproject.toml; do if [ -e "$folder/$marker" ]; then printf BLOCKED; exit; fi; done; done'
        if self.shell(serial,command)=='BLOCKED':
            raise SafetyError('Android : dossier privé, masqué ou de développement exclu.')
        # stat without -L refuses symlinks; regular files with a single link only.
        values=self.shell(serial,"stat -c '%s|%Y|%h|%F' "+shlex.quote(path)).split('|')
        if len(values)!=4 or values[2]!='1' or values[3] not in ('regular file','regular empty file'):
            raise SafetyError('Android : fichier lié ou non ordinaire exclu.')
        return {'size':int(values[0]),'mtime':float(values[1]),'canonical':canonical}

    def authorize(self,serial,path,label='Android'):
        self._serial(serial);validate_path(path)
        if not any(d['serial']==serial and d['state']=='device' for d in self.devices()):
            raise SafetyError('Téléphone absent, hors ligne ou non autorisé. Validez la clé USB sur le téléphone.')
        # Only read the selected folder; no mkdir, push, rm, settings or remount on Android.
        if self.shell(serial,'test -d '+shlex.quote(path)+' && printf OK')!='OK':
            raise SafetyError('Dossier Android inaccessible.')
        return self.config.add_android_root(serial,path,label)

    def validate_snapshot(self,snapshot):
        entry=snapshot.get('root',{})
        current=next((r for r in self.config.snapshot().get('android_roots',[]) if r['id']==entry.get('id') and r['serial']==entry.get('serial') and r['path']==entry.get('path')),None)
        if current is None:raise SafetyError('Autorisation Android retirée.')
        meta=self.metadata(current,snapshot['path'])
        if any(meta[k]!=snapshot[k] for k in ('size','mtime','canonical')):
            raise SafetyError('Android : fichier modifié depuis le plan.')

    @contextmanager
    def open_source(self,snapshot,cancel_event=None):
        self.validate_snapshot(snapshot)
        process=subprocess.Popen([self.adb(),'-s',snapshot['root']['serial'],'exec-out','cat '+shlex.quote(snapshot['path'])],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        stream=ProcessStream(process,cancel_event=cancel_event)
        try:
            yield stream
            if process.wait(timeout=10)!=0:raise OSError('Android : lecture interrompue.')
            self.validate_snapshot(snapshot)
            digest=self.shell(snapshot['root']['serial'],'sha256sum '+shlex.quote(snapshot['path'])).split()[0]
            if digest!=snapshot['sha256']:raise SafetyError('Android : source modifiée pendant le transfert.')
        finally:stream.close()

    def start_scan(self,root_id):
        with self.lock:
            if self.busy():raise ValueError('Analyse Android déjà en cours.')
            entry=next((r for r in self.config.snapshot().get('android_roots',[]) if r['id']==root_id),None)
            if not entry:raise ValueError('Dossier Android non autorisé.')
            self.stop.clear();self.job={'id':uuid.uuid4().hex,'status':'running','files':0,'errors':0,'current':''}
            self.thread=threading.Thread(target=self._scan,args=(entry,),daemon=True);self.thread.start()
            return dict(self.job)

    def busy(self):return self.thread is not None and self.thread.is_alive()

    def _scan(self,entry):
        seen=self.job['id']
        with self.db.connect() as c:c.execute("UPDATE android_files SET status='unverified' WHERE root_id=?",(entry['id'],))
        try:
            validate_path(entry['path'])
            command='find '+shlex.quote(entry['path'])+r" \( -name '.*' -o -name Android -o -name node_modules -o -name 'com.*' -o -name 'org.*' -o -name 'net.*' \) -prune -o -type f -print0"
            # Directory names are filtered again before any per-file reads.
            output=self._run(['-s',entry['serial'],'shell','-T',command],timeout=120)
            for raw in output.split(b'\0'):
                if not raw:continue
                if self.stop.is_set():self.job['status']='cancelled';return
                path=raw.decode('utf-8','strict');self.job['current']=path
                try:
                    validate_path(path)
                    meta=self.metadata(entry,path)
                    header=self._run(['-s',entry['serial'],'exec-out','head -c 8192 '+shlex.quote(path)])
                    category,mime,detected=detect_type(header,Path(path))
                    # Only media are inventoried by this connector, even in Download.
                    if category not in ('images','videos','audio') or detected!='signature':continue
                    digest=self.shell(entry['serial'],'sha256sum '+shlex.quote(path)).split()[0]
                    if not re.fullmatch('[0-9a-f]{64}',digest) or self.metadata(entry,path)!=meta:
                        raise SafetyError('Android : fichier instable ou empreinte indisponible.')
                    with self.db.connect() as c:
                        c.execute('''INSERT INTO android_files(serial,root_id,path,name,size,mtime,sha256,category,mime,detected_by,status,seen)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(serial,path) DO UPDATE SET
                           root_id=excluded.root_id,size=excluded.size,mtime=excluded.mtime,sha256=excluded.sha256,
                           category=excluded.category,mime=excluded.mime,detected_by=excluded.detected_by,status=excluded.status,seen=excluded.seen''',
                           (entry['serial'],entry['id'],path,PurePosixPath(path).name,meta['size'],meta['mtime'],digest,category,mime,detected,'ok',seen))
                    self.job['files']+=1
                except SafetyError as e:
                    self.db.event('android_excluded',f'{path} : {e}','warning')
            with self.db.connect() as c:c.execute('DELETE FROM android_files WHERE root_id=? AND seen!=?',(entry['id'],seen))
            self.job['status']='completed'
            self.db.event('android_scan_completed',f"{self.job['files']} médias Android inventoriés.")
        except (OSError,ValueError,subprocess.SubprocessError,IndexError) as e:
            self.job.update(status='blocked',message=str(e));self.job['errors']+=1
            self.db.event('android_error',str(e),'warning')
        finally:self.job['current']=''

    def files(self,root_id='',limit=100,offset=0):
        with self.db.connect() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM android_files WHERE (?=\'\' OR root_id=?) ORDER BY size DESC,id LIMIT ? OFFSET ?',(root_id,root_id,limit,offset))]
            total=c.execute('SELECT count(*) FROM android_files WHERE (?=\'\' OR root_id=?)',(root_id,root_id)).fetchone()[0]
        return {'items':rows,'total':total}

    def simulate(self,root_id,destination):
        base=destination_path(destination);cfg=self.config.snapshot()
        entry=next((r for r in cfg.get('android_roots',[]) if r['id']==root_id),None)
        if not entry:raise ValueError('Dossier Android non autorisé.')
        if not any(d['serial']==entry['serial'] and d['state']=='device' for d in self.devices()):
            raise SafetyError('Téléphone Android non disponible.')
        plan_id=uuid.uuid4().hex;count=total=0;now=time.time()
        with self.db.connect() as c:
            for row in c.execute("SELECT * FROM android_files WHERE root_id=? AND status='ok' ORDER BY id",(root_id,)).fetchall():
                rule=next((r for r in cfg['archive_rules'] if r['enabled'] and r['category']==row['category'] and now-row['mtime']>=r['older_than_days']*86400),None)
                if not rule:continue
                meta=self.metadata(entry,row['path'])
                snapshot=dict(row)|meta|{'root':entry,'kind':'android'}
                if (meta['size'],meta['mtime'])!=(row['size'],row['mtime']):continue
                date=datetime.fromtimestamp(row['mtime'],timezone.utc)
                target=base/safe_name(entry['label'])/row['category']/f'{date.year:04}'/f'{date.month:02}'/(str(row['id'])+'_'+safe_name(row['name']))
                c.execute('INSERT INTO plan_items VALUES(?,?,?,?,?,?,?,?,?)',(plan_id,-row['id'],row['path'],str(target),row['size'],row['sha256'],rule['name'],WARNING,json.dumps(snapshot)))
                count+=1;total+=row['size']
            c.execute('INSERT INTO plans VALUES(?,?,?,?,?)',(plan_id,now,str(base),count,total))
        self.db.event('android_simulated',f'{count} médias Android proposés ; aucun transfert.')
        return {'id':plan_id,'count':count,'bytes':total,'mode':'simulation','destination_verified':False}

    def source_present(self,snapshot):
        """Read-only per-file check; never treats a transport/permission failure as deletion."""
        entry=snapshot['root'];path=validate_path(snapshot['path']);root=validate_path(entry['path'])
        current=next((r for r in self.config.snapshot()['android_roots'] if r['id']==entry['id'] and r['serial']==entry['serial'] and r['path']==entry['path']),None)
        if not current or not current.get('cleanup_allowed'):
            raise SafetyError('Autorisation de nettoyage Android absente.')
        canonical_root=self.shell(entry['serial'],'readlink -f '+shlex.quote(str(root)))
        actual_parent=self.shell(entry['serial'],'readlink -f '+shlex.quote(str(path.parent)))
        if actual_parent!=str(PurePosixPath(canonical_root)/path.parent.relative_to(root)):
            raise SafetyError('Android : parent absent ou redirigé ; retrait impossible à confirmer.')
        quoted=shlex.quote(str(path));parent=shlex.quote(str(path.parent))
        answer=self.shell(entry['serial'],f'if [ -e {quoted} ] || [ -L {quoted} ]; then printf PRESENT; elif [ -r {parent} ] && [ -x {parent} ]; then printf ABSENT; else printf INACCESSIBLE; fi')
        if answer not in ('PRESENT','ABSENT'):raise SafetyError('Android : état du fichier inaccessible ou ambigu.')
        return answer=='PRESENT'
