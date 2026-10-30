# JARVIS UNHINGED NEXT · 0.0.1

Premier socle desktop local : fenêtre sombre COMMAND OS, modèles Ollama installés,
conversation en streaming, arrêt, conversations SQLite et paramètres persistants.
Aucun abonnement, compte cloud, téléchargement silencieux ou outil système.

**Centre de contrôle :** Menu → Centre de contrôle ou Ctrl+,. PRESENCE Studio
permet de prévisualiser, comparer et appliquer les réglages graphiques.
[Guide, démonstration hors ligne et recette Windows](docs/CONTROL-STUDIO.md).

## Lancer sur Windows 11

1. Installer **Python 3.12 x64** depuis [python.org](https://www.python.org/downloads/windows/),
   avec le lanceur `py` et Tcl/Tk (options standard). Python 3.12.10 est la version du build CI.
2. Installer et démarrer [Ollama pour Windows](https://ollama.com/download/windows).
3. Dans PowerShell, télécharger un modèle une fois :

   ```powershell
   ollama pull qwen2.5:3b
   ollama list
   ```

   C’est un point de départ, sans garantie de débit sur votre matériel. Les autres
   modèles locaux compatibles Ollama, y compris abliterated, sont acceptés.
4. Ouvrir PowerShell **dans le dossier du dépôt** (celui qui contient `run.py`) :

   ```powershell
   py -3.12 -m pip install -r requirements.txt
   py -3.12 run.py
   ```

La seule dépendance de base est `tzdata` (environ 340 Kio), pour les fuseaux IANA
hors ligne sous Windows ; aucun modèle n'est téléchargé. Dans la fenêtre, cliquer sur
**Actualiser**, choisir le modèle, écrire et cliquer sur **Envoyer** ou **Ctrl+Entrée**.
Entrée insère une nouvelle ligne. **Arrêter** conserve la réponse partielle.
L’historique à gauche permet de reprendre une conversation ou de la supprimer avec confirmation.
Sans Ollama, l’historique et les paramètres restent accessibles.

Les paramètres permettent de choisir l’adresse locale, la température, le contexte,
la limite de réponse et une instruction système facultative. Aucun prompt de filtrage
n’est ajouté par JARVIS. Les modèles explicitement déclarés distants par Ollama
ne sont pas proposés. Le modèle n’a aucun moyen d’exécuter une commande.

## Produire Jarvis.exe sur Windows

Depuis PowerShell, dans le même dossier :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

Le script crée `.venv-build`, installe les outils épinglés, lance les tests, compile,
puis vérifie le démarrage et le processus secondaire de l’EXE sans nécessiter Ollama.
Résultat : **`dist\jalon-2\Jarvis.exe`** et `dist\jalon-2\Jarvis.exe.sha256`.
L’EXE embarque Python/Tk ; Ollama et ses modèles restent à installer séparément.
Le binaire est **non signé**, portable, sans installateur ni mise à jour automatique.

Alternative sans compiler sur votre PC : après l’envoi de ces fichiers sur GitHub,
ouvrir **Actions → Windows Jarvis → Run workflow** sur la branche contenant ce code.
Après un résultat vert, télécharger l’artefact **Jarvis-Jalon2-Windows-x64-…** en bas de
l’exécution et décompresser le ZIP. Le workflow se lance aussi sur une PR et sur
les mises à jour de `main` ou `work`. Aucun artefact Windows n’a été produit dans
cette session Linux ; la recette Windows 11 avec un vrai modèle reste requise.

## Données et dépannage

- Windows : `%LOCALAPPDATA%\Jarvis\jarvis.sqlite3`. Historique et paramètres sont
  dans cette base locale **non chiffrée** ; évitez d’y saisir des secrets.
- Pour sauvegarder ce premier socle, **fermer JARVIS**, puis copier le dossier
  `%LOCALAPPDATA%\Jarvis`. Pour restaurer : fermer JARVIS, conserver une copie du
  dossier actuel, puis remettre la sauvegarde. Pas encore de restauration guidée.
- Pour isoler un profil de test : définir `JARVIS_DATA_DIR` vers un autre dossier.
- « Connexion impossible » : lancer Ollama depuis le menu Démarrer ou utiliser
  `ollama serve` s’il ne tourne pas déjà ; vérifier `http://127.0.0.1:11434` dans les paramètres.
- Liste vide : `ollama pull qwen2.5:3b`, puis **Actualiser**.
- Mémoire insuffisante : réduire contexte ou taille du modèle ; une seule génération
  à la fois. Aucune mesure GPU ou promesse de 60 tokens/s dans ce socle.
- Flux interrompu : le texte déjà reçu est conservé avec état d’échec. Les échanges
  échoués/arrêtés ne sont pas réinjectés comme réponses complètes au prochain envoi.
- Une fermeture brutale conserve les fragments déjà enregistrés (environ toutes
  les 40 ms pendant réception) ; la dernière réponse est marquée interrompue à la relance.
- Supprimer une conversation l’enlève de l’archive applicative ; cela ne garantit
  pas l’effacement forensique du disque ou des sauvegardes.
- Pour retirer l’application portable : supprimer l’EXE. Les données sont conservées ;
  ne supprimer le dossier de données que si vous souhaitez aussi effacer votre historique.

## Tests

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 run.py --smoke-test
```

Test facultatif avec **un vrai modèle déjà installé** :

```powershell
$env:JARVIS_TEST_MODEL = 'qwen2.5:3b'
py -3.12 -m unittest discover -s tests -v
Remove-Item Env:JARVIS_TEST_MODEL
```

Les tests HTTP utilisent un serveur de test explicitement distinct d’Ollama.
Le test d’inférence réelle est ignoré si `JARVIS_TEST_MODEL` n’est pas défini ;
les tests desktop sont ignorés si aucun écran n’est disponible.
Résultats et périmètre : [notes de réalisation](docs/IMPLEMENTATION.md).

## Jalon 2 : voix locale et PRESENCE

La branche Jalon2 ajoute capture/VAD/STT local, deux profils Piper FR, orchestration
mains libres, arrêt/interruption au casque, migration SQLite conservatrice et PRESENCE.
Les composants vocaux et modèles sont facultatifs et installés explicitement.
Voir **[installation et recette Windows](docs/VOICE.md)**, le
[journal vérifiable](docs/JALON-2-PROGRESS.md) et la [reprise](docs/NEXT-CODEX-SESSION.md).

Pour le build vocal, utiliser `scripts\build-windows.ps1 -WithVoice` ; le script
produit désormais `dist\jalon-2\Jarvis.exe` sans écraser l’ancien EXE.
L’artefact GitHub porte le nom **Jarvis-Jalon2-Windows-x64-…**.
Le guide vocal précise les contrôles disponibles et les validations matérielles restantes.
