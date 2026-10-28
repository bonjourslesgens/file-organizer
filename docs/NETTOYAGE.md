# Nettoyer après archivage

## Conditions et limites

Une copie réussie ne suffit pas à autoriser un retrait. Il faut :

- Un dossier source toujours dans la liste blanche, déclaré séparément personnel et autonome.
- Une copie enregistrée `verified` ou `already_present`, jamais un élément incomplet/erreur.
- Un type reconnu par signature : images, vidéos, audio ou PDF. Les types ambigus, estimés par
  extension, archives, programmes et fichiers sensibles ne sont pas proposés.
- Une source encore identique au snapshot, avec le même SHA-256.
- Une archive accessible sur le volume/dossier attendu, ordinaire, sans liens, même taille et même SHA-256.

Les contrôles sont refaits lors de la proposition, de la confirmation et avant chaque action.
Une source modifiée, une copie corrompue, une destination indisponible/remplacée ou une autorisation
retirée bloque le retrait. Sous Windows, une source en lecture seule est exclue.

## Procédure

1. Dans Dossiers autorisés / Appareils, cochez l’autorisation de **propositions de nettoyage** seulement
   pour un dossier dont vous connaissez l’usage personnel indépendant des applications.
2. Après votre copie, ouvrez **Nettoyage** et choisissez le transfert concerné.
3. Cliquez sur **Revérifier et proposer un nettoyage**. Cette lecture complète peut être longue ; elle
   ne modifie aucun fichier. Les exclusions sont affichées avec leur motif.
4. Cochez les fichiers exacts souhaités. Une validation est limitée à 1 000 fichiers pour rester contrôlable.
5. Préparez le retrait. Examinez source, archive, méthode et avertissement de sauvegarde.
6. Saisissez **NETTOYER** et reconnaissez explicitement le risque de copie unique.
   Cette validation distincte de COPIER expire après cinq minutes et n’est utilisable qu’une fois.
7. Consultez les reçus et l’historique. Une interruption ne reprend jamais le retrait automatiquement.

Les autres exemplaires sur des appareils déconnectés ou dans des index anciens ne constituent pas
une preuve de sauvegarde indépendante. Par prudence, l’avertissement de copie unique s’applique à tous
les retraits. Après nettoyage, gardez une seconde sauvegarde des fichiers irremplaçables.

## Windows : Corbeille

Sur un volume source NTFS fixe où le mécanisme natif est disponible, FileOrganizer utilise
IFileOperation avec demande de recyclage et veto avant une suppression sans recyclage.
Il n’existe aucune fonction de suppression définitive ni de vidage de Corbeille dans le logiciel.

Pour lier l’action au bon objet, le fichier est ouvert sans partage d’écriture/suppression, son identité
et son hash sont revérifiés, puis il est renommé **par son handle** sous un nom unique dans le même dossier.
Le chemin retourné par Windows est vérifié avant de confier ce nom à la Corbeille.
Si le recyclage est refusé, le retour au nom d’origine est tenté sans remplacement.
En cas de conflit ou d’état incertain, le journal fournit les informations de récupération ; aucun
fichier existant n’est écrasé pour « réparer » l’opération.

L’entrée peut porter un préfixe `.FileOrganizer-retrait-…`. Pour restaurer : recherchez cette entrée
dans la Corbeille Windows, utilisez **Restaurer**, puis redonnez-lui le nom original indiqué dans le reçu.
Les reçus peuvent contenir un identifiant Shell virtuel lorsque Windows n’expose pas de chemin physique.
En cas de chemin de sécurité restant dans le dossier source, conservez-le et contrôlez son contenu avant remise en place.

**La mise à la Corbeille ne libère pas immédiatement l’espace du volume.** Après vérification de vos
sauvegardes, vous décidez vous-même, dans Windows, de vider les seules entrées concernées ou la Corbeille.
FileOrganizer n’effectue jamais ce vidage et ne supprime pas d’autres éléments déjà présents.
Si le recyclage n’est pas adapté au volume ou au système, une procédure manuelle est proposée.

## Android et autres procédures manuelles

Aucune suppression ADB n’est exécutée. Vous choisissez vous-même les fichiers dans Galerie/Fichiers,
puis confirmez **RETRAIT EFFECTUÉ**. L’application contrôle l’absence des sources et relit leurs archives.
Un téléphone hors ligne, un parent inaccessible ou une erreur de communication bloque la confirmation.
Voir [le guide Android](ANDROID.md).

Sur Linux, le logiciel prépare également une procédure manuelle : aucun backend de suppression
Linux de fichiers personnels n’est activé. Les tests du contrôleur utilisent une Corbeille synthétique isolée.
L’absence d’un fichier ne prouve pas un nombre d’octets effectivement libérés : il peut avoir été
mis à la Corbeille ou déplacé par vous. Le journal confirme ce qui a été observé, pas une purge.
