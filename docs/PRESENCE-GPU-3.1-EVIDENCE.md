# PRESENCE GPU3.1 — preuves et mesures

Les PNG proviennent de véritables framebuffers OpenGL, à leur dimension native. Aucun agrandissement logiciel, recadrage ou filtre de netteté n’est appliqué. Mesa/llvmpipe est un renderer logiciel : **validation RTX3070, microphone et Piper physiques en attente**.

## Phase A — résolution et cadence

Comparaison courte : processus neuf par cas, même scène THINKING t=4s, framebuffer physique1440×960, trois secondes mesurées après compilation et capture. Les sources renderer/shaders/adaptateur/config historiques sont figées depuis4ae4f71 ; les modules communs utilisent le code courant et leurs empreintes sont consignées. Il ne s’agit pas d’un benchmark historique complet de JARVIS.

Les FPS ci-dessous comptent les frames réellement dessinées et achevées via EGL, sans moniteur ni swapchain. Le plafond de mesure vient du profil figé :30FPS ancien Équilibré,60FPS nouveau Équilibré/Cinématique. Le vieux plafond45FPS du helper a été supprimé. Aucun FPS d’export vidéo n’intervient.

| Version / profil / échelle | Interne | FPS EGL | Rendu P95(ms) | RAM moyenne(Mio) |
|---|---:|---:|---:|---:|
| 3.0-Équilibré-100% | 1080×720 | 29.22 | 37.07 | 111.2 |
| 3.0-Cinématique-100% | 1440×960 | 24.26 | 52.41 | 116.7 |
| 3.1-Équilibré-100% | 1440×960 | 25.01 | 52.82 | 116.6 |
| 3.1-Équilibré-125 | 1800×1200 | 17.98 | 72.49 | 137.5 |
| 3.1-Équilibré-150 | 2160×1440 | 13.50 | 85.49 | 149.3 |
| 3.1-Cinématique-100% | 1440×960 | 27.12 | 46.81 | 116.6 |
| 3.1-Cinématique-125 | 1800×1200 | 17.63 | 69.25 | 137.6 |
| 3.1-Cinématique-150 | 2160×1440 | 12.76 | 88.52 | 149.2 |

**60FPS ne sont pas atteints sur ce Mesa logiciel à1440×960.** La nouvelle version dessine davantage de pixels en Équilibré :1,38M contre0,78M. Le supersampling125/150% augmente encore ce coût. Ces relevés courts ne prouvent ni gain statistique ni performances RTX. Le processus logiciel utilise environ quatre cœurs ; CPU/RAM/P50/P95/P99/frames longues et ressources demandées restent dans les rapports bruts. VRAM physique, watts, impact Ollama et latence Piper ne sont pas mesurés.

Les huit [rapports bruts et le manifeste SHA256](benchmarks/presence-gpu31-A/comparison.json) distinguent dimensions physiques, internes, bloom, cadence cible, comptage de frames et portée de mesure.

- Netteté native Équilibré : [3.0](assets/presence-gpu31-A/before-balanced-native.png) / [3.1](assets/presence-gpu31-A/after-balanced-native.png), PNG1440×960 identiques en dimensions.
- Supersampling natif : [125%](assets/presence-gpu31-A/after-balanced-125.png) / [150%](assets/presence-gpu31-A/after-balanced-150.png).
- Texte HiDPI : [ancien HUD4K](assets/presence-gpu31-A/presence-gpu31-hud-4k-before.png) / [nouveau HUD4K](assets/presence-gpu31-A/presence-gpu31-hud-4k-after.png), véritables PNG3840×2160 à DPI200%.

Le HUD historique rasterisait un atlas1920×172 avant de l’étirer ; le nouveau utilise3840×344, pixels physiques natifs. La [sonde HUD](assets/presence-gpu31-A/presence-gpu31-hud-4k.json) donne sources, atlas, bornes et empreintes. Cette capture isole le texte sur fond noir, sans noyau ni audio.

Reproduction, avec dépendances GPU/EGL disponibles, dans un dossier de sortie neuf :

```bash
python scripts/compare_presence_gpu.py --revision 4ae4f71 --historical-scene --case balanced --width 1440 --height 960 --seconds 3 --render-scale 100 --output /tmp/jarvis-avant-neuf
python scripts/compare_presence_gpu.py --revision 5cd8866 --historical-scene --case balanced --width 1440 --height 960 --seconds 3 --render-scale 125 --output /tmp/jarvis-apres-neuf
python scripts/capture_presence_integration.py --hud-comparison --output /tmp/jarvis-hud-neuf
```

La comparaison historique nécessite ce commit dans l’historique Git. Les dossiers existants sont refusés. Les benchmarks ne lancent aucun modèle ni appareil audio.

## Phases C et D — aura, états et commandes directes

Les nouvelles captures suivent le véritable chemin `IntegratedPresence.update_event`
→ snapshot validé → `GpuRenderer` + `GpuHud` OpenGL/EGL. Les événements d'écoute et
de parole utilisent des blocs **PCM synthétiques 16 kHz explicitement identifiés**,
avec des syllabes et des silences, analysés par le vrai composant trois bandes.
Le transport graphique de capture et la frontière audio sont des doubles : aucun
microphone, Piper, Whisper ou Ollama n'est lancé. Les vidéos n'ont pas de son.

- [Scénario complet, 12 s / 360 images](assets/presence-gpu31-CD/presence-gpu31-demo.mp4) : repos, micro ouvert sans parole, réception VAD, réflexion, parole rayonnante, sourire gravé, interruption et retour au repos.
- [LISTENING, 74 images](assets/presence-gpu31-CD/presence-gpu31-listening.mp4), [THINKING, 59 images](assets/presence-gpu31-CD/presence-gpu31-thinking.mp4), [SPEAKING et expression, 130 images](assets/presence-gpu31-CD/presence-gpu31-speaking.mp4).
- [Basculement 2D → 2.5D → 2D, 3 s / 90 images](assets/presence-gpu31-CD/presence-gpu31-toggle.mp4) : véritables frames Tk et OpenGL. Le bouton Tk est invoqué ; le clic HUD est résolu par `hit_test`, validé, puis transmis au même gestionnaire du parent via le double de transport. Les vrais clics GLFW et le vrai processus IPC ont été vérifiés séparément par le test XTest natif de la phase B.
- Contrôles visibles dans [Canvas](assets/presence-gpu31-CD/presence-gpu31-toggle-canvas.png) et le [HUD GPU](assets/presence-gpu31-CD/presence-gpu31-toggle-gpu.png), puis [retour Canvas](assets/presence-gpu31-CD/presence-gpu31-toggle-canvas-return.png).
- Images natives : [réception](assets/presence-gpu31-CD/presence-gpu31-écoute.png), [réflexion](assets/presence-gpu31-CD/presence-gpu31-thinking.png), [parole](assets/presence-gpu31-CD/presence-gpu31-speaking.png), [sourire](assets/presence-gpu31-CD/presence-gpu31-smile.png), [interruption](assets/presence-gpu31-CD/presence-gpu31-interruption.png), [repos](assets/presence-gpu31-CD/presence-gpu31-idle.png).
- Studio réel : [échelle de rendu](assets/presence-gpu31-CD/presence-gpu31-studio-scale.png) et [référence artistique 3.0 chargée dans le brouillon](assets/presence-gpu31-CD/presence-gpu31-studio-reference.png). Ces captures n'appliquent aucune préférence à une base utilisateur.

Toutes les vidéos sont encodées à **30 images/s**, à 960 × 640, sans
redimensionnement des frames capturées. Cette cadence d'export est une horloge
de démonstration hors ligne ; **elle ne mesure ni 30 ni 60 FPS en usage réel**.
Les durées des clips sont arrondies aux frontières des images (environ 2,47 s,
1,97 s et 4,33 s). Les performances live restent celles des mesures distinctes.

Le script vérifie qu'un sourire à plus de 95 % atteint le renderer, qu'une
enveloppe vocale expressive dépasse 0,1 pendant le PCM et qu'une interruption
ne garde ni expression ni énergie sortante. Le pic d'enveloppe observé est 0,573.
Le parcours des commandes atteint bien GPU puis Canvas. Ces assertions valident
le routage logiciel et ne remplacent pas l'appréciation visuelle de l'utilisateur.

[Chronologie, valeurs PCM/états/enveloppes, mesures et SHA-256](assets/presence-gpu31-CD/presence-integrated-evidence.json)
identifient les onze sources et tous les artefacts. Tous les hashes ont été
revérifiés après la capture finale.

Sur ce Linux/Tk 9/Mesa llvmpipe, la capture GL + HUD + `context.finish` coûte
28,44 ms en moyenne et 49,33 ms au P95, lecture des pixels et encodage exclus.
Le processus complet de capture utilise 39,03 s CPU sur 18,09 s écoulées,
avec rendu logiciel multithread, interface et pipe vidéo. Son pic RSS atteint
164 368 384 octets ; les ressources propres renderer/HUD sont estimées à
8 041 344 octets, hors framebuffer de capture et coûts du pilote.
Ces valeurs ne constituent pas un benchmark du JARVIS quotidien ; la VRAM
physique, les watts, l'impact Ollama et la latence acoustique Piper ne sont pas
mesurés. **Validation matérielle Windows/RTX 3070 en attente.**

Reproduction avec Tk/X11, NumPy, ffmpeg et les dépendances GPU disponibles :

```bash
DISPLAY=:98 MESA_SHADER_CACHE_DIR=/tmp/jarvis-polish-cache/mesa \
  /tmp/jarvis-polish-env/bin/python scripts/capture_presence_integration.py \
  --gpu31 --fps 30 --output /tmp/jarvis-gpu31-capture-neuve
```

Le dossier doit être neuf : aucune preuve antérieure n'est écrasée.
