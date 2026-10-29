"""Searchable navigation to the existing preference owners; no copied values."""
from dataclasses import dataclass
import sqlite3
import tkinter as tk
from tkinter import font, ttk
import unicodedata


FAMILIES = ("PRESENCE", "Conversation et mémoire", "Voix", "Interface",
            "Système, sécurité et performances")
LEVELS = {"essential": "Essentiel", "personalize": "Personnaliser", "advanced": "Avancé"}
VIEWS = {**LEVELS, "favorites": "Favoris"}


@dataclass(frozen=True)
class Route:
    key: str
    family: str
    title: str
    description: str
    terms: str
    advanced: bool = False
    level: str = "essential"
    owner: str = ""
    control: str = ""


ROUTES = (
    Route("presence", FAMILIES[0], "PRESENCE Studio", "Personnaliser et comparer le rendu, puis appliquer vos choix.",
          "onde épaisseur expressivité halo diffusion lumière noyau thinking structure vitesse transitions palette couleur émotion microexpression morphing emoji sous-titres mini éco équilibré cinématique mouvement animations fond immersion diagnostic"),
    Route("presence_engine", FAMILIES[0], "Choisir le moteur PRESENCE", "Automatique, Classique 2D Canvas ou Holographique 2.5D GPU ; moteur actif et raison d’un éventuel repli.",
          "moteur automatique canvas gpu moderngl opengl 2d 2.5d sélection basculement secours réessayer"),
    Route("canvas_studio", FAMILIES[0], "Studio Classique 2D", "Conserver et personnaliser l’identité Canvas, indépendamment des réglages GPU.",
          "canvas classique 2d onde graphisme configuration", level="personalize"),
    # Keep this historical ID so existing favourites still open the GPU editor.
    Route("gpu", FAMILIES[0], "Studio Holographique 2.5D", "Prévisualiser le vrai renderer GPU et appliquer ses réglages indépendants ; Canvas reste une alternative permanente.",
          "gpu opengl moderngl rtx holographique 2.5d shader halo anneaux particules performance vram", level="personalize"),
    Route("generation", FAMILIES[1], "Génération et contexte", "Budgets, raisonnement, instruction système et rappel ciblé.",
          "température contexte tokens budget discussion vocal mission raisonnement utilisation instruction système personnalité mémoire ciblée rappel lexical"),
    Route("cognition", FAMILIES[1], "Politique cognitive", "Choisir Manuel, Automatique local, Rapide, Approfondi ou Créatif dans COMMAND OS.",
          "cerveau automatique manuel rapide approfondi créatif mode cognitif"),
    Route("memory", FAMILIES[1], "Mémoire locale", "Consulter, approuver ou modifier les souvenirs et leur provenance.",
          "souvenir historique contexte origine source sauvegarde supprimer approuver document"),
    Route("context", FAMILIES[1], "Inspecter le contexte préparé", "Voir les extraits et les origines sélectionnés pour la requête.",
          "pourquoi réponse provenance mémoire source hypothèse contexte sélectionné", True),
    Route("voice", FAMILIES[2], "Voix et périphériques", "Microphone, sortie, voix installée, préécoute et fin de tour.",
          "micro entrée sortie bluetooth tom siwis piper vitesse débit silence casque haut-parleurs dossier modèles code profil personnalité vad seuil threads cpu"),
    Route("diagnostics", FAMILIES[2], "Diagnostic microphone et transcription", "Signal PCM réel, RMS, VAD, Whisper, erreurs, WAV et comparaison WER.",
          "microphone ouvert sélectionné rms vad whisper stt transcription erreur wav wer latence diagnostic", True),
    Route("reading", FAMILIES[3], "Lecture et typographie", "Aperçu réel des polices, tailles, titres et accents Markdown.",
          "police famille taille échelle densité compact confortable monospace code tableau accent gras italique souligné surligné barré markdown", level="personalize"),
    Route("metrics", FAMILIES[3], "Afficher / masquer les métriques", "Basculer les mesures réelles sous les réponses : TTFT, débit et durée.",
          "tokens seconde ttft durée génération modèle statistiques métriques"),
    Route("navigation", FAMILIES[3], "Replier / ouvrir la barre latérale", "Basculer le menu ; Conversation et PRESENCE restent accessibles.",
          "menu navigation barre latérale réduire sidebar"),
    Route("ollama", FAMILIES[4], "Connexion Ollama et modèle", "Adresse locale dans les paramètres ; modèle installé choisi dans COMMAND OS.",
          "ollama adresse connexion port endpoint modèle qwen local serveur", True),
    Route("model", FAMILIES[4], "Choisir le modèle installé", "Revenir au sélecteur des modèles Ollama de COMMAND OS.",
          "modèle ollama qwen installé liste sélection"),
    Route("local", FAMILIES[4], "Données locales et permissions", "Emplacement SQLite et garanties actuelles d'accès au système.",
          "stockage sqlite dossier données sauvegarde sécurité permissions local disque", True),
    # These are navigation anchors into the same editors, never copied controls.
    Route("wave_thickness", FAMILIES[0], "Épaisseur de l’onde", "Régler le trait dans le Studio ; aucun effet sur le signal microphone.",
          "épaisseur onde trait visualiseur", level="personalize", owner="presence", control="visualizer_thickness"),
    Route("wave_expression", FAMILIES[0], "Expressivité de l’onde", "Amplification graphique indépendante du gain micro et du VAD.",
          "expressivité onde amplitude visuelle", level="personalize", owner="presence", control="wave_expressivity"),
    Route("halo", FAMILIES[0], "Intensité du halo", "Ajuster la lumière du contour dans le Studio existant.",
          "halo intensité lumière", level="personalize", owner="presence", control="halo_intensity"),
    Route("thinking_size", FAMILIES[0], "Taille du noyau THINKING", "Accéder directement à la taille du noyau dans le Studio.",
          "thinking noyau taille", level="personalize", owner="presence", control="thinking_size"),
    Route("gpu_core_size", FAMILIES[0], "GPU · Taille du noyau", "Modifier le rayon apparent de la sphère holographique dans le Studio 2.5D.",
          "gpu noyau rayon taille sphère", level="personalize", owner="gpu", control="core_size"),
    Route("gpu_halo_intensity", FAMILIES[0], "GPU · Luminosité du halo", "Régler la lumière indépendamment du rayon de diffusion.",
          "gpu halo luminosité intensité aura", level="personalize", owner="gpu", control="halo_intensity"),
    Route("gpu_halo_radius", FAMILIES[0], "GPU · Taille du halo", "Régler le rayon de diffusion indépendamment de la luminosité.",
          "gpu halo taille rayon diffusion aura", level="personalize", owner="gpu", control="halo_radius"),
    Route("gpu_ring_speed", FAMILIES[0], "GPU · Vitesse des anneaux", "Ajuster la rotation des orbites holographiques.",
          "gpu anneaux orbites rotation vitesse", level="personalize", owner="gpu", control="ring_speed"),
    Route("gpu_particle_density", FAMILIES[0], "GPU · Quantité de particules", "Densité bornée par le profil de performances, dans le Studio 2.5D.",
          "gpu particules densité quantité", level="personalize", owner="gpu", control="particle_density"),
    Route("gpu_particle_size", FAMILIES[0], "GPU · Taille des particules", "Ajuster la taille des particules sans modifier leur quantité.",
          "gpu particules taille", level="personalize", owner="gpu", control="particle_size"),
    Route("gpu_render_scale", FAMILIES[0], "GPU · Échelle de rendu", "Choisir Auto ou 100–200 % des pixels physiques dans le Studio existant.",
          "gpu échelle rendu résolution définition pixels dpi natif supersampling performance", level="personalize", owner="gpu", control="render_scale"),
    Route("voice_speed", FAMILIES[2], "Vitesse de la voix", "Régler la vitesse Piper dans Voix et périphériques.",
          "vitesse débit voix piper", level="personalize", owner="voice", control="speed"),
    Route("voice_profile", FAMILIES[2], "Profil de lecture", "Discussion, explication technique, récit ou réponse courte : rythme et pauses Piper.",
          "voix profil lecture prosodie technique récit discussion court", level="personalize", owner="voice", control="speech_profile"),
    Route("voice_actions", FAMILIES[2], "Lecture et commandes", "Arrêter, répéter, reprendre, continuer, ralentir ou développer via des boutons accessibles.",
          "voix stop répète reprends continue lentement commandes relecture interruption"),
    Route("turn_silence", FAMILIES[2], "Silence de fin de tour", "Ajuster l’attente de fin de parole dans les réglages vocaux existants.",
          "silence fin tour attente", level="personalize", owner="voice", control="silence_ms"),
    Route("reading_font", FAMILIES[3], "Police de lecture", "Choisir une police dans l’aperçu typographique existant.",
          "police famille lecture", level="personalize", owner="reading", control="family"),
)


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def navigation_preferences(raw):
    """Bounded IDs only: no values from any model, voice or visual preference."""
    raw = raw if isinstance(raw, dict) else {}
    known = {route.key for route in ROUTES}
    values = raw.get("favorites", [])
    favorites = []
    if isinstance(values, list):
        for key in values[:128]:
            if isinstance(key, str) and key in known and key not in favorites:
                favorites.append(key)
    view = raw.get("view", "essential")
    return tuple(favorites), view if isinstance(view, str) and view in VIEWS else "essential"


def find_routes(query="", family=None, advanced=False, *, level=None, favorites=(), only_favorites=False):
    words = normalized(query).split()
    ranks = {"essential": 0, "personalize": 1, "advanced": 2}
    maximum = ranks.get(level, 2 if advanced else 1)
    favorites = set(favorites)
    routes = tuple(route for route in ROUTES
                 if (not words or all(word in normalized(" ".join((route.title, route.description, route.terms, route.family))) for word in words))
                 and (words or only_favorites or family is None or route.family == family)
                 and (words or only_favorites or ranks["advanced" if route.advanced else route.level] <= maximum)
                 and (not only_favorites or route.key in favorites))
    return tuple(sorted(routes, key=lambda route: route.key not in favorites))


class ControlCenter:
    """Two navigation levels: family/search, then the canonical editor."""
    def __init__(self, app):
        from .ui import PANEL, FIELD, TEXT, MUTED, CYAN
        self.app = app
        self._saved_navigation = {}
        self._navigation_error = None
        try:
            raw = app.store.get_preference("control_center", {})
            self._saved_navigation = dict(raw) if isinstance(raw, dict) else {}
        except (OSError, sqlite3.Error, ValueError):
            self._navigation_error = "Impossible de lire les favoris locaux. Fermez puis rouvrez le Centre ; aucun réglage n’a été modifié."
        self.favorites, self._view = navigation_preferences(self._saved_navigation)
        self._changing_view = False
        self.window = dialog = tk.Toplevel(app.root)
        dialog.title("JARVIS · Centre de contrôle")
        dialog.configure(bg=PANEL, padx=14, pady=12)
        dialog.transient(app.root)
        dialog.geometry(f"{min(760, dialog.winfo_screenwidth()-60)}x{min(620, dialog.winfo_screenheight()-100)}")
        dialog.minsize(360, 300)
        self.query, self.family = tk.StringVar(dialog), tk.StringVar(dialog, value=FAMILIES[0])
        self.level = tk.StringVar(dialog, value=VIEWS[self._view])
        footer = ttk.Frame(dialog)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Button(footer, text="Fermer", command=dialog.destroy).pack(side="right")
        self.open_button = ttk.Button(footer, text="Ouvrir", command=self.open_selected)
        self.open_button.pack(side="left")
        self.favorite_button = ttk.Button(footer, text="☆", width=3, command=self.toggle_favorite,
                                         style="Favorite.TButton")
        self.favorite_button.pack(side="left", padx=6)
        self.heading = tk.Label(dialog, text="CENTRE DE CONTRÔLE", bg=PANEL, fg=TEXT, anchor="w")
        self.heading.pack(fill="x")
        self.hint = tk.Label(dialog, text="Une recherche locale, vos réglages habituels. Aucun modèle ni micro requis.",
                             bg=PANEL, fg=MUTED, wraplength=330, justify="left")
        self.hint.pack(anchor="w", pady=(4, 8))
        self.search = ttk.Entry(dialog, name="settings_search", textvariable=self.query)
        self.search.pack(fill="x", pady=(0, 8))
        filters = ttk.Frame(dialog)
        filters.pack(fill="x", pady=(0, 6))
        filters.columnconfigure(0, weight=3)
        filters.columnconfigure(1, weight=2)
        self.category = ttk.Combobox(filters, width=1, textvariable=self.family, values=FAMILIES, state="readonly")
        self.category.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.level_choice = ttk.Combobox(filters, width=1, textvariable=self.level, values=tuple(VIEWS.values()), state="readonly")
        self.level_choice.grid(row=0, column=1, sticky="ew")
        self.detail = tk.Text(dialog, bg=PANEL, fg=MUTED, wrap="word", height=3, width=1,
                              state="disabled", borderwidth=0, takefocus=True,
                              font=(app.font_family, 10))
        self.detail.pack(side="bottom", fill="x", pady=(8, 0))
        self.detail.bind("<Tab>", lambda event: self._tab(event))
        self.detail.bind("<Shift-Tab>", lambda event: self._tab(event, reverse=True))
        self.detail.bind("<ISO_Left_Tab>", lambda event: self._tab(event, reverse=True))
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True)
        # Tk9's default Treeview does not inherit the dark TFrame palette.
        self.result_font = font.Font(dialog, family=app.font_family, size=10)
        style = ttk.Style(dialog)
        style.configure("Favorite.TButton", padding=(5, 7))
        style.configure("Control.Treeview", background=FIELD, fieldbackground=FIELD,
                        foreground=TEXT, font=self.result_font,
                        rowheight=self.result_font.metrics("linespace") + 10)
        style.map("Control.Treeview", background=[("selected", "#244055")],
                  foreground=[("selected", CYAN)])
        self.results = ttk.Treeview(body, style="Control.Treeview", show="tree", selectmode="browse", height=5)
        self.results.column("#0", minwidth=80, width=250, stretch=True)
        scrollbar = ttk.Scrollbar(body, command=self.results.yview)
        self.results.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.results.pack(fill="both", expand=True)
        self.results.bind("<<TreeviewSelect>>", self.describe)
        self.results.bind("<Return>", self.open_selected)
        self.results.bind("<Double-1>", self.open_selected)
        self.search.bind("<Down>", self.focus_results)
        self.search.bind("<Return>", self.open_selected)
        # On Unix, Entry's class binding otherwise deletes a character before
        # the toplevel receives Ctrl+D. Consume the shortcut at the widget.
        self.search.bind("<Control-d>", self.toggle_favorite)
        dialog.bind("<Control-f>", self.focus_search)
        dialog.bind("<Control-d>", self.toggle_favorite)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.bind("<Configure>", self.resize)
        self.traces = [(v, v.trace_add("write", self.refresh)) for v in (self.query, self.family)]
        self.traces.append((self.level, self.level.trace_add("write", self.change_view)))
        dialog.bind("<Destroy>", self.closed)
        self.refresh()
        if self._navigation_error:
            self.set_detail(self._navigation_error)
        self.search.focus_set()

    def refresh(self, *_args):
        previous = self.results.selection()
        self.results.delete(*self.results.get_children())
        routes = find_routes(self.query.get(), self.family.get(),
                             level=self._view, favorites=self.favorites,
                             only_favorites=self._view == "favorites" and not self.query.get().strip())
        for route in routes:
            title = f"{route.title} · {route.family}" if self.query.get().strip() or self._view == "favorites" else route.title
            if route.key in self.favorites:
                title = "★ " + title
            self.results.insert("", "end", iid=route.key, text=title)
        if routes:
            keys = {route.key for route in routes}
            self.results.selection_set(previous[0] if previous and previous[0] in keys else routes[0].key)
        self.open_button.configure(state="normal" if routes else "disabled")
        self.describe()

    def describe(self, _event=None):
        selected = self.results.selection()
        route = next((r for r in ROUTES if selected and r.key == selected[0]), None)
        self.favorite_button.configure(text="★" if route and route.key in self.favorites else "☆",
                                       state="normal" if route and not self._navigation_error else "disabled")
        if self._navigation_error:
            self.set_detail(self._navigation_error)
            return
        self.set_detail((route.description + "\n☆ / Ctrl+D : ajouter ou retirer ce raccourci des favoris.") if route else
                        "Aucun favori enregistré. Recherchez un réglage puis choisissez ☆." if self._view == "favorites" and not self.query.get().strip() else
                        "Aucun réglage trouvé. Essayez un mot plus court ou le niveau Personnaliser / Avancé.")

    def _save_navigation(self, favorites, view):
        if self._navigation_error:
            self.set_detail(self._navigation_error)
            return False
        values = {**self._saved_navigation, "favorites": list(favorites), "view": view}
        try:
            self.app.store.set_preference("control_center", values)
        except (OSError, sqlite3.Error, ValueError):
            self.set_detail("Impossible d’enregistrer les favoris ou la navigation. Vérifiez les droits du dossier et l’espace disque ; votre choix précédent est conservé.")
            return False
        self._saved_navigation = values
        self.favorites, self._view = tuple(favorites), view
        return True

    def change_view(self, *_args):
        if self._changing_view:
            return
        chosen = next((key for key, label in VIEWS.items() if label == self.level.get()), self._view)
        if self._save_navigation(self.favorites, chosen):
            self.refresh()
        else:
            self._changing_view = True
            try:
                self.level.set(VIEWS[self._view])
            finally:
                self._changing_view = False

    def toggle_favorite(self, _event=None):
        selected = self.results.selection()
        if selected:
            key = selected[0]
            candidate = tuple(item for item in self.favorites if item != key) if key in self.favorites else (*self.favorites, key)
            if self._save_navigation(candidate, self._view):
                self.refresh()
        return "break"

    def set_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def resize(self, event):
        if event.widget is not self.window:
            return
        scale = float(self.window.tk.call("tk", "scaling")) / (96 / 72)
        compact = event.height < 480 * scale
        self.detail.configure(height=1 if compact else 3)
        if compact:
            self.heading.pack_forget()
            self.hint.pack_forget()
        else:
            self.heading.pack(before=self.search, fill="x")
            self.hint.pack(before=self.search, anchor="w", pady=(4, 8))

    @staticmethod
    def _tab(event, reverse=False):
        (event.widget.tk_focusPrev() if reverse else event.widget.tk_focusNext()).focus_set()
        return "break"

    def focus_search(self, _event=None):
        self.search.focus_set()
        self.search.selection_range(0, "end")
        return "break"

    def focus_results(self, _event=None):
        self.results.focus_set()
        return "break"

    def open_selected(self, _event=None):
        selected = self.results.selection()
        if not selected:
            return "break"
        key, app = selected[0], self.app
        route = next(route for route in ROUTES if route.key == key)
        if route.owner:
            if route.owner == "voice":
                app.voice.open_settings(focus_key=route.control)
            elif route.owner == "presence":
                dialog = app.presence.open_canvas_settings()
                if dialog is not None:
                    dialog.focus_control(route.control)
            elif route.owner == "gpu":
                dialog = app.presence.open_gpu_settings()
                if dialog is not None:
                    dialog.focus_control(route.control)
            elif route.owner == "reading":
                dialog = app.open_conversation_settings()
                if dialog is not None:
                    dialog.update_idletasks()
                    for widget in descendants(dialog):
                        if widget.winfo_name() == route.control:
                            widget.focus_set()
                            break
            return "break"
        actions = {"presence": app.presence.open_settings,
                   "presence_engine": app.presence.open_engine_settings,
                   "canvas_studio": app.presence.open_canvas_settings,
                   "gpu": app.presence.open_gpu_settings, "generation": app.open_settings,
                   "memory": app.open_memory, "context": app.open_context,
                   "voice": app.voice.open_settings, "diagnostics": app.voice.open_diagnostics,
                   "voice_actions": app.voice.open_actions,
                   "reading": app.open_conversation_settings, "navigation": app.toggle_sidebar}
        if key in actions:
            actions[key]()
        elif key == "metrics":
            app.metrics_visible.set(not app.metrics_visible.get())
            app.toggle_metrics()
        elif key == "cognition":
            if app.sidebar_collapsed:
                app.toggle_sidebar()
            app.root.lift()
            self.window.withdraw()
            app.cognitive_combo.focus_set()
        elif key == "model":
            self.window.withdraw()
            app.root.lift()
            app.model_combo.focus_set()
        elif key == "ollama":
            dialog = app.open_settings()
            if dialog is not None:
                dialog.controls["endpoint"].focus_set()
        elif key == "local":
            path = app.store.db.execute("PRAGMA database_list").fetchone()[2]
            self.set_detail(f"SQLite : {path}\nSauvegardes mémoire conservées. Stockage local non chiffré. Aucun accès système accordé au modèle.")
        return "break"

    def closed(self, event):
        if event.widget is self.window:
            for variable, trace in self.traces:
                variable.trace_remove("write", trace)
            self.app.control_center = None


def descendants(widget):
    """Read-only lookup for existing typography controls; no extra editor."""
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)
