"""Context provenance reads canonical archives without migrating or editing them."""
import json
import tempfile
import unittest
from pathlib import Path

from jarvis.config import Settings
from jarvis.storage import SCHEMA_VERSION, Store


class ContextStorageTests(unittest.TestCase):
    def test_context_projection_preserves_pair_boundaries_and_all_status_rules(self):
        """An invalid/orphan archive row must not realign unrelated messages."""
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "mixed.sqlite3")
            try:
                sid, other = store.new_session(), store.new_session()
                statuses = ("complete", "streaming", "cancelled", "error", "interrupted")
                included = []
                for status in statuses:
                    mid = store.begin_turn(sid, "Question « été » 👩🏽‍💻 " + status, "original-model")
                    store.update_response(mid, "Réponse " + status, status)
                    if status == "complete":
                        included.extend((mid - 1, mid))
                    foreign = store.begin_turn(other, "Autre session", "autre-modèle")
                    store.update_response(foreign, "Privé", "complete")
                # Keep the old consecutive-pair rule even when imported data
                # contains unexpected roles or a final unpaired message.
                with store.db:
                    store.db.executemany(
                        "INSERT INTO messages(session_id,role,content,status) VALUES (?,?,?,?)",
                        [(sid, "assistant", "Ne doit pas devenir une question", "complete"),
                         (sid, "user", "Ne doit pas devenir une réponse", "complete"),
                         (sid, "user", "Dernière question", "error"),
                         (sid, "assistant", "Réponse finale valide", "complete"),
                         (sid, "user", "Question sans réponse", "complete")])
                originals = store.messages(sid)
                included.extend(row["id"] for row in originals[-3:-1])
                expected = [{key: row[key] for key in ("id", "session_id", "role", "content", "created")}
                            for row in originals if row["id"] in included]
                self.assertEqual(store.context_records(sid), expected)
                self.assertEqual(store.context_records("absent"), [])
                self.assertEqual([tuple(row) for row in store.messages(sid)], [tuple(row) for row in originals])
                self.assertEqual(store.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                store.close()

    def test_large_provenance_is_not_loaded_into_context_rows(self):
        """Only text/provenance IDs are needed by C1; private metadata stays archived."""
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "provenance.sqlite3")
            try:
                sid = store.new_session()
                mid = store.begin_turn(sid, "Quel réglage Éole ?", "abliterated",
                                       metadata={"context": {"system_instructions": "Privé. " * 20000}})
                store.update_response(mid, "Le port est 8421. Ne pas le publier.", "complete")
                metadata = store.message(mid)["metadata"]
                factory = store.db.row_factory
                projected_columns = []
                def observe_columns(cursor, row):
                    projected_columns.append({column[0] for column in cursor.description})
                    return factory(cursor, row)
                store.db.row_factory = observe_columns
                try:
                    records = store.context_records(sid)
                finally:
                    store.db.row_factory = factory
                self.assertEqual(len(records), 2)
                self.assertTrue(projected_columns)
                self.assertTrue(all("metadata" not in columns for columns in projected_columns))
                self.assertEqual(records[1]["content"], "Le port est 8421. Ne pas le publier.")
                self.assertEqual(store.message(mid)["metadata"], metadata)
                self.assertEqual(store.memory.search_messages("Éole")[0]["content"], "Quel réglage Éole ?")
            finally:
                store.close()

    def test_records_match_complete_turns_and_resolve_exact_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "context.sqlite3")
            try:
                sid = store.new_session()
                mid = store.begin_turn(sid, "Mon projet fusée 🚀", "abliterated", source="voice")
                store.update_response(mid, "La précision française : été.", "complete")
                failed = store.begin_turn(sid, "Échange échoué", "abliterated")
                store.update_response(failed, "Fragment", "error")
                other = store.new_session()
                unrelated = store.begin_turn(other, "Privé autre conversation", "abliterated")
                store.update_response(unrelated, "Autre réponse", "complete")
                before = [tuple(row) for row in store.messages(sid)]
                records = store.context_records(sid)
                self.assertEqual([row["id"] for row in records], [mid - 1, mid])
                self.assertEqual([row["session_id"] for row in records], [sid, sid])
                self.assertEqual([row["role"] for row in records], ["user", "assistant"])
                self.assertTrue(all(row["created"] for row in records))
                self.assertEqual(store.context(sid), [
                    {"role": row["role"], "content": row["content"]} for row in records])
                for record in records:
                    original = store.message(record["id"])
                    self.assertEqual(original["content"], record["content"])
                    self.assertEqual(original["source"], "voice")
                self.assertIsNone(store.message(999999))
                self.assertEqual([tuple(row) for row in store.messages(sid)], before)
                self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(store.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                store.close()

    def test_context_preferences_round_trip_and_legacy_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.sqlite3"
            store = Store(path)
            with store.db:
                store.db.execute("INSERT INTO settings VALUES ('profile', ?)",
                                 (json.dumps({"model": "old-model"}),))
            self.assertTrue(store.settings().targeted_context)
            self.assertEqual(store.settings().retrieval_budget, 768)
            store.save_settings(Settings(targeted_context=False, retrieval_budget=512))
            store.close()
            store = Store(path)
            try:
                self.assertFalse(store.settings().targeted_context)
                self.assertEqual(store.settings().retrieval_budget, 512)
            finally:
                store.close()

    def test_context_preferences_validate_types_and_bounds(self):
        for changes in ({"targeted_context": "false"}, {"retrieval_budget": True},
                        {"retrieval_budget": -1}, {"retrieval_budget": 8193}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Settings(**changes).validate()
