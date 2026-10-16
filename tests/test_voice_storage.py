"""Voice provenance and lossless migration of the original SQLite archive."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.storage import Store


class VoiceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "data.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_text_call_compatible_and_voice_details_survive_restart(self):
        text_sid = self.store.new_session()
        self.store.begin_turn(text_sid, "Clavier", "local:latest")
        for message in self.store.messages(text_sid):
            self.assertEqual(message["source"], "text")
            self.assertEqual(json.loads(message["metadata"]), {})

        voice_sid = self.store.new_session()
        metadata = {"final_transcription": "Bonjour été", "voice": "fr_FR-tom-medium",
                    "engine": "piper", "audio_state": "playing"}
        mid = self.store.begin_turn(voice_sid, "Bonjour été", "abliterated:latest",
                                    source="voice", metadata=metadata)
        self.store.update_response(mid, "Réponse intégrale", "complete")
        self.store.update_message_metadata(mid, {"audio_state": "interrupted"})
        self.store.close()
        self.store = Store(self.path)

        user, assistant = self.store.messages(voice_sid)
        for message in (user, assistant):
            self.assertEqual(message["source"], "voice")
            self.assertEqual(message["model"], "abliterated:latest")
            self.assertTrue(message["created"])
            self.assertEqual(json.loads(message["metadata"])["final_transcription"], "Bonjour été")
        self.assertEqual(json.loads(user["metadata"]), metadata)
        self.assertEqual(json.loads(assistant["metadata"]), {**metadata, "audio_state": "interrupted"})
        self.assertEqual(assistant["content"], "Réponse intégrale")
        self.assertEqual(assistant["status"], "complete")
        self.assertEqual(self.store.context(voice_sid), [
            {"role": "user", "content": "Bonjour été"},
            {"role": "assistant", "content": "Réponse intégrale"},
        ])

    def test_metadata_merge_is_canonical_and_preserves_content(self):
        sid = self.store.new_session()
        mid = self.store.begin_turn(sid, "Salut", "local", "voice", {"z": "été", "a": 1})
        self.store.update_response(mid, "Déjà sauvegardé", "cancelled")
        created = self.store.messages(sid)[1]["created"]
        self.store.update_message_metadata(mid, {"interrupted": True, "a": 2})
        message = self.store.messages(sid)[1]
        self.assertEqual(message["metadata"], '{"a":2,"interrupted":true,"z":"été"}')
        self.assertEqual(message["content"], "Déjà sauvegardé")
        self.assertEqual(message["status"], "cancelled")
        self.assertEqual(message["created"], created)
        self.assertEqual(self.store.messages(sid)[0]["metadata"], '{"a":1,"z":"été"}')

    def test_preferences_persist_separately_from_model_settings(self):
        settings = Settings(model="existing", temperature=0.4)
        self.store.save_settings(settings)
        fallback = {"enabled": False}
        self.assertIs(self.store.get_preference("missing", fallback), fallback)
        profiles = {"selected": "female", "profiles": ["tom", "siwis"], "speed": 1.1}
        self.store.set_preference("voice", profiles)
        self.store.set_preference("profile", {"background": "#000000"})
        self.store.set_preference("nullable", None)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get_preference("voice"), profiles)
        self.assertEqual(self.store.get_preference("profile"), {"background": "#000000"})
        self.assertIsNone(self.store.get_preference("nullable", "absent"))
        self.assertEqual(self.store.settings(), settings)
        self.assertEqual(self.store.db.execute("SELECT value FROM preferences WHERE key='voice'").fetchone()[0],
                         '{"profiles":["tom","siwis"],"selected":"female","speed":1.1}')

    def test_invalid_source_or_json_leaves_existing_archive_unchanged(self):
        sid = self.store.new_session()
        for options in ({"source": "cloud"}, {"metadata": []}, {"metadata": {"value": float("nan")}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.store.begin_turn(sid, "Invalid", "local", **options)
        self.assertEqual(self.store.messages(sid), [])
        self.assertEqual(self.store.sessions()[0]["title"], "Nouvelle conversation")
        mid = self.store.begin_turn(sid, "Valid", "local", metadata={"keep": True})
        with self.assertRaises(ValueError):
            self.store.update_message_metadata(mid, {"bad": float("nan")})
        self.assertEqual(json.loads(self.store.messages(sid)[1]["metadata"]), {"keep": True})
        self.store.set_preference("voice", {"speed": 1})
        with self.assertRaises(ValueError):
            self.store.set_preference("voice", {"speed": float("inf")})
        self.assertEqual(self.store.get_preference("voice"), {"speed": 1})


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy.sqlite3"
        # Recreate the actual v1 schema, independently of the new initializer.
        self.legacy = sqlite3.connect(self.path)
        self.addCleanup(self.legacy.close)
        self.legacy.execute("PRAGMA journal_mode=WAL")
        self.legacy.executescript("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                updated TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL, model TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('complete','streaming','cancelled','error','interrupted')),
                created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
            CREATE INDEX messages_session ON messages(session_id,id);
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            PRAGMA user_version=1;
        """)
        self.settings = Settings(model="existing-abliterated", temperature=0.3)
        with self.legacy:
            self.legacy.executemany("INSERT INTO sessions VALUES (?,?,?)", [
                ("first", "Conversation préexistante", "2025-12-24T12:00:00Z"),
                ("second", "Autre conversation", "2025-12-25T12:00:00Z"),
            ])
            self.legacy.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?)", [
                (7, "first", "user", "Bonjour été", "", "complete", "2025-12-24T12:00:00Z"),
                (8, "first", "assistant", "Réponse partielle", "existing-abliterated", "streaming", "2025-12-24T12:00:01Z"),
                (9, "second", "user", "Conservé", "", "complete", "2025-12-25T12:00:00Z"),
                (10, "second", "assistant", "Oui", "existing-abliterated", "complete", "2025-12-25T12:00:01Z"),
            ])
            self.legacy.executemany("INSERT INTO settings VALUES (?,?)", [
                ("profile", json.dumps(self.settings.to_dict(), ensure_ascii=False)),
                ("legacy-note", "Ne pas modifier"),
            ])
        self.original = {table: self.legacy.execute("SELECT * FROM " + table).fetchall()
                         for table in ("sessions", "messages", "settings")}

    def test_real_v1_migration_backup_and_reopen_are_lossless(self):
        # Leave the v1 connection open: backup must include committed WAL data.
        store = Store(self.path)
        self.addCleanup(store.close)
        backup_path = store.migration_backup
        self.assertTrue(backup_path.is_file())
        backup = sqlite3.connect(backup_path)
        try:
            self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            for table, rows in self.original.items():
                self.assertEqual(backup.execute("SELECT * FROM " + table).fetchall(), rows)
        finally:
            backup.close()

        self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(store.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        for table in ("sessions", "settings"):
            self.assertEqual([tuple(row) for row in store.db.execute("SELECT * FROM " + table)], self.original[table])
        migrated = [tuple(row) for row in store.db.execute("SELECT id,session_id,role,content,model,status,created FROM messages")]
        expected = [row[:5] + (("interrupted",) if row[5] == "streaming" else (row[5],)) + row[6:]
                    for row in self.original["messages"]]
        self.assertEqual(migrated, expected)
        for sid in ("first", "second"):
            for message in store.messages(sid):
                self.assertEqual(message["source"], "text")
                self.assertEqual(message["metadata"], "{}")
        self.assertEqual(store.settings(), self.settings)
        store.set_preference("voice", {"selected": "tom"})
        store.close()
        reopened = Store(self.path)
        self.addCleanup(reopened.close)
        self.assertIsNone(reopened.migration_backup)
        self.assertEqual(reopened.get_preference("voice"), {"selected": "tom"})
        self.assertEqual(reopened.settings(), self.settings)
        self.assertEqual(reopened.messages("first")[1]["status"], "interrupted")
        self.assertEqual(len(list(self.path.parent.glob("*.v1-backup*.sqlite3"))), 1)

    def test_existing_backup_is_never_overwritten(self):
        previous = Path(str(self.path) + ".v1-backup.sqlite3")
        previous.write_bytes(b"existing user backup")
        store = Store(self.path)
        self.addCleanup(store.close)
        self.assertEqual(previous.read_bytes(), b"existing user backup")
        self.assertNotEqual(store.migration_backup, previous)
        self.assertTrue(store.migration_backup.is_file())

    def test_failed_migration_rolls_back_columns_version_and_recovery(self):
        original_connect = sqlite3.connect

        class FailSecondAlter(sqlite3.Connection):
            def execute(self, statement, parameters=()):
                if statement.startswith("ALTER TABLE messages ADD COLUMN metadata"):
                    raise sqlite3.OperationalError("injected migration failure")
                return super().execute(statement, parameters)

        def connect(*args, **kwargs):
            return original_connect(*args, factory=FailSecondAlter, **kwargs)

        with patch("jarvis.storage.sqlite3.connect", side_effect=connect):
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected"):
                Store(self.path)
        self.assertEqual(self.legacy.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertNotIn("source", [row[1] for row in self.legacy.execute("PRAGMA table_info(messages)")])
        for table, rows in self.original.items():
            self.assertEqual(self.legacy.execute("SELECT * FROM " + table).fetchall(), rows)
        self.assertTrue(Path(str(self.path) + ".v1-backup.sqlite3").is_file())

    def test_newer_version_refused_without_changing_data(self):
        self.legacy.execute("PRAGMA user_version=3")
        with self.assertRaisesRegex(ValueError, "récente"):
            Store(self.path)
        self.assertEqual(self.legacy.execute("PRAGMA user_version").fetchone()[0], 3)
        for table, rows in self.original.items():
            self.assertEqual(self.legacy.execute("SELECT * FROM " + table).fetchall(), rows)
        self.assertEqual(list(self.path.parent.glob("*.v1-backup*.sqlite3")), [])


if __name__ == "__main__":
    unittest.main()
