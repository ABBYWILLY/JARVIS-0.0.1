"""Native navigation and canonical settings, offline without audio devices."""
import gc
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from jarvis.control_center import FAMILIES, ROUTES, find_routes
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
        for dpi in (1., 2.5):
            self.root.tk.call("tk", "scaling", 96 / 72 * dpi)
            center = self.app.open_control_center()
            for size in ("360x340", "620x380", "380x640"):
                center.window.geometry(size)
                self.root.update()
                for widget in (center.search, center.category, center.results, center.open_button):
                    self.assert_inside(widget, center.window)
                self.assertGreater(center.results.winfo_height(), 10)
            center.window.destroy()

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
