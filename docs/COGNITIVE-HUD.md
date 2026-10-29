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
