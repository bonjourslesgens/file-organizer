# Bilan de livraison — version 0.2.0

Développement poursuivi dans le dépôt existant, sans remplacer le socle 0.1.
Les fichiers personnels et appareils réels de l’utilisateur n’ont pas été modifiés ni utilisés pour les tests.

## Livré

| Fonction | Implémentation et vérification |
|---|---|
| Inventaire, statistiques, recherche, catégories, doublons SHA-256, rapports | Conservés et tests de régression réussis ; sources locales/Android regroupées |
| Distribution Windows autonome | Scripts PyInstaller, ressources versionnées, installateur Inno Setup et CI Windows préparés ; **non compilés/non exécutés ici** |
| Première utilisation et paramètres persistants | Guide dans l’interface, configuration préservée, verrou d’instance ; test CLI avec redémarrage |
| Mise à jour et migration 0.1 | Migration additive, sauvegarde cohérente de l’ancien index, installateur à identifiant stable, guide de mise à jour manuelle |
| Sélection et confirmation avant écriture | Sélection par cases ou plan entier, diagnostic, validation COPIER expirant après 15 min et à usage unique |
| Copie réelle vérifiée | SHA-256 source/partiel/final, originaux conservés, mtime des nouvelles copies, progression et journal |
| Collisions | Aucun remplacement : contenu identique vérifié/réutilisé, sinon suffixe ; fichiers et répertoires existants préservés |
| Pause/reprise et erreurs | Prefixe relu et comparé, identité du support et des temporaires contrôlée, refus des sources modifiées/copies corrompues |
| Diagnostic non destructif | Volume/FS/capacité/espace/accès ; Windows : modèle et état via API/PowerShell ; Linux : montage réel et métadonnées. Aucun fichier d’essai créé |
| Android USB ADB | Racines publiques autorisées, médias par signature, inventaire, doublons croisés, aperçu d’images, plans et lecture en flux directement vers destination |
| Automatisation | Parcours périodiques des racines locales, classement dans l’index, doublons et plans ; jamais de validation ou copie automatiques |
| Interface | Appareils, Automatisation, Notifications, plans enregistrés, progression des copies, distinction simulation/en cours/vérifié |
| Fichiers sensibles | Motifs modifiables dans Règles, appliqués à l’analyse et aux anciennes propositions avant copie |

## Tests exécutés dans cette session Linux

- `python -m unittest discover -q` : **91 tests recensés, 89 réussis, 2 ignorés, aucun échec**.
  Les deux tests ignorés concernent de vraies jonctions NTFS source et destination, exécutables uniquement sous Windows.
- `python -m tests.browser_smoke` : Chromium réel, ajout de dossier, guide initial, analyse, recherche,
  fiche, doublons, simulation/export, sélection et validation d’une **copie réelle de 3 médias synthétiques**,
  diagnostic, cycle d’automatisation sans transfert, notifications, règles et historique.
  Mise en page bureau et mobile ; contrôles d’absence de débordement sur Appareils/Automatisation/Règles/Dossiers.
  Aucune erreur JavaScript/CSP constatée.
- `python -m tests.binary_smoke --source` : programme lancé en sous-processus, inventaire,
  copie vérifiée, originaux préservés, seconde instance refusée, redémarrage avec index/paramètres/transfert conservés.
  **Ce test a porté sur le CLI Python source, pas sur un `.exe` Windows.**
- Migration sur l’instance cloud existante : 5 fichiers de démonstration conservés depuis 0.1,
  sauvegarde SQLite préalable créée, automatisation désactivée et aucune copie lancée sur cette instance.

### Cas couverts par les tests synthétiques

- Contenus identiques et contenus de même taille différents ; doublons entre Android simulé et fichiers locaux.
- Contrôle de whitelist, dossiers système, applications, dépendances, liens symboliques, liens physiques,
  attribut reparse simulé et substitution d’ancêtre POSIX.
- Source changée après plan et pendant copie ; sources retirées ou devenues sensibles ; fichier disparu.
- Hash de copie erroné, préfixe partiel corrompu, permissions refusées, copie interrompue, disque plein injecté.
- Pause puis reprise avec un nouveau contrôleur, tâches interrompues au redémarrage.
- Destination remplacée, déconnexion simulée en cours de copie, reconnexion et reprise.
- Collision avec fichier différent, fichier identique et répertoire existant ; aucune perte de leur contenu.
- Chemins source et destination de plus de 300 caractères sous Linux.
- Diagnostic de dossier absent sans création, volume inconnu/lecture seule/inaccessible et espace insuffisant.
- Authentification HTTP, origines étrangères, rebinding Host, JSON invalide, CSV et aperçus protégés.
- Migration d’un index ancien avec conservation des lignes/sauvegarde ; configuration ancienne enrichie sans perte de racines.
- Planification persistante, intervalle, nouveaux fichiers, exclusions et absence d’appel automatique au moteur de copie.

### Android : portée exacte de la validation

Les commandes ADB sont **émulées**, avec identifiant `SYNTHETIC` et modèle `Oukitel_Test`.
Les tests de flux utilisent de vrais sous-processus Python produisant des octets binaires,
sans téléphone, câble, pilote ou `adb` réel. Ils vérifient le connecteur, le format des commandes,
les contrôles de chemins, l’indexation, les doublons, les plans et le moteur de transfert.
Cela ne prouve pas encore la compatibilité de l’ADB/USB et des outils shell avec l’Oukitel WP100 Titan.

## À vérifier sur les appareils et dans la CI Windows

1. Exécuter la compilation Windows : dépendances de construction, tests NTFS/handles, création du `.exe`
   et de l’installateur, installation, réinstallation, ressources statiques et démarrage sans Python utilisateur.
   Le workflow est fourni mais n’a pas tourné ici ; aucun `.exe`/installateur n’est présenté comme disponible ou testé.
2. Recette Windows 11 physique : ouverture du navigateur, chemins longs, fichiers réellement verrouillés,
   permissions, jonctions et gestion de fermeture pendant copie. La CI ne remplace pas cette recette.
3. Seagate : identification du vrai modèle/capacité/système de fichiers et état réel. Son ancien statut
   « unknown » n’a pas été résolu à distance. Aucune écriture n’est autorisée si les contrôles échouent.
4. Oukitel : pilote USB, autorisation de clé, commandes `find/stat/readlink/head/sha256sum`, déconnexion
   pendant copie et reprise sur le même disque. Aucune modification ni suppression Android n’est prévue.
5. Coupures USB et panne matérielle réelles, latences et volumes de plusieurs centaines de gigaoctets :
   seules des fautes simulées et de petits volumes ont été testés ici. Aucun benchmark de masse n’est revendiqué.

## Limites restantes

- Pas de signature des binaires, publication distante ou mise à jour automatique : procédure manuelle vérifiée par sommes prévues.
- Pas d’agent réseau sur le PC portable, de fusion entre PC, de pairage/chiffrement distant ni de serveur public.
- Pas de suppression, même après vérification ; **la copie ne libère pas automatiquement l’espace source**.
- Pas d’IA, EXIF/GPS, similarité perceptuelle, aperçu HEIC/vidéo ou restauration complète des ACL/attributs système.
- Le diagnostic ne remplace pas SMART ; santé matérielle non mesurée sous Linux.
  Les volumes Windows montés en sous-dossier, les partages réseau et les FS non pris en charge sont bloqués pour les copies.
- Surveillance par parcours périodique, application ouverte ; Android reste à analyse manuelle.
- Exports complets, listes ADB et très grands groupes de doublons encore en mémoire ; journal/plans/temporaires sans purge automatique.
- Les copies partielles ambiguës sont conservées. Une identité de montage impossible à prouver exige un nouveau plan.

La sécurité des sources est conservée : aucune primitive de suppression, formatage, réparation,
commande shell libre ou envoi de fichiers vers Android n’est exposée par l’application.
