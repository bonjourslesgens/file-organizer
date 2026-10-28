# Bilan de validation — FileOrganizer 0.3.0

Le projet existant est conservé. Les opérations de développement et les essais utilisent uniquement
nos fichiers synthétiques ; aucun fichier personnel ni appareil physique de l’utilisateur n’a été modifié.

## Fonctionnalités livrées

| Fonction | Comportement de la version 0.3 |
|---|---|
| Inventaire et classification | Racines personnelles autorisées, exclusions système/applications, catégories, recherche, aperçu et exports conservés |
| Doublons | Comparaison SHA-256 réelle, y compris entre sources locales et Android |
| Archivage | Simulation puis sélection et COPIER ; lecture source/partiel/final, contrôle de volume, collisions sans remplacement, pause/reprise, journal |
| Nettoyage | Autorisation distincte par source, sélection des seuls fichiers admissibles, nouvelle lecture intégrale source/archive, NETTOYER et reconnaissance du risque de copie unique |
| Corbeille Windows | IFileOperation natif, identité contrôlée par handle, veto contre la suppression sans recyclage, reçu et récupération en cas de refus ; jamais de vidage automatique |
| Android | Lecture seule ADB dans les dossiers publics autorisés ; retrait exclusivement manuel dans Galerie/Fichiers puis contrôle d’absence et SHA-256 de l’archive |
| Première utilisation | Détection de supports, choix de dossiers, protections obligatoires, diagnostic sans écriture, règles, première analyse, doublons et simulation |
| Automatisation | Analyses et simulations périodiques facultatives ; aucune copie ni aucun nettoyage automatiques |
| Persistance | Configuration, index, simulations, transferts et reçus ; migration additive et verrou d’instance conservés |

L’autorisation de nettoyage est désactivée pour les sources anciennes et nouvelles. Les fichiers
ambigus, archives, programmes, données applicatives, éléments sensibles, liens, jonctions et sources
modifiées sont exclus. Une archive absente, corrompue ou sur un autre volume bloque le retrait.
L’assistant n’autorise jamais le nettoyage et n’écrit pas sur le support d’archives.

## Résultats automatisés

| Environnement | Résultat observé |
|---|---|
| Linux cloud, Python 3.12 | 126 tests recensés : **117 réussis, 9 ignorés, 0 échec** |
| GitHub Actions Ubuntu | Même résultat : **117 réussis, 9 ignorés, 0 échec** |
| GitHub Actions Windows natif | 126 tests recensés : **125 réussis, 1 ignoré, 0 échec** |
| Chromium Linux | Parcours complet assistant → inventaire → classification/doublons → simulation → copie SHA-256 → proposition et confirmation de nettoyage → constat du retrait manuel ; bureau et mobile réussis |
| CLI Linux en sous-processus | Copie et proposition, seconde instance refusée, conservation de l’index et des paramètres après redémarrage |
| Exécutable Windows PyInstaller | Construction réelle et parcours sans Python dans PATH ; copie SHA-256, recyclage natif et véritable redémarrage réussis sur fichiers synthétiques |
| Installateur Inno Setup | Construit, installé silencieusement, binaire installé testé, puis réinstallé et retesté ; configuration et index par défaut conservés octet pour octet |
| Paquet Python | Wheel 0.3.0 construite, installée dans un environnement distinct hors dépôt, ressources et démarrage HTTP vérifiés |

Exécution de référence : [workflow réussi du commit bec315e](https://github.com/bonjourslesgens/file-organizer/actions/runs/40692275842),
le 28 octobre 2026 (4 min 58 s). Les deux matrices et la distribution sont vertes.
L’artefact **FileOrganizer-0.3-Windows-x64** (27,9 Mo compressés) contient le portable, l’installateur
et leurs sommes SHA-256. Il se télécharge depuis la rubrique Artifacts, après connexion GitHub si demandée.
Les guides 0.3 et les témoins explicites de validation sont intégrés à la construction finale suivante,
avec le même code applicatif. Les rapports JSON Linux et Windows sont des artefacts séparés du workflow.

Le test du binaire retire Python de PATH et efface PYTHONPATH/PYTHONHOME pour ses lancements.
Il exerce trois distributions : portable, application installée puis application réinstallée.
Le test de redémarrage arrête l’arbre de processus PyInstaller complet avant de relancer ; il contrôle
ainsi la conservation réelle des données après arrêt, sans réutiliser un processus enfant encore actif.

Le runner Windows utilise **Windows-2025Server-10.0.26100-SP0**, sur NTFS, et Python 3.12 pour les tests
source. Il s’agit de tests natifs Windows, pas d’une recette sur le PC Windows 11 de l’utilisateur.
Les neuf tests ignorés sur Linux concernent Windows ; le seul ignoré sous Windows concerne un échange
d’ancêtre POSIX. Aucun test ignoré n’est compté comme réussi.

### Contrôles Windows effectivement exécutés

- Chemins source et destination de plus de 300 caractères et lecture/copie via les chemins natifs étendus.
- Permissions NTFS réellement refusées par ACL, fichier réellement verrouillé sans partage compatible.
- Liens symboliques et jonctions NTFS source/destination ; absence d’écriture hors destination autorisée.
- Cohérence du cache SHA-256 sur le ChangeTime natif, y compris entre chemins et handles.
- Copie, confirmation de nettoyage et IFileOperation natif sur NTFS.
- Restauration de la seule entrée synthétique de Corbeille créée par le test, puis contrôle du contenu.
- Refus forcé du recyclage par le callback Shell : veto réellement invoqué, source remise au nom initial.
- Sources et archives ouvertes/revérifiées, renommage natif par handle sans écrasement et vérification
  du chemin réellement retourné par Windows.

Les premières exécutions natives ont révélé des défauts spécifiques à Windows (métadonnées NTFS,
création indue lors d’une vérification, format du renommage et interface COM du callback). Ils ont
été corrigés ; les contrôles d’identité et d’intégrité ont été conservés.

### Contrôles de sécurité et fautes injectées

Source modifiée après simulation ou pendant transfert ; empreinte erronée ; partiel corrompu ;
pause/reprise ; processus interrompu ; destination déconnectée ou substituée ; erreur de lecture,
permission refusée et disque plein ; collisions fichier/dossier ; racine retirée ou devenue sensible ;
archive altérée après proposition ; consentement expiré/réutilisé/absent ; autorisation de nettoyage
retirée ; nettoyage interrompu sans reprise automatique. La vérification d’archives ne recrée pas
un dossier absent. Les appels concurrents incompatibles sont bloqués.

Les erreurs HTTP, jetons, origines, en-têtes Host, JSON, exports et aperçus restent testés.
Le parcours navigateur vérifie aussi l’absence de copies durant l’assistant et les analyses périodiques,
la sélection explicite, les avertissements, les confirmations et les reçus. Aucun dépassement horizontal
ni erreur JavaScript/CSP n’a été observé aux tailles de bureau et mobile testées.

### Android : simulation uniquement

Aucun téléphone physique ni véritable transport ADB/USB n’a été connecté. Les réponses ADB, modèles,
autorisations et erreurs sont simulés ; les tests de flux utilisent aussi de vrais sous-processus Python
produisant des octets binaires. Cela valide les règles de chemins, le connecteur, les doublons croisés,
les transferts et les refus en cas d’erreur, sans prouver la compatibilité matérielle de l’Oukitel.
Une déconnexion ou une erreur d’accès n’est jamais assimilée à une suppression réussie.

## À valider sur les appareils réels

| Appareil ou situation | Recette restante |
|---|---|
| PC Windows 11 | Installation, ouverture du navigateur, droits du compte, antivirus/SmartScreen et première copie avec quelques fichiers de test |
| Seagate Expansion 5 To | Identification, partition, FS, santé, accès et capacité ; ancien statut unknown **non résolu à distance** ; aucune écriture avant diagnostic favorable |
| Oukitel WP100 Titan | Platform Tools/pilote USB, autorisation de clé, outils shell disponibles, accès aux dossiers publics, copie puis contrôle du retrait manuel |
| Déconnexion/coupure matérielle | Scénarios physiques USB et panne, sur des copies de test ; seules des fautes injectées ont été validées dans le cloud |
| Gros volumes | Temps de scan/hachage, mémoire et latence sur les volumes réels ; aucun benchmark de plusieurs centaines de Go revendiqué |

## Limites et précautions utiles

- Les binaires ne sont pas signés et il n’existe pas de mise à jour automatique. Vérifiez leur provenance
  et les sommes SHA-256. Les artefacts Actions ont une durée de conservation limitée.
- La Corbeille occupe encore l’espace source jusqu’à votre vidage manuel. L’application ne vide aucune
  Corbeille. Sur Android et lorsque le recyclage natif sûr est indisponible, le retrait reste manuel.
- Un retrait laisse potentiellement une seule copie indépendante. L’index et une entrée de Corbeille
  ne remplacent pas une seconde sauvegarde des fichiers irremplaçables.
- Le recyclage utilise un nom temporaire unique dans le dossier source. Une restauration depuis la
  Corbeille peut nécessiter de redonner le nom original du reçu. En cas d’état incertain, aucun retrait
  n’est repris automatiquement ; consulter le journal et préserver les fichiers de récupération.
- Le diagnostic logique ne remplace pas SMART. Il ne répare, ne formate et n’initialise aucun disque.
  Les volumes Windows montés en sous-dossier, chemins réseau et FS non supportés restent bloqués.
- Une modification ou une déconnexion externe reste possible après n’importe quel contrôle logiciel.
  Gardez les supports branchés et les archives stables pendant une opération ; conservez une sauvegarde.
- Pas d’accès aux données privées Android, de synchronisation réseau entre PC, d’agent distant,
  d’IA, de similarité perceptuelle, d’EXIF/GPS ou de restauration complète d’ACL.
- Certains exports/listes ADB/groupes de doublons restent en mémoire ; journaux, plans et partiels ambigus
  ne sont pas purgés automatiquement. Les automatismes exigent que l’application soit ouverte.

## Guides et commandes reproductibles

[Installation](INSTALLATION.md) · [Première configuration](PREMIERE_CONFIGURATION.md) ·
[Seagate](SEAGATE.md) · [Android](ANDROID.md) · [Nettoyage](NETTOYAGE.md) · [Architecture](ARCHITECTURE.md)

```text
python -m tests.ci_runner
python -m tests.binary_smoke --source
python -m tests.browser_smoke --artifacts /workspace/artifacts/v03
```

Sous Windows : `./Construire-Windows.ps1 -Installer`. Le workflow construit puis teste le binaire,
installe et réinstalle ; consulter le résultat effectif de chaque étape avant de conclure.
Les commandes de test n’utilisent que leurs propres données fictives.
