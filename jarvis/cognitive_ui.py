"""Small views of the owner's observations. No device, DB or model polling."""
import json
import sqlite3
import time
import tkinter as tk
from dataclasses import replace
from tkinter import ttk, messagebox

from .cognitive_state import CognitiveHudSettings, LABELS, summary
from .settings_form import SettingsForm


class CognitivePanel:
    def __init__(self, app, parent):
        self.app = app
        raw = app.store.get_preference("cognitive_hud", {})
        self.saved = dict(raw) if isinstance(raw, dict) else {}
        self.settings = CognitiveHudSettings.from_dict(raw)
        self.last_revision, self.last_at = -1, 0.
        self.window = self.details = None
        self.text = tk.StringVar(app.root)
        self.label = tk.Label(parent, textvariable=self.text, bg="#0b1019", fg="#a6b8cb",
                              anchor="w", font=(app.font_family, 9), takefocus=True, cursor="hand2")
        self.label.pack(fill="x", pady=(3, 0))
        self.label.bind("<Button-1>", lambda _event: self.open())
        self.label.bind("<Return>", lambda _event: self.open())

    def refresh(self, force=False):
        now = time.monotonic()
        changed = self.last_revision != self.app.cognitive.revision
        if not force and not changed and (self.settings.level == "minimal" or not self.settings.show_durations
                                          or now - self.last_at < 1.):
            return
        presence = getattr(self.app, "presence", None)
        window = getattr(presence, "window", None)
        visible = (self.app.root.winfo_viewable() or window is not None and window.winfo_viewable()
                   or getattr(presence, "_gpu_visible", False))
        if not force and not visible:
            return
        snapshot = self.app.cognitive.snapshot(now=now)
        text = summary(snapshot, self.settings, now=now)
        if text != self.text.get():
            self.text.set(text)
            update = getattr(presence, "update_cognitive", None)
            if callable(update):
                update(text[:300])
        if self.settings.enabled:
            if not self.label.winfo_manager():
                self.label.pack(fill="x", pady=(3, 0))
        else:
            self.label.pack_forget()
        if self.details is not None and self.details.winfo_exists() and self.details.winfo_viewable():
            lines = ["Activités observées : " + ", ".join(LABELS[key] for key in snapshot["activities"]),
                     "Mesures disponibles : " + json.dumps(snapshot["metrics"], ensure_ascii=False),
                     "Événements récents — mémoire temporaire, 64 maximum, 15 minutes :"]
            lines.extend(f"{event['at']:.3f} · tour {event['turn_id']} / génération {event['generation']} · "
                         f"{event['activity']} {'début' if event['active'] else 'fin'} {event['detail']}"
                         for event in self.app.cognitive.events(now=now))
            value = "\n".join(lines)
            if self.details.get("1.0", "end-1c") != value:
                self.details.configure(state="normal")
                self.details.delete("1.0", "end")
                self.details.insert("1.0", value)
                self.details.configure(state="disabled")
        self.last_revision, self.last_at = snapshot["revision"], now

    def open(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            return self.window
        dialog = self.window = tk.Toplevel(self.app.root)
        dialog.title("Cognitive HUD · activité observée")
        shell = SettingsForm(dialog, background="#121c29")
        body, footer = shell.content, shell.footer
        values, controls = {}, {}
        dialog.controls = controls
        ttk.Label(body, text="Les statuts décrivent les événements de JARVIS, pas ses pensées.\n"
                  "Aucune progression ni certitude interne estimée.", wraplength=300).pack(fill="x", pady=8)
        for key, label in (("enabled", "Afficher le Cognitive HUD"), ("show_durations", "Durée de l’activité"),
                           ("show_model", "Modèle Ollama"), ("show_policy", "Politique C1 et budget"),
                           ("show_provenance", "Nombre de sources dans le contexte"),
                           ("show_actions", "Actions sur les sélections de réponses")):
            values[key] = tk.BooleanVar(dialog, value=getattr(self.settings, key))
            controls[key] = ttk.Checkbutton(body, name=key, text=label, variable=values[key])
            controls[key].pack(anchor="w", pady=3)
        levels = {"Minimal": "minimal", "Standard": "standard", "Diagnostic": "diagnostic"}
        level = tk.StringVar(dialog, value=next(key for key, value in levels.items() if value == self.settings.level))
        controls["level"] = ttk.Combobox(body, name="level", values=list(levels), state="readonly", textvariable=level)
        controls["level"].pack(fill="x", pady=6)
        ttk.Button(body, text="Contexte et provenance de la réponse", command=self.app.open_context).pack(fill="x", pady=4)
        self.details = tk.Text(body, height=10, wrap="word", bg="#192638", fg="#e4edf6", state="disabled")
        self.details.pack(fill="x", pady=8)
        def save():
            candidate = replace(self.settings, level=levels[level.get()], **{key: var.get() for key, var in values.items()})
            saved = {**self.saved, **candidate.to_dict()}
            try:
                self.app.store.set_preference("cognitive_hud", saved)
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("Cognitive HUD", str(exc), parent=dialog)
                return
            self.saved, self.settings = saved, candidate
            self.last_revision = -1
            self.refresh(force=True)
            handler = getattr(self.app, "configure_selection_actions", None)
            if callable(handler):
                handler()
            dialog.destroy()
        dialog.save_button = ttk.Button(footer, text="Appliquer", command=save)
        dialog.save_button.pack(side="right")
        ttk.Button(footer, text="Annuler", command=dialog.destroy).pack(side="left")
        dialog.bind("<Control-s>", lambda _event: save())
        self.refresh(force=True)
        return dialog
