# Centre de contrôle et PRESENCE Studio — inventaire de départ

24 octobre 2026, étape A. Base `1795dd8`, branche
`feat/jalon-2-voice-presence`, arbre de travail initialement propre. Commits
`3c75c54` (Windows), `65bd81c` (C1), `1e9c765` (atelier/Mini), `cec390b`
(morphing), `4eda447`/`a93a70f` (COMMAND OS/lecture) et `e6d33c4` (audit)
présents. Références : cahier des charges original dans
`MASTER-SPEC.MD.docx`, `COGNITIVE-PRESENCE-SPEC.md`, `PRESENCE-3.2-SPEC.md`
et contrôle détaillé `AUDIT-LOTS-3-6.md`. Aucun travail antérieur à refaire.

## Acquis vérifiés avant changement

| Fonction | Flux existant conservé | Contrôle ciblé |
| --- | --- | --- |
| Micro réel → RMS/onde → VAD/STT | Résumés PCM indépendants du seuil VAD, générations et états suspendus filtrés, diagnostic visible | `test_capture_presence`, `test_capture_turns`, `test_voice_flow` : signal/bruit/silence contrôlés, erreurs et reprise |
| Navigation et boutons essentiels | Barre fixe, panneau latéral repliable/défilant, raccourcis | `test_responsive_navigation` : paysage/portrait/petites fenêtres/DPI |
| C1 automatique et manuel | `route_request` → paramètres effectifs → métadonnées archivées ; budgets voix/chat/mission préservés | `test_cognition`, `test_request_settings`, `test_cognitive_ui` |
| Continuer, mémoire et provenance | Contexte borné, objectif initial, extraits explicités ; souvenirs approuvés et archive SQLite réutilisés | `test_cognitive_continuation`, `test_memory_flow`, `test_memory_context`, `test_context_ui` |
| THINKING, atelier et Mini | Un modèle, un Canvas/pool borné ; F10 et géométrie restaurée ; préférences persistantes | `test_presence_advanced` : formes, halo/épaisseur, PCM prioritaire, clavier et DPI |
| Morphing terminal et interruption | `richtext` → expressions protégées → epochs/segments PCM → fin fiable de segment → `MorphController` → Canvas | `test_voice_flow`, `test_semantic_presence` : 😊, ❤️, 😂 en fin de phrase, huit familles, code exclu, perte de callback visuel, annulation et événements obsolètes |
| Emotional Field et sous-titres | Événements préparés par segment, progression PCM monotone, deux lignes | `test_emotional_field`, `test_presence_integration` : couleurs/mots-clés, neutre, erreurs, masquage et fermeture |

Résultat de départ : **177 tests exécutés, 177 réussis, aucun ignoré**, Linux
Tk9, 35,710 s. Commande :

```sh
DISPLAY=:99 python -m unittest tests.test_cognition tests.test_cognitive_continuation tests.test_request_settings tests.test_cognitive_ui tests.test_memory_flow tests.test_memory_context tests.test_context_ui tests.test_capture_presence tests.test_capture_turns tests.test_voice_flow tests.test_presence_advanced tests.test_semantic_presence tests.test_emotional_field tests.test_presence_integration tests.test_responsive_navigation tests.test_rich_conversation
```

Tk/Canvas, événements clavier et SQLite sont réels ; PCM, périphériques, STT et
génération sont contrôlés dans ces tests. Aucun nouveau défaut reproduit dans
ce périmètre. Le retour utilisateur précédent confirme micro/onde/couleurs/
sous-titres sur son PC ; cette campagne distante ne le remplace pas.

## LOT 2 : présent, pas officiellement validé

Les exigences originales ont été rapprochées du code, sans annoncer une nouvelle
livraison du lot : surfaces sombres, états/focus, saisie responsive, métriques
discrètes, polices réelles et titres, gras/italique/combinés, souligné/surligné/
barré, listes imbriquées, citations, séparateurs, liens confirmés, code,
tableaux textuels, Unicode ; flux original/structure/TTS séparés, rendu de la
seule région active, sélection/copie et source SQLite préservées. Préférences
de lecture et aperçu utilisent le même `MarkdownView`.

Limites précises : tableaux textuels susceptibles de se replier en fenêtre
étroite ; mathématiques textuelles simples, pas moteur LaTeX ; extensions
explicites `++souligné++`, `==surligné==`, sans interprétation HTML. L'acceptation
esthétique et l'accessibilité Windows/DPI restent à constater sur le PC.
**LOT 2 non officiellement validé** ; aucun succès automatisé ne vaut jugement
esthétique. Les LOTS 4, 5 et 7 restent hors de cette mission.

## Écarts visés par la mission actuelle

- Paramètres dispersés entre modèle/contexte, voix, lecture et atelier ; aucun
  point d'entrée unifié/recherche locale. Les stockages existants (`Settings`,
  préférences `voice`, `conversation`, `presence`, navigation/métriques) sont à
  réutiliser, sans nouvelle base ou duplication de valeurs.
- Atelier fonctionnel mais changements immédiatement enregistrés : absence de
  session de brouillon avec Avant/Après, Annuler/Appliquer et restauration.
- Aperçus hors ligne déjà réels ; scénario existant limité à des ambiances,
  sans parcours complet repos/écoute/réflexion/parole/émotion/emoji/interruption.
- Contrat de réglages à partager entre renderers ; l'adaptateur GPU de
  production n'existe pas et ne doit pas être annoncé comme intégré.

## Prototype GPU : décision conservée

`presence_gpu.ReactorScene` réutilise le modèle et les formes ; shaders
ModernGL, ressources bornées, halos/particules/anneaux, sondes et packaging
PyInstaller séparés existent. Fenêtre GLFW autonome : aucune preuve
d'intégration à la boucle Tk. Canvas reste le moteur de production.
Les mesures publiées sont **Mesa logiciel Linux**, environ95 MiB RSS et
318–398 %CPU pendant THINKING ; elles ne mesurent ni RTX3070 ni VRAM physique.
Le repos dessine une frame puis attend. Voir `PRESENCE-GPU-BENCHMARKS.md` et
`PRESENCE-GPU.md`. Aucune dépendance ModernGL obligatoire à ajouter à JARVIS.

**Validation matérielle en attente** : Windows11/RTX3070, micro/VAD/Whisper,
Piper audible, Qwen réel, interruptions et coexistence des charges, rendu à
différents DPI et appréciation des captures/animations par l'utilisateur.
