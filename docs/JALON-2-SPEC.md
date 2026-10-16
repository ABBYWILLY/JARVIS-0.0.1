# JARVIS UNHINGED NEXT
## MASTER PROMPT — JALON 2 : VOICE ENGINE + PRESENCE
### Spécification d'implémentation et protocole de livraison résilient

**Dépôt officiel :** https://github.com/ABBYWILLY/JARVIS-0.0.1

**Objectif :** transformer le JARVIS textuel déjà fonctionnel en un assistant vocal local, conversationnel, mains libres, disposant de deux voix françaises et d'une interface PRESENCE immersive fondée sur un visualiseur morphologique unique.

**Priorités absolues :** fonctionnement réel, qualité conversationnelle, esthétique, performances locales, absence de régressions, traçabilité et économie des crédits Codex.

---

# 0. RÔLE ET DIRECTIVES FONDAMENTALES

Tu es simultanément :

- Architecte logiciel senior.
- Ingénieur IA locale et Ollama.
- Ingénieur audio temps réel.
- Spécialiste des assistants vocaux.
- Développeur Windows 11.
- Directeur artistique UI/UX.
- Motion designer temps réel.
- Ingénieur qualité et intégration continue.

Tu dois livrer un logiciel réellement fonctionnel, et non une démonstration visuelle ou une accumulation de fonctionnalités partielles.

Travaille sur une branche dédiée issue de la dernière version de `main`.

**Ne modifie jamais directement `main`.**

## État initial validé

Le jalon 1 a déjà été testé sur Windows 11 :

- `Jarvis.exe` démarre.
- Ollama fonctionne en local.
- Les modèles installés sont détectés.
- Qwen3.5 Abliterated génère des réponses.
- La conversation textuelle est opérationnelle.
- L'historique SQLite est conservé après redémarrage.
- GitHub Actions compile une version Windows.

Ces fonctionnalités ne doivent subir aucune régression.

Lis le cahier des charges existant dans `docs/`, qui reste la spécification générale du produit. Le présent prompt précise les objectifs du jalon 2 ; il ne remplace pas les exigences globales.

Toute contradiction majeure doit être identifiée. Pour les détails techniques non bloquants, prends une décision raisonnable et documente-la brièvement.

---

# 1. RÉFÉRENCES TECHNIQUES ET VISUELLES

## Projets de référence

Étudie uniquement les parties pertinentes des projets suivants :

- https://github.com/FatihMakes/Mark-LV
- https://github.com/jaredrhod/fullstack-agent
- https://github.com/jaredrhod/backtalk
- https://ledevfouyt.github.io/jarvis/

Objectifs de cette consultation :

- Identifier les bonnes pratiques de modularité.
- Étudier les systèmes de dialogue vocal.
- Comprendre les mécanismes de contrôle des périphériques.
- Étudier les visualiseurs et animations audio.
- Identifier les composants réutilisables.

Ne copie pas aveuglément les projets.

Vérifie les licences et les dépendances. Ne rends aucun service distant indispensable.

## Bibliothèques vocales prioritaires

- Kokoro : https://github.com/hexgrad/kokoro
- Piper : https://github.com/rhasspy/piper
- faster-whisper : https://github.com/SYSTRAN/faster-whisper
- Silero VAD : https://github.com/snakers4/silero-vad

Vérifie les véritables capacités françaises des moteurs TTS, notamment la présence de deux voix naturelles distinctes.

Privilégie une solution principale et une alternative légère plutôt qu'une étude exhaustive.

Consulte les références graphiques du dépôt lorsqu'elles existent. Ne suppose pas qu'un simple lien vers une démonstration constitue une spécification graphique complète.

---

# 2. VOICE ENGINE — MOTEUR VOCAL LOCAL

## 2.1 Capture audio et reconnaissance

Implémente :

1. Capture microphone locale.
2. Sélection du périphérique d'entrée.
3. Sélection de la sortie audio.
4. Activation et désactivation explicites de l'écoute.
5. Détection d'activité vocale locale (VAD).
6. Reconnaissance vocale française locale (STT).
7. Transcription progressive si le moteur choisi le permet.
8. Détection de fin de tour.
9. Gestion des silences, hésitations et bruits ambiants.
10. Gestion des périphériques absents ou déconnectés.
11. Libération correcte des ressources à l'arrêt.

L'utilisateur doit pouvoir converser pendant plusieurs minutes sans cliquer sur « Envoyer ».

## 2.2 Synthèse vocale

Fournir au minimum :

- Une véritable voix masculine française.
- Une véritable voix féminine française.
- Deux timbres distincts, et non une simple modification artificielle de hauteur.
- Un gestionnaire de voix accessible depuis les paramètres.
- Une préécoute réellement audible.
- Des réglages de vitesse lorsque compatibles.
- Des moteurs TTS interchangeables.
- Des préférences conservées après redémarrage.

La voix masculine doit rechercher l'élégance, le calme et le caractère sophistiqué de l'expérience JARVIS de Jared, sans reproduction non autorisée d'une voix propriétaire.

La voix féminine doit être naturelle, agréable et intelligible.

Priorité à la qualité perçue et à la latence réelle.

Le système principal doit fonctionner localement et gratuitement après installation des modèles nécessaires.

## 2.3 Dialogue bidirectionnel

Implémente :

- Intégration du LLM Ollama en streaming.
- Orchestration STT → LLM → TTS.
- Lecture audio segmentée ou progressive lorsque pertinente.
- Interruption naturelle par la voix utilisateur.
- Annulation des segments audio obsolètes.
- Arrêt de la sortie TTS lors d'une interruption.
- Prévention des auto-déclenchements causés par la propre voix de JARVIS.
- Gestion des échos et des reprises.
- Interruption manuelle.
- Arrêt d'urgence.
- Gestion de l'annulation des requêtes longues.

L'interruption audio doit avoir priorité sur les transitions graphiques.

Ne prétends pas implémenter du full-duplex si l'utilisateur ne peut pas réellement interrompre JARVIS lorsqu'il parle.

## 2.4 Historique conversationnel

Les conversations vocales doivent rejoindre le stockage SQLite existant.

Enregistrer :

- Texte prononcé par l'utilisateur.
- Transcription finale.
- Réponse textuelle de JARVIS.
- Provenance textuelle ou vocale.
- Horodatages.
- Modèle LLM utilisé lorsque connu.
- Voix et moteur utilisés lorsque connus.
- État des interventions interrompues.

Préserver toutes les conversations et préférences préexistantes.

---

# 3. PRESENCE — PHILOSOPHIE GRAPHIQUE

## 3.1 Concept central

PRESENCE doit représenter JARVIS comme **une seule entité audiovisuelle vivante et morphologique**.

Cette entité existe sous plusieurs formes, mais ne se dédouble jamais en plusieurs visualiseurs indépendants.

**Règle fondamentale : UNE ENTITÉ, PLUSIEURS FORMES, UNE SEULE SOURCE DE VÉRITÉ.**

Les formes principales sont :

- Ligne plate.
- Onde sonore courbe.
- Noyau holographique.
- Forme dormante.

Les transitions entre elles doivent donner l'impression que la même matière lumineuse se transforme.

Il est interdit d'afficher simultanément une ligne audio permanente et un noyau permanent comme deux visualiseurs autonomes.

Le système de rendu doit posséder une machine à états unique.

## 3.2 Fond personnalisable

Le fond PRESENCE doit être **noir absolu `#000000` par défaut**.

L'utilisateur doit pouvoir :

- Modifier librement la couleur de fond.
- Utiliser un sélecteur de couleur.
- Enregistrer ses préférences.
- Revenir instantanément au noir par défaut.

Adapter automatiquement les contrastes des éléments textuels et des commandes lorsque nécessaire.

Les halos lumineux et effets holographiques sont autorisés autour du visualiseur, mais ne doivent pas imposer un dégradé permanent au fond.

Identité par défaut :

- Noir profond.
- Cyan lumineux.
- Typographie blanche ou gris clair.
- Matériaux holographiques subtils.
- Interface épurée et premium.

## 3.3 Centrage absolu et proportions responsives

**Le visualiseur principal doit toujours être centré géométriquement dans la surface PRESENCE disponible.**

Exigences :

- Centrage horizontal.
- Centrage vertical.
- Adaptation automatique au redimensionnement.
- Conservation des proportions.
- Aucune déformation du noyau circulaire.
- Aucun décalage provoqué par les transcriptions.
- Aucun panneau secondaire ne doit déplacer artificiellement le centre.
- Aucun débordement ou recadrage accidentel.

Le noyau doit posséder une présence visuelle forte sans encombrer l'interface.

### Taille de référence

Viser une emprise visuelle approximative d'un tiers de la zone disponible, adaptée selon le format de la fenêtre.

Ce tiers constitue une intention de composition, pas une obligation mathématique rigide.

Pour un visualiseur circulaire, privilégier un diamètre initial proche de 30 à 40 % de la plus petite dimension utile, à ajuster selon le résultat visuel.

Ne pas confondre diamètre et proportion de surface.

La taille finale doit respecter les principes d'équilibre, de hiérarchie visuelle, de respiration et d'espace négatif d'une interface haut de gamme.

Prévoir un dimensionnement fluide avec des limites minimales et maximales.

Sur une fenêtre étroite, réduire le noyau pour préserver les commandes et transcriptions.

Sur un grand écran, éviter qu'il devienne disproportionné.

### Responsive design

L'interface doit rester cohérente :

- En plein écran.
- En fenêtre redimensionnée.
- Sur plusieurs résolutions.
- Sur écrans larges.
- Avec les paramètres de mise à l'échelle Windows.
- En présence d'une transcription plus longue.
- Avec les paramètres d'accessibilité et d'agrandissement du texte.

Tester plusieurs proportions d'affichage.

Les commandes et transcriptions doivent s'adapter autour du visualiseur, jamais l'inverse.

---

# 4. PRESENCE — MORPHING SYSTEM

## 4.1 Une seule géométrie visuelle

Le moteur graphique doit représenter la transformation continue d'une entité unique.

Transitions :

LIGNE PLATE ↔ ONDE COURBE ↔ NOYAU HOLOGRAPHIQUE.

Les changements de forme doivent être fluides, réversibles et annulables.

Les transitions ne doivent jamais retarder un événement audio réel.

## 4.2 SILENT — JARVIS se tait

Lorsque ni l'utilisateur ni JARVIS ne parlent, et qu'aucun traitement visuel prioritaire n'est actif :

- Le visualiseur devient une ligne horizontale.
- La ligne est parfaitement plate.
- Elle traverse la largeur utile de la fenêtre.
- Elle est centrée verticalement.
- Le noyau n'est plus visible.
- Aucun battement sonore fictif ne doit apparaître.

Le silence correspond à une absence réelle de signal vocal pertinent.

Ne pas confondre silence et sommeil.

## 4.3 LISTENING — JARVIS écoute

Lorsque le microphone est activé mais que personne ne parle :

- La ligne demeure horizontale.
- Son intensité lumineuse peut être légèrement différente de l'état SILENT.
- Elle ne doit pas osciller sans signal vocal pertinent.

Cette représentation doit indiquer que JARVIS est prêt à écouter.

## 4.4 USER SPEAKING — L'interlocuteur parle

Lorsque l'utilisateur parle :

- La ligne se transforme en une onde sonore.
- L'amplitude dépend du signal réel du microphone.
- Le mouvement suit les variations de parole.
- Le noyau reste absent.
- L'animation cesse lorsque la parole s'arrête.

### Exigence graphique : courbes organiques

**L'onde doit être entièrement fluide, douce et organique.**

Je ne veux pas :

- De pics triangulaires.
- D'angles aigus.
- De cassures abruptes.
- De tracé en dents de scie.
- De segments rectilignes assemblés.
- D'apparence d'électrocardiogramme.
- De visualisation brutalement angulaire.

Je veux une apparence rappelant une onde acoustique élégante, continue et arrondie.

Privilégier :

- Courbes de Bézier.
- Interpolation spline adaptée.
- Continuité géométrique et tangente.
- Lissage temporel contrôlé.
- Variation progressive de l'amplitude.
- Transitions douces entre les échantillons visuels.

Le tracé doit représenter les données audio réelles après une transformation visuelle appropriée.

Le lissage ne doit pas créer de mouvements sans signal ni introduire une latence perceptible excessive.

Éviter également les oscillations artificiellement régulières ressemblant à une sinusoïde décorative.

Les extrémités de l'onde doivent rejoindre naturellement la ligne de base.

### Réactivité

L'amplitude peut dépendre de l'énergie du signal avec un filtrage visant à supprimer les pics parasites.

Le lissage doit être configuré pour conserver la sensation de synchronisation avec la voix.

Le rendu doit rester calme lorsque l'utilisateur chuchote et devenir plus expressif lorsque l'intensité augmente, sans exagération systématique.

## 4.5 THINKING — JARVIS réfléchit

À la fin d'une intervention utilisateur :

- L'onde s'atténue.
- Ses oscillations convergent progressivement.
- La ligne se rassemble visuellement vers son centre.
- La forme se transforme en noyau holographique.

Le noyau reste géométriquement centré.

Animation de réflexion :

- Rotations internes très lentes.
- Anneaux ou structures concentriques élégantes.
- Déformation volumétrique subtile.
- Variation lumineuse douce.
- Sensation de concentration et d'activité.

L'animation représente l'attente d'un traitement réel, pas les pensées internes cachées du modèle.

Aucun faux pourcentage de réflexion.

Aucune animation agressive.

La réflexion doit se terminer lorsqu'un changement d'état réel survient.

## 4.6 JARVIS SPEAKING — JARVIS parle

Le noyau demeure au centre.

Il réagit au signal audio TTS effectivement diffusé :

- Amplitude réelle.
- Intensité vocale.
- Rythme.
- Pauses.
- Variation temporelle.

Utiliser une modulation élégante du noyau, de ses anneaux ou de ses contours.

Les déformations doivent rester organiques et arrondies.

Éviter les pics agressifs ou les effets de tremblement.

Le rendu ne doit pas se comporter comme une animation prédéfinie sans rapport avec l'audio.

Lors des pauses vocales, l'activité du noyau doit naturellement diminuer.

À la fin de la réponse :

- Le noyau ralentit.
- Il se contracte ou se déploie progressivement.
- Sa géométrie redevient une ligne horizontale.
- Le système retrouve l'état SILENT ou LISTENING selon la configuration.

## 4.7 INTERRUPTION

Si l'utilisateur intervient pendant la réponse :

- La lecture TTS est interrompue.
- Les segments audio obsolètes sont annulés.
- L'animation du noyau cesse de suivre le TTS interrompu.
- Le visualiseur se transforme immédiatement vers l'onde microphone.
- La nouvelle intervention utilisateur devient prioritaire.

La transformation visuelle doit être courte, fluide et non bloquante.

Ne pas attendre la fin d'une animation pour traiter la voix.

## 4.8 DORMANT — Sommeil

Le sommeil doit être distinct du silence.

En mode DORMANT :

- Le visualiseur devient un point très discret ou une ligne fortement atténuée.
- Les animations coûteuses sont suspendues.
- Le microphone est désactivé sauf fonction de réveil explicitement autorisée.
- Les ressources inutiles doivent être libérées lorsque possible.
- Les inférences et tâches actives suivent une politique d'arrêt ou de suspension contrôlée.

Le réveil doit restaurer progressivement la représentation visuelle appropriée sans perturber l'historique ou les paramètres.

---

# 5. EMOTIONAL SPECTRUM — SÉMANTIQUE CONVERSATIONNELLE

Créer un système chromatique inspiré conceptuellement des Lantern Corps, sans reproduire d'assets propriétaires.

| Couleur | Signification |
|---|---|
| Rouge | Rage, colère, intensité |
| Orange | Avarice, désir, ambition |
| Jaune | Peur, anticipation |
| Vert | Volonté, détermination |
| Bleu | Espoir, confiance |
| Indigo | Compassion, empathie |
| Violet / Rose | Amour, attachement |
| Blanc | Vie, renouveau |
| Noir | Mort, fin de cycle |
| Cyan | Neutralité, identité JARVIS |

## 5.1 Utilisation

Les couleurs émotionnelles ne doivent affecter que :

1. Les accents lumineux du visualiseur morphologique.
2. Quelques mots-clés pertinents de la transcription.

Ne pas recolorer les paragraphes complets, les menus, les permissions ou l'arrière-plan général.

La couleur traduit une interprétation de la tonalité du discours.

JARVIS ne doit jamais prétendre ressentir réellement cette émotion.

## 5.2 Régulation

Prévoir :

- Analyse sémantique conservatrice.
- Seuil de pertinence.
- Inertie temporelle.
- Transitions douces.
- Retour au cyan si le contexte est ambigu.
- Absence de changement inutile à chaque phrase.
- Limitation des appels supplémentaires au LLM.

La classification émotionnelle ne doit pas augmenter sensiblement la latence de conversation.

Le noir émotionnel doit se traduire par une réduction contrôlée de luminosité du noyau, avec conservation de contours perceptibles.

## 5.3 Modes

- Spectre adaptatif.
- Cyan fixe.
- Couleur fixe personnalisée.
- Aucun accent émotionnel.

Les préférences doivent persister après redémarrage.

---

# 6. OPERATIONAL SPECTRUM — SÉMANTIQUE FONCTIONNELLE

Créer un spectre indépendant inspiré des conventions de circulation et de sécurité.

| Couleur | Signification |
|---|---|
| Vert | Autorisé, action permise |
| Bleu | Disponible, information |
| Jaune | Vigilance, incertitude |
| Orange | Prudence, confirmation |
| Rouge | Interdiction, danger, arrêt |
| Gris | Inactif, indisponible |

Utilisation :

- Autorisations.
- Outils.
- Missions.
- Diagnostics.
- Alertes.
- Erreurs.
- Disponibilité.

Une information critique doit toujours comporter une icône ou un texte explicite.

Les spectres émotionnel et opérationnel doivent être techniquement indépendants.

Les émotions ne modifient jamais les permissions système.

Le mode UNHINGED et les modèles abliterated ne doivent pas contourner cette règle.

---

# 7. TRANSCRIPTION CINÉTIQUE

La transcription doit accompagner l'audio réellement joué.

Priorité :

1. Timestamps TTS.
2. Alignement audio-texte.
3. Approximation signalée.

Prévoir :

- Apparition progressive des groupes de mots.
- Synchronisation avec la parole.
- Accentuation sélective de mots.
- Déplacement minimal.
- Transitions d'opacité douces.
- Lisibilité permanente.
- Sous-titres facultatifs.
- Historique intégral consultable.
- Copie et archivage.

La transcription ne doit jamais déplacer le noyau hors du centre de la fenêtre.

---

# 8. PERFORMANCE GRAPHIQUE ET ACCESSIBILITÉ

Trois profils :

### ÉCO

- Animations simples.
- Faible consommation GPU.
- Rafraîchissement réduit.
- Morphing simplifié.

### ÉQUILIBRÉ

- Profil par défaut.
- Bonne fluidité.
- Effets maîtrisés.
- Transitions naturelles.

### CINÉMATIQUE

- Effets lumineux plus développés.
- Profondeur accrue.
- Matériaux holographiques sophistiqués.
- Qualité améliorée si les ressources sont disponibles.

Tous les profils doivent conserver la même logique fonctionnelle.

Prévoir :

- Support de la réduction du mouvement.
- Contrastage approprié.
- Absence de stroboscope.
- Contrôles accessibles au clavier.
- Possibilité de désactiver les effets coûteux.
- Dégradation gracieuse du rendu si les ressources sont insuffisantes.

Ne jamais laisser l'interface consommer des ressources nécessaires à l'inférence.

---

# 9. CONFIGURATION MATÉRIELLE ET INFÉRENCE

Matériel de référence :

- Windows 11.
- AMD Ryzen 7 7800X3D.
- 32 Go RAM DDR5.
- RTX 3070 8 Go VRAM.
- Ollama.
- Modèles Qwen3.5, notamment abliterated.

Évolutions prévues :

- RTX 3090 24 Go.
- Multi-GPU.
- Serveur d'inférence LAN.
- llama.cpp ou autres moteurs compatibles.

Objectif conversationnel historique : environ 60 tokens/seconde lorsque le modèle et les conditions matérielles le permettent.

Ne pas présenter cet objectif comme une performance garantie.

Privilégier le CPU pour les composants audio lorsque cela préserve la VRAM et la fluidité du LLM.

Mesurer lorsque possible :

- Latence VAD.
- Latence STT.
- TTFT du LLM.
- Temps avant premier son TTS.
- Temps d'interruption.
- Latence vocale bout en bout.
- Utilisation CPU/GPU.
- Consommation RAM/VRAM.
- Charge du visualiseur.
- Synchronisation audio/animation.

Distinguer systématiquement mesures, estimations et objectifs.

---

# 10. PERSONNALITÉ ET SÉCURITÉ

Le logiciel doit rester compatible avec les modèles abliterated.

Prévoir :

- Prompts système configurables.
- Profils de personnalité.
- Mode UNHINGED.
- Aucun filtrage conversationnel additionnel imposé par l'interface.
- Indépendance des permissions système.

Un profil de personnalité libre ne doit jamais accorder automatiquement des droits d'accès supplémentaires aux outils, fichiers, navigateurs ou comptes.

Les actions sensibles requièrent des autorisations explicites.

Préserver :

- Les données utilisateur.
- Les préférences.
- Les conversations.
- Les secrets.
- Les journaux nécessaires au diagnostic.

---

# 11. EXÉCUTION PAR ÉTAPES — DÉVELOPPEMENT RÉSILIENT

Le budget de crédits Codex est limité.

L'organisation doit maximiser le travail utile produit par session tout en réduisant les risques d'interruption.

Les étapes ci-dessous représentent des points de validation et d'enregistrement. Elles ne nécessitent pas une session distincte chacune.

## J2.0 — Préparation

- Inspection ciblée du projet existant.
- Sélection des bibliothèques.
- Vérification des licences.
- Architecture minimale des modules audio et PRESENCE.
- Préparation de la branche et du journal de progression.

## J2.1 — Capture et transcription

- Capture micro.
- Périphériques.
- VAD.
- STT français.
- États et gestion des erreurs.
- Tests ciblés.

## J2.2 — Synthèse vocale

- TTS local.
- Deux voix françaises.
- Sélection et préécoute.
- Lecture audio.
- Tests ciblés.

## J2.3 — Conversation mains libres

- Orchestration audio et LLM.
- Échanges continus.
- Barge-in.
- Annulations.
- Historique unifié.
- Tests.

## J2.4 — PRESENCE morphologique

- Fond personnalisable.
- Interface responsive.
- Visualiseur centré.
- Ligne plate.
- Onde microphone arrondie.
- Noyau de réflexion.
- Noyau de parole synchronisé au TTS.
- Transitions morphologiques.
- Tests.

## J2.5 — Couleurs et transcription

- Emotional Spectrum.
- Operational Spectrum.
- Séparation des fonctions.
- Transcription cinétique.
- Préférences.
- Tests.

## J2.6 — Livraison Windows

- Tests de non-régression.
- Compilation Windows.
- Artefact contenant `Jarvis.exe`.
- Documentation d'installation.
- Tests de réception Windows.
- Rapport final.

**Termine et enregistre chaque étape cohérente avant d'en engager une nouvelle.**

N'attends cependant pas inutilement une nouvelle session pour continuer si le travail peut progresser dans la session courante.

---

# 12. FAIL-SAFE — PROTECTION CONTRE LES INTERRUPTIONS

## 12.1 Commits et sauvegardes

Après chaque étape cohérente :

1. Exécute les tests applicables.
2. Consigne les résultats.
3. Enregistre les fichiers modifiés.
4. Crée un commit Git.
5. Push si les permissions le permettent.
6. Mets à jour les documents de reprise.

Ne jamais faire de force push.

Ne jamais écraser le jalon 1 validé.

Si une étape doit rester partielle, conserve un commit récupérable en la signalant explicitement comme inachevée.

Ne confonds pas « commit créé » et « push réussi ».

## 12.2 Journal d'avancement obligatoire

Maintiens :

`docs/JALON-2-PROGRESS.md`

Pour chaque étape, indiquer :

- Identifiant.
- Statut.
- Critères satisfaits.
- Critères restants.
- Tests exécutés.
- Tests réussis.
- Tests échoués.
- Tests ignorés.
- Fonctions réellement vérifiées sur Windows.
- Limitations.
- Commit correspondant.
- Prochaine opération.

Statuts autorisés :

- NON COMMENCÉ.
- EN COURS.
- IMPLÉMENTÉ.
- TESTÉ.
- VALIDÉ WINDOWS.
- BLOQUÉ.

## 12.3 Pourcentages objectifs

Créer dès le début une liste stable et numérotée des critères d'implémentation et de validation du jalon.

Calculer séparément :

**Avancement d'implémentation**

Nombre de critères d'implémentation satisfaits / total des critères × 100.

**Avancement de validation**

Nombre de critères validés avec preuve / total des critères de validation × 100.

Ne jamais inventer de pourcentage sur la base d'une impression.

Ne pas compter une fonction comme validée Windows si les seuls tests disponibles ont été exécutés dans le cloud ou sous Linux.

Ne pas compter un test ignoré comme réussi.

Les critères doivent rester stables pour permettre des comparaisons entre sessions.

## 12.4 Fichier de reprise

Maintiens :

`docs/NEXT-CODEX-SESSION.md`

Contenu obligatoire :

- Dépôt et branche.
- Dernier commit exploitable.
- État du jalon.
- Étapes terminées.
- Étape en cours.
- Fonctionnalités restantes.
- Derniers résultats de tests.
- Problèmes connus.
- Prochaine modification précise.
- Commandes utiles.
- Instructions permettant de reprendre sans refaire les étapes validées.

## 12.5 Gestion des limites de session

Tu ne peux pas présumer connaître les crédits restants.

Applique une politique prudente :

- Préférer des sous-tâches de durée maîtrisée.
- Éviter de démarrer un gros chantier lorsqu'un arrêt paraît imminent.
- Ne pas multiplier les expérimentations longues.
- Toujours préserver un état récupérable.
- En cas d'interruption prévisible, terminer ou sécuriser la sous-tâche en cours.
- Ne pas engager une nouvelle étape si la précédente n'est pas enregistrée.
- Ne jamais inventer un résultat pour clôturer artificiellement une étape.

Une interruption brutale reste possible : les commits fréquents doivent limiter la perte de travail.

---

# 13. TESTS D'ACCEPTATION

Préparer les contrôles suivants, à vérifier réellement sur Windows 11 lorsque nécessaire :

1. `Jarvis.exe` démarre.
2. Ollama est détecté.
3. Les conversations textuelles fonctionnent toujours.
4. L'historique persiste après redémarrage.
5. Le microphone fonctionne.
6. Le STT transcrit correctement le français.
7. Le TTS masculin fonctionne.
8. Le TTS féminin fonctionne.
9. Le changement de voix fonctionne.
10. La conversation est mains libres.
11. JARVIS peut être interrompu oralement.
12. Les segments audio annulés ne sont plus diffusés.
13. Les échanges vocaux sont sauvegardés.
14. Le fond noir est appliqué par défaut.
15. La couleur de fond peut être personnalisée et restaurée.
16. Le noyau reste centré après redimensionnement.
17. La taille du noyau reste harmonieuse et adaptée à l'écran.
18. La ligne reste plate au silence.
19. L'onde réagit à la voix utilisateur.
20. L'onde est composée de courbes continues, sans pics anguleux.
21. La réflexion déclenche une animation propre.
22. Le noyau réagit au TTS réellement diffusé.
23. Le noyau et la ligne ne sont jamais deux visualiseurs indépendants simultanément.
24. Les transitions morphologiques sont fluides et annulables.
25. Le mode DORMANT se distingue réellement du silence.
26. La transcription suit la restitution vocale selon la précision annoncée.
27. Le spectre émotionnel respecte ses règles.
28. Le spectre opérationnel respecte ses règles.
29. Les deux spectres sont indépendants.
30. Les profils graphiques fonctionnent.
31. Aucune métrique fictive n'est affichée.
32. Aucune régression majeure du jalon 1.
33. Le workflow Windows produit un artefact exploitable.
34. Les données restent préservées lors d'une mise à jour.

Ces contrôles constituent une base minimale. Tu peux les subdiviser en critères techniques précis sans gonfler artificiellement les pourcentages.

---

# 14. LIVRABLES

Développe sur une branche dédiée issue de `main`.

Livrer :

- Sources fonctionnelles.
- Modules audio et PRESENCE.
- Tests automatisés.
- Résultats des tests.
- Workflow GitHub Actions Windows.
- Nouvel artefact contenant `Jarvis.exe`.
- Guide d'installation des composants audio.
- Guide de validation sur Windows.
- Journal de progression.
- Fichier de reprise.
- Procédure de restauration du jalon 1.

Commit et push régulièrement.

Créer une Pull Request si les permissions le permettent.

Ne pas fusionner automatiquement vers `main`.

Ne pas remplacer le précédent exécutable fonctionnel.

---

# 15. RAPPORT DE FIN DE SESSION OBLIGATOIRE

Même si le jalon n'est pas entièrement terminé, fournir ce compte rendu :

**JARVIS UNHINGED NEXT — JALON 2**

- Implémentation : X/Y critères — Z %.
- Validation : A/B critères — C %.
- Dernière étape terminée : J2.X.
- Étape actuelle : J2.X ou aucune.
- Fonctionnalités réellement opérationnelles : ...
- Fonctionnalités partiellement implémentées : ...
- Tests réussis : ...
- Tests échoués : ...
- Tests ignorés : ...
- Validation Windows restante : ...
- Branche Git : ...
- Dernier commit : ...
- Push GitHub : réussi / impossible.
- Pull Request : lien ou indisponible.
- Prochaine action exacte : ...

Terminer par :

**PROMPT DE REPRISE CODEX**

Fournir un texte court prêt à copier dans une nouvelle session Codex, indiquant de lire `docs/JALON-2-PROGRESS.md` et `docs/NEXT-CODEX-SESSION.md`, puis de poursuivre exactement à partir du dernier état enregistré.

Ne pas répéter les étapes déjà terminées et validées.

---

# 16. ORDRE DE PRIORITÉ FINAL

1. Préserver le jalon 1.
2. Obtenir une capture et une transcription réelles.
3. Faire fonctionner les deux voix françaises.
4. Permettre une conversation mains libres.
5. Implémenter l'interruption naturelle.
6. Créer le visualiseur morphologique unique.
7. Obtenir une onde audio arrondie et réellement synchronisée.
8. Centrer et dimensionner correctement le noyau sur toutes les tailles de fenêtre.
9. Implémenter les animations de réflexion et de parole.
10. Intégrer le fond personnalisable.
11. Intégrer les deux spectres chromatiques indépendants.
12. Finaliser la transcription cinétique.
13. Optimiser les performances.
14. Tester et livrer une nouvelle version Windows.
15. Conserver toutes les preuves et instructions de reprise.

Ne cherche pas à obtenir une finition cinématique parfaite avant d'avoir assuré le fonctionnement vocal réel.

Ne transforme pas les exigences difficiles en simulations trompeuses.

**Une fonction vaut davantage lorsqu'elle fonctionne réellement que lorsqu'elle semble terminée dans l'interface.**

## INSTRUCTION FINALE

Commence maintenant le développement du Jalon 2.

Exécute les étapes de manière autonome et incrémentale.

Privilégie les résultats concrets, les tests, les commits, la récupération du travail et les composants réutilisables.

Poursuis tant que les étapes peuvent être terminées proprement dans la session disponible. En cas de risque d'interruption, sécurise le travail et prépare la reprise plutôt que d'engager une nouvelle étape majeure.

**Objectif final : un JARVIS vocal local, naturel, réactif et visuellement remarquable, représenté par une seule entité holographique qui se transforme harmonieusement entre silence, écoute, parole, réflexion et sommeil.**