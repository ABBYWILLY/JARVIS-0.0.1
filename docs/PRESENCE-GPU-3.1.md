> Validation visuelle utilisateur sur Windows (28 octobre 2026) : fluidité,
> netteté, animations et bascule 2D/2.5D satisfaisantes. Rendu conservé.
> Benchmarks combinés RTX 3070 + Ollama + voix encore à effectuer.
> CI finale c40d724 : [application Windows](https://github.com/ABBYWILLY/JARVIS-0.0.1/actions/runs/40759274807)
> et [prototype](https://github.com/ABBYWILLY/JARVIS-0.0.1/actions/runs/40759274772) réussis.

# PRESENCE GPU 3.1

28 octobre 2026 · base `4ae4f71` · branche `feat/jalon-2-voice-presence`.
[Demande conservée](PRESENCE-GPU-3.1-SPEC.md). Direction artistique 3.0 conservée,
Canvas reste une alternative permanente. Aucun moteur vocal ou modèle ajouté.

## A — Cadence et netteté

Causes constatées dans le code : Équilibré plafonné à 30 images/s, rendu enfant
conditionné aux snapshots Tk, attente pouvant atteindre 100 ms, VSync désactivé ;
géométrie limitée à 720p/1080p puis agrandie ; atlas HUD limité à 1920 pixels.

Le processus graphique évalue désormais les horloges/orbites entre snapshots
horodatés, sans inventer de PCM, d'état ou d'expression. Le parent envoie ses
ancres à 25 Hz maximum ; l'analyse audio garde sa cadence indépendante.
Équilibré/Cinématique visent 60 dessins/s, Éco 15. Présentation VSync demandée,
échéances absolues sans attente active ni double attente après le swap.
Une interruption/expiration garde priorité ; un parent bloqué fige l'animation
après 350 ms. Repos et masquage ne dessinent pas continuellement.

Le rendu principal utilise les pixels physiques, avec Auto/100/125/150/200 %
et des plafonds de 8,29 Mpx/4096 par dimension. Le bloom reste indépendant.
Traits, particules et diffusion gardent leur taille apparente en supersampling.
Le HUD rasterise ses deux bandes en pixels natifs jusqu'à 4096, avec un budget
borné. Les changements de taille/DPI libèrent les ressources remplacées.

L'adaptation réduit successivement bloom, particules secondaires, puis seulement
en Auto la résolution principale à 75 % : surcharge durable 2 s, récupération
8 s, étapes espacées. Les préférences artistiques ne sont pas réécrites.

F9 affiche FPS dessinés et résolution réellement utilisée. Le diagnostic vocal
copiable contient les mesures du processus GPU : moyenne/P50/P95/P99, frames
longues, CPU/RAM, PID, framebuffer et facteur DPI. Le rafraîchissement du moniteur
et les appels swap sont distingués ; l'affichage physique à l'écran n'est pas
directement observable et la VRAM physique reste non mesurée.

Les mesures Mesa ne prouvent pas 60 FPS sur RTX, ni leur maintien avec Ollama.
L'objectif reste à vérifier sur le PC ; un FPS insuffisant ne bloque pas l'audio.

Phase A : **152 tests ciblés réussis** (Tk/OpenGL/EGL réel, 14,434 s), plus
smoke d'une fenêtre GLFW avec Mini/masquage/restauration/retour Canvas.
[Captures natives, rapports et limites](PRESENCE-GPU-3.1-EVIDENCE.md) : à
1440 × 960, Mesa logiciel atteint environ 25–27 FPS natifs, 18 FPS à 125 %,
13 FPS à 150 %. Le coût supérieur de la netteté native est explicite ; aucun
objectif 60 FPS matériel n'est déclaré atteint.

## B — Choix direct 2D / 2.5D

Le contrôle permanent `[2D | 2.5D]` en haut à gauche indique le moteur réellement
actif. Il existe dans Canvas et dans le HUD GPU ; ses clics GPU traversent le
canal IPC borné et validé. Le parent seul enregistre le choix et change de moteur.
`Ctrl+F7` bascule depuis COMMAND OS ou PRESENCE ; Automatique reste disponible
dans le Centre de contrôle. Tab/Entrée permettent de parcourir les commandes GPU.

Les tests vérifient commandes visibles, vrai transport spawn, petites fenêtres,
Mini, DPI simulés et préservation de l'audio/historique/génération au basculement.
Une sélection GPU reste affichée comme 2D jusqu'à la notification prêt ; en cas
d'échec, le motif et le nouvel essai manuel restent accessibles dans les paramètres.

## C — Écoute, concentration et aura vocale

Le spectre linéaire était trop peu visible : à RMS 0,056, l'ancien halo variait
d'environ 4 % en largeur et 6 % en lumière. Trois enveloppes graphiques utilisent
maintenant le PCM existant, avec seuil de silence, compression douce, attaque
rapide et relâchements distincts. Les trois bandes, leurs contributions, le gain
visuel et l'amplitude existants sont réutilisés. Aucun changement du son prononcé.

Écoute confirmée VAD : particules/impulsions convergentes et réception brève.
THINKING : concentration, contraction 8 % et trois axes rapides conservés.
Parole Piper : halo proche réactif, dilatation intermédiaire et aura externe
plus lente, émissions rayonnantes. Le repos est statique après relâchement.
Un micro ouvert sans VAD ne déclenche pas une fausse réception vocale.

Les états restent ceux du parent. Les enveloppes suivent l'échéance PCM
PortAudio existante ; interruptions, erreurs et nouveaux tours effacent l'énergie
sortante. Un snapshot périmé ne conserve ni énergie ni réception. La réduction
du mouvement atténue les effets ; les huit gravures et la sphère restent visibles.
Les couleurs des mots du HUD reçoivent désormais les valeurs RGB entières
attendues, au lieu de retomber sur le cyan à cause d'un format incompatible.

Les 66 réglages sont conservés. Trois paramètres seulement sont ajoutés : rayon
de pulsation, intensité convergente et intensité rayonnante. La référence
artistique 3.0 désactive ces nouvelles couches, sans remettre l'ancien plafond FPS.

Phase C : **189 tests ciblés réussis**, dont vrais pixels OpenGL, huit gravures,
silence/relâchement, VAD, délai PCM, interruption et reprise. Les journaux Windows
de B/C ont révélé une limite arbitraire de 60 pixels dans le test de position.
La vérification utilise désormais l'ancrage et les boîtes réelles des widgets,
leur visibilité complète et l'absence de chevauchement avec les états/micro.
Le placement réserve la hauteur réellement demandée par le thème natif.

## D — Studio et livraison

Le même Studio conserve ses six commandes essentielles, ses niveaux, sa recherche
et les favoris du Centre. Il expose 69 curseurs : les 66 existants et les trois
nouveaux paramètres de C. Le choix d'échelle Auto/100/125/150/200 % est disponible
dans Performances, dans la recherche et via « GPU · Échelle de rendu » au Centre.
Il utilise le même brouillon et la même clé SQLite que les autres réglages GPU.

« Charger le style de référence 3.0 » restaure l'apparence approuvée en conservant
le profil, l'échelle et la limite FPS choisis. Les effets 3.1 peuvent ensuite être
réactivés. Avant/Après, Annuler, Appliquer et Restaurer restent transactionnels ;
aucun aperçu ne réécrit le choix de moteur ni les préférences Canvas.

Les clips et captures du [dossier de preuves](PRESENCE-GPU-3.1-EVIDENCE.md) sont
issus des composants réels. Leur PCM de test est synthétique et identifié ; leur
cadence d'export n'est pas une mesure de FPS en situation réelle.

Validation finale locale : **802 tests exécutés, 793 réussis, 9 ignorés** en
97,466 s sous Linux/Tk 9/EGL réel. Les ignorés nécessitent les dépendances audio
natives ou une activation explicite des modèles réels. Sous Tk 8.6 : 51 tests
ciblés exécutés, 50 réussis et un test EGL ignoré faute de dépendance facultative.
Ces résultats et les captures ne remplacent pas la recette Windows matérielle.
Consulter les deux workflows GitHub Actions du SHA final pour le build et les
smoke tests : « Windows Jarvis » et « PRESENCE GPU prototype ».

## Validation Windows — matériel en attente

1. Lancer JARVIS complet et choisir 2.5D ; F9 affiche les mesures réelles.
2. Comparer Équilibré/Cinématique avec puis sans Ollama : FPS/P95, TTFT, tokens/s,
   audio, CPU/RAM/VRAM du Gestionnaire des tâches. Conserver le même modèle.
3. Tester fenêtres réduites, plein écran et déplacement entre moniteurs/DPI.
   Comparer Auto/100/125/150 % ; lire la résolution effective et les plafonds.
4. Parler puis se taire, écouter Piper et interrompre : pas d'effet audio ancien,
   pas de perte de conversation. Revenir en Canvas et vérifier après redémarrage.
5. Dans le Studio, comparer les échelles et les styles 3.0/3.1 sans sauvegarder,
   puis Appliquer et redémarrer pour vérifier les préférences des deux moteurs.
6. Comparer écoute sans parole, VAD confirmé et Piper : réception convergente,
   réflexion contenue, émission rayonnante. Tester les trois expressions
   « Heureux de te revoir 😊 », « Je t'aime ❤️ », « C'est drôle 😂 ».
7. Vérifier Ctrl+F7 et les deux boutons, puis réduire/masquer la fenêtre et
   constater la baisse d'activité graphique. Tester les interruptions en plein
   PCM et les sorties casque/haut-parleurs/Bluetooth habituelles.
8. Pour conserver les mesures : Voix → Diagnostic → Copier. La section GPU donne
   le PID, la RAM/CPU du processus, les percentiles et les résolutions. La VRAM
   du pilote, la sortie acoustique Bluetooth et l'impact Ollama exigent une
   observation matérielle ; ils ne sont pas estimés à partir d'une vidéo.

[Lancement et compilation Windows](PRESENCE-DUAL-ENGINE.md). Aucun essai sur votre
microphone, votre sortie Bluetooth ou votre RTX 3070 n'est revendiqué ici.
