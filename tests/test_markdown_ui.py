"""Real Tk/SQLite Markdown presentation without model, browser, or audio access."""
import gc
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.markdown_view import MarkdownView
from jarvis.ollama import Event
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class MarkdownWidgetTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("650x400")
        self.widget = tk.Text(self.root, wrap="word", state="disabled")
        self.widget.pack(fill="both", expand=True)
        self.view = MarkdownView(self.widget, "TkDefaultFont", "black", "gray", "blue", "#eeeeee")
        self.root.update()

    def tearDown(self):
        self.view.close()
        self.root.destroy()
        self.view = self.widget = self.root = None
        gc.collect()

    def tagged_text(self, tag):
        ranges = self.widget.tag_ranges(tag)
        return [self.widget.get(start, end) for start, end in zip(ranges[::2], ranges[1::2])]

    def test_stream_closing_markers_and_unicode_keep_exact_tag_boundaries(self):
        region = self.view.append("🚀 **gr", final=False)
        self.view.update(region, "🚀 **gras** puis ***lié*** et *fin*", final=False)
        self.assertEqual(self.widget.get(region.start, region.end), "🚀 gras puis lié et fin")
        self.assertIn("gras", self.tagged_text("md_bold"))
        self.assertIn("lié", self.tagged_text("md_bold"))
        self.assertIn("lié", self.tagged_text("md_italic"))
        self.assertIn("fin", self.tagged_text("md_italic"))
        position = self.widget.search("lié", region.start)
        names = self.widget.tag_names(position)
        fonts = [name for name in names if name.startswith("md_font_")]
        self.assertEqual(len(fonts), 1)
        face = self.widget.tk.call("font", "actual", self.widget.tag_cget(fonts[0], "font"))
        self.assertIn("bold", face)
        self.assertIn("italic", face)
        self.view.update(region, "🚀 **gras** puis ***lié*** et *fin*", final=True)
        self.assertEqual(self.widget.cget("state"), "disabled")

    def test_only_current_region_changes_and_copy_selection_and_scroll_survive(self):
        history = self.view.append("\n".join(f"Archive {index}: **texte conservé** 🚀" for index in range(90)))
        self.widget.configure(state="normal")
        self.widget.insert("end", "\nNOUVELLE RÉPONSE\n")
        self.widget.configure(state="disabled")
        stream = self.view.append("début stable ", final=False)
        self.root.update()
        self.widget.yview_moveto(0.2231)
        first = self.widget.index("@0,0")
        top_y = self.widget.dlineinfo(first)[1]
        start = self.widget.search("Archive 4:", history.start)
        end = self.view.offset(start, "Archive 4:")
        self.widget.tag_add("sel", start, end)
        archived = self.widget.get(history.start, history.end)
        self.view.update(stream, "début stable **nouveau 🚀**\n" * 12, final=False)
        self.root.update_idletasks()
        self.assertEqual(self.widget.get(history.start, history.end), archived)
        self.assertEqual(self.widget.get("sel.first", "sel.last"), "Archive 4:")
        self.assertEqual(self.widget.index("@0,0"), first)
        self.assertEqual(self.widget.dlineinfo(first)[1], top_y)
        self.widget.event_generate("<<Copy>>")
        self.assertEqual(self.widget.clipboard_get(), "Archive 4:")

    def test_selection_in_stream_survives_closing_delimiter_and_new_phrase(self):
        region = self.view.append("**mot choisi", final=False)
        start = self.widget.search("mot choisi", region.start)
        self.widget.tag_add("sel", start, self.view.offset(start, "mot choisi"))
        self.view.update(region, "**mot choisi** et la suite", final=False)
        self.assertEqual(self.widget.get("sel.first", "sel.last"), "mot choisi")

    def test_large_link_close_preserves_selected_label_words(self):
        source = "[mot choisi " + "a " * 70000 + "]"
        region = self.view.append(source, final=False)
        start = self.widget.search("mot choisi", region.start)
        self.widget.tag_add("sel", start, self.view.offset(start, "mot choisi"))
        self.view.update(region, source + "(https://example.com) et suite", final=False)
        self.assertEqual(self.widget.get("sel.first", "sel.last"), "mot choisi")

    def test_public_links_preview_and_copy_without_opening_or_executing(self):
        source = ("[documentation](https://example.com/guide?q=été) "
                  "[script](javascript:alert(1)) [commande](file:///tmp/a) "
                  "[local](https://127.0.0.1/x) [secret](https://user:pass@example.com/x) "
                  "<script>alert('texte')</script>")
        region = self.view.append(source)
        self.assertEqual(list(self.view.links), ["https://example.com/guide?q=été"])
        self.assertIn("<script>alert('texte')</script>", self.widget.get(region.start, region.end))
        with patch("webbrowser.open") as browser, patch("subprocess.Popen") as process:
            tag = self.view.links["https://example.com/guide?q=été"]
            start = self.widget.tag_ranges(tag)[0]
            self.widget.mark_set("insert", start)
            self.widget.focus_force()
            self.root.update()
            self.widget.event_generate("<Return>")
            self.root.update()
            dialogs = [child for child in self.widget.winfo_children() if isinstance(child, tk.Toplevel)]
            self.assertEqual(len(dialogs), 1)
            dialog = dialogs[0]
            actions = [child for child in dialog.winfo_children() if child.winfo_class() == "TFrame"][0]
            copy = [child for child in actions.winfo_children() if child.cget("text") == "Copier l’adresse"][0]
            copy.invoke()
            self.assertEqual(self.widget.clipboard_get(), "https://example.com/guide?q=été")
            browser.assert_not_called()
            process.assert_not_called()
            dialog.destroy()
        self.assertEqual(self.view._next_link(), "break")
        self.assertEqual(self.widget.index("insert"), self.widget.index(start))

    def test_fenced_code_and_math_remain_readable_and_tk_responsive(self):
        source = "# Résultat\n\n```python\nprint('🚀')\n```\n\n$\\alpha^2 + \\beta_1 = 3$\n"
        started = time.monotonic()
        region = self.view.append(source)
        self.assertIn("print('🚀')", self.widget.get(region.start, region.end))
        self.assertTrue(self.widget.tag_ranges("md_codeblock"))
        self.assertTrue(self.widget.tag_ranges("md_math"))
        callbacks = []
        self.root.after(0, lambda: callbacks.append(True))
        self.root.update()
        self.assertEqual(callbacks, [True])
        self.assertLess(time.monotonic() - started, 2)


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class MarkdownAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "markdown.sqlite3"
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.root.after_cancel(self.app.poll_id)
        self.addCleanup(self.close_app)

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.app = self.root = self.store = None
        gc.collect()

    def tick(self, events):
        with patch.object(self.app.worker, "poll", return_value=events), patch.object(self.app.worker, "alive", return_value=True):
            self.app.poll()
        self.root.after_cancel(self.app.poll_id)
        self.root.update_idletasks()

    def test_stream_batches_preserve_original_sqlite_and_restore_legacy_markdown(self):
        question = "# Question **littérale** 🚀 <script>texte</script>"
        source = "# Titre 🚀\n\n**Bonjour** et ***été***.\n```python\nprint('🚀')\n```\n$\\alpha^2$"
        self.app.settings = Settings(model="local-test")
        self.app.models = ["local-test"]
        with patch.object(self.app.worker, "start"):
            self.app.send(text=question)
        message_id, session_id = self.app.message_id, self.app.session_id
        region = self.app.assistant_region
        with patch.object(self.app.markdown, "update", wraps=self.app.markdown.update) as render:
            self.tick([Event("chunk", source[:15]), Event("chunk", source[15:31]), Event("chunk", source[31:])])
            self.assertEqual(render.call_count, 1)
        self.assertEqual(self.store.message(message_id)["content"], source)
        self.assertEqual(self.store.message(message_id)["status"], "streaming")
        self.assertEqual(self.app.assistant_region, region)
        self.tick([Event("done", {})])
        self.assertEqual(self.store.message(message_id)["content"], source)
        self.assertEqual(self.store.message(message_id)["status"], "complete")
        displayed = self.app.chat.get("1.0", "end-1c")
        self.assertIn(question, displayed)
        self.assertIn("Bonjour et été.", displayed)
        self.assertNotIn("**Bonjour**", displayed)
        self.close_app()
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.root.after_cancel(self.app.poll_id)
        self.assertEqual(self.app.session_id, session_id)
        self.assertEqual(self.store.message(message_id)["content"], source)
        self.assertEqual(self.app.chat.get("1.0", "end-1c"), displayed)
        # User markup is plain, including after a historical session is restored.
        position = self.app.chat.search("# Question", "1.0")
        self.assertFalse(any(name.startswith("md_") for name in self.app.chat.tag_names(position)))

    def test_cancel_finalizes_incomplete_markup_and_keeps_original(self):
        self.app.settings = Settings(model="local-test")
        self.app.models = ["local-test"]
        with patch.object(self.app.worker, "start"):
            self.app.send(text="Question")
        mid = self.app.message_id
        self.tick([Event("chunk", "🚀 **incomplet")])
        self.app.cancel()
        row = self.store.message(mid)
        self.assertEqual(row["content"], "🚀 **incomplet")
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(self.app.chat.cget("state"), "disabled")
        before = self.app.chat.get(self.app.assistant_region.start, self.app.assistant_region.end)
        bold_before = bool(self.app.chat.tag_ranges("md_bold"))
        self.app.render_session()
        ranges = self.app.chat.tag_ranges("md_bold")
        self.assertIn(before, self.app.chat.get("1.0", "end-1c"))
        self.assertEqual(bool(ranges), bold_before)
