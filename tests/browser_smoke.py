"""Real Chromium test; optional development dependency: playwright, not needed to run the app."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright, expect
from file_organizer.server import Application, make_server
from tests.test_core import PNG, MP4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, default=Path(tempfile.gettempdir()) / 'file-organizer-artifacts')
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='FileOrganizer-Browser-') as tmp:
        base = Path(tmp).resolve()
        root = base / 'personal'
        root.mkdir()
        destination=base/'archives';destination.mkdir()
        for name, content in {'voile.png':PNG, 'photo-copie.png':PNG, 'DJI_test.mp4':MP4, 'cours-navigation.txt':b'document'}.items():
            p = root / name
            p.write_bytes(content)
            old = time.time() - 500 * 86400
            import os
            os.utime(p, (old, old))
        app = Application(base / 'state')
        server = make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width':1440,'height':1100}, device_scale_factor=1)
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda e: errors.append(e.text) if e.type=='error' and 'Content Security Policy' in e.text else None)
                page.goto(f'http://127.0.0.1:{server.server_port}')
                expect(page.get_by_role('heading', name='Vue d’ensemble', exact=True)).to_be_visible()
                expect(page.get_by_text('Un espace qui vous ressemble')).to_be_visible()
                page.get_by_role('link',name='Suivre le guide de démarrage').click()
                expect(page.get_by_role('heading',name='Vos fichiers restent sous votre contrôle.')).to_be_visible()
                page.get_by_role('button',name='Choisir mon premier dossier').click()
                assert app.config.snapshot()['onboarding_completed']
                page.get_by_role('link', name='Dossiers autorisés', exact=True).click()
                page.get_by_role('textbox', name='Chemin absolu').fill(str(root))
                page.get_by_role('textbox', name='Nom du dossier').fill('Photos & documents')
                page.get_by_role('textbox', name='Nom de cet appareil').fill('PC de test')
                page.get_by_role('button', name='Autoriser ce dossier', exact=True).click()
                expect(page.get_by_role('heading',name='Photos & documents')).to_be_visible()
                page.get_by_role('button',name='Analyser mes dossiers').click()
                expect(page.locator('#scan-status')).to_contain_text('Analyse terminée', timeout=15000)
                page.get_by_role('link',name='Explorateur').click()
                expect(page.locator('#file-results tbody tr')).to_have_count(4)
                page.get_by_role('textbox',name='Rechercher un fichier').fill('voile')
                page.get_by_role('button',name='Rechercher',exact=True).click()
                expect(page.locator('#file-results tbody tr')).to_have_count(1)
                page.get_by_role('button',name='voile.png',exact=True).click()
                expect(page.locator('dialog')).to_be_visible()
                expect(page.locator('dialog')).to_contain_text('image/png')
                page.get_by_role('button',name='Fermer',exact=True).click()
                page.get_by_role('link',name='Doublons',exact=True).click()
                expect(page.locator('.duplicate-group')).to_have_count(1)
                expect(page.locator('.duplicate-group tbody tr')).to_have_count(2)
                page.get_by_role('link',name='Archivage',exact=False).first.click()
                page.get_by_role('textbox',name='Dossier de destination envisagé').fill(str(destination))
                page.get_by_role('button',name='Simuler l’archivage').click()
                expect(page.locator('#plan-results')).to_contain_text('3 fichiers proposés')
                with page.expect_download() as download_info:
                    page.get_by_role('button',name='Exporter le plan').click()
                plan = json.loads(Path(download_info.value.path()).read_text())
                assert len(plan['items'])==3 and plan['mode']=='simulation'
                page.get_by_role('button',name='Sélectionner tout le plan',exact=True).click()
                page.get_by_role('button',name='Préparer la copie de la sélection').click()
                expect(page.locator('dialog')).to_contain_text('Valider une copie réelle')
                page.get_by_role('checkbox',name='Je reconnais cette destination et valide ces copies.').check()
                page.get_by_role('textbox',name='Pour confirmer, saisissez COPIER').fill('COPIER')
                page.get_by_role('button',name='Démarrer les copies vérifiées').click()
                expect(page.locator('#transfer-jobs')).to_contain_text('Terminé · SHA-256 vérifié',timeout=20000)
                assert len([p for p in destination.rglob('*') if p.is_file()])==3
                assert len(list(root.iterdir()))==4
                page.get_by_role('link',name='Appareils',exact=True).click()
                page.get_by_role('textbox',name='Chemin du disque ou dossier').fill(str(destination))
                page.get_by_role('button',name='Diagnostiquer',exact=True).click()
                expect(page.locator('#diagnostic-result')).to_contain_text('Volume accessible')
                from file_organizer.safety import SafetyError
                def missing_adb(): raise SafetyError('ADB absent : prérequis simulé du test')
                app.android.devices=missing_adb
                page.get_by_role('button',name='Détecter les appareils USB').click()
                expect(page.locator('#android-devices')).to_contain_text('ADB absent')
                page.get_by_role('link',name='Automatisation',exact=True).click()
                page.get_by_role('spinbutton',name='Intervalle en secondes').fill('30')
                page.get_by_role('textbox',name='Destination des simulations automatiques (facultative)').fill(str(destination))
                page.get_by_role('button',name='Enregistrer la planification').click()
                expect(page.locator('#toast')).to_contain_text('Planification enregistrée')
                page.get_by_role('button',name='Analyser et simuler maintenant').click()
                expect(page.locator('#automation-history')).to_contain_text('Voir le plan',timeout=15000)
                assert len(app.transfers.list())==1  # Automation only creates simulations.
                page.get_by_role('link',name='Notifications',exact=False).first.click()
                expect(page.locator('#view-content')).to_contain_text('transfer_completed')
                page.get_by_role('button',name='Marquer comme lu').first.click()
                page.get_by_role('link',name='Règles',exact=True).click()
                page.get_by_role('textbox',name='Catégories modifiables').fill('Voile : navigation, bateau\nÉtudes : cours')
                page.get_by_role('button',name='Enregistrer les règles',exact=True).click()
                expect(page.locator('#toast')).to_contain_text('Règles enregistrées')
                assert app.config.snapshot()['keyword_categories']['Voile']==['navigation','bateau']
                page.get_by_role('link',name='Historique',exact=True).click()
                expect(page.locator('#view-content')).to_contain_text('archive_simulated')
                page.get_by_role('link',name='Vue d’ensemble',exact=True).click()
                expect(page.locator('.metric').first).to_contain_text('4')
                page.locator('#toast').evaluate('(element) => element.hidden = true')
                screenshot=args.artifacts / 'file-organizer-dashboard.png'
                screenshot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot),full_page=True)
                page.get_by_role('link',name='Archivage',exact=True).click()
                expect(page.locator('#transfer-jobs')).to_contain_text('Terminé · SHA-256 vérifié')
                page.screenshot(path=str(args.artifacts / 'file-organizer-archive.png'),full_page=True)
                page.get_by_role('link',name='Vue d’ensemble',exact=True).click()
                page.set_viewport_size({'width':390,'height':844})
                page.screenshot(path=str(args.artifacts / 'file-organizer-mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Débordement horizontal mobile'
                for target in ('devices','automation','roots','rules'):
                    page.goto(f'http://127.0.0.1:{server.server_port}/#{target}')
                    expect(page.locator('#view-content .panel').first).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Débordement mobile : {target}'
                assert not errors, errors
                browser.close()
                print('PASS Chromium : autorisation, analyse, filtre, fiche, doublons, simulation, export, copie réelle validée, diagnostic, automatisation sans copie, notifications, règles, historique, responsive. Aucune erreur JavaScript/CSP.')
        finally:
            app.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__=='__main__':
    main()
