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
