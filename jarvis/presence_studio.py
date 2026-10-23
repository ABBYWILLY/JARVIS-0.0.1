"""Transactional visual editor for the existing, single PRESENCE renderer.

The draft is transient UI state. The only persisted source remains
Store.preference['presence']; optional future renderers can consume the same
validated PresenceSettings instead of creating another settings store.
"""
from dataclasses import asdict
import tkinter as tk
from tkinter import colorchooser, ttk

from .presence import (ACCENT_LABELS, AMBIENCE_LABELS, COLORING_LABELS,
                       EXPRESSION_LABELS, FLUIDITY_LABELS, MICRO_LABELS,
                       MORPH_INTENSITY_LABELS, PALETTE_LABELS, PROFILE_LABELS,
                       SPECTRUM_LABELS, PresenceSettings)


PRESETS = {
    "eco": dict(profile="eco", halos=True, halo_intensity=55, halo_diffusion=70,
                animation_speed=75, transition_speed=100, visualizer_thickness=5),
    "balanced": dict(profile="balanced", halos=True, halo_intensity=80, halo_diffusion=100,
                     animation_speed=100, transition_speed=100, visualizer_thickness=6),
    "cinematic": dict(profile="cinematic", halos=True, halo_intensity=100, halo_diffusion=150,
                      animation_speed=85, transition_speed=85, visualizer_thickness=7),
}
STRUCTURE_LABELS = {"lens": "Lentille organique", "round": "Noyau circulaire",
                    "elongated": "Lentille étirée"}


class PresenceStudio:
    """One draft, one renderer, explicit persistence and reversible comparison."""

    def __init__(self, view):
        self.view = view
        self.baseline = self.draft = view.settings
        self.dirty = set()
        self.previewing = False
        self.closed = False
        self.variables = {}
        self._syncing = False
        self.window = window = tk.Toplevel(view.app.root)
        window.title("PRESENCE Studio 2.0")
        window.transient(view.app.root)
        window.configure(bg="#121c29", padx=12, pady=10)
        sw, sh = window.winfo_screenwidth(), window.winfo_screenheight()
        window.geometry(f"{min(700, max(320, sw - 60))}x{min(730, max(300, sh - 80))}")
        window.minsize(320, 300)
        window.maxsize(max(320, sw - 30), max(300, sh - 40))
        window.protocol("WM_DELETE_WINDOW", self.cancel)
        window.bind("<Escape>", lambda _event: self.cancel())
        window.bind("<Control-Return>", lambda _event: self.apply())
        window.bind("<Destroy>", self._destroyed, add="+")
        ttk.Label(window, text="PRESENCE STUDIO", font=(getattr(view.app, "font_family", "Segoe UI"), 15, "bold")).pack(anchor="w")
        self.status = tk.StringVar(value="Modifiez un brouillon · Appliquer enregistre · Ctrl+Entrée")
        ttk.Label(window, textvariable=self.status, wraplength=440).pack(fill="x", pady=(3, 8))
        # Fixed action rows are reserved before the scrollable content, including
        # at large DPI. No navigation item depends on a tab bar's total width.
        footer = ttk.Frame(window)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        self.action_buttons = {}
        for column, (key, text, command) in enumerate((("cancel", "Annuler", self.cancel), ("restore", "Restaurer", self.restore),
                                                       ("apply", "Appliquer", self.apply))):
            footer.columnconfigure(column, weight=1, uniform="actions")
            button = self.action_buttons[key] = ttk.Button(footer, name=key, text=text, command=command)
            button.grid(row=0, column=column, sticky="ew", padx=2)
        comparison = ttk.Frame(window)
        comparison.pack(side="bottom", fill="x", pady=(6, 0))
        self.comparison = tk.StringVar(value="after")
        ttk.Radiobutton(comparison, text="Avant", variable=self.comparison, value="before",
                        command=self.compare).pack(side="left")
        ttk.Radiobutton(comparison, text="Après", variable=self.comparison, value="after",
                        command=self.compare).pack(side="left", padx=8)
        ttk.Button(comparison, text="Aperçu vivant", command=self.preview).pack(side="right")
        selector = ttk.Frame(window)
        selector.pack(fill="x", pady=(0, 6))
        self.section = tk.StringVar(value="Atelier")
        self.navigation = ttk.Combobox(selector, state="readonly", textvariable=self.section,
                                      values=("Atelier", "Visualiseur", "Spectre et aperçu", "Sous-titres", "Expressions"))
        self.navigation.pack(fill="x")
        style = ttk.Style(window)
        style.layout("Studio.TNotebook.Tab", [])
        self.notebook = ttk.Notebook(window, style="Studio.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.pages = {name: self._page(name) for name in self.navigation.cget("values")}
        self.navigation.bind("<<ComboboxSelected>>", lambda _event:
                             self.notebook.select(list(self.pages).index(self.section.get())))
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event:
                           self.section.set(self.notebook.tab(self.notebook.select(), "text")))
        self._build()
        self.navigation.focus_set()

    def _page(self, title):
        outer = ttk.Frame(self.notebook)
        self.notebook.add(outer, text=title)
        canvas = tk.Canvas(outer, highlightthickness=0, bg="#121c29", takefocus=False)
        scroll = ttk.Scrollbar(outer, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        inner = ttk.Frame(canvas, padding=8)
        item = canvas.create_window(0, 0, window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        def resized(event):
            canvas.itemconfigure(item, width=event.width)
            for child in inner.winfo_children():
                if isinstance(child, ttk.Label):
                    child.configure(wraplength=max(100, event.width - 24))
        canvas.bind("<Configure>", resized)
        def reveal(event):
            if not str(event.widget).startswith(str(inner) + "."):
                return
            y = event.widget.winfo_rooty() - inner.winfo_rooty()
            bottom = y + event.widget.winfo_height()
            top = canvas.canvasy(0)
            if y < top or bottom > top + canvas.winfo_height():
                canvas.yview_moveto(max(0, bottom - canvas.winfo_height()) / max(1, inner.winfo_height()))
        self.window.bind("<FocusIn>", reveal, add="+")
        def wheel(event):
            if str(event.widget).startswith(str(inner)) and not isinstance(event.widget, (ttk.Combobox, tk.Scale)):
                up = getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0
                canvas.yview_scroll(-3 if up else 3, "units")
                return "break"
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.window.bind(sequence, wheel, add="+")
        return inner

    def _label(self, page, text):
        ttk.Label(page, text=text, wraplength=440, justify="left").pack(fill="x", pady=(8, 3))

    def _choice(self, page, key, label, choices):
        self._label(page, label)
        variable = self.variables[key] = tk.StringVar(value=choices[getattr(self.draft, key)])
        widget = ttk.Combobox(page, name=key, textvariable=variable, state="readonly", values=list(choices.values()))
        widget.pack(fill="x", pady=(0, 5))
        widget.bind("<<ComboboxSelected>>", lambda _event: self.change(**{
            key: next(option for option, text in choices.items() if text == variable.get())}))
        variable._studio_choices = choices

    def _scale(self, page, key, label, low, high):
        self._label(page, label)
        variable = self.variables[key] = tk.IntVar(value=getattr(self.draft, key))
        tk.Scale(page, name=key, from_=low, to=high, resolution=1, orient="horizontal", variable=variable,
                 bg="#121c29", fg="#e4edf6", troughcolor="#203040", highlightthickness=0,
                 command=lambda value: self.change(**{key: round(float(value))}) if not self._syncing else None).pack(fill="x")

    def _check(self, page, key, label):
        variable = self.variables[key] = tk.BooleanVar(value=getattr(self.draft, key))
        tk.Checkbutton(page, name=key, text=label, variable=variable, bg="#121c29", fg="#e4edf6",
                       selectcolor="#203040", activebackground="#121c29", activeforeground="#e4edf6",
                       wraplength=360, anchor="w", justify="left",
                       command=lambda: self.change(**{key: variable.get()})).pack(fill="x", pady=5)

    def _build(self):
        workshop, visual, spectrum, captions, expressions = self.pages.values()
        self._label(workshop, "Un seul visualiseur réel · aperçus sans micro, Ollama ni Piper.\n"
                    "Les signaux de démonstration sont explicitement synthétiques.")
        self.preset = tk.StringVar(value=PROFILE_LABELS[self.draft.profile])
        ttk.Combobox(workshop, name="preset", textvariable=self.preset, state="readonly",
                     values=list(PROFILE_LABELS.values())).pack(fill="x", pady=4)
        ttk.Button(workshop, text="Charger le préréglage", command=lambda: self.load_preset(
            next(key for key, text in PROFILE_LABELS.items() if text == self.preset.get()))).pack(fill="x")
        self._label(workshop, "Éco limite le travail graphique ; Cinématique augmente le halo et le plafond de rendu.\n"
                    "Aucun préréglage ne change les modèles, l’audio ou les permissions.")
        self._choice(workshop, "ambience", "Ambiance visuelle", AMBIENCE_LABELS)
        self._choice(workshop, "thinking_structure", "Structure du noyau THINKING", STRUCTURE_LABELS)
        self._scale(workshop, "thinking_size", "Taille du noyau THINKING (%)", 70, 130)
        ttk.Button(workshop, text="Prévisualiser le noyau THINKING", command=self.preview).pack(fill="x", pady=5)
        ttk.Button(workshop, text="Prévisualiser la ligne sans signal", command=lambda:
                   self.preview(lambda: self.view.preview_workshop("line"))).pack(fill="x", pady=5)
        ttk.Button(workshop, text="Démo · signaux synthétiques", command=self.demo).pack(fill="x", pady=5)
        ttk.Button(workshop, text="Arrêter l’aperçu", command=self.stop_preview).pack(fill="x", pady=5)
        self._check(workshop, "mini_mode", "Mode Mini-PRESENCE · même fenêtre et même visualiseur")
        self._label(workshop, "Canvas reste le moteur de production. Le prototype GPU séparé n’est pas activé ici ;\n"
                    "ces préférences validées constituent le contrat commun pour un futur adaptateur.")
        self._choice(visual, "profile", "Qualité graphique (plafond de rendu)", PROFILE_LABELS)
        self._scale(visual, "visualizer_thickness", "Épaisseur du visualiseur", 1, 10)
        self._scale(visual, "wave_expressivity", "Expressivité de l’onde (%) · affichage seulement", 0, 100)
        self._check(visual, "halos", "Halos lumineux")
        self._scale(visual, "halo_intensity", "Intensité lumineuse (%)", 0, 100)
        self._scale(visual, "halo_diffusion", "Diffusion du halo (%) · étalement des contours", 50, 180)
        self._choice(visual, "fluidity", "Fluidité des courbes", FLUIDITY_LABELS)
        self._scale(visual, "animation_speed", "Vitesse des animations symboliques (%)", 50, 150)
        self._scale(visual, "transition_speed", "Vitesse des transitions géométriques (%)", 50, 150)
        self._check(visual, "animations", "Animations visuelles")
        self._check(visual, "reduced_motion", "Réduire les mouvements")
        ttk.Button(visual, text="Choisir le fond…", command=lambda: self.choose_color("background")).pack(fill="x", pady=5)
        ttk.Button(visual, text="Rétablir le noir", command=lambda: self.change(background="#000000")).pack(fill="x", pady=4)
        self._label(visual, "Les vitesses concernent les formes symboliques, jamais le PCM, les seuils VAD ou Piper.\n"
                    "La réduction de mouvement reste prioritaire, y compris après un préréglage.")
        self._choice(spectrum, "emotional_palette", "Palette émotionnelle", PALETTE_LABELS)
        self._choice(spectrum, "accent_mode", "Accents de tonalité", ACCENT_LABELS)
        self._choice(spectrum, "spectrum_mode", "Interprétation locale du spectre", SPECTRUM_LABELS)
        self._scale(spectrum, "spectrum_intensity", "Intensité du spectre (%)", 0, 100)
        ttk.Button(spectrum, text="Choisir la couleur d’accent…", command=lambda: self.choose_color("fixed_color")).pack(fill="x", pady=5)
        self._label(spectrum, "Aperçu local · phrase au choix ; estimation sans effet sur les permissions.")
        self.phrase = tk.StringVar(value="Je suis heureux et ravi.")
        ttk.Entry(spectrum, textvariable=self.phrase).pack(fill="x", pady=4)
        ttk.Button(spectrum, text="Prévisualiser la phrase", command=lambda:
                   self.preview(lambda: self.view.preview_text(self.phrase.get()))).pack(fill="x", pady=4)
        self._check(expressions, "microexpressions", "Microexpressions contextuelles")
        self.micro_family = tk.StringVar(value=MICRO_LABELS["surprise"])
        ttk.Combobox(expressions, name="micro_family", textvariable=self.micro_family, state="readonly",
                     values=list(MICRO_LABELS.values())).pack(fill="x", pady=4)
        ttk.Button(expressions, text="Prévisualiser la microexpression", command=lambda: self.preview(lambda:
            self.view.preview_workshop(next(key for key, text in MICRO_LABELS.items() if text == self.micro_family.get())))).pack(fill="x", pady=4)
        self._check(expressions, "semantic_morphing", "Semantic Morphing")
        self._choice(expressions, "morph_intensity", "Intensité de l’expression", MORPH_INTENSITY_LABELS)
        self.morph_family = tk.StringVar(value=EXPRESSION_LABELS["smile"])
        ttk.Combobox(expressions, name="morph_family", textvariable=self.morph_family, state="readonly",
                     values=list(EXPRESSION_LABELS.values())).pack(fill="x", pady=4)
        ttk.Button(expressions, text="Prévisualiser l’expression", command=lambda: self.preview(lambda:
            self.view.preview_expression(next(key for key, text in EXPRESSION_LABELS.items() if text == self.morph_family.get())))).pack(fill="x", pady=4)
        self._label(expressions, "Huit familles vectorielles existantes. Priorité à la parole réelle ; synchronisation\n"
                    "estimée par segment PCM. Mouvement réduit : symbole statique, retour au noyau.")
        self._check(captions, "subtitles", "Afficher les sous-titres")
        self._check(captions, "emotional_subtitles", "Sous-titres émotionnels")
        self._choice(captions, "subtitle_coloring", "Colorisation des mots-clés", COLORING_LABELS)
        self._scale(captions, "subtitle_size", "Taille préférée · ajustée dans les petites fenêtres", 12, 32)
        self._check(captions, "diagnostic_mode", "Mode Diagnostic (F9) · indicateurs détaillés")
        self._check(captions, "timing_monitor", "Afficher le moniteur temporel")
        self._label(captions, "Deux lignes maximum. Les indicateurs de microphone, arrêt et sécurité restent\n"
                    "visibles en Immersion. Aucun réglage ici ne démarre une capture.")

    def _sync(self):
        self._syncing = True
        try:
            for key, variable in self.variables.items():
                value = getattr(self.draft, key)
                choices = getattr(variable, "_studio_choices", None)
                variable.set(choices[value] if choices else value)
        finally:
            self._syncing = False

    def change(self, **changes):
        if self.closed or self._syncing:
            return
        self.draft = PresenceSettings.from_dict({**asdict(self.draft), **changes})
        self.dirty = {key for key, value in asdict(self.draft).items() if value != getattr(self.baseline, key)}
        self.status.set("Brouillon modifié · non enregistré")
        if self.previewing:
            self.view._apply_options(self.baseline if self.comparison.get() == "before" else self.draft)

    def rebase(self, candidate, changed):
        """Real F9/F10/background actions win, without saving unrelated draft values."""
        edits = {key: getattr(self.draft, key) for key in self.dirty - changed}
        self.baseline = candidate
        self.draft = PresenceSettings.from_dict({**asdict(candidate), **edits})
        self.dirty = {key for key in edits if getattr(self.draft, key) != getattr(candidate, key)}
        self._sync()
        if self.previewing:
            self.view._apply_options(candidate if self.comparison.get() == "before" else self.draft)

    def load_preset(self, key):
        self.change(**PRESETS[key])
        self._sync()

    def restore(self):
        self.change(**asdict(PresenceSettings()))
        self._sync()
        self.status.set("Valeurs d’origine dans le brouillon · Appliquer pour enregistrer")

    def _available(self):
        view = self.view
        preview_active = view._workshop_preview or view._semantic_preview or view._preview_text is not None
        return (not view.app.voice.listening and not getattr(view.app, "operation", None)
                and (view.state in {"silent", "dormant"} or preview_active))

    def compare(self):
        if not self._available():
            self.status.set("Aperçu indisponible pendant l’écoute ou une réponse réelle")
            return False
        self.previewing = True
        self.view._apply_options(self.baseline if self.comparison.get() == "before" else self.draft)
        self.status.set("Comparaison " + ("Avant · réglages enregistrés" if self.comparison.get() == "before" else "Après · brouillon non enregistré"))
        return True

    def preview(self, action=None):
        if not self.compare():
            return False
        self.view.show()
        self.view.clear_preview()
        result = (action or self.view.preview_workshop)()
        self.window.lift()
        return result

    def demo(self):
        from .presence_demo import DemoController
        if not self.compare():
            return False
        self.view.show()
        self.view.clear_preview()
        if self.view._demo is None:
            self.view._demo = DemoController(self.view)
        result = self.view._demo.start()
        self.window.lift()
        return result

    def stop_preview(self):
        self.view.clear_preview()
        self.suspend_preview()

    def suspend_preview(self):
        if self.previewing:
            self.previewing = False
            self.view._apply_options(self.baseline)
            self.status.set("Aperçu arrêté · brouillon conservé, priorité aux événements réels")

    def choose_color(self, key):
        _, color = colorchooser.askcolor(getattr(self.draft, key), parent=self.window, title="Couleur PRESENCE")
        if color:
            self.change(**{key: color.lower()}, **({"accent_mode": "fixed"} if key == "fixed_color" else {}))
            self._sync()

    def apply(self):
        if self.closed:
            return False
        edits = {key: getattr(self.draft, key) for key in self.dirty}
        if edits and not self.view.set_options(**edits):
            return False
        self.status.set("Préférences enregistrées localement")
        return True

    def cancel(self):
        if self.closed:
            return
        self.closed = True
        self.view.clear_preview()
        self.view._apply_options(self.baseline)
        self.view.studio = None
        self.view.settings_dialog = None
        if self.window.winfo_exists():
            self.window.destroy()

    def _destroyed(self, event):
        if event.widget is self.window:
            self.cancel()
