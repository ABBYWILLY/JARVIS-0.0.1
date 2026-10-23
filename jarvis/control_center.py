"""Searchable navigation to the existing preference owners; no copied values."""
from dataclasses import dataclass
import tkinter as tk
from tkinter import font, ttk
import unicodedata


FAMILIES = ("PRESENCE", "Conversation et mémoire", "Voix", "Interface",
            "Système, sécurité et performances")


@dataclass(frozen=True)
class Route:
    key: str
    family: str
    title: str
    description: str
    terms: str
    advanced: bool = False


ROUTES = (
    Route("presence", FAMILIES[0], "PRESENCE Studio", "Personnaliser et comparer le rendu, puis appliquer vos choix.",
          "onde épaisseur expressivité halo diffusion lumière noyau thinking structure vitesse transitions palette couleur émotion microexpression morphing emoji sous-titres mini éco équilibré cinématique mouvement animations fond immersion diagnostic"),
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
          "police famille taille échelle densité compact confortable monospace code tableau accent gras italique souligné surligné barré markdown"),
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
    Route("gpu", FAMILIES[4], "Canvas et prototype GPU", "Canvas reste actif. Le prototype OpenGL est autonome et expérimental.",
          "gpu opengl moderngl rtx canvas performance vram consommation moteur", True),
)


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def find_routes(query="", family=None, advanced=False):
    words = normalized(query).split()
    return tuple(route for route in ROUTES
                 if (not words or all(word in normalized(" ".join((route.title, route.description, route.terms, route.family))) for word in words))
                 and (words or family is None or route.family == family)
                 and (words or advanced or not route.advanced))


class ControlCenter:
    """Two navigation levels: family/search, then the canonical editor."""
    def __init__(self, app):
        from .ui import PANEL, FIELD, TEXT, MUTED, CYAN
        self.app = app
        self.window = dialog = tk.Toplevel(app.root)
        dialog.title("JARVIS · Centre de contrôle")
        dialog.configure(bg=PANEL, padx=14, pady=12)
        dialog.transient(app.root)
        dialog.geometry(f"{min(760, dialog.winfo_screenwidth()-60)}x{min(620, dialog.winfo_screenheight()-100)}")
        dialog.minsize(360, 300)
        self.query, self.family = tk.StringVar(dialog), tk.StringVar(dialog, value=FAMILIES[0])
        self.advanced = tk.BooleanVar(dialog, value=False)
        footer = ttk.Frame(dialog)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Button(footer, text="Fermer", command=dialog.destroy).pack(side="right")
        self.open_button = ttk.Button(footer, text="Ouvrir", command=self.open_selected)
        self.open_button.pack(side="left")
        self.heading = tk.Label(dialog, text="CENTRE DE CONTRÔLE", bg=PANEL, fg=TEXT, anchor="w")
        self.heading.pack(fill="x")
        self.hint = tk.Label(dialog, text="Une recherche locale, vos réglages habituels. Aucun modèle ni micro requis.",
                             bg=PANEL, fg=MUTED, wraplength=330, justify="left")
        self.hint.pack(anchor="w", pady=(4, 8))
        self.search = ttk.Entry(dialog, name="settings_search", textvariable=self.query)
        self.search.pack(fill="x", pady=(0, 8))
        self.category = ttk.Combobox(dialog, textvariable=self.family, values=FAMILIES, state="readonly")
        self.category.pack(fill="x", pady=(0, 6))
        self.advanced_button = ttk.Checkbutton(dialog, text="Afficher les réglages avancés", variable=self.advanced)
        self.advanced_button.pack(anchor="w", pady=(0, 6))
        self.detail = tk.Text(dialog, bg=PANEL, fg=MUTED, wrap="word", height=3, width=1,
                              state="disabled", borderwidth=0, takefocus=True)
        self.detail.pack(side="bottom", fill="x", pady=(8, 0))
        self.detail.bind("<Tab>", lambda event: self._tab(event))
        self.detail.bind("<Shift-Tab>", lambda event: self._tab(event, reverse=True))
        self.detail.bind("<ISO_Left_Tab>", lambda event: self._tab(event, reverse=True))
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True)
        # Tk9's default Treeview does not inherit the dark TFrame palette.
        self.result_font = font.Font(dialog, family=app.font_family, size=10)
        style = ttk.Style(dialog)
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
        dialog.bind("<Control-f>", self.focus_search)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.bind("<Configure>", self.resize)
        self.traces = [(v, v.trace_add("write", self.refresh)) for v in (self.query, self.family, self.advanced)]
        dialog.bind("<Destroy>", self.closed)
        self.refresh()
        self.search.focus_set()

    def refresh(self, *_args):
        self.results.delete(*self.results.get_children())
        routes = find_routes(self.query.get(), self.family.get(), self.advanced.get())
        for route in routes:
            title = f"{route.title} · {route.family}" if self.query.get().strip() else route.title
            self.results.insert("", "end", iid=route.key, text=title)
        if routes:
            self.results.selection_set(routes[0].key)
        self.open_button.configure(state="normal" if routes else "disabled")
        self.describe()

    def describe(self, _event=None):
        selected = self.results.selection()
        route = next((r for r in ROUTES if selected and r.key == selected[0]), None)
        self.set_detail(route.description if route else "Aucun réglage trouvé. Essayez un mot plus court.")

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
        actions = {"presence": app.presence.open_settings, "generation": app.open_settings,
                   "memory": app.open_memory, "context": app.open_context,
                   "voice": app.voice.open_settings, "diagnostics": app.voice.open_diagnostics,
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
        elif key == "gpu":
            self.set_detail("Canvas actif · prototype OpenGL autonome. Validation RTX en attente. Réglages visuels communs ; aucune activation GPU en production. Guide : docs/PRESENCE-GPU.md.")
        return "break"

    def closed(self, event):
        if event.widget is self.window:
            for variable, trace in self.traces:
                variable.trace_remove("write", trace)
            self.app.control_center = None
