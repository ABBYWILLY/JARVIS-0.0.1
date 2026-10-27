# JARVIS — PRESENCE GPU 3.0
## VALIDATION ARTISTIQUE A+B ET DIRECTIVES D'ANIMATION C+D

**Dépôt :** ABBYWILLY/JARVIS-0.0.1  
**Branche :** `feat/jalon-2-voice-presence`

Je valide la direction artistique actuelle des sous-lots A et B, notamment le noyau iridescent, les anneaux et le fond noir pur.

**Ne pas refaire ces éléments. Les conserver comme référence visuelle officielle.**

Je donne le feu vert pour les sous-lots **C — Animation et états** et **D — Semantic Morphing surfacique**, selon les directives suivantes.

## 1. ANNEAUX — ORBITES TRIDIMENSIONNELLES MULTIAXIALES

Je veux que les anneaux tournent réellement dans la profondeur autour du noyau.

Tous doivent avoir exactement le même centre que la sphère.

En revanche, chaque anneau possède son propre plan orbital incliné et son axe de rotation.

### Comportement

- Trois anneaux principaux, comme dans le rendu validé.
- Axe de rotation différent pour chaque anneau.
- Inclinaisons mêlant composantes horizontales, verticales et profondeur.
- Rotation continue, avec vitesses angulaires indépendantes.
- Sens horaire ou antihoraire propre à chaque anneau.
- Perspectives et déformations elliptiques cohérentes.
- Les anneaux passent visiblement devant et derrière le noyau.
- Occultation correcte des portions situées derrière la sphère.
- Aucun décentrage orbital ou vibration parasite.

Les anneaux ne doivent pas simplement tourner en 2D autour du centre de l'écran.

Employer des transformations tridimensionnelles et une projection perspective réelles ou mathématiquement cohérentes, adaptées au renderer ModernGL.

Créer des orientations qui évitent que les trois anneaux se superposent fréquemment.

Le résultat doit évoquer un gyroscope énergétique tridimensionnel.

## 2. VITESSE SELON L'ÉTAT

**IDLE**
- Noyau stable.
- Rotations très lentes ou suspendues selon les préférences.
- Halo doux et consommation minimale.

**LISTENING**
- Orbites lentes et ouvertes.
- Réaction du noyau au vrai microphone lors de l'intégration future.
- Pas de fausse activité audio.

**THINKING**
- Le noyau se contracte légèrement, d'environ 5 à 10 % de sa taille apparente, avec transition douce.
- Il semble concentrer son énergie.
- Les anneaux accélèrent clairement autour de leurs axes respectifs.
- Ils restent centrés sur le noyau contracté.
- L'énergie interne devient plus dense.
- Quelques impulsions lumineuses parcourent les orbites.
- La vitesse élevée reste fluide et lisible : éviter un flou permanent.

**SPEAKING**
- Le noyau reprend progressivement sa taille normale.
- Les anneaux ralentissent.
- Ils continuent à tourner lentement pendant toute la parole.
- La sphère demeure visible en permanence.
- La lumière et les pulsations suivent les véritables données audio.

Transitions avec inertie, accélérations et ralentissements progressifs.

Ne jamais téléporter les anneaux ou réinitialiser brutalement leurs angles.

## 3. PARTICULES — PLUS DE RICHESSE SANS CHAOS

Le rendu est actuellement trop pauvre en particules.

Augmenter leur densité, mais avec une distribution maîtrisée :

- Particules fines autour du noyau.
- Petites traînées sur certaines orbites.
- Quelques particules proches de la sphère.
- Profondeur variable.
- Tailles et luminosités différentes selon la distance.
- Apparitions et disparitions progressives.
- Aucun clignotement aléatoire.

Conserver de l'espace négatif.

Les particules doivent embellir le noyau, pas le masquer.

Nombre et complexité dépendants du profil Éco / Équilibré / Cinématique.

## 4. HALO — AURA PLUS INTENSE

Le halo est encore trop discret.

Renforcer :
- Le liseré Fresnel du noyau.
- L'aura lumineuse autour de la sphère.
- La diffusion lumineuse des anneaux.
- Les petits reflets.
- Le bloom sélectif.

Le fond reste strictement noir `#000000`.

Le bloom est produit par les objets lumineux, sans dégradé permanent dans le fond.

Éviter la surexposition et conserver la lisibilité de la surface sphérique.

## 5. PAROLE — AURA PILOTÉE PAR LE SPECTRE AUDIO

Je veux que l'aura du noyau pulse en fonction de la voix de JARVIS.

Ne pas limiter cette réaction au seul volume global RMS.

À partir du véritable PCM Piper, calculer à cadence bornée une représentation légère de plusieurs bandes fréquentielles, par exemple :
- Graves.
- Médiums.
- Aigus.

Utiliser une transformation spectrale légère lorsque nécessaire, avec fenêtre audio adaptée, lissage attaque/relâchement et traitement hors boucle graphique.

Associer les bandes à des comportements subtils :
- Graves : respiration et expansion du halo externe.
- Médiums : densité lumineuse et pulsation de la sphère.
- Aigus : scintillement fin des anneaux et reflets.

Le rendu doit rester musical et élégant, jamais stroboscopique.

Aucun son artificiel.

Silence PCM : retour naturel vers l'aura calme.

Distinguer clairement les essais de PCM synthétique du véritable flux Piper.

Cette analyse devra être réutilisable lors d'une future intégration GPU à Jarvis.exe, sans recalculer inutilement le spectre dans plusieurs modules.

## 6. SEMANTIC MORPHING — NE JAMAIS FAIRE DISPARAÎTRE LE NOYAU

Défaut actuellement constaté : lorsque le visualiseur affiche un emoji, il revient encore à une représentation 2D simple.

**C'est à corriger.**

Dans le prototype GPU :

- Le noyau reste sphérique et visible pendant toute l'expression.
- Les anneaux ralentissent et se disposent élégamment en couronnes concentriques autour de la sphère.
- Le visage ou le line art de l'emoji est gravé sur l'hémisphère visible.
- Les traits suivent la courbure de la surface.
- Le symbole doit être clairement identifiable.
- Le halo et la matière iridescente restent présents.
- À la fin, les traits se dissipent et les anneaux reprennent leur rotation.
- Aucun remplacement brutal par un maillage emoji plat.

Réutiliser les huit familles d'expressions existantes.

Pour les emojis faciaux :
- Yeux et bouche sur la surface de la sphère.
- Détails reconnaissables.
- Orientation temporairement frontale si nécessaire.

Pour les emojis non faciaux :
- Line art lumineux du symbole sur la sphère.

Préserver les priorités d'interruption et les exclusions du texte technique.

## 7. PRÉVISUALISATION ET TESTS

Tester distinctement :

1. THINKING prolongé, avec accélération des trois anneaux.
2. SPEAKING, avec rotation lente des anneaux et aura pilotée par PCM.
3. Sourire 😊 sur la surface du noyau.
4. Rire 😂.
5. Affection ❤️.
6. Transition THINKING → SPEAKING.
7. Interruption pendant une expression.

Produire des captures réelles du renderer et une courte vidéo montrant les mouvements.

Les tests doivent vérifier :
- Les axes de rotation indépendants.
- Le centrage constant.
- L'occlusion.
- L'absence de disparition de la sphère pendant le morphing.
- La modulation spectrale.
- La stabilité des transitions.
- L'absence de callbacks ou d'événements obsolètes.

## 8. PERFORMANCES ET ARCHITECTURE

Matériel cible : RTX 3070 8 Go.

Priorité absolue à Ollama, Whisper et Piper.

Préserver :
- ModernGL local et gratuit.
- Prototype autonome.
- Canvas stable en production.
- Fond noir.
- Profils de qualité.
- Suspension du rendu lorsqu'il est masqué.
- Réduction des mouvements.
- Limites de ressources.
- Aucun modèle IA additionnel.
- Pas d'intégration du GPU à Jarvis.exe pour l'instant.

Mesurer CPU, RAM, FPS, frametime et allocation GPU quand accessible.

Ne pas prétendre avoir effectué un benchmark RTX 3070 si seul Mesa est disponible.

## 9. LIVRAISON

Implémenter **C puis D**, en commits séparés.

Tests ciblés, push et CI Windows pour chaque sous-lot.

Produire une comparaison avant/après et une documentation des nouveaux raccourcis.

Ne pas engager les sous-lots E et F au-delà des preuves et vérifications nécessaires à C et D, sans instruction supplémentaire.

Ne pas modifier `main`.

**CRITÈRE FINAL :**

PRESENCE doit rester une sphère holographique vivante dans tous ses états.

Ses anneaux tournent autour d'axes tridimensionnels indépendants.

Elle se contracte légèrement lorsqu'elle réfléchit.

Ses orbites accélèrent pendant THINKING et ralentissent pendant SPEAKING.

Son aura réagit aux fréquences réelles de sa voix.

Ses émotions apparaissent gravées à la surface du noyau, sans retour à un emoji plat.

L'ensemble doit être sensiblement plus vivant, lumineux et expressif, sans devenir brouillon ni gourmand en ressources.