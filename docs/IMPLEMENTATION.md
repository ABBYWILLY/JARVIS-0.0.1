# Décision et périmètre de cette livraison

Ce document décrit la livraison historique du jalon1. Pour l’état actuel
(voix/PRESENCE, J2.8 raisonnement/contexte/mémoire), lire `JALON-2-PROGRESS.md`
et `NEXT-CODEX-SESSION.md` ; les limites « pas encore » ci-dessous sont historiques.

Les deux DOCX du dossier `docs/` ont le même SHA-256 et le même contenu. Ils restent
la spécification complète, inchangée. La présente mission livre le sous-ensemble
conversation demandé, **pas la recette finale P0**.
Contradiction interne : la synthèse MVP indique « voix optionnelle », tandis que
VOC-002/003/004 et l’acceptation finale imposent STT et deux voix FR. Ces exigences
restent au programme ; elles ne sont pas annoncées comme satisfaites ici.

## ADR-001 — Socle desktop économique

Python 3.12 + Tkinter + SQLite standard : pas de dépendance d’exécution, tests rapides,
fenêtre desktop et compilation PyInstaller Windows. Alternative .NET : excellente
intégration Windows, mais non retenue pour garder ce premier socle exécutable/testable
ici et limiter l’outillage. La direction graphique est sombre/cyan, sans réutiliser
d’assets des références. Ce socle n’est pas une reproduction de leurs projets.

`run.py → ui.App → storage.Store` ; l’interface lance `worker.Worker` dans un processus
`spawn` séparé, qui utilise le contrat `InferenceProvider` et son adaptateur `Ollama`.
Un futur adaptateur, la voix, la mémoire ou PRESENCE pourront exploiter ces frontières
sans déplacer les accès réseau dans les callbacks UI. Aucun framework agent prématuré.

Contrat IPC v1 : `Event(kind, payload, version=1)` ; `models` contient `list[str]`,
`chunk` du texte, `done` les métriques disponibles, `error` une explication utilisateur.
La file est bornée à 128 événements ; pas plus d’un worker. Arrêter tue le worker
et ferme son socket ; Ollama reste un service externe et peut libérer ses ressources
avec un délai. Une panne du worker ne ferme pas l’interface.

Stockage v1 : `sessions` (identifiant/titre/date UTC), `messages` (rôle, contenu,
modèle, statut/date UTC), `settings` (profil JSON validé), `PRAGMA user_version=1`.
Transactions, clés étrangères, WAL ; refus des schémas plus récents. Les fragments
reçus sont enregistrés, puis finalisés en `complete`, `cancelled` ou `error` ;
`streaming` devient `interrupted` à la réouverture.

Budget contexte : estimation prudente par octets UTF-8 + marge, pas tokenizer exact.
Réserve réponse et instruction système, conserve les derniers tours complets,
affiche le nombre de messages hors contexte pendant la génération. Les originaux
restent archivés. Pas encore de résumé automatique ni de recherche mémoire.

Sécurité : requêtes HTTP directes sur loopback seulement, sans proxy, télémétrie
ou endpoint cloud obligatoire. Pas d’authentification réseau stockée. Aucun outil
système ni accès de fichiers fourni au modèle ; aucun texte produit ne s’exécute.
L’intégration future des outils exigera un moteur de permissions séparé, un aperçu
et une approbation explicite avant chaque action concernée. Le stockage n’est pas chiffré.

## Exigences conservées pour les prochaines missions

- Voix réelle STT/TTS FR, interruption et audio : VOC ; PRESENCE : UI-002/003/004.
- Pièces jointes, vision et protections documentaires : MM ; outils et permissions
  granulaires avec audit : AGT et SEC associés. Aucun de ces modules n’est simulé.
- Recherche/souvenirs, résumés, sauvegarde/restauration guidée, chiffrement et purge :
  MEM et DAT non couverts par le simple historique SQLite.
- Mesures GPU/ressources, tokenizer précis, benchmarks et cible 60 tokens/s : LLM-004/005, PER.
- Installateur/signature, licences à choisir avant distribution publique, mises à jour,
  recette Windows/DPI/accessibilité et restauration : REL, QA, UI-005/006, DAT.

Les exigences et priorités originales restent celles des DOCX. Le workflow produit
un artefact de développement, pas une release certifiée conforme à tous les P0.

## Validation de cette session

- Python 3.12.14 / Linux : tests unitaires, SQLite, HTTP/NDJSON réel vers serveur de test,
  processus spawn et parcours Tk sur serveur X virtuel : **15 tests réussis, 1 ignoré**
  (inférence réelle). Build PyInstaller Linux et test de démarrage du binaire réussis,
  avec inclusion explicite des bibliothèques Tcl/Tk du runtime Linux de cette machine.
  Cela ne valide pas le binaire Windows. Voir commandes de test dans le README.
- Serveur **Ollama 0.40.5 réel**, archive officielle vérifiée par SHA-256 : démarrage,
  `/api/version` et inventaire vide `/api/tags` accessibles par l’application.
- Téléchargement `qwen2.5:0.5b` refusé par le proxy pour `registry.ollama.ai`.
  Inférence réelle non exécutée ; test live ignoré. Sur Windows, lancer le test
  `JARVIS_TEST_MODEL` après installation du modèle, sans modifier le code.
- Build et lancement Windows non exécutés ici. Le workflow Windows exécute la suite
  et vérifie Tk, SQLite et multiprocessing dans l’EXE, sans prétendre tester un modèle
  absent du runner. Une vérification manuelle sur Windows 11 avec Ollama reste nécessaire.

Prochaine mission : recette sur votre Windows 11 (EXE, vrai modèle, arrêt/reprise,
DPI 100/150/200 %), puis premier pipeline vocal local push-to-talk avec deux voix FR
évaluées et licences vérifiées. La spécification complète reste le cap.
