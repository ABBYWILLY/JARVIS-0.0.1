"""Rich Tk conversation contracts: no model, browser or system action is run."""
import gc
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import font
import unittest
from unittest.mock import patch

from jarvis.markdown_view import ConversationTypography, MarkdownView
from jarvis.richtext import parse_text
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available


class TypographyValidationTests(unittest.TestCase):
    def test_preferences_validate_available_fonts_and_bounded_numeric_values(self):
        value = ConversationTypography.from_dict({"family": "test font", "size": 18,
            "scale": 125, "spacing": "compact"}, ("Test Font",))
        self.assertEqual(value.to_dict(), {"family": "Test Font", "size": 18, "scale": 125, "spacing": "compact"})
        for raw in (None, [], {"family": "missing", "size": True, "scale": 999, "spacing": []}):
            self.assertEqual(ConversationTypography.from_dict(raw, ("Test Font",)), ConversationTypography())


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class RichConversationWidgetTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("700x450")
        self.widget = tk.Text(self.root, wrap="word", state="disabled")
        self.widget.pack(fill="both", expand=True)
        self.view = MarkdownView(self.widget, "TkDefaultFont", "black", "gray", "blue", "#eeeeee")
        self.root.update()

    def tearDown(self):
        self.view.close()
        self.root.destroy()
        self.view = self.widget = self.root = None
        gc.collect()

    def tagged(self, name):
        ranges = self.widget.tag_ranges("md_" + name)
        return [self.widget.get(a, b) for a, b in zip(ranges[::2], ranges[1::2])]

    def test_rich_styles_lists_tables_and_hierarchy_share_existing_tags(self):
        source = ("# Titre\n## Sous-titre\n### Section\n"
                  "***lié*** ++souligné++ ==éclairé==\n- élément\n  2. second\n\n---\n"
                  "| Nom | Valeur |\n| --- | --- |\n| **été** | 12 € 😊 |\n")
        region = self.view.append(source)
        displayed = self.widget.get(region.start, region.end)
        self.assertIn("• élément", displayed)
        self.assertIn("2. second", displayed)
        self.assertIn("été", displayed)
        self.assertIn("12 € 😊", displayed)
        self.assertIn("souligné", self.tagged("underline"))
        self.assertIn("éclairé", self.tagged("highlight"))
        self.assertTrue(self.widget.tag_ranges("md_separator"))
        self.assertTrue(self.widget.tag_ranges("md_list_depth_1"))
        position = self.widget.search("Nom", region.start)
        table_fonts = [name for name in self.widget.tag_names(position) if name.startswith("md_font_")]
        self.assertEqual(len(table_fonts), 1)
        actual = font.Font(root=self.root, font=self.widget.tag_cget(table_fonts[0], "font"))
        self.assertEqual(actual.actual("family"), self.view.fixed_family)
        self.assertEqual(actual.actual("weight"), "bold")
        del actual
        sizes = []
        for word in ("Titre", "Sous-titre", "Section", "souligné"):
            position = self.widget.search(word, region.start)
            name = next(name for name in self.widget.tag_names(position) if name.startswith("md_font_"))
            sizes.append(int(self.widget.tk.call("font", "actual", self.widget.tag_cget(name, "font"), "-size")))
        self.assertTrue(all(a > b for a, b in zip(sizes, sizes[1:])))
        self.assertEqual(region.original, source)

    def test_font_changes_reuse_fonts_and_keep_source_selection_and_viewport(self):
        source = "\n".join(f"Texte **choisi {i}** et été 👩🏽‍💻." for i in range(80))
        region = self.view.append(source)
        self.root.update()
        self.widget.yview_moveto(.35)
        first = self.widget.index("@0,0")
        selected = self.widget.search("choisi 31", region.start)
        self.widget.tag_add("sel", selected, self.view.offset(selected, "choisi 31"))
        old_fonts = {key: id(face) for key, (_, face) in self.view.fonts.items()}
        settings = ConversationTypography(family=self.view.family, size=17, scale=125, spacing="compact")
        with patch("jarvis.markdown_view.parse_text", side_effect=AssertionError("historical text re-parsed")):
            self.view.configure_typography(settings)
        self.assertEqual(old_fonts, {key: id(face) for key, (_, face) in self.view.fonts.items()})
        self.assertEqual(self.widget.get("sel.first", "sel.last"), "choisi 31")
        self.assertEqual(self.widget.index("@0,0"), first)
        self.assertEqual(self.widget.get(region.start, region.end), parse_text(source).text)
        self.assertEqual(region.original, source)
        self.widget.event_generate("<<Copy>>")
        self.assertEqual(self.widget.clipboard_get(), "choisi 31")
        self.view.copy_original()
        self.assertEqual(self.widget.clipboard_get(), source)
        self.assertEqual(self.widget.get("sel.first", "sel.last"), "choisi 31")

    def test_only_active_region_is_parsed_and_link_cache_is_bounded(self):
        history = self.view.append("\n".join(f"Archive {i} : **été**" for i in range(90)))
        archived = self.widget.get(history.start, history.end)
        current = self.view.append("début", final=False)
        with patch("jarvis.markdown_view.parse_text", wraps=parse_text) as scanner:
            for i in range(5):
                self.view.update(current, "début " + "**nouveau** " * (i + 1))
            self.assertEqual(scanner.call_count, 5)
        self.assertEqual(self.widget.get(history.start, history.end), archived)
        source = " ".join(f"[lien{i}](https://example.com/{i})" for i in range(300))
        links = self.view.append(source)
        self.assertEqual(self.widget.get(links.start, links.end).count("lien"), 300)
        self.assertLessEqual(len(self.view.links), 256)
        self.assertLessEqual(len(self.view.fonts), 56)
        self.view.reset()
        self.assertEqual(self.view.regions, [])
        self.assertEqual(self.view.links, {})

    def test_opening_a_link_requires_valid_https_and_separate_user_confirmation(self):
        with patch("jarvis.markdown_view.messagebox.askyesno", return_value=True) as confirm, \
             patch("jarvis.markdown_view.webbrowser.open", return_value=True) as browser:
            for url in ("javascript:alert(1)", "file:///C:/secret", "https://127.0.0.1/x", "https://user:pw@example.com"):
                self.assertFalse(self.view.open_link(url))
            browser.assert_not_called()
            confirm.assert_not_called()
            url = "https://example.com/été"
            confirm.return_value = False
            self.assertFalse(self.view.open_link(url))
            browser.assert_not_called()
            confirm.return_value = True
            self.assertTrue(self.view.open_link(url))
            browser.assert_called_once_with(url, new=2)
            self.assertEqual(confirm.call_count, 2)

    def test_font_and_streamed_unicode_survive_resolutions_and_dpi_scales(self):
        scaling = self.root.tk.call("tk", "scaling")
        try:
            for scale, geometry in ((1, "650x400"), (2, "900x600"), (2.5, "620x440")):
                with self.subTest(scale=scale):
                    self.root.tk.call("tk", "scaling", 96 / 72 * scale)
                    self.root.geometry(geometry)
                    self.view.reset()
                    self.widget.configure(state="normal")
                    self.widget.delete("1.0", "end")
                    self.widget.configure(state="disabled")
                    region = self.view.append("🚀 **été", final=False)
                    self.view.configure_typography(ConversationTypography(size=18, scale=125))
                    self.view.update(region, "🚀 **été** et ++français++ 😊", final=True)
                    self.root.update()
                    self.assertEqual(self.widget.get(region.start, region.end), "🚀 été et français 😊")
                    self.assertIn("été", self.tagged("bold"))
                    self.assertIn("français", self.tagged("underline"))
                    self.assertEqual(self.widget.cget("wrap"), "word")
                    self.assertGreater(self.view.body_font.metrics("linespace"), 0)
        finally:
            self.root.tk.call("tk", "scaling", scaling)


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class ConversationPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "conversation.sqlite3"
        self.open_app()
        self.addCleanup(self.close_app)

    def open_app(self):
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.root.after_cancel(self.app.poll_id)
        self.root.update()

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.app = self.root = self.store = None
        gc.collect()

    def test_preferences_survive_reopen_and_original_history_is_unchanged(self):
        source = "# Titre **été** 😊\n\n++précis++ et ==utile==."
        message = self.store.begin_turn(self.app.session_id, "Question **littérale**", "test")
        self.store.update_response(message, source, "complete")
        self.store.set_preference("presence", {"wave_expressivity": 65})
        self.app.render_session()
        family = self.app.markdown.family
        self.app.set_conversation_typography(family=family, size=18, scale=125, spacing="compact")
        region = self.app.markdown.regions[0]
        self.app.chat.mark_set("insert", region.start)
        self.app.markdown.copy_original()
        self.assertEqual(self.root.clipboard_get(), source)
        self.assertEqual(self.store.message(message)["content"], source)
        self.assertEqual(self.store.get_preference("presence"), {"wave_expressivity": 65})
        self.close_app()
        self.open_app()
        self.assertEqual(self.app.typography, ConversationTypography(family=family, size=18, scale=125, spacing="compact"))
        self.assertEqual(self.store.message(message)["content"], source)
        self.assertEqual(self.app.chat.cget("font"), str(self.app.markdown.body_font))
        self.assertIn("Titre été 😊", self.app.chat.get("1.0", "end-1c"))
        with self.assertRaises(ValueError):
            self.app.set_conversation_typography(family="not installed", size=999)
        self.assertEqual(self.app.typography.size, 18)

    def test_reading_dialog_keeps_footer_and_its_settings_reachable(self):
        scaling = self.root.tk.call("tk", "scaling")
        try:
            for scale in (1, 2, 2.5):
                self.root.tk.call("tk", "scaling", 96 / 72 * scale)
                self.app.open_conversation_settings()
                self.root.update()
                dialog = self.app.conversation_dialog
                frames = dialog.winfo_children()
                footer = next(frame for frame in frames if any(child.winfo_class() == "TButton" for child in frame.winfo_children()))
                self.assertEqual({button.cget("text") for button in footer.winfo_children()}, {"Enregistrer", "Fermer"})
                self.assertLessEqual(footer.winfo_y() + footer.winfo_height(), dialog.winfo_height())
                dialog.destroy()
                self.assertIsNone(self.app.conversation_dialog)
        finally:
            self.root.tk.call("tk", "scaling", scaling)


if __name__ == "__main__":
    unittest.main()
