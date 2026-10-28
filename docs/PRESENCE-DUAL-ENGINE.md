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
