# Architecture et sécurité — 0.3

## Composants conservés et ajoutés

Le socle reste Python, SQLite WAL et une interface HTML/CSS/JS locale, sans CDN, télémétrie ni service
public. Windows utilise pywin32 311 pour le mécanisme Shell ; cette dépendance est embarquée dans
la distribution autonome. Linux ne nécessite pas de paquet d’exécution supplémentaire.

| Module | Responsabilité |
|---|---|
| `safety.py`, `paths.py` | Whitelist, exclusions, ouvertures prudentes, identités cohérentes et chemins longs Windows |
| `scanner.py`, `database.py` | Inventaire asynchrone, signatures, cache, SHA-256, index local/Android, migrations, journal |
| `archive.py` | Simulation et snapshot de chaque source |
| `storage.py`, `destination.py` | Diagnostic non destructif, volume attendu, écritures confinées et publication sans remplacement |
| `transfers.py` | Validation COPIER à usage unique, progression, copie vérifiée, pause/reprise |
| `cleanup.py` | Propositions fraîches, autorisation de dossier, validation NETTOYER, audit et contrôle des retraits manuels |
| `win_recycle.py` | Recyclage Windows natif, nom de sécurité par handle, veto et récupération sans écrasement |
| `setup_flow.py` | Découverte en lecture seule, configuration guidée, première analyse et propositions sans transfert |
| `android.py` | ADB USB en lecture seule, médias publics, flux et contrôle d’absence après action manuelle |
| `automation.py`, `instance.py` | Analyses périodiques sans transfert/retrait et verrou OS par dossier interne |
| `server.py`, `static/` | API locale authentifiée, interface française, assistant, notifications et reçus |
| `windows/`, `.github/workflows/` | Métadonnées, installateur, compilation native et tests de distribution |

Les solutions Czkawka/Syncthing examinées initialement ne sont pas activées. Le projet n’enveloppe
aucun moteur tiers de suppression. PyInstaller inclut l’interpréteur ; Inno Setup installe par utilisateur.
ADB reste un outil officiel externe facultatif, sans téléchargement ou installation silencieux.

## Frontières et concurrence

Le serveur écoute sur `127.0.0.1`. Les API exigent un jeton par session, un Host local au bon port ;
les mutations JSON rejettent les origines étrangères. Pas de CORS permissif, accès arbitraire par
chemin, commande shell libre, formatage, réparation ou vidage de Corbeille. Ressources statiques sur
liste fixe, CSP, échappement HTML, images bornées et protection CSV sont conservés.
Ce n’est pas une frontière contre un logiciel disposant déjà des droits de la session et du dossier interne.

Le verrou d’opérations empêche les démarrages concurrents incompatibles et les modifications d’autorisations
pendant une copie/retrait. L’assistant n’autorise pas le nettoyage. L’automatisation ne peut appeler
ni une validation COPIER ni une validation NETTOYER. Le CLI détient un verrou OS empêchant un second
processus de réinterpréter les états d’opérations actives.

## Whitelist, métadonnées et chemins Windows

Chaque ancêtre est contrôlé avant résolution ; les liens, jonctions/reparse points, liens physiques,
projets/dépendances, système, applications, jeux et motifs sensibles sont exclus.
L’autorisation d’analyser/copier n’est pas une autorisation de retirer : `cleanup_allowed` doit être
explicitement le booléen true pour le dossier courant. La chaîne JSON `"false"` n’est jamais un accord.

POSIX tient des descripteurs O_NOFOLLOW et emploie dir_fd. Windows conserve des handles d’ancêtres
sans partage de suppression. Les chemins étendus sont internes aux appels système ; les chemins
utilisateur UNC/périphérique/flux NTFS restent refusés. Les chemins source/destination longs sont couverts
par les intégrations natives, sans utiliser une comparaison affaiblie pour les faire passer.

Python 3.12 ne donne pas la même signification à st_ctime dans stat et fstat sous Windows.
Le module emploie FILE_BASIC_INFO/GetFileInformationByHandleEx pour obtenir **ChangeTime** et
LastWriteTime de manière cohérente, ainsi que CreationTime pour l’affichage. Le cache et les comparaisons
conservent les identifiants, tailles et temps précis ; un recalcul complet reste possible.
Les copies et nettoyages relisent toujours le contenu et son SHA-256, même si le cache paraît inchangé.

## Volumes et copies

Le diagnostic ne crée aucun fichier. Windows lit GUID/série/FS/flags via les API et modèle/état via
Get-Volume/Get-Partition/Get-Disk. L’identité, l’accessibilité et l’espace restent revérifiés ; la lecture
PowerShell de santé est amortie pendant cinq secondes au maximum pour éviter un processus par fichier.
Un diagnostic explicite de l’interface force son rafraîchissement. Le timestamp de l’échantillon est conservé.
Linux identifie le montage réel depuis le descripteur et mountinfo, puis findmnt/lsblk lorsque disponibles.
La santé matérielle SMART n’est pas mesurée sous Linux et n’est pas présentée comme vérifiée.

Unknown/RAW, volume non identifié/non sain, lecture seule, destination remplacée ou inaccessible bloquent
les écritures. Une lettre seule ne fait pas identité. Le dossier de base ne doit pas chevaucher les
sources ni le stockage interne. Les vérifications de montage se répètent entre blocs et à la publication.
Les diagnostics/lectures de vérification utilisent `directory(create=False)` : un chemin disparu n’est pas recréé.

COPIER consomme une validation à usage unique de 15 minutes liée à une sélection et une identité de volume.
Le worker écrit un temporaire exclusif sur la destination, contrôle le hash source prévu, le temporaire
puis le fichier final. La source est recontrôlée après lecture avant publication.
La publication utilise renameat2(RENAME_NOREPLACE) sous Linux, link/unlink compatible en repli,
ou rename Windows sans remplacement. Un nom existant est réutilisé seulement si le contenu est confirmé
identique ; sinon suffixe. La reprise compare intégralement le préfixe partiel à la source, sans troncature
ou adoption d’un temporaire ambigu. Les créations/horodatages ne concernent que les nouvelles copies.

## Nettoyage contrôlé

Le contrôleur accepte uniquement des éléments déjà vérifiés, reconnus par signature et actuellement
identiques à leur snapshot. Les types ambigus et archives de contenu potentiellement applicatif sont exclus ;
les documents sont limités aux PDF reconnus. Il vérifie le dossier source courant, les exclusions sensibles,
la source complète et l’archive complète sur le bon support. Une source Windows protégée en lecture seule est exclue.

NETTOYER est distinct de COPIER : sélection de 1 à 1 000 éléments, relecture, avertissement de copie unique,
reconnaissance explicite de ce risque, puis validation à usage unique de cinq minutes. Le worker recommence
les contrôles avant chaque action et maintient l’archive ouverte durant le retrait Windows.
Un seul exemplaire connu hors Corbeille n’est jamais présenté comme une sauvegarde suffisante.

### Windows

Le backend est limité aux sources NTFS fixes où la Corbeille native est adaptée. Il ouvre la source
avec lecture/DELETE sans partage d’écriture ou suppression, compare identité et hash, puis renomme le
même objet **par handle**, sans remplacement, sous un nom unique dans le dossier source.
FILE_RENAME_INFO est terminé correctement en UTF-16 et le chemin final retourné par Windows est contrôlé.
Cela évite de confier à la Corbeille un nouveau fichier apparu sous le nom d’origine entre deux appels.

IFileOperation demande recyclage et enregistrement d’annulation. Le progress sink **lève E_ABORT** si
Windows prépare une suppression sans recyclage ; retourner seulement un entier depuis Python n’est pas
suffisant. Le sink utilise le gateway direct PythonCOM : cet IID est SERVER_ONLY et n’a pas de wrapper client.
Une intégration native vérifie que ce veto est réellement appelé et que le fichier revient intact.

Un IShellItem de réception non nul confirme l’entrée de Corbeille. Son chemin physique peut être absent
car l’objet Shell est virtuel ; les noms/identifiants disponibles et le nom de sécurité restent journalisés.
Une erreur d’affichage ne fait pas perdre un reçu natif valide. Si le recyclage échoue avant transfert,
le nom d’origine est restauré sans écrasement. Un conflit/état incertain exige un contrôle manuel ; les
chemins de récupération restent dans l’audit. Le logiciel ne vide jamais la Corbeille.

### Procédures manuelles

Android n’utilise aucun backend de suppression ADB. Après la préparation contrôlée, l’utilisateur agit
dans Galerie/Fichiers. RETRAIT EFFECTUÉ relit l’archive et vérifie une absence **par fichier** avec un parent
accessible/non redirigé. Erreurs ADB et permissions ne deviennent jamais « absent ». Linux reste également
en action manuelle pour les fichiers personnels. L’audit confirme l’état observé, pas des octets réellement libérés.

Les états de nettoyage interrompus deviennent incertains et ne reprennent jamais automatiquement.
Les reçus de copie restent conservés ; le compteur d’originaux retirés est distinct du statut de copie réussie.
Les API de liste des reçus sont bornées/paginées.

## Android et limites

ADB est USB seulement. Racines publiques : DCIM/Pictures/Movies/Download de l’espace utilisateur.
Android/data/obb/media, paquets, cachés/nomedia, projets et liens sont exclus. Métadonnées/realpath et hash
sont revérifiés ; le flux exec-out cat va directement au temporaire sur le support cible, avec mémoire bornée
et délai de lecture. La reprise relit le préfixe depuis le téléphone, sans staging massif sur le SSD.
Aucune commande root/remount/push/tcpip/connect/rm n’est une fonctionnalité du connecteur.
Les tests du téléphone sont simulés ; son OS, câble, pilote et commandes réels restent à valider.

Pas d’agent réseau PC portable, IA, EXIF/GPS, similarité perceptuelle, aperçu vidéo/HEIC ou clone complet des ACL.
Certains exports complets/listes ADB et groupes de doublons extrêmes restent en mémoire. Journal/plans et
partiels ne sont pas purgés automatiquement. Aucun benchmark matériel à plusieurs centaines de milliers
de fichiers n’est revendiqué. Les vérifications n’éliminent ni les pannes futures ni les risques d’un
logiciel privilégié qui contrôlerait la session ; une sauvegarde indépendante demeure nécessaire.
