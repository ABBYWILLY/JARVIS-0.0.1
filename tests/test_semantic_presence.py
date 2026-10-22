"""Real Canvas integration with explicit PCM doubles, no models or devices."""
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from jarvis.morphing import FAMILIES
from jarvis.presence import PresenceSettings, PresenceView
from jarvis.richtext import parse_text
from jarvis.storage import Store
from tests.test_jarvis import display_available


SAMPLES = {"rms": .12, "wave": [.2, -.1, .05, -.3, .1]}


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class SemanticPresenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.store = Store(Path(self.temp.name) / "semantic.sqlite3")
        self.addCleanup(self.store.close)
        self.voice = SimpleNamespace(listening=False, toggle=Mock(), emergency=Mock(), stop_listening=Mock())
        self.app = SimpleNamespace(root=self.root, store=self.store, voice=self.voice, font_family="TkDefaultFont")
        self.view = PresenceView(self.app)
        self.addCleanup(self.view.close)
        self.view.show()
        self.root.update()

    def queued(self, text, *, response=41, segment=1, start=0):
        document = parse_text(text)
        events, plan = self.view.prepare_segment(text, document.text, start)
        source_events = tuple(type(event)(event.kind, event.start + start, event.end + start, event.value)
                              for event in document.events)
        self.view.queue_expressions(response, segment, text, start, start + len(text), source_events)
        return {"text": document.text, "response_id": response, "segment_id": segment,
                "original_start": start, "original_end": start + len(text), "fraction": 1.,
                "spectrum_mode": self.view.settings.spectrum_mode,
                "spectrum_events": [asdict(event) for event in events], "caption_plan": asdict(plan)}

    def playback(self, payload, signal=None):
        self.view.update_event("jarvis_speaking", SAMPLES if signal is None else signal, payload)

    def test_all_eight_families_change_the_existing_contour_then_return_to_flat_silence(self):
        examples = (":)", "😂", "❤️", "😢", "😠", "😮", "🤔", "😉")
        canvas_items = self.view.canvas.find_all()
        contour_paths = tuple(self.view.paths)
        for number, (symbol, family) in enumerate(zip(examples, FAMILIES)):
            with self.subTest(family=family), patch("jarvis.presence.time.monotonic", return_value=10. + number * 3):
                payload = self.queued("Bonjour " + symbol, response=41 + number)
                self.assertFalse(self.view.semantic.active)
                self.playback(payload)
                self.assertFalse(self.view.semantic.active, "A final emoji must await real completion")
                accent = self.view._target_accent()
                before = self.view.canvas.coords(contour_paths[-1])
                self.view.complete_segment(payload)
                self.assertEqual(self.view.semantic.family, family)
                self.assertEqual(self.view.canvas.coords(contour_paths[-1]), before)
                self.assertEqual(self.view._target_accent(), accent)
            with patch("jarvis.presence.time.monotonic", return_value=10.55 + number * 3):
                self.view._render()
                points = self.view.canvas.coords(contour_paths[-1])
                self.assertGreater(max(points[1::2]) - min(points[1::2]), 30)
                details_visible = any(self.view.canvas.itemcget(path, "state") == "normal"
                                      for pair in self.view.semantic_paths for path in pair)
                self.assertEqual(details_visible, family != "affection")  # A heart needs only its outline.
                self.assertAlmostEqual((max(points[::2]) + min(points[::2])) / 2,
                                       self.view.canvas.winfo_width() / 2)
                self.assertAlmostEqual((max(points[1::2]) + min(points[1::2])) / 2,
                                       self.view.canvas.winfo_height() / 2)
                self.assertEqual(self.view.canvas.find_all(), canvas_items)
                self.assertEqual(tuple(self.view.paths), contour_paths)
            with patch("jarvis.presence.time.monotonic", return_value=12. + number * 3):
                self.view._render()
                points = self.view.canvas.coords(contour_paths[-1])
                self.assertEqual(len(set(points[1::2])), 1)
                self.assertFalse(self.view.semantic.active)
                self.assertIsNone(self.view.after_id)

    def test_late_visual_only_tail_keeps_captions_and_uses_the_spoken_segment(self):
        for response, symbol, expected in ((41, "😊", "smile"), (42, "👩🏽‍🚀", None)):
            with self.subTest(symbol=symbol):
                payload = self.queued("Bonjour. ", response=response)
                tail = parse_text(symbol)
                start = len("Bonjour. ")
                events = tuple(type(event)(event.kind, event.start + start, event.end + start, event.value)
                               for event in tail.events)
                self.view.queue_expressions(response, 1, symbol, start, start + len(symbol), events)
                self.playback(payload)
                self.assertIn(symbol, self.view.caption_text)
                self.view.complete_segment(payload)
                self.assertEqual(self.view.semantic.family, expected)

    def test_mid_sentence_uses_a_real_quiet_interval_and_audio_resumes_immediately(self):
        payload = self.queued("Bonjour 😊 et continuons la discussion.")
        self.playback({**payload, "fraction": .5})
        self.assertFalse(self.view.semantic.active)
        self.playback({**payload, "fraction": .6}, {"rms": 0., "wave": [0.]})
        self.assertEqual(self.view.semantic.family, "smile")
        self.playback({**payload, "fraction": .7})
        self.assertFalse(self.view.semantic.active)
        self.assertEqual(self.view.state, "jarvis_speaking")
        self.assertEqual(self.view.model.signal["rms"], SAMPLES["rms"])

    def test_adjacent_symbols_are_grouped_and_unknown_symbols_do_not_guess_a_shape(self):
        payload = self.queued("Bravo 😊 ❤️ 😉")
        self.assertEqual(len(self.view._semantic_cues), 1)
        self.playback(payload)
        self.view.complete_segment(payload)
        self.assertEqual(self.view.semantic.family, "smile")
        self.view.begin_response()
        payload = self.queued("Dans l’espace 👩🏽‍🚀 🛸", response=42)
        self.assertFalse(self.view._semantic_cues)
        self.playback(payload)
        self.view.complete_segment(payload)
        self.assertFalse(self.view.semantic.active)

    def test_newer_pcm_response_error_and_user_interruption_cancel_without_old_resurrection(self):
        for action in (lambda: self.view.update_event("user_speaking", SAMPLES),
                       lambda: self.view.update_event("thinking"),
                       lambda: self.view.update_operation("error", "Arrêt explicite"),
                       lambda: self.view.update_microphone("disabled"),
                       lambda: self.view.update_microphone("voice"),
                       self.view.return_to_command, self.view.close):
            with self.subTest(action=action):
                self.view.show()
                self.view.update_event("silent")
                # Each new scope is a genuine new response in this test double.
                response = self.view._semantic_response + 1
                self.view._semantic_last_trigger = float("-inf")
                payload = self.queued("Bonjour 😊", response=response)
                self.playback(payload)
                self.view.complete_segment(payload)
                self.assertTrue(self.view.semantic.active)
                action()
                self.assertFalse(self.view.semantic.active)
                self.view.complete_segment(payload)
                self.assertFalse(self.view.semantic.active)
                self.assertFalse(self.view._semantic_cues)
        self.view.show()
        first = self.queued("Bonjour 😊", response=self.view._semantic_response + 1)
        second = self.queued("Je poursuis.", response=first["response_id"], segment=2, start=50)
        self.playback(first)
        self.playback(second)
        self.view.complete_segment(first)
        self.assertFalse(self.view.semantic.active)
        self.assertEqual(self.view.state, "jarvis_speaking")

    def test_open_silent_microphone_does_not_delay_capture_or_hide_final_expression(self):
        payload = self.queued("Bonjour ❤️")
        self.playback(payload)
        self.view.complete_segment(payload)
        self.view.update_microphone("open")
        self.view.update_event("listening")
        self.assertTrue(self.view.semantic.active)
        self.view.update_event("user_speaking", SAMPLES)
        self.assertFalse(self.view.semantic.active)
        self.voice.toggle.assert_not_called()

    def test_prepared_timeline_never_parses_text_in_pcm_or_paint_callbacks(self):
        payload = self.queued("Je suis heureux 😊")
        with patch("jarvis.presence.parse_text", side_effect=AssertionError("parsing during playback")), \
             patch("jarvis.presence.expression_family", side_effect=AssertionError("detection during playback")), \
             patch("jarvis.presence.prepare_caption", side_effect=AssertionError("analysis during playback")):
            self.playback(payload)
            self.view.complete_segment(payload)
            for _ in range(3):
                self.view._render()

    def test_settings_persist_and_reduced_motion_uses_a_static_bounded_hold(self):
        self.view.set_options(semantic_morphing=False, morph_intensity="discreet")
        reopened = PresenceView(self.app)
        self.addCleanup(reopened.close)
        self.assertFalse(reopened.settings.semantic_morphing)
        self.assertEqual(reopened.settings.morph_intensity, "discreet")
        payload = self.queued("Bonjour 😊")
        self.playback(payload)
        self.view.complete_segment(payload)
        self.assertFalse(self.view.semantic.active)
        self.view.update_event("silent")
        self.view.set_options(semantic_morphing=True, reduced_motion=True)
        self.assertTrue(self.view.preview_expression("affection"))
        before = self.view.canvas.coords(self.view.paths[-1])
        self.view._render()
        self.assertEqual(self.view.canvas.coords(self.view.paths[-1]), before)
        self.assertIsNotNone(self.view.after_id)
        self.view.clear_preview()
        self.view._render()
        self.assertFalse(self.view.semantic.active)
        self.assertIsNone(self.view.after_id)
        self.assertEqual(PresenceSettings.from_dict({"morph_intensity": []}).morph_intensity, "normal")

    def test_queue_and_canvas_remain_bounded_and_hidden_preview_is_cancelled(self):
        items = self.view.canvas.find_all()
        for segment in range(1, 100):
            self.queued("Bonjour 😊", segment=segment)
        self.assertLessEqual(len(self.view._semantic_cues), 64)
        self.assertLessEqual(len(self.view._semantic_plans), 64)
        for family in FAMILIES:
            self.view.preview_expression(family)
            self.assertEqual(self.view.canvas.find_all(), items)
        self.view.window.withdraw()
        self.root.update()
        self.assertFalse(self.view.semantic.active)
        self.assertIsNone(self.view.after_id)

    def test_field_preview_preempts_a_symbol_and_a_symbol_clears_the_field_preview(self):
        self.assertTrue(self.view.preview_expression("smile"))
        self.view.preview_text("Je suis heureux.")
        self.assertFalse(self.view.semantic.active)
        self.assertEqual(self.view.tone.name, "joie")
        self.assertTrue(self.view.preview_expression("affection"))
        self.assertTrue(self.view.preview_scenario())
        self.assertFalse(self.view.semantic.active)
        self.assertEqual(self.view.state, "thinking")
        self.view.clear_preview()
        self.assertEqual(self.view.state, "silent")
        self.assertTrue(self.view.preview_expression("wink"))
        self.assertIsNone(self.view._preview_id)


if __name__ == "__main__":
    unittest.main()
