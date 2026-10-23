"""Context selection is inspectable and never rewrites its SQLite originals."""
import gc
import json
import tempfile
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from tkinter import ttk
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available
from tests.test_reasoning_ui import ControlledWorker


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class ContextDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "context.sqlite3"
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.app.worker = ControlledWorker()
        self.app.settings = Settings(model="qwen3.5:4b")
        self.app.models = ["qwen3.5:4b"]
        self.addCleanup(self.close_app)

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.app = self.root = self.store = None
        gc.collect()

    def previous_turn(self):
        mid = self.store.begin_turn(self.app.session_id, "Le projet Atlas utilise SQLite.", "qwen3.5:4b")
        self.store.update_response(mid, "Le fichier du projet Atlas reste local.", "complete")
        return mid

    def context_record(self, source_id, estimate=300):
        source = self.store.message(source_id)
        return {"context_estimate_tokens": estimate, "context_limit_tokens": 4096,
                "output_reserved_tokens": 1024, "omitted_messages": 0,
                "recent_messages": 0, "retrieved_messages": 1, "summary_messages": 1,
                "context_strategy": "targeted",
                "sources": [{"message_id": source_id, "session_id": source["session_id"],
                             "created": source["created"], "role": source["role"],
                             "method": "extractive", "excerpt": "projet Atlas"}]}

    def open_inspector(self):
        self.app.context_button.invoke()
        return next(widget for widget in self.root.winfo_children()
                    if isinstance(widget, tk.Toplevel) and widget.title() == "Contexte envoyé à Ollama")

    def test_send_records_exact_builder_selection_only_on_assistant(self):
        old_mid = self.previous_turn()
        originals = [dict(row) for row in self.store.messages(self.app.session_id)]
        prior_context = self.store.context_records(self.app.session_id)
        record = self.context_record(old_mid)
        outgoing = [{"role": "user", "content": "Question ciblée"}]
        result = SimpleNamespace(messages=outgoing, stats={key: value for key, value in record.items() if key != "sources"},
                                 sources=record["sources"])
        with patch("jarvis.ui.ContextBuilder") as builder:
            builder.return_value.build.return_value = result
            self.app.send(source="voice", text="Question ciblée")
            request_settings = builder.call_args.args[0]
            self.assertEqual(request_settings.max_tokens, self.app.settings.voice_tokens)
            builder.return_value.build.assert_called_once_with(
                prior_context + [{"role": "user", "content": "Question ciblée"}], memories=[])
        rows = self.store.messages(self.app.session_id)
        self.assertEqual([dict(row) for row in rows[:2]], originals)
        self.assertEqual(json.loads(rows[-2]["metadata"]), {"final_transcript": "Question ciblée"})
        metadata = json.loads(rows[-1]["metadata"])
        decision = metadata.pop("cognition")
        self.assertEqual(metadata, {"final_transcript": "Question ciblée", "context": record})
        self.assertEqual((decision["mode"], decision["origin"], decision["budget"], decision["usage"]),
                         ("fast", "manual", self.app.settings.voice_tokens, "voice"))
        self.assertEqual(self.app.worker.calls[-1][2], outgoing)

    def test_real_builder_sources_link_archived_messages_without_mutation(self):
        self.previous_turn()
        before = [dict(row) for row in self.store.messages(self.app.session_id)]
        self.app.settings = replace(self.app.settings, targeted_context=False)
        self.app.send(text="Peux-tu préciser le projet Atlas ?")
        rows = self.store.messages(self.app.session_id)
        context = json.loads(rows[-1]["metadata"])["context"]
        self.assertEqual([dict(row) for row in rows[:2]], before)
        self.assertEqual(context["context_limit_tokens"], self.app.settings.context)
        self.assertEqual(context["output_reserved_tokens"], self.app.settings.max_tokens)
        self.assertGreater(context["context_estimate_tokens"], 0)
        self.assertEqual({source["message_id"] for source in context["sources"] if source["message_id"] is not None},
                         {row["id"] for row in before})
        self.assertEqual(self.app.worker.calls[-1][2][-1],
                         {"role": "user", "content": "Peux-tu préciser le projet Atlas ?"})

    def test_inspector_reopens_metadata_and_allows_older_source_inspection(self):
        source_id = self.previous_turn()
        first = self.store.begin_turn(self.app.session_id, "Rappel Atlas", "qwen3.5:4b")
        self.store.update_response(first, "Réponse première", "complete")
        self.store.update_message_metadata(first, {"context": self.context_record(source_id, 300),
            "generation_metrics": {"prompt_eval_count": 81, "prompt_eval_duration": 25_000_000}})
        last = self.store.begin_turn(self.app.session_id, "Autre rappel", "qwen3.5:4b")
        self.store.update_response(last, "Réponse seconde", "complete")
        self.store.update_message_metadata(last, {"context": self.context_record(source_id, 400)})
        snapshot = [dict(row) for row in self.store.messages(self.app.session_id)]
        self.close_app()
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        dialog = self.open_inspector()
        picker = dialog.nametowidget("responses")
        self.assertEqual(picker.current(), 1)
        summary_widget = dialog.nametowidget("summary")
        self.assertIn("400 tokens", self.root.getvar(summary_widget.cget("textvariable")))
        picker.current(0)
        picker.event_generate("<<ComboboxSelected>>")
        self.root.update()
        summary = self.root.getvar(summary_widget.cget("textvariable"))
        self.assertIn("300 tokens", summary)
        self.assertIn("81 tokens", summary)
        self.assertIn("25.0 ms", summary)
        self.assertIn("pas un comptage exact", summary)
        details = dialog.nametowidget("detail.details")
        self.assertEqual(str(details.cget("state")), "disabled")
        text = details.get("1.0", "end")
        self.assertIn("Passage injecté :\nprojet Atlas", text)
        self.assertIn("Original archivé :\nLe fichier du projet Atlas reste local.", text)
        self.assertIn(str(source_id), text)
        self.assertEqual([dict(row) for row in self.store.messages(self.app.session_id)], snapshot)

    def test_settings_persist_targeting_and_retrieval_budget(self):
        self.app.open_settings()
        dialog = next(widget for widget in self.root.winfo_children() if isinstance(widget, tk.Toplevel))
        dialog.controls["targeted_context"].invoke()
        entry = dialog.controls["retrieval_budget"]
        self.root.setvar(entry.cget("textvariable"), "1024")
        dialog.save_button.invoke()
        self.assertFalse(self.store.settings().targeted_context)
        self.assertEqual(self.store.settings().retrieval_budget, 1024)
        self.assertEqual(self.store.settings().reasoning_mode, "fast")

    def test_recent_source_inspection_uses_full_original_not_its_short_preview(self):
        original = "Le projet Atlas est local. " * 20
        mid = self.store.begin_turn(self.app.session_id, "Projet Atlas", "qwen3.5:4b")
        self.store.update_response(mid, original, "complete")
        record = self.context_record(mid)
        record["sources"][0].update(method="recent", excerpt=original[:240])
        last = self.store.begin_turn(self.app.session_id, "Précise", "qwen3.5:4b")
        self.store.update_response(last, "Réponse", "complete")
        self.store.update_message_metadata(last, {"context": record})
        dialog = self.open_inspector()
        text = dialog.nametowidget("detail.details").get("1.0", "end")
        self.assertIn("Original archivé :", text)
        self.assertIn(original, text)

    def test_legacy_history_without_context_metadata_remains_readable(self):
        self.previous_turn()
        self.app.render_session()
        dialog = self.open_inspector()
        labels = [widget.cget("text") for widget in dialog.winfo_children() if isinstance(widget, tk.Label)]
        self.assertTrue(any("Aucun contexte instrumenté" in label for label in labels))
        self.assertIn("projet Atlas reste local", self.app.chat.get("1.0", "end"))


if __name__ == "__main__":
    unittest.main()
