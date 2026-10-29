"""Voice orchestration on Tk's thread; capture, STT and playback run elsewhere."""
import math
import time
import sqlite3
import tkinter as tk
from collections import deque
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from .richtext import SpeechBuffer, parse_text
from .captions import prepare_caption
from .spectrum import analyze_passages
from .tts import SpeechText
from .voice_config import PERSONALITY_PROMPTS, SPEECH_PROFILES, VOICES, VoiceSettings
from .voice_commands import recognize_command, command_echo
from .voice_runtime import AudioProcess, audio_error


class VoiceControls:
    MICROPHONE_STATES = frozenset({"disabled", "starting", "open", "voice", "stt", "suspended", "error"})

    def __init__(self, app, parent):
        self.app = app
        self.microphone_state = "disabled"
        self.microphone_detail = ""
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
        self.visual_spectrum_requested = False
        self.spectrum_diagnostic = ""
        self.playing_sample = False
        self.last_sample = None
        self.stt_details = {}
        self.reference_result = ""
        self.segmenter = SpeechBuffer(speak_code=self.settings.speak_code)
        self.segment_id = 0
        self.last_capture = self.last_speech = 0.0
        self.pending_visuals = []
        self.pending_segment_ends = []
        self.visual_end_pending = None
        self.pending_phrases = deque(maxlen=64)
        self.resume_id = None
        self.transcribing = False
        self.diagnostics = {}
        self.diagnostic_events = deque(maxlen=32)
        self.diagnostic_window = None
        self.settings_dialog = None
        self.actions_dialog = None
        self.confirmed_turn = None
        self.transcript_handled = None
        self.echo_turn_output = ()
        self.echo_until = 0.
        self.echo_tail_output = ()
        self.recent_output = deque(maxlen=8)
        self.submitted_output = deque(maxlen=8)
        self.replay_mid = None
        self.replay_session = None
        self.replay_offset = 0
        self.source_offset = 0
        self.replay_source = None
        self.replay_cursor = 0
        self.last_capture_event = "aucun"
        self.last_capture_event_at = self.last_pcm_at = None
        self.diagnostic_failure = ""
        self._diagnostic_refreshed_at = 0.0
        self._diagnostic_body = None
        self.reset_turn_latency()
        self.status = tk.StringVar(value=initial_status)
        self.listen_button = ttk.Button(parent, text="Activer l’écoute", command=self.toggle)
        self.listen_button.pack(fill="x", pady=(10, 4))
        ttk.Button(parent, text="Voix / périphériques", command=self.open_settings).pack(fill="x")
        ttk.Button(parent, text="Diagnostic micro / STT", command=self.open_diagnostics).pack(fill="x", pady=2)
        ttk.Button(parent, text="Lecture et commandes", command=self.open_actions).pack(fill="x", pady=2)
        ttk.Button(parent, text="Arrêt d’urgence", command=self.emergency).pack(fill="x", pady=4)
        tk.Label(parent, textvariable=self.status, bg="#121c29", fg="#a6b8cb",
                 wraplength=235, justify="left", font=(app.font_family, 9)).pack(fill="x", pady=4)

    def notify_presence(self, state, signal=None, caption=None):
        if hasattr(self.app, "presence"):
            self.app.presence.update_event(state, signal=signal, caption=caption)

    def observe_activity(self, activity=None, active=True, *, response=True, metrics=None):
        observer = getattr(type(self.app), "observe_audio_activity", None)
        if callable(observer):
            observer(self.app, activity, active, epoch=self.epoch,
                     generation=getattr(self, "cognitive_generation", None) if response else None,
                     metrics=metrics)

    def set_mic_state(self, state, detail=""):
        """Publish capture status separately from the emotional/audio visual."""
        if state not in self.MICROPHONE_STATES:
            raise ValueError(f"Unknown microphone state: {state}")
        detail = str(detail or "")[:256]
        changed = (state, detail) != (self.microphone_state, self.microphone_detail)
        self.microphone_state, self.microphone_detail = state, detail
        update = getattr(getattr(self.app, "presence", None), "update_microphone", None)
        if changed and callable(update):
            update(state, detail=detail)
        if changed:
            self.observe_activity("audio_loading", state == "starting", response=False)
            self.observe_activity("listening", state in {"open", "voice", "stt"}, response=False)
            self.observe_activity("user_speaking", state == "voice", response=False)
            self.observe_activity("transcribing", state == "stt", response=False)
            if state == "error":
                self.observe_activity("error", response=False)

    def toggle(self):
        if self.listening:
            self.stop_listening()
            return
        if hasattr(self.app, "presence") and self.app.presence.state == "dormant":
            self.app.presence.wake()
        if not messagebox.askyesno("Activer le microphone local", "Autoriser JARVIS à écouter ce microphone et à envoyer les transcriptions au modèle Ollama local ?\n\nL’écoute reste active jusqu’à désactivation. Aucun fichier audio n’est conservé.\nMode casque : interruption vocale. Mode haut-parleurs : écoute suspendue pendant la lecture.", parent=self.app.root):
            self.set_mic_state("disabled", "Autorisation refusée")
            return
        self.capture.start("capture", self.settings)
        self.listening = True
        self.transcribing = False
        self.diagnostics = {}
        self.diagnostic_events.clear()
        self.last_capture_event = "démarrage demandé"
        self.last_capture_event_at = time.monotonic()
        self.last_pcm_at = None
        self.diagnostic_failure = ""
        self.stt_details = {}
        self.reference_result = ""
        self.reset_turn_latency()
        self.heard = 0
        self.confirmed_turn = None
        self.transcript_handled = None
        self.listen_button.configure(text="Désactiver l’écoute")
        self.last_capture = time.monotonic()
        if self.tts_active and self.settings.acoustic_mode == "speakers":
            # The capture worker consumes mute before VAD reads its first PCM.
            # Activating listening during a button-initiated replay must retain
            # exactly the same speaker isolation as a normal voice response.
            if not self.capture.send({"kind": "mute", "value": True}):
                self.stop_listening()
                self.status.set("Écoute annulée : suspension du microphone impossible pendant la lecture.")
                self.set_mic_state("error", "Suspension du microphone impossible")
                return
            self.set_mic_state("suspended", "Chargement local ; lecture haut-parleurs")
            self.status.set("Lecture haut-parleurs : microphone suspendu")
        else:
            self.status.set("Chargement STT/VAD local…")
            self.set_mic_state("starting", "Chargement STT/VAD local")
        if not self.tts_active:
            self.notify_presence("thinking")

    def stop_listening(self):
        self.capture.stop()
        self.listening = False
        self.confirmed_turn = None
        self.transcribing = False
        self.listen_button.configure(text="Activer l’écoute")
        self.status.set("Microphone désactivé")
        self.cancel_speech()
        self.set_mic_state("disabled")
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
        self.set_mic_state("disabled", "Arrêt d’urgence")
        self.notify_presence("silent")

    def halt_without_persistence(self):
        """Fail closed even when SQLite is the failing component."""
        self.capture.stop()
        self.speech.stop()
        self.epoch += 1
        self.pending_visuals.clear()
        self.pending_segment_ends.clear()
        self.visual_end_pending = None
        self.pending_phrases.clear()
        self.segmenter = SpeechBuffer(speak_code=self.settings.speak_code)
        self.end_pending = self.reading = self.listening = False
        self.tts_active = self.tts_ready = False
        self.transcribing = False
        self.playing_sample = False
        self.mid = None
        self.replay_source = None
        if self.resume_id is not None:
            self.app.root.after_cancel(self.resume_id)
            self.resume_id = None
        self.listen_button.configure(text="Activer l’écoute")
        self.set_mic_state("disabled", "Arrêt de sécurité")
        self.notify_presence("silent")

    def begin_turn(self, mid, source):
        self.cancel_speech()
        self.cognitive_generation = getattr(getattr(self.app, "cognitive", None), "generation", None)
        presence = getattr(self.app, "presence", None)
        reset_field = getattr(type(presence), "begin_response", None)
        if callable(reset_field):
            reset_field(presence)
        if source != "voice":
            self.reset_turn_latency()
        self.llm_started_at = time.monotonic()
        self.mid = mid if self.listening else None
        self.replay_mid, self.replay_session, self.replay_offset = mid, self.app.session_id, 0
        self.source_offset = 0
        self.reading = self.listening
        self.segmenter = SpeechBuffer(speak_code=self.settings.speak_code)
        self.segment_id = 0
        self.notify_presence("thinking")
        if self.reading:
            self.prepare_speech()

    def prepare_speech(self):
        # Warm loading overlaps Ollama. It never opens/mutes the microphone and
        # opens no output stream until an actual phrase is available.
        engine_keys = ("voice", "models_dir", "output_device")
        if (self.speech.process is None or not self.speech.alive() or self.tts_profile is None
                or any(getattr(self.tts_profile, key) != getattr(self.settings, key) for key in engine_keys)):
            self.speech.start("speech", self.settings, self.epoch)
            self.observe_activity("synthesis")
            self.tts_profile = self.settings
            self.tts_ready = False
            self.last_speech = time.monotonic()
            if self.visual_spectrum_requested:
                self.speech.send({"kind": "visual_spectrum", "enabled": True})
        self.speech.generation = self.epoch

    def set_visual_spectrum(self, enabled):
        """Change only the playback analyser policy, never a device or worker.

        Remember the renderer's request when Piper has not started yet. The
        shared control bypasses the speech text queue, including mid-phrase.
        """
        if not isinstance(enabled, bool):
            raise ValueError("L'activation du spectre visuel doit être booléenne.")
        if enabled == self.visual_spectrum_requested:
            return True
        self.visual_spectrum_requested = enabled
        if self.speech.alive() and getattr(self.speech, "kind", "speech") == "speech":
            if not self.speech.send({"kind": "visual_spectrum", "enabled": enabled}):
                self._spectrum_diagnostic("Commande de spectre visuel non transmise ; lecture audio maintenue.")
                return False
        return True

    def _spectrum_diagnostic(self, detail):
        """Expose a bounded, deduplicated optional-visual error in diagnostics."""
        detail = str(detail or "")[:512]
        if detail != self.spectrum_diagnostic:
            self.spectrum_diagnostic = detail
            self.record_diagnostic("spectrum_diagnostic", detail or "Analyse spectrale rétablie")

    def submit_phrase(self, phrase):
        if not self.reading:
            return
        if not self.tts_active:
            self.tts_requested_at = time.monotonic()
            self.mark_latency("Premier texte → première phrase TTS", self.first_llm_at, self.tts_requested_at)
            self.prepare_speech()
            self.record_diagnostic("tts_engine", {"ready_before_phrase": self.tts_ready})
            self.tts_active = True
            self.observe_activity("synthesis")
            self.app.stop_button.configure(state="normal")
            self.last_speech = time.monotonic()
            self.app.store.update_message_metadata(self.mid, {"tts_engine": "piper", "voice": self.settings.voice,
                "speech_profile": self.settings.speech_profile, "tts_speed": self.settings.speed,
                "audio_status": "synthesizing"})
            if self.listening and self.settings.acoustic_mode == "speakers":
                if not self.capture.send({"kind": "mute", "value": True}):
                    self.cancel_speech(status="error")
                    self.status.set("Lecture annulée : suspension du microphone impossible.")
                    self.set_mic_state("error", "Suspension du microphone impossible")
                    return
                self.status.set("Lecture haut-parleurs : microphone suspendu")
                self.set_mic_state("suspended", "Lecture haut-parleurs")
        if len(self.pending_phrases) == self.pending_phrases.maxlen:
            self.cancel_speech(status="error")
            self.status.set("Lecture arrêtée : trop de phrases audio en attente (64). Le texte reste enregistré.")
            return
        self.pending_phrases.append(phrase)
        self.submitted_output.append(str(phrase))
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
            if self.source_offset:
                segment = replace(segment, start=segment.start + self.source_offset,
                    end=segment.end + self.source_offset,
                    events=tuple(replace(event, start=event.start + self.source_offset,
                        end=event.end + self.source_offset) for event in segment.events))
            if not self.reading:
                break  # A saturated/cancelled submission invalidates its tail.
            visual_only = getattr(segment, "visual_only", False)
            if not visual_only:
                self.segment_id += 1
            presence = getattr(self.app, "presence", None)
            queue_expressions = getattr(type(presence), "queue_expressions", None)
            if visual_only:
                # A streamed emoji after an already submitted sentence belongs
                # to its visual timeline, never to an empty Piper request.
                if callable(queue_expressions):
                    queue_expressions(presence, self.epoch, self.segment_id,
                                      segment.original, segment.start, segment.end, segment.events)
                continue
            # Keep display/emoji text out of the engine; retain source positions
            # for captions and later PCM-triggered visual events.
            document = parse_text(segment.original)
            display = "".join("Bloc de code non lu. " if "codeblock" in span.tags
                              and not self.settings.speak_code else span.text for span in document.spans)
            if len(display) > 4000:
                stop = max(display.rfind(" ", 0, 3999), display.rfind("\n", 0, 3999), 0)
                display = display[:stop] + "…"
            mode = getattr(getattr(getattr(self.app, "presence", None), "settings", None),
                           "spectrum_mode", "expression")
            if mode not in {"expression", "thematic", "neutral"}:
                mode = "expression"
            prepare_field = getattr(type(presence), "prepare_segment", None)
            if callable(prepare_field):
                events, plan = prepare_field(presence, segment.original, display, segment.start)
            else:
                events = analyze_passages(segment.original, mode=mode, start=segment.start)
                plan = prepare_caption(display, mode=mode)
            if callable(queue_expressions):
                queue_expressions(presence, self.epoch, self.segment_id,
                                  segment.original, segment.start, segment.end, segment.events)
            _label, rate, pause_ms = SPEECH_PROFILES[self.settings.speech_profile]
            if self.tts_profile is not None:
                rate *= self.settings.speed / self.tts_profile.speed
            self.submit_phrase(SpeechText(segment.text, original=segment.original,
                display_text=display, start=segment.start, end=segment.end,
                events=segment.events, segment_id=self.segment_id, response_id=self.epoch,
                spectrum_events=events, spectrum_mode=mode, caption_plan=plan,
                rate=rate, pause_ms=pause_ms))

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
        if had_audio:
            self.echo_until = time.monotonic() + self.settings.resume_delay_ms / 1000
            self.echo_tail_output = tuple(dict.fromkeys((*self.recent_output, *self.submitted_output)))
        if had_audio or not self.listening or status == "error":
            self.speech.stop()
            self.tts_ready = False
        self.tts_active = False
        self.observe_activity("speaking", False)
        self.observe_activity("synthesis", False)
        if had_audio:
            self.observe_activity("error" if status == "error" else "interrupted")
        self._cognitive_segment = None
        self.playing_sample = False
        self.epoch += 1
        self.pending_visuals.clear()
        self.pending_segment_ends.clear()
        self.visual_end_pending = None
        self.pending_phrases.clear()
        self.replay_source = None
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
                if not self.capture.send({"kind": "mute", "value": False}):
                    self.set_mic_state("error", "Reprise du microphone impossible")
                elif self.microphone_state == "suspended":
                    self.set_mic_state("open")
        state = "thinking" if self.app.operation == "chat" else "listening" if self.listening else "silent"
        self.notify_presence(state, signal={"rms": 0.0, "wave": []})

    def _resume_microphone(self, epoch):
        self.resume_id = None
        if self.listening and epoch == self.epoch and not self.tts_active:
            if self.capture.send({"kind": "mute", "value": False}):
                self.set_mic_state("open")
                self.status.set("Écoute locale active")
            else:
                self.set_mic_state("error", "Reprise du microphone impossible")
                self.status.set("Reprise du microphone impossible ; vérifiez le diagnostic audio.")
            if not self.app.operation:
                self.notify_presence("listening")

    def schedule_resume(self):
        if self.resume_id is not None:
            self.app.root.after_cancel(self.resume_id)
        self.resume_id = self.app.root.after(self.settings.resume_delay_ms,
            lambda epoch=self.epoch: self._resume_microphone(epoch))

    def replay_response(self, resume=False):
        """Replay the canonical archive; resume at a DAC-observed segment boundary."""
        if self.app.operation:
            self.status.set("Arrêtez la génération avant de relire sa réponse.")
            return False
        row = self.app.store.message(self.replay_mid) if self.replay_mid is not None else None
        if row is None or row["session_id"] != self.app.session_id or row["role"] != "assistant":
            row = next((item for item in reversed(self.app.store.messages(self.app.session_id))
                        if item["role"] == "assistant" and item["content"].strip()), None)
            self.replay_offset = 0
        if row is None or not row["content"].strip():
            self.status.set("Aucune réponse à relire dans cette conversation.")
            return False
        offset = self.replay_offset if resume and row["id"] == self.replay_mid else 0
        if offset >= len(row["content"]):
            self.status.set("Cette réponse a déjà été lue entièrement ; utilisez Répéter.")
            return False
        self.cancel_speech()
        self.reset_turn_latency()
        begin_observation = getattr(type(self.app), "begin_audio_observation", None)
        if callable(begin_observation):
            self.cognitive_generation = begin_observation(self.app, row["id"])
        self.replay_mid, self.replay_session = row["id"], self.app.session_id
        self.replay_offset = self.source_offset = offset
        self.mid, self.reading, self.segment_id = row["id"], True, 0
        # Establish the loaded engine's base speed before deriving per-segment
        # ratios, including after an interrupted worker and a slower command.
        self.prepare_speech()
        presence = getattr(self.app, "presence", None)
        begin = getattr(type(presence), "begin_response", None)
        if callable(begin):
            begin(presence)
        self.replay_source, self.replay_cursor = row["content"][offset:], 0
        self._feed_replay()
        if self.reading or self.tts_active:
            self.status.set("Reprise au début du segment interrompu (alignement approximatif)." if resume
                            else "Relecture locale de la dernière réponse.")
        return self.reading or self.tts_active

    def _feed_replay(self):
        """Respect worker backpressure instead of queueing a whole long archive."""
        for _ in range(4):
            if self.replay_source is None or not self.reading or len(self.pending_phrases) >= 4:
                return
            end = min(len(self.replay_source), self.replay_cursor + 96)
            chunk = self.replay_source[self.replay_cursor:end]
            self.replay_cursor = end
            final = end == len(self.replay_source)
            self.feed_speech(chunk, final=final)
            if final:
                self.replay_source = None
                if self.tts_active:
                    self.end_pending = True
                else:
                    self.reading, self.mid = False, None
                return

    def handle_command(self, command):
        """Shared explicit-button / recognized-microphone actions; no LLM parsing."""
        try:
            result = self._handle_command(command)
            self.record_diagnostic("voice_command" if result else "voice_command_rejected", command)
            return result
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.halt_without_persistence()
            self.record_diagnostic("voice_command_error", f"{type(exc).__name__}: {exc}")
            self.status.set("Commande vocale impossible ; audio arrêté, archive préservée. " + str(exc)[:240])
            return False

    def _handle_command(self, command):
        if command == "stop":
            if self.app.operation:
                self.app.cancel()
            self.cancel_speech()
            self.status.set("Lecture et génération arrêtées ; écoute conservée.")
        elif command in {"repeat", "resume"}:
            return self.replay_response(resume=command == "resume")
        elif command == "continue":
            if self.app.operation or not self.app.continuation_id:
                self.status.set("Aucune réponse disponible à continuer maintenant.")
                return False
            self.app.continue_response()
        elif command == "slower":
            speed = max(.5, round(self.settings.speed - .1, 2))
            candidate = replace(self.settings, speed=speed).validate()
            self.app.store.set_preference("voice", candidate.to_dict())
            self.settings = candidate
            self.status.set(f"Vitesse Piper : {speed:g}× ; appliquée à la prochaine lecture.")
        elif command == "expand":
            row = self.app.store.message(self.replay_mid) if self.replay_mid is not None else None
            if self.app.operation or row is None or row["session_id"] != self.app.session_id or not row["content"].strip():
                self.status.set("Aucun passage de cette conversation à développer maintenant.")
                return False
            # Reuse the context builder and its recorded provenance/budget.
            excerpt = row["content"][-1500:]
            self.app.send(text="Développe ce passage de ta réponse (extrait original, sans inventer de faits) :\n\n" + excerpt)
        else:
            return False
        return True

    def open_actions(self):
        if self.actions_dialog is not None and self.actions_dialog.winfo_exists():
            self.actions_dialog.lift()
            return self.actions_dialog
        dialog = self.actions_dialog = tk.Toplevel(self.app.root)
        dialog.title("Lecture et commandes vocales")
        dialog.geometry("440x420")
        dialog.minsize(300, 320)
        footer = ttk.Frame(dialog, padding=8)
        footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Fermer", command=dialog.destroy).pack(fill="x")
        viewport = ttk.Frame(dialog)
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, highlightthickness=0, bg="#121c29")
        scroll = ttk.Scrollbar(viewport, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        body = ttk.Frame(canvas, padding=12)
        item = canvas.create_window(0, 0, window=body, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        def reveal(event):
            if not str(event.widget).startswith(str(body) + "."):
                return
            y = event.widget.winfo_rooty() - body.winfo_rooty()
            bottom = y + event.widget.winfo_height()
            if y < canvas.canvasy(0) or bottom > canvas.canvasy(0) + canvas.winfo_height():
                canvas.yview_moveto(max(0, bottom - canvas.winfo_height()) / max(1, body.winfo_height()))
        dialog.bind("<FocusIn>", reveal, add="+")
        dialog.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-3 if event.delta > 0 else 3, "units"))
        ttk.Label(body, text="Commandes seules : Stop, Répète, Reprends, Continue,\nPlus lentement, Développe ce passage.", wraplength=270).pack(fill="x", pady=4)
        ttk.Label(body, text="Casque pour interrompre par la voix. En mode haut-parleurs, le micro reste suspendu pendant la lecture. La reprise peut répéter le segment interrompu.", wraplength=270).pack(fill="x", pady=4)
        dialog.controls = {}
        for command, label in (("stop", "Stop"), ("repeat", "Répéter"), ("resume", "Reprendre la lecture"),
                               ("continue", "Continuer la réponse"), ("slower", "Plus lentement"),
                               ("expand", "Développer ce passage")):
            button = ttk.Button(body, name=command, text=label, command=lambda key=command: self.handle_command(key))
            button.pack(fill="x", pady=2)
            dialog.controls[command] = button
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        return dialog

    def _response_owns_visuals(self):
        # Only speech_start is a new user interruption. A late STT status for
        # the question being answered must not close its prepared visual epoch.
        presence = getattr(self.app, "presence", None)
        final_expression = getattr(getattr(presence, "semantic", None), "active", False) is True
        return (self.reading or self.tts_active or bool(self.pending_visuals)
                or bool(self.pending_segment_ends) or self.visual_end_pending is not None
                or final_expression)

    def poll(self):
        now = time.monotonic()
        for event in self.capture.poll():
            if not self.listening:
                continue  # Queued notifications cannot reactivate a stopped microphone.
            self.last_capture = now
            self.last_capture_event, self.last_capture_event_at = event.kind, now
            if event.kind in {"diagnostic", "capture_stage"}:
                self.diagnostics.update(event.payload)
                if event.payload.get("last_frame_at") is not None:
                    self.last_pcm_at = event.payload["last_frame_at"]
                if event.kind == "capture_stage":
                    if not self._response_owns_visuals():
                        self.status.set(str(event.payload.get("stage", "Initialisation audio locale…")))
                    self.record_diagnostic(event.kind, event.payload)
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
                if event.kind == "capture_error":
                    self.diagnostics.update(event.payload)
                    self.diagnostic_failure = "Capture : " + str(event.payload.get("error", "Capture indisponible"))
                    self.set_mic_state("error", event.payload.get("error", "Capture indisponible"))
                if event.generation == self.heard:
                    if event.kind == "turn_end":
                        self.turn_ended_at = event.payload.get("ended_at")
                        if "silence_ms" in event.payload:
                            self.set_latency("Silence de fin de tour (PCM)", event.payload["silence_ms"])
                    elif event.kind == "stt_complete":
                        self.transcribing = False
                        if self.listening and self.microphone_state != "suspended":
                            self.set_mic_state("open")
                        self.stt_details = event.payload
                        self.stt_latency(event.payload)
                    elif event.kind == "stt_superseded":
                        self.transcribing = False
                        if self.listening and self.microphone_state != "suspended":
                            self.set_mic_state("open")
            elif event.kind == "stt_error":
                self.record_diagnostic(event.kind, event.payload)
                if event.generation == self.heard:
                    self.transcribing = False
                    self.diagnostic_failure = "STT : " + str(event.payload.get("error", "Transcription impossible"))
                    self.stt_latency(event.payload)
                    self.status.set("Échec STT ; écoute maintenue. Détails dans Diagnostic micro / STT.")
                    if self._response_owns_visuals():
                        self.record_diagnostic("stt_visual_ignored", "response_active; no speech_start")
                    else:
                        if self.listening:
                            self.set_mic_state("error", "STT ; écoute maintenue : " + str(event.payload.get("error", "")))
                        if not self.app.operation:
                            self.notify_presence("listening")
            elif event.kind == "speech_start":
                if self.microphone_state == "suspended" or event.generation <= self.heard:
                    continue
                self.record_diagnostic(event.kind, {"tour": event.generation})
                self.confirmed_turn = event.generation
                self.echo_turn_output = tuple(dict.fromkeys((*self.recent_output, *self.submitted_output))) if self.tts_active else (
                    tuple(self.echo_tail_output or self.recent_output) if self.pending_visuals or now < self.echo_until else ())
                self.heard = event.generation
                self.cancel_speech()
                self.transcribing = False
                self.reset_turn_latency()
                self.stt_details = {}
                self.reference_result = ""
                if self.app.operation == "chat":
                    self.app.cancel()
                self.status.set("Voix détectée")
                if self.listening:
                    self.set_mic_state("voice")
                self.notify_presence("user_speaking")
            elif event.kind in {"transcribing", "stt_queued"}:
                self.record_diagnostic(event.kind, {"tour": event.generation})
                if event.generation == self.heard:
                    if self._response_owns_visuals():
                        self.record_diagnostic("stt_visual_ignored", "response_active; no speech_start")
                        continue
                    self.transcribing = True
                    self.status.set("Transcription française locale…" if event.kind == "transcribing"
                                    else "Tour vocal conservé ; attente du STT local…")
                    if self.listening:
                        self.set_mic_state("stt", "Transcription locale" if event.kind == "transcribing" else "Attente du STT local")
                    self.notify_presence("thinking")
            elif event.kind == "transcript" and event.generation == self.heard:
                if self.transcript_handled == event.generation:
                    self.record_diagnostic("transcript_ignored", "Tour déjà traité")
                    continue
                self.transcript_handled = event.generation
                self.record_diagnostic("transcript", str(event.payload)[:2000])
                self.transcribing = False
                if self.listening and self.microphone_state != "suspended":
                    self.set_mic_state("open")
                text = event.payload.strip()
                if self.microphone_state == "suspended":
                    self.record_diagnostic("voice_command_ignored", "Microphone suspendu : transcription tardive écartée")
                    continue
                command = recognize_command(text, confirmed_user_turn=event.generation == self.confirmed_turn)
                self.confirmed_turn = None
                if command and command_echo(text, self.echo_turn_output):
                    self.record_diagnostic("voice_command_ignored", "Commande présente dans la propre lecture ; écho possible")
                    self.status.set("Commande écartée : écho possible de JARVIS. Réessayez après la lecture.")
                    continue
                if command:
                    self.handle_command(command)
                elif text and not self.app.operation:
                    self.app.send(source="voice", text=text)
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
                if (self.microphone_state == "suspended" or event.generation < self.heard
                        or event.generation > self.heard and event.payload.get("speaking")):
                    continue
                # A speech_start discarded during suspension may have advanced
                # the worker epoch. Quiet PCM after resume is still observable,
                # without accepting that discarded turn's speech or transcript.
                self.last_pcm_at = event.payload.get("captured_at", now)
                if self.listening and not self.transcribing and self.microphone_state != "suspended":
                    self.set_mic_state("voice" if event.payload.get("speaking") else "open")
                if event.payload.get("speaking"):
                    self.notify_presence("user_speaking", signal=event.payload)
                elif self.listening and not self.transcribing and not self.app.operation and not self.tts_active:
                    self.notify_presence("listening", signal=event.payload)
            elif event.kind == "listening":
                if event.payload:
                    self.diagnostics.update(event.payload)
                    self.record_diagnostic("capture_ready", event.payload)
                if self.microphone_state != "suspended":
                    self.status.set("Écoute locale active")
                if self.listening and self.microphone_state != "suspended":
                    self.set_mic_state("open")
                if not self._response_owns_visuals():
                    self.notify_presence("listening")
            elif event.kind == "error":
                if not self.diagnostic_failure:
                    self.diagnostic_failure = str(event.payload)
                self.stop_listening()
                self.status.set(str(event.payload))
                self.set_mic_state("error", event.payload)
            elif event.kind == "warning":
                self.status.set(str(event.payload))
        if self.listening and not self.capture.alive() and now - self.last_capture > 0.5:
            self.diagnostic_failure = self.diagnostic_failure or "Processus micro arrêté sans notification ; réactivez l’écoute après vérification audio."
            self.stop_listening()
            self.status.set("Processus micro arrêté. Réactivez l’écoute après vérification audio.")
            self.set_mic_state("error", "Processus micro arrêté")
        for event in self.speech.poll():
            self.last_speech = now
            if event.kind == "tts_ready":
                self.tts_ready = True
                if not self.tts_active:
                    self.observe_activity("synthesis", False)
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
                if view.get("spectrum_error"):
                    self._spectrum_diagnostic(view["spectrum_error"])
                elif view.get("spectrum_status") == "ready":
                    self._spectrum_diagnostic("")
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
            elif event.kind == "spectrum_diagnostic":
                self._spectrum_diagnostic(event.payload)
            elif event.kind == "segment_done":
                # Keep this boundary behind every preceding DAC-timed callback.
                # No audio waits for the UI; only the visual notification does.
                due = max(now, event.payload.get("completed_at", now),
                          max((due for due, _view, epoch in self.pending_visuals
                               if epoch == self.epoch), default=now))
                self.pending_segment_ends.append((due, event.payload, self.epoch))
                self.pending_segment_ends = self.pending_segment_ends[-64:]
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
                self.status.set("Lecture terminée")
                self.echo_until = now + self.settings.resume_delay_ms / 1000
                self.echo_tail_output = tuple(dict.fromkeys((*self.recent_output, *self.submitted_output)))
                if self.listening:
                    self.schedule_resume()
                self.visual_end_pending = (self.epoch, "listening" if self.listening else "silent")
            elif event.kind == "error":
                self.cancel_speech(status="error")
                self.status.set(str(event.payload))
        self._drain_visuals(now)
        self._feed_replay()
        self.drain_phrases()
        if self.end_pending and not self.pending_phrases and self.speech.send(None):
            self.end_pending = False
        if self.speech.process is not None and not self.speech.alive() and now - self.last_speech > 0.5:
            self.cancel_speech(status="error")
            self.status.set("Processus de lecture arrêté ; texte conservé.")
        # Ages must advance even when a worker stops emitting notifications.
        if now < self._diagnostic_refreshed_at or now - self._diagnostic_refreshed_at >= .25:
            self.refresh_diagnostics()

    def _drain_visuals(self, now):
        """Deliver final PCM, segment boundaries, then the final functional state."""
        for due, view, epoch in self.pending_visuals[:]:
            if due <= now:
                if epoch == self.epoch:
                    self._cognitive_segment = (epoch, view.get("segment_id"))
                    self.observe_activity("synthesis", False)
                    self.observe_activity("speaking")
                    self.replay_offset = int(view.get("original_start", self.replay_offset))
                    spoken = view.get("spoken_text", view.get("text", ""))
                    if spoken and (not self.recent_output or self.recent_output[-1] != spoken):
                        self.recent_output.append(spoken)
                    self.notify_presence("jarvis_speaking", signal=view, caption=view)
                self.pending_visuals.remove((due, view, epoch))
        for due, payload, epoch in self.pending_segment_ends[:]:
            if due <= now:
                if epoch == self.epoch:
                    if getattr(self, "_cognitive_segment", None) == (epoch, payload.get("segment_id")):
                        self.observe_activity("speaking", False)
                        self.observe_activity("synthesis", self.tts_active)
                    self.replay_offset = int(payload.get("original_end", self.replay_offset))
                    presence = getattr(self.app, "presence", None)
                    complete = getattr(type(presence), "complete_segment", None)
                    if callable(complete):
                        complete(presence, payload)
                self.pending_segment_ends.remove((due, payload, epoch))
        if self.visual_end_pending is not None and not self.pending_visuals and not self.pending_segment_ends:
            epoch, state = self.visual_end_pending
            self.visual_end_pending = None
            if epoch == self.epoch:
                self.observe_activity("speaking", False)
                self.observe_activity("synthesis", False)
                self.notify_presence(state)

    def record_diagnostic(self, kind, payload):
        stamp = time.strftime("%H:%M:%S")
        self.diagnostic_events.append(f"{stamp} · {kind} · {payload}")
        if kind in {"stt_error", "capture_error", "voice_command_error"}:
            self.observe_activity("error", response=False)
        self.refresh_diagnostics()

    def reset_turn_latency(self):
        self.latencies = {}
        self.turn_ended_at = self.llm_started_at = self.first_llm_at = None
        self.tts_requested_at = self.first_pcm_at = None
        self.publish_timing(new_turn=True)

    def set_latency(self, label, milliseconds):
        self.latencies[label] = max(0, round(milliseconds))
        key = {"Whisper : transcription": "stt_ms", "Silence de fin de tour (PCM)": "silence_ms",
               "Piper : synthèse du premier bloc": "piper_ms",
               "Phrase TTS → premier PCM (DAC estimé)": "tts_first_pcm_ms",
               "Fin de tour détectée → premier PCM (DAC estimé)": "end_to_pcm_estimate_ms"}.get(label)
        if key:
            self.observe_activity(metrics={key: self.latencies[label]})
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

    def capture_assessment(self, now):
        """Describe the observed boundary, without inferring hardware success."""
        values = self.diagnostics
        if not self.listening:
            return self.status.get()
        if self.microphone_state == "suspended":
            return "Capture suspendue pendant la lecture ; reprise après la sortie audio."
        if values.get("capture_status") in {"loading_stt", "loading_vad", "opening_microphone"}:
            return str(values.get("stage", "Initialisation locale en cours")) + " ; microphone pas encore confirmé ouvert."
        if self.last_pcm_at is None:
            return "Aucune trame PCM reçue. Vérifiez le micro réellement ouvert, Confidentialité > Microphone Windows et le périphérique MME/WASAPI sélectionné."
        if now - self.last_pcm_at > 1.0:
            return "PCM interrompu ou ancien. Vérifiez le périphérique, les erreurs PortAudio et réactivez l’écoute."
        if self.transcribing:
            return "Voix transmise à Whisper ; transcription locale en cours ou en attente du STT."
        if self.microphone_state == "voice":
            return "Voix détectée ; attente de fin de tour. Après un vrai silence, vérifiez fin de tour puis STT dans la trace."
        if self.app.operation == "chat":
            return "Génération Ollama en cours ; le microphone reste diagnostiqué séparément."
        if self.stt_details.get("result"):
            return "Transcription reçue. Si aucune réponse : vérifiez le modèle Ollama, le message d’état et la saisie conservée."
        if values.get("rms") == 0:
            return "Microphone ouvert, PCM nul. Vérifiez mute matériel, niveau d’entrée Windows et autorisations."
        return "Signal PCM reçu sans parole VAD confirmée. Parlez puis comparez RMS, probabilité VAD et trace ; aucun seuil n’est modifié automatiquement."

    def refresh_diagnostics(self):
        if self.diagnostic_window is None or not self.diagnostic_window.winfo_exists():
            return
        now = time.monotonic()
        self._diagnostic_refreshed_at = now
        values = self.diagnostics
        probability = values.get("vad")
        rms = values.get("rms")
        fresh_pcm = self.last_pcm_at is not None and now - self.last_pcm_at <= 1.0
        rms_text = f"{rms:.5f}" if rms is not None and math.isfinite(rms) else "—"
        vad_text = f"{probability:.3f}" if probability is not None else "—"
        pcm_age = f"{max(0, now - self.last_pcm_at):.1f} s" if self.last_pcm_at is not None else "aucune trame"
        event_age = f"{max(0, now - self.last_capture_event_at):.1f} s" if self.last_capture_event_at is not None else "—"
        opened = values.get("opened_device")
        opened_text = (f"{opened.get('name', '—')} · {opened.get('hostapi', '—')} · index {opened.get('index', '—')}"
                       if opened else "non confirmé")
        selected = values.get("selected_device", self.settings.input_device or "Par défaut Windows")
        measurements = (f"RMS micro : {rms_text}   |   Probabilité VAD : {vad_text}"
                + f"\nÉtat : {values.get('state', 'en attente')}   |   Tour : {values.get('turn_seconds', 0):.2f} s"
                + f"\nPCM : {values.get('native_rate', '—')} → {values.get('rate', '—')} Hz ; trames : {values.get('frame_samples', '—')}"
                + f"\nDernière fin : {values.get('end_reason', '') or 'aucune'}")
        if "silence_target_ms" in values:
            measurements += (f"\nSilence PCM : {values.get('silence_elapsed_ms', 0)} / {values['silence_target_ms']} ms"
                + f" ; reprise candidate : {'oui' if values.get('resume_pending') else 'non'}"
                + f" ; début confirmé : {values.get('onset_ms', 160)} ms")
        self.diagnostic_summary.set(
            f"Sélectionné : {selected}\nOuvert : {opened_text}"
            + f"\nRMS : {rms_text}{' (ancien)' if rms is not None and not fresh_pcm else ''} · VAD : {vad_text}"
            + f" · PCM : {pcm_age} · Dernier événement : {self.last_capture_event} ({event_age})"
            + f"\n{self.capture_assessment(now)}"
            + (f"\nDernière erreur conservée : {self.diagnostic_failure}" if self.diagnostic_failure else ""))
        meter_value = max(0., min(80., 80 + 20 * math.log10(rms))) if fresh_pcm and rms is not None and rms > 0 else 0.
        self.rms_meter.configure(value=meter_value)
        self.rms_meter.state(["!disabled"] if fresh_pcm and rms is not None else ["disabled"])
        presence = getattr(self.app, "presence", None)
        semantic = getattr(type(presence), "semantic_diagnostics", None)
        semantic_text = semantic(presence) if callable(semantic) else "Semantic Morphing indisponible"
        text = (measurements
                + f"\nCapture : {values.get('capture_status', '—')} ; étape : {values.get('stage', '—')}"
                + f"\nTrames 16 kHz reçues : {values.get('frames_received', '—')} ; trames natives : {values.get('native_frames_received', '—')}"
                + f"\nPortAudio : {values.get('callback_status') or 'aucun statut signalé'} ; pertes PCM : {values.get('dropped_frames', 0)} ; événements perdus : {values.get('event_drops', 0)}"
                + f"\nDernière erreur conservée : {self.diagnostic_failure or 'aucune'}"
                + f"\nSTT : {values.get('last_stt', 'en attente')}\n\n"
                + "Latences du dernier tour (ms) :\n"
                + ("\n".join(f"{label} : {value}" for label, value in self.latencies.items()) or "En attente de mesures")
                + "\nDAC estimé par PortAudio ; délai acoustique/Bluetooth non mesuré.\n\n"
                + f"STT conservé : {self.stt_details.get('result', '—')}\n"
                + f"STT brut : {self.stt_details.get('raw_result', '—')}\n"
                + f"Langue demandée : {self.stt_details.get('language_requested', '—')} ; segments écartés : {self.stt_details.get('discarded_segments', '—')}\n"
                + (f"Qualité du dernier WAV : {self.last_sample.get('quality', {})} ; fin : {self.last_sample.get('end_reason', '—')}\n" if self.last_sample else "")
                + self.reference_result + "\n\n"
                + semantic_text + "\n\n"
                + "\n".join(self.diagnostic_events))
        if text != self._diagnostic_body:
            position = self.diagnostic_text.yview()[0]
            selection = self.diagnostic_text.tag_ranges("sel")
            self.diagnostic_text.configure(state="normal")
            self.diagnostic_text.delete("1.0", "end")
            self.diagnostic_text.insert("1.0", text)
            if selection:
                self.diagnostic_text.tag_add("sel", *selection)
            self.diagnostic_text.configure(state="disabled")
            self.diagnostic_text.yview_moveto(position)
            self._diagnostic_body = text

    def copy_diagnostics(self):
        self.refresh_diagnostics()
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(self._diagnostic_body or "Aucun diagnostic disponible")

    def open_diagnostics(self):
        if self.diagnostic_window is not None and self.diagnostic_window.winfo_exists():
            self.diagnostic_window.lift()
            return
        dialog = self.diagnostic_window = tk.Toplevel(self.app.root)
        dialog.title("Diagnostic local · micro → VAD → STT")
        dialog.geometry("820x670")
        dialog.configure(bg="#121c29", padx=12, pady=12)
        intro = tk.Frame(dialog, bg="#121c29")
        intro.pack(fill="x")
        tk.Label(intro, text="Mesures réelles, actualisées 4 fois/s. Trace en mémoire ; WAV uniquement sur demande explicite. Aucun envoi réseau.",
                 bg="#121c29", fg="#e4edf6", wraplength=600, justify="left").pack(side="left", fill="x", expand=True)
        ttk.Button(intro, text="Copier le diagnostic", command=self.copy_diagnostics).pack(side="right", padx=(8, 0))
        self.diagnostic_summary = tk.StringVar()
        summary = tk.Label(dialog, textvariable=self.diagnostic_summary, bg="#121c29", fg="#e4edf6",
                           justify="left", anchor="w", wraplength=780)
        summary.pack(fill="x", pady=5)
        summary.bind("<Configure>", lambda event: summary.configure(wraplength=max(200, event.width)))
        tk.Label(dialog, text="Vu-mètre PCM RMS logarithmique : −80 à 0 dBFS (— = aucune mesure actuelle)",
                 bg="#121c29", fg="#a6b8cb", anchor="w").pack(fill="x")
        self.rms_meter = ttk.Progressbar(dialog, maximum=80, mode="determinate")
        self.rms_meter.pack(fill="x", pady=3)
        from tkinter.scrolledtext import ScrolledText
        self.diagnostic_text = ScrolledText(dialog, wrap="word", bg="#0b1019", fg="#e4edf6", height=14)
        self.diagnostic_text.pack(fill="both", expand=True, pady=8)
        self._diagnostic_body = None
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
        begin_observation = getattr(type(self.app), "begin_audio_observation", None)
        if callable(begin_observation):
            self.cognitive_generation = begin_observation(self.app)
        self.playing_sample = self.tts_active = True
        self.tts_ready = False
        self.tts_profile = None
        if self.listening and not self.capture.send({"kind": "mute", "value": True}):
            self.cancel_speech(status="error")
            self.status.set("Réécoute annulée : suspension du microphone impossible.")
            self.set_mic_state("error", "Suspension du microphone impossible")
            return
        if self.listening:
            self.set_mic_state("suspended", "Réécoute du PCM demandé")
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
        begin_observation = getattr(type(self.app), "begin_audio_observation", None)
        if callable(begin_observation):
            self.cognitive_generation = begin_observation(self.app)
        self.reset_turn_latency()
        self.tts_requested_at = time.monotonic()
        self.prepare_speech()
        self.tts_active = True
        self.app.stop_button.configure(state="normal")
        self.last_speech = time.monotonic()
        if self.listening and self.settings.acoustic_mode == "speakers":
            if self.capture.send({"kind": "mute", "value": True}):
                self.set_mic_state("suspended", "Aperçu vocal haut-parleurs")
            else:
                self.set_mic_state("error", "Suspension du microphone impossible")
                self.cancel_speech(status="error")
                self.status.set("Aperçu annulé : suspension du microphone impossible.")
                return
        _label, rate, pause_ms = SPEECH_PROFILES[self.settings.speech_profile]
        rate *= self.settings.speed / self.tts_profile.speed
        if not self.speech.send(SpeechText("Bonjour. Je suis JARVIS. Voici un aperçu de ma voix française.",
                                         rate=rate, pause_ms=pause_ms)):
            self.cancel_speech(status="error")
            self.status.set("Aperçu non transmis ; réessayez.")
            return
        self.end_pending = True

    def open_settings(self, focus_key=None):
        """One scrollable editor; the profile remains the sole saved voice state."""
        existing = getattr(self, "settings_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            if focus_key is not None:
                existing.focus_control(focus_key)
            return existing
        if self.listening or self.app.operation:
            messagebox.showinfo("Voix", "Désactivez l’écoute et terminez la génération avant de changer les périphériques.", parent=self.app.root)
            return
        from .audio import device_inventory
        try:
            devices = device_inventory()
        except Exception as exc:
            devices = {"input": [], "output": []}
            self.status.set(audio_error(exc))
        dialog = self.settings_dialog = tk.Toplevel(self.app.root)
        dialog.title("Voix locale · microphone désactivé")
        dialog.configure(bg="#121c29", padx=14, pady=12)
        dialog.transient(self.app.root)
        width = min(660, max(280, dialog.winfo_screenwidth() - 60))
        height = min(720, max(300, dialog.winfo_screenheight() - 100))
        dialog.geometry(f"{width}x{height}")
        dialog.minsize(280, 280)
        dialog.grab_set()
        footer = ttk.Frame(dialog)
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        body = tk.Frame(dialog, bg="#121c29")
        body.pack(fill="both", expand=True)
        canvas = dialog.settings_canvas = tk.Canvas(body, bg="#121c29", highlightthickness=0)
        scroll = ttk.Scrollbar(body, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        content = tk.Frame(canvas, bg="#121c29", padx=2)
        item = canvas.create_window(0, 0, anchor="nw", window=content)
        labels = []

        def note(parent, text, muted=False):
            label = tk.Label(parent, text=text, bg="#121c29", fg="#a6b8cb" if muted else "#e4edf6",
                             justify="left", anchor="w", wraplength=width - 65)
            label.pack(fill="x", pady=(7, 3))
            labels.append(label)
            return label

        def resize(event):
            canvas.itemconfigure(item, width=event.width)
            for label in labels:
                label.configure(wraplength=max(100, event.width - 12))

        canvas.bind("<Configure>", resize)
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))

        def reveal(widget):
            if not str(widget).startswith(str(content) + ".") or not widget.winfo_viewable():
                return
            y = widget.winfo_rooty() - content.winfo_rooty()
            bottom = y + widget.winfo_height()
            top = canvas.canvasy(0)
            if y < top or bottom > top + canvas.winfo_height():
                canvas.yview_moveto(max(0, bottom - canvas.winfo_height()) / max(1, content.winfo_height()))

        dialog.bind("<FocusIn>", lambda event: reveal(event.widget), add="+")

        def wheel(event):
            if str(event.widget).startswith(str(content)) and not isinstance(event.widget, ttk.Combobox):
                direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
                canvas.yview_scroll(direction * 3, "units")
                return "break"

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            dialog.bind(sequence, wheel, add="+")
        values, controls = {}, {}
        dialog.controls = controls
        options = {"input_device": [""] + [d["key"] for d in devices["input"]],
                   "output_device": [""] + [d["key"] for d in devices["output"]],
                   "voice": list(VOICES), "acoustic_mode": ["speakers", "headphones"],
                   "speech_profile": [profile[0] for profile in SPEECH_PROFILES.values()],
                   "personality": ["Personnalisé", *PERSONALITY_PROMPTS]}
        fields = [("input_device", "Microphone (vide = défaut Windows)"), ("output_device", "Sortie audio (vide = défaut Windows)"),
                  ("voice", "Voix : Tom homme / Siwis femme"), ("speed", "Vitesse (0.5–2)"),
                  ("speech_profile", "Profil de lecture (rythme et pauses Piper)"),
                  ("acoustic_mode", "speakers = haut-parleurs / headphones = casque"),
                  ("silence_ms", "Silence de fin de tour (300–2500 ms)"), ("models_dir", "Dossier modèles (vide = profil local)"),
                  ("personality", "Profil (changer remplace l’instruction système)")]
        def field(parent, key, label):
            note(parent, label)
            value = SPEECH_PROFILES[self.settings.speech_profile][0] if key == "speech_profile" else str(getattr(self.settings, key))
            values[key] = tk.StringVar(dialog, value=value)
            if key in options:
                widget = ttk.Combobox(parent, name=key, textvariable=values[key], values=options[key], state="readonly", width=1)
            else:
                widget = ttk.Entry(parent, name=key, textvariable=values[key], width=1)
            widget.pack(fill="x", pady=(0, 4))
            controls[key] = widget

        for key, label in fields:
            field(content, key, label)
        ttk.Button(content, text="Choisir dossier…", command=lambda: values["models_dir"].set(filedialog.askdirectory(parent=dialog) or values["models_dir"].get())).pack(fill="x", pady=4)
        speak_code = tk.BooleanVar(dialog, value=self.settings.speak_code)
        controls["speak_code"] = ttk.Checkbutton(content, name="speak_code", text="Lire les blocs de code", variable=speak_code)
        controls["speak_code"].pack(anchor="w", pady=(10, 0))
        note(content, "Sinon, la voix annonce « Bloc de code non lu ».", muted=True)
        advanced = tk.Frame(content, bg="#121c29")
        advanced_open = False

        def toggle_advanced(opened=None):
            nonlocal advanced_open
            advanced_open = not advanced_open if opened is None else bool(opened)
            advanced_button.configure(text=("▾" if advanced_open else "▸") + " Réglages avancés")
            if advanced_open:
                advanced.pack(fill="x", after=advanced_button)
            else:
                advanced.pack_forget()

        advanced_button = ttk.Button(content, name="advanced", text="▸ Réglages avancés", command=toggle_advanced)
        advanced_button.pack(fill="x", pady=(12, 4))
        field(advanced, "vad_threshold", "Seuil de détection vocale (0.3–0.95)")
        note(advanced, "Valeur conservée tant que vous ne la changez pas. Un seuil plus bas peut détecter davantage de bruit ; consultez le diagnostic avant de l’ajuster.", muted=True)
        field(advanced, "cpu_threads", "Threads CPU audio (1–8)")
        field(advanced, "resume_delay_ms", "Reprise micro après lecture (100–1500 ms)")
        note(advanced, "350 ms par défaut. Ce délai laisse retomber le son des haut-parleurs ; il ne mesure pas le délai acoustique Bluetooth. Aucun AEC annoncé.", muted=True)
        note(advanced, "Un nombre élevé peut concurrencer les autres traitements locaux. Ce réglage ne change pas le moteur vocal.", muted=True)

        def focus_control(key):
            widget = controls.get(key)
            if widget is None:
                return False
            if key in {"vad_threshold", "cpu_threads", "resume_delay_ms"}:
                toggle_advanced(True)
            dialog.update_idletasks()
            widget.focus_set()
            reveal(widget)
            return True

        dialog.focus_control = focus_control

        def save(close=True):
            try:
                candidate = replace(self.settings, **{k: v.get() for k, v in values.items() if k not in {"speed", "silence_ms", "vad_threshold", "cpu_threads", "resume_delay_ms", "speech_profile"}},
                                    speed=float(values["speed"].get()), silence_ms=int(values["silence_ms"].get()),
                                    vad_threshold=float(values["vad_threshold"].get()), cpu_threads=int(values["cpu_threads"].get()),
                                    resume_delay_ms=int(values["resume_delay_ms"].get()),
                                    speech_profile=next((key for key, profile in SPEECH_PROFILES.items() if profile[0] == values["speech_profile"].get()), None),
                                    speak_code=speak_code.get()).validate()
                if candidate.personality != self.settings.personality and candidate.personality in PERSONALITY_PROMPTS:
                    model_settings = replace(self.app.settings, system_prompt=PERSONALITY_PROMPTS[candidate.personality])
                    self.app.store.save_settings(model_settings)
                    self.app.settings = model_settings
                self.app.store.set_preference("voice", candidate.to_dict())
                self.cancel_speech()
                self.settings = candidate
            except (ValueError, OSError, sqlite3.Error, tk.TclError) as exc:
                messagebox.showerror("Voix", str(exc), parent=dialog)
                return
            if close:
                dialog.destroy()
            else:
                self.preview()

        note(content, "Modèles à installer séparément (guide docs/VOICE.md). Aucun téléchargement automatique.\nCasque requis pour interrompre par la voix pendant la lecture. Aucun AEC haut-parleurs annoncé.", muted=True)
        note(content, "La préécoute réelle enregistre d’abord vos réglages, puis utilise Piper local.", muted=True)
        ttk.Button(content, name="preview_voice", text="Préécoute réelle", command=lambda: save(False)).pack(fill="x", pady=8)
        dialog.save_button = ttk.Button(footer, name="save_voice", text="Enregistrer", command=save)
        dialog.save_button.pack(fill="x", pady=(0, 4))
        dialog.cancel_button = ttk.Button(footer, name="cancel_voice", text="Annuler", command=dialog.destroy)
        dialog.cancel_button.pack(fill="x")

        def closed(event):
            if event.widget is dialog:
                self.settings_dialog = None

        dialog.bind("<Destroy>", closed, add="+")
        dialog.bind("<Escape>", lambda _event: (dialog.destroy(), "break")[-1])
        dialog.bind("<Control-s>", lambda _event: (save(), "break")[-1])
        if focus_key is not None:
            focus_control(focus_key)
        return dialog
