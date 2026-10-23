"""Explicit, local memory curation. Nothing is approved from chat automatically."""
import hashlib
import json
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


KINDS = {"Souvenir durable": "durable", "Résumé": "summary",
         "Projet / mission": "project", "Document": "document"}
STATUSES = {"pending": "en attente", "approved": "approuvé", "disabled": "désactivé"}
IMPORT_LIMIT = 256 * 1024


class MemoryDialog:
    def __init__(self, app):
        from .ui import PANEL, FIELD, TEXT, MUTED, CYAN
        self.app, self.repo = app, app.store.memory
        self.selected_id = None
        self.provenance = {}
        self.rows, self.message_rows = [], []
        self.context_records, self.context_warnings = [], []
        self.window = tk.Toplevel(app.root)
        self.window.title("Mémoire locale")
        self.window.configure(bg=PANEL, padx=14, pady=12)
        self.window.transient(app.root)
        self.window.geometry(f"1000x{min(720, max(540, app.root.winfo_screenheight() - 100))}")
        self.window.minsize(820, 540)
        self.window.columnconfigure(1, weight=1)
        self.window.rowconfigure(2, weight=1)
        tk.Label(self.window, text="Souvenirs explicites : enregistrer puis approuver. Historique et contexte de requête restent distincts.",
                 bg=PANEL, fg=MUTED, anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        search = tk.Frame(self.window, bg=PANEL)
        search.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.query = tk.StringVar()
        entry = ttk.Entry(search, textvariable=self.query)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self.search())
        ttk.Button(search, text="Rechercher", command=self.search).pack(side="left", padx=6)
        ttk.Button(search, text="Tout afficher", command=self.refresh).pack(side="left")
        self.index_label = tk.Label(search, text="FTS5 lexical" if self.repo.fts_available else "Recherche locale de secours",
                                    bg=PANEL, fg=MUTED, font=(app.font_family, 9))
        self.index_label.pack(side="left", padx=8)
        tabs = ttk.Notebook(self.window)
        tabs.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        memories = tk.Frame(tabs, bg=PANEL)
        messages = tk.Frame(tabs, bg=PANEL)
        contexts = tk.Frame(tabs, bg=PANEL)
        tabs.add(memories, text="Souvenirs")
        tabs.add(messages, text="Historique")
        tabs.add(contexts, text="Contexte")
        self.memory_list = tk.Listbox(memories, width=32, bg=FIELD, fg=TEXT,
            selectbackground="#244055", selectforeground=CYAN, exportselection=False)
        self.memory_list.pack(fill="both", expand=True)
        self.memory_list.bind("<<ListboxSelect>>", self.select_memory)
        self.message_list = tk.Listbox(messages, width=32, bg=FIELD, fg=TEXT,
            selectbackground="#244055", selectforeground=CYAN, exportselection=False)
        self.message_list.pack(fill="both", expand=True)
        self.message_list.bind("<<ListboxSelect>>", self.select_message)
        self.context_info = tk.Text(contexts, bg=FIELD, fg=TEXT, wrap="word", width=32,
                                    state="disabled", font=(app.font_family, 10))
        self.context_info.pack(fill="both", expand=True)
        ttk.Button(contexts, text="Actualiser la trace", command=self.refresh_context).pack(fill="x", pady=3)
        ttk.Button(contexts, text="Inspecter le contexte envoyé", command=app.open_context).pack(fill="x", pady=3)
        editor = tk.Frame(self.window, bg=PANEL)
        editor.grid(row=2, column=1, sticky="nsew")
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(3, weight=1)
        self.kind = tk.StringVar(value="Souvenir durable")
        self.title, self.topic = tk.StringVar(), tk.StringVar()
        for row, (label, variable) in enumerate((("Type", self.kind), ("Titre", self.title), ("Sujet / clé de conflit", self.topic))):
            tk.Label(editor, text=label, bg=PANEL, fg=TEXT).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            widget = (ttk.Combobox(editor, textvariable=variable, values=list(KINDS), state="readonly")
                      if row == 0 else ttk.Entry(editor, textvariable=variable))
            if row == 0:
                self.kind_combo = widget
            widget.grid(row=row, column=1, sticky="ew", pady=3)
        self.content = tk.Text(editor, bg=FIELD, fg=TEXT, insertbackground=CYAN, wrap="word",
            font=(app.font_family, 10), height=9, width=42, padx=8, pady=8)
        self.content.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(8, 6))
        self.info = tk.Text(editor, bg=PANEL, fg=MUTED, wrap="word", height=6, state="disabled",
                            font=(app.font_family, 9), borderwidth=0)
        self.info.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.status = tk.StringVar()
        tk.Label(self.window, textvariable=self.status, bg=PANEL, fg=CYAN, justify="left", anchor="w",
            wraplength=940, font=(app.font_family, 10)).grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)
        actions = tk.Frame(self.window, bg=PANEL)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew")
        for column, (text, command) in enumerate((("Nouveau", self.new), ("Enregistrer", self.save),
                ("Approuver", self.approve), ("Désactiver", self.disable), ("Supprimer", self.delete))):
            ttk.Button(actions, text=text, command=command).grid(row=0, column=column, padx=(0, 6), pady=3)
        for column, (text, command) in enumerate((("Importer TXT / MD", self.import_file),
                ("Préparer un résumé", self.prepare_summary), ("Voir les origines", self.inspect_origins),
                ("Fermer", self.window.destroy))):
            ttk.Button(actions, text=text, command=command).grid(row=1, column=column, padx=(0, 6), pady=3)
        self.new()
        self.refresh()

    def report_error(self, exc):
        detail = str(exc) if isinstance(exc, ValueError) else "Lecture ou sauvegarde locale impossible. Vérifiez les droits du dossier et l’espace libre."
        self.status.set("ERREUR · " + detail)

    def display_info(self, text):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", text)
        self.info.configure(state="disabled")

    def fill(self, content):
        self.content.configure(state="normal")
        self.content.delete("1.0", "end")
        self.content.insert("1.0", content)

    def new(self):
        self.selected_id = None
        self.memory_list.selection_clear(0, "end")
        self.message_list.selection_clear(0, "end")
        self.kind.set("Souvenir durable")
        self.kind_combo.configure(state="readonly")
        self.title.set("")
        self.topic.set("")
        self.provenance = {"source": "manual", "session_id": self.app.session_id}
        self.fill("")
        self.display_info("Nouvelle entrée manuelle. Indiquez un sujet pour repérer les contradictions avec une mémoire approuvée.")
        self.status.set("Aucune mémorisation sans votre action Enregistrer, puis Approuver.")

    def refresh(self, selected=None):
        try:
            if selected is None:
                self.new()
            self.rows = list(self.repo.list())
            self.message_rows = []
            self.message_list.delete(0, "end")
            self.refresh_context()
            self.render_list(selected)
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def render_list(self, selected=None):
        self.memory_list.delete(0, "end")
        for index, row in enumerate(self.rows):
            self.memory_list.insert("end", f"#{row['id']} · {STATUSES.get(row['status'], row['status'])} · {row['title'] or row['content'][:50]}")
            if row["id"] == selected:
                self.memory_list.selection_set(index)
                self.memory_list.see(index)
        if selected is not None:
            self.select_memory()

    def select_memory(self, _event=None):
        indices = self.memory_list.curselection()
        if not indices:
            return
        row = self.rows[indices[0]]
        self.selected_id = row["id"]
        self.kind.set(next(label for label, kind in KINDS.items() if kind == row["kind"]))
        self.kind_combo.configure(state="disabled")
        self.title.set(row["title"])
        self.topic.set(row["topic"])
        self.provenance = json.loads(row["provenance"])
        self.fill(row["content"])
        self.display_info(self.memory_info(row))

    def memory_info(self, row):
        return (f"Souvenir explicite #{row['id']} · {STATUSES.get(row['status'], row['status'])}\n"
                f"Création : {row['created']}\nMise à jour : {row['updated']}\n"
                + self.inclusion_summary(row["id"]) + "\nProvenance : "
                + json.dumps(json.loads(row["provenance"]), ensure_ascii=False, indent=2))

    def select_message(self, _event=None):
        indices = self.message_list.curselection()
        if not indices:
            return
        row = self.message_rows[indices[0]]
        self.selected_id = None
        self.memory_list.selection_clear(0, "end")
        self.kind_combo.configure(state="disabled")
        self.fill(row["content"])
        self.content.configure(state="disabled")
        self.provenance = {"source": "conversation_search", "message_ids": [row["id"]],
            "sources": [{"message_id": row["id"], "session_id": row["session_id"], "created": row["created"]}]}
        self.display_info(f"Consultation seule · Message #{row['id']} · {row['role']} · {row['created']}\nConversation : {row['session_id']}")
        self.status.set("Original archivé en lecture seule. Nouveau permet de rédiger une mémoire distincte.")

    def refresh_context(self):
        """Inspect recorded prompt selection, never infer a model's hidden use.

        Scan at most 100 response metadata records in the active conversation;
        no model call, new memory, migration or additional persistent cache.
        """
        try:
            records = self.app.store.db.execute(
                "SELECT id,created,metadata FROM messages WHERE session_id=? AND role='assistant' ORDER BY id DESC LIMIT 100",
                (self.app.session_id,)).fetchall()
            self.context_records, self.context_warnings = [], []
            for row in records:
                try:
                    metadata = json.loads(row["metadata"])
                    if not isinstance(metadata, dict):
                        raise ValueError("métadonnées non structurées")
                    context = metadata.get("context")
                    if context is None:
                        continue
                    if not isinstance(context, dict) or not isinstance(context.get("sources", []), list):
                        raise ValueError("trace de contexte non structurée")
                    if any(not isinstance(source, dict) for source in context.get("sources", [])):
                        raise ValueError("source de contexte non structurée")
                except ValueError:
                    self.context_warnings.append(f"Réponse #{row['id']} : trace illisible, non interprétée.")
                    continue
                self.context_records.append({"id": row["id"], "created": row["created"], "context": context})
            text = ("Sélection temporaire de requête\n\n"
                    "Trace conservée dans l’historique, distincte des souvenirs durables. "
                    "L’inclusion dans le contexte ne prouve pas que le modèle s’en est servi, ni que l’information est vraie.\n\n")
            if self.context_records:
                latest = self.context_records[0]
                sources = latest["context"].get("sources", [])
                memories = [source for source in sources if source.get("method") == "memory"]
                history = [source for source in sources if source.get("method") != "memory"]
                text += (f"Dernière trace : réponse #{latest['id']} · {latest['created']}\n"
                         f"Souvenirs explicitement rappelés : {len(memories)}\n"
                         f"Références historiques : {len(history)}\n\n")
                for source in sources[:32]:
                    if source.get("method") == "memory":
                        text += (f"Souvenir #{source.get('memory_id', '—')} · état enregistré : "
                                 f"{STATUSES.get(source.get('status'), source.get('status', 'non précisé'))}\n")
                    else:
                        origin = {"user": "message utilisateur", "assistant": "réponse générée, non vérifiée"}.get(
                            source.get("role"), "origine non précisée")
                        text += f"Archive #{source.get('message_id', '—')} · {origin}\n"
                if len(sources) > 32:
                    text += "Aperçu limité à 32 références ; ouvrir l’inspection pour le détail.\n"
                text += "\nOuvrir Contexte envoyé pour consulter les extraits et leurs originaux."
            else:
                text += "Aucun contexte instrumenté dans les 100 dernières réponses de cette conversation."
            text += "\n\nContrôle limité aux 100 dernières réponses de la conversation active."
            if self.context_warnings:
                text += "\n\n" + "\n".join(self.context_warnings)
            self.context_info.configure(state="normal")
            self.context_info.delete("1.0", "end")
            self.context_info.insert("1.0", text)
            self.context_info.configure(state="disabled")
            if self.selected_id is not None:
                selected = next((row for row in self.rows if row["id"] == self.selected_id), None)
                if selected is not None:
                    self.display_info(self.memory_info(selected))  # Preserve unsaved editor text.
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def inclusion_summary(self, mid):
        included = [row["id"] for row in self.context_records if any(
            source.get("method") == "memory" and type(source.get("memory_id")) is int
            and source["memory_id"] == mid for source in row["context"].get("sources", []))]
        if not included:
            return "Aucune inclusion enregistrée parmi les 100 dernières réponses de cette conversation."
        ids = ", ".join(f"#{rid}" for rid in included[:3]) + ("…" if len(included) > 3 else "")
        return (f"Inclus dans {len(included)} contexte(s) enregistré(s) : {ids}. "
                "Inspecter l’extrait envoyé ; ces traces ne valident pas la version actuelle du souvenir.")

    def save(self):
        if str(self.content.cget("state")) == "disabled":
            self.status.set("Original de conversation en lecture seule. Utilisez Nouveau pour une entrée distincte.")
            return
        try:
            content = self.content.get("1.0", "end-1c")
            if self.selected_id is None:
                mid = self.repo.create(content, kind=KINDS[self.kind.get()], title=self.title.get(),
                                       topic=self.topic.get(), provenance=self.provenance)
                notice = "Entrée enregistrée en attente. Inspectez son contenu et sa provenance avant de l’approuver."
            else:
                if not messagebox.askyesno("Corriger la mémoire", "Créer une sauvegarde SQLite et remplacer cette entrée ?\nLa version corrigée reviendra en attente d’approbation.", parent=self.window):
                    return
                mid = self.selected_id
                backup = self.repo.update(mid, content, title=self.title.get(), topic=self.topic.get(), provenance=self.provenance)
                notice = f"Correction en attente d’approbation. Sauvegarde : {backup}"
            self.refresh(mid)
            self.status.set(notice)
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def approve(self):
        if self.selected_id is None:
            self.status.set("Sélectionnez une mémoire en attente à approuver.")
            return
        try:
            row = self.repo.get(self.selected_id)
            if row is None or row["status"] != "pending":
                self.status.set("Seule une entrée en attente peut être approuvée. Une correction revient en attente.")
                return
            if (self.content.get("1.0", "end-1c") != row["content"] or self.title.get() != row["title"]
                    or self.topic.get() != row["topic"]):
                self.status.set("Modifications non enregistrées : cliquez sur Enregistrer avant d’approuver.")
                return
            if not messagebox.askyesno("Approuver la mémoire", f"Confirmez-vous ce contenu comme référence utilisable par JARVIS ?\n{row['title'] or row['content'][:140]}\nSujet : {row['topic'] or 'non précisé'}", parent=self.window):
                return
            self.repo.approve(self.selected_id, confirmed=True)
            self.refresh(self.selected_id)
            self.status.set("Mémoire approuvée. Elle sera proposée uniquement aux recherches pertinentes.")
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def disable(self):
        if self.selected_id is None:
            self.status.set("Sélectionnez la mémoire à désactiver.")
            return
        try:
            self.repo.disable(self.selected_id)
            self.refresh(self.selected_id)
            self.status.set("Mémoire désactivée, conservée et exclue du rappel. Une correction permet de la soumettre à nouveau.")
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def delete(self):
        if self.selected_id is None:
            self.status.set("Sélectionnez la mémoire à supprimer.")
            return
        try:
            row = self.repo.get(self.selected_id)
            if row is None:
                raise ValueError("Cette mémoire n’existe plus. Actualisez la liste.")
            if not messagebox.askyesno("Supprimer la mémoire", f"Créer une sauvegarde SQLite puis supprimer uniquement la mémoire #{row['id']} ?\n{row['title'] or row['content'][:140]}\nSujet : {row['topic'] or 'non précisé'}\nLes conversations et les autres entrées seront conservées.", parent=self.window):
                return
            backup = self.repo.delete(self.selected_id, confirmed=True)
            self.new()
            self.refresh()
            self.status.set(f"Mémoire supprimée. Sauvegarde : {backup}")
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def search(self):
        try:
            self.new()
            self.rows = list(self.repo.search(self.query.get(), limit=100, approved_only=False))
            self.message_rows = list(self.repo.search_messages(self.query.get(), limit=100))
            self.render_list()
            self.message_list.delete(0, "end")
            for row in self.message_rows:
                self.message_list.insert("end", f"#{row['id']} · {row['role']} · {row['content'][:65]}")
            self.status.set(f"Recherche lexicale locale : {len(self.rows)} mémoire(s), {len(self.message_rows)} message(s). Aucune recherche sémantique ni requête LLM.")
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def import_file(self):
        name = filedialog.askopenfilename(parent=self.window, title="Importer un document local (256 Kio maximum)",
            filetypes=[("Texte UTF-8", "*.txt *.md")])
        if not name:
            return
        try:
            path = Path(name)
            if path.suffix.casefold() not in {".txt", ".md"}:
                raise ValueError("Choisissez un fichier TXT ou MD encodé en UTF-8.")
            with path.open("rb") as source:
                data = source.read(IMPORT_LIMIT + 1)
            if len(data) > IMPORT_LIMIT:
                raise ValueError("Document trop volumineux : limite de 256 Kio. Choisissez un extrait plus court.")
            try:
                content = data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("Le document doit être encodé en UTF-8.") from exc
            mid = self.repo.create(content, kind="document", title=path.name, provenance={
                "source": "file", "path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "encoding": "utf-8"})
            self.refresh(mid)
            self.status.set("Document importé en attente. Prévisualisez son contenu avant toute approbation.")
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def prepare_summary(self):
        try:
            sources = []
            for row in reversed(self.app.store.messages(self.app.session_id)):
                if row["role"] == "assistant":
                    context = json.loads(row["metadata"]).get("context", {})
                    sources = [source for source in context.get("sources", []) if source.get("method") == "extractive"]
                    break
            if not sources:
                self.status.set("Le dernier échange ne contient aucun extrait d’archives à résumer. Consultez son Contexte.")
                return
            content = "Résumé extractif non exhaustif — citations exactes d’archives.\n\n" + "\n\n".join(
                f"[Message #{source.get('message_id')} · {source.get('role')} · {source.get('created')}]\n{source.get('excerpt', '')}" for source in sources)
            mid = self.repo.create(content, kind="summary", title="Résumé extractif de conversation", provenance={
                "source": "extractive_summary", "session_id": self.app.session_id,
                "message_ids": list(dict.fromkeys(source["message_id"] for source in sources if isinstance(source.get("message_id"), int))),
                "sources": sources})
            self.refresh(mid)
            self.status.set("Résumé extractif préparé en attente, sans appel LLM. Vérifiez les citations et leurs originaux avant approbation.")
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.report_error(exc)

    def inspect_origins(self):
        from .ui import PANEL, FIELD, TEXT
        window = tk.Toplevel(self.window)
        window.title("Origines de la mémoire")
        window.configure(bg=PANEL, padx=12, pady=12)
        text = tk.Text(window, width=80, height=24, bg=FIELD, fg=TEXT, wrap="word", font=(self.app.font_family, 10))
        text.pack(fill="both", expand=True)
        content = "Provenance enregistrée :\n" + json.dumps(self.provenance, ensure_ascii=False, indent=2)
        for mid in self.provenance.get("message_ids", []):
            row = self.app.store.message(mid)
            source = next((source for source in self.provenance.get("sources", []) if source.get("message_id") == mid), {})
            if row is not None and (row["session_id"] != source.get("session_id") or row["created"] != source.get("created")):
                row = None
            content += f"\n\nOriginal #{mid} :\n" + (row["content"] if row is not None else "Original indisponible ; les citations enregistrées restent consultables.")
        text.insert("1.0", content)
        text.configure(state="disabled")
        ttk.Button(window, text="Fermer", command=window.destroy).pack(anchor="e", pady=(8, 0))
