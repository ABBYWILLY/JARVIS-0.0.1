# JARVIS 0.0.1 — LOT 7
## Optimisation globale, stabilité, performances et préparation au prochain jalon

**Dépôt :** `ABBYWILLY/JARVIS-0.0.1`
**Branche de travail :** `feat/jalon-2-voice-presence`
**Dernier commit vérifié :** `19c003a` — vérifier le HEAD avant de commencer.

**INTERDICTION DE MODIFIER `main`.**

# 0 — MISSION

Les lots précédents sont désormais suffisamment matures pour entreprendre l'optimisation globale.

État approuvé :
- PRESENCE GPU 3.1 : utilisateur satisfait de la fluidité, de la netteté, des animations et du toggle 2D/2.5D.
- LOT 4 : voix naturelle V1 jugée satisfaisante.
- LOT 5 : Cognitive HUD 1.0 livré, tests et CI finales verts.
- COMMAND OS, mémoire SQLite/FTS5, cerveau C1, Ollama, Whisper et Piper doivent être conservés.

Le LOT 7 doit rendre l'ensemble **plus stable, plus léger, plus mesurable, plus résilient et prêt pour le prochain jalon**.

Ne pas ajouter de fonctionnalités agentiques, de contrôle Windows ou de vision dans cette mission.

Ne pas réinventer les lots précédents.

Ne pas modifier la direction artistique approuvée.

## Matériel cible

- Windows 11.
- NVIDIA RTX 3070, 8 Go VRAM.
- Ollama local / modèles Qwen.
- Whisper / Silero VAD.
- Piper TTS.
- PRESENCE ModernGL 2.5D.
- Alternative Canvas 2D permanente.

JARVIS doit pouvoir utiliser simultanément ces composants sans que le visualiseur monopolise le GPU au détriment de l'inférence.

# 1 — AUDIT INITIAL

Inspecter l'architecture et la documentation existantes.

Identifier les budgets CPU, RAM, VRAM, les fréquences de mise à jour, les files, les threads, les processus et les mécanismes de fermeture.

Réutiliser en priorité :
- Les diagnostics vocaux.
- Les mesures Ollama.
- F9 et les statistiques GPU.
- Les métriques existantes.
- Les tests automatiques.
- Les outils de benchmark déjà présents.

Établir une référence mesurée avant modification.

Ne pas déclarer une optimisation nécessaire sans identifier un problème réel ou un risque démontrable.

Documenter :
1. Situation initiale.
2. Problèmes confirmés.
3. Risques potentiels.
4. Corrections retenues.
5. Corrections rejetées avec justification.

# 2 — SOUS-LOT 7A : OBSERVABILITÉ ET BENCHMARKS REPRODUCTIBLES

Créer une procédure de benchmark locale, utilisable sur Windows, capable de comparer plusieurs configurations.

Scénarios :
- JARVIS au repos.
- COMMAND OS seul.
- PRESENCE Canvas.
- PRESENCE GPU Éco.
- PRESENCE GPU Équilibré.
- PRESENCE GPU Cinématique.
- Ollama sans GPU visualiseur.
- Ollama avec PRESENCE GPU.
- Synthèse Piper.
- Capture VAD / Whisper.
- Conversation complète micro → STT → Ollama → TTS.
- Interruptions et changement 2D/2.5D.

Mesures selon disponibilité :
- CPU par processus.
- RAM par processus.
- Utilisation GPU.
- VRAM attribuable.
- FPS réels et P95/P99 de frame time.
- Temps de transcription.
- TTFT Ollama.
- Tokens/seconde.
- Temps jusqu'au premier audio estimé.
- Temps de synthèse.
- Latence de bout en bout.
- Consommation au repos.
- Temps de démarrage et de fermeture.

Ne pas confondre estimation DAC et latence acoustique.

Les mesures doivent préciser les conditions : modèle, contexte, profil graphique, résolution, DPI, périphérique audio et état du cache.

Aucun téléchargement automatique de modèle.

Prévoir des résultats JSON/CSV et un résumé Markdown avec comparaison avant/après.

Ne pas enregistrer de conversation privée ou PCM brut par défaut.

# 3 — SOUS-LOT 7B : OPTIMISATION CPU, RAM ET VRAM

Examiner les coûts réellement identifiés.

Priorités :

**GPU**
- Préserver une fluidité proche de 60 FPS sur le matériel cible quand la charge le permet.
- Vérifier que le renderer ne provoque pas de famine de ressources pour Ollama.
- Optimiser les ressources graphiques inutilisées.
- Libérer correctement les buffers, textures et contextes.
- Préserver les profils et l'adaptation de qualité existants.
- Ne pas augmenter automatiquement la résolution interne lorsque le modèle local nécessite davantage de ressources.

**CPU**
- Supprimer les boucles inutiles et les réveils excessifs.
- Vérifier les travaux exécutés sur le thread Tkinter.
- Éviter les recomputations de mise en page ou de HUD sans changement réel.
- Contrôler les workers, les timers et les callbacks après annulation.

**RAM**
- Examiner l'évolution mémoire pendant les longues conversations.
- Contrôler les files audio et les buffers PCM.
- Vérifier les caches de rendu et de Rich Text.
- Éviter de dupliquer les modèles, les historiques et les textes volumineux.
- Détecter les ressources conservées après fermeture des fenêtres.

**SQLite**
- Mesurer les requêtes réellement lentes.
- Vérifier l'indexation FTS5 et les accès concurrents.
- Conserver la provenance et l'intégrité des archives.
- Éviter toute migration destructive.

Règle fondamentale : **une modification n'est considérée comme une optimisation que si elle améliore une mesure pertinente ou élimine un défaut démontré sans régression majeure.**

# 4 — SOUS-LOT 7C : STABILITÉ ET RÉSILIENCE

Tester les situations dégradées :

- Ollama indisponible.
- Modèle non chargé.
- Modèle trop volumineux pour les ressources disponibles.
- Déconnexion du microphone.
- Changement de sortie audio.
- Échec de Piper.
- Erreur Whisper.
- Arrêt brutal du processus GPU.
- Pilote graphique incompatible.
- Fichiers de préférences ou données invalides.
- Annulations répétées.
- Plusieurs bascules 2D/2.5D.
- Fermeture pendant génération ou lecture.
- Redémarrage après interruption.
- Réponses Ollama longues.
- Historique conversationnel volumineux.

Vérifier :
- Aucune fenêtre gelée.
- Aucune file illimitée.
- Aucun thread orphelin.
- Aucun processus enfant persistant après fermeture normale.
- Aucun appel audio concurrent incontrôlé.
- Aucune écriture SQLite corrompue.
- Aucune relance de génération non demandée.
- Aucun ancien événement visuel réinjecté après annulation.

Préserver les fragments de réponse conformément aux mécanismes existants.

Les erreurs doivent être compréhensibles et récupérables lorsqu'une récupération est possible.

# 5 — SOUS-LOT 7D : QUALITÉ DE L'EXPÉRIENCE CONVERSATIONNELLE

Ne pas remplacer Whisper, Piper ni Ollama.

Examiner uniquement les problèmes observables :
- Temps morts entre transcription et génération.
- Attente entre premier texte et première parole.
- Saccades audio.
- Retard de sous-titrage.
- Délais d'interruption.
- Synchronisation des états cognitifs.
- Démarrage lent de la génération.
- Blocages pendant une réponse longue.
- Réactivité des actions contextuelles.

Réduire les latences lorsque c'est possible sans compromettre les réponses.

Préserver :
- Les profils vocaux du LOT 4.
- Les commandes Stop / Répète / Reprends / Continue.
- Les fonctions de sélection du LOT 5.
- Les politiques C1.
- Les états réels du Cognitive HUD.

Ne pas générer des réponses plus courtes artificiellement pour améliorer les chiffres.

Ne pas réduire les budgets de contexte sans justification et sans préserver le choix utilisateur.

# 6 — SOUS-LOT 7E : VALIDATION SUR WINDOWS ET PACKAGING

Vérifier le packaging complet :

- `Jarvis.exe`.
- Dépendances voix et GPU optionnelles.
- Processus GPU secondaire.
- Ressources embarquées.
- Chargement Piper.
- SQLite.
- Préférences existantes.
- Écrans HiDPI.
- Raccourcis.
- Fallback Canvas.
- Démarrage sans Ollama.
- Démarrage sans microphone.
- Absence de téléchargement silencieux.
- Fermeture propre.

Vérifier qu'une mise à jour de l'EXE conserve les données et préférences utilisateur.

Documenter les limites de l'EXE non signé.

Produire une recette Windows précise pour les tests impossibles en CI Linux.

La CI Windows verte confirme le build et les tests automatisés, **pas les performances physiques sur RTX 3070**.

# 7 — SOUS-LOT 7F : BILAN ET PRÉPARATION DE L'ARCHITECTURE FUTURE

Préparer uniquement la documentation du prochain jalon :

**Agent Windows sécurisé + vision multimodale locale + orchestration agentique.**

Ne pas implémenter ces fonctionnalités maintenant.

Identifier les points d'extension existants pour :
- Registre d'outils.
- Permissions et confirmations.
- Exécution bornée.
- Journal d'actions.
- Analyse d'images ou captures d'écran.
- Chargement ponctuel d'un modèle visuel.
- Gestion des conflits de VRAM.
- Planification de tâches à étapes.
- Interruption et reprise.
- Isolation des opérations sensibles.

Proposer une architecture minimale et extensible.

Aucun modèle visuel téléchargé.

Aucune permission système ajoutée.

Aucun accès Windows élargi.

# 8 — TESTS OBLIGATOIRES

Exécuter :
- Tests ciblés par sous-lot.
- Suite complète existante.
- Tests de non-régression du cerveau C1 et de la mémoire.
- Tests voix / interruptions.
- Tests Rich Text et Cognitive HUD.
- Tests PRESENCE 2D / GPU.
- Tests de fermeture et de reprise.
- Tests SQLite.
- Tests de packaging Windows.
- Benchmarks comparatifs disponibles.

Ajouter des tests de longue durée bornés pour vérifier :
- Stabilité de la RAM.
- Absence de croissance incontrôlée des files.
- Fermeture des processus.
- Répétition des cycles de conversation.
- Bascule répétée des moteurs.

Ne pas déclarer « aucune fuite mémoire » sur la seule base d'un essai court.

Ne pas inventer de chiffres.

Pour les mesures indisponibles, fournir les commandes et la procédure permettant de les obtenir sur le PC utilisateur.

# 9 — MÉTHODE DE LIVRAISON

Exécuter successivement :

**7A — Audit et instrumentation**

**7B — Optimisations mesurées**

**7C — Robustesse et récupération**

**7D — Latence et expérience conversationnelle**

**7E — Validation Windows et packaging**

**7F — Rapport final et architecture du prochain jalon**

Chaque étape doit produire :
- Commit distinct.
- Tests ciblés.
- Mesures ou justification technique.
- Documentation.
- Absence de régression constatée.

Push sur `feat/jalon-2-voice-presence`.

Ne jamais modifier `main`.

Après chaque phase, vérifier les CI concernées.

La dernière phase exige :
- Suite complète.
- CI Windows au SHA final.
- Rapport comparatif.
- Synthèse des défauts corrigés.
- Liste des risques résiduels.
- Guide de test RTX 3070.
- Documentation de transition vers le prochain jalon.

# 10 — CRITÈRES D'ACCEPTATION

Le LOT 7 sera livré côté logiciel si :

1. Les performances initiales et finales sont documentées.
2. Les optimisations apportent des améliorations mesurées ou corrigent des risques démontrés.
3. Le visualiseur validé conserve son apparence et ses fonctionnalités.
4. Les pipelines audio et Ollama restent fiables.
5. Les interruptions fonctionnent correctement.
6. Les données SQLite sont préservées.
7. Les ressources sont correctement libérées.
8. Les cas d'erreur sont correctement gérés.
9. Les performances au repos restent sobres.
10. Le passage Canvas/GPU est toujours fiable.
11. Les fonctions des LOTS 4 et 5 ne régressent pas.
12. Le packaging Windows fonctionne.
13. La CI finale réussit.
14. Les mesures manquantes sur le vrai matériel sont explicitement identifiées.
15. Les futures capacités agentiques et multimodales disposent d'une proposition d'architecture, sans implémentation prématurée.

## IMPORTANT — NE PAS SUR-OPTIMISER

La stabilité et la qualité utilisateur sont prioritaires.

Ne pas dégrader une animation déjà satisfaisante pour économiser une quantité insignifiante de ressources.

Ne pas remplacer un composant éprouvé uniquement parce qu'une alternative paraît plus moderne.

Ne pas introduire de nouvelles dépendances lourdes sans démontrer leur nécessité.

Ne pas modifier l'architecture principale sans bénéfice concret.

**Je veux terminer ce jalon avec un JARVIS fiable, réactif, mesurable et prêt à recevoir ensuite une véritable vision et des capacités d'action sur Windows.**

Commence par l'audit 7A, puis réalise les six phases dans l'ordre. Conclus par un bilan honnête, distinguant validation automatisée et validation matérielle réelle.
