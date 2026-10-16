# Reprise JARVIS UNHINGED NEXT — Jalon 2

- Dépôt : https://github.com/ABBYWILLY/JARVIS-0.0.1
- Branche : `feat/jalon-2-voice-presence`, issue de main `dcc327b`.
- Dernier commit de code exploitable : **d0c18c6** (J2.6 packaging). Les commits
  suivants peuvent ne contenir que ce bilan/reprise ; utiliser `git log -8 --oneline`.
- Implémentation : **23/24 = 95,83 %** ; validation : **16/34 = 47,06 %**,
  invariants testés sous Linux. **Aucune validation matérielle Windows du jalon 2.**
- Dernière étape terminée : J2.5 ; actuelle : J2.6 BLOQUÉ sur artefact/recette Windows.

## Ne pas refaire le travail enregistré

J2.0 à J2.5 sont enregistrés et poussés. Capture native→SOXR16k, Silero par frames,
STT français local CPU int8, deux profils Piper réels installables, sélection/preview,
chaîne STT→LLM→TTS, arrêts/epochs/backlog borné, migration SQLite v2 avec backup,
PRESENCE unique centrée/morphing, fond/contraste/profils/sommeil, deux spectres,
sous-titres PCM estimés et profils conversationnels sont codés.
Le micro est fermé au lancement ; aucun poids n’est téléchargé à l’exécution.
Les voix/STT n’ont pas été entendus/exécutés avec de vrais poids dans le cloud.
Piper est le seul moteur livré ; SpeechProvider prépare des alternatives.

## Dernières preuves

- `DISPLAY=:99 .venv-voice/bin/python -m unittest discover -s tests -v` :
  **89 exécutés, 86 réussis, 0 échec, 3 ignorés** (Ollama réel et deux tests voix réels).
- Source et binaire PyInstaller Linux : Tk/SQLite/spawn et diagnostic vocal réussis.
  Phonémisation française eSpeak **fr**, VAD ONNX et SOXR exécutés réellement.
- Paquets Windows x64 Python3.12 de requirements-voice.txt résolus/téléchargés.
- Compilation Linux requiert bibliothèques Tcl/Tk du runtime et PortAudio local ;
  un premier smoke vocal sans chemin PortAudio a échoué, cause corrigée par le chemin
  de bibliothèques. Cela ne valide ni EXE Windows ni distribution Linux standalone.
- Pas de microphone, pas de GPU de référence, pas de Windows ; HuggingFace renvoie403.
- Git push réussi ; API PR/Actions Forbidden. Aucun résultat CI Windows confirmé.

## Prochaine opération exacte

1. Ouvrir GitHub Actions **Windows Jarvis** sur la branche Jalon2 ; vérifier le
   dernier push ou lancer manuellement. Si échec, lire le log et corriger uniquement
   la cause prouvée. Build : `scripts\build-windows.ps1 -WithVoice`, sortie
   `dist\jalon-2\Jarvis.exe`, ancien EXE préservé. Artefact distinct Jalon2.
2. Télécharger l’artefact vert. Sur Windows, suivre **docs/VOICE.md** pour lire les
   licences et installer explicitement Whisper et Tom/Siwis. Aucun poids dans l’EXE.
3. Exécuter les tests réels facultatifs puis les 34 contrôles de réception Windows
   dans docs/JALON-2-SPEC.md §13 ; compléter les preuves dans JALON-2-PROGRESS.md.
4. Casque pour barge-in. Mode haut-parleurs suspend le micro ; pas d’AEC/full-duplex.
   Mesurer qualité/latences/ressources réelles, examiner DPI100/150/200 et plein écran.
5. Créer la PR si l’API redevient utilisable ; sinon interface GitHub compare.
   Ne pas fusionner automatiquement, ne jamais force-push.

## Données et restauration

Préserver ancien EXE et dossier utilisateur avant premier lancement J2. Une v1 est
sauvegardée avant migration v2. Ne pas ouvrir une DBv2 avec l’ancien EXE ; restaurer
la copie v1 dans un autre dossier JARVIS_DATA_DIR selon docs/VOICE.md. Conserver la
base v2 avec les nouvelles conversations. Ne jamais supprimer les données pour
réparer un test.

Lire les deux fichiers de suivi et la spécification jointe avant de reprendre ;
ne pas refaire les étapes validées. Pas de promesse de voix naturelle, de performance
ou d’EXE Windows fonctionnel tant que la recette correspondante n’est pas exécutée.
