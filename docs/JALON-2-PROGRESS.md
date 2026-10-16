# Jalon 2 — progression vérifiable

Branche : `feat/jalon-2-voice-presence`, issue de `origin/main` `dcc327b`.
Le jalon 1 a été validé sur Windows par le propriétaire ; ce n’est pas une validation
Windows du présent jalon. Spécifications : DOCX existants + `JALON-2-SPEC.md`.
Aucun changement direct de main, aucun force push, aucune fusion automatique.

## Critères d’implémentation stables (24)

Une case cochée signifie code intégré et testé au niveau indiqué, pas recette Windows.

- [ ] I01 Capture micro locale sur activation explicite, libération à l’arrêt.
- [ ] I02 Sélection entrée/sortie et erreurs de périphériques.
- [ ] I03 VAD réel local, fin de tour, silences, pré-roll et limites.
- [ ] I04 STT français local avec modèle installé, sans téléchargement implicite.
- [ ] I05 TTS Piper : véritable modèle masculin français.
- [ ] I06 TTS Piper : véritable modèle féminin français.
- [ ] I07 Gestionnaire de voix, préécoute audio et vitesse persistante.
- [ ] I08 Orchestration STT → Ollama → TTS segmenté, tours mains libres.
- [ ] I09 Interruption vocale, invalidation des anciens segments et politique d’écho explicite.
- [ ] I10 Arrêt manuel/urgence et sommeil désactivant capture et tâches.
- [ ] I11 Migration SQLite préservant textes, provenance, dates, voix/moteur et interruptions.
- [ ] I12 PRESENCE : une machine à états et une géométrie morphologique unique.
- [ ] I13 Ligne plate au silence et onde arrondie pilotée par micro réel.
- [ ] I14 Réflexion sur traitement réel et noyau piloté par audio diffusé.
- [ ] I15 Centrage et proportions responsives sans déplacement par sous-titres.
- [ ] I16 Fond noir, sélecteur, restauration et contraste automatique persistants.
- [ ] I17 Spectre émotionnel conservateur, mots sélectifs, quatre modes persistants.
- [ ] I18 Spectre opérationnel indépendant, texte explicite, aucun droit supplémentaire.
- [ ] I19 Sous-titres sur audio joué, approximation annoncée, historique/copie.
- [ ] I20 Profils graphiques et réduction du mouvement, ressources bornées.
- [ ] I21 Préférences vocales/personnalité sans filtrage ni modification des permissions.
- [ ] I22 Tests ciblés audio et non-régression du jalon 1.
- [ ] I23 Build Windows vocal séparé, contrôles de démarrage et artefact versionné.
- [ ] I24 Installation, recette Windows, restauration et reprise documentées.

## Critères de validation stables (34)

V01 à V34 sont exactement les 34 contrôles de la section 13 de `JALON-2-SPEC.md`.
Une preuve Linux peut valider un invariant indépendant de l’OS (ex. géométrie),
jamais le microphone, l’écoute perceptive ou l’exécutable Windows. Aucune case
validée par un test ignoré. Preuves actuelles : aucune pour le jalon 2.

Validés : aucun. Implémentation : **0/24 = 0 %**. Validation : **0/34 = 0 %**.

## Étapes

| Étape | Statut | Preuves / reste | Commit / prochaine opération |
|---|---|---|---|
| J2.0 | TESTÉ | main inspecté, branche dédiée ; moteurs et contraintes définis ; tests baseline ci-dessous | commit `J2.0: prepare voice milestone and recovery checklist` ; implémenter J2.1 |
| J2.1 | NON COMMENCÉ | capture/VAD/STT | à venir |
| J2.2 | NON COMMENCÉ | TTS/deux voix | à venir |
| J2.3 | NON COMMENCÉ | dialogue/interruption/SQLite | à venir |
| J2.4 | NON COMMENCÉ | PRESENCE | à venir |
| J2.5 | NON COMMENCÉ | spectres/sous-titres | à venir |
| J2.6 | NON COMMENCÉ | build/recette | à venir |

## Décisions et limites initiales

- Conserver Python/Tk et le processus Ollama existant. Modules audio facultatifs ;
  une panne ou une absence de dépendances audio ne bloque pas le texte.
- faster-whisper 1.2.1 CPU int8 + Silero VAD ONNX embarqué dans ce paquet : éviter
  PyTorch et préserver la VRAM. Modèle STT par chemin local, aucune récupération cachée.
- Piper 1.8.0 CPU/ONNX : deux modèles FR distincts. Moteur GPL-3.0-or-later ;
  notices et licences à conserver avec toute distribution vocale. Kokoro est
  étudié comme alternative ; ne pas promettre une voix masculine FR inexistante.
- Un casque est requis pour l’interruption vocale pendant la lecture dans ce jalon.
  En mode haut-parleurs, capture suspendue pendant TTS pour éviter l’auto-déclenchement ;
  interruption manuelle disponible. Pas de promesse d’AEC/full-duplex haut-parleurs.
- Cloud : aucun périphérique `/dev/snd`, aucun Windows. HuggingFace renvoie 403 :
  modèles non téléchargeables ici. Continuer le code et les tests indépendants ;
  fournir une installation explicite sur le PC Windows et des tests live opt-in.
- Contradiction générale existante : voix « optionnelle » dans résumé DOCX mais P0
  dans les exigences détaillées. Ce jalon cible bien la voix, sans supprimer de P0.

J2.0 tests baseline : 16 exécutés, 12 réussis, 0 échoué, 4 ignorés (3 écran, 1 modèle
Ollama absent). Windows du jalon 2 : aucun test. Références consultées sans copie :
Mark-LV CC BY-NC 4.0, backtalk/fullstack-agent AGPL-3+, site jarvis AGPL-3 ; ne pas
intégrer leur code. Concepts retenus : activation explicite, devices par nom/host API,
fréquence native et casque pour barge-in. Sources/liens dans JALON-2-SPEC.md.
