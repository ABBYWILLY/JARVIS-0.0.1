"""Navigation geometry on a real Tk display, without models or audio devices."""
import gc
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class ResponsiveNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "navigation.sqlite3"
        self.app = self.root = None
        self.open_app()
        self.addCleanup(self.close_app)

    def open_app(self, scale=1):
        self.root = tk.Tk()
        self.root.tk.call("tk", "scaling", 96 / 72 * scale)
        self.app = App(self.root, Store(self.path), refresh=False)
        self.root.after_cancel(self.app.poll_id)
        self.root.update()

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.app = self.root = None
        gc.collect()

    def assert_in_client(self, widget):
        self.assertTrue(widget.winfo_viewable(), str(widget))
        x = widget.winfo_rootx() - self.root.winfo_rootx()
        y = widget.winfo_rooty() - self.root.winfo_rooty()
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + widget.winfo_width(), self.root.winfo_width())
        self.assertLessEqual(y + widget.winfo_height(), self.root.winfo_height())
        # A mapped sliver is not an accessible button: its label must fit too.
        self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth())
        self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight())

    def test_presence_conversation_stop_and_send_fit_portrait_landscape_small_and_dpi(self):
        for scale in (1, 1.5, 2, 2.5):
            self.close_app()
            self.open_app(scale)
            for geometry in ("1100x620", "620x900", "640x480", "560x400"):
                with self.subTest(scale=scale, geometry=geometry):
                    self.root.geometry(geometry)
                    self.root.update()
                    for button in (self.app.sidebar_button, self.app.conversation_button,
                                   self.app.presence_button, self.app.emergency_button,
                                   self.app.send_button, self.app.stop_button):
                        self.assert_in_client(button)
                    self.assertGreater(self.app.chat.winfo_height(), 0)
                    self.assertIs(self.app.presence_button.master, self.app.navigation)

    def test_sidebar_collapses_persists_and_opens_as_an_overlay_in_a_narrow_window(self):
        if not self.app.sidebar.winfo_manager():
            self.app.toggle_sidebar()
            self.root.update()
        self.app.toggle_sidebar()
        self.root.update()
        self.assertEqual(self.app.sidebar.winfo_manager(), "")
        self.assertTrue(self.app.store.get_preference("sidebar_collapsed"))
        self.close_app()
        self.open_app()
        self.assertEqual(self.app.sidebar.winfo_manager(), "")
        self.root.geometry("620x700")
        self.root.update()
        chat_width = self.app.chat.winfo_width()
        self.app.toggle_sidebar()
        self.root.update()
        self.assertEqual(self.app.sidebar.winfo_manager(), "place")
        self.assertEqual(self.app.chat.winfo_width(), chat_width)
        self.assertFalse(self.app.store.get_preference("sidebar_collapsed"))
        self.app.conversation_button.invoke()
        self.root.update()
        self.assertEqual(self.app.sidebar.winfo_manager(), "")
        self.assert_in_client(self.app.presence_button)

    def test_secondary_controls_scroll_and_keyboard_focus_reveals_them_without_moving_navigation(self):
        self.root.geometry("620x480")
        self.root.update()
        if not self.app.sidebar.winfo_manager():
            self.app.toggle_sidebar()
        self.root.update()
        canvas = self.app.sidebar_canvas
        self.assertGreater(self.app.sidebar_content.winfo_height(), canvas.winfo_height())
        before = self.app.presence_button.winfo_rooty()
        canvas.yview_moveto(0)
        self.app._reveal_sidebar_focus(SimpleNamespace(widget=self.app.memory_button))
        self.root.update()
        top = self.app.memory_button.winfo_rooty() - canvas.winfo_rooty()
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(top + self.app.memory_button.winfo_height(), canvas.winfo_height())
        self.assertEqual(self.app.presence_button.winfo_rooty(), before)
        canvas.yview_moveto(0)
        self.app._sidebar_wheel(SimpleNamespace(widget=self.app.settings_button, delta=-120, num=None))
        self.assertGreater(canvas.yview()[0], 0)
        position = canvas.yview()
        self.app._sidebar_wheel(SimpleNamespace(widget=self.app.history, delta=-120, num=None))
        self.assertEqual(canvas.yview(), position)

    def test_keyboard_and_fixed_buttons_work_during_generation(self):
        self.app.busy("chat")
        try:
            for button in (self.app.sidebar_button, self.app.presence_button,
                           self.app.conversation_button, self.app.emergency_button):
                self.assertNotIn("disabled", button.state())
            with patch.object(self.app.presence, "show") as show:
                self.app.presence_button.invoke()
                show.assert_called_once()
                binding = self.root.bind("<F7>")
                self.assertTrue(binding)
                callback = binding.split("[", 1)[1].split()[0]
                self.root.tk.call(callback, "test-key-event")
                self.assertEqual(show.call_count, 2)
            with patch.object(self.app.voice, "emergency") as stop:
                self.app.emergency_button.invoke()
                stop.assert_called_once()
            with patch.object(self.app.input, "focus_set") as focus:
                binding = self.root.bind("<F8>")
                callback = binding.split("[", 1)[1].split()[0]
                self.root.tk.call(callback)
                focus.assert_called_once()
            self.assertTrue(self.root.bind("<F6>"))
        finally:
            self.app.busy(None)

    def test_compact_status_can_be_read_in_full_by_an_explicit_action(self):
        text = "Erreur détaillée : " + "vérifier le périphérique sélectionné et les autorisations. " * 5
        self.app.status.set(text)
        self.root.geometry("560x400")
        self.root.update()
        with patch("jarvis.ui.messagebox.showinfo") as detail:
            self.app.show_status()
        self.assertEqual(detail.call_args.args[1], text)
        self.assertEqual(self.app.status.get(), text)


if __name__ == "__main__":
    unittest.main()
