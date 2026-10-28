from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
import threading
import time
import webbrowser

from .config import default_state_dir
from . import __version__
from .instance import InstanceLock
from .server import Application, make_server


def create_demo(app):
    """Only create synthetic files in a newly allocated directory, never replace user files."""
    folder = Path(tempfile.mkdtemp(prefix='FileOrganizer-Demo-', dir=Path.home() if os.name == 'nt' else None))
    (folder / 'Photos').mkdir()
    (folder / 'Vidéos').mkdir()
    # Genuine minimal PNG, with two copies under different names.
    import base64
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4d8AAAAASUVORK5CYII=')
    files = {
        folder / 'Photos' / 'voile-2023.png': png,
        folder / 'Photos' / 'copie-souvenir.png': png,
        folder / 'Vidéos' / 'DJI_exemple.mp4': b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 8192,
        folder / 'cours-navigation.txt': 'Cours de navigation — document synthétique.\n'.encode(),
        folder / 'facture-exemple.pdf': b'%PDF-1.4\n% fichier synthetique pour inventaire uniquement\n%%EOF',
    }
    for path, content in files.items():
        path.write_bytes(content)
        old = time.time() - 500 * 86400
        os.utime(path, (old, old))
    app.config.add_root(str(folder), 'Données de démonstration', 'Ordinateur de démonstration')
    app.db.event('demo_created', f'Données synthétiques créées dans {folder}. La vidéo et le PDF sont des en-têtes de test, pas des médias lisibles.')
    app.scanner.start()
    return folder


def main():
    parser = argparse.ArgumentParser(description='File Organizer : inventaire, simulation et copies vérifiées après validation.')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--data-dir', type=Path, default=default_state_dir(), help='Dossier de configuration, index et journaux')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--demo', action='store_true', help='Créer et analyser uniquement des données synthétiques dans un nouveau dossier')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('Port hors limites.')
    instance = InstanceLock(args.data_dir)
    try:
        instance.acquire()
        app = Application(args.data_dir)
        server = make_server(app, args.port)
        if args.demo:
            print(f'Démonstration : {create_demo(app)}')
    except (OSError, ValueError) as e:
        instance.close()
        parser.exit(1, f'Impossible de démarrer : {e}\n')
    url = f'http://127.0.0.1:{server.server_port}'
    app.automation.start()
    print(f'File Organizer {__version__} — simulation par défaut, copies après validation\nInterface locale : {url}\nDonnées internes : {app.config.state_dir}\nCtrl+C pour arrêter.', flush=True)
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()
        instance.close()


if __name__ == '__main__':
    main()
