# FileOrganizer 0.2 — inventaire et copies vérifiées

Application locale en français pour inventorier vos dossiers personnels, retrouver les doublons,
préparer des archives et **copier après validation explicite**. Les fonctionnalités de la version 0.1
sont conservées. Aucune suppression d’original, aucun déplacement, aucun formatage, aucune réparation.

## Première utilisation

- **Distribution Windows autonome** : le projet fournit une compilation automatisée du `.exe` et
  d’un installateur par utilisateur, avec Python inclus. **Aucun binaire Windows n’a pu être construit
  ni exécuté dans cette session Linux.** Le workflow Windows doit encore tourner sur GitHub.
- **Distribution source disponible maintenant** : installez Python 3.11+, décompressez le projet,
  puis ouvrez `Lancer.cmd` sous Windows, ou lancez `python -m file_organizer` sous Linux.
  Aucune dépendance Python d’exécution à installer.

L’interface propose un guide de démarrage. Autorisez un dossier personnel précis puis lancez une
analyse. Les paramètres, l’index, les plans et les transferts sont conservés entre les démarrages.
Le serveur reste lié à `127.0.0.1` ; aucun port public et aucun agent distant ne sont activés.

## Ce que fait cette version

- Inventaire SQLite persistant, statistiques, recherche, filtres, étiquettes et rapports CSV/JSON.
- Doublons exacts SHA-256 entre dossiers locaux et médias Android inventoriés.
- Exclusions système/applications/jeux/dépendances, liens et fichiers sensibles par noms configurables.
- Simulation par règles : âge, type, appareil/dossier, année/mois, vidéos DJI.
- Sélection des propositions, diagnostic de destination, saisie de **COPIER** et validation temporaire
  à usage unique avant le transfert réel.
- Copie partielle sur la destination, vérification SHA-256 source/copie/fichier final,
  publication sans remplacement, collisions gérées, pause et reprise manuelle après interruption.
- Réutilisation d’un fichier déjà présent seulement après vérification de son contenu.
- Diagnostic logique non destructif : volume, capacité, système de fichiers, accès, espace,
  état Windows et modèle lorsqu’exposés. Unknown/RAW, lecture seule, volume changé ou inaccessible : blocage.
- Android USB via ADB facultatif : autorisation de dossiers publics, inventaire média, aperçu d’images,
  plans et flux directement vers la destination, sans staging massif sur le SSD du PC.
- Surveillance **périodique** des dossiers locaux, classement dans l’index et simulations automatiques.
  L’application doit rester ouverte ; aucune copie périodique ne se valide automatiquement.
- Rubriques Appareils, Automatisation et Notifications, progression et historique.

**La copie ne libère pas d’espace sur la source.** Les originaux restent en place et aucun bouton de
suppression n’est livré. Un Seagate contenant l’unique copie ne constitue pas une sauvegarde suffisante.

## Essayer avec des données synthétiques

```console
python -m file_organizer --demo
```

Un nouveau dossier `FileOrganizer-Demo-*` est créé. Pour ne pas utiliser une configuration précédente,
ajoutez `--data-dir` suivi d’un dossier interne neuf. Le PDF et la vidéo de démo sont des en-têtes de
test, pas des médias lisibles. Aucune source personnelle n’est autorisée automatiquement.

Autres options : `--no-browser`, `--port 8765`, `--data-dir CHEMIN`, `--version`.
Une seule instance peut utiliser un même dossier interne. `Ctrl+C` arrête l’application et demande
la pause des opérations ; les copies partielles sont conservées pour une reprise manuelle.

## Tests

```console
python -m unittest discover -v
python -m tests.binary_smoke --source
```

Test navigateur facultatif (Playwright n’est pas une dépendance de l’application) :

```console
python -m pip install playwright==1.62.0
python -m playwright install chromium
python -m tests.browser_smoke
```

Le test navigateur utilise Chromium système s’il est disponible, sinon celui de Playwright.
Les tests n’utilisent que des sources synthétiques ; les réponses ADB sont simulées.
Consultez le [bilan](docs/BILAN.md) pour les résultats exacts et les validations matérielles manquantes.

## Guides

- [Installation, `.exe`, installateur Windows et mise à jour](docs/INSTALLATION.md)
- [Première utilisation, copies, reprise, Android et automatisation](docs/UTILISATION.md)
- [Architecture et garanties de sécurité](docs/ARCHITECTURE.md)
- [Bilan et limites vérifiées](docs/BILAN.md)
- [Configuration d’exemple](examples/config.json)

Restent notamment : validation Windows 11/Oukitel/Seagate physiques, signature des binaires,
connexion sécurisée au PC portable, métadonnées EXIF/GPS, similarité visuelle, recherche sémantique et IA.
