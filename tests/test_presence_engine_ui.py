"""Actual engine selector widgets and SQLite, without GL or audio devices."""
from pathlib import Path
import sqlite3
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis.presence_engine import ENGINE_LABELS
from jarvis.presence_host import IntegratedPresence
from jarvis.storage import Store
from tests.test_jarvis import display_available


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class EngineSelectorTkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / "engines.sqlite3")
        self.addCleanup(self.store.close)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.app = SimpleNamespace(root=self.root, store=self.store, font_family="DejaVu Sans",
            voice=SimpleNamespace(set_visual_spectrum=Mock()), set_status=Mock(), operation=None)
        self.view = IntegratedPresence(self.app)
        self.addCleanup(self.view.close)
        self.dialog = self.view.open_engine_settings()
        self.root.update()

    def assert_inside(self, widget, container):
        self.assertTrue(widget.winfo_viewable())
        left = widget.winfo_rootx() - container.winfo_rootx()
        top = widget.winfo_rooty() - container.winfo_rooty()
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(left + widget.winfo_width(), container.winfo_width())
        self.assertLessEqual(top + widget.winfo_height(), container.winfo_height())

    def choose(self, key):
        self.dialog.engine_choice.set(ENGINE_LABELS[key])
        self.dialog.engine_combo.event_generate("<<ComboboxSelected>>")
        self.root.update()

    def test_open_reopen_and_escape_make_no_preference_write_or_callbacks(self):
        with patch.object(self.store, "set_preference") as save:
            self.assertIs(self.view.open_engine_settings(), self.dialog)
            self.assertEqual(tuple(self.dialog.engine_combo.cget("values")), tuple(ENGINE_LABELS.values()))
            self.assertEqual(self.dialog.engine_choice.get(), ENGINE_LABELS["canvas"])
            self.assertIn(ENGINE_LABELS["canvas"], self.view.engine_status.get())
            self.assertIsNone(self.view._gpu)
            save.assert_not_called()
        self.dialog.focus_force()
        self.dialog.event_generate("<Escape>")
        self.root.update()
        self.assertFalse(self.dialog.winfo_exists())
        self.assertEqual(tuple(self.root.tk.call("after", "info")), ())

    def test_selection_and_failed_write_keep_preference_and_actual_engine_distinct(self):
        with patch.object(self.view, "show") as show:
            self.choose("gpu")
            self.assertEqual(self.store.get_preference("presence_engine")["mode"], "gpu")
            self.assertEqual(self.dialog.engine_choice.get(), ENGINE_LABELS["gpu"])
            # No renderer has reported readiness; the active engine stays 2D.
            self.assertIn(ENGINE_LABELS["canvas"], self.view.engine_status.get())
            show.assert_called_once_with()
            with patch.object(self.store, "set_preference", side_effect=sqlite3.OperationalError("full")):
                self.choose("canvas")
            self.assertEqual(self.dialog.engine_choice.get(), ENGINE_LABELS["gpu"])
            self.assertEqual(self.view.engine_preferences.mode, "gpu")
            self.assertEqual(self.store.get_preference("presence_engine")["mode"], "gpu")
            self.assertEqual(show.call_count, 1)
            self.app.set_status.assert_called()

    def test_common_controls_use_existing_preferences_and_rollback_failed_save(self):
        self.dialog.common_controls["reduced_motion"].invoke()
        self.assertTrue(self.view.settings.reduced_motion)
        self.assertTrue(self.store.get_preference("presence")["reduced_motion"])
        self.assertIsNone(self.store.get_preference("presence_gpu"))
        original = self.view.settings.subtitles
        with patch.object(self.store, "set_preference", side_effect=sqlite3.OperationalError("full")), \
                patch("jarvis.presence.messagebox.showerror") as error:
            self.dialog.common_controls["subtitles"].invoke()
            error.assert_called_once()
        self.assertEqual(self.view.settings.subtitles, original)
        self.assertEqual(self.dialog.common_variables["subtitles"].get(), original)

    def test_small_windows_and_dpi_keep_close_fixed_and_keyboard_controls_reachable(self):
        original = self.root.tk.call("tk", "scaling")
        self.addCleanup(lambda: self.root.tk.call("tk", "scaling", original))
        for scale in (1., 2., 2.5):
            self.root.tk.call("tk", "scaling", scale * 96/72)
            for size in ("340x300", "620x340", "360x640"):
                with self.subTest(scale=scale, size=size):
                    self.dialog.geometry(size)
                    self.root.update()
                    self.assert_inside(self.dialog.close_button, self.dialog)
                    for control in (self.dialog.engine_combo, *self.dialog.editor_buttons.values(),
                                    *self.dialog.common_controls.values()):
                        control.focus_force()
                        self.root.update()
                        self.assertIs(self.root.focus_get(), control)
                        self.assert_inside(control, self.dialog.scroll_canvas)
                    # Native keyboard traversal remains available after scrolling.
                    self.dialog.engine_combo.focus_force()
                    self.root.update()
                    self.dialog.engine_combo.event_generate("<Tab>")
                    self.root.update()
                    self.assertIs(self.root.focus_get(), self.dialog.editor_buttons["canvas"])


if __name__ == "__main__":
    unittest.main()
