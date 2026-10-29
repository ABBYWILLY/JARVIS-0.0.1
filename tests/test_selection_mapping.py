"""Exact source projection with real Tk; no audio, models or device doubles."""
import gc
import tkinter as tk
import unittest
from unittest.mock import Mock

from jarvis.markdown_view import MarkdownView
from jarvis.richtext import parse_mapped_text, parse_text
from jarvis.selection import MAX_SELECTION, MAX_SOURCE, project_selection
from tests.test_jarvis import display_available


class SourceProjectionTests(unittest.TestCase):
    def project(self, source, visible=None, *, start=None, end=None, final=True):
        text = parse_text(source, final=final).text
        if start is None:
            start = text.index(visible) if visible is not None else 0
        if end is None:
            end = start + len(visible) if visible is not None else len(text)
        return project_selection(source, text, start, end, message_id=17, session_id="session",
                                 region_key="region", revision=2, final=final)

    def test_opt_in_projection_does_not_change_existing_scanner_output(self):
        samples = ["# Titre\n**gras** *italique* ++souligné++ ==surligné== ~~barré~~.",
                   "- premier\n  - second\n> citation\n---\n",
                   "[le **guide**](https://example.org/guide) puis https://example.org.",
                   "```python\nx = 12 😊\n```\nSuite `code` et \\(x=2\\).",
                   "| Nom | Valeur |\n| --- | --- |\n| été | 12 € |\n",
                   r"Un \* utile, 👩🏽‍🚀 et :) ; $12.", "**balise partielle"]
        for source in samples:
            for final in (True, False):
                with self.subTest(source=source, final=final):
                    document, mapping = parse_mapped_text(source, final=final)
                    self.assertEqual(document, parse_text(source, final=final))
                    self.assertEqual(len(mapping), len(document.text))
                    ranges = [interval for interval in mapping if interval[0] is not None]
                    self.assertTrue(all(0 <= left < right <= len(source) for left, right in ranges))

    def test_repeated_words_and_link_destination_never_steal_source_position(self):
        source = "[alpha](https://example.org/alpha) alpha **alpha**."
        result = self.project(source, start=parse_text(source).text.rindex("alpha"), end=len(parse_text(source).text) - 1)
        self.assertEqual(result.original, "alpha")
        self.assertEqual(result.source_start, source.rindex("alpha"))
        self.assertEqual(source[result.source_start:result.source_end], result.original)
        self.assertEqual(result.display_text, "alpha")

    def test_multi_paragraph_formatting_and_unicode_preserve_exact_selection(self):
        source = "# Été 👩🏽‍🚀\nDu **gras**, puis *cœur*.\n> Déjà là."
        display = parse_text(source).text
        chosen = display[2:]
        result = self.project(source, start=2, end=len(display))
        self.assertEqual(result.display_text, chosen)
        self.assertEqual(result.original, source[result.source_start:result.source_end])
        self.assertIn("👩🏽‍🚀", result.display_text)
        self.assertEqual(result.message_id, 17)
        self.assertEqual(result.session_id, "session")

    def test_table_full_and_partial_cells_are_mapped_without_generated_padding_words(self):
        source = "| Nom | Valeur |\n| --- | --- |\n| été | 12 € |\n"
        result = self.project(source)
        self.assertIn("│", result.display_text)
        self.assertNotIn("│", parse_text(result.speech_source).speech)
        self.assertIn("12 €", parse_text(result.speech_source).speech)
        cell = self.project(source, "été")
        self.assertEqual(cell.original, "été")
        self.assertEqual(cell.source_start, source.index("été"))
        self.assertEqual(parse_text(cell.speech_source).speech, "été")

    def test_code_excerpt_keeps_code_policy_and_does_not_create_emoji_expression(self):
        source = "Avant.\n```python\nprint('😊')\nvalue = 12\n```\nAprès."
        result = self.project(source, "print('😊')")
        self.assertEqual(result.original, "print('😊')")
        self.assertEqual(parse_text(result.speech_source).speech, "Bloc de code non lu.")
        spoken = parse_text(result.speech_source, speak_code=True)
        self.assertIn("print", spoken.speech)
        self.assertFalse(any(event.kind == "expression" for event in spoken.events))
        self.assertEqual(result.source_start, source.index("print"))

    def test_inline_code_and_math_keep_their_speech_semantics(self):
        inline = self.project("Une valeur `x=12` utile.", "x=12")
        self.assertIn("`", inline.speech_source)
        math = self.project(r"La formule \(12/2=6\) est utile.", "12/2=6")
        self.assertIn("12", parse_text(math.speech_source).speech)
        self.assertIn("égal", parse_text(math.speech_source).speech)

    def test_selected_literal_number_is_not_dropped_as_a_new_list_marker(self):
        result = self.project("Il choisit 1. puis poursuit.", "1. puis")
        self.assertIn("1.", parse_text(result.speech_source).speech)
        result = self.project("Une valeur - témoin conservée.", "- témoin")
        self.assertIn("-", parse_text(result.speech_source).speech)

    def test_visible_end_keeps_hidden_closing_delimiters_for_continuation(self):
        for source in ("**Bonjour**", "**Bonjour**\n", "[Bonjour](https://example.org)",
                       "# Bonjour", "```\nBonjour\n```\n"):
            with self.subTest(source=source):
                result = self.project(source, "Bonjour")
                self.assertGreaterEqual(result.source_end, len(source.rstrip()))
                self.assertEqual(result.display_text, "Bonjour")

    def test_source_selection_limits_and_unarchived_or_changed_text_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "archivée"):
            project_selection("Texte", "Texte", 0, 5, message_id=None, session_id="x", region_key="r", revision=1)
        with self.assertRaisesRegex(ValueError, "changé"):
            project_selection("Texte", "Autre", 0, 5, message_id=1, session_id="x", region_key="r", revision=1)
        with self.assertRaisesRegex(ValueError, "trop longue"):
            self.project("a" * (MAX_SOURCE + 1))
        with self.assertRaisesRegex(ValueError, "trop longue"):
            self.project("a" * (MAX_SELECTION + 1))
        with self.assertRaisesRegex(ValueError, "décoration"):
            self.project("- Élément", "•")


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class SelectionTkTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.text = tk.Text(self.root, width=55, height=16)
        self.text.pack(fill="both", expand=True)
        self.view = MarkdownView(self.text, "TkDefaultFont", "#ffffff", "#aaaaaa", "#55ddff", "#112233")
        self.addCleanup(self.close)

    def close(self):
        self.view.close()
        self.root.destroy()
        self.view = self.root = self.text = None
        gc.collect()

    def select(self, region, start=0, end=None):
        end = len(region.text) if end is None else end
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", self.view.offset(region.start, region.text[:start]),
                          self.view.offset(region.start, region.text[:end]))

    def test_restored_message_unicode_streaming_and_snapshot_invalidation(self):
        region = self.view.append("Bonjour **été 👩🏽‍🚀**", final=False, message_id=4, session_id="s")
        chosen = "été 👩🏽‍🚀"
        self.select(region, region.text.index(chosen), region.text.index(chosen) + len(chosen))
        result = self.view.resolve_selection()
        self.assertEqual(result.display_text, chosen)
        self.assertTrue(self.view.validate_selection(result))
        self.view.update(region, "Bonjour **été 👩🏽‍🚀** et suite.", final=True)
        self.assertFalse(self.view.validate_selection(result))
        fresh = self.view.resolve_selection()
        self.assertEqual(fresh.display_text, chosen)
        self.assertEqual(fresh.original, chosen)

    def test_selection_across_message_boundary_or_metadata_is_refused(self):
        first = self.view.append("Première **réponse**", message_id=1, session_id="s")
        self.text.configure(state="normal")
        self.text.insert("end", "\nMÉTRIQUES\n")
        self.text.configure(state="disabled")
        second = self.view.append("Seconde réponse", message_id=2, session_id="s")
        self.text.tag_add("sel", first.start, second.end)
        with self.assertRaisesRegex(ValueError, "seule réponse"):
            self.view.resolve_selection()
        self.select(second)
        self.assertEqual(self.view.resolve_selection().message_id, 2)

    def test_menu_reuses_copy_and_dispatches_only_validated_selection(self):
        region = self.view.append("Le **passage** choisi.", message_id=8, session_id="s")
        self.select(region, 3, 10)
        callback = Mock()
        self.view.set_action_handler(callback)
        result = self.view.prepare_actions()
        self.assertEqual(result.display_text, "passage")
        self.assertTrue(self.view.invoke_action("read"))
        callback.assert_called_once_with("read", result)
        self.assertTrue(self.view.invoke_action("copy"))
        self.assertEqual(self.root.clipboard_get(), "passage")
        self.view.update(region, "Le **nouveau passage** choisi.", final=True)
        self.assertFalse(self.view.invoke_action("read"))
        self.assertIn("changé", self.view.selection_error)

    def test_preview_without_archive_cannot_invoke_model_or_voice(self):
        region = self.view.append("Aperçu seulement")
        self.select(region)
        callback = Mock()
        self.view.set_action_handler(callback)
        self.assertIsNone(self.view.prepare_actions())
        self.assertFalse(self.view.invoke_action("read"))
        callback.assert_not_called()

    def test_actions_can_be_hidden_without_losing_existing_copy_commands(self):
        region = self.view.append("Passage fiable", message_id=4, session_id="s")
        self.select(region)
        callback = Mock()
        self.view.set_action_handler(callback)
        self.view.prepare_actions()
        self.view.set_action_handler(callback, enabled=False)
        self.assertEqual(self.view.source_menu.index("end"), 1)
        self.assertFalse(self.view.invoke_action("read"))
        callback.assert_not_called()
        self.view.set_action_handler(callback, enabled=True)
        self.assertEqual(len(self.view._action_entries), 7)
        self.assertIsNotNone(self.view.prepare_actions())


if __name__ == "__main__":
    unittest.main()
