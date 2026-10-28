# Première utilisation et opérations

## 1. Démarrer et autoriser une source

Ouvrez FileOrganizer et suivez **Première utilisation → guide de démarrage**.
Dans Dossiers autorisés, copiez le chemin complet d’un petit dossier personnel (Images, Vidéos,
Documents), nommez-le et cliquez sur Autoriser. Aucun disque entier ni profil entier n’est accepté.
Aucun dossier personnel n’est ajouté automatiquement. Le PC portable doit, pour l’instant, utiliser
sa propre instance locale : aucun agent distant ni fusion entre les deux PC n’est livré.

Les dossiers système, applications, jeux, dépendances, projets, répertoires cachés et fichiers
applicatifs sont exclus. Liens symboliques, jonctions et fichiers à plusieurs liens physiques sont
refusés. Les placeholders/jonctions OneDrive ne sont pas implicitement suivis. Un média dans une
application n’est jamais une preuve qu’il peut être supprimé.
Retirer une autorisation enlève uniquement les entrées d’index concernées, jamais les fichiers.

## 2. Analyser et consulter

Cliquez sur Analyser mes dossiers. La première analyse lit chaque fichier accepté intégralement
pour SHA-256 ; les suivantes utilisent le cache si l’identité, la taille et les dates fines n’ont
pas changé. Cochez **Recalculer toutes les empreintes** pour relire tous les contenus, notamment
après un outil conservant artificiellement les dates et tailles. Arrêter conserve le travail validé.

Une source déconnectée garde son index mais les entrées non revérifiées sont exclues des doublons
confirmés et des propositions. Réanalysez après reconnexion. Les résultats sont des instantanés ;
ils ne prouvent pas que les fichiers n’ont pas changé depuis la dernière analyse.

L’Explorateur propose recherche, filtres par type/étiquette, fiche de fichier et CSV. Les images
PNG/JPEG/GIF/WebP indexées et inchangées, jusqu’à 10 Mio, disposent d’un aperçu authentifié,
y compris via Android. HEIC et les vidéos ne disposent pas de lecteur intégré.
Les types reconnus par signature se distinguent des estimations par extension.
Les étiquettes se basent sur le nom/chemin, pas une compréhension IA du contenu.

Doublons regroupe les contenus strictement égaux selon leur SHA-256, y compris entre médias
Android et fichiers locaux. La copie la plus ancienne est une **suggestion**, pas une sélection
de suppression. Aucune suppression n’est possible. Rapport exporte un bilan JSON.
Les capacités de plusieurs dossiers sur un même volume ne doivent pas être additionnées.

## 3. Diagnostiquer le Seagate avant toute écriture

Dans **Appareils**, saisissez le chemin du volume (ex. `E:\`) et cliquez sur Diagnostiquer.
L’opération interroge uniquement les informations du système : aucun fichier de test n’est créé.
Vérifiez modèle, capacité, système de fichiers, espace et anomalies. La lettre n’est pas une identité
suffisante. Sur Windows, l’état du disque et du volume doit pouvoir être lu et être sain/en ligne.
Sur Linux, la santé matérielle SMART reste indiquée non mesurée.

Si le volume est Unknown/RAW, inaccessible, en lecture seule ou déclaré non sain : arrêtez.
Ne formatez, n’initialisez et ne réparez pas automatiquement. Préservez les données et, si nécessaire,
faites réaliser un diagnostic matériel/récupération. Le logiciel ne fournit aucune action de formatage.
Un contrôle logique favorable ne garantit pas l’absence de panne future.

Après identification favorable, choisissez/créez vous-même un dossier personnel d’archives sur ce volume,
puis utilisez son chemin (ex. `E:\Archives`). Le dossier de base doit exister ; les sous-dossiers
chronologiques ne sont créés qu’après validation de la copie.
Ne sélectionnez pas un dossier source, un dossier qui le contient, ni le stockage interne de l’application.

## 4. Simuler et sélectionner

Dans Archivage, renseignez la destination et simulez. Cette étape ne touche pas la destination.
Les règles initiales proposent photos de plus de 365 jours et vidéos de plus de 183 jours, en utilisant
la date de modification UTC. Les vidéos dont le nom commence par DJI sont séparées.
Modifiez les règles dans Règles. Les documents actifs restent en place sauf règle explicite.

Le plan décrit `Destination / Appareil / Dossier / Type / Année / Mois / Nom`.
Cochez les éléments souhaités ou sélectionnez tout le plan. Sélectionner puis décocher une ligne après
« tout le plan » ramène la sélection aux cases visibles : le nombre affiché et la validation indiquent
la sélection exacte. Les noms Windows réservés sont neutralisés. Un plan enregistré est un instantané,
jamais une autorisation permanente. Les anciens plans se retrouvent dans Archivage.

## 5. Valider une copie réelle

Cliquez sur Préparer la copie de la sélection. Le logiciel contrôle : sources toujours autorisées
et inchangées, destination locale identifiée, système de fichiers supporté, droits, état, espace
(et réserve de 16 Mio). FAT32 refuse les fichiers de plus de 4 Gio. Les sources retirées/sensibles
et les anciens plans sans identité sont bloqués.

Examinez le nombre, le volume, le chemin et le diagnostic. Confirmez que vous reconnaissez ce disque,
puis saisissez **COPIER** et démarrez. Cette validation ne vaut que pour cette sélection, expire après
15 minutes et ne peut servir qu’une fois. Ce bouton écrit réellement sur la destination.

Le traitement utilise un fichier `.fileorganizer-….partial` **sur la destination** :

1. Copie du contenu en blocs, avec contrôle des sources et du volume.
2. Comparaison du SHA-256 de la source lue au plan, puis du fichier partiel.
3. Publication atomique sans remplacer un fichier existant.
4. En cas de collision, réutilisation seulement si le contenu existant est vérifié identique,
   sinon ajout d’un suffixe `__copieN`. Aucun écrasement silencieux.
5. Nouvelle vérification du fichier final, journalisation et statut terminé.

La date de modification est conservée sur les nouvelles copies. ACL, propriétaire, flux NTFS
alternatifs, attributs étendus et date de création ne sont pas reproduits comme une image disque.
La validation ne supprime jamais un original. **Copier ne libère pas d’espace sur la source.**

## 6. Pause, erreur, déconnexion et reprise

Archivage distingue les simulations et les transferts réels : en cours, terminé/vérifié, pause,
interrompu ou bloqué. Les détails montrent les fichiers et erreurs. Le centre Notifications regroupe
les refus, erreurs et réussites ; Marquer comme lu ne retire pas le journal.

Mettre en pause conserve les fichiers partiels. Après une interruption ou un redémarrage, choisissez
Préparer la reprise et saisissez **REPRENDRE**. Le logiciel vérifie de nouveau le disque, les droits,
l’espace et les sources, puis compare intégralement le préfixe partiel à la source avant de continuer.
Un préfixe corrompu n’est ni tronqué ni réutilisé. Une source modifiée exige une nouvelle analyse/simulation.

Une déconnexion bloque le traitement. Rebranchez le **même** disque au même emplacement avant reprise.
Si son identité ne peut plus être prouvée (notamment montage Linux sans UUID recréé), la reprise est
refusée : faites un nouveau diagnostic et un nouveau plan. Les temporaires ambigus restent conservés,
sans nettoyage automatique. Ne retirez pas les `.partial` d’un transfert encore actif.
Un fichier déjà publié juste avant une coupure sera reconnu par contenu lors de la reprise.

## 7. Connecter l’Oukitel

Installez les Platform Tools officiels et préparez l’USB comme décrit dans Installation.
Dans Appareils, indiquez `adb.exe` puis Détecter les appareils USB. Un état unauthorized nécessite
votre accord sur le téléphone ; une liste vide peut indiquer câble, mode USB ou pilote absent.

Autorisez explicitement un dossier parmi DCIM, Pictures, Movies et Download de l’espace utilisateur.
Les dossiers Android/data, obb, media, les chemins système, les paquets d’applications, les dossiers
cachés/`.nomedia`, projets et liens redirigés sont exclus. Seuls les médias reconnus par signature sont
indexés. Aucun dossier privé ne peut être autorisé en saisissant un autre chemin.

Analysez, consultez l’inventaire puis simulez les médias Android vers votre destination.
Le plan rejoint Archivage et suit la même validation COPIER. Le flux va du téléphone à la destination,
sans fichier intermédiaire massif sur le SSD. La reprise relit le préfixe depuis Android : elle consomme
à nouveau cette bande passante, mais pas l’espace SSD. SHA-256 est vérifié côté téléphone et destination.
Il n’existe aucune commande de suppression sur Android. Révoquer une autorisation ne touche pas au téléphone.
La compatibilité USB, `stat`, `find`, `readlink`, `head` et `sha256sum` doit être testée sur votre Android.

## 8. Automatiser sans perdre le contrôle

Dans Automatisation, activez les analyses périodiques des dossiers locaux, choisissez un intervalle
(30 secondes à 24 heures) et, facultativement, une destination de simulation. Les règles classent les
nouveaux fichiers dans l’index, réévaluent l’âge et recalculent les groupes de doublons.
Il s’agit d’un parcours périodique avec cache, pas d’une surveillance système instantanée.
L’application doit rester ouverte. Aucun service, tâche Windows ou copie au démarrage n’est créé.
Un cycle attend si une analyse ou un transfert est déjà en cours.

Les cycles génèrent des **plans**, accessibles dans leur historique. Ils ne valident jamais COPIER.
L’archivage réel reste manuel. Android n’est pas analysé automatiquement en arrière-plan.

Dans Règles, configurez les types/âges, les étiquettes et les motifs sensibles (un par ligne,
`*` pour plusieurs caractères). Les exclusions système restent obligatoires. Les motifs sensibles
portent sur les noms/chemins : ce n’est pas une détection exhaustive de secrets dans le contenu.
Une nouvelle exclusion s’applique aux copies même si le plan est antérieur ; relancez l’analyse
pour nettoyer l’inventaire. Les paramètres JSON restent modifiables application arrêtée.
