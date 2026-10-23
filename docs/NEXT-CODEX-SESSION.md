# PRESENCE GPU — phase0 audit, 23 octobre 2026

Nouvelle demande : `PRESENCE-GPU-SPEC.md`. Audit complet ciblé LOTS3/6 dans
`AUDIT-LOTS-3-6.md`, code existant réutilisé. Défauts reproduits corrigés : citations
simples et négations auto, valeurs numériques démesurées dans affichage/paramètres,
cyan neutre des palettes. Nouveau vrai test clavier F10/Mini→normal/DPI.
Suite globale :528tests,519réussis,9ignorés ; campagnes ciblées Tk8.6/9 vertes.
Pas de validation matérielle distante. `main` inchangée. Prototype ModernGL
optionnel autonome après ce contrôle ; aucune intégration de production avant
mesures Windows RTX/voix/Ollama. Sourcebase a93a70f propre, aucun travail perdu.

---

# Reprise finale — aperçu RichText, 23 octobre 2026

LOTS1/2 déjà livrés conservés. LOT3 publié65bd81c, LOT6 publié1e9c765,
correctif morphing cec390b ; aucun changement de main. Dernier ajout : Menu→
Lecture et typographie montre un vrai aperçu Markdown local (H1/H2/H3, gras,
italique, souligné, surligné, barré, code/tableau). Six réglages actualisent les
fontes/tags réutilisés sans reparsing de l'historique. Saisie incomplète garde le
dernier aperçu valide. Fermer/Restaurer l'aperçu ne modifient pas SQLite ;
Réglages d'origine conserve son contrat explicite de reset immédiat enregistré.
Navigation Tab/Maj+Tab et libération des ressources testées. 46tests ciblés
intégrés Tk9 réussis ; 32ciblés Tk8.6 réussis en copie isolée avant intégration.
Suite globale finale Tk8.6 :523tests exécutés,514réussis,9ignorés. CI : voir
progression et dernier run Windows, pas de modèle
ou téléchargement ajouté. Recette PC courte dans VOICE.md.
La bibliothèque existante reste8familles expressives, pas100nouveaux emojis.
Pas de validation du microphone physique à distance ou de synchronisation
mot à mot prétendue. Ne pas refaire les LOTS3/6 ; LOTS4/5/7 restent hors livraison.

---

# Reprise — LOT6 PRESENCE avancé, 23 octobre 2026

Travail interrompu conservé, intégré après LOT3/cec390b. THINKING devient une
lentille organique distincte du noyau PCM, même en réduction de mouvement. Vraies
largeurs à96dpi : trait6px/halo27px au réglage6, sliders existants conservés.
Atelier : intensité halo0–100%, taille THINKING70–130%,4ambiances et3palettes,
microexpressions cosmétiques bornées (surprise/réconfort/enthousiasme/gravité).
Préréglages et préférences futures préservés. Aperçus hors ligne clairement
signalés, sans modèle/micro. La parole réelle annule l'aperçu immédiatement.
Mini/F10 : même fenêtre, même Canvas et23objets réutilisés, redimensionnable,
statut micro visible, retour COMMAND OS, sans always-on-top ni deuxième boucle.
Correctif de position relative/absolue des libellés au retour Mini→normal.
Le rendu ne change ni PCM/RMS/VAD ni TTS, inférence, permissions ou états réels.
Silence plat, interruptions prioritaires, réduction du mouvement et suspension
hors écran conservés. Tests ciblés Tk8.6/9 et géométrie passent ; suite intégrée et
CI dans la progression. Captures Linux réelles d'aperçu, pas de matériel validé.
Sur PC : THINKING/ligne/halo, atelier, Mini→normal à différentes tailles/DPI,
écoute puis interruption d'un aperçu, trois phrases emoji et reprise vocale.
Pas de gain CPU/RAM/latence Windows annoncé. LOTS4/5/7 non implémentés ici.

---

# Reprise — LOT3 Cerveau C1, 23 octobre 2026

Travail interrompu conservé et finalisé, après correctif morphing cec390b.
Menu Conversation : politique persistante ManuelJ2.8/Automatique local/Rapide/
Approfondi/Créatif. Heuristiques conservatrices sur la demande, sans appel LLM
additionnel ; citations/code/négations exclus. Manuel reste prioritaire, anciens
profils inchangés. Créatif = température minimale0,9 et think:false, pas une
capacité de raisonnement distincte. Budgets voix/chat/mission J2.8 conservés.
Continuer/Suite poursuit la dernière réponse finalisée non vide, même coupée à
la limite : requête initiale et passages originaux épinglés, chaîne complète si
elle tient, sinon extraits début/fin explicitement non exhaustifs. Contexte borné,
erreurs visibles, brouillon et archive intacts ; aucune garantie LLM inventée.
Mémoire : onglets Souvenirs/Historique/Contexte, approbation et sauvegardes
existantes réutilisées. Trace limitée aux100dernières réponses de la conversation,
inclusion inspectable, aucune mémorisation implicite. Inspecteur distingue donnée
utilisateur/réponse générée non vérifiée/mémoire/extraits ; ne prétend ni savoir
ce que le modèle a utilisé ni mesurer la vérité. Mode/budget/origine archivés.
Tests ciblés :91backend,27interfaceTk9 et41interfaceTk8.6 réussis, sans Ollama
ou microphone. Suite globale et CI : voir progression/Actions après intégration.
Sur PC : choix modes et budgets, récit tronqué→Continuer→interrompre→Continuer,
inspection mémoire/contexte. Qualité narrative réelle à vérifier avec Qwen.
LOT6 et aperçu RichText finalisés séparément ; ne pas refaire les LOTS1–3.

---

# Reprise — correctif Semantic Morphing, 23 octobre 2026

Priorité traitée avant publication des LOTS 3/6. Les trois phrases « Heureux de
te revoir 😊 », « Je t'aime ❤️ », « C'est drôle 😂 » fonctionnent en parcours
événements voix/Canvas. Cinq régressions reproduites : THINKING répété ferme le
plan, statuts STT tardifs ferment la réponse, fin de segment fiable rejetée si le
callback visuel PCM a été perdu. Correctif ciblé, audio/Piper inchangés, vrais
speech_start/interruption et exclusions code/exemples conservés.
Diagnostic micro/STT : trace Semantic Morphing bornée à48étapes et bouton Copier.
164tests ciblés passent sous Tk8.6 et Tk9, dont parcours avec doublures PCM
explicitement identifiées ; pas de validation matérielle distante. Le retour
utilisateur confirme micro/onde/couleurs/sous-titres sur son PC. Morphing Windows
reste à vérifier : PRESENCE visible, Semantic Morphing activé, les trois phrases,
interruption puis reprise ; copier la trace si absent. Animation approximée par
segment et pauses PCM, sans alignement mot à mot ni délai ajouté à Piper.
LOTS 3/6 préexistants en cours de finalisation, ne pas les réimplémenter.

---

# Cognitive & Presence Evolution — LOT 2, 23 octobre 2026

L'utilisateur a explicitement demandé de poursuivre le LOT 2 après livraison du
LOT 1 logiciel3c75c54 (CI verte39910459009). Cela ne valide pas le micro physique :
**validation matérielle en attente**, recette dans `docs/VOICE.md`.
COMMAND OS NEO réutilise Tk/MarkdownView : deux surfaces arrondies statiques,
navigation LOT1 préservée, groupes secondaires, hiérarchie des messages, saisie
adaptative, états survol/focus/sélection/désactivation et scrollbars réservées.
Métriques masquées par défaut, préférence antérieure respectée. Un seul Text pour
les messages, aucun widget/animation par message ; pas de WebView/dépendance.
Rich Text2.0 complète l'existant : barré ~~texte~~ combinable, accents0–100 et
police code/tableaux monospace réellement mesurée. Corps/titres/styles/listes/
citations/liens/code/tableaux/Unicode déjà livrés réutilisés, sans réécriture.
Menu→Lecture et typographie : champs persistants accent_intensity/code_family,
reset aux réglages d'origine, densité et tailles. Anciennes préférences et clés
inconnues conservées ; fontes et marges réutilisées sans reparsing de l'historique.
La saisie compacte est limitée à18pt, le texte de lecture garde sa taille choisie.
Streaming et sourcesSQLite inchangés, TTS sans marqueurs ~~ ; code/tildes techniques
préservés. Sélection/copie/scroll testés ; HTML reste inerte, liens confirmés.
Limites : tableaux textuels pouvant se replier, maths textuelles simples ; aucun
moteur LaTeX, stylesHTML ou rendu complet de toutes variantes Markdown annoncé.
Suite locale Tk9 : 473 tests exécutés, 464 réussis, 9 ignorés (natifs/modèles absents).
Tk8.6 : 85 tests ciblés verts ; démarrages sources Tk8.6/9 avec profils isolés OK.
LOT2 publié4eda447 ; CI39915837584 a révélé un test ancien dépendant du coût réel
d'une frame : le mode adaptatif >12ms masque des arcs que le test attendait tous.
Reproduction déterministe, horloge contrôlée pour la géométrie ; nouvelle régression
de charge20ms puis reprise des calques sans allocation. Runtime PRESENCE inchangé.
CI et commit : voir progression, git log et dernier run Windows Jarvis.
Captures réelles Linux avec textes de démonstration explicites, sans modèle/micro :
/workspace/artifacts/command-os-neo-linux.png et command-os-neo-compact-linux.png.
LOT 3 et suivants non commencés. Ne pas refaire les lots1/2 ni annoncer le problème
de transcription matériel Windows résolu sans recette sur le PC utilisateur.

---

# Cognitive & Presence Evolution — LOT 1, 23 octobre 2026

Demande complète : `docs/COGNITIVE-PRESENCE-SPEC.md` ; branche uniquement
`feat/jalon-2-voice-presence`. Préserver J2.8, voix, mémoire et PRESENCE 3.2.
Le LOT 1 logiciel corrige le RMS/onde effacés lorsque le VAD n'a pas confirmé de
parole et la géométrie toujours plate de l'état écoute. Résumé visuel par extrema
PCM réels ordonnés, sans porteuse inventée ; RMS exact, aucun seuil VAD modifié.
Cela explique l'absence de réaction visuelle, pas la cause matérielle d'une absence
de transcription Windows. Le pipeline VAD/Whisper existant est conservé.
Diagnostic : micro sélectionné/ouvert/API/fréquence, RMS/vu-mètre, VAD, étapes,
fin de tour, STT, erreurs PortAudio et pertes. Heartbeat sans PCM = mesure inconnue,
jamais faux zéro ; âge PCM distinct du dernier événement, même si le worker se tait.
Erreurs détaillées conservées. Notifications suspendues/arrêtées/anciennes ne
réactivent pas l'onde. Stream fermé même si collecte métadonnées/abort échoue.
Navigation fixe Menu/Conversation/PRESENCE/Arrêt, sidebar rétractable/défilante,
overlay étroit, statut complet accessible et F6/F7/F8 ; aucune refonte LOT 2.
Tests de capture avec doublures explicites, signal faible/bruit/silence, routage
PRESENCE, fin de tour/STT/reprise, erreurs et absence de PCM. Navigation Tk8.6/9 :
16 configurations 560×400 à 1100×620/620×900 et DPI100–250 %.
Résultats finaux et SHA : voir `docs/JALON-2-PROGRESS.md` et `git log -1`.
**Validation matérielle en attente** : recette simple dans `docs/VOICE.md`, section
LOT 1. Vérifier sur le PC USB réel RMS silence/parole/silence, onde, VAD→Whisper→
Ollama, erreurs et navigation Windows/DPI. Ni microphone physique ni latence/CPU
Windows mesurés ici. Ne pas annoncer le LOT 1 entièrement validé. À cette livraison,
les LOTS 2–7 n'étaient pas commencés ; les missions ultérieures sont indiquées en tête.

---

# Reprise PRESENCE 3.2 — 22 octobre 2026

Demande complète : `docs/PRESENCE-3.2-SPEC.md`. Branche `feat/jalon-2-voice-presence`.
Lot 1 Rich Conversation : extension du scanner et des tags existants, soulignage
`++texte++`, surlignage `==texte==`, listes visibles, séparateurs et tableaux texte.
Typographie persistante via préférence `conversation`, copie source explicite,
liens HTTPS validés puis ouverture confirmée. SQLite et sélection affichée préservés.
Lot 1 validé : 390 tests exécutés, 381 réussis et 9 ignorés (dépendances/modèles
absents). Rendu : 16 tests verts sous Tk8.6 et Tk9. Tableaux textuels avec repli ;
256 URL interactives au maximum, texte/source conservés au-delà. CI lot 1 verte :
run 39842257220, commit 2f896d7.
Lots 2–3 implémentés ensemble sur le même moteur vectoriel : huit familles réelles
(sourire, rire, affection, tristesse, colère, surprise, réflexion, complicité).
Contour principal existant transformé ; détails et halos réutilisés, catalogue local.
Événements source/response_id/segment_id préparés à l’arrivée ; fin de segment émise
après tous les blocs réellement joués, derniers PCM conservés avant fin visuelle.
Queues bornées (64), maintien statique sans frames inutiles, contexte et annulation
par réponse. Émojis inconnus préservés dans les sous-titres sans forme inventée.
Queues d’emojis après une phrase conservées sans requête TTS vide ; ASCII expressif
retiré du TTS seulement, code/liens/chemins/citations/technique exclus du morphing.
PRESENCE → Réglages → Expressions : activation, intensité, aperçu local 8 familles.
Réduction de mouvement existante : symbole statique. Couleur Emotional Field conservée.
Synchro approximative : emoji final à fin du segment réellement joué ; milieu lors
un creux PCM estimé, sinon report à fin de segment. Reprise de parole, erreur,
arrêt, masque et nouvelle réponse annulent ; micro ouvert silencieux peut maintenir
un symbole bref sans retarder sa reprise350ms. Aucun timestamp mot à mot.
Validation finale : 435 tests exécutés, 426 réussis, 9 ignorés (natifs/modèles
absents). Parcours Tk8.6 : 80 tests ciblés puis 26 après priorité entre aperçus ;
Tk9 : suite complète. Démarrages source isolés Tk8.6/9 réussis. CI du moteur
959a94d verte : run 39844486651. Vérifier le SHA du dernier lot de finition.
Capture réelle source Tk8.6/Linux : /workspace/artifacts/presence32-smile-linux.png.
Mesure Linux étendue (CPU processus, médiane5×400 frames, hors audio/affichage GPU) :
THINKING équilibré 517µs contre579 avant2f896d7 ; paroleJARVIS538µs contre623 ;
pool Canvas23 objets stables, aucun timer silence/sommeil/masque. Variations VM :
pas de gain matériel ni de latence Windows déduit. Contrôleur seul≈11µs transition,
picPython≈52Ko origine/cache inclus, catalogue préexistant exclu.
Recette PCWindows11 restante : Réglages→Expressions, tester8familles uneàune,
réduction mouvements, puis vraie phrase 'Heureux de te revoir Abraham :)', ❤️,
emoji final/après ponctuation, reprise voix et arrêt. COMMAND OS : Lecture et
typographie, copier source vs sélection, lien confirmé et DPI100/150/200/250%.
Synchronisation estimée explicitée ; Bluetooth et latence réelle non mesurés.
Ne pas reprendre Emotional Field 3.0, Living Core 3.1 ni les optimisations J2.8.
La cible historique de 100 emojis reste différée : cette mission porte sur 8 familles.
Aucun téléchargement de modèle ou dépendance supplémentaire autorisé/nécessaire.

---

# Reprise PRESENCE3 — 22 octobre 2026

Demande complète : `docs/PRESENCE-3-SPEC.md`. Préserver les exigences DOCX/J2.8.
Sous-lot1 publié9c4d719 : épaisseur1–10/défaut6, halo multicouche, noyau orbital
THINKING centré, profils/DPI/charge, cache signal et canvasréutilisés.106tests ciblés.
Sous-lot2 livré : dominante stable par réponse, nuances locales/pivots conservateurs,
apaisement et expressions contextuelles. Ambiance thématique par défaut, cyan
neutre ou expression sélectionnables. Une heuristique locale, aucun second LLM.
Plans immuables source→IPC→PCM→sous-titres ; classification à l’arrivée du texte,
aucune analyse dans le rendu. Timeline64 passages/4000caractères par segment puis
queue neutre explicite, sans modifier le texte prononcé ni l’archive SQLite.
Sous-titres2lignes max, seulement mots/expressions pertinents estimés prononcés,
ponctuation/Unicode/emojis préservés. Couleurs interpolées, interruption prioritaire.
Réglages persistants : expressivité75, fluiditéRéactive/Cinématique/Apaisée (défaut
Cinématique), colorisationDiscrète/Normale/Expressive, taille12–32, sous-titres
émotionnels, halos/animations ; anciennes valeurs65/expression et clés inconnues
préservées. F9Immersion/Diagnostic masque les données auxiliaires, jamais la sécurité.
Microphone structuré : désactivé/initialisation/ouvert/voix/STT/suspendu/erreur,
sans changer permissions, moteurs, garde350ms ou filesaudio. Scénario horsligne
espoir→affection→tension→apaisement, annulé par voix/arrêt/erreur/masque/fermeture.
Réglages défilants/clavier, tests DPI100/200/250%. Petitefenêtre : tailleeffective
adaptée sans changer préférence, copie/notice auxiliaires masquées si nécessaire ;
indication≈toujoursprésente. Pleinécran recommandé pourgrande police.
157tests ciblés réussis sous Tk8.6 ; suite complète377 exécutés/368réussis/9ignorés.
Démarrages source Tk8.6/9 réussis ; capture réelle source Tk8.6/Linux inspectée.
Recette PCWindows11 et vraie latencevoix/Bluetooth restent à effectuer. Synchronisation
estimée phrase/bloc PCM/groupes de mots, aucun timestampmotàmot ni émotion réelle
mesurée. CI Windows du sous-lot 1 verte (run 39804343514). Sous-lot 2 :
un ancien test comparait le sous-titre responsive à une chaîne sans reflow,
avant stabilisation de la géométrie Windows (trace run 39810312573).
Fixture corrigée : attendre le layout ; conserver mots, positions, tags exacts,
copie et limite de deux lignes mesurées. 21 tests ciblés Tk8.6 + le test Tk9 réussis.
Les erreurs unittest sont aussi exposées en annotations CI, sans test désactivé.
Vérifier le nouveau run du dernier SHA avant d’annoncer compilation Windows verte.
Pas de travaux restants connus dans ce périmètre hors recette matérielle/mesures
Windows. Ne pas lancer voixpremium/bibliothèque100emojis/stockage sans nouvelle mission.

---

# Reprise — Markdown, TTS et spectre organique (18 octobre 2026)

- Lot Markdown/TTS : rendu Tk sûr en streaming/historique, source SQLite intacte,
  pipeline commun `richtext`, voix sans balises/emojis, liens lus par leur libellé.
  Liens HTTPS publics : aperçu/copie explicites, aucun navigateur lancé.
- Voix → périphériques : lecture des blocs de code facultative, désactivée par
  défaut (« Bloc de code non lu »). Maths simples verbalisées ; affichage texte
  des formules sans délimiteurs, sans moteur de composition LaTeX.
- Les constructions inachevées attendent leur fermeture ou la fin du flux avant
  lecture ; décimaux et URL protégés. Préchargement Piper et annulation préservés.
- Événements avec positions source transmis avec les callbacks PCM. Synchronisation
  approximative par phrase/bloc Piper, aucun alignement mot à mot annoncé.
- Lot spectre organique livré : modes ambiance / expression (défaut) / neutre,
  intensité 0–100 (défaut65), aperçu local dans Affichage PRESENCE. Aucun second LLM.
  Indices affirmés, négations/citations/questions/ambiguïtés prudentes ; heuristique
  lexicale locale, aucune prétention à comprendre toutes les émotions ou le sarcasme.
- Couleurs seulement à la lecture PCM, transitions450ms, fractions monotones par
  segment Piper ; interruption efface immédiatement la file et les sous-titres,
  couleur revient doucement cyan. Géométrie unique et permissions préservées.
- Validation finale : 140 tests ciblés sans ignoré sous Tk8.6 ; PRESENCE également
  testé sous Tk9. Source --smoke-test réussi, aucun modèle ou audio matériel exécuté.
- Markdown/TTS publié fa4e6f6 +6e4312f (UnicodeTk8.6) +12e47ab (devises).
  Build Windows12e47ab vert : actions/runs/39122219877. Vérifier le run du dernier
  commit spectre avant d’annoncer son EXE validé en CI.
- Recette matérielle Windows toujours requise : écoute réelle Tom/Siwis, Markdown,
  devises/formules, sous-titres avec emojis, interruption. Aucun modèle téléchargé.
- Ne pas reprendre J2.8, la voix premium ou la bibliothèque Semantic Morphing.

---

# Reprise JARVIS — correctif VAD/STT + PRESENCE

## Priorité actuelle : J2.8 tokens, contexte et mémoire

La demande J2.8 remplace l’ordre des lots J2.7 ci-dessous :
1. Livré : raisonnement Ollama et budgets de génération, 74 tests ciblés sans
   ignoré, démarrage de contrôle vocal Linux réussi. Retrouver le SHA par
   `git log --oneline --grep='control Ollama reasoning'`.
2. Livré : Context Builder centralisé, budget UTF-8 prudent/réserve, derniers
   tours complets, allègement des questions autonomes, rappels lexicaux et
   résumés extractifs non exhaustifs. Bouton Contexte : sélection historique,
   statistiques et originaux consultables. 100 tests ciblés distincts réussis.
3. Livré : mémoire locale durable/résumé/projet/document, approbation explicite,
   FTS5 lexical (secours LIKE signalé), provenance et inspection, sauvegarde
   avant correction/suppression et migration SQLite3 depuis v1/v2.
4. Livré : observabilité facultative et comparaison locale reproductible à
   configuration identique, `python -m jarvis.inference_benchmark`.
Validation finale J2.8 : 260 tests exécutés,257 réussis,3 ignorés faute de modèles
réels. Aucun échec ; aucun gain réel Qwen/Windows ou EXE Windows validé ici.
Voix premium, Semantic Morphing et stockage restent différés, sans effacer leurs
spécifications. Ne pas reprendre les travaux audio J2.7 déjà livrés.

Audit historique ciblé : `ABBYWILLY/JARVIS` au commit `b6066c4`,
`JARVIS-SOURCES-v0.5/jarvis_core.py`. L’ancien `stream_chat` et `chat_once`
envoyaient `think:false` par défaut ; ce contrôle manquait au nouveau client.
L’ancien contexte estimait 2,4 caractères/token, tronquait le système et pouvait
garder des messages isolés ; ne pas copier ces limites. Son FTS5/BM25 local est
réutilisable, sans le considérer comme recherche sémantique complète.

J2.8 publiés : lot1 **bbe88af**, lot2 **01ff571**, lot3 **234ff62**.
Lot2 sans migration, index ou dépendance nouvelle ;
les rappels de messages concernent la conversation active. Le lot3 ajoute les
souvenirs approuvés pertinents au même budget partagé, et la consultation FTS5
manuelle interconversations/documents. Aucun souvenir durable n’est créé
automatiquement. Les résumés sont des citations exactes de
phrases originales, jamais une synthèse LLM systématique ; phrases trop longues
omises plutôt que découpées en affirmations trompeuses. L’estimation UTF-8 reste
prudente, pas une tokenisation exacte. Gains de tokens/latence Windows à mesurer.

Lot3 : bouton Mémoire, ajout manuel puis Approuver ; import TXT/MD UTF-8≤256Kio
en attente, aucune lecture automatique de fichiers. Correction sauvegardée puis
nouvelle approbation. Les contenus différents partageant une même clé de sujet
approuvée sont bloqués jusqu’à correction/désactivation : détection structurée,
pas compréhension sémantique complète des contradictions. Doublons exacts/NFC
par type refusés. IDs mémoire jamais réutilisés ; métadonnées des réponses
gardent les citations utilisées même si la mémoire est modifiée/supprimée.
Sauvegardes SQLite locales uniques conservées, aucun modèle/donnée effacé ici.

### Recette Windows J2.8 à réaliser

Dans COMMAND OS : Paramètres → Raisonnement Rapide ; vérifier « 2+2 ? », un suivi
et un rappel ancien. Métriques montre les observations Ollama ; Contexte montre
les sources et la réserve ; Mémoire permet ajout puis approbation explicite.
Les compteurs visibles restent indisponibles si le serveur ne les fournit pas.

Dans PowerShell ouvert dans le dépôt, avec Ollama et un modèle déjà installé :

```powershell
ollama list
.\.venv-voice\Scripts\python.exe -m jarvis.inference_benchmark --model "NOM_EXACT_DE_OLLAMA_LIST" --output .\jarvis-j28-4b.jsonl --context 4096 --max-tokens 256 --repeats 1
```

Remplacer le nom du modèle ; utiliser un autre fichier pour le9B ou une répétition.
Le programme refuse d’écraser un rapport. Corpus synthétique de trois questions,
six appels mesurés et un préchauffage de16 tokens hors comparaison. Modèle,
contexte total, budget de sortie et température identiques ; comparaison combinée
avant(auto/contexte récent) et après(rapide/contexte ciblé), ordre alterné.
JSONL conserve les textes visibles, paramètres et compteurs réels, jamais la
pensée interne. Réponses vides/tronquées/échouées exclues des gains. Le cache et
l’ordre influencent les résultats ; examiner aussi la qualité des réponses.
Aucun modèle téléchargé ; aucun benchmark Qwen réel exécuté dans le cloud.

Compilation Windows inchangée (consulter aussi `VOICE.md`) :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -WithVoice
```

Actions API = `Forbidden` ici ; vérifier les résultats du workflow et l’artefact
sur GitHub. Aucune fusion dans main, aucune recette Windows prétendue.

- Dépôt : https://github.com/ABBYWILLY/JARVIS-0.0.1
- Branche : `feat/jalon-2-voice-presence`. Aucun changement direct de main/force push.
- Dernier état J2.8 : les lots ci-dessus ; les bilans J2.7 ci-dessous sont
  historiques. Retrouver le dernier SHA par `git log -5 --oneline`.
- J2.0–J2.6 et jalon 1 préservés. Lire JALON-2-PROGRESS.md et VOICE.md pour les preuves.

## Lot 2 livré après d90fd5a

COMMAND OS : stats réelles finales Ollama, tokens/s/eval_duration/eval_count/modèle
reçu et TTFT HTTP premier texte visible ; SQLite metadata.generation_metrics,
case Métriques persistante, historique restauré, valeurs absentes = —.
PRESENCE : Chrono masquable/persistant, délais STT/LLM/texte→DAC/fin VAD→DAC,
historique12 tours réels, estimation audio/Bluetooth clairement distinguée.
THINKING plus organique, même maillage fermé exact, halos de même géométrie,
réduction mouvement, silence plat et centre responsive préservés.
75 tests ciblés réussis, aucun ignoré ; HTTP/Tk/SQLite réels, données de test et
audio simulés explicitement. Contrôle visuel Linux, aucune nouvelle validation Windows.
Lot1 conservé. Prochain lot prioritaire : voix premium (sélection vérifiée et un
seul adaptateur), aucun téléchargement volumineux avant accord. Lots4/5 restent
à implémenter. Les anciens paragraphes ci-dessous sont des bilans historiques.

### Lot 3 : blocage documentaire précis, aucun moteur ajouté

Lot2 publié **21a1284**,75 tests ciblés sans ignoré. Consultation Actions refusée
`Forbidden` après push ; aucun EXE Windows de ce lot exécuté ici.
Comparaison officielle du16octobre2026 :
- PocketTTS3.3.0 (tag3dbee45d343d7dddd0d105468d17f8dcba14db3e) : français natif,
  CPU, codeMIT, dépendances déclarées compatibles avec pinsvoix actuels (résolution
  complète non exécutée). Meilleur candidat technique pour préserver la VRAM
  Ollama. VoixEstelleFR documentée, genres non documentés ; licence de chaque voix
  et des poids **non vérifiée**, README contient conditions d’usage et liensHF.
- Qwen3-TTS0.6B CustomVoice (repo022e286b98fbec7e1e916cb940cdf532cd9f488e) :
  français, Vivian/Ryan documentées, codeApache2 ; instruct ignoré pour0.6B.
  Transformers4.57.3 incompatible Hub2.2/Tokenizers0.23.3 actuels. Poids/voix
  non vérifiés ; performances3070 simultanées avecQwen4B inconnues.
- Chatterbox MultilingualV3 existe (5de7a54aa4e5e2baadb0182dde554908b48b85c2),
  français/codeMIT ; chargeur défautV2 donc V3 doit être explicite. Numpy<2,
  Torch2.6 et Transformers5.2 imposés : conflits avec pinsvoix actuels.
  Poids/voix non vérifiés, Windows11/Python3.12 non validés officiellement ici.
GitHubGit/raw accessibles, mais HF(API/raw/Git), kyutai.org et blogsQwen = CONNECT403.
Ne pas confondre licence du code avec celles des poids/voix. Aucune sélection
définitive, installation, audition ou poids téléchargé ; Piper reste inchangé.
Tailles complètes inconnues : wheelPocket86452octets seulement, **horsTorch/poids**.
Ne pas demander un accord de téléchargement sur un volume total inventé.
Question utilisateur posée pour fournir les licences officielles manquantes.
Après preuve : un adaptateur, chargement strict local, préécoute comparative,
tests, taille exacte/accord avant téléchargements, buildWindows premium explicite.
Ne pas installer Qwen/Chatterbox dans le venvPiper en cassant ses pins.

## Optimisation audio — lot 1 livré, recette Windows ouverte

Base0b47997 ; propriétaire : STT/conversation légèrement améliorés, latence encore
perceptible, qualité Piper insuffisante. Ryzen7800X3D/RTX3070 8Go/32Go RAM,
Qwen3.5 Abliterated4B, peu de disque. Aucun chiffre de latence PC fourni.

- Piper préchauffé pendant Ollama et réutilisé après fin normale ; worker chargé
  distinct de lecture active, epochs par commande, arrêt fort sur interruption.
  Arrêt écoute/sommeil/fermeture libèrent le moteur ; profil nouveau invalide le cache.
- Première clause à sa virgule si assez longue ; seuil initial96 conservé.
  Aucun changement aveugle de VAD/garde350ms/threads/GPU.
- Diagnostic STT brut/conservé, fr, un WAV explicite confirmé avec chemin neuf,
  réécoute arrêtable, qualité PCM/indices de bords, cinq références et WER.
  CLI corpus et benchmark Piper avant/après : commandes dans VOICE.md.
- 80 tests distincts réussis, smoke source vocal isolé réussi sous Linux.
  Deux tours→un chargement plutôt que deux contrôlé à moteur simulé, aucun gain
  Windows en secondes ni WER réel annoncé sans poids/enregistrements ici.
  Zéro poids ajouté, maximum625Kio par WAV demandé, rien supprimé.

Prochaine action : sur le PC, exécuter le benchmark Piper de VOICE.md et conserver
le JSON ; compléter ensuite corpus/recette matérielle. Vérifier l’artefact Windows.

Ordre restant, aucun autre lot commencé :
2. Statistiques réelles Ollama sous réponse : modèle/tokens/tok-s/TTFT/durée ; panneau
   temporel PRESENCE compact, masquable, aucune fausse activité biologique/interne.
3. Comparer Chatterbox Multilingual V3/Qwen3-TTS0.6B/Pocket TTS : français, prosodie,
   timbres, ressources avec Qwen4B/3070 ; vérifier licences code/poids/voix, un seul
   candidat et préécoute avant remplacement. Inventaire tailles/chemins et retrait
   confirmé après validation seulement, sans toucher données/Ollama/dépendances partagées.
4. THINKING plus marqué sur visualiseur unique, diagnostic/test du spectre émotionnel.
5. Emoji-aware puis100 vrais symboles : spécification existante ci-dessous à réutiliser.

## État actuel J2.7 — priorités techniques

Fiabilité STT et instrumentation des latences implémentées/testées. Les mentions
historiques d’absence de ces travaux plus bas décrivent l’état avant cette mission.

- Second tour abandonné si Whisper occupé : corrigé avec un seul emplacement
  d’attente, priorité au dernier tour, purge sur nouvelle parole ou suspension.
  Après erreur STT, le tour conservé démarre ; anciennes générations sans effet
  sur statut, PRESENCE ou mesures du tour courant.
- Première phrase longue : limite initiale 96 caractères au lieu de 240, suite
  inchangée, sans perte de texte. Aucun moteur, seuil ou modèle remplacé.
- **Diagnostic micro / STT** : silence PCM, file/inférence STT, attente premier
  texte Ollama, premier segment, chargement/synthèse Piper, premier PCM au DAC
  estimé et total depuis la fin de tour détectée. Ce total exclut le silence VAD ;
  le délai acoustique/Bluetooth n’est pas mesuré. Aucune promesse de gain chiffré.
- 52 tests ciblés distincts réussis, sans ignoré, détails dans le suivi. Les mesures
  d’horloge/périphériques de test ne sont pas des benchmarks du PC Windows.

Prochaine action : vérifier le build Windows de ce commit puis mesurer à froid et
à chaud plusieurs tours sur le PC, en gardant modèle/voix/silence identiques.
Recette : tour bref et long, reprise pendant STT, interruption casque, fin TTS puis
réouverture du micro speakers. Copier les mesures/erreurs du diagnostic si échec.
Ne pas déclarer la validation matérielle terminée sans ces preuves.

## Ne pas recommencer le diagnostic établi

Le propriétaire a confirmé sur Windows 11 : capture USB Condenser/MME réelle,
préécoutes Tom/Siwis et chat Ollama fonctionnels, mais aucune transcription après
« Voix détectée », même à 300/800/1500 ms. Sortie XTREME140 en mode speakers.

Cause reproduite : cancel_speech sur speech_start renvoie mute=False ; le worker
réinitialisait VAD/TurnDetector même sans changement d’état. Le tour était effacé.
Correctif : mute idempotent. Ajouter les diagnostics, fin manuelle et garde 20 s
avec réarmement après silence, reprise après erreur STT. Aucun moteur remplacé,
aucun seuil modifié, pas de réduction du bruit sans preuve ni téléchargement implicite.
PRESENCE conserve un seul maillage spline : amplification visuelle indépendante,
attaque rapide/retour doux ; expressivité persistante 0–100 %, défaut 65 %.

61 tests ciblés distincts réussis sous Linux/X virtuel (59 puis 11 dont 9 communs).
SOXR réel 44,1/48 kHz et Silero ONNX réel testés. Les séquences de parole/bruit
utilisent des probabilités contrôlées et STT simulé, pas un vrai microphone.
Ne pas déclarer la conversation matérielle corrigée avant essai du nouvel EXE.

## Prochaine opération concrète

1. Vérifier Actions **Windows Jarvis** sur le dernier commit de cette branche.
   API Actions refusée ici (`Forbidden`), mais le proxy Git permet le push.
   Workflow existant : tests complets, build vocal, smoke EXE, artefact
   `Jarvis-Jalon2-Windows-x64-<commit>`. Ne pas demander de token pour Git.
2. Télécharger cet artefact vert et préserver l’ancien EXE et les données.
   Build manuel : `powershell -NoProfile -ExecutionPolicy Bypass -File
   .\scripts\build-windows.ps1 -WithVoice` → `dist\jalon-2\Jarvis.exe`.
3. Dans COMMAND OS ouvrir **Diagnostic micro / STT**, activer l’écoute puis parler
   et laisser le silence. Attendu : speech_start → turn_end (silence) → transcribing
   → stt_complete + texte. Vérifier aux trois durées, bruit seul/avec parole,
   phrase longue, réponse Ollama/TTS puis reprise du micro speakers.
4. Si blocage : relever RMS, probabilité, état, durée, fréquence PCM/512 échantillons
   et événements/exception. Si VAD reste haute, bouton **Terminer le tour courant**.
   Ne pas attribuer le problème au ventilateur sans ces observations.
5. Ajuster **PRESENCE → Réglages → Expressivité de l’onde (%)** : vérifier la
   persistance, le silence immobile, les courbes et le centrage/DPI sur Windows.
   Compléter les validations Windows dans le suivi après preuve seulement.

Pas de microphone ni de Windows cloud ; aucun EXE Windows de ce correctif exécuté
ici. Préserver les modèles, SQLite v2 et sauvegardes v1. Ne pas fusionner automatiquement.

## Extension J2.7 en attente — Emoji-aware Speech & Semantic Morphing

Demande du 16 octobre 2026. **Non commencée : 0/100 représentations implémentées,
0/100 validées**, aucune galerie ni séparation emoji/TTS livrée. Préalable imposé
par le propriétaire : corrections STT et latence J2.7 implémentées, testées et
enregistrées dans Git avant cette extension. STT : correctif `a12ca3f` avec preuves
ci-dessus ; travaux/mesures de latence J2.7 non attestés dans le dépôt. Ne pas
considérer le seul temps STT du diagnostic comme une mesure de latence bout en bout.

Après ce préalable, livrer par lots cohérents testés et committés :

- Séparer texte original, texte TTS et événements visuels avec positions dans le
  texte original. Préserver intégralement COMMAND OS, sous-titres et SQLite.
  Retirer seulement les séquences emoji du TTS avant toute conversion descriptive,
  gérer variantes, modificateurs, ZWJ, drapeaux, touches et caractères invisibles
  associés sans supprimer le français, les mots explicites (« une fusée »),
  la ponctuation utile ou la prosodie. Aucun filtrage des noms d’emojis dans le
  texte ordinaire : leur origine doit déterminer leur traitement.
- Sélectionner 100 emojis distincts d’après une source vérifiée : priorité
  https://www.unicode.org/emoji/frequency.html et complément
  https://home.unicode.org/emoji/emoji-frequency/ . Sources proposées, **pas encore
  étudiées ni classement retenu**. Vérifier date des données, ordre, méthode,
  représentativité et limites ; comparer toute source plus récente solide.
  Ne pas présenter une page consultée récemment comme des données mondiales récentes.
  Variantes/teintes de peau peuvent partager un dessin, sans gonfler le compteur.
- 100 formes vectorielles légères, reconnaissables et réellement animées, intégrées
  au programme. Mutualiser yeux/bouches/cœurs/larmes/mains/flammes/étoiles.
  Exemples initiaux proposés : ❤️ 💡 🚀 ✨ ⚠️ ✅ ❌ 😊 ; la sélection finale suit
  la source et les lots livrés, jamais des placeholders comptés comme terminés.
  Emoji inconnu : texte conservé, retiré du TTS, aucune transformation inventée.
- Même visualiseur UNIQUE : noyau → symbole holographique arrondi → noyau,
  monochrome cyan ou Emotional Spectrum, centré et responsive, transitions fluides
  et courtes, sans duplication, bitmap, GIF, pack externe ni clignotement.
- Déclencher depuis les callbacks PCM et la portion de phrase correspondante ;
  conserver la correspondance malgré le nettoyage du texte TTS. Si pas d’alignement
  mot à mot, documenter une approximation bornée et son erreur, sans synchronisation
  parfaite annoncée. Regrouper les emojis adjacents et limiter la cadence ; aucune
  animation concurrente. Interruption : annuler immédiatement l’actuel et les
  événements en attente, priorité à l’écoute, aucun retour tardif d’ancienne génération.
- Préférences persistantes : Semantic Morphing activé/désactivé, intensité
  discret/normal/expressif, réduction du mouvement (respecter aussi celle existante).
  Aucun ralentissement sensible du TTS, modèle ou téléchargement supplémentaire.
- Galerie de prévisualisation individuelle des 100 formes. Tests paramétrés pour
  chaque entrée : Unicode reconnu, véritable géométrie associée, absence de lecture
  descriptive, transition et retour au noyau. Tests français/Unicode complexe,
  original intact, ponctuation, synchronisation approximative, interruption et
  annulation, préférences, responsive et non-régression du visualiseur principal.
  Publier nombre exact implémenté/validé et liste exacte restante après chaque lot.

Prochaine mission prioritaire : établir puis traiter les latences J2.7 et compléter
la recette vocale Windows, avec mesures et commits. Ne pas engager les 100 tracés
tant que ce préalable n’est pas rempli ; conserver cette extension dans la reprise.
