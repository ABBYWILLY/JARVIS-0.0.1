# Reprise JARVIS Jalon 2

- Dépôt : ABBYWILLY/JARVIS-0.0.1 ; branche : feat/jalon-2-voice-presence.
- Base exploitable : dcc327b (main avec jalon 1 fusionné).
- Étape terminée : J2.0 (préparation), commit nommé `J2.0: prepare voice milestone and recovery checklist`.
- Étape suivante : J2.1 capture locale, Silero ONNX par frame, STT faster-whisper CPU int8.
- Lire JALON-2-PROGRESS.md et JALON-2-SPEC.md ; ne pas refaire le jalon 1 validé.
- Aucun matériel audio ni Windows dans le cloud ; HuggingFace est refusé par le proxy.
- Commandes : `python -m unittest discover -s tests -v`, `git status --short`.
- Restent ensuite deux voix Piper FR, orchestration/interruptions/SQLite, PRESENCE,
  spectres, sous-titres, CI Windows vocale et recette réelle.
- Ne pas confondre tests de contrat/signal synthétique et validation micro/voix réelle.
- Pas de force push ni fusion ; préserver EXE et profils utilisateurs du jalon 1.
