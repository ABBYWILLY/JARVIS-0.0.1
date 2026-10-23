"""Real Canvas Studio transactions; no model, microphone or audio playback."""
from dataclasses import asdict
import math
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis.presence import PresenceModel, PresenceSettings, PresenceView, stroke_widths
from jarvis.presence_studio import PRESETS
from jarvis.storage import Store
from tests.test_jarvis import display_available


class StudioSettingsTests(unittest.TestCase):
    def test_settings_schema_validates_new_controls_and_presets_keep_accessibility(self):
        for key, low, high in (("halo_diffusion", 50, 180), ("animation_speed", 50, 150),
                               ("transition_speed", 50, 150)):
            for value in (True, low - 1, high + 1, 10 ** 1000, float("nan"), "100"):
                with self.subTest(key=key, value=type(value)):
                    self.assertEqual(PresenceSettings.from_dict({key: value}), PresenceSettings())
            self.assertEqual(getattr(PresenceSettings.from_dict({key: high}), key), high)
        for preset in PRESETS.values():
            raw = asdict(PresenceSettings(reduced_motion=True, semantic_morphing=False)) | preset
            settings = PresenceSettings.from_dict(raw)
            self.assertTrue(settings.reduced_motion)
            self.assertFalse(settings.semantic_morphing)

    def test_structure_diffusion_and_speeds_change_real_geometry_without_changing_pcm(self):
        shapes = []
        for structure in ("lens", "round", "elongated"):
            model = PresenceModel(PresenceSettings(thinking_structure=structure, reduced_motion=True))
            model.update_event("thinking", now=5.)
            shapes.append(tuple(model.target_geometry(900, 600, now=6.)))
        self.assertEqual(len(set(shapes)), 3)
        for diffusion in (50, 100, 180):
            widths = stroke_widths(6, 1., diffusion)
            self.assertEqual(widths[-1], stroke_widths(6)[-1])
            self.assertTrue(all(left > right for left, right in zip(widths, widths[1:])))
        self.assertLess(stroke_widths(6, diffusion=50)[0], stroke_widths(6, diffusion=180)[0])
        slow, fast = [PresenceModel(PresenceSettings(animation_speed=speed)) for speed in (50, 150)]
        for model in (slow, fast):
            model.update_event("thinking", now=5.)
        self.assertNotEqual(slow.target_geometry(900, 600, 6.), fast.target_geometry(900, 600, 6.))
        pcm = {"rms": .05, "wave": [math.sin(n) * .1 for n in range(48)]}
        for model in (slow, fast):
            model.update_event("listening", pcm, now=10.)
        self.assertEqual(slow.target_geometry(900, 600, 10.1), fast.target_geometry(900, 600, 10.1))
        self.assertEqual(slow.signal, fast.signal)
        initial = [(0., 0.)] * 97
        slow, fast = [PresenceModel(PresenceSettings(transition_speed=speed)) for speed in (50, 150)]
        for model in (slow, fast):
            model.points, model.size, model.last_frame = initial, (900, 600), 10.
            model.update_event("thinking", now=10.)
        target = fast.target_geometry(900, 600, 10.04)
        distance = lambda frame: sum(math.dist(a, b) for a, b in zip(frame, target))
        self.assertLess(distance(fast.frame(900, 600, 10.04)), distance(slow.frame(900, 600, 10.04)))


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class StudioTkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.store = Store(Path(self.temp.name) / "studio.sqlite3")
        self.addCleanup(self.store.close)
        self.store.set_preference("presence", {"future_option": "preserved", "wave_expressivity": 75})
        self.store.set_preference("voice", {"untouched": True})
        self.voice = SimpleNamespace(listening=False, toggle=Mock(), emergency=Mock(), stop_listening=Mock())
        self.app = SimpleNamespace(root=self.root, store=self.store, voice=self.voice,
                                   font_family="DejaVu Sans", operation=None)
        self.view = PresenceView(self.app)
        self.addCleanup(self.view.close)
        self.view.open_settings()
        self.studio = self.view.studio
        self.root.update()

    def test_every_visual_preference_has_one_editor_and_opening_writes_nothing(self):
        self.assertEqual(set(self.studio.variables), set(asdict(PresenceSettings())) - {"background", "fixed_color"})
        self.assertEqual(self.store.get_preference("presence"),
                         {"future_option": "preserved", "wave_expressivity": 75})
        self.assertIs(self.view.open_settings(), self.studio.window)
        self.assertIsNone(self.view.canvas)

    def test_demo_can_start_on_first_click_when_presence_has_never_been_opened(self):
        self.assertIsNone(self.view.canvas)
        self.assertTrue(self.studio.demo())
        self.assertTrue(self.view._demo.active)
        self.assertTrue(self.view._visible())
        self.studio.cancel()
        self.assertFalse(self.view._demo.active)
        self.assertIsNone(self.view._demo.after_id)

    def test_draft_before_after_cancel_and_apply_use_one_real_renderer_and_one_preference(self):
        original = self.store.get_preference("presence")
        self.studio.change(visualizer_thickness=10, halo_diffusion=170, thinking_structure="round")
        self.assertEqual(self.view.settings.visualizer_thickness, 6)
        self.assertTrue(self.studio.preview())
        self.root.update()
        canvas, pool = self.view.canvas, self.view.canvas.find_all()
        self.assertEqual(len(pool), 23)
        self.assertEqual(self.view.settings.visualizer_thickness, 10)
        self.assertEqual(float(canvas.itemcget(self.view.paths[-1], "width")), stroke_widths(10,
            max(.75, min(4., float(self.root.tk.call("tk", "scaling")) / (96 / 72))), 170)[-1])
        self.studio.comparison.set("before")
        self.assertTrue(self.studio.compare())
        self.assertEqual(self.view.settings.visualizer_thickness, 6)
        self.studio.comparison.set("after")
        self.assertTrue(self.studio.compare())
        self.assertEqual(self.view.settings.visualizer_thickness, 10)
        self.assertEqual(self.store.get_preference("presence"), original)
        self.studio.cancel()
        self.assertEqual(self.view.settings.visualizer_thickness, 6)
        self.assertEqual(self.view.state, "silent")
        self.assertIs(self.view.canvas, canvas)
        self.assertEqual(canvas.find_all(), pool)
        self.assertEqual(self.store.get_preference("presence"), original)
        self.view.open_settings()
        self.studio = self.view.studio
        self.studio.change(halo_diffusion=170, thinking_structure="round")
        self.assertTrue(self.studio.apply())
        reopened = PresenceView(self.app)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.settings.halo_diffusion, 170)
        self.assertEqual(reopened.settings.thinking_structure, "round")
        self.assertEqual(self.store.get_preference("presence")["future_option"], "preserved")
        self.assertEqual(self.store.get_preference("voice"), {"untouched": True})
        for command in (self.voice.toggle, self.voice.emergency, self.voice.stop_listening):
            command.assert_not_called()

    def test_external_shortcuts_do_not_accidentally_persist_draft_and_cancel_keeps_them(self):
        self.studio.change(visualizer_thickness=10)
        self.studio.preview()
        self.view.set_options(diagnostic_mode=False, mini_mode=True)
        self.assertEqual(self.store.get_preference("presence")["visualizer_thickness"], 6)
        self.assertFalse(self.studio.baseline.diagnostic_mode)
        self.assertTrue(self.studio.draft.mini_mode)
        self.studio.cancel()
        self.assertEqual(self.view.settings.visualizer_thickness, 6)
        self.assertFalse(self.view.settings.diagnostic_mode)
        self.assertTrue(self.view.settings.mini_mode)

    def test_restore_is_a_draft_and_failed_save_retains_it(self):
        self.view.set_options(thinking_size=125)
        original = self.store.get_preference("presence")
        self.studio.restore()
        self.assertEqual(self.studio.draft.thinking_size, 100)
        self.assertEqual(self.store.get_preference("presence"), original)
        with patch.object(self.store, "set_preference", side_effect=OSError("full")), \
             patch("jarvis.presence.messagebox.showerror") as error:
            self.assertFalse(self.studio.apply())
        error.assert_called_once()
        self.assertIn("thinking_size", self.studio.dirty)
        self.assertEqual(self.studio.baseline.thinking_size, 125)

    def test_real_events_preempt_preview_keep_draft_and_preserve_pcm(self):
        self.studio.change(visualizer_thickness=10)
        self.studio.preview()
        pcm = {"rms": .04, "wave": [math.sin(n) for n in range(48)]}
        self.view.update_event("listening", pcm)
        self.assertFalse(self.studio.previewing)
        self.assertIsNone(self.view._preview_text)
        self.assertEqual(self.view.state, "listening")
        self.assertEqual(self.view.model.signal["rms"], .04)
        self.assertEqual(self.view.settings.visualizer_thickness, 6)
        self.assertEqual(self.studio.draft.visualizer_thickness, 10)
        self.voice.listening = True
        self.assertFalse(self.studio.preview())
        self.studio.cancel()
        self.assertEqual(self.view.state, "listening")

    def test_small_window_large_dpi_fixed_actions_keyboard_scroll_and_cleanup(self):
        for scale in (1., 2.5):
            self.root.tk.call("tk", "scaling", 96 / 72 * scale)
            self.studio.window.geometry("440x390")
            self.root.update()
            actions = [widget for frame in self.studio.window.winfo_children()
                       for widget in frame.winfo_children() if isinstance(widget, ttk.Button)
                       and widget.cget("text") in ("Annuler", "Restaurer", "Appliquer")]
            self.assertEqual(len(actions), 3)
            for button in actions:
                self.assertTrue(button.winfo_viewable())
                self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                     self.studio.window.winfo_rootx() + self.studio.window.winfo_width())
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                     self.studio.window.winfo_rooty() + self.studio.window.winfo_height())
            self.studio.notebook.select(1)
            target = self.studio.variables["reduced_motion"]
            widget = self.studio.pages["Visualiseur"].nametowidget("reduced_motion")
            widget.focus_force()
            self.root.update()
            self.assertIs(self.studio.window.focus_get(), widget)
            canvas = widget.master.master
            self.assertGreater(canvas.yview()[0], 0)
            self.assertFalse(target.get())
        self.studio.preview()
        self.studio.cancel()
        self.assertIsNone(self.view.studio)
        self.view.close()
        self.root.update()
        self.assertIsNone(self.view.after_id)
        self.assertIsNone(self.view._preview_id)

    def test_direct_window_destruction_restores_preferences_without_touching_dead_widgets(self):
        errors = []
        self.root.report_callback_exception = lambda kind, exc, trace: errors.append(str(exc))
        baseline = self.view.settings
        self.studio.change(halo_diffusion=180)
        self.studio.preview()
        self.root.update()
        self.view.window.destroy()
        self.root.update()
        self.assertEqual(errors, [])
        self.assertIsNone(self.view.window)
        self.assertIsNone(self.view.canvas)
        self.assertIsNone(self.view.studio)
        self.assertIsNone(self.view.after_id)
        self.assertIsNone(self.view._preview_id)
        self.assertEqual(self.view.settings, baseline)
        self.assertEqual(tuple(self.root.tk.call("after", "info")), ())
