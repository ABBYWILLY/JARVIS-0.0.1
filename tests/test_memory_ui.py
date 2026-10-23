"""Explicit Tk memory actions against the real local SQLite repository."""
import gc
import hashlib
import json
import sqlite3
import tempfile
import tkinter as tk
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.memory_ui import IMPORT_LIMIT, MemoryDialog
from jarvis.storage import Store
from jarvis.ui import App
from tests.test_jarvis import display_available
from tests.test_reasoning_ui import ControlledWorker


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class MemoryDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "memory.sqlite3"
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.app.memory_button.invoke()
        self.dialog = self.app.memory_dialog
        self.addCleanup(self.close_app)

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.dialog = self.app = self.root = self.store = None
        gc.collect()

    def draft(self, content="Le projet Atlas utilise SQLite.", topic="atlas-stockage"):
        self.dialog.new()
        self.dialog.fill(content)
        self.dialog.title.set("Projet Atlas")
        self.dialog.topic.set(topic)
        self.dialog.save()
        return self.dialog.selected_id

    def test_manual_create_requires_approval_and_refusal_changes_nothing(self):
        mid = self.draft()
        self.assertEqual(self.store.memory.get(mid)["status"], "pending")
        self.assertEqual(self.store.memory.search("Atlas"), [])
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=False):
            self.dialog.approve()
        self.assertEqual(self.store.memory.get(mid)["status"], "pending")
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=True):
            self.dialog.approve()
        self.assertEqual(self.store.memory.get(mid)["status"], "approved")
        self.assertEqual(self.store.memory.search("Atlas")[0]["id"], mid)
        self.assertIn("manual", self.dialog.info.get("1.0", "end"))
        self.assertIn("Création", self.dialog.info.get("1.0", "end"))

    def test_unsaved_changes_cannot_approve_different_stored_content(self):
        mid = self.draft()
        self.dialog.fill("Un contenu différent non enregistré.")
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=True) as confirm:
            self.dialog.approve()
            confirm.assert_not_called()
        self.assertEqual(self.store.memory.get(mid)["status"], "pending")
        self.assertEqual(self.store.memory.get(mid)["content"], "Le projet Atlas utilise SQLite.")
        self.assertIn("non enregistrées", self.dialog.status.get())

    def test_correction_and_delete_are_confirmed_and_backed_up_without_history_changes(self):
        chat = self.store.begin_turn(self.app.session_id, "Archive originale", "local")
        self.store.update_response(chat, "À préserver", "complete")
        history = [dict(row) for row in self.store.messages(self.app.session_id)]
        mid = self.draft()
        self.store.memory.approve(mid, confirmed=True)
        self.dialog.refresh(mid)
        self.dialog.fill("Le projet Atlas utilise SQLite localement.")
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=False):
            self.dialog.save()
        self.assertEqual(self.store.memory.get(mid)["status"], "approved")
        self.assertEqual(list(Path(self.temp.name).glob("*memory-update*")), [])
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=True):
            self.dialog.save()
        self.assertEqual(self.store.memory.get(mid)["status"], "pending")
        updates = list(Path(self.temp.name).glob("*memory-update*"))
        self.assertEqual(len(updates), 1)
        with closing(sqlite3.connect(updates[0])) as backup:
            self.assertEqual(backup.execute("SELECT content FROM memories WHERE id=?", (mid,)).fetchone()[0],
                             "Le projet Atlas utilise SQLite.")
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=False):
            self.dialog.delete()
        self.assertIsNotNone(self.store.memory.get(mid))
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=True) as confirm:
            self.dialog.delete()
            self.assertIn(f"#{mid}", confirm.call_args.args[1])
            self.assertIn("atlas-stockage", confirm.call_args.args[1])
        self.assertIsNone(self.store.memory.get(mid))
        self.assertEqual(len(list(Path(self.temp.name).glob("*memory-delete*"))), 1)
        self.assertEqual([dict(row) for row in self.store.messages(self.app.session_id)], history)

    def test_conflicting_topic_has_an_explanation_and_disable_excludes_recall(self):
        first = self.draft("Atlas utilise SQLite.")
        self.store.memory.approve(first, confirmed=True)
        second = self.draft("Atlas utilise PostgreSQL.")
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=True):
            self.dialog.approve()
        self.assertEqual(self.store.memory.get(second)["status"], "pending")
        self.assertIn("Conflit", self.dialog.status.get())
        self.dialog.refresh(first)
        self.dialog.disable()
        self.assertEqual(self.store.memory.get(first)["status"], "disabled")
        self.assertEqual(self.store.memory.search("Atlas"), [])

    def test_document_import_preserves_unicode_hash_and_stays_pending(self):
        path = Path(self.temp.name) / "notes.md"
        data = "# Projet\nÉté, cœur ❤️ et mémoire française.\n".encode("utf-8")
        path.write_bytes(data)
        with patch("jarvis.memory_ui.filedialog.askopenfilename", return_value=str(path)):
            self.dialog.import_file()
        row = self.store.memory.get(self.dialog.selected_id)
        self.assertEqual((row["kind"], row["status"]), ("document", "pending"))
        self.assertEqual(row["content"], data.decode("utf-8"))
        provenance = json.loads(row["provenance"])
        self.assertEqual(provenance["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(provenance["path"], str(path.resolve()))
        self.assertEqual(self.store.memory.search("française"), [])
        self.assertIn("Été, cœur ❤️", self.dialog.content.get("1.0", "end"))

    def test_import_refuses_oversize_and_invalid_utf8_without_creating_entries(self):
        path = Path(self.temp.name) / "notes.txt"
        for data, message in ((b"a" * (IMPORT_LIMIT + 1), "256 Kio"), (b"\xff\xfe", "UTF-8")):
            with self.subTest(message=message):
                path.write_bytes(data)
                with patch("jarvis.memory_ui.filedialog.askopenfilename", return_value=str(path)):
                    self.dialog.import_file()
                self.assertEqual(self.store.memory.list(), [])
                self.assertIn(message, self.dialog.status.get())

    def test_global_search_originals_are_read_only_and_do_not_create_memories(self):
        mid = self.store.begin_turn(self.app.session_id, "Document Atlas archivé", "local")
        self.store.update_response(mid, "Réponse Atlas originale", "complete")
        self.dialog.query.set("Atlas")
        self.dialog.search()
        self.assertEqual(len(self.dialog.message_rows), 2)
        self.dialog.message_list.selection_set(0)
        self.dialog.select_message()
        self.assertEqual(str(self.dialog.content.cget("state")), "disabled")
        self.dialog.save()
        self.assertEqual(self.store.memory.list(), [])
        self.assertIn("lecture seule", self.dialog.status.get())
        self.assertEqual(self.store.message(mid)["content"], "Réponse Atlas originale")

    def test_prepare_summary_keeps_exact_quotes_pending_with_inspectable_origins(self):
        mid = self.store.begin_turn(self.app.session_id, "Question Atlas", "local")
        quote = "Le projet Atlas utilise le fichier cœur.sqlite."
        self.store.update_response(mid, quote, "complete")
        original = self.store.message(mid)
        source = {"message_id": mid, "session_id": original["session_id"], "created": original["created"],
                  "role": "assistant", "method": "extractive", "excerpt": quote}
        self.store.update_message_metadata(mid, {"context": {"sources": [source]}})
        self.dialog.prepare_summary()
        row = self.store.memory.get(self.dialog.selected_id)
        self.assertEqual((row["kind"], row["status"]), ("summary", "pending"))
        self.assertIn(quote, row["content"])
        self.assertEqual(json.loads(row["provenance"])["message_ids"], [mid])
        self.dialog.inspect_origins()
        origins = next(widget for widget in self.dialog.window.winfo_children()
                       if isinstance(widget, tk.Toplevel) and widget.title() == "Origines de la mémoire")
        text = next(widget for widget in origins.winfo_children() if isinstance(widget, tk.Text))
        self.assertIn(f"Original #{mid} :\n{quote}", text.get("1.0", "end"))
        self.assertEqual(str(text.cget("state")), "disabled")

    def test_search_clears_selected_memory_before_destructive_actions(self):
        mid = self.draft()
        self.dialog.query.set("absent")
        self.dialog.search()
        self.assertIsNone(self.dialog.selected_id)
        with patch("jarvis.memory_ui.messagebox.askyesno", return_value=True) as confirm:
            self.dialog.delete()
            confirm.assert_not_called()
        self.assertIsNotNone(self.store.memory.get(mid))

    def test_context_uses_only_approved_memory_and_retains_snapshot_after_deletion(self):
        approved = self.draft("Le projet Atlas utilise SQLite pour sa mémoire.")
        self.store.memory.approve(approved, confirmed=True)
        self.draft("Le projet Atlas contient une hypothèse non confirmée.", topic="")
        self.app.settings = Settings(model="qwen3.5:4b")
        self.app.models = ["qwen3.5:4b"]
        self.app.worker = ControlledWorker()
        self.app.send(text="Quelle mémoire pour le projet Atlas ?")
        context = json.loads(self.store.messages(self.app.session_id)[-1]["metadata"])["context"]
        memory_sources = [source for source in context["sources"] if source["method"] == "memory"]
        self.assertEqual([source["memory_id"] for source in memory_sources], [approved])
        self.assertEqual(memory_sources[0]["status"], "approved")
        self.store.memory.delete(approved, confirmed=True)
        self.app.open_context()
        inspector = next(widget for widget in self.root.winfo_children()
                         if isinstance(widget, tk.Toplevel) and widget.title() == "Contexte envoyé à Ollama")
        text = inspector.nametowidget("detail.details").get("1.0", "end")
        self.assertIn("État lors de la requête : approuvé", text)
        self.assertIn("entrée supprimée ou indisponible", text)
        self.assertIn(memory_sources[0]["excerpt"], text)
        self.assertIn("manual", text)

    def test_reused_message_identifier_cannot_be_presented_as_historical_original(self):
        mid = self.store.begin_turn(self.app.session_id, "Nouvelle question", "local")
        self.store.update_response(mid, "NOUVEL_ORIGINAL_DIFFERENT", "complete")
        source = {"message_id": mid, "session_id": "conversation-historique-supprimee", "created": "2000-01-01",
                  "role": "assistant", "method": "extractive", "excerpt": "Citation historique conservée."}
        self.store.update_message_metadata(mid, {"context": {"sources": [source]}})
        self.app.open_context()
        inspector = next(widget for widget in self.root.winfo_children()
                         if isinstance(widget, tk.Toplevel) and widget.title() == "Contexte envoyé à Ollama")
        text = inspector.nametowidget("detail.details").get("1.0", "end")
        self.assertIn("Citation historique conservée.", text)
        self.assertIn("Original indisponible", text)
        self.assertNotIn("NOUVEL_ORIGINAL_DIFFERENT", text)

    def test_memory_context_trace_distinguishes_explicit_memories_and_history_without_claiming_truth(self):
        memory = self.draft()
        self.store.memory.approve(memory, confirmed=True)
        response = self.store.begin_turn(self.app.session_id, "Question Atlas", "local")
        self.store.update_response(response, "Réponse", "complete")
        sources = [
            {"method": "memory", "memory_id": memory, "status": "approved", "excerpt": "Version transmise"},
            {"method": "recent", "message_id": memory, "role": "user", "excerpt": "Donnée utilisateur"},
            {"method": "extractive", "message_id": 88, "role": "assistant", "excerpt": "Texte généré"},
        ]
        self.store.update_message_metadata(response, {"context": {"sources": sources}})
        self.dialog.refresh(memory)
        trace = self.dialog.context_info.get("1.0", "end")
        self.assertIn("Sélection temporaire de requête", trace)
        self.assertIn("Souvenirs explicitement rappelés : 1", trace)
        self.assertIn("Références historiques : 2", trace)
        self.assertIn("message utilisateur", trace)
        self.assertIn("réponse générée, non vérifiée", trace)
        self.assertIn("ne prouve pas que le modèle", trace)
        self.assertEqual(str(self.dialog.context_info.cget("state")), "disabled")
        info = self.dialog.info.get("1.0", "end")
        self.assertIn(f"Souvenir explicite #{memory}", info)
        self.assertIn(f"Inclus dans 1 contexte(s) enregistré(s) : #{response}", info)
        self.assertIn("manual", info)
        self.assertEqual(len(self.store.memory.list()), 1)
        self.assertEqual(json.loads(self.store.message(response)["metadata"])["context"]["sources"], sources)

    def test_memory_usage_window_is_bounded_scoped_and_reports_invalid_trace(self):
        memory = self.draft()
        for index in range(101):
            response = self.store.begin_turn(self.app.session_id, f"Question {index}", "local")
            self.store.update_response(response, "Réponse", "complete")
            self.store.update_message_metadata(response, {"context": {"sources": [
                {"method": "memory", "memory_id": memory}] if index == 0 else []}})
        other = self.store.begin_turn(self.store.new_session(), "Autre conversation", "local")
        self.store.update_message_metadata(other, {"context": {"sources": [{"method": "memory", "memory_id": memory}]}})
        self.dialog.refresh(memory)
        self.assertEqual(len(self.dialog.context_records), 100)
        self.assertIn("Aucune inclusion enregistrée parmi les 100 dernières", self.dialog.info.get("1.0", "end"))
        self.store.update_message_metadata(response, {"context": {"sources": ["trace invalide"]}})
        self.dialog.refresh_context()
        trace = self.dialog.context_info.get("1.0", "end")
        self.assertIn(f"Réponse #{response} : trace illisible", trace)
        self.assertEqual(len(self.store.memory.list()), 1)

    def test_refreshing_prompt_trace_preserves_unsaved_memory_edits_and_uses_existing_inspector(self):
        memory = self.draft()
        self.dialog.refresh(memory)
        edited = "Brouillon non sauvegardé : été 😊."
        self.dialog.fill(edited)
        self.dialog.title.set("Titre non sauvegardé")
        self.dialog.refresh_context()
        self.assertEqual(self.dialog.content.get("1.0", "end-1c"), edited)
        self.assertEqual(self.dialog.title.get(), "Titre non sauvegardé")
        self.assertNotEqual(self.store.memory.get(memory)["content"], edited)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        inspector = next(widget for widget in descendants(self.dialog.window)
                         if getattr(widget, "cget", None) and widget.winfo_class() == "TButton"
                         and widget.cget("text") == "Inspecter le contexte envoyé")
        inspector.invoke()
        self.assertTrue(any(isinstance(widget, tk.Toplevel) and widget.title() == "Contexte envoyé à Ollama"
                            for widget in self.root.winfo_children()))


if __name__ == "__main__":
    unittest.main()
