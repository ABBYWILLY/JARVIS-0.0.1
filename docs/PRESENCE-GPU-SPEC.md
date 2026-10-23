# JARVIS — PRESENCE 2.0 GPU CINEMATIC ENGINE
## Validation LOTS 3 & 6 + moteur graphique haute fidélité

### CONTEXTE FONDAMENTAL

Projet : JARVIS 0.0.1

Dépôt de référence :
https://github.com/ABBYWILLY/JARVIS-0.0.1

Branche de travail :
`feat/jalon-2-voice-presence`

Ne jamais modifier `main`.

JARVIS doit évoluer vers une intelligence artificielle personnelle, locale, agentique et multimodale.

Philosophie non négociable :
- Local-first.
- Gratuit et open source autant que possible.
- Optimisation maximale des performances.
- Fonctionnement efficace sur RTX 3070 8 Go.
- CPU, RAM, VRAM, disque et énergie maîtrisés.
- Modularité pour matériel futur.
- Architecture durable.
- Installation Windows simple.
- Aucun cloud obligatoire.
- Aucun sacrifice de l'intelligence locale pour des effets visuels.

COMMAND OS demeure l'interface principale Tkinter.

PRESENCE doit évoluer vers un visualiseur holographique haut de gamme, avec un moteur graphique GPU optionnel.

---

# PHASE 0 — AUDIT OBLIGATOIRE DES LOTS 3 ET 6

AVANT toute nouvelle fonction graphique, contrôler réellement les livraisons existantes.

Commits de référence :
- LOT 3 : `65bd81c`.
- LOT 6 : `1e9c765`.
- Correctif Semantic Morphing : `cec390b`.
- Dernière référence connue : `a93a70f`.

Vérifier d'abord l'état Git actuel et ne pas supposer que ces SHA sont encore les derniers.

Préserver toutes les modifications locales non commitées.

## A. LOT 3 — VALIDATION DU CERVEAU COGNITIF

Contrôler les fonctionnalités effectivement implémentées :

1. Politique Manuel J2.8.
2. Routage automatique local.
3. Mode Rapide.
4. Mode Approfondi.
5. Mode Créatif.
6. Budgets distincts voix/chat/mission.
7. Continuer/Suite pour les réponses longues.
8. Conservation du contexte malgré une génération tronquée.
9. Historique et mémoire SQLite.
10. Approbation et suppression contrôlée de souvenirs.
11. Inspecteur de contexte et provenance.
12. Préservation des réponses archivées après interruption.

Pour chaque fonctionnalité :
- Identifier le code qui la réalise.
- Vérifier son raccordement à COMMAND OS.
- Exécuter les tests existants.
- Ajouter les tests manquants.
- Vérifier les préférences persistantes.
- Tester les erreurs et interruptions.
- Identifier clairement ce qui nécessite Ollama réel sur Windows.

Ne pas confondre routage heuristique et raisonnement autonome.

Ne pas inventer une qualité cognitive mesurée.

Corriger les défauts observables avant de déclarer le lot validé.

## B. LOT 6 — VALIDATION PRESENCE AVANCÉE

Contrôler :

1. Animation THINKING réellement distincte du visualiseur PCM.
2. Halo lumineux et épaisseur réglables.
3. Atelier de personnalisation.
4. Préréglages et palettes.
5. Microexpressions.
6. Mini-PRESENCE avec F10.
7. Retour Mini → normal.
8. Redimensionnement et DPI.
9. Emotional Field.
10. Sous-titres PCM.
11. Semantic Morphing : huit familles existantes.
12. Prévisualisation hors ligne.
13. Priorité aux vrais événements audio.
14. Annulation immédiate des animations obsolètes.
15. Persistance des préférences.
16. Fonctionnement des profils de performance.

Tester expressément :
- « Heureux de te revoir 😊 »
- « Je t'aime ❤️ »
- « C'est drôle 😂 »

Le morphing doit être visible dans le Canvas et ne pas être annulé prématurément par les événements vocaux.

Vérifier aussi que l'emoji expressif est bien affiché dans COMMAND OS mais non lu descriptivement par Piper.

Conserver les protections des blocs de code et des exemples Unicode littéraux.

### Livrable de phase 0

Créer un rapport concis :

`docs/AUDIT-LOTS-3-6.md`

Inclure :
- Fonctionnalités réellement présentes.
- Tests exécutés et résultats.
- Défauts détectés et corrigés.
- Tests Windows manuels restants.
- Validation réelle vs validation simulée.

**Ne pas déclarer les lots 3 et 6 validés matériellement sans test sur mon ordinateur.**

---

# PHASE 1 — ÉTUDE DE FAISABILITÉ GPU

Objectif : remplacer progressivement les limites visuelles de Tkinter Canvas par une solution graphique GPU légère, sans remplacer COMMAND OS.

Comparer prioritairement :

**ModernGL**
https://github.com/moderngl/moderngl

**Panda3D**
https://www.panda3d.org/

Évaluer :
- Qualité visuelle atteignable.
- Rendu OpenGL et shaders.
- Gestion des fenêtres sous Windows.
- Intégration avec Tkinter.
- Coexistence des boucles d'événements.
- Facilité de packaging PyInstaller.
- Taille supplémentaire de l'application.
- Maintenance, licences et dépendances.
- Charge CPU et RAM.
- Allocation VRAM.
- Stabilité des pilotes.
- Compatibilité RTX 3070.
- Support d'un mode dégradé sans GPU.

ModernGL est le candidat prioritaire, mais sa sélection finale doit être étayée.

Écarter un moteur complet si sa complexité ou ses ressources ne sont pas justifiées.

Ne pas transformer JARVIS en application de jeu vidéo.

### Livrable

`docs/PRESENCE-GPU-FEASIBILITY.md`

Décision argumentée avec avantages, limites et risques.

---

# PHASE 2 — PROTOTYPE COGNITIVE REACTOR

Créer un prototype GPU indépendant du fonctionnement de JARVIS.

Le prototype doit être local, gratuit, reproductible et sans téléchargement de modèles.

## Direction artistique

Je souhaite un noyau énergétique holographique digne d'un jeu vidéo de science-fiction moderne.

Il doit être nettement plus impressionnant que le rendu Canvas.

### Géométrie

Créer :
- Un cœur énergétique tridimensionnel ou pseudo-tridimensionnel.
- Plusieurs anneaux inclinés.
- Des segments orbitaux.
- Des filaments lumineux.
- Des particules animées.
- Des couronnes concentriques.
- Des flux énergétiques.
- Une aura volumétrique simulée.

### Lumière

Rechercher :
- Un bloom lumineux réaliste.
- Un centre brillant.
- Des halos doux.
- Des dégradés cohérents.
- Une lumière pulsatile.
- Un contraste fort avec l'arrière-plan.
- Des traînées lumineuses.
- Une palette thématique dynamique.

Utiliser des shaders GPU et des buffers sobres plutôt que multiplier les objets Python.

Éviter l'usage coûteux d'effets de post-traitement pleine résolution lorsque ce n'est pas nécessaire.

### Animation

Le noyau doit paraître vivant.

Utiliser :
- Rotations orbitales indépendantes.
- Variations de vitesse.
- Oscillations organiques.
- Respiration énergétique.
- Trajectoires paramétriques.
- Interpolations fluides.
- Microvariations déterministes.
- Transformations géométriques continues.

Ne pas produire un simple spinner.

### Transformation des états

**IDLE**
Ligne lumineuse stable, peu coûteuse.

**LISTENING**
Onde réactive au véritable RMS/PCM microphone.

**THINKING**
La ligne se contracte progressivement, devient un filament spiralé puis forme le noyau énergétique.

Le noyau reste visuellement actif tant que l'inférence Ollama est réellement en cours.

**SPEAKING**
Le noyau se déploie et redevient une onde animée par le vrai PCM Piper.

**MORPHING**
Le visualiseur forme temporairement un symbole expressif vectoriel, synchronisé de manière approximative avec le segment vocal correspondant.

**INTERRUPTION**
Toutes les animations obsolètes sont annulées immédiatement.

Aucune progression fictive, aucun faux signal audio.

### Exigence visuelle

L'effet doit être :
- Spectaculaire.
- Futuriste.
- Original.
- Lisible.
- Fluide.
- Immédiatement identifiable.
- Adapté aux petites fenêtres.
- Modulable selon la puissance disponible.

Produire des images ou captures de démonstration et, si possible, une courte séquence animée pour juger le mouvement réel.

---

# PHASE 3 — BENCHMARKS OBLIGATOIRES

Ne jamais intégrer un moteur GPU sur sa seule apparence.

Mesurer au minimum :

- FPS réels.
- Temps médian de frame.
- P95 de frame.
- CPU moyen et pics.
- RAM moyenne et pics.
- Allocation VRAM.
- Utilisation GPU graphique.
- Charge GPU pendant Ollama.
- Temps de démarrage.
- Taille du package.
- Fluidité sous redimensionnement.
- Fermeture propre.
- Consommation au repos.
- Impact sur la latence d'Ollama.
- Impact sur le débit de génération.
- Impact sur Piper, Whisper et le VAD.

Effectuer si possible les essais :
- PRESENCE seul.
- PRESENCE + génération Ollama.
- PRESENCE + lecture Piper.
- PRESENCE + écoute microphone.
- PRESENCE masqué.
- Sessions prolongées.

Distinguer les mesures du poste de développement, de la CI et de ma RTX 3070 réelle.

### Budgets cibles initiaux

Ces valeurs sont des objectifs de test, non des résultats garantis :

**Éco**
- Canvas Tkinter.
- Animation réduite.
- Ressources minimales.

**Équilibré**
- Rendu GPU simplifié.
- 30 FPS stables si possible.
- Bloom limité.
- Particules réduites.

**Cinématique**
- Effets graphiques avancés.
- 60 FPS si le matériel et la charge le permettent.
- Bloom et particules configurables.
- Priorité absolue à la fluidité et à l'IA.

Cible exploratoire : viser moins de 100 Mo de VRAM graphique supplémentaire pour le visualiseur, sans l'imposer comme une garantie irréaliste.

Si une session Ollama approche de la saturation VRAM :
- Réduire automatiquement la résolution interne.
- Réduire le bloom.
- Réduire le nombre de particules.
- Réduire la fréquence de rendu.
- Revenir à Canvas si nécessaire.

Ne pas se baser uniquement sur un nombre de FPS élevé.

Une génération IA ralentie ou une transcription dégradée invalide l'optimisation.

---

# PHASE 4 — INTÉGRATION MODULAIRE

Ne pas remplacer directement le moteur PRESENCE actuel.

Créer une abstraction commune, par exemple :

`PresenceRenderer`

Avec des opérations telles que :
- `initialize`
- `resize`
- `update_state`
- `update_audio`
- `render`
- `set_theme`
- `set_quality`
- `shutdown`

Les noms réels doivent être adaptés à l'architecture existante.

Prévoir deux implémentations :

**CanvasRenderer**
- Moteur Tkinter existant.
- Mode Éco et secours.
- Conserve les fonctionnalités déjà validées.

**GpuRenderer**
- Nouveau moteur ModernGL ou autre candidat sélectionné.
- Modes Équilibré et Cinématique.
- Même source d'événements que Canvas.

Contraintes :
- Aucun deuxième cerveau d'état.
- Aucun double flux PCM.
- Aucun double moteur de morphing.
- Aucune duplication permanente des visualiseurs.
- Pas de fenêtre supplémentaire inutile.
- Communication explicite et maîtrisée entre GUI et GPU.
- Mise en sommeil lorsque PRESENCE n'est pas visible.
- Libération propre des ressources graphiques.

Attention : l'intégration OpenGL dans Tkinter sous Windows n'est pas triviale.

Ne pas supposer qu'un contexte ModernGL peut être placé directement dans un Canvas Tkinter standard.

Étudier un hôte OpenGL compatible ou une fenêtre spécialisée avant de choisir l'architecture.

Si une intégration embarquée fiable n'est pas réalisable, proposer un compromis documenté plutôt qu'un bricolage fragile.

---

# PHASE 5 — INSTALLATION SIMPLE

L'utilisateur final est débutant.

Il ne doit pas avoir à :
- Installer séparément un moteur de jeu.
- Configurer OpenGL manuellement.
- Télécharger des shaders.
- Copier des DLL au hasard.
- Installer un environnement Python.

La version Windows doit rester utilisable via un package PyInstaller clair.

Prévoir :
- Le mode GPU inclus lorsqu'il est validé.
- La détection de compatibilité.
- Une sélection simple du moteur.
- Un retour vers Canvas en cas d'erreur.
- Des messages d'erreur compréhensibles.
- Une procédure de mise à jour sans perte des données SQLite et des modèles.

Documenter les éventuels prérequis des pilotes.

---

# PHASE 6 — VALIDATION ET NON-RÉGRESSION

Ne considérer la mission comme réussie qu'après vérification :

### Cerveau et conversation
- LOT 3 toujours fonctionnel.
- Routage automatique correct sur les exemples testés.
- Continuation des histoires.
- Mémoire et provenance.
- Historique intact.
- Pas de dégradation des performances LLM.

### PRESENCE
- LOT 6 toujours fonctionnel.
- Emotional Field préservé.
- Sous-titres conservés.
- Semantic Morphing opérationnel.
- Mini-PRESENCE fonctionnel.
- Atelier de réglages opérationnel.
- Réduction des mouvements.
- Redimensionnement et DPI.

### Voix
- Micro et VAD fonctionnels.
- Whisper conservé.
- Piper conservé.
- PCM réel.
- Interruption et reprise.
- Pas de boucle audio parasite.

### GPU
- Contexte OpenGL créé et détruit sans fuite.
- Rendu réellement accéléré.
- Aucun blocage Tkinter.
- Aucune baisse injustifiée de performance.
- Retour automatique au moteur Canvas.
- Build Windows reproductible.

### Livraison

Produire :
- Un rapport d'audit des lots 3 et 6.
- Un rapport comparatif des moteurs.
- Un prototype visuel fonctionnel.
- Les benchmarks disponibles.
- L'implémentation modulaire, si le prototype passe les critères.
- Des tests de non-régression.
- Une documentation utilisateur.
- Un build Windows validé en CI.

Commits et push uniquement sur :
`feat/jalon-2-voice-presence`

Ne pas modifier `main`.

Ne pas prétendre que les tests matériels Windows ont été réalisés à distance.

---

# CRITÈRE FINAL DE RÉUSSITE

**PRESENCE doit devenir un visualiseur holographique spectaculaire digne d'un jeu vidéo de science-fiction, sans compromettre l'objectif fondamental de JARVIS : une intelligence artificielle locale, multimodale, agentique, extrêmement optimisée et évolutive.**

La réussite se juge sur trois axes simultanés :

1. Qualité visuelle réellement supérieure.
2. Impact matériel mesuré et acceptable.
3. Préservation de toutes les capacités fonctionnelles existantes.

Si un moteur GPU ne respecte pas ces trois conditions, ne pas forcer son intégration.

Préserver le mode Canvas et documenter les limites.

**Priorité de réalisation : audit lots 3 et 6 → prototype GPU → mesures → décision d'intégration → tests Windows.**