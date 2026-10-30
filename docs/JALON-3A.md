# Jalon 3A — outils locaux bornés

Branche `feat/jalon-3a-tools`, issue de `df0e84a`. `main` et la branche du jalon 2
ne sont ni modifiées ni fusionnées. [Demande](JALON-3A-SPEC.md).

## 3A.1 — audit et contrats

Le parcours reste `App.send → worker → Ollama → App.poll`, avec SQLite/Tk dans
le parent. Le nouvel exécuteur d'outils est un worker de lecture distinct, à
concurrence un, sans deuxième orchestrateur conversationnel. Les demandes
temporelles entières et non ambiguës passent directement à l'horloge ; les
autres conversations gardent C1, les modèles et budgets existants.

Ollama fournit des sorties structurées via le champ HTTP `format` (JSON Schema).
Une proposition explicite d'outil sera une requête locale bornée, jamais du
code à exécuter. Les chunks de conversation ordinaires restent du texte. Une
proposition n'est ni une autorisation ni une exécution. La disposition `none`
signifie qu'aucun outil n'est proposé ; quatre outils seulement sont enregistrés.

Frontières retenues : registre immuable et arguments stricts ; politique hors
LLM ; sélection de dossier conservée seulement en RAM ; exécuteur isolé avec
identifiant/génération, délais et files bornés ; résultats vérifiés et limités ;
journal minimal dans SQLite existant. Aucun shell, PowerShell, installation,
écriture de fichier, réseau libre, vision ou orchestration autonome.

Les modèles déjà installés restent sélectionnables, standard ou abliterated :
la politique de permissions est la même. Whisper et Piper sont actuellement
CPU ; aucune nouvelle VRAM modèle n'est requise. Les états d'outil seront
projetés dans le HUD existant, sans nouveau renderer ni boucle graphique.

Les résultats d'outil restent des données non fiables. Ils ne sont pas réinjectés
automatiquement dans le contexte LLM ; les observations d'horloge archivées ne
deviennent pas une date courante persistante. L'historique original est conservé.

Windows ne fournit pas nécessairement une base IANA à `zoneinfo`. Une petite
base `tzdata` empaquetée est prévue pour les conversions explicites hors ligne ;
la zone par défaut reste celle du système Windows, jamais la France imposée.

Risque fichier : les vérifications textuelles de chemin seules ne suffisent pas.
Les lectures utiliseront des handles/descripteurs, refuseront liens/reparse
points/chemins spéciaux et vérifieront les identités. Un processus `spawn` est
une frontière de cycle de vie, **pas un bac à sable de sécurité**.

Réutilisés : `Worker`, `Event`, gardes d'annulation LOT 7, `Store`/sauvegardes,
`CognitiveState`, `SettingsForm`, traitement Rich Text/TTS/PCM. Les profils
vocaux, l'alternative Canvas/GPU et les shaders approuvés restent préservés.
Full-duplex haut-parleurs/AEC reporté explicitement, sans changement de seuil.

Les étapes suivantes consignent tests, limites et publication ; les tests
logiciels/CI seront distingués des essais physiques Windows 11/RTX/micro.

Contrats initiaux : 11 tests réussis (0,045 s), schémas fermés, champs inconnus,
clés JSON dupliquées, valeurs non finies, appels multiples et outils inexistants
refusés. Définitions et propositions immuables, copies de transport validées,
vérification explicitement distincte d'une vérité générale. Les deux workflows
existants suivent la nouvelle branche, sans changement de `main`.
