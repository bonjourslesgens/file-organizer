"""Guided first-run configuration: read-only discovery and scan; no copies or removals."""
from copy import deepcopy
import ctypes
import json
import os
from pathlib import Path
import shutil
import time
import uuid

from .safety import BLOCKED_NAMES,SafetyError,validate_root


class SetupFlow:
    def __init__(self,app):
        self.app=app
        with app.db.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS setup_runs(id TEXT PRIMARY KEY,created REAL,data TEXT,plan_id TEXT)')

    def discover(self):
        config=self.app.config.snapshot();volumes=[];suggestions=[]
        if os.name=='nt':
            from .storage import windows_volume
            k=ctypes.WinDLL('kernel32',use_last_error=True)
            mask=k.GetLogicalDrives()
            k.GetDriveTypeW.argtypes=[ctypes.c_wchar_p]
            for i in range(26):
                if not mask & (1<<i):continue
                raw=chr(65+i)+':\\'
                if k.GetDriveTypeW(raw) not in (2,3):continue
                item={'path':raw,'accessible':False,'filesystem':'unknown'}
                try:
                    item.update(windows_volume(Path(raw)));u=shutil.disk_usage(raw)
                    item.update(accessible=True,capacity=u.total,free=u.free)
                except (OSError,ValueError) as e:item['error']=str(e)
                volumes.append(item)
            # Windows known folders, including relocated/localized Documents/Pictures.
            import winreg
            definitions=[('Documents','Personal'),('Images','My Pictures'),('Vidéos','My Video'),('Téléchargements','{374DE290-123F-4565-9164-39C4925E467B}')]
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                    for label,name in definitions:
                        try:raw=winreg.QueryValueEx(key,name)[0];suggestions.append((label,os.path.expandvars(raw)))
                        except OSError:pass
            except OSError:pass
        else:
            candidates=[Path.home(),Path('/workspace')]
            for base in (Path('/media'),Path('/mnt')):
                if base.is_dir():
                    for child in base.iterdir():
                        if child.is_dir() and not child.is_symlink():
                            candidates.append(child)
                            candidates.extend(p for p in child.iterdir() if p.is_dir() and not p.is_symlink())
            seen=set()
            from .storage import linux_mount
            for path in candidates:
                try:
                    mount=linux_mount(path)
                    if mount['mount_id'] in seen:continue
                    seen.add(mount['mount_id']);u=shutil.disk_usage(path)
                    volumes.append(mount|{'path':mount['mount'],'accessible':True,'capacity':u.total,'free':u.free})
                except OSError:pass
            suggestions=[('Documents',str(Path.home()/'Documents')),('Images',str(Path.home()/'Pictures')),
                         ('Vidéos',str(Path.home()/'Videos')),('Téléchargements',str(Path.home()/'Downloads'))]
        suggestions.extend((r['label'],r['path']) for r in config['roots'])
        roots=[];seen_paths=set()
        for label,raw in suggestions:
            if raw in seen_paths:continue
            seen_paths.add(raw)
            item={'label':label,'path':raw,'available':False}
            try:validate_root(raw,self.app.config.state_dir);item['available']=True
            except (OSError,ValueError) as e:item['reason']=str(e)
            roots.append(item)
        return {'volumes':volumes,'sources':roots,'protected_names':sorted(BLOCKED_NAMES),
                'config':config,'diagnostic_required_before_archive':True,'destructive_operations':False}

    def validate_source(self,raw):
        path=validate_root(raw,self.app.config.state_dir)
        return {'path':str(path),'label':path.name,'device':'Cet ordinateur'}

    def apply(self,body):
        if body.get('protected_ack') is not True:raise SafetyError('Reconnaissez les exclusions de sécurité avant la configuration.')
        roots=body.get('roots')
        if not isinstance(roots,list) or not roots or len(roots)>50:raise ValueError('Choisissez au moins un dossier personnel précis (50 maximum).')
        cfg=self.app.config.snapshot();updated=deepcopy(cfg)
        for root in roots:
            if not isinstance(root,dict):raise ValueError('Source invalide.')
            path=validate_root(root['path'],self.app.config.state_dir)
            found=next((r for r in updated['roots'] if Path(r['path'])==path),None)
            if found:continue
            if any(path in Path(r['path']).parents or Path(r['path']) in path.parents for r in updated['roots']):
                raise SafetyError('Dossiers sources chevauchants ; la configuration n’a pas été appliquée.')
            updated['roots'].append({'id':uuid.uuid4().hex,'path':str(path),'label':str(root.get('label') or path.name)[:80],
                                    'device':str(root.get('device') or 'Cet ordinateur')[:80],'cleanup_allowed':False})
        destination=body.get('destination','')
        if not isinstance(destination,str):raise ValueError('Destination invalide.')
        diagnostic=None
        if destination:
            diagnostic=self.app.storage.require(destination)
            target=Path(destination)
            if any(target==Path(r['path']) or target in Path(r['path']).parents or Path(r['path']) in target.parents for r in updated['roots']):
                raise SafetyError('La destination et les sources ne doivent pas se chevaucher.')
        updated['archive_destination']=destination
        updated['archive_rules']=body.get('archive_rules',cfg['archive_rules'])
        updated['keyword_categories']=body.get('keyword_categories',cfg['keyword_categories'])
        updated['automation']=body.get('automation',cfg['automation'])|{'destination':destination}
        updated['onboarding_completed']=True
        self.app.config.validate(updated)
        with self.app.config.lock:
            self.app.config.data=updated;self.app.config.save()
        self.app.automation.last_run=time.time()
        scan=self.app.scanner.start()
        setup_id=uuid.uuid4().hex
        data={'scan_id':scan['id'],'destination':destination,'destination_identity':diagnostic['identity'] if diagnostic else None,
              'sources':len(updated['roots']),'destructive_operations':False}
        with self.app.db.connect() as c:c.execute('INSERT INTO setup_runs VALUES(?,?,?,NULL)',(setup_id,time.time(),json.dumps(data)))
        self.app.automation.start()
        self.app.db.event('first_setup_applied',f"{len(updated['roots'])} dossiers autorisés ; première analyse sans copie ni suppression.")
        return self.result(setup_id)

    def result(self,setup_id):
        with self.app.db.connect() as c:
            row=c.execute('SELECT * FROM setup_runs WHERE id=?',(setup_id,)).fetchone()
            if not row:raise ValueError('Assistant introuvable.')
            data=json.loads(row['data']);scan=c.execute('SELECT data FROM scans WHERE id=?',(data['scan_id'],)).fetchone()
        current=self.app.scanner.snapshot()
        scan=current if current.get('id')==data['scan_id'] else (json.loads(scan[0]) if scan else {'status':'interrupted'})
        return data|{'id':setup_id,'scan':scan,'stats':self.app.db.stats(),'plan_id':row['plan_id'],'ready':scan['status']=='completed'}

    def finish(self,setup_id):
        report=self.result(setup_id)
        if not report['ready']:raise SafetyError('L’analyse doit se terminer sans erreur avant de proposer un archivage.')
        if report['destination'] and not report['plan_id']:
            self.app.storage.require(report['destination'],expected=report['destination_identity'])
            plan=self.app.planner.simulate(report['destination'])
            with self.app.db.connect() as c:c.execute('UPDATE setup_runs SET plan_id=? WHERE id=?',(plan['id'],setup_id))
        return self.result(setup_id)
