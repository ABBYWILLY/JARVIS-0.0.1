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

Le spectre adaptatif est une **estimation lexicale prudente**, sans appel LLM et sans
prétention de ressentir une émotion. Ambiguïté → cyan, inertie de 3 s, négation simple.
Les menus, permissions et alertes ont leur propre spectre opérationnel indépendant.
Les profils JARVIS/UNHINGED changent une instruction système visible/modifiable,
jamais les permissions. Aucun outil système n’est activé.

Les sous-titres commencent sur les callbacks du PCM envoyé au périphérique, avec
prise en compte de l’horloge de sortie. Les groupes de mots sont une **approximation
par durée**, signalée dans l’interface, sans timestamps mot à mot. Le bouton Copier
copie le groupe visible ; COMMAND OS conserve l’intégralité des textes dans SQLite.
Les fichiers audio micro ne sont pas enregistrés. La base texte reste non chiffrée.

## Compilation et récupération de l’artefact

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

## Recette réelle sur votre Windows

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
