# JARVIS — COGNITIVE & PRESENCE EVOLUTION

## Mission globale : cerveau, voix, interface, indicateurs et corrections Windows

**Dépôt :** ABBYWILLY/JARVIS-0.0.1
**Branche :** `feat/jalon-2-voice-presence`

### Objectif général

Transformer JARVIS en un assistant conversationnel local, moderne, expressif, réactif et transparent, sans altérer ses fonctions existantes.

Cette mission intègre :
- Les dysfonctionnements détectés lors des tests réels Windows.
- Une refonte esthétique de COMMAND OS.
- Un moteur de mise en forme textuelle réellement complet.
- Une amélioration du cerveau conversationnel.
- Une amélioration des interactions vocales.
- Une évolution du langage visuel de PRESENCE.
- Un Cognitive HUD fondé uniquement sur des données réelles.

**Contrainte centrale : préserver l'architecture existante, respecter le cahier des charges original et minimiser CPU, RAM, VRAM, stockage, consommation énergétique et latence.**

---

# 0. DIRECTIVE ARCHITECTURALE PRIORITAIRE

Avant toute modification :

1. Inspecter les commits récents, les modules existants et les fonctionnalités déjà livrées.
2. Consulter le cahier des charges original s'il est accessible.
3. Identifier les composants réutilisables et les risques de régression.
4. Ne pas redévelopper les mécanismes déjà fonctionnels.
5. Préparer des tests ciblés avant les modifications à risque.

Préserver impérativement :
- Ollama, Qwen et les optimisations J2.8.
- Les budgets et modes de raisonnement.
- La mémoire SQLite et FTS5.
- Whisper, VAD, Piper et le pipeline PCM.
- COMMAND OS et PRESENCE 3.2.
- Emotional Field, Cognitive Singularity et Semantic Morphing.
- Les préférences utilisateur et l'historique.
- Les mécanismes de sécurité, permissions et interruption.
- Le fonctionnement local-first et hors ligne.

Ne pas ajouter de nouveau modèle ou moteur graphique obligatoire.

**Aucune fonctionnalité cosmétique ne doit compromettre le microphone, la voix, l'inférence ou la sécurité.**

---

# LOT 1 — CORRECTIFS BLOQUANTS WINDOWS

## 1.1 Microphone et absence de signal

Constat réel : l'écoute semble s'activer, mais aucune onde ne réagit à la parole et aucune transcription identifiable n'est obtenue.

Examiner toute la chaîne :

**Micro Windows → capture PCM → RMS → mic_level → PRESENCE → VAD → Whisper → Ollama.**

Vérifier le périphérique réellement ouvert, les autorisations, les formats audio, les erreurs PortAudio, les événements perdus, les états suspendus et les générations obsolètes.

Créer ou renforcer un diagnostic montrant :
- Microphone sélectionné et microphone réellement ouvert.
- Fréquence native et statut de capture.
- Vu-mètre RMS fondé sur le PCM réel.
- Activité VAD.
- Dernier événement reçu et son ancienneté.
- Statut Whisper/STT.
- Erreurs détaillées et actions correctives.

Distinguer clairement :
- Microphone ouvert sans signal.
- Signal reçu sans détection vocale.
- Voix détectée sans transcription.
- Transcription reçue sans réponse.

Ne jamais générer un faux signal audio.

Ne pas masquer un défaut matériel derrière un simple changement de seuil VAD.

Validation matérielle Windows obligatoire avant d'affirmer que le problème est résolu.

## 1.2 Navigation responsive

Constat réel : le bouton PRESENCE est inaccessible en paysage sur certaines dimensions de fenêtre, mais visible en portrait.

Corriger la structure de navigation :
- Conversation et PRESENCE toujours accessibles.
- Barre latérale rétractable.
- Commandes secondaires regroupées.
- Défilement approprié si nécessaire.
- Navigation clavier.
- Compatibilité différentes hauteurs, largeurs et échelles DPI.

Tester les fenêtres réduites, paysage et portrait.

Aucun bouton essentiel ne doit sortir de la zone visible.

---

# LOT 2 — COMMAND OS NEO INTERFACE ET RICH TEXT 2.0

## 2.1 Refonte graphique moderne

Le rendu actuel ressemble encore à une application Tkinter ancienne.

Créer une esthétique contemporaine cohérente avec PRESENCE :

- Interface sombre élégante.
- Navigation épurée.
- Panneaux et messages aux formes arrondies lorsque techniquement raisonnable.
- Espacement et alignement modernes.
- Hiérarchie typographique soignée.
- Zone de saisie confortable.
- Commandes visuellement cohérentes.
- États survol, sélection, désactivation et focus clavier.
- Informations techniques discrètes par défaut.
- Compatibilité avec le redimensionnement Windows.

Réutiliser Tkinter et les composants existants.

Ne pas migrer vers une WebView ou un framework lourd sans justification démontrée.

Conserver une interface rapide et accessible.

## 2.2 Véritable moteur de mise en forme

Le rendu actuel sait traiter certaines balises, notamment le gras, mais reste incomplet.

Implémenter un moteur Rich Text fiable prenant en charge :

**Typographie**
- Choix de la famille de police.
- Tailles différentes selon les titres et le contenu.
- Paramètres de taille utilisateur.
- Gras, italique et gras italique.
- Soulignement.
- Barré.
- Surlignage.
- Couleurs d'accent contrôlées.
- Interlignage et marges.

**Structure des réponses**
- Titres H1, H2, H3.
- Paragraphes distincts.
- Listes à puces et listes numérotées.
- Listes imbriquées.
- Citations.
- Séparateurs.
- Liens cliquables.
- Code inline.
- Blocs de code.
- Tableaux avec colonnes lisibles.
- Unicode et emojis.

Important : distinguer Markdown standard, extensions prises en charge et préférences de présentation. Ne pas inventer une interprétation de syntaxe ambiguë.

Les styles de police et tailles doivent être représentés réellement dans le widget, pas simplement annoncés dans les paramètres.

## 2.3 Streaming propre

Pendant la génération Qwen :
- Ne pas montrer durablement des balises Markdown incomplètes.
- Mettre à jour uniquement les parties modifiées lorsque possible.
- Préserver le défilement, la sélection et la copie.
- Éviter les reconstructions intégrales de l'historique.
- Respecter le texte original stocké en SQLite.

Séparer texte brut, structure formatée, rendu visuel et texte transmis à Piper.

Ne jamais exécuter du code ou du HTML provenant d'une réponse.

## 2.4 Paramètres de lecture

Proposer :
- Police.
- Taille.
- Densité compacte / confortable.
- Affichage de code monospace.
- Intensité des accents visuels.
- Retour aux réglages d'origine.

Préférences persistantes.

---

# LOT 3 — CERVEAU CONVERSATIONNEL C1

## 3.1 Routage cognitif intelligent

Ajouter un mode automatique capable de choisir entre :
- Rapide.
- Approfondi.
- Créatif.

Utiliser d'abord des heuristiques locales, sans second appel au modèle.

Respecter les paramètres manuels.

Le mode Créatif doit être une politique de génération documentée, pas une prétendue capacité de raisonnement distincte.

Afficher le mode réellement choisi, le budget de génération et son origine.

Éviter les basculements inutiles vers le raisonnement approfondi.

## 3.2 Continuité conversationnelle

Permettre de poursuivre une réponse longue ou une histoire interrompue par une limite de tokens.

Ajouter :
- Bouton Continuer.
- Conservation des personnages, événements et objectifs narratifs.
- Gestion de la fin de génération et des limites de sortie.
- Résumé compact seulement lorsque nécessaire.
- Protection contre les répétitions et les contradictions évidentes.

Ne pas effectuer de résumés supplémentaires systématiques.

Réutiliser la mémoire et le constructeur de contexte existants.

## 3.3 Mémoire transparente

Créer un panneau de contrôle des souvenirs locaux :

- Afficher les souvenirs enregistrés.
- Afficher leur provenance lorsqu'elle est disponible.
- Approuver, modifier ou supprimer.
- Distinguer souvenirs explicites, éléments historiques et contexte temporaire.
- Vérifier leur usage dans la génération.
- Préserver sauvegardes et intégrité SQLite.

Aucune mémorisation personnelle implicite non documentée.

## 3.4 Fiabilité et provenance

Indiquer clairement :
- Contenu issu de la mémoire.
- Données fournies par l'utilisateur.
- Hypothèse ou estimation.
- Information non vérifiée.

Ne pas inventer des citations, sources ou scores de confiance.

Préférer des indicateurs de provenance vérifiables à une prétendue mesure de vérité.

---

# LOT 4 — VOIX NATURELLE V1

## 4.1 Tour de parole

Améliorer les transitions :
- Détection de début de parole.
- Gestion des hésitations.
- Silence de fin de tour.
- Interruptions vocales.
- Reprise après réponse.
- Casques et haut-parleurs.

Réutiliser VAD, Whisper et Piper.

Ne jamais modifier les seuils sans diagnostic et tests.

## 4.2 Prosodie et normalisation

Améliorer la lecture :
- Nombres et décimaux.
- Montants et devises.
- Dates et heures.
- Sigles et abréviations.
- Ponctuation et pauses.
- Phrases longues.
- Markdown et emojis non destinés à la lecture.

Tester les possibilités réelles de Piper avant d'annoncer des émotions vocales avancées.

## 4.3 Commandes conversationnelles

Ajouter, avec détection prudente :
- « Stop ».
- « Répète ».
- « Reprends ».
- « Continue ».
- « Parle moins vite ».
- « Développe ce passage ».

Ne pas interpréter ces expressions comme des commandes lorsqu'elles figurent simplement dans une dictée ou une citation.

Prévoir une alternative accessible par boutons.

## 4.4 Profils vocaux contextuels

Proposer :
- Discussion normale.
- Explication technique.
- Récit.
- Réponse courte.

Adapter les pauses et paramètres TTS uniquement dans les limites réellement prises en charge.

Aucun changement de modèle obligatoire.

---

# LOT 5 — COGNITIVE HUD ET OUTILS DE CONVERSATION

## 5.1 Cognitive HUD

Créer un panneau d'indicateurs sobre et actualisé à partir des événements réels.

Afficher :
- État actuel : écoute, transcription, réflexion, parole, arrêt.
- Mode cognitif réellement actif.
- Modèle Ollama.
- Budget actif et tokens générés.
- Mémoire consultée.
- État microphone et VAD.
- État Piper.
- Chronométrages disponibles.
- Erreurs et modes dégradés.

Aucune progression en pourcentage fictive.

Ne pas présenter le débit de tokens comme un niveau d'intelligence.

Deux modes :
- Immersion : indicateurs essentiels seulement.
- Diagnostic : informations détaillées.

## 5.2 « Pourquoi cette réponse ? »

Ajouter une commande permettant d'inspecter :
- Mode de génération.
- Budget choisi.
- Mémoire utilisée.
- Contexte sélectionné.
- Limitations détectées.
- Provenance des informations lorsqu'elle existe.

Ne pas fabriquer d'explication causale ou de raisonnement caché.

## 5.3 Replay intelligent

Permettre de sélectionner un passage de la réponse et de :
- Le relire vocalement.
- Réduire ou augmenter le débit dans les limites du moteur TTS.
- Changer de voix installée.
- Reprendre la lecture après interruption.

Réutiliser Piper, le traitement Markdown/TTS et les sous-titres existants.

Ne pas lancer de nouveau moteur audio.

---

# LOT 6 — PRESENCE ADVANCED P1

## 6.1 Microexpressions

Ajouter de petites variations de géométrie en lien avec le contexte émotionnel :

- Surprise : contraction puis expansion discrète.
- Réconfort : courbes douces.
- Enthousiasme : léger accroissement d'énergie.
- Gravité : mouvement ralenti et retenu.

Utiliser Emotional Field existant.

Ne pas déclencher d'effets intempestifs à chaque mot.

Préserver la priorité du véritable PCM.

## 6.2 Atelier PRESENCE

Permettre de régler et prévisualiser :
- Épaisseur de l'onde.
- Intensité du halo.
- Taille du noyau THINKING.
- Fluidité des transitions.
- Palette émotionnelle.
- Morphing sémantique.
- Profils graphiques.

Prévisualisation hors ligne, sans modèle ni micro.

## 6.3 Mini-PRESENCE

Créer un mode compact et optionnel :
- Fenêtre flottante redimensionnable.
- État du microphone visible.
- Visualiseur principal réutilisé.
- Retour rapide à COMMAND OS.
- Pas de deuxième boucle graphique autonome.

Ne pas utiliser de mécanisme d'affichage qui empêche les autres applications de fonctionner normalement.

## 6.4 Identité visuelle contextuelle

Proposer des ambiances :
- Conversation.
- Explication.
- Récit.
- Concentration.

Ces ambiances agissent uniquement sur le rendu visuel, pas sur les permissions, la sécurité ou les capacités du modèle.

---

# LOT 7 — OPTIMISATION ET VALIDATION GLOBALE

## Performance

- Priorité au pipeline audio et à l'inférence.
- Aucun nouvel appel Ollama systématique.
- Pas de modèle additionnel obligatoire.
- Réutilisation des objets Canvas.
- Animations suspendues si fenêtre invisible.
- Files d'événements et caches bornés.
- Pas de recalcul linguistique à chaque frame.
- Réutilisation des structures SQLite existantes.
- Profils de qualité adaptatifs.

Comparer avant et après :
- CPU et RAM du processus.
- Latence de première réponse.
- Temps de première lecture TTS.
- Régularité graphique.
- Comportement de la capture micro.
- Fluidité du streaming.
- Réactivité des interruptions.

Ne pas inventer de benchmarks matériels.

## Validation

Tester :
- Windows 11.
- Tk 8.6 et Tk 9 lorsque disponibles.
- Différents DPI.
- Paysage et portrait.
- Fenêtres réduites.
- Fonctionnement hors ligne.
- Unicode et Markdown.
- Mémoires et historiques.
- Gestion des erreurs.
- Événements audio réels.
- Interruption et reprise.
- Compilation PyInstaller.

Distinguer clairement les tests automatisés, la CI et la recette matérielle Windows.

---

# MÉTHODE D'EXÉCUTION CODEX

**Ne pas implémenter tous les lots dans un seul changement massif.**

Procéder dans l'ordre :
1. Corriger le microphone et le responsive.
2. Moderniser COMMAND OS et compléter Rich Text.
3. Améliorer le cerveau.
4. Améliorer la voix.
5. Ajouter Cognitive HUD et Replay.
6. Finaliser PRESENCE.
7. Optimiser et valider.

Chaque lot doit produire :
- Des changements fonctionnels.
- Des tests ciblés.
- Un commit séparé.
- Un push sur `feat/jalon-2-voice-presence`.
- Un état de CI Windows connu.
- Une liste courte des vérifications matérielles restantes.

Ne jamais modifier `main`.

Si le budget Codex arrive à sa limite, terminer et sauvegarder proprement le lot actif. Ne pas laisser une refonte partiellement intégrée casser l'application.

## RAPPORT FINAL

Fournir :
1. Fonctionnalités réellement terminées.
2. Bugs corrigés et causes identifiées.
3. Fichiers modifiés.
4. Tests exécutés.
5. Mesures de performance lorsqu'elles existent.
6. Commits.
7. État GitHub Actions.
8. Points à tester sur mon PC.

**Résultat visé : un JARVIS plus intelligent, plus naturel à écouter, plus moderne à utiliser et plus transparent sur son fonctionnement, sans transformer le projet en logiciel lourd ou fragile.**
