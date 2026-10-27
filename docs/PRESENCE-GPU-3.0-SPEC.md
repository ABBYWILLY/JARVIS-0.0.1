> Demande utilisateur conservée. **Portée de cette session : A + B uniquement.**
> Arrêt obligatoire ensuite pour validation artistique utilisateur ; C, D, E et F différés.
> Les preuves visuelles et contrôles techniques ci-dessous sont limités à cette revue intermédiaire.

# JARVIS — PRESENCE GPU 3.0
## CINEMATIC LIVING CORE — Direction artistique, animation, optimisation et validation

**Dépôt officiel :** https://github.com/ABBYWILLY/JARVIS-0.0.1

**Branche de développement :** `feat/jalon-2-voice-presence`

**Mission :** perfectionner le prototype graphique GPU de PRESENCE jusqu'à obtenir un noyau holographique vivant, élégant, expressif et visuellement remarquable, en s'inspirant des qualités artistiques du rendu Unreal Engine, sans utiliser Unreal Engine ni introduire de moteur lourd.

Ne jamais modifier `main`.

---

## 0. PHILOSOPHIE ET CONTRAINTES

JARVIS doit devenir une IA personnelle locale, agentique et multimodale.

La performance de l'intelligence artificielle reste prioritaire sur les effets graphiques.

Matériel de référence :
- NVIDIA RTX 3070 — 8 Go VRAM.
- Windows 11.
- Ollama et modèles Qwen locaux.
- Whisper, VAD et Piper.
- RAM, CPU, VRAM, stockage et énergie à optimiser.

Exigences :
- Gratuit.
- Local-first.
- Pas de cloud obligatoire.
- Installation simple.
- Modularité.
- Compatibilité avec matériel plus puissant à l'avenir.
- Pas de modèle IA supplémentaire pour produire les animations.
- Pas de dépendance graphique lourde imposée à `Jarvis.exe`.

Le prototype GPU ModernGL reste autonome jusqu'à validation matérielle réelle.

Préserver Canvas en production.

Avant toute modification, inspecter le dépôt, les derniers commits et les shaders existants.

Ne pas réimplémenter ce qui fonctionne.

---

# 1. RÉFÉRENCE ARTISTIQUE PRIORITAIRE

La référence principale fournie par l'utilisateur représente :

**Une sphère énergétique translucide, bleu-violet iridescent, entourée de grands anneaux lumineux rappelant Saturne, sur un fond parfaitement noir.**

Cette composition doit guider le rendu.

Ne pas copier d'asset tiers ni les images Adobe Stock précédemment partagées.

Reproduire uniquement les principes artistiques :
- Sphère centrale dominante.
- Composition aérée.
- Anneaux amples et élégants.
- Lumière concentrée sur les contours.
- Surface translucide.
- Reflets iridescents.
- Relief évident.
- Halo doux mais intense.
- Grande quantité d'espace négatif.

### RÈGLE ABSOLUE — FOND NOIR

**Le fond du visualiseur doit être noir pur : `#000000`, RGB `(0, 0, 0)`.**

Aucun dégradé bleu, gris ou violet dans l'arrière-plan.

Aucune texture de fond, vignette colorée ou brouillard ambiant.

Les seules couleurs visibles proviennent du noyau, des anneaux, des particules, des halos et des éventuels éléments d'interface volontairement superposés.

Le bloom des objets peut naturellement s'étendre sur le noir, mais le fond lui-même reste noir.

Cette règle concerne le rendu PRESENCE GPU, sans imposer automatiquement un fond noir à COMMAND OS.

---

# 2. RECOMPOSITION — MOINS D'ÉLÉMENTS, PLUS DE QUALITÉ

Le rendu précédent était encombré par les intersections de lignes, les arcs multiples et les particules.

Je souhaite un résultat beaucoup plus épuré.

### Le noyau

- Une sphère dominante, volumique et immédiatement reconnaissable.
- Surface translucide.
- Centre relativement sombre.
- Bord lumineux.
- Matière énergétique intérieure subtile.
- Reflets doux.
- Impression d'épaisseur et de profondeur.

### Les anneaux

- Deux à trois grandes orbites principales par défaut.
- Trajectoires clairement séparées.
- Inclinaisons tridimensionnelles.
- Portions avant/arrière correctement occultées.
- Anneaux concentriques lorsque le contexte l'exige.
- Variation subtile d'épaisseur, de brillance et de profondeur.

### Les particules

- Peu nombreuses.
- Distribuées intentionnellement.
- Mouvements fluides et cohérents.
- Quelques particules parcourant les anneaux.
- Aucune tempête permanente de points lumineux.

### Les filaments

Réserver les filaments énergétiques aux moments importants.

Ne pas encombrer constamment le noyau.

La composition doit rester lisible sur une capture statique.

---

# 3. SHADERS — QUALITÉ VISUELLE CINÉMATIQUE

## A. Fresnel iridescent

Créer un éclairage de bord dépendant de l'angle de vue.

Palette :
- Cyan lumineux.
- Bleu électrique.
- Violet.
- Magenta discret.

La périphérie doit être plus lumineuse que le centre.

Éviter la surexposition blanche permanente.

## B. Matière de verre énergétique

Donner à la sphère :
- Une translucidité contrôlée.
- Une épaisseur optique simulée.
- Un dégradé intérieur.
- Des différences de lumière entre face et bord.
- Une légère impression de réfraction, si le coût reste faible.

Priorité à la crédibilité du volume.

## C. Bloom HDR sélectif

Améliorer le halo sans rendre l'image floue.

Utiliser si pertinent :
- Buffer HDR.
- Extraction des hautes lumières.
- Flou à résolution réduite.
- Composition additive contrôlée.
- Réglages d'intensité et de rayon.

Ne pas multiplier les passes coûteuses.

Mesurer leur coût réel.

## D. Reflets spéculaires

Ajouter quelques reflets mobiles suivant la courbure du noyau.

Éviter l'effet boule de plastique.

## E. Plasma intérieur

Créer une animation lente et subtile de matière énergétique sous la surface.

Préférer un bruit procédural léger.

Aucune simulation volumétrique lourde.

## F. Aberration chromatique

Effet très discret, uniquement sur les zones lumineuses.

Désactivable.

Ne jamais sacrifier la netteté générale.

---

# 4. ANIMATION — PHYSIQUE VISUELLE ET INERTIE

Les animations doivent avoir un comportement organique.

Je souhaite :
- Des accélérations progressives.
- Des décélérations douces.
- Une sensation de masse.
- Des rotations orbitales indépendantes.
- Une respiration du noyau.
- Une parallaxe discrète.
- Des transitions continues.

Éviter :
- Les changements brusques de géométrie.
- Les clignotements.
- Les rotations identiques sur tous les anneaux.
- Les particules aléatoires incohérentes.
- Les effets qui se déclenchent sans raison.

Utiliser des fonctions d'easing, une animation fondée sur le temps monotone et des trajectoires déterministes.

---

# 5. ÉTATS VISUELS — UN SEUL OBJET VIVANT

Le noyau doit rester l'identité principale de PRESENCE.

## IDLE — Veille

Sphère stable et faiblement lumineuse.

Anneaux presque immobiles.

Halo discret.

Aucun faux mouvement audio.

Consommation minimale.

Option de présentation en ligne classique conservée.

## LISTENING — Écoute

Sphère clairement visible.

Anneaux ouverts et relativement calmes.

La surface réagit au véritable PCM/RMS du microphone.

Une petite onde énergétique traverse la surface lorsque l'utilisateur parle.

Le noyau augmente légèrement en intensité lors d'une véritable activité vocale.

Retour rapide au calme pendant le silence.

Aucun signal fictif.

## THINKING — Réflexion

Cet état doit devenir le point fort visuel de PRESENCE.

Séquence d'entrée :
1. Le noyau se densifie.
2. Les orbites se rapprochent légèrement.
3. Une impulsion lumineuse traverse la sphère.
4. Les anneaux prennent des inclinaisons différentes.
5. Leur rotation accélère avec inertie.

Pendant l'inférence :
- Noyau volumique stable.
- Rotations orbitales clairement lisibles.
- Flux de lumière sur les anneaux.
- Léger plasma intérieur.
- Respiration énergétique.
- Parallaxe subtile.

Sortie :
- Décélération des orbites.
- Stabilisation des reflets.
- Transition naturelle vers la parole ou le repos.

Ne jamais afficher de faux pourcentage de progression.

Ne pas prétendre représenter les véritables calculs internes du LLM.

## SPEAKING — Parole

Conserver la sphère.

Faire réagir sa luminosité et sa surface au vrai PCM Piper.

Les anneaux ralentissent pour privilégier la lecture visuelle.

Éventuellement, de fines ondulations sphériques rayonnent autour du noyau.

Les sous-titres restent lisibles.

Aucune waveform fictive.

## INTERRUPTION

Annuler immédiatement les animations et expressions obsolètes.

Revenir vers l'état réel correspondant.

Aucun effet différé d'une ancienne réponse.

---

# 6. SEMANTIC MORPHING — GRAVURE HOLOGRAPHIQUE SUR LA SPHÈRE

Je souhaite abandonner l'idée d'un emoji plat remplaçant brutalement le noyau dans le prototype GPU.

Le noyau doit conserver son volume.

Lorsqu'une expression est détectée :

1. Les anneaux ralentissent.
2. Ils se disposent en couronnes concentriques élégantes autour de la sphère.
3. La surface visible du noyau s'oriente légèrement vers l'utilisateur.
4. Le symbole apparaît progressivement comme une gravure lumineuse.
5. Il reste visible durant la fenêtre d'expression.
6. Le symbole se dissipe.
7. Les anneaux reprennent leur configuration précédente.

### Emojis faciaux

Pour les expressions de sourire, rire, tristesse, colère, surprise, réflexion et clin d'œil :

- Dessiner les yeux et la bouche sur la face visible.
- Adapter leurs courbes à la géométrie sphérique.
- Conserver leur reconnaissance visuelle.
- Ajouter les détails pertinents, comme les larmes pour le rire.

### Emojis non faciaux

Pour ❤️ et les autres familles compatibles :

- Dessiner le line art du symbole sur l'hémisphère visible.
- Épouser la courbure.
- Ne pas aplatir la sphère.
- Éviter les contours flottant devant le noyau.

### Implémentation

Réutiliser les huit familles actuellement prises en charge.

Projeter les coordonnées locales des tracés sur la surface visible.

Employer un shader de surface, un masque ou une géométrie projetée légère.

Maintenir la séparation :
- Texte original.
- Texte TTS.
- Événements d'expression.
- Rendu visuel.

Préserver les exclusions concernant le code et les exemples Unicode littéraux.

Ne pas annoncer une synchronisation mot à mot si le pipeline ne dispose que d'une synchronisation approximative par segment.

---

# 7. PRÉVISUALISATION COMPLÈTE

Le prototype doit permettre de tester facilement toutes les phases.

Ajouter une interface de démonstration claire, avec raccourcis visibles.

Scènes :
- IDLE.
- LISTENING simulé.
- THINKING prolongé.
- SPEAKING simulé.
- Sourire.
- Rire.
- Affection.
- Interruption.

Créer un scénario automatique complet :

IDLE → LISTENING → THINKING → SPEAKING → MORPHING → IDLE.

Maintenir THINKING suffisamment longtemps pour apprécier le mouvement orbital.

Afficher le SHA du build exécuté et le profil graphique.

Les données simulées doivent être explicitement identifiées.

Ne pas utiliser de faux PCM dans le fonctionnement réel de JARVIS.

---

# 8. PERSONNALISATION DANS PRESENCE STUDIO

Préparer la compatibilité du prototype GPU avec les réglages futurs du Studio.

Regrouper les commandes artistiques autour de :

- Brillance des contours.
- Translucidité du noyau.
- Intensité du bloom.
- Densité des particules.
- Vitesse orbitale.
- Intensité du plasma.
- Inclinaison des anneaux.
- Intensité des reflets.
- Complexité graphique.

Conserver les profils :
- Éco.
- Équilibré.
- Cinématique.

Ne pas dupliquer les préférences existantes.

Ne pas intégrer prématurément le prototype dans `Jarvis.exe`.

---

# 9. OPTIMISATION RTX 3070 — 8 GO VRAM

L'intelligence locale demeure prioritaire.

Préserver les ressources pour :
- Ollama.
- Qwen.
- Whisper.
- Piper.
- L'interface.
- Les futures capacités multimodales.

Privilégier :
- Shaders efficaces.
- Buffers réduits.
- Bloom à résolution adaptée.
- Faible nombre de draw calls.
- Géométrie mutualisée.
- Absence de recalcul Python par pixel.
- Suspension hors écran.
- FPS adaptatifs.
- Limites explicites de ressources.
- Repli Canvas.

Mesurer :
- CPU.
- RAM.
- VRAM réellement allouée quand accessible.
- FPS.
- Temps de frame P50/P95.
- Consommation au repos.
- Temps de démarrage.
- Stabilité.
- Impact sur les tokens/s et le TTFT Ollama quand le matériel est disponible.

Ne pas inventer de gains GPU ou de mesures RTX à partir des benchmarks Mesa logiciel.

---

# 10. RÉFÉRENCE MATÉRIELLE À CONSERVER DANS GITHUB

Ajouter une section de référence dans la documentation de performance du projet.

Source communautaire :

https://www.reddit.com/r/LocalLLM/comments/1u4lz1v/what_can_you_realistically_do_with_8gb_vram_in/

Sujet : « What can you realistically do with 8GB VRAM in 2026? »

Cette discussion aborde :
- Les limites pratiques de 8 Go de VRAM.
- Les modèles MoE quantifiés.
- L'offloading CPU/RAM.
- Les compromis contexte long / vitesse.
- La fiabilité de petits agents locaux.
- Les performances déclarées sur du matériel grand public.

Consignes :
- Étudier les contributions pertinentes et dater les références.
- Séparer témoignages individuels et mesures reproductibles.
- Ne pas appliquer directement les chiffres des participants à JARVIS.
- Ne pas modifier les modèles installés sur la seule base de commentaires Reddit.
- Conserver le lien dans une section « Ressources de recherche — IA locale 8 Go VRAM ».
- Utiliser cette référence lors de futures études matérielles, de benchmark ou de sélection de modèles.
- Préférer les mesures locales de la RTX 3070 réelle pour prendre les décisions.

Cette référence doit enrichir les futures décisions d'architecture, pas devenir une spécification technique obligatoire.

---

# 11. VALIDATION ARTISTIQUE ET TECHNIQUE

Produire des preuves issues du vrai moteur de rendu :

- Capture du noyau au repos.
- Capture THINKING.
- Capture LISTENING.
- Capture SPEAKING.
- Capture sourire gravé.
- Capture cœur gravé.
- Courte vidéo des transitions.
- Comparaison avant/après.

Comparer à résolution et profil identiques.

Vérifier :
- Fond noir RGB exact.
- Lisibilité du noyau.
- Volume apparent.
- Occlusion des anneaux.
- Séparation visuelle des couches.
- Qualité du bloom.
- Reconnaissance des expressions.
- Régularité des animations.
- Absence de fuite de ressources.
- Fermeture propre.

Les captures statiques ne remplacent pas la validation de fluidité.

Ne pas utiliser une image générée indépendamment comme preuve du rendu OpenGL.

Si le résultat reste visuellement encombré, simplifier les composants avant d'en ajouter.

---

# 12. MÉTHODE DE LIVRAISON

Procéder par sous-lots indépendants :

**A — Direction artistique**
Fond noir, composition aérée, noyau dominant et orbites simplifiées.

**B — Matière et lumière**
Fresnel, translucence, shading, reflets et bloom.

**C — Animations et états**
Inertie, écoute, réflexion, parole et interruptions.

**D — Morphing surfacique**
Expressions faciales et line art gravés sur l'hémisphère.

**E — Prévisualisations**
Scénarios, captures et séquences avant/après.

**F — Optimisation et validation**
Profils, benchmarks, tests, documentation et CI Windows.

Pour chaque sous-lot :
- Tests ciblés.
- Commit.
- Push.
- CI.
- Bilan court.

Ne pas modifier `main`.

Préserver les développements existants des lots 1, 3 et 6, ainsi que les composants du lot 2 déjà publiés.

Ne pas engager les lots 4, 5 ou 7 dans cette mission.

Ne pas remplacer Canvas en production.

---

# CRITÈRE FINAL

**Je veux que PRESENCE ressemble à une entité holographique vivante et élégante, pas à un regroupement de lignes et de particules.**

Son noyau possède une vraie matière.

Ses anneaux créent la profondeur.

Sa lumière révèle son volume.

Ses mouvements transmettent son activité.

Sa surface exprime ses émotions.

Son fond reste noir absolu.

Sa qualité artistique doit évoquer les effets graphiques de science-fiction d'un jeu vidéo moderne, tout en restant légère et optimisée.

L'expérience doit être spectaculaire par sa finition, sa composition et son animation, non par une accumulation d'effets.

La validation esthétique finale sur Windows appartient à l'utilisateur.