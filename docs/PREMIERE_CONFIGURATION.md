# Première configuration — sans opération destructive

1. Ouvrez FileOrganizer depuis le menu Démarrer. Laissez sa fenêtre ouverte pendant l’utilisation.
2. Dans Vue d’ensemble, choisissez **Suivre le guide de démarrage**.
3. **Supports** : les volumes accessibles sont détectés en lecture seule. Diagnostiquez le Seagate
   et vérifiez son modèle, sa capacité et son système de fichiers. Unknown/RAW ou anomalie : arrêtez l’archivage.
4. **Dossiers** : choisissez Images, Vidéos, Documents ou un autre petit dossier personnel physique.
   Vous pouvez saisir un chemin et nommer le dossier/appareil. Ne choisissez pas un disque ou un profil entier.
   Les sources déjà configurées restent conservées ; leur retrait se gère dans Dossiers autorisés.
5. **Protections** : consultez les exclusions obligatoires et confirmez que les sources sont personnelles.
   Les liens, jonctions, programmes et données d’applications restent exclus.
6. **Destination** : choisissez un dossier existant, par exemple `E:\Archives`, et vérifiez son diagnostic.
   Le logiciel n’y crée aucun fichier pendant l’assistant. Vous pouvez commencer sans destination,
   uniquement pour l’inventaire. Si le volume est unknown, ne créez pas de dossier pour « essayer ».
7. **Catégories/règles** : adaptez les étiquettes, mots-clés, âges d’archivage et types. L’activation des
   analyses périodiques est facultative et ne déclenche jamais une copie ni un nettoyage automatique.
8. **Première analyse** : lancez l’analyse sans modifier vos fichiers. Attendez la fin sans erreur.
9. **Résultats** : consultez inventaire, doublons et propositions d’archivage. La simulation ne copie rien.

Aucun nettoyage n’est autorisé par cet assistant. L’autorisation d’un dossier comme personnel et
**autonome pour les propositions de nettoyage** se donne séparément dans Dossiers autorisés ou Appareils.
Elle ne retire aucun fichier ; une autre sélection et la saisie NETTOYER seront encore nécessaires.

Pour un premier essai, commencez avec les données synthétiques (`--demo`) ou un petit dossier contenant
quelques copies de test. N’utilisez pas directement votre unique exemplaire de fichiers irremplaçables.
Les dossiers OneDrive/espaces cloud contenant des reparse points ou placeholders ne sont pas suivis
implicitement : choisissez un emplacement physique accepté sans désactiver les contrôles.
