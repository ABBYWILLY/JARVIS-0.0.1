# PRESENCE intégré : preuves hors ligne

28 octobre 2026. Ces captures montrent les vrais composants Tk et OpenGL.
Les états et le PCM sont **synthétiques et explicitement identifiés** ; aucun
microphone, Piper, Whisper ou Ollama n'est démarré. Validation matérielle en attente.

- [Démonstration MP4, 9 secondes](assets/presence-integrated-demo/presence-integrated-demo.mp4) : repos → écoute → THINKING → parole → sourire gravé → interruption → repos.
- [THINKING GPU](assets/presence-integrated-demo/presence-integrated-thinking.png) et [THINKING classique 2D](assets/presence-integrated-demo/presence-integrated-classic-thinking.png).
- [Expression terminale 😊](assets/presence-integrated-demo/presence-integrated-smile.png), [parole](assets/presence-integrated-demo/presence-integrated-speaking.png), [interruption](assets/presence-integrated-demo/presence-integrated-interruption.png), [repos](assets/presence-integrated-demo/presence-integrated-idle.png).
- [Sélecteur des deux moteurs](assets/presence-integrated-demo/presence-integrated-engine-selector.png).
- [Studio 2D](assets/presence-integrated-demo/presence-integrated-studio-2d.png) et [Studio GPU](assets/presence-integrated-demo/presence-integrated-studio-gpu.png).
- [Mesures, chronologie et SHA-256](assets/presence-integrated-demo/presence-integrated-evidence.json).

Le scénario appelle `IntegratedPresence.update_event`, `queue_expressions` et
`complete_segment`. Un double de transport retient le dernier snapshot validé ;
ce snapshot traverse ensuite le vrai `GpuRenderer` et `GpuHud`, comme dans le
processus enfant. Le script vérifie qu'un sourire pleinement visible arrive au
renderer et qu'une interruption l'annule. Le test des files/processus natifs
est distinct de cette preuve visuelle. La vidéo ne contient pas de piste sonore.

Environnement : Linux, Tk 9, Mesa 25 / llvmpipe LLVM 19, EGL, 960 × 640,
108 images encodées à 12 images/s. Rendu GL + HUD + synchronisation du contexte :
18,86 ms en moyenne, P95 27,89 ms ; lecture des pixels et encodage exclus.
Les ressources estimées propres au renderer/HUD occupent 8 041 344 octets,
hors framebuffer de capture. Le pic RSS du processus entier de capture est
162 557 952 octets. Le processus consomme 8,11 secondes CPU sur 3,75 secondes
écoulées, avec rendu logiciel parallèle, interface, captures et pipe vidéo.
Ces valeurs ne mesurent ni le JARVIS quotidien ni une RTX 3070. VRAM réelle,
impact Ollama et latence matérielle audio : non mesurés.

Reproduction Linux, avec les dépendances GPU facultatives, NumPy, ffmpeg, Tk et
un affichage X11 disponibles :

```bash
DISPLAY=:98 MESA_SHADER_CACHE_DIR=/tmp/jarvis-polish-cache/mesa \
  /tmp/jarvis-polish-env/bin/python scripts/capture_presence_integration.py \
  --output /tmp/jarvis-nouvelle-capture
```

Le dossier de sortie doit être nouveau : le script refuse tout écrasement.
Les sources exactes et artefacts sont identifiés par leurs empreintes dans le
JSON. Une réussite automatisée n'est pas une validation esthétique utilisateur.
