# PRESENCE GPU — prototype autonome

Ce programme expérimental accompagne JARVIS, sans remplacer son moteur Canvas.
La direction artistique A+B est validée. Le guide [C+D](PRESENCE-GPU-3.0-CD.md)
décrit les états, le spectre, les nouveaux raccourcis et les preuves actuelles.
La revue artistique [GPU 3.0 — A + B](PRESENCE-GPU-3.0.md) conserve la référence
validée. L'utilisateur a autorisé C/D ; E/F fonctionnels restent différés.
La phase [GPU2.5D](UX-POLISH-PRESENCE-25D.md) ajoute perspective, occlusion et
matière énergétique légère. Ce document contient la comparaison réelle
avant/après, la vidéo et les mesures logicielles ; aucune validation RTX n'est
déduite de ces résultats.
L'audit préalable est dans [AUDIT-LOTS-3-6.md](AUDIT-LOTS-3-6.md) ; le choix
ModernGL/GLFW est expliqué dans [PRESENCE-GPU-FEASIBILITY.md](PRESENCE-GPU-FEASIBILITY.md).
Aucun modèle, compte cloud, pack graphique ou téléchargement automatique.
Captures et mesures disponibles : [PRESENCE-GPU-BENCHMARKS.md](PRESENCE-GPU-BENCHMARKS.md).

## Utilisation Windows sans Python

Depuis un run **vert** du workflow **PRESENCE GPU prototype**, télécharger
`Jarvis-Presence-GPU-Windows-x64-<commit>` et extraire le ZIP dans un nouveau
dossier. Lancer `JarvisPresenceGPU.exe`. Le `Jarvis.exe` habituel, les modèles,
paramètres et bases SQLite restent indépendants. Fermer la fenêtre PRESENCE Canvas
pendant cet aperçu pour conserver un seul visualiseur visible.

Pilote constructeur avec OpenGL3.3 requis, normalement fourni par le pilote
NVIDIA de la RTX3070. Aucun réglage OpenGL manuel ni DLL à copier. Une absence
de pilote produit un message ; une dépendance ou un shader défectueux est une
erreur, pas une compatibilité déclarée. Un renderer logiciel/inconnu est refusé
par défaut dans la fenêtre. `--allow-software` est réservé aux essais développeur
et peut consommer plusieurs cœurs CPU.

| Touche | Aperçu |
| --- | --- |
| I / V | Repos sphérique stable / option de ligne classique immobile |
| T | Contraction de 8 %, orbites multiaxiales accélérées, aura HDR |
| L / S | Écoute / parole ; sphère conservée, aura calme sans PCM |
| 1 / 2 / 3 | Sourire 😊 / affection ❤️ / rire 😂 gravés sur la sphère, puis dissipation |
| X | Annuler l'expression et suspendre l'ancien WAV ; L/S le reprennent explicitement |
| Q / C | Qualité Éco/Équilibré/Cinématique ; couleur de l'aperçu |
| R / Échap | Réduction du mouvement ; fermeture |

Le titre indique **APERÇU HORS LIGNE**. T n'annonce pas qu'Ollama réfléchit.
L/S ne capturent pas le micro et ne lancent pas Piper. `--wav fichier.wav` accepte
du PCM16 mono/stéréo jusqu'à192kHz : RMS et trois bandes fréquentielles viennent
du fichier enregistré, pas du matériel en direct. Le WAV n'est pas joué.
Le prototype n'est pas raccordé aux réponses vocales de production.
Le morphing de JARVIS actuel reste piloté par ses callbacks PCM, approximativement
par segment, avec exclusions code/citations et interruptions conservées.

## Diagnostic et mesures sur votre RTX3070

Dans PowerShell ouvert dans le dossier extrait, utiliser des noms de fichiers
neufs : les rapports et captures existants ne sont jamais écrasés.

```powershell
.\JarvisPresenceGPU.exe --probe --require-hardware --report .\gpu-sonde.json
.\JarvisPresenceGPU.exe --state thinking --quality balanced --seconds 30 --report .\gpu-equilibre.json --capture .\gpu-equilibre.png
.\JarvisPresenceGPU.exe --state thinking --quality cinematic --seconds 30 --report .\gpu-cinema.json
.\JarvisPresenceGPU.exe --state idle --seconds 30 --report .\gpu-repos.json
```

Le JSON contient FPS réellement dessinés sur la durée totale, médiane/p95 des
frames rendues, CPU processus moyen/pic échantillonné (100%=un cœur), RSS RAM
moyenne/pic, démarrage Python, résolution et qualité effective. La mesure de
construction Windows ajoute taille de l'EXE et durée parent complète de sa sonde,
incluant extraction PyInstaller, imports, rendu et fermeture.

VRAM : les octets demandés par les textures/buffers sont une **estimation**,
pas une mesure physique. `nvidia-smi`, s'il existe et identifie sans ambiguïté la
carte OpenGL, donne mémoire/utilisation **globales de la carte**, pas celles du
seul visualiseur ni une charge graphique distincte. Compteurs indisponibles,
temps GPU précis et latences IA/voix non mesurées restent `null` avec leur raison.
Les percentiles sont bornés aux6000dernières frames ; le compteur/FPS couvre
toute la durée, y compris les périodes cachées ou immobiles.

Dégradation automatique :12frames consécutives >50ms ou pression mémoire globale
>94% entraînent résolution divisée par deux, bloom/particules retirés et15FPS.
Q redemande un profil ; une nouvelle pression peut de nouveau le réduire.
`--no-adaptive` permet un essai fixe isolé. Minimiser suspend le rendu ; le repos
et THINKING avec mouvement réduit ne dessinent qu'à un changement utile.

Recette d'acceptation avant intégration :

1. Vérifier `hardware_reported` avec vendeur NVIDIA, puis les trois profils,
   portrait/paysage, plusieurs DPI, minimisation/restauration, fermeture et reprise.
2. Dans COMMAND OS, même modèle Qwen/budget/mode/question, relever TTFT et débit
   sans prototype puis avec, trois fois en alternant l'ordre. Les caches peuvent
   influencer les résultats ; aucune amélioration n'est présumée.
3. Même phrase micro et même réponse Piper : relever VAD/STT et chronométrages
   réels de JARVIS, interruptions/reprise, avec et sans aperçu. Aucun flux PCM
   supplémentaire n'est ouvert par ce prototype.
4. Observer mémoire GPU globale et les deux processus dans le Gestionnaire des
   tâches ; tester une session prolongée. Toute dégradation IA/voix bloque
   l'intégration, même si les FPS sont élevés.

## Architecture et décision actuelle

`GpuRenderer` possède initialisation, resize borné, qualité, rendu, capture et
shutdown ; shaders GLSL intégrés, bloom séparé au quart de chaque dimension.
`ReactorScene` réutilise **PresenceModel et MorphController** existants, sans
second cerveau d'état ni seconde bibliothèque de morphings. Aucun objet Python
par particule. L'entrée est séparée de COMMAND OS et n'ouvre ni SQLite ni audio.

**Intégration dans JARVIS différée** : le cloud n'a pas de GPU physique et ne peut
mesurer la coexistence RTX/Ollama/Whisper/Piper. Le moteur Canvas reste celui de
production. L'adaptateur commun Canvas/GPU, le raccordement aux vrais événements
et le repli automatique en production seront à réaliser après cette recette,
sans faire héberger un contexte OpenGL dans un Canvas Tk standard.

La CI Linux compile et exerce réellement les shaders via Mesa/EGL logiciel.
La CI Windows compile l'EXE et contrôle ses sondes source/gelée ; sur runner sans
pilote3.3, seul le refus explicite attendu est accepté et consigné. Un build vert
ne valide donc pas nécessairement le rendu matériel Windows/RTX.

Build développeur Windows reproductible :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-presence-gpu.ps1
```

`-RequireHardware` rend obligatoire une sonde matérielle réussie. Les licences
MIT/zlib et métadonnées des composants sont fournies avec l'artefact. Aucun
poids vocal ou modèle Ollama inclus ou supprimé.
