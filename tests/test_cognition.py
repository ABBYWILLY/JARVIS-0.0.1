"""Local generation policy contracts; no model, network or confidence score."""
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from jarvis.cognition import route_request
from jarvis.config import Settings
from jarvis.storage import Store, SCHEMA_VERSION


class CognitivePolicyTests(unittest.TestCase):
    def test_manual_profiles_preserve_every_reasoning_mode_temperature_and_budget(self):
        for mode, effective in (("fast", "fast"), ("deep", "deep"), ("auto", "model_default")):
            with self.subTest(mode=mode):
                original = Settings(reasoning_mode=mode, temperature=.25, max_tokens=700)
                request, metadata = route_request(original, "Raconte une histoire et analyse les risques.")
                self.assertEqual(request, original.for_request())
                self.assertEqual(metadata["mode"], effective)
                self.assertEqual(metadata["origin"], "manual")
                self.assertEqual(metadata["budget"], 700)
                self.assertEqual(metadata["temperature"], .25)

    def test_automatic_modes_use_explicit_local_requests_and_leave_profile_unchanged(self):
        original = Settings(cognitive_mode="auto", reasoning_mode="auto", temperature=.3)
        for text, mode, reasoning in (
            ("Bonjour, combien font 2 + 2 ?", "fast", "fast"),
            ("Raconte une histoire sur Éole et son équipage.", "creative", "fast"),
            ("Écris un poème sur l’été.", "creative", "fast"),
            ("Analyse en profondeur les compromis de cette architecture.", "deep", "deep"),
            ("Démontre le théorème de Pythagore.", "deep", "deep"),
            ("Compare ces solutions selon leurs risques.", "deep", "deep")):
            with self.subTest(text=text):
                request, metadata = route_request(original, text)
                self.assertEqual(metadata["mode"], mode)
                self.assertEqual(request.reasoning_mode, reasoning)
                self.assertEqual(metadata["origin"], "local_heuristic")
                self.assertTrue(metadata["reason"])
                self.assertNotIn("confidence", metadata)
                json.dumps(metadata, allow_nan=False)
        self.assertEqual(original.reasoning_mode, "auto")
        self.assertEqual(original.temperature, .3)

    def test_length_quotes_negations_and_bare_keywords_do_not_trigger_deep_or_creative(self):
        for text in ("Bonjour " * 2000, "Que signifie le mot analyse ?", "Compare Paris et Lyon.",
                     'Explique la phrase « raconte une histoire ». ',
                     "Que signifie 'raconte une histoire' ?",
                     "Explique la phrase ‘raconte l’histoire d’Éole’.",
                     'Explique la phrase “analyse en profondeur les risques”.',
                     'Explique le code `analyse en profondeur`.',
                     "Ne raconte pas d’histoire, réponds simplement.",
                     "Ne raconte aucune histoire, donne seulement la date.",
                     "Ne raconte rien sur cette histoire, donne seulement la date.",
                     "N’analyse pas les risques, donne seulement la date."):
            with self.subTest(text=text[:80]):
                _, metadata = route_request(Settings(cognitive_mode="auto"), text)
                self.assertEqual(metadata["mode"], "fast")

    def test_quotes_and_negation_keep_other_explicit_requests_eligible(self):
        for text, expected in (
                ("Raconte l'histoire d'Éole.", "creative"),
                ("Ne raconte aucune histoire. Analyse en profondeur les risques.", "deep"),
                ("Explique ‘analyse les risques’. Raconte une histoire.", "creative")):
            with self.subTest(text=text):
                _, metadata = route_request(Settings(cognitive_mode="auto"), text)
                self.assertEqual(metadata["mode"], expected)

    def test_explicit_policy_overrides_heuristics_and_creative_is_only_a_generation_policy(self):
        for mode in ("fast", "deep", "creative"):
            request, metadata = route_request(Settings(cognitive_mode=mode, temperature=.2), "Bonjour")
            self.assertEqual(metadata["mode"], mode)
            self.assertEqual(metadata["origin"], "manual")
            self.assertEqual(request.reasoning_mode, "deep" if mode == "deep" else "fast")
            self.assertEqual(request.temperature, .9 if mode == "creative" else .2)
        request, _ = route_request(Settings(cognitive_mode="creative", temperature=1.5), "Histoire")
        self.assertEqual(request.temperature, 1.5)

    def test_voice_and_mission_budget_caps_remain_independent_of_policy(self):
        original = Settings(cognitive_mode="auto", context=4096, max_tokens=900,
                            voice_tokens=180, mission_tokens=4000, usage="mission")
        for source, expected in (("voice", 180), ("text", 2048)):
            request, metadata = route_request(original, "Analyse en profondeur les risques.", source)
            self.assertEqual(request.max_tokens, expected)
            self.assertEqual(metadata["budget"], expected)
        self.assertEqual(original.max_tokens, 900)
        self.assertEqual(original.voice_tokens, 180)

    def test_continuation_flag_does_not_replace_the_original_prompt_for_routing(self):
        request, metadata = route_request(Settings(cognitive_mode="auto"), "Raconte une histoire.", continuation=True)
        self.assertTrue(metadata["continuation"])
        self.assertEqual(metadata["mode"], "creative")
        self.assertEqual(request.reasoning_mode, "fast")

    def test_cognitive_preferences_persist_without_database_migration_or_archive_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cognitive.sqlite3"
            store = Store(path)
            try:
                sid = store.new_session()
                mid = store.begin_turn(sid, "Question", "local")
                store.update_response(mid, "Réponse originale 😊", "complete")
                old = {"model": "local", "reasoning_mode": "auto"}
                with store.db:
                    store.db.execute("INSERT INTO settings VALUES ('profile', ?)", (json.dumps(old),))
                self.assertEqual(store.settings().cognitive_mode, "manual")
                chosen = replace(store.settings(), cognitive_mode="creative")
                store.save_settings(chosen)
            finally:
                store.close()
            store = Store(path)
            try:
                self.assertEqual(store.settings(), chosen)
                self.assertEqual(store.message(mid)["content"], "Réponse originale 😊")
                self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            finally:
                store.close()

    def test_invalid_policy_or_text_is_rejected(self):
        for mode in (None, True, "cloud", "mission"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                Settings(cognitive_mode=mode).validate()
        with self.assertRaises(ValueError):
            route_request(Settings(), None)


if __name__ == "__main__":
    unittest.main()
