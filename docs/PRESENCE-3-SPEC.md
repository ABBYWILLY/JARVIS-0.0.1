# PRESENCE — Emotional Field 3.0 / Living Core 3.1

Demande utilisateur du 22 octobre 2026, conservée pour la reprise.

1. CADRE ET GARDE-FOUS

Branche : feat/jalon-2-voice-presence. Ne jamais modifier main.
Avant toute modification, vérifier l'état Git, les fonctionnalités déjà implémentées et les exigences du cahier des charges original JARVIS 0.0.1. Ne pas recommencer les éléments terminés.
Objectif : faire de PRESENCE une entité visuelle unique, expressive et émotionnellement cohérente, sans ralentir la conversation.
Lire les implémentations existantes (spectrum.py, presence.py, voice_ui.py), améliorer les composants en place et réutiliser Tkinter, le canvas et les mécanismes fonctionnels, sans refonte ni système parallèle.
Préserver COMMAND OS, Ollama, Whisper, Piper, SQLite, la mémoire J2.8, les budgets de tokens, les permissions, les diagnostics, les événements audio, ainsi que les données et modèles des utilisateurs.
Respecter toutes les exigences P0 : isolation, interruption, streaming, accessibilité, états structurés et séparation stricte entre émotions et permissions.
Priorités absolues : réactivité vocale, stabilité, sécurité et respect du signal audio réel.
Aucun second appel Ollama pour l'analyse émotionnelle, aucun nouveau modèle, moteur IA, visualiseur, thread lourd, calcul GPU dédié, téléchargement volumineux ou dépendance graphique lourde.

2. OPTIMISATION ET RENDU

Optimiser CPU, RAM, VRAM, disque et consommation d'énergie.
Réutiliser le canvas et les objets graphiques, en privilégiant leur mise à jour incrémentale et la limitation des allocations par frame.
Ne jamais effectuer de calcul linguistique dans la boucle de rendu : classifier les segments de texte uniquement à leur arrivée.
Réduire ou suspendre les animations pendant le silence, le sommeil ou lorsque la fenêtre est masquée.
Adapter la qualité graphique à la charge, au DPI, à la taille de fenêtre et aux profils Éco / Équilibré / Cinématique.
Utiliser des files et caches bornés. Préserver la fluidité Windows et éviter toute dégradation mesurable de la latence vocale.
Mesurer les coûts avant/après sans inventer de gains ni de résultats matériels.
Respecter la réduction des mouvements, le thème, le centrage, le responsive, le contraste et les préférences utilisateur.

3. EMOTIONAL FIELD 3.0 — ÉMOTIONS ET COULEURS

Conserver intégralement la mission Emotional Field 3.0.
Définir un mood dominant par réponse avec des nuances secondaires locales. Distinguer l'ambiance du sujet (choix par défaut), l'émotion réellement exprimée et le cyan neutre.
Effectuer une analyse locale du français : expressions, contexte immédiat, affirmations, négations, citations, intensificateurs et ambiguïtés. Ne pas confondre la simple mention d'une émotion avec une émotion exprimée.
Garder une dominante visuelle stable ; ne permettre un pivot que lorsque l'ambiance du récit change réellement.
Faire agir le mood sur la couleur, le halo, l'inertie et le style des courbes.
Assurer des transitions et interpolations de couleurs progressives, avec lissage temporel, sans flash, clignotement ni changement à chaque mot.
Séparer entièrement les couleurs émotionnelles des couleurs opérationnelles, des permissions, des erreurs et de la sécurité.
Pour la parole, piloter l'amplitude uniquement avec le véritable signal PCM ; ne jamais simuler un signal audio ou microphone.

4. VISUALISEUR LUMINEUX MULTICOUCHE

Remplacer le trait trop fin par un tracé visuellement unique composé d'un trait central net, d'une enveloppe lumineuse douce, d'un halo subtil et de terminaisons arrondies.
L'épaisseur doit être indépendante de l'expressivité audio.
Ajouter le réglage persistant « Épaisseur du visualiseur » : 1 à 10, défaut 6.
À 100 % DPI, viser environ 3–4 px pour le trait net et 8–14 px pour le halo, avec adaptation au scaling Windows.
Les couches ne doivent jamais former plusieurs lignes fonctionnelles.
En silence réel, le tracé reste parfaitement plat et sans ondulation artificielle.

5. LIVING CORE 3.1 — COGNITIVE SINGULARITY / THINKING

Créer une transformation continue de la ligne vers un unique noyau énergétique orbital, parfaitement centré.
Faire apparaître des arcs incomplets, des flux lumineux circulants, une profondeur visuelle, un halo et des micro-pulsations lentes ; mouvements élégants, fluides, perceptibles et sans effet stroboscopique.
Dimension apparente du noyau THINKING : environ 25 à 35 % de la plus petite dimension utile de la fenêtre, ajustée à la résolution et au DPI, sans décentrage.
Dès le premier PCM, réaliser une expansion organique du noyau vers la forme parlante.
Le noyau représente symboliquement le traitement : ne jamais le présenter comme la mesure de la pensée réelle ou de la charge neuronale.
Distinguer le sommeil du silence : silence = ligne plate ; sommeil = forme compacte, atténuée, immobile et sans animation inutile.
Garantir des transitions continues entre écoute, réflexion, parole et silence.
La priorité des états fonctionnels est absolue : interruption, erreur, microphone désactivé ou arrêt d'urgence annulent immédiatement animations émotionnelles, transformations et événements en attente.

6. AUDIO, MICROPHONE ET TIMELINE

Afficher clairement les états du microphone : ouvert, voix détectée, STT, suspendu et erreur.
Créer une timeline légère des événements émotionnels associés aux segments TTS et la synchroniser aux callbacks de lecture audio.
En l'absence de timestamps mot à mot, conserver une synchronisation approximative par groupes de mots et signaler cette limite ; ne pas prétendre à une précision supérieure.
Ne jamais retarder l'audio pour synchroniser le visuel.
En cas d'interruption, supprimer immédiatement l'audio, les événements visuels périmés et les surlignages différés.

7. SOUS-TITRES ÉMOTIONNELS

Faire des sous-titres une extension visuelle d'Emotional Field 3.0, affichant le passage vocal courant sous le visualiseur.
Afficher au maximum deux lignes centrées, avec texte principal en blanc doux légèrement atténué.
Repérer les mots et expressions importants pour le sens ou l'émotion ; colorer uniquement les éléments contextuellement pertinents avec la teinte émotionnelle réellement active du noyau. Les mots non pertinents restent neutres.
Respecter le mood dominant ; éviter les effets arc-en-ciel, la saturation excessive et la coloration systématique de tous les mots émotionnels.
Déclencher le surlignage à la prononciation effective, d'après la timeline, les événements PCM et les positions textuelles déjà disponibles ; en l'absence de timestamps précis, employer l'approximation décrite ci-dessus.
Faire évoluer doucement la couleur des mots concernés lors d'une véritable transition émotionnelle, sans clignotement.
Autoriser un léger halo typographique, une ombre ou un voile discret si nécessaires à la lisibilité.
Adapter taille et contraste au fond sélectionné, à la résolution et au scaling Windows ; garantir la lisibilité.
Ne jamais remplacer les indicateurs de sécurité ou les couleurs opérationnelles par des couleurs émotionnelles.

8. RÉGLAGES ET MODES

Exposer et conserver après redémarrage :
- Mode émotionnel.
- Expressivité de 0 à 100, défaut 75.
- Fluidité Réactive / Cinématique / Apaisée, défaut Cinématique.
- Épaisseur du visualiseur de 1 à 10, défaut 6.
- Sous-titres émotionnels activés / désactivés.
- Intensité de colorisation discrète / normale / expressive.
- Option pour désactiver halos et animations.
- Taille des sous-titres ajustable.
Préserver les préférences existantes et l'accessibilité.
Ajouter un mode Immersion / Diagnostic commutable au clavier.

9. PRÉVISUALISATION ET TESTS

Fournir une prévisualisation hors ligne des formes, couleurs et états sans charger de modèle, avec scénario émotionnel reproductible : espoir → affection → tension → apaisement.
Réaliser une capture ou une recette visuelle du Thinking Halo.
Tester automatiquement : classification des passages et cas ambigus, stabilité du mood dominant, transitions, interruption, silence réel, sommeil, rendu, timing audio et persistance.
Tester les sous-titres sur mots simples, expressions composées, ponctuation, Unicode français, Markdown et emojis ; vérifier les changements de couleur, la neutralité des mots non pertinents et les changements rapides de segments audio.
Effectuer des tests ciblés et une validation réelle sur Windows. Ne pas affirmer que le rendu visuel Windows a été validé si seuls des tests simulés ont été exécutés.
Exiger une CI Windows verte avant livraison.

10. ORDRE D'EXÉCUTION ET LIVRABLES

Commencer par l'épaisseur multicouche et Cognitive Singularity. Réaliser ensuite les autres ajouts UX en fonction des crédits disponibles, sans refaire les sous-lots déjà achevés.
Implémenter par sous-lots fonctionnels ; après chacun : tests, commit et push sur feat/jalon-2-voice-presence.
Si les crédits Codex approchent de leur limite, sécuriser immédiatement les changements et documenter les travaux restants.
Produire un compte rendu bref : fichiers/code modifiés, réglages livrés, tests, commits, push, état de la CI, gains ou coûts effectivement mesurés, limites et validations restant à effectuer sur PC Windows.