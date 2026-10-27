> Additif utilisateur prioritaire : Canvas est une alternative permanente complète,
> jamais un simple dépannage. Choix Automatique / 2D classique / 2.5D GPU,
> préférences artistiques séparées, basculement sans relancer audio/modèles,
> un seul visualiseur actif, choix persistant et repli expliqué sans boucle.

# JARVIS — PRESENCE GPU 3.0
## MISSION : INTÉGRATION DANS JARVIS + STUDIO DE PERSONNALISATION AVANCÉ

**Dépôt :** ABBYWILLY/JARVIS-0.0.1  
**Branche :** `feat/jalon-2-voice-presence`  
**Base actuelle vérifiée :** `901f360`

Ne pas modifier `main`.

## 0 — DÉCISION UTILISATEUR ET ÉTAT DU PROJET

Je valide l'apparence et les animations actuelles du visualiseur PRESENCE GPU 3.0.

Le noyau iridescent me plaît, les anneaux tridimensionnels aussi, et le Semantic Morphing gravé sur la sphère correspond à la direction artistique souhaitée.

Il reste quelques détails à peaufiner, mais **la direction artistique générale est officiellement approuvée**.

Les sous-lots A, B, C et D sont réalisés. Ne pas les recommencer.

Je donne maintenant mon autorisation pour :

1. Finaliser les prévisualisations et tests nécessaires.
2. Développer un Studio avancé offrant le réglage individuel des composants graphiques.
3. Intégrer progressivement PRESENCE GPU dans le vrai JARVIS.
4. Connecter ses états aux événements réels de conversation, de microphone et de synthèse vocale.
5. Valider les performances et la stabilité avant toute activation par défaut.

L'objectif n'est pas une nouvelle refonte artistique, mais **la transformation du prototype autonome en composant réellement utilisable du logiciel JARVIS**.

---

## 1 — PRESENCE STUDIO : PERSONNALISATION COMPLÈTE

Je veux pouvoir modifier le comportement de chaque élément du visualiseur, dans la mesure où le moteur le permet.

Créer des commandes intuitives, essentiellement des curseurs, organisées par catégories.

### A. NOYAU CENTRAL

Réglages :
- Taille / rayon apparent.
- Luminosité.
- Opacité.
- Translucidité.
- Intensité du Fresnel.
- Saturation et nuance de couleur.
- Intensité des reflets.
- Vitesse de rotation ou mouvement de surface.
- Intensité et vitesse du plasma interne.
- Amplitude de respiration.
- Contraction pendant THINKING, avec 8 % comme valeur de référence.
- Lissage des transitions.

Préserver sa forme sphérique et l'impression de volume.

### B. HALO ET AURA

**Deux réglages sont absolument indispensables :**

- **Intensité lumineuse du halo.**
- **Taille / rayon de diffusion du halo.**

Ajouter également :
- Opacité du halo.
- Douceur de diffusion.
- Intensité du bloom.
- Seuil du bloom.
- Réactivité à la voix.
- Amplitude des pulsations.
- Lissage des pulsations.
- Vitesse de retour au calme.
- Contribution des graves, médiums et aigus au mouvement lumineux.

La taille du halo et sa luminosité doivent être deux paramètres indépendants.

Augmenter sa taille ne doit pas automatiquement augmenter son intensité.

Préserver le fond noir absolu `#000000`.

### C. ANNEAUX ORBITAUX

Réglages :
- Taille / rayon orbital.
- Épaisseur.
- Luminosité.
- Opacité.
- Nombre d'anneaux, dans les limites prises en charge.
- Espacement.
- Vitesse de rotation globale.
- Multiplicateur de vitesse THINKING.
- Multiplicateur de vitesse SPEAKING.
- Inclinaison / orientation.
- Intensité des traînées.
- Lissage des accélérations.

Préserver les axes multiaxiaux indépendants.

Les réglages ne doivent pas casser le centrage du noyau, l'occlusion ou la projection 3D.

Prévoir un mode Simple avec peu de paramètres, et un mode Expert avec les paramètres d'orientation individuels.

### D. PARTICULES

**Ajouter impérativement un curseur de taille des particules.**

Autres réglages :
- Densité / quantité.
- Taille.
- Variation de taille.
- Luminosité.
- Opacité.
- Vitesse.
- Dispersion autour du noyau.
- Distance de distribution.
- Durée de vie.
- Intensité des traînées.
- Variation des couleurs.
- Réaction éventuelle à la voix.

Prévoir des limites raisonnables pour protéger les performances.

La modification de quantité ne doit pas entraîner d'allocation GPU incontrôlée.

### E. EXPRESSIONS ET MORPHING

Réglages :
- Luminosité des traits gravés.
- Épaisseur des traits.
- Opacité.
- Taille apparente du visage.
- Durée des transitions.
- Durée de maintien.
- Vitesse de réorganisation des anneaux.
- Intensité de l'illumination du noyau pendant l'expression.

Ne jamais remplacer la sphère par un emoji plat.

Préserver les huit familles actuelles.

### F. COMPORTEMENTS PAR ÉTAT

Prévoir des réglages distincts ou des multiplicateurs pour :

- IDLE.
- LISTENING.
- THINKING.
- SPEAKING.
- MORPHING.

Exemples :
- Vitesse des anneaux pendant THINKING.
- Vitesse des anneaux pendant SPEAKING.
- Contraction du noyau pendant THINKING.
- Sensibilité audio pendant LISTENING.
- Intensité de l'aura pendant SPEAKING.

Éviter la duplication inutile : un paramètre général et des multiplicateurs par état constituent une bonne approche.

---

## 2 — ERGONOMIE DU CENTRE DE CONTRÔLE

Ne pas ajouter cinquante curseurs dans une seule fenêtre.

Réutiliser le Centre de contrôle à cinq familles et PRESENCE Studio.

Organiser l'éditeur PRESENCE autour des sections :

- Noyau.
- Anneaux.
- Halo et lumière.
- Particules.
- Animations et états.
- Expressions.
- Performances.

Conserver trois niveaux :

**Essentiel**
Les réglages les plus utiles : taille du noyau, luminosité et taille du halo, vitesse des anneaux, densité et taille des particules.

**Personnaliser**
Couleurs, opacité, réactions audio, rotations, transitions, intensité des effets.

**Avancé**
Paramètres des shaders, orientation individuelle, seuils, limites de performance et diagnostics.

Utiliser la recherche existante pour retrouver rapidement un réglage.

Afficher une aide contextuelle claire.

Conserver les fonctionnalités transactionnelles :
- Avant / Après.
- Appliquer.
- Annuler.
- Restaurer.
- Préréglages.

### Prévisualisation

Chaque curseur doit produire un effet réellement visible sur le rendu GPU.

Prévoir un aperçu GPU dédié ou un canal de prévisualisation isolé, en respectant l'architecture Tkinter / GLFW existante.

Les modifications non appliquées ne doivent pas affecter durablement le renderer principal.

Ne pas multiplier inutilement les processus, fenêtres OpenGL ou contextes GPU.

### Persistance

Utiliser la configuration locale existante et ses mécanismes de validation.

Conserver les préférences après redémarrage.

Prévoir des valeurs par défaut et une migration sûre.

Ne jamais casser une ancienne configuration.

Ne pas créer une deuxième source de vérité concurrente dans des fichiers JSON indépendants.

### Préréglages

Maintenir :
- Éco.
- Équilibré.
- Cinématique.

Ajouter éventuellement un système de profils personnalisés nommés, sans multiplier les réglages stockés inutilement.

Permettre la restauration du style GPU 3.0 actuellement approuvé.

---

## 3 — INTÉGRATION DU GPU DANS JARVIS PRINCIPAL

### Principe impératif

**PRESENCE GPU doit devenir un moteur de rendu optionnel de JARVIS, pas remplacer immédiatement Canvas.**

Conserver un sélecteur :

- Automatique.
- Canvas — Compatibilité / secours.
- GPU — Qualité avancée.

Au premier lancement, conserver le comportement stable actuel, sauf validation explicite de l'utilisateur.

Permettre ensuite de choisir GPU comme moteur préféré.

### Architecture

Auditer les composants existants avant de choisir la méthode d'intégration.

Mettre en place une interface commune pour les événements visuels :

- État courant.
- RMS microphone.
- Activité vocale VAD.
- Énergie et bandes spectrales de sortie.
- Début / fin d'inférence.
- Premier token / génération.
- Début / fin de TTS.
- Événements Semantic Morphing.
- Interruption.
- Paramètres graphiques.
- Préférences d'accessibilité.

Adapter Canvas et ModernGL à ce contrat.

Ne pas dupliquer la logique métier entre moteurs.

Ne pas réécrire Ollama, Whisper, Piper ou SQLite.

### Processus et fenêtre

Choisir la solution la plus robuste pour Windows 11 après étude :

- Fenêtre GPU séparée pilotée par JARVIS.
- Ou intégration native dans la fenêtre PRESENCE si faisable de manière fiable.

**Ne pas imposer l'intégration de GLFW dans le thread Tkinter si elle introduit des problèmes de boucle d'événements.**

Une fenêtre GPU séparée mais contrôlée de façon transparente par JARVIS est acceptable pour la première version intégrée.

Si un processus séparé est nécessaire, utiliser un canal local borné, simple et robuste.

Pas de communication cloud.

Prévoir :
- Initialisation.
- État prêt.
- Transmission des événements.
- Gestion des erreurs.
- Fermeture propre.
- Redémarrage contrôlé.
- Absence de processus orphelin.

---

## 4 — CONNEXION AU MICROPHONE RÉEL

En mode GPU intégré :

- Utiliser le microphone déjà géré par JARVIS.
- Ne jamais ouvrir le périphérique une seconde fois depuis le renderer.
- Réutiliser les données RMS / VAD du pipeline existant.
- Transmettre les informations visuelles utiles à cadence limitée.
- Animer l'écoute à partir de véritables mesures audio.
- Assurer un retour calme pendant les silences.

Aucun faux signal PCM.

Le mode aperçu peut conserver des données synthétiques, explicitement identifiées.

---

## 5 — CONNEXION À LA VOIX PIPER

La bibliothèque d'analyse spectrale trois bandes est déjà préparée dans le prototype GPU.

La raccorder maintenant à la lecture audio réelle de JARVIS.

Objectif :

**Quand JARVIS parle, son aura pulse en fonction de sa vraie voix.**

- Graves : expansion douce du halo.
- Médiums : intensité lumineuse du noyau.
- Aigus : détails lumineux et scintillement fin des anneaux.

Utiliser les échantillons correspondant à l'audio effectivement en cours de lecture, en tenant compte de la latence et des buffers.

Ne pas simplement analyser tout le WAV avant la lecture puis animer indépendamment.

Préserver :
- Arrêt.
- Interruption.
- Reprise.
- Annulation.
- Sortie casque / haut-parleurs.
- Priorité de l'état réel.

Les calculs audio doivent rester hors du thread graphique.

Cadence bornée, file bornée et rejet des événements obsolètes.

---

## 6 — CONVERSATION ET SEMANTIC MORPHING

Le moteur GPU doit recevoir les vrais événements issus de JARVIS.

Conserver :
- Le noyau sphérique.
- Les expressions gravées.
- Les anneaux concentriques pendant le morphing.
- Les huit familles existantes.
- Les annulations.
- Les exclusions du code et des exemples techniques.
- La synchronisation approximative actuelle, sans promesse de synchronisation mot à mot.

Vérifier une séquence réelle :

L'utilisateur parle → JARVIS écoute → Whisper transcrit → Ollama réfléchit → Piper parle → Une expression apparaît sur le noyau → Retour au repos.

La chronologie visuelle doit suivre les vrais événements logiciels, pas un script indépendant.

---

## 7 — PERFORMANCES, SÉCURITÉ ET ACCESSIBILITÉ

Matériel cible : RTX 3070 8 Go.

Priorités :
1. Stabilité de JARVIS.
2. Qualité de la conversation locale.
3. Fluidité audio.
4. Faible consommation CPU/RAM/VRAM.
5. Qualité graphique.

Conserver :
- Profils Éco / Équilibré / Cinématique.
- Réduction des mouvements.
- Suspension ou forte réduction du rendu lorsque la fenêtre est masquée.
- Limitation du FPS.
- Ressources GPU bornées.
- Pas de dépendance lourde.
- Pas de cloud.
- Pas de téléchargement graphique automatique.
- Repli Canvas.

### Gestion des erreurs

Si le GPU est indisponible, le shader échoue, la fenêtre plante ou le renderer ne répond plus :

- Signaler une erreur utile.
- Revenir à Canvas.
- Continuer la conversation sans interruption.
- Éviter les boucles infinies de redémarrage.
- Préserver les paramètres.
- Nettoyer le processus GPU.

Ne pas faire planter Jarvis.exe à cause du visualiseur.

### Mesures

Lorsque possible :
- FPS réels.
- Frametime moyen et P95.
- CPU.
- RAM.
- VRAM GPU réelle si disponible.
- Coût au repos.
- Temps d'initialisation.
- Impact sur TTFT et tokens/s d'Ollama.
- Latence audio.

Différencier les mesures Mesa des mesures RTX réelles.

Ne jamais annoncer un résultat Windows matériel non testé.

---

## 8 — PLAN D'EXÉCUTION

Ne pas tout développer dans un seul commit.

### Phase 1 — Audit et contrats

Étudier les composants existants.

Définir :
- Contrat commun des événements.
- Contrat des paramètres graphiques.
- Stratégie Windows du renderer GPU.
- Migration des préférences.
- Stratégie de retour Canvas.

Tester les interfaces avant d'implémenter l'intégration complète.

### Phase 2 — Paramètres graphiques

Ajouter les curseurs de personnalisation.

Commencer par :
- Luminosité du halo.
- Taille du halo.
- Taille des particules.
- Densité des particules.
- Vitesse des anneaux.
- Taille du noyau.

Puis ajouter les commandes avancées dont le comportement est réellement implémenté.

Prévisualisation et persistance validées.

### Phase 3 — Intégration optionnelle

Piloter PRESENCE GPU depuis JARVIS.

Préserver Canvas.

Ajouter le sélecteur de moteur.

Valider ouverture, fermeture, états, communication et secours.

### Phase 4 — Audio et expressions réelles

Brancher les événements microphone, Ollama et Piper.

Synchroniser l'aura aux données de lecture réelles.

Transmettre les événements Semantic Morphing.

Tester les interruptions et les séquences complètes.

### Phase 5 — Optimisation et validation

Tests ciblés et de non-régression.

Captures et vidéo de démonstration.

Packaging Windows.

CI.

Benchmarks disponibles.

Procédure d'essai local Windows 11 avec RTX 3070, Ollama et Piper.

---

## 9 — LIVRAISON ET CRITÈRES D'ACCEPTATION

Pour chaque phase :
- Commit distinct.
- Push sur `feat/jalon-2-voice-presence`.
- Tests automatisés pertinents.
- CI Windows.
- Documentation mise à jour.
- Rapport des limitations.

Ne pas toucher `main`.

Ne pas entamer automatiquement les autres lots de la feuille de route Cognitive & Presence.

### Critères d'acceptation

1. Le style artistique de PRESENCE GPU 3.0 est préservé.
2. Le fond reste noir absolu.
3. Le halo possède des curseurs indépendants pour taille et luminosité.
4. Les particules possèdent un réglage de taille.
5. Les composants disposent de paramètres de vitesse, taille, lumière et opacité lorsque cela a un sens technique.
6. Les modifications sont prévisualisables et persistantes.
7. Les états du renderer suivent les événements réels de JARVIS.
8. Le microphone existant fonctionne toujours.
9. L'aura réagit à la voix Piper effectivement jouée.
10. Les expressions restent gravées sur la sphère.
11. Les interruptions sont respectées.
12. Canvas demeure disponible immédiatement.
13. Une panne GPU n'interrompt pas la conversation.
14. L'application Windows principale peut toujours être compilée.
15. Aucune validation RTX réelle n'est revendiquée sans essai matériel.

**POINT DE CONTRÔLE IMPORTANT**

Après la phase 3, réaliser un premier bilan d'intégration.

Si le renderer GPU fonctionne dans JARVIS mais que les événements audio réels ne sont pas encore raccordés, le signaler explicitement.

Si des problèmes architecturaux bloquants apparaissent, conserver la version fonctionnelle et documenter les choix plutôt que forcer un remplacement fragile.

**OBJECTIF FINAL**

Je veux conserver le visualiseur holographique que j'ai approuvé, tout en pouvant personnaliser finement chacun de ses composants.

Je veux ensuite retrouver ce même noyau dans mon JARVIS quotidien, réagissant réellement à ma voix, à son activité cognitive, à sa parole et à ses expressions.

Le résultat doit rester fluide, performant, local, modulaire et fiable, même avec une RTX 3070 de 8 Go.