# LOT 7 — comparaison logicielle avant/après

Référence `19c003a` ; code final `8b89101` + correctif de fermeture GPU identifié par SHA-256 dans `runtime-final.json`. Les sources mesurées sont des snapshots exacts sans `__pycache__`, avec écriture de bytecode désactivée. Aucun gain global n’est revendiqué.

Linux/Python 3.12.14/Tk 9.0.4, Xorg virtuel, Mesa llvmpipe logiciel. **Un seul échantillon de 2 s par cas**, préchauffage UI de 1 s, même ordre. Les caches OS/shaders ne sont pas purgés et restent indiqués « non spécifiés ». Pas de modèle ni périphérique physique ; THINKING explicitement synthétique dans Canvas/GPU.

CPU = processus Tk principal, pourcentage d’un cœur ; RSS en Mio. Initialisation = imports enfant + SQLite temporaire + Tk/App, pas le chargement complet du renderer GPU ni le lancement OS. Fermeture = retour de App.close.

| Scénario | CPU avant → après (%) | RSS avant → après (Mio) | Initialisation avant → après (ms) | Fermeture avant → après (ms) |
| --- | ---: | ---: | ---: | ---: |
| idle | 0.878 → 0.893 | 40.08 → 40.02 | 443.0 → 462.0 | 2.8 → 3.2 |
| command | 0.940 → 0.824 | 40.07 → 40.16 | 390.1 → 427.7 | 4.4 → 4.2 |
| canvas | 2.272 → 2.259 | 40.10 → 40.03 | 506.3 → 527.7 | 10.2 → 12.9 |
| gpu-eco | 2.661 → 2.696 | 40.40 → 40.44 | 512.6 → 540.5 | 81.2 → 55.5 |
| gpu-balanced | 4.491 → 4.541 | 40.50 → 40.45 | 559.5 → 557.1 | 64.4 → 34.3 |
| gpu-cinematic | 4.122 → 3.943 | 40.50 → 40.45 | 519.4 → 472.1 | 34.5 → 32.5 |

Les chiffres GPU suivants concernent **les dernières fenêtres de heartbeat échantillonnées**, environ 0,5 s chacune. Ils ne sont pas des percentiles regroupés de l’essai entier. Les différences positives/négatives d’un court échantillon logiciel ne prouvent ni amélioration ni régression sur RTX.

| Profil GPU | FPS dessinés avant → après | Intervalle P95 avant → après (ms) | Intervalle P99 avant → après (ms) | CPU renderer avant → après (%) | RSS renderer avant → après (Mio) |
| --- | ---: | ---: | ---: | ---: | ---: |
| gpu-eco | 15.00 → 15.00 | 67.17 → 67.44 | 67.17 → 67.44 | 98.5 → 117.7 | 134.57 → 104.77 |
| gpu-balanced | 50.90 → 46.52 | 26.81 → 29.19 | 29.25 → 29.74 | 381.4 → 378.4 | 104.96 → 104.87 |
| gpu-cinematic | 52.29 → 53.68 | 25.38 → 24.09 | 26.60 → 24.43 | 393.1 → 394.8 | 104.71 → 104.87 |

Les six essais finaux sont complets, sans erreur de callback. Résolution GPU physique/interne 960 × 640, échelle effective 1, adaptation 0 dans les fenêtres comparées ; géométrie/shaders non modifiés. Les allocations graphiques demandées restent exposées dans les rapports bruts ; elles ne représentent pas la VRAM physique.

Le benchmark a détecté une erreur réelle de fermeture introduite pendant 7C : double fermeture concurrente du lecteur de file par le parent et le feeder (`OSError: [Errno 9] Bad file descriptor`), puis nouvelle tentative sur un objet Process déjà fermé. Le correctif ordonne les fermetures et conserve un état de reprise cohérent. Trois cycles de reproduction avec le correctif, puis les six essais finaux, se sont terminés normalement. Cela ne démontre pas l’absence de fuite sur longue durée.

Le premier essai final utilisant le checkout avec bytecode préexistant a été écarté pour biais méthodologique. Un second essai a révélé le défaut de fermeture et a été arrêté. Seule la campagne finale corrigée est publiée comme comparaison.

Mesures indisponibles ici : VRAM physique attribuable, watts, RTX 3070 avec Ollama/Whisper/Piper simultanés, TTFT et STT réels, latence acoustique/Bluetooth, DPI multiécran et périphériques physiques. **Validation matérielle en attente.** Les commandes sont dans `docs/LOT-7-BENCHMARKS.md`.

Sources brutes : [avant](runtime-baseline.json), [après](runtime-final.json). Les SHA-256 des fichiers mesurés font foi ; le dernier correctif GPU n’était pas encore commité lors de la capture et est livré avec ce rapport.
