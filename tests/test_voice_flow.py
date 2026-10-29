"""Voice contracts: simulated audio events, real Tk/SQLite and HTTP LLM fixture.

These tests do not validate a microphone, audible playback, or model inference.
"""
import gc
import json
import queue
import tempfile
import time
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.audio import AudioEvent
from jarvis.config import Settings
from jarvis.presence import PresenceView
from jarvis.storage import Store
from jarvis.ui import App
from jarvis.voice_runtime import AudioProcess, emit_event
from tests.test_jarvis import Fixture, display_available


class SimulatedAudioProcess:
    """Only the process/event interface is simulated; no fake audio is emitted."""
    def __init__(self):
        self.process = None
        self.events = []
        self.commands = []
        self.starts = []
        self.stops = 0
        self.accept_commands = True

    def start(self, kind, settings, generation=0):
        self.stop()
        self.process = object()
        self.starts.append((kind, settings, generation))

    def stop(self):
        self.process = None
        self.events.clear()
        self.stops += 1

    def send(self, command):
        if self.process is None or not self.accept_commands:
            return False
        self.commands.append(command)
        return True

    def poll(self):
        events, self.events = self.events, []
        return events

    def alive(self):
        return self.process is not None


class SemanticPresenceRecorder:
    """Record optional semantic hooks without a graphics or audio engine."""
    state = "silent"

    def __init__(self):
        self.events, self.queued = [], []

    def update_event(self, state, signal=None, caption=None):
        self.state = state
        self.events.append((state, caption))

    def queue_expressions(self, *args):
        self.queued.append(args)

    def complete_segment(self, payload):
        self.events.append(("segment_done", payload))

    def update_microphone(self, state, detail=""):
        pass

    def update_timing(self, *args, **kwargs):
        pass

    def close(self):
        pass


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class VoiceFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audio_patch = patch("jarvis.voice_ui.AudioProcess", SimulatedAudioProcess)
        self.audio_patch.start()
        self.addCleanup(self.audio_patch.stop)
        self.store = Store(Path(self.temp.name) / "voice.sqlite3")
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.addCleanup(self.close_app)
        self.voice = self.app.voice
        self.app.presence = Mock()

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.voice = self.app = self.root = self.store = None
        # Finalize Tk cycles here, before a later HTTP fixture starts threads.
        gc.collect()

    def pump_until(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(predicate(), self.app.status.get() + " / " + self.voice.status.get())

    def activate(self, acoustic_mode="speakers"):
        self.voice.settings = replace(self.voice.settings, acoustic_mode=acoustic_mode)
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=True) as permission:
            self.voice.toggle()
        permission.assert_called_once()
        self.assertTrue(self.voice.listening)

    def begin_simulated_audio_turn(self):
        mid = self.store.begin_turn(self.app.session_id, "Question vocale", "local", source="voice",
                                    metadata={"final_transcript": "Question vocale"})
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk("Voici une phrase complète.")
        self.assertTrue(self.voice.speech.alive())
        return mid

    def semantic_playback(self, *, delay=0):
        recorder = self.app.presence = SemanticPresenceRecorder()
        self.activate("headphones")
        self.begin_simulated_audio_turn()
        recorder.events.clear()
        epoch = self.voice.epoch
        payload = {"text": "Voici une phrase complète.", "response_id": epoch, "segment_id": 1,
                   "fraction": 1, "rms": .1, "wave": [.1, -.1],
                   "emitted_at": 10.0, "delay": delay, "started_at": 10.0 + delay}
        self.voice.speech.events.extend([
            AudioEvent("played", payload, epoch),
            AudioEvent("segment_done", {**payload, "completed_at": 10.0}, epoch),
            AudioEvent("speech_done", generation=epoch),
        ])
        return recorder, epoch

    def test_final_pcm_is_delivered_before_segment_completion_and_final_state(self):
        recorder, epoch = self.semantic_playback()
        with patch("jarvis.voice_ui.time.monotonic", return_value=10.1):
            self.voice.poll()
        self.assertEqual([kind for kind, _ in recorder.events],
                         ["jarvis_speaking", "segment_done", "listening"])
        self.assertEqual(recorder.events[1][1]["response_id"], epoch)
        self.assertFalse(self.voice.pending_visuals)
        self.assertFalse(self.voice.pending_segment_ends)
        self.assertIsNone(self.voice.visual_end_pending)
        self.assertFalse(self.voice.tts_active)

    def test_dac_delay_defers_only_visual_completion_without_delaying_audio_finish(self):
        recorder, epoch = self.semantic_playback(delay=2)
        with patch("jarvis.voice_ui.time.monotonic", return_value=10.1):
            self.voice.poll()
        self.assertEqual(recorder.events, [])
        self.assertFalse(self.voice.tts_active)
        self.assertFalse(self.voice.reading)
        self.assertEqual(self.voice.visual_end_pending, (epoch, "listening"))
        self.assertEqual(len(self.voice.pending_visuals), 1)
        self.assertEqual(len(self.voice.pending_segment_ends), 1)
        with patch("jarvis.voice_ui.time.monotonic", return_value=12.1):
            self.voice.poll()
        self.assertEqual([kind for kind, _ in recorder.events],
                         ["jarvis_speaking", "segment_done", "listening"])
        self.assertIsNone(self.voice.visual_end_pending)

    def test_interruption_invalidates_delayed_segment_completion_and_old_generation(self):
        recorder, old_epoch = self.semantic_playback(delay=2)
        with patch("jarvis.voice_ui.time.monotonic", return_value=10.1):
            self.voice.poll()
        self.voice.cancel_speech()
        recorder.events.clear()
        self.voice.speech.events.append(AudioEvent("segment_done", {"completed_at": 10.0}, old_epoch))
        with patch("jarvis.voice_ui.time.monotonic", return_value=12.1):
            self.voice.poll()
        self.assertEqual(recorder.events, [])
        self.assertFalse(self.voice.pending_visuals)
        self.assertFalse(self.voice.pending_segment_ends)
        self.assertIsNone(self.voice.visual_end_pending)

    def real_semantic_phrase(self, text):
        """Real text/orchestration/Canvas, designated PCM process double only."""
        if self.voice.listening:
            self.voice.stop_listening()
        self.app.presence.close()
        self.app.presence = PresenceView(self.app)
        self.app.presence.show()
        self.root.update()
        self.activate("headphones")
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk(text)
        self.voice.finish_turn("complete")
        phrase = [command for command in self.voice.speech.commands if command is not None][-1]
        from dataclasses import asdict
        payload = {"text": phrase.display_text, "response_id": self.voice.epoch,
                   "segment_id": phrase.segment_id, "original_start": phrase.start,
                   "original_end": phrase.end, "fraction": 1., "rms": .12,
                   "wave": [.2, -.1, .05, -.3], "emitted_at": 10., "delay": 0.,
                   "spectrum_mode": phrase.spectrum_mode,
                   "spectrum_events": [asdict(event) for event in phrase.spectrum_events],
                   "caption_plan": asdict(phrase.caption_plan)}
        return phrase, payload

    def finish_semantic_pcm(self, payload, *, played=True):
        epoch = self.voice.epoch
        if played:
            self.voice.speech.events.append(AudioEvent("played", payload, epoch))
        self.voice.speech.events.extend([
            AudioEvent("segment_done", {**payload, "completed_at": 10.}, epoch),
            AudioEvent("speech_done", generation=epoch)])
        with patch("jarvis.voice_ui.time.monotonic", return_value=10.1):
            self.voice.poll()

    def assert_semantic_canvas(self, family):
        view = self.app.presence
        self.assertEqual(view.semantic.family, family)
        items = view.canvas.find_all()
        with patch("jarvis.presence.time.monotonic", return_value=10.65):
            view._render()
        points = view.canvas.coords(view.paths[-1])
        self.assertGreater(max(points[1::2]) - min(points[1::2]), 30)
        self.assertEqual(view.canvas.itemcget(view.paths[-1], "state"), "normal")
        self.assertEqual(view.canvas.find_all(), items)
        details = any(view.canvas.itemcget(path, "state") == "normal"
                      for pair in view.semantic_paths for path in pair)
        self.assertEqual(details, family != "affection")
        self.assertFalse(self.voice.tts_active)
        self.assertFalse(self.voice.reading)
        self.assertEqual(view.state, "listening")

    def test_three_terminal_expressions_via_real_voice_events_and_canvas(self):
        for text, family in (("Heureux de te revoir 😊", "smile"),
                             ("Je t'aime ❤️", "affection"),
                             ("C'est drôle 😂", "laughter")):
            with self.subTest(text=text):
                phrase, payload = self.real_semantic_phrase(text)
                region = self.app.markdown.append(text)
                self.assertEqual(self.app.chat.get(region.start, region.end), text)
                self.assertTrue(any(event.kind == "expression" for event in phrase.events))
                self.assertFalse(any(symbol in str(phrase) for symbol in ("😊", "❤", "😂")))
                self.finish_semantic_pcm(payload)
                self.assert_semantic_canvas(family)
                self.app.presence.close()
                self.voice.stop_listening()

    def test_repeated_waiting_state_does_not_discard_queued_voice_expression(self):
        _phrase, payload = self.real_semantic_phrase("Heureux de te revoir 😊")
        self.voice.notify_presence("thinking")
        self.finish_semantic_pcm(payload)
        self.assert_semantic_canvas("smile")

    def test_late_stt_notifications_do_not_preempt_a_response_without_speech_start(self):
        for kind in ("transcribing", "stt_queued", "stt_error"):
            with self.subTest(kind=kind):
                _phrase, payload = self.real_semantic_phrase("Je t'aime ❤️")
                self.voice.capture.events.append(AudioEvent(kind, {"error": "STT local", "elapsed_ms": 3}, self.voice.heard))
                self.finish_semantic_pcm(payload)
                self.assert_semantic_canvas("affection")
                self.app.presence.close()
                self.voice.stop_listening()

    def test_late_stt_after_audio_finish_preserves_the_final_expression(self):
        for kind in ("transcribing", "stt_queued", "stt_error"):
            with self.subTest(kind=kind):
                _phrase, payload = self.real_semantic_phrase("Heureux de te revoir 😊")
                self.finish_semantic_pcm(payload)
                self.voice.capture.events.append(AudioEvent(kind,
                    {"error": "STT local", "elapsed_ms": 3}, self.voice.heard))
                with patch("jarvis.voice_ui.time.monotonic", return_value=10.2):
                    self.voice.poll()
                self.assert_semantic_canvas("smile")

    def test_reliable_segment_boundary_survives_dropped_pcm_visual_callbacks(self):
        _phrase, payload = self.real_semantic_phrase("C'est drôle 😂")
        self.finish_semantic_pcm(payload, played=False)
        self.assert_semantic_canvas("laughter")

    def test_real_user_interruption_closes_semantic_epoch_and_rejects_old_completion(self):
        _phrase, payload = self.real_semantic_phrase("Heureux de te revoir 😊")
        self.finish_semantic_pcm(payload)
        self.assert_semantic_canvas("smile")
        old_epoch = self.voice.epoch
        self.voice.capture.events.append(AudioEvent("speech_start", generation=self.voice.heard + 1))
        with patch("jarvis.voice_ui.time.monotonic", return_value=10.8):
            self.voice.poll()
        self.assertGreater(self.voice.epoch, old_epoch)
        self.assertFalse(self.app.presence.semantic.active)
        self.assertTrue(self.app.presence._semantic_closed)
        self.assertEqual(self.app.presence.state, "user_speaking")
        self.voice.speech.events.append(AudioEvent("segment_done", payload, old_epoch))
        with patch("jarvis.voice_ui.time.monotonic", return_value=11.):
            self.voice.poll()
        self.assertFalse(self.app.presence.semantic.active)
        self.assertFalse(self.app.presence._semantic_cues)

    def test_code_and_technical_examples_never_trigger_through_voice_events(self):
        for text in ("Exemple `😊`.", "La regex 😊 est un exemple technique.",
                     "Le symbole « ❤️ » est montré."):
            with self.subTest(text=text):
                phrase, payload = self.real_semantic_phrase(text)
                self.assertFalse(any(event.kind == "expression" for event in phrase.events))
                self.finish_semantic_pcm(payload)
                self.assertFalse(self.app.presence.semantic.active)

    def test_semantic_trace_is_bounded_and_copyable_from_microphone_diagnostics(self):
        _phrase, payload = self.real_semantic_phrase("C'est drôle 😂")
        self.finish_semantic_pcm(payload)
        self.app.presence.update_microphone("disabled")
        self.app.presence.complete_segment(payload)
        self.voice.open_diagnostics()
        self.voice.copy_diagnostics()
        copied = self.root.clipboard_get()
        for stage in ("detected", "scheduled", "triggered", "cancelled", "ignored"):
            self.assertIn(stage, copied)
        self.assertIn("laughter", copied)
        self.assertIn("microphone:disabled", copied)
        self.assertIn("closed_or_stale_completion", copied)
        for segment in range(100):
            self.app.presence._trace_semantic("ignored", "test", (123, segment))
        self.assertEqual(len(self.app.presence._semantic_trace), 48)
        self.voice.copy_diagnostics()
        self.assertIn("segment 99", self.root.clipboard_get())

    def test_visual_only_emoji_tail_attaches_to_previous_segment_without_empty_piper_request(self):
        recorder = self.app.presence = SemanticPresenceRecorder()
        self.activate("headphones")
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk("Bonjour. ")
        self.voice.chunk("😊")
        self.voice.finish_turn("complete")
        phrases = [command for command in self.voice.speech.commands if command is not None]
        self.assertEqual([str(command) for command in phrases], ["Bonjour."])
        self.assertEqual(self.voice.segment_id, 1)
        self.assertTrue(all(command.response_id == self.voice.epoch for command in phrases))
        self.assertEqual([entry[1] for entry in recorder.queued], [1, 1])
        response_id, segment_id, original, start, end, events = recorder.queued[-1]
        self.assertEqual((response_id, segment_id), (self.voice.epoch, 1))
        self.assertEqual(original, "😊")
        self.assertEqual((start, end), (9, 10))
        self.assertEqual([event.value for event in events if event.kind == "expression"], ["😊"])

    def test_microphone_closed_until_explicit_acceptance_and_toggle_stops_it(self):
        self.assertFalse(self.voice.listening)
        self.assertEqual(self.voice.microphone_state, "disabled")

        self.assertEqual(self.voice.capture.starts, [])
        self.assertEqual(self.voice.speech.starts, [])
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=False) as permission:
            self.voice.toggle()
        permission.assert_called_once()
        self.assertFalse(self.voice.listening)
        self.assertEqual(self.voice.capture.starts, [])
        self.assertEqual(self.voice.microphone_state, "disabled")
        self.assertEqual(self.voice.microphone_detail, "Autorisation refusée")
        self.app.presence.update_microphone.assert_called_with("disabled", detail="Autorisation refusée")
        self.activate()
        self.assertEqual(len(self.voice.capture.starts), 1)
        self.assertEqual(self.voice.microphone_state, "starting")
        with patch("jarvis.voice_ui.messagebox.askyesno") as permission:
            self.voice.toggle()
        permission.assert_not_called()
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.listening)
        self.assertEqual(self.voice.microphone_state, "disabled")

    def test_microphone_state_is_separate_bounded_and_optional(self):
        self.voice.set_mic_state("error", "Échec STT " + "é" * 400)
        self.assertEqual(self.voice.microphone_state, "error")
        self.assertEqual(len(self.voice.microphone_detail), 256)
        self.app.presence.update_microphone.assert_called_once_with("error", detail=self.voice.microphone_detail)
        self.app.presence.update_event.assert_not_called()
        self.assertEqual(self.voice.capture.starts, [])
        self.assertEqual(self.voice.capture.commands, [])
        self.voice.set_mic_state("error", self.voice.microphone_detail)
        self.app.presence.update_microphone.assert_called_once()
        with patch.object(self.app, "presence", object()):
            self.voice.set_mic_state("disabled")
        self.assertEqual(self.voice.microphone_state, "disabled")
        with self.assertRaises(ValueError):
            self.voice.set_mic_state("emotion")

    def test_microphone_states_follow_capture_events_and_stale_stt_is_ignored(self):
        self.activate("headphones")
        for event, expected in (
                (AudioEvent("listening"), "open"),
                (AudioEvent("speech_start", generation=2), "voice"),
                (AudioEvent("stt_queued", generation=2), "stt"),
                (AudioEvent("transcribing", generation=1), "stt"),
                (AudioEvent("stt_error", {"error": "ancien", "elapsed_ms": 2}, 1), "stt"),
                (AudioEvent("transcribing", generation=2), "stt"),
                (AudioEvent("mic_level", {"speaking": False, "rms": 0}, 2), "stt"),
                (AudioEvent("stt_complete", {"result": "", "elapsed_ms": 2}, 2), "open")):
            with self.subTest(event=event.kind, generation=event.generation):
                self.voice.capture.events.append(event)
                self.voice.poll()
                self.assertEqual(self.voice.microphone_state, expected)
                self.assertTrue(self.voice.capture.alive())

    def test_speaker_microphone_stays_suspended_until_successful_resume(self):
        self.activate()
        self.voice.capture.events.append(AudioEvent("listening"))
        self.voice.poll()
        self.begin_simulated_audio_turn()
        self.assertEqual(self.voice.microphone_state, "suspended")
        self.voice.capture.events.append(AudioEvent("mic_level", {"speaking": False, "rms": 0}))
        self.voice.poll()
        self.assertEqual(self.voice.microphone_state, "suspended")
        self.voice.speech.events.append(AudioEvent("speech_done", generation=self.voice.epoch))
        self.voice.poll()
        self.assertEqual(self.voice.microphone_state, "suspended")
        self.voice.capture.accept_commands = False
        self.pump_until(lambda: self.voice.resume_id is None)
        self.assertEqual(self.voice.microphone_state, "error")
        self.assertIn("Reprise", self.voice.microphone_detail)
        self.assertTrue(self.voice.listening)
        self.voice.capture.accept_commands = True
        self.voice.schedule_resume()
        self.pump_until(lambda: self.voice.resume_id is None)
        self.assertEqual(self.voice.microphone_state, "open")

    def test_capture_failure_then_explicit_stop_and_emergency_have_distinct_states(self):
        self.activate()
        self.voice.capture.events.extend([
            AudioEvent("capture_error", {"stage": "ouverture microphone", "error": "Périphérique absent"}),
            AudioEvent("error", "Capture indisponible"),
        ])
        self.voice.poll()
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.listening)
        self.assertEqual(self.voice.microphone_state, "error")
        self.assertEqual(self.voice.microphone_detail, "Capture indisponible")
        self.voice.stop_listening()
        self.assertEqual(self.voice.microphone_state, "disabled")
        self.activate("headphones")
        self.voice.emergency()
        self.assertEqual(self.voice.microphone_state, "disabled")
        self.assertIn("urgence", self.voice.microphone_detail)
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.speech.alive())

    def test_markdown_stream_reaches_tts_clean_only_after_construct_closes(self):
        self.activate("headphones")
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk("**Bonjour. Voici [le guide](https://example")
        self.assertEqual(self.voice.speech.commands, [])
        self.voice.chunk(".org)** 👩🏽‍🚀. ")
        self.voice.finish_turn("complete")
        phrases = [command for command in self.voice.speech.commands if command is not None]
        self.assertTrue(phrases)
        spoken = " ".join(phrases)
        self.assertIn("Bonjour", spoken)
        self.assertIn("le guide", spoken)
        for marker in ("*", "[", "]", "https", "👩", "fusée", "astronaute"):
            self.assertNotIn(marker, spoken)
        self.assertIn("👩🏽‍🚀", "".join(phrase.display_text for phrase in phrases))
        self.assertTrue(any(event.kind == "emoji" for phrase in phrases for event in phrase.events))
        self.assertEqual([phrase.segment_id for phrase in phrases], list(range(1, len(phrases) + 1)))

    def test_interruption_discards_incomplete_markup_before_next_turn(self):
        self.activate("headphones")
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk("**Ancienne réponse inachevée")
        self.assertTrue(self.voice.segmenter.pending)
        self.voice.cancel_speech()
        self.assertEqual(self.voice.segmenter.pending, "")
        self.voice.finish_turn("complete")
        self.assertEqual(self.voice.speech.commands, [])
        next_mid = self.store.begin_turn(self.app.session_id, "Suite", "local", source="voice")
        self.voice.begin_turn(next_mid, "voice")
        self.voice.chunk("Nouvelle réponse.")
        self.assertEqual(self.voice.speech.commands, ["Nouvelle réponse."])

    def test_rejected_voice_send_keeps_transcript_in_composer(self):
        self.activate()
        self.voice.capture.events.extend([
            AudioEvent("speech_start", generation=1),
            AudioEvent("transcript", "Parole sans modèle sélectionné", generation=1),
        ])
        self.voice.poll()
        self.assertIsNone(self.app.operation)
        self.assertIn("Parole sans modèle sélectionné", self.app.input.get("1.0", "end"))

    def test_stt_diagnostics_and_error_recovery_keep_microphone_active(self):
        self.activate()
        self.voice.open_diagnostics()
        self.voice.capture.events.extend([
            AudioEvent("speech_start", generation=1),
            AudioEvent("diagnostic", {"rms": 0.02, "vad": 0.12, "state": "silence",
                                      "turn_seconds": 1.28, "native_rate": 48000,
                                      "rate": 16000, "frame_samples": 512}),
            AudioEvent("turn_end", {"reason": "silence", "duration": 1.28}, generation=1),
            AudioEvent("transcribing", generation=1),
            AudioEvent("mic_level", {"speaking": False, "rms": 0}, generation=1),
        ])
        self.voice.poll()
        self.assertIn("Transcription française locale", self.voice.status.get())
        self.assertTrue(self.voice.transcribing)
        self.app.presence.update_event.assert_called_with("thinking", signal=None, caption=None)
        text = self.voice.diagnostic_text.get("1.0", "end")
        for value in ("0.02000", "0.120", "48000 → 16000", "512", "turn_end", "transcribing"):
            self.assertIn(value, text)
        self.voice.capture.events.append(AudioEvent("stt_error", {"error": "STT failure", "elapsed_ms": 250}, 1))
        self.voice.poll()
        self.assertFalse(self.voice.transcribing)
        self.assertTrue(self.voice.capture.alive())
        self.assertEqual(self.voice.microphone_state, "error")
        self.assertIn("STT ; écoute maintenue", self.voice.microphone_detail)
        self.assertIn("STT failure", self.voice.diagnostic_text.get("1.0", "end"))
        button = next(child for child in self.voice.diagnostic_window.winfo_children()
                      if child.winfo_class() == "TButton")
        button.invoke()
        self.assertEqual(self.voice.capture.commands[-1], {"kind": "finish_turn"})
        self.voice.capture.events.append(AudioEvent("mic_level", {"speaking": False, "rms": 0}, 1))
        self.voice.poll()
        self.assertEqual(self.voice.microphone_state, "open")
        self.voice.capture.events.extend([
            AudioEvent("speech_start", generation=2),
            AudioEvent("transcribing", generation=2),
            AudioEvent("stt_complete", {"result": "Bonjour", "elapsed_ms": 200}, 2),
            AudioEvent("transcript", "Bonjour", 2),
        ])
        self.voice.poll()
        self.assertIn("Bonjour", self.app.input.get("1.0", "end"))
        self.assertFalse(self.voice.transcribing)
        self.voice.diagnostic_window.destroy()
        self.voice.open_diagnostics()
        self.assertIn("stt_complete", self.voice.diagnostic_text.get("1.0", "end"))

    def test_old_stt_notifications_do_not_override_new_turn_status_or_presence(self):
        self.activate()
        self.voice.capture.events.extend([
            AudioEvent("speech_start", generation=2),
            AudioEvent("stt_queued", generation=2),
            AudioEvent("transcribing", generation=1),
            AudioEvent("stt_complete", {"elapsed_ms": 200, "queue_ms": 5, "result": "Ancien"}, 1),
            AudioEvent("stt_error", {"error": "Ancienne erreur", "elapsed_ms": 300}, 1),
        ])
        self.voice.poll()
        self.assertTrue(self.voice.transcribing)
        self.assertIn("attente du STT", self.voice.status.get())
        self.assertEqual(self.voice.latencies, {})
        self.app.presence.update_event.assert_called_with("thinking", signal=None, caption=None)
        self.voice.capture.events.append(AudioEvent("stt_superseded", "Microphone suspendu", 2))
        self.voice.poll()
        self.assertFalse(self.voice.transcribing)

    def test_latency_chain_uses_dac_timestamp_and_rejects_cancelled_playback(self):
        self.activate()
        self.voice.capture.events.extend([
            AudioEvent("speech_start", generation=1),
            AudioEvent("turn_end", {"ended_at": 10.0, "silence_ms": 800}, 1),
            AudioEvent("stt_complete", {"elapsed_ms": 250, "queue_ms": 40}, 1),
        ])
        self.voice.poll()
        with patch("jarvis.voice_ui.time.monotonic", return_value=11.0):
            mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
            self.voice.begin_turn(mid, "voice")
        with patch("jarvis.voice_ui.time.monotonic", return_value=11.2):
            self.voice.chunk("Le début")
        with patch("jarvis.voice_ui.time.monotonic", return_value=11.5):
            self.voice.chunk(" de la réponse.")
        self.voice.speech.events.extend([
            AudioEvent("tts_ready", {"load_ms": 120}, self.voice.epoch),
            AudioEvent("tts_pcm_ready", {"elapsed_ms": 80}, self.voice.epoch),
            # Deliberately observe the event much later: the device timestamp wins.
            AudioEvent("played", {"emitted_at": 11.8, "delay": 0.1, "started_at": 11.9}, self.voice.epoch),
        ])
        with patch("jarvis.voice_ui.time.monotonic", return_value=12.2):
            self.voice.poll()
        expected = {"Silence de fin de tour (PCM)": 800, "Whisper : transcription": 250,
                    "Whisper : attente en file": 40, "Ollama : envoi → premier texte reçu": 200,
                    "Premier texte → première phrase TTS": 300, "Chargement Piper (worker)": 120,
                    "Piper : synthèse du premier bloc": 80, "Phrase TTS → premier PCM (DAC estimé)": 400,
                    "Fin de tour détectée → premier PCM (DAC estimé)": 1900,
                    "Premier texte → premier PCM (DAC estimé)": 700,
                    "Fin de parole VAD → premier PCM (estimé)": 2700}
        self.assertEqual(self.voice.latencies, expected)
        values = self.app.presence.update_timing.call_args.args[0]
        self.assertEqual(values["token_to_audio_ms"], 700)
        self.assertEqual(values["speech_to_audio_ms"], 2700)
        old_epoch = self.voice.epoch
        self.voice.cancel_speech()
        self.voice.speech.events.extend([
            AudioEvent("tts_pcm_ready", {"elapsed_ms": 999}, old_epoch),
            AudioEvent("played", {"emitted_at": 12.3, "delay": 0.2}, old_epoch),
        ])
        self.voice.poll()
        self.assertEqual(self.voice.latencies, expected)
        self.voice.open_diagnostics()
        self.assertIn("1900", self.voice.diagnostic_text.get("1.0", "end"))
        self.assertIn("Bluetooth non mesuré", self.voice.diagnostic_text.get("1.0", "end"))

    def test_unhinged_profile_only_changes_prompt_not_microphone_or_endpoint(self):
        from jarvis.voice_config import PERSONALITY_PROMPTS
        endpoint = self.app.settings.endpoint
        with patch("jarvis.audio.device_inventory", return_value={"input": [], "output": []}):
            dialog = self.voice.open_settings()
        choice = dialog.controls["personality"]
        self.assertIn("UNHINGED", choice.cget("values"))
        choice.set("UNHINGED")
        dialog.save_button.invoke()
        self.assertEqual(self.app.settings.system_prompt, PERSONALITY_PROMPTS["UNHINGED"])
        self.assertEqual(self.app.settings.endpoint, endpoint)
        self.assertFalse(self.voice.listening)
        self.assertEqual(self.voice.capture.starts, [])
        self.assertEqual(self.store.get_preference("voice")["personality"], "UNHINGED")

    def test_voice_transcript_uses_real_http_stream_and_sqlite_archive(self):
        with Fixture() as fixture:
            self.app.settings = Settings(endpoint=fixture.endpoint, model="test-abliterated:latest")
            self.app.models = [self.app.settings.model]
            self.activate()
            self.voice.capture.events.extend([
                AudioEvent("speech_start", generation=1),
                AudioEvent("transcript", "  Bonjour depuis le microphone  ", generation=1),
            ])
            self.voice.poll()
            self.assertEqual(self.app.operation, "chat")
            self.pump_until(lambda: self.app.operation is None)
            user, assistant = self.store.messages(self.app.session_id)
            for message in (user, assistant):
                self.assertEqual(message["source"], "voice")
                self.assertEqual(message["model"], "test-abliterated:latest")
                self.assertEqual(json.loads(message["metadata"])["final_transcript"], "Bonjour depuis le microphone")
            self.assertEqual(user["content"], "Bonjour depuis le microphone")
            self.assertEqual(assistant["content"], "Bonjour été 🚀")
            self.assertEqual(assistant["status"], "complete")
            self.assertTrue(fixture.server.request_body["stream"])
            self.assertNotIn("tools", fixture.server.request_body)
            self.assertEqual(fixture.server.request_body["messages"][-1],
                             {"role": "user", "content": "Bonjour depuis le microphone"})
            self.voice.poll()
            self.assertEqual(self.voice.speech.commands, ["Bonjour été", None])
            self.assertIn("🚀", self.voice.speech.commands[0].display_text)
            self.assertEqual(self.voice.speech.commands[0].original, "Bonjour été 🚀")
            self.assertIn({"kind": "mute", "value": True}, self.voice.capture.commands)
            self.assertEqual(json.loads(assistant["metadata"])["tts_engine"], "piper")
            self.voice.speech.events.append(AudioEvent("speech_done", generation=self.voice.epoch))
            self.voice.poll()
            self.assertEqual(json.loads(self.store.messages(self.app.session_id)[1]["metadata"])["audio_status"], "complete")
            self.assertTrue(self.voice.speech.alive())  # Idle voice is reused, audio is finished.
            self.assertFalse(self.voice.tts_active)
            self.pump_until(lambda: self.voice.capture.commands[-1] == {"kind": "mute", "value": False})

    def test_positioned_spectrum_changes_only_on_pcm_and_is_cleared_by_interruption(self):
        from dataclasses import asdict
        from jarvis.presence import PresenceView
        self.app.presence = PresenceView(self.app)
        self.activate("headphones")
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        source = "**Je suis furieux !** Je suis confiant."
        self.voice.chunk(source)
        self.voice.finish_turn("complete")
        phrases = [command for command in self.voice.speech.commands if command is not None]
        # Balanced emphasis is kept atomic for TTS; one audio phrase may still
        # contain several positioned colour passages.
        self.assertEqual(len(phrases), 1)
        self.assertEqual(self.app.presence.tone.name, "neutralité")
        phrase = phrases[0]
        self.assertEqual(source[phrase.start:phrase.end], phrase.original)
        self.assertEqual([event.tone.name for event in phrase.spectrum_events], ["colère", "espoir"])
        for fraction, expected in ((0.05, "colère"), (0.95, "espoir")):
            self.voice.speech.events.append(AudioEvent("played", {
                "text": phrase.display_text, "spoken_text": str(phrase), "fraction": fraction,
                "segment_id": phrase.segment_id, "original_start": phrase.start,
                "original_end": phrase.end, "spectrum_mode": phrase.spectrum_mode,
                "spectrum_events": [asdict(event) for event in phrase.spectrum_events],
                "emitted_at": time.monotonic() - 0.01, "delay": 0,
                "rms": 0.1, "wave": [0.1, -0.1]}, self.voice.epoch))
            self.voice.poll()
            self.assertEqual(self.app.presence.tone.name, expected)
        old_epoch = self.voice.epoch
        self.voice.capture.events.append(AudioEvent("speech_start", generation=1))
        self.voice.poll()
        self.assertGreater(self.voice.epoch, old_epoch)
        self.assertEqual(self.app.presence.tone.name, "neutralité")
        self.assertEqual(self.voice.pending_visuals, [])
        self.assertIsNone(self.app.presence.caption_data)

    def test_headphone_voice_interrupt_stops_audio_and_invalidates_old_visuals(self):
        self.activate("headphones")
        mid = self.begin_simulated_audio_turn()
        old_epoch = self.voice.epoch
        self.voice.pending_visuals.append((time.monotonic() + 1, {"rms": 0.2}, old_epoch))
        self.voice.capture.events.append(AudioEvent("speech_start", generation=2))
        self.voice.poll()
        self.assertFalse(self.voice.speech.alive())
        self.assertGreater(self.voice.epoch, old_epoch)
        self.assertEqual(self.voice.pending_visuals, [])
        self.assertEqual(json.loads(self.store.messages(self.app.session_id)[1]["metadata"])["audio_status"], "interrupted")
        self.assertIsNone(self.voice.mid)
        self.assertFalse(self.voice.reading)
        self.assertNotIn({"kind": "mute", "value": True}, self.voice.capture.commands)
        # A delayed notification from the old epoch must never animate/speak again.
        self.app.presence.reset_mock()
        self.voice.speech.events.append(AudioEvent("played", {"emitted_at": 0, "delay": 0}, old_epoch))
        self.voice.poll()
        self.app.presence.update_event.assert_not_called()
        self.assertEqual(self.store.messages(self.app.session_id)[1]["id"], mid)

    def test_preload_overlaps_llm_without_muting_then_reuses_idle_voice(self):
        self.activate()
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.assertTrue(self.voice.speech.alive())
        self.assertFalse(self.voice.tts_active)
        self.assertEqual(self.voice.speech.commands, [])
        self.assertNotIn({"kind": "mute", "value": True}, self.voice.capture.commands)
        self.assertNotIn("audio_status", json.loads(self.store.messages(self.app.session_id)[1]["metadata"]))
        self.voice.speech.events.append(AudioEvent("tts_ready", {"load_ms": 120}, self.voice.epoch))
        self.voice.poll()
        self.voice.chunk("Première réponse.")
        self.voice.finish_turn("complete")
        self.voice.poll()
        self.voice.speech.events.append(AudioEvent("speech_done", generation=self.voice.epoch))
        self.voice.poll()
        self.assertTrue(self.voice.speech.alive())
        self.assertFalse(self.voice.tts_active)
        second = self.store.begin_turn(self.app.session_id, "Autre question", "local", source="voice")
        self.voice.begin_turn(second, "voice")
        self.voice.chunk("Seconde réponse.")
        self.assertEqual(len(self.voice.speech.starts), 1)
        self.assertTrue(self.voice.tts_ready)
        self.assertTrue(self.voice.tts_active)
        self.voice.stop_listening()
        self.assertFalse(self.voice.speech.alive())

    def test_preload_failure_is_reported_and_next_turn_restarts_engine(self):
        self.activate()
        first = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(first, "voice")
        self.voice.speech.events.append(AudioEvent("tts_load_error", "Voix absente", self.voice.epoch))
        self.voice.poll()
        self.assertIn("Voix absente", self.voice.status.get())
        self.assertFalse(self.voice.speech.alive())
        second = self.store.begin_turn(self.app.session_id, "Réessayer", "local", source="voice")
        self.voice.begin_turn(second, "voice")
        self.assertTrue(self.voice.speech.alive())
        self.assertEqual(len(self.voice.speech.starts), 2)

    def test_sample_request_requires_confirmation_and_replay_mutes_microphone(self):
        self.activate()
        self.voice.open_diagnostics()
        path = str(Path(self.temp.name) / "requested.wav")
        with patch("jarvis.voice_ui.filedialog.asksaveasfilename", return_value=path), \
                patch("jarvis.voice_ui.messagebox.askyesno", return_value=False):
            self.voice.request_sample()
        self.assertNotIn({"kind": "sample_next", "path": path}, self.voice.capture.commands)
        with patch("jarvis.voice_ui.filedialog.asksaveasfilename", return_value=path), \
                patch("jarvis.voice_ui.messagebox.askyesno", return_value=True):
            self.voice.request_sample()
        self.assertEqual(self.voice.capture.commands[-1], {"kind": "sample_next", "path": path})
        self.voice.capture.events.append(AudioEvent("sample_saved", {"path": path, "quality": {"rms": 0.02}}))
        self.voice.poll()
        self.voice.replay_sample()
        self.assertEqual(self.voice.speech.starts[-1][0], "sample")
        self.assertEqual(self.voice.speech.commands, [path])
        self.assertEqual(self.voice.capture.commands[-1], {"kind": "mute", "value": True})
        self.assertTrue(self.voice.tts_active)
        self.voice.speech.events.append(AudioEvent("speech_done", generation=self.voice.epoch))
        self.voice.poll()
        self.assertFalse(self.voice.speech.alive())
        self.assertFalse(self.voice.tts_active)
        self.pump_until(lambda: self.voice.capture.commands[-1] == {"kind": "mute", "value": False})
        self.voice.reference.set("Bonjour, été !")
        self.voice.stt_details = {"result": "bonjour été"}
        self.voice.compare_reference()
        self.assertIn("0.0%", self.voice.reference_result)
        self.voice.reference.set("...")
        self.voice.compare_reference()
        self.assertIn("au moins un mot", self.voice.reference_result)
        self.assertTrue(self.voice.listening)

    def test_stopping_listening_releases_a_still_loading_idle_engine(self):
        self.activate()
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.voice.stop_listening()
        self.assertFalse(self.voice.speech.alive())
        self.assertFalse(self.voice.tts_ready)
        self.assertFalse(self.voice.tts_active)

    def test_manual_stop_also_stops_audio_after_llm_finished(self):
        self.activate()
        mid = self.begin_simulated_audio_turn()
        self.store.update_response(mid, "Texte intégral déjà terminé.", "complete")
        self.voice.finish_turn("complete")
        self.assertIsNone(self.app.operation)
        self.assertEqual(str(self.app.stop_button.cget("state")), "normal")
        self.app.stop_button.invoke()
        self.assertFalse(self.voice.speech.alive())
        self.assertEqual(str(self.app.stop_button.cget("state")), "disabled")
        message = self.store.messages(self.app.session_id)[1]
        self.assertEqual(message["status"], "complete")
        self.assertEqual(message["content"], "Texte intégral déjà terminé.")
        self.assertEqual(json.loads(message["metadata"])["audio_status"], "interrupted")

    def test_older_transcript_is_discarded_after_new_speech_start(self):
        self.activate("headphones")
        self.voice.capture.events.extend([
            AudioEvent("speech_start", generation=3),
            AudioEvent("transcript", "Intervention obsolète", generation=2),
        ])
        with patch.object(self.app, "send") as send:
            self.voice.poll()
        send.assert_not_called()
        self.assertEqual(self.store.messages(self.app.session_id), [])

    def test_emergency_cancels_stream_and_both_audio_processes(self):
        with Fixture() as fixture:
            fixture.server.mode = "slow"
            self.app.settings = Settings(endpoint=fixture.endpoint, model="test")
            self.app.models = ["test"]
            self.activate("headphones")
            self.app.send(source="voice", text="Question lente")
            self.pump_until(lambda: bool(self.app.response))
            self.voice.submit_phrase("Phrase audio déjà prête.")
            self.voice.emergency()
            self.assertFalse(self.voice.capture.alive())
            self.assertFalse(self.voice.speech.alive())
            self.assertFalse(self.app.worker.alive())
            self.assertFalse(self.voice.listening)
            self.assertIsNone(self.app.operation)
            message = self.store.messages(self.app.session_id)[1]
            self.assertEqual(message["content"], "Bonjour ")
            self.assertEqual(message["status"], "cancelled")
            self.assertEqual(json.loads(message["metadata"])["audio_status"], "interrupted")

    def test_callback_failure_silences_audio_before_recovery(self):
        self.activate("headphones")
        self.begin_simulated_audio_turn()
        self.app.callback_error(RuntimeError, RuntimeError("UI failure"), None)
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.speech.alive())
        self.assertFalse(self.voice.listening)
        self.assertIn("Erreur interne", self.app.status.get())

    def test_text_only_turn_never_marked_as_interrupted_audio(self):
        first = self.store.begin_turn(self.app.session_id, "Texte uniquement", "local")
        self.voice.begin_turn(first, "text")
        self.voice.chunk("Réponse sans lecture.")
        self.store.update_response(first, "Réponse sans lecture.", "complete")
        self.voice.finish_turn("complete")
        second = self.store.begin_turn(self.app.session_id, "Autre texte", "local")
        self.voice.begin_turn(second, "text")
        self.voice.stop_listening()
        for message in self.store.messages(self.app.session_id):
            self.assertNotIn("audio_status", json.loads(message["metadata"]))
        self.assertEqual(self.voice.speech.starts, [])

    def test_stop_listening_cancels_delayed_resume_before_window_closes(self):
        self.activate()
        self.begin_simulated_audio_turn()
        existing_callbacks = set(self.root.tk.call("after", "info"))
        self.voice.speech.events.append(AudioEvent("speech_done", generation=self.voice.epoch))
        self.voice.poll()
        self.assertNotEqual(set(self.root.tk.call("after", "info")), existing_callbacks)
        self.voice.stop_listening()
        self.assertEqual(set(self.root.tk.call("after", "info")), existing_callbacks)

    def test_saturated_speaker_mute_prevents_playback_and_preserves_text(self):
        self.activate()
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.voice.capture.accept_commands = False
        self.voice.chunk("Texte déjà généré.")
        self.assertFalse(self.voice.speech.alive())
        self.assertEqual(self.voice.speech.commands, [])
        self.assertEqual(json.loads(self.store.messages(self.app.session_id)[1]["metadata"])["audio_status"], "error")
        self.assertIn("suspension du microphone impossible", self.voice.status.get())
        self.assertEqual(self.voice.microphone_state, "error")

    def bounded_speech_queue(self):
        """Real bounded transport; synthesis/playback remain explicitly simulated."""
        transport = queue.Queue(maxsize=8)
        original_send = self.voice.speech.send

        def send(command):
            try:
                transport.put_nowait(command)
            except queue.Full:
                return False
            return original_send(command)

        self.send_patch = patch.object(self.voice.speech, "send", side_effect=send)
        self.send_patch.start()
        self.addCleanup(self.send_patch.stop)
        return transport

    def test_fast_ten_phrase_response_waits_for_worker_then_drains_in_order(self):
        self.activate("headphones")
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        transport = self.bounded_speech_queue()
        phrases = [f"Phrase {i}." for i in range(10)]
        self.voice.chunk(" ".join(phrases))
        self.voice.finish_turn("complete")
        self.voice.poll()  # A full worker queue must keep the last phrases and sentinel waiting.
        self.assertTrue(self.voice.speech.alive())
        self.assertEqual(self.voice.speech.commands, phrases[:8])
        self.assertEqual(list(self.voice.pending_phrases), phrases[8:])
        self.assertTrue(self.voice.end_pending)
        self.assertEqual([transport.get_nowait() for _ in range(8)], phrases[:8])
        self.voice.poll()
        self.assertEqual(self.voice.speech.commands, phrases + [None])
        self.assertEqual([transport.get_nowait() for _ in range(3)], phrases[8:] + [None])
        self.assertFalse(self.voice.pending_phrases)
        self.assertFalse(self.voice.end_pending)
        self.assertEqual(json.loads(self.store.messages(self.app.session_id)[1]["metadata"])["audio_status"], "synthesizing")

    def test_cancel_discards_backlog_and_pending_end_marker(self):
        self.activate("headphones")
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.bounded_speech_queue()
        self.voice.chunk("Une phrase. " * 10)
        self.voice.finish_turn("complete")
        self.assertEqual(len(self.voice.pending_phrases), 2)
        previous_epoch = self.voice.epoch
        self.voice.cancel_speech()
        self.voice.poll()
        self.assertFalse(self.voice.pending_phrases)
        self.assertFalse(self.voice.end_pending)
        self.assertGreater(self.voice.epoch, previous_epoch)
        self.assertFalse(self.voice.speech.alive())
        self.assertEqual(self.voice.speech.commands, ["Une phrase."] * 8)
        self.assertEqual(json.loads(self.store.messages(self.app.session_id)[1]["metadata"])["audio_status"], "interrupted")

    def test_backlog_limit_reports_error_without_silent_phrase_eviction(self):
        self.activate("headphones")
        mid = self.store.begin_turn(self.app.session_id, "Question", "local", source="voice")
        self.voice.begin_turn(mid, "voice")
        self.bounded_speech_queue()
        self.voice.chunk("Une phrase. " * 72)
        self.assertEqual(len(self.voice.pending_phrases), 64)
        self.assertTrue(self.voice.speech.alive())
        self.voice.chunk("Phrase en trop.")
        self.assertFalse(self.voice.speech.alive())
        self.assertFalse(self.voice.pending_phrases)
        self.assertIn("64", self.voice.status.get())
        self.assertIn("texte reste enregistré", self.voice.status.get())
        self.assertEqual(json.loads(self.store.messages(self.app.session_id)[1]["metadata"])["audio_status"], "error")


class RuntimeContractTests(unittest.TestCase):
    def test_explicit_sample_replay_reads_wav_without_loading_piper(self):
        from jarvis.audio_diagnostics import save_wav
        from jarvis.voice_config import VoiceSettings
        from jarvis.voice_runtime import sample_worker
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            save_wav(path, [0.25] * 1600)
            commands, outbox = queue.Queue(), queue.Queue()
            commands.put(str(path))
            with patch("jarvis.tts.AudioPlayer") as player, patch("jarvis.tts.PiperSpeech") as piper:
                sample_worker(outbox, commands, VoiceSettings().to_dict(), 7)
            piper.assert_not_called()
            pcm = player.return_value.play.call_args.args[0]
            self.assertEqual(pcm.sample_rate, 16000)
            self.assertEqual(pcm.samples, [0.25] * 1600)
            event = outbox.get_nowait()
            self.assertEqual((event.kind, event.generation), ("speech_done", 7))

    def test_persistent_worker_loads_once_for_two_generations(self):
        from jarvis.tts import PCM
        from jarvis.voice_config import VoiceSettings
        from jarvis.voice_runtime import speech_worker
        from tests.test_capture_turns import EndCapture

        class Commands:
            def __init__(self):
                self.commands = iter([{"text": text, "generation": generation}
                    for text, generation in (("Bonjour.", 4), (None, 4), ("Rebonjour.", 9), (None, 9))])

            def get(self):
                try:
                    return next(self.commands)
                except StopIteration:
                    raise EndCapture

        outbox = queue.Queue()
        with patch("jarvis.tts.PiperSpeech") as speech, patch("jarvis.tts.AudioPlayer") as player:
            speech.return_value.synthesize.side_effect = [[PCM([0.1], 16000)], [PCM([0.2], 16000)]]
            with self.assertRaises(EndCapture):
                speech_worker(outbox, Commands(), VoiceSettings().to_dict(), 4, persistent=True)
        speech.assert_called_once()
        self.assertEqual(player.return_value.play.call_count, 2)
        events = list(outbox.queue)
        self.assertEqual([e.generation for e in events if e.kind == "speech_done"], [4, 9])
        self.assertEqual([call.args[3] for call in player.return_value.play.call_args_list], [4, 9])

    def test_speech_transport_freezes_generation_with_each_command(self):
        transport = AudioProcess()
        transport.kind = "speech"
        transport.commands = queue.Queue(maxsize=2)
        transport.generation = 4
        self.assertTrue(transport.send("Bonjour"))
        transport.generation = 9
        self.assertTrue(transport.send(None))
        self.assertEqual(transport.commands.get_nowait(), {"text": "Bonjour", "generation": 4})
        self.assertEqual(transport.commands.get_nowait(), {"text": None, "generation": 9})

    def test_speech_worker_reports_load_and_first_block_timing_in_epoch(self):
        from jarvis.tts import PCM
        from jarvis.voice_config import VoiceSettings
        from jarvis.voice_runtime import speech_worker
        outbox, commands = queue.Queue(), queue.Queue()
        commands.put("Bonjour.")
        commands.put(None)
        pcm = PCM([0.2], 16000)
        with patch("jarvis.tts.PiperSpeech") as speech, patch("jarvis.tts.AudioPlayer") as player, \
                patch("jarvis.voice_runtime.time.monotonic", side_effect=[1.0, 1.1, 2.0, 2.2, 3.0]):
            speech.return_value.synthesize.return_value = [pcm]
            speech_worker(outbox, commands, VoiceSettings().to_dict(), 9)
        events = list(outbox.queue)
        self.assertEqual([e.kind for e in events], ["tts_ready", "tts_pcm_ready", "speech_done"])
        self.assertTrue(all(e.generation == 9 for e in events))
        self.assertEqual(events[0].payload["load_ms"], 100)
        self.assertEqual(events[1].payload["elapsed_ms"], 200)
        self.assertIs(player.return_value.play.call_args.args[0], pcm)

    def test_levels_drop_on_full_queue_but_control_events_report_failure(self):
        outbox = queue.Queue(maxsize=1)
        original = AudioEvent("speech_start", generation=1)
        outbox.put(original)
        emit_event(outbox, AudioEvent("mic_level", {"rms": 0.1}))
        emit_event(outbox, AudioEvent("played", {"rms": 0.1}))
        emit_event(outbox, AudioEvent("diagnostic", {"rms": 0.1, "vad": 0.9}))
        self.assertIs(outbox.get_nowait(), original)
        # Avoid waiting the real 1 s timeout: enforce the same queue-full contract.
        blocked = Mock()
        blocked.put.side_effect = queue.Full
        with self.assertRaisesRegex(RuntimeError, "saturée"):
            emit_event(blocked, AudioEvent("transcript", "Important"))
        blocked.put.assert_called_once()

    def test_process_stop_terminates_then_kills_and_discards_channels(self):
        boundary = AudioProcess()
        process, inbox, outbox = Mock(), Mock(), Mock()
        process.is_alive.side_effect = [True, True, False]
        boundary.process, boundary.commands, boundary.outbox = process, inbox, outbox
        boundary.stop()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.join.call_count, 2)
        process.close.assert_called_once()
        for channel in (inbox, outbox):
            channel.cancel_join_thread.assert_called_once()
            channel.close.assert_called_once()
        self.assertIsNone(boundary.process)
        self.assertIsNone(boundary.commands)
        self.assertIsNone(boundary.outbox)


if __name__ == "__main__":
    unittest.main()
