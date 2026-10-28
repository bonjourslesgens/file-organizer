# Vérifier le Seagate Expansion 5 To

Son ancien statut « unknown » n’est pas considéré comme résolu. Aucun accès physique au disque
de l’utilisateur n’a été réalisé depuis le cloud.

1. Branchez le disque avec une connexion USB stable.
2. Dans Appareils ou l’assistant, diagnostiquez d’abord le **volume**, par exemple `E:\`.
   Ce diagnostic ne crée aucun fichier et ne lance aucune réparation.
3. Vérifiez le modèle, la capacité (5 To décimaux correspondent à environ 4,55 Tio), le système de
   fichiers, l’espace disponible et l’état. Une lettre de lecteur seule n’identifie pas un disque.
4. Sur Windows, le volume et le disque doivent être identifiables, sains et en ligne. Une absence
   d’information bloque les écritures. Le diagnostic Windows explicite rafraîchit aussi l’état disque.
5. Si Unknown/RAW, partition absente, erreurs, lecture seule ou demande d’initialisation : **ne rien
   formater ni initialiser**. Préservez le support avant de chercher une réparation/récupération.
6. Seulement après un diagnostic favorable, utilisez un dossier personnel d’archives existant
   (ou créez-le vous-même depuis Windows). Sélectionnez ce dossier, pas la racine entière, pour les copies.
7. Faites une première simulation puis une petite copie de données de test. Comparez le statut
   final SHA-256 et testez une pause/reprise avant un transfert volumineux.

Pour consulter manuellement, sans modifier le support :

```powershell
Get-Disk | Select Number,FriendlyName,Size,PartitionStyle,OperationalStatus,HealthStatus,IsReadOnly
Get-Volume | Select DriveLetter,FileSystemLabel,FileSystem,HealthStatus,OperationalStatus,Size,SizeRemaining
```

Le diagnostic logique ne remplace pas SMART ni un diagnostic matériel. Aucun formatage, initialisation,
CHKDSK de réparation ou commande de remount n’est proposé par l’application.
Les volumes Windows montés en sous-dossier, partages réseau et FS non supportés restent bloqués.

Après déconnexion, une copie/reprise ou un nettoyage doit retrouver le même volume **et** le même dossier.
Une autre unité branchée sous la même lettre ne suffit pas. Ne retirez pas le disque pendant le nettoyage.
Un fichier unique sur le Seagate n’est pas une sauvegarde indépendante ; gardez une autre copie des
éléments irremplaçables avant de retirer la source ou de vider sa Corbeille.
