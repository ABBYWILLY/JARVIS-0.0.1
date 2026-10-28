# PRESENCE GPU 3.1

28 octobre 2026 · base `4ae4f71` · branche `feat/jalon-2-voice-presence`.
[Demande conservée](PRESENCE-GPU-3.1-SPEC.md). Direction artistique 3.0 conservée,
Canvas reste une alternative permanente. Aucun moteur vocal ou modèle ajouté.

## A — Cadence et netteté

Causes constatées dans le code : Équilibré plafonné à 30 images/s, rendu enfant
conditionné aux snapshots Tk, attente pouvant atteindre 100 ms, VSync désactivé ;
géométrie limitée à 720p/1080p puis agrandie ; atlas HUD limité à 1920 pixels.

Le processus graphique évalue désormais les horloges/orbites entre snapshots
horodatés, sans inventer de PCM, d'état ou d'expression. Le parent envoie ses
ancres à 25 Hz maximum ; l'analyse audio garde sa cadence indépendante.
Équilibré/Cinématique visent 60 dessins/s, Éco 15. Présentation VSync demandée,
échéances absolues sans attente active ni double attente après le swap.
Une interruption/expiration garde priorité ; un parent bloqué fige l'animation
après 350 ms. Repos et masquage ne dessinent pas continuellement.

Le rendu principal utilise les pixels physiques, avec Auto/100/125/150/200 %
et des plafonds de 8,29 Mpx/4096 par dimension. Le bloom reste indépendant.
Traits, particules et diffusion gardent leur taille apparente en supersampling.
Le HUD rasterise ses deux bandes en pixels natifs jusqu'à 4096, avec un budget
borné. Les changements de taille/DPI libèrent les ressources remplacées.

L'adaptation réduit successivement bloom, particules secondaires, puis seulement
en Auto la résolution principale à 75 % : surcharge durable 2 s, récupération
8 s, étapes espacées. Les préférences artistiques ne sont pas réécrites.

F9 affiche FPS dessinés et résolution réellement utilisée. Le diagnostic vocal
copiable contient les mesures du processus GPU : moyenne/P50/P95/P99, frames
longues, CPU/RAM, PID, framebuffer et facteur DPI. Le rafraîchissement du moniteur
et les appels swap sont distingués ; l'affichage physique à l'écran n'est pas
directement observable et la VRAM physique reste non mesurée.

Les mesures Mesa ne prouvent pas 60 FPS sur RTX, ni leur maintien avec Ollama.
L'objectif reste à vérifier sur le PC ; un FPS insuffisant ne bloque pas l'audio.

Phase A : **152 tests ciblés réussis** (Tk/OpenGL/EGL réel, 14,434 s), plus
smoke d'une fenêtre GLFW avec Mini/masquage/restauration/retour Canvas.
[Captures natives, rapports et limites](PRESENCE-GPU-3.1-EVIDENCE.md) : à
1440 × 960, Mesa logiciel atteint environ 25–27 FPS natifs, 18 FPS à 125 %,
13 FPS à 150 %. Le coût supérieur de la netteté native est explicite ; aucun
objectif 60 FPS matériel n'est déclaré atteint.

## Validation Windows — matériel en attente

1. Lancer JARVIS complet et choisir 2.5D ; F9 affiche les mesures réelles.
2. Comparer Équilibré/Cinématique avec puis sans Ollama : FPS/P95, TTFT, tokens/s,
   audio, CPU/RAM/VRAM du Gestionnaire des tâches. Conserver le même modèle.
3. Tester fenêtres réduites, plein écran et déplacement entre moniteurs/DPI.
   Comparer Auto/100/125/150 % ; lire la résolution effective et les plafonds.
4. Parler puis se taire, écouter Piper et interrompre : pas d'effet audio ancien,
   pas de perte de conversation. Revenir en Canvas et vérifier après redémarrage.

[Lancement et compilation Windows](PRESENCE-DUAL-ENGINE.md). Aucun essai sur votre
microphone, votre sortie Bluetooth ou votre RTX 3070 n'est revendiqué ici.
