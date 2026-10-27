# PRESENCE GPU 3.0 — revue artistique A + B

27 octobre 2026. Prototype autonome ; Canvas reste le moteur de `Jarvis.exe`.
Référence avant travaux : `3a4c2fd`, branche `feat/jalon-2-voice-presence`.

## Point d'arrêt utilisateur

Cette livraison concerne exclusivement **A — Direction artistique** et
**B — Matière et lumière**. Les captures, export vidéo, tests, mesures et CI
servent à leur validation intermédiaire ; ils n'ouvrent pas les sous-lots
C (animations/états), D (gravure morphologique), E (nouveaux scénarios) ou
F (campagne d'optimisation). Attendre l'avis artistique de l'utilisateur avant
de les commencer. Aucun accord esthétique ou essai matériel n'est présumé.

## A — Composition

- Fond RGB `(0, 0, 0)` ; seule la lumière des objets s'étend sur le noir.
- Sphère centrale agrandie, trois orbites apparentées et espacées ; suppression
  de la spirale et de la cage de filaments permanentes en plein THINKING.
- 24 particules orbitales en Équilibré, 36 en Cinématique, contre 768/1 536.
  Les accents filaires nécessitent un RMS fourni non nul ; aucun PCM inventé.
- Caméra et occlusion analytique partagées, mêmes entrées et états existants.

La vérification du noir a aussi révélé une fuite réelle : près d'une intersection
rasante rayon/plan, la dérivée utilisée pour l'anticrénelage pouvait devenir
immense et éclairer des pixels loin des anneaux. Sa largeur est bornée dans le
shader ; le fond n'est pas artificiellement masqué à la composition finale.

L'API, les allocations, le contrôle d'interruption, les huit familles de symboles
existantes et le repos en ligne sont conservés. Le nouveau repos sphérique,
les animations d'entrée THINKING et les expressions gravées restent différés.

## Validation et limites

**A : 56 tests ciblés réussis**, dont 17 tests du renderer sur un vrai contexte
EGL ; noir RGB exact avec/sans bloom, réduction du mouvement, huit symboles,
PCM, interruptions, fichiers et libération des ressources.

Les preuves et mesures finales A + B seront ajoutées dans ce document avec le
second commit. OpenGL/EGL sous Mesa logiciel ne valide ni la RTX 3070, ni la
coexistence avec Ollama/Whisper/Piper, ni l'esthétique Windows. Aucun modèle,
asset tiers, moteur lourd ou paquet obligatoire n'est ajouté.
