"""Run on a built executable; supports --source for equivalent CLI validation on Linux."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from tests.test_core import PNG


def main():
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path);p.add_argument('--source',action='store_true');args=p.parse_args()
    command=[sys.executable,'-m','file_organizer'] if args.source else [str(args.exe.resolve())]
    with tempfile.TemporaryDirectory(prefix='FileOrganizer-Binary-',dir=Path.home() if os.name=='nt' else None) as tmp:
        base=Path(tmp);source=base/'personal';source.mkdir();dest=base/'archives';dest.mkdir()
        source_file=source/'old.png';source_file.write_bytes(PNG);old=time.time()-500*86400;os.utime(source_file,(old,old))
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        def start():
            process=subprocess.Popen(command+['--no-browser','--port',str(port),'--data-dir',str(base/'state')],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    if process.poll() is not None:raise AssertionError(process.stderr.read().decode('utf-8','replace'))
                    try:
                        html=urllib.request.urlopen(url,timeout=1).read()
                        token=re.search(b'name="organizer-token" content="([^"]+)"',html).group(1).decode()
                        return process,token
                    except (OSError,urllib.error.URLError):time.sleep(.2)
                raise AssertionError('Application non prete')
            except BaseException:
                process.terminate();process.wait(timeout=10);raise
        process,token=start()
        def api(path,body=None):
            req=urllib.request.Request(url+path,headers={'X-Organizer-Token':token,'Content-Type':'application/json'},data=json.dumps(body).encode() if body is not None else None)
            return json.load(urllib.request.urlopen(req,timeout=45))
        try:
            api('/api/roots/add',{'path':str(source),'label':'Photos','device':'PC test'})
            api('/api/scan',{})
            for _ in range(100):
                state=api('/api/state')
                if state['scan']['status']!='running':break
                time.sleep(.1)
            assert state['scan']['status']=='completed' and state['stats']['files']==1
            plan=api('/api/simulate',{'destination':str(dest)})
            a=api('/api/transfers/prepare',{'plan_id':plan['id'],'all_files':True})
            j=api('/api/transfers/start',{'approval_id':a['approval_id'],'confirmation':'COPIER'})
            for _ in range(200):
                j=api('/api/transfer?id='+j['id'])
                if j['status']!='running':break
                time.sleep(.1)
            assert j['status']=='completed',j
            assert Path(j['items'][0]['destination']).read_bytes()==PNG
            assert source_file.read_bytes()==PNG
            # A second process must not mutate recovery state of a running transfer/index.
            second=subprocess.run(command+['--no-browser','--data-dir',str(base/'state')],capture_output=True,timeout=30)
            assert second.returncode!=0
            process.terminate();process.wait(timeout=15)
            process,token=start()
            restored=api('/api/state')
            assert restored['stats']['files']==1 and len(restored['config']['roots'])==1
            assert restored['transfers'][0]['status']=='completed'
            print('PASS distribution : inventaire, copie SHA-256, source preservee, instance unique, index et parametres conserves apres redemarrage.')
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=15)
            process.stderr.close()


if __name__=='__main__':main()
