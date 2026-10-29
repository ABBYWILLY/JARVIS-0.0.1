# Cognitive HUD 1.0 — preuves et mesures

Les preuves utilisent les composants de production : propriétaire cognitif de
l’application, PRESENCE, paquet validé, `GpuRenderer` et `GpuHud`. Le scénario
injecte explicitement ses états et son PCM synthétique ; aucun microphone,
modèle Whisper/Piper/Ollama, réseau ou archive utilisateur n’est ouvert.
Le stockage temporaire du scénario est supprimé après capture.

- [Démonstration des états — MP4, 13 s](assets/cognitive-hud-1.0/cognitive-hud-demo.mp4).
- [GPU avec HUD](assets/cognitive-hud-1.0/gpu-thinking-hud-on.png) et
  [sans HUD cognitif](assets/cognitive-hud-1.0/gpu-thinking-hud-off.png),
  même image réelle à960×640 : tous les pixels hors bande de titre sont identiques.
- [Mini GPU](assets/cognitive-hud-1.0/gpu-mini-hud.png),
  [Canvas](assets/cognitive-hud-1.0/canvas-thinking-hud.png) et
  [Mini Canvas](assets/cognitive-hud-1.0/canvas-mini-hud.png).
- [Sélection Rich Text et menu des sept actions](assets/cognitive-hud-1.0/command-os-selection-menu.png),
  [trace de lecture ciblée](assets/cognitive-hud-1.0/selection-actions-trace.json) et
  [inspecteur de provenance](assets/cognitive-hud-1.0/context-inspector-demo.png).
  Le vrai gestionnaire Lire transmet le passage vérifié à un double audio qui
  enregistre les demandes sans produire de son ; zéro appel Ollama et zéro
  ouverture micro. Le contexte de démonstration est préparé, jamais envoyé.
  Les instructions affichées sont synthétiques et non personnelles.
- [Manifestes, traces et benchmark OpenGL](assets/cognitive-hud-1.0/cognitive-hud-evidence.json) :
  hashes des sources et artefacts, dimensions natives, événements injectés,
  identité du renderer, CPU et mémoire du processus de capture.
- [Mesures App/Tk au repos](benchmarks/cognitive-hud-idle.json) : neuf processus
  frais, référence1985a99 / HUD minimal / HUD désactivé, trois échantillons
  de2s après0,5s de chauffe.

La vidéo contient156 images exportées à12i/s. Cette cadence d’encodage ne mesure
pas les FPS réels de présentation. L’interruption et les états d’erreur sont
des événements de démonstration, pas une recette matérielle.

Le test automatique du HUD EGL vérifie que le titre est la seule région modifiée,
que le centre et les sous-titres restent inchangés, que l’atlas reste identique
en taille et que les images inchangées ne sont pas téléversées de nouveau.
Les contrôles Canvas sont testés à100/200 % de DPI et en Mini-PRESENCE ; les
fenêtres cachées ne créent aucun nouveau callback ou paquet cognitif GPU.

## Reproduire les mesures

Dans un environnement de développement avec les dépendances GPU optionnelles,
Tk, EGL et ffmpeg disponibles, depuis le dépôt :

```bash
python scripts/capture_cognitive_hud.py --output NOUVEAU_DOSSIER --fps 12 --benchmark
python scripts/benchmark_cognitive_idle.py --output NOUVEAU_RAPPORT.json --seconds 2 --repetitions 3
```

Sous Linux sans écran, définir `DISPLAY` vers un serveur X de test. La référence
Git1985a99 doit être disponible pour les comparaisons ; les outils n’écrasent
aucun fichier existant et ne modifient aucune branche. La capture GPU demande
EGL : elle ne remplace pas l’essai GLFW natif du PC Windows.

Le benchmark OpenGL conserve la même sphère THINKING, les mêmes shaders et les
mêmes dimensions. Il sépare le HUD historique, le nouveau HUD désactivé, le
HUD activé avec titre en cache et un stress où le titre change à chaque frame.
Ce dernier est volontairement plus coûteux que les mises à jour de durée à1Hz
de l’application. Les temps incluent le rendu réel et `context.finish`, mais
pas lecture de framebuffer, encodage, VSync ou attente d’un écran.

Le benchmark au repos lance des processus App/Tk réels et SQLite temporaires,
avec la fenêtre principale visible, PRESENCE fermée et audio désactivé. Après
0,5s de chauffe, il observe CPU, RSS Linux disponible et le nombre de callbacks
du poll existant à25Hz. Aucun sondage supplémentaire n’est ajouté au produit.

Mesures finales Linux/Python3.12/Mesa llvmpipe (échantillons courts) :

| Cas | CPU au repos sur2s, médiane | RSS du processus, médiane | Polls existants |
| --- | ---: | ---: | ---: |
| Référence1985a99 | 14,129ms | 35,680Mo | 50 |
| HUD minimal | 13,909ms | 35,918Mo | 49 |
| HUD désactivé | 12,988ms | 35,926Mo | 49 |

Les empreintes du code sont consignées par processus. Ces mesures au repos
précèdent les dernières corrections de détails inactifs dans ce scénario
(PRESENCE et inspecteur fermés, audio désactivé) ; elles ne comparent pas ces parcours actifs.

À960×640 avec la même sphère THINKING, médiane des moyennes de trois séquences
de40frames : référence17,27ms, HUD désactivé18,23ms, activé en cache18,45ms,
titre changé à chaque frame22,24ms. Ces petites variations ne démontrent pas
un gain significatif. L’atlas HUD reste à660480octets dans tous les cas.
La capture entière consomme un pic RSS de168116224octets ; son rendu réel
GL+HUD+`finish` mesure21,326ms en moyenne, P9529,910ms. Ces données incluent un
processus de preuve et ses bibliothèques, pas un surcoût RAM mesuré de JARVIS.

Les échantillons courts du cloud Mesa sont sensibles à la charge et aux caches.
La mémoire RSS concerne tout le processus, pas le seul HUD. Les estimations
d’allocations OpenGL propres au renderer ne sont pas la VRAM physique. Aucun
gain matériel significatif, impact TTFT/Piper, wattage ou performance RTX3070
combinée à Ollama et à la voix ne se déduit de ces données.

La validation acoustique et les mesures combinées sur Windows restent à effectuer.
