"""Real SQLite memories, FTS indexes, snapshots and lossless v2 migration."""
import json
import sqlite3
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.memory import KINDS, MemoryRepository
from jarvis.storage import SCHEMA_VERSION, Store


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "memory.sqlite3"
        self.store = Store(self.path)
        self.addCleanup(lambda: self.store.close())
        self.memory = self.store.memory

    def approved(self, content, **kwargs):
        mid = self.memory.create(content, **kwargs)
        self.memory.approve(mid, confirmed=True)
        return mid

    def snapshot_row(self, path, mid):
        with sqlite3.connect(path) as snapshot:
            snapshot.row_factory = sqlite3.Row
            self.assertEqual(snapshot.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            return snapshot.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()

    def test_all_categories_start_pending_with_exact_original_and_provenance(self):
        original = "  Le réseau d’Éole 👩🏽‍💻 reste local.\n"
        provenance = {"message_id": 42, "session_id": "origine", "source": "confirmation utilisateur"}
        for kind in KINDS:
            mid = self.memory.create(original, kind=kind, title="Éole", topic="Réseau", provenance=provenance)
            row = self.memory.get(mid)
            self.assertEqual(row["content"], original)
            self.assertEqual(row["kind"], kind)
            self.assertEqual(row["status"], "pending")
            self.assertEqual(json.loads(row["provenance"]), provenance)
            self.assertTrue(row["created"].endswith("Z"))
            self.assertTrue(row["updated"].endswith("Z"))
        self.assertEqual(len(self.memory.list()), 4)
        self.assertEqual(self.memory.search("Éole"), [])

    def test_explicit_approval_is_required_and_only_approved_entries_are_selected(self):
        mid = self.memory.create("Le serveur Zephyr écoute sur le port 8765.")
        for unconfirmed in (False, None, 1, "oui"):
            with self.subTest(unconfirmed=unconfirmed), self.assertRaisesRegex(ValueError, "Confirmez"):
                self.memory.approve(mid, confirmed=unconfirmed)
        self.assertEqual(self.memory.get(mid)["status"], "pending")
        self.assertEqual(self.memory.search("Zephyr"), [])
        self.assertEqual([r["id"] for r in self.memory.search("Zephyr", approved_only=False)], [mid])
        self.memory.approve(mid, confirmed=True)
        self.assertEqual([r["id"] for r in self.memory.search("Zephyr")], [mid])

    def test_deduplication_is_nfc_exact_per_kind_and_reports_original_id(self):
        mid = self.memory.create("Le café d’Éole est local.")
        duplicate = "  " + unicodedata.normalize("NFD", "Le café d’Éole est local.") + "\n"
        with self.assertRaisesRegex(ValueError, "#" + str(mid)):
            self.memory.create(duplicate)
        other = self.memory.create("Le café d’Éole est local.", kind="project")
        case = self.memory.create("Le café d’Éole est LOCAL.")
        self.assertNotEqual(mid, other)
        self.assertNotEqual(mid, case)
        self.assertEqual(len(self.memory.list()), 3)

    def test_topic_conflict_is_explicit_and_never_silently_replaces_a_fact(self):
        old = self.approved("Le port vaut 8765.", topic="  Réseau   ÉOLE ")
        new = self.memory.create("Le port vaut 9000.", topic=unicodedata.normalize("NFD", "réseau éole"))
        with self.assertRaisesRegex(ValueError, f"#{new}.*#{old}"):
            self.memory.approve(new, confirmed=True)
        self.assertEqual(self.memory.get(old)["status"], "approved")
        self.assertEqual(self.memory.get(new)["status"], "pending")
        self.memory.disable(old)
        self.memory.approve(new, confirmed=True)
        self.assertEqual(self.memory.get(new)["status"], "approved")

    def test_identical_content_across_kinds_is_not_a_topic_conflict(self):
        text = "Le serveur Éole reste privé."
        first = self.approved(text, topic="Éole", kind="durable")
        second = self.approved(text, topic="éole", kind="project")
        self.assertEqual(self.memory.get(first)["status"], "approved")
        self.assertEqual(self.memory.get(second)["status"], "approved")

    def test_update_saves_approved_original_then_resets_to_pending_and_preserves_provenance(self):
        provenance = {"message_id": 12, "source": "commande explicite"}
        mid = self.approved("Le serveur Zephyr utilise 8765.", provenance=provenance)
        created = self.memory.get(mid)["created"]
        backup = self.memory.update(mid, "Le serveur Boreal utilise 9000.", title="Nouveau", topic="Port")
        previous = self.snapshot_row(backup, mid)
        self.assertEqual(previous["content"], "Le serveur Zephyr utilise 8765.")
        self.assertEqual(previous["status"], "approved")
        current = self.memory.get(mid)
        self.assertEqual(current["status"], "pending")
        self.assertEqual(current["created"], created)
        self.assertEqual(json.loads(current["provenance"]), provenance)
        self.assertEqual(self.memory.search("Boreal"), [])
        self.memory.approve(mid, confirmed=True)
        self.assertEqual([r["id"] for r in self.memory.search("Boreal")], [mid])
        self.assertEqual(self.memory.search("Zephyr"), [])

    def test_update_duplicate_is_rejected_without_changing_either_entry(self):
        first = self.approved("Un souvenir Éole.")
        second = self.memory.create("Un souvenir Zephyr.")
        with self.assertRaisesRegex(ValueError, "#" + str(first)):
            self.memory.update(second, "Un souvenir Éole.")
        self.assertEqual(self.memory.get(second)["content"], "Un souvenir Zephyr.")
        self.assertEqual(self.memory.get(first)["status"], "approved")

    def test_backup_failure_prevents_update_and_delete(self):
        mid = self.approved("Ne pas perdre Éole.")
        with patch.object(self.memory, "backup_callback", side_effect=OSError("disque indisponible")):
            with self.assertRaisesRegex(OSError, "disque"):
                self.memory.update(mid, "Autre contenu.")
            with self.assertRaisesRegex(OSError, "disque"):
                self.memory.delete(mid, confirmed=True)
        self.assertEqual(self.memory.get(mid)["content"], "Ne pas perdre Éole.")
        self.assertEqual(self.memory.get(mid)["status"], "approved")

    def test_sql_failure_after_backup_keeps_original_and_snapshot(self):
        mid = self.approved("Éole doit rester intact.")
        with self.store.db:
            self.store.db.execute("""CREATE TRIGGER reject_memory_update BEFORE UPDATE ON memories
                BEGIN SELECT RAISE(ABORT,'injected update failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected"):
            self.memory.update(mid, "Ce contenu ne doit pas remplacer l’ancien.")
        self.assertEqual(self.memory.get(mid)["content"], "Éole doit rester intact.")
        self.assertEqual(self.memory.get(mid)["status"], "approved")
        backups = list(self.path.parent.glob("*.memory-update-*-backup*.sqlite3"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.snapshot_row(backups[0], mid)["content"], "Éole doit rester intact.")

    def test_disable_is_reversible_and_does_not_delete_provenance(self):
        mid = self.approved("Le projet Zephyr demeure local.", provenance={"origin": "utilisateur"})
        self.memory.disable(mid)
        self.assertEqual(self.memory.search("Zephyr"), [])
        self.assertEqual(self.memory.get(mid)["status"], "disabled")
        self.assertEqual(json.loads(self.memory.get(mid)["provenance"]), {"origin": "utilisateur"})
        self.memory.approve(mid, confirmed=True)
        self.assertEqual([r["id"] for r in self.memory.search("Zephyr")], [mid])

    def test_delete_requires_confirmation_and_snapshot_preserves_other_user_data(self):
        sid = self.store.new_session()
        response = self.store.begin_turn(sid, "Question vocale", "qwen-abliterated", source="voice",
                                         metadata={"voice": "Tom", "wave": "conservée"})
        self.store.update_response(response, "Réponse intacte ❤️", "complete")
        self.store.set_preference("voice", {"speaker": "Siwis"})
        mid = self.approved("Mémoire à supprimer.")
        other = self.approved("Autre mémoire à préserver.")
        with self.assertRaisesRegex(ValueError, "Confirmez"):
            self.memory.delete(mid)
        self.assertIsNotNone(self.memory.get(mid))
        backup = self.memory.delete(mid, confirmed=True)
        self.assertEqual(self.snapshot_row(backup, mid)["content"], "Mémoire à supprimer.")
        self.assertIsNone(self.memory.get(mid))
        self.assertIsNotNone(self.memory.get(other))
        self.assertEqual(self.store.messages(sid)[1]["content"], "Réponse intacte ❤️")
        self.assertEqual(self.store.messages(sid)[0]["source"], "voice")
        self.assertEqual(self.store.get_preference("voice"), {"speaker": "Siwis"})
        self.assertEqual(self.memory.search("supprimer"), [])

    def test_deleted_last_identifier_is_never_reused_after_reopen(self):
        deleted = self.memory.create("Ancienne mémoire source d’un contexte sauvegardé.")
        self.memory.delete(deleted, confirmed=True)
        self.store.close()
        self.store = Store(self.path)
        self.memory = self.store.memory
        created = self.memory.create("Nouvelle mémoire distincte.")
        self.assertGreater(created, deleted)
        self.assertIsNone(self.memory.get(deleted))

    def test_repeated_snapshots_are_unique_and_each_holds_previous_content(self):
        mid = self.memory.create("Version initiale.")
        first = self.memory.update(mid, "Version suivante.")
        second = self.memory.update(mid, "Version finale.")
        self.assertNotEqual(first, second)
        self.assertEqual(self.snapshot_row(first, mid)["content"], "Version initiale.")
        self.assertEqual(self.snapshot_row(second, mid)["content"], "Version suivante.")

    def test_ftssafe_queries_unicode_and_meaningful_words_rank_real_match(self):
        for number in range(8):
            self.approved(f"Le moniteur conserve mon ancien journal {number}.")
        actual = self.approved("Le réseau Éole utilise le port 8765 avec son moteur IA.", title="Réseau Éole")
        self.assertTrue(self.memory.fts_available)
        self.assertEqual([r["id"] for r in self.memory.search("Quel est le port du reseau Eole ?")], [actual])
        self.assertEqual([r["id"] for r in self.memory.search("IA 8765")], [actual])
        self.assertEqual(self.memory.search("LE MON LE JE"), [])
        self.assertEqual(self.memory.search("🙂"), [])
        self.memory.search('"Eole" OR "x"; DROP TABLE memories; --')
        self.assertEqual(len(self.memory.list()), 9)

    def test_messages_index_tracks_stream_updates_and_session_cascade_without_creating_memories(self):
        sid = self.store.new_session()
        mid = self.store.begin_turn(sid, "Ancien réseau Éole", "qwen", source="voice", metadata={"a": 1})
        self.store.update_response(mid, "Première version Zephyr", "streaming")
        found = self.memory.search_messages("Eole")
        self.assertEqual(found[0]["content"], "Ancien réseau Éole")
        self.assertEqual(found[0]["session_id"], sid)
        self.assertEqual(found[0]["source"], "voice")
        self.assertEqual(json.loads(found[0]["metadata"]), {"a": 1})
        self.store.update_response(mid, "Version finale Boreal", "cancelled")
        self.assertEqual(self.memory.search_messages("Zephyr"), [])
        self.assertEqual(self.memory.search_messages("Boreal")[0]["status"], "cancelled")
        self.assertEqual(self.memory.list(), [])
        self.store.delete_session(sid)
        self.assertEqual(self.memory.search_messages("Eole Boreal"), [])

    def test_streaming_replies_are_indexed_once_finalized_and_status_updates_keep_index_consistent(self):
        sid = self.store.new_session()
        mid = self.store.begin_turn(sid, "Question initiale", "qwen")
        for text in ("Zephyr", "Zephyr Boreal", "Zephyr Boreal Aurora"):
            self.store.update_response(mid, text, "streaming")
            self.assertEqual(self.memory.search_messages("Zephyr Boreal Aurora"), [])
            self.assertIsNone(self.store.db.execute(
                "SELECT id FROM messages_fts_docsize WHERE id=?", (mid,)).fetchone())
        self.store.update_response(mid, "Zephyr Boreal Aurora", "complete")
        self.assertEqual([r["id"] for r in self.memory.search_messages("Aurora")], [mid])
        # A finalized original can be corrected, or explicitly returned to an
        # in-progress state, without leaving obsolete tokens in the index.
        self.store.update_response(mid, "Nouveau Vega", "complete")
        self.assertEqual(self.memory.search_messages("Zephyr Aurora"), [])
        self.assertEqual([r["id"] for r in self.memory.search_messages("Vega")], [mid])
        self.store.update_response(mid, "Reprise Polaris", "streaming")
        self.assertEqual(self.memory.search_messages("Vega Polaris"), [])
        self.store.update_response(mid, "Reprise Polaris", "error")
        self.assertEqual(self.memory.search_messages("Polaris")[0]["status"], "error")
        self.store.delete_session(sid)
        self.assertEqual(self.memory.search_messages("Polaris"), [])

    def test_interrupted_stream_is_indexed_after_reopen_recovery(self):
        sid = self.store.new_session()
        mid = self.store.begin_turn(sid, "Question initiale", "qwen")
        self.store.update_response(mid, "Réponse inachevée Zephyr", "streaming")
        self.assertEqual(self.memory.search_messages("Zephyr"), [])
        self.store.close()
        self.store = Store(self.path)
        self.memory = self.store.memory
        found = self.memory.search_messages("Zephyr")
        self.assertEqual([r["id"] for r in found], [mid])
        self.assertEqual(found[0]["status"], "interrupted")

    def test_explicit_like_fallback_preserves_unicode_and_approval_filter(self):
        fallback = MemoryRepository(self.store.db, self.store.backup, fts_available=False)
        approved = self.approved("Le réseau d’Éole écoute sur 8765.")
        pending = fallback.create("Autre réseau d’Éole.")
        self.assertFalse(fallback.fts_available)
        self.assertEqual([r["id"] for r in fallback.search("reseau EOLE")], [approved])
        self.assertEqual({r["id"] for r in fallback.search("Eole", approved_only=False)}, {approved, pending})
        sid = self.store.new_session()
        mid = self.store.begin_turn(sid, "Un réseau Éole archivé.", "local")
        self.assertEqual(fallback.search_messages("reseau EOLE")[0]["session_id"], sid)
        self.store.update_response(mid, "Réponse streaming Zephyr Boreal", "streaming")
        self.assertEqual(fallback.search_messages("Zephyr Boreal"), [])
        self.store.update_response(mid, "Réponse finale Zephyr Boreal", "complete")
        self.assertEqual([row["id"] for row in fallback.search_messages("Zephyr Boreal")], [mid])

    def test_invalid_content_provenance_limits_and_identifiers_do_not_write(self):
        for kwargs in ({"content": ""}, {"content": " \n"}, {"content": None}, {"content": "ok", "kind": "auto"},
                       {"content": "ok", "provenance": []}, {"content": "ok", "provenance": {"n": float("nan")}},
                       {"content": "é" * 131073}, {"content": "ok", "topic": None}):
            with self.subTest(kwargs={key: type(value).__name__ for key, value in kwargs.items()}), self.assertRaises(ValueError):
                self.memory.create(**kwargs)
        self.assertEqual(self.memory.list(), [])
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.memory.get(invalid)
        for limit in (0, 101, True, "1"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.memory.search("Éole", limit=limit)

    def test_backup_refuses_pending_transactions_instead_of_hanging(self):
        self.store.db.execute("INSERT INTO preferences VALUES ('uncommitted','true')")
        with self.assertRaisesRegex(ValueError, "opération en cours"):
            self.store.backup("manual")
        self.store.db.rollback()


class MemoryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy-v2.sqlite3"
        self.legacy = sqlite3.connect(self.path)
        self.addCleanup(self.legacy.close)
        self.legacy.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE sessions(id TEXT PRIMARY KEY,title TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,content TEXT NOT NULL,model TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'text',metadata TEXT NOT NULL DEFAULT '{}');
            CREATE INDEX messages_session ON messages(session_id,id);
            CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            PRAGMA user_version=2;
        """)
        with self.legacy:
            self.legacy.execute("INSERT INTO sessions VALUES ('voice','Ancienne voix','2026-01-01T12:00:00Z')")
            self.legacy.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)", [
                (7, "voice", "user", "Réseau Éole 👩🏽‍💻", "qwen-abliterated:4b", "complete",
                 "2026-01-01T12:00:00Z", "voice", '{"voice":"Tom","latency_ms":120}'),
                (8, "voice", "assistant", "Local, préservé ❤️", "qwen-abliterated:4b", "complete",
                 "2026-01-01T12:00:01Z", "voice", '{"generation_metrics":{"eval_count":12}}'),
            ])
            self.legacy.execute("INSERT INTO settings VALUES ('legacy-extra','Ne jamais modifier')")
            self.legacy.execute("INSERT INTO preferences VALUES ('voice','{\"voice\":\"Siwis\"}')")
        self.original = {table: self.legacy.execute("SELECT * FROM " + table).fetchall()
                         for table in ("sessions", "messages", "settings", "preferences")}

    def assert_original(self, db):
        for table, original in self.original.items():
            self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM " + table)], original)

    def test_v2_backup_migration_backfills_fts_without_changing_existing_data(self):
        store = Store(self.path)
        self.addCleanup(store.close)
        self.assertEqual(store.migration_backup, Path(str(self.path) + ".v2-backup.sqlite3"))
        with sqlite3.connect(store.migration_backup) as backup:
            self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assert_original(backup)
            self.assertIsNone(backup.execute("SELECT name FROM sqlite_master WHERE name='memories'").fetchone())
        self.assert_original(store.db)
        self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(store.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertTrue(store.memory.fts_available)
        found = store.memory.search_messages("reseau Eole")
        self.assertEqual([row["id"] for row in found], [7])
        self.assertEqual(json.loads(found[0]["metadata"])["voice"], "Tom")
        self.assertEqual(store.memory.list(), [])
        store.close()
        reopened = Store(self.path)
        self.addCleanup(reopened.close)
        self.assertIsNone(reopened.migration_backup)
        self.assert_original(reopened.db)

    def test_existing_v2_backup_is_never_overwritten(self):
        previous = Path(str(self.path) + ".v2-backup.sqlite3")
        previous.write_bytes(b"previous user snapshot")
        store = Store(self.path)
        self.addCleanup(store.close)
        self.assertNotEqual(previous, store.migration_backup)
        self.assertEqual(previous.read_bytes(), b"previous user snapshot")
        with sqlite3.connect(store.migration_backup) as backup:
            self.assert_original(backup)

    def test_unexpected_index_error_rolls_back_entire_migration(self):
        original_connect = sqlite3.connect

        class RejectMessageIndex(sqlite3.Connection):
            def execute(self, statement, parameters=()):
                if statement.startswith("CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts"):
                    raise sqlite3.OperationalError("injected memory index failure")
                return super().execute(statement, parameters)

        def connect(*args, **kwargs):
            return original_connect(*args, factory=RejectMessageIndex, **kwargs)

        with patch("jarvis.storage.sqlite3.connect", side_effect=connect):
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected"):
                Store(self.path)
        self.assert_original(self.legacy)
        self.assertEqual(self.legacy.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(self.legacy.execute("SELECT name FROM sqlite_master WHERE name LIKE 'memories%' OR name='messages_fts'").fetchall(), [])
        self.assertTrue(Path(str(self.path) + ".v2-backup.sqlite3").is_file())

    def test_missing_fts_is_explicit_and_next_capable_open_rebuilds_both_indexes(self):
        original_connect = sqlite3.connect

        class WithoutFTS(sqlite3.Connection):
            def execute(self, statement, parameters=()):
                if statement.startswith("CREATE VIRTUAL TABLE"):
                    raise sqlite3.OperationalError("no such module: fts5")
                return super().execute(statement, parameters)

        def connect(*args, **kwargs):
            return original_connect(*args, factory=WithoutFTS, **kwargs)

        with patch("jarvis.storage.sqlite3.connect", side_effect=connect):
            store = Store(self.path)
        self.assertFalse(store.memory.fts_available)
        mid = store.memory.create("Le réseau Éole est approuvé.")
        store.memory.approve(mid, confirmed=True)
        self.assertEqual([row["id"] for row in store.memory.search("Eole")], [mid])
        self.assertEqual(store.memory.search_messages("reseau EOLE")[0]["id"], 7)
        self.assert_original(store.db)
        store.close()
        reopened = Store(self.path)
        self.addCleanup(reopened.close)
        self.assertTrue(reopened.memory.fts_available)
        self.assertEqual([row["id"] for row in reopened.memory.search("Eole")], [mid])
        self.assertEqual(reopened.memory.search_messages("reseau EOLE")[0]["id"], 7)


if __name__ == "__main__":
    unittest.main()
