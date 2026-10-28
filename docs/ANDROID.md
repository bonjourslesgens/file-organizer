# Connecter l’Oukitel WP100 Titan

La compatibilité USB/Oukitel physique reste à vérifier. Les tests du connecteur utilisent un appareil
ADB simulé et des flux binaires de test ; ils ne remplacent pas un essai sur votre téléphone.

1. Téléchargez les [Platform Tools officiels Google](https://developer.android.com/tools/releases/platform-tools).
   Décompressez-les sur le PC ; FileOrganizer ne les installe pas silencieusement.
2. Branchez un câble USB de données. Un pilote OEM Windows peut être nécessaire.
3. Si vous choisissez ADB, activez vous-même les options développeur et le débogage USB sur Android.
   Reconnaissez puis autorisez la clé du PC sur le téléphone. L’application ne change pas ces réglages.
4. Dans **Appareils**, indiquez le chemin de `adb.exe` ou utilisez celui présent dans PATH.
5. Cliquez sur **Détecter les appareils USB**. Unauthorized : validez la clé ; aucun appareil : vérifiez
   câble/pilote/mode USB ; offline/erreur de communication : reconnectez avant toute opération.
6. Autorisez explicitement DCIM, Pictures, Movies ou Download de l’espace utilisateur. Analysez puis
   consultez l’inventaire. Seuls les médias reconnus par signature sont retenus.
7. Simulez vers votre dossier Seagate préalablement diagnostiqué, puis sélectionnez et validez COPIER.
   Le flux va directement vers un temporaire sur la destination, sans staging massif sur le SSD.
8. Après copie vérifiée, vous pouvez autoriser les **propositions de retrait manuel** pour cette source
   dans Appareils. Cela ne déclenche aucune suppression.

Android/data, obb, media, dossiers privés, paquets d’applications, dossiers cachés/nomedia, projets et
liens redirigés sont exclus. Une image n’est pas considérée indépendante d’une application du seul
fait de son extension. Les commandes `root`, `remount`, `push`, `tcpip`, `connect`, `rm`, `rmdir` et
les suppressions génériques ne sont pas des fonctions du connecteur.

## Retrait manuel après archivage

Dans Nettoyage, revérifiez les copies, choisissez les fichiers, reconnaissez l’avertissement de copie
unique et confirmez NETTOYER. Pour Android, cette confirmation prépare seulement une procédure :

- Contrôlez votre archive accessible et votre sauvegarde indépendante.
- Sur le téléphone, ouvrez Galerie ou Fichiers, identifiez **chaque fichier exact** indiqué et utilisez
  vous-même la Corbeille/suppression du système. Ne sélectionnez pas un dossier entier par raccourci.
- Dans FileOrganizer, choisissez **J’ai effectué le retrait manuel** puis saisissez **RETRAIT EFFECTUÉ**.
- Le logiciel relit le SHA-256 de l’archive et vérifie, en lecture seule, que chaque source est absente
  et que son dossier parent est accessible/non redirigé. Une erreur ADB n’est jamais interprétée comme une absence.

Une Corbeille Android peut continuer à occuper l’espace jusqu’à sa purge, qui reste votre décision.
Aucune commande ADB de suppression n’est envoyée, même après confirmation.
Après une déconnexion ou une modification de source, refaites les vérifications avant toute action.
