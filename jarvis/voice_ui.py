"""Voice orchestration on Tk's thread; capture, STT and playback run elsewhere."""
import time
import sqlite3
import tkinter as tk
from collections import deque
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from .richtext import SpeechBuffer, parse_text
from .spectrum import analyze_passages
from .tts import SpeechText
from .voice_config import PERSONALITY_PROMPTS, VOICES, VoiceSettings
from .voice_runtime import AudioProcess, audio_error


class VoiceControls:
    def __init__(self, app, parent):
        self.app = app
        initial_status = "Microphone désactivé"
        try:
            self.settings = VoiceSettings(**app.store.get_preference("voice", {})).validate()
        except (TypeError, ValueError):
            self.settings = VoiceSettings()
            initial_status = "Préférences vocales invalides ; valeurs par défaut temporaires, chat disponible"
        self.capture, self.speech = AudioProcess(), AudioProcess()
        self.listening = False
        self.epoch = self.heard = 0
        self.mid = None
        self.reading = self.end_pending = False
        self.tts_active = self.tts_ready = False
        self.tts_profile = None
        self.playing_sample = False
        self.last_sample = None
        self.stt_details = {}
        self.reference_result = ""
        self.segmenter = SpeechBuffer(speak_code=self.settings.speak_code)
        self.segment_id = 0
        self.last_capture = self.last_speech = 0.0
        self.pending_visuals = []
        self.pending_phrases = deque(maxlen=64)
        self.resume_id = None
        self.transcribing = False
        self.diagnostics = {}
        self.diagnostic_events = deque(maxlen=32)
        self.diagnostic_window = None
        self.reset_turn_latency()
        self.status = tk.StringVar(value=initial_status)
        self.listen_button = ttk.Button(parent, text="Activer l’écoute", command=self.toggle)
        self.listen_button.pack(fill="x", pady=(10, 4))
        ttk.Button(parent, text="Voix / périphériques", command=self.open_settings).pack(fill="x")
        ttk.Button(parent, text="Diagnostic micro / STT", command=self.open_diagnostics).pack(fill="x", pady=2)
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
        if hasattr(self.app, "presence") and self.app.presence.state == "dormant":
            self.app.presence.wake()
        if not messagebox.askyesno("Activer le microphone local", "Autoriser JARVIS à écouter ce microphone et à envoyer les transcriptions au modèle Ollama local ?\n\nL’écoute reste active jusqu’à désactivation. Aucun fichier audio n’est conservé.\nMode casque : interruption vocale. Mode haut-parleurs : écoute suspendue pendant la lecture.", parent=self.app.root):
            return
        self.capture.start("capture", self.settings)
        self.listening = True
        self.transcribing = False
        self.diagnostics = {}
        self.diagnostic_events.clear()
        self.reset_turn_latency()
        self.heard = 0
        self.listen_button.configure(text="Désactiver l’écoute")
        self.status.set("Chargement STT/VAD local…")
        self.last_capture = time.monotonic()
        self.notify_presence("thinking")

    def stop_listening(self):
        self.capture.stop()
        self.listening = False
        self.transcribing = False
        self.listen_button.configure(text="Activer l’écoute")
        self.status.set("Microphone désactivé")
        self.cancel_speech()
        self.notify_presence("silent")

    def emergency(self):
        # Audio always stops before any UI transitions or persistence work.
        self.capture.stop()
        self.speech.stop()
        self.listening = False
        self.transcribing = False
        self.listen_button.configure(text="Activer l’écoute")
        self.cancel_speech()
        if self.app.operation:
            self.app.cancel()
        self.status.set("ARRÊT — microphone, génération et lecture arrêtés")
        self.notify_presence("silent")

    def halt_without_persistence(self):
        """Fail closed even when SQLite is the failing component."""
        self.capture.stop()
        self.speech.stop()
        self.epoch += 1
        self.pending_visuals.clear()
        self.pending_phrases.clear()
        self.segmenter = SpeechBuffer(speak_code=self.settings.speak_code)
        self.end_pending = self.reading = self.listening = False
        self.tts_active = self.tts_ready = False
        self.transcribing = False
        self.playing_sample = False
        self.mid = None
        if self.resume_id is not None:
            self.app.root.after_cancel(self.resume_id)
            self.resume_id = None
        self.listen_button.configure(text="Activer l’écoute")
        self.notify_presence("silent")

    def begin_turn(self, mid, source):
        self.cancel_speech()
        if source != "voice":
            self.reset_turn_latency()
        self.llm_started_at = time.monotonic()
        self.mid = mid if self.listening else None
        self.reading = self.listening
        self.segmenter = SpeechBuffer(speak_code=self.settings.speak_code)
        self.segment_id = 0
        self.notify_presence("thinking")
        if self.reading:
            self.prepare_speech()

    def prepare_speech(self):
        # Warm loading overlaps Ollama. It never opens/mutes the microphone and
        # opens no output stream until an actual phrase is available.
        if (self.speech.process is None or not self.speech.alive()
                or self.tts_profile != self.settings):
            self.speech.start("speech", self.settings, self.epoch)
            self.tts_profile = self.settings
            self.tts_ready = False
            self.last_speech = time.monotonic()
        self.speech.generation = self.epoch

    def submit_phrase(self, phrase):
        if not self.reading:
            return
        if not self.tts_active:
            self.tts_requested_at = time.monotonic()
            self.mark_latency("Premier texte → première phrase TTS", self.first_llm_at, self.tts_requested_at)
            self.prepare_speech()
            self.record_diagnostic("tts_engine", {"ready_before_phrase": self.tts_ready})
            self.tts_active = True
            self.app.stop_button.configure(state="normal")
            self.last_speech = time.monotonic()
            self.app.store.update_message_metadata(self.mid, {"tts_engine": "piper", "voice": self.settings.voice, "audio_status": "synthesizing"})
            if self.listening and self.settings.acoustic_mode == "speakers":
                if not self.capture.send({"kind": "mute", "value": True}):
                    self.cancel_speech(status="error")
                    self.status.set("Lecture annulée : suspension du microphone impossible.")
                    return
                self.status.set("Lecture haut-parleurs : microphone suspendu")
        if len(self.pending_phrases) == self.pending_phrases.maxlen:
            self.cancel_speech(status="error")
            self.status.set("Lecture arrêtée : trop de phrases audio en attente (64). Le texte reste enregistré.")
            return
        self.pending_phrases.append(phrase)
        self.drain_phrases()

    def drain_phrases(self):
        while self.speech.process is not None and self.pending_phrases:
            if not self.speech.send(self.pending_phrases[0]):
                break
            self.pending_phrases.popleft()

    def chunk(self, text):
        if self.reading:
            if text and self.first_llm_at is None:
                self.first_llm_at = time.monotonic()
                self.mark_latency("Ollama : envoi → premier texte reçu", self.llm_started_at, self.first_llm_at)
            self.feed_speech(text)

    def feed_speech(self, text, final=False):
        for segment in self.segmenter.feed(text, final=final):
            self.segment_id += 1
            # Keep display/emoji text out of the engine; retain source positions
            # for captions and later PCM-triggered visual events.
            display = parse_text(segment.original).text
            mode = getattr(getattr(getattr(self.app, "presence", None), "settings", None),
                           "spectrum_mode", "expression")
            if mode not in {"expression", "thematic", "neutral"}:
                mode = "expression"
            self.submit_phrase(SpeechText(segment.text, original=segment.original,
                display_text=display[:4000], start=segment.start, end=segment.end,
                events=segment.events, segment_id=self.segment_id,
                spectrum_events=analyze_passages(segment.original, mode=mode, start=segment.start),
                spectrum_mode=mode))

    def finish_turn(self, status):
        if status != "complete":
            self.cancel_speech()
            return
        if self.reading:
            self.feed_speech("", final=True)
            if self.tts_active:
                self.end_pending = True
            else:
                self.reading = False
                self.mid = None
                self.notify_presence("listening" if self.listening else "silent")
        elif not self.tts_active:
            self.notify_presence("listening" if self.listening else "silent")

    def cancel_speech(self, status="interrupted"):
        if self.resume_id is not None:
            self.app.root.after_cancel(self.resume_id)
            self.resume_id = None
        had_audio = self.tts_active
        if had_audio or not self.listening or status == "error":
            self.speech.stop()
            self.tts_ready = False
        self.tts_active = False
        self.playing_sample = False
        self.epoch += 1
        self.pending_visuals.clear()
        self.pending_phrases.clear()
        self.segmenter = SpeechBuffer(speak_code=self.settings.speak_code)
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
        if self.listening and epoch == self.epoch and not self.tts_active:
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
            if event.kind == "diagnostic":
                self.diagnostics = event.payload
                self.refresh_diagnostics()
            elif event.kind in {"sample_armed", "sample_saved", "sample_error"}:
                self.record_diagnostic(event.kind, event.payload)
                if event.kind == "sample_saved":
                    self.last_sample = event.payload
                    self.status.set("Échantillon PCM enregistré sur votre demande ; réécoute disponible dans le diagnostic.")
                elif event.kind == "sample_error":
                    self.status.set("Échantillon non enregistré : " + str(event.payload))
            elif event.kind in {"turn_end", "stt_complete", "capture_error", "stt_superseded"}:
                self.record_diagnostic(event.kind, event.payload)
                if event.generation == self.heard:
                    if event.kind == "turn_end":
                        self.turn_ended_at = event.payload.get("ended_at")
                        if "silence_ms" in event.payload:
                            self.set_latency("Silence de fin de tour (PCM)", event.payload["silence_ms"])
                    elif event.kind == "stt_complete":
                        self.transcribing = False
                        self.stt_details = event.payload
                        self.stt_latency(event.payload)
                    elif event.kind == "stt_superseded":
                        self.transcribing = False
            elif event.kind == "stt_error":
                self.record_diagnostic(event.kind, event.payload)
                if event.generation == self.heard:
                    self.transcribing = False
                    self.stt_latency(event.payload)
                    self.status.set("Échec STT ; écoute maintenue. Détails dans Diagnostic micro / STT.")
                    if not self.app.operation:
                        self.notify_presence("listening")
            elif event.kind == "speech_start":
                self.record_diagnostic(event.kind, {"tour": event.generation})
                self.heard = event.generation
                self.cancel_speech()
                self.transcribing = False
                self.reset_turn_latency()
                self.stt_details = {}
                self.reference_result = ""
                if self.app.operation == "chat":
                    self.app.cancel()
                self.status.set("Voix détectée")
                self.notify_presence("user_speaking")
            elif event.kind in {"transcribing", "stt_queued"}:
                self.record_diagnostic(event.kind, {"tour": event.generation})
                if event.generation == self.heard:
                    self.transcribing = True
                    self.status.set("Transcription française locale…" if event.kind == "transcribing"
                                    else "Tour vocal conservé ; attente du STT local…")
                    self.notify_presence("thinking")
            elif event.kind == "transcript" and event.generation == self.heard:
                self.transcribing = False
                if event.payload.strip() and not self.app.operation:
                    self.app.send(source="voice", text=event.payload.strip())
                    if self.app.operation != "chat":
                        self.app.input.insert("end", event.payload.strip() + "\n")
                        self.status.set("Transcription conservée dans la saisie ; vérifiez le modèle ou le contexte.")
                elif event.payload.strip():
                    self.status.set("Modèle occupé ; transcription conservée dans la saisie.")
                    self.app.input.insert("end", event.payload + "\n")
                else:
                    self.status.set("Aucune parole transcrite ; écoute active")
                    self.notify_presence("listening")
            elif event.kind == "mic_level":
                if event.payload.get("speaking"):
                    self.notify_presence("user_speaking", signal=event.payload)
                elif self.listening and not self.transcribing and not self.app.operation and not self.tts_active:
                    self.notify_presence("listening", signal=event.payload)
            elif event.kind == "listening":
                if event.payload:
                    self.record_diagnostic("capture_ready", event.payload)
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
            if event.kind == "tts_ready":
                self.tts_ready = True
                self.record_diagnostic("tts_loaded", event.payload)
                if event.generation == self.epoch and event.payload:
                    self.set_latency("Chargement Piper (worker)", event.payload["load_ms"])
                continue
            if event.kind == "tts_load_error":
                self.cancel_speech(status="error")
                self.status.set(str(event.payload))
                continue
            if event.generation != self.epoch:
                continue
            if event.kind == "played":
                view = event.payload
                if not self.playing_sample and self.first_pcm_at is None and self.tts_requested_at is not None:
                    self.first_pcm_at = view.get("started_at", view["emitted_at"] + view["delay"])
                    self.mark_latency("Phrase TTS → premier PCM (DAC estimé)", self.tts_requested_at, self.first_pcm_at)
                    self.mark_latency("Fin de tour détectée → premier PCM (DAC estimé)", self.turn_ended_at, self.first_pcm_at)
                    self.mark_latency("Premier texte → premier PCM (DAC estimé)", self.first_llm_at, self.first_pcm_at)
                    if self.turn_ended_at is not None and "Silence de fin de tour (PCM)" in self.latencies:
                        self.set_latency("Fin de parole VAD → premier PCM (estimé)",
                            (self.first_pcm_at - self.turn_ended_at) * 1000 + self.latencies["Silence de fin de tour (PCM)"])
                    self.publish_timing(complete=True)
                self.pending_visuals.append((view["emitted_at"] + view["delay"], view, self.epoch))
                self.pending_visuals = self.pending_visuals[-64:]
            elif event.kind == "tts_pcm_ready":
                if "Piper : synthèse du premier bloc" not in self.latencies:
                    self.set_latency("Piper : synthèse du premier bloc", event.payload["elapsed_ms"])
            elif event.kind == "speech_done":
                if self.mid is not None:
                    self.app.store.update_message_metadata(self.mid, {"audio_status": "complete"})
                self.mid = None
                self.tts_active = False
                if not self.listening or self.playing_sample:
                    self.speech.stop()
                    self.tts_ready = False
                self.playing_sample = False
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
        self.drain_phrases()
        if self.end_pending and not self.pending_phrases and self.speech.send(None):
            self.end_pending = False
        if self.speech.process is not None and not self.speech.alive() and now - self.last_speech > 0.5:
            self.cancel_speech(status="error")
            self.status.set("Processus de lecture arrêté ; texte conservé.")

    def record_diagnostic(self, kind, payload):
        stamp = time.strftime("%H:%M:%S")
        self.diagnostic_events.append(f"{stamp} · {kind} · {payload}")
        self.refresh_diagnostics()

    def reset_turn_latency(self):
        self.latencies = {}
        self.turn_ended_at = self.llm_started_at = self.first_llm_at = None
        self.tts_requested_at = self.first_pcm_at = None
        self.publish_timing(new_turn=True)

    def set_latency(self, label, milliseconds):
        self.latencies[label] = max(0, round(milliseconds))
        self.refresh_diagnostics()
        self.publish_timing()

    def publish_timing(self, new_turn=False, complete=False):
        if not hasattr(self.app, "presence"):
            return
        names = {"vad_silence_ms": "Silence de fin de tour (PCM)", "stt_ms": "Whisper : transcription",
                 "llm_wait_ms": "Ollama : envoi → premier texte reçu",
                 "token_to_audio_ms": "Premier texte → premier PCM (DAC estimé)",
                 "turn_to_audio_ms": "Fin de tour détectée → premier PCM (DAC estimé)",
                 "speech_to_audio_ms": "Fin de parole VAD → premier PCM (estimé)"}
        self.app.presence.update_timing({key: self.latencies[label] for key, label in names.items()
                                       if label in self.latencies}, new_turn=new_turn, complete=complete)

    def mark_latency(self, label, start, end):
        if start is not None and end is not None:
            self.set_latency(label, (end - start) * 1000)

    def stt_latency(self, payload):
        self.set_latency("Whisper : transcription", payload["elapsed_ms"])
        if "queue_ms" in payload:
            self.set_latency("Whisper : attente en file", payload["queue_ms"])

    def refresh_diagnostics(self):
        if self.diagnostic_window is None or not self.diagnostic_window.winfo_exists():
            return
        values = self.diagnostics
        probability = values.get("vad")
        text = (f"RMS micro : {values.get('rms', 0):.5f}   |   Probabilité VAD : "
                + (f"{probability:.3f}" if probability is not None else "—")
                + f"\nÉtat : {values.get('state', 'en attente')}   |   Tour : {values.get('turn_seconds', 0):.2f} s"
                + f"\nPCM : {values.get('native_rate', '—')} → {values.get('rate', '—')} Hz ; trames : {values.get('frame_samples', '—')}"
                + f"\nDernière fin : {values.get('end_reason', '') or 'aucune'}"
                + f"\nSTT : {values.get('last_stt', 'en attente')}\n\n"
                + "Latences du dernier tour (ms) :\n"
                + ("\n".join(f"{label} : {value}" for label, value in self.latencies.items()) or "En attente de mesures")
                + "\nDAC estimé par PortAudio ; délai acoustique/Bluetooth non mesuré.\n\n"
                + f"STT conservé : {self.stt_details.get('result', '—')}\n"
                + f"STT brut : {self.stt_details.get('raw_result', '—')}\n"
                + f"Langue demandée : {self.stt_details.get('language_requested', '—')} ; segments écartés : {self.stt_details.get('discarded_segments', '—')}\n"
                + (f"Qualité du dernier WAV : {self.last_sample.get('quality', {})} ; fin : {self.last_sample.get('end_reason', '—')}\n" if self.last_sample else "")
                + self.reference_result + "\n\n"
                + "\n".join(self.diagnostic_events))
        self.diagnostic_text.configure(state="normal")
        self.diagnostic_text.delete("1.0", "end")
        self.diagnostic_text.insert("1.0", text)
        self.diagnostic_text.configure(state="disabled")
        self.diagnostic_text.see("end")

    def open_diagnostics(self):
        if self.diagnostic_window is not None and self.diagnostic_window.winfo_exists():
            self.diagnostic_window.lift()
            return
        dialog = self.diagnostic_window = tk.Toplevel(self.app.root)
        dialog.title("Diagnostic local · micro → VAD → STT")
        dialog.geometry("820x670")
        dialog.configure(bg="#121c29", padx=12, pady=12)
        tk.Label(dialog, text="Mesures réelles, actualisées 4 fois/s. Trace en mémoire ; WAV uniquement sur demande explicite. Aucun envoi réseau.",
                 bg="#121c29", fg="#e4edf6", wraplength=720, justify="left").pack(anchor="w")
        from tkinter.scrolledtext import ScrolledText
        self.diagnostic_text = ScrolledText(dialog, wrap="word", bg="#0b1019", fg="#e4edf6", height=14)
        self.diagnostic_text.pack(fill="both", expand=True, pady=8)
        ttk.Button(dialog, text="Terminer le tour courant (si VAD reste actif)",
                   command=lambda: self.capture.send({"kind": "finish_turn"})).pack(anchor="w")
        ttk.Button(dialog, text="Enregistrer le prochain tour en WAV… (sur demande)",
                   command=self.request_sample).pack(anchor="w", pady=3)
        ttk.Button(dialog, text="Réécouter le dernier WAV demandé", command=self.replay_sample).pack(anchor="w", pady=3)
        from .audio_diagnostics import REFERENCE_PHRASES
        tk.Label(dialog, text="Référence française à lire avant la comparaison (modifiable) :",
                 bg="#121c29", fg="#e4edf6").pack(anchor="w", pady=(8, 2))
        self.reference = tk.StringVar(value=REFERENCE_PHRASES[0])
        ttk.Combobox(dialog, textvariable=self.reference, values=REFERENCE_PHRASES).pack(fill="x")
        ttk.Button(dialog, text="Comparer référence / dernière transcription (WER)",
                   command=self.compare_reference).pack(anchor="w", pady=3)
        self.refresh_diagnostics()

    def request_sample(self):
        if not self.listening:
            self.status.set("Activez explicitement l’écoute avant de demander un échantillon.")
            return
        path = filedialog.asksaveasfilename(parent=self.diagnostic_window, title="PCM micro local, un seul tour (20 s maximum)",
                                           defaultextension=".wav", filetypes=[("Audio WAV", "*.wav")])
        if path and messagebox.askyesno("Enregistrer un échantillon microphone", f"Enregistrer le prochain tour transcrit dans :\n{path}\n\nUn seul WAV mono 16 kHz, 20 s maximum (environ 625 Kio). Aucun envoi réseau. Fichier conservé jusqu’à votre suppression. Ne pas utiliser cet enregistrement pour mesurer la latence normale.", parent=self.diagnostic_window):
            if not self.capture.send({"kind": "sample_next", "path": path}):
                self.status.set("Demande non transmise : file micro occupée, réessayez.")

    def replay_sample(self):
        if not self.last_sample:
            self.status.set("Aucun échantillon demandé et enregistré dans cette session.")
            return
        self.cancel_speech()
        self.playing_sample = self.tts_active = True
        self.tts_ready = False
        self.tts_profile = None
        if self.listening and not self.capture.send({"kind": "mute", "value": True}):
            self.cancel_speech(status="error")
            self.status.set("Réécoute annulée : suspension du microphone impossible.")
            return
        self.speech.start("sample", self.settings, self.epoch)
        self.last_speech = time.monotonic()
        if not self.speech.send(self.last_sample["path"]):
            self.cancel_speech(status="error")
            self.status.set("Réécoute non transmise, réessayez.")
        else:
            self.app.stop_button.configure(state="normal")
            self.status.set("Réécoute du PCM microphone demandé ; Arrêter coupe le son.")

    def compare_reference(self):
        from .audio_diagnostics import word_error
        if "result" not in self.stt_details or not self.reference.get().strip():
            self.reference_result = "Lire une référence, puis attendre sa transcription avant de comparer."
        else:
            score = word_error(self.reference.get(), self.stt_details["result"])
            if not score["words"]:
                self.reference_result = "La référence doit contenir au moins un mot pour calculer le WER."
            else:
                self.reference_result = f"WER (référence saisie) : {score['wer']:.1%} ; {score['errors']} erreur(s) / {score['words']} mots."
        self.refresh_diagnostics()

    def preview(self):
        if hasattr(self.app, "presence") and self.app.presence.state == "dormant":
            self.app.presence.wake()
        self.cancel_speech()
        self.reset_turn_latency()
        self.tts_requested_at = time.monotonic()
        self.prepare_speech()
        self.tts_active = True
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
                   "voice": list(VOICES), "acoustic_mode": ["speakers", "headphones"],
                   "personality": ["Personnalisé", *PERSONALITY_PROMPTS]}
        fields = [("input_device", "Microphone (vide = défaut Windows)"), ("output_device", "Sortie audio (vide = défaut Windows)"),
                  ("voice", "Voix : Tom homme / Siwis femme"), ("speed", "Vitesse (0.5–2)"),
                  ("acoustic_mode", "speakers = haut-parleurs / headphones = casque"),
                  ("silence_ms", "Silence de fin de tour (300–2500 ms)"), ("models_dir", "Dossier modèles (vide = profil local)"),
                  ("personality", "Profil (changer remplace l’instruction système)")]
        for row, (key, label) in enumerate(fields):
            tk.Label(dialog, text=label, bg="#121c29", fg="#e4edf6").grid(row=row, column=0, sticky="w", pady=5)
            values[key] = tk.StringVar(value=str(getattr(self.settings, key)))
            if key in options:
                widget = ttk.Combobox(dialog, textvariable=values[key], values=options[key], state="readonly", width=45)
            else:
                widget = ttk.Entry(dialog, textvariable=values[key], width=48)
            widget.grid(row=row, column=1, sticky="ew", padx=8)
        ttk.Button(dialog, text="Choisir dossier…", command=lambda: values["models_dir"].set(filedialog.askdirectory(parent=dialog) or values["models_dir"].get())).grid(row=8, column=1, sticky="e")
        speak_code = tk.BooleanVar(value=self.settings.speak_code)
        ttk.Checkbutton(dialog, text="Lire le contenu des blocs de code (sinon : « Bloc de code non lu »)",
                        variable=speak_code).grid(row=9, column=0, columnspan=2, sticky="w")

        def save(close=True):
            try:
                candidate = replace(self.settings, **{k: v.get() for k, v in values.items() if k not in {"speed", "silence_ms"}},
                                    speed=float(values["speed"].get()), silence_ms=int(values["silence_ms"].get()),
                                    speak_code=speak_code.get()).validate()
                if candidate.personality != self.settings.personality and candidate.personality in PERSONALITY_PROMPTS:
                    model_settings = replace(self.app.settings, system_prompt=PERSONALITY_PROMPTS[candidate.personality])
                    self.app.store.save_settings(model_settings)
                    self.app.settings = model_settings
                self.app.store.set_preference("voice", candidate.to_dict())
                self.cancel_speech()
                self.settings = candidate
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("Voix", str(exc), parent=dialog)
                return
            if close:
                dialog.destroy()
            else:
                self.preview()

        tk.Label(dialog, text="Modèles à installer séparément (guide docs/VOICE.md). Aucun téléchargement automatique.\nCasque requis pour interrompre par la voix pendant la lecture. Aucun AEC haut-parleurs annoncé.",
                 bg="#121c29", fg="#a6b8cb", wraplength=700, justify="left").grid(row=10, column=0, columnspan=2, pady=12, sticky="w")
        ttk.Button(dialog, text="Préécoute réelle", command=lambda: save(False)).grid(row=11, column=0, sticky="w")
        ttk.Button(dialog, text="Enregistrer", command=save).grid(row=11, column=1, sticky="e")
