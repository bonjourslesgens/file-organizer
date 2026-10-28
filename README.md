# FileOrganizer 0.3 — organiser, archiver et retirer avec contrôle

Application locale en français pour Windows 11 : inventaire, doublons SHA-256, copies vérifiées,
assistant initial et nettoyage après archivage. Le projet 0.2 est conservé et enrichi.

## Installer sur Windows

Téléchargez l’artefact **FileOrganizer-0.3-Windows-x64** du [workflow Windows](https://github.com/bonjourslesgens/file-organizer/actions/workflows/checks.yml),
décompressez-le, puis ouvrez `FileOrganizer-Setup-0.3.0-Windows-x64.exe`.
L’application autonome inclut Python et pywin32 : **aucune installation manuelle de Python** sur le PC utilisateur.
Les résultats réels, le commit et les liens de validation sont détaillés dans le [bilan](docs/BILAN.md).
Les artefacts GitHub peuvent demander votre connexion ; un workflow en échec ne fournit pas une distribution validée.

L’installateur fonctionne par utilisateur, sans service public ni lancement automatique.
Les paramètres et l’index restent dans `%LOCALAPPDATA%\FileOrganizer` et sont conservés lors d’une mise à jour.
Les binaires ne sont pas signés ; vérifiez la provenance et les sommes SHA-256 fournies.

## Première utilisation

1. Lancez FileOrganizer depuis le menu Démarrer, puis ouvrez **Suivre le guide de démarrage**.
2. Détectez les supports et autorisez des dossiers personnels précis.
3. Vérifiez les protections obligatoires et, si souhaité, un dossier de destination sain.
4. Adaptez catégories et règles puis lancez une **première analyse sans copie ni retrait**.
5. Consultez doublons et simulations avant de décider d’une copie réelle.

[Guide de première configuration](docs/PREMIERE_CONFIGURATION.md) · [Installation et mise à jour](docs/INSTALLATION.md)

## Copie et nettoyage : deux validations séparées

- La simulation décrit les fichiers et destinations sans écrire sur le support d’archives.
- **COPIER** autorise une sélection précise, avec contrôle du volume, SHA-256 source/partiel/final,
  collisions sans remplacement, pause et reprise. Les originaux restent présents à ce stade.
- Les propositions de nettoyage exigent une autorisation distincte du dossier comme personnel/autonome.
- Sources et archives sont relues ; ambiguïtés, changements, erreurs et supports indisponibles excluent le retrait.
- **NETTOYER** et un avertissement de copie unique sont nécessaires avant toute action de retrait.
- Windows utilise la Corbeille lorsque le mécanisme natif sûr est adapté. L’application ne la vide jamais.
- Android reste en retrait manuel dans Galerie/Fichiers ; **aucun ordre ADB de suppression** n’est envoyé.

La Corbeille continue à occuper l’espace jusqu’à son vidage manuel. Un seul exemplaire sur le Seagate
n’est pas une sauvegarde indépendante. Préservez une seconde copie des fichiers irremplaçables.
[Guide du nettoyage et restauration](docs/NETTOYAGE.md)

## Fonctions conservées

Inventaire SQLite persistant, statistiques globales, recherche et filtres, catégories/étiquettes,
empreintes exactes, doublons entre sources locales et Android, aperçu d’images borné,
règles d’âge/type, DJI/année/mois, simulations enregistrées, rapports CSV/JSON, journal et notifications.
La surveillance est périodique et ne valide jamais une copie ou un nettoyage automatiquement.
Le serveur écoute seulement sur `127.0.0.1` ; pas d’agent PC distant ni de port public.

## Seagate et Android

- [Diagnostiquer le Seagate sans écriture](docs/SEAGATE.md)
- [Connecter l’Oukitel et gérer les retraits manuels](docs/ANDROID.md)

Le statut historique « unknown » du Seagate n’est pas présumé résolu. Les tests dans le cloud
n’accèdent pas à vos appareils réels. Le connecteur ADB est vérifié par simulation ; la recette
Oukitel/câble/pilote reste nécessaire. Aucun formatage, initialisation ou réparation automatique.

## Développer et tester

Python 3.12 est la version de construction testée. Sur Windows, `py -3 -m pip install .` installe
la dépendance native `pywin32==311` ; sous Linux, aucun paquet d’exécution n’est nécessaire.
Lancez ensuite `python -m file_organizer` ou `Lancer.cmd` avec le même interpréteur sous Windows.

```console
python -m unittest discover -v
python -m tests.binary_smoke --source
python -m file_organizer --demo
```

La démonstration crée un dossier neuf de données synthétiques. Pour un essai isolé, ajoutez
`--data-dir CHEMIN_NEUF`. Les en-têtes MP4/PDF de la démo ne sont pas des médias lisibles.
Les tests n’agissent que sur des données fictives. Sous Windows, les intégrations natives créent
quelques entrées de Corbeille de test, sans jamais vider les autres entrées.

Test Chromium facultatif : installez Playwright 1.62.0, son Chromium si nécessaire, puis
`python -m tests.browser_smoke`. Construction Windows : `Construire-Windows.ps1 -Installer`.

[Architecture et sécurité](docs/ARCHITECTURE.md) · [Rapport de validation](docs/BILAN.md)
