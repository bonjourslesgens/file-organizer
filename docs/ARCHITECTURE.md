# Architecture 0.2

## Socle et composants

Le projet conserve le socle 0.1 : Python 3.11+, SQLite WAL, HTTP standard sur IPv4 `127.0.0.1`,
interface HTML/CSS/JS locale sans CDN. Aucun service distant, abonnement, télémétrie ou IA obligatoire.
Le PC fixe peut inventorier ses sources locales et un Android USB ; le PC portable exige encore
une instance locale distincte. Le protocole d’agents distants chiffrés reste à développer.

| Module | Responsabilité |
|---|---|
| `safety.py` | Liste blanche, ancêtres, liens, ouverture prudente, exclusions sensibles |
| `scanner.py` | Inventaire local asynchrone, signatures, SHA-256, cache, arrêt/reprise |
| `database.py` | Schéma compatible, migration additive et sauvegarde, vue locale/Android, journal |
| `archive.py` | Simulation, arborescence et snapshot immuable de chaque source |
| `storage.py` | Diagnostic non destructif et identité du volume/dossier |
| `destination.py` | Écritures confinées, ancêtres maintenus ouverts, publication sans remplacement |
| `transfers.py` | Sélection, validation à usage unique, copie, intégrité, progression, reprise |
| `android.py` | ADB USB facultatif, racines publiques, inventaire et lecture binaire en flux |
| `automation.py` | Analyses périodiques locales et simulations, sans validation automatique |
| `instance.py` | Verrou OS du dossier interne pour un processus CLI unique |
| `server.py`, `static/` | API authentifiée, assistant initial, interface, notifications |
| `windows/` | Version native et installateur Inno Setup ; construction sur Windows |

## Choix des outils

La bibliothèque standard suffit à l’exécution, ce qui réduit les dépendances sur les PC.
[Czkawka](https://github.com/qarmin/czkawka), examiné lors de la phase initiale, reste une piste pour
la similarité avancée ; aucun de ses outils de suppression n’est enveloppé.
[Syncthing](https://github.com/syncthing/syncthing) n’est pas activé : synchronisation et archivage
vérifié ont des contrats différents. [PyInstaller](https://github.com/pyinstaller/pyinstaller)
embarque Python ; Inno Setup prépare une installation par utilisateur avec mise à jour manuelle.
Ces outils de construction ne sont pas des dépendances de l’application installée.
ADB est choisi pour un flux USB direct contrôlable ; MTP n’est pas traité comme un chemin local.
Aucune dépendance Android n’est téléchargée silencieusement.

## Frontières HTTP et concurrence

Chaque API exige un jeton aléatoire renouvelé au démarrage, transmis en en-tête. L’hôte doit être
localhost au bon port ; les mutations JSON rejettent les origines étrangères. Pas de CORS permissif,
pas de téléchargement arbitraire par chemin, ressources statiques sur liste fixe. CSP,
échappement HTML, aperçus d’images bornés et protection des formules CSV sont maintenus.
Ce n’est pas un serveur multiutilisateur : un processus ayant accès à la session et au dossier interne
n’est pas une frontière d’authentification couverte. Le service n’est pas exposé au LAN/Internet.

Un verrou d’opérations sérialise les démarrages d’analyses/transferts et les mutations d’autorisations.
Les workers tournent en arrière-plan. L’automatisation attend les opérations actives et ne peut pas
valider un transfert. Le verrou OS du dossier interne protège les migrations/états de reprise contre
un second processus CLI. Les API de suppression, formatage, réparation et commande shell libre n’existent pas.

## Lecture et inventaire

L’ouverture locale vérifie les ancêtres et refuse symlinks, jonctions/reparse points, liens physiques,
projets/dépendances, chemins système et motifs sensibles. Sous POSIX, des descripteurs O_NOFOLLOW
sont conservés ; sous Windows, les handles d’ancêtres n’autorisent pas leur suppression/remplacement.
Les dates et identités sont contrôlées après lecture. Le cache évite une relecture si tous les
identifiants sont identiques ; un recalcul complet reste disponible. Les copies réelles relisent
systématiquement le contenu et vérifient le SHA-256 du plan, même si le cache était inchangé.

Les lignes `unverified`/`offline` restent consultables, sans confirmer de doublons ni de propositions.
La vue SQLite `inventory` regroupe local et Android avec identifiants distincts (Android négatifs).
Les listes sont paginées. L’inventaire Android conserve aussi ses propres racines et états.
Les formats reconnus couvrent les signatures principales, pas une validation exhaustive de chaque conteneur.

## Diagnostic et destination

Windows utilise les API volume (GUID, numéro de série, FS, flags) et des commandes PowerShell
**uniquement de consultation** Get-Volume/Get-Partition/Get-Disk pour modèle et état.
Sans preuve d’un disque/volume sain et en ligne, les copies sont bloquées.
Linux utilise le montage réel du descripteur via `/proc/self/fdinfo` et mountinfo, les métadonnées
findmnt/lsblk et disk_usage. Les montages masqués/empilés ne sont pas confondus avec le montage actif.
La santé SMART n’est pas mesurée sous Linux et est présentée ainsi.

L’identité combine volume UUID/GUID ou montage, système de fichiers et identité du dossier de base.
Elle est liée à la validation puis contrôlée avant la copie et entre blocs (au plus une fois par
seconde pour le contrôle courant), et aux étapes de publication. Une autre destination sous la même
lettre ou le même chemin est refusée. Un montage recréé sans identité stable n’est pas réadopté.
Le diagnostic n’utilise aucun test d’écriture. Les permissions effectives et erreurs d’E/S restent
contrôlées lors de la copie. Un diagnostic favorable ne garantit pas un matériel sans panne.

Le dossier de base doit exister et ne pas chevaucher une source ou le stockage interne. Les ancêtres
de destination sont maintenus ouverts. Les sous-dossiers et temporaires ne sont créés qu’après validation.
POSIX utilise mkdir/open avec dir_fd et O_NOFOLLOW ; Windows utilise des handles sans partage de
suppression et OPEN_REPARSE_POINT. Les branches natives Windows nécessitent la recette sur cet OS.

## Protocole de copie et reprise

1. Un plan persistant contient chemins, tailles, SHA-256, métadonnées d’identité et autorisation source.
2. `prepare` sélectionne les éléments, revalide sources et volume, contrôle l’espace avec 16 Mio
   de réserve et crée une validation interne expirant après 15 minutes, sans écriture sur la destination.
3. `start` consomme cette validation uniquement avec la confirmation COPIER et recontrôle les prérequis.
4. Le worker écrit un temporaire exclusif sur le support cible, journalise inode et progression,
   flush/fsync à chaque bloc et contrôle les changements de source.
5. Reprise : temporaire ordinaire, un seul lien, identité enregistrée ; chaque octet du préfixe est
   comparé à la source. Aucun fichier ambigu/corrompu n’est écrasé ou tronqué pour « réussir ».
6. SHA-256 source lu = plan, SHA-256 du temporaire = source. La publication intervient seulement
   après sortie du contexte qui recontrôle la source.
7. Sous Linux, renameat2(RENAME_NOREPLACE) ; repli link/unlink sur supports compatibles.
   Sous Windows, rename échoue si le nom existe. Aucun enchaînement exists()+rename écrasant.
8. Collision : le fichier existant est réutilisé seulement si hash et taille correspondent, sinon
   un autre nom est essayé. Seul le temporaire propre à ce transfert peut être retiré après réussite.
9. Hash du fichier final, puis statut vérifié persistant. Une coupure entre publication et commit
   est récupérée en reconnaissant le contenu déjà présent. Les sources ne sont jamais supprimées.

Les états pending/copying/paused/error/verified/already_present sont conservés par fichier ; les
jobs running au redémarrage deviennent interrupted et demandent REPRENDRE. La copie de fichiers
actifs, la disparition du périphérique, les permissions ou ENOSPC bloquent le travail sans annoncer
une réussite. Le contenu et mtime sont préservés sur les nouvelles copies, pas toutes les ACL/attributs.
Les `.partial` inconnus sont conservés, sans purge automatique.

## Android

Aucun ADB réseau ni écriture distante. Seuls DCIM/Pictures/Movies/Download de l’espace utilisateur
peuvent être autorisés. Chemins équivalents, applications/paquets, Android, dossiers cachés/nomedia,
projets, liens et fichiers non ordinaires sont refusés. Le serveur vérifie realpath/stat avant et après.
La détection de type utilise un petit en-tête ; SHA-256 est calculé sur le téléphone.

La copie utilise `adb exec-out cat` avec arguments cités, un lecteur de pipe borné et un délai maximal.
Les blocs vont au temporaire du disque de destination ; aucun média complet n’est stocké sur le SSD.
La reprise relit le préfixe depuis le téléphone, puis le flux restant. Hash et métadonnées du téléphone
sont revérifiés avant publication, ainsi que les octets reçus. Cette protection ne prétend pas
rendre fiable un téléphone compromis capable de mentir sur ses lectures/métadonnées.
Les tests émulent les réponses ADB et utilisent de vrais sous-processus binaires synthétiques ;
ils ne remplacent pas un test du câble, du pilote et des commandes sur Oukitel.

## Limites de charge et travaux restants

Les hash locaux sont séquentiels et en blocs pour limiter les lectures concurrentes du HDD.
Les exports complets CSV/JSON, listes ADB et très grands groupes de doublons sont encore assemblés
en mémoire ; l’export en flux et la pagination des membres extrêmes sont à améliorer avant de promettre
les performances sur plusieurs centaines de milliers de fichiers. Aucun benchmark matériel de ce volume
n’a été effectué. Le journal, les plans et temporaires n’ont pas de rotation automatique.

Pas d’agent PC distant, authentification réseau/pairage, IA, similarité perceptuelle, EXIF/GPS,
lecteur vidéo, suppression manuelle d’originaux ou réparation de disque dans cette version.
Les vérifications protègent des erreurs de l’application et redirections accidentelles ; les droits OS,
les logiciels privilégiés, les pannes matérielles et les sauvegardes demeurent indépendants.
