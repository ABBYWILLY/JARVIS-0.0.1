"""Read-only update checks use synthetic archives and never a user's profile."""
from contextlib import closing, redirect_stderr
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jarvis.storage import Store
from scripts.check_update_data import DATABASE, SNAPSHOT, main, seed, verify
from tests.test_jarvis import display_available

REPO = Path(__file__).resolve().parents[1]


class UpdateDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jarvis-update-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "fixture"

    def recover(self):
        store = Store(self.directory / DATABASE)
        store.close()

    def test_seed_refuses_existing_directory_without_opening_sqlite(self):
        self.directory.mkdir()
        original = self.directory / "user-file.txt"
        original.write_text("Préserver intégralement.", encoding="utf-8")
        with patch("jarvis.storage.Store", side_effect=AssertionError("must not open SQLite")):
            with self.assertRaises(FileExistsError):
                seed(self.directory)
        self.assertEqual(list(self.directory.iterdir()), [original])
        self.assertEqual(original.read_text(encoding="utf-8"), "Préserver intégralement.")

    def test_unrecovered_fragment_is_detected_without_mutating_the_database(self):
        seed(self.directory)
        before = (self.directory / DATABASE).read_bytes()
        with patch("jarvis.storage.Store", side_effect=AssertionError("read-only verifier must not recover")):
            with self.assertRaisesRegex(ValueError, "messages"):
                verify(self.directory)
        self.assertEqual((self.directory / DATABASE).read_bytes(), before)
        with closing(sqlite3.connect(self.directory / DATABASE)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM messages WHERE status='streaming'").fetchone()[0], 1)

    def test_recovery_preserves_all_tables_preferences_and_fts(self):
        seed(self.directory)
        self.recover()
        before = hashlib.sha256((self.directory / DATABASE).read_bytes()).hexdigest()
        snapshot = (self.directory / SNAPSHOT).read_bytes()
        report = verify(self.directory)
        self.assertEqual(report["status"], "preserved")
        self.assertEqual(report["streaming_fragment"], "recovered_as_interrupted")
        self.assertEqual(report["all_preferences_and_settings"], "unchanged")
        self.assertEqual(report["hardware_validation"], "not_performed")
        self.assertEqual(hashlib.sha256((self.directory / DATABASE).read_bytes()).hexdigest(), before)
        self.assertEqual((self.directory / SNAPSHOT).read_bytes(), snapshot)
        self.assertNotIn("épreuve", json.dumps(report, ensure_ascii=False))
        self.assertNotIn("12,50", json.dumps(report, ensure_ascii=False))

    def test_changes_to_each_persisted_family_are_rejected(self):
        changes = {
            "sessions": "UPDATE sessions SET title='changed'",
            "messages": "UPDATE messages SET metadata='{}'",
            "settings": "UPDATE settings SET value='{}'",
            "preferences": "DELETE FROM preferences WHERE key='future_fixture_preference'",
            "memories": "UPDATE memories SET status='disabled'",
        }
        for index, (table, sql) in enumerate(changes.items()):
            with self.subTest(table=table):
                self.directory = Path(self.temp.name) / str(index)
                seed(self.directory)
                self.recover()
                with closing(sqlite3.connect(self.directory / DATABASE)) as db:
                    with db:
                        db.execute(sql)
                with self.assertRaisesRegex(ValueError, table):
                    verify(self.directory)

    def test_lost_fts_fragment_is_detected_without_archive_changes(self):
        seed(self.directory)
        self.recover()
        expected = json.loads((self.directory / SNAPSHOT).read_text(encoding="utf-8"))
        if not expected["fts_available"]:
            self.skipTest("SQLite FTS5 unavailable")
        with closing(sqlite3.connect(self.directory / DATABASE)) as db:
            mid = expected["partial_id"]
            content = db.execute("SELECT content FROM messages WHERE id=?", (mid,)).fetchone()[0]
            with db:
                db.execute("INSERT INTO messages_fts(messages_fts,rowid,content) VALUES('delete',?,?)", (mid, content))
        with self.assertRaisesRegex(ValueError, "FTS"):
            verify(self.directory)

    def test_verification_never_creates_a_missing_database(self):
        seed(self.directory)
        (self.directory / DATABASE).unlink()
        with self.assertRaises(sqlite3.OperationalError):
            verify(self.directory)
        self.assertFalse((self.directory / DATABASE).exists())

    def test_existing_report_is_rejected_before_seeding_or_verification(self):
        report = Path(self.temp.name) / "report.json"
        report.write_text("original", encoding="utf-8")
        with patch("scripts.check_update_data.seed") as seeding, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(["seed", str(self.directory), "--report", str(report)])
        self.assertEqual(error.exception.code, 2)
        seeding.assert_not_called()
        self.assertFalse(self.directory.exists())
        self.assertEqual(report.read_text(encoding="utf-8"), "original")

    @unittest.skipUnless(display_available(), "Écran graphique indisponible")
    def test_two_actual_source_starts_preserve_same_existing_profile_and_exit(self):
        seed(self.directory)
        env = {**os.environ, "JARVIS_DATA_DIR": str(self.directory)}
        for attempt in range(2):
            with self.subTest(attempt=attempt + 1):
                result = subprocess.run([sys.executable, "run.py", "--smoke-test"],
                    cwd=REPO, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(verify(self.directory)["status"], "preserved")


if __name__ == "__main__":
    unittest.main()
