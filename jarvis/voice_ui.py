"""Voice orchestration on Tk's thread; capture, STT and playback run elsewhere."""
import time
import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from .tts import SentenceBuffer
from .voice_config import VOICES, VoiceSettings
from .voice_runtime import AudioProcess, audio_error


class VoiceControls:
    def __init__(self, app, parent):
        self.app = app
        self.settings = VoiceSettings(**app.store.get_preference("voice", {})).validate()
        self.capture, self.speech = AudioProcess(), AudioProcess()
        self.listening = False
        self.epoch = self.heard = 0
        self.mid = None
        self.reading = self.end_pending = False
        self.segmenter = SentenceBuffer()
        self.last_capture = self.last_speech = 0.0
        self.pending_visuals = []
        self.resume_id = None
        self.status = tk.StringVar(value="Microphone désactivé")
        self.listen_button = ttk.Button(parent, text="Activer l’écoute", command=self.toggle)
        self.listen_button.pack(fill="x", pady=(10, 4))
        ttk.Button(parent, text="Voix / périphériques", command=self.open_settings).pack(fill="x")
        ttk.Button(parent, text="Arrêt d’urgence", command=self.emergency).pack(fill="x", pady=4)
        tk.Label(parent, textvariable=self.status, bg="#121c29", fg="#a6b8cb",
                 wraplength=235, justify="left", font=(app.font_family, 9)).pack(fill="x", pady=4)

    def notify_presence(self, state, signal=None, caption=None):
        if hasattr(self.app, "presence"):
            self.app.presence.update_event(state, signal=signal, caption=caption)

    def toggle(self):
        if self.listening:
            self.stop_listening()
            return
        if not messagebox.askyesno("Activer le microphone local", "Autoriser JARVIS à écouter ce microphone et à envoyer les transcriptions au modèle Ollama local ?\n\nL’écoute reste active jusqu’à désactivation. Aucun fichier audio n’est conservé.\nMode casque : interruption vocale. Mode haut-parleurs : écoute suspendue pendant la lecture.", parent=self.app.root):
            return
        self.capture.start("capture", self.settings)
        self.listening = True
        self.heard = 0
        self.listen_button.configure(text="Désactiver l’écoute")
        self.status.set("Chargement STT/VAD local…")
        self.last_capture = time.monotonic()
        self.notify_presence("thinking")

    def stop_listening(self):
        self.capture.stop()
        self.listening = False
        self.listen_button.configure(text="Activer l’écoute")
        self.status.set("Microphone désactivé")
        self.cancel_speech()
        self.notify_presence("silent")

    def emergency(self):
        # Audio always stops before any UI transitions or persistence work.
        self.capture.stop()
        self.speech.stop()
        self.listening = False
        self.listen_button.configure(text="Activer l’écoute")
        self.cancel_speech()
        if self.app.operation:
            self.app.cancel()
        self.status.set("ARRÊT — microphone, génération et lecture arrêtés")
        self.notify_presence("silent")

    def begin_turn(self, mid, source):
        self.cancel_speech()
        self.mid = mid if self.listening else None
        self.reading = self.listening
        self.segmenter = SentenceBuffer()
        self.notify_presence("thinking")

    def submit_phrase(self, phrase):
        if not self.reading:
            return
        if self.speech.process is None:
            self.speech.start("speech", self.settings, self.epoch)
            self.app.stop_button.configure(state="normal")
            self.last_speech = time.monotonic()
            self.app.store.update_message_metadata(self.mid, {"tts_engine": "piper", "voice": self.settings.voice, "audio_status": "synthesizing"})
            if self.listening and self.settings.acoustic_mode == "speakers":
                if not self.capture.send({"kind": "mute", "value": True}):
                    self.cancel_speech(status="error")
                    self.status.set("Lecture annulée : suspension du microphone impossible.")
                    return
                self.status.set("Lecture haut-parleurs : microphone suspendu")
        if not self.speech.send(phrase):
            self.cancel_speech(status="error")
            self.status.set("Lecture arrêtée : file audio saturée. Le texte reste enregistré.")

    def chunk(self, text):
        if self.reading:
            for phrase in self.segmenter.feed(text):
                self.submit_phrase(phrase)

    def finish_turn(self, status):
        if status != "complete":
            self.cancel_speech()
            return
        if self.reading:
            for phrase in self.segmenter.feed("", final=True):
                self.submit_phrase(phrase)
            if self.speech.process is not None:
                self.end_pending = True
            else:
                self.reading = False
                self.mid = None
                self.notify_presence("listening" if self.listening else "silent")
        elif not self.speech.alive():
            self.notify_presence("listening" if self.listening else "silent")

    def cancel_speech(self, status="interrupted"):
        if self.resume_id is not None:
            self.app.root.after_cancel(self.resume_id)
            self.resume_id = None
        had_audio = self.speech.process is not None
        self.speech.stop()
        self.epoch += 1
        self.pending_visuals.clear()
        self.end_pending = False
        self.reading = False
        if not self.app.operation:
            self.app.stop_button.configure(state="disabled")
        if self.mid is not None:
            self.app.store.update_message_metadata(self.mid, {"audio_status": status})
            self.mid = None
        if self.listening:
            if had_audio and self.settings.acoustic_mode == "speakers":
                self.schedule_resume()
            else:
                self.capture.send({"kind": "mute", "value": False})
        state = "thinking" if self.app.operation == "chat" else "listening" if self.listening else "silent"
        self.notify_presence(state, signal={"rms": 0.0, "wave": []})

    def _resume_microphone(self, epoch):
        self.resume_id = None
        if self.listening and epoch == self.epoch and self.speech.process is None:
            self.capture.send({"kind": "mute", "value": False})
            self.status.set("Écoute locale active")
            if not self.app.operation:
                self.notify_presence("listening")

    def schedule_resume(self):
        if self.resume_id is not None:
            self.app.root.after_cancel(self.resume_id)
        self.resume_id = self.app.root.after(350, lambda epoch=self.epoch: self._resume_microphone(epoch))

    def poll(self):
        now = time.monotonic()
        for event in self.capture.poll():
            self.last_capture = now
            if event.kind == "speech_start":
                self.heard = event.generation
                self.cancel_speech()
                if self.app.operation == "chat":
                    self.app.cancel()
                self.status.set("Voix détectée")
                self.notify_presence("user_speaking")
            elif event.kind == "transcribing":
                self.status.set("Transcription française locale…")
                self.notify_presence("thinking")
            elif event.kind == "transcript" and event.generation == self.heard:
                if event.payload.strip() and not self.app.operation:
                    self.app.send(source="voice", text=event.payload.strip())
                elif event.payload.strip():
                    self.status.set("Modèle occupé ; transcription conservée dans la saisie.")
                    self.app.input.insert("end", event.payload + "\n")
                else:
                    self.status.set("Aucune parole transcrite ; écoute active")
                    self.notify_presence("listening")
            elif event.kind == "mic_level":
                if event.payload.get("speaking"):
                    self.notify_presence("user_speaking", signal=event.payload)
                elif self.listening and not self.app.operation and not self.speech.alive():
                    self.notify_presence("listening", signal=event.payload)
            elif event.kind == "listening":
                self.status.set("Écoute locale active")
                self.notify_presence("listening")
            elif event.kind == "error":
                self.stop_listening()
                self.status.set(str(event.payload))
            elif event.kind == "warning":
                self.status.set(str(event.payload))
        if self.listening and not self.capture.alive() and now - self.last_capture > 0.5:
            self.stop_listening()
            self.status.set("Processus micro arrêté. Réactivez l’écoute après vérification audio.")
        for event in self.speech.poll():
            self.last_speech = now
            if event.generation != self.epoch:
                continue
            if event.kind == "played":
                view = event.payload
                self.pending_visuals.append((view["emitted_at"] + view["delay"], view, self.epoch))
                self.pending_visuals = self.pending_visuals[-64:]
            elif event.kind == "speech_done":
                if self.mid is not None:
                    self.app.store.update_message_metadata(self.mid, {"audio_status": "complete"})
                self.mid = None
                self.speech.stop()
                self.reading = False
                if not self.app.operation:
                    self.app.stop_button.configure(state="disabled")
                self.pending_visuals.clear()
                self.status.set("Lecture terminée")
                if self.listening:
                    self.schedule_resume()
                self.notify_presence("listening" if self.listening else "silent")
            elif event.kind == "error":
                self.cancel_speech(status="error")
                self.status.set(str(event.payload))
        for due, view, epoch in self.pending_visuals[:]:
            if due <= now:
                if epoch == self.epoch:
                    self.notify_presence("jarvis_speaking", signal=view, caption=view)
                self.pending_visuals.remove((due, view, epoch))
        if self.end_pending and self.speech.send(None):
            self.end_pending = False
        if self.speech.process is not None and not self.speech.alive() and now - self.last_speech > 0.5:
            self.cancel_speech(status="error")
            self.status.set("Processus de lecture arrêté ; texte conservé.")

    def preview(self):
        self.cancel_speech()
        self.speech.start("speech", self.settings, self.epoch)
        self.app.stop_button.configure(state="normal")
        self.last_speech = time.monotonic()
        self.speech.send("Bonjour. Je suis JARVIS. Voici un aperçu de ma voix française.")
        self.end_pending = True
        if self.listening and self.settings.acoustic_mode == "speakers":
            self.capture.send({"kind": "mute", "value": True})

    def open_settings(self):
        if self.listening or self.app.operation:
            messagebox.showinfo("Voix", "Désactivez l’écoute et terminez la génération avant de changer les périphériques.", parent=self.app.root)
            return
        from .audio import device_inventory
        try:
            devices = device_inventory()
        except Exception as exc:
            devices = {"input": [], "output": []}
            self.status.set(audio_error(exc))
        dialog = tk.Toplevel(self.app.root)
        dialog.title("Voix locale · microphone désactivé")
        dialog.configure(bg="#121c29", padx=18, pady=18)
        dialog.transient(self.app.root)
        dialog.grab_set()
        values = {}
        options = {"input_device": [""] + [d["key"] for d in devices["input"]],
                   "output_device": [""] + [d["key"] for d in devices["output"]],
                   "voice": list(VOICES), "acoustic_mode": ["speakers", "headphones"]}
        fields = [("input_device", "Microphone (vide = défaut Windows)"), ("output_device", "Sortie audio (vide = défaut Windows)"),
                  ("voice", "Voix : Tom homme / Siwis femme"), ("speed", "Vitesse (0.5–2)"),
                  ("acoustic_mode", "speakers = haut-parleurs / headphones = casque"),
                  ("silence_ms", "Silence de fin de tour (300–2500 ms)"), ("models_dir", "Dossier modèles (vide = profil local)")]
        for row, (key, label) in enumerate(fields):
            tk.Label(dialog, text=label, bg="#121c29", fg="#e4edf6").grid(row=row, column=0, sticky="w", pady=5)
            values[key] = tk.StringVar(value=str(getattr(self.settings, key)))
            if key in options:
                widget = ttk.Combobox(dialog, textvariable=values[key], values=options[key], state="readonly", width=45)
            else:
                widget = ttk.Entry(dialog, textvariable=values[key], width=48)
            widget.grid(row=row, column=1, sticky="ew", padx=8)
        ttk.Button(dialog, text="Choisir dossier…", command=lambda: values["models_dir"].set(filedialog.askdirectory(parent=dialog) or values["models_dir"].get())).grid(row=7, column=1, sticky="e")

        def save(close=True):
            try:
                candidate = replace(self.settings, **{k: v.get() for k, v in values.items() if k not in {"speed", "silence_ms"}},
                                    speed=float(values["speed"].get()), silence_ms=int(values["silence_ms"].get())).validate()
                self.app.store.set_preference("voice", candidate.to_dict())
                self.settings = candidate
            except (ValueError, OSError) as exc:
                messagebox.showerror("Voix", str(exc), parent=dialog)
                return
            if close:
                dialog.destroy()
            else:
                self.preview()

        tk.Label(dialog, text="Modèles à installer séparément (guide docs/VOICE.md). Aucun téléchargement automatique.\nCasque requis pour interrompre par la voix pendant la lecture. Aucun AEC haut-parleurs annoncé.",
                 bg="#121c29", fg="#a6b8cb", wraplength=700, justify="left").grid(row=8, column=0, columnspan=2, pady=12, sticky="w")
        ttk.Button(dialog, text="Préécoute réelle", command=lambda: save(False)).grid(row=9, column=0, sticky="w")
        ttk.Button(dialog, text="Enregistrer", command=save).grid(row=9, column=1, sticky="e")
