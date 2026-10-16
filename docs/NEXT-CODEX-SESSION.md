# Reprise JARVIS Jalon 2

- Dépôt ABBYWILLY/JARVIS-0.0.1, branche feat/jalon-2-voice-presence issue de main dcc327b.
- Dernier code exploitable : commit nommé `J2.4: add single-mesh responsive audio-driven Presence`.
- J2.0, adaptateurs J2.1/J2.2 et orchestration J2.3 enregistrés. Aucun matériel audio/Windows validé ici.
- Lire JALON-2-PROGRESS.md et JALON-2-SPEC.md. Ne pas refaire le jalon 1 validé.
- J2.4 enregistré : PRESENCE, 15 tests réussis. Prochaine étape exacte : J2.5 spectres indépendants et sous-titres depuis événements audio joués.
- Ensuite J2.6 : packaging vocal séparé, guide installation/licences/modèles, recette Windows.
- Tests : `DISPLAY=:99 .venv-voice/bin/python -m unittest tests.test_voice_flow tests.test_voice_storage tests.test_jarvis.DesktopTests -v`.
- 16 contrats de flux audio, 8 stockage et 3 desktop réussis ; STT/Piper testés par contrats, VAD ONNX réel sur silence.
- Cloud sans PortAudio/micro/Windows ; HuggingFace renvoie403. Modèles réels non téléchargés, tests live à faire sur PC.
- Echo : casque pour barge-in ; mode speakers suspend le micro pendant lecture et 350 ms ensuite. Pas d’AEC haut-parleurs.
- Migration v1→v2 avec backup sqlite3 avant ALTER. Ne jamais ouvrir la v2 avec ancien EXE ; restaurer la sauvegarde v1 séparée pour rollback.
- Ne pas force-push/fusionner, préserver ancien EXE. Toutes les captures partent d’une activation explicite ; audio non conservé sur disque.
