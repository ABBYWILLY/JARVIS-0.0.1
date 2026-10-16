# Jalon 2 — progression vérifiable

Branche : `feat/jalon-2-voice-presence`, issue de `origin/main` `dcc327b`.
Le jalon 1 a été validé sur Windows par le propriétaire ; ce n’est pas une validation
Windows du présent jalon. Spécifications : DOCX existants + `JALON-2-SPEC.md`.
Aucun changement direct de main, aucun force push, aucune fusion automatique.

**Dernier correctif : VAD/STT + expressivité**, détail en fin de fichier. Les
bilans J2.0–J2.6 ci-dessous restent des preuves historiques ; les observations
Windows du propriétaire ne valident pas encore la nouvelle version corrigée.

**Actualisation J2.7 : fiabilité STT et instrumentation des latences implémentées
et testées sous Linux**, bilan en fin de fichier. Mesures matérielles Windows
toujours à réaliser ; les constats antérieurs sur l’absence d’instrumentation
J2.7 sont historiques.

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

## Correctif conversation VAD/STT + expressivité PRESENCE

- Constat propriétaire Windows 11 : USB Condenser/MME, capture et onde réelles,
  « Voix détectée » sans STT aux silences 300/800/1500 ms. Préécoutes Tom/Siwis
  et chat Ollama fonctionnent ; sortie XTREME140 Bluetooth en mode speakers.
- **Cause reproduite dans le code** : `speech_start` appelle `cancel_speech()`
  qui envoie `mute=False` alors que le micro est déjà actif. Le worker réinitialisait
  inconditionnellement TurnDetector et Silero, effaçant le tour nouvellement détecté.
  Même séquence PCM/VAD et même commande UI : ancien code = 3 débuts/0 segment STT ;
  correctif = 1 début/1 segment/transcription de test. Le ventilateur n’est pas une
  cause démontrée et aucun réducteur de bruit ou moteur supplémentaire n’est ajouté.
- Réinitialisation seulement lors d’un changement réel de mute. Les véritables
  suspensions restent effectives. Fin normale au silence inchangée ; garde 20 s
  existante conservée, puis attente de silence pour éviter les boucles de faux tours.
  Fin manuelle explicite accessible dans le diagnostic.
- Diagnostic local discret : RMS PCM réel, probabilité Silero, parole/silence,
  durée, fin de tour/motif, début/fin STT, texte ou exception et temps STT ;
  4 mesures/s maximum, 32 événements en mémoire, sans enregistrement audio.
  Une erreur STT ne tue plus la capture ; reprise au tour suivant testée.
- PRESENCE : même maillage/splines centrés, compression visuelle non linéaire,
  attaque rapide et relâchement plus doux, ligne strictement plate sans signal.
  Curseur persistant 0–100 %, défaut 65 %, indépendant de PCM/gain/VAD/STT.
- **61 tests ciblés distincts réussis**, aucun échec ni ignoré : première passe
  59 tests (`tests.test_capture_turns tests.test_audio tests.test_voice_flow
  tests.test_presence`), puis 11 tests capture/contrats après ajout de deux cas
  de commande manuelle/suspension réelle (9 cas déjà exécutés, ne pas additionner).
  Commande : `DISPLAY=:99 LD_LIBRARY_PATH=/tmp/j2-portaudio/usr/lib/x86_64-linux-gnu
  .venv-voice/bin/python -m unittest <modules ci-dessus> -v`.
  SOXR réel vérifié à 44,1/48 kHz → 16 kHz avec trames de 512 sans perte ; Silero
  ONNX réel vérifié au silence/réinitialisation. Parole courte/longue, bruit constant,
  parole avec bruit, VAD bloqué et reprise STT sont des scénarios PCM/probabilités
  contrôlés, **pas une mesure de reconnaissance réelle en présence du ventilateur**.
  Tk/SQLite/HTTP de test sont réels ; microphone et reconnaissance des phrases simulés.
- Workflow Windows vocal existant conservé : tests, compilation et smoke EXE,
  artefact `Jarvis-Jalon2-Windows-x64-<commit>`. Consultation Actions refusée par
  l’API (`Forbidden`) dans cet environnement. Aucun nouvel EXE Windows exécuté ici.
- **À vérifier sur le PC** après récupération de l’artefact vert : une phrase puis
  silence aux trois réglages, phrase longue, bruit seul, phrase avec bruit, réponse
  et reprise micro speakers ; consulter la chaîne d’événements décrite dans VOICE.md.
  Si l’échec persiste, ces valeurs et l’étape d’exception permettent un diagnostic
  exploitable. Les validations matérielles/latences restent ouvertes, sans les déclarer réussies.

## Extension J2.7 demandée le 16 octobre 2026 — reportée selon priorité utilisateur

- **Statut : non commencée, 0/100 emojis graphiques implémentés, 0/100 validés.**
  Ni galerie, ni nettoyage Unicode TTS, ni synchronisation emoji livrés.
- Préalable utilisateur : corrections STT et latences J2.7 implémentées, testées
  et committées. Correctif STT `a12ca3f` enregistré ; travaux de latence J2.7 non
  attestés ici, validation de la nouvelle conversation Windows encore ouverte.
  Aucun développement partiel de l’extension avant ce préalable.
- Cahier de reprise dans `NEXT-CODEX-SESSION.md` : texte original/TTS/événements
  distincts, Unicode complexe, 100 formes vectorielles mutualisées, visualiseur
  unique, callbacks PCM avec approximation annoncée, annulation prioritaire,
  préférences persistantes, galerie et tests pour les 100 entrées.
- Sources Unicode officielles proposées consignées, mais non évaluées et aucun
  classement choisi. Date des données, méthode et limites à vérifier lors de
  l’implémentation ; aucune prétention de fréquence mondiale actuelle.
- Cette mise à jour touche uniquement la reprise et le suivi : aucun code,
  dépendance ou test modifié ; aucun test relancé pour cette documentation.

## J2.7 — fiabilité STT et latences, priorité technique

- Défaut reproduit : un second tour terminé pendant une inférence Whisper était
  abandonné. Correction : un emplacement d’attente borné au dernier tour pertinent,
  lancé dès la fin du calcul en cours, y compris après erreur. Nouvelle parole ou
  suspension réelle invalide le tour en attente ; pas de backlog croissant.
- Les événements STT des anciennes générations ne peuvent plus effacer l’indicateur
  de traitement, l’état PRESENCE ni les mesures du tour actuel. Les résultats
  obsolètes restent ignorés. Le correctif mute idempotent `a12ca3f` est conservé.
- Attente évitable reproduite : première phrase sans ponctuation retenue jusqu’à
  240 caractères. Premier segment désormais borné à 96 caractères, puis limite
  précédente conservée ; texte français/ponctuation/mots préservés par les tests.
  C’est une réduction du tampon initial, pas un gain de latence matérielle mesuré.
- Diagnostic existant enrichi sans dépendance : silence PCM, attente/inférence STT
  mesurées séparément, premier texte Ollama, premier segment TTS, chargement Piper,
  synthèse initiale, premier PCM et fin de tour détectée → PCM au DAC estimé.
  Horloge monotone commune aux processus ; temps de réception UI inclus pour
  Ollama, estimation PortAudio pour le DAC. Aucune mesure acoustique/Bluetooth
  et aucune valeur de performance du PC inventée. Mesures transitoires en mémoire.
- **52 tests ciblés distincts réussis, 0 échec/ignoré** : passe initiale de 50
  (`test_capture_turns`, `test_audio`, `test_tts`, `test_voice_flow`,
  `test_presence_integration`), puis deux cas supplémentaires validés : purge STT
  sur mute réel et instrumentation du worker TTS. Reprises ciblées après ajustement
  des assertions d’annulation, sans compter les cas répétés deux fois.
  Les trois régressions principales échouaient avant modification puis passent.
  SOXR/Silero réels, Tk/SQLite/HTTP réels ; reconnaissance/parole, horloges du test
  de métriques et périphérique de sortie simulés explicitement. Aucun microphone
  ou modèle Whisper/Piper réel exécuté pour ces mesures dans le cloud.
- Procédure PC dans `VOICE.md` : relever les latences à froid/chaud sur plusieurs
  tours à configuration constante, reprise pendant STT, barge-in casque, retour
  micro speakers. Build Windows/artefact à vérifier, aucune validation Windows
  du présent correctif annoncée. Moteurs, seuils, modèles et visualiseur conservés.

## J2.7 optimisation audio — lot 1

- Piper préparé pendant Ollama, réutilisé au repos après fin normale, générations
  par commande. Lecture active distincte du worker chargé : Stop/PRESENCE/reprise
  speakers préservés. Interruption active/urgence/erreur ferment le processus ;
  arrêt écoute/sommeil/fermeture libèrent aussi un moteur encore en chargement.
  Première clause assez longue envoyée à sa virgule avant96 caractères.
- STT brut/conservé, fr, export exclusif d’un seul WAV demandé/confirmé, réécoute
  sans Piper, échec d’export sans perte de conversation et demande annulée signalée.
  Qualité PCM et bords heuristiques, cinq références/WER ; CLI corpus/benchmark.
- **80 tests distincts réussis, aucun ignoré** :75 audio/diagnostic/flux/PRESENCE,
  3 desktop J1, 2 nouveaux cas réécoute sans Piper/demande WAV remplacée. Reprises
  non additionnées. Smoke source vocal réussi avec profil temporaire sous /tmp ;
  premier essai sur profil par défaut hors droits refusé, corrigé par isolation.
  Silero/SOXR/Tk/SQLite/HTTP réels ; reconnaissance/voix/callbacks de tests simulés.
- Avant/après contrôlé : deux tours→2 chargements auparavant,1 en réutilisation.
  **Aucun gain Windows en secondes ni WER réel mesuré** sans modèles et microphone.
  Commandes exactes et limites dans VOICE.md ; modèles absents refusés sans téléchargement.
- Aucun poids, moteur alternatif, paquet, thread ou GPU ajouté. Disque : code
  léger ;625Kio maximum par WAV demandé, rien supprimé. VAD et garde350ms conservés
  faute de preuve justifiant réduction ; délai acoustique Bluetooth non mesuré.
- Lot1 codé/testé, recette matérielle Windows ouverte ; lots2–5 non commencés.

## Lot 2 — COMMAND OS / PRESENCE

- Métriques sous chaque réponse : modèle reçu, tokens, tokens/s et durée eval
  issus des statistiques finales Ollama ; TTFT observé avant HTTP→premier texte
  visible, sans exposer ni inventer l’activité interne du modèle. Valeurs absentes
  ou invalides = —. Préférence de masquage persistante, métadonnées SQLite v2
  enrichies sans migration, historique et annulations/erreurs testés.
- PRESENCE : moniteur latéral superposé (pas de déplacement du canvas), Chrono
  masquable/persistant, STT, attente LLM, premier texte→audio, fin de tour→audio et
  fin de parole estimée→audio. DAC estimé, Bluetooth acoustique non mesuré.
  Courbe historique12 tours réels, aucun signal biologique ou calcul LLM simulé.
- THINKING : déformations harmoniques arrondies plus marquées et halo doux sur
  le même maillage ; fermeture exacte pour spline continue. Réduction mouvement,
  micro réel, plat au silence, transitions/interruption et lot1 conservés.
- **75 tests ciblés réussis, 0 ignoré**, commande : `DISPLAY=:99
  LD_LIBRARY_PATH=/tmp/j2-portaudio/usr/lib/x86_64-linux-gnu .venv-voice/bin/python
  -m unittest tests.test_metrics tests.test_presence tests.test_voice_flow
  tests.test_presence_integration tests.test_jarvis.ProtocolTests
  tests.test_jarvis.DesktopTests -v`. Données serveur de test, audio simulé ;
  HTTP/Tk/SQLite et transports spawn réels. Test live Ollama non exécuté.
- Rendu inspecté sous X virtuel avec valeurs de test explicitement contrôlées.
  Pas de microphone/benchmark matériel ni EXE Windows validé ici. Aucun poids
  ou paquet supplémentaire. Lot3 ensuite ; lots4/5 non commencés.

## Lot 3 — comparaison faite, implémentation bloquée, pas livré

Sources officielles consultées (code/manifests, sans poids),16octobre2026 :
[Pocket3.3.0](https://github.com/kyutai-labs/pocket-tts/tree/3dbee45d343d7dddd0d105468d17f8dcba14db3e),
[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS/tree/022e286b98fbec7e1e916cb940cdf532cd9f488e),
[ChatterboxV3](https://github.com/resemble-ai/chatterbox/tree/5de7a54aa4e5e2baadb0182dde554908b48b85c2).
Pocket français/CPU est prioritaire techniquement ; Qwen/Chatterbox imposent des
versions incompatibles avec les dépendances voix installées. Détail dans la reprise.
CodeMIT/Apache vérifié, **licences poids/voix non vérifiées**, pas de certification
d’usage commercial ou de redistribution. Accès HF et sites officiels complémentaires
refusé CONNECT403 malgré vérification des routes HTTP/Git disponibles.
Pas d’adaptateur premium ou de téléchargement ajouté sous une conformité supposée.
Pas de taille totale ni de gain sonore/latence Windows inventés. Une preuve de
licences est demandée à l’utilisateur. Lot2 publié21a1284 ; APIActionsForbidden.
Lots4/5 non commencés, aucune suppression ni modification du moteurPiper.
