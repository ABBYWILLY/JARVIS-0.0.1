"""Visual policies and the actual shared Tk Canvas, without audio hardware."""
import math
from pathlib import Path
import tempfile
import tkinter as tk
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis.presence import AMBIENCES, PresenceModel, PresenceSettings, PresenceView, stroke_widths
from jarvis.spectrum import Tone
from jarvis.storage import Store
from tests.test_jarvis import display_available


PCM = {"rms": .06, "wave": [math.sin(n * .8) * .2 for n in range(48)]}


class AdvancedGeometryTests(unittest.TestCase):
    def test_new_visual_preferences_are_bounded_and_do_not_accept_invalid_types(self):
        defaults = PresenceSettings()
        for raw in ({"thinking_size": 131}, {"thinking_size": True}, {"halo_intensity": -1},
                    {"halo_intensity": float("nan")}, {"mini_mode": "yes"}, {"ambience": "agent"},
                    {"emotional_palette": "invented"}, {"microexpressions": 1}):
            self.assertEqual(PresenceSettings.from_dict(raw), defaults)
        settings = PresenceSettings.from_dict({"thinking_size": 130, "halo_intensity": 0,
            "mini_mode": True, "ambience": "focus", "emotional_palette": "warm"})
        self.assertEqual((settings.thinking_size, settings.halo_intensity, settings.mini_mode), (130, 0, True))

    def test_unrepresentable_numeric_preferences_fall_back_without_breaking_startup(self):
        for key in ("wave_expressivity", "spectrum_intensity", "halo_intensity", "visualizer_thickness"):
            for value in (10 ** 1000, -(10 ** 1000)):
                with self.subTest(key=key, value_sign=value > 0):
                    self.assertEqual(PresenceSettings.from_dict({key: value}), PresenceSettings())

    def test_thinking_size_changes_real_geometry_and_ambiences_remain_visually_distinct(self):
        small = PresenceModel(PresenceSettings(reduced_motion=True))
        large = PresenceModel(PresenceSettings(reduced_motion=True, thinking_size=130))
        for model in (small, large):
            model.update_event("thinking", now=10.)
        a, b = small.target_geometry(1000, 700, 10.), large.target_geometry(1000, 700, 10.)
        distance = lambda points: max(math.hypot(x - 500, y - 350) for x, y in points)
        self.assertAlmostEqual(distance(b) / distance(a), 1.3)
        geometries = []
        for ambience in AMBIENCES:
            model = PresenceModel(PresenceSettings(ambience=ambience))
            model.update_event("thinking", now=10.)
            geometries.append(model.target_geometry(1000, 700, 11.))
        self.assertEqual(len({tuple(points) for points in geometries}), 4)

    def test_visible_stroke_controls_keep_halos_wider_at_every_dpi(self):
        for scale in (1., 1.5, 2.5):
            thin, normal, thick = [stroke_widths(value, scale) for value in (1, 6, 10)]
            for layers in (thin, normal, thick):
                self.assertTrue(all(a > b for a, b in zip(layers, layers[1:])))
            self.assertGreaterEqual(normal[-1], 6 * scale)
            self.assertGreaterEqual(normal[0], 27 * scale)
            self.assertTrue(all(a < b < c for a, b, c in zip(thin, normal, thick)))

    def test_microexpressions_never_modify_the_microphone_wave_or_expired_pcm(self):
        for state in ("listening", "user_speaking"):
            plain, expressive = PresenceModel(), PresenceModel()
            for model in (plain, expressive):
                model.update_event(state, PCM, now=10.)
            expressive.micro.trigger("surprise", 10.)
            self.assertEqual(plain.target_geometry(1000, 700, 10.1), expressive.target_geometry(1000, 700, 10.1))
            self.assertEqual(expressive.signal, plain.signal)
        expressive.update_event("jarvis_speaking", PCM, now=10.)
        expressive.micro.trigger("surprise", 14.)
        flat = expressive.target_geometry(1000, 700, 14.2)
        self.assertTrue(all(y == 350 for _, y in flat))
        self.assertFalse(expressive.needs_animation(14.2))

    def test_microexpression_phase_is_bounded_even_after_a_long_thinking_state(self):
        plain, expressive = PresenceModel(), PresenceModel()
        for model in (plain, expressive):
            model.update_event("thinking", now=0.)
        expressive.micro.trigger("enthusiasm", 1_000_000.)
        a = plain.target_geometry(1000, 700, 1_000_000.7)
        b = expressive.target_geometry(1000, 700, 1_000_000.7)
        self.assertLess(max(math.dist(left, right) for left, right in zip(a, b)), 15.)


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class AdvancedPresenceTkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.store = Store(Path(self.temp.name) / "advanced.sqlite3")
        self.addCleanup(self.store.close)
        self.voice = SimpleNamespace(listening=False, toggle=Mock(), emergency=Mock(), stop_listening=Mock())
        self.app = SimpleNamespace(root=self.root, store=self.store, voice=self.voice, font_family="DejaVu Sans")
        self.view = PresenceView(self.app)
        self.addCleanup(self.view.close)

    def assert_in_window(self, widget):
        window = self.view.window
        self.assertTrue(widget.winfo_viewable())
        x, y = widget.winfo_rootx() - window.winfo_rootx(), widget.winfo_rooty() - window.winfo_rooty()
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + widget.winfo_width(), window.winfo_width())
        self.assertLessEqual(y + widget.winfo_height(), window.winfo_height())

    def test_mini_reuses_window_canvas_pool_and_controls_at_small_sizes_and_dpi(self):
        for scaling in (1, 2.5):
            self.root.tk.call("tk", "scaling", 96 / 72 * scaling)
            self.view.show()
            self.root.update()
            window, canvas, items = self.view.window, self.view.canvas, self.view.canvas.find_all()
            self.assertTrue(self.view.set_options(mini_mode=True, reduced_motion=True))
            self.view.window.geometry("320x240")
            self.voice.listening, self.voice.microphone_state = True, "open"
            self.view.update_microphone("open")
            self.view.update_event("thinking")
            self.root.update()
            for widget in (self.view.mic_label, self.view.mini_button, self.view.listen_button,
                           self.view.command_button):
                self.assert_in_window(widget)
            self.assertIn("MICRO OUVERT", self.view.mic_label.cget("text"))
            self.assertEqual(self.view.state_label.winfo_y(), 12)
            self.assertEqual(self.view.mic_label.winfo_y(), 44)
            self.assertFalse(self.view.window.tk.getboolean(self.view.window.attributes("-topmost")))
            self.assertIs(self.view.window, window)
            self.assertIs(self.view.canvas, canvas)
            self.assertEqual(self.view.canvas.find_all(), items)
            self.assertEqual(self.view.timing_panel.winfo_manager(), "")
            self.assertIsNone(self.view.after_id)
            self.view.set_options(mini_mode=False)
            self.root.update()
            self.assertIs(self.view.canvas, canvas)
            self.assertEqual(self.view.canvas.find_all(), items)
            self.assertAlmostEqual(self.view.state_label.winfo_y(),
                                   self.view.window.winfo_height() * .105, delta=1)
            self.assertAlmostEqual(self.view.mic_label.winfo_y(),
                                   self.view.window.winfo_height() * .15, delta=1)
            self.voice.listening = False
            self.view.close()

    def test_workshop_previews_are_real_geometry_offline_and_audio_events_cancel_them(self):
        self.view.show()
        self.root.update()
        canvas = self.view.canvas
        self.assertTrue(self.view.preview_workshop("surprise"))
        self.assertEqual(self.view.state, "thinking")
        self.assertEqual(self.view.model.signal["rms"], 0.)
        self.assertTrue(self.view.model.micro.active(self.view.model.micro.started + .2))
        self.view.update_event("user_speaking", PCM)
        self.assertFalse(self.view._workshop_preview)
        self.assertIsNone(self.view._preview_text)
        self.assertFalse(self.view.model.micro.active(self.view.model.signal_at))
        self.assertEqual(self.view.model.signal["rms"], PCM["rms"])
        self.assertIs(self.view.canvas, canvas)
        self.view.update_event("silent")
        self.assertTrue(self.view.preview_workshop("line"))
        self.root.update()
        self.assertTrue(all(y == canvas.winfo_height() / 2 for _, y in self.view.model.points))
        self.view.return_to_command()
        self.assertIsNone(self.view.after_id)
        for command in (self.voice.toggle, self.voice.emergency, self.voice.stop_listening):
            command.assert_not_called()

    def test_microphone_off_cancels_workshop_and_keyboard_toggle_consumes_event(self):
        self.view.show()
        self.root.update()
        self.assertTrue(self.view.preview_workshop("surprise"))
        self.view.update_microphone("disabled")
        self.assertFalse(self.view._workshop_preview)
        self.assertIsNone(self.view._preview_text)
        self.assertEqual(self.view.state, "silent")
        self.assertIsNone(self.view.after_id)
        self.assertEqual(self.view.toggle_mini(), "break")
        self.assertTrue(self.view.settings.mini_mode)

    def test_f10_binding_restores_normal_geometry_and_keeps_the_canvas_at_each_dpi(self):
        self.view.show()
        self.root.update()
        canvas, items = self.view.canvas, self.view.canvas.find_all()
        for scaling in (1., 2.5):
            with self.subTest(scaling=scaling):
                self.root.tk.call("tk", "scaling", 96 / 72 * scaling)
                self.view.window.geometry("760x520+45+55")
                # X focus is asynchronous, like native Windows geometry.
                deadline = time.monotonic() + 2
                while self.root.focus_get() != self.view.window and time.monotonic() < deadline:
                    self.view.window.focus_force()
                    self.root.update()
                self.assertEqual(self.root.focus_get(), self.view.window)
                geometry = self.view.window.geometry()
                self.view.window.event_generate("<F10>")
                self.root.update()
                self.assertTrue(self.view.settings.mini_mode)
                self.view.window.event_generate("<F10>")
                self.root.update()
                self.assertFalse(self.view.settings.mini_mode)
                self.assertEqual(self.view.window.geometry(), geometry)
                self.assertIs(self.view.canvas, canvas)
                self.assertEqual(self.view.canvas.find_all(), items)
        for command in (self.voice.toggle, self.voice.emergency, self.voice.stop_listening):
            command.assert_not_called()

    @patch("jarvis.presence.time.monotonic", return_value=100.)
    def test_halo_strength_and_workshop_preferences_persist_without_touching_voice(self, _clock):
        self.root.tk.call("tk", "scaling", 96 / 72)
        self.store.set_preference("voice", {"preserve": "original"})
        self.store.set_preference("presence", {"future_option": "keep"})
        self.view._saved_preferences["future_option"] = "keep"
        self.view.show()
        self.root.update()
        self.view.set_options(profile="cinematic", reduced_motion=True, halo_intensity=0,
                              thinking_size=125, ambience="story", emotional_palette="soft", mini_mode=True)
        self.view.update_event("thinking")
        self.root.update()
        self.assertEqual([self.view.canvas.itemcget(path, "state") for path in self.view.paths],
                         ["hidden", "hidden", "hidden", "normal"])
        reopened = PresenceView(self.app)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.settings, self.view.settings)
        self.assertEqual(self.store.get_preference("voice"), {"preserve": "original"})
        self.assertEqual(self.store.get_preference("presence")["future_option"], "keep")
        self.view.set_options(halo_intensity=100)
        self.assertTrue(all(self.view.canvas.itemcget(path, "state") == "normal" for path in self.view.paths))

