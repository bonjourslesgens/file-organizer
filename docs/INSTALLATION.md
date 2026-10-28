# Installation et mise à jour — 0.2

## Application Windows autonome

La cible est Windows 11 x64. Le `.exe` PyInstaller inclut l’interpréteur et n’exige pas Python sur le
PC utilisateur. L’installateur Inno Setup s’installe pour l’utilisateur courant dans
`%LOCALAPPDATA%\Programs\FileOrganizer`, sans élévation ni service au démarrage.
Il crée une entrée du menu Démarrer ; le raccourci Bureau est facultatif.

**Ces binaires ne sont pas fournis comme compilés ou testés ici : la machine de développement est
Linux.** Le code de construction et les tests Windows sont prêts. Aucun workflow distant n’a été
lancé, aucun code n’a été poussé ni publié sur GitHub par cette session.

## Construire sous Windows ou dans GitHub Actions

La construction nécessite Python 3.11+ et Inno Setup 6 (uniquement sur le poste de construction).

```powershell
.\Construire-Windows.ps1 -Installer
```

Le script utilise Python dans PATH, crée `.venv-build`, installe `PyInstaller==6.16.0`, exécute les
tests, embarque les ressources et les informations de version, puis démarre le binaire obtenu.
Le test du binaire réalise sur données synthétiques une analyse, une copie SHA-256, un contrôle
d’instance unique et un redémarrage conservant l’index et la configuration.
Sans `-Installer`, seul le `.exe` autonome est construit. Les contrôles TLS restent activés.

Sorties attendues :

```text
dist/FileOrganizer.exe
dist/FileOrganizer-Setup-0.2.0-Windows-x64.exe
dist/SHA256SUMS.txt
```

Le workflow `.github/workflows/checks.yml` prépare Python 3.12 sur les runners Windows, utilise
Inno Setup disponible sur l’image, construit, installe silencieusement, vérifie le programme installé,
puis réinstalle et vérifie à nouveau. Il échoue si le compilateur ou un contrôle manque.
Les fichiers sont déposés comme artefacts du workflow ; il n’y a pas de publication de release automatique.
Le job Windows doit être lancé après envoi du code dans le dépôt, par push ou `workflow_dispatch`.
Un runner Windows Server ne remplace pas une recette sur votre Windows 11 physique.

Pour vérifier un téléchargement :

```powershell
Get-FileHash .\FileOrganizer-Setup-0.2.0-Windows-x64.exe -Algorithm SHA256
```

Comparez à la somme provenant du même artefact authentifié. Les binaires sont pour l’instant non signés ;
la signature de distribution reste à organiser. PyInstaller ne compile pas un `.exe` Windows sur Linux.

## Exécuter le projet source

Avec Python 3.11+ : double-cliquez sur `Lancer.cmd`, ou exécutez `python -m file_organizer`.
Aucune bibliothèque Python supplémentaire n’est nécessaire. L’index et les copies ne nécessitent
pas le GPU. N’utilisez pas le mode administrateur pour contourner un refus de dossier ou de diagnostic.

Si le port est occupé, utilisez l’instance existante ou `--port 8766` avec un `--data-dir` distinct.
Le verrou par dossier interne empêche une seconde instance de modifier les états de reprise.

## Données persistantes et migration

- Windows : `%LOCALAPPDATA%\FileOrganizer`.
- Linux : `$XDG_DATA_HOME/file-organizer` ou `~/.local/share/file-organizer`.
- Le paramètre `--data-dir` permet un autre emplacement.

`config.json` contient autorisations, règles et paramètres ADB/automatisation.
`inventory.sqlite3` contient inventaire, plans, validations, transferts, notifications et journal.
Les fichiers SQLite WAL/SHM et `instance.lock` sont internes. Ne les placez pas dans une source analysée.
Ne supprimez pas le verrou d’une instance active : fermez l’application.

La migration depuis 0.1 ajoute des champs et tables sans effacer les données. Avant l’ajout du champ
de snapshot des plans à un index existant, une copie SQLite cohérente
`inventory.before-0.2-<identifiant>.sqlite3` est créée dans le dossier interne.
Un ancien plan sans identité des sources reste consultable mais doit être simulé à nouveau avant copie.

## Mettre à jour

1. Mettez les transferts en pause puis fermez FileOrganizer.
2. Copiez le dossier interne **entier**, application arrêtée, vers un emplacement sûr.
3. Vérifiez la provenance et la somme du nouvel installateur ; exécutez-le avec le même compte utilisateur.
4. Le même identifiant Inno Setup remplace les fichiers de l’application ; il ne supprime ni index,
   ni paramètres, ni archives. Rouvrez et contrôlez les autorisations ainsi que les transferts en attente.

Il n’existe pas de mise à jour téléchargée ou exécutée en arrière-plan. Pour revenir à 0.1, restaurez
l’index sauvegardé dans un dossier interne distinct : son ancien moteur de planification ne comprend
pas le nouveau schéma. La désinstallation de l’application ne purge pas le dossier de données.
La copie de l’index n’est pas une sauvegarde des médias qu’il référence.

## Android

ADB reste une dépendance **facultative externe** : téléchargez les
[Platform Tools officiels Google](https://developer.android.com/tools/releases/platform-tools).
Dans Appareils, indiquez le chemin de `adb.exe` si absent de PATH.
Windows peut nécessiter le pilote USB du fabricant. Activez le débogage USB sur le téléphone,
branchez-le et validez uniquement la clé du PC que vous reconnaissez. Aucun `adb root`, `push`, `rm`,
`remount`, `tcpip` ou appairage réseau n’est utilisé par FileOrganizer.
Le serveur ADB peut démarrer localement lors de la détection demandée par l’utilisateur.

Les Platform Tools ne sont pas téléchargés ni installés automatiquement. Le GPU, MTP et une application
Android dédiée ne sont pas requis par ce connecteur. Sa compatibilité Oukitel reste à vérifier sur place.
