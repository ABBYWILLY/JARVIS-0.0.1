# LOT 5 — Cognitive HUD 1.0

Base : `1985a99`, branche `feat/jalon-2-voice-presence`. L’utilisateur juge le
LOT 4 satisfaisant et confirme la validation visuelle GPU 3.1. Les mesures
combinées RTX 3070/Ollama/voix restent à effectuer. Aucun modèle ni changement
artistique ajouté dans cette mission. Demande complète : [spécification](COGNITIVE-HUD-SPEC.md).

## Inventaire initial

| Capacité | État initial | Réemploi / changement minimal |
| --- | --- | --- |
| États conversation/audio | Partiels, propriétaires App/VoiceControls | Contrat observable commun, observations aux événements acceptés |
| TTFT, débit, durée, tokens | Présents | `metrics.py`, événements Ollama, timing DAC existants |
| HUD Canvas/GPU | Statuts opérationnels présents | Résumé périphérique parent, pas de calcul métier dans les renderers |
| Répéter/reprendre/continuer | Présents LOT 4/C1 | Ajouter une portée de sélection sans second moteur |
| Sélection Rich Text | Affichage/copie présents ; offsets source absents | Mapping opt-in fiable, une réponse identifiée, refus expliqué si ambigu |
| Contexte/mémoire/provenance | Inspecteurs et métadonnées présents | Différencier recherche, insertion, réception HTTP et références explicites |
| Préférences/navigation | SQLite, cinq familles, favoris présents | Un seul éditeur HUD et mêmes propriétaires de valeurs |

## Architecture

`App` conserve le contrat observé. `VoiceControls` publie uniquement après ses
gardes de génération et échéances DAC ; les états graphiques et couleurs ne
déterminent jamais l’activité cognitive. Les vues reçoivent une projection sans
souvenirs, instructions, chemins ni texte de conversation. Aucun second appel
Ollama ou sondage SQLite n’est nécessaire pour afficher un statut.

Le journal est borné, temporaire en RAM, sans PCM ni copie des conversations.
Les générations périmées sont rejetées. Erreur/annulation/interruption restent
observables ; elles ne modifient jamais les permissions. Les chevauchements
(inférence + Piper + parole) sont représentés comme activités simultanées.

Les détails privés se consultent explicitement dans l’inspecteur existant.
Présence dans le contexte, réception HTTP et usage réel ne sont pas synonymes :
aucun indicateur ne prétend connaître le raisonnement ou l’usage interne Ollama.

## Validation

Résultats et mesures ajoutés à chaque sous-lot. La CI Windows compile l’EXE ;
les essais acoustiques, DPI multiécran et mesures RTX physiques restent une
recette utilisateur, jamais une conséquence d’un test simulé vert.

5A : contrat pur, 14 tests réussis (générations, concurrence, bornes, confidentialité,
préférences). Aucune interrogation de périphérique/SQLite ou minuterie créée.


## 5B — intégration et contrôle architectural

Même contrat consommé dans COMMAND OS, Canvas et GPU ; affichage désactivable,
Minimal/Standard/Diagnostic, réglages dans le Centre de contrôle existant.
Les observations viennent des propriétaires App et VoiceControls, après leurs
gardes de génération et aux échéances PCM. Les activités peuvent se chevaucher.
Journal consultable explicitement ; aucune copie de souvenirs/instructions au GPU.

Contrôle avant 5C/5D : tests de flux Tk 9/Tk 8.6 réussis ; 100 rafraîchissements
inchangés ne créent ni snapshot supplémentaire, ni lecture SQLite, ni timer.
Vues masquées mises en cache ; durées rafraîchies au plus une fois par seconde
via la boucle existante. Tests OpenGL : géométrie centrale et pied de fenêtre
identiques avec/sans HUD, atlas réutilisé et allocation propre inchangée.
Les séquences audio, interruptions et générations périmées sont couvertes.
Une fixture qui injectait directement un faux statut de vue a été corrigée
pour alimenter le vrai propriétaire App, qui restait la source de vérité.
La fluidité RTX réelle ne se déduit pas de Mesa et reste à mesurer sur le PC.


## 5C — actions sur passage

Dans une réponse : sélectionner, clic droit ou Maj+F10, puis Lire/Répéter,
Expliquer/Développer/Résumer, Continuer ou Copier. Les préférences HUD permettent
de masquer ces entrées ; Ctrl+C et copie de la réponse originale restent présents.
La projection source est construite seulement à l’action, avec les vrais offsets
du scanner : aucun alignement deviné par recherche d’un mot répété. Un message,
une révision et une empreinte sont vérifiés contre l’archive ; sélections ambiguës,
inter-messages ou trop longues refusées avec explication. Limites : réponse65 536
caractères, sélection8192. Tables, code, liens, titres et Unicode sont couverts.

Lecture/relecture réutilisent Piper et les préférences LOT4, sans ouverture micro
ni Ollama. Reprends reste dans le périmètre sélectionné après interruption, au
début du segment PCM approximatif ; une origine modifiée/supprimée est refusée.
Pendant streaming, copier reste possible ; les autres actions demandent de
terminer/arrêter la génération. Continuer cible seulement la fin de la dernière
réponse et réutilise C1. Les trois demandes à Ollama contiennent la sélection
exacte dans une donnée JSON explicitement citée, jamais dans un rôle système.
Leurs deux messages archivés conservent IDs, offsets et empreinte d’origine ;
le modèle, les budgets et les permissions existants restent applicables.

Projection synthétique2780caractères : moyenne6,14ms/P957,30ms ; aucun travail
supplémentaire par frame ou callback audio. Les tests et essais matériels sont
rapportés séparément, sans déduire une qualité acoustique du test de sélection.


## 5D — provenance observable et réception

L’inspecteur de contexte existant reste unique et se rafraîchit sur ouverture
explicite. Il sépare les candidats récupérés mais exclus, les extraits préparés,
les références textuelles formelles reliées à une source connue, et l’acceptation
HTTP. Une réponse contenant un marqueur inconnu n’obtient aucune source inventée.
L’inclusion et même HTTP200 ne prouvent ni utilisation d’un souvenir, ni vérité,
ni succès de génération. Les archives anciennes indiquent ce qui n’a pas été
observé ; les réglages actuels ne reconstituent jamais une instruction passée.

Instructions système effectives : capture privée bornée65 536caractères et
empreinte, uniquement depuis les messages réellement préparés. Aucun extrait,
chemin ou instruction n’est envoyé dans le HUD GPU. Les souvenirs modifiés,
supprimés ou remplacés sont signalés sans réécrire leur extrait historique.
Pas de seconde mémoire ni nouvelle télémétrie. Statuts HTTP observés après200,
jamais avant connexion ni sur refusHTTP ; une erreur de flux après200 reste
un échec de génération avec acceptation observée.

99 tests ciblés :98 réussis,1 modèle réel opt-in ignoré,24,974s. Le contrôle
Windows intermédiaire a identifié une ligneHUD supplémentaire dépassant les
boutons à560×400/250%DPI et une fixture audio sans propriétaireApp ; corrigés,
sans réduire les assertions de visibilité ou désactiver de tests. En mode compact,
le HUD réutilise le statut existant. Les variables/callbacks Tk supplémentaires
sont libérés explicitement à la fermeture ; validation Windows finale à suivre.


## 5E — validation et limites

Suite complète Linux/Tk9/EGL réel :948 exécutés,939 réussis,9 ignorés
(composants audio natifs absents et essais de modèles réels opt-in),115,439s.
La campagne Tk8.6 a révélé un dépassement d’un pixel du statut Mini : le calcul
réserve maintenant le padding/bordure natifs du Label, sans assouplir le test.
Le test Mini ciblé passe après correction. Une erreur STT tardive ou d’ancienne
génération reste dans le diagnostic local et ne remplace plus le HUD de parole.
Le résumé de l’inspecteur est correctement enfant de son Canvas, donc visible
et limité à sa zone de défilement ; testé à100/250%DPI sans recouvrir les sources.

Preuves réelles et rapports : [vidéo, captures et mesures](COGNITIVE-HUD-EVIDENCE.md).
21PNG, vidéo13s, vrai menu de sélection et trace de lecture locale ; données
simulées annoncées et aucun micro/modèle réel ouvert. Processus App au repos,
mesure courte2s : CPU médian14,129ms avant /13,909ms HUD minimal, RSS35,680 /
35,918Mo. Aucune réduction significative démontrée. Pas de nouvelle minuterie.
Mesa logiciel, atlasHUDinchangé :660480octets. Pas de mesure VRAM physique,
watts, impact TTFT/Piper ou charge combinée RTX/Ollama/voix à distance.

La CI de5D `bef37b4` est verte (applicationWindows40890560484 et prototype
40890560381). Suivre les deux workflows du dernier commit5E pour l’EXE final.
Pas de nouveau modèle, framework ou dépendance. Canvas reste une alternative
permanente ; shaders, sphère, anneaux et géométrieGPU3.1 sont conservés.

## Recette sur le PC Windows

1. Ouvrir **Centre de contrôle → Interface → Cognitive HUD**. Comparer Minimal,
   Standard et Diagnostic, désactiver puis réactiver. Réouvrir JARVIS : valeurs
   conservées. En petite fenêtre, le statut compact utilise la ligne existante.
2. Faire une question texte puis vocale : vérifier attente, génération, voix,
   parole PCM et chevauchement. Interrompre : aucune ancienne notification ne
   doit rétablir une réponse annulée. Vérifier micro coupé, silence et erreurSTT.
3. Sélectionner du gras, un lien, une table, du code et des emojis : clic droit
   ou Maj+F10. Lire/Répéter ne lancent pas Ollama ; l’option de code reste respectée.
   Interrompre puis Reprends : la lecture reste dans le passage. Vitesse et voix
   installées se règlent dans l’éditeur vocal existant, sans nouveau moteur.
4. Expliquer/Développer/Résumer : une nouvelle demande citant le passage est
   archivée. Vérifier modèle/budgetC1 et annulation. Continuer seulement sur la fin
   de la dernière réponse. Une source changée ou une ancienne sélection doit
   être refusée ; pendant génération, copie possible et autres actions différées.
5. Ouvrir **Contexte** : comparer récupéré/inclus/référence explicite, instructions
   effectives et acceptationHTTP. Les détails privés doivent rester dans cet
   inspecteur, jamais sur PRESENCE. Modifier/supprimer un souvenir : l’extrait
   historique reste distinct de son état actuel. Vérifier aussi un ancien échange.
6. Répéter avec Canvas, GPU, Mini, plein écran, DPI100/150/200/250% et deux écrans.
   Tester clavier, réduction des mouvements, GPU indisponible/repli et bascule
   pendant parole, sans réouverture micro/Piper ni déplacement du noyau.
7. Comparer même requête/modèle, HUDmasqué/Minimal/Diagnostic : métriques TTFT,
   transcription, premierPCM estimé et temps de frameF9. Mesurer CPU/RAM/VRAM
   avec Ollama et voix sur RTX3070 ; le délai acoustique Bluetooth reste séparé
   des estimations DAC. Ce test physique du LOT5 est encore à réaliser.

Sources : même procédure d’installation que [VOICE.md](VOICE.md), puis `python run.py`.
Compilation Windows : `.\scripts\build-windows.ps1 -WithVoice -WithGpu` ;
les artefactsGitHubActions comprennent `Jarvis.exe`, sonSHA-256 et les diagnostics.
Aucun travail sur main, LOT7 ou fonctions agentiques.


Vérifications finales complémentaires après cadrage natifMini :27 tests
pertinents réussis en6,246s ; campagne Tk8.6 complète ciblée81/81 réussis en
31,751s (100/200/250%DPI, sélectionUnicode, provenance et navigation compris).
Empreintes des10sources et23artefacts de preuve vérifiées avant publication.
