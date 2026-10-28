# PRESENCE — choix permanent 2D / 2.5D

28 octobre 2026, base `901f360`, branche `feat/jalon-2-voice-presence`.
Direction artistique A–D validée ; aucun changement d'Ollama, Whisper, SQLite
ou de voix. [Demande complète et additif prioritaire](PRESENCE-INTEGRATION-SPEC.md).

## Phase 1 — Contrats

- **Canvas est le moteur initial et une alternative permanente complète.**
  Les anciennes préférences `presence` conservent les réglages 2D et les valeurs
  véritablement communes (palette, sous-titres, réduction du mouvement).
- `presence_gpu` reçoit uniquement les réglages artistiques GPU validés.
  `presence_engine` conserve le choix, la décision automatique et une éventuelle
  panne expliquée. Toutes ces clés utilisent le même magasin SQLite existant,
  sans nouveau fichier de configuration. Les clés futures sont préservées.
- Une sélection automatique réussie est mémorisée. Une panne verrouille le
  nouvel essai jusqu'à une action explicite, tout en gardant le choix demandé.
  Pas de sondage GPU au démarrage lorsque Canvas est choisi.
- Le parent reste propriétaire de l'état conversationnel, du microphone, du
  PCM, des sous-titres et du contrôleur sémantique. Il transmet des snapshots
  complets, bornés et numérotés au processus graphique local.
- Un seul snapshot récent est retenu, au plus 16 notifications ; pas de canal
  cloud. Les horloges PCM et d'expression permettent de rejeter le périmé.
  Le processus enfant n'ouvre ni microphone ni synthétiseur.
- La fenêtre GLFW est créée cachée et n'apparaît qu'une fois prête et après
  retrait de Canvas. Le retour Canvas arrête d'abord l'ancien processus.
  Les données métier ne sont ni transférées ni réinitialisées au basculement.

Le choix d'une fenêtre GLFW contrôlée séparément évite d'insérer une deuxième
boucle native dans le thread Tk. Son HUD rend les commandes et sous-titres dans
la même fenêtre OpenGL ; aucune seconde fenêtre PRESENCE active. Pillow sera
une dépendance facultative GPU pour rasteriser le texte, pas un moteur graphique
obligatoire pour Canvas. Le matériel et l'accessibilité Windows restent à tester.

Contrats validés : **17 tests réussis** (préférences, configuration GPU et
protocole borné), sans ouverture de périphérique ni contexte graphique.
Les phases suivantes implémentent les paramètres, le processus, le Studio et
le raccordement réel ; ces contrats seuls ne constituent pas une intégration.

## Phase 2 — Personnalisation GPU

66 commandes numériques et trois profils utilisent le vrai renderer, sans
modifier les réglages Canvas. Les six essentiels sont présentés d'abord ;
sept sections, recherche et niveaux Personnaliser/Avancé donnent accès au reste.
Le Studio conserve un brouillon, Avant/Après, Restaurer, Appliquer et Annuler.
Le propriétaire PRESENCE fournit le canal d'aperçu et l'unique persistance SQLite ;
le raccordement de l'éditeur dans l'application est la phase 3.

74 tests configuration/Scene/GL réussis : effets réels des 66 commandes,
rayon/luminosité du halo indépendants en HDR, ressources bornées. Le Studio a
11 tests Tk/transactions/petites fenêtres/DPI simulés et le comparateur 7 tests.
Les valeurs par défaut conservent le style approuvé A–D. Aucun nouveau modèle.
La CI Windows est contrôlée après publication ; les essais RTX/micro/Piper
sur le PC restent en attente.

## Phase 3 — Intégration optionnelle

Centre de contrôle → PRESENCE → Moteur : Automatique, 2D classique — Canvas,
2.5D holographique — GPU. Le moteur actif et le motif d'un repli sont affichés.
Canvas reste choisi pour une configuration existante sans préférence de moteur.
Automatique mémorise sa décision ; une panne exige une nouvelle sélection GPU
ou « Réessayer ». Aucun sondage au démarrage en mode 2D.

Une seule fenêtre PRESENCE est visible. Le parent conserve le même modèle
conversationnel et les mêmes sous-titres/expressions. Le basculement nettoie le
processus graphique sans rouvrir le micro ni redémarrer Piper/Ollama. Les deux
Studios restent accessibles et leurs brouillons sont indépendants ; un aperçu
GPU indique son origine, est annulable et cède devant un événement réel.

13 tests d'intégration Tk/SQLite réussis, dont un vrai processus EGL et les
trois expressions terminales 😊 ❤️ 😂. Transport/HUD : 16 tests réussis,
incluant crash, blocage, files bornées, retour au calme et arrêt sans orphelin.
Les frontières audio des tests sont des doublures explicites, pas du matériel.

**Point de contrôle phase 3 :** états, RMS, sous-titres et morphing empruntent
le propriétaire existant ; les bandes spectrales du PCM Piper sont raccordées
dans le commit séparé de phase 4. À ce stade, aucune écoute matérielle GPU ni
mesure RTX n'est déclarée validée. Le build GPU intégré est la phase 5.

## Phase 4 — Événements audio et expressions

Le PCM du microphone existant alimente le même modèle RMS/VAD ; le renderer
n'ouvre aucun périphérique. Les blocs de sortie Piper rééchantillonnés alimentent
une analyse trois bandes hors callback audio et hors thread graphique, à 25 Hz
maximum. Chaque résultat porte l'offset et le nombre exact d'échantillons du
bloc : un calcul en retard n'est jamais réutilisé pour un autre bloc.

Les événements visuels conservent l'échéance `emitted_at + delay` PortAudio.
Il s'agit d'une estimation DAC, pas de la sortie acoustique Bluetooth ni d'un
alignement mot à mot. Les générations obsolètes sont rejetées et l'interruption
annule immédiatement expressions et énergie sortante. Les erreurs FFT restent
visibles dans le diagnostic et n'arrêtent pas la lecture.

Le choix de moteur active/désactive l'analyse via un booléen partagé, y compris
au milieu d'une phrase : aucun redémarrage Piper ni commande ajoutée au texte
à prononcer. Canvas et une fenêtre GPU masquée n'exigent pas cette analyse.
Les nouveaux tests couvrent blocs/DAC, annulation, reprise après erreur,
activation à chaud et processus spawn ; aucune voix artificielle n'est
présentée comme un essai Piper ou microphone physique.

## Phase 5 — Build et recette Windows

Suite locale Linux/Tk 9/EGL réel requis : **745 tests, 736 réussis, 9 ignorés**
en 93,544 s. Les tests ignorés nécessitent les dépendances audio natives ou un
modèle/matériel explicitement activé. Cette réussite ne remplace pas la CI.

[Captures, vidéo et mesures du vrai renderer](PRESENCE-INTEGRATED-DEMO.md).
Le scénario est hors ligne, explicitement synthétique. Il ne valide pas votre
microphone, les sorties Bluetooth, la voix Piper ou la RTX 3070.

Depuis PowerShell dans le dépôt, après mise à jour de la branche :

```powershell
git switch feat/jalon-2-voice-presence
git pull --ff-only
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt -r requirements-gpu.txt
.\.venv\Scripts\python.exe run.py
```

Les modèles vocaux et Ollama déjà installés sont réutilisés, sans téléchargement
automatique. Canvas fonctionne sans `requirements-gpu.txt`. Les erreurs GPU
replient vers Canvas avec un motif et un nouvel essai manuel.

Compilation des deux moteurs dans le même EXE :

```powershell
.\scripts\build-windows.ps1 -WithVoice -WithGpu
```

Résultat : `dist\jalon-2\Jarvis.exe`, empreinte SHA-256 et diagnostics.
Sans `-WithGpu`, le build Canvas reste possible. GitHub Actions « Windows
Jarvis » compile les deux moteurs, exécute la suite puis les smoke tests source
et EXE. La sonde distingue pilote absent, vrai rendu effectué et erreur de
packaging ; un pilote absent n'est jamais annoncé comme une frame réussie.
Les rapports JSON sont livrés dans l'artefact. Le prototype autonome reste
compilé séparément. Ni EXE ni PowerShell n'ont été exécutés sous ce Linux.

### À votre retour sur Windows 11 — validation matérielle en attente

1. Dans Centre de contrôle → PRESENCE, choisir 2D classique. Parler puis se
   taire : vérifier RMS réel, onde et transcription. Tester une réponse Piper.
2. Choisir 2.5D holographique. Vérifier le moteur actif, le RMS/VAD, THINKING,
   la voix et le halo. Le micro ne doit pas demander une nouvelle ouverture.
3. Pendant une lecture, basculer 2.5D → 2D → 2.5D. Vérifier continuité audio,
   conversation/historique conservés et une seule fenêtre PRESENCE visible.
4. Faire lire « Heureux de te revoir 😊 », « Je t'aime ❤️ », « C'est drôle 😂 » :
   traits gravés, sous-titres, puis arrêt/interruption sans expression résiduelle.
   Les symboles restent exclus des exemples techniques et blocs de code.
5. Ouvrir chaque Studio : aperçu, Avant/Après, Annuler puis Appliquer. Modifier
   halo rayon/lumière et taille des particules indépendamment. Redémarrer JARVIS
   et vérifier les deux configurations et le choix de moteur.
6. Tester Mini, fenêtre masquée, petites fenêtres et vos DPI. Vérifier clavier
   Tab/Entrée, F6 Studio, M micro, Ctrl+Espace arrêt, D sommeil, F9 diagnostic,
   F10 Mini, F11 plein écran et Échap. Ctrl+C copie le sous-titre GPU affiché.
7. Comparer Canvas/GPU Éco/Équilibré/Cinématique avec le même modèle Ollama :
   TTFT, tokens/s, latence vocale et CPU/RAM/VRAM du Gestionnaire des tâches.
   Aucun gain RTX, coût énergétique ou impact Ollama n'a été mesuré ici.

Le HUD GPU offre commandes clavier et copie Unicode ; sa lecture par les
technologies d'assistance Windows reste à vérifier. COMMAND OS conserve ses
widgets Tk. Les sous-titres et expressions suivent les blocs PCM : précision
approximative, délai acoustique Bluetooth inconnu, aucune promesse mot à mot.
