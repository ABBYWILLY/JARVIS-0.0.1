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
