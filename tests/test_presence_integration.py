"""Real PRESENCE/Tk/SQLite integration; audio boundaries are explicit doubles."""
import json
import sqlite3
import tempfile
import time
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jarvis.audio import AudioEvent
from jarvis.config import Settings
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import Fixture, display_available
from tests.test_voice_flow import SimulatedAudioProcess


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class PresenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audio_patch = patch("jarvis.voice_ui.AudioProcess", SimulatedAudioProcess)
        self.audio_patch.start()
        self.addCleanup(self.audio_patch.stop)
        self.store = Store(Path(self.temp.name) / "presence-integration.sqlite3")
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.addCleanup(self.app.close)
        self.voice, self.presence = self.app.voice, self.app.presence
        self.presence.show()

    def pump_until(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(predicate(), self.app.status.get())

    def start_audio_contract(self):
        self.voice.settings = replace(self.voice.settings, acoustic_mode="headphones")
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=True):
            self.voice.toggle()
        mid = self.store.begin_turn(self.app.session_id, "Voix initiale", "local", source="voice")
        self.store.update_response(mid, "Réponse déjà enregistrée.", "complete")
        self.voice.begin_turn(mid, "voice")
        self.voice.chunk("Réponse déjà enregistrée.")
        epoch = self.voice.epoch
        self.voice.speech.events.append(self.played(epoch))
        self.voice.poll()
        self.assertEqual(self.presence.state, "jarvis_speaking")
        self.assertTrue(self.presence.caption_text)
        return mid, epoch

    def played(self, epoch, delay=0):
        return AudioEvent("played", {"rms": 0.2, "wave": [0.1, -0.2, 0.1, 0.05, -0.1],
                                    "text": "Réponse déjà enregistrée.", "fraction": 0.5,
                                    "emitted_at": time.monotonic(), "delay": delay}, epoch)

    def test_sleep_and_wake_discard_old_audio_and_captions_from_prior_epoch(self):
        mid, epoch = self.start_audio_contract()
        self.voice.speech.events.append(self.played(epoch, delay=5))
        self.voice.poll()
        self.assertTrue(self.voice.pending_visuals)
        self.presence.sleep()
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.speech.alive())
        self.assertFalse(self.voice.listening)
        self.assertEqual(self.presence.state, "dormant")
        self.assertFalse(self.voice.pending_visuals)
        self.assertFalse(self.voice.pending_phrases)
        self.assertIsNone(self.presence.after_id)
        self.voice.speech.events.append(self.played(epoch))
        self.voice.poll()
        self.assertEqual(self.presence.state, "dormant")
        self.presence.wake()
        self.voice.speech.events.append(self.played(epoch))
        self.voice.poll()
        self.assertEqual(self.presence.state, "silent")
        self.assertEqual(self.presence.caption_text, "")
        self.assertFalse(self.voice.listening)
        message = self.store.messages(self.app.session_id)[1]
        self.assertEqual(message["id"], mid)
        self.assertEqual(message["content"], "Réponse déjà enregistrée.")
        self.assertEqual(message["status"], "complete")
        self.assertEqual(json.loads(message["metadata"])["audio_status"], "interrupted")

    def test_command_microphone_wakes_presence_and_requires_fresh_permission(self):
        self.presence.sleep()
        self.presence.return_to_command()
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=False) as permission:
            self.voice.listen_button.invoke()
        permission.assert_called_once()
        self.assertEqual(self.presence.state, "silent")
        self.assertFalse(self.voice.listening)
        self.assertFalse(self.voice.capture.alive())
        self.presence.sleep()
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=True) as permission:
            self.voice.listen_button.invoke()
        permission.assert_called_once()
        self.assertTrue(self.voice.listening)
        self.assertTrue(self.voice.capture.alive())
        self.assertEqual(self.presence.state, "thinking")
        self.voice.capture.events.append(AudioEvent("listening"))
        self.voice.poll()
        self.assertEqual(self.presence.state, "listening")
        self.assertIsNone(self.presence.after_id)  # Window remains hidden in COMMAND.

    def test_command_text_wakes_without_microphone_and_returns_to_silence(self):
        with Fixture() as fixture:
            self.app.settings = Settings(endpoint=fixture.endpoint, model="test")
            self.app.models = ["test"]
            self.presence.sleep()
            self.app.input.insert("1.0", "Question depuis COMMAND")
            self.app.send_button.invoke()
            self.assertEqual(self.app.operation, "chat")
            self.assertEqual(self.presence.state, "thinking")
            self.assertFalse(self.voice.listening)
            self.assertFalse(self.voice.capture.alive())
            self.pump_until(lambda: self.app.operation is None)
            self.assertEqual(self.presence.state, "silent")
            self.assertEqual(self.voice.speech.starts, [])
            user, assistant = self.store.messages(self.app.session_id)
            self.assertEqual(user["source"], "text")
            self.assertEqual(assistant["status"], "complete")
            self.assertEqual(assistant["content"], "Bonjour été 🚀")

    def test_storage_callback_error_cannot_resurrect_queued_played_visuals(self):
        _mid, epoch = self.start_audio_contract()
        # Already-consumed IPC notification, waiting for the actual DAC deadline.
        view = self.played(epoch).payload
        self.voice.pending_visuals.append((time.monotonic() - 1, view, epoch))
        self.voice.pending_phrases.append("Phrase désormais obsolète.")
        self.voice.resume_id = self.root.after(350, lambda: None)
        # The handler must recover even while all metadata writes fail.
        with patch.object(self.store, "update_message_metadata", side_effect=sqlite3.OperationalError("disk unavailable")):
            self.app.callback_error(sqlite3.OperationalError, sqlite3.OperationalError("disk unavailable"), None)
        self.assertFalse(self.voice.capture.alive())
        self.assertFalse(self.voice.speech.alive())
        self.assertFalse(self.voice.listening)
        self.assertGreater(self.voice.epoch, epoch)
        self.assertFalse(self.voice.pending_visuals)
        self.assertFalse(self.voice.pending_phrases)
        self.assertFalse(self.voice.reading)
        self.assertIsNone(self.voice.resume_id)
        self.voice.speech.events.append(self.played(epoch))
        self.voice.poll()
        self.assertEqual(self.presence.state, "silent")
        self.assertEqual(self.presence.caption_text, "")
        self.assertEqual(self.presence.operation, "error")


if __name__ == "__main__":
    unittest.main()
