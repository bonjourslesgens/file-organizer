"""Freshly verified cleanup proposals and explicitly authorized recycling; no permanent-delete primitive."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from .destination import directory
from .safety import SafetyError, identity, validate_root, check_components, file_stat
from .win_recycle import WindowsRecycleBin

WARNING='Après retrait, il ne restera qu’un exemplaire connu hors Corbeille, à la destination. Conservez une sauvegarde indépendante des fichiers irremplaçables.'
SCHEMA='''CREATE TABLE IF NOT EXISTS cleanup_reviews(id TEXT PRIMARY KEY,created REAL,transfer_id TEXT,selection TEXT,used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS cleanup_jobs(id TEXT PRIMARY KEY,created REAL,status TEXT,message TEXT);
CREATE TABLE IF NOT EXISTS cleanup_actions(id INTEGER PRIMARY KEY,cleanup_job_id TEXT,transfer_job_id TEXT,file_id INTEGER,
 source TEXT,destination TEXT,snapshot TEXT,method TEXT,status TEXT,receipt TEXT,message TEXT,
 UNIQUE(cleanup_job_id,file_id));'''


class Cleanup:
    def __init__(self,config,db,transfers,recycler=None):
        self.config,self.db,self.transfers=config,db,transfers
        self.recycler=recycler or WindowsRecycleBin()
        self.thread=None;self.lock=threading.RLock();self.stop=threading.Event()
        with db.connect() as c:
            c.executescript(SCHEMA)
            c.execute("UPDATE cleanup_jobs SET status='interrupted',message='Interruption : contrôler le journal et la Corbeille avant toute nouvelle proposition.' WHERE status='running'")
            c.execute("UPDATE cleanup_actions SET status='uncertain',message='Interruption pendant le nettoyage : vérification manuelle requise.' WHERE status='running'")

    def busy(self):return self.thread is not None and self.thread.is_alive()

    def _items(self,transfer_id):
        with self.db.connect() as c:
            job=c.execute('SELECT * FROM transfer_jobs WHERE id=?',(transfer_id,)).fetchone()
            if not job:raise ValueError('Transfert introuvable.')
            items=[dict(r) for r in c.execute('SELECT * FROM transfer_items WHERE job_id=? ORDER BY file_id',(transfer_id,))]
        return dict(job),items

    def _opt_in(self,item,source_expected=True):
        if item['status'] not in ('verified','already_present'):
            raise SafetyError('Copie non vérifiée ou incomplète.')
        snapshot=json.loads(item['snapshot']);kind=snapshot.get('kind')
        root=snapshot.get('root',{})
        roots=self.config.snapshot()['android_roots' if kind=='android' else 'roots']
        current=next((r for r in roots if r['id']==root.get('id') and r['path']==root.get('path')),None)
        if not current or current.get('cleanup_allowed',False) is not True:
            raise SafetyError('Le dossier n’est pas déclaré personnel et autonome pour le nettoyage.')
        if snapshot.get('detected_by')!='signature' or snapshot.get('category') not in ('images','videos','audio','documents'):
            raise SafetyError('Type ambigu ou estimé par extension : retrait exclu.')
        if source_expected and kind=='local' and os.name=='nt' and getattr(file_stat(path=snapshot['path']),'st_file_attributes',0)&1:
            raise SafetyError('Source protégée en lecture seule : retrait exclu.')
        if snapshot['category']=='documents' and snapshot.get('mime')!='application/pdf':
            raise SafetyError('Seuls les documents PDF reconnus sont proposés au nettoyage.')
        return snapshot

    def _digest(self,stream):
        h=hashlib.sha256()
        while chunk:=stream.read(1024*1024):
            if self.stop.is_set():raise SafetyError('Nettoyage interrompu avant l’action suivante.')
            h.update(chunk)
        return h.hexdigest()

    @contextmanager
    def archive(self,job,item):
        base=validate_root(job['destination'],self.config.state_dir)
        expected=json.loads(job['volume'])
        info=self.transfers.storage.diagnose(str(base))
        if not info['safe_to_write'] or info.get('identity')!=expected['identity']:
            raise SafetyError('Destination inaccessible, suspecte ou remplacée ; nettoyage bloqué.')
        path=Path(item['destination'])
        if not path.is_relative_to(base) or path==base:raise SafetyError('Archive hors de la destination validée.')
        with directory(base,path.relative_to(base).parent,create=False) as folder:
            with folder.open(path.name) as stream:
                before=identity(os.fstat(stream.fileno()))
                def guard():
                    self.transfers.storage.guard(base,info)
                    if identity(os.fstat(stream.fileno()))!=before:raise SafetyError('Archive modifiée pendant la vérification.')
                guard()
                if os.fstat(stream.fileno()).st_size!=item['size'] or self._digest(stream)!=item['sha256']:
                    raise SafetyError('SHA-256 de l’archive différent : aucune suppression proposée.')
                guard()
                yield guard
                guard()

    @contextmanager
    def verified(self,job,item):
        snapshot=self._opt_in(item)
        with self.archive(job,item) as guard:
            with self.transfers.reader(snapshot,Path(job['destination'])) as source:
                if self._digest(source)!=item['sha256']:raise SafetyError('Source différente de la copie archivée.')
            guard()
            yield snapshot,guard

    def candidates(self,transfer_id):
        job,items=self._items(transfer_id)
        eligible=[];excluded=[]
        self.stop.clear()
        for item in items:
            try:
                with self.verified(job,item) as (snapshot,guard):pass
                method='manual_android' if snapshot['kind']=='android' else ('windows_recycle_bin' if self.recycler.available() and (not hasattr(self.recycler,'can_recycle') or self.recycler.can_recycle(snapshot)) else 'manual_local')
                eligible.append({'file_id':item['file_id'],'source':item['source'],'destination':item['destination'],'size':item['size'],'method':method,'sha256':item['sha256']})
            except (OSError,ValueError) as e:
                excluded.append({'file_id':item['file_id'],'source':item['source'],'reason':str(e)})
        return {'transfer_id':transfer_id,'items':eligible,'excluded':excluded,'bytes':sum(r['size'] for r in eligible),'warning':WARNING,
                'notice':'Propositions seulement. La Corbeille libère l’espace après son vidage manuel dans Windows.'}

    def prepare(self,transfer_id,file_ids):
        if not isinstance(file_ids,list) or not file_ids or len(file_ids)>1000 or any(type(v) is not int for v in file_ids):
            raise ValueError('Sélectionnez de 1 à 1 000 fichiers pour un nettoyage contrôlé.')
        report=self.candidates(transfer_id);selected=set(file_ids)
        items=[i for i in report['items'] if i['file_id'] in selected]
        if len(items)!=len(selected):raise SafetyError('La sélection contient des fichiers exclus ou devenus incertains. Actualisez les propositions.')
        review=uuid.uuid4().hex
        with self.db.connect() as c:c.execute('INSERT INTO cleanup_reviews(id,created,transfer_id,selection) VALUES(?,?,?,?)',(review,time.time(),transfer_id,json.dumps(items)))
        self.db.event('cleanup_prepared',f'{len(items)} fichiers revérifiés ; aucune action sur les sources.')
        return {'review_id':review,'items':items,'bytes':sum(i['size'] for i in items),'warning':WARNING,'confirmation':'NETTOYER','expires_in':300}

    def start(self,review_id,confirmation,acknowledge_single_copy):
        with self.lock:
            if self.busy():raise ValueError('Un nettoyage est déjà en cours.')
            if confirmation!='NETTOYER' or acknowledge_single_copy is not True:
                raise SafetyError('Saisissez NETTOYER et reconnaissez le risque de copie unique.')
            with self.db.connect() as c:
                review=c.execute('SELECT * FROM cleanup_reviews WHERE id=?',(review_id,)).fetchone()
                if not review or review['used'] or time.time()-review['created']>300:raise SafetyError('Validation expirée ou déjà utilisée. Revérifiez les fichiers.')
                job,all_items=self._items(review['transfer_id']);selected=json.loads(review['selection'])
                indexed={i['file_id']:i for i in all_items}
                for chosen in selected:
                    item=indexed[chosen['file_id']]
                    with self.verified(job,item) as verified:pass
                cleanup_id=uuid.uuid4().hex
                c.execute('UPDATE cleanup_reviews SET used=1 WHERE id=?',(review_id,))
                c.execute('INSERT INTO cleanup_jobs VALUES(?,?,?,?)',(cleanup_id,time.time(),'running','Validation explicite enregistrée.'))
                for chosen in selected:
                    item=indexed[chosen['file_id']]
                    c.execute('INSERT INTO cleanup_actions(cleanup_job_id,transfer_job_id,file_id,source,destination,snapshot,method,status,receipt,message) VALUES(?,?,?,?,?,?,?,?,?,?)',
                              (cleanup_id,job['id'],item['file_id'],item['source'],item['destination'],item['snapshot'],chosen['method'],'pending','{}',''))
            self.stop.clear();self.thread=threading.Thread(target=self._run,args=(cleanup_id,),daemon=True);self.thread.start()
            return self.get(cleanup_id)

    def _mark(self,action_id,status,message,receipt=None):
        with self.db.connect() as c:
            c.execute('UPDATE cleanup_actions SET status=?,message=?,receipt=? WHERE id=?',(status,message,json.dumps(receipt or {}),action_id))

    def _forget(self,item,snapshot):
        with self.db.connect() as c:
            if snapshot['kind']=='android':c.execute('DELETE FROM android_files WHERE id=?',(-item['file_id'],))
            else:c.execute('DELETE FROM files WHERE id=?',(item['file_id'],))

    def _run(self,cleanup_id):
        status,message='completed','Actions terminées ; archives conservées. La Corbeille ne sera jamais vidée par FileOrganizer.'
        try:
            actions=self._actions(cleanup_id)
            for action in actions:
                if self.stop.is_set():raise SafetyError('Arrêt demandé : nouvelle vérification requise.')
                job,items=self._items(action['transfer_job_id']);item=next(i for i in items if i['file_id']==action['file_id'])
                with self.verified(job,item) as (snapshot,guard):
                    if action['method']!='windows_recycle_bin':
                        self._mark(action['id'],'manual_required','Retrait à effectuer vous-même dans la Corbeille/Galerie/Gestionnaire de fichiers, après contrôle de l’archive. Aucun ordre de suppression envoyé.')
                        status='manual_required';continue
                    self._mark(action['id'],'running','Envoi explicite à la Corbeille Windows.')
                    receipt=self.recycler.recycle(snapshot,guard,self._digest)
                    self._mark(action['id'],'recycled','Fichier mis à la Corbeille ; restaurable. Espace libéré après vidage manuel uniquement.',receipt)
                    self._forget(item,snapshot)
                    self.db.event('source_recycled',f'{item["source"]} : Corbeille, après vérification de {item["destination"]}.')
        except Exception as e:
            status,message='blocked',str(e)
            if 'action' in locals():
                # Preserve a successful receipt even if a device fails immediately afterwards.
                current=next(r for r in self._actions(cleanup_id) if r['id']==action['id'])
                if current['status'] not in ('recycled','manual_removed'):
                    self._mark(action['id'],'blocked',str(e),{'recovery_path':getattr(e,'recovery_path',None)})
        finally:
            with self.db.connect() as c:c.execute('UPDATE cleanup_jobs SET status=?,message=? WHERE id=?',(status,message,cleanup_id))
            self.db.event('cleanup_'+status,message,'info' if status=='completed' else 'warning')

    def confirm_manual(self,cleanup_id,confirmation):
        if confirmation!='RETRAIT EFFECTUÉ':raise SafetyError('Confirmez RETRAIT EFFECTUÉ après votre action manuelle.')
        result=self.get(cleanup_id)
        for action in self._actions(cleanup_id):
            if action['status']!='manual_required':continue
            job,items=self._items(action['transfer_job_id']);item=next(i for i in items if i['file_id']==action['file_id'])
            snapshot=self._opt_in(item,source_expected=False)
            with self.archive(job,item) as guard:
                if snapshot['kind']=='android':present=self.transfers.android.source_present(snapshot)
                else:
                    validate_root(snapshot['root']['path'],self.config.state_dir)
                    source=Path(snapshot['path']);check_components(source.parent)
                    try:source.lstat();present=True
                    except FileNotFoundError:present=False
                if present:raise SafetyError('La source est encore présente : retrait non confirmé.')
                guard();self._mark(action['id'],'manual_removed','Absence de la source contrôlée ; archive SHA-256 revérifiée.',{'method':'user_controlled','checked_at':time.time()})
                self._forget(item,snapshot)
                self.db.event('source_manual_removal_confirmed',item['source'])
        with self.db.connect() as c:
            remaining=c.execute("SELECT count(*) FROM cleanup_actions WHERE cleanup_job_id=? AND status NOT IN ('recycled','manual_removed')",(cleanup_id,)).fetchone()[0]
            if not remaining:c.execute("UPDATE cleanup_jobs SET status='completed',message='Retraits contrôlés et archives revérifiées.' WHERE id=?",(cleanup_id,))
        return self.get(cleanup_id)

    def _actions(self,cleanup_id):
        with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM cleanup_actions WHERE cleanup_job_id=? ORDER BY id',(cleanup_id,))]

    def get(self,cleanup_id,limit=100,offset=0):
        with self.db.connect() as c:
            row=c.execute('SELECT * FROM cleanup_jobs WHERE id=?',(cleanup_id,)).fetchone()
            if not row:raise ValueError('Nettoyage introuvable.')
            items=[dict(r) for r in c.execute('SELECT * FROM cleanup_actions WHERE cleanup_job_id=? ORDER BY id LIMIT ? OFFSET ?',(cleanup_id,limit,offset))]
            counts=dict(c.execute("SELECT count(*) AS total,coalesce(sum(status='manual_required'),0) AS manual_required FROM cleanup_actions WHERE cleanup_job_id=?",(cleanup_id,)).fetchone())
        return dict(row)|counts|{'items':items,'warning':WARNING,'permanent_delete_supported':False}

    def list(self):
        with self.db.connect() as c:ids=[r[0] for r in c.execute('SELECT id FROM cleanup_jobs ORDER BY created DESC LIMIT 20')]
        return [self.get(i,limit=20) for i in ids]

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=10)
