"""One CLI process per state directory; protects restart recovery from a second instance."""
from pathlib import Path
import os


class InstanceLock:
    def __init__(self,path):
        self.path=Path(path).resolve();self.stream=None

    def acquire(self):
        self.path.mkdir(parents=True,exist_ok=True)
        self.stream=(self.path/'instance.lock').open('a+b')
        if self.stream.seek(0,2)==0:self.stream.write(b'0');self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as e:
            self.stream.close();self.stream=None
            raise ValueError('Une instance utilise déjà ce dossier interne. Ouvrez son interface ou choisissez un --data-dir distinct.') from e

    def close(self):
        if self.stream is not None:self.stream.close();self.stream=None
