# Jalon 2 — progression vérifiable

Branche : `feat/jalon-2-voice-presence`, issue de `origin/main` `dcc327b`.
Le jalon 1 a été validé sur Windows par le propriétaire ; ce n’est pas une validation
Windows du présent jalon. Spécifications : DOCX existants + `JALON-2-SPEC.md`.
Aucun changement direct de main, aucun force push, aucune fusion automatique.

## Critères d’implémentation stables (24)

Une case cochée signifie code intégré et testé au niveau indiqué, pas recette Windows.

- [x] I01 Capture micro locale sur activation explicite, libération à l’arrêt.
- [x] I02 Sélection entrée/sortie et erreurs de périphériques.
- [x] I03 VAD réel local, fin de tour, silences, pré-roll et limites.
- [x] I04 STT français local avec modèle installé, sans téléchargement implicite.
- [x] I05 TTS Piper : véritable modèle masculin français.
- [x] I06 TTS Piper : véritable modèle féminin français.
- [x] I07 Gestionnaire de voix, préécoute audio et vitesse persistante.
- [x] I08 Orchestration STT → Ollama → TTS segmenté, tours mains libres.
- [x] I09 Interruption vocale, invalidation des anciens segments et politique d’écho explicite.
- [x] I10 Arrêt manuel/urgence et sommeil désactivant capture et tâches.
- [x] I11 Migration SQLite préservant textes, provenance, dates, voix/moteur et interruptions.
- [x] I12 PRESENCE : une machine à états et une géométrie morphologique unique.
- [x] I13 Ligne plate au silence et onde arrondie pilotée par micro réel.
- [x] I14 Réflexion sur traitement réel et noyau piloté par audio diffusé.
- [x] I15 Centrage et proportions responsives sans déplacement par sous-titres.
- [x] I16 Fond noir, sélecteur, restauration et contraste automatique persistants.
- [x] I17 Spectre émotionnel conservateur, mots sélectifs, quatre modes persistants.
- [x] I18 Spectre opérationnel indépendant, texte explicite, aucun droit supplémentaire.
- [x] I19 Sous-titres sur audio joué, approximation annoncée, historique/copie.
- [x] I20 Profils graphiques et réduction du mouvement, ressources bornées.
- [x] I21 Préférences vocales/personnalité sans filtrage ni modification des permissions.
- [x] I22 Tests ciblés audio et non-régression du jalon 1.
- [ ] I23 Build Windows vocal séparé, contrôles de démarrage et artefact versionné.
- [x] I24 Installation, recette Windows, restauration et reprise documentées.

## Critères de validation stables (34)

V01 à V34 sont exactement les 34 contrôles de la section 13 de `JALON-2-SPEC.md`.
Une preuve Linux peut valider un invariant indépendant de l’OS (ex. géométrie),
jamais le microphone, l’écoute perceptive ou l’exécutable Windows. Aucune case
validée par un test ignoré. Preuves dans tests/test_voice_storage.py ; aucune preuve de matériel audio/Windows.

Validés : V04, V14, V15, V16, V18, V20, V21, V23, V24, V25, V27, V28, V29, V30, V31, V34.
Preuves : tests/test_voice_storage.py et les 15 tests tests/test_presence.py.
Il s’agit de persistance/invariants graphiques et d’orchestration sous Linux, pas
de la recette matérielle Windows. V17 (qualité/DPI) reste à examiner sur Windows. Implémentation : **23/24 = 95,83 %**. Validation : **16/34 = 47,06 %**.

## Étapes

| Étape | Statut | Preuves / reste | Commit / prochaine opération |
|---|---|---|---|
| J2.0 | TESTÉ | main inspecté, branche dédiée ; moteurs et contraintes définis ; tests baseline ci-dessous | commit `J2.0: prepare voice milestone and recovery checklist` ; implémenter J2.1 |
| J2.1 | IMPLÉMENTÉ | adaptateurs capture native/SOXR, périphériques, VAD Silero et STT FR local ; intégration UI en J2.3 ; matériel et modèle non disponibles ici | commit `J2.1: add local capture VAD and French transcription adapters` ; J2.2 |
| J2.2 | IMPLÉMENTÉ | Piper CPU, 2 profils distincts, PCM à fréquence native, segmentation et lecture ; UI J2.3 ; modèles/licences individuelles/écoute restent à vérifier | commit `J2.2: add Piper synthesis real playback and explicit model installer` ; J2.3 |
| J2.3 | IMPLÉMENTÉ | UI écoute explicite/devices/préécoute ; STT→LLM→TTS, epochs et arrêt prioritaire ; migration v2/backup ; tests de contrat, pas conversation audio réelle | commit `J2.3: integrate hands-free orchestration cancellation and lossless history` ; J2.4 |
| J2.4 | TESTÉ | maillage spline unique, états réels, fond/contraste, centre responsive, profils, sommeil et annulation ; 15 tests Linux | commit `J2.4: add single-mesh responsive audio-driven Presence` ; J2.5 |
| J2.5 | TESTÉ | spectres indépendants, quatre modes, mots ciblés, sous-titres depuis fraction PCM avec approximation signalée ; profils conversationnels persistants | commit `J2.5: add independent spectra and playback-driven captions` ; J2.6 |
| J2.6 | BLOQUÉ | code build/guide/tests terminés ; artefact et recette Windows non confirmés dans cette machine Linux | commit `J2.6: package optional voice build and preserve Windows baseline` ; vérifier Actions puis PC cible |

## Décisions et limites initiales

- Conserver Python/Tk et le processus Ollama existant. Modules audio facultatifs ;
  une panne ou une absence de dépendances audio ne bloque pas le texte.
- faster-whisper 1.2.1 CPU int8 + Silero VAD ONNX embarqué dans ce paquet : éviter
  PyTorch et préserver la VRAM. Modèle STT par chemin local, aucune récupération cachée.
- Piper 1.8.0 CPU/ONNX : deux modèles FR distincts. Moteur GPL-3.0-or-later ;
  notices et licences à conserver avec toute distribution vocale. Kokoro est
  étudié comme alternative ; ne pas promettre une voix masculine FR inexistante.
- Un casque est requis pour l’interruption vocale pendant la lecture dans ce jalon.
  En mode haut-parleurs, capture suspendue pendant TTS pour éviter l’auto-déclenchement ;
  interruption manuelle disponible. Pas de promesse d’AEC/full-duplex haut-parleurs.
- Cloud : aucun périphérique `/dev/snd`, aucun Windows. HuggingFace renvoie 403 :
  modèles non téléchargeables ici. Continuer le code et les tests indépendants ;
  fournir une installation explicite sur le PC Windows et des tests live opt-in.
- Contradiction générale existante : voix « optionnelle » dans résumé DOCX mais P0
  dans les exigences détaillées. Ce jalon cible bien la voix, sans supprimer de P0.

J2.0 tests baseline : 16 exécutés, 12 réussis, 0 échoué, 4 ignorés (3 écran, 1 modèle
Ollama absent). Windows du jalon 2 : aucun test. Références consultées sans copie :
Mark-LV CC BY-NC 4.0, backtalk/fullstack-agent AGPL-3+, site jarvis AGPL-3 ; ne pas
intégrer leur code. Concepts retenus : activation explicite, devices par nom/host API,
fréquence native et casque pour barge-in. Sources/liens dans JALON-2-SPEC.md.

J2.1 : `.venv-voice/bin/python -m unittest tests.test_audio -v` : 7 réussis, 0 échec,
0 ignoré. VAD ONNX réel sur silence ; STT testé par contrat, pas par un vrai modèle.
Capture matérielle et transcription française réelle non validées, aucun test Windows.

J2.2 : 4 tests TTS réussis, aucun échec/ignoré dans l’environnement vocal. Contrats
Piper des deux profils et fréquence vérifiés avec doubles de test ; aucune voix
synthétisée ni audible ici. Installateur explicite avec fiches de licence, versions
HF résolues et contrôle SHA-256 LFS / Git blob pour chaque fichier. Runtime offline.

J2.3 : 12 tests de flux réussis (Tk+SQLite+HTTP fixture, audio simulé explicitement),
8 tests stockage et 3 parcours desktop baseline réussis. Arrêt après fin du LLM,
barge-in casque, segments obsolètes et fermeture callback testés. Suite initiale
audio+baseline+stockage : 34 réussis, 1 ignoré (modèle Ollama). Aucun test Windows,
aucune audition ni capture physique. Les critères I05/I06 désignent les adaptateurs
et profils installables, pas des poids téléchargés ni une qualité vocale validée.

J2.4 : 15 tests présence + 17 flux/capture ciblés réussis, zéro échec/ignoré ;
smoke source réussi. Revue : tampon TTS de 64 phrases alimenté progressivement,
ancien plafond8 ne coupe plus les réponses rapides ; capture libérée si ouverture
échoue ; transcription sans modèle conservée dans la saisie. Capture écran du
silence inspectée sous X virtuel : noir et ligne plate ; aucune donnée audio inventée.

J2.5 : 27 tests présence/spectre réussis + 26 tests spectre/flux/desktop réussis
(certaines suites communes, ne pas additionner comme tests uniques). Aucun échec.
Estimation de tonalité lexicale conservatrice, négation simple, inertie3s, aucunappelLLM ;
aucune prétention de ressentir une émotion. Sous-titres : groupesde3 mots estimés
par durée PCM, pas alignement mots/phonèmes ; précisionaudible à vérifierWindows.
Profil UNHINGED testé : promptseul, aucuneactivationmicro ni permissionmodifiée.

## Résultat J2.6 de cette session

- Suite complète : **89 tests exécutés, 86 réussis, 0 échec, 3 ignorés**.
  Ignorés : vrai modèle Ollama, deux voix Piper réelles, aller-retour réel TTS→STT.
  Commande : `DISPLAY=:99 .venv-voice/bin/python -m unittest discover -s tests -v`
  (PortAudio local fourni dans les chemins de bibliothèques pour diagnostics).
- Préflight source `--voice-smoke-test` réussi : processus spawn, Tk/SQLite,
  imports natifs, phonémisation française **réelle**, VAD Silero ONNX **réel**,
  rééchantillonnage SOXR **réel**. Aucun microphone ni poids Whisper/Piper utilisés.
- Dépendances voix/installation épinglées et paquets Windows x64 téléchargés
  avec succès par pip ; aucun paquet absent à la résolution Windows Python3.12.
- PyInstaller Linux : binaire de contrôle 173 Mio, `--smoke-test` réussi et
  `--voice-smoke-test` réussi **avec PortAudio local disponible**. Le premier essai
  vocal sans ce chemin système a échoué ; cause isolée à la découverte de PortAudio,
  corrigée par configuration de bibliothèque (pas de vérification désactivée).
  PortAudio extrait d’un paquet Debian vérifié par APT et les index signés, sans
  installation système. Bibliothèques Tcl/Tk spécifiques à cette machine incluses.
  Cela ne constitue pas un test Windows ni une distribution Linux standalone.
- Défaut détecté en revue et corrigé : après une erreur SQLite/UI, purger aussi les
  buffers/callbacks et invalider les epochs ; 4 tests d’intégration supplémentaires
  prouvent qu’aucun ancien sous-titre/état audio ne réapparaît après arrêt/sommeil.
- Windows : workflow vocal prêt sur push/PR/manual ; artefact distinct et sortie
  `dist/jalon-2`, ancien EXE préservé. **Aucun nouveau EXE Windows exécuté ici**.
- Matériel/qualité : pas de microphone cloud, pas d’audition Tom/Siwis, pas de STT
  français réel ni d’inférence réelle ; modèles HF refusés403. Pas de mesures
  utilisateur inventées, pas de garantie60tok/s, pas d’AEC haut-parleurs.
- Licences : moteur Piper GPL3+, sources et notices référencées ; licences des poids
  Tom/Siwis non vérifiées ici, fiches à lire avant installation explicite. Aucun
  poids redistribué. Piper est le seul moteur livré, interface SpeechProvider prévue.

Les 16 validations concernent les preuves indépendantes de l’OS listées plus haut.
**0 contrôle matériel validé sur Windows pour ce jalon.** Ne pas marquer J2.6 terminé
avant réception de l’artefact et recette. Prochaine opération : Actions Windows,
puis installation explicite des modèles et exécution des contrôles réels du guide.

## Commits et publication

J2.0 `ad91560` ; J2.1 `a1ba661` ; J2.2 `a263a0a` ; J2.3 `b515983` ;
J2.4 `3dfc6fe` ; J2.5 `e773a08` ; J2.6 code exploitable `d0c18c6`.
Tous ces commits ont été poussés sur `feat/jalon-2-voice-presence` (aucun force push).
Création de PR refusée par l’API GraphQL GitHub : Forbidden. Le proxy Git HTTPS
fonctionne ; ne pas demander de token pour le push qui fonctionne déjà. L’exécution
Actions et son artefact ne sont pas confirmables via l’API de cette session.
Ouvrir Actions sur GitHub puis vérifier le dernier workflow de cette branche ;
créer une PR via compare/main...feat/jalon-2-voice-presence si nécessaire. Ne pas fusionner.
