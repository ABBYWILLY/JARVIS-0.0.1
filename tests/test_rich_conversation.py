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
from jarvis.ui import App, READING_PREVIEW
from tests.test_jarvis import display_available


class TypographyValidationTests(unittest.TestCase):
    def test_preferences_validate_available_fonts_and_bounded_numeric_values(self):
        value = ConversationTypography.from_dict({"family": "test font", "size": 18,
            "scale": 125, "spacing": "compact", "accent_intensity": 23, "code_family": "test mono"},
            ("Test Font", "Proportional"), ("Test Mono",))
        self.assertEqual(value.to_dict(), {"family": "Test Font", "size": 18, "scale": 125,
            "spacing": "compact", "accent_intensity": 23, "code_family": "Test Mono"})
        for raw in (None, [], {"family": "missing", "size": True, "scale": 999, "spacing": [],
                              "accent_intensity": True, "code_family": "Proportional"}):
            self.assertEqual(ConversationTypography.from_dict(raw, ("Test Font",)), ConversationTypography())

    def test_accent_endpoints_and_only_measured_monospace_choices_are_allowed(self):
        for intensity in (0, 100):
            value = ConversationTypography.from_dict({"accent_intensity": intensity,
                "code_family": "Installed Proportional"}, ("Installed Proportional",), ("Fixed Font",))
            self.assertEqual(value.accent_intensity, intensity)
            self.assertEqual(value.code_family, "")
        for intensity in (-1, 101, "65", None):
            self.assertEqual(ConversationTypography.from_dict({"accent_intensity": intensity}).accent_intensity, 65)


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

    def test_strikethrough_composes_with_bold_italic_and_leaves_code_literal(self):
        source = "~~***obsolète***~~ et `~~littéral~~` ; ++souligné++ et ==surligné==."
        region = self.view.append(source)
        self.assertEqual(region.text, "obsolète et ~~littéral~~ ; souligné et surligné.")
        self.assertIn("obsolète", self.tagged("strike"))
        position = self.widget.search("obsolète", region.start)
        name = next(name for name in self.widget.tag_names(position) if name.startswith("md_font_"))
        actual = self.widget.tk.call("font", "actual", self.widget.tag_cget(name, "font"))
        actual = dict(zip(actual[::2], actual[1::2]))
        self.assertEqual(actual["-weight"], "bold")
        self.assertEqual(actual["-slant"], "italic")
        self.assertEqual(int(actual["-overstrike"]), 1)
        self.assertNotIn("~~littéral~~", self.tagged("strike"))
        self.assertEqual(region.original, source)

    def test_accent_and_code_font_update_existing_tags_without_reparsing_or_losing_selection(self):
        source = "## Titre\n[guide](https://example.com) ==accent== et `code`"
        region = self.view.append(source)
        selected = self.widget.search("guide", region.start)
        self.widget.tag_add("sel", selected, self.view.offset(selected, "guide"))
        old_fonts = {key: id(face) for key, (_, face) in self.view.fonts.items()}
        code_family = self.view.code_families[-1]
        with patch("jarvis.markdown_view.parse_text", side_effect=AssertionError("historical text re-parsed")):
            self.view.configure_typography(ConversationTypography(code_family=code_family, accent_intensity=0))
        self.assertEqual(self.widget.winfo_rgb(self.widget.tag_cget("md_link", "foreground")),
                         self.widget.winfo_rgb(self.view.foreground))
        self.assertEqual(self.widget.winfo_rgb(self.widget.tag_cget("md_highlight", "background")),
                         self.widget.winfo_rgb(self.widget.cget("background")))
        link_tag = self.view.links["https://example.com"]
        self.assertEqual(self.widget.winfo_rgb(self.widget.tag_cget(link_tag, "foreground")),
                         self.widget.winfo_rgb(self.view.foreground))
        for key, (_, face) in self.view.fonts.items():
            if key[0]:
                self.assertEqual(face.actual("family"), code_family)
                self.assertTrue(face.metrics("fixed"))
        self.assertEqual(old_fonts, {key: id(face) for key, (_, face) in self.view.fonts.items()})
        self.assertEqual(self.widget.get("sel.first", "sel.last"), "guide")
        self.assertEqual(region.original, source)
        self.view.configure_typography(ConversationTypography(accent_intensity=100))
        self.assertEqual(self.widget.winfo_rgb(self.widget.tag_cget(link_tag, "foreground")),
                         self.widget.winfo_rgb(self.view.accent))

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

    def reading_control(self, name):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        return next(widget for widget in descendants(self.app.conversation_dialog)
                    if widget.winfo_name() == name)

    def reading_button(self, label):
        return next(button for frame in self.app.conversation_dialog.winfo_children()
                    for button in frame.winfo_children()
                    if button.winfo_class() == "TButton" and button.cget("text") == label)

    def replace_reading_value(self, name, value):
        control = self.reading_control(name)
        control.delete(0, "end")
        control.insert(0, str(value))

    def test_reading_preview_uses_real_styles_and_live_fonts_without_writes_or_reparsing(self):
        source = "# Archive privée\n++À préserver++ et ==été==."
        message = self.store.begin_turn(self.app.session_id, "Question", "local")
        self.store.update_response(message, source, "complete")
        self.app.render_session()
        saved, typography = self.store.get_preference("conversation"), self.app.typography
        archive = self.app.chat.get("1.0", "end-1c")
        with patch.object(self.app.worker, "start") as inference, patch.object(self.app.voice.capture, "start") as capture:
            self.app.open_conversation_settings()
            self.root.update()
            preview = self.app.conversation_dialog.typography_preview
            widget = preview.widget
            self.assertEqual(preview.regions[0].original, READING_PREVIEW)
            for tag, word in (("underline", "souligné"), ("highlight", "surligné")):
                ranges = widget.tag_ranges("md_" + tag)
                self.assertEqual([widget.get(a, b) for a, b in zip(ranges[::2], ranges[1::2])], [word])
            self.assertTrue(widget.tk.getboolean(widget.tag_cget("md_underline", "underline")))
            self.assertNotEqual(widget.tag_cget("md_highlight", "background"), widget.cget("background"))
            sizes = []
            for word in ("Titre H1", "Sous-titre H2", "Section H3", "Texte courant"):
                index = widget.search(word, "1.0")
                tag = next(tag for tag in widget.tag_names(index) if tag.startswith("md_font_"))
                sizes.append(int(widget.tk.call("font", "actual", widget.tag_cget(tag, "font"), "-size")))
            self.assertTrue(all(a > b for a, b in zip(sizes, sizes[1:])))
            original_fonts = {key: id(face) for key, (_, face) in preview.fonts.items()}
            family = next((name for name in self.app.conversation_families if name != preview.family), preview.family)
            mono = preview.code_families[-1]
            with patch("jarvis.markdown_view.parse_text", side_effect=AssertionError("text reparsed")), \
                 patch.object(self.store, "set_preference", side_effect=AssertionError("preview persisted")):
                self.reading_control("family").set(family)
                self.replace_reading_value("size", 18)
                self.replace_reading_value("scale", 125)
                self.reading_control("spacing").set("Compact")
                self.reading_control("code_family").set(mono)
                self.reading_control("accent_intensity").set(0)
                self.root.update()
            expected_face = font.Font(root=self.root, family=family, size=22)
            self.assertEqual(preview.body_font.actual("family"), expected_face.actual("family"))
            self.assertEqual(preview.typography.family, family)
            del expected_face
            self.assertEqual(preview.body_font.actual("size"), 22)
            self.assertEqual(preview.typography.spacing, "compact")
            self.assertEqual(int(widget.cget("spacing1")), 2)
            self.assertEqual(widget.winfo_rgb(widget.tag_cget("md_highlight", "background")),
                             widget.winfo_rgb(widget.cget("background")))
            self.assertEqual(widget.winfo_rgb(widget.tag_cget("md_heading1", "foreground")),
                             widget.winfo_rgb(preview.foreground))
            self.assertEqual({key: id(face) for key, (_, face) in preview.fonts.items()}, original_fonts)
            self.assertTrue(all(face.actual("family") == mono for key, (_, face) in preview.fonts.items() if key[0]))
            self.assertEqual(self.app.typography, typography)
            self.assertEqual(self.store.get_preference("conversation"), saved)
            self.assertEqual(self.app.chat.get("1.0", "end-1c"), archive)
            self.assertEqual(self.store.message(message)["content"], source)
            inference.assert_not_called()
            capture.assert_not_called()

    def test_invalid_draft_restore_and_close_keep_saved_preferences_and_release_preview(self):
        self.app.set_conversation_typography(size=16, accent_intensity=34)
        saved, typography = self.store.get_preference("conversation"), self.app.typography
        self.app.open_conversation_settings()
        self.root.update()
        preview = self.app.conversation_dialog.typography_preview
        preview.widget.focus_force()
        self.root.update()
        next_control = preview.widget.tk_focusNext()
        preview.widget.event_generate("<Tab>")
        self.root.update()
        self.assertIs(self.root.focus_get(), next_control)
        preview.widget.focus_force()
        self.root.update()
        previous_control = preview.widget.tk_focusPrev()
        preview.widget.event_generate("<Shift-Tab>")
        self.root.update()
        self.assertIs(self.root.focus_get(), previous_control)
        self.replace_reading_value("size", 19)
        self.assertEqual(preview.typography.size, 19)
        self.replace_reading_value("size", "")
        self.assertEqual(preview.typography.size, 19)
        status = self.reading_control("preview_status")
        self.assertIn("Aperçu conservé", status.cget("text"))
        with patch("jarvis.ui.messagebox.showerror") as error:
            self.reading_button("Enregistrer").invoke()
        error.assert_called_once()
        self.assertIsNotNone(self.app.conversation_dialog)
        with patch.object(self.store, "set_preference", side_effect=AssertionError("draft persisted")):
            self.reading_control("restore_preview").invoke()
            self.assertEqual(self.reading_control("size").get(), "16")
            self.assertEqual(preview.typography.size, 16)
            self.assertEqual(preview.typography.accent_intensity, 34)
            self.replace_reading_value("size", 20)
            self.reading_button("Fermer").invoke()
        self.assertIsNone(self.app.conversation_dialog)
        self.assertIsNone(preview.widget)
        self.assertFalse(preview.fonts)
        self.assertEqual(self.app.typography, typography)
        self.assertEqual(self.store.get_preference("conversation"), saved)
        self.app.open_conversation_settings()
        preview = self.app.conversation_dialog.typography_preview
        self.assertEqual(preview.typography.size, 16)
        self.app.close()
        self.assertIsNone(preview.widget)

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
                preview = dialog.typography_preview
                preview_height = preview.widget.winfo_height()
                self.replace_reading_value("size", 24)
                self.replace_reading_value("scale", 175)
                self.root.update()
                self.assertEqual(preview.widget.winfo_height(), preview_height)
                self.assertGreater(preview.widget.winfo_width(), 0)
                frames = dialog.winfo_children()
                footer = next(frame for frame in frames if any(child.winfo_class() == "TButton" for child in frame.winfo_children()))
                self.assertEqual({button.cget("text") for button in footer.winfo_children()}, {"Enregistrer", "Fermer"})
                self.assertLessEqual(footer.winfo_y() + footer.winfo_height(), dialog.winfo_height())
                # Tabbing to the last action reveals it inside the settings pane.
                control = self.reading_control("restore_preview")
                control.focus_force()
                self.root.update()
                canvas = control.master.master
                self.assertGreaterEqual(control.winfo_rooty(), canvas.winfo_rooty())
                self.assertLessEqual(control.winfo_rooty() + control.winfo_height(),
                                     canvas.winfo_rooty() + canvas.winfo_height())
                dialog.destroy()
                self.assertIsNone(self.app.conversation_dialog)
        finally:
            self.root.tk.call("tk", "scaling", scaling)

    def test_code_font_and_accent_survive_reopen_with_unknown_preferences_preserved(self):
        self.store.set_preference("conversation", {"future_option": "keep", "size": 13})
        self.close_app()
        self.open_app()
        code_family = self.app.markdown.code_families[0]
        self.app.set_conversation_typography(code_family=code_family, accent_intensity=24)
        self.assertEqual(self.store.get_preference("conversation")["future_option"], "keep")
        self.close_app()
        self.open_app()
        self.assertEqual(self.app.typography.code_family, code_family)
        self.assertEqual(self.app.typography.accent_intensity, 24)
        self.assertEqual(self.app.typography.size, 13)
        self.assertEqual(self.store.get_preference("conversation")["future_option"], "keep")


if __name__ == "__main__":
    unittest.main()
