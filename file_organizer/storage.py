"""Read-only volume diagnostics. Never probes writability by creating a file."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .paths import native_path,display_path
from .safety import SafetyError, validate_root, check_components

KNOWN_FS = {'ntfs', 'exfat', 'fat32', 'vfat', 'ext2', 'ext3', 'ext4', 'xfs', 'btrfs', 'f2fs', 'tmpfs', 'overlay'}


def linux_mount(path):
    matches = []
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        mount_id = next(line.split(':',1)[1].strip() for line in Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines() if line.startswith('mnt_id:'))
    finally:
        os.close(fd)
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ', 1)
        fields, extra = left.split(), right.split()
        mount = fields[4].replace('\\040', ' ').replace('\\134', '\\')
        if path == Path(mount) or Path(mount) in path.parents:
            matches.append((len(mount), {'mount_id': fields[0], 'mount': mount, 'source': extra[1],
                                        'filesystem': extra[0], 'read_only': 'ro' in fields[5].split(',') or 'ro' in extra[2].split(',')}))
    if not matches:
        raise SafetyError('Volume non identifiable.')
    actual = next((m for _,m in matches if m['mount_id']==mount_id), None)
    if actual is None:
        raise SafetyError('Montage masqué ou non identifiable.')
    return actual


def windows_volume(path):
    from ctypes import wintypes as w
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    volume_path = ctypes.create_unicode_buffer(1024)
    k.GetVolumePathNameW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
    if not k.GetVolumePathNameW(native_path(path), volume_path, len(volume_path)):
        raise ctypes.WinError(ctypes.get_last_error())
    volume_path.value=display_path(volume_path.value)
    if Path(volume_path.value) != Path(path.anchor):
        raise SafetyError('Volume monté en sous-dossier non pris en charge : utilisez sa propre lettre de lecteur.')
    label, fs, guid = (ctypes.create_unicode_buffer(1024) for _ in range(3))
    serial, maximum, flags = w.DWORD(), w.DWORD(), w.DWORD()
    k.GetVolumeInformationW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.POINTER(w.DWORD), ctypes.POINTER(w.DWORD), w.LPWSTR, w.DWORD]
    if not k.GetVolumeInformationW(volume_path.value, label, len(label), ctypes.byref(serial), ctypes.byref(maximum), ctypes.byref(flags), fs, len(fs)):
        raise ctypes.WinError(ctypes.get_last_error())
    k.GetVolumeNameForVolumeMountPointW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
    if not k.GetVolumeNameForVolumeMountPointW(volume_path.value, guid, len(guid)):
        raise ctypes.WinError(ctypes.get_last_error())
    k.GetDriveTypeW.argtypes = [w.LPCWSTR]
    drive_type = k.GetDriveTypeW(volume_path.value)
    if drive_type not in (2, 3):
        raise SafetyError('Seuls les volumes locaux fixes ou amovibles sont acceptés.')
    return {'mount':volume_path.value, 'source':guid.value, 'filesystem':fs.value.lower(),
            'label':label.value, 'serial':str(serial.value), 'read_only':bool(flags.value & 0x80000),
            'drive_type':drive_type, 'mount_id':guid.value, 'volume_uuid':guid.value + ':' + str(serial.value)}


class Storage:
    def __init__(self, state_dir):
        self.state_dir = state_dir

    def diagnose(self, raw):
        result = {'path':str(raw), 'checked_at':time.time(), 'safe_to_write':False, 'anomalies':[],
                  'health':'non mesurée', 'model':'non disponible', 'non_destructive':True}
        try:
            path = check_components(Path(str(raw)).expanduser())
            if not os.path.isdir(native_path(path)): raise SafetyError('Un volume ou un dossier existant est requis.')
            st = os.stat(native_path(path))
            volume = windows_volume(path) if os.name == 'nt' else linux_mount(path)
            result.update(volume)
            if os.name != 'nt' and shutil.which('findmnt'):
                # Read-only metadata lookup; no scan/repair/format command is ever used.
                proc = subprocess.run(['findmnt','--json','--target',str(path),'--output','UUID'],capture_output=True,text=True,timeout=8)
                if proc.returncode == 0:
                    rows = json.loads(proc.stdout).get('filesystems', [])
                    if rows and rows[0].get('uuid'):
                        result['volume_uuid'] = rows[0]['uuid']
            usage = shutil.disk_usage(native_path(path))
            result.update(capacity=usage.total, free=usage.free, used=usage.used, accessible=os.access(native_path(path), os.R_OK),
                          directory_id=f'{st.st_dev}:{st.st_ino}', path=str(path))
            if os.name == 'nt':
                # Required Windows health evidence; fail closed if unavailable.
                letter = result['mount'][0]
                script = f"$ErrorActionPreference='Stop'; $v=Get-Volume -DriveLetter '{letter}'; $p=Get-Partition -DriveLetter '{letter}'; $d=$p | Get-Disk; [pscustomobject]@{{Model=$d.FriendlyName;DiskNumber=$d.Number;DiskSize=$d.Size;Health=[string]$d.HealthStatus;VolumeHealth=[string]$v.HealthStatus;Offline=$d.IsOffline;ReadOnly=$d.IsReadOnly;Operational=([string]::Join(',', $d.OperationalStatus))}} | ConvertTo-Json -Compress"
                proc = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=15)
                if proc.returncode:
                    raise SafetyError('État du disque Windows non vérifiable ; copie bloquée.')
                info = json.loads(proc.stdout.lstrip('\ufeff'))
                result.update(model=info['Model'], health=info['Health'], disk_number=info['DiskNumber'], disk_capacity=info['DiskSize'])
                if info['Health'] != 'Healthy' or info['VolumeHealth'] != 'Healthy' or info['Offline'] or info['ReadOnly'] or info['Operational'] != 'Online':
                    result['anomalies'].append('Le disque ou le volume Windows n’est pas sain, en ligne et inscriptible.')
            elif result['source'].startswith('/dev/') and shutil.which('lsblk'):
                proc = subprocess.run(['lsblk','--json','--bytes','--output','PATH,MODEL,SIZE',result['source']],capture_output=True,text=True,timeout=8)
                if proc.returncode == 0:
                    rows = json.loads(proc.stdout).get('blockdevices', [])
                    if rows:
                        result.update(model=rows[0].get('model') or 'modèle non exposé', disk_capacity=rows[0].get('size'))
            if result['filesystem'].lower() not in KNOWN_FS:
                result['anomalies'].append('Système de fichiers inconnu ou non pris en charge.')
            if result['read_only'] or not os.access(native_path(path), os.W_OK):
                result['anomalies'].append('Volume en lecture seule ou droits d’écriture absents.')
            if not result['accessible']:
                result['anomalies'].append('Dossier inaccessible en lecture.')
            stable = result.get('volume_uuid') or result['mount_id']
            result['identity'] = hashlib.sha256((stable+'|'+result['filesystem']+'|'+result['directory_id']).encode()).hexdigest()
            result['safe_to_write'] = not result['anomalies']
            result['notice'] = 'Contrôle logique non destructif ; ne remplace pas un diagnostic matériel SMART ni une sauvegarde indépendante.'
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            result['anomalies'].append(str(e))
        return result

    def require(self, raw, expected=None, required_bytes=0):
        validate_root(str(raw), self.state_dir)
        info = self.diagnose(raw)
        if not info['safe_to_write']:
            raise SafetyError('Écriture bloquée : ' + '; '.join(info['anomalies']))
        if expected and info['identity'] != expected:
            raise SafetyError('Le volume ou le dossier de destination a changé. Refaites un plan et un diagnostic.')
        if info['free'] < required_bytes + 16 * 1024 * 1024:
            raise SafetyError('Espace libre insuffisant (réserve de sécurité de 16 Mio incluse).')
        return info

    def guard(self, base, info):
        """Cheap check between blocks: detect detached/replaced mounts, including same path."""
        st = os.stat(native_path(base))
        if f'{st.st_dev}:{st.st_ino}' != info['directory_id']:
            raise SafetyError('Destination déconnectée ou remplacée.')
        current = windows_volume(base) if os.name == 'nt' else linux_mount(base)
        if current['mount_id'] != info['mount_id'] or current['read_only']:
            raise SafetyError('Montage de destination modifié ou passé en lecture seule.')
