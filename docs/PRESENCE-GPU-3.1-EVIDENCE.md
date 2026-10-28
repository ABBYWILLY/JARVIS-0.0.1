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
python scripts/compare_presence_gpu.py --historical-scene --case balanced --width 1440 --height 960 --seconds 3 --render-scale 125 --output /tmp/jarvis-apres-neuf
python scripts/capture_presence_integration.py --hud-comparison --output /tmp/jarvis-hud-neuf
```

La comparaison historique nécessite ce commit dans l’historique Git. Les dossiers existants sont refusés. Les benchmarks ne lancent aucun modèle ni appareil audio.
