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
from jarvis.markdown_view import ConversationTypography
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
                                   self.app.send_button, self.app.continue_button, self.app.stop_button):
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

    def reading_control(self, name):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        return next(widget for widget in descendants(self.app.conversation_dialog)
                    if widget.winfo_name() == name)

    def test_reading_controls_save_real_fonts_and_accents_without_starting_audio_or_inference(self):
        with patch.object(self.app.voice.capture, "start") as capture, patch.object(self.app.worker, "start") as inference:
            self.app.open_conversation_settings()
            self.root.update()
            self.reading_control("size").delete(0, "end")
            self.reading_control("size").insert(0, "17")
            self.reading_control("spacing").set("Compact")
            code = self.app.markdown.code_families[0]
            self.reading_control("code_family").set(code)
            self.reading_control("accent_intensity").set(23)
            footer = next(frame for frame in self.app.conversation_dialog.winfo_children()
                          if any(child.winfo_class() == "TButton" for child in frame.winfo_children()))
            next(button for button in footer.winfo_children() if button.cget("text") == "Enregistrer").invoke()
            self.assertIsNone(self.app.conversation_dialog)
            self.assertEqual(self.app.typography.size, 17)
            self.assertEqual(self.app.typography.spacing, "compact")
            self.assertEqual(self.app.typography.code_family, code)
            self.assertEqual(self.app.typography.accent_intensity, 23)
            self.assertEqual(self.app.markdown.body_font.actual("size"), 17)
            self.assertEqual(self.app.store.get_preference("conversation")["accent_intensity"], 23)
            capture.assert_not_called()
            inference.assert_not_called()
        self.root.update()
        for button in (self.app.send_button, self.app.stop_button, self.app.presence_button):
            self.assert_in_client(button)

    def test_reading_reset_preserves_history_voice_presence_and_future_preference_keys(self):
        source = "# Une réponse **originale** 😊\n++Été++ et ~~ancien~~."
        message = self.app.store.begin_turn(self.app.session_id, "Question", "local")
        self.app.store.update_response(message, source, "complete")
        voice = self.app.voice.settings.to_dict()
        self.app.store.set_preference("voice", voice)
        self.app.store.set_preference("presence", {"wave_expressivity": 42})
        self.app.conversation_preferences = {"future_option": "préserver"}
        self.app.set_conversation_typography(size=18, accent_intensity=12, spacing="compact")
        self.app.render_session()
        region = self.app.markdown.regions[0]
        selected = self.app.chat.search("originale", region.start)
        self.app.chat.tag_add("sel", selected, self.app.markdown.offset(selected, "originale"))
        with patch("jarvis.markdown_view.parse_text", side_effect=AssertionError("archive reparsed")):
            self.app.open_conversation_settings()
            self.root.update()
            self.reading_control("reset_typography").invoke()
        self.assertEqual(self.app.typography, ConversationTypography())
        self.assertEqual(self.app.store.get_preference("conversation")["future_option"], "préserver")
        self.assertEqual(self.app.store.get_preference("presence"), {"wave_expressivity": 42})
        self.assertEqual(self.app.store.get_preference("voice"), voice)
        self.assertEqual(self.app.store.message(message)["content"], source)
        self.assertEqual(self.app.chat.get("sel.first", "sel.last"), "originale")
        self.app.conversation_dialog.destroy()
        self.close_app()
        self.open_app()
        self.assertEqual(self.app.typography, ConversationTypography())

    def test_metrics_are_discreet_by_default_and_an_existing_choice_survives_restart(self):
        self.assertFalse(self.app.metrics_visible.get())
        self.assertTrue(self.root.tk.getboolean(self.app.chat.tag_cget("metrics", "elide")))
        self.app.metrics_visible.set(True)
        self.app.toggle_metrics()
        self.close_app()
        self.open_app()
        self.assertTrue(self.app.metrics_visible.get())
        self.assertFalse(self.root.tk.getboolean(self.app.chat.tag_cget("metrics", "elide")))

    def test_largest_reading_font_does_not_hide_controls_in_small_high_dpi_windows(self):
        for scale in (1, 2, 2.5):
            with self.subTest(scale=scale):
                self.close_app()
                self.open_app(scale)
                self.app.set_conversation_typography(size=24, scale=175)
                self.root.geometry("560x400")
                self.root.update()
                for button in (self.app.presence_button, self.app.send_button, self.app.continue_button, self.app.stop_button):
                    self.assert_in_client(button)
                self.assertGreater(self.app.chat.winfo_height(), 0)
                self.assertEqual(self.app.markdown.body_font.actual("size"), 42)
                self.assertLessEqual(self.app.input_font.actual("size"), 18)

    def test_native_message_selection_survives_resize_without_allocating_new_surfaces(self):
        source = "# Été 😊\n**Texte choisi** et `code`.\n| Nom | Prix |\n| --- | --- |\n| Été | 12 € |"
        message = self.app.store.begin_turn(self.app.session_id, "Mon message brut **inchangé**", "local")
        self.app.store.update_response(message, source, "complete")
        self.app.render_session()
        region = self.app.markdown.regions[0]
        selected = self.app.chat.search("Texte choisi", region.start)
        self.app.chat.tag_add("sel", selected, self.app.markdown.offset(selected, "Texte choisi"))
        text_widget = self.app.chat
        items = (self.app.chat_surface.find_all(), self.app.input_surface.find_all())
        for geometry in ("1100x620", "620x900", "560x400"):
            self.root.geometry(geometry)
            self.root.update()
            self.assertIs(self.app.chat, text_widget)
            self.assertTrue(self.app.chat_scroll.winfo_viewable())
            self.assertEqual(self.app.chat.get("sel.first", "sel.last"), "Texte choisi")
            self.assertEqual((self.app.chat_surface.find_all(), self.app.input_surface.find_all()), items)
            self.app.chat.event_generate("<<Copy>>")
            self.assertEqual(self.root.clipboard_get(), "Texte choisi")
        self.assertIn("Mon message brut **inchangé**", self.app.chat.get("1.0", "end"))
        self.assertEqual(self.app.store.message(message)["content"], source)


if __name__ == "__main__":
    unittest.main()
