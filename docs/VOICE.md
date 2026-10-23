# Jalon 2 — installer, utiliser et vérifier la voix

Le chat reste utilisable sans dépendances vocales. Le microphone est fermé au
lancement. Aucun poids STT/TTS n’est téléchargé par l’application. Les modèles
Ollama restent indépendants des modèles vocaux.

## Installation Windows 11 (une fois, accès Internet nécessaire)

Conservez votre EXE du jalon 1 et sauvegardez le dossier `%LOCALAPPDATA%\Jarvis`
avec JARVIS fermé. Installez Python 3.12 x64 (lanceur py) et le redistribuable
[Microsoft Visual C++ x64](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)
si les DLL de CTranslate2/ONNX ne sont pas disponibles.

Depuis le dossier du dépôt ou de l’artefact décompressé :

```powershell
py -3.12 -m venv .venv-voice
.\.venv-voice\Scripts\python.exe -m pip install -r requirements-voice.txt
.\.venv-voice\Scripts\python.exe scripts\install_voice_models.py
```

Cette dernière commande récupère seulement les fiches de licence dans
`%LOCALAPPDATA%\Jarvis\models\licenses`. Lisez-les. Pour installer les poids après
acceptation de leurs conditions :

```powershell
.\.venv-voice\Scripts\python.exe scripts\install_voice_models.py --accept-model-licenses
```

Dans l’artefact GitHub, les chemins `scripts/` et `docs/` sont conservés. Si vous
avez déplacé l’installateur à côté de l’EXE, utilisez simplement son chemin réel.
Le helper est autonome et n’a pas besoin du code source JARVIS.

Le STT par défaut est **Whisper small**, CPU int8, quatre threads. Pour une machine
plus lente, ajouter `--stt-size base` ou `tiny` pendant une nouvelle installation.
Les modèles sont placés sous `models\whisper` et `models\piper` ; leur manifeste
conserve les révisions et SHA-256. Chaque téléchargement est vérifié contre les
métadonnées du dépôt (SHA-256 LFS ou identifiant Git du fichier), sans désactiver TLS.
Un dossier de modèles déjà existant est préservé : pour réinstaller, choisir une
nouvelle destination avec `--destination C:\chemin\modeles`, puis la sélectionner
sous **Voix / périphériques**. Les poids ne sont pas inclus dans l’EXE ou l’artefact.

Lancer depuis les sources :

```powershell
.\.venv-voice\Scripts\python.exe run.py
```

Ou lancer l’EXE **vocal** `dist\jalon-2\Jarvis.exe` / celui de l’artefact Jalon2.
Il embarque son runtime ; le venv n’est nécessaire que pour l’installation des
modèles et les tests sources. Après installation, aucune connexion cloud n’est requise.

## Utilisation

1. Démarrer Ollama et choisir le modèle local déjà installé.
2. **Voix / périphériques** : choisir entrée/sortie, Tom ou Siwis, vitesse et dossier
   modèles si personnalisé. Un nom enregistré disparu produit une erreur explicite.
3. **Préécoute réelle** lit un exemple sur la sortie choisie ; Arrêter coupe la lecture.
4. **Activer l’écoute**, puis accepter l’accès au micro. Autoriser aussi les applications
   de bureau dans Paramètres Windows → Confidentialité et sécurité → Microphone.
5. Parler, puis laisser environ 800 ms de silence. La transcription finale est envoyée
   automatiquement ; le STT ne fournit pas de transcription progressive dans ce moteur.
6. **headphones / casque** permet de reprendre la parole pendant JARVIS : la VAD
   déclenche l’arrêt et invalide les anciens segments. Utilisez un vrai casque.
7. **speakers / haut-parleurs**, par défaut : micro suspendu pendant TTS et 350 ms après.
   Arrêt manuel disponible ; **pas de full-duplex ni d’AEC haut-parleurs promis**.
8. **Arrêt d’urgence** coupe micro, lecture et génération. **Sommeil** fait de même,
   réduit PRESENCE à un point/trait et suspend l’animation. Le réveil ne rouvre pas le micro.

**PRESENCE** ouvre une fenêtre dédiée. F11 active le plein écran, Échap le quitte,
Ctrl+Espace bascule l’écoute avec consentement. Fond noir par défaut, choix libre
et rétablissement instantané ; Éco/Équilibré/Cinématique, réduction du mouvement et
sous-titres sont persistants. Les transcriptions restent des overlays : le centre
ne se déplace pas. Fermer PRESENCE ne ferme pas la conversation ; désactivez le micro
explicitement si vous ne souhaitez plus être écouté.

Dans **PRESENCE → Réglages**, **Expressivité de l’onde (%)** va de 0 à 100,
65 par défaut. L’amplification non linéaire et le lissage sont purement visuels :
aucun changement du PCM, du gain micro, de la sensibilité VAD ou de Whisper.
L’onde reste une spline du signal réel ; signal nul ou périmé → ligne plate.

## Diagnostic micro → VAD → STT sur Windows

Dans COMMAND OS, ouvrir **Diagnostic micro / STT**, puis activer l’écoute.
La fenêtre affiche le RMS micro réel (même si l’onde est plate), la probabilité
Silero, l’état parole/silence, la durée du tour, les fréquences PCM et les trames
de 512 échantillons à 16 kHz. Mesures au plus 4 fois/s, trace des 32 événements
récents en mémoire seulement, aucun fichier audio ni téléchargement.

Parler brièvement puis attendre le silence configuré : la trace doit montrer
`speech_start → turn_end (silence) → transcribing → stt_complete`, avec le texte
reconnu et le temps STT. La transcription arrive dans COMMAND OS ; si aucun
modèle Ollama n’est choisi, elle est conservée dans la saisie.

Si la VAD reste haute après l’arrêt de la parole, noter RMS/probabilité/durée.
**Terminer le tour courant** envoie explicitement le segment au STT. La limite
existante de 20 s envoie aussi le segment, puis attend un vrai silence avant de
réarmer pour éviter des transcriptions répétées de bruit. Le bouton ne crée pas
de segment au repos. Cette limite peut couper une intervention de plus de 20 s :
faire des pauses. Aucun réducteur de bruit ajouté sans mesure justifiant son usage.

Une erreur STT apparaît avec son type/message et sa durée ; l’écoute reste active
pour le tour suivant. Une erreur capture/VAD indique l’étape et nécessite de
réactiver l’écoute. En cas d’échec sur le PC, copier le contenu de cette fenêtre
(il peut contenir les transcriptions privées) avec la fréquence et le périphérique,
sans supposer que le ventilateur est la cause. Tester aussi un tour avec et sans
ventilation, Tom/Siwis en préécoute et le retour du micro après TTS en mode speakers.

### Mesures de latence J2.7

Le même diagnostic affiche en millisecondes le silence PCM de fin de tour,
l’attente en file Whisper, son temps de transcription, l’attente du premier texte
Ollama, le délai avant la première phrase TTS, le chargement Piper, sa première
synthèse et l’arrivée prévue du premier PCM au DAC. La mesure **fin de tour
détectée → premier PCM** commence après le silence VAD : celui-ci est affiché
séparément. Les temps Ollama incluent la préparation locale, le processus et
le retour à l’interface ; ce ne sont pas des temps GPU purs.

Les horodatages viennent des processus et callbacks audio réels. La date DAC est
une **estimation PortAudio**, qui ne mesure pas le délai acoustique ou Bluetooth
de XTREME140. Aucun gain réel en secondes n’est annoncé sans mesure sur le PC.
Une mesure absente reste absente ; les données ne sont ni stockées ni envoyées.

Si Whisper est occupé, le dernier tour complet est conservé dans un seul emplacement
en attente au lieu d’être abandonné. Une nouvelle prise de parole remplace le tour
en attente devenu obsolète ; une suspension du micro le purge. L’inférence déjà
en cours peut se terminer, mais son ancien résultat ne remplace pas le tour courant.
Arrêt d’urgence ferme les processus. Une longue phrase initiale sans ponctuation
part désormais au TTS à une limite de 96 caractères au lieu de 240 (coupure sur
espace si possible) ; la suite conserve la limite précédente, sans perte de mots.

Pour comparer sur Windows : même modèle Ollama, même voix, même microphone et
même réglage de silence ; relever plusieurs tours après démarrage à froid puis
à chaud dans **Diagnostic micro / STT**. Tester aussi une reprise pendant STT,
une interruption au casque et le retour d’écoute après TTS en mode speakers.
Conserver les valeurs réelles et les erreurs plutôt qu’une estimation de performance.

Le spectre adaptatif est une **estimation lexicale prudente**, sans appel LLM et sans
prétention de ressentir une émotion. Ambiguïté → cyan, inertie de 3 s, négation simple.
Les menus, permissions et alertes ont leur propre spectre opérationnel indépendant.
Les profils JARVIS/UNHINGED changent une instruction système visible/modifiable,
jamais les permissions. Aucun outil système n’est activé.

Les sous-titres commencent sur les callbacks du PCM envoyé au périphérique, avec
prise en compte de l’horloge de sortie. Les groupes de mots sont une **approximation
par durée**, signalée dans l’interface, sans timestamps mot à mot. Le bouton Copier
copie le groupe visible ; COMMAND OS conserve l’intégralité des textes dans SQLite.
Les fichiers audio micro ne sont pas enregistrés par défaut. Le diagnostic peut
exporter un unique WAV sur demande explicite. La base texte reste non chiffrée.

## Compilation et récupération de l’artefact

La case **Menu → Conversation → Métriques de génération** masque/affiche
les statistiques sous chaque réponse, avec préférence persistante. Elles sont
masquées initialement ; un choix antérieur est conservé. Tokens et durée
de génération proviennent de `eval_count`/`eval_duration` d’Ollama ; tokens/s =
tokens ÷ durée en secondes. Le **TTFT reçu** est le délai HTTP jusqu’au premier
texte visible (chargement/réflexion/réseau inclus), pas le premier token interne.
Les valeurs absentes restent `—`. Les mesures sont conservées avec la réponse
dans SQLite, y compris les observations disponibles après arrêt/erreur.

Dans PRESENCE, **Chrono** masque/affiche le moniteur latéral sans déplacer le noyau.
STT/attente LLM sont des temps observés ; texte→son et fin de tour→son utilisent
l’estimation DAC PortAudio. Parole→son ajoute le silence VAD : estimation de fin
de parole, pas mesure acoustique/Bluetooth. La courbe montre les 12 derniers tours
mesurés, sans mouvement inventé ni donnée biologique. Le THINKING plus organique
reste limité au traitement réel ; réduction du mouvement et silence plat conservés.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -WithVoice
```

Sortie séparée : `dist\jalon-2\Jarvis.exe` et SHA256 ; l’ancien `dist\Jarvis.exe`
n’est pas écrasé. Sans `-WithVoice`, le build reste textuel, également dans le dossier
Jalon2. Le workflow **Windows Jarvis** compile le build vocal sur chaque push de la
branche Jalon2, PR, main et lancement manuel. Dans GitHub → Actions → exécution verte,
télécharger **Jarvis-Jalon2-Windows-x64-<commit>**, décompresser, conserver les chemins.
Ni installateur Windows ni signature binaire ajoutés à ce jalon.

La CI vérifie les imports natifs, le VAD ONNX livré, la suite de tests, puis deux
smoke tests de l’EXE. Elle ne dispose pas de microphone, de modèles STT/TTS installés
ni du PC cible : **un artefact vert ne valide pas la qualité vocale ou le barge-in**.

## COMMAND OS NEO — lecture et présentation

**Menu → Lecture et typographie** : police installée, taille9–24, échelle75–175 %,
densité compacte/confortable, police monospace du code/tableaux et accents0–100 %.
**Enregistrer** applique et conserve ces choix ; **Réglages d’origine** rétablit
immédiatement les préférences de lecture, sans toucher à la voix, PRESENCE ou aux
archives. La grande police reste appliquée à la conversation ; en petite fenêtre,
la saisie est plafonnée à18points pour garder Envoyer/Arrêter accessibles.

Markdown rendu : titres, gras/italique/combinés, listes imbriquées, citations,
séparateurs, liens HTTPS confirmés, code inline/blocs, Unicode et emojis.
Extensions : `~~barré~~` (délimiteurs doubles aux limites de mots), `++souligné++`,
`==surligné==` et tableaux textuels monospace. Les tildes d'une notation technique
intramot restent littéraux. Pas de styles HTML ou de couleurs arbitraires exécutés.
Les tableaux peuvent se replier dans une petite fenêtre ; les formules simples
restent textuelles, sans composition LaTeX ni prétention de prise en charge complète.

Pendant le streaming, seule la réponse active est modifiée ; sélection, copie et
défilement restent natifs. Clic droit/Ctrl+Maj+C copie la réponse originale ; Ctrl+C
copie la sélection rendue. Les marqueurs sont retirés uniquement de la présentation
et du texte vocal, jamais de SQLite. Le code reste non lu par défaut (résumé explicite).
Les surfaces arrondies sont statiques, sans image, moteur supplémentaire ou animation.

Recette Windows : demander une réponse avec titres, liste imbriquée, tableau,
code, citation, `~~barré~~`, `++souligné++`, `==surligné==`, accents français et 😊.
Sélectionner/copier un passage pendant le streaming, faire défiler vers le haut,
changer les réglages, redémarrer et vérifier la conservation des choix/source.
Tester Tab/focus, F6/F7/F8, paysage/portrait, 560×400 et DPI100/150/200/250 %,
puis la lecture Piper réelle. Cette recette humaine reste à effectuer sur le PC.

## Recette réelle sur votre Windows

### LOT 1 Cognitive & Presence — validation matérielle en attente

La CI et les tests PCM de laboratoire ne valident pas votre microphone physique.
Ne pas poursuivre le LOT 2 avant cette recette. Ne changer ni seuil VAD ni modèle
pour masquer un problème de capture. Aucun enregistrement audio automatique.

1. Dans Windows 11, vérifier **Paramètres → Confidentialité et sécurité →
   Microphone → Autoriser les applications de bureau** et le niveau/mute du micro.
2. Dans JARVIS, **Menu → Voix / périphériques**, sélectionner explicitement votre
   USB Condenser et son API (MME si c'est votre configuration). Garder votre modèle
   Ollama et vos modèles Whisper/Piper installés. Activer l'écoute en l'autorisant,
   puis **Diagnostic micro / STT**. Aucun téléchargement n'est lancé.
3. Vérifier **Sélectionné / Ouvert**, API, index et fréquence native → 16000 Hz.
   L'étape d'initialisation STT/VAD n'est pas une ouverture confirmée du micro.
   Le compteur de trames doit augmenter et l'âge PCM rester récent. `—` signifie
   aucune mesure actuelle ; `0.00000` signifie de vrais échantillons PCM nuls.
4. Rester silencieux cinq secondes, parler trois secondes, rester silencieux.
   Noter les trois RMS : ils doivent monter pendant la parole et revenir au bruit
   ambiant, pas nécessairement à zéro. Dans PRESENCE, l'onde doit suivre ces mêmes
   variations même sous le seuil VAD. Aucun mouvement n'est synthétisé au repos.
5. Lire « Bonjour JARVIS, quelle heure est-il ? », puis attendre en silence.
   Vérifier dans la trace **speech_start → turn_end → transcribing → stt_complete
   → transcript**, le résultat français, puis la réponse Ollama dans COMMAND OS.
   Tester aussi une phrase longue et une seconde phrase après une erreur éventuelle.
   Si le modèle est absent/occupé, la transcription est conservée dans la saisie.
6. En cas d'échec, relever Sélectionné/Ouvert, RMS silencieux/parole, VAD, âge PCM,
   étape, fin de tour et dernière erreur conservée. Le diagnostic distingue absence
   de PCM, PCM nul, signal sans VAD, attente de fin de tour, STT et transcription
   reçue sans réponse. « Terminer le tour courant » sert au diagnostic d'un VAD
   bloqué ; cela ne prouve pas que sa fin de tour automatique fonctionne.
   L'export du prochain tour WAV reste facultatif et nécessite votre accord.
7. Vérifier **Menu / Chat / PRESENCE / Arrêt** à 1100×620 (paysage), 620×900
   (portrait), 640×480 et 560×400, puis DPI Windows 100/150/200/250 %. Tester F6
   (menu), F7 (PRESENCE), F8 (conversation), Tab, défilement et barre rétractable.
   Pendant Piper en mode speakers, aucun événement micro ancien ne doit réactiver
   l'onde ; au casque, l'interruption vocale réelle doit rester prioritaire.

Consigner le résultat et les erreurs avant de déclarer ce LOT 1 validé sur matériel.
Compilation verte et démarrage de l'EXE en CI ne remplacent pas cette recette.

Tester d’abord le texte, le redémarrage et votre Qwen abliterated. Ensuite :

```powershell
$env:JARVIS_TEST_VOICE = '1'
.\.venv-voice\Scripts\python.exe -m unittest tests.test_voice_live -v
Remove-Item Env:JARVIS_TEST_VOICE
```

Pour des modèles ailleurs, définir également `JARVIS_TEST_MODELS` vers leur dossier.
Les deux voix réelles et un aller-retour TTS→STT sont alors testés ; ce n’est pas
un test du micro ou une évaluation perceptive. Pour le vrai LLM, utiliser aussi le
`JARVIS_TEST_MODEL` du README. Ne pas interpréter les tests ignorés comme réussis.

Recette manuelle : écouter Tom puis Siwis ; parler français pendant cinq minutes ;
changer voix/sortie ; couper/rebrancher le micro ; couper Ollama ; interrompre au
casque ; vérifier qu’aucun ancien segment ne reprend ; Arrêt/Sommeil/réveil ;
contrôler historique et paramètres après redémarrage. Examiner PRESENCE à 100/150/200 %
de DPI, plein écran et fenêtres larges/étroites, sur fond noir et clair. Relever
sur le PC les latences et ressources si souhaité ; aucun débit 60 tok/s n’est garanti.
Les 34 contrôles stables figurent dans JALON-2-SPEC.md §13 ; consigner les résultats
sans cocher ceux qui n’ont pas été exécutés.

## Restaurer le jalon 1 sans perte

La première ouverture d’une base v1 crée `jarvis.sqlite3.v1-backup.sqlite3` (ou suffixe
unique) avant migration v2. L’ancien EXE ne sait pas lire v2 : ne pas supprimer la DB.
Fermer JARVIS, archiver **tout** le dossier courant, puis copier le backup v1 sous
`jarvis.sqlite3` dans un **autre dossier** et lancer l’ancien EXE avec
`$env:JARVIS_DATA_DIR = 'C:\chemin\restauration-j1'`. Les conversations créées après
migration restent dans l’archive v2 ; elles ne figurent pas dans l’instantané v1.
Après test, `Remove-Item Env:JARVIS_DATA_DIR`. Garder les deux copies.

## Sources et licences

Piper 1.8.0 : [GPL-3.0-or-later](https://github.com/OHF-Voice/piper1-gpl/tree/v1.8.0),
avec espeak-ng et ses notices ; conserver les obligations/licences lors de distribution.
Voix officielles : [Tom et Siwis](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/fr/fr_FR),
deux poids distincts, pas un changement de pitch. Fiches individuelles à lire avant
installation ; impossibles à vérifier dans ce cloud (403), aucun poids redistribué.
[faster-whisper](https://github.com/SYSTRAN/faster-whisper/tree/v1.2.1) et
[Silero](https://github.com/snakers4/silero-vad) : MIT ; sounddevice : MIT ;
ONNX Runtime : MIT ; SOXR : LGPL-2.1-or-later ; conserver les notices tierces.
Kokoro a été consulté comme alternative Apache-2.0, mais seule sa voix FR ff_siwis
était vérifiable : il n’a pas été retenu pour garantir deux timbres FR. Un contrat
SpeechProvider isole le TTS ; **Piper est le seul moteur livré dans cette version**.
Aucun code ni asset des références AGPL/CC BY-NC n’a été copié.

## Lot 1 : moteur réutilisé et diagnostic français

Piper se prépare pendant Ollama, sans lecture ni suspension micro. Après fin
normale, la voix reste chargée pendant l’écoute ; interruption active, erreur,
arrêt de l’écoute ou nouveau profil libèrent le moteur. `tts_engine /
ready_before_phrase` indique s’il était prêt ; aucun faux temps de chargement nul.
Une première clause assez longue part à sa virgule avant la limite de96 caractères.

Dans **Diagnostic micro / STT**, le brut Whisper et le texte conservé sont comparables,
langue demandée `fr`. Pour inspecter le signal : **Enregistrer le prochain tour en
WAV…**, choisir un chemin neuf et confirmer. Un tour, mono PCM16/16kHz,625Kio maximum.
Aucun écrasement ni envoi. **Réécouter** suspend le micro, utilise la sortie choisie
et reste arrêtable. Les fichiers restent aux chemins choisis jusqu’à votre suppression.
Une demande affectée à un tour abandonné est signalée comme annulée.
RMS/pic/écrêtage/DC sont mesurés ; énergie aux bords = simple indice de coupure,
jamais preuve (le bruit peut le déclencher). `max_duration` indique la limite20s.
Choisir une des cinq références françaises, la lire, puis **Comparer** calcule le
WER du dernier résultat (accents conservés, casse/ponctuation normalisées).

Depuis les sources Windows, fermer JARVIS pour éviter la concurrence CPU, puis :

```powershell
.\.venv-voice\Scripts\python.exe -m jarvis.audio_diagnostics --benchmark-tts --models-dir "$env:LOCALAPPDATA\Jarvis\models"
```

JSON : deux chargements Piper contre un chargement pour deux synthèses identiques,
Tom par défaut ; chargement, premier PCM, synthèse totale. Aucun son joué/spawn :
pas une latence audible. Caches et ordre des essais peuvent influencer le résultat.
Aucun téléchargement. Remplacer le dossier si vos modèles sont ailleurs.

Pour le corpus STT, lire/exporter les cinq références vers des WAV distincts.
Créer `corpus-fr.json` UTF-8 avec la liste des fichiers et textes réellement lus :

```json
[{"wav":"phrase-1.wav","reference":"Bonjour JARVIS, peux-tu me dire quelle heure il est ?"}]
```

Ajouter les quatre autres références du diagnostic, puis lancer :

```powershell
.\.venv-voice\Scripts\python.exe -m jarvis.audio_diagnostics --corpus .\corpus-fr.json --models-dir "$env:LOCALAPPDATA\Jarvis\models"
```

Whisper chargé une fois ; JSON par fichier + WER global pondéré et temps. Comparer
le même corpus avant/après. La fidélité réelle ne se déduit pas des tests simulés.
Garder silence VAD et garde speakers350ms pour comparer ; aucun changement aveugle
de threads/GPU. PortAudio estime le DAC, pas le délai Bluetooth XTREME140 : comparer
à une sortie filaire avec même configuration avant d’attribuer un délai au moteur.
