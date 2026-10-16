# Reprise JARVIS — correctif VAD/STT + PRESENCE

- Dépôt : https://github.com/ABBYWILLY/JARVIS-0.0.1
- Branche : `feat/jalon-2-voice-presence`. Aucun changement direct de main/force push.
- Dernier correctif : `fix(voice): preserve active turns and expose local STT diagnostics`.
  Retrouver son SHA par `git log -5 --oneline`.
- J2.0–J2.6 et jalon 1 préservés. Lire JALON-2-PROGRESS.md et VOICE.md pour les preuves.

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
