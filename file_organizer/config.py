from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import threading
import uuid

from .safety import validate_root, SafetyError

DEFAULTS = {
    'version': 1,
    'roots': [],
    'android_roots': [],
    'adb_path': '',
    'sensitive_patterns': ['*password*','*mot-de-passe*','*secret*','*recovery*','*seed*','*.key','*.pem','*.pfx','*.p12'],
    'onboarding_completed': False,
    'automation': {'enabled': False, 'interval_seconds': 300, 'destination': ''},
    'keyword_categories': {
        'Études': ['cours', 'étude', 'examen', 'mémoire', 'université'],
        'Projets': ['projet', 'rapport'],
        'Voile': ['voile', 'bateau', 'régate', 'navigation'],
        'Informatique': ['informatique', 'ordinateur', 'réseau'],
        'Documents personnels': ['facture', 'contrat', 'assurance', 'identité'],
    },
    'archive_rules': [
        {'name': 'Vidéos anciennes', 'category': 'videos', 'older_than_days': 183, 'enabled': True},
        {'name': 'Photos anciennes', 'category': 'images', 'older_than_days': 365, 'enabled': True},
    ],
}


def default_state_dir() -> Path:
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'FileOrganizer'
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))) / 'file-organizer'


class Config:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / 'config.json'
        self.lock = threading.RLock()
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            for key in ('android_roots','adb_path','automation','onboarding_completed','sensitive_patterns'):
                self.data.setdefault(key, deepcopy(DEFAULTS[key]))
            self.validate(self.data)
        else:
            self.data = deepcopy(DEFAULTS)
            self.save()

    def validate(self, data):
        if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('roots'), list):
            raise ValueError('Configuration non reconnue.')
        for r in data['roots']:
            if not isinstance(r, dict) or not all(isinstance(r.get(k), str) and r[k].strip() for k in ('id', 'path', 'device', 'label')):
                raise ValueError('Dossier autorisé incomplet.')
        if len({r['id'] for r in data['roots']}) != len(data['roots']):
            raise ValueError('Identifiants de dossiers en double.')
        patterns=data.get('sensitive_patterns',[])
        if not isinstance(patterns,list) or len(patterns)>100 or any(not isinstance(p,str) or not p.strip() or len(p)>160 for p in patterns):
            raise ValueError('Liste d’exclusions sensibles invalide.')
        automation = data.get('automation', DEFAULTS['automation'])
        if not isinstance(automation, dict) or type(automation.get('enabled')) is not bool or type(automation.get('interval_seconds')) is not int or not 30 <= automation['interval_seconds'] <= 86400 or not isinstance(automation.get('destination'), str):
            raise ValueError('Planification invalide : intervalle de 30 à 86 400 secondes requis.')
        if not isinstance(data.get('android_roots', []), list) or not isinstance(data.get('adb_path',''),str):
            raise ValueError('Configuration Android invalide.')
        for root in data.get('android_roots', []):
            if not isinstance(root,dict) or not all(isinstance(root.get(k),str) and root[k] for k in ('id','serial','path','label')):
                raise ValueError('Dossier Android incomplet.')
        themes = data.get('keyword_categories')
        if not isinstance(themes, dict) or len(themes) > 50:
            raise ValueError('Les catégories doivent être un objet de 50 entrées au maximum.')
        for name, words in themes.items():
            if not name or len(name) > 80 or not isinstance(words, list) or not words or len(words) > 100 or any(not isinstance(w, str) or not w or len(w) > 80 for w in words):
                raise ValueError('Chaque catégorie doit contenir une liste de mots-clés non vides.')
        rules = data.get('archive_rules')
        if not isinstance(rules, list) or len(rules) > 50:
            raise ValueError('Liste de règles invalide.')
        for r in rules:
            if not isinstance(r, dict) or not isinstance(r.get('name'), str) or not r['name'] or r.get('category') not in ('images', 'videos', 'audio', 'documents', 'archives', 'other') or type(r.get('older_than_days')) is not int or not 0 <= r['older_than_days'] <= 36500 or type(r.get('enabled')) is not bool:
                raise ValueError('Règle invalide (catégorie, âge en jours, activation).')

    def snapshot(self):
        with self.lock:
            return deepcopy(self.data)

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(self.path)

    def add_root(self, raw: str, label: str, device: str):
        with self.lock:
            root = validate_root(raw, self.state_dir)
            for existing in self.data['roots']:
                p = Path(existing['path'])
                if root == p or root in p.parents or p in root.parents:
                    raise SafetyError('Les dossiers autorisés ne doivent pas se chevaucher.')
            entry = {'id': uuid.uuid4().hex, 'path': str(root), 'label': label.strip()[:80] or root.name,
                     'device': device.strip()[:80] or 'Cet ordinateur'}
            self.data['roots'].append(entry)
            self.save()
            return entry

    def remove_root(self, root_id):
        with self.lock:
            self.data['roots'] = [r for r in self.data['roots'] if r['id'] != root_id]
            self.save()

    def update_rules(self, themes, rules, sensitive_patterns=None):
        with self.lock:
            data = self.snapshot()
            data.update(keyword_categories=themes, archive_rules=rules)
            if sensitive_patterns is not None:data['sensitive_patterns']=sensitive_patterns
            self.validate(data)
            self.data = data
            self.save()

    def add_android_root(self,serial,path,label):
        with self.lock:
            from .android import validate_path
            validate_path(path)
            for root in self.data['android_roots']:
                if root['serial']==serial and (root['path']==path or path.startswith(root['path']+'/') or root['path'].startswith(path+'/')):
                    raise SafetyError('Dossiers Android chevauchants.')
            entry={'id':uuid.uuid4().hex,'serial':serial,'path':path,'label':label.strip()[:80] or 'Android'}
            self.data['android_roots'].append(entry);self.save()
            return entry

    def settings(self, **values):
        with self.lock:
            if any(k not in ('automation','adb_path','onboarding_completed') for k in values):
                raise ValueError('Paramètre inconnu.')
            data=self.snapshot();data.update(values);self.validate(data)
            self.data=data;self.save()

    def allow_cleanup(self,root_id,enabled,kind='local'):
        if type(enabled) is not bool or kind not in ('local','android'):
            raise ValueError('Autorisation de nettoyage invalide.')
        with self.lock:
            roots=self.data['roots' if kind=='local' else 'android_roots']
            entry=next((r for r in roots if r['id']==root_id),None)
            if entry is None:raise ValueError('Dossier non autorisé.')
            entry['cleanup_allowed']=enabled
            self.save()
            return entry
