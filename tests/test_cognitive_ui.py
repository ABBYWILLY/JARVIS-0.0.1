"""Real Tk/SQLite integration; no model, microphone or additional inference."""
import gc
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.ollama import Event
from jarvis.storage import Store
from jarvis.ui import App, COGNITIVE_LABELS
from tests.test_jarvis import display_available
from tests.test_reasoning_ui import ControlledWorker


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class CognitiveDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "cognitive.sqlite3")
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

    def choose(self, mode):
        self.app.cognitive_var.set(COGNITIVE_LABELS[mode])
        self.app.change_cognitive_mode()

    def test_local_choice_persists_and_actual_request_policy_is_archived(self):
        self.choose("auto")
        self.assertEqual(self.store.settings().cognitive_mode, "auto")
        self.app.send(text="Raconte une histoire avec Alix.")
        request = self.app.worker.calls[-1][1]
        self.assertEqual(request.reasoning_mode, "fast")
        self.assertGreaterEqual(request.temperature, .9)
        self.assertEqual(request.max_tokens, self.app.settings.max_tokens)
        decision = json.loads(self.store.message(self.app.message_id)["metadata"])["cognition"]
        self.assertEqual((decision["mode"], decision["origin"]), ("creative", "local_heuristic"))
        self.assertEqual(decision["temperature"], request.temperature)
        self.assertIn("disabled", self.app.cognitive_combo.state())
        self.deliver(Event("chunk", "Alix arrive à Éole."), Event("done", {"outcome": "complete"}))
        self.app.render_session()
        displayed = self.app.chat.get("1.0", "end")
        self.assertIn("Créatif", displayed)
        self.assertIn("non vérifié", displayed)
        self.choose("deep")
        self.app.send(text="Bonjour")
        self.assertEqual(self.app.worker.calls[-1][1].reasoning_mode, "deep")

    def test_continue_preserves_draft_archive_story_and_interruption(self):
        self.choose("auto")
        self.app.send(text="Raconte une histoire avec Alix et Nadir, vers Éole.")
        self.deliver(Event("chunk", "Alix confie la clé à Nadir."),
                     Event("done", {"outcome": "length", "done_reason": "length"}))
        original = [dict(row) for row in self.store.messages(self.app.session_id)]
        self.assertNotIn("disabled", self.app.continue_button.state())
        self.app.input.insert("1.0", "Mon brouillon privé")
        with patch.object(self.app.voice.capture, "start") as capture:
            self.app.continue_button.invoke()
            capture.assert_not_called()
        self.assertEqual(len(self.app.worker.calls), 2)
        request, messages = self.app.worker.calls[-1][1:]
        self.assertEqual(request.reasoning_mode, "fast")
        self.assertGreaterEqual(request.temperature, .9)
        prompt = "\n".join(item["content"] for item in messages)
        self.assertIn(original[0]["content"], prompt)
        self.assertIn(original[1]["content"], prompt)
        self.assertIn("sans le répéter", prompt)
        self.assertEqual(self.app.input.get("1.0", "end-1c"), "Mon brouillon privé")
        self.assertEqual([dict(row) for row in self.store.messages(self.app.session_id)[:2]], original)
        continued = self.store.message(self.app.message_id)
        metadata = json.loads(continued["metadata"])
        self.assertEqual(metadata["continuation"]["target_message_id"], original[-1]["id"])
        self.assertEqual(metadata["cognition"]["mode"], "creative")
        self.assertIn("disabled", self.app.continue_button.state())
        self.deliver(Event("chunk", "Nadir ouvre le sas."))
        self.app.stop_button.invoke()
        self.assertEqual(self.store.message(continued["id"])["status"], "cancelled")
        self.assertEqual([dict(row) for row in self.store.messages(self.app.session_id)[:2]], original)
        self.assertNotIn("disabled", self.app.continue_button.state())

    def test_continue_missing_model_or_context_does_not_create_a_turn(self):
        mid = self.store.begin_turn(self.app.session_id, "Une histoire.", self.app.settings.model)
        self.store.update_response(mid, "Le récit commence.", "cancelled")
        self.app.render_session()
        before = [dict(row) for row in self.store.messages(self.app.session_id)]
        self.app.models = []
        self.app.continue_response()
        self.assertEqual(self.app.worker.calls, [])
        self.assertIn("Choisissez", self.app.status.get())
        self.app.models = [self.app.settings.model]
        with patch("jarvis.cognition.build_continuation", side_effect=ValueError("Contexte insuffisant")):
            self.app.continue_response()
        self.assertEqual([dict(row) for row in self.store.messages(self.app.session_id)], before)
        self.assertEqual(self.app.worker.calls, [])
        self.assertIn("Contexte insuffisant", self.app.status.get())

    def test_inspector_separates_user_generated_and_prepared_sources_without_truth_claim(self):
        self.app.send(text="Mon projet se nomme Atlas.")
        self.deliver(Event("chunk", "Hypothèse : il reste local."), Event("done", {"outcome": "complete"}))
        self.app.open_context()
        dialog = next(child for child in self.root.winfo_children()
                      if isinstance(child, tk.Toplevel) and child.title() == "Contexte envoyé à Ollama")
        sources = dialog.nametowidget("sources")
        self.assertIn("Votre demande", sources.get(sources.size() - 2))
        self.assertIn("Réponse non vérifiée", sources.get(sources.size() - 1))
        summary = self.root.getvar(dialog.nametowidget("summary").cget("textvariable"))
        self.assertIn("contexte préparé", summary)
        self.assertIn("ne prouvent ni sa réception", summary)
        for index, category, original in ((sources.size() - 2, "Donnée fournie", "Mon projet se nomme Atlas."),
                                           (sources.size() - 1, "généré non vérifié", "Hypothèse : il reste local.")):
            sources.selection_clear(0, "end")
            sources.selection_set(index)
            sources.event_generate("<<ListboxSelect>>")
            self.root.update()
            details = dialog.nametowidget("detail.details").get("1.0", "end")
            self.assertIn(category, details)
            self.assertIn(original, details)
            self.assertNotIn("injecté intégralement", details)

    def test_empty_response_never_enables_continuation(self):
        self.assertIn("disabled", self.app.continue_button.state())
        self.app.send(text="Bonjour")
        self.deliver(Event("done", {"outcome": "empty"}))
        self.assertIsNone(self.app.continuation_id)
        self.assertIn("disabled", self.app.continue_button.state())
