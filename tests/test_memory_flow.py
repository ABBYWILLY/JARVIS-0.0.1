"""Real SQLite/FTS -> UI -> worker -> HTTP fixture, without model downloads."""
import gc
import json
import tempfile
import time
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available
from tests.test_metrics import MetricsFixture


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class MemoryFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "flow.sqlite3"
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.addCleanup(self.close_app)

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.app = self.root = self.store = None
        gc.collect()

    def send(self, fixture):
        self.app.settings = replace(self.app.settings, endpoint=fixture.endpoint, model="qwen3.5:4b")
        self.app.models = ["qwen3.5:4b"]
        self.app.send(source="voice", text="Quel port pour Zephyr ? 🚀")
        deadline = time.monotonic() + 8
        while self.app.operation and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertIsNone(self.app.operation, self.app.status.get())
        row = self.store.messages(self.app.session_id)[-1]
        self.assertEqual(row["status"], "complete")
        return json.loads(row["metadata"])["context"], fixture.server.request_body

    def test_pending_approval_recall_disable_and_reopen_preserve_conversation(self):
        mid = self.store.memory.create("Zephyr utilise le port 8765.", kind="project", topic="Zephyr",
                                       provenance={"source": "manual", "note": "Confirmé par le propriétaire"})
        unrelated = self.store.memory.create("La cuisson du pain dure 40 minutes.", topic="Cuisine")
        self.store.memory.approve(unrelated, confirmed=True)
        with MetricsFixture() as fixture:
            first, _ = self.send(fixture)
            self.assertEqual(first["selected_memory_ids"], [])
            self.store.memory.approve(mid, confirmed=True)
            selected, body = self.send(fixture)
            self.assertEqual(selected["selected_memory_ids"], [mid])
            self.assertEqual(selected["memory_count"], 1)
            self.assertIn("8765", str(body["messages"]))
            self.assertNotIn("cuisson", str(body["messages"]))
            self.assertIs(body["think"], False)
            self.assertEqual(body["options"]["num_predict"], self.app.settings.voice_tokens)
            source = next(s for s in selected["sources"] if s["method"] == "memory")
            self.assertEqual(source["provenance"]["source"], "manual")
            self.store.memory.disable(mid)
            disabled, body = self.send(fixture)
            self.assertEqual(disabled["selected_memory_ids"], [])
            self.assertNotIn("8765", str(body["messages"]))
        sid = self.app.session_id
        rows = [dict(row) for row in self.store.messages(sid)]
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["content"] == "Quel port pour Zephyr ? 🚀" for row in rows[::2]))
        self.assertEqual(len(self.store.memory.list()), 2)  # No automatic memories.
        self.close_app()
        self.store = Store(self.path)
        try:
            self.assertEqual([dict(row) for row in self.store.messages(sid)], rows)
            self.assertEqual(self.store.memory.get(mid)["status"], "disabled")
            self.assertEqual(json.loads(rows[3]["metadata"])["context"]["selected_memory_ids"], [mid])
        finally:
            self.store.close()
            self.store = None

    def test_disabling_targeted_context_skips_memory_lookup(self):
        self.app.settings = Settings(targeted_context=False)
        with MetricsFixture() as fixture, patch.object(self.store.memory, "search", side_effect=AssertionError("lookup disabled")):
            context, _ = self.send(fixture)
        self.assertEqual(context["memory_count"], 0)
