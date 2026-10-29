# LOT 7 — stabilité et performances

Branche `feat/jalon-2-voice-presence`, référence initiale `19c003a`.
Demande complète : [LOT-7-SPEC.md](LOT-7-SPEC.md). Le rendu GPU 3.1 et
les lots 4/5 sont conservés. Aucun modèle ni moteur supplémentaire.

## 7A — audit initial

L'architecture conserve Tk/SQLite dans le parent, l'inférence et les appareils
audio dans des processus `spawn` distincts, et OpenGL dans sa fenêtre/processus
isolé. Les DOCX d'origine imposent local-first, interruption, traçabilité et
permissions externes au LLM ; ce lot n'ajoute aucune capacité système.

| Composant | Bornes et fréquence existantes | Observation |
| --- | --- | --- |
| COMMAND OS | boucle existante 40 ms ; pas de timer HUD supplémentaire | HUD inchangé au repos, au plus 1 projection/s pour les durées visibles |
| Ollama | IPC 128 événements, un worker ; HTTP loopback | le `spawn` échoué n'est pas nettoyé transactionnellement |
| Capture | PCM 64 blocs, événements 128, commandes 8 | un STT actif + un dernier segment en attente |
| Lecture | phrases/événements visuels/fins bornés à 64 | profils, commandes et échéances PCM réutilisés |
| GPU intégré | images 1 + dernière locale, événements 16, paquet 128 Kio | parent 50 ms, snapshots ≤25 Hz, dessin indépendant ≤60 FPS |
| Rendu GPU | ≤8 294 400 pixels, dimension ≤4096 ; atlas ≤16 Mio, 12 polices | VSync/gouverneur et profils existants, aucune nécessité de changer l'art |
| Cognitive HUD | 64 événements, TTL paresseux 900 s | aucun texte privé ni PCM dans ce journal |
| SQLite | WAL, index `messages_session`, FTS5 en fin de réponse | sauvegardes explicitement fermées ; pas de nouvel index nécessaire |

Défauts et décisions, établis avant correction :

| Constat démontré | Traitement prévu |
| --- | --- |
| `context_records()` lit `SELECT *`, dont le JSON de provenance ensuite jeté | 7B : projection des seules colonnes nécessaires, mêmes paires/statuts et originaux |
| échec `Process.start()` suivi de `stop()` : tentative de `join()` sur processus jamais démarré | 7C : rollback et fermeture des files, réessai explicite possible |
| `_stop_gpu()` perd sa référence avant confirmation de fermeture | 7C : conserver la propriété, empêcher un deuxième enfant si l'arrêt échoue |
| lot d'événements GPU encore parcouru après changement de session | 7C : arrêter le lot devenu obsolète |
| erreurs `renderer.release_errors` ignorées dans le processus intégré | 7C : propager les erreurs de nettoyage existantes |
| échec d'initialisation App : connexion Store conservée jusqu'au ramasse-miettes | 7C : fermeture explicite, données conservées |
| déconnexion micro pendant STT bloqué : `ThreadPoolExecutor.__exit__(wait=True)` retarde fermeture et diagnostic | 7D : fermer/signaler immédiatement, annuler le travail en attente ; processus parent toujours responsable de l'arrêt borné |

Référence SQLite synthétique exploratoire : 400 tours/800 messages, 2 048
caractères et 9 530 octets de métadonnées/message, cache chaud, 20 répétitions.
Lecture actuelle médiane 8,266 ms, pic `tracemalloc` 9 767 456 octets ; candidat
à projection 2,794 ms / 1 991 596 octets, résultat strictement égal. Ces chiffres
mesurent la lecture de contexte seule, pas une réponse Ollama ni la RAM globale.
La mesure reproductible 7B devra confirmer ce résultat.

Modifications rejetées : nouvel index SQLite (l'index existant est utilisé),
réduction des budgets/contextes, baisse des profils graphiques, nouveau moteur
vocal ou shader. Reparser les paramètres GPU coûte environ 30 µs/boucle dans un
microtest : bénéfice trop faible pour une modification isolée. La pagination et
le classement du contexte restent des pistes si un grand historique mesuré les
justifie ; aucune refonte préventive.

## Validation et limites

Les benchmarks doivent distinguer processus parent/enfant, GPU global et
ressources GL demandées, cache froid/chaud, modèle/contexte, résolution/DPI,
périphériques audio et mesures/estimations. Un délai vers PCM/DAC ne mesure pas
la sortie acoustique Bluetooth. Sans compteur disponible, la valeur reste
absente avec une raison ; aucun zéro artificiel.

Le benchmark réutilise les métriques Ollama, les diagnostics vocaux, F9 et les
outils GPU existants. Les scénarios interactifs exigent les modèles déjà locaux
et une action explicite ; aucun téléchargement et aucune conversation/PCM dans
les exports de mesure par défaut. Les essais cloud logiciels ne valident ni le
microphone physique ni la concurrence RTX 3070 + Ollama + voix.

Les étapes suivantes compléteront ce document avec leurs résultats et commits.

### Livraison 7A

[Guide des commandes](LOT-7-BENCHMARKS.md) et
[référence brute](benchmarks/lot7/runtime-baseline.json) : six vrais processus
frais importés depuis `19c003a`, 1 s de préchauffage + 2 s mesurées chacun,
Linux/Tk/Mesa logiciel. CPU du parent : repos masqué 0,88 % d'un cœur,
COMMAND OS 0,94 %, Canvas THINKING synthétique 2,27 %. Dernière fenêtre de
mesure GPU : Éco 15,00 FPS, Équilibré 50,90, Cinématique 52,29 ; résolution
intégrée 960 × 640. Mesures du processus GPU séparées dans le JSON. Ces essais
courts ne démontrent ni gain statistique, ni consommation électrique, ni
performances RTX, ni fonctionnement d'un microphone/modèle.

Le nouvel outil opt-in ne change pas la boucle de production. Douze scénarios,
exports JSON/CSV/Markdown, comparaison contrôlée, arrêt borné de l'arbre d'essai,
aucun texte/PCM dans les exports. Les parcours interactifs incomplets ne sont
pas des succès. 11 tests ciblés réussis en 1,954 s ; référence de non-régression
initiale : 120 exécutés, 119 réussis, 1 modèle réel ignoré, 29,293 s.

## 7B — lecture de contexte SQLite

`Store.context_records()` projette maintenant uniquement les six colonnes
requises, consomme les mêmes paires consécutives et ferme son curseur. Aucune
modification de contenu, budget, schéma, FTS, réglage ou sauvegarde.

Comparaison reproductible :

```powershell
python scripts/benchmark_context_storage.py --output contexte-comparaison.json
```

[Résultats bruts](benchmarks/lot7-context.json), source initiale vérifiée par
AST contre `19c003a`, mêmes 800 messages synthétiques et lectures alternées
sur le même cache chaud : médiane **8,324 → 3,695 ms** ; pic d'allocations
Python **9 767 520 → 1 991 596 octets** (−79,6 %). C'est une réduction du coût
de préparation des données, pas une promesse de débit Ollama ou de RAM globale.
Résultats exactement égaux, index existant utilisé, intégrité SQLite `ok`.
66 tests contexte/mémoire/provenance/stockage vocal réussis, dont paires
irrégulières, tous les statuts, Unicode et grosses métadonnées privées conservées
dans l'archive mais exclues de la lecture contextuelle.

## 7C — arrêt, erreurs et récupération

- Allocation/démarrage des workers Ollama et audio transactionnels : une erreur
  avant PID ferme les files et le processus non démarré, préserve l'exception et
  permet un nouvel essai. Un enfant encore vivant après `kill` reste possédé ;
  aucun deuxième worker ne peut être lancé à sa place.
- PRESENCE conserve aussi la session GPU si son arrêt échoue, rend l'erreur
  visible et laisse COMMAND OS accessible pour réessayer. L'application ne
  détruit pas son propriétaire avant confirmation des arrêts.
- Les événements d'une ancienne session ne sont plus consommés après une
  bascule. Les erreurs différées de libération GL et l'acquittement de fermeture
  remontent jusqu'au diagnostic et aux probes de compilation : une première
  image ne suffit plus à déclarer le nettoyage réussi.
- Défaut supplémentaire reproduit : trois arrêts forcés après paquet graphique
  de ~96 Kio laissaient **trois `QueueFeederThread`** bloqués malgré la mort des
  enfants. Le transport libère maintenant ses pipes après confirmation de leur
  mort et attend son feeder dans le délai d'arrêt existant : **zéro sur trois**
  dans le même essai borné. Les erreurs de transport en fonctionnement sont
  signalées ; seuls les paquets visuels devenus inutiles à l'arrêt sont abandonnés.
- Le démarrage échoué ferme explicitement SQLite et expose le type d'erreur ;
  archive, fragment récupérable et préférences invalides sont préservés pour
  diagnostic. L'outil de benchmark ferme aussi sa base jetable en cas d'échec
  et applique la vraie préférence typographique `conversation`.

Validation : 18 tests worker/audio/démarrage, dont dix cycles réels de chaque
worker ; 49 tests transport GPU/host/smoke avec EGL réel ; 12 tests de l'outil,
dont rendu Tk de la taille de police et erreur de nettoyage Windows simulée.
Douze cycles de bascule gardent les mêmes instances audio/conversation. Aucun
test ne prouve une absence universelle de fuite mémoire ; les fermetures forcées
ou non acquittées restent explicitement distinctes d'un nettoyage GL confirmé.
Les connexions privées de `multiprocessing.Queue` sont fermées seulement après
la mort de l'enfant : vérification Windows/Tk 8.6 requise en plus de Linux.

## 7D — réactivité des erreurs de capture

Le contexte `ThreadPoolExecutor` attendait la fin de Whisper avant de fermer le
microphone et d'exposer une erreur de capture/VAD. La sortie ferme maintenant le
micro puis signale l'erreur sans cette attente ; les tâches en attente sont
annulées. Un appel STT natif déjà engagé ne peut pas être interrompu comme une
tâche Python : le parent reçoit l'erreur et conserve l'arrêt borné du processus.
Aucun texte tardif ni deuxième tour en attente n'est envoyé à Ollama.

[Comparatif et protocole](benchmarks/lot7/capture-recovery.json) : cinq essais
par version, STT volontairement retenu jusqu'à libération du test (100 ms côté
référence). Avant : erreur et fermeture attendent cette libération ; après :
elles la précèdent dans les cinq essais. Coût de boucle synthétique médian
100,368 → 0,013 ms pour le diagnostic, **pas** une mesure de latence Whisper,
acoustique ou Windows. Trois régressions testent déconnexion, panne VAD, tour
en attente et arrêt d'un vrai enfant dont le STT est bloqué.

135 tests ciblés voix/commandes/capture/HUD réussis en 24,715 s ; 24 tests
supplémentaires Tk 8.6 en 8,225 s. Les seuils VAD, durées de silence, profils,
budgets C1, normalisation, PCM et direction artistique n'ont pas changé. Aucune
preuve de saccade ou latence de succès nécessitant de modifier Piper/Ollama dans
le cloud : pas de raccourcissement artificiel des réponses ni d'optimisation
spéculative de ce parcours. Confirmation GPU finale : 50 tests Tk 9/EGL et
23 tests Tk 8.6 réussis, y compris annulation de l'aperçu pendant panne.

## 7E — packaging et conservation des données

[Recette Windows/RTX](LOT-7-WINDOWS.md). Le build conserve les probes natifs
voix/Silero, démarrage sans Ollama/appareil et GPU source/EXE. Il ajoute une
archive synthétique préremplie utilisée successivement par les sources puis
deux démarrages du même EXE : comparaison exacte après **chaque** lancement,
préférences et champs inconnus, mémoire approuvée, FTS, intégrité et récupération
du fragment. Le vérificateur est en lecture seule pour ne pas masquer un défaut
de récupération. Rapport `diagnostics/update-data-<GUID>.json` dans l'artefact.
Seul le dossier synthétique réservé par le test est supprimé ensuite.

Huit tests réussis en 1,460 s, dont deux vrais démarrages source sur le même
profil et refus des altérations de chaque table/FTS. PowerShell et EXE non
exécutables ici : compilation et probes Windows confiés aux workflows du SHA
publié. Une CI verte n'établira ni la qualité acoustique ni le budget RTX sous
charge. Données/modèles hors EXE, binaire non signé, limites et procédure de
mise à jour dans le guide. Suite complète et bilan au SHA final en 7F.
