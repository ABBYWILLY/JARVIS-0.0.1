"""Real PCM summaries and Tk routing with explicit device/STT doubles.

No test here validates the user's physical Windows microphone.
"""
import math
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from jarvis.audio import AudioEvent, signal_view
from jarvis.presence import PresenceModel, SIGNAL_LIFETIME
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available
from tests.test_voice_flow import SimulatedAudioProcess


PCM = tuple(.03 * math.sin(2 * math.pi * 205 * n / 16000) for n in range(512))


class ListeningSignalTests(unittest.TestCase):
    def test_listening_geometry_uses_real_pcm_without_claiming_vad_speech(self):
        model = PresenceModel()
        model.update_event("listening", signal_view(PCM), now=10.)
        points = model.frame(1000, 700, now=10.01)
        self.assertEqual(model.state, "listening")
        self.assertGreater(max(y for _, y in points) - min(y for _, y in points), 5.)
        self.assertTrue(model.needs_animation(now=10.01))
        self.assertEqual(points[0][1], 350.)
        self.assertEqual(points[-1][1], 350.)

    def test_listening_cache_updates_with_pcm_then_expires_to_flat_without_a_carrier(self):
        model = PresenceModel()
        model.update_event("listening", signal_view(PCM), now=10.)
        first = model.target_geometry(1000, 700, now=10.01)
        changed = tuple(sample * .2 for sample in PCM)
        model.update_event("listening", signal_view(changed), now=10.05)
        second = model.target_geometry(1000, 700, now=10.06)
        self.assertNotEqual(first, second)
        flat = model.frame(1000, 700, now=10.05 + SIGNAL_LIFETIME + .01)
        self.assertTrue(all(y == 350. for _, y in flat))
        self.assertFalse(model.needs_animation(now=11.))
        model.update_event("listening", {"rms": 0., "wave": [1., -1.]}, now=12.)
        self.assertTrue(all(y == 350. for _, y in model.frame(1000, 700, now=12.)))


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class CapturePresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch("jarvis.voice_ui.AudioProcess", SimulatedAudioProcess)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = Store(Path(self.temp.name) / "capture-ui.sqlite3")
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.addCleanup(self.app.close)
        self.root.after_cancel(self.app.poll_id)
        self.voice, self.presence = self.app.voice, self.app.presence
        self.presence.show()
        self.root.update()
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=True):
            self.voice.toggle()

    def events(self, *events):
        self.voice.capture.events.extend(events)
        self.voice.poll()

    def test_pcm_below_vad_reaches_presence_and_keeps_explicit_listening_state(self):
        self.events(AudioEvent("listening"), AudioEvent("mic_level", {
            **signal_view(PCM), "speaking": False, "vad": .05}))
        self.assertEqual(self.presence.state, "listening")
        self.assertAlmostEqual(self.presence.model.signal["rms"], signal_view(PCM)["rms"])
        # Allow the existing fast attack one frame, without sleeping or depending
        # on machine speed. This is still inside the real summary's expiry time.
        with patch("jarvis.presence.time.monotonic", return_value=self.presence.model.signal_at + .04):
            self.presence._render()
        coordinates = self.presence.canvas.coords(self.presence.paths[-1])
        self.assertGreater(max(coordinates[1::2]) - min(coordinates[1::2]), 5.)
        self.assertEqual(self.voice.microphone_state, "open")

    def test_suspended_stopped_and_stale_microphone_events_do_not_revive_the_wave(self):
        self.voice.heard = 4
        before = self.voice.epoch
        self.voice.set_mic_state("suspended", "Lecture haut-parleurs")
        self.events(AudioEvent("speech_start", generation=5),
                    AudioEvent("mic_level", {**signal_view(PCM), "speaking": True}, 5))
        self.assertEqual(self.voice.epoch, before)
        self.assertEqual(self.voice.microphone_state, "suspended")
        self.assertNotEqual(self.presence.state, "user_speaking")
        self.voice.set_mic_state("open")
        self.events(AudioEvent("mic_level", {**signal_view(PCM), "speaking": True}, 3))
        self.assertNotEqual(self.presence.state, "user_speaking")
        # The ignored start still advanced the worker epoch. Quiet real PCM must
        # become visible on resume, while its discarded transcript stays rejected.
        self.events(AudioEvent("mic_level", {**signal_view(PCM), "speaking": False}, 5),
                    AudioEvent("transcript", "Tour suspendu", 5))
        self.assertEqual(self.presence.state, "listening")
        self.assertAlmostEqual(self.presence.model.signal["rms"], signal_view(PCM)["rms"])
        self.assertEqual(self.voice.heard, 4)
        self.assertNotIn("Tour suspendu", self.app.input.get("1.0", "end"))
        self.voice.stop_listening()
        self.events(AudioEvent("speech_start", generation=6),
                    AudioEvent("mic_level", {**signal_view(PCM), "speaking": True}, 6))
        self.assertEqual(self.presence.state, "silent")
        self.assertFalse(self.voice.listening)

    def test_diagnostic_no_pcm_is_unknown_not_zero_and_age_keeps_increasing(self):
        self.voice.open_diagnostics()
        with patch("jarvis.voice_ui.time.monotonic", return_value=100.):
            self.events(AudioEvent("capture_stage", {"stage": "ouverture microphone", "opened_device": None}),
                        AudioEvent("diagnostic", {"rms": None, "vad": None, "last_frame_at": None,
                                   "capture_status": "waiting_for_pcm", "state": "attente PCM"}))
        self.assertIn("—", self.voice.diagnostic_summary.get())
        self.assertNotIn("RMS : 0.00000", self.voice.diagnostic_summary.get())
        self.assertIn("Aucune trame", self.voice.diagnostic_summary.get())
        with patch("jarvis.voice_ui.time.monotonic", return_value=103.):
            self.voice.poll()
        self.assertIn("3.0 s", self.voice.diagnostic_summary.get())
        self.assertTrue(self.voice.listening)

    def test_new_capture_does_not_present_a_previous_sessions_transcript_as_current(self):
        self.voice.stt_details = {"result": "Ancienne transcription"}
        self.voice.reference_result = "Ancien WER"
        self.voice.stop_listening()
        with patch("jarvis.voice_ui.messagebox.askyesno", return_value=True):
            self.voice.toggle()
        self.assertEqual(self.voice.stt_details, {})
        self.assertEqual(self.voice.reference_result, "")
        self.assertNotIn("Transcription reçue", self.voice.capture_assessment(100.))

    def test_real_rms_vad_device_and_stt_error_are_visible_and_not_overwritten_by_heartbeat(self):
        self.voice.open_diagnostics()
        self.voice.heard = 2
        with patch("jarvis.voice_ui.time.monotonic", return_value=100.):
            self.events(AudioEvent("diagnostic", {"rms": .02, "vad": .12, "last_frame_at": 100.,
                            "selected_device": "MME | USB Condenser", "capture_status": "receiving_pcm",
                            "opened_device": {"name": "USB Condenser", "index": 7, "hostapi": "MME"},
                            "native_rate": 48000, "rate": 16000, "frame_samples": 512}),
                        AudioEvent("stt_error", {"error": "RuntimeError: modèle inaccessible", "elapsed_ms": 22}, 2))
        text = self.voice.diagnostic_text.get("1.0", "end") + self.voice.diagnostic_summary.get()
        self.assertIn("USB Condenser", text)
        self.assertIn("MME", text)
        self.assertIn("0.02000", text)
        self.assertIn("modèle inaccessible", text)
        self.assertIn("48000", text)
        self.assertIn("16000", text)
        self.assertGreater(float(self.voice.rms_meter.cget("value")), 0.)
        with patch("jarvis.voice_ui.time.monotonic", return_value=103.):
            self.events(AudioEvent("diagnostic", {"rms": None, "vad": None, "last_frame_at": 100.,
                        "capture_status": "waiting_for_pcm"}, 2))
        text = self.voice.diagnostic_text.get("1.0", "end")
        self.assertIn("modèle inaccessible", text)
        self.assertIn("3.0 s", self.voice.diagnostic_summary.get())
        self.assertTrue(self.voice.listening)


if __name__ == "__main__":
    unittest.main()
