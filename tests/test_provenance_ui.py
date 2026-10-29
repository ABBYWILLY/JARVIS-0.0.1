"""Private provenance inspector and actual HTTP acceptance over local fixtures.

Tk/SQLite and HTTP are real; model output and optional GPU transport are explicit
test doubles. No physical audio, GPU or Ollama model is validated here.
"""
from dataclasses import replace
import gc
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jarvis.ollama import Event, Ollama, OllamaError
from jarvis.config import Settings
from tests import test_cognitive_ui as cognitive_tests
from tests.test_jarvis import Fixture, display_available
from tests.test_presence_host import RendererDouble


class ProvenanceHTTPTests(unittest.TestCase):
    def setUp(self):
        gc.collect()

    def test_observer_runs_after_actual_http_acceptance_and_does_not_add_adapter_events(self):
        with Fixture() as fixture:
            provider = Ollama(fixture.endpoint)
            observations = []
            provider.on_request_accepted = observations.append
            events = list(provider.chat([{"role": "user", "content": "Bonjour"}], Settings(model="local")))
            self.assertEqual(len(observations), 1)
            self.assertGreater(observations[0], 0)
            self.assertEqual([event.kind for event in events], ["chunk", "chunk", "done"])
            self.assertEqual(fixture.server.request_body["messages"], [{"role": "user", "content": "Bonjour"}])

    def test_observer_does_not_acknowledge_http_rejection_or_refused_connection(self):
        for mode in ("missing", "oom"):
            with self.subTest(mode=mode), Fixture() as fixture:
                fixture.server.mode = mode
                provider = Ollama(fixture.endpoint)
                accepted = []
                provider.on_request_accepted = accepted.append
                with self.assertRaises(OllamaError):
                    list(provider.chat([{"role": "user", "content": "Bonjour"}], Settings(model="local")))
                self.assertEqual(accepted, [])
        with Fixture() as closed:
            endpoint = closed.endpoint
        provider = Ollama(endpoint, timeout=.2)
        accepted = []
        provider.on_request_accepted = accepted.append
        with self.assertRaises(OSError):
            list(provider.chat([{"role": "user", "content": "Bonjour"}], Settings(model="local")))
        self.assertEqual(accepted, [])

    def test_accepted_http_does_not_falsely_mean_successful_generation(self):
        with Fixture() as fixture:
            fixture.server.mode = "invalid"
            provider = Ollama(fixture.endpoint)
            accepted = []
            provider.on_request_accepted = accepted.append
            with self.assertRaises(ValueError):
                list(provider.chat([{"role": "user", "content": "Bonjour"}], Settings(model="local")))
            self.assertEqual(len(accepted), 1)


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class ProvenanceDesktopTests(unittest.TestCase):
    setUp = cognitive_tests.CognitiveDesktopTests.setUp
    close_app = cognitive_tests.CognitiveDesktopTests.close_app
    deliver = cognitive_tests.CognitiveDesktopTests.deliver

    def stored_metadata(self, mid):
        return json.loads(self.store.message(mid)["metadata"])

    def finish_response(self, text="Réponse locale."):
        mid = self.app.message_id
        self.deliver(Event("chunk", text), Event("done", {"outcome": "complete"}))
        return mid

    def inspector(self):
        dialog = self.app.open_context()
        self.root.update()
        return dialog

    def select_source(self, dialog, label):
        sources = dialog.nametowidget("sources")
        index = next(index for index, item in enumerate(sources.get(0, "end")) if label in item)
        sources.selection_clear(0, "end")
        sources.selection_set(index)
        sources.event_generate("<<ListboxSelect>>")
        self.root.update()
        return dialog.nametowidget("detail.details").get("1.0", "end-1c")

    def memory(self, text, title="Atlas"):
        mid = self.store.memory.create(text, title=title, topic=title, provenance={"source": "explicit_user"})
        self.store.memory.approve(mid, confirmed=True)
        return dict(self.store.memory.get(mid))

    def send_with_memory(self):
        original = self.memory("Le projet Atlas conserve ses données dans SQLite.")
        self.app.send(text="Quel stockage pour le projet Atlas ?")
        mid = self.finish_response()
        self.assertIn(original["id"], self.stored_metadata(mid)["context"]["selected_memory_ids"])
        return original, mid

    def test_effective_instruction_snapshot_survives_settings_change_and_legacy_is_unknown(self):
        original = "Instruction privée conservée 79b31, réponds en français."
        self.app.settings = replace(self.app.settings, system_prompt=original)
        self.app.send(text="Bonjour")
        mid = self.finish_response()
        self.app.settings = replace(self.app.settings, system_prompt="Nouvelle instruction privée 42.")
        dialog = self.inspector()
        details = self.select_source(dialog, "Instructions effectives")
        self.assertIn(original, details)
        self.assertNotIn("Nouvelle instruction privée 42", details)
        self.assertIn("SHA-256", details)
        self.assertEqual(self.stored_metadata(mid)["context"]["system_instructions"][0]["content"], original)
        self.store.update_message_metadata(mid, {"context": {"sources": []}})
        self.assertIs(self.app.open_context(), dialog)
        summary = self.root.getvar(dialog.nametowidget("summary").cget("textvariable"))
        self.assertIn("Instructions système non enregistrées", summary)
        self.assertFalse(any("Instructions effectives" in item for item in dialog.nametowidget("sources").get(0, "end")))

    def test_http_acceptance_updates_archived_context_only_after_observed_event(self):
        self.app.send(text="Bonjour")
        mid = self.app.message_id
        prepared = self.stored_metadata(mid)["context"]
        self.assertEqual(prepared["delivery"], "prepared")
        self.deliver(Event("request_accepted", {"accepted_at": 123.5}))
        accepted = self.stored_metadata(mid)["context"]
        self.assertEqual(accepted, {**prepared, "delivery": "accepted", "accepted_at": 123.5})
        self.assertEqual(self.store.message(mid)["content"], "")
        self.finish_response()
        dialog = self.inspector()
        summary = self.root.getvar(dialog.nametowidget("summary").cget("textvariable"))
        self.assertIn("Requête acceptée par Ollama (HTTP)", summary)
        self.assertIn("utilisation de chaque source non démontrée", summary)

    def test_failed_request_and_late_acceptance_after_cancel_do_not_claim_delivery(self):
        self.app.send(text="Bonjour")
        failed = self.app.message_id
        self.deliver(Event("error", "Connexion locale refusée."))
        self.assertEqual(self.stored_metadata(failed)["context"]["delivery"], "prepared")
        self.app.send(text="Autre demande")
        cancelled = self.app.message_id
        self.app.cancel()
        self.deliver(Event("request_accepted", {"accepted_at": 99.}))
        self.assertEqual(self.stored_metadata(cancelled)["context"]["delivery"], "prepared")
        self.assertEqual(self.store.message(cancelled)["status"], "cancelled")

    def test_retrieved_but_excluded_memory_has_distinct_private_inspector_entry(self):
        first = self.memory("Atlas utilise SQLite.")
        second = self.memory("Résultat privé exclu 8cf80, non transmis.", title="Autre résultat")
        source = {"method": "memory", "memory_id": first["id"], "role": "memory",
                  "created": first["created"], "status": "approved", "title": first["title"],
                  "excerpt": first["content"], "provenance": {"source": "explicit_user"}}
        result = SimpleNamespace(messages=[{"role": "user", "content": "Question Atlas"}],
            sources=[source], stats={"omitted_messages": 0, "memory_count": 1})
        with patch.object(self.store.memory, "search", return_value=[first, second]), patch("jarvis.ui.ContextBuilder") as builder:
            builder.return_value.build.return_value = result
            self.app.send(text="Question Atlas")
        mid = self.finish_response()
        dialog = self.inspector()
        excluded = self.select_source(dialog, "Récupéré, non inséré")
        self.assertIn(f"Souvenir #{second['id']} récupéré", excluded)
        self.assertIn("non inséré dans le contexte", excluded)
        self.assertNotIn(second["content"], excluded)
        captured = self.stored_metadata(mid)["context"]
        self.assertEqual([source["memory_id"] for source in captured["sources"]], [first["id"]])
        self.assertEqual(len(captured["retrieved_memory_candidates"]), 2)

    def test_modified_and_deleted_memory_keep_archived_original_and_refresh_one_window(self):
        original, mid = self.send_with_memory()
        dialog = self.inspector()
        archived = self.stored_metadata(mid)
        first = self.select_source(dialog, "Mémoire approuvée")
        self.assertIn("contenu identique", first)
        self.store.memory.update(original["id"], "Le projet Atlas utilise une autre version.", title="Atlas", topic="Atlas")
        self.assertIs(self.app.open_context(), dialog)
        changed = self.select_source(dialog, "Mémoire approuvée")
        self.assertIn("contenu modifié depuis la requête", changed)
        self.assertIn(original["content"], changed)
        self.assertIn("État actuel : en attente", changed)
        self.store.memory.delete(original["id"], confirmed=True)
        self.assertIs(self.app.open_context(), dialog)
        missing = self.select_source(dialog, "Mémoire approuvée")
        self.assertIn("souvenir supprimé", missing)
        self.assertIn(original["content"], missing)
        self.assertEqual(self.stored_metadata(mid), archived)

    def test_private_context_does_not_enter_cognitive_or_gpu_projection(self):
        secret = "Instruction hyperprivée 52bc3"
        private_memory = self.memory("Le secret Atlas vaut 78cc39.")
        self.app.settings = replace(self.app.settings, system_prompt=secret)
        self.app.send(text="Quel secret pour le projet Atlas ?")
        self.app.cognitive_view.refresh(force=True)
        public = json.dumps(self.app.cognitive.snapshot(), ensure_ascii=False) + self.app.presence.cognitive_text
        self.assertNotIn(secret, public)
        self.assertNotIn(private_memory["content"], public)
        self.app.presence.session_factory = RendererDouble
        self.assertTrue(self.app.presence.set_engine("gpu"))
        child = self.app.presence._gpu
        child.events.append({"kind": "ready", "renderer": {"acceleration": "test_double"}})
        deadline = time.monotonic() + 3
        while self.app.presence.active_engine != "gpu" and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertEqual(self.app.presence.active_engine, "gpu")
        self.app.cognitive_view.refresh(force=True)
        self.app.presence._render()
        self.assertTrue(child.frames)
        packet = json.dumps(child.frames[-1], ensure_ascii=False)
        self.assertNotIn(secret, packet)
        self.assertNotIn(private_memory["content"], packet)
        self.assertNotIn("system_instructions", packet)
        self.assertNotIn("provenance", packet)


if __name__ == "__main__":
    unittest.main()
