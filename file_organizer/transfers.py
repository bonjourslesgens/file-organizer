"""Explicitly approved, resumable, SHA-256 verified copies. Never deletes sources."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from .archive import destination_path
from .destination import directory, set_timestamp
from .safety import SafetyError, open_personal, validate_root
from .storage import Storage

SCHEMA = '''
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, created REAL, plan_id TEXT, data TEXT, used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS transfer_jobs(id TEXT PRIMARY KEY, created REAL, updated REAL, status TEXT, destination TEXT, volume TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS transfer_items(job_id TEXT, file_id INTEGER, source TEXT, destination TEXT,
 snapshot TEXT, size INTEGER, sha256 TEXT, status TEXT DEFAULT 'pending', bytes_done INTEGER DEFAULT 0,
 partial TEXT, partial_inode TEXT, message TEXT DEFAULT '', PRIMARY KEY(job_id,file_id));
'''
ACTIVE = ('running', 'pausing')
FINISHED = ('verified', 'already_present')


class Paused(Exception):
    pass


class Transfers:
    def __init__(self, config, db, storage=None, android=None):
        self.config,self.db = config,db
        self.storage = storage or Storage(config.state_dir)
        self.android = android
        self.lock=threading.RLock()
        self.stop_event=threading.Event()
        self.thread=None
        with db.connect() as c:
            c.executescript(SCHEMA)
            c.execute("UPDATE transfer_jobs SET status='interrupted',message='Interruption : reprise manuelle requise.' WHERE status IN ('running','pausing')")

    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def prepare(self, plan_id, file_ids=None, all_files=False):
        with self.db.connect() as c:
            plan=c.execute('SELECT * FROM plans WHERE id=?',(plan_id,)).fetchone()
            if not plan:
                raise ValueError('Simulation introuvable.')
            base=Path(destination_path(plan['destination']))
            if not base.is_absolute():
                raise SafetyError('Destination étrangère au système local.')
            base=validate_root(str(base),self.config.state_dir)
            if type(all_files) is not bool:
                raise ValueError('Sélection invalide.')
            if all_files:
                selected=[r[0] for r in c.execute('SELECT file_id FROM plan_items WHERE plan_id=?',(plan_id,))]
            else:
                if not isinstance(file_ids,list) or not file_ids or len(file_ids)>2000 or any(type(i) is not int for i in file_ids):
                    raise ValueError('Sélectionnez des fichiers (2 000 maximum, ou « tout le plan »).')
                selected=sorted(set(file_ids))
            rows=c.execute('SELECT * FROM plan_items WHERE plan_id=?',(plan_id,)).fetchall()
            selected_set=set(selected)
            items=[dict(r) for r in rows if r['file_id'] in selected_set]
        if not items or len(items)!=len(selected_set):
            raise ValueError('Sélection vide ou fichiers absents du plan.')
        for item in items:
            snapshot=json.loads(item['snapshot'])
            self.validate_snapshot(snapshot,base)
            target=Path(item['destination'])
            if not target.is_relative_to(base) or target==base or '..' in target.parts:
                raise SafetyError('Destination de fichier hors du dossier approuvé.')
        total=sum(i['size'] for i in items)
        info=self.storage.require(str(base),required_bytes=total)
        if info['filesystem'] in ('fat32','vfat') and any(i['size']>4294967295 for i in items):
            raise SafetyError('FAT32 ne permet pas les fichiers de plus de 4 Gio. Choisissez un volume NTFS ou exFAT sans formater vos données.')
        approval=uuid.uuid4().hex
        payload={'selected':selected,'identity':info['identity'],'count':len(items),'bytes':total,'destination':str(base)}
        with self.db.connect() as c:
            c.execute('INSERT INTO approvals(id,created,plan_id,data) VALUES(?,?,?,?)',(approval,time.time(),plan_id,json.dumps(payload)))
        return payload | {'approval_id':approval,'expires_in':900,'diagnostic':info,'confirmation':'COPIER',
                          'notice':'Copies uniquement ; les originaux seront conservés. La destination n’a pas encore été modifiée.'}

    def start(self, approval_id, confirmation):
        with self.lock:
            if self.busy():
                raise ValueError('Un transfert est déjà en cours.')
            if confirmation!='COPIER':
                raise SafetyError('Saisissez COPIER pour valider ce transfert précis.')
            with self.db.connect() as c:
                row=c.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
                if not row or row['used'] or time.time()-row['created']>900:
                    raise SafetyError('Validation expirée ou déjà utilisée. Préparez à nouveau la sélection.')
                data=json.loads(row['data'])
                info=self.storage.require(data['destination'],expected=data['identity'],required_bytes=data['bytes'])
                job_id=uuid.uuid4().hex
                selected=set(data['selected'])
                items=[r for r in c.execute('SELECT * FROM plan_items WHERE plan_id=?',(row['plan_id'],)) if r['file_id'] in selected]
                for item in items:
                    self.validate_snapshot(json.loads(item['snapshot']),Path(data['destination']))
                c.execute('UPDATE approvals SET used=1 WHERE id=?',(approval_id,))
                c.execute('INSERT INTO transfer_jobs VALUES(?,?,?,?,?,?,?)',(job_id,time.time(),time.time(),'running',data['destination'],json.dumps(info),'Copie validée explicitement.'))
                c.executemany('INSERT INTO transfer_items(job_id,file_id,source,destination,snapshot,size,sha256) VALUES(?,?,?,?,?,?,?)',
                              [(job_id,i['file_id'],i['source'],i['destination'],i['snapshot'],i['size'],i['sha256']) for i in items])
            self._launch(job_id)
            self.db.event('transfer_approved',f'Transfert {job_id} : {len(items)} copies validées, originaux conservés.')
            return self.get(job_id)

    def resume(self, job_id, confirmation):
        with self.lock:
            if confirmation!='REPRENDRE':
                raise SafetyError('Saisissez REPRENDRE pour autoriser la reprise.')
            if self.busy():
                raise ValueError('Un transfert est déjà en cours.')
            job=self.get(job_id)
            if job['status']=='completed':
                raise ValueError('Ce transfert est déjà terminé.')
            with self.db.connect() as c:
                volume=json.loads(c.execute('SELECT volume FROM transfer_jobs WHERE id=?',(job_id,)).fetchone()[0])
                remaining=c.execute("SELECT coalesce(sum(size-bytes_done),0) FROM transfer_items WHERE job_id=? AND status NOT IN ('verified','already_present')",(job_id,)).fetchone()[0]
                info=self.storage.require(job['destination'],expected=volume['identity'],required_bytes=max(remaining,0))
                c.execute("UPDATE transfer_jobs SET status='running',volume=?,updated=?,message='Reprise validée.' WHERE id=?",(json.dumps(info),time.time(),job_id))
            self._launch(job_id)
            return self.get(job_id)

    def _launch(self, job_id):
        self.stop_event.clear()
        self.thread=threading.Thread(target=self._run,args=(job_id,),daemon=True)
        self.thread.start()

    def pause(self):
        self.stop_event.set()

    def wait(self, timeout=30):
        if self.thread:self.thread.join(timeout)

    def _check(self):
        if self.stop_event.is_set():raise Paused('Transfert mis en pause. Les originaux restent intacts.')

    def _update(self, job_id, file_id, **values):
        with self.db.connect() as c:
            c.execute('UPDATE transfer_items SET '+','.join(k+'=?' for k in values)+' WHERE job_id=? AND file_id=?',(*values.values(),job_id,file_id))
            c.execute('UPDATE transfer_jobs SET updated=? WHERE id=?',(time.time(),job_id))

    def validate_snapshot(self, snapshot, base):
        if snapshot.get('kind')=='android':
            if not self.android:raise SafetyError('Connecteur Android indisponible.')
            self.android.validate_snapshot(snapshot)
            return
        if snapshot.get('kind')!='local' or not snapshot.get('root') or not snapshot.get('sha256'):
            raise SafetyError('Ancien plan sans identité des sources. Refaites une simulation.')
        root=snapshot['root']
        current=next((r for r in self.config.snapshot()['roots'] if r['id']==root['id'] and r['path']==root['path']),None)
        if current is None:
            raise SafetyError('Dossier source retiré de la liste blanche.')
        source_root=validate_root(root['path'],self.config.state_dir)
        from .safety import is_sensitive
        if is_sensitive(Path(snapshot['path']).relative_to(source_root),self.config.snapshot().get('sensitive_patterns',[])):
            raise SafetyError('Source sensible exclue par les règles actuelles.')
        if source_root==base or source_root in base.parents or base in source_root.parents:
            raise SafetyError('Source et destination ne doivent pas se chevaucher.')
        from .safety import validate_file
        st=validate_file(source_root,Path(snapshot['path']))
        expected=(snapshot['size'],snapshot['mtime_ns'],snapshot['ctime_ns'],snapshot['inode'],snapshot['device_id'])
        if (st.st_size,st.st_mtime_ns,st.st_ctime_ns,str(st.st_ino),str(st.st_dev))!=expected:
            raise SafetyError('Source modifiée depuis la simulation. Refaites l’analyse et le plan.')

    @contextmanager
    def reader(self,snapshot,base):
        self.validate_snapshot(snapshot,base)
        if snapshot['kind']=='android':
            with self.android.open_source(snapshot,cancel_event=self.stop_event) as f:yield f
        else:
            with open_personal(Path(snapshot['root']['path']),Path(snapshot['path'])) as (f,_):yield f

    def _digest(self, f, guard=None):
        h=hashlib.sha256()
        while True:
            self._check()
            if guard:guard()
            chunk=f.read(1024*1024)
            if not chunk:break
            h.update(chunk)
        return h.hexdigest()

    def _copy(self, job, item, info):
        base=Path(job['destination']);snapshot=json.loads(item['snapshot'])
        self.validate_snapshot(snapshot,base)
        self.storage.guard(base,info)
        target=Path(item['destination'])
        relative=target.relative_to(base)
        partial=item['partial'] or f'.fileorganizer-{job["id"]}-{item["file_id"]}.partial'
        last_check=0
        def guard():
            nonlocal last_check
            if time.monotonic()-last_check>1:
                self.storage.guard(base,info);last_check=time.monotonic()
        with directory(base,relative.parent) as folder:
            try:
                out=folder.open(partial,new=True,writable=True)
                inode=str(os.fstat(out.fileno()).st_ino)
                self._update(job['id'],item['file_id'],partial=partial,partial_inode=inode,status='copying',bytes_done=0)
            except FileExistsError:
                if not item['partial_inode']:
                    raise SafetyError('Fichier temporaire sans identité enregistrée. Il ne sera pas écrasé.')
                out=folder.open(partial,writable=True)
                inode=str(os.fstat(out.fileno()).st_ino)
                if inode!=item['partial_inode']:
                    out.close();raise SafetyError('Copie temporaire remplacée. Reprise refusée.')
            with out:
                offset=os.fstat(out.fileno()).st_size
                if offset>item['size']:
                    raise SafetyError('Copie temporaire trop longue ; aucune troncature automatique.')
                h=hashlib.sha256()
                # Re-read the source and compare *every* persisted prefix byte on resume.
                with self.reader(snapshot,base) as src:
                    remaining=offset
                    while remaining:
                        self._check();guard()
                        count=min(1024*1024,remaining)
                        chunk=src.read(count)
                        if len(chunk)!=count or out.read(count)!=chunk:
                            raise SafetyError('Préfixe de reprise différent de la source. Copie bloquée.')
                        h.update(chunk);remaining-=count
                    done=offset
                    while True:
                        self._check();guard()
                        chunk=src.read(1024*1024)
                        if not chunk:break
                        if done+len(chunk)>item['size']:
                            raise SafetyError('Source agrandie pendant la copie.')
                        out.write(chunk);h.update(chunk);done+=len(chunk)
                        out.flush();os.fsync(out.fileno())
                        self._update(job['id'],item['file_id'],status='copying',bytes_done=done)
                    if done!=item['size'] or h.hexdigest()!=item['sha256']:
                        raise SafetyError('SHA-256 source différent du plan ; aucune publication.')
                # Context exit checks source identity *before* any final destination publication.
                out.flush();os.fsync(out.fileno());out.seek(0)
                if self._digest(out,guard)!=h.hexdigest():
                    raise SafetyError('SHA-256 de la copie partielle incorrect.')
                # Preserve relevant time metadata on our copy only; never modify the source.
                timestamp=snapshot['mtime']
                set_timestamp(out,timestamp)
            self._check();self.storage.guard(base,info)
            final=target.name
            status='verified'
            for attempt in range(1000):
                try:
                    folder.publish(partial,final)
                    break
                except FileExistsError:
                    try:
                        with folder.open(final) as existing:
                            same=os.fstat(existing.fileno()).st_size==item['size'] and self._digest(existing,guard)==item['sha256']
                        if same:
                            folder.remove_partial(partial,inode)
                            status='already_present';break
                    except (OSError,SafetyError):
                        pass
                    final=f'{target.stem[:100]}__copie{attempt+1}{target.suffix}'
            else:
                raise SafetyError('Trop de collisions : aucun fichier existant remplacé.')
            self.storage.guard(base,info)
            with folder.open(final) as verified:
                if self._digest(verified,guard)!=item['sha256']:
                    raise SafetyError('Contrôle final échoué. Original conservé, destination à examiner.')
            self._update(job['id'],item['file_id'],status=status,bytes_done=item['size'],destination=str(folder.path/final),message='SHA-256 vérifié. Original conservé.')
            self.db.event('copy_verified',f'{item["source"]} → {folder.path/final} : {status}, SHA-256 vérifié.')

    def _run(self, job_id):
        status,message='completed','Toutes les copies sont vérifiées ; originaux conservés.'
        try:
            with self.db.connect() as c:
                job=dict(c.execute('SELECT * FROM transfer_jobs WHERE id=?',(job_id,)).fetchone())
                items=[dict(r) for r in c.execute("SELECT * FROM transfer_items WHERE job_id=? AND status NOT IN ('verified','already_present') ORDER BY file_id",(job_id,))]
            info=json.loads(job['volume'])
            self.storage.require(job['destination'],expected=info['identity'])
            for item in items:
                self._check()
                try:
                    self._copy(job,item,info)
                except BaseException as e:
                    self._update(job_id,item['file_id'],status='paused' if isinstance(e,Paused) else 'error',message=str(e))
                    raise
        except Paused as e:
            status,message='paused',str(e)
        except Exception as e:
            status,message=('paused' if self.stop_event.is_set() else 'blocked'),str(e)
        finally:
            with self.db.connect() as c:
                c.execute('UPDATE transfer_jobs SET status=?,message=?,updated=? WHERE id=?',(status,message,time.time(),job_id))
            self.db.event('transfer_'+status,f'{job_id} : {message}','info' if status=='completed' else 'warning')

    def get(self, job_id, limit=100, offset=0):
        with self.db.connect() as c:
            row=c.execute('SELECT id,created,updated,status,destination,message FROM transfer_jobs WHERE id=?',(job_id,)).fetchone()
            if not row:raise ValueError('Transfert introuvable.')
            stats=dict(c.execute("SELECT count(*) AS count,coalesce(sum(size),0) AS bytes,coalesce(sum(bytes_done),0) AS bytes_done,coalesce(sum(status IN ('verified','already_present')),0) AS verified FROM transfer_items WHERE job_id=?",(job_id,)).fetchone())
            items=[dict(r) for r in c.execute('SELECT file_id,source,destination,size,status,bytes_done,message FROM transfer_items WHERE job_id=? ORDER BY file_id LIMIT ? OFFSET ?',(job_id,limit,offset))]
        return dict(row)|stats|{'items':items,'mode':'copy','originals_preserved':True}

    def list(self):
        with self.db.connect() as c:
            ids=[r[0] for r in c.execute('SELECT id FROM transfer_jobs ORDER BY created DESC LIMIT 20')]
        return [self.get(i,limit=0) for i in ids]
