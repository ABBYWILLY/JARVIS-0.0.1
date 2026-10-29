"""Owner/UI contracts over real Tk/SQLite and explicitly doubled audio/LLM IPC.

These tests observe the same application event paths as live operation. They
do not claim a physical microphone, Piper inference, Ollama or acoustic timing.
"""
from dataclasses import replace
import json
import time
import unittest
from unittest.mock import Mock, patch

from jarvis.audio import AudioEvent
from jarvis.cognitive_state import CognitiveHudSettings
from jarvis.ollama import Event
from tests import test_voice_flow as flows
from tests.test_jarvis import display_available


class EventWorker:
    """Bounded test input replaces process transport, never inventing metrics."""
    def __init__(self):
        self.events = []
        self.starts = []
        self.running = False

    def start(self, operation, settings, messages=None):
        self.starts.append((operation, settings, messages))
        self.running = True

    def poll(self):
        events, self.events = self.events, []
        return events

    def alive(self):
        return self.running

    def stop(self):
        self.running = False
        self.events.clear()


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class CognitiveFlowTests(unittest.TestCase):
    setUp = flows.VoiceFlowTests.setUp
    close_app = flows.VoiceFlowTests.close_app
    activate = flows.VoiceFlowTests.activate

    def configured_request(self, *, listening=False):
        self.app.worker = EventWorker()
        self.app.settings = replace(self.app.settings, model="local:4b")
        self.app.models = ["local:4b"]
        if listening:
            self.activate("headphones")
            self.voice.capture.events.append(AudioEvent("listening", {"capture_status": "open"}))
            self.voice.poll()
        self.app.send(text="Explique ce calcul en français.")
        return self.app.message_id

    def poll_app(self):
        # App owns its existing 40 ms poll. Manual dispatch must replace that
        # one callback, never create a concurrent polling loop in a test.
        if self.app.poll_id is not None:
            self.root.after_cancel(self.app.poll_id)
        self.app.poll()

    def played(self, *, delay=0., segment=1, text="Une phrase réelle."):
        now = time.monotonic()
        view = {"text": text, "spoken_text": text, "original_start": 0,
                "original_end": len(text), "fraction": .5, "rms": .1,
                "wave": [.1, -.1], "emitted_at": now, "delay": delay,
                "started_at": now + delay, "response_id": self.voice.epoch,
                "segment_id": segment}
        self.voice.speech.events.append(AudioEvent("played", view, self.voice.epoch))
        self.voice.poll()
        return view

    def test_request_context_wait_and_stream_are_observed_without_new_calls(self):
        mid = self.configured_request()
        state = self.app.cognitive.snapshot()
        self.assertEqual(state["turn_id"], mid)
        self.assertEqual(state["model"], "local:4b")
        self.assertEqual(state["primary"], "waiting")
        self.assertGreater(state["budget"], 0)
        self.assertGreaterEqual(state["metrics"]["context_ms"], 0)
        events = [(item["activity"], item["active"]) for item in self.app.cognitive.events()]
        self.assertIn(("context", True), events)
        self.assertIn(("context", False), events)
        self.assertIn(("context_bound", True), events)
        self.assertIn(("waiting", True), events)
        self.app.worker.events.append(Event("chunk", "Voici une réponse.", metadata={"ttft_seconds": .123}))
        self.poll_app()
        state = self.app.cognitive.snapshot()
        self.assertEqual(state["primary"], "generating")
        self.assertNotIn("waiting", state["activities"])
        self.assertEqual(state["metrics"]["ttft_seconds"], .123)
        self.assertNotIn("eval_count", state["metrics"])
        self.assertEqual(len(self.app.worker.starts), 1)
        self.assertEqual(self.store.message(mid)["content"], "Voici une réponse.")

    def test_audio_overlaps_generation_and_speaking_waits_for_pcm_deadline(self):
        self.configured_request(listening=True)
        # Warm loading is observable concurrently, rather than pretending the
        # local inference and Piper are sequential operations.
        self.assertEqual(set(self.app.cognitive.snapshot()["activities"]),
                         {"synthesis", "waiting", "listening"})
        self.voice.speech.events.append(AudioEvent("tts_ready", {"load_ms": 20}, self.voice.epoch))
        self.voice.poll()
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "waiting")
        self.app.worker.events.append(Event("chunk", "Une phrase réelle."))
        self.poll_app()
        state = self.app.cognitive.snapshot()
        self.assertEqual(set(state["activities"]), {"generating", "synthesis", "listening"})
        self.assertEqual(state["primary"], "synthesis")
        view = self.played(delay=2.)
        self.assertNotIn("speaking", self.app.cognitive.snapshot()["activities"])
        self.voice._drain_visuals(view["emitted_at"] + 2.01)
        state = self.app.cognitive.snapshot()
        self.assertEqual(state["primary"], "speaking")
        self.assertIn("generating", state["activities"])
        self.assertNotIn("synthesis", state["activities"])
        self.assertEqual(len(self.voice.speech.starts), 1)

    def test_inference_finish_keeps_actual_audio_until_segment_and_dac_end(self):
        mid = self.configured_request(listening=True)
        self.app.worker.events.append(Event("chunk", "Une phrase réelle."))
        self.poll_app()
        view = self.played()
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "speaking")
        self.app.worker.events.append(Event("done", {"eval_count": 6, "eval_duration": 2_000_000_000}))
        self.poll_app()
        self.assertIsNone(self.app.operation)
        self.assertEqual(self.store.message(mid)["status"], "complete")
        state = self.app.cognitive.snapshot()
        self.assertEqual(state["primary"], "speaking")
        self.assertNotIn("generating", state["activities"])
        self.assertEqual(state["metrics"]["tokens_per_second"], 3.)
        self.voice.speech.events.extend([
            AudioEvent("segment_done", {**view, "completed_at": time.monotonic()}, self.voice.epoch),
            AudioEvent("speech_done", generation=self.voice.epoch)])
        self.voice.poll()
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "listening")
        self.assertNotIn("speaking", self.app.cognitive.snapshot()["activities"])
        self.assertNotIn("synthesis", self.app.cognitive.snapshot()["activities"])

    def test_cancel_invalidates_old_audio_observations_and_preserves_archive(self):
        mid = self.configured_request(listening=True)
        self.app.worker.events.append(Event("chunk", "Réponse partielle."))
        self.poll_app()
        old_epoch, generation = self.voice.epoch, self.app.cognitive.generation
        view = self.played(delay=2.)
        self.app.cancel()
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "cancelled")
        self.assertEqual(self.store.message(mid)["content"], "Réponse partielle.")
        self.assertEqual(self.store.message(mid)["status"], "cancelled")
        self.assertFalse(self.voice.pending_visuals)
        before = self.app.cognitive.revision
        self.assertFalse(self.app.observe_audio_activity("speaking", epoch=old_epoch, generation=generation))
        self.voice.speech.events.append(AudioEvent("played", view, old_epoch))
        self.voice.poll()
        self.assertEqual(self.app.cognitive.revision, before)
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "cancelled")
        self.app.begin_audio_observation(mid)
        self.assertFalse(self.app.observe_audio_activity("error", epoch=self.voice.epoch, generation=generation))

    def test_microphone_loading_open_vad_and_stt_error_have_observable_boundaries(self):
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "idle")
        self.activate("headphones")
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "audio_loading")
        self.assertNotIn("listening", self.app.cognitive.snapshot()["activities"])
        self.voice.capture.events.append(AudioEvent("listening", {"capture_status": "open"}))
        self.voice.poll()
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "listening")
        self.voice.capture.events.append(AudioEvent("speech_start", generation=1))
        self.voice.poll()
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "user_speaking")
        self.voice.capture.events.append(AudioEvent("transcribing", generation=1))
        self.voice.poll()
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "transcribing")
        self.voice.capture.events.append(AudioEvent("stt_error", {"error": "Local STT failure", "elapsed_ms": 45}, 1))
        self.voice.poll()
        self.assertEqual(self.app.cognitive.snapshot()["primary"], "error")
        self.assertIn("échec", self.voice.status.get().casefold())
        self.assertNotIn("Local STT failure", json.dumps(self.app.cognitive.events()))

    def test_hud_reuses_owner_revision_and_existing_poll_without_sqlite_reads(self):
        panel = self.app.cognitive_view
        self.app.presence.window = None
        self.app.presence._gpu_visible = False
        self.root.update_idletasks()
        panel.refresh(force=True)
        before_callbacks = tuple(self.root.tk.call("after", "info"))
        with patch.object(self.store, "get_preference", side_effect=AssertionError("HUD read SQLite")), \
             patch.object(self.store, "messages", side_effect=AssertionError("HUD queried archive")), \
             patch.object(self.app.cognitive, "snapshot", wraps=self.app.cognitive.snapshot) as snapshot:
            for _ in range(100):
                panel.refresh()
            snapshot.assert_not_called()
        self.assertEqual(tuple(self.root.tk.call("after", "info")), before_callbacks)
        revision = self.app.cognitive.revision
        self.app.cognitive.update("listening")
        with patch.object(self.app.cognitive, "snapshot", wraps=self.app.cognitive.snapshot) as snapshot:
            panel.refresh()
            self.assertEqual(snapshot.call_count, 1)
        self.assertGreater(self.app.cognitive.revision, revision)
        self.assertEqual(panel.text.get(), "J’écoute")

    def test_hidden_hud_does_not_project_or_recompute_and_restores_latest_state(self):
        panel = self.app.cognitive_view
        panel.refresh(force=True)
        self.app.presence.window = None
        self.app.presence._gpu_visible = False
        self.root.withdraw()
        self.root.update_idletasks()
        self.app.cognitive.update("transcribing")
        with patch.object(self.app.cognitive, "snapshot", wraps=self.app.cognitive.snapshot) as snapshot:
            for _ in range(100):
                panel.refresh()
            snapshot.assert_not_called()
        self.root.deiconify()
        self.root.update_idletasks()
        panel.refresh()
        self.assertEqual(panel.text.get(), "Transcription en cours")

    def test_editor_applies_one_preference_preserves_future_keys_and_has_no_timer(self):
        panel = self.app.cognitive_view
        panel.saved = {"future_navigation": "keep"}
        before_model = self.store.settings()
        before_voice = self.store.get_preference("voice")
        before_callbacks = tuple(self.root.tk.call("after", "info"))
        dialog = panel.open()
        self.root.update_idletasks()
        self.assertIs(panel.open(), dialog)
        self.assertEqual(set(dialog.controls), set(CognitiveHudSettings().to_dict()))
        self.root.setvar(dialog.controls["level"].cget("textvariable"), "Diagnostic")
        self.root.setvar(dialog.controls["enabled"].cget("variable"), False)
        dialog.save_button.invoke()
        saved = self.store.get_preference("cognitive_hud")
        self.assertEqual(saved, {**CognitiveHudSettings(enabled=False, level="diagnostic").to_dict(),
                                 "future_navigation": "keep"})
        self.assertEqual(panel.settings, CognitiveHudSettings(enabled=False, level="diagnostic"))
        self.assertEqual(panel.text.get(), "")
        self.assertFalse(panel.label.winfo_manager())
        self.assertEqual(self.store.settings(), before_model)
        self.assertEqual(self.store.get_preference("voice"), before_voice)
        self.assertEqual(tuple(self.root.tk.call("after", "info")), before_callbacks)

    def test_editor_cancel_does_not_persist_draft_or_duplicate_readers(self):
        panel = self.app.cognitive_view
        dialog = panel.open()
        self.root.setvar(dialog.controls["level"].cget("textvariable"), "Diagnostic")
        dialog.destroy()
        self.assertIsNone(self.store.get_preference("cognitive_hud"))
        self.assertEqual(panel.settings, CognitiveHudSettings())
        next_dialog = panel.open()
        self.assertIsNot(next_dialog, dialog)
        self.assertEqual(self.root.getvar(next_dialog.controls["level"].cget("textvariable")), "Minimal")
        next_dialog.destroy()

    def test_disabled_diagnostic_hud_has_no_periodic_work_and_close_releases_tk(self):
        panel = self.app.cognitive_view
        panel.settings = replace(panel.settings, enabled=False, level="diagnostic")
        panel.refresh(force=True)
        panel.last_at -= 100
        with patch.object(self.app.cognitive, "snapshot") as snapshot:
            for _ in range(100):
                panel.refresh()
        snapshot.assert_not_called()
        dialog = panel.open()
        with patch.object(dialog, "destroy", wraps=dialog.destroy) as destroy:
            self.app.close()
        destroy.assert_called_once()
        self.assertIsNone(panel.text)
        self.assertIsNone(panel.app)
        self.assertIsNone(panel.window)
        panel.close()  # Shutdown is idempotent, with no Tcl call after destruction.
