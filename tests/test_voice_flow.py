"""Voice contracts: simulated audio events, real Tk/SQLite and HTTP LLM fixture.

These tests do not validate a microphone, audible playback, or model inference.
"""
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
        self.addCleanup(self.app.close)
        self.voice = self.app.voice
        self.app.presence = Mock()

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

    def test_microphone_closed_until_explicit_acceptance_and_toggle_stops_it(self):
        self.assertFalse(self.voice.listening)

        self.assertEqual(self.voice.capture.starts, [])
        self.assertEqual(self.voice.speech.starts, [])
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=False) as permission:
            self.voice.toggle()
        permission.assert_called_once()
        self.assertFalse(self.voice.listening)
        self.assertEqual(self.voice.capture.starts, [])
        self.activate()
        self.assertEqual(len(self.voice.capture.starts), 1)
        with patch("jarvis.voice_ui.messagebox.askyesno") as permission:
            self.voice.toggle()
        permission.assert_not_called()
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.listening)

    def test_rejected_voice_send_keeps_transcript_in_composer(self):
        self.activate()
        self.voice.capture.events.extend([
            AudioEvent("speech_start", generation=1),
            AudioEvent("transcript", "Parole sans modèle sélectionné", generation=1),
        ])
        self.voice.poll()
        self.assertIsNone(self.app.operation)
        self.assertIn("Parole sans modèle sélectionné", self.app.input.get("1.0", "end"))

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
            self.assertEqual(self.voice.speech.commands, ["Bonjour été 🚀", None])
            self.assertIn({"kind": "mute", "value": True}, self.voice.capture.commands)
            self.assertEqual(json.loads(assistant["metadata"])["tts_engine"], "piper")
            self.voice.speech.events.append(AudioEvent("speech_done", generation=self.voice.epoch))
            self.voice.poll()
            self.assertEqual(json.loads(self.store.messages(self.app.session_id)[1]["metadata"])["audio_status"], "complete")
            self.assertFalse(self.voice.speech.alive())
            self.pump_until(lambda: self.voice.capture.commands[-1] == {"kind": "mute", "value": False})

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
    def test_levels_drop_on_full_queue_but_control_events_report_failure(self):
        outbox = queue.Queue(maxsize=1)
        original = AudioEvent("speech_start", generation=1)
        outbox.put(original)
        emit_event(outbox, AudioEvent("mic_level", {"rms": 0.1}))
        emit_event(outbox, AudioEvent("played", {"rms": 0.1}))
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
        process.is_alive.side_effect = [True, True]
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
