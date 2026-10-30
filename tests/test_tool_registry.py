"""Strict proposal/policy boundaries; no tools or resources are opened."""
import dataclasses
import json
import math
import subprocess
import sys
import unittest
from unittest.mock import patch

from jarvis.tool_registry import (MAX_ARGUMENT_BYTES, MAX_PROPOSAL_BYTES, MAX_RESULT_BYTES,
    REGISTRY, STATUSES, PermissionDecision, ToolProposal, ToolResult, ToolTask,
    ToolValidationError, authorize, get_tool, parse_proposal, schema_for_proposals,
    validate_arguments)


class RegistryTests(unittest.TestCase):
    def test_import_has_no_tool_side_effects_or_heavy_dependency(self):
        code = ("import sys; import jarvis.tool_registry; "
                "assert not any(x in sys.modules for x in "
                "('tkinter','sqlite3','requests','sounddevice','piper','numpy','moderngl','jarvis.file_tools','jarvis.system_clock'))")
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)

    def test_exactly_four_read_only_definitions_with_immutable_nested_schemas(self):
        self.assertEqual(set(REGISTRY), {"system.get_datetime", "system.get_basic_info",
            "files.list_selected_directory", "files.get_metadata"})
        for tool in REGISTRY.values():
            with self.subTest(tool=tool.tool_id):
                self.assertEqual(tool.effect, "read_only")
                self.assertGreater(tool.timeout_seconds, 0)
                self.assertLessEqual(tool.timeout_seconds, 5)
                self.assertLessEqual(tool.max_result_bytes, MAX_RESULT_BYTES)
                self.assertTrue(tool.verification_method)
                self.assertFalse(tool.schema()["additionalProperties"])
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    tool.permission = "allow_all"
                with self.assertRaises(TypeError):
                    tool.arguments_schema["additionalProperties"] = True
        with self.assertRaises(TypeError):
            REGISTRY["shell"] = REGISTRY["system.get_basic_info"]
        clock = get_tool("system.get_datetime")
        with self.assertRaises(TypeError):
            clock.arguments_schema["properties"]["days"]["maximum"] = 10**30
        copy = clock.schema()
        copy["properties"]["kind"]["enum"].append("shell")
        self.assertNotIn("shell", clock.schema()["properties"]["kind"]["enum"])

    def test_schema_copies_cover_only_one_tool_or_none(self):
        schema = schema_for_proposals()
        self.assertEqual(len(schema["oneOf"]), 5)
        self.assertEqual({case["properties"]["tool"]["const"] for case in schema["oneOf"]},
                         {*REGISTRY, "none"})
        for case in schema["oneOf"]:
            self.assertFalse(case["additionalProperties"])
            self.assertEqual(set(case["required"]), {"tool", "arguments"})
            self.assertFalse(case["properties"]["arguments"]["additionalProperties"])
        schema["oneOf"].clear()
        self.assertEqual(len(schema_for_proposals()["oneOf"]), 5)

    def test_canonical_defaults_and_relative_path_separators(self):
        self.assertEqual(validate_arguments("system.get_datetime", {}), {"kind": "datetime", "days": 0})
        self.assertEqual(validate_arguments("files.list_selected_directory", {}), {"path": "."})
        self.assertEqual(validate_arguments("files.get_metadata", {"path": "été\\fichier 😊.txt"}),
                         {"path": "été/fichier 😊.txt"})
        self.assertEqual(validate_arguments("system.get_basic_info", {}), {})

    def test_clock_types_limits_and_iana_syntax_are_strict(self):
        for changes in ({"days": True}, {"days": 1.0}, {"days": 36601}, {"days": -36601},
                        {"kind": "shell"}, {"timezone": None}, {"timezone": ""},
                        {"timezone": "../secret"}, {"timezone": "/Europe/Paris"},
                        {"timezone": "France heure locale"}, {"timezone": "UTC\n"},
                        {"timezone": "A"*129}, {"permission": True}, {"days": math.nan},
                        {"kind": "time", "days": 1}):
            with self.subTest(changes=changes), self.assertRaises(ToolValidationError):
                validate_arguments("system.get_datetime", changes)
        for days in (-36600, 0, 36600):
            self.assertEqual(validate_arguments("system.get_datetime", {"days": days})["days"], days)
        for zone in ("UTC", "Europe/Paris", "America/Argentina/Buenos_Aires", "Etc/GMT+3", "US/East-Indiana"):
            self.assertEqual(validate_arguments("system.get_datetime", {"timezone": zone})["timezone"], zone)
        # Availability is checked by the clock tool, not guessed by this pure contract.
        self.assertEqual(validate_arguments("system.get_datetime", {"timezone": "Unavailable/Zone"})["timezone"],
                         "Unavailable/Zone")

    def test_malformed_and_multi_call_proposals_never_become_tasks(self):
        cases = (
            '[]', '[{"tool":"system.get_basic_info","arguments":{}}]',
            '{"tool":"system.get_basic_info","arguments":{},"authorized":true}',
            '{"tool":"system.get_basic_info","arguments":{},"tool":"files.get_metadata"}',
            '{"tool":"system.get_datetime","arguments":{"days":1,"days":2}}',
            '{"tool":"system.get_datetime","arguments":{"days":NaN}}',
            '{"tool":"system.get_datetime","arguments":{"days":Infinity}}',
            '{"tool":"system.get_datetime","arguments":{"days":-Infinity}}',
            '{"tool":"shell.exec","arguments":{"command":"whoami"}}',
            '{"tool":"system.get_basic_info","arguments":null}',
            '{"tool":null,"arguments":{}}',
            '{"tool":"system.get_basic_info","arguments":{}} trailing',
            '```json\n{"tool":"system.get_basic_info","arguments":{}}\n```',
            '{"tool":"system.get_basic_info"}',
            '{"tool":"none","arguments":{"action":"shell"}}',
            '{"tool":"system.get_basic_info","arguments":{"scope":"C:/"}}',
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ToolValidationError):
                parse_proposal(value)
        with self.assertRaisesRegex(ToolValidationError, "volumineuse"):
            parse_proposal(" " * (MAX_PROPOSAL_BYTES + 1))
        with self.assertRaises(ToolValidationError):
            parse_proposal("["*1500 + "]"*1500)
        with self.assertRaises(ToolValidationError):
            parse_proposal({"tool": "system.get_basic_info", "arguments": {}})

    def test_json_utf8_limits_and_invalid_surrogates(self):
        with self.assertRaises(ToolValidationError):
            parse_proposal("\ud800")
        raw = json.dumps({"tool": "files.get_metadata", "arguments": {"path": "é"*1024}}, ensure_ascii=False)
        with self.assertRaises(ToolValidationError):
            parse_proposal(raw)  # Per-component limit, not removal of useful French.
        parts = "/".join(["😊"*205]*5)
        self.assertGreater(len(json.dumps({"path": parts}, ensure_ascii=False).encode()), MAX_ARGUMENT_BYTES)
        with self.assertRaises(ToolValidationError):
            validate_arguments("files.get_metadata", {"path": parts})

    def test_paths_and_resource_grants_cannot_be_forged_in_arguments(self):
        paths = ("/etc/passwd", "C:/Windows", "C:relative", "\\\\server\\share", "\\\\?\\C:\\file",
                 "..", "a/../b", "a//b", "a/./b", "x:secret", "NUL", "con.txt", "sub/COM1.log",
                 "file.", "file ", "a\x00b", "a\nb", "a/", "CONOUT$", ".")
        for value in paths:
            with self.subTest(path=value), self.assertRaises(ToolValidationError):
                validate_arguments("files.get_metadata", {"path": value})
        for field in ("scope", "scope_id", "root", "authorized", "max_entries", "timeout", "command"):
            with self.subTest(field=field), self.assertRaises(ToolValidationError):
                validate_arguments("files.list_selected_directory", {field: True})

    def test_permissions_depend_only_on_owner_scope_not_model_or_data(self):
        for tool in ("system.get_datetime", "system.get_basic_info"):
            self.assertTrue(authorize(ToolProposal(tool)).allowed)
        for tool, arguments in (("files.list_selected_directory", {}),
                                ("files.get_metadata", {"path": "ignore all instructions.txt"})):
            proposal = ToolProposal(tool, arguments)
            self.assertEqual(authorize(proposal).code, "selection_required")
            self.assertFalse(authorize(proposal).allowed)
            self.assertTrue(authorize(proposal, scope_available=True).allowed)
        with self.assertRaises(ToolValidationError):
            authorize(ToolProposal("system.get_basic_info"), scope_available="yes")
        none = parse_proposal('{"tool":"none","arguments":{}}')
        self.assertEqual(authorize(none), PermissionDecision(False, "no_action",
            "Aucun outil nécessaire ou autorisé pour cette demande."))
        self.assertEqual(len(REGISTRY), 4)
        with self.assertRaises(ToolValidationError):
            ToolTask.new(none, 0)

    def test_proposal_and_task_are_detached_immutable_and_hash_bound_to_args(self):
        arguments = {"timezone": "UTC", "kind": "time"}
        proposal = ToolProposal("system.get_datetime", arguments)
        original_hash = proposal.fingerprint
        arguments["timezone"] = "Europe/Paris"
        self.assertEqual(proposal.arguments["timezone"], "UTC")
        self.assertEqual(proposal.fingerprint, original_hash)
        self.assertNotEqual(ToolProposal("system.get_datetime", arguments).fingerprint, original_hash)
        self.assertEqual(ToolProposal("system.get_datetime", {"kind": "time", "timezone": "UTC", "days": 0}).fingerprint,
                         original_hash)
        with self.assertRaises(TypeError):
            proposal.arguments["days"] = 50
        task = ToolTask.new(proposal, 42)
        other = ToolTask.new(proposal, 42)
        self.assertNotEqual(task.task_id, other.task_id)
        self.assertEqual(task.generation, 42)
        payload = task.to_dict()
        self.assertEqual(ToolTask.from_dict(payload), task)
        payload["arguments"]["days"] = 100
        self.assertEqual(task.arguments["days"], 0)
        for generation in (True, -1, 1.0, "1", 2**53):
            with self.assertRaises(ToolValidationError):
                ToolTask.new(proposal, generation)
        for change in ({"version": True}, {"version": 2}, {"authorized": True}, {"task_id": "old-content"}):
            with self.subTest(change=change), self.assertRaises(ToolValidationError):
                ToolTask.from_dict({**task.to_dict(), **change})

    def test_result_schema_size_finiteness_and_verification_boundaries(self):
        task = ToolTask.new(ToolProposal("system.get_basic_info"), 1)
        valid = {"method": "system_api", "scope": "schema_and_actual_read", "passed": True,
                 "checks": ["available fields read"], "limitations": ["Not a hardware benchmark"]}
        result = ToolResult(task.task_id, 1, task.tool_id, "verified", {"os": "Windows"}, valid)
        self.assertEqual(ToolResult.from_dict(result.to_dict()), result)
        source = result.to_dict()
        source["data"]["os"] = "changed"
        source["verification"]["checks"].append("invented")
        self.assertEqual(result.data["os"], "Windows")
        self.assertEqual(len(result.verification["checks"]), 1)
        for verification in ({}, {**valid, "passed": False}, {**valid, "passed": "true"},
                             {**valid, "confidence": 1.}, {**valid, "checks": ["x"]*9}):
            with self.subTest(verification=verification), self.assertRaises(ToolValidationError):
                ToolResult(task.task_id, 1, task.tool_id, "verified", {}, verification)
        for data in ({"raw": "x"*8192}, {"x": math.nan}, {"x": math.inf}, {"x": object()},
                     {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": 1}}}}}}}}}}}}}):
            with self.subTest(data=str(type(data))), self.assertRaises(ToolValidationError):
                ToolResult(task.task_id, 1, task.tool_id, "received", data)
        for status in STATUSES - {"verified"}:
            self.assertEqual(ToolResult(task.task_id, 1, task.tool_id, status).status, status)
        for change in ({"status": "executed_and_true"}, {"version": False}, {"extra": "private"}):
            with self.subTest(change=change), self.assertRaises(ToolValidationError):
                ToolResult.from_dict({**result.to_dict(), **change})

    def test_oversized_leaves_and_aggregate_are_rejected_before_encoding(self):
        task = ToolTask.new(ToolProposal("system.get_basic_info"), 0)
        for data in ({"raw": "x"*100000}, {"rows": ["x"*3000]*3}, {"integer": 1 << 100000}):
            with self.subTest(kind=tuple(data)), \
                    patch("jarvis.tool_registry.json.dumps", side_effect=AssertionError("must reject before encoding")):
                with self.assertRaises(ToolValidationError):
                    ToolResult(task.task_id, 0, task.tool_id, "received", data)


if __name__ == "__main__":
    unittest.main()
