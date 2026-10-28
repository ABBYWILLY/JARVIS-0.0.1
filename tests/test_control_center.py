"""Native navigation and canonical settings, offline without audio devices."""
import gc
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import sqlite3
import unittest
from unittest.mock import patch

from jarvis.control_center import FAMILIES, LEVELS, ROUTES, VIEWS, find_routes, navigation_preferences
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available


class SettingsSearchTests(unittest.TestCase):
    def test_five_families_search_accent_and_advanced_revelation(self):
        self.assertEqual(len(FAMILIES), 5)
        self.assertEqual(len({r.key for r in ROUTES}), len(ROUTES))
        self.assertEqual({r.key for r in find_routes("MICROPHONE TRANSCRIPTION")}, {"diagnostics"})
        self.assertIn("presence", {r.key for r in find_routes("epaisseur")})
        self.assertIn("reading", {r.key for r in find_routes("souligné")})
        self.assertIn("gpu", {r.key for r in find_routes("OpenGL")})
        self.assertFalse(any(r.advanced for r in find_routes(family=FAMILIES[4])))
        self.assertTrue(any(r.advanced for r in find_routes(family=FAMILIES[4], advanced=True)))
        self.assertFalse(find_routes("réglage inexistant xyz"))

    def test_progressive_levels_and_global_search_keep_every_route_reachable(self):
        self.assertEqual(tuple(LEVELS.values()), ("Essentiel", "Personnaliser", "Avancé"))
        essential = {route.key for route in find_routes(level="essential")}
        personal = {route.key for route in find_routes(level="personalize")}
        advanced = {route.key for route in find_routes(level="advanced")}
        self.assertLess(essential, personal)
        self.assertLess(personal, advanced)
        self.assertEqual(advanced, {route.key for route in ROUTES})
        for route in ROUTES:
            self.assertIn(route, find_routes(route.title, family=FAMILIES[0], level="essential"))
        self.assertTrue(all(route.control and route.owner for route in ROUTES if route.key == "wave_thickness"))

    def test_navigation_data_is_bounded_deduplicated_and_contains_no_parameter_values(self):
        for raw in (None, [], "voice", {"favorites": "voice"}, {"favorites": {}},
                    {"favorites": [None, [], {}, 5]}, {"view": []}):
            with self.subTest(raw=raw):
                self.assertEqual(navigation_preferences(raw), ((), "essential"))
        favorites, view = navigation_preferences({"favorites": ["voice", "voice", "missing", "halo"],
                                                  "view": "favorites", "speed": 100})
        self.assertEqual((favorites, view), (("voice", "halo"), "favorites"))
        self.assertEqual(len(navigation_preferences({"favorites": ["voice"] * 10000})[0]), 1)
        routes = find_routes(level="essential", favorites=favorites, only_favorites=True)
        self.assertEqual({route.key for route in routes}, {"voice", "halo"})
        self.assertTrue(all(route.key in favorites for route in routes))

    def test_both_engines_and_gpu_essentials_have_canonical_navigation(self):
        from jarvis.gpu_config import FIELD_SPECS
        routes = {route.key: route for route in ROUTES}
        self.assertEqual(routes["gpu"].family, FAMILIES[0])
        self.assertEqual(routes["presence_engine"].family, FAMILIES[0])
        self.assertIn(routes["presence_engine"], find_routes("2.5d", level="essential"))
        gpu_fields = {route.control for route in ROUTES if route.owner == "gpu"}
        self.assertEqual(gpu_fields, {key for key, spec in FIELD_SPECS.items() if spec.level == "essential"})
        old_favorites = ["presence", "gpu", "wave_thickness", "halo"]
        self.assertEqual(navigation_preferences({"favorites": old_favorites})[0], tuple(old_favorites))


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class ControlCenterTkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "controls.sqlite3")
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.addCleanup(self.close)

    def close(self):
        if not self.app.closed:
            self.app.close()
        self.app = self.root = self.store = None
        gc.collect()

    def assert_inside(self, widget, window):
        self.assertTrue(widget.winfo_viewable())
        x = widget.winfo_rootx() - window.winfo_rootx()
        y = widget.winfo_rooty() - window.winfo_rooty()
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + widget.winfo_width(), window.winfo_width())
        self.assertLessEqual(y + widget.winfo_height(), window.winfo_height())

    def test_existing_editors_are_dispatched_without_copied_preferences(self):
        center = self.app.open_control_center()
        style = ttk.Style(self.root)
        self.assertEqual(style.lookup("Control.Treeview", "fieldbackground"), "#192638")
        self.assertEqual(style.lookup("Control.Treeview", "foreground"), "#e4edf6")
        with patch.object(self.app.voice, "open_settings") as voice, patch.object(self.app.presence, "open_settings") as presence:
            with patch.object(self.store, "set_preference") as save:
                center.query.set("silence")
                center.open_selected()
                voice.assert_called_once_with()
                center.query.set("morphing")
                center.open_selected()
                presence.assert_called_once_with()
                save.assert_not_called()
        self.assertIs(self.app.open_control_center(), center)
        center.window.destroy()
        self.assertIsNone(self.app.control_center)
        self.assertIsNot(self.app.open_control_center(), center)

    def test_search_keyboard_empty_result_and_no_callbacks_after_close(self):
        center = self.app.open_control_center()
        self.root.update()
        center.window.focus_force()
        center.window.event_generate("<Control-f>")
        self.root.update()
        self.assertIs(self.root.focus_get(), center.search)
        center.query.set("monospace")
        center.search.focus_force()
        self.root.update()
        center.search.event_generate("<Down>")
        self.root.update()
        self.assertIs(self.root.focus_get(), center.results)
        self.assertEqual(center.results.selection(), ("reading",))
        center.query.set("xyz inexistante")
        self.assertIn("disabled", center.open_button.state())
        self.assertIn("Aucun", center.detail.get("1.0", "end"))
        center.window.event_generate("<Escape>")
        self.root.update()
        self.assertIsNone(self.app.control_center)
        # No timer is created by search, selection, closing or reopening.
        self.assertEqual(tuple(self.root.tk.call("after", "info")), (self.app.poll_id,))

    def test_center_small_landscape_portrait_and_dpi(self):
        original_scaling = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", original_scaling))
        for dpi in (1., 2.5):
            self.root.tk.call("tk", "scaling", 96 / 72 * dpi)
            center = self.app.open_control_center()
            for size in ("360x340", "620x380", "380x640"):
                center.window.geometry(size)
                self.root.update()
                for widget in (center.search, center.category, center.level_choice, center.results,
                               center.open_button, center.favorite_button):
                    self.assert_inside(widget, center.window)
                self.assertGreater(center.results.winfo_height(), 10)
            center.window.destroy()

    def test_favorite_and_level_persist_only_navigation_ids_and_preserve_future_keys(self):
        original_model = self.store.settings()
        original_presence = self.store.get_preference("presence")
        original_voice = self.store.get_preference("voice")
        self.store.set_preference("control_center", {"future_navigation": {"keep": True}})
        center = self.app.open_control_center()
        center.query.set("Épaisseur de l’onde")
        center.results.selection_set("wave_thickness")
        center.toggle_favorite()
        self.assertEqual(center.favorite_button.cget("text"), "★")
        center.level.set("Favoris")
        center.query.set("")
        self.assertEqual(center.results.get_children(), ("wave_thickness",))
        saved = self.store.get_preference("control_center")
        self.assertEqual(saved, {"future_navigation": {"keep": True},
                                 "favorites": ["wave_thickness"], "view": "favorites"})
        center.window.destroy()
        center = self.app.open_control_center()
        self.assertEqual(center.level.get(), "Favoris")
        self.assertEqual(center.results.get_children(), ("wave_thickness",))
        center.toggle_favorite()
        self.assertEqual(center.results.get_children(), ())
        self.assertIn("Aucun favori", center.detail.get("1.0", "end"))
        self.assertEqual(self.store.settings(), original_model)
        self.assertEqual(self.store.get_preference("presence"), original_presence)
        self.assertEqual(self.store.get_preference("voice"), original_voice)

    def test_search_in_favorites_is_still_global_and_targets_canonical_controls(self):
        center = self.app.open_control_center()
        center.level.set("Favoris")
        center.query.set("Vitesse de la voix")
        center.results.selection_set("voice_speed")
        with patch.object(self.app.voice, "open_settings") as voice:
            center.open_selected()
        voice.assert_called_once_with(focus_key="speed")
        center.query.set("Épaisseur de l’onde")
        center.results.selection_set("wave_thickness")
        with patch.object(self.app.presence, "open_canvas_settings") as presence:
            center.open_selected()
        presence.return_value.focus_control.assert_called_once_with("visualizer_thickness")
        self.assertEqual(center.favorites, ())

    def test_dual_engine_navigation_opens_one_canonical_editor_without_persisting(self):
        center = self.app.open_control_center()
        with patch.object(self.app.presence, "open_engine_settings") as engine, \
                patch.object(self.app.presence, "open_canvas_settings") as canvas, \
                patch.object(self.app.presence, "open_gpu_settings") as gpu, \
                patch.object(self.store, "set_preference") as save:
            for key, action in (("presence_engine", engine), ("canvas_studio", canvas), ("gpu", gpu)):
                center.query.set(next(route.title for route in ROUTES if route.key == key))
                center.results.selection_set(key)
                center.open_selected()
                action.assert_called_once_with()
            for route in (route for route in ROUTES if route.owner == "gpu"):
                center.query.set(route.title)
                center.results.selection_set(route.key)
                center.open_selected()
                gpu.return_value.focus_control.assert_called_with(route.control)
            save.assert_not_called()

    def test_failed_save_preserves_old_favorites_and_level_and_reports_error(self):
        self.store.set_preference("control_center", {"favorites": ["voice"], "view": "essential"})
        center = self.app.open_control_center()
        center.query.set("morphing")
        center.results.selection_set("presence")
        with patch.object(self.store, "set_preference", side_effect=sqlite3.OperationalError("disk full")):
            center.toggle_favorite()
            self.assertIn("Impossible d’enregistrer", center.detail.get("1.0", "end"))
            center.level.set("Avancé")
        self.assertEqual(center.level.get(), "Essentiel")
        self.assertEqual(center.favorites, ("voice",))
        self.assertEqual(self.store.get_preference("control_center"), {"favorites": ["voice"], "view": "essential"})

    def test_unreadable_navigation_never_overwrites_it_or_blocks_editors(self):
        with patch.object(self.store, "get_preference", side_effect=sqlite3.OperationalError("read failed")):
            center = self.app.open_control_center()
        self.assertIn("Impossible de lire", center.detail.get("1.0", "end"))
        self.assertIn("disabled", center.favorite_button.state())
        with patch.object(self.store, "set_preference") as save:
            center.toggle_favorite()
            center.level.set("Avancé")
            save.assert_not_called()
        with patch.object(self.app.presence, "open_settings") as presence:
            center.open_selected()
        presence.assert_called_once_with()

    def test_keyboard_favorite_toggle_uses_selected_route_and_has_no_extra_timer(self):
        center = self.app.open_control_center()
        self.root.update()
        center.window.focus_force()
        center.results.selection_set("presence")
        center.window.event_generate("<Control-d>")
        self.root.update()
        self.assertEqual(center.favorites, ("presence",))
        center.window.event_generate("<Control-d>")
        self.root.update()
        self.assertEqual(center.favorites, ())
        center.query.set("morphing")
        center.search.focus_force()
        center.search.icursor(0)
        self.root.update()
        center.search.event_generate("<Control-d>")
        self.root.update()
        self.assertEqual(center.query.get(), "morphing")
        self.assertEqual(center.favorites, ("presence",))
        center.window.destroy()
        self.assertEqual(tuple(self.root.tk.call("after", "info")), (self.app.poll_id,))

    def test_model_settings_scroll_focus_and_cancel_preserve_canonical_values(self):
        before = self.store.settings()
        dialog = self.app.open_settings()
        self.assertIs(self.app.open_settings(), dialog)
        dialog.geometry("380x340")
        self.root.update()
        dialog.controls["system_prompt"].focus_force()
        self.root.update()
        self.assert_inside(dialog.save_button, dialog)
        self.assert_inside(dialog.controls["system_prompt"], dialog)
        self.root.setvar(dialog.controls["voice_tokens"].cget("textvariable"), "300")
        dialog.event_generate("<Escape>")
        self.root.update()
        self.assertEqual(self.store.settings(), before)

    def test_metrics_toggle_reuses_its_existing_preference_and_keeps_archive(self):
        center = self.app.open_control_center()
        original = [dict(row) for row in self.store.messages(self.app.session_id)]
        before = self.app.metrics_visible.get()
        center.query.set("métriques")
        center.open_selected()
        self.assertIs(self.store.get_preference("show_generation_metrics", None), not before)
        self.assertEqual([dict(row) for row in self.store.messages(self.app.session_id)], original)


if __name__ == "__main__":
    unittest.main()
