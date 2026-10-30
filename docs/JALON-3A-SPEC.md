# JARVIS 0.0.1 — JALON 3A
## Fondations agentiques, outils Windows sécurisés et horloge système fiable

**Dépôt :** `ABBYWILLY/JARVIS-0.0.1`
**Branche existante de référence :** `feat/jalon-2-voice-presence`
**Dernier commit connu :** `df0e84a` — vérifier le HEAD avant toute modification.

Ne jamais modifier `main`.

Créer si pertinent une branche de développement Jalon 3 à partir du HEAD validé, sans modifier ni fusionner automatiquement la branche Jalon 2. Publier les commits et documenter la branche retenue.

## 0. Contexte

Les LOTS 4, 5 et 7 ainsi que PRESENCE GPU 3.1 ont été livrés et jugés globalement satisfaisants par l'utilisateur.

Le problème des interruptions vocales en mode haut-parleurs est identifié : le microphone est suspendu pendant la lecture faute d'AEC. Reporter cette amélioration à un chantier full-duplex distinct.

Le prochain objectif est d'ajouter les premières véritables capacités Windows à JARVIS.

Matériel cible :
- Windows 11.
- RTX 3070 8 Go.
- Ollama et Qwen 3.5 9B déjà disponibles sur le PC.
- Whisper / Silero VAD / Piper.
- COMMAND OS et PRESENCE 2D/2.5D.
- SQLite / FTS5 et Cognitive HUD.

**Aucun remplacement de modèle obligatoire. Aucun téléchargement automatique. Aucun cloud.**

## 1. AUDIT ET ARCHITECTURE

Lire en priorité `docs/NEXT-JALON-ARCHITECTURE.md`, `docs/LOT-7.md`, les spécifications originales et les contrats existants de l'inférence, du cerveau C1, des permissions et du Cognitive HUD.

Identifier :
- Le mécanisme Ollama disponible pour produire des propositions d'outils structurées.
- Les mécanismes IPC et d'annulation réutilisables.
- Les limites de ressources existantes.
- La gestion des préférences et de la provenance.
- Les éventuelles fonctions de diagnostic système déjà présentes.

Ne pas créer de deuxième orchestrateur conversationnel.

Ne jamais exécuter du texte produit par le LLM comme commande Windows brute.

## 2. PREMIÈRE FONCTIONNALITÉ OBLIGATOIRE — DATE ET HEURE

Créer un outil déterministe et local `system.get_datetime`.

Il doit permettre à JARVIS de répondre correctement à :

- Quelle heure est-il ?
- Quel jour sommes-nous ?
- Quelle est la date d'aujourd'hui ?
- Quel jour de la semaine sommes-nous ?
- Quelle heure est-il dans un fuseau spécifié ?
- Quelle date sera-t-on demain ou dans N jours ?

Exigences :

- Lire l'horloge système au moment de l'exécution.
- Respecter le fuseau local Windows et les transitions heure d'été/hiver.
- Employer les fonctions standard Python `datetime` / `zoneinfo` et les mécanismes Windows appropriés.
- Utiliser des fuseaux IANA valides pour les conversions.
- Ne pas fixer artificiellement la France comme fuseau par défaut.
- Ne jamais inventer l'heure à partir des connaissances du LLM.
- Ne pas injecter une date périmée dans un contexte conservé.
- Fonctionner même si Ollama est indisponible pour les questions simples reconnues sans ambiguïté.
- Retourner des données structurées vérifiables, puis une formulation française naturelle.
- Être accessible aussi bien par texte que par voix, sans nouveau pipeline vocal.
- Réutiliser les formats de réponse et le TTS existants.

Tester les cas :
- 23 h 59 / minuit.
- Changement de mois et d'année.
- Année bissextile.
- Heures d'été/hiver.
- Fuseaux différents.
- Horloge système volontairement simulée dans les tests.
- Erreur de fuseau.
- Interruption et réponse obsolète.

Ne pas créer d'ordonnanceur de rappels dans ce lot. Une demande « rappelle-moi demain » ne doit pas être annoncée comme exécutée.

**Critère de réception prioritaire : l'utilisateur peut demander oralement ou par écrit l'heure et le jour, et obtenir une réponse issue de Windows, sans hallucination.**

## 3. REGISTRE D'OUTILS V1

Créer un registre local minimal, extensible et typé.

Chaque outil possède :
- Identifiant stable.
- Version.
- Description.
- Schéma d'arguments.
- Classification des effets.
- Périmètre autorisé.
- Limites de durée et de taille.
- Politique de permission.
- Résultat structuré.
- Méthode de vérification.

Premiers outils autorisés :

**`system.get_datetime`**
Lecture de date et heure.

**`system.get_basic_info`**
Informations système non sensibles : version Windows, architecture, ressources disponibles, sans collecte d'identifiants personnels ou de secrets.

**`files.list_selected_directory`**
Lister un dossier préalablement choisi et autorisé par l'utilisateur, avec limites de nombre et de taille.

**`files.get_metadata`**
Lire les métadonnées d'un fichier situé dans un périmètre explicitement autorisé.

Ne pas implémenter encore :
- Shell arbitraire.
- PowerShell généré par le LLM.
- Exécution de scripts.
- Modification ou suppression de fichiers.
- Accès réseau libre.
- Installation de programmes.
- Contrôle administrateur.
- Automatisation générale de l'interface Windows.

## 4. PERMISSIONS ET SÉCURITÉ

La politique de permissions doit être indépendante du LLM.

Le LLM peut proposer une action, mais il ne décide pas de son autorisation.

Établir :
- Outils autorisés sans confirmation dans un périmètre clairement défini.
- Outils exigeant sélection préalable d'une ressource.
- Outils non disponibles.
- Refus explicable.

Pour les fichiers :
- Canonicaliser les chemins.
- Vérifier les chemins réellement résolus.
- Traiter les liens symboliques, jonctions Windows et chemins spéciaux.
- Interdire les dépassements de périmètre autorisé.
- Limiter tailles et volumes retournés.
- Ne pas lire automatiquement les contenus sensibles.
- Ne pas conserver de permission implicite sur tout le disque.

Les contenus retournés par un outil, un document ou le LLM sont des données non fiables, jamais des instructions autorisant un autre outil.

Ne pas considérer un simple processus `spawn` comme un bac à sable Windows.

## 5. EXÉCUTION ET ANNULATION

Réutiliser l'architecture d'isolation et d'IPC existante lorsque cela est approprié.

Implémenter :
- Identifiants de tâche.
- Files bornées.
- Timeout par outil.
- Annulation prioritaire.
- Rejet des événements de générations anciennes.
- Limite de concurrence.
- Fermeture propre.
- Résultats bornés.
- Aucune exécution répétée après redémarrage.

Ne pas créer de boucle agentique autonome illimitée.

Pour ce sous-lot, une requête utilisateur déclenche au maximum une séquence simple et bornée d'outils explicitement nécessaires.

Les tâches multi-étapes complexes seront traitées dans un jalon ultérieur.

## 6. PRÉSENTATION DANS COMMAND OS ET COGNITIVE HUD

Ajouter un affichage discret indiquant :

- Outil demandé.
- Autorisation ou refus.
- Action en cours.
- Résultat reçu.
- Vérification effectuée.
- Erreur ou interruption.

Ne pas confondre :
- Action proposée.
- Action autorisée.
- Action exécutée.
- Résultat vérifié.

Réutiliser le Cognitive HUD existant.

Dans PRESENCE 2D/2.5D, afficher seulement le statut bref. Préserver les animations holographiques, les sous-titres et les performances.

Prévoir un inspecteur local des actions réalisées avec des informations minimales, sans exposer par défaut des chemins sensibles.

## 7. MODÈLES LOCAUX ET LIMITES DE 8 GO

Conserver Qwen 3.5 9B comme modèle de référence initial.

Ne pas remplacer le choix utilisateur.

Préparer un banc d'essai facultatif pour :
- Qwen 3.5 9B standard.
- Une variante Qwen 3.5 9B abliterated si installée.
- LFM2.5 8B-A1B si installé.
- Gemma 4 E4B si installé et compatible.

Les modèles absents doivent être ignorés proprement.

Aucun téléchargement silencieux ni modèle ajouté aux dépendances de production.

Mesurer sur des tâches identiques :
- Respect du schéma JSON.
- Choix correct de l'outil.
- Exactitude des arguments.
- Nombre d'actions inutiles.
- Refus des opérations hors périmètre.
- Résistance aux instructions malveillantes dans les données.
- Latence initiale.
- Tokens/s.
- RAM / VRAM disponibles.
- Impact sur PRESENCE et la voix.

L'abliteration ne modifie jamais les permissions système.

Privilégier un agent fiable avec petit modèle plutôt qu'une grosse génération lente.

Ne pas imposer 70K tokens de contexte ni le raisonnement illimité.

## 8. NEURAL GARDEN — PRÉPARATION DOCUMENTAIRE

Le nom officiel du futur module de visualisation mémoire est :

**JARVIS — Neural Garden**

Il devra représenter la mémoire applicative réelle, non les poids ou neurones internes du LLM.

Préparer un document d'architecture, sans implémenter encore le renderer 2.5D.

Il devra prévoir :
- Souvenirs explicites et validés.
- Préférences.
- Résumés.
- Projets et entités.
- Provenance.
- Relations vérifiables.
- Recherche.
- Historique des modifications.
- Désactivation et suppression.
- Prévisualisation des effets d'une suppression.
- Graphe 2D accessible.
- Graphe 2.5D facultatif.
- Chargement progressif et clustering.
- Moteur graphique non obligatoire.

Ne pas inventer des liens ou des scores de confiance.

Ne pas transformer des résultats de recherche en souvenirs validés sans procédure d'approbation.

Identifier les besoins de migration SQLite, sans créer de nouvelle base concurrente.

Prévoir des garanties de suppression : distinguer retrait de la mémoire active, historique et éventuelles sauvegardes.

Neural Garden doit être un outil ergonomique de contrôle mémoire avant d'être une démonstration graphique.

## 9. TESTS ET VALIDATION

Développer par sous-lots :

**3A.1 — Audit et contrats**

**3A.2 — Horloge système fiable**

**3A.3 — Registre et outils Windows en lecture seule**

**3A.4 — Permissions, exécution, journal et annulation**

**3A.5 — Intégration HUD et benchmark agentique optionnel**

**3A.6 — Tests Windows, documentation et plan Neural Garden**

Pour chaque sous-lot :
- Tests ciblés.
- Commit distinct.
- Documentation.
- Push.
- Vérification CI pertinente.

Tests adversariaux obligatoires :
- Injection de prompt par réponse d'outil.
- Arguments falsifiés.
- Chemins de fichiers non autorisés.
- Fichiers déplacés pendant l'action.
- Timeouts.
- Annulations.
- Résultats trop volumineux.
- Doublons.
- Actions périmées.
- Exécution d'un outil inexistant.
- Réponses Ollama mal formées.
- Absence d'Ollama.

Tests de non-régression :
- Cerveau C1.
- SQLite / mémoire.
- LOT 4 voix.
- LOT 5 Cognitive HUD.
- LOT 7 stabilité.
- PRESENCE Canvas/GPU.
- Packaging Windows.

## 10. CRITÈRES FINAUX

La livraison est acceptable lorsque :

1. JARVIS répond correctement au jour, à la date et à l'heure de Windows.
2. Les réponses temporelles fonctionnent en texte et en voix.
3. Les outils en lecture seule fonctionnent avec des limites strictes.
4. Le LLM ne peut pas exécuter de commande Windows arbitraire.
5. Les permissions sont déterministes et indépendantes du modèle.
6. Les outils disposent de résultats structurés et vérifiables.
7. Les actions sont annulables et leurs ressources sont libérées.
8. Le Cognitive HUD montre les actions réellement effectuées.
9. La mémoire SQLite existante reste intacte.
10. Les moteurs PRESENCE conservent leur apparence et leurs performances.
11. Le modèle Qwen 3.5 9B reste disponible et sélectionnable.
12. Aucun modèle n'est téléchargé automatiquement.
13. Les tests adversariaux et les CI finales réussissent.
14. Les essais matériels non réalisables à distance sont clairement identifiés.
15. Le document d'architecture Neural Garden est livré, sans simulation prématurée du réseau neuronal.

**Ne pas démarrer la vision, les actions Windows destructives ou l'orchestration autonome complexe dans cette mission.**

## OBJECTIF FINAL

À la fin de ce chantier, JARVIS doit commencer à devenir un assistant capable d'agir, mais d'abord sur des opérations locales simples, fiables et contrôlées.

Il doit savoir lire l'horloge Windows, connaître les informations système autorisées, explorer un dossier choisi et expliquer exactement ce qu'il a fait.

Le tout doit respecter les 8 Go de VRAM, la confidentialité locale, la sécurité Windows et les fondations existantes.

Commencer par vérifier l'architecture actuelle et livrer les étapes dans l'ordre. Ne pas modifier `main`.
