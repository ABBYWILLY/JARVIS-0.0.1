"""GPU artist transactions and actual Tk controls; GL belongs to integration tests."""
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest

from jarvis.gpu_config import FIELD_SPECS, GpuSettings, SECTIONS
from jarvis.gpu_studio import (ESSENTIAL_SECTION, GpuStudio, LEVEL_LABELS,
                               PREVIEW_STATES, find_settings)
from jarvis.storage import Store
from tests.test_jarvis import display_available


class GpuStudioMetadataTests(unittest.TestCase):
    def test_essential_view_contains_the_six_real_high_value_controls(self):
        self.assertEqual(set(find_settings()), {"core_size", "halo_intensity", "halo_radius",
                                               "particle_density", "particle_size", "ring_speed"})
        self.assertEqual(find_settings("halo_intensity"), ("halo_intensity",))
        self.assertEqual(find_settings("INCLINAISON anneau 3"), ("ring_3_tilt",))
        self.assertIn("expression_hold_ms", find_settings("maintien"))
        self.assertIn("ring_3_tilt", find_settings("anneau 3"))
        self.assertEqual(find_settings("introuvable_xyz"), ())

    def test_every_implemented_control_can_be_found_in_its_section(self):
        for key, spec in FIELD_SPECS.items():
            with self.subTest(key=key):
                self.assertIn(key, find_settings("", spec.section, "advanced"))
                self.assertIn(key, find_settings(key))
                self.assertIn(spec.section, SECTIONS)


class LocalGpuView:
    """Explicit UI boundary: SQLite is real, graphics and audio are not started."""
    def __init__(self, root, store):
        self.app = SimpleNamespace(root=root, store=store, font_family="DejaVu Sans",
                                   operation=None, voice=SimpleNamespace(listening=False))
        self.gpu_settings = GpuSettings.from_dict(store.get_preference("presence_gpu", {}))
        self.actual_gpu_settings = self.gpu_settings
        self.gpu_studio = self.settings_dialog = None
        self.end_calls = self.write_calls = self.engine_calls = 0
        self.states = []
        self.preview_available = True
        self.save_available = True

    def set_gpu_options(self, **changes):
        if not self.save_available:
            return False
        self.write_calls += 1
        candidate = GpuSettings.from_dict(self.gpu_settings.to_dict() | changes)
        self.app.store.set_preference("presence_gpu", self.app.store.get_preference("presence_gpu", {}) | candidate.to_dict())
        self.gpu_settings = candidate
        return True

    def preview_gpu_options(self, candidate):
        if not self.preview_available or self.app.voice.listening or self.app.operation:
            return False
        self.actual_gpu_settings = candidate
        return True

    def end_gpu_preview(self):
        self.end_calls += 1
        self.actual_gpu_settings = self.gpu_settings

    def preview_gpu_state(self, state):
        self.states.append(state)
        return True

    def open_engine_settings(self):
        self.engine_calls += 1


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class GpuStudioTkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "gpu-studio.sqlite3")
        self.addCleanup(self.store.close)
        self.store.set_preference("presence_gpu", {"future_gpu": "preserved", "halo_radius": 110})
        self.store.set_preference("presence", {"background": "#123456", "visualizer_thickness": 9})
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        original = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", original))
        self.root.tk.call("tk", "scaling", 96/72)
        self.view = LocalGpuView(self.root, self.store)
        self.studio = GpuStudio(self.view)
        self.view.gpu_studio = self.studio
        self.view.settings_dialog = self.studio.window
        self.addCleanup(self.studio.cancel)
        self.root.update()

    def test_opening_creates_one_control_per_implemented_field_and_writes_nothing(self):
        self.assertEqual(set(self.studio.controls), set(FIELD_SPECS) | {"profile", "render_scale"})
        self.assertEqual(self.store.get_preference("presence_gpu"), {"future_gpu": "preserved", "halo_radius": 110})
        self.assertEqual(self.view.write_calls, 0)
        visible = {key for key, row in self.studio.rows.items() if row.winfo_manager()}
        self.assertEqual(visible, set(find_settings()))

    def test_scale_control_search_preview_and_persistence_share_the_existing_draft(self):
        self.assertEqual(find_settings("render_scale"), ("render_scale",))
        self.assertIn("render_scale", find_settings("résolution"))
        self.assertTrue(self.studio.focus_control("render_scale"))
        self.root.update()
        control = self.studio.controls["render_scale"]
        self.assertIs(self.root.focus_get(), control)
        self.assertTrue(self.studio.rows["render_scale"].winfo_manager())
        self.assertEqual(tuple(control.cget("values")), ("Auto", "100 %", "125 %", "150 %", "200 %"))
        self.studio.render_scale.set("150 %")
        control.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(self.studio.draft.render_scale, "150")
        self.assertEqual(self.view.gpu_settings.render_scale, "auto")
        self.assertTrue(self.studio.preview())
        self.assertEqual(self.view.actual_gpu_settings.render_scale, "150")
        self.studio.comparison.set("before")
        self.assertTrue(self.studio.compare())
        self.assertEqual(self.view.actual_gpu_settings.render_scale, "auto")
        self.assertTrue(self.studio.apply())
        self.assertEqual(LocalGpuView(self.root, self.store).gpu_settings.render_scale, "150")
        self.assertEqual(self.store.get_preference("presence")["background"], "#123456")

    def test_reference_30_is_reversible_and_keeps_performance_choices(self):
        self.studio.change(profile="eco", render_scale="125", fps_limit=24, core_size=110)
        self.assertTrue(self.studio.load_reference())
        self.assertEqual(self.studio.draft.profile, "eco")
        self.assertEqual(self.studio.draft.render_scale, "125")
        self.assertEqual(self.studio.draft.fps_limit, 24)
        for key in ("converging_intensity", "radiating_intensity", "pulse_radius"):
            self.assertEqual(getattr(self.studio.draft, key), 0)
        self.assertEqual(self.view.write_calls, 0)
        self.studio.cancel()
        self.assertEqual(self.view.gpu_settings.converging_intensity, 100)

    def test_only_three_new_sliders_extend_the_preserved_66_controls(self):
        self.assertEqual(len(FIELD_SPECS), 69)
        for key in ("pulse_radius", "converging_intensity", "radiating_intensity",
                    "audio_reactivity", "pulse_amplitude", "audio_attack_ms", "audio_release_ms"):
            self.assertTrue(self.studio.focus_control(key))
            self.assertIn(key, self.studio.variables)

    def test_preview_before_after_cancel_restore_previous_renderer_without_persisting(self):
        original = self.store.get_preference("presence_gpu")
        self.studio.change(halo_intensity=180, halo_radius=220, particle_size=200)
        self.assertEqual(self.view.gpu_settings.halo_radius, 110)
        self.assertTrue(self.studio.preview())
        self.assertEqual(self.view.actual_gpu_settings.halo_radius, 220)
        self.studio.comparison.set("before")
        self.assertTrue(self.studio.compare())
        self.assertEqual(self.view.actual_gpu_settings.halo_radius, 110)
        self.studio.comparison.set("after")
        self.assertTrue(self.studio.compare())
        self.assertEqual(self.view.actual_gpu_settings.halo_intensity, 180)
        self.assertEqual(self.store.get_preference("presence_gpu"), original)
        self.studio.cancel()
        self.assertEqual(self.view.end_calls, 1)
        self.assertEqual(self.view.actual_gpu_settings, self.view.gpu_settings)
        self.assertIsNone(self.view.gpu_studio)
        self.assertIsNone(self.view.settings_dialog)
        self.studio.cancel()
        self.assertEqual(self.view.end_calls, 1)

    def test_apply_persists_through_existing_store_preserves_canvas_and_unknown_fields(self):
        canvas = self.store.get_preference("presence")
        self.studio.change(core_size=120, halo_radius=160, halo_intensity=45)
        self.assertTrue(self.studio.apply())
        self.assertFalse(self.studio.dirty)
        self.assertEqual(self.view.write_calls, 1)
        reopened = LocalGpuView(self.root, self.store)
        self.assertEqual(reopened.gpu_settings.core_size, 120)
        self.assertEqual(reopened.gpu_settings.halo_radius, 160)
        self.assertEqual(reopened.gpu_settings.halo_intensity, 45)
        self.assertEqual(self.store.get_preference("presence"), canvas)
        self.assertEqual(self.store.get_preference("presence_gpu")["future_gpu"], "preserved")
        self.assertTrue(self.studio.apply())
        self.assertEqual(self.view.write_calls, 1)

    def test_failed_save_and_unavailable_preview_keep_the_draft_honestly(self):
        self.studio.change(particle_size=175)
        self.view.save_available = self.view.preview_available = False
        self.assertFalse(self.studio.apply())
        self.assertIn("impossible", self.studio.status.get())
        self.assertIn("particle_size", self.studio.dirty)
        self.assertFalse(self.studio.preview())
        self.assertFalse(self.studio.previewing)
        self.assertIn("indisponible", self.studio.status.get())
        self.assertEqual(self.view.end_calls, 0)
        self.assertEqual(self.view.write_calls, 0)

    def test_real_activity_suspends_only_preview_and_keeps_unapplied_values(self):
        self.studio.change(ring_speed=170)
        self.assertTrue(self.studio.preview())
        self.view.app.voice.listening = True
        self.studio.suspend_preview()
        self.assertFalse(self.studio.previewing)
        self.assertEqual(self.studio.draft.ring_speed, 170)
        self.assertEqual(self.view.gpu_settings.ring_speed, 100)
        self.assertEqual(self.view.end_calls, 1)
        self.assertTrue(self.view.app.voice.listening)
        self.assertFalse(self.studio.compare())

    def test_preset_restore_and_external_rebase_are_transactions(self):
        self.studio.change(core_size=120, halo_radius=200)
        external = GpuSettings.from_dict(self.view.gpu_settings.to_dict() | {"core_size": 80})
        self.view.gpu_settings = external
        self.studio.rebase(external, {"core_size"})
        self.assertEqual(self.studio.draft.core_size, 80)
        self.assertEqual(self.studio.draft.halo_radius, 200)
        self.assertEqual(self.studio.dirty, {"halo_radius"})
        self.assertTrue(self.studio.load_preset("eco"))
        self.assertEqual(self.studio.draft, GpuSettings(profile="eco"))
        self.assertEqual(self.view.gpu_settings, external)
        self.studio.restore()
        self.assertEqual(self.studio.draft, GpuSettings())
        self.assertEqual(self.view.write_calls, 0)

    def test_global_search_and_favourite_focus_find_the_real_expert_slider(self):
        self.studio.query.set("anneau 3")
        self.root.update()
        self.assertTrue(self.studio.rows["ring_3_tilt"].winfo_manager())
        self.assertTrue(self.studio.focus_control("audio_release_ms"))
        self.root.update()
        self.assertEqual(self.studio.section.get(), "Halo et lumière")
        slider = self.studio.controls["audio_release_ms"]
        self.assertIs(self.studio.window.focus_get(), slider)
        self.assertGreaterEqual(slider.winfo_rooty(), self.studio.canvas.winfo_rooty())
        self.assertLessEqual(slider.winfo_rooty()+slider.winfo_height(),
                             self.studio.canvas.winfo_rooty()+self.studio.canvas.winfo_height())
        self.assertFalse(self.studio.focus_control("missing"))
        before = self.studio.draft.audio_release_ms
        slider.event_generate("<Right>")
        self.root.update()
        self.assertEqual(self.studio.draft.audio_release_ms, before+1)
        self.studio.window.event_generate("<Control-f>")
        self.root.update()
        self.assertIs(self.studio.window.focus_get(), self.studio.search)

    def test_direct_previews_are_explicit_and_no_callback_survives_close(self):
        for label in PREVIEW_STATES:
            self.assertTrue(self.studio.preview_state(label))
        self.assertFalse(self.studio.preview_state("missing"))
        self.assertEqual(tuple(self.view.states), PREVIEW_STATES)
        self.assertIn("synthétique", self.studio.status.get())
        old_dirty = set(self.studio.dirty)
        self.studio.window.destroy()
        self.assertTrue(self.studio.closed)
        self.assertEqual(self.view.end_calls, 1)
        self.assertIsNone(self.studio._query_trace)
        self.assertEqual(self.studio.dirty, old_dirty)
        self.assertFalse(self.root.tk.call("after", "info"))

    def test_small_portrait_and_landscape_keep_actions_accessible_at_several_dpi(self):
        for dpi in (1., 2., 2.5):
            self.root.tk.call("tk", "scaling", dpi*96/72)
            for width, height in ((360, 540), (600, 400)):
                with self.subTest(dpi=dpi, size=(width, height)):
                    self.studio.window.geometry(f"{width}x{height}")
                    self.root.update()
                    left, top = self.studio.window.winfo_rootx(), self.studio.window.winfo_rooty()
                    right, bottom = left+self.studio.window.winfo_width(), top+self.studio.window.winfo_height()
                    for button in self.studio.action_buttons.values():
                        self.assertTrue(button.winfo_viewable())
                        self.assertGreaterEqual(button.winfo_rootx(), left)
                        self.assertGreaterEqual(button.winfo_rooty(), top)
                        self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), right)
                        self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), bottom)
                    self.assertTrue(self.studio.focus_control("particle_size"))
                    self.root.update()
                    self.assertTrue(self.studio.controls["particle_size"].winfo_viewable())


if __name__ == "__main__":
    unittest.main()
