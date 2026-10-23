"""Continuation preserves the original request and its inspectable local source."""
import copy
import json
import sqlite3
import unittest
from contextlib import closing

from jarvis.cognition import CONTINUE_PROMPT, build_continuation, continuation_origin
from jarvis.config import Settings


def record(mid, role, content, status="complete", continuation=None):
    metadata = ({"continuation": {"target_message_id": continuation}}
                if continuation is not None else {})
    return {"id": mid, "session_id": "mission", "role": role, "content": content,
            "status": status, "created": f"2026-10-23T12:{mid:02d}:00Z",
            "metadata": json.dumps(metadata)}


def chain(hops):
    records = [record(1, "user", "Rédige le récit de la mission Éole, avec Alix et Nadir."),
               record(2, "assistant", "Alix et Nadir ouvrent le sas de la station Éole.")]
    for index in range(hops):
        previous = records[-1]["id"]
        records += [record(previous + 1, "user", CONTINUE_PROMPT),
                    record(previous + 2, "assistant",
                           f"Segment {index + 1} : la mission atteint le relais Boréal.",
                           continuation=previous)]
    return records


class CognitiveContinuationTests(unittest.TestCase):
    def build(self, records, target=None, **settings):
        result = build_continuation(Settings(**settings), records,
                                    records[-1] if target is None else target)
        estimate = 256 + sum(len(message["content"].encode("utf-8")) + 32
                             for message in result.messages)
        self.assertEqual(result.stats["context_estimate_tokens"], estimate)
        self.assertLessEqual(estimate + result.stats["output_reserved_tokens"],
                             result.stats["context_limit_tokens"])
        self.assertTrue(all(set(message) == {"role", "content"}
                            for message in result.messages))
        self.assertEqual(result.messages[-1], {"role": "user", "content": CONTINUE_PROMPT})
        json.dumps(result.stats, allow_nan=False)
        json.dumps(result.sources, allow_nan=False)
        return result

    def test_original_request_and_selected_response_are_pinned_with_real_provenance(self):
        for status in ("complete", "cancelled", "interrupted", "error"):
            with self.subTest(status=status):
                records = chain(0)
                records[-1]["status"] = status
                original = copy.deepcopy(records)
                result = self.build(records, system_prompt="Écris en français.")
                self.assertEqual(records, original)
                self.assertEqual(result.messages[0],
                                 {"role": "system", "content": "Écris en français."})
                self.assertIn({"role": "user", "content": records[0]["content"]},
                              result.messages)
                self.assertIn({"role": "assistant", "content": records[1]["content"]},
                              result.messages)
                provenance = result.stats["continuation"]
                self.assertEqual(provenance["target_message_id"], 2)
                self.assertEqual(provenance["source_user_id"], 1)
                self.assertFalse(provenance["excerpted"])
                self.assertIn("limitations", provenance)
                sources = [source for source in result.sources
                           if source["method"] == "continuation_original"]
                self.assertEqual({source["message_id"] for source in sources}, {1, 2})
                self.assertTrue(all(source["session_id"] == "mission" for source in sources))

    def test_one_and_two_hop_chains_resolve_sqlite_rows_to_the_original_request(self):
        for hops in (1, 2):
            with self.subTest(hops=hops):
                records = chain(hops)
                with closing(sqlite3.connect(":memory:")) as database:
                    database.row_factory = sqlite3.Row
                    database.execute("CREATE TABLE messages (id, session_id, role, content, "
                                     "status, created, metadata)")
                    database.executemany("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                                         [tuple(item.values()) for item in records])
                    rows = database.execute("SELECT * FROM messages ORDER BY id").fetchall()
                original = [dict(row) for row in rows]
                self.assertEqual(continuation_origin(rows, rows[-1])["id"], 1)
                result = self.build(rows, context=8192, max_tokens=512)
                self.assertEqual([dict(row) for row in rows], original)
                prompt = "\n".join(message["content"] for message in result.messages)
                for item in (records[0], records[1], records[-1]):
                    self.assertIn(item["content"], prompt)
                self.assertIn("Alix et Nadir ouvrent le sas", prompt)
                self.assertEqual(result.stats["continuation"]["source_user_id"], 1)
                self.assertEqual(result.stats["continuation"]["target_message_id"],
                                 rows[-1]["id"])
                self.assertTrue({1, 2, rows[-1]["id"]}.issubset(
                    {source["message_id"] for source in result.sources
                     if source["method"].startswith("continuation_")}))

    def test_oversized_originals_keep_labeled_beginning_and_ending_within_utf8_budget(self):
        request = "REQUÊTE Éole : conserver les noms. " + "détail médian 🚀 " * 700 + "FIN REQUÊTE : ton sobre."
        answer = "DÉBUT RÉPONSE : Alix trouve le sas. " + "passage médian 🌙 " * 900 + "FIN RÉPONSE : Nadir garde la clé."
        records = [record(1, "user", request), record(2, "assistant", answer, "interrupted")]
        original = copy.deepcopy(records)
        result = self.build(records, context=2048, max_tokens=512)
        self.assertEqual(records, original)
        prompt = "\n".join(message["content"] for message in result.messages)
        for fragment in ("REQUÊTE Éole", "ton sobre.", "Alix trouve le sas.", "Nadir garde la clé."):
            self.assertIn(fragment, prompt)
        self.assertNotIn(request, prompt)
        self.assertNotIn(answer, prompt)
        self.assertRegex(prompt.casefold(), r"extrait|extract|tronqu|omission|début|debut|partiel")
        provenance = result.stats["continuation"]
        self.assertTrue(provenance["excerpted"])
        self.assertTrue(provenance["limitations"])
        extracts = [source for source in result.sources
                    if source["method"] == "continuation_extract"]
        self.assertEqual({source["message_id"] for source in extracts}, {1, 2})
        self.assertIn("Nadir garde la clé.", next(source["excerpt"] for source in extracts if source["message_id"] == 2))

    def test_intermediate_story_events_are_retained_when_the_context_can_fit_them(self):
        records = chain(2)
        records[3]["content"] = "Nadir confie la clé bleue à Alix ; leur objectif devient le phare lunaire."
        result = self.build(records, context=8192, max_tokens=512)
        prompt = "\n".join(message["content"] for message in result.messages)
        self.assertIn(records[3]["content"], prompt)
        self.assertTrue({2, 4, 6}.issubset({source["message_id"] for source in result.sources}))
        self.assertFalse(result.stats["continuation"]["excerpted"])

    def test_other_incomplete_assistants_do_not_become_continuation_context(self):
        records = []
        for index, status in enumerate(("cancelled", "interrupted", "error", "streaming")):
            records += [record(index * 2 + 1, "user", f"Ancienne demande {index}."),
                        record(index * 2 + 2, "assistant", f"PARTIEL À EXCLURE {index}", status)]
        records += [record(9, "user", "Décris la mission Éole avec Alix."),
                    record(10, "assistant", "Alix rejoint le pont de la station Éole.")]
        result = self.build(records, context=8192, max_tokens=512)
        prompt = "\n".join(message["content"] for message in result.messages)
        self.assertNotIn("PARTIEL À EXCLURE", prompt)
        self.assertFalse({2, 4, 6, 8}.intersection(
            source["message_id"] for source in result.sources))
        self.assertIn(records[8]["content"], prompt)
        self.assertIn(records[9]["content"], prompt)

    def test_invalid_missing_stale_or_nonlatest_targets_are_rejected(self):
        records = chain(1)
        missing = record(999, "assistant", "Réponse absente des archives.")
        stale = dict(records[-1], content="Copie obsolète de la réponse.")
        streaming = copy.deepcopy(records)
        streaming[-1]["status"] = "streaming"
        empty = copy.deepcopy(records)
        empty[-1]["content"] = "  \n"
        cases = [(records, missing), (records, stale), (records, records[1]),
                 (records, records[0]), (streaming, streaming[-1]), (empty, empty[-1])]
        for archive, target in cases:
            with self.subTest(target=target), self.assertRaises(ValueError) as error:
                build_continuation(Settings(), archive, target)
            self.assertTrue(str(error.exception))

    def test_missing_links_cycles_and_excessive_depth_fail_explicitly(self):
        missing = chain(1)
        missing[-1]["metadata"] = json.dumps({"continuation": {"target_message_id": 999}})
        cycle = chain(1)
        cycle[1]["metadata"] = json.dumps({"continuation": {"target_message_id": 4}})
        for records in (missing, cycle, chain(20)):
            with self.subTest(records=len(records)), self.assertRaises(ValueError) as error:
                continuation_origin(records, records[-1])
            self.assertTrue(str(error.exception))

    def test_insufficient_budget_rejects_instead_of_dropping_pinned_sources(self):
        records = chain(0)
        original = copy.deepcopy(records)
        with self.assertRaises(ValueError) as error:
            build_continuation(Settings(context=512, max_tokens=256,
                                        system_prompt="Instruction obligatoire. " * 8),
                               records, records[-1])
        self.assertTrue(str(error.exception))
        self.assertEqual(records, original)


if __name__ == "__main__":
    unittest.main()
