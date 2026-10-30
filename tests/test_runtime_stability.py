"""Bounded software soak: real Tk/SQLite/Canvas, simulated LLM/audio transports.

Default: 100 synthetic conversation/cancel/selected-replay cycles. Set
JARVIS_SOAK_CYCLES=100..1000 for a longer run and JARVIS_SOAK_REPORT to a new JSON
path to retain allocation/RSS observations. No device/model/network is opened.
These finite observations do not prove absence of memory leaks or hardware
performance. Session cleanup keeps the compared archive sizes equal.
"""
from dataclasses import replace
import gc
import json
import os
from pathlib import Path
import platform
import sqlite3
import tempfile
import time
import tkinter as tk
import tracemalloc
import unittest
from unittest.mock import patch

from jarvis.audio import AudioEvent
from jarvis.gpu_benchmark import read_process_memory
from jarvis.ollama import Event
from jarvis.storage import Store
from jarvis.ui import App
from tests import test_cognitive_flow as hud_flows
from tests import test_voice_flow as audio_flows
from tests.test_jarvis import display_available


def widget_count(widget):
    return 1 + sum(widget_count(child) for child in widget.winfo_children())


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class RuntimeStabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jarvis-soak-")
        self.addCleanup(self.temp.cleanup)
        audio_patch = patch("jarvis.voice_ui.AudioProcess", audio_flows.SimulatedAudioProcess)
        audio_patch.start()
        self.addCleanup(audio_patch.stop)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.addCleanup(self.close_app)
        self.voice = self.app.voice
        self.app.worker = hud_flows.EventWorker()
        self.app.models = ["synthetic:local"]
        self.app.settings = replace(self.app.settings, model="synthetic:local")
        self.voice.settings = replace(self.voice.settings, speed=1.1, speech_profile="story")
        self.store.save_settings(self.app.settings)
        self.store.set_preference("voice", self.voice.settings.to_dict())
        self.store.set_preference("lot7_soak_marker", {"preserved": True})
        self.app.presence.set_engine("canvas")
        self.root.update()

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.voice = self.app = self.root = self.store = None
        gc.collect()

    def dispatch(self, *events):
        # Replace the existing poll callback; never create a second UI loop.
        self.app.worker.events.extend(events)
        self.root.after_cancel(self.app.poll_id)
        self.app.poll()

    def observe(self, completed):
        self.root.update_idletasks()
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        memory = read_process_memory()
        return {"completed_cycles": completed,
                "python_current_bytes": current, "python_peak_bytes": peak,
                "rss_bytes": memory.get("rss_current_bytes"),
                "rss_source": memory.get("source"),
                "widgets": widget_count(self.root),
                "pending_callbacks": len(self.root.tk.call("after", "info")),
                "tcl_commands": len(self.root.tk.call("info", "commands")),
                "canvas_items": len(self.app.presence.canvas.find_all()),
                "markdown_region_marks": sum(str(name).startswith("md_region_")
                                             for name in self.app.chat.mark_names()),
                "cognitive_events": len(self.app.cognitive.events()),
                "audio_diagnostics": len(self.voice.diagnostic_events)}

    def test_repeated_conversation_replay_cancel_cleanup_and_restart(self):
        cycles = int(os.environ.get("JARVIS_SOAK_CYCLES", "100"))
        self.assertTrue(100 <= cycles <= 1000, "JARVIS_SOAK_CYCLES must be between 100 and 1000")
        output = Path(os.environ["JARVIS_SOAK_REPORT"]) if os.environ.get("JARVIS_SOAK_REPORT") else None
        if output is not None:
            self.assertFalse(output.exists(), "Choose a new report; existing evidence is preserved")
        samples, logical_baseline = [], None
        completed = cancelled = inference_starts = replay_starts = stale_rejected = 0
        started = time.perf_counter()
        own_trace = not tracemalloc.is_tracing()
        if own_trace:
            tracemalloc.start()
        try:
            for index in range(cycles):
                sid = self.app.session_id
                self.app.send(text="Question synthétique sans donnée personnelle.")
                mid = self.app.message_id
                self.assertIsNotNone(mid)
                self.assertEqual(len(self.app.worker.starts), 1)
                inference_starts += len(self.app.worker.starts)
                self.dispatch(Event("chunk", "Avant. **Passage choisi 😊**. Après."))
                if index % 2:
                    self.app.cancel()
                    cancelled += 1
                    expected_status = "cancelled"
                else:
                    self.dispatch(Event("done", {}))
                    completed += 1
                    expected_status = "complete"
                self.assertEqual(self.store.message(mid)["status"], expected_status)
                region = next(region for region in self.app.markdown.regions if region.message_id == mid)
                chosen = "Passage choisi 😊"
                left = region.text.index(chosen)
                self.app.chat.tag_remove("sel", "1.0", "end")
                self.app.chat.tag_add("sel", self.app.markdown.offset(region.start, region.text[:left]),
                                      self.app.markdown.offset(region.start, region.text[:left + len(chosen)]))
                selection = self.app.markdown.resolve_selection()
                self.assertTrue(self.app.selection_action("read", selection))
                replay_starts += len(self.voice.speech.starts)
                self.assertEqual(len(self.voice.speech.starts), 1)
                self.assertFalse(self.voice.capture.starts)
                phrase = next(command for command in self.voice.speech.commands
                              if command is not None and hasattr(command, "original"))
                self.assertNotIn("😊", str(phrase))
                now = time.monotonic()
                view = {"text": phrase.display_text, "spoken_text": str(phrase),
                        "original_start": phrase.start, "original_end": phrase.end,
                        "response_id": self.voice.epoch, "segment_id": phrase.segment_id,
                        "fraction": .5, "rms": .1, "wave": [.1, -.1],
                        "emitted_at": now - .01, "started_at": now - .01, "delay": 0.}
                old_epoch = self.voice.epoch
                self.voice.speech.events.append(AudioEvent("played", view, old_epoch))
                self.voice.poll()
                self.assertEqual(self.app.cognitive.snapshot()["primary"], "speaking")
                self.voice.cancel_speech()
                revision = self.app.cognitive.revision
                self.voice.speech.events.append(AudioEvent("played", view, old_epoch))
                self.voice.poll()
                self.assertEqual(self.app.cognitive.revision, revision)
                stale_rejected += 1
                self.assertFalse(self.voice.pending_visuals)
                self.assertFalse(self.voice.pending_segment_ends)
                self.assertFalse(self.voice.pending_phrases)
                self.assertIsNone(self.voice.visual_end_pending)
                self.assertIsNone(self.voice.replay_source)
                self.assertIsNone(self.voice.resume_id)
                self.assertFalse(self.voice.speech.alive())
                self.assertFalse(self.voice.capture.alive())
                self.assertFalse(self.app.worker.alive())
                self.assertFalse(self.app.worker.events)
                self.assertEqual(len(self.app.worker.starts), 1, "Replay must not launch inference")
                self.assertLessEqual(len(self.app.cognitive.events()), 64)
                self.assertLessEqual(len(self.voice.diagnostic_events), 32)
                self.assertLessEqual(len(self.voice.submitted_output), 8)
                self.assertLessEqual(len(self.app.presence._semantic_cues), 64)
                self.assertLessEqual(len(self.app.presence._semantic_plans), 64)
                # Clear the test transports' recording lists; they are logs of
                # this fixture, not production queues retained by JARVIS.
                self.voice.speech.commands.clear()
                self.voice.speech.starts.clear()
                self.app.worker.starts.clear()
                self.app.new_session()
                self.store.delete_session(sid)
                self.app.reload_history()
                self.assertEqual(len(self.store.sessions()), 1)
                self.assertFalse(self.store.messages(self.app.session_id))
                self.assertFalse(self.app.markdown.regions)
                self.assertIsNone(self.app.operation)
                if (index + 1) % 20 == 0 or index + 1 == cycles:
                    sample = self.observe(index + 1)
                    samples.append(sample)
                    # Compare the same quiescent state after first-cohort warmup.
                    logical = {key: sample[key] for key in ("widgets", "pending_callbacks",
                               "tcl_commands", "canvas_items", "markdown_region_marks")}
                    if logical_baseline is None:
                        logical_baseline = logical
                    self.assertEqual(logical, logical_baseline)
            self.assertEqual(inference_starts, cycles)
            self.assertEqual(replay_starts, cycles)
            self.assertEqual(self.store.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            # Closing mid-generation must retain a partial archive and release
            # the actual SQLite connection and both Tk-owned polling callbacks.
            self.app.send(text="Dernière question synthétique.")
            self.dispatch(Event("chunk", "Fragment conservé à la fermeture."))
            sid, mid, database = self.app.session_id, self.app.message_id, self.store.db
            self.root.update_idletasks()
            registered = set(self.root.tk.call("after", "info"))
            self.app.close()
            self.assertTrue(self.app.closed)
            self.assertFalse(self.app.worker.alive())
            self.assertFalse(self.voice.speech.alive())
            self.assertFalse(self.voice.capture.alive())
            self.assertFalse(registered & set(self.root.tk.call("after", "info")))
            with self.assertRaises(sqlite3.ProgrammingError):
                database.execute("SELECT 1")
            self.store = Store(self.path)
            self.root = tk.Tk()
            self.app = App(self.root, self.store, refresh=False)
            self.voice = self.app.voice
            self.assertIsNone(self.app.operation)
            self.assertIsNone(self.app.worker.process)
            self.assertFalse(self.voice.capture.starts)
            self.assertEqual(self.store.message(mid)["content"], "Fragment conservé à la fermeture.")
            self.assertEqual(self.store.message(mid)["status"], "cancelled")
            self.assertEqual(self.store.message(mid)["session_id"], sid)
            self.assertEqual(self.store.get_preference("lot7_soak_marker"), {"preserved": True})
            self.assertEqual(self.voice.settings.speed, 1.1)
            self.assertEqual(self.voice.settings.speech_profile, "story")
            self.assertEqual(self.app.settings.model, "synthetic:local")
            self.assertEqual(self.store.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            report = {"scope": __doc__, "platform": platform.platform(),
                      "tk_patchlevel": self.root.tk.call("info", "patchlevel"),
                      "cycles": cycles, "completed_turns": completed, "cancelled_turns": cancelled,
                      "requested_inferences": inference_starts, "local_replays": replay_starts,
                      "stale_pcm_events_rejected": stale_rejected,
                      "seconds": time.perf_counter() - started,
                      "observations": samples, "restart_fragment_and_preferences": "preserved",
                      "sqlite_integrity": "ok", "device_model_network_calls": 0,
                      "limitations": "Finite synthetic event soak; not an acoustic/RTX benchmark or proof of no memory leak."}
            if output is not None:
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("x", encoding="utf-8") as stream:
                    json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.write("\n")
        finally:
            if own_trace:
                tracemalloc.stop()
