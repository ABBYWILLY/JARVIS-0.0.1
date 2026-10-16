"""Geometry and real Tk rendering contracts; no simulated audio is called live."""
import math
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis.presence import (POINT_COUNT, PROFILES, PresenceModel, PresenceSettings,
                             PresenceView, contrast, core_radius, palette, readable_accent)
from jarvis.spectrum import OPERATIONAL, caption_group
from jarvis.storage import Store


SIGNAL = {"rms": 0.12, "wave": [0.05, -0.2, 0.15, 0.08, -0.13, 0.3, -0.08, 0.02]}


def bounds(points):
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


class GeometryTests(unittest.TestCase):
    def assert_centered(self, points, width, height):
        left, top, right, bottom = bounds(points)
        self.assertAlmostEqual((left + right) / 2, width / 2, places=6)
        self.assertAlmostEqual((top + bottom) / 2, height / 2, places=6)
        self.assertGreaterEqual(left, 0)
        self.assertLessEqual(right, width)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(bottom, height)

    def test_silent_and_listening_are_exact_flat_lines_without_fake_motion(self):
        model = PresenceModel()
        for state in ("silent", "listening"):
            model.update_event(state, SIGNAL, now=0)
            first = model.frame(1000, 700, now=0.01)
            self.assertTrue(all(y == 350 for _, y in first))
            self.assertGreater(first[-1][0] - first[0][0], 800)
            self.assertEqual(first, model.frame(1000, 700, now=50))
            self.assertFalse(model.needs_animation(now=50))

    def test_microphone_wave_uses_real_signal_and_joins_the_baseline(self):
        model = PresenceModel()
        model.update_event("user_speaking", SIGNAL, now=1)
        points = model.frame(1000, 700, now=1.01)
        self.assertEqual(len(points), POINT_COUNT)
        self.assertGreater(max(y for _, y in points), 350)
        self.assertLess(min(y for _, y in points), 350)
        self.assertAlmostEqual(points[0][1], 350)
        self.assertAlmostEqual(points[-1][1], 350)
        self.assert_centered(points, 1000, 700)
        model.update_event("user_speaking", {"rms": 0, "wave": [1, -1]}, now=1.05)
        self.assertTrue(all(y == 350 for _, y in model.frame(1000, 700, now=1.06)))

    def test_expired_or_missing_signal_never_keeps_audio_motion_alive(self):
        model = PresenceModel()
        model.update_event("user_speaking", SIGNAL, now=1)
        self.assertTrue(model.needs_animation(now=1.01))
        model.frame(1000, 700, now=1.01)
        flat = model.frame(1000, 700, now=1.3)
        self.assertTrue(all(y == 350 for _, y in flat))
        self.assertFalse(model.needs_animation(now=1.3))
        model.update_event("jarvis_speaking", now=2)
        core = model.frame(1000, 700, now=2.01)
        self.assertEqual(core, model.frame(1000, 700, now=5))
        self.assertFalse(model.needs_animation(now=5))
        model.update_event("jarvis_speaking", SIGNAL, now=6)
        self.assertNotEqual(core, model.target_geometry(1000, 700, now=6.01))

    def test_core_is_circular_and_centred_in_multiple_aspect_ratios(self):
        model = PresenceModel(PresenceSettings(reduced_motion=True))
        for width, height in ((620, 440), (480, 840), (1920, 1080), (3440, 1440), (900, 600)):
            for signal in (None, SIGNAL):
                model.update_event("jarvis_speaking", signal, now=0)
                points = model.frame(width, height, now=0.01)
                self.assert_centered(points, width, height)
                if signal is None:
                    radius = core_radius(width, height)
                    for x, y in points:
                        self.assertAlmostEqual(math.hypot(x - width / 2, y - height / 2), radius, places=6)
                    self.assertAlmostEqual(bounds(points)[2] - bounds(points)[0], 2 * radius)
        self.assertAlmostEqual(core_radius(1000, 700), 126)
        self.assertLessEqual(core_radius(10000, 10000), 260)

    def test_one_mesh_morphs_reversibly_and_interrupts_without_waiting(self):
        model = PresenceModel()
        line = model.frame(1000, 700, now=0)
        model.update_event("thinking", now=0.01)
        middle = model.frame(1000, 700, now=0.04)
        self.assertNotEqual(middle, line)
        self.assertNotEqual(middle, model.target_geometry(1000, 700, now=0.04))
        self.assertTrue(model.morphing)
        model.update_event("user_speaking", SIGNAL, now=0.05)
        interrupted = model.frame(1000, 700, now=0.08)
        self.assertEqual(model.state, "user_speaking")
        self.assertEqual(len(interrupted), len(line))
        self.assert_centered(interrupted, 1000, 700)
        model.update_event("silent", now=0.09)
        for index in range(1, 31):
            model.frame(1000, 700, now=0.09 + index * 0.03)
        self.assertEqual(model.points, line)
        self.assertFalse(model.needs_animation(now=2))

    def test_thinking_animates_only_actual_state_and_reduced_motion_disables_it(self):
        model = PresenceModel()
        model.update_event("thinking", now=1)
        self.assertNotEqual(model.target_geometry(1000, 700, now=1),
                            model.target_geometry(1000, 700, now=4))
        model.settings = PresenceSettings(reduced_motion=True)
        first = model.frame(1000, 700, now=5)
        self.assertEqual(first, model.frame(1000, 700, now=9))
        self.assertFalse(model.needs_animation(now=9))
        model.update_event("dormant", now=10)
        dormant = model.frame(1000, 700, now=10)
        self.assertLessEqual(bounds(dormant)[2] - bounds(dormant)[0], 5)
        self.assertFalse(model.needs_animation(now=10))

    def test_malformed_preferences_and_signal_are_safe(self):
        for raw in (None, [], "invalid", {"profile": [], "background": "white",
                                         "reduced_motion": "yes", "subtitles": 1,
                                         "accent_mode": [], "fixed_color": "invisible"}):
            self.assertEqual(PresenceSettings.from_dict(raw), PresenceSettings())
        model = PresenceModel()
        model.update_event("user_speaking", {"rms": float("nan"), "wave": [None, float("inf")]}, now=0)
        self.assertTrue(all(y == 350 for _, y in model.frame(1000, 700, now=0.01)))
        with self.assertRaises(ValueError):
            model.update_event("invented")

    def test_text_contrast_adapts_to_user_background(self):
        for background in ("#000000", "#ffffff", "#ffcc00", "#00ffff", "#808080", "#aa0077"):
            colors = palette(background)
            self.assertGreaterEqual(contrast(background, colors["foreground"]), 4.5)
            self.assertGreaterEqual(contrast(background, colors["muted"]), 4.5)
        self.assertEqual(set(PROFILES), {"eco", "balanced", "cinematic"})


def display_available():
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class PresenceTkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.store = Store(Path(self.temp.name) / "presence.sqlite3")
        self.addCleanup(self.store.close)
        voice = SimpleNamespace(listening=False, toggle=Mock(), emergency=Mock(), stop_listening=Mock())
        self.app = SimpleNamespace(root=self.root, store=self.store, voice=voice, font_family="DejaVu Sans")
        self.view = PresenceView(self.app)
        self.addCleanup(self.view.close)

    def test_lazy_window_reopens_and_all_layers_share_one_spline(self):
        self.assertEqual(self.root.winfo_children(), [])
        self.view.update_event("thinking")
        self.assertIsNone(self.view.window)
        self.assertIsNone(self.view.after_id)
        self.view.show()
        self.root.update()
        original = self.view.window
        self.assertIsNotNone(self.view.after_id)
        self.assertEqual(self.view.canvas.cget("background"), "#000000")
        coordinates = self.view.canvas.coords(self.view.paths[0])
        for path in self.view.paths:
            self.assertEqual(self.view.canvas.coords(path), coordinates)
            self.assertIn(str(self.view.canvas.itemcget(path, "smooth")), {"true", "1"})
        self.view.close()
        self.assertIsNone(self.view.after_id)
        self.assertFalse(self.root.tk.call("after", "info"))
        self.view.show()
        self.assertIsNot(self.view.window, original)
        self.assertEqual(self.view.state, "thinking")

    def test_caption_overlay_never_changes_canvas_or_core_centre(self):
        self.view.show()
        self.view.set_options(reduced_motion=True)
        self.root.update()
        width, height = self.view.canvas.winfo_width(), self.view.canvas.winfo_height()
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": "Phrase courte", "fraction": 0.5})
        self.root.update()
        before = bounds(self.view.model.points)
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": "Une transcription très longue " * 30, "fraction": 1})
        self.root.update()
        self.assertEqual((self.view.canvas.winfo_width(), self.view.canvas.winfo_height()), (width, height))
        self.assertEqual(before, bounds(self.view.model.points))
        self.assertEqual(self.view.caption_label.winfo_manager(), "place")
        left, top, right, bottom = bounds(self.view.model.points)
        self.assertAlmostEqual((left + right) / 2, width / 2)
        self.assertAlmostEqual((top + bottom) / 2, height / 2)
        self.view.set_options(subtitles=False)
        self.assertEqual(self.view.caption_label.winfo_manager(), "")

    def test_preferences_persist_and_bad_saved_values_are_not_overwritten_on_load(self):
        raw = {"background": "invalid", "profile": [], "future": "preserve"}
        self.store.set_preference("presence", raw)
        view = PresenceView(self.app)
        self.addCleanup(view.close)
        self.assertEqual(view.settings, PresenceSettings())
        self.assertEqual(self.store.get_preference("presence"), raw)
        self.assertTrue(view.set_background("#FfFfFf"))
        self.assertFalse(view.set_background("arbitrary"))
        self.assertTrue(view.set_options(profile="eco", reduced_motion=True, subtitles=False))
        reopened = PresenceView(self.app)
        self.assertEqual(reopened.settings, PresenceSettings("#ffffff", "eco", True, False))
        self.assertEqual(self.store.get_preference("presence")["future"], "preserve")
        reopened.reset_background()
        self.assertEqual(self.store.get_preference("presence")["background"], "#000000")

    def test_background_picker_applies_real_selection_and_cancellation_is_inert(self):
        with patch("jarvis.presence.colorchooser.askcolor", return_value=((255, 255, 255), "#ffffff")):
            self.view.choose_background()
        self.assertEqual(self.view.settings.background, "#ffffff")
        with patch("jarvis.presence.colorchooser.askcolor", return_value=(None, None)):
            self.view.choose_background()
        self.assertEqual(self.view.settings.background, "#ffffff")

    def test_dormant_stops_real_activity_first_and_wake_never_enables_microphone(self):
        self.view.show()
        self.view.update_event("thinking")
        states_at_stop = []
        self.app.voice.emergency.side_effect = lambda: states_at_stop.append(self.view.state)
        self.view.sleep()
        self.assertEqual(states_at_stop, ["thinking"])
        self.assertEqual(self.view.state, "dormant")
        self.assertIsNone(self.view.after_id)
        self.view.update_event("jarvis_speaking", SIGNAL)
        self.assertEqual(self.view.state, "dormant")
        self.view.wake()
        self.assertEqual(self.view.state, "silent")
        self.app.voice.stop_listening.assert_called_once()
        self.app.voice.toggle.assert_not_called()

    def test_hidden_and_closed_windows_cancel_all_animation_callbacks(self):
        self.view.show()
        self.view.update_event("thinking")
        self.assertIsNotNone(self.view.after_id)
        self.view.return_to_command()
        self.assertIsNone(self.view.after_id)
        self.view.update_event("user_speaking", SIGNAL)
        self.assertIsNone(self.view.after_id)
        self.view.show()
        self.root.update()
        self.assertIsNotNone(self.view.after_id)
        self.view.close()
        self.assertFalse(self.root.tk.call("after", "info"))

    def test_resize_is_responsive_and_reduced_motion_uses_no_thinking_timer(self):
        self.view.show()
        self.view.set_options(reduced_motion=True)
        self.view.update_event("thinking")
        for width, height in ((800, 500), (700, 900), (1200, 650)):
            self.view.window.geometry(f"{width}x{height}")
            self.root.update()
            actual_width, actual_height = self.view.canvas.winfo_width(), self.view.canvas.winfo_height()
            left, top, right, bottom = bounds(self.view.model.points)
            self.assertAlmostEqual((left + right) / 2, actual_width / 2)
            self.assertAlmostEqual((top + bottom) / 2, actual_height / 2)
            self.assertAlmostEqual(right - left, bottom - top)
            self.assertIsNone(self.view.after_id)

    def test_emotional_modes_persist_and_never_recolor_operational_controls(self):
        self.view.show()
        self.view.update_operation("error", "Arrêt explicite")
        old_operation_color = self.view.operation_label.cget("foreground")
        old_background = self.view.canvas.cget("background")
        old_button_color = self.view.listen_button.cget("foreground")
        old_identity_color = self.view.identity.cget("foreground")
        self.assertEqual(self.view.interpret_text("Une colère et une rage explicites.").name, "colère")
        self.assertEqual(self.view.mesh_accent(), self.view.tone.color)
        self.assertEqual(self.view.operation, "error")
        self.assertEqual(self.view.operation_label.cget("foreground"), old_operation_color)
        self.assertIn(OPERATIONAL["error"]["label"], self.view.operation_label.cget("text"))
        self.assertEqual(self.view.canvas.cget("background"), old_background)
        self.assertEqual(self.view.listen_button.cget("foreground"), old_button_color)
        self.assertEqual(self.view.identity.cget("foreground"), old_identity_color)
        for mode in ("cyan", "fixed", "none", "adaptive"):
            self.assertTrue(self.view.set_options(accent_mode=mode, fixed_color="#AB78EF"))
            self.assertEqual(self.store.get_preference("presence")["accent_mode"], mode)
            self.assertEqual(self.view.operation_label.cget("foreground"), old_operation_color)
            reopened = PresenceView(self.app)
            self.assertEqual(reopened.settings.accent_mode, mode)
            self.assertEqual(reopened.settings.fixed_color, "#ab78ef")
            if mode == "cyan":
                self.assertEqual(self.view.mesh_accent(), "#69edf5")
            elif mode == "fixed":
                self.assertEqual(self.view.mesh_accent(), "#ab78ef")
            elif mode == "none":
                self.assertEqual(self.view.mesh_accent(), palette("#000000")["muted"])
        self.app.voice.toggle.assert_not_called()
        self.app.voice.emergency.assert_not_called()

    def test_captions_follow_played_fraction_and_only_keywords_receive_accents(self):
        self.view.show()
        text = "La colère et la rage, le reste demeure une simple phrase ordinaire."
        self.view.interpret_text(text)
        self.assertEqual(self.view.caption_label.winfo_manager(), "")
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0})
        self.assertEqual(self.view.caption_label.winfo_manager(), "")
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0.4})
        self.assertEqual(self.view.caption_label.get("1.0", "end-1c"), caption_group(text, 0.4))
        self.assertEqual(self.view.caption_label.winfo_manager(), "place")
        self.assertIn("estimée", self.view.caption_note.cget("text"))
        self.assertEqual(self.view.caption_footer.winfo_manager(), "place")
        ranges = self.view.caption_label.tag_ranges("keyword")
        emphasized = [self.view.caption_label.get(start, end) for start, end in zip(ranges[::2], ranges[1::2])]
        self.assertEqual(emphasized, ["colère", "rage"])
        self.assertEqual(self.view.caption_label.cget("foreground"), palette("#000000")["foreground"])
        self.assertEqual(self.view.caption_label.tag_cget("keyword", "foreground"), self.view.tone.color)
        self.view.copy_caption()
        self.assertEqual(self.root.clipboard_get(), caption_group(text, 0.4))
        self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 1})
        self.assertEqual(self.view.caption_text, caption_group(text, 1))
        self.assertLessEqual(len(self.view.caption_text.split()), 12)
        self.view.update_event("thinking")
        self.assertEqual(self.view.caption_text, "")
        self.assertEqual(self.view.caption_label.winfo_manager(), "")

    def test_none_mode_removes_keyword_tags_without_affecting_audio_or_text(self):
        self.view.show()
        self.view.update_event("jarvis_speaking", SIGNAL,
                               {"text": "Une colère et une rage explicites", "fraction": 1})
        self.assertTrue(self.view.caption_label.tag_ranges("keyword"))
        text = self.view.caption_label.get("1.0", "end-1c")
        self.view.set_options(accent_mode="none")
        self.assertEqual(self.view.caption_label.tag_ranges("keyword"), ())
        self.assertEqual(self.view.caption_label.get("1.0", "end-1c"), text)
        self.assertEqual(self.view.state, "jarvis_speaking")
        self.app.voice.emergency.assert_not_called()

    def test_dark_emotional_and_fixed_colors_retain_visible_contours(self):
        self.assertEqual(self.view.interpret_text("La mort et le deuil.").name, "deuil")
        self.assertGreaterEqual(contrast(self.view.mesh_accent(), "#000000"), 3)
        self.view.set_options(accent_mode="fixed", fixed_color="#000000")
        self.assertNotEqual(self.view.mesh_accent(), "#000000")
        self.assertGreaterEqual(contrast(self.view.mesh_accent(), "#000000"), 3)
        for background in ("#000000", "#ffffff", "#ffcc00", "#808080"):
            self.assertGreaterEqual(contrast(readable_accent(background, background), background), 3)

    def test_repeated_playback_text_does_not_repeat_tone_analysis(self):
        self.view.show()
        text = "Une colère et une rage explicites."
        with patch.object(self.view.analyzer, "update", wraps=self.view.analyzer.update) as analyze:
            self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0.2})
            self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0.4})
            self.view.update_event("jarvis_speaking", SIGNAL, {"text": text, "fraction": 0.8})
        analyze.assert_called_once_with(text)

    def test_ambiguous_caption_returns_to_cyan_after_inertia(self):
        with patch("jarvis.presence.time.monotonic", return_value=10):
            self.assertEqual(self.view.interpret_text("colère et rage", render=False).name, "colère")
        with patch("jarvis.presence.time.monotonic", return_value=11):
            self.assertEqual(self.view.interpret_text("Une réponse ambiguë", render=False).name, "colère")
        with patch("jarvis.presence.time.monotonic", return_value=14):
            self.assertEqual(self.view.interpret_text("Une réponse ambiguë", render=False).name, "neutralité")


if __name__ == "__main__":
    unittest.main()
