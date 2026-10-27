"""Explicit synthetic rehearsal through the production Canvas, never hardware."""
import math
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis.presence import PresenceView
from jarvis.presence_demo import DEMO_LABEL, PREVIEW_SECONDS, STAGES, DemoController, synthetic_signal
from jarvis.storage import Store
from tests.test_jarvis import display_available


class DemoSignalTests(unittest.TestCase):
    def test_invalid_direct_state_is_rejected_before_touching_the_view(self):
        for stage in (-1, len(STAGES), "thinking", True, 1.5):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                DemoController(object()).start(stage=stage)

    def test_synthetic_pcm_is_explicit_deterministic_bounded_and_has_true_rms(self):
        self.assertIn("synthétique", DEMO_LABEL)
        for elapsed in (0., .2, 1., 8., 100.):
            signal = synthetic_signal(elapsed)
            self.assertEqual(signal, synthetic_signal(elapsed))
            self.assertEqual(len(signal["wave"]), 97)
            self.assertTrue(all(-1 <= value <= 1 for value in signal["wave"]))
            self.assertAlmostEqual(signal["rms"], math.sqrt(sum(x*x for x in signal["wave"]) / 97))
        self.assertNotEqual(synthetic_signal(0.), synthetic_signal(.2))

    def test_demo_rejects_real_work_or_hidden_window_before_any_side_effect(self):
        for listening, operation, state, visible in (
                (True, None, "silent", True), (False, "generate", "silent", True),
                (False, None, "thinking", True), (False, None, "dormant", True),
                (False, None, "silent", False)):
            view = SimpleNamespace(app=SimpleNamespace(voice=SimpleNamespace(listening=listening),
                                   operation=operation), state=state, _visible=lambda: visible,
                                   clear_preview=Mock())
            self.assertFalse(DemoController(view).start())
            view.clear_preview.assert_not_called()
            self.assertFalse(hasattr(view, "_demo"))


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class DemoCanvasTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = Store(Path(self.temporary.name) / "demo.sqlite3")
        self.addCleanup(self.store.close)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.voice = SimpleNamespace(listening=False, microphone_state="disabled", toggle=Mock(),
                                     emergency=Mock(), stop_listening=Mock())
        self.app = SimpleNamespace(root=self.root, store=self.store, voice=self.voice,
                                   operation=None, font_family="DejaVu Sans")
        self.view = PresenceView(self.app)
        self.addCleanup(self.view.close)
        self.view.show()
        self.root.update()
        self.now = 100.
        self.clock_patch = patch("jarvis.presence.time.monotonic", side_effect=lambda: self.now)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.demo = DemoController(self.view, clock=lambda: self.now)
        self.addCleanup(self.demo.stop)
        self.history = []
        self.demo.on_stage = lambda index, _label: self.history.append(index)

    def advance(self, elapsed):
        self.now = 100. + elapsed
        if self.demo.after_id is not None:
            self.root.after_cancel(self.demo.after_id)
            self.demo.after_id = None
        self.demo._tick()

    def test_all_stages_use_one_existing_canvas_morph_terminal_emoji_and_return_flat(self):
        canvas, items = self.view.canvas, self.view.canvas.find_all()
        with patch.object(self.store, "set_preference") as persist:
            self.assertTrue(self.demo.start())
            edge = 0.
            for index, (label, duration, state) in enumerate(STAGES):
                self.advance(edge + .01)
                self.assertEqual(self.demo.stage, index)
                self.assertIs(self.view.canvas, canvas)
                self.assertEqual(canvas.find_all(), items)
                self.assertIn(DEMO_LABEL, self.view._preview_text)
                self.assertIn("PCM SYNTHÉTIQUE", self.view.state_label.cget("text"))
                self.assertEqual(self.voice.microphone_state, "disabled")
                if index in (1, 3, 4, 6):
                    self.assertGreater(self.view.model.signal["rms"], 0.)
                if index == 5:
                    self.assertEqual(self.view.semantic.family, "smile")
                    self.advance(edge + .55)
                    points = canvas.coords(self.view.paths[-1])
                    self.assertGreater(max(points[1::2]) - min(points[1::2]), 30)
                    self.assertIn("triggered", self.view.semantic_diagnostics())
                edge += duration
            self.advance(edge + .01)
            persist.assert_not_called()
        self.assertEqual(self.history, list(range(8)))
        self.assertEqual(self.demo.reason, "completed")
        self.assertFalse(self.demo.active)
        self.assertIsNone(self.demo.after_id)
        self.assertIsNone(self.view._preview_text)
        self.assertFalse(self.view.semantic.active)
        self.assertEqual(self.view.model.signal["rms"], 0.)
        self.now += 4.
        self.view._render()
        points = canvas.coords(self.view.paths[-1])
        self.assertLess(max(points[1::2]) - min(points[1::2]), 1e-7)
        self.assertIsNone(self.view.after_id)
        self.voice.toggle.assert_not_called()

    def test_each_direct_state_is_bounded_and_returns_to_flat_without_playing_other_stages(self):
        canvas, items = self.view.canvas, self.view.canvas.find_all()
        original = self.store.get_preference("presence")
        for stage, (_, _, state) in enumerate(STAGES[:7]):
            with self.subTest(stage=stage):
                self.now = 100.
                self.history.clear()
                self.assertTrue(self.demo.start(stage=stage))
                self.advance(.25)
                self.assertEqual(self.demo.stage, stage)
                self.assertEqual(self.history, [stage])
                self.assertIs(self.view.canvas, canvas)
                self.assertEqual(canvas.find_all(), items)
                self.assertIn("PCM SYNTHÉTIQUE", self.view.state_label.cget("text"))
                self.assertEqual(self.view.state, "silent" if stage == 5 else state)
                if stage == 5:
                    self.assertEqual(self.view.semantic.family, "smile")
                timer = self.demo.after_id
                self.advance(PREVIEW_SECONDS + .01)
                self.assertFalse(self.demo.active)
                self.assertEqual(self.demo.reason, "completed")
                self.assertIsNone(self.demo.after_id)
                self.assertNotIn(timer, self.root.tk.call("after", "info"))
                self.assertEqual(self.view.state, "silent")
                self.assertEqual(self.view.model.signal["rms"], 0.)
                self.assertEqual(self.view._semantic_response, -1)
        self.assertEqual(self.store.get_preference("presence"), original)
        self.voice.toggle.assert_not_called()

    def test_real_event_cancels_timer_and_restores_response_ids_before_receiving_pcm(self):
        self.view._semantic_response = 7
        self.assertTrue(self.demo.start())
        emoji_start = sum(stage[1] for stage in STAGES[:5])
        self.advance(emoji_start + .01)
        self.assertTrue(self.view.semantic.active)
        timer = self.demo.after_id
        self.assertGreater(self.view._semantic_response, 7)
        incoming = {"rms": .09, "wave": [.1] * 48}
        self.view.update_event("user_speaking", incoming)
        self.assertFalse(self.demo.active)
        self.assertEqual(self.view._semantic_response, 7)
        self.assertEqual(self.view.state, "user_speaking")
        self.assertAlmostEqual(self.view.model.signal["rms"], .09)
        self.assertFalse(self.view.semantic.active)
        self.assertIsNone(self.demo.after_id)
        self.assertNotIn(timer, self.root.tk.call("after", "info"))

    def test_hidden_or_closed_demo_leaves_no_rehearsal_callbacks_and_real_text_has_priority(self):
        self.assertTrue(self.demo.start())
        timer = self.demo.after_id
        self.view.begin_response()
        self.assertFalse(self.demo.active)
        self.assertNotIn(timer, self.root.tk.call("after", "info"))
        self.assertTrue(self.demo.start())
        timer = self.demo.after_id
        self.view.window.withdraw()
        self.root.update()
        self.assertFalse(self.demo.active)
        self.assertNotIn(timer, self.root.tk.call("after", "info"))
        self.view.show()
        self.root.update()
        self.assertTrue(self.demo.start())
        timer = self.demo.after_id
        self.view.close()
        self.assertFalse(self.demo.active)
        self.assertIsNone(self.demo.after_id)
        self.assertNotIn(timer, self.root.tk.call("after", "info"))

    def test_reduced_motion_keeps_symbol_static_and_repeated_runs_do_not_accumulate_timers(self):
        self.view.set_options(reduced_motion=True)
        for _ in range(3):
            self.assertTrue(self.demo.start())
            emoji_start = sum(stage[1] for stage in STAGES[:5])
            self.advance(emoji_start + .01)
            self.advance(emoji_start + .2)
            first = self.view.canvas.coords(self.view.paths[-1])
            self.advance(emoji_start + .6)
            self.assertEqual(self.view.canvas.coords(self.view.paths[-1]), first)
            # The renderer may keep one timer for the static symbol's expiry
            # or its color interpolation; there must still be just one demo
            # timer, and neither may survive cancellation.
            timer = self.demo.after_id
            render_timer = self.view.after_id
            self.demo.stop()
            self.assertIsNone(self.demo.after_id)
            self.assertNotIn(timer, self.root.tk.call("after", "info"))
            if render_timer is not None:
                self.assertNotIn(render_timer, self.root.tk.call("after", "info"))
            self.now = 100.
