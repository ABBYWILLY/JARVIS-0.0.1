"""Prepared/retrieved/referenced distinctions, without a DB/model/renderer."""
import copy
import json
import unittest
from types import SimpleNamespace

from jarvis.provenance import context_observations, inspect_provenance, MAX_SYSTEM_CHARACTERS


def memory(mid=3, content="Mon projet Atlas emploie SQLite."):
    return {"id": mid, "content": content, "status": "approved", "kind": "durable",
            "title": "Atlas", "created": "2026-10-29T10:00:00Z", "updated": "2026-10-29T10:00:00Z"}


def source(item):
    return {"memory_id": item["id"], "method": "memory", "status": item["status"],
            "created": item["created"], "excerpt": item["content"], "provenance": {"source": "explicit_user"}}


def metadata(candidates=None, included=None, systems=None, **stats):
    candidates = [memory()] if candidates is None else candidates
    included = candidates[:1] if included is None else included
    context = SimpleNamespace(messages=systems if systems is not None else [
        {"role": "system", "content": "Instruction effective française."},
        {"role": "user", "content": "Quel projet ?"}], sources=[source(item) for item in included])
    return {"context": {"sources": context.sources, **stats,
                        **context_observations(context, candidates, prepared_ms=1.25)}}


class ProvenanceTests(unittest.TestCase):
    def test_search_candidates_and_actually_included_sources_are_distinct(self):
        first, second = memory(3), memory(4, "Autre souvenir retrouvé mais hors budget.")
        record = metadata([first, second], included=[first])
        report = inspect_provenance(record)
        self.assertTrue(report["retrieval_observed"])
        self.assertEqual([item["included"] for item in report["retrieved"]], [True, False])
        self.assertEqual([item["memory_id"] for item in report["included"]], [3])
        self.assertEqual(report["cited"], [])
        self.assertIn("l’inclusion ne prouve pas l’utilisation", report["summary"])

    def test_real_empty_search_differs_from_unrecorded_legacy_or_no_search(self):
        report = inspect_provenance(metadata(candidates=[]))
        self.assertTrue(report["retrieval_observed"])
        self.assertIn("recherche : 0", report["summary"])
        context = SimpleNamespace(messages=[], sources=[])
        for record in ({}, {"context": {"sources": []}},
                       {"context": context_observations(context, retrieved_memories=None)}):
            with self.subTest(record=record):
                report = inspect_provenance(record)
                self.assertFalse(report["retrieval_observed"])
                self.assertIn("Recherche mémoire non enregistrée", report["summary"])

    def test_current_settings_never_replace_effective_archived_instructions(self):
        instructions = "Tu es JARVIS, réponds en français et cite les incertitudes."
        context = SimpleNamespace(messages=[{"role": "system", "content": instructions}], sources=[])
        captured = context_observations(context, [])
        context.messages[0]["content"] = "Autre instruction actuelle."
        record = {"context": captured}
        report = inspect_provenance(record)
        self.assertEqual(report["system_instructions"], [{"role": "system", "content": instructions}])
        self.assertEqual(len(report["instructions_sha256"]), 64)
        self.assertNotEqual(report["instructions_sha256"], context_observations(context, [])["system_instructions_sha256"])
        self.assertNotIn("Autre instruction", report["summary"])

    def test_no_system_message_is_observed_empty_not_unknown(self):
        report = inspect_provenance(metadata(systems=[{"role": "user", "content": "Question"}]))
        self.assertTrue(report["instructions_available"])
        self.assertEqual(report["system_instructions"], [])
        legacy = inspect_provenance({"context": {"sources": []}})
        self.assertFalse(legacy["instructions_available"])
        self.assertIn("réglages actuels ne les reconstituent pas", legacy["summary"])

    def test_capture_is_bounded_and_marks_truncated_instruction(self):
        context = SimpleNamespace(messages=[{"role": "system", "content": "x" * (MAX_SYSTEM_CHARACTERS + 10)}], sources=[])
        result = context_observations(context, [memory(i) for i in range(1, 12)])
        self.assertEqual(len(result["retrieved_memory_candidates"]), 5)
        self.assertTrue(result["system_instructions_truncated"])
        self.assertEqual(len(result["system_instructions"][0]["content"]), MAX_SYSTEM_CHARACTERS)
        self.assertIn("Capture des instructions incomplète", inspect_provenance({"context": result})["summary"])
        self.assertNotIn("content", result["retrieved_memory_candidates"][0])

    def test_formal_reference_must_match_an_included_known_memory(self):
        record = metadata([memory(3), memory(4)], included=[memory(3)])
        report = inspect_provenance(record, response_text="Atlas [mémoire #3]. Puis [souvenir #4] et [mémoire #999].")
        self.assertEqual([item["memory_id"] for item in report["cited"]], [3])
        self.assertEqual([item["memory_id"] for item in report["unknown_references"]], [4, 999])
        self.assertEqual(report["cited"][0]["kind"], "explicit_text_reference")
        self.assertIn("utilisation", report["usage_note"])

    def test_overlap_ids_and_code_examples_never_invent_a_reference(self):
        record = metadata()
        for text in ("Mon projet Atlas emploie SQLite.", "Le numéro 3 est utile.",
                     "`[mémoire #3]`", "```text\n[mémoire #3]\n```", "~~~\n[souvenir #3]\n~~~",
                     "[mémoire #3](https://example.org)".replace("mémoire", "projet")):
            with self.subTest(text=text):
                self.assertEqual(inspect_provenance(record, response_text=text)["cited"], [])

    def test_memory_edits_deletion_and_reused_id_preserve_original_inclusion(self):
        original = memory()
        record = metadata([original])
        cases = [({}, "missing"), ({3: original}, "unchanged"),
                 ({3: {**original, "content": "Une autre version."}}, "modified"),
                 ({3: {**original, "status": "disabled"}}, "status_changed"),
                 ({3: {**original, "created": "2027-01-01T00:00:00Z"}}, "identity_mismatch")]
        for current, expected in cases:
            with self.subTest(condition=expected):
                report = inspect_provenance(record, memory_current=current)
                self.assertEqual(report["included"][0]["current_condition"], expected)
                self.assertEqual(report["included"][0]["excerpt"], original["content"])
                self.assertEqual(report["included"][0]["status"], "approved")
        self.assertEqual(inspect_provenance(record)["included"][0]["current_condition"], "not_checked")

    def test_old_memory_source_without_digest_is_not_asserted_unchanged(self):
        item = memory()
        record = {"context": {"sources": [source(item)]}}
        report = inspect_provenance(record, memory_current={3: item})
        self.assertEqual(report["included"][0]["current_condition"], "unverified")

    def test_http_acceptance_is_observed_separately_from_prepared_context(self):
        record = metadata()
        prepared = inspect_provenance(record)
        self.assertEqual(prepared["delivery"], "prepared")
        self.assertIn("acceptation HTTP par Ollama non observée", prepared["summary"])
        record["context"]["delivery"] = "accepted"
        accepted = inspect_provenance(record)
        self.assertIn("acceptée par Ollama (HTTP)", accepted["summary"])
        self.assertIn("utilisation de chaque source non démontrée", accepted["summary"])
        self.assertEqual(accepted["cited"], [])
        self.assertEqual(inspect_provenance({})["delivery"], "unknown")

    def test_observations_do_not_mutate_sources_or_include_unrelated_message_text(self):
        candidate = memory()
        context = SimpleNamespace(messages=[{"role": "user", "content": "Secret conversation à ne pas dupliquer"}], sources=[source(candidate)])
        before = copy.deepcopy((context.messages, context.sources, candidate))
        observation = context_observations(context, [candidate], 1.234567)
        self.assertEqual((context.messages, context.sources, candidate), before)
        self.assertEqual(observation["preparation_ms"], 1.235)
        self.assertNotIn("Secret conversation", json.dumps(observation, ensure_ascii=False))
        self.assertNotIn(candidate["content"], json.dumps(observation, ensure_ascii=False))
        encoded = json.dumps({"context": {**observation, "sources": context.sources}}, ensure_ascii=False)
        self.assertEqual(inspect_provenance(encoded)["included"][0]["memory_id"], 3)

    def test_missing_and_malformed_legacy_provenance_does_not_fabricate_information(self):
        for value in (None, "broken JSON", [], {"context": "bad"},
                      {"context": {"delivery": [], "sources": "bad", "retrieved_memory_candidates": None}}):
            with self.subTest(value=value):
                report = inspect_provenance(value)
                self.assertEqual(report["cited"], [])
                self.assertFalse(report["instructions_available"])
                json.dumps(report, allow_nan=False)

    def test_budget_omissions_and_missing_timings_are_presented_as_such(self):
        record = metadata(omitted_messages=9)
        report = inspect_provenance(record)
        self.assertIn("9 messages hors contexte", report["summary"])
        context = SimpleNamespace(messages=[], sources=[])
        for timing in (None, -1, float("nan"), float("inf"), True):
            with self.subTest(timing=timing):
                self.assertNotIn("preparation_ms", context_observations(context, [], timing))


if __name__ == "__main__":
    unittest.main()
