# LOT 7 — recette Windows 11 / RTX 3070

La CI vérifie les sources et le packaging Windows ; elle ne remplace pas votre
microphone, Piper installé, votre écran, le Bluetooth ou la RTX 3070 sous charge.
**Validation matérielle en attente.** Aucun poids supplémentaire n'est requis.

## Compiler et conserver les données

Depuis la branche `feat/jalon-2-voice-presence`, Python 3.12 :

```powershell
.\scripts\build-windows.ps1 -WithVoice -WithGpu
```

Sortie : `dist/jalon-2/Jarvis.exe`, SHA-256 et `diagnostics/`. La compilation
exécute la suite, les probes voix/Silero et GPU source/EXE, et vérifie le même
profil synthétique prérempli après un démarrage source et deux lancements EXE.
Le vérificateur SQLite est en lecture seule : archives, provenance, réglages,
souvenir approuvé, FTS et fragment récupéré doivent être conservés exactement.
Une simple première image ne valide plus la fermeture GL : son acquittement et
ses erreurs différées sont contrôlés séparément. Un pilote absent est distingué
d'un problème de packaging, et n'est jamais compté comme rendu réussi.

Mise à jour réelle : fermer JARVIS, sauvegarder `%LOCALAPPDATA%\Jarvis` (ou votre
`JARVIS_DATA_DIR`), puis remplacer seulement le binaire. Les données/modèles
restent hors de l'EXE. Le binaire n'est pas signé ; SmartScreen peut afficher un
avertissement. Signature et installateur certifié restent hors de ce lot.

## Recette fonctionnelle

1. Démarrer sans Ollama et sans micro branché : fenêtre accessible, erreur
   compréhensible, conversation historique intacte. Relancer Ollama et
   actualiser : aucun modèle téléchargé automatiquement.
2. Vérifier modèle Qwen, modes C1 Auto/manuel, budget, mémoire approuvée et
   inspecteur de provenance. Tester une réponse longue et Continuer ; arrêter
   en streaming et vérifier le fragment après redémarrage.
3. Activer l'écoute avec le micro choisi : RMS réel qui suit la parole puis le
   bruit ambiant, VAD, fin de tour, Whisper et texte. Débrancher le micro pendant
   transcription : diagnostic et récupération manuelle, sans relance de question.
4. Préécouter Tom/Siwis installés, tester les profils et Plus lentement. Au casque,
   Stop/Répète/Reprends/Continue ; citations et propre voix de JARVIS ne doivent
   pas déclencher de commande. En haut-parleurs, vérifier suspension/retour micro.
   Aucun AEC nouveau n'est annoncé. Tester séparément la sortie Bluetooth.
5. Sélectionner un passage Rich Text : Copier/Lire/Répéter/Expliquer/Développer/
   Résumer/Continuer. Relire sans appel Ollama ; interruption/reprise limitée au
   passage. Vérifier Markdown, monnaie, maths, emojis et sous-titres synchronisés.
6. Pendant parole et réflexion, alterner Canvas/GPU par Ctrl+F7 au moins dix fois.
   Même conversation/audio, pas de deuxième fenêtre active ni réouverture micro.
   Tester une fermeture manuelle GPU et son repli ; refaire un essai explicite.
7. HUD off/Minimal/Standard/Diagnostic, Mini-PRESENCE, portrait/paysage, fenêtre
   réduite et DPI 100/150/200/250 %, puis changement d'écran. Préférences conservées
   au redémarrage, commandes accessibles, aucun déplacement du noyau.
8. Fermer pendant génération puis pendant lecture ; vérifier dans le gestionnaire
   des tâches qu'aucun enfant JARVIS ne persiste après fermeture normale. Si un
   pilote refuse l'arrêt, le diagnostic doit rester visible et permettre de
   réessayer ; ne pas confondre arrêt forcé et libération GL acquittée.

## Mesures comparables

Utiliser [LOT-7-BENCHMARKS.md](LOT-7-BENCHMARKS.md) depuis l'environnement Python
du projet. Choisir un nouveau dossier par essai. Consigner le modèle exact,
contexte, profils, résolution/DPI, périphériques et état du cache déclaré.

- COMMAND OS, Canvas et chaque profil GPU, au moins 60 s puis plusieurs répétitions.
- Même question/contexte Ollama sans puis avec GPU, dans les deux ordres ; relever
  TTFT/tokens/s et F9/P95/P99, charge GPU globale et RSS des processus séparés.
- Piper, capture seule, puis conversation complète durant 180 s ; relever STT,
  premier PCM et délai fin de tour → PCM. Le DAC estimé ne mesure pas l'acoustique.
- Session de 20–30 min avec échanges et bascules, puis 5 min au repos : relever
  les processus, RSS, erreurs et fermeture. Une hausse due à l'historique attendu
  n'est pas automatiquement une fuite ; un essai court sans hausse ne prouve pas
  l'absence de fuite. Les exports restent bornés (512 tours, 7 200 échantillons,
  120 fenêtres GPU), sans conversation/PCM exportés par défaut.

Les Watts, la VRAM physique attribuable par processus, le délai acoustique et les
performances combinées RTX/Ollama/voix ne sont pas mesurés dans le cloud. Les
résultats logiciels Mesa ne doivent pas être extrapolés à votre carte.
