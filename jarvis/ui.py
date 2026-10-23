"""COMMAND OS: Tk main thread owns widgets/storage; inference is isolated."""
import json
import sqlite3
import tkinter as tk
from dataclasses import replace
from tkinter import font, messagebox, ttk

from .config import Settings
from .context import ContextBuilder
from .metrics import generation_metrics, metrics_label
from .worker import Worker

BG, PANEL, FIELD = "#0b1019", "#121c29", "#192638"
TEXT, MUTED, CYAN, RED = "#e4edf6", "#a6b8cb", "#65e0ef", "#ff9c9c"
SURFACE, BORDER = "#101925", "#2b4053"
COGNITIVE_LABELS = {"manual": "Manuel · profil J2.8", "auto": "Automatique local",
                    "fast": "Rapide", "deep": "Approfondi", "creative": "Créatif"}


def cognitive_label(record):
    """The selected application policy, not a claim about model intelligence."""
    if not isinstance(record, dict) or not record:
        return "Politique non enregistrée pour cette réponse ancienne."
    mode = {"fast": "Rapide", "deep": "Approfondi", "creative": "Créatif",
            "model_default": "Choix du modèle"}.get(record.get("mode"), "—")
    origin = "heuristique locale" if record.get("origin") == "local_heuristic" else "réglage manuel"
    return f"Mode choisi : {mode} · {record.get('budget', '—')} tokens maximum · {origin}"


class RoundedSurface(tk.Canvas):
    """One static rounded shell around native, accessible Tk widgets.

    One Canvas item per surface, no animation, images or message widgets. Text
    remains in the existing Text widget for selection and incremental streaming.
    """
    def __init__(self, parent, *, color):
        super().__init__(parent, bg=BG, highlightthickness=0, borderwidth=0, height=1)
        self.outline = self.create_polygon(0, 0, 0, 0, smooth=True, splinesteps=24,
                                           fill=color, outline=BORDER, width=1)
        self.body = tk.Frame(self, bg=color)
        # Native geometry propagation keeps the composer fitted to font/DPI
        # changes, including before the first paint of a very small window.
        self.body.pack(fill="both", expand=True, padx=12, pady=10)
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        w, h = max(2, event.width - 1), max(2, event.height - 1)
        r = min(16, w / 3, h / 3)
        self.coords(self.outline, r, 1, w-r, 1, w, 1, w, r, w, h-r,
                    w, h, w-r, h, r, h, 1, h, 1, h-r, 1, r, 1, 1)

    def focus_ring(self, active):
        self.itemconfigure(self.outline, outline=CYAN if active else BORDER)


class App:
    def __init__(self, root, store, refresh=True):
        self.root, self.store = root, store
        self.worker = Worker()
        self.operation = None
        self.message_id = None
        self.response = ""
        self.response_metrics = {}
        self.continuation_id = None
        self.models = []
        self.dead_polls = 0
        self.closed = False
        self.settings = store.settings()
        families = {family.casefold(): family for family in font.families(root)}
        self.font_family = next((families[name] for name in ("segoe ui", "dejavu sans", "helvetica") if name in families), "TkDefaultFont")
        root.title("JARVIS UNHINGED NEXT · 0.0.1")
        root.geometry("1100x760")
        root.minsize(560, 400)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self.callback_error
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=PANEL, foreground=TEXT, font=(self.font_family, 11))
        style.configure("TButton", padding=(12, 7), background=FIELD, foreground=TEXT,
                        borderwidth=1, relief="flat", bordercolor=FIELD, focusthickness=1,
                        focuscolor=CYAN)
        style.map("TButton", background=[("disabled", PANEL), ("pressed", "#2b4b61"), ("active", "#244055")],
                  foreground=[("disabled", "#7b8999")], bordercolor=[("focus", CYAN), ("active", BORDER)])
        style.configure("Primary.TButton", background=CYAN, foreground=BG, bordercolor=CYAN)
        style.map("Primary.TButton", background=[("disabled", FIELD), ("pressed", "#40bfce"), ("active", "#96f1f7")],
                  foreground=[("disabled", MUTED), ("!disabled", BG)])
        style.configure("Quiet.TButton", background=PANEL, bordercolor=PANEL, foreground=MUTED)
        style.configure("Danger.TButton", foreground=RED)
        style.map("Danger.TButton", foreground=[("disabled", "#7b8999"), ("!disabled", RED)])
        style.configure("TCombobox", fieldbackground=FIELD, foreground=TEXT, arrowcolor=CYAN,
                        bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, padding=(6, 3))
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], selectbackground=[("readonly", FIELD)],
                  bordercolor=[("focus", CYAN), ("!focus", BORDER)])
        style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"sticky": "nswe", "expand": True})]})])
        style.configure("Vertical.TScrollbar", background=BORDER, troughcolor=BG, arrowcolor=CYAN,
                        bordercolor=BG, lightcolor=BORDER, darkcolor=BORDER, borderwidth=0, arrowsize=9)
        style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT)
        style.configure("TCheckbutton", background=PANEL, foreground=MUTED, focuscolor=CYAN)
        style.map("TCheckbutton", foreground=[("active", TEXT), ("selected", CYAN)])
        root.option_add("*TCombobox*Listbox.background", FIELD)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)

        # Essential navigation never competes with history or audio diagnostics
        # for the sidebar's height. Secondary controls scroll independently.
        self.navigation = tk.Frame(root, bg=PANEL, padx=8, pady=5)
        self.navigation.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.navigation_font = font.Font(root=root, family=self.font_family, size=9)
        style.configure("Navigation.TButton", font=self.navigation_font, padding=(8, 5),
                        background=PANEL, bordercolor=PANEL)
        style.map("Navigation.TButton", background=[("selected", FIELD), ("active", FIELD)],
                  foreground=[("selected", CYAN)])
        self.sidebar_button = ttk.Button(self.navigation, text="Menu", style="Navigation.TButton",
                                         command=self.toggle_sidebar, width=0)
        self.conversation_button = ttk.Button(self.navigation, text="Conversation", style="Navigation.TButton",
                                              command=self.focus_conversation, width=0)
        self.presence_button = ttk.Button(self.navigation, text="PRESENCE", style="Navigation.TButton",
                                          command=lambda: self.presence.show(), width=0)
        self.emergency_button = ttk.Button(self.navigation, text="Arrêt", style="Navigation.TButton",
                                           command=lambda: self.voice.emergency(), width=0)
        for button in (self.sidebar_button, self.conversation_button, self.presence_button, self.emergency_button):
            button.pack(side="left", padx=2)
        self.conversation_button.state(["selected"])
        self.sidebar_collapsed = store.get_preference("sidebar_collapsed", False) is True
        self._sidebar_manual = None
        self._navigation_layout = None
        self.sidebar = tk.Frame(root, bg=PANEL)
        self.sidebar_canvas = tk.Canvas(self.sidebar, bg=PANEL, highlightthickness=0, width=270, height=1)
        sidebar_scroll = ttk.Scrollbar(self.sidebar, command=self.sidebar_canvas.yview)
        sidebar_scroll.pack(side="right", fill="y")
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        self.sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)
        sidebar = tk.Frame(self.sidebar_canvas, bg=PANEL, padx=14, pady=12)
        self.sidebar_content = sidebar
        sidebar_item = self.sidebar_canvas.create_window(0, 0, anchor="nw", window=sidebar)
        sidebar.bind("<Configure>", lambda _event: self.sidebar_canvas.configure(
            scrollregion=self.sidebar_canvas.bbox("all")))
        self.sidebar_canvas.bind("<Configure>", lambda event: self.sidebar_canvas.itemconfigure(
            sidebar_item, width=event.width))
        root.bind("<FocusIn>", self._reveal_sidebar_focus, add="+")
        root.bind("<MouseWheel>", self._sidebar_wheel, add="+")
        root.bind("<Button-4>", self._sidebar_wheel, add="+")
        root.bind("<Button-5>", self._sidebar_wheel, add="+")
        self.sidebar_canvas.bind("<MouseWheel>", self._scroll_sidebar)
        self.sidebar_canvas.bind("<Button-4>", lambda _event: self.sidebar_canvas.yview_scroll(-3, "units"))
        self.sidebar_canvas.bind("<Button-5>", lambda _event: self.sidebar_canvas.yview_scroll(3, "units"))
        tk.Label(sidebar, text="J A R V I S", bg=PANEL, fg=CYAN,
                 font=(self.font_family, 21, "bold")).pack(anchor="w")
        tk.Label(sidebar, text="COMMAND OS  /  LOCAL", bg=PANEL, fg=MUTED,
                 font=(self.font_family, 9)).pack(anchor="w", pady=(2, 22))
        self.new_button = ttk.Button(sidebar, text="+ Nouvelle conversation", command=self.new_session)
        self.new_button.pack(fill="x")
        tk.Label(sidebar, text="CONVERSATIONS", bg=PANEL, fg=MUTED,
                 font=(self.font_family, 9)).pack(anchor="w", pady=(24, 8))
        history_frame = tk.Frame(sidebar, bg=PANEL)
        history_frame.pack(fill="both", expand=True)
        self.history = tk.Listbox(history_frame, bg=PANEL, fg=TEXT, selectbackground="#244055",
            selectforeground=CYAN, borderwidth=0, highlightthickness=1, highlightcolor=CYAN,
            highlightbackground=FIELD, font=(self.font_family, 10), width=20, height=8, activestyle="dotbox", exportselection=False)
        history_scroll = ttk.Scrollbar(history_frame, command=self.history.yview)
        self.history.configure(yscrollcommand=history_scroll.set)
        self.history.pack(side="left", fill="both", expand=True)
        history_scroll.pack(side="right", fill="y")
        self.history.bind("<<ListboxSelect>>", self.select_session)
        self.delete_button = ttk.Button(sidebar, text="Supprimer la conversation", command=self.delete_session, style="Quiet.TButton")
        self.delete_button.pack(fill="x", pady=(10, 6))
        tools = self.conversation_tools = tk.Frame(sidebar, bg=PANEL)
        tools.pack(fill="x", pady=(12, 8))
        tk.Label(tools, text="CONVERSATION", bg=PANEL, fg=MUTED,
                 font=(self.font_family, 9)).pack(anchor="w", pady=(0, 6))
        self.cognitive_var = tk.StringVar(value=COGNITIVE_LABELS[getattr(self.settings, "cognitive_mode", "manual")])
        self.cognitive_combo = ttk.Combobox(tools, name="cognitive_mode", textvariable=self.cognitive_var,
                                          values=list(COGNITIVE_LABELS.values()), state="readonly", width=1)
        self.cognitive_combo.pack(fill="x", pady=(0, 6))
        self.cognitive_combo.bind("<<ComboboxSelected>>", self.change_cognitive_mode)
        preferences = tk.Frame(sidebar, bg=PANEL)
        preferences.pack(fill="x", pady=(6, 8))
        tk.Label(preferences, text="PRÉFÉRENCES", bg=PANEL, fg=MUTED,
                 font=(self.font_family, 9)).pack(anchor="w", pady=(0, 6))
        self.settings_button = ttk.Button(preferences, text="Paramètres", command=self.open_settings)
        self.settings_button.pack(fill="x")
        ttk.Button(preferences, text="Lecture et typographie", command=self.open_conversation_settings).pack(fill="x", pady=4)
        tk.Label(sidebar, text="VOIX LOCALE", bg=PANEL, fg=MUTED,
                 font=(self.font_family, 9)).pack(anchor="w", pady=(12, 0))
        from .voice_ui import VoiceControls
        self.voice = VoiceControls(self, sidebar)
        from .presence import PresenceView
        self.presence = PresenceView(self)
        tk.Label(sidebar, text="Outils système : désactivés",
                 justify="left", bg=PANEL, fg=MUTED, font=(self.font_family, 9)).pack(anchor="w", pady=(16, 0))

        top = self.model_panel = tk.Frame(root, bg=BG, padx=20, pady=15)
        top.grid(row=1, column=1, sticky="ew")
        self.model_heading = tk.Label(top, text="COMMAND OS  /  CONVERSATION", bg=BG, fg=TEXT, font=(self.font_family, 12, "bold"))
        self.model_heading.pack(anchor="w")
        model_row = self.model_row = tk.Frame(top, bg=BG)
        model_row.pack(fill="x", pady=(6, 0))
        self.model_var = tk.StringVar(value=self.settings.model)
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_var, state="readonly", width=1)
        self.model_combo.bind("<<ComboboxSelected>>", self.change_model)
        self.refresh_button = ttk.Button(model_row, text="Actualiser", command=self.refresh_models)
        self.refresh_button.pack(side="right", padx=(10, 0))
        self.model_combo.pack(side="left", fill="x", expand=True)
        self.status = tk.StringVar(value="Prêt. Sélectionnez un modèle Ollama local.")
        self.status_label = tk.Label(top, textvariable=self.status, bg=BG, fg=CYAN,
            justify="left", anchor="w", wraplength=650, font=(self.font_family, 10))
        self.status_label.pack(fill="x", pady=(12, 0))
        self.status_label.configure(takefocus=True, cursor="hand2")
        self.status_label.bind("<Button-1>", self.show_status)
        self.status_label.bind("<Return>", self.show_status)
        top.bind("<Configure>", lambda e: self.status_label.configure(wraplength=max(200, e.width - 40)))

        chat_frame = tk.Frame(root, bg=BG, padx=20)
        chat_frame.grid(row=2, column=1, sticky="nsew")
        self.chat_surface = RoundedSurface(chat_frame, color=SURFACE)
        self.chat_surface.pack(fill="both", expand=True)
        self.chat = tk.Text(self.chat_surface.body, bg=SURFACE, fg=TEXT, wrap="word", state="disabled",
            font=(self.font_family, 12), padx=8, pady=8, borderwidth=0,
            highlightthickness=0,
            selectbackground="#244055", insertbackground=CYAN)
        self.chat.bind("<FocusIn>", lambda _event: self.chat_surface.focus_ring(True))
        self.chat.bind("<FocusOut>", lambda _event: self.chat_surface.focus_ring(False))
        scroll = self.chat_scroll = ttk.Scrollbar(self.chat_surface.body, command=self.chat.yview)
        self.chat.configure(yscrollcommand=scroll.set)
        # Reserve the scrollbar before the wide native Text asks for space.
        scroll.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_configure("speaker", foreground=CYAN, font=(self.font_family, 10, "bold"), spacing1=18, spacing3=8)
        self.chat.tag_configure("speaker_user", foreground=MUTED, font=(self.font_family, 10, "bold"), spacing1=18, spacing3=8)
        self.chat.tag_configure("message_user", background=FIELD, lmargin1=14, lmargin2=14,
                                rmargin=14, spacing1=8, spacing3=10)
        self.chat.tag_configure("welcome", foreground=TEXT, font=(self.font_family, 20, "bold"), spacing1=24, spacing3=12)
        self.chat.tag_configure("meta", foreground=MUTED, font=(self.font_family, 9), spacing3=10)
        self.chat.tag_configure("policy", foreground=MUTED, font=(self.font_family, 9), spacing3=6)
        self.metrics_visible = tk.BooleanVar(value=store.get_preference("show_generation_metrics", False) is True)
        self.chat.tag_configure("metrics", foreground=MUTED, font=(self.font_family, 9),
                                spacing3=10, elide=not self.metrics_visible.get())
        from .markdown_view import ConversationTypography, MarkdownView
        self.markdown = MarkdownView(self.chat, self.font_family, TEXT, MUTED, CYAN, FIELD)
        self.conversation_families = tuple(sorted(font.families(root), key=str.casefold))
        self.conversation_preferences = store.get_preference("conversation", {})
        self.typography = ConversationTypography.from_dict(self.conversation_preferences, self.conversation_families,
                                                          self.markdown.code_families)
        self._apply_conversation_typography(self.typography)
        self.conversation_dialog = None
        self.assistant_region = None
        compose = self.compose_panel = tk.Frame(root, bg=BG, padx=20, pady=14)
        compose.grid(row=3, column=1, sticky="ew")
        self.input_surface = RoundedSurface(compose, color=FIELD)
        self.input_surface.pack(fill="x")
        self.input = tk.Text(self.input_surface.body, height=3, bg=FIELD, fg=TEXT, insertbackground=CYAN,
            wrap="word", font=(self.font_family, 11), padx=2, pady=2, borderwidth=0,
            highlightthickness=0)
        self.input.pack(fill="x")
        self.input.bind("<FocusIn>", lambda _event: self.input_surface.focus_ring(True))
        self.input.bind("<FocusOut>", lambda _event: self.input_surface.focus_ring(False))
        self.input.bind("<Control-Return>", lambda e: self.send() or "break")
        self.input_font = font.Font(root=root, family=self.markdown.body_font.actual("family"),
                                    size=self.markdown.body_font.actual("size"))
        self.input.configure(font=self.input_font)
        actions = tk.Frame(self.input_surface.body, bg=FIELD)
        actions.pack(fill="x", pady=(8, 0))
        self.compose_hint = tk.Label(actions, text="Ctrl + Entrée : envoyer · Entrée : nouvelle ligne",
                 bg=FIELD, fg=MUTED, font=(self.font_family, 9))
        style.configure("Metrics.TCheckbutton", background=PANEL, foreground=MUTED,
                        font=(self.font_family, 9))
        self.metrics_toggle = ttk.Checkbutton(tools, text="Métriques de génération", variable=self.metrics_visible,
            command=self.toggle_metrics, style="Metrics.TCheckbutton")
        self.metrics_toggle.pack(fill="x", pady=3)
        self.context_button = ttk.Button(tools, text="Contexte", command=self.open_context)
        self.context_button.pack(fill="x", pady=3)
        self.memory_button = ttk.Button(tools, text="Mémoire", command=self.open_memory)
        self.memory_button.pack(fill="x", pady=3)
        self.send_button = ttk.Button(actions, text="Envoyer", command=self.send, width=0, style="Primary.TButton")
        self.send_button.pack(side="right")
        self.stop_button = ttk.Button(actions, text="Arrêter", command=self.cancel, state="disabled", width=0, style="Danger.TButton")
        self.stop_button.pack(side="right", padx=8)
        self.continue_button = ttk.Button(actions, name="continue_response", text="Continuer", width=0,
                                         command=self.continue_response, style="Quiet.TButton", state="disabled")
        self.continue_button.pack(side="right")
        self.compose_hint.pack(side="left")
        root.rowconfigure(2, weight=1)
        root.columnconfigure(1, weight=1)
        self.session_id = None
        self.reload_history()
        if self.session_rows:
            self.session_id = self.session_rows[0]["id"]
        else:
            self.session_id = store.new_session()
        self.reload_history()
        self.render_session()
        self.input.focus_set()
        root.bind("<F6>", self.toggle_sidebar)
        root.bind("<F7>", lambda _event: self.presence.show() or "break")
        root.bind("<F8>", self.focus_conversation)
        root.bind("<Configure>", self._responsive_navigation, add="+")
        root.update_idletasks()
        self._responsive_navigation()
        self.poll_id = root.after(40, self.poll)
        if refresh:
            self.refresh_models()

    def toggle_sidebar(self, _event=None):
        visible = bool(self.sidebar.winfo_manager())
        self.sidebar_collapsed = visible
        self._sidebar_manual = not visible
        self.store.set_preference("sidebar_collapsed", self.sidebar_collapsed)
        self._responsive_navigation()
        if self._sidebar_manual:
            self.new_button.focus_set()
        else:
            self.sidebar_button.focus_set()
        return "break"

    def focus_conversation(self, _event=None):
        if self.sidebar.winfo_manager() == "place":
            self._sidebar_manual = False
            self._responsive_navigation()
        if self.presence.window is not None and self.presence.window.winfo_exists():
            self.presence.return_to_command()
        self.root.deiconify()
        self.root.lift()
        self.input.focus_set()
        return "break"

    def _scroll_sidebar(self, event):
        self.sidebar_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _sidebar_wheel(self, event):
        if (str(event.widget).startswith(str(self.sidebar_content) + ".")
                and not isinstance(event.widget, (tk.Listbox, tk.Text, ttk.Combobox))):
            amount = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
            self.sidebar_canvas.yview_scroll(amount * 3, "units")
            return "break"

    def show_status(self, _event=None):
        messagebox.showinfo("Statut complet de JARVIS", self.status.get(), parent=self.root)
        return "break"

    def _reveal_sidebar_focus(self, event):
        if not str(event.widget).startswith(str(self.sidebar_content) + "."):
            return
        self.sidebar_content.update_idletasks()
        y = event.widget.winfo_rooty() - self.sidebar_content.winfo_rooty()
        bottom = y + event.widget.winfo_height()
        top = self.sidebar_canvas.canvasy(0)
        if y < top or bottom > top + self.sidebar_canvas.winfo_height():
            self.sidebar_canvas.yview_moveto(max(0, bottom - self.sidebar_canvas.winfo_height())
                                            / max(1, self.sidebar_content.winfo_height()))

    def _responsive_navigation(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        width, height = self.root.winfo_width(), self.root.winfo_height()
        scale = max(.75, float(self.root.tk.call("tk", "scaling")) / (96 / 72))
        compact = width < round(980 * scale) or height < round(680 * scale)
        wide = width >= round(980 * scale)
        show_sidebar = self._sidebar_manual if self._sidebar_manual is not None else not self.sidebar_collapsed and wide
        layout = (width, height, scale, show_sidebar, compact, self.typography)
        if layout == self._navigation_layout:
            return
        self._navigation_layout = layout
        self.sidebar.grid_forget()
        self.sidebar.place_forget()
        if show_sidebar:
            if wide:
                self.sidebar_canvas.configure(width=round(270 * scale))
                self.sidebar.grid(row=1, column=0, rowspan=3, sticky="nsew")
            else:
                self.sidebar.place(x=0, y=self.navigation.winfo_reqheight(),
                    width=min(width - 24, round(290 * scale)),
                    height=max(80, height - self.navigation.winfo_reqheight()))
                self.sidebar.lift()
        self.navigation.lift()
        self.conversation_button.configure(text="Chat" if compact else "Conversation")
        self.continue_button.configure(text="Suite" if compact else "Continuer")
        # Fit the essential labels even on a physically small high-DPI window.
        self.navigation_font.configure(size=9)
        self.navigation.update_idletasks()
        requested = sum(button.winfo_reqwidth() + 4 for button in
                        (self.sidebar_button, self.conversation_button, self.presence_button, self.emergency_button)) + 16
        if requested > width:
            pixels = max(12, round(9 * (96 / 72) * scale * width / requested))
            self.navigation_font.configure(size=-pixels)
        self.model_panel.configure(padx=10 if compact else 20, pady=5 if compact else 15)
        self.compose_panel.configure(padx=10 if compact else 20, pady=5 if compact else 14)
        self.input.configure(height=1 if compact else 3)
        self.input_font.configure(family=self.markdown.body_font.actual("family"),
            size=min(18, self.markdown.body_font.actual("size")) if compact else self.markdown.body_font.actual("size"))
        self.status_label.configure(height=(1 if height < max(500, round(240 * scale)) else 2) if compact else 0)
        if compact:
            self.model_heading.pack_forget()
            self.compose_hint.pack_forget()
        else:
            self.model_heading.pack(anchor="w", before=self.model_row)
            self.compose_hint.pack(side="left")

    def set_conversation_typography(self, **changes):
        from .markdown_view import ConversationTypography
        options = {**self.typography.to_dict(), **changes}
        validated = ConversationTypography.from_dict(options, self.conversation_families, self.markdown.code_families)
        if any(getattr(validated, key, None) != value for key, value in changes.items()):
            raise ValueError("Choisissez une police installée (monospace pour le code), une taille de 9 à 24, une échelle de 75 à 175 % et des accents de 0 à 100 %.")
        saved = self.conversation_preferences if isinstance(self.conversation_preferences, dict) else {}
        saved = {**saved, **validated.to_dict()}
        self.store.set_preference("conversation", saved)
        self.conversation_preferences, self.typography = saved, validated
        self._apply_conversation_typography(validated)

    def _apply_conversation_typography(self, validated):
        self.markdown.configure_typography(validated)
        # Reading fonts are reused; the composer adapts in compact windows.
        # Controls and PRESENCE retain their own geometry and preferences.
        for tag, base in (("speaker", 10), ("speaker_user", 10), ("meta", 9), ("metrics", 9), ("policy", 9), ("welcome", 20)):
            size = max(8, round((base + validated.size - 12) * validated.scale / 100))
            self.chat.tag_configure(tag, font=(validated.family or self.font_family, size,
                                              "bold" if tag in {"speaker", "speaker_user", "welcome"} else "normal"))
        if hasattr(self, "input_font"):
            self._responsive_navigation()

    def open_conversation_settings(self):
        if self.conversation_dialog is not None and self.conversation_dialog.winfo_exists():
            self.conversation_dialog.lift()
            return
        dialog = self.conversation_dialog = tk.Toplevel(self.root)
        dialog.title("COMMAND OS · lecture")
        dialog.transient(self.root)
        dialog.configure(bg=PANEL, padx=16, pady=12)
        width, height = min(620, dialog.winfo_screenwidth() - 60), min(430, dialog.winfo_screenheight() - 100)
        dialog.geometry(f"{width}x{height}")
        footer = ttk.Frame(dialog)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        body = tk.Frame(dialog, bg=PANEL)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, bg=PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        content = tk.Frame(canvas, bg=PANEL)
        item = canvas.create_window(0, 0, anchor="nw", window=content)
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        def wheel(event):
            if str(event.widget).startswith(str(content)) and not isinstance(event.widget, (ttk.Combobox, tk.Scale)):
                direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
                canvas.yview_scroll(direction * 3, "units")
                return "break"
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            dialog.bind(sequence, wheel, add="+")
        def reveal(event):
            if not str(event.widget).startswith(str(content) + "."):
                return
            y = event.widget.winfo_rooty() - content.winfo_rooty()
            bottom = y + event.widget.winfo_height()
            top = canvas.canvasy(0)
            if y < top or bottom > top + canvas.winfo_height():
                canvas.yview_moveto(max(0, bottom - canvas.winfo_height()) / max(1, content.winfo_height()))
        dialog.bind("<FocusIn>", reveal, add="+")
        variables = {
            "family": tk.StringVar(value=self.typography.family or self.markdown.family),
            "size": tk.StringVar(value=str(self.typography.size)),
            "scale": tk.StringVar(value=str(self.typography.scale)),
            "spacing": tk.StringVar(value="Compact" if self.typography.spacing == "compact" else "Confortable"),
            "code_family": tk.StringVar(value=self.typography.code_family or self.markdown.fixed_family),
            "accent_intensity": tk.IntVar(value=self.typography.accent_intensity),
        }
        for key, label, values in (("family", "Police installée", self.conversation_families),
                                    ("size", "Taille du texte (9–24 points)", None),
                                    ("scale", "Échelle de lecture (75–175 %)", None),
                                    ("spacing", "Densité de lecture", ("Compact", "Confortable")),
                                    ("code_family", "Police monospace du code et des tableaux", self.markdown.code_families)):
            tk.Label(content, text=label, bg=PANEL, fg=TEXT).pack(anchor="w", pady=(8, 3))
            if values is None:
                ttk.Entry(content, name=key, textvariable=variables[key]).pack(fill="x")
            else:
                ttk.Combobox(content, name=key, textvariable=variables[key], values=values,
                             state="readonly").pack(fill="x")
        accent_label = tk.StringVar()
        def show_accent(*_args):
            accent_label.set(f"Intensité des accents visuels : {variables['accent_intensity'].get()} %")
        variables["accent_intensity"].trace_add("write", show_accent)
        show_accent()
        tk.Label(content, textvariable=accent_label, bg=PANEL, fg=TEXT).pack(anchor="w", pady=(8, 3))
        tk.Scale(content, name="accent_intensity", from_=0, to=100, resolution=1, orient="horizontal",
                 variable=variables["accent_intensity"], bg=PANEL, fg=TEXT, troughcolor=FIELD,
                 highlightthickness=0, activebackground=CYAN, takefocus=True).pack(fill="x")

        def reset():
            from .markdown_view import ConversationTypography
            try:
                self.set_conversation_typography(**ConversationTypography().to_dict())
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror("Lecture", str(exc), parent=dialog)
                return
            for key, value in self.typography.to_dict().items():
                if key == "family":
                    value = value or self.markdown.family
                elif key == "code_family":
                    value = value or self.markdown.fixed_family
                elif key == "spacing":
                    value = "Compact" if value == "compact" else "Confortable"
                variables[key].set(value)
        ttk.Button(content, name="reset_typography", text="Réglages d’origine", command=reset).pack(fill="x", pady=(12, 4))
        tk.Label(content, bg=PANEL, fg=MUTED, justify="left", wraplength=max(240, width - 55),
                 text="Titres, listes et code gardent leur hiérarchie.\n"
                      "Markdown : **gras**, *italique*, listes, liens, code.\n"
                      "Extensions : ~~barré~~ (GFM), ++souligné++, ==surligné==.\n"
                      "Tableaux textuels ; formules simples, sans composition LaTeX.\n"
                      "Clic droit ou Ctrl+Maj+C : copier la réponse originale.\n"
                      "Ctrl+C : copier la sélection affichée.").pack(anchor="w", pady=12)

        def save():
            try:
                self.set_conversation_typography(family=variables["family"].get(), size=int(variables["size"].get()),
                    scale=int(variables["scale"].get()),
                    spacing="compact" if variables["spacing"].get() == "Compact" else "comfortable",
                    code_family=variables["code_family"].get(), accent_intensity=variables["accent_intensity"].get())
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror("Lecture", str(exc), parent=dialog)
                return
            dialog.destroy()

        def closed(event):
            if event.widget is dialog:
                self.conversation_dialog = None

        dialog.bind("<Destroy>", closed)
        ttk.Button(footer, text="Enregistrer", command=save).pack(side="right")
        ttk.Button(footer, text="Fermer", command=dialog.destroy).pack(side="left")

    def set_status(self, text, error=False):
        from .spectrum import OPERATIONAL
        self.status.set(("ERREUR · " if error else "") + text)
        key = "error" if error else "info"
        self.status_label.configure(fg=OPERATIONAL[key]["color"])
        if hasattr(self, "presence"):
            self.presence.update_operation(key, text)

    def append(self, text, tag=None):
        at_bottom = self.chat.yview()[1] >= 0.98
        self.chat.configure(state="normal")
        self.chat.insert("end", text, tag or ())
        self.chat.configure(state="disabled")
        if at_bottom:
            self.chat.see("end")

    def reload_history(self):
        self.session_rows = self.store.sessions()
        self.history.delete(0, "end")
        for index, row in enumerate(self.session_rows):
            self.history.insert("end", row["title"])
            if row["id"] == self.session_id:
                self.history.selection_set(index)

    def toggle_metrics(self):
        self.store.set_preference("show_generation_metrics", self.metrics_visible.get())
        # Elision only changes presentation, including during an active stream.
        self.chat.tag_configure("metrics", elide=not self.metrics_visible.get())

    def remember_generation_metrics(self, values):
        metrics = generation_metrics({**self.response_metrics, **generation_metrics(values)})
        if metrics != self.response_metrics:
            self.store.update_message_metadata(self.message_id, {"generation_metrics": metrics})
            self.response_metrics = metrics

    def render_session(self):
        self.markdown.reset()
        self.assistant_region = None
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        rows = self.store.messages(self.session_id)
        last = rows[-1] if rows else None
        self.continuation_id = (last["id"] if last is not None and last["role"] == "assistant"
                                and last["status"] != "streaming" and last["content"].strip() else None)
        self.update_continue_button()
        if not rows:
            self.append("Que souhaitez-vous explorer ?\n", "welcome")
            self.append("Choisissez un modèle local, puis partagez une question, une idée ou un projet.\n", "meta")
        for row in rows:
            self.append(("VOUS" if row["role"] == "user" else "JARVIS · " + row["model"]) + "\n",
                        "speaker_user" if row["role"] == "user" else "speaker")
            if row["role"] == "assistant":
                metadata = json.loads(row["metadata"])
                if metadata.get("cognition"):
                    self.append(cognitive_label(metadata["cognition"]) + "\n", "policy")
                region = self.markdown.append(row["content"], final=row["status"] != "streaming")
                if row["status"] == "streaming":
                    self.assistant_region = region
                else:
                    self.append("\n")
            else:
                self.append(row["content"] + "\n", "message_user")
            if row["status"] not in {"complete", "streaming"}:
                self.append({"streaming": "En cours", "cancelled": "Arrêtée", "error": "Échec",
                             "interrupted": "Interrompue à la fermeture"}[row["status"]] + "\n", "meta")
            if row["role"] == "assistant" and row["status"] != "streaming":
                metadata = json.loads(row["metadata"])
                self.append("Texte généré non vérifié · Contexte / provenance dans le menu.\n", "policy")
                self.append(metrics_label(metadata.get("generation_metrics")) + "\n", "metrics")
        self.chat.see("end")

    def new_session(self):
        if self.operation:
            return
        if hasattr(self, "voice"):
            self.voice.stop_listening()
        self.session_id = self.store.new_session()
        self.reload_history()
        self.render_session()
        self.input.focus_set()

    def select_session(self, _event=None):
        selected = self.history.curselection()
        if selected and not self.operation:
            self.voice.stop_listening()
            self.session_id = self.session_rows[selected[0]]["id"]
            self.render_session()

    def delete_session(self):
        if not self.operation and messagebox.askyesno("Supprimer", "Supprimer définitivement cette conversation de JARVIS ?", parent=self.root):
            self.voice.stop_listening()
            self.store.delete_session(self.session_id)
            rows = self.store.sessions()
            self.session_id = rows[0]["id"] if rows else self.store.new_session()
            self.reload_history()
            self.render_session()

    def change_model(self, _event=None):
        self.settings = replace(self.settings, model=self.model_var.get())
        self.store.save_settings(self.settings)

    def change_cognitive_mode(self, _event=None):
        mode = next((key for key, label in COGNITIVE_LABELS.items() if label == self.cognitive_var.get()), None)
        if self.operation or mode is None:
            self.cognitive_var.set(COGNITIVE_LABELS[self.settings.cognitive_mode])
            return
        settings = replace(self.settings, cognitive_mode=mode).validate()
        self.store.save_settings(settings)
        self.settings = settings
        self.set_status("Politique de conversation : " + COGNITIVE_LABELS[mode])

    def update_continue_button(self):
        self.continue_button.configure(state="normal" if self.continuation_id and not self.operation else "disabled")

    def continue_response(self):
        if self.operation or not self.continuation_id:
            return
        from .cognition import CONTINUE_PROMPT
        self.send(text=CONTINUE_PROMPT, continuation=self.continuation_id)

    def busy(self, operation):
        self.operation = operation
        state = "disabled" if operation else "normal"
        for widget in (self.new_button, self.delete_button, self.settings_button, self.refresh_button, self.send_button, self.history):
            widget.configure(state=state)
        self.model_combo.configure(state="disabled" if operation else "readonly")
        self.cognitive_combo.configure(state="disabled" if operation else "readonly")
        self.update_continue_button()
        speech_active = hasattr(self, "voice") and self.voice.tts_active
        self.stop_button.configure(state="normal" if operation or speech_active else "disabled")
        self.dead_polls = 0

    def refresh_models(self):
        if self.operation:
            return
        self.worker.start("models", self.settings)
        self.busy("models")
        self.set_status("Connexion à Ollama…")

    def send(self, source="text", text=None, continuation=None):
        if self.operation:
            return
        from_input = text is None
        text = (self.input.get("1.0", "end-1c") if from_input else text).strip()
        if not text:
            return
        if self.presence.state == "dormant":
            self.presence.wake()
        self.presence.interpret_text(text)
        if not self.settings.model or self.settings.model not in self.models:
            self.set_status("Choisissez un modèle installé. Cliquez sur Actualiser ; si la liste est vide, utilisez « ollama pull qwen2.5:3b ».", True)
            return
        try:
            from .cognition import build_continuation, continuation_origin, route_request
            records = self.store.messages(self.session_id) if continuation is not None else None
            if continuation is not None:
                if not records or records[-1]["id"] != continuation:
                    raise ValueError("La réponse à poursuivre n’est plus la dernière de cette conversation.")
                prompt = continuation_origin(records, records[-1])["content"]
            else:
                prompt = text
            request_settings, decision = route_request(self.settings, prompt, source, continuation=continuation is not None)
            memories = self.store.memory.search(prompt, approved_only=True) if request_settings.targeted_context else []
            context = (build_continuation(request_settings, records, records[-1], memories=memories)
                       if continuation is not None else ContextBuilder(request_settings).build(
                           self.store.context_records(self.session_id) + [{"role": "user", "content": text}], memories=memories))
        except ValueError as exc:
            self.set_status(str(exc), True)
            return
        metadata = {"final_transcript": text} if source == "voice" else None
        self.message_id = self.store.begin_turn(self.session_id, text, self.settings.model, source=source, metadata=metadata)
        details = {"context": {**context.stats, "sources": context.sources}, "cognition": decision}
        if continuation is not None:
            details["continuation"] = context.stats["continuation"]
        self.store.update_message_metadata(self.message_id, details)
        self.voice.begin_turn(self.message_id, source)
        self.response = ""
        self.response_metrics = {}
        if from_input:
            self.input.delete("1.0", "end")
        self.reload_history()
        self.render_session()
        self.worker.start("chat", request_settings, context.messages)
        self.busy("chat")
        omitted = context.stats["omitted_messages"]
        self.set_status("Génération locale…" + (f" {omitted} anciens messages hors contexte actif, conservés dans l’historique." if omitted else ""))

    def open_memory(self):
        from .memory_ui import MemoryDialog
        current = getattr(self, "memory_dialog", None)
        if current is not None and current.window.winfo_exists():
            current.window.lift()
        else:
            self.memory_dialog = MemoryDialog(self)

    def open_context(self):
        """Inspect the recorded selection and its originals without altering it."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Contexte envoyé à Ollama")
        dialog.configure(bg=PANEL, padx=16, pady=14)
        dialog.transient(self.root)
        dialog.geometry("820x660")
        dialog.minsize(600, 480)
        archive = list(self.store.messages(self.session_id))
        user_inputs = {row["id"]: archive[index - 1] for index, row in enumerate(archive)
                       if index and row["role"] == "assistant" and archive[index - 1]["role"] == "user"}
        rows = [row for row in archive if row["role"] == "assistant"]
        recorded = [(row, json.loads(row["metadata"])) for row in rows]
        recorded = [(row, metadata) for row, metadata in recorded if isinstance(metadata.get("context"), dict)]
        if not recorded:
            tk.Label(dialog, text="Aucun contexte instrumenté dans cette conversation.\nLes conversations déjà archivées restent conservées.",
                     bg=PANEL, fg=MUTED, justify="left").pack(anchor="w", pady=14)
            ttk.Button(dialog, text="Fermer", command=dialog.destroy).pack(anchor="e")
            return
        labels = [f"Réponse #{row['id']} · {row['created']} · {row['content'][:45]}" for row, _ in recorded]
        picker = ttk.Combobox(dialog, name="responses", values=labels, state="readonly")
        picker.pack(fill="x")
        summary = tk.StringVar()
        summary_label = tk.Label(dialog, name="summary", textvariable=summary, bg=PANEL, fg=MUTED,
                 justify="left", anchor="w", wraplength=760, font=(self.font_family, 10))
        summary_label.pack(fill="x", pady=12)
        dialog.bind("<Configure>", lambda event: summary_label.configure(wraplength=max(300, event.width - 32))
                    if event.widget is dialog else None)
        tk.Label(dialog, text="Sources retenues — sélectionnez un passage pour consulter son original", bg=PANEL,
                 fg=TEXT, anchor="w").pack(fill="x")
        source_list = tk.Listbox(dialog, name="sources", height=5, bg=FIELD, fg=TEXT,
            selectbackground="#244055", selectforeground=CYAN, exportselection=False, activestyle="dotbox")
        source_list.pack(fill="x", pady=(6, 10))
        detail_frame = tk.Frame(dialog, name="detail", bg=PANEL)
        detail_frame.pack(fill="both", expand=True)
        details = tk.Text(detail_frame, name="details", bg=FIELD, fg=TEXT, wrap="word", state="disabled",
            font=(self.font_family, 10), padx=10, pady=10, borderwidth=0)
        scrollbar = ttk.Scrollbar(detail_frame, command=details.yview)
        details.configure(yscrollcommand=scrollbar.set)
        details.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        sources = []

        def write_details(text):
            details.configure(state="normal")
            details.delete("1.0", "end")
            details.insert("1.0", text)
            details.configure(state="disabled")

        def show_source(_event=None):
            indices = source_list.curselection()
            if not indices:
                write_details("Aucun message historique sélectionné pour cette demande.")
                return
            source = sources[indices[0]]
            if source.get("method") == "memory":
                memory_id = source.get("memory_id")
                memory = self.store.memory.get(memory_id) if isinstance(memory_id, int) else None
                labels = {"pending": "en attente", "approved": "approuvé", "disabled": "désactivé"}
                state = labels.get(memory["status"], memory["status"]) if memory is not None else "entrée supprimée ou indisponible"
                text = (f"Mémoire #{memory_id} · {source.get('title', '')}\nType : {source.get('kind', '—')}\n"
                        f"État lors de la requête : {labels.get(source.get('status'), source.get('status', '—'))}\nÉtat actuel : {state}\n"
                        f"\nPassage injecté :\n{source.get('excerpt', '')}\n\nProvenance lors de la requête :\n"
                        + json.dumps(source.get("provenance", {}), ensure_ascii=False, indent=2))
                if memory is not None:
                    text += "\n\nContenu actuel de la mémoire :\n" + memory["content"]
                write_details(text)
                return
            mid = source.get("message_id")
            original = self.store.message(mid) if isinstance(mid, int) else None
            if original is not None and (original["session_id"] != source.get("session_id")
                                         or original["created"] != source.get("created")):
                original = None
            category = {"user_input": "Donnée fournie par l’utilisateur", "generated_output": "Contenu généré non vérifié",
                        "continuation_original": "Passage original à continuer",
                        "continuation_extract": "Extrait original non exhaustif à continuer",
                        "extractive": "Extrait historique ciblé", "recent": "Échange historique récent"}.get(source.get("method"), "Source historique")
            heading = (f"{category}\nMessage #{mid if mid is not None else '—'} · {source.get('role', '—')} · "
                       f"{source.get('created', '—')}\nConversation : {source.get('session_id', '—')}\n"
                       f"Sélection : {'extrait ciblé' if source.get('method') == 'extractive' else 'échange récent'}\n")
            if source.get("method") in {"recent", "user_input", "continuation_original", "generated_output"}:
                text = heading + ("\nOriginal archivé :\n" + original["content"]
                                  if original is not None else "\nAperçu conservé (original indisponible) :\n" + source.get("excerpt", ""))
            else:
                text = heading + "\nPassage injecté :\n" + source.get("excerpt", "")
                text += "\n\nOriginal archivé :\n" + (original["content"] if original is not None else "Original indisponible ; le passage injecté reste conservé.")
            write_details(text)

        def show_response(_event=None):
            response_row, metadata = recorded[picker.current()]
            context = metadata["context"]
            metrics = generation_metrics(metadata.get("generation_metrics"))
            duration = metrics.get("prompt_eval_duration")
            prompt_time = f"{duration / 1_000_000:.1f} ms" if duration is not None else "—"
            memory_warnings = context.get("memory_warnings", [])
            warning_text = "\nMémoire : " + " ; ".join(memory_warnings) if memory_warnings else ""
            summary.set(
                cognitive_label(metadata.get("cognition")) + "\n"
                + (str(metadata["cognition"].get("reason", "")) + "\n" if metadata.get("cognition") else "")
                + f"Estimation prudente UTF-8, pas un comptage exact : {context.get('context_estimate_tokens', '—')} tokens.\n"
                f"Contexte total : {context.get('context_limit_tokens', '—')} · Réserve réponse : {context.get('output_reserved_tokens', '—')} · "
                f"Stratégie : {context.get('context_strategy', '—')}\n"
                f"Messages récents : {context.get('recent_messages', '—')} · Rappels ciblés : {context.get('retrieved_messages', '—')} · "
                f"Résumés extractifs : {context.get('summary_messages', '—')} · Souvenirs : {context.get('memory_count', 0)} · Hors contexte : {context.get('omitted_messages', '—')}\n"
                f"Prompt réellement évalué par Ollama : {metrics.get('prompt_eval_count', '—')} tokens · Traitement : {prompt_time}\n"
                "Les références indiquent le contexte préparé pour l'appel ; elles ne prouvent ni sa réception ni l'utilisation ou la vérité de chaque phrase.\n"
                "Réponse, hypothèses et estimations du modèle non vérifiées." + warning_text
                + ("\nContinuation : " + " ".join(metadata["continuation"].get("limitations", []))
                   if isinstance(metadata.get("continuation"), dict) else ""))
            sources[:] = [source for source in context.get("sources", []) if isinstance(source, dict)]
            current_user = user_inputs.get(response_row["id"])
            for row, method in ((current_user, "user_input"), (response_row, "generated_output")):
                if row is not None:
                    sources.append({"message_id": row["id"], "session_id": row["session_id"], "created": row["created"],
                                    "role": row["role"], "method": method, "excerpt": row["content"][:240]})
            source_list.delete(0, "end")
            for source in sources:
                label = {"extractive": "Extrait", "memory": "Mémoire approuvée", "user_input": "Votre demande",
                         "generated_output": "Réponse non vérifiée", "continuation_original": "Continuation",
                         "continuation_extract": "Continuation · extrait"}.get(source.get("method"), "Récent")
                source_id = source.get("memory_id") if source.get("method") == "memory" else source.get("message_id", "—")
                source_list.insert("end", f"{label} · #{source_id} · {source.get('role', '—')} · {source.get('excerpt', '')[:85]}")
            if sources:
                source_list.selection_set(0)
            show_source()

        picker.bind("<<ComboboxSelected>>", show_response)
        source_list.bind("<<ListboxSelect>>", show_source)
        picker.current(len(recorded) - 1)
        show_response()
        ttk.Button(dialog, text="Fermer", command=dialog.destroy).pack(anchor="e", pady=(10, 0))

    def finish(self, status, text, error=False, read_partial=False):
        if self.operation == "chat" and self.message_id is not None:
            if status == "complete" and not self.response.strip():
                status, error = "error", True
                text = "Aucun texte visible reçu. Le modèle a terminé sans réponse ; consultez les statistiques de raisonnement et la limite de génération."
            self.store.update_response(self.message_id, self.response, status)
            self.continuation_id = self.message_id if self.response.strip() else None
            if self.assistant_region is not None:
                self.markdown.update(self.assistant_region, self.response, final=True)
            # Finish playback of the visible fragment, while its archive remains
            # explicitly incomplete. Manual cancellation still stops audio.
            self.voice.finish_turn("complete" if read_partial and self.response.strip() else status)
            self.append("\n", "meta")
            self.append("Texte généré non vérifié · Contexte / provenance dans le menu.\n", "policy")
            self.append(metrics_label(self.response_metrics) + "\n", "metrics")
        self.worker.stop()
        self.busy(None)
        if not self.voice.tts_active:
            self.voice.notify_presence("listening" if self.voice.listening else "silent")
        self.message_id = None
        self.set_status(text, error)

    def cancel(self):
        if self.operation:
            self.finish("cancelled", "Arrêt demandé ; réponse partielle conservée. Ollama peut mettre un instant à libérer le modèle.")
        elif self.voice.tts_active:
            self.voice.cancel_speech()
            self.set_status("Lecture vocale arrêtée ; texte conservé.")

    def poll(self):
        try:
            self.voice.poll()
            if self.operation:
                changed = False
                for event in self.worker.poll():
                    if event.kind == "chunk":
                        self.remember_generation_metrics(event.metadata)
                        self.response += event.payload
                        changed = True
                        if len(self.response) > 1_000_000:
                            self.finish("cancelled", "Limite de taille de réponse atteinte ; génération arrêtée.", True)
                            break
                        self.voice.chunk(event.payload)
                    elif event.kind == "models":
                        self.models = event.payload
                        self.model_combo.configure(values=self.models)
                        if self.models and self.settings.model not in self.models:
                            self.model_var.set(self.models[0])
                            self.change_model()
                        self.finish("complete", f"Ollama connecté · {len(self.models)} modèle(s) installé(s)." if self.models else "Ollama connecté, aucun modèle. Installez-en un avec « ollama pull qwen2.5:3b », puis Actualiser.")
                        break
                    elif event.kind == "done":
                        self.remember_generation_metrics(event.payload)
                        outcome = self.response_metrics.get("outcome")
                        if not self.response.strip() or outcome in {"empty", "empty_length"}:
                            detail = ("Limite de génération atteinte sans texte visible. "
                                      if outcome == "empty_length" else "Aucun texte visible reçu. ")
                            self.finish("error", detail + "Le modèle n’a fourni aucune réponse utilisable ; consultez les statistiques de raisonnement.", True)
                        elif outcome == "length" or self.response_metrics.get("done_reason") == "length":
                            self.append("\nRéponse partielle : limite de génération atteinte.\n", "meta")
                            self.finish("cancelled", "Réponse partielle conservée : limite de génération atteinte. Augmentez le budget du mode choisi si nécessaire.", read_partial=True)
                        else:
                            self.finish("complete", "Réponse terminée · historique enregistré.")
                        break
                    elif event.kind == "notice":
                        self.remember_generation_metrics(event.metadata)
                        self.set_status(str(event.payload))
                    elif event.kind == "error":
                        self.finish("error", str(event.payload), True)
                        break
                if self.operation == "chat" and changed:
                    self.store.update_response(self.message_id, self.response)
                    if self.assistant_region is not None:
                        self.markdown.update(self.assistant_region, self.response, final=False)
                if self.operation and not self.worker.alive():
                    self.dead_polls += 1
                    if self.dead_polls > 5:
                        self.finish("error", "Le processus Ollama s’est arrêté sans résultat. Actualisez ou réessayez ; l’historique est conservé.", True)
        except Exception as exc:
            self.callback_error(type(exc), exc, exc.__traceback__)
        if not self.closed:
            self.poll_id = self.root.after(40, self.poll)

    def open_settings(self):
        if self.operation:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Paramètres locaux")
        dialog.configure(bg=PANEL, padx=20, pady=14)
        dialog.transient(self.root)
        dialog.grab_set()
        variables = {}
        fields = [("endpoint", "Adresse Ollama locale"), ("temperature", "Température (0–2)"),
                  ("context", "Contexte total (tokens)"), ("max_tokens", "Budget discussion (tokens)"),
                  ("voice_tokens", "Budget réponse vocale (tokens)"),
                  ("mission_tokens", "Budget mission complexe (tokens)")]
        for i, (key, label) in enumerate(fields):
            tk.Label(dialog, text=label, bg=PANEL, fg=TEXT).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 16))
            variables[key] = tk.StringVar(value=str(getattr(self.settings, key)))
            ttk.Entry(dialog, textvariable=variables[key], width=34).grid(row=i, column=1, sticky="ew")
        choices = {
            "reasoning_mode": {"Rapide": "fast", "Automatique": "auto", "Approfondi": "deep"},
            "usage": {"Discussion": "chat", "Réponse vocale": "voice", "Mission complexe": "mission"},
        }
        for row, (key, label) in enumerate((("reasoning_mode", "Raisonnement"), ("usage", "Utilisation")), start=len(fields)):
            values = choices[key]
            variables[key] = tk.StringVar(value=next(name for name, value in values.items() if value == getattr(self.settings, key)))
            tk.Label(dialog, text=label, bg=PANEL, fg=TEXT).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 16))
            ttk.Combobox(dialog, textvariable=variables[key], values=list(values), state="readonly", width=32).grid(row=row, column=1, sticky="ew")
        context_row = len(fields) + len(choices)
        variables["targeted_context"] = tk.BooleanVar(value=self.settings.targeted_context)
        ttk.Checkbutton(dialog, name="targeted_context", text="Contexte ciblé et rappel lexical des anciens échanges",
            variable=variables["targeted_context"]).grid(row=context_row, column=0, columnspan=2, sticky="w", pady=3)
        variables["retrieval_budget"] = tk.StringVar(value=str(self.settings.retrieval_budget))
        tk.Label(dialog, text="Budget des rappels ciblés (tokens estimés)", bg=PANEL, fg=TEXT).grid(
            row=context_row + 1, column=0, sticky="w", pady=3, padx=(0, 16))
        ttk.Entry(dialog, name="retrieval_budget", textvariable=variables["retrieval_budget"], width=34).grid(
            row=context_row + 1, column=1, sticky="ew")
        prompt_row = context_row + 2
        tk.Label(dialog, text="Instruction système (facultative)", bg=PANEL, fg=TEXT).grid(row=prompt_row, column=0, columnspan=2, sticky="w", pady=(6, 4))
        prompt = tk.Text(dialog, height=4, width=58, bg=FIELD, fg=TEXT, insertbackground=CYAN, wrap="word", font=(self.font_family, 10))
        prompt.grid(row=prompt_row + 1, column=0, columnspan=2, sticky="ew")
        prompt.insert("1.0", self.settings.system_prompt)
        tk.Label(dialog, text="Historique et paramètres : " + str(self.store.db.execute("PRAGMA database_list").fetchone()[2]) +
                 "\nStockage local non chiffré ; aucun accès système accordé au modèle."
                 "\nRapide : think:false · Approfondi : think:true · Automatique : choix du modèle."
                 "\nMicrophone : budget vocal. Budgets effectifs plafonnés à la moitié du contexte."
                 "\nTTFT : envoi HTTP → texte visible. Les tokens de génération peuvent inclure la pensée interne.",
                 bg=PANEL, fg=MUTED, wraplength=620, justify="left", font=(self.font_family, 9)).grid(row=prompt_row + 2, column=0, columnspan=2, pady=12, sticky="w")

        def save():
            try:
                settings = replace(self.settings, endpoint=variables["endpoint"].get().strip().rstrip("/"),
                    temperature=float(variables["temperature"].get()), context=int(variables["context"].get()),
                    max_tokens=int(variables["max_tokens"].get()), voice_tokens=int(variables["voice_tokens"].get()),
                    mission_tokens=int(variables["mission_tokens"].get()),
                    reasoning_mode=choices["reasoning_mode"][variables["reasoning_mode"].get()],
                    usage=choices["usage"][variables["usage"].get()],
                    targeted_context=variables["targeted_context"].get(),
                    retrieval_budget=int(variables["retrieval_budget"].get()),
                    system_prompt=prompt.get("1.0", "end-1c")).validate()
                if settings.reasoning_mode != self.settings.reasoning_mode:
                    settings = replace(settings, cognitive_mode="manual")
                self.store.save_settings(settings)
                if settings.system_prompt != self.settings.system_prompt:
                    voice_settings = replace(self.voice.settings, personality="Personnalisé")
                    self.store.set_preference("voice", voice_settings.to_dict())
                    self.voice.settings = voice_settings
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror("Paramètres invalides", str(exc), parent=dialog)
                return
            self.settings = settings
            self.cognitive_var.set(COGNITIVE_LABELS[settings.cognitive_mode])
            dialog.destroy()
            self.refresh_models()

        ttk.Button(dialog, text="Enregistrer", command=save).grid(row=prompt_row + 3, column=1, sticky="e")
        ttk.Button(dialog, text="Annuler", command=dialog.destroy).grid(row=prompt_row + 3, column=0, sticky="w")

    def callback_error(self, _kind, exc, _trace):
        self.voice.halt_without_persistence()
        self.worker.stop()
        self.continuation_id = None
        self.busy(None)
        self.set_status("Erreur de stockage local : vérifiez l’espace libre et les droits du dossier de données. Redémarrez JARVIS." if isinstance(exc, (sqlite3.Error, OSError)) else "Erreur interne de l’interface. Redémarrez JARVIS ; les données déjà enregistrées sont conservées.", True)

    def close(self):
        try:
            self.voice.stop_listening()
            self.presence.close()
            if self.operation:
                self.cancel()
        finally:
            self.closed = True
            self.worker.stop()
            self.root.after_cancel(self.poll_id)
            self.markdown.close()
            self.store.close()
            self.navigation_font = None
            self.input_font = None
            self.root.destroy()
