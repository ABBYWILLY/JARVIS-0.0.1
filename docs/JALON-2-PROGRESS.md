# Validation Centre / Studio — étape E, 24 octobre 2026

Commits publiés : A e2f8b27, B 513dc86, C c0e21c6, D 426e270,
correctif d'isolation DPI 441f0dd. Centre à cinq familles avec recherche locale,
éditeurs canoniques, Studio transactionnel, quatre réglages visuels réellement
rendus, démonstration à huit états, CLI isolée, captures et MP4 sont livrés.

Suite Linux Tk9 et EGL logiciel réel : 604 tests exécutés, 595 réussis,
9 ignorés, 76,079 s. Les ignorés concernent six dépendances natives absentes
et trois essais réels opt-in. Campagnes ciblées Tk8.6 réussies ; après
isolation DPI, 23 tests ciblés réussis. Les comptes se recouvrent.

La CI A est verte (40039278838). Les prototypes GPU A/B/C/D sont verts.
Les builds applicatifs B 40039808068 et C 40040103974 ont révélé une pollution
des nouvelles fixtures DPI : l'échelle 250 % restait active entre deux
interpréteurs Tk. Le pied de sous-titres se masquait alors faute de place.
Ces tests restaurent maintenant l'échelle initiale ; aucune assertion PCM,
sous-titres ou mots-clés n'est supprimée et le rendu métier n'est pas modifié.
C contenait aussi l'ancien contrat « Fermer », adapté dans D à « Annuler »
avec vérification renforcée des trois actions. Suivre les derniers runs Actions
avant de déclarer la compilation verte.

Guide et preuves : docs/CONTROL-STUDIO.md. Observation du seul aperçu Canvas
Linux au repos sur 5,02 s : CPU moyen 0,47 % d'un cœur, RSS moyen 36,38 MiB,
aucun callback Canvas actif. Pas de comparaison globale LOT 7 ni de mesure RTX.

Restent : recette Windows/DPI/esthétique et micro/Piper/Qwen sur le PC ; palettes
libres non ajoutées ; ancienne fenêtre Mémoire de largeur minimale 820 px ;
intégration GPU conditionnée aux mesures RTX3070. LOT 2 non officiellement validé.
LOTS 4/5/7 non commencés. main préservée. Validation matérielle en attente.

---

# Démonstration et preuves visuelles — étape D, 24 octobre 2026

Studio publié c0e21c6 ; CLI run_presence_demo.py utilise uniquement un profil
SQLite temporaire. Scénario8états réel Canvas, étiquette PCM synthétique,
--auto-close/--reduced-motion et captures facultatives sans écrasement.
Preuves intégrées docs/assets : Centre sombre, Studio, planche8états et MP4
202images exportées25FPS (pas une mesureFPS matérielle). Guide CONTROL-STUDIO.md.
Inspection visuelle : THINKING distinct, sourire reconnaissable, repos plat ;
l'esthétique finale Windows reste à juger sur PC. Relevé limité Linux5,02s du
processusCanvas seul : CPU0,47% d'un cœur, RSSmoyen36,38MiB, zéroafterCanvas
au repos. Aucun moteur IA/audio actif ni comparaison globale LOT7.
Première suite globale603tests : trois erreurs de sous-cas d'un ancien test
cherchantFermer. Il vérifie maintenant Annuler et les3actions à100/200/250%DPI,
avec leurs bornes absolues et fermeture effective ; aucune validation supprimée.
32tests ciblés après adaptation réussis sousTk9 etTk8.6. Nouveau cas première
ouvertureDémo réussi. Suite globale finale et CI à vérifier étapeE.
Ne pas modifiermain ; LOTS4/5/7 hors mission, LOT2 non officiellementvalidé.

---

# PRESENCE Studio2.0 — étape C, 24 octobre 2026

B publié513dc86. Nouveau Studio remplace l'atelier immédiat : un brouillon,
Avant/Après sur le même Canvas, préréglages Éco/Équilibré/Cinématique,
Annuler/Restaurer/Appliquer. Seul Appliquer enregistre ; restauration d'origine
reste un brouillon. Préférences futures et raccourcis externes préservés.
Tous les réglages existants restent accessibles ; diffusion du halo, structure
THINKING et vitesses d'animation/transition ont un effet réel dans Canvas.
PresenceSettings demeure le contrat partagé, sans intégration GPU production.
Scénario hors ligne complet par DemoController : vrais objets de rendu,
PCM synthétique explicitement étiqueté ; événements réels prioritaires.
Deux défauts reproduits corrigés : Treeview blanc illisible sousTk9 et
TclError/callback résiduel après destruction directe de PRESENCE avec Studio.
79tests intégrés Tk9 réussis (5,710s), 39tests ciblés Tk8.6 réussis (8,639s).
Export et captures étapeD en préparation ; suite globale/CI ensuite.
Aucun modèle ou moteur obligatoire ajouté. Validation matérielle en attente.

---

# UX Master Control — étape B, 24 octobre 2026

Inventaire A publié e2f8b27, deux CI Windows vertes (40039278838 application,
40039278787 prototype). Centre de contrôle : cinq familles, recherche locale
insensible aux accents, recherche globale incluant les réglages avancés,
Ctrl+, depuis COMMAND OS, Ctrl+F/Entrée/Escape. Il ouvre les éditeurs canoniques,
sans recopier les préférences. Paramètres modèle et Voix désormais défilants,
actions fixes, champs atteignables au clavier ; Voix expose les seuils/threads
existants dans Avancé sans changer leurs valeurs. Préécoute conserve son contrat
d'enregistrement préalable, explicitement indiqué. 24tests ciblés intégrés Tk9
réussis (4,249s), 7Voix Tk8.6 réussis. Petites fenêtres paysage/portrait et
DPI100/250% automatisés sous Linux, pas recette Windows matérielle.
Étapes C Studio transactionnel puis D démonstration/preuves en préparation.
LOT2 reste non officiellement validé ; LOTS4/5/7 hors mission.

---

# Jalon 2 — progression vérifiable

## PRESENCE GPU — prototype optionnel

Reprise après quota, aucun travail perdu : moteur ModernGL/GLFW autonome avec
shaders procéduraux, anneaux/filaments/particules, bloom quart-résolution,
réemploi des8familles et du modèle PRESENCE. Canvas reste celui de JARVIS.
Guide, étude et mesures : PRESENCE-GPU*.md ; JSON brut dans docs/benchmarks.
47tests ciblés puis une régression d'économie de rendu ; suite intégrée :
576tests,567réussis,9ignorés,70,325s. EGL/GLFW Linux réels, driver logiciel.
Mesures isolées :29,70/36,28FPS aux profils30/60, CPU logiciel318–398%,
~95MiB RSS moyenne ; aucune VRAM physique/latence IA ou voix mesurée.
Intégration différée jusqu'à recetteRTX3070+IA/voix. CompilationWindows séparée
avec sondes et licences ; résultats finaux dans Actions du commit publié.

## PRESENCE GPU — phase0 préalable

Audit LOTS3/6 sura93a70f, rapport `AUDIT-LOTS-3-6.md`. Corrections démontrées :
heuristiques auto sur citations/négations, OverflowError sur numériques malformés,
cyan neutre des palettes. Raccourci F10 réel et restauration géométrie/DPI testés.
528tests exécutés,519réussis,9ignorés,71,107s Linux/Tk9 ; ciblés Tk8.6/9 verts.
SQLite/Canvas réels, PCM/LLM contrôlés ; matériel Windows et Qwen réel en attente.
Prototype GPU ensuite, intégré seulement si ses mesures respectent la mission.

## Finition reprise — aperçu RichText

Menu Lecture et typographie : vrai MarkdownView local, polices/styles et titres
visibles avant enregistrement. Modifications temporaires séparées de l'archive,
pas de reparsing du chat ni d'inférence. Aide syntaxique explicite souligné et
surligné, aperçu restaurable, clavier et nettoyage ressources testés.
46tests intégrés Tk9 et32tests isolés Tk8.6 réussis. Suite finale intégrée
Tk8.6 :523tests exécutés,514réussis,9ignorés (natifs/modèles absents),97,162s.
La suite Tk9 avant cet ajout comptait521tests,512réussis,9ignorés ; ses46tests
concernés repassent après intégration. Commits de reprise :
cec390b morphing,65bd81c LOT3,1e9c765 LOT6 ; dernier ajout par git log.
CI morphing39944644962 etLOT3 39944920954 vertes, compilation/EXEsmoke Windows.
Dernière CI et validation globale après intégration : consulter Actions.

## Presence Evolution — LOT6 P1

Travail interrompu repris après LOT3 : THINKING lenticulaire organique, trait6px
et halo27px réels au réglage6/96dpi. Atelier et réglages persistants de halo,
taille, palette, ambiance et microexpressions bornées. Aperçu hors ligne annulé
par le vrai audio. Mini/F10 réutilise fenêtre/Canvas/pool23objets, sans topmost ;
retour COMMAND OS et statut micro visibles. Correction des offsets Mini→normal.
Pas de modification de capture/VAD/STT/PCM/TTS, des modèles ou des permissions.
Tests ciblés Tk8.6/9, géométrie et préférences ; suite intégrée locale Tk9 :
521tests exécutés,512réussis,9ignorés (natifs/modèles absents),70,486s. Inclut les
LOT3/6, le correctif morphing et le retour Mini→normal. CPU/RAM/latence Windows
et recette graphique sur PC en attente.

## Cognitive Evolution — LOT3 C1

Reprise du travail interrompu : routage heuristique local avec priorité manuelle,
budgets J2.8 conservés et provenance du choix persistée ; Créatif documenté comme
politique de génération. Continuer épingle objectif/passages originaux dans le
contexte existant, chaîne complète si possible sinon extraits déclarés ; archive,
brouillon et interruptions préservés. Pas de résumé LLM systématique.
Mémoire/Contexte expose les inclusions enregistrées, distingue souvenirs approuvés,
historique, demande utilisateur et texte généré non vérifié. Pas de migration ni
de mémorisation implicite, garanties de sauvegarde inchangées.
91tests backend +27interfaceTk9 +41interfaceTk8.6 réussis ; tests à doublures
Ollama, sans prétendre avoir mesuré la qualité narrative ou le matériel Windows.
LOT6 et dernière suite intégrée/CI : sections suivantes et dernier run Actions.

## Reprise du23octobre — Semantic Morphing

Correctif ciblé : attente THINKING idempotente, statuts STT tardifs non
interruptifs sans nouvelle parole, fin de segment fiable malgré callback visuel
PCM perdu. Annulation réelle et générations obsolètes préservées. Trace48étapes
dans Diagnostic micro/STT, copiable. Trois phrases sourire/cœur/rire : parcours
Tk/événements voix/Canvas couvert ; 164tests sous Tk8.6 et164sousTk9 réussis.
Échantillons PCM de test, pas de micro physique ni d'audio Piper réel validés ici.
Cause exacte du cas Windows à confirmer avec trace si le défaut persiste.
Publication et CI : voir git log/Actions ; LOTS3/6 en finalisation séparée.

## J2.8 — lot 4 : observabilité et comparaison locale

Les métriques masquables distinguent génération, durée totale serveur, traitement
du prompt, compteurs réels et TTFT visible. Contexte expose estimation prudente,
réserve et souvenirs effectivement sélectionnés. Raisonnement demandé/observé
distingué, sans affirmer qu’un serveur a obéi à un champ qu’il pourrait ignorer.

`python -m jarvis.inference_benchmark` : trois questions sur corpus synthétique
fixe, mêmes modèle/contexte/sortie/température, ordre alterné, préchauffage commun
de16 tokens hors comparaison. JSONL neuf/exclusif, écrit et vidé après chaque
mesure ; interruption conservée, modèle absent refusé sans téléchargement,
aucune pensée interne enregistrée. Écarts uniquement sur mesures présentes et
réponses complètes/non vides ; absence de tokens jamais remplacée par estimation.
Comparaison combinée contexte+raisonnement, caches influents, qualité à inspecter.
Commande Windows exacte dans `NEXT-CODEX-SESSION.md`.

Validation finale : **260 tests exécutés, 257 réussis, 3 ignorés**,35,231s sous
Linux avec Tk/FTS/HTTP/IPC réels. Les ignorés exigent Ollama et les poids vocaux
réels absents du cloud.12 tests du benchmark utilisent des fixtures HTTP/CLI,
sans mesure Qwen réelle. Démarrage vocal de contrôle Linux réussi au lot3.
Ni compilation/EXE Windows ni gain matériel prétendus. Actions API = `Forbidden`.
Commits déjà publiés : lot1 `bbe88af`, lot2 `01ff571`, lot3 `234ff62` ; retrouver
le lot4 par `git log --oneline --grep='benchmark local inference'`.
Prochaine action : recette du propriétaire sous Windows11, Qwen3.5 4B/9B,
conversation vocale, approbation/rappel mémoire et comparaison des rapports.

## J2.8 — lot 3 : mémoire persistante approuvée

SQLite3 : migration atomique v1/v2 avec snapshot SQLite préalable conservant le
WAL, jamais écrasé ; échec d’indexation inattendu annule toute la migration.
Archives, voix, paramètres et jalon1 préservés. Table mémoires distincte avec
types durable/résumé/projet/document, états attente/approuvée/désactivée,
provenance JSON/date/titre/sujet, ID non réutilisable et déduplication exacte/NFC
par type. Aucune extraction automatique de fait utilisateur.

FTS5/BM25 local, index externes mémoires/documents et messages, triggers de
cohérence ; messages indexés seulement après finalisation, sans réindexer chaque
fragment du flux. Absence de FTS5 signalée et repli LIKE Unicode testé. Recherche
interconversations en consultation seule. Le contexte n’ajoute que les souvenirs
approuvés pertinents, dans son budget de rappels existant, avec leurs citations
et références inspectables. Aucune base vectorielle ni dépendance supplémentaire.

Bouton Mémoire : création manuelle, import TXT/MD UTF-8≤256Kio en attente,
préparation de résumés par citations exactes sans appel LLM, inspection des
originaux et approbation explicite. Correction : confirmation + snapshot puis
retour en attente. Suppression : ID/sujet confirmé + snapshot. Désactivation
réversible. Conflits de contenus pour même clé de sujet approuvée bloqués ;
ce contrôle ne prétend pas détecter toutes les contradictions sémantiques.

Suite complète Linux : **246 tests exécutés, 243 réussis, 3 ignorés** (inférence
Ollama réelle et deux essais vocaux réels sans poids présents). Tests HTTP/Tk/
SQLite/FTS/IPC réels, PCM et réponses de fixtures clairement simulés. Aucun EXE
ni benchmark Qwen/Windows exécuté. Reprises et paramètres cloud de démarrage de
test sauvegardés en brouillon, sans publication de l’environnement.
Après optimisation des triggers : 36 tests backend ciblés réussis, dont24 mémoire/
migration (deux tests supplémentaires sur l’absence de réindexation par fragment).
Puis43 tests d’intégration HTTP/interface/voix réussis et démarrage de contrôle
vocal Linux réussi, sans activer de microphone ni charger de poids STT/TTS.

## J2.8 — lot 2 : contexte ciblé et inspectable

`ContextBuilder` centralise le budget total, la réserve de réponse effective,
les instructions système intactes, la demande intacte et les tours récents
complets. Estimation UTF-8 prudente +32/message +256 de marge, jamais assimilée
au tokenizer Qwen. Questions autonomes : fenêtre allégée ; suivis : plus de
tours ; missions : fenêtre élargie. Déduplication exacte/NFC sans altérer casse
ou indentation du code. Aucun appel supplémentaire au LLM.

Rappel lexical ciblé dans la conversation active, pondéré par rareté des mots ;
phrases originales contiguës en résumé extractif explicitement non exhaustif,
sans couper une longue phrase potentiellement négative. Budget incluant les
marquages JSON/citations. Sources par ID/date/rôle/conversation ; aperçu récent
borné pour éviter de recopier tout l’historique dans chaque métadonnée.

COMMAND OS : bouton Contexte, sélection d’une réponse ancienne, détail de son
contexte, originaux consultables, comparaison à `prompt_eval_count` et au temps
de traitement réel. Réglages persistants ciblage/budget des extraits ; ciblage
désactivable. PRESENCE et voix inchangées. Schéma SQLite2 conservé sans migration.

**100 tests ciblés distincts réussis, aucun ignoré** : test_context20,
test_context_ui6, test_reasoning_ui6, test_context_storage3,
test_request_settings4, test_jarvis.SettingsTests4/StoreTests4/DesktopTests3,
test_voice_storage8, test_metrics10, test_voice_flow28, test_presence_integration4.
Revue supplémentaire de 1000 variantes : 908 constructions dans le budget,
92 refusées explicitement pour budget insuffisant (hors compte de tests).
Windows, tokens réels et gain de latence toujours à mesurer sur Ollama local.

Comparaison reproductible sur les six tours de la fixture `test_context.py`,
contexte4096/réserve1024 identiques, ciblage désactivé puis activé : estimation
UTF-8 incluant256 de marge, « 2+2? » 1609→514 (−68,1 %), suivi « Et le premier ? »
1617→960 (−40,6 %), rappel du port Zephyr1598→892 (−44,2 %), deux sources
anciennes effectivement retenues, port8765 et négation préservés. Ce sont des
tailles estimées de prompts de test, pas des tokens ou délais mesurés sur Qwen.

Lot1 publié `bbe88af`. Prochaine étape J2.8 : mémoire approuvée/FTS5/migration
sauvegardée, puis comparaison instrumentée à configuration identique.

## J2.8 — lot 1 : génération Ollama

L’ancien `JARVIS-SOURCES-v0.5/jarvis_core.py` (`ABBYWILLY/JARVIS`, b6066c4)
envoyait `think:false` par défaut. Le nouveau client omettait ce champ : les
modèles à raisonnement pouvaient épuiser leur budget sans texte visible.
Cause vérifiée dans le code ; aucun chronométrage Qwen réel effectué ici.

- Paramètres persistants Rapide/Automatique/Approfondi : `think:false`, omission,
  `think:true` au niveau racine HTTP. Rapide par défaut, y compris voix ; le
  choix explicite Approfondi reste possible. Budget indépendant : vocal256,
  discussion1024, mission4096 demandés, effectif plafonné à la moitié du contexte.
- Repli une seule fois sans `think` uniquement sur rejet explicite HTTP400/422,
  avertissement et statut conservés ; aucune relance d’un flux partiellement reçu.
- `message.thinking` reste privé ; présence observée signalée, contenu non stocké.
  TTFT du premier contenu non blanc ; réponse vide = erreur, limite atteinte =
  réponse partielle archivée, exclue du contexte complet. Lecture du fragment
  visible possible, arrêt manuel toujours prioritaire.
- Statistiques masquables : génération totale, prompt/temps de prompt, TTFT,
  débit, état du raisonnement. Tokens visibles indisponibles si Ollama ne fournit
  pas de compteur séparé : aucune estimation par caractères/soustraction.
- **74 tests ciblés distincts réussis, aucun ignoré** : test_request_settings,
  test_reasoning, test_reasoning_ui, test_metrics, test_jarvis.SettingsTests,
  ProtocolTests, DesktopTests et test_voice_flow. HTTP/Tk/SQLite et IPC réels ;
  réponses de fixtures, aucun modèle Qwen ni micro utilisé.

Pas de migration ni dépendance nouvelle. Aucune mesure de gain matériel ou
validation Windows annoncée. Actions API refuse la consultation (`Forbidden`) ;
workflow Windows existant conservé. Lots2–4 J2.8 à poursuivre dans cet ordre.

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


## Correctif Markdown/TTS — 18 octobre 2026

Rendu Markdown natif Tk pour réponses et historique, sans interprétation HTML ou
script. Styles combinés, titres/listes/citations/code, formules en texte et liens
HTTPS validés avec aperçu/copie. Mise à jour de la seule réponse courante, sélection
et défilement préservés, indices Unicode relatifs compatibles Tk 8.6/9.
Pipeline source/affichage/parole/événements commun : emojis et source conservés dans
SQLite/sous-titres, ponctuation/pauses et montants préservés ; maths usuelles
verbalisées, code omis explicitement par défaut ou lecture activable/persistante.
Segmentation protégée contre fragments Markdown/URL/LaTeX incomplets, métadonnées
source conservées à travers IPC Windows, annulation immédiate de la file vocale.
Aucune dépendance/modèle supplémentaire ; validation sonore Windows à réaliser.
Validation : **73 tests ciblés réussis, zéro ignoré** (richtext, pipeline vocal,
voice_flow, Markdown Tk, métriques, protocole HTTP et bureau). Démarrage source
`--smoke-test` réussi sous Linux/Tk virtuel ; aucune validation sonore matérielle.
Fixtures Tk libérées sur le thread principal, évitant leur GC dans le serveur HTTP.

Compatibilité Tk 8.6 : les colonnes Tcl sont UTF-16 mais les déplacements `+Nc`
comptent les points de code Unicode. Le calcul par longueur Tcl décalait les styles
après un emoji ; corrigé et reproduit/testé sous Tk 8.6 et Tk 9 (6 tests de rendu
sur chaque version). Premier run Windows fa4e6f6 échoué ; logs détaillés masqués
sans connexion, API403. Statut du prochain run à vérifier, sans présumer sa cause.
Vérification devises complémentaire : `20 $.` et `$5+$10` conservent chaque
mention dollars, sans les traiter comme une formule LaTeX. 16 tests parser réussis.


## Correctif spectre organique — 18 octobre 2026

Modes persistants expression/ambiance/neutre, intensité0–100, prévisualisation
visuelle locale sans micro/TTS/modèle. Classifieur lexical par passage : affirmation
explicite suffisante, joie ajoutée, négations/citations/hypothèses/ambiguïtés neutres.
Aucune inertie sémantique3s ; interpolation couleur450ms sur le même maillage.
Événements avec offsets originaux transmis dans l’IPC ; couleur déclenchée par les
callbacks PCM réellement lus, jamais par l’arrivée du texte LLM. Progression monotone
si Piper remet la fraction à zéro. Synchronisation estimée par phrase/bloc Piper,
pas de timestamp mot à mot ; précision limitée si une phrase produit plusieurs blocs.
Interruption prioritaire, file et sous-titres vidés, retour progressif cyan, réduction
des mouvements conservée. Aucun changement aux alertes ou permissions opérationnelles.
Validation : **140 tests ciblés réussis, zéro ignoré**, avec `/usr/bin/python3`
sous Tk8.6 : spectrum, presence, presence_integration, speech_pipeline, voice_flow,
richtext, markdown_ui, metrics, test_jarvis.ProtocolTests/ DesktopTests. Inclut raccord
source→voix→PCM→PRESENCE et interruption. PRESENCE38 tests aussi passés sous Tk9.
Aucune dépendance nouvelle, téléchargement de poids ou validation matérielle Windows.
Build Windows Markdown/TTS12e47ab réussi (run39122219877), après correctif UnicodeTk8.6.


## PRESENCE3 — sous-lot1, 22 octobre 2026

Demande complète : PRESENCE-3-SPEC.md. Épaisseur persistante1–10/défaut6 ; trait
3,44px et halo11px@96DPI, couches coïncidentes et trois sous-arcs préalloués issus
du mesh unique. THINKING orbital centré (diamètre~29% petit côté), symbolique ;
transitions ligne/noyau/PCM, silence parfaitement plat, sommeil compact immobile.
Halos et animations désactivables, réduction des mouvements, profils/DPI/charge
adaptatifs ; caches de signal/géométrie bornés et contrôles mis à jour si modifiés.
Tests :106 ciblés (presence/integration/voice_flow/spectrum) sous Tk9 ;48 sous Tk8.6.
Pas de modification moteur audio/LLM/SQLite ni de modèle/dépendance supplémentaire.

Mesure reproductible : `DISPLAY=:99 python scripts/benchmark_presence.py candidate
--output /tmp/presence-apres.json` (nouveau fichier obligatoire), `baseline` pour55311d1.
Linux/Python3.12/Tk9/Xorg960×640, fixture PCM générée explicitement, deux séries de
3 répétitions. CPU Python/Tcl par frame THINKING équilibré :599–659→489–555µs ;
silence410–429→297–299µs. JARVIS parle560–589→546–662µs : aucun gain confirmé.
7 objets canvas stables (4 auparavant), pas de timer silence/sommeil/masqué.
Pic allocations Python Tk THINKING/24frames :99,54→94,90Kio ; pic modèle
31,95→35,05Kio (hausse). Pas de mesure latence vocale réelle, Windows, RSS, VRAM
ou énergie. Ne pas extrapoler ces micro-mesures à une amélioration matérielle.

Recette Thinking Halo : PRESENCE→Réglages→Visualiseur ; épaisseur6, halos/animations
actifs, Équilibré. Observer une vraie attente Ollama : noyau centré sans bruit audio,
sous-arcs fluides, puis passage à la voix au premier PCM. Tester épaisseur1/10,
DPI100/150/200%, fenêtre redimensionnée, Réduire mouvements, masque et sommeil,
arrêt/interruption. Capture source Linux horsligne inspectée ; rendu Windows réel
et périphériques à vérifier sur le PC, sans prétendre que la CI remplace cette recette.


## PRESENCE3 — sous-lot2 : Emotional Field et UX

Dominante par réponse et nuances locales via MoodTracker à état borné ; pivots
après cohérence répétée ou marqueur narratif affirmé. Français : négations, citations,
contextes, intensificateurs et hypothèses ; analyse lexicale conservatrice, pas IA
émotionnelle ni lecture de la pensée. Nouvel apaisement et expressions composées.
Timeline source préparée une fois puis envoyée dans IPC : PCM déclenche couleur et
surlignages, pas arrivée anticipée des tokens. Rendu sans tokenisation/classification,
plancher et groupes approximatifs explicités. Plans capturent ponctuation, français,
Markdown et emojis ; 2lignes/12mots auplus, mots neutres et non encore estimés prononcés
sans coloration. Cache courant seulement, 64événements/4000caractères analysés par
segment ; queue visuelle inconnue neutre, audio/texteSQLite conservés intacts.
Mood pilote couleur/halo/inertie et courbes symboliques, pas amplitudeaudio inventée.

Réglages et interfaces : nouveaux défauts ambiance/expressivité75/Cinématique,
anciennes préférences explicites préservées ; intensité3modes, sous-titresémotionnels,
taille12–32, F9Immersion/Diagnostic. Étatsmicro structurés par vrais événements,
suspension jusqu’à démutage confirmé et repriseSTT après erreur. Moteurs et garde350ms
inchangés. Scénario4moods horsligne sans micro/modèle/son simulé. Annulation prioritaire
par écoute/arrêt/erreur/masque/fermeture. Contrôles de sécurité toujoursvisibles.
Réglages à onglets défilants au clavier, boutonFermer réservé ; tests Tk8.6/9 auxDPI
100/200/250%, sous-titresadaptatifs sans recouvrement des boutons. Danspetites fenêtres,
policeeffectiveajustée (préférenceconservée) et footeroptionnel masqué pour lisibilité.

Mesure finale sous-lot2 (même sondeLinux960×640, médiane3, unpassage, hors sous-titres) :
CPU Tk/frame THINKING équilibré520µs contre599–659µs initial ; silence309µs,
sommeil218µs, utilisateur625µs, JARVIS534µs. PicPython THINKING92,1Kio/24frames.
Pas de gain matériel global annoncé : pas Windows/GPU/RAMtotale/énergie/latencevocale.
Tests ciblés157 sans ignoré sousTk8.6, complémentsunitaires et parcoursTk9 réussis.
CaptureThinkingHalo réellement rendue par Tk8.6 sousLinux ; aperçu étiqueté horsligne.
Recette Windows11 toujours nécessaire (Tom/Siwis/micro/Bluetooth/DPI/accessibilité).
Validation finale complète :377 tests exécutés,368 réussis,9 ignorés (dépendances
vocales natives ou modèles réels absents), aucun échec. Démarrages source isolés
`--smoke-test` réussis sous Tk9 et Tk8.6 ; aucun profil utilisateur réel utilisé.

CI Windows : sous-lot 1 compilé et démarré avec succès (run 39804343514).
Le run 39810312573 identifie un seul échec : ancien test de sous-titres appelé
avant le layout natif, avec comparaison à une chaîne sans reflow. La fixture
attend désormais le layout et vérifie les mots exacts, les tags, la copie et les
deux lignes mesurées. 21 tests ciblés Tk8.6 et le test concerné Tk9 réussis.
Annotations d'échec ajoutées au runner CI ; aucune validation désactivée.
Compilation du dernier correctif à confirmer avant livraison.

## PRESENCE 3.2 — lot 1 Rich Conversation

Scanner et renderer existants étendus : ++soulignage++, ==surlignage==, titres,
styles combinés, listes visibles/indentées, séparateurs et tableaux monospace
textuels (repli possible). Typographie persistante : police installée, taille,
échelle et interligne, polices réutilisées sans reparsing de l'historique.
Copie source par clic droit/Ctrl+Maj+C ; sélection rendue conservée. Liens HTTPS
validés, aperçu puis ouverture explicite confirmée. Aucun HTML actif.
Cache interactif borné à 256 URL ; originaux et texte toujours conservés.
Validation : 390 tests exécutés, 381 réussis, 9 ignorés (natifs/modèles absents).
16 tests de rendu réussis sous Tk8.6 et Tk9. Recette Windows physique à effectuer.

## PRESENCE 3.2 — lots 2–3 Semantic Morphing

Un même moteur vectoriel léger pour les huit familles (pas de placeholders) :
sourire, rire, affection, tristesse, colère, surprise, réflexion, complicité.
Le contour principal du Canvas existant se contracte depuis sa géométrie visible,
se transforme en symbole puis retrouve l’état réel ; détails et halos mutualisés.
Réglages persistants d’activation/intensité, aperçu hors ligne des huit familles,
réduction du mouvement statique. Couleur du mood conservée, aucun moteur nouveau.
Événements source et scopes réponse/segment préparés à l’arrivée. Worker : fin de
segment après tous les PCM réellement joués. Drain final préservé, annulation et
queues64 bornées. Tails visuels après ponctuation attachés à la phrase précédente,
emojis connus/inconnus conservés dans les sous-titres, aucun audio fictif.
Synchronisation estimée, jamais mot à mot : milieu sur creux PCM réel puis cède à
la reprise ; à défaut, report à fin de segment. Les expressions finales ne
retardent ni l’audio ni la reprise micro350ms. Un micro ouvert silencieux n’est pas
une interruption ; vraie voix, nouvelle parole, erreur et arrêt restent prioritaires.
Validation : suite433/424réussis/9ignorés avant derniers cas de queue inconnue, puis
39 tests ciblés réussis (Tk8.6, géométries/parseur/intégration) après correctifs.
Suite finale et CI du dernier SHA à confirmer ; recette physique Windows restante.

## PRESENCE 3.2 — finition et validation

Les aperçus Emotional Field et Semantic Morphing s'annulent mutuellement :
aucun symbole ne masque le scénario THINKING existant. 435 tests exécutés,
426 réussis et 9 ignorés localement (dépendances natives/modèles non installés).
Tk8.6 : 80 tests ciblés puis 26 après cette finition ; Tk9 : suite complète.
Démarrages source isolés Tk8.6/9 réussis, capture réelle de l'aperçu intégrée inspectée.
CI Windows Rich Conversation2f896d7 et moteur959a94d vertes (runs39842257220 et
39844486651), avec compilation et démarrages de contrôle EXE ; dernier SHA à vérifier.

Coûts Linux960×640, sonde étendue5×400frames, CPU du processus Python/Tcl :
THINKING équilibré579→517µs/frame, utilisateur546→534µs, JARVIS623→538µs ;
silence315→278µs, sommeil212→200µs. Comparaison au code2f896d7 avec dépendances
courantes identiques ; VM partagée et dispersion observée dans les passes courtes :
aucun gain matériel global ou vocal déduit. Pool Canvas7→23objets, stable, détails
masqués non mis à jour au repos ; aucun timer silence/sommeil/fenêtre masquée.
Pic tracemalloc THINKING92,1Kio et paroleJARVIS96,1Kio inchangés sur24frames.
Contrôleur final seul : entrée11,24µs/frame, maintien1,55µs, retour11,79µs ;
picPython52 464octets avec contrôleur/origine/cache et24frames, catalogue préexistant
exclu. Pas de mesure RAM système/VRAM/énergie/latence audio/Windows physique.
Sonde existante étendue par --baseline-revision (SHA), aucun modèle téléchargé.

Recette Windows11 : COMMAND OS → Lecture et typographie, titres/styles/listes/
tableaux, copie source et sélection, liens confirmés, DPI100/150/200/250%.
PRESENCE → Réglages → Expressions, sélectionner chaque famille puis Prévisualiser ;
avec mouvement réduit, forme statique. Ensuite utiliser Piper réel avec une phrase
se terminant par :) ou ❤️, une expression au milieu, une queue emoji après ponctuation,
puis interrompre/reprendre la parole. Contrôler glyphes français, Bluetooth,
synchronisation approximative et priorité de la capture réelle. Cette recette
matérielle n'a pas été exécutée ici. La bibliothèque100emojis reste différée.

## Cognitive & Presence Evolution — LOT 1 logiciel, 23 octobre 2026

Causes vérifiées : le résumé PCM était remplacé par zéro avant confirmation VAD,
l'état écoute ne dessinait aucune onde, et la moyenne par buckets pouvait annuler
des fréquences réellement présentes. Le microphone reste distinct de la parole :
RMS exact et extrema PCM réels maintenant transmis/dessinés, sans signal inventé,
changement de sensibilité, gain, VAD ou moteur. Ces défauts visuels ne démontrent
pas la cause de l'absence de transcription constatée sur le PC Windows.

Diagnostic renforcé : périphérique sélectionné/réel/API, fréquence native, PCM,
vu-mètre RMS, VAD, tour/STT, statut PortAudio, pertes, étape et erreurs conservées.
Sans PCM, mesure inconnue plutôt que zéro ; ancienneté du PCM distincte de celle
du heartbeat, actualisée même sans événement. Une exception dans le callback est
remontée et le stream reste fermé si collecte métadonnées/abort échoue. Les
événements anciens/pendant suspension/après arrêt ne ravivent pas la parole.
Le PCM calme reprend aussi après un speech_start rejeté pendant suspension, sans
accepter la transcription de ce tour rejeté. La réactivation efface l'ancien STT.

COMMAND OS : navigation essentielle fixe, menu rétractable persistant, secondaires
défilants/clavier et overlay étroit ; statut complet consultable. F6 menu, F7
PRESENCE, F8 conversation. Pas de refonte esthétique ou de nouveau moteur.

Tests : suite locale Tk9, 460 exécutés, 451 réussis et 9 ignorés (dépendances natives
et modèles absents). Tk8.6 : 90 tests ciblés réussis, avec doublures PCM/STT
explicites, jamais le micro du PC. Navigation vérifiée aux quatre tailles
1100×620/620×900/640×480/560×400 et
échelles100/150/200/250 %, boutons essentiels entièrement visibles sous Tk8.6/9.
Source --smoke-test réussie sous Tk8.6 et Tk9 avec profils isolés. Aucun modèle téléchargé, donnée
utilisateur effacée ou benchmark matériel annoncé. CI du SHA courant à consulter
dans le workflow Windows Jarvis (tests, compilation PyInstaller et démarrages EXE).

**Validation matérielle en attente**. Recette guidée dans `docs/VOICE.md` : RMS
silence/parole/silence réel, onde, VAD→Whisper→Ollama, erreur/reprise, Windows/DPI.
LOT 1 non déclaré entièrement validé ; LOTS 2–7 non commencés avant cette recette.
Demande globale conservée dans `docs/COGNITIVE-PRESENCE-SPEC.md`.

## Cognitive & Presence Evolution — LOT 2 COMMAND OS NEO / Rich Text2.0

Poursuite explicitement demandée par l'utilisateur après le LOT 1 logiciel3c75c54
(CI Windows verte39910459009). La validation matérielle de son microphone reste
en attente ; aucun succès audio physique ou gain de latence n'est déduit de ce lot.

Interface Tk conservée : surfaces arrondies statiques pour conversation/saisie,
hiérarchie des messages, navigation et groupes secondaires, boutons/focus cohérents,
défilement natif réservé même en petite fenêtre. Métriques initialement masquées,
choix antérieurs conservés. Deux objets Canvas statiques au total pour ces surfaces,
aucune animation ou widget par message ; PRESENCE et pipeline audio non remplacés.

Rich Text réutilisé et complété : barré réel combinable avec gras/italique, accents
contrôlés0–100 %, fonte code/tableaux monospace vérifiée sur le système. Réglages
persistants et remise à l'origine, clés inconnues et profils voix/PRESENCE conservés.
Fontes/marges changées en place sans reparsing d'archive. Composer limité à18pt en
compact pour garder les actions visibles, texte conversation à la taille demandée.
TTS dérivé par le même scanner, marqueurs ~~ retirés sans perte de mots/source.
Syntaxe standard/extensions explicitée ; tableaux textuels et maths simples restent
les limites connues, sans composition LaTeX. Aucun HTML actif ; liens validés
ouverts seulement après confirmation.

Tests locaux Tk9 : 473 exécutés, 464 réussis, 9 ignorés pour natifs/modèles absents.
Tk8.6 : 85 tests ciblés réussis, démarrages sources Tk8.6/9 avec profils isolés OK.
Tests couvrant styles effectifs, persistance/reset, source/copie/sélection/scroll,
streaming et voix, formats complexes, petites fenêtres et DPI100–250 %, y compris
lecture maximale24pt/175 %. CI Windows du SHA courant : workflow Windows Jarvis,
tests complets, compilation et deux démarrages EXE ; résultat accessible dans Actions.
Recette humaine Windows/Tom/Siwis/micro reste à effectuer (docs/VOICE.md).
LOT 3 non commencé ; aucun modèle, moteur ou dépendance supplémentaire téléchargé.

CI4eda447 / run39915837584 : un test géométrique PRESENCE supposait tous les arcs
visibles alors qu'une frame >12ms déclenche correctement la réduction adaptative.
Même échec reproduit par horloge de coût contrôlé. Fixture cinématique stabilisée
(horloge/DPI) sans retirer ses assertions ; régression supplémentaire vérifiant
20ms de coût, réduction à2calques/1arc puis retour4calques/3arcs après3s, avec pool
Canvas et absence de timer inchangés. Aucun code applicatif PRESENCE modifié.
