# PRESENCE GPU — faisabilité et choix du prototype

Relevé des sources publiques : **23 octobre 2026**. Cible : Windows x64,
Python 3.12, RTX 3070, application Tkinter et distribution PyInstaller.

**Choix proposé : ModernGL + glfw pour un prototype à fenêtre native autonome.**
Le besoin de PRESENCE porte sur un
champ animé et des shaders procéduraux ; un moteur de scène complet apporte
peu au premier essai. Garder le rendu Tk/CPU actuel disponible. La mise en
production dépendra des mesures Windows/RTX, encore absentes.

| Critère | ModernGL + glfw | Panda3D |
| --- | --- | --- |
| OpenGL / shaders | API OpenGL Core et GLSL explicites ; contexte 3.3 minimum par défaut. GLFW crée la fenêtre et le contexte. | Moteur de scène avec fenêtres natives, backend OpenGL et GLSL ; utile si PRESENCE évolue vers caméra, scène et assets 3D. |
| Boucles Tk / fenêtre Windows | GLFW réserve initialisation, création/destruction et événements au thread principal. Un processus autonome évite de partager cette boucle avec Tk. | `ShowBase.startTk()` existe et pilote les tâches Panda par `Tk.after()` ; cela ne valide pas son intégration dans la fenêtre existante. |
| Dépendances Python publiées | `moderngl` exige `glcontext>=3.0.0` ; ajouter `glfw`. Le wheel Windows glfw embarque DLL GLFW et runtime Visual C++. | Aucun `Requires-Dist` dans PyPI ; le wheel contient néanmoins un moteur natif et ses bibliothèques/plugins. |
| Redistribution | ModernGL, glcontext et wrapper pyGLFW : MIT ; bibliothèque GLFW : zlib/libpng. Conserver les notices. | BSD modifiée à trois clauses ; inventorier aussi les licences des bibliothèques/plugins réellement distribués. |
| PyInstaller | Vérifier extensions ModernGL/glcontext, backend WGL, DLL GLFW et ressources GLSL. Le README glfw documente les chemins de DLL des applications gelées. | La voie documentée par Panda est son propre `build_apps`. Un EXE PyInstaller demande une validation spécifique des plugins et ressources. |

## Versions et poids observés

Dernières versions PyPI au jour du relevé ; **tailles exactes des archives wheel
compressées**, sans téléchargement des wheels. Les trois premières constituent
le lot ModernGL ; la roue glfw universelle convient à CPython 3.12.

| Distribution Windows x64 | Version | Wheel | Octets | Publication du wheel |
| --- | --- | --- | ---: | --- |
| [moderngl](https://pypi.org/pypi/moderngl/5.13.0/json) | 5.13.0 | `cp312-cp312-win_amd64` | 110 202 | 2026-10-07 |
| [glcontext](https://pypi.org/pypi/glcontext/3.1.0/json) | 3.1.0 | `cp312-cp312-win_amd64` | 12 604 | 2026-10-07 |
| [glfw](https://pypi.org/pypi/glfw/2.11.0/json) | 2.11.0 | `py2.py3-none-win_amd64` | 564 482 | 2026-10-16 |
| [panda3d](https://pypi.org/pypi/panda3d/1.10.16/json) | 1.10.16 | `cp312-cp312-win_amd64` | 65 586 786 | 2025-12-25 |

Total ModernGL + glcontext + glfw : **687 288 octets, soit 0,655 MiB** ;
Panda3D : **62,548 MiB**. Ces chiffres ne mesurent ni le poids installé ni le
surcoût final de l’EXE, qui doivent être relevés après build. Les publications
récentes attestent des versions distribuées ; elles ne garantissent ni support
futur ni absence de régression. Épingler les versions du prototype et retester
avant toute mise à jour.

## Validation attendue sur la RTX 3070

Un prototype doit exposer un diagnostic de contexte (`GL_VENDOR`, `GL_RENDERER`,
`GL_VERSION`), compiler les shaders et rendre dans un framebuffer GPU à la
taille effective de la fenêtre. L’absence de périphérique, un pilote inadéquat,
une erreur de création/compilation ou un renderer logiciel doivent produire un
diagnostic clair et laisser le mode CPU utilisable. Une RTX 3070 avec pilote
adapté est une cible plausible ; sa présence et ses performances restent à
constater sur la machine Windows. Aucune dépendance CUDA n’est nécessaire au
rendu OpenGL.

Mesurer sur cette machine : temps de frame CPU/GPU et p95, FPS, CPU/RAM/VRAM,
tailles fenêtre/résolution, démarrage et fermeture répétés, redimensionnement,
EXE sans Python installé et réactivité de la conversation/voix pendant le rendu.
Comparer des scènes et paramètres identiques ; examiner aussi lisibilité,
cohérence des états et absence de scintillement. Ne conclure sur la qualité
visuelle qu’après observation humaine de captures et de l’animation.

**Limite de cette session :** Linux sans `/dev/dri` ni `nvidia-smi`, donc aucun
GPU physique accessible. La recherche documentaire ne constitue pas un test
OpenGL/Windows/RTX. Le prototype autonome a depuis été réalisé et mesuré sous
Mesa logiciel : voir [PRESENCE-GPU-BENCHMARKS.md](PRESENCE-GPU-BENCHMARKS.md).
Ses résultats ne valident pas l'intégration à Tk ni la RTX.

Sources officielles complémentaires :
[ModernGL 5.13.0 : contexte et aide aux outils de gel](https://github.com/moderngl/moderngl/blob/5.13.0/moderngl/__init__.py),
[pyGLFW : Windows et PyInstaller](https://github.com/FlorianRhiem/pyGLFW/blob/master/README.rst),
[GLFW : contraintes de threads](https://github.com/glfw/glfw/blob/master/docs/intro.md#thread-safety-thread_safety),
[Panda3D 1.10.16 : boucle Tk](https://github.com/panda3d/panda3d/blob/v1.10.16/direct/src/showbase/ShowBase.py),
[API GLSL Panda3D](https://github.com/panda3d/panda3d/blob/v1.10.16/panda/src/gobj/shader.h),
[distribution Panda3D](https://github.com/panda3d/panda3d-docs/blob/master/distribution/building-binaries.rst),
[licence ModernGL](https://github.com/moderngl/moderngl/blob/main/LICENSE),
[licence glcontext](https://github.com/moderngl/glcontext/blob/main/LICENSE),
[licence pyGLFW](https://github.com/FlorianRhiem/pyGLFW/blob/master/LICENSE.txt),
[licence GLFW](https://github.com/glfw/glfw/blob/master/LICENSE.md),
[licence Panda3D](https://github.com/panda3d/panda3d/blob/v1.10.16/LICENSE).
