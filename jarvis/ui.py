"""COMMAND OS: Tk main thread owns widgets/storage; inference is isolated."""
import json
import sqlite3
import tkinter as tk
from dataclasses import replace
from tkinter import font, messagebox, ttk

from .config import Settings, active_context
from .metrics import generation_metrics, metrics_label
from .worker import Worker

BG, PANEL, FIELD = "#0b1019", "#121c29", "#192638"
TEXT, MUTED, CYAN, RED = "#e4edf6", "#a6b8cb", "#65e0ef", "#ff9c9c"


class App:
    def __init__(self, root, store, refresh=True):
        self.root, self.store = root, store
        self.worker = Worker()
        self.operation = None
        self.message_id = None
        self.response = ""
        self.response_metrics = {}
        self.models = []
        self.dead_polls = 0
        self.closed = False
        self.settings = store.settings()
        families = {family.casefold(): family for family in font.families(root)}
        self.font_family = next((families[name] for name in ("segoe ui", "dejavu sans", "helvetica") if name in families), "TkDefaultFont")
        root.title("JARVIS UNHINGED NEXT · 0.0.1")
        root.geometry("1100x760")
        root.minsize(900, 600)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self.callback_error
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=PANEL, foreground=TEXT, font=(self.font_family, 11))
        style.configure("TButton", padding=(12, 8), background=FIELD, foreground=TEXT)
        style.map("TButton", background=[("active", "#244055")], foreground=[("disabled", "#7b8999")])
        style.configure("TCombobox", fieldbackground=FIELD, foreground=TEXT, arrowcolor=CYAN)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], selectbackground=[("readonly", FIELD)])
        style.configure("Vertical.TScrollbar", background=FIELD, troughcolor=BG, arrowcolor=CYAN, bordercolor=BG)
        style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT)
        root.option_add("*TCombobox*Listbox.background", FIELD)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)

        sidebar = tk.Frame(root, bg=PANEL, padx=14, pady=18)
        sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
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
            highlightbackground=FIELD, font=(self.font_family, 10), width=26, activestyle="dotbox", exportselection=False)
        history_scroll = ttk.Scrollbar(history_frame, command=self.history.yview)
        self.history.configure(yscrollcommand=history_scroll.set)
        self.history.pack(side="left", fill="both", expand=True)
        history_scroll.pack(side="right", fill="y")
        self.history.bind("<<ListboxSelect>>", self.select_session)
        self.delete_button = ttk.Button(sidebar, text="Supprimer la conversation", command=self.delete_session)
        self.delete_button.pack(fill="x", pady=(10, 6))
        self.settings_button = ttk.Button(sidebar, text="Paramètres", command=self.open_settings)
        self.settings_button.pack(fill="x")
        from .voice_ui import VoiceControls
        self.voice = VoiceControls(self, sidebar)
        from .presence import PresenceView
        self.presence = PresenceView(self)
        ttk.Button(sidebar, text="PRESENCE", command=self.presence.show).pack(fill="x", pady=4)
        tk.Label(sidebar, text="Outils système : désactivés",
                 justify="left", bg=PANEL, fg=MUTED, font=(self.font_family, 9)).pack(anchor="w", pady=(16, 0))

        top = tk.Frame(root, bg=BG, padx=20, pady=15)
        top.grid(row=0, column=1, sticky="ew")
        tk.Label(top, text="MODÈLE LOCAL", bg=BG, fg=MUTED, font=(self.font_family, 9)).pack(anchor="w")
        model_row = tk.Frame(top, bg=BG)
        model_row.pack(fill="x", pady=(6, 0))
        self.model_var = tk.StringVar(value=self.settings.model)
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_var, state="readonly")
        self.model_combo.pack(side="left", fill="x", expand=True)
        self.model_combo.bind("<<ComboboxSelected>>", self.change_model)
        self.refresh_button = ttk.Button(model_row, text="Actualiser", command=self.refresh_models)
        self.refresh_button.pack(side="left", padx=(10, 0))
        self.status = tk.StringVar(value="Prêt. Sélectionnez un modèle Ollama local.")
        self.status_label = tk.Label(top, textvariable=self.status, bg=BG, fg=CYAN,
            justify="left", anchor="w", wraplength=650, font=(self.font_family, 10))
        self.status_label.pack(fill="x", pady=(12, 0))
        top.bind("<Configure>", lambda e: self.status_label.configure(wraplength=max(200, e.width - 40)))

        chat_frame = tk.Frame(root, bg=BG, padx=20)
        chat_frame.grid(row=1, column=1, sticky="nsew")
        self.chat = tk.Text(chat_frame, bg=BG, fg=TEXT, wrap="word", state="disabled",
            font=(self.font_family, 12), padx=14, pady=14, borderwidth=0,
            highlightthickness=1, highlightbackground=FIELD, highlightcolor=CYAN,
            selectbackground="#244055", insertbackground=CYAN)
        scroll = ttk.Scrollbar(chat_frame, command=self.chat.yview)
        self.chat.configure(yscrollcommand=scroll.set)
        self.chat.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.chat.tag_configure("speaker", foreground=CYAN, font=(self.font_family, 10, "bold"), spacing1=18, spacing3=8)
        self.chat.tag_configure("meta", foreground=MUTED, font=(self.font_family, 9), spacing3=10)
        self.metrics_visible = tk.BooleanVar(value=store.get_preference("show_generation_metrics", True) is not False)
        self.chat.tag_configure("metrics", foreground=MUTED, font=(self.font_family, 9),
                                spacing3=10, elide=not self.metrics_visible.get())
        compose = tk.Frame(root, bg=BG, padx=20, pady=14)
        compose.grid(row=2, column=1, sticky="ew")
        self.input = tk.Text(compose, height=4, bg=FIELD, fg=TEXT, insertbackground=CYAN,
            wrap="word", font=(self.font_family, 11), padx=10, pady=8, borderwidth=0,
            highlightthickness=1, highlightcolor=CYAN, highlightbackground=FIELD)
        self.input.pack(fill="x")
        self.input.bind("<Control-Return>", lambda e: self.send() or "break")
        actions = tk.Frame(compose, bg=BG)
        actions.pack(fill="x", pady=(10, 0))
        tk.Label(actions, text="Ctrl + Entrée : envoyer · Entrée : nouvelle ligne",
                 bg=BG, fg=MUTED, font=(self.font_family, 9)).pack(side="left")
        style.configure("Metrics.TCheckbutton", background=BG, foreground=MUTED,
                        font=(self.font_family, 9))
        self.metrics_toggle = ttk.Checkbutton(model_row, text="Métriques", variable=self.metrics_visible,
            command=self.toggle_metrics, style="Metrics.TCheckbutton")
        self.metrics_toggle.pack(side="right", padx=(10, 0))
        self.send_button = ttk.Button(actions, text="Envoyer", command=self.send)
        self.send_button.pack(side="right")
        self.stop_button = ttk.Button(actions, text="Arrêter", command=self.cancel, state="disabled")
        self.stop_button.pack(side="right", padx=8)
        root.rowconfigure(1, weight=1)
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
        self.poll_id = root.after(40, self.poll)
        if refresh:
            self.refresh_models()

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
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        rows = self.store.messages(self.session_id)
        if not rows:
            self.append("JARVIS / CONVERSATION LOCALE\n", "speaker")
            self.append("Choisissez un modèle, puis écrivez votre message.\n"
                        "Les réponses du modèle ne peuvent déclencher aucune action système.\n", "meta")
        for row in rows:
            self.append(("VOUS" if row["role"] == "user" else "JARVIS · " + row["model"]) + "\n", "speaker")
            self.append(row["content"] + ("" if row["status"] == "streaming" else "\n"))
            if row["status"] not in {"complete", "streaming"}:
                self.append({"streaming": "En cours", "cancelled": "Arrêtée", "error": "Échec",
                             "interrupted": "Interrompue à la fermeture"}[row["status"]] + "\n", "meta")
            if row["role"] == "assistant" and row["status"] != "streaming":
                metadata = json.loads(row["metadata"])
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

    def busy(self, operation):
        self.operation = operation
        state = "disabled" if operation else "normal"
        for widget in (self.new_button, self.delete_button, self.settings_button, self.refresh_button, self.send_button, self.history):
            widget.configure(state=state)
        self.model_combo.configure(state="disabled" if operation else "readonly")
        speech_active = hasattr(self, "voice") and self.voice.tts_active
        self.stop_button.configure(state="normal" if operation or speech_active else "disabled")
        self.dead_polls = 0

    def refresh_models(self):
        if self.operation:
            return
        self.worker.start("models", self.settings)
        self.busy("models")
        self.set_status("Connexion à Ollama…")

    def send(self, source="text", text=None):
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
            request_settings = self.settings.for_request(source)
            messages, omitted = active_context(self.store.context(self.session_id) + [{"role": "user", "content": text}], request_settings)
        except ValueError as exc:
            self.set_status(str(exc), True)
            return
        metadata = {"final_transcript": text} if source == "voice" else None
        self.message_id = self.store.begin_turn(self.session_id, text, self.settings.model, source=source, metadata=metadata)
        self.voice.begin_turn(self.message_id, source)
        self.response = ""
        self.response_metrics = {}
        if from_input:
            self.input.delete("1.0", "end")
        self.reload_history()
        self.render_session()
        self.worker.start("chat", request_settings, messages)
        self.busy("chat")
        self.set_status("Génération locale…" + (f" {omitted} anciens messages hors contexte actif, conservés dans l’historique." if omitted else ""))

    def finish(self, status, text, error=False, read_partial=False):
        if self.operation == "chat" and self.message_id is not None:
            if status == "complete" and not self.response.strip():
                status, error = "error", True
                text = "Aucun texte visible reçu. Le modèle a terminé sans réponse ; consultez les statistiques de raisonnement et la limite de génération."
            self.store.update_response(self.message_id, self.response, status)
            # Finish playback of the visible fragment, while its archive remains
            # explicitly incomplete. Manual cancellation still stops audio.
            self.voice.finish_turn("complete" if read_partial and self.response.strip() else status)
            self.append("\n", "meta")
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
                        self.append(event.payload)
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
        dialog.configure(bg=PANEL, padx=20, pady=20)
        dialog.transient(self.root)
        dialog.grab_set()
        variables = {}
        fields = [("endpoint", "Adresse Ollama locale"), ("temperature", "Température (0–2)"),
                  ("context", "Contexte total (tokens)"), ("max_tokens", "Budget discussion (tokens)"),
                  ("voice_tokens", "Budget réponse vocale (tokens)"),
                  ("mission_tokens", "Budget mission complexe (tokens)")]
        for i, (key, label) in enumerate(fields):
            tk.Label(dialog, text=label, bg=PANEL, fg=TEXT).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 16))
            variables[key] = tk.StringVar(value=str(getattr(self.settings, key)))
            ttk.Entry(dialog, textvariable=variables[key], width=34).grid(row=i, column=1, sticky="ew")
        choices = {
            "reasoning_mode": {"Rapide": "fast", "Automatique": "auto", "Approfondi": "deep"},
            "usage": {"Discussion": "chat", "Réponse vocale": "voice", "Mission complexe": "mission"},
        }
        for row, (key, label) in enumerate((("reasoning_mode", "Raisonnement"), ("usage", "Utilisation")), start=len(fields)):
            values = choices[key]
            variables[key] = tk.StringVar(value=next(name for name, value in values.items() if value == getattr(self.settings, key)))
            tk.Label(dialog, text=label, bg=PANEL, fg=TEXT).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 16))
            ttk.Combobox(dialog, textvariable=variables[key], values=list(values), state="readonly", width=32).grid(row=row, column=1, sticky="ew")
        prompt_row = len(fields) + len(choices)
        tk.Label(dialog, text="Instruction système (facultative)", bg=PANEL, fg=TEXT).grid(row=prompt_row, column=0, columnspan=2, sticky="w", pady=(10, 6))
        prompt = tk.Text(dialog, height=4, width=58, bg=FIELD, fg=TEXT, insertbackground=CYAN, wrap="word", font=(self.font_family, 10))
        prompt.grid(row=prompt_row + 1, column=0, columnspan=2, sticky="ew")
        prompt.insert("1.0", self.settings.system_prompt)
        tk.Label(dialog, text="Historique et paramètres : " + str(self.store.db.execute("PRAGMA database_list").fetchone()[2]) +
                 "\nStockage local non chiffré. Aucun accès système accordé au modèle."
                 "\nRapide demande think:false ; Approfondi demande think:true. Automatique laisse le choix au modèle. Un paramètre refusé produit un avertissement."
                 "\nLe budget vocal s’applique aux demandes du microphone. Chaque budget effectif est plafonné à la moitié du contexte."
                 "\nTTFT reçu : envoi HTTP → premier texte visible, chargement et réseau inclus. Les tokens de génération peuvent inclure la pensée interne.",
                 bg=PANEL, fg=MUTED, wraplength=620, justify="left", font=(self.font_family, 9)).grid(row=prompt_row + 2, column=0, columnspan=2, pady=12, sticky="w")

        def save():
            try:
                settings = replace(self.settings, endpoint=variables["endpoint"].get().strip().rstrip("/"),
                    temperature=float(variables["temperature"].get()), context=int(variables["context"].get()),
                    max_tokens=int(variables["max_tokens"].get()), voice_tokens=int(variables["voice_tokens"].get()),
                    mission_tokens=int(variables["mission_tokens"].get()),
                    reasoning_mode=choices["reasoning_mode"][variables["reasoning_mode"].get()],
                    usage=choices["usage"][variables["usage"].get()],
                    system_prompt=prompt.get("1.0", "end-1c")).validate()
                self.store.save_settings(settings)
                if settings.system_prompt != self.settings.system_prompt:
                    voice_settings = replace(self.voice.settings, personality="Personnalisé")
                    self.store.set_preference("voice", voice_settings.to_dict())
                    self.voice.settings = voice_settings
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror("Paramètres invalides", str(exc), parent=dialog)
                return
            self.settings = settings
            dialog.destroy()
            self.refresh_models()

        ttk.Button(dialog, text="Enregistrer", command=save).grid(row=prompt_row + 3, column=1, sticky="e")
        ttk.Button(dialog, text="Annuler", command=dialog.destroy).grid(row=prompt_row + 3, column=0, sticky="w")

    def callback_error(self, _kind, exc, _trace):
        self.voice.halt_without_persistence()
        self.worker.stop()
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
            self.store.close()
            self.root.destroy()
