# Installer et mettre à jour FileOrganizer 0.3

## Pour l’utilisateur Windows 11

1. Ouvrez le workflow [Tests et distribution Windows 11](https://github.com/bonjourslesgens/file-organizer/actions/workflows/checks.yml).
2. Choisissez l’exécution validée indiquée dans le bilan, puis l’artefact **FileOrganizer-0.3-Windows-x64**.
   Connectez-vous à GitHub si le téléchargement le demande.
3. Décompressez le ZIP. Il contient `FileOrganizer.exe`, `FileOrganizer-Setup-0.3.0-Windows-x64.exe`
   et `SHA256SUMS.txt`. Les témoins `PORTABLE_VALIDATED.txt` et `INSTALLER_VALIDATED.txt`
   indiquent respectivement la réussite des essais du portable et de l’installation/réinstallation.
4. Vérifiez la provenance et la somme du fichier, puis ouvrez l’installateur. Ne désactivez pas les
   protections globales de Windows pour lancer une copie de provenance incertaine.
5. Choisissez l’installation par utilisateur ; le raccourci Bureau est facultatif.
6. Ouvrez FileOrganizer depuis le menu Démarrer et suivez le guide de première configuration.

L’interpréteur Python et la dépendance native Windows sont embarqués. Il n’est pas nécessaire
qu’un Python soit présent dans PATH. Le test du binaire retire les chemins Python de son environnement
pour contrôler ce point lorsqu’il est exécuté par la CI.

Les binaires ne disposent pas encore d’une signature d’éditeur. Les résultats effectifs et limites de
validation matérielle restent dans le bilan : une exécution Windows Server ne vaut pas recette de votre PC Windows 11.

Exemple de contrôle d’intégrité du téléchargement :

```powershell
Get-FileHash .\FileOrganizer-Setup-0.3.0-Windows-x64.exe -Algorithm SHA256
```

Comparez au fichier de sommes venant du même artefact authentifié. L’option portable consiste à lancer
`FileOrganizer.exe` directement, sans installateur. La fenêtre doit rester ouverte pour maintenir le service local.

## Configuration persistante

- Application installée : `%LOCALAPPDATA%\Programs\FileOrganizer`.
- Données Windows : `%LOCALAPPDATA%\FileOrganizer`.
- Données Linux : `$XDG_DATA_HOME/file-organizer` ou `~/.local/share/file-organizer`.

Le dossier interne contient `config.json`, `inventory.sqlite3`, les fichiers SQLite WAL/SHM temporaires
et `instance.lock`. Il conserve autorisations, règles, index, simulations, copies et reçus de nettoyage.
Une seule instance peut l’utiliser. Ne supprimez pas son verrou pour forcer un second démarrage.
La désinstallation ne purge pas cet index et ne touche pas aux archives ou fichiers personnels.

## Mise à jour depuis 0.1/0.2

1. Mettez les transferts en pause et fermez FileOrganizer.
2. Sauvegardez le dossier de données **entier**, application arrêtée.
3. Vérifiez et lancez le nouvel installateur avec le même compte.
4. Le même AppId Inno Setup remplace les fichiers de l’application sans effacer les données.
5. Rouvrez et contrôlez les sources et opérations en attente. Un nettoyage interrompu ne reprend pas tout seul.

Les ajouts de schéma sont conservateurs. Un ancien index sans snapshot de plan reçoit une sauvegarde
SQLite cohérente `inventory.before-0.2-….sqlite3` avant migration. Un ancien plan sans preuve d’identité
reste consultable, mais doit être refait avant copie. L’autorisation de nettoyage est **désactivée par défaut**
pour les racines anciennes et nouvelles, tant que vous ne la donnez pas séparément.

Le cache Windows utilise désormais le même ChangeTime NTFS pour les chemins et handles ; une nouvelle
analyse peut recalculer des empreintes anciennes. Aucune désactivation de contrôles n’est nécessaire.
Le dossier d’index ne sauvegarde pas les médias qu’il référence.

## Construire sous Windows

Prérequis du constructeur seulement : Python 3.12, réseau vers PyPI et Inno Setup 6.

```powershell
.\Construire-Windows.ps1 -Installer
```

Le script installe la distribution source et PyInstaller 6.16.0 dans `.venv-build`, exécute les tests,
construit l’exécutable puis réalise un parcours complet de copie/nettoyage natif sur données fictives.
Les ressources et la version sont embarquées. Les vérifications TLS restent actives.
Sans `-Installer`, seul le portable est construit. Inno Setup disponible sur le runner produit l’installateur.

La CI teste Linux et Windows, construit, installe silencieusement, vérifie l’application installée,
réinstalle et vérifie encore. Elle conserve les rapports JSON et ne publie pas de release automatiquement.
Les changements de documentation seuls ne relancent pas une compilation identique.
Le bilan distingue les étapes effectivement réussies de celles encore non exécutées.

## Dépannage

- Port déjà occupé : réutilisez la session existante ou `--port 8766` avec un dossier interne distinct.
- Dossier refusé : vérifiez qu’il est personnel, physique et hors des exclusions ; ne contournez pas les jonctions.
- Disque unknown/RAW/inaccessible : aucune écriture ; suivez la procédure Seagate.
- ADB absent : l’inventaire local reste utilisable ; les Platform Tools sont facultatifs et externes.
- Corbeille indisponible : le logiciel ne bascule pas sur une suppression définitive automatique.
- Appareil déconnecté : conservez les partiels et rebranchez le même support avant toute reprise.

Aucune exclusion antivirus, élévation automatique ou règle publique de pare-feu n’est requise par conception.
