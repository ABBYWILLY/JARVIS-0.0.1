# LOT 7 — mesures reproductibles

L'outil facultatif utilise le véritable `App`, SQLite temporaire, le renderer
Canvas/GPU intégré et les événements vocaux/Ollama existants. Il n'ajoute aucun
échantillonnage à JARVIS hors de sa commande explicite. Aucun modèle n'est
téléchargé ; aucune conversation, instruction système, transcription ou PCM
n'apparaît dans les exports. Le profil personnel et ses sauvegardes ne sont pas
ouverts. Les échanges d'un essai restent uniquement dans son SQLite temporaire,
supprimé à la sortie normale. Ne pas utiliser de contenu sensible pour la recette.

Depuis le dépôt et son environnement Python installé :

```powershell
python -m jarvis.runtime_benchmark --scenario command --seconds 30 --output mesures-commande-avant
python -m jarvis.runtime_benchmark --scenario command --seconds 30 --output mesures-commande-apres --baseline mesures-commande-avant/report.json
```

Chaque nouveau dossier contient `report.json`, `metrics.csv` et `summary.md`.
Un dossier existant est refusé avant démarrage d'un modèle ou périphérique.
Durée 1–3 600 secondes ; préchauffage UI `--warmup` 1 seconde par défaut. Le
superviseur arrête uniquement l'arbre de son essai si la durée + préchauffage +
30 secondes est dépassée. Un échec/interruption conserve un rapport d'erreur,
jamais une mesure inventée. Un essai incomplet retourne le code 2.

## Scénarios

| `--scenario` | Travail réellement exécuté et action attendue |
| --- | --- |
| `idle` | Application initialisée, fenêtre principale masquée ; sans micro/inférence |
| `command` | COMMAND OS visible au repos ; sans micro/inférence |
| `canvas` | PRESENCE Canvas visible ; repos par défaut |
| `gpu-eco` | PRESENCE GPU intégré, profil Éco |
| `gpu-balanced` | PRESENCE GPU intégré, profil Équilibré |
| `gpu-cinematic` | PRESENCE GPU intégré, profil Cinématique |
| `ollama` | COMMAND OS sans visualiseur GPU ; inventaire local puis question saisie par l'utilisateur |
| `ollama-gpu` | Même échange avec PRESENCE GPU ; même modèle/question/contexte pour comparaison |
| `piper` | Vraie préécoute française Piper, mêmes voix/vitesse/profil ; sans micro |
| `capture` | Cliquer « Activer l'écoute », accepter la permission habituelle puis parler ; sans modèle sélectionné, STT seul |
| `conversation` | Choisir le modèle déjà installé, activer explicitement le micro puis converser |
| `interruptions-toggle` | Conversation/lecture, interruption, Ctrl+F7 dans les deux sens ; actions humaines observées |

Pour mesurer une animation sans modèle ni micro :

```powershell
python -m jarvis.runtime_benchmark --scenario canvas --visual-state thinking --seconds 30 --output mesures-canvas
python -m jarvis.runtime_benchmark --scenario gpu-balanced --visual-state thinking --seconds 30 --output mesures-gpu
```

`THINKING` est **un état synthétique explicitement signalé**, avec le vrai
renderer et aucun faux signal audio. Le repos statique ne constitue pas une
mesure de fluidité animée. `--allow-software` autorise explicitement Mesa pour
le développement ; ce résultat ne valide pas une RTX. Le repli Canvas n'est
jamais compté comme un succès de scénario GPU.

## Modèles et préférences déjà présents

L'essai n'importe pas automatiquement les données privées. Un fichier JSON
explicite permet de reproduire les réglages nécessaires sans ouvrir l'archive :

```json
{
  "settings": {"model": "NOM_EXACT_INSTALLE", "context": 4096, "max_tokens": 1024},
  "preferences": {
    "voice": {
      "models_dir": "C:/chemin/vers/Jarvis/models",
      "input_device": "",
      "output_device": "",
      "voice": "fr_FR-tom-medium",
      "speech_profile": "normal",
      "acoustic_mode": "headphones"
    }
  }
}
```

Seules les familles existantes `voice`, `presence`, `presence_engine`,
`presence_gpu`, `conversation`, `cognitive_hud` sont acceptées. Le scénario impose
uniquement son moteur et son profil GPU dans la base temporaire. Rien n'écrase
les préférences personnelles. Les autres paramètres sont les valeurs normales
du programme ; aucun budget n'est abaissé pour embellir les chiffres.

```powershell
python -m jarvis.runtime_benchmark --scenario piper --preferences profil-mesure.json --seconds 30 --output mesures-piper
python -m jarvis.runtime_benchmark --scenario capture --preferences profil-mesure.json --seconds 90 --output mesures-stt
python -m jarvis.runtime_benchmark --scenario conversation --preferences profil-mesure.json --seconds 180 --output mesures-completes
python -m jarvis.runtime_benchmark --scenario ollama --model NOM_EXACT_INSTALLE --context 4096 --seconds 90 --output mesures-ollama
python -m jarvis.runtime_benchmark --scenario ollama-gpu --model NOM_EXACT_INSTALLE --context 4096 --seconds 90 --output mesures-ollama-gpu
python -m jarvis.runtime_benchmark --scenario interruptions-toggle --preferences profil-mesure.json --seconds 180 --output mesures-bascules
```

Le micro conserve le bouton/consentement existant. Le casque est nécessaire pour
tester l'interruption pendant lecture ; aucun AEC nouveau n'est prétendu. Pour
les deux essais Ollama, conserver la question, le modèle, le contexte, les
préférences et l'état de cache ; `--cache-state warm_observed` ou `cold_observed`
est une **annotation déclarée par l'opérateur**, pas une purge vérifiée du cache.
Un scénario sans ses événements attendus est marqué incomplet, avec des valeurs
absentes et leurs raisons. Il ne valide pas l'audio simplement parce que la
fenêtre s'est ouverte.

## Mesures, comparaison et limites

- CPU et RSS du processus Tk principal réellement lus ; le CPU peut dépasser
  100 % d'un cœur. Démarrage = imports enfant + Store + Tk/App ; lancement OS
  du processus superviseur exclu. Fermeture = retour de `App.close`.
- En GPU, métriques du processus renderer réutilisées depuis les heartbeats
  F9 : FPS dessinés, intervalles animés, P95/P99, CPU, RSS et résolution physique.
  Les 120 dernières fenêtres de heartbeat échantillonnées sont conservées ; les
  percentiles d'une fenêtre ne sont pas présentés comme ceux de tout l'essai.
- Si `nvidia-smi` fonctionne, charge/mémoire **globales du GPU identifié** ;
  aucune attribution arbitraire à JARVIS/Ollama. La VRAM physique propre à
  chaque processus et la puissance électrique restent indisponibles.
- Les durées Whisper, TTFT reçu, tokens/s et synthèse/PCM sont celles des
  événements existants, au maximum 512 tours et 7 200 échantillons. Les valeurs
  absentes ne deviennent jamais zéro. Le TTFT commence à l'envoi HTTP, pas au
  premier token interne du modèle. PCM/DAC estimé n'est pas la latence acoustique
  Bluetooth. CPU/RSS des enfants Whisper/Piper/Ollama non exposés : indisponibles.
- Les exports comportent modèle/contexte/budget, profil, taille/échelle Tk,
  voix/périphériques, cache déclaré, empreintes des réglages et sources. Ni le
  texte des instructions ni le chemin du dossier des modèles ne sont exportés.
- La comparaison refuse les différences de conditions observables : plateforme,
  Python/Tk, renderer, moteur réellement actif, dimensions/échelles, profils,
  voix, contexte, budgets, cache, durées/préchauffage et empreintes des réglages.
  Un delta brut sur un petit échantillon n'est pas une amélioration statistique.
  Comparer volontairement des profils différents reste possible en lisant les
  rapports côte à côte, sans un faux delta « toutes choses égales ».

`--width`, `--height` règlent COMMAND OS. La fenêtre GPU garde sa géométrie
intégrée normale, qui est mesurée séparément. `--tk-scaling` règle l'échelle Tk
de l'essai ; cela ne simule pas un changement physique de DPI multiécran.

Pour reprendre un checkout antérieur avec **le même outil actuel** :

```powershell
python -m jarvis.runtime_benchmark --source C:/checkout-reference --scenario command --seconds 30 --output reference
```

Le code réellement importé est vérifié contre le checkout demandé et ses SHA-256
sont exportés. Le benchmark logiciel initial LOT 7 figure dans
[`runtime-baseline.json`](benchmarks/lot7/runtime-baseline.json) : six processus
frais, source `19c003a`, courts essais Linux/Tk/Mesa, aucun micro ou modèle réel.
Le fichier groupé est accepté comme `--baseline` pour le scénario correspondant.
Les commandes locales existantes restent utilisables pour un corpus reproductible :

```powershell
python -m jarvis.inference_benchmark --model NOM_EXACT_INSTALLE --output ollama-corpus.jsonl
python -m jarvis.audio_diagnostics --models-dir C:/chemin/models --benchmark-tts
python -m jarvis.audio_diagnostics --models-dir C:/chemin/models --corpus manifeste-wav.json
```

Ces outils de corpus ont leur propre politique : l'outil STT affiche les
références/transcriptions locales pour calculer le WER. Leur sortie n'est pas
intégrée automatiquement dans le rapport anonyme de ce benchmark.

Windows/RTX 3070 + Ollama + voix simultanés, acoustique, Bluetooth, DPI physique,
déconnexions réelles et stabilité de longue durée : **validation matérielle en
attente**. Répéter les essais dans les deux ordres, plusieurs fois, avec les mêmes
conditions, sans tests ou compilation simultanés. Un court essai n'établit pas
« aucune fuite mémoire ».
