"""Transactional GPU-only artist editor, using the existing preference owner.

No graphics context or audio is opened by this module. The view owns preview,
real-event priority, engine restoration and SQLite writes. This editor only
keeps a transient validated draft and describes implemented renderer controls.
"""
import tkinter as tk
from tkinter import ttk
import unicodedata

from .gpu_config import FIELD_SPECS, GpuSettings, LEVELS, PROFILES, RENDER_SCALES, SECTIONS


LEVEL_LABELS = {"essential": "Essentiel", "personalize": "Personnaliser", "advanced": "Avancé"}
PROFILE_LABELS = {"eco": "Éco", "balanced": "Équilibré", "cinematic": "Cinématique"}
SCALE_LABELS = {value: "Auto" if value == "auto" else value + " %" for value in RENDER_SCALES}
SCALE_TERMS = "render_scale échelle rendu gpu résolution définition pixels natif supersampling dpi performance"
ESSENTIAL_SECTION = "Réglages essentiels"
PREVIEW_STATES = ("Repos", "Écoute", "THINKING", "Parole", "Sourire 😊", "Rire 😂", "Cœur ❤️", "Interruption")


def _search_text(value):
    return "".join(char for char in unicodedata.normalize("NFKD", str(value).casefold())
                   if not unicodedata.combining(char))


def find_settings(query="", section=ESSENTIAL_SECTION, level="essential"):
    """Search across sections/levels; normal browsing stays progressively small."""
    words = _search_text(query).split()
    rank = LEVELS.index(level) if level in LEVELS else 0
    matches = []
    for key, spec in FIELD_SPECS.items():
        if words:
            haystack = _search_text(" ".join((key, spec.label, spec.section, spec.help)))
            if not all(word in haystack for word in words):
                continue
        elif section == ESSENTIAL_SECTION:
            if spec.level != "essential":
                continue
        elif spec.section != section or LEVELS.index(spec.level) > rank:
            continue
        matches.append(key)
    if (words and all(word in _search_text(SCALE_TERMS) for word in words)
            or not words and section == "Performances" and rank >= LEVELS.index("personalize")):
        matches.append("render_scale")
    # Searches remain usable even for a very broad term; every field remains
    # reachable by its section or direct focus instead of making a 66-row page.
    return tuple(matches[:24])


class GpuStudio:
    """One validated draft, real previews, explicit Apply and reversible Cancel."""

    def __init__(self, view):
        self.view = view
        self.baseline = self.draft = view.gpu_settings
        self.dirty = set()
        self.previewing = self.closed = self._syncing = False
        self.variables, self.controls, self.rows = {}, {}, {}
        self._footer_mode = None
        self.window = window = tk.Toplevel(view.app.root)
        window.focus_control = self.focus_control
        window.controls = self.controls
        window.title("PRESENCE Studio · Holographique 2.5D")
        # COMMAND OS may be withdrawn while the independent GPU window is
        # active. A transient of a hidden owner can itself stay unmapped on Tk.
        if view.app.root.winfo_viewable():
            window.transient(view.app.root)
        window.configure(bg="#121c29", padx=10, pady=10)
        width, height = window.winfo_screenwidth(), window.winfo_screenheight()
        window.geometry(f"{min(700, max(340, width-60))}x{min(760, max(360, height-80))}")
        window.minsize(320, 300)
        window.maxsize(max(320, width-30), max(300, height-40))
        window.protocol("WM_DELETE_WINDOW", self.cancel)
        window.bind("<Escape>", lambda _event: self.cancel())
        window.bind("<Control-Return>", lambda _event: self.apply())
        window.bind("<Control-f>", self.focus_search)
        window.bind("<Destroy>", self._destroyed, add="+")

        # Reserve critical actions before content. Filters are scrollable too,
        # so large fonts/DPI cannot pack essential buttons outside the window.
        self.footer = footer = ttk.Frame(window)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        self.action_buttons = {}
        for key, label, action in (("cancel", "Annuler", self.cancel),
                                   ("restore", "Restaurer", self.restore),
                                   ("apply", "Appliquer", self.apply)):
            self.action_buttons[key] = ttk.Button(footer, name=key, text=label, command=action)
        footer.bind("<Configure>", self._layout_footer)
        self._layout_footer()
        comparison = ttk.Frame(window)
        comparison.pack(side="bottom", fill="x", pady=(5, 0))
        for index in range(3):
            comparison.columnconfigure(index, weight=1)
        self.comparison = tk.StringVar(value="after")
        ttk.Radiobutton(comparison, text="Avant", variable=self.comparison, value="before",
                        command=self.compare).grid(row=0, column=0, sticky="ew")
        ttk.Radiobutton(comparison, text="Après", variable=self.comparison, value="after",
                        command=self.compare).grid(row=0, column=1, sticky="ew")
        ttk.Button(comparison, name="preview", text="Aperçu", command=self.preview).grid(row=0, column=2, sticky="ew")

        family = getattr(view.app, "font_family", "Segoe UI")
        ttk.Label(window, text="STUDIO · GPU 2.5D", font=(family, 14, "bold")).pack(anchor="w", pady=(0, 5))
        body = ttk.Frame(window)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="#121c29", highlightthickness=0, takefocus=False)
        scrollbar = ttk.Scrollbar(body, command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.content = content = ttk.Frame(self.canvas, padding=(2, 0, 8, 8))
        self._content_item = self.canvas.create_window(0, 0, anchor="nw", window=content)
        content.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resized)
        window.bind("<FocusIn>", self._reveal_focus, add="+")
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            window.bind(sequence, self._wheel, add="+")

        self.status = tk.StringVar(value="Brouillon local · Appliquer enregistre · aperçu sans micro ni modèle")
        self.status_label = ttk.Label(content, textvariable=self.status, wraplength=560, justify="left")
        self.status_label.pack(fill="x", pady=(0, 6))
        ttk.Button(content, text="Moteur actif, préférences communes et réglages 2D…",
                   command=view.open_engine_settings).pack(fill="x", pady=(0, 8))
        filters = ttk.Frame(content)
        filters.pack(fill="x")
        filters.columnconfigure(0, weight=3)
        filters.columnconfigure(1, weight=2)
        self.section = tk.StringVar(value=ESSENTIAL_SECTION)
        self.level = tk.StringVar(value=LEVEL_LABELS["essential"])
        self.section_choice = ttk.Combobox(filters, name="section", width=1, state="readonly", textvariable=self.section,
                                            values=(ESSENTIAL_SECTION, *SECTIONS))
        self.section_choice.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.level_choice = ttk.Combobox(filters, name="level", width=1, state="readonly", textvariable=self.level,
                                         values=tuple(LEVEL_LABELS.values()))
        self.level_choice.grid(row=0, column=1, sticky="ew")
        self.section_choice.bind("<<ComboboxSelected>>", self.refresh)
        self.level_choice.bind("<<ComboboxSelected>>", self._level_changed)
        ttk.Label(content, text="Rechercher un réglage · Ctrl+F").pack(anchor="w", pady=(8, 2))
        self.query = tk.StringVar()
        self.search = ttk.Entry(content, name="search", textvariable=self.query)
        self.search.pack(fill="x")
        self._query_trace = self.query.trace_add("write", self.refresh)
        self.results = tk.StringVar()
        ttk.Label(content, textvariable=self.results, wraplength=560).pack(fill="x", pady=(4, 8))

        self.quick = ttk.Frame(content)
        self.quick.pack(fill="x", pady=(0, 8))
        self.preview_state_var = tk.StringVar(value="THINKING")
        ttk.Combobox(self.quick, name="preview_state", width=1, state="readonly",
                     textvariable=self.preview_state_var, values=PREVIEW_STATES).pack(fill="x")
        ttk.Button(self.quick, name="preview_state_button", text="Voir cet état · aperçu identifié",
                   command=lambda: self.preview_state(self.preview_state_var.get())).pack(fill="x", pady=3)
        ttk.Button(self.quick, name="stop_preview", text="Arrêter l’aperçu", command=self.stop_preview).pack(fill="x")
        self.fields = ttk.Frame(content)
        self.fields.pack(fill="x")
        self.profile_row = ttk.Frame(self.fields)
        ttk.Label(self.profile_row, text="Profil graphique").pack(anchor="w")
        self.profile = tk.StringVar(value=PROFILE_LABELS[self.draft.profile])
        profile_widget = self.controls["profile"] = ttk.Combobox(self.profile_row, name="profile", state="readonly",
                 textvariable=self.profile, values=tuple(PROFILE_LABELS.values()))
        profile_widget.pack(fill="x", pady=(3, 0))
        profile_widget.bind("<<ComboboxSelected>>", lambda _event: self.change(profile=next(
            key for key, label in PROFILE_LABELS.items() if label == self.profile.get())))
        ttk.Button(self.profile_row, text="Charger ce préréglage", command=lambda: self.load_preset(next(
            key for key, label in PROFILE_LABELS.items() if label == self.profile.get()))).pack(fill="x", pady=4)
        ttk.Button(self.profile_row, name="reference_30", text="Charger le style de référence 3.0",
                   command=self.load_reference).pack(fill="x", pady=4)
        ttk.Label(self.profile_row, text="Le profil limite le coût graphique ; le style 3.0 conserve le noyau approuvé.",
                  wraplength=560).pack(fill="x")

        scale_row = self.rows["render_scale"] = ttk.Frame(self.fields)
        ttk.Label(scale_row, text="Échelle de rendu GPU").pack(anchor="w", pady=(7, 0))
        self.render_scale = tk.StringVar(value=SCALE_LABELS[self.draft.render_scale])
        scale_choice = self.controls["render_scale"] = ttk.Combobox(scale_row, name="render_scale",
            state="readonly", textvariable=self.render_scale, values=tuple(SCALE_LABELS.values()))
        scale_choice.pack(fill="x", pady=3)
        scale_choice.bind("<<ComboboxSelected>>", lambda _event: self.change(render_scale=next(
            key for key, label in SCALE_LABELS.items() if label == self.render_scale.get())))
        ttk.Label(scale_row, wraplength=560, justify="left", text=
            "Facteur des pixels physiques, pas une résolution fixe. Auto permet l'adaptation ; "
            "125–200 % coûtent davantage. Plafonds : 8,29 Mpx et 4096 pixels par dimension. "
            "F9 affiche le rendu effectivement utilisé.").pack(fill="x", pady=(0, 6))

        for key, spec in FIELD_SPECS.items():
            row = self.rows[key] = ttk.Frame(self.fields)
            ttk.Label(row, text=spec.label).pack(anchor="w", pady=(7, 0))
            variable = self.variables[key] = tk.IntVar(value=getattr(self.draft, key))
            widget = self.controls[key] = tk.Scale(row, name=key, orient="horizontal", from_=spec.low, to=spec.high,
                resolution=spec.step, variable=variable, bg="#121c29", fg="#e4edf6", troughcolor="#203040",
                highlightthickness=0, takefocus=True,
                command=lambda value, name=key: self.change(**{name: round(float(value))}) if not self._syncing else None)
            widget.pack(fill="x")
            ttk.Label(row, text=spec.help, wraplength=560, justify="left").pack(fill="x", pady=(0, 6))
        self.refresh()
        self.search.focus_set()

    def _layout_footer(self, event=None):
        width = event.width if event is not None else 680
        needed = sum(button.winfo_reqwidth() for button in self.action_buttons.values()) + 16
        compact = width < needed
        if compact == self._footer_mode:
            return
        self._footer_mode = compact
        for button in self.action_buttons.values():
            button.grid_forget()
        for index in range(3):
            self.footer.columnconfigure(index, weight=1 if index < (2 if compact else 3) else 0,
                                        uniform="gpu_actions")
        if compact:
            self.action_buttons["cancel"].grid(row=0, column=0, sticky="ew", padx=2, pady=2)
            self.action_buttons["apply"].grid(row=0, column=1, sticky="ew", padx=2, pady=2)
            self.action_buttons["restore"].grid(row=1, column=0, columnspan=2, sticky="ew", padx=2, pady=2)
        else:
            for index, key in enumerate(("cancel", "restore", "apply")):
                self.action_buttons[key].grid(row=0, column=index, sticky="ew", padx=2, pady=2)

    def _level_key(self):
        return next((key for key, label in LEVEL_LABELS.items() if label == self.level.get()), "essential")

    def _level_changed(self, _event=None):
        if self.section.get() == ESSENTIAL_SECTION and self._level_key() != "essential":
            self.section.set(SECTIONS[0])
        self.refresh()

    def refresh(self, *_args):
        if self.closed:
            return
        visible = find_settings(self.query.get(), self.section.get(), self._level_key())
        for row in self.rows.values():
            row.pack_forget()
        self.profile_row.pack_forget()
        words = _search_text(self.query.get())
        show_profile = (not words and self.section.get() in {ESSENTIAL_SECTION, "Performances"}
                        or words and all(word in _search_text("profile profil qualité performance éco équilibré cinématique")
                                         for word in words.split()))
        if show_profile:
            self.profile_row.pack(fill="x", pady=(0, 6))
        for key in visible:
            self.rows[key].pack(fill="x")
        count = len(visible) + bool(show_profile)
        self.results.set(f"{count} réglage(s) · recherche globale, jusqu’à 24 résultats" if words else
                         f"{count} réglage(s) · {self.section.get()} · {self.level.get()}")
        self.canvas.yview_moveto(0)

    def _resized(self, event):
        self.canvas.itemconfigure(self._content_item, width=event.width)
        wrap = max(120, event.width-22)
        for parent in (self.content, self.profile_row, *self.rows.values()):
            for child in parent.winfo_children():
                if isinstance(child, ttk.Label):
                    child.configure(wraplength=wrap)

    def _reveal_widget(self, widget):
        self.window.update_idletasks()
        y = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = y + widget.winfo_height()
        top = self.canvas.canvasy(0)
        if y < top:
            self.canvas.yview_moveto(y/max(1, self.content.winfo_height()))
        elif bottom > top+self.canvas.winfo_height():
            self.canvas.yview_moveto(max(0, bottom-self.canvas.winfo_height())/max(1, self.content.winfo_height()))

    def _reveal_focus(self, event):
        if str(event.widget).startswith(str(self.content)+"."):
            self._reveal_widget(event.widget)

    def _wheel(self, event):
        if str(event.widget).startswith(str(self.content)) and not isinstance(event.widget, (tk.Scale, ttk.Combobox)):
            up = getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0
            self.canvas.yview_scroll(-3 if up else 3, "units")
            return "break"

    def focus_search(self, _event=None):
        self.search.focus_set()
        self._reveal_widget(self.search)
        return "break"

    def focus_control(self, key):
        if self.closed or key not in self.controls:
            return False
        self.query.set("")
        if key in {"profile", "render_scale"}:
            self.section.set("Performances")
            if key == "render_scale":
                self.level.set(LEVEL_LABELS["personalize"])
        else:
            spec = FIELD_SPECS[key]
            self.section.set(spec.section)
            self.level.set(LEVEL_LABELS[spec.level])
        self.refresh()
        self.window.deiconify()
        self.window.lift()
        widget = self.controls[key]
        widget.focus_force()
        self._reveal_widget(widget)
        return True

    def _sync(self):
        self._syncing = True
        try:
            for key, variable in self.variables.items():
                variable.set(getattr(self.draft, key))
            self.profile.set(PROFILE_LABELS[self.draft.profile])
            self.render_scale.set(SCALE_LABELS[self.draft.render_scale])
        finally:
            self._syncing = False

    def change(self, **changes):
        if self.closed or self._syncing:
            return
        self.draft = GpuSettings.from_dict(self.draft.to_dict() | changes)
        self.dirty = {key for key, value in self.draft.to_dict().items() if value != getattr(self.baseline, key)}
        self.status.set("Brouillon modifié · non enregistré")
        if self.previewing:
            self.compare()

    def rebase(self, candidate, changed):
        edits = {key: getattr(self.draft, key) for key in self.dirty-set(changed)}
        self.baseline = candidate
        self.draft = GpuSettings.from_dict(candidate.to_dict() | edits)
        self.dirty = {key for key in edits if getattr(self.draft, key) != getattr(candidate, key)}
        self._sync()
        if self.previewing:
            self.compare()

    def load_preset(self, key):
        if key not in PROFILES:
            return False
        self.change(**GpuSettings.from_dict({"profile": key}).to_dict())
        self._sync()
        self.status.set("Préréglage « "+PROFILE_LABELS[key]+" » dans le brouillon · Appliquer pour enregistrer")
        return True

    def restore(self):
        self.change(**GpuSettings().to_dict())
        self._sync()
        self.status.set("Réglages GPU 3.1 par défaut dans le brouillon · Appliquer pour enregistrer")

    def load_reference(self):
        # This is an artwork preset, not a second renderer or a performance
        # migration. Keep the chosen profile, scale and user frame limit.
        reference = GpuSettings.reference_30(profile=self.draft.profile).to_dict()
        reference.update(render_scale=self.draft.render_scale, fps_limit=self.draft.fps_limit)
        self.change(**reference)
        self._sync()
        self.status.set("Style approuvé 3.0 dans le brouillon · cadence et échelle conservées · Appliquer pour enregistrer")
        return True

    def compare(self):
        if self.closed:
            return False
        candidate = self.baseline if self.comparison.get() == "before" else self.draft
        if not self.view.preview_gpu_options(candidate):
            self.status.set("Aperçu indisponible · vérifiez le moteur GPU ou terminez l’échange en cours")
            return False
        self.previewing = True
        self.status.set("Aperçu GPU · "+("Avant, réglages enregistrés" if self.comparison.get() == "before" else
                                      "Après, brouillon non enregistré")+" · aucun micro ni modèle")
        return True

    def preview(self):
        if not self.compare():
            return False
        return bool(self.view.preview_gpu_state(self.preview_state_var.get()))

    def preview_state(self, label):
        if label not in PREVIEW_STATES or not self.compare():
            return False
        result = bool(self.view.preview_gpu_state(label))
        if result:
            self.status.set("Aperçu identifié · PCM synthétique si nécessaire · aucun micro ni modèle")
        return result

    def suspend_preview(self):
        if self.previewing:
            self.previewing = False
            self.view.end_gpu_preview()
            self.status.set("Aperçu arrêté · priorité aux événements réels · brouillon conservé")

    def stop_preview(self):
        self.suspend_preview()

    def apply(self):
        if self.closed:
            return False
        edits = {key: getattr(self.draft, key) for key in self.dirty}
        if edits and not self.view.set_gpu_options(**edits):
            self.status.set("Enregistrement impossible · brouillon conservé")
            return False
        self.rebase(self.view.gpu_settings, set(edits))
        self.status.set("Préférences GPU enregistrées localement")
        return True

    def cancel(self):
        if self.closed:
            return
        self.closed = True
        self.suspend_preview()
        if self._query_trace is not None:
            self.query.trace_remove("write", self._query_trace)
            self._query_trace = None
        if getattr(self.view, "gpu_studio", None) is self:
            self.view.gpu_studio = None
        if getattr(self.view, "settings_dialog", None) is self.window:
            self.view.settings_dialog = None
        if self.window.winfo_exists():
            self.window.destroy()

    def _destroyed(self, event):
        if event.widget is self.window:
            self.cancel()
