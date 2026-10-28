"""Periodic local inventory/classification and archive simulations. No automatic transfers."""
import threading
import time


class Automation:
    def __init__(self, app):
        self.app=app;self.stop=threading.Event();self.thread=None;self.worker=None
        self.lock=threading.RLock()
        self.status={'status':'disabled','last_run':None,'next_run':None,'message':'Aucune copie automatique.'}
        with app.db.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS automation_runs(id INTEGER PRIMARY KEY,started REAL,status TEXT,message TEXT,plan_id TEXT)')
            c.execute("UPDATE automation_runs SET status='interrupted',message='Interruption de l’application ; nouvelle analyse nécessaire.' WHERE status='running'")
            last=c.execute('SELECT started FROM automation_runs ORDER BY id DESC LIMIT 1').fetchone()
        self.last_run=last[0] if last else 0

    def configure(self, settings):
        self.app.config.settings(automation=settings)
        self.app.db.event('automation_updated','Analyses périodiques '+('activées' if settings['enabled'] else 'désactivées')+'. Aucun transfert automatique.')
        self.start()
        return self.snapshot()

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            self.stop.clear();self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()

    def snapshot(self):
        settings=self.app.config.snapshot()['automation']
        return dict(self.status)|{'settings':settings}

    def tick(self,now=None,force=False):
        now=time.time() if now is None else now
        settings=self.app.config.snapshot()['automation']
        if not settings['enabled'] and not force:
            self.status.update(status='disabled',next_run=None);return False
        if self.worker and self.worker.is_alive():return False
        due=self.last_run+settings['interval_seconds']
        self.status['next_run']=due
        if not force and now<due:return False
        with self.app.operation_lock:
            if self.app.busy():
                self.status.update(status='waiting',message='Une opération est en cours.');return False
            if not self.app.config.snapshot()['roots']:
                self.status.update(status='waiting',message='Autorisez un dossier local avant de planifier.');return False
            self.app.scanner.start()
            self.last_run=now
            self.status.update(status='running',last_run=now,next_run=now+settings['interval_seconds'],message='Analyse et classement dans l’index ; simulation uniquement.')
            with self.app.db.connect() as c:
                run_id=c.execute("INSERT INTO automation_runs(started,status,message) VALUES(?,'running','')",(now,)).lastrowid
            self.worker=threading.Thread(target=self._finish,args=(run_id,settings),daemon=True);self.worker.start()
            return True

    def _finish(self,run_id,settings):
        self.app.scanner.wait(timeout=None)
        scan=self.app.scanner.snapshot();status=scan['status'];plan_id=None
        message=scan.get('message','')
        try:
            with self.app.operation_lock:
                if status=='completed' and settings.get('destination') and not self.app.busy(ignore_automation=True):
                    plan=self.app.planner.simulate(settings['destination']);plan_id=plan['id']
                    message=f"Analyse terminée ; {plan['count']} propositions. Aucune copie automatique."
        except Exception as e:
            status='blocked';message=str(e)
        with self.app.db.connect() as c:c.execute('UPDATE automation_runs SET status=?,message=?,plan_id=? WHERE id=?',(status,message,plan_id,run_id))
        self.status.update(status=status,message=message)
        self.app.db.event('automation_finished',message,'info' if status=='completed' else 'warning')

    def _loop(self):
        while not self.stop.is_set():
            try:self.tick()
            except Exception as e:
                self.status.update(status='error',message=str(e))
                self.app.db.event('automation_error',str(e),'error')
            self.stop.wait(1)

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        if self.worker:self.worker.join(timeout=5)

    def history(self):
        with self.app.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM automation_runs ORDER BY id DESC LIMIT 30')]
