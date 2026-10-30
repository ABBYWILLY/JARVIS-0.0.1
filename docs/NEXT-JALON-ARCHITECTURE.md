# Prochain jalon — proposition, aucune capacité ajoutée

Ce document prépare l'agent Windows sécurisé et la vision locale. Le LOT 7
n'installe aucun modèle visuel, n'ajoute aucune permission et n'exécute aucun
outil proposé par Ollama. Une réponse contenant du code reste du texte.

## Points d'extension existants

| Existant | Réutilisation future |
| --- | --- |
| `ollama.InferenceProvider`, événements versionnés | adaptateur de proposition d'actions structuré, jamais exécution depuis un `chunk` |
| `worker.Worker`, isolation `spawn`, IPC bornée | garder l'inférence séparée d'un futur exécuteur d'outils |
| `App.send/cancel/poll`, générations audio/visuelles | identifiant de tâche explicite ; interruption et rejet des résultats anciens |
| `ContextBuilder`, C1, `ContextResult.sources/stats` | contexte borné, politique manuelle prioritaire, résultats d'outils avec provenance |
| `Store`, `MemoryRepository` et sauvegardes | préférences existantes ; éventuelles tables d'actions additives et sauvegardées |
| `CognitiveState` et inspecteur de contexte | afficher ce qui a été proposé, autorisé et réellement observé ; aucun raisonnement caché prétendu |
| `GpuSettings`/profils, F9 et benchmarks LOT 7 | mesurer puis arbitrer le budget graphique/inférence ; Canvas reste un vrai choix |

## Frontières minimales proposées

1. **Registre d'outils** : identifiant stable, schéma d'arguments, effets possibles,
   limites de durée/taille, périmètre fichiers/applications et stratégie de
   vérification. Refuser tout outil inconnu et tous arguments non conformes.
2. **Politique de permissions hors LLM** : décision déterministe fondée sur
   l'utilisateur et le périmètre, jamais sur le ton, une couleur PRESENCE ou une
   instruction générée. Avant action sensible : aperçu concret et confirmation
   explicite, liée aux arguments validés ; modification ⇒ nouvelle confirmation.
3. **Exécuteur isolé** : processus distinct, concurrence limitée, timeout,
   annulation de l'arbre, résultat structuré et tailles bornées. Un processus
   `spawn` seul n'est **pas** un bac à sable de sécurité : concevoir et tester les
   restrictions Windows/ACL nécessaires avant d'exposer une opération sensible.
4. **Journal d'actions distinct** : tâche/action, demande, décision, début/fin,
   résultat, annulation et preuve de vérification. Minimiser/rédiger les données
   privées ; ne pas utiliser l'archive de conversation comme preuve d'exécution.
   Une commande terminée n'établit pas que l'objectif utilisateur est atteint.
5. **Orchestrateur borné** : plan explicite et modifiable, maximum d'étapes,
   temps/tokens, checkpoints, politiques d'idempotence et reprise vérifiée.
   Aucun nouvel essai destructif automatique ; Stop garde la priorité.

## Vision ponctuelle et budget matériel

Un fichier ou une capture doit être fourni/autorisé explicitement, avec zone
visible, durée de conservation et action attendue. Pas de capture de fond. Le
contenu d'image/document reste une donnée non fiable et ne donne aucune permission.
Prévoir un adaptateur multimodal local optionnel, chargé à la demande : pas de
nouveau modèle obligatoire ni de téléchargement silencieux.

L'admission d'une tâche visuelle doit partager un budget avec Ollama et OpenGL,
avec marges mesurées pour les pics et refus explicable plutôt qu'OOM répétées.
Aujourd'hui Whisper utilise CPU/int8 et Piper CPU ; ne pas leur attribuer une
VRAM imaginaire. La télémétrie GPU globale n'est pas une attribution précise par
processus. Si l'information manque, proposer un mode séquentiel explicite, la
décharge autorisée du modèle temporaire ou Canvas, sans effacer le choix utilisateur.

## Conditions avant implémentation

- Recette physique du LOT 7 sur Windows 11/RTX 3070, Ollama + voix + GPU ensemble.
- Premier outil étroit et vérifiable en lecture seule, menace et permissions
  définies, tests d'injection, chemins, timeout, annulation et redémarrage.
- Premier essai visuel sur fichier choisi, modèle/licence/taille et budget
  annoncés avant téléchargement volumineux, sans capture générale de l'écran.
- Conservation des lots C1/voix/HUD, SQLite, profils et alternatives Canvas/GPU.

Ces éléments sont une proposition de transition, pas des fonctions livrées.
