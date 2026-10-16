# Reprise JARVIS Jalon 2

- Dépôt : ABBYWILLY/JARVIS-0.0.1 ; branche : feat/jalon-2-voice-presence.
- Base exploitable : dcc327b (main avec jalon 1 fusionné).
- Étape terminée : J2.1 adaptateurs (commit `J2.1: add local capture VAD and French transcription adapters`), intégration UI encore à venir.
- Étape suivante : J2.2 Piper, deux modèles FR, préécoute et vitesse.
- Lire JALON-2-PROGRESS.md et JALON-2-SPEC.md ; ne pas refaire le jalon 1 validé.
- Aucun matériel audio ni Windows dans le cloud ; HuggingFace est refusé par le proxy.
- Tests audio : `.venv-voice/bin/python -m unittest tests.test_audio -v` : 7 réussis ; `git status --short`.
- Restent ensuite deux voix Piper FR, orchestration/interruptions/SQLite, PRESENCE,
  spectres, sous-titres, CI Windows vocale et recette réelle.
- Ne pas confondre tests de contrat/signal synthétique et validation micro/voix réelle.
- Pas de force push ni fusion ; préserver EXE et profils utilisateurs du jalon 1.

Dernier état J2.2 : adaptateurs Piper/AudioPlayer et installateur explicite créés ;
4 tests TTS réussis. Prochaine modification : voice worker puis intégration UI et
migration de métadonnées. Aucune audition réelle de Tom/Siwis (HF bloqué).
