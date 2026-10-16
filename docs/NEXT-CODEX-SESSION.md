# Reprise JARVIS — correctif VAD/STT + PRESENCE

- Dépôt : https://github.com/ABBYWILLY/JARVIS-0.0.1
- Branche : `feat/jalon-2-voice-presence`. Aucun changement direct de main/force push.
- Dernier correctif : `fix(voice): retain pending STT turns and measure response latency`.
  Retrouver son SHA par `git log -5 --oneline`.
- J2.0–J2.6 et jalon 1 préservés. Lire JALON-2-PROGRESS.md et VOICE.md pour les preuves.

## État actuel J2.7 — priorités techniques

Fiabilité STT et instrumentation des latences implémentées/testées. Les mentions
historiques d’absence de ces travaux plus bas décrivent l’état avant cette mission.

- Second tour abandonné si Whisper occupé : corrigé avec un seul emplacement
  d’attente, priorité au dernier tour, purge sur nouvelle parole ou suspension.
  Après erreur STT, le tour conservé démarre ; anciennes générations sans effet
  sur statut, PRESENCE ou mesures du tour courant.
- Première phrase longue : limite initiale 96 caractères au lieu de 240, suite
  inchangée, sans perte de texte. Aucun moteur, seuil ou modèle remplacé.
- **Diagnostic micro / STT** : silence PCM, file/inférence STT, attente premier
  texte Ollama, premier segment, chargement/synthèse Piper, premier PCM au DAC
  estimé et total depuis la fin de tour détectée. Ce total exclut le silence VAD ;
  le délai acoustique/Bluetooth n’est pas mesuré. Aucune promesse de gain chiffré.
- 52 tests ciblés distincts réussis, sans ignoré, détails dans le suivi. Les mesures
  d’horloge/périphériques de test ne sont pas des benchmarks du PC Windows.

Prochaine action : vérifier le build Windows de ce commit puis mesurer à froid et
à chaud plusieurs tours sur le PC, en gardant modèle/voix/silence identiques.
Recette : tour bref et long, reprise pendant STT, interruption casque, fin TTS puis
réouverture du micro speakers. Copier les mesures/erreurs du diagnostic si échec.
Ne pas déclarer la validation matérielle terminée sans ces preuves.

## Ne pas recommencer le diagnostic établi

Le propriétaire a confirmé sur Windows 11 : capture USB Condenser/MME réelle,
préécoutes Tom/Siwis et chat Ollama fonctionnels, mais aucune transcription après
« Voix détectée », même à 300/800/1500 ms. Sortie XTREME140 en mode speakers.

Cause reproduite : cancel_speech sur speech_start renvoie mute=False ; le worker
réinitialisait VAD/TurnDetector même sans changement d’état. Le tour était effacé.
Correctif : mute idempotent. Ajouter les diagnostics, fin manuelle et garde 20 s
avec réarmement après silence, reprise après erreur STT. Aucun moteur remplacé,
aucun seuil modifié, pas de réduction du bruit sans preuve ni téléchargement implicite.
PRESENCE conserve un seul maillage spline : amplification visuelle indépendante,
attaque rapide/retour doux ; expressivité persistante 0–100 %, défaut 65 %.

61 tests ciblés distincts réussis sous Linux/X virtuel (59 puis 11 dont 9 communs).
SOXR réel 44,1/48 kHz et Silero ONNX réel testés. Les séquences de parole/bruit
utilisent des probabilités contrôlées et STT simulé, pas un vrai microphone.
Ne pas déclarer la conversation matérielle corrigée avant essai du nouvel EXE.

## Prochaine opération concrète

1. Vérifier Actions **Windows Jarvis** sur le dernier commit de cette branche.
   API Actions refusée ici (`Forbidden`), mais le proxy Git permet le push.
   Workflow existant : tests complets, build vocal, smoke EXE, artefact
   `Jarvis-Jalon2-Windows-x64-<commit>`. Ne pas demander de token pour Git.
2. Télécharger cet artefact vert et préserver l’ancien EXE et les données.
   Build manuel : `powershell -NoProfile -ExecutionPolicy Bypass -File
   .\scripts\build-windows.ps1 -WithVoice` → `dist\jalon-2\Jarvis.exe`.
3. Dans COMMAND OS ouvrir **Diagnostic micro / STT**, activer l’écoute puis parler
   et laisser le silence. Attendu : speech_start → turn_end (silence) → transcribing
   → stt_complete + texte. Vérifier aux trois durées, bruit seul/avec parole,
   phrase longue, réponse Ollama/TTS puis reprise du micro speakers.
4. Si blocage : relever RMS, probabilité, état, durée, fréquence PCM/512 échantillons
   et événements/exception. Si VAD reste haute, bouton **Terminer le tour courant**.
   Ne pas attribuer le problème au ventilateur sans ces observations.
5. Ajuster **PRESENCE → Réglages → Expressivité de l’onde (%)** : vérifier la
   persistance, le silence immobile, les courbes et le centrage/DPI sur Windows.
   Compléter les validations Windows dans le suivi après preuve seulement.

Pas de microphone ni de Windows cloud ; aucun EXE Windows de ce correctif exécuté
ici. Préserver les modèles, SQLite v2 et sauvegardes v1. Ne pas fusionner automatiquement.

## Extension J2.7 en attente — Emoji-aware Speech & Semantic Morphing

Demande du 16 octobre 2026. **Non commencée : 0/100 représentations implémentées,
0/100 validées**, aucune galerie ni séparation emoji/TTS livrée. Préalable imposé
par le propriétaire : corrections STT et latence J2.7 implémentées, testées et
enregistrées dans Git avant cette extension. STT : correctif `a12ca3f` avec preuves
ci-dessus ; travaux/mesures de latence J2.7 non attestés dans le dépôt. Ne pas
considérer le seul temps STT du diagnostic comme une mesure de latence bout en bout.

Après ce préalable, livrer par lots cohérents testés et committés :

- Séparer texte original, texte TTS et événements visuels avec positions dans le
  texte original. Préserver intégralement COMMAND OS, sous-titres et SQLite.
  Retirer seulement les séquences emoji du TTS avant toute conversion descriptive,
  gérer variantes, modificateurs, ZWJ, drapeaux, touches et caractères invisibles
  associés sans supprimer le français, les mots explicites (« une fusée »),
  la ponctuation utile ou la prosodie. Aucun filtrage des noms d’emojis dans le
  texte ordinaire : leur origine doit déterminer leur traitement.
- Sélectionner 100 emojis distincts d’après une source vérifiée : priorité
  https://www.unicode.org/emoji/frequency.html et complément
  https://home.unicode.org/emoji/emoji-frequency/ . Sources proposées, **pas encore
  étudiées ni classement retenu**. Vérifier date des données, ordre, méthode,
  représentativité et limites ; comparer toute source plus récente solide.
  Ne pas présenter une page consultée récemment comme des données mondiales récentes.
  Variantes/teintes de peau peuvent partager un dessin, sans gonfler le compteur.
- 100 formes vectorielles légères, reconnaissables et réellement animées, intégrées
  au programme. Mutualiser yeux/bouches/cœurs/larmes/mains/flammes/étoiles.
  Exemples initiaux proposés : ❤️ 💡 🚀 ✨ ⚠️ ✅ ❌ 😊 ; la sélection finale suit
  la source et les lots livrés, jamais des placeholders comptés comme terminés.
  Emoji inconnu : texte conservé, retiré du TTS, aucune transformation inventée.
- Même visualiseur UNIQUE : noyau → symbole holographique arrondi → noyau,
  monochrome cyan ou Emotional Spectrum, centré et responsive, transitions fluides
  et courtes, sans duplication, bitmap, GIF, pack externe ni clignotement.
- Déclencher depuis les callbacks PCM et la portion de phrase correspondante ;
  conserver la correspondance malgré le nettoyage du texte TTS. Si pas d’alignement
  mot à mot, documenter une approximation bornée et son erreur, sans synchronisation
  parfaite annoncée. Regrouper les emojis adjacents et limiter la cadence ; aucune
  animation concurrente. Interruption : annuler immédiatement l’actuel et les
  événements en attente, priorité à l’écoute, aucun retour tardif d’ancienne génération.
- Préférences persistantes : Semantic Morphing activé/désactivé, intensité
  discret/normal/expressif, réduction du mouvement (respecter aussi celle existante).
  Aucun ralentissement sensible du TTS, modèle ou téléchargement supplémentaire.
- Galerie de prévisualisation individuelle des 100 formes. Tests paramétrés pour
  chaque entrée : Unicode reconnu, véritable géométrie associée, absence de lecture
  descriptive, transition et retour au noyau. Tests français/Unicode complexe,
  original intact, ponctuation, synchronisation approximative, interruption et
  annulation, préférences, responsive et non-régression du visualiseur principal.
  Publier nombre exact implémenté/validé et liste exacte restante après chaque lot.

Prochaine mission prioritaire : établir puis traiter les latences J2.7 et compléter
la recette vocale Windows, avec mesures et commits. Ne pas engager les 100 tracés
tant que ce préalable n’est pas rempli ; conserver cette extension dans la reprise.
