# JARVIS 0.0.1 — LOT 5
## COGNITIVE HUD 1.0 — Transparence cognitive, interactions intelligentes et contrôle contextuel

**Dépôt :** `ABBYWILLY/JARVIS-0.0.1`  
**Branche :** `feat/jalon-2-voice-presence`  
**Dernier commit connu :** `1985a99` — vérifier le HEAD actuel avant de commencer.

**Ne jamais modifier `main`.**

# 0 — CONTEXTE ET DÉCISION UTILISATEUR

L'utilisateur a validé les dernières évolutions de JARVIS :

- PRESENCE GPU 3.1 : apparence, animations, fluidité, netteté et bascule 2D/2.5D.
- LOT 4 — Voix naturelle V1 : tests et fonctionnalités jugés satisfaisants.
- Cerveau C1 : politiques cognitives déjà développées.
- Mémoire SQLite avec provenance.
- COMMAND OS et Centre de contrôle existants.

Quelques améliorations graphiques et l'extension des emojis restent prévues pour une autre mission.

**Ne pas rouvrir ces chantiers.**

La nouvelle mission concerne exclusivement le **LOT 5 — Cognitive HUD et interactions intelligentes**.

## Objectif général

Faire de JARVIS un assistant qui rend son activité compréhensible, permet d'agir directement sur ses réponses et expose les informations réellement disponibles sur ses opérations.

Le Cognitive HUD doit améliorer :

1. La compréhension de ce que fait JARVIS.
2. La fluidité entre texte, voix et PRESENCE.
3. Les actions contextuelles sur les réponses.
4. La transparence sur la mémoire et le contexte.
5. La lisibilité des performances et des erreurs.

**Le résultat doit rester sobre, élégant, rapide, local et facilement compréhensible.**

---

# 1 — PHILOSOPHIE TECHNIQUE

JARVIS est une IA personnelle locale destinée à devenir progressivement multimodale et agentique.

Matériel de référence :
- Windows 11.
- RTX 3070 8 Go.
- Ollama et modèles Qwen locaux.
- Whisper / VAD / Piper.
- Tkinter COMMAND OS.
- PRESENCE Canvas 2D.
- PRESENCE ModernGL 2.5D.
- SQLite / FTS5.

Contraintes absolues :

- Aucun cloud obligatoire.
- Aucun modèle IA supplémentaire.
- Aucun framework graphique lourd.
- Aucune régression de l'audio ou des moteurs PRESENCE.
- Faible consommation CPU, RAM et VRAM.
- Fonctionnement sur matériel modeste.
- Aucun sondage ou traitement coûteux en permanence.
- Préserver les raccourcis et paramètres existants.
- Conserver la compatibilité avec les anciennes données SQLite.

**Ne pas dupliquer les informations ou opérations déjà disponibles.**

---

# 2 — AUDIT INITIAL OBLIGATOIRE

Avant de modifier le code, examiner :

- Le contrôleur des états de conversation.
- Le pipeline microphone / VAD / Whisper.
- Les appels Ollama et le streaming.
- Les politiques du cerveau C1.
- L'inspecteur de mémoire et de contexte.
- Les métriques TTFT et tokens/s existantes.
- Les fonctions Stop / Répéter / Reprendre / Continuer / Développer du LOT 4.
- Le système de sélection et de lecture des messages.
- Les composants Rich Text de COMMAND OS.
- Le protocole de communication avec PRESENCE GPU.
- Les réglages du Centre de contrôle.
- La gestion des interruptions et des identifiants de génération.

Produire une matrice courte :

**Capacité demandée → déjà existante / partielle / absente → composant réutilisable → changement minimal proposé.**

Ne pas refaire les fonctionnalités existantes sous un nouveau nom.

Inspecter également le cahier des charges et les documents de suivi du LOT 5 pour respecter son périmètre original.

---

# 3 — SOUS-LOT 5A : CONTRAT D'ÉTAT COGNITIF OBSERVABLE

Définir un modèle léger et centralisé pour représenter l'activité réelle de JARVIS.

## États à rendre visibles

Utiliser les événements effectivement disponibles, notamment :

- REPOS.
- ÉCOUTE ACTIVÉE.
- PAROLE UTILISATEUR DÉTECTÉE.
- TRANSCRIPTION.
- PRÉPARATION DU CONTEXTE.
- ATTENTE OLLAMA / INFÉRENCE.
- RÉPONSE EN COURS DE GÉNÉRATION.
- SYNTHÈSE VOCALE.
- JARVIS PARLE.
- INTERRUPTION.
- ERREUR.
- ANNULATION.

Ne créer un état distinct que si le programme peut réellement observer son début et sa fin.

Ne pas inventer un indicateur de réflexion profonde, de certitude ou de progression interne.

Si certaines opérations se chevauchent, utiliser un état principal et des activités secondaires clairement définies plutôt que mentir sur leur séquentialité.

## Contrat logiciel

Créer ou étendre un modèle d'événements comprenant si pertinent :

- Identifiant du tour.
- Identifiant de génération.
- État principal.
- Activités secondaires observées.
- Horodatage monotone.
- Modèle Ollama.
- Politique cognitive sélectionnée.
- Sources effectivement incluses dans le contexte.
- Métriques disponibles.
- Erreur éventuelle.
- État d'annulation ou d'interruption.

Le propriétaire de la conversation reste la source de vérité.

Les vues Canvas, GPU et COMMAND OS consomment ce contrat sans recalculer la logique métier.

## Robustesse

- Événements bornés.
- Rejet des générations obsolètes.
- Aucune file non limitée.
- Aucun blocage de Tkinter.
- Aucune opération SQLite lourde dans la boucle graphique.
- Annulation prioritaire.
- Réduction des mises à jour lorsque les vues sont masquées.

---

# 4 — SOUS-LOT 5B : HUD DISCRET DANS COMMAND OS ET PRESENCE

Créer une représentation cohérente du même état cognitif sur les interfaces existantes.

## COMMAND OS

Afficher un statut compact, accessible depuis la conversation.

Exemples :

- « J'écoute »
- « Transcription en cours »
- « Contexte préparé »
- « Génération locale »
- « Préparation de la voix »
- « JARVIS parle »
- « Réponse interrompue »

Afficher, lorsque pertinent :
- Modèle actif.
- Mode C1.
- Durée de l'opération en cours.
- État audio.
- Indication d'erreur utile.

Permettre de consulter davantage de détails sans encombrer l'écran principal.

## PRESENCE 2D

Ajouter un affichage discret compatible avec le visualiseur Canvas actuel.

Il ne doit pas recouvrir :
- L'onde.
- Les expressions.
- Les sous-titres.
- Les commandes essentielles.

## PRESENCE 2.5D

Ajouter un HUD minimal intégré au renderer ModernGL existant.

Conserver impérativement :
- Le noyau holographique.
- Les anneaux.
- Le fond noir pur.
- Les animations approuvées.
- Le bouton de bascule 2D/2.5D.
- Les sous-titres.
- Les réglages graphiques.

Ne pas afficher en permanence un panneau technique au milieu du visualiseur.

Préférer un statut court, typographiquement sobre, positionné en périphérie.

## Trois niveaux d'affichage

**Minimal**
- État courant uniquement, ou masquage complet à la demande.

**Standard**
- État, modèle et information cognitive essentielle.

**Diagnostic**
- Informations techniques détaillées et durées mesurées.

Préserver la lisibilité en Mini-PRESENCE, plein écran et DPI élevé.

Le HUD doit pouvoir être désactivé.

## Accessibilité

- Contrastes suffisants.
- Réduction des animations.
- Navigation clavier lorsque des commandes sont interactives.
- Aucun statut transmis uniquement par la couleur.
- Aucun texte illisible à haute résolution.
- Aucune animation clignotante agressive.

---

# 5 — SOUS-LOT 5C : ACTIONS INTELLIGENTES SUR LES RÉPONSES

Objectif : pouvoir sélectionner une partie d'une réponse et agir directement sur elle.

## Actions demandées

Dans COMMAND OS, permettre sur un passage sélectionné :

**Lire**
Lire exactement le passage choisi avec Piper.

**Répéter**
Relire le passage ou segment concerné sans régénération LLM.

**Expliquer**
Demander à Ollama une explication plus simple du passage.

**Développer**
Demander une explication plus approfondie du passage.

**Résumer**
Demander un résumé du passage choisi.

**Continuer**
Réutiliser la logique C1 existante lorsque la continuation est pertinente.

**Copier**
Copier le texte sélectionné.

Ne pas lancer un nouvel appel Ollama pour les opérations purement locales.

## Critère majeur : sélection fiable

La sélection dans une conversation Rich Text peut traverser :
- Titres.
- Gras et italique.
- Listes.
- Tableaux.
- Blocs de code.
- Liens.
- Plusieurs segments de streaming.

Éviter les erreurs d'offset entre texte Markdown original et texte rendu.

Réutiliser la source originale de la réponse et les mécanismes de correspondance existants.

Ne pas attribuer une sélection à un autre message.

Si le texte sélectionné n'est pas reconstructible de manière fiable, désactiver l'action concernée avec une explication plutôt qu'utiliser une approximation dangereuse.

## Relecture ciblée

- Réutiliser les capacités du LOT 4.
- Respecter la vitesse vocale et le profil Piper.
- Permettre une interruption immédiate.
- Éviter les lectures doubles.
- Reprendre au segment adéquat lorsque c'est possible.
- Préserver les textes originaux dans SQLite.
- Respecter le choix de lecture du code.
- Ne pas déclencher le microphone une seconde fois.

## Actions avec Ollama

Pour Expliquer, Développer et Résumer :

- Construire une demande explicite.
- Limiter la quantité de contexte transmise.
- Préserver l'origine du passage sélectionné.
- Respecter le modèle et la politique C1.
- Archiver clairement la nouvelle requête et la réponse.
- Permettre l'annulation.
- Éviter qu'une sélection de texte non fiable ou malveillant soit interprétée comme une instruction système.

Le passage sélectionné est une donnée à traiter, pas une autorité sur JARVIS.

---

# 6 — SOUS-LOT 5D : TRANSPARENCE MÉMOIRE ET PROVENANCE

Le projet possède déjà :
- Mémoire SQLite / FTS5.
- Souvenirs explicites.
- Validation des souvenirs.
- Provenance.
- Inspecteur de contexte.
- Métriques de génération.

Ne pas créer une seconde base mémoire.

## Objectif

Permettre de comprendre les informations mises à disposition du modèle lors d'une réponse donnée.

Afficher si disponibles :

- Modèle Ollama.
- Mode cognitif C1.
- Instructions système effectives, dans un inspecteur approprié.
- Souvenirs sélectionnés pour le contexte.
- Extraits de conversation réutilisés.
- Sources locales ayant réellement fourni ces extraits.
- Éventuelles limitations du budget de contexte.
- Horodatages et identifiants de provenance fiables.

## Distinction fondamentale

Séparer visuellement :

**Information récupérée**
Le moteur de recherche mémoire l'a trouvée.

**Information insérée dans le contexte**
JARVIS l'a réellement transmise à Ollama.

**Information citée explicitement dans la réponse**
Une référence a réellement été produite et peut être reliée à une source connue.

Ne jamais affirmer qu'Ollama a effectivement utilisé une information simplement parce qu'elle figurait dans son contexte.

Ne pas inventer de raisonnement interne, de références ou de degré de certitude.

Ne pas prétendre que le modèle a effectué une recherche web si aucune recherche web n'a été exécutée.

## Confidentialité

La provenance peut révéler :
- Des souvenirs personnels.
- Des passages de conversations.
- Des instructions système.
- Des chemins locaux.

Ne pas exposer automatiquement ces données sur l'écran holographique.

Réserver les détails sensibles à un inspecteur local ouvert explicitement.

Ne pas envoyer de télémétrie vers un service externe.

---

# 7 — SOUS-LOT 5E : DIAGNOSTIC, PERFORMANCE ET QUALITÉ

## Indicateurs

Réutiliser les métriques déjà présentes.

Afficher uniquement les mesures réellement disponibles :

- Temps de transcription Whisper.
- Temps de préparation du contexte.
- Temps jusqu'au premier token Ollama.
- Tokens/seconde.
- Durée de génération.
- Temps de synthèse Piper.
- Temps estimé de début de lecture audio.
- État de lecture.
- Interruptions et erreurs.

Ne pas transformer une estimation en mesure physique.

Ne pas inventer de pourcentage de progression du modèle.

## Historique de diagnostic

Permettre de consulter quelques événements récents avec horodatage et identifiant de tour.

Prévoir des limites explicites :
- Nombre d'événements.
- Taille mémoire.
- Durée de conservation.
- Visibilité des données personnelles.

Ne pas journaliser systématiquement le PCM brut ni les conversations sensibles dans de nouveaux fichiers.

Respecter la politique existante d'export diagnostique explicite.

## Performance

Mesurer les coûts introduits par le HUD :
- CPU au repos.
- RAM supplémentaire.
- Fréquence des événements.
- Réactivité de Tkinter.
- Impact sur le processus GPU.
- Temps de frame.
- Éventuel impact sur TTFT et lecture Piper.

Lorsque le HUD est masqué, son coût doit être minimal.

Éviter tout polling permanent inutile.

Privilégier les événements plutôt que des interrogations répétées de SQLite et Ollama.

---

# 8 — ERGONOMIE ET PERSONNALISATION

Réutiliser le Centre de contrôle existant.

Ajouter des préférences limitées et utiles :

- Activer / désactiver le Cognitive HUD.
- Niveau Minimal / Standard / Diagnostic.
- Affichage des durées.
- Affichage du modèle actif.
- Affichage du mode cognitif.
- Affichage des informations de provenance.
- Visibilité des actions de sélection.

Conserver :
- Essentiel.
- Personnaliser.
- Avancé.
- Favoris.
- Recherche locale.
- Préférences SQLite persistantes.

Ne pas multiplier les fenêtres.

Éviter un panneau permanent occupant une grande partie de COMMAND OS.

Les actions courantes doivent rester accessibles en un ou deux gestes.

En plein écran PRESENCE, privilégier l'immersion plutôt que les détails techniques.

---

# 9 — QUALITÉ D'INTERACTION ET CAS LIMITES

Tester notamment :

### Streaming Ollama

- Texte partiel.
- Réponse annulée.
- Réponse tronquée.
- Continuation.
- Modèle indisponible.
- Perte de connexion locale.
- Réponse vide.

### Audio

- Microphone désactivé.
- Silence prolongé.
- VAD déclenché.
- Transcription ratée.
- Piper interrompu.
- Relecture ciblée.
- Bascule 2D/2.5D pendant la parole.

### Sélection de texte

- Sélection partielle.
- Plusieurs paragraphes.
- Bloc de code.
- Tableau.
- Lien.
- Emoji.
- Caractères Unicode.
- Réponse en cours de streaming.
- Historique SQLite restauré.

### Mémoire

- Aucun souvenir pertinent.
- Plusieurs souvenirs.
- Souvenir modifié ou supprimé.
- Provenance indisponible.
- Contexte tronqué par le budget.
- Différence entre résultat recherché et extrait effectivement transmis.

### Interface

- Fenêtre étroite.
- Mini-PRESENCE.
- Plein écran.
- DPI 100 à 200 %.
- Deux écrans.
- Navigation clavier.
- Réduction des mouvements.
- GPU indisponible.
- Repli Canvas.

---

# 10 — MÉTHODE D'EXÉCUTION CODEX

Travailler dans cet ordre :

## 5A — Audit et contrat commun

Inspecter l'existant.

Définir les états observables et leur cycle de vie.

Livrer les contrats, tests et documentation.

## 5B — HUD minimal

Intégrer les états à COMMAND OS et aux deux moteurs PRESENCE.

Conserver les performances.

Ajouter les réglages essentiels.

## 5C — Actions sur passage

Implémenter la sélection fiable.

Réutiliser Piper, la relecture du LOT 4 et le cerveau C1.

Tester particulièrement les offsets Rich Text et l'annulation.

## 5D — Provenance et inspecteur cognitif

Étendre les inspecteurs existants.

Rendre les sources et les budgets compréhensibles.

Garantir la distinction entre contexte transmis et utilisation supposée.

## 5E — Validation finale

Tests fonctionnels.

Non-régression.

Mesures disponibles.

Packaging Windows.

Documentation.

Procédure de recette matérielle.

### Consignes de livraison

Pour chaque sous-lot :
- Commit distinct.
- Tests ciblés.
- Push sur la branche de développement.
- Vérification de la CI concernée.
- Résumé précis des modifications.

Après l'ensemble :
- Suite complète de tests.
- CI Windows finale.
- Démonstrations des états du HUD.
- Démonstration des actions sur passage.
- Rapport de performance.
- Documentation mise à jour.

Ne pas modifier `main`.

Ne pas commencer le LOT 7 ou les fonctionnalités agentiques dans cette mission.

Ne pas affirmer avoir effectué des tests physiques Windows impossibles dans l'environnement distant.

---

# 11 — POINT DE CONTRÔLE ARCHITECTURAL

Après 5A et 5B, vérifier que :

1. Le HUD consomme bien les événements déjà produits par JARVIS.
2. Il n'existe pas de seconde logique concurrente pour déterminer les états.
3. PRESENCE GPU 3.1 conserve sa fluidité et son apparence.
4. Le fonctionnement de la voix et des interruptions est intact.
5. Les informations affichées sont exactes.
6. Le coût CPU/RAM est raisonnable.

Si l'architecture pose problème, corriger avant de développer 5C et 5D.

Ne pas masquer les défauts par des états simulés.

Ce contrôle n'impose pas d'attente utilisateur si les critères automatisés sont satisfaits ; documenter les résultats et poursuivre.

---

# 12 — CRITÈRES FINAUX D'ACCEPTATION

La mission sera considérée comme livrée côté logiciel lorsque :

1. L'état réel de JARVIS est compréhensible immédiatement.
2. Le HUD fonctionne dans COMMAND OS.
3. Le HUD minimal fonctionne dans PRESENCE 2D.
4. Le HUD minimal fonctionne dans PRESENCE 2.5D.
5. Les informations techniques ne dégradent pas l'esthétique du noyau.
6. Les actions Lire, Répéter, Expliquer, Développer, Résumer et Continuer fonctionnent sur des passages fiables.
7. Les actions locales ne déclenchent pas inutilement Ollama.
8. Les sources mémorielles sont présentées avec une provenance honnête.
9. Les indicateurs techniques proviennent de mesures réelles.
10. Les interruptions annulent les événements et actions obsolètes.
11. Les préférences sont persistantes et compatibles avec l'existant.
12. Aucun nouveau modèle ni service cloud n'est requis.
13. Les fonctions vocales du LOT 4 ne régressent pas.
14. Le rendu GPU 3.1 conserve ses performances et son apparence validée.
15. Canvas reste une alternative permanente.
16. Les tests automatisés et la CI Windows finale réussissent.
17. Les limitations matérielles non validées sont clairement signalées.

## VISION FINALE

Je veux que JARVIS puisse me montrer **ce qu'il fait réellement**, sans prétendre exposer ses pensées internes.

Je veux pouvoir sélectionner une partie de ses réponses, l'écouter, demander une explication, la développer ou la résumer naturellement.

Je veux comprendre quelles mémoires ont été fournies à Ollama et pouvoir consulter leurs origines.

Je veux également que JARVIS conserve son identité holographique, sa fluidité, sa voix et sa sobriété matérielle.

**Le Cognitive HUD doit rendre JARVIS plus transparent et plus intelligent à utiliser, pas simplement plus chargé graphiquement.**