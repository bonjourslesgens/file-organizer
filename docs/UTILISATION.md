# Guide utilisateur 0.3

## Démarrage

Installez le binaire autonome sous Windows, ouvrez le menu Démarrer puis FileOrganizer.
L’interface fonctionne dans votre navigateur local, sans compte, abonnement ou service public.
Le PC portable utilise encore sa propre instance : les deux PC ne sont pas reliés par un agent distant.
Suivez [la première configuration](PREMIERE_CONFIGURATION.md) pour détecter les supports,
autoriser les sources et réaliser une première analyse **sans copie ni retrait**.

## Inventaire, exploration et doublons

Choisissez des dossiers personnels précis ; l’application refuse disques/profils entiers,
système, programmes, jeux, données applicatives, dépendances, liens/jonctions et noms sensibles.
Les espaces cloud/OneDrive utilisant des placeholders ne sont pas implicitement suivis.
Retirer un dossier de l’index ne retire jamais ses fichiers.

Analyser lit chaque fichier accepté par blocs. Les SHA-256 inchangés peuvent être réutilisés selon
les identifiants et dates ; Recalculer toutes les empreintes force une relecture complète.
Sous Windows, le cache emploie le véritable ChangeTime NTFS. Les résultats sont des instantanés,
pas une garantie de présence future. Une source inaccessible garde son inventaire non vérifié.

L’Explorateur offre recherche, filtres, fiches et export CSV. Les images JPEG/PNG/GIF/WebP inchangées,
de 10 Mio au maximum, peuvent être prévisualisées après contrôle. Il n’existe pas encore de lecteur
vidéo ni d’aperçu HEIC. Les types estimés par extension sont distingués des signatures reconnues.
Les étiquettes utilisent noms et chemins ; le contenu n’est pas classé par IA.

Doublons regroupe les contenus exacts, y compris médias Android et sources locales, par SHA-256.
Les métadonnées différentes et similitudes visuelles ne suffisent pas. La copie à conserver est une
suggestion, sans autorisation de retrait. Le volume redondant n’est pas de l’espace déjà libéré.

## Archivage

Diagnostiquez le [Seagate](SEAGATE.md) avant toute écriture. Un dossier de base existant et sain
est requis pour les copies ; la simulation peut être faite sans y accéder.
Règles propose par défaut photos de plus de 365 jours et vidéos de plus de 183 jours, selon la date
**de modification UTC**, sans prétendre lire la date EXIF de prise de vue.
La destination est organisée par appareil/dossier/type/année/mois, avec un groupe DJI pour ces vidéos.

Simulez, consultez les chemins puis sélectionnez des fichiers ou tout le plan. Préparer la copie
vérifie les sources, le volume, l’espace avec réserve de 16 Mio, les droits et le système de fichiers.
Confirmez la destination et saisissez **COPIER**. Cette validation expire en 15 minutes, est à usage
unique et ne permet aucun nettoyage. La source reste intacte lors de cette phase.

Les octets vont dans un `.partial` du support cible. Le SHA-256 du flux source, du temporaire puis
du fichier publié est vérifié. Une collision est résolue sans remplacement ; un contenu existant
n’est réutilisé que s’il est confirmé identique. FAT32 refuse les fichiers de plus de 4 Gio.
La date de modification est préservée sur les nouvelles copies, pas toutes les ACL/attributs d’une image disque.

## Pause et reprise

Mettre en pause conserve les temporaires. Une reprise demande **REPRENDRE**, contrôle de nouveau
le même volume/dossier et compare chaque octet du préfixe à la source. Un temporaire ambigu/corrompu
n’est ni tronqué ni réadopté pour forcer une réussite. Une modification de source exige un nouveau plan.
Après déconnexion USB, rebranchez le même support ; une autre unité sous la même lettre est refusée.
Si un montage sans identifiant stable a changé, refaites diagnostic et plan. Les erreurs restent au journal.

## Nettoyage après archivage

Le retrait a son propre parcours : autorisation du dossier comme personnel/autonome, copies réussies,
relecture source/archive, sélection, avertissement de copie unique et saisie **NETTOYER**.
Les types ambigus, les changements et les destinations indisponibles excluent les propositions.
Windows privilégie la Corbeille native lorsqu’elle est adaptée ; Android reste entièrement en action manuelle.
FileOrganizer ne vide jamais de Corbeille et n’effectue pas de suppression définitive générique.

Après une action manuelle, **RETRAIT EFFECTUÉ** permet de contrôler la source absente et l’archive intacte.
Une erreur ADB, un parent inaccessible ou une archive absente bloque la confirmation.
L’absence d’un chemin ne prouve pas des octets libérés : une Corbeille peut encore contenir le fichier.
Consultez [le guide de nettoyage et restauration](NETTOYAGE.md) avant votre premier retrait.

## Automatisation, erreurs et rapports

Les analyses/simulations périodiques fonctionnent seulement application ouverte. Elles classent les
nouveaux fichiers dans l’index et génèrent des plans, jamais des validations COPIER/NETTOYER.
Un cycle attend les opérations actives. Les règles et motifs sensibles se modifient sans programmation.
Les exclusions système restent obligatoires ; les motifs de noms ne sont pas une analyse exhaustive de secrets.

Appareils affiche diagnostic et connexion USB Android. Notifications regroupe erreurs, refus et réussites ;
Marquer comme lu ne supprime pas l’audit. Historique conserve les opérations. Les reçus de nettoyage
et de récupération restent distincts des confirmations de copie.

Rapport exporte un bilan JSON et l’Explorateur un CSV. Ces fichiers contiennent vos chemins personnels :
choisissez où vous les partagez. La configuration JSON reste éditable, application arrêtée et sauvegardée.
Les compteurs de capacité d’un même disque ne doivent pas être additionnés pour chaque dossier.

[Android](ANDROID.md) · [Seagate](SEAGATE.md) · [Installation/mise à jour](INSTALLATION.md) · [Bilan](BILAN.md)
