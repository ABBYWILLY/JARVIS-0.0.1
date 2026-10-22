# JARVIS — PRESENCE 3.2 SEMANTIC MORPHING + COMMAND OS RICH CONVERSATION

**Dépôt :** ABBYWILLY/JARVIS-0.0.1
**Branche :** `feat/jalon-2-voice-presence`

**Mission complémentaire aux évolutions Emotional Field 3.0 et Living Core 3.1.**

## DIRECTIVE PRIORITAIRE — INTÉGRATION ARCHITECTURALE

Avant de modifier le code :

1. Vérifier l'état Git et identifier ce qui a déjà été implémenté.
2. Lire les modules actuels de PRESENCE, du rendu Markdown, du pipeline TTS et des événements PCM.
3. Consulter le cahier des charges original JARVIS 0.0.1 s'il est disponible dans le dépôt.
4. Réutiliser les composants existants plutôt que développer un système parallèle.

Préserver intégralement :
- COMMAND OS, PRESENCE et leurs préférences ;
- Emotional Field 3.0 et Cognitive Singularity ;
- Ollama et les optimisations J2.8 ;
- Whisper, VAD et Piper ;
- SQLite, la mémoire et les budgets de tokens ;
- Les permissions, interruptions et états opérationnels ;
- Les performances, diagnostics et mécanismes de sécurité.

**Principe fondamental : aucune amélioration visuelle ne doit ralentir la conversation ni augmenter inutilement les ressources consommées.**

---

# A. PRESENCE 3.2 — SEMANTIC MORPHING ENGINE

## A1. Objectif

Lorsque JARVIS utilise un emoji ou une émoticône dans sa réponse, son unique visualiseur PRESENCE doit se transformer temporairement en une représentation holographique reconnaissable de cette expression.

**Il ne s'agit pas d'afficher une image emoji au-dessus de l'onde. Le visualiseur doit réellement changer de géométrie.**

Exemple :

« Heureux de te revoir Abraham :) »

Comportement attendu :

1. JARVIS prononce normalement « Heureux de te revoir Abraham ».
2. Piper ne prononce pas le symbole `:)`.
3. Lorsque le passage vocal correspondant se termine, le visualiseur se contracte.
4. Il se transforme progressivement en un sourire holographique.
5. Le sourire reste visible brièvement.
6. Il retrouve progressivement l'onde ou l'état fonctionnel suivant.

La voix ne doit jamais être interrompue ou ralentie pour permettre l'animation.

## A2. Moteur vectoriel universel

Créer un moteur de morphing léger intégré au Canvas Tkinter existant.

Utiliser :
- Courbes vectorielles ;
- Arcs ;
- Cercles ;
- Points lumineux ;
- Tracés lumineux multicouches ;
- Interpolations géométriques ;
- Transitions d'opacité lorsque nécessaire et compatibles avec Tkinter.

Conserver une seule entité visuelle centrale.

Ne pas superposer un second avatar, une image emoji ou une nouvelle fenêtre.

### Architecture recommandée

Définir une représentation géométrique commune pour les expressions, avec :
- Contour principal ;
- Éléments secondaires facultatifs ;
- Couleur héritée d'Emotional Field ;
- Intensité lumineuse ;
- Paramètres d'interpolation ;
- Durées de transformation et de maintien.

Ne pas imposer une correspondance point par point artificielle entre des formes incompatibles.

Préférer un morphing combinant transformation du contour principal et apparition progressive des détails secondaires.

Réutiliser les objets graphiques autant que possible.

## A3. Catalogue initial de 8 familles émotionnelles

Implémenter huit familles vectorielles :

| Famille | Exemples |
|---|---|
| Sourire | `:)`, `🙂`, `😊` |
| Rire | `😂`, `🤣`, `:D` |
| Affection | `❤️`, `💕`, `♥` |
| Tristesse | `😢`, `😭`, `:(` |
| Colère | `😠`, `😡` |
| Surprise | `😮`, `😲` |
| Réflexion | `🤔` |
| Complicité | `😉`, `;)` |

Chaque famille peut partager une géométrie principale avec des variantes d'expressivité.

Éviter de créer une animation indépendante pour chaque emoji.

L'architecture doit permettre d'ajouter progressivement de nouvelles familles sans modifier le moteur central.

Un emoji inconnu reste affiché normalement dans le texte, sans déclencher de morphing incorrect.

## A4. Détection sémantique et protection des contenus

Réutiliser ou étendre le parseur textuel existant pour détecter :

- Emojis Unicode ;
- Émoticônes ASCII ;
- Séquences Unicode composées ;
- Variantes de présentation emoji ;
- Séquences ZWJ ;
- Positions dans le texte original.

Éviter les faux positifs dans :
- Les URL ;
- Les blocs de code ;
- Le code inline ;
- Les chemins de fichiers ;
- Les expressions techniques ;
- Les chaînes littérales citées lorsque leur interprétation expressive est ambiguë.

Conserver les emojis dans COMMAND OS, dans les sous-titres et dans l'historique.

Les emojis purement visuels ne doivent pas être prononcés comme des noms de symboles. Préserver toutefois les symboles ayant une signification orale réelle dans leur contexte.

La détection doit rester déterministe et locale, sans appel supplémentaire à Ollama.

## A5. Synchronisation avec la parole

Réutiliser le pipeline existant :

**Texte Qwen → analyse des expressions → préparation TTS → événements PCM → PRESENCE.**

Pour chaque morphing, conserver :
- Identifiant de réponse ;
- Identifiant de segment ;
- Position dans le texte original ;
- Famille d'expression ;
- Progression audio estimée ;
- Statut d'annulation.

Règles :

- Emoji en fin de phrase : transformation lorsque le segment vocal correspondant se termine.
- Emoji au milieu d'une phrase : déclenchement au passage estimé.
- Plusieurs emojis consécutifs : regrouper ou sélectionner intelligemment une expression dominante.
- Plusieurs emojis éloignés : autoriser des événements distincts si le rythme le permet.
- Interruption : annuler immédiatement tous les événements devenus obsolètes.

Ne pas annoncer une synchronisation précise au mot près sans véritables timestamps de phonèmes ou de mots.

Ne jamais retarder l'audio pour attendre une animation.

## A6. Cinématique du morphing

Créer une animation continue comprenant :

**Phase 1 — Transformation**
- Contraction organique de l'onde ;
- Réorganisation des tracés ;
- Apparition progressive du contour émotionnel.

Durée indicative : 300 à 450 ms.

**Phase 2 — Expression**
- Figure stable et immédiatement reconnaissable ;
- Halo léger ;
- Microanimation expressive facultative.

Durée indicative : 500 à 800 ms.

**Phase 3 — Retour**
- Dissolution des éléments secondaires ;
- Transformation du contour vers la géométrie normale ;
- Reprise de l'état réel de PRESENCE.

Ces durées sont des valeurs initiales à ajuster par prévisualisation et mesure.

Ne jamais faire attendre une nouvelle réponse, une interruption ou une reprise du microphone à cause du morphing.

### Gestion des priorités

Les états fonctionnels sont prioritaires sur toute animation expressive :

1. Arrêt d'urgence, erreur critique et sécurité.
2. Interruption et capture microphone.
3. Réflexion et parole en cours.
4. Morphing sémantique.
5. Animation décorative.

Si JARVIS reprend la parole pendant une expression, le morphing cède immédiatement la place à l'onde parlante.

## A7. Cohérence avec Emotional Field

Le morphing doit conserver :
- Le mood dominant de la réponse ;
- Les couleurs émotionnelles actives ;
- Les nuances secondaires pertinentes ;
- Les transitions douces ;
- L'épaisseur lumineuse Living Core ;
- Le centrage et les proportions de PRESENCE.

La forme exprime le symbole choisi ; la couleur conserve la cohérence émotionnelle globale.

Éviter que les emojis déclenchent des couleurs contradictoires avec le ton général de la réponse.

## A8. Optimisation du Semantic Morphing

Exigences :

- Aucun nouveau modèle IA.
- Aucun nouveau processus.
- Aucun second moteur graphique.
- Aucune bibliothèque lourde.
- Catalogue géométrique initialisé une seule fois.
- Objets Canvas réutilisés.
- Paramètres invariants précalculés.
- Aucun parsing Unicode ou calcul linguistique à chaque frame.
- Files d'événements bornées.
- Animations désactivées ou réduites si PRESENCE est masqué.
- Respect des profils Éco / Équilibré / Cinématique.
- Respect du mode Réduction des mouvements.

Limiter les halos à quelques tracés légers plutôt qu'à un flou logiciel coûteux.

Mesurer l'impact CPU, RAM et fluidité, et réduire les effets si nécessaire.

## A9. Paramètres utilisateur

Ajouter dans les préférences PRESENCE :

- Semantic Morphing : activé / désactivé.
- Intensité : discrète / normale / expressive.
- Réduction des animations : conserver les formes statiques si nécessaire.
- Prévisualisation locale des huit familles sans Ollama ni Piper.

Conserver ces préférences après redémarrage.

---

# B. COMMAND OS 2.0 — RICH CONVERSATION

## B1. Objectif

Transformer l'affichage textuel de COMMAND OS en une véritable interface de conversation riche, lisible et personnalisable.

**Réutiliser en priorité le moteur Markdown déjà implémenté. Ne pas le reconstruire inutilement.**

## B2. Mise en forme attendue

Supporter correctement :

- Titres H1, H2 et H3 ;
- Texte gras et italique ;
- Gras italique ;
- Soulignage contrôlé ;
- Surlignage ;
- Listes à puces ;
- Listes numérotées ;
- Indentation cohérente ;
- Citations ;
- Séparateurs ;
- Liens cliquables ;
- Code inline ;
- Blocs de code monospace ;
- Tableaux lisibles ;
- Emojis Unicode ;
- Expressions mathématiques avec représentation textuelle sûre lorsque nécessaire.

Gérer convenablement les combinaisons de styles, sans produire d'artefacts visuels.

Ne pas afficher littéralement les marqueurs Markdown lorsque leur syntaxe est valide.

## B3. Typographie personnalisable

Ajouter des paramètres persistants permettant de choisir :

- Famille de police parmi celles disponibles sur Windows ;
- Taille générale du texte ;
- Échelle de lecture ;
- Interlignage adapté ;
- Éventuellement un mode de lecture compact ou confortable.

Conserver une hiérarchie automatique entre titres, paragraphes, listes et code.

Ne pas laisser des choix de typographie casser la géométrie des messages.

## B4. Architecture de rendu

Maintenir quatre représentations distinctes :

1. **Texte original** : intégralement conservé dans l'historique.
2. **Structure analysée** : Markdown, emojis, styles et positions.
3. **Rendu graphique** : tags Tkinter et composants existants.
4. **Texte vocal** : version préparée pour Piper.

Ne pas modifier le contenu original pour obtenir un effet graphique.

Préserver :
- Copie du texte original ;
- Sélection du texte affiché ;
- Historique SQLite ;
- Streaming Ollama ;
- Unicode français ;
- Markdown mixte ;
- Accessibilité.

## B5. Streaming Markdown intelligent

Pendant la génération :

- Ne pas afficher les délimiteurs Markdown incomplets comme du texte définitif.
- Ne pas reconstruire inutilement tout l'historique à chaque token.
- Utiliser des mises à jour incrémentales lorsque possible.
- Stabiliser les blocs incomplets avant d'appliquer leur style.
- Corriger progressivement l'affichage sans clignotement.
- Préserver le défilement et la position de lecture de l'utilisateur.

À la fin de la génération, le rendu doit correspondre au Markdown final.

## B6. Liens et sécurité

Aucun contenu généré ne doit exécuter de code.

- Aucun HTML ou JavaScript actif.
- Aucune interprétation de commandes système.
- Aucun lancement automatique de programme.
- Liens soumis à une validation appropriée avant ouverture.
- Pas d'accès aux fichiers locaux déclenché automatiquement par le texte généré.

Ne pas introduire un navigateur embarqué ou une WebView si les composants Tk existants suffisent.

## B7. Performance

- Réutiliser le parseur Markdown existant.
- Réutiliser les tags et polices plutôt que recréer constamment des objets.
- Éviter les recalculs sur les anciens messages inchangés.
- Préserver la fluidité du streaming.
- Limiter la mémoire consacrée aux rendus volumineux.
- Ne pas perturber le moteur de réponse vocale.

---

# C. VALIDATION ET TESTS

## C1. Tests Semantic Morphing

Tester au minimum :

- `:)`, `😊`, `❤️` ;
- Les huit familles ;
- Emoji final et emoji au milieu d'une phrase ;
- Plusieurs emojis successifs ;
- Emoji inconnu ;
- Unicode complexe ;
- Emoji dans un bloc de code ou une URL ;
- Synchronisation PCM ;
- TTS qui ne lit pas les symboles purement expressifs ;
- Morphing annulé pendant une interruption ;
- Reprise immédiate de la parole ;
- Réduction des mouvements ;
- Préférences ;
- Performance des profils graphiques.

## C2. Tests Rich Conversation

Tester :

- Titres, styles, listes et tableaux ;
- Code, Unicode et emojis ;
- Markdown reçu progressivement ;
- Copie, sélection et historique ;
- Police et taille personnalisées ;
- Affichage sur plusieurs résolutions et valeurs DPI ;
- Absence de scripts exécutables ;
- Compatibilité Tk 8.6 et Tk 9 ;
- Performance sur des conversations longues.

## C3. Tests de non-régression

Vérifier qu'aucun changement ne dégrade :

- PRESENCE Emotional Field ;
- Cognitive Singularity ;
- Les sous-titres émotionnels ;
- COMMAND OS ;
- Ollama et les budgets de tokens ;
- Whisper, VAD et Piper ;
- L'interruption vocale ;
- La mémoire SQLite ;
- Les permissions Windows ;
- La compilation de `Jarvis.exe`.

Les mesures matérielles non réalisées doivent être signalées, jamais inventées.

---

# D. PLAN D'IMPLÉMENTATION

Procéder par sous-lots :

### Lot 1 — COMMAND OS Rich Conversation

Étendre et stabiliser la mise en forme existante.

Tests ciblés, commit et push.

### Lot 2 — Semantic Morphing fonctionnel

Livrer en priorité :
- Sourire `:)` / `😊` ;
- Cœur `❤️` ;
- Événements PCM ;
- Morphing et retour naturel ;
- Interruption immédiate.

Tests ciblés, commit et push.

### Lot 3 — Extension du moteur vectoriel

Ajouter les huit familles, les variantes, les optimisations et les paramètres.

Tests ciblés, commit et push.

### Lot 4 — Finitions et validation

Tester les emojis complexes, les performances, l'accessibilité et la CI Windows.

Ne pas modifier `main`.

En cas de limite de crédits Codex, terminer proprement le sous-lot en cours, sauvegarder les changements et documenter ce qui reste à faire.

---

# E. COMPTE RENDU FINAL

Fournir uniquement :

1. Fonctionnalités réellement implémentées.
2. Composants existants réutilisés.
3. Fichiers modifiés.
4. Tests réussis et limites restantes.
5. Consommation CPU/RAM et performance, si mesurées.
6. Commits et état de la CI Windows.
7. Éléments à vérifier manuellement sur Windows 11.

**Résultat recherché : JARVIS possède une conversation textuelle riche et une présence capable de transformer organiquement son propre visualiseur en expressions holographiques synchronisées à sa parole, tout en conservant son architecture, son efficacité et sa réactivité.**
