"""Observable state contracts: pure events, no model, device or graphics."""
import json
import unittest
from dataclasses import FrozenInstanceError, replace

from jarvis.cognitive_state import CognitiveHudSettings, CognitiveState, summary


class CognitiveStateTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.
        self.state = CognitiveState(clock=lambda: self.now)

    def test_concurrent_activities_have_one_deterministic_primary(self):
        self.state.update("listening")
        self.state.begin(21, 1, model="qwen:4b", policy="fast", budget=800)
        for activity in ("context", "waiting", "generating", "synthesis", "speaking"):
            self.now += .1
            self.assertTrue(self.state.update(activity, generation=1, turn_id=21))
            self.assertEqual(self.state.snapshot()["primary"], activity)
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot["activities"],
                         ("speaking", "synthesis", "generating", "waiting", "context", "listening"))
        self.state.update("speaking", False)
        self.assertEqual(self.state.snapshot()["primary"], "synthesis")

    def test_stale_generations_turns_and_boolean_ids_do_not_change_state(self):
        self.state.begin(42, 5)
        self.state.update("generating", generation=5)
        before = self.state.snapshot()
        for kwargs in ({"generation": 4}, {"generation": 6}, {"generation": True},
                       {"turn_id": 41}, {"turn_id": "42"}):
            self.assertFalse(self.state.update("error", **kwargs))
            self.assertFalse(self.state.observe_metrics({"eval_count": 2}, **kwargs))
        self.assertEqual(self.state.snapshot(), before)
        self.state.begin(41, 4, model="old")
        self.state.begin(999, 5, model="same-generation-wrong-turn")
        self.assertEqual(self.state.snapshot(), before)

    def test_terminal_events_clear_work_and_survive_duplicate_listening(self):
        self.state.update("listening")
        self.state.begin(21, 1)
        self.state.update("speaking")
        self.state.update("cancelled")
        self.assertEqual(self.state.snapshot()["activities"], ("listening",))
        for _ in range(10):
            self.assertFalse(self.state.update("listening"))
        self.assertEqual(self.state.snapshot()["primary"], "cancelled")
        self.state.update("user_speaking")
        self.assertEqual(self.state.snapshot()["primary"], "user_speaking")
        self.state.update("interrupted")
        self.assertTrue(self.state.snapshot()["interrupted"])
        self.state.begin(22, 2)
        self.assertEqual(self.state.snapshot()["primary"], "listening")
        self.assertFalse(self.state.snapshot()["interrupted"])

    def test_loading_audio_never_claims_a_microphone_is_already_listening(self):
        self.state.update("audio_loading")
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot["primary"], "audio_loading")
        self.assertNotIn("listening", snapshot["activities"])
        self.assertEqual(summary(snapshot), "Chargement audio local")
        self.state.update("audio_loading", False)
        self.state.update("listening")
        self.assertEqual(self.state.snapshot()["primary"], "listening")

    def test_idle_and_terminal_clear_are_explicit_and_idempotent(self):
        self.assertFalse(self.state.update("idle"))
        self.assertFalse(self.state.update("error", False))
        self.state.update("listening")
        self.state.update("error", detail="stt_error")
        self.assertTrue(self.state.update("error", False))
        self.assertEqual(self.state.snapshot()["primary"], "listening")
        self.assertTrue(self.state.update("idle"))
        self.assertEqual(self.state.snapshot()["primary"], "idle")
        self.assertFalse(self.state.update("idle"))

    def test_metrics_keep_real_numbers_and_never_estimate_missing_tokens(self):
        self.state.begin(1, 1)
        self.assertTrue(self.state.observe_metrics({"ttft_seconds": .12,
            "eval_count": 12, "eval_duration": 2_000_000_000, "stt_ms": 125.5,
            "context_ms": -1, "piper_ms": float("nan"), "made_up_progress": 99,
            "audio_start_estimate_ms": 35}))
        metrics = self.state.snapshot()["metrics"]
        self.assertEqual(metrics["tokens_per_second"], 6)
        self.assertEqual(metrics["stt_ms"], 125.5)
        self.assertEqual(metrics["audio_start_estimate_ms"], 35.)
        for field in ("context_ms", "piper_ms", "made_up_progress", "response_tokens"):
            self.assertNotIn(field, metrics)
        revision = self.state.revision
        self.assertFalse(self.state.observe_metrics({"stt_ms": 125.5}))
        self.assertFalse(self.state.observe_metrics({"stt_ms": 2}, generation=0))
        self.assertEqual(self.state.revision, revision)

    def test_history_is_bounded_expires_and_contains_no_source_or_error_content(self):
        sensitive = "Mon souvenir personnel C:\\Users\\Alice\\secret.txt"
        self.state.begin(1, 1, sources=[{"excerpt": sensitive, "system_prompt": sensitive}])
        for index in range(100):
            self.now += .1
            self.state.update("listening", bool(index % 2), detail=sensitive)
        self.state.update("error", detail=sensitive)
        events = self.state.events()
        self.assertEqual(len(events), self.state.HISTORY_LIMIT)
        self.assertNotIn(sensitive, json.dumps(events))
        self.assertNotIn("secret", json.dumps(self.state.snapshot()))
        self.assertEqual(self.state.snapshot()["source_count"], 1)
        self.assertEqual(self.state.snapshot()["error"], "")
        self.now += 901
        self.assertEqual(self.state.events(), ())

    def test_snapshot_and_journal_copies_cannot_mutate_the_owner(self):
        self.state.begin(1, 1)
        self.state.update("context")
        self.state.observe_metrics({"stt_ms": 20})
        snapshot = self.state.snapshot()
        snapshot["metrics"]["stt_ms"] = 100
        snapshot["activity_started"].clear()
        self.state.events()[0]["activity"] = "fake"
        self.assertEqual(self.state.snapshot()["metrics"]["stt_ms"], 20.)
        self.assertIn("context", self.state.snapshot()["activity_started"])
        self.assertEqual(self.state.events()[0]["activity"], "begin")

    def test_begin_resets_metrics_and_work_but_preserves_actual_listening(self):
        self.state.update("listening")
        self.state.begin(1, 1, sources=[1, 2], budget=512)
        self.state.update("generating")
        self.state.observe_metrics({"eval_count": 12})
        self.now += 1
        snapshot = self.state.begin(2, 2, model="new", policy="creative", sources=[3])
        self.assertEqual(snapshot["metrics"], {})
        self.assertEqual(snapshot["activities"], ("listening",))
        self.assertEqual(snapshot["source_count"], 1)
        self.assertEqual(snapshot["model"], "new")
        self.assertEqual(snapshot["started_at"], self.now)

    def test_timestamps_remain_monotone_and_invalid_inputs_are_rejected(self):
        self.state.update("context", now=20.)
        self.state.update("waiting", now=19.)
        self.assertEqual(self.state.snapshot()["changed_at"], 20.)
        for value in (float("nan"), float("inf"), -1, True):
            with self.subTest(now=value), self.assertRaises(ValueError):
                self.state.snapshot(now=value)
        for activity, active in (("intelligence", True), ("speaking", 1), ([], True)):
            with self.assertRaises(ValueError):
                self.state.update(activity, active)
        for turn, generation in ((True, 1), ("text with private content", 1), (1, True), (1, -1)):
            with self.assertRaises(ValueError):
                self.state.begin(turn, generation)


class CognitiveHudProjectionTests(unittest.TestCase):
    def test_preferences_use_exact_booleans_safe_defaults_and_immutable_values(self):
        defaults = CognitiveHudSettings()
        self.assertEqual(CognitiveHudSettings.from_dict(None), defaults)
        self.assertEqual(CognitiveHudSettings.from_dict({"enabled": 0, "level": "unbounded",
            "show_actions": "false", "future": 1}), defaults)
        self.assertEqual(CognitiveHudSettings.from_dict({"level": []}), defaults)
        options = replace(defaults, enabled=False, level="diagnostic", show_provenance=True)
        self.assertEqual(CognitiveHudSettings.from_dict(options.to_dict()), options)
        with self.assertRaises(FrozenInstanceError):
            options.enabled = True

    def test_levels_and_disabled_state_share_a_safe_summary(self):
        state = CognitiveState(clock=lambda: 10.)
        state.begin(1, 1, model="qwen:4b", policy="fast", budget=1000,
                    sources=[{"excerpt": "private"}])
        state.update("waiting")
        state.observe_metrics({"stt_ms": 42, "ttft_seconds": .12,
                               "eval_count": 8, "eval_duration": 1_000_000_000})
        snapshot = state.snapshot(now=10.5)
        self.assertEqual(summary(snapshot), "Attente d’Ollama")
        self.assertEqual(summary(snapshot, CognitiveHudSettings(enabled=False)), "")
        standard = summary(snapshot, CognitiveHudSettings(level="standard"))
        self.assertIn("qwen:4b", standard)
        self.assertIn("Rapide", standard)
        self.assertIn("1000 tokens", standard)
        self.assertIn("0.5 s", standard)
        self.assertNotIn("STT", standard)
        diagnostic = summary(snapshot, CognitiveHudSettings(level="diagnostic", show_provenance=True))
        self.assertIn("STT 42 ms", diagnostic)
        self.assertIn("TTFT reçu 120 ms", diagnostic)
        self.assertIn("8.0 tokens/s", diagnostic)
        self.assertIn("1 source(s) dans le contexte", diagnostic)
        self.assertNotIn("private", diagnostic)
        self.assertNotIn("utilisée", diagnostic)

    def test_display_flags_remove_only_their_values_and_no_progress_is_fabricated(self):
        state = CognitiveState(clock=lambda: 10.)
        state.begin(1, 1, model="qwen:4b", policy="fast", budget=1000)
        state.update("synthesis")
        text = summary(state.snapshot(now=11.), CognitiveHudSettings(level="standard",
            show_durations=False, show_model=False, show_policy=False))
        self.assertEqual(text, "Préparation de la voix")
        self.assertNotIn("%", text)

    def test_diagnostic_lists_observed_secondary_activities_without_inventing_thoughts(self):
        state = CognitiveState(clock=lambda: 1.)
        state.update("listening")
        state.update("generating")
        state.update("speaking")
        text = summary(state.snapshot(), CognitiveHudSettings(level="diagnostic"))
        self.assertIn("JARVIS parle", text)
        self.assertIn("Génération locale", text)
        self.assertIn("J’écoute", text)
        self.assertNotIn("réflexion", text)
