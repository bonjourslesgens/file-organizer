"""Synthetic native identity probe used to diagnose OS-specific stat discrepancies."""
import json,os,tempfile,time
from pathlib import Path
from file_organizer.safety import identity,open_personal


def main():
    if os.name!='nt':return
    with tempfile.TemporaryDirectory(prefix='FileOrganizer-Probe-',dir=Path.home()) as raw:
        root=Path(raw)
        for i in range(20):
            p=root/f'{i}.png';p.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic')
            old=time.time()-500*86400;os.utime(p,(old,old))
            before=identity(p.lstat())
            with p.open('rb') as f:opened=identity(os.fstat(f.fileno()))
            try:
                with open_personal(root,p) as (f,st):f.read()
            except Exception as e:
                message=json.dumps({'before':before,'fstat':opened,'after':identity(p.lstat()),'error':str(e)})
                print('::warning title=Windows identity diagnostic::'+message,flush=True)
if __name__=='__main__':main()
