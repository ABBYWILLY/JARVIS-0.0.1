"""Tk/SQLite reasoning controls and incomplete-response contracts."""
import gc
import json
import tempfile
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.ollama import Event
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available


class ControlledWorker:
    def __init__(self):
        self.events = []
        self.calls = []

    def start(self, *args):
        self.calls.append(args)

    def poll(self):
        events, self.events = self.events, []
        return events

    def alive(self):
        return True

    def stop(self):
        pass


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class ReasoningDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "reasoning.sqlite3")
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

    def deliver(self, *events):
        self.app.worker.events = list(events)
        self.root.after_cancel(self.app.poll_id)
        self.app.poll()

    def assistant(self):
        return self.store.messages(self.app.session_id)[-1]

    def test_empty_and_thinking_only_results_are_errors_without_internal_text(self):
        for outcome in ("empty", "empty_length"):
            with self.subTest(outcome=outcome):
                self.app.new_session()
                self.app.send(text="2 + 2 ?")
                self.deliver(Event("done", {"outcome": outcome, "eval_count": 656,
                             "thinking_observed": True, "reasoning_status": "requested_disabled"}))
                row = self.assistant()
                self.assertEqual(row["status"], "error")
                self.assertEqual(row["content"], "")
                self.assertIn("ERREUR", self.app.status.get())
                self.assertNotIn("historique enregistré", self.app.status.get())
                self.assertNotIn("Interne", self.app.chat.get("1.0", "end"))
                metrics = json.loads(row["metadata"])["generation_metrics"]
                self.assertEqual(metrics["eval_count"], 656)
                self.assertEqual(metrics["outcome"], outcome)

    def test_whitespace_only_is_not_a_success_even_without_outcome_flag(self):
        self.app.send(text="Question")
        self.deliver(Event("chunk", " \n"), Event("done", {}))
        self.assertEqual(self.assistant()["status"], "error")
        self.assertEqual(self.assistant()["content"], " \n")
        self.assertEqual(self.store.context(self.app.session_id), [])

    def test_length_limited_answer_remains_visible_but_outside_complete_context(self):
        self.app.send(text="Explique ceci")
        with patch.object(self.app.voice, "finish_turn") as finish_voice:
            self.deliver(Event("chunk", "Une réponse partielle"),
                         Event("done", {"outcome": "length", "done_reason": "length", "eval_count": 256}))
            finish_voice.assert_called_once_with("complete")
        row = self.assistant()
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(row["content"], "Une réponse partielle")
        self.assertEqual(self.store.context(self.app.session_id), [])
        self.assertIn("partielle", self.app.status.get())
        self.assertIn("limite", self.app.status.get())
        self.assertIn("Une réponse partielle", self.app.chat.get("1.0", "end"))
        self.app.render_session()
        self.assertIn("Limite de génération atteinte", self.app.chat.get("1.0", "end"))

    def test_request_budget_is_selected_without_changing_saved_budgets(self):
        for source, usage, expected in (("text", "chat", 900), ("voice", "mission", 128),
                                         ("text", "mission", 1800), ("text", "voice", 128)):
            with self.subTest(source=source, usage=usage):
                self.app.settings = replace(self.app.settings, usage=usage, max_tokens=900,
                                            voice_tokens=128, mission_tokens=1800)
                self.app.send(source=source, text="Question")
                operation, request_settings, messages = self.app.worker.calls[-1]
                self.assertEqual(operation, "chat")
                self.assertEqual(request_settings.max_tokens, expected)
                self.assertEqual(self.app.settings.max_tokens, 900)
                self.assertEqual(messages[-1], {"role": "user", "content": "Question"})
                self.deliver(Event("chunk", "Réponse"), Event("done", {"outcome": "complete"}))

    def test_settings_dialog_persists_reasoning_usage_and_three_budgets(self):
        self.app.open_settings()
        dialog = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        for key, value in (("max_tokens", "800"), ("voice_tokens", "180"), ("mission_tokens", "3000"),
                           ("reasoning_mode", "Approfondi"), ("usage", "Mission complexe")):
            self.root.setvar(dialog.controls[key].cget("textvariable"), value)
        dialog.save_button.invoke()
        saved = self.store.settings()
        self.assertEqual((saved.reasoning_mode, saved.usage), ("deep", "mission"))
        self.assertEqual((saved.max_tokens, saved.voice_tokens, saved.mission_tokens), (800, 180, 3000))
        self.assertFalse(dialog.winfo_exists())

    def test_unsupported_notice_is_discrete_and_preserved_in_response_metadata(self):
        self.app.send(text="Bonjour")
        self.deliver(Event("notice", "Paramètre think non pris en charge : repli explicite.",
                           metadata={"reasoning_status": "unsupported", "thinking_observed": False}))
        self.assertEqual(self.app.operation, "chat")
        self.assertIn("repli explicite", self.app.status.get())
        self.deliver(Event("chunk", "Bonjour"), Event("done", {"outcome": "complete"}))
        metrics = json.loads(self.assistant()["metadata"])["generation_metrics"]
        self.assertEqual(metrics["reasoning_status"], "unsupported")
        self.assertIn("non pris en charge", self.app.chat.get("1.0", "end"))


if __name__ == "__main__":
    unittest.main()
