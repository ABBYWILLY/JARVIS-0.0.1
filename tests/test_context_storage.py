"""Context provenance reads canonical archives without migrating or editing them."""
import json
import tempfile
import unittest
from pathlib import Path

from jarvis.config import Settings
from jarvis.storage import Store


class ContextStorageTests(unittest.TestCase):
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
                self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], 2)
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
