# Audit LOTS 3 et 6 — 23 octobre 2026

Base inspectée : branche `feat/jalon-2-voice-presence`, HEAD `a93a70f`, dépôt
initialement propre. Références `65bd81c`, `1e9c765`, `cec390b` présentes.
Aucun moteur graphique ajouté avant ce contrôle. `main` reste inchangée.

## LOT3 : code présent et raccordé

| Fonction | Réalisation et raccordement | Vérification |
| --- | --- | --- |
| Manuel J2.8, Rapide, Approfondi, Créatif, Auto | `cognition.route_request`, `ui.change_cognitive_mode` et `ui.send` ; sélection persistante. Créatif ajuste la génération, sans capacité de raisonnement autonome annoncée. | `test_cognition`, `test_cognitive_ui`, `test_reasoning_ui` |
| Budgets voix/chat/mission | `Settings.for_request`, requête effective et métadonnées archivées | `test_request_settings`, budgets et priorité manuelle |
| Continuer/Suite, limite de génération | `ui.continue_response`, `build_continuation` ; objectif initial et chaîne épinglés si possible, extraits UTF-8 explicitement non exhaustifs sinon | `test_cognitive_continuation`, `test_cognitive_ui`, erreurs contexte/modèle absent, brouillon intact |
| SQLite, historique après interruption | `storage.Store`, finalisation/reprise, FTS5 ; aucun remplacement des originaux | `test_memory`, `test_context`, `test_memory_flow`, `test_reasoning_ui` ; arrêt brutal d'un writer Linux vérifié séparément |
| Souvenirs approuvés, modification/suppression | `memory.MemoryRepository`, `MemoryDialog`, sauvegardes et consentement existants | `test_memory`, `test_memory_ui`, `test_memory_context`, `test_memory_flow` |
| Contexte et provenance | `ui.open_context`, onglets Souvenirs/Historique/Contexte ; trace de préparation, pas preuve d'utilisation ou de vérité | `test_context_ui`, `test_memory_ui`, `test_cognitive_ui` |

Défaut reproduit : citations simples/typographiques et négations « aucune/rien »
pouvaient activer à tort Créatif/Approfondi. Correction minimale de reconnaissance,
six sous-cas en échec avant correctif puis verts ; apostrophes françaises préservées.

## LOT6 : code présent et raccordé

| Fonction | Réalisation et raccordement | Vérification |
| --- | --- | --- |
| THINKING distinct, halo/épaisseur | `PresenceModel`, `stroke_widths`, `PresenceView._render` ; même contour | Géométrie lenticulaire, silence réel, paramètres bornés, largeur/DPI |
| Atelier, profils, palettes, microexpressions | `open_settings`, `PresenceSettings`, `presence_motion` ; aperçus explicitement hors ligne | Persistance, 4 ambiances, 3 palettes, 4 microexpressions, priorité PCM |
| Mini/F10, retour normal, resize/DPI | `toggle_mini`, `_apply_window_mode`, `_layout_controls` ; fenêtre/Canvas/pool23objets réutilisés | Vrais événements clavier F10, restauration géométrie à100/250%, centrage et commandes |
| Emotional Field, sous-titres PCM | `spectrum`, `captions`, préparation par segment, progression monotone | Dominante/pivots/négations, deux lignes, accents, absence d'analyse linguistique par frame |
| 8 familles Semantic Morphing | `richtext→expressions→voice_ui→complete_segment→MorphController→Canvas` | Huit contours, détails, transitions/retour ; textes 😊/❤️/😂 conservés dans COMMAND OS et retirés du TTS |
| Audio prioritaire, annulation, profils | Epochs, callbacks PCM et fin de segment fiables ; `render_quality` | Interruptions, événements tardifs/perdus, surcharge, mouvement réduit, aperçus et veille |

Défauts reproduits et corrigés : palettes pastel/ambre teintaient le cyan même
sans émotion locale ni dominante ; nombres démesurés levaient `OverflowError`
dans préférences, résumé PCM et chronométrages. Régressions ajoutées avant
correction, sans changement du signal audio ou des seuils VAD.
Le vrai raccourci F10 est désormais testé ; aucun défaut F10 de production constaté.

## Résultats et limites

- LOT3 :74tests backend et33tests GUI par version Tk8.6/Tk9 réussis.
- Présence :124tests par version Tk, puis111tests purs et test renforcé des trois
  phrases repassés ; campagnes qui se recouvrent, ne pas additionner les comptes.
- Suite globale après corrections :528tests exécutés,519réussis,9ignorés
  (dépendances/modèles locaux absents),71,107s sous Linux/Tk9.
- Tk, Canvas, fichiers SQLite/FTS/WAL et événements clavier sont réels sous Linux.
  Worker LLM et PCM contrôlés sont des doublures ; aucun Ollama ou Piper audible
  ni microphone physique testé dans cette campagne. Le crash Linux `os._exit(73)`
  conserve texte/interruption/FTS et intégrité, sans simuler une coupure électrique.

**Validation matérielle en attente.** Sur Windows : modes/budgets avec Qwen réel,
récit tronqué→Continuer→interruption/reprise, mémoire/provenance, micro/VAD/Whisper,
Piper et les trois phrases, F10/Mini et DPI entre moniteurs. Voir `VOICE.md`.
Routage heuristique borné, continuité sans garantie automatique de cohérence,
synchronisation visuelle approximative par segment ; aucune qualité cognitive
ou performance matérielle mesurée inventée. La CI Windows complète cette
validation logicielle ; elle ne remplace pas la RTX3070 et le matériel du PC.
