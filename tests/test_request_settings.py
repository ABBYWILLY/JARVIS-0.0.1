"""Generation policy persistence without model downloads or schema changes."""
import json
import tempfile
import unittest
from pathlib import Path

from jarvis.config import Settings
from jarvis.storage import Store


class RequestSettingsTests(unittest.TestCase):
    def test_default_fast_and_independent_budgets(self):
        settings = Settings(context=16384)
        self.assertEqual(settings.reasoning_mode, "fast")
        self.assertEqual(settings.for_request().max_tokens, 1024)
        self.assertEqual(settings.for_request("voice").max_tokens, 256)
        mission = Settings(context=16384, usage="mission", reasoning_mode="deep")
        self.assertEqual(mission.for_request().max_tokens, 4096)
        self.assertEqual(mission.for_request("voice").max_tokens, 256)
        self.assertEqual(mission.for_request("voice").reasoning_mode, "deep")
        self.assertEqual(mission.max_tokens, 1024)
        self.assertEqual(mission.usage, "mission")

    def test_mission_and_voice_reserve_at_most_half_context(self):
        for usage in ("voice", "mission"):
            with self.subTest(usage=usage):
                settings = Settings(context=1024, max_tokens=256, usage=usage,
                                    voice_tokens=2000, mission_tokens=8000)
                self.assertEqual(settings.for_request().max_tokens, 512)

    def test_policy_validation(self):
        for values in ({"reasoning_mode": "yes"}, {"usage": "agent"},
                       {"voice_tokens": True}, {"mission_tokens": 0},
                       {"voice_tokens": 65537}, {"mission_tokens": "100"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Settings(**values).validate()

    def test_old_and_new_profiles_survive_reopen_without_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            store = Store(path)
            sid = store.new_session()
            mid = store.begin_turn(sid, "Bonjour", "qwen3.5:4b")
            store.update_response(mid, "Salut", "complete")
            with store.db:
                store.db.execute("INSERT INTO settings VALUES ('profile', ?)",
                                 (json.dumps({"model": "qwen3.5:4b"}),))
            self.assertEqual(store.settings().reasoning_mode, "fast")
            custom = Settings(reasoning_mode="deep", usage="mission", voice_tokens=384,
                              mission_tokens=6000)
            store.save_settings(custom)
            store.close()
            store = Store(path)
            try:
                self.assertEqual(store.settings(), custom)
                self.assertEqual(store.messages(sid)[1]["content"], "Salut")
                self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], 2)
            finally:
                store.close()
