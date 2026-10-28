# JARVIS — PRESENCE GPU 3.1
## Fluidité 60 FPS, netteté HiDPI, expressivité vocale et ergonomie

**Dépôt :** `ABBYWILLY/JARVIS-0.0.1`  
**Branche :** `feat/jalon-2-voice-presence`  
**Base de référence connue :** `4ae4f71` — vérifier le HEAD actuel avant toute modification.

**Ne jamais modifier `main`.**

## 0. CONTEXTE ET OBJECTIF

Le double moteur PRESENCE est désormais intégré dans JARVIS : Canvas 2D et ModernGL 2.5D.

La direction artistique du noyau holographique est validée par l'utilisateur.

**Ne pas refaire le design actuel.**

Ce que j'apprécie déjà :
- Sphère iridescente et volumique.
- Trois anneaux orbitaux multiaxiaux.
- Particules et halos.
- Fond noir absolu.
- Gravure des expressions sur la sphère.
- Personnalisation avancée.
- Possibilité de choisir entre 2D et 2.5D.

Après utilisation réelle sous Windows 11, j'ai identifié les améliorations suivantes :

1. L'animation GPU manque de fluidité : viser 60 FPS réels.
2. Le rendu 2.5D est trop pixelisé.
3. L'aura ne pulse pas suffisamment lorsque JARVIS parle.
4. Le choix 2D/2.5D est trop enfoui dans les paramètres.
5. L'écoute utilisateur et la parole JARVIS doivent avoir des signatures visuelles immédiatement distinctes.

### Philosophie

Maximiser la qualité perceptuelle par unité de ressources.

Matériel cible : RTX 3070 8 Go, avec Ollama et la chaîne vocale locale fonctionnant simultanément.

Aucun moteur lourd supplémentaire, aucun cloud, aucune refonte globale.

**Priorité : fiabilité de JARVIS > audio > inférence > fluidité graphique > effets secondaires.**

---

# 1. AUDIT INITIAL OBLIGATOIRE

Avant de coder :

- Inspecter le dernier HEAD de la branche.
- Vérifier l'architecture réelle Canvas / processus GPU / IPC / Studio / audio.
- Vérifier les 66 paramètres GPU existants.
- Identifier les réglages déjà présents pour halo, particules, qualité et animation.
- Diagnostiquer les limitations de FPS, de résolution et de frame pacing.
- Examiner les plafonds de cadence, le VSync, les attentes, les timers, les allocations et les transferts CPU↔GPU.
- Inspecter les dimensions physiques du framebuffer, le DPI Windows et les buffers de post-traitement.

Ne pas conclure que le GPU est trop lent sans mesurer.

Ne pas ajouter de curseur qui existe déjà.

Documenter brièvement les causes constatées et distinguer hypothèses et mesures.

---

# 2. FLUIDITÉ — OBJECTIF 60 FPS

**Objectif nominal : 60 images réellement rendues par seconde dans les états animés, avec un frame pacing régulier.**

Ne pas se contenter de changer une constante FPS ou de déclarer 60 FPS en comptant des images répétées.

### Implémentation

- Vérifier et corriger les éventuels plafonds historiques de 30/45 FPS.
- Viser environ 16,7 ms par frame lorsque la scène est animée.
- Synchroniser proprement la présentation à l'écran selon les capacités du pilote.
- Éviter le busy-wait et les boucles gourmandes en CPU.
- Décorréler fréquence d'animation, fréquence d'analyse audio et fréquence de rendu.
- Conserver l'animation basée sur le temps réel pour éviter les changements de vitesse selon les FPS.
- Optimiser les allocations, transferts, shaders et passes avant de réduire la qualité.
- Maintenir les états de repos et de fenêtre masquée économes en énergie.

### Qualité adaptative

Conserver Éco / Équilibré / Cinématique.

Prévoir une adaptation graduelle des coûts graphiques si les temps de frame dépassent durablement le budget :
- Résolution du bloom.
- Particules secondaires.
- Résolution interne du rendu.
- Effets non essentiels.

Éviter les changements incessants de qualité : hystérésis, temporisation et restauration progressive.

Ne jamais dégrader brutalement le noyau principal.

Si 60 FPS stables ne sont pas atteignables avec Ollama actif, présenter les performances mesurées et les compromis, sans inventer de résultat.

### Mesures

Mesurer :
- FPS réellement dessinés et présentés si observable.
- Frame time moyen, P50, P95 et P99.
- Frames longues ou saccadées.
- Charge CPU du processus GPU.
- Mémoire RAM.
- Mémoire GPU lorsque la mesure est disponible et correctement attribuable.
- Impact sur la génération Ollama et la lecture Piper.

Distinguer fréquence de rafraîchissement du moniteur, cadence de rendu et cadence d'encodage des vidéos.

---

# 3. NETTETÉ — DPI WINDOWS ET RÉSOLUTION ADAPTATIVE

Le rendu actuel paraît pixelisé sur mon écran.

**Corriger la cause réelle avant d'augmenter aveuglément la résolution.**

### Diagnostic

Inspecter :
- Taille logique de la fenêtre.
- Taille physique du framebuffer OpenGL.
- Facteur DPI Windows.
- Viewport OpenGL.
- Résolution des buffers internes.
- Interpolation et filtrage.
- Résolution du HUD et des sous-titres.
- Effets du bloom sur la netteté des contours.

### Implémentation

- Rendre la géométrie principale à la résolution physique du framebuffer.
- Gérer correctement les changements DPI et le déplacement entre moniteurs.
- Recréer proprement les ressources dépendantes de la résolution.
- Conserver des contours nets et correctement anticrénelés.
- Ne pas confondre résolution du noyau et résolution du bloom.
- Adapter le HUD à la densité physique d'affichage.

Ajouter un réglage **Échelle de rendu GPU** :
- Auto.
- 100 %.
- 125 %.
- 150 %.
- 200 % si matériel et budget compatibles.

Ces valeurs représentent des facteurs par rapport à la résolution physique utile, non une résolution fixe imposée.

Ne pas forcer systématiquement 2.3K.

Préférer une résolution native nette et un anticrénelage approprié à un supersampling excessif.

Prévoir des plafonds de pixels et de mémoire, avec indication de la résolution réellement utilisée.

### Critère

À dimensions de fenêtre comparables, les anneaux, les contours de la sphère, les particules et les textes doivent être visiblement plus nets.

Fournir des captures natives, sans redimensionnement artificiel.

---

# 4. CHOIX 2D / 2.5D DIRECTEMENT DANS PRESENCE

L'utilisateur ne doit plus passer par plusieurs menus pour changer de moteur.

Ajouter un contrôle compact, discret et permanent **en haut à gauche de la fenêtre PRESENCE**.

Présentation souhaitée :

**[ 2D | 2.5D ]**

Conserver le mode Automatique dans les paramètres avancés existants.

### Comportement

- Le contrôle doit exister dans les deux moteurs, Canvas et GPU.
- Il doit être réellement interactif.
- Il doit indiquer le moteur actif.
- Il doit permettre le basculement dans les deux sens.
- Le choix doit être persistant.
- Aucun redémarrage complet de JARVIS.
- Aucun redémarrage Ollama ou Piper.
- Aucune réouverture du microphone.
- Aucune perte de conversation ou d'historique.
- Aucune seconde fenêtre PRESENCE visible simultanément.

### Contrainte architecturale importante

La fenêtre GPU est actuellement un processus GLFW distinct.

Ne pas ajouter un faux bouton uniquement graphique.

Raccorder le clic GPU au parent via le protocole IPC existant ou un message de commande borné et validé.

Le parent reste seul responsable du choix de moteur.

Prévoir également un raccourci clavier commun, documenté et sans conflit.

Si le GPU échoue, basculer vers Canvas et afficher une explication accessible.

Conserver le choix dans le Centre de contrôle comme alternative.

---

# 5. PAROLE JARVIS — AURA PLUS EXPRESSIVE

La modulation actuelle du halo pendant SPEAKING est trop faible visuellement.

Je souhaite une réaction nettement perceptible, sans surexposition.

### Préserver l'architecture actuelle

Réutiliser la vraie chaîne PCM Piper et l'analyse trois bandes déjà implémentée.

Ne pas ajouter de seconde capture ou lecture audio.

Ne pas analyser tout le fichier indépendamment de la lecture réelle.

Ne pas modifier la voix ni le contenu prononcé.

### Rendu souhaité

Créer une pulsation énergétique sur trois échelles :

**Halo proche**
- Réponse lumineuse rapide et précise à la voix.
- Accent visible sur les syllabes.

**Halo intermédiaire**
- Dilatation et rétraction souples.
- Intensité dépendante de l'énergie sonore.

**Aura externe**
- Expansion diffuse et plus lente.
- Sensation de projection d'énergie.

Associer les bandes fréquentielles existantes :
- Graves : expansion de l'aura.
- Médiums : luminosité et respiration du noyau.
- Aigus : détails spéculaires et scintillement subtil.

### Traitement du signal

- Normalisation et compression douce.
- Seuil de silence.
- Lissage distinct attaque / relâchement.
- Limitation de l'amplitude maximale.
- Absence de stroboscope.
- Aucun halo géant permanent.

Préserver les expressions gravées et leur lisibilité.

Exposer les réglages pertinents dans le Studio existant :
- Gain de réactivité audio.
- Amplitude de pulsation.
- Rayon de pulsation.
- Attaque.
- Relâchement.

Ne pas dupliquer les réglages déjà existants.

---

# 6. LANGAGE VISUEL — ÉTATS DISTINCTS

Créer un langage visuel cohérent à partir du même noyau, sans ajouter d'effets gratuits.

## A. IDLE — REPOS

- Noyau calme.
- Orbites très lentes ou immobiles selon l'accessibilité.
- Halo discret.
- Aucune activité audio simulée.
- Consommation minimale.

## B. LISTENING — L'UTILISATEUR PREND LA PAROLE

**Signature : l'énergie entre vers le noyau.**

Lorsque le microphone est réellement activé :

- Préparer une posture visuelle attentive.
- Orbites légèrement plus ouvertes.
- Halo froid et maîtrisé.

Lorsque le VAD confirme la parole :

- Déclencher une courte animation d'accusé de réception.
- Les particules convergent doucement vers le centre.
- Des impulsions lumineuses parcourent les anneaux vers la sphère.
- Le noyau absorbe visuellement cette énergie.
- Une fine réaction de surface suit le RMS réel.

Différencier clairement :
- Micro activé, silence.
- Parole effectivement détectée.
- Fin de tour de parole.

À la fin du tour :
- Une courte convergence lumineuse marque la réception.
- Transition continue vers THINKING ou TRANSCRIBING selon les véritables états disponibles.

Ne jamais simuler une transcription réussie si elle a échoué.

## C. THINKING — CONCENTRATION

**Signature : énergie contenue et mouvement orbital rapide.**

Conserver :
- Contraction actuelle du noyau d'environ 8 %.
- Trois anneaux sur axes 3D indépendants.
- Accélération orbitale progressive.
- Densification lumineuse intérieure.
- Halo moins expansif que pendant SPEAKING.

Les particules doivent davantage suivre les orbites que rayonner vers l'extérieur.

Pas de faux indicateur de progression cognitive.

## D. SPEAKING — JARVIS S'EXPRIME

**Signature : l'énergie sort du noyau.**

Au début de la lecture Piper :
- Légère expansion initiale.
- Stabilisation des anneaux.
- Activation de l'aura vocale.

Pendant la parole :
- Pulsation forte mais maîtrisée en synchronisation avec le PCM.
- Impulsions lumineuses qui rayonnent de la sphère vers les anneaux.
- Quelques particules qui s'éloignent du centre.
- Noyau dominant.
- Anneaux lents et élégants.
- Expressions gravées préservées.

Entre deux segments :
- Relâchement progressif de l'aura.
- Pas de retour brutal à IDLE.

À la fin :
- Décélération et retour au calme.

## E. INTERRUPTION

- Réaction immédiate.
- Annulation des anciens effets audio et des expressions obsolètes.
- Extinction rapide et douce des émissions.
- Aucune animation résiduelle de la réponse annulée.

### Critère de lisibilité

Même sans sous-titres, je dois pouvoir distinguer en quelques instants :

- Moi qui parle : énergie convergente.
- JARVIS qui réfléchit : énergie concentrée et rotations rapides.
- JARVIS qui parle : énergie rayonnante, aura vocale expressive.

Conserver le fond noir pur `#000000`.

---

# 7. STUDIO — NE PAS REFAIRE LES 66 CONTRÔLES EXISTANTS

Le dépôt contient déjà un éditeur GPU avancé.

L'objectif est de compléter et de corriger celui-ci, pas de créer un deuxième panneau concurrent.

Auditer les commandes existantes et ajouter uniquement les paramètres réellement manquants, notamment :

- Échelle de rendu.
- Réactivité audio expressive.
- Intensité des animations convergentes.
- Intensité des animations rayonnantes.
- Éventuels réglages d'attaque et de relâchement.

Conserver :
- Les six commandes essentielles.
- Les niveaux Essentiel / Personnaliser / Avancé.
- Les favoris.
- Avant / Après.
- Appliquer / Annuler.
- Profils de qualité.
- Configuration SQLite unique.
- Préférences séparées Canvas / GPU.

Chaque curseur doit contrôler un effet réel, borné, mesurable et persistable.

Préserver le style GPU 3.0 validé comme préréglage de référence.

---

# 8. TESTS, PREUVES ET VALIDATION

### Tests automatisés

Couvrir :
- Changement 2D ↔ 2.5D par les commandes visibles.
- Clics et événements IPC dans les deux directions.
- Persistance du moteur sélectionné.
- Fallback Canvas.
- Redimensionnement et changements DPI.
- Résolution physique du framebuffer.
- Réglages d'échelle de rendu.
- Synchronisation des pulsations au vrai timing PCM.
- Différenciation LISTENING / SPEAKING.
- Interruptions et événements obsolètes.
- Absence de fuite de ressources.
- Maintien du noyau et des expressions gravées.

### Preuves visuelles

Produire avec le vrai renderer :

- Comparaison de netteté avant/après.
- Vidéo THINKING multiaxiale.
- Vidéo LISTENING avec signal de test clairement identifié.
- Vidéo SPEAKING avec PCM de test clairement identifié.
- Démonstration du basculement 2D / 2.5D.
- Captures du contrôle de moteur dans les deux fenêtres.

Les signaux synthétiques doivent être explicitement identifiés.

Ne pas prétendre avoir effectué un test réel sur mon microphone ou ma RTX si ce n'est pas le cas.

### Benchmarks

Comparer sur la même scène :
- Ancienne version.
- Nouvelle version.
- Équilibré.
- Cinématique.
- Résolution native.
- Échelle 125 % et 150 %, lorsque pertinent.

Conserver les rapports bruts.

Ne pas confondre FPS d'export MP4 et FPS réellement mesurés.

### Validation Windows utilisateur

Préparer une procédure courte pour tester sur mon Windows 11 :

1. Lancer JARVIS complet.
2. Passer de 2D à 2.5D.
3. Vérifier la netteté.
4. Tester 60 FPS avec et sans Ollama actif.
5. Parler au microphone.
6. Écouter Piper.
7. Vérifier le halo.
8. Interrompre la réponse.
9. Revenir en 2D.
10. Vérifier la persistance après redémarrage.

---

# 9. MÉTHODE DE TRAVAIL ET LIVRAISON

Procéder dans cet ordre :

**Phase A — Fluidité et DPI**
Diagnostiquer, corriger la cadence et la résolution.

**Phase B — Toggle direct**
Ajouter le contrôle dans Canvas et GPU.

**Phase C — Aura et langage visuel**
Différencier écoute, réflexion et parole.

**Phase D — Studio et finalisation**
Raccorder les réglages manquants, documenter et valider.

Créer des commits distincts par phase.

Tester avant chaque push.

Vérifier la CI Windows au SHA final.

Ne pas toucher `main`.

Ne pas engager les lots cognitifs et vocaux non concernés.

### Point de contrôle

Si un objectif de qualité ou de cadence n'est pas atteint, ne pas déclarer la mission complètement réussie.

Documenter :
- La cause.
- Les mesures.
- Les limites.
- Les compromis.
- Les vérifications restant à faire sur la RTX 3070.

L'application et la conversation doivent continuer à fonctionner même si le GPU n'atteint pas 60 FPS.

---

# CRITÈRES FINAUX D'ACCEPTATION

La mission est réussie lorsque :

1. Le rendu GPU est nettement plus fluide et vise 60 FPS réels.
2. La pixellisation est corrigée par une gestion propre du framebuffer et du DPI.
3. Le sélecteur 2D/2.5D est directement visible dans PRESENCE.
4. Le basculement fonctionne dans les deux sens.
5. L'aura de JARVIS pulse nettement avec sa voix réelle.
6. La prise de parole utilisateur possède une animation de réception identifiable.
7. La parole JARVIS possède une animation d'émission visuellement différente.
8. THINKING conserve les orbites rapides et la contraction du noyau.
9. Les expressions restent gravées sur la sphère.
10. Les paramètres existants et la stabilité du logiciel sont préservés.
11. Canvas reste une alternative complète et permanente.
12. Les performances CPU, RAM et VRAM restent compatibles avec une IA locale exécutée sur RTX 3070 8 Go.
13. Les tests et les CI du SHA final sont verts.
14. Les limites matérielles non testées sont déclarées explicitement.

**OBJECTIF ARTISTIQUE :**

PRESENCE doit donner l'impression d'une véritable entité holographique vivante.

Elle absorbe l'énergie lorsqu'elle écoute.

Elle la concentre lorsqu'elle réfléchit.

Elle la rayonne lorsqu'elle parle.

Le tout doit rester élégant, fluide, lumineux, net, configurable et performant, sans modifier l'identité visuelle déjà approuvée.