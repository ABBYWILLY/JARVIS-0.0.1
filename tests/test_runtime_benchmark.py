"""Privacy, bounded supervision and real-Tk benchmark regression contracts."""
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from jarvis import runtime_benchmark as benchmark


class RuntimeBenchmarkTests(unittest.TestCase):
    def test_import_opens_no_model_device_display_or_database(self):
        code = "import sys; import jarvis.runtime_benchmark; assert not any(k in sys.modules for k in ('tkinter','sqlite3','numpy','sounddevice','moderngl','jarvis.ui','jarvis.ollama','jarvis.voice_runtime'))"
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, timeout=10)

    def test_pipeline_allowlist_rejects_text_boolean_nonfinite_and_unknown_metrics(self):
        private = "conversation privée 😀"
        values = {"stt_ms": 123.5, "ttft_seconds": .3, "eval_count": 42, "tokens_per_second": 24,
                  "model": private, "transcript": private, "prompt": private, "pcm": [1, 2],
                  "context_ms": True, "piper_ms": math.nan, "silence_ms": -1,
                  "audio_start_estimate_ms": 10**1000, "tts_first_pcm_ms": math.inf}
        cleaned = benchmark.numeric_metrics(values)
        self.assertEqual(cleaned, {"stt_ms": 123.5, "ttft_seconds": .3, "eval_count": 42, "tokens_per_second": 24})
        self.assertNotIn(private, json.dumps(cleaned))
        self.assertEqual(benchmark.numeric_metrics(None), {})

    def test_summary_uses_actual_samples_and_nearest_rank_percentiles(self):
        rows = [{"stt_ms": value} for value in range(1, 101)] + [{"stt_ms": None}, {"stt_ms": math.inf}]
        report = benchmark.metric_summary(rows)
        self.assertEqual(report["stt_ms"], {"count": 100, "median": 50.5, "p95": 95, "p99": 99})
        self.assertNotIn("piper_ms", report)
        self.assertEqual(benchmark.metric_summary([]), {})

    def test_profile_is_explicit_json_and_rejects_unknown_or_oversized_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            values = {"settings": {"model": "local:4b"}, "preferences": {"voice": {"speed": 1.1}, "conversation": {"size": 18}}}
            path.write_text(json.dumps(values), encoding="utf-8")
            self.assertEqual(benchmark.load_profile(path), values)
            for invalid in ([1], {"archive": "personal.sqlite3"}, {"preferences": {"other": {}}}, {"preferences": {"reading": {"size": 18}}}, {"preferences": {"voice": []}}):
                path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(ValueError):
                    benchmark.load_profile(path)
            path.write_text(" " * 65537)
            with self.assertRaises(ValueError):
                benchmark.load_profile(path)
            path.write_text('{"settings":{"temperature":NaN}}')
            with self.assertRaises(ValueError):
                benchmark.load_profile(path)
        self.assertEqual(benchmark.load_profile(None), {"settings": {}, "preferences": {}})

    def test_comparison_refuses_different_hardware_profiles_dpi_and_incomplete_runs(self):
        left = {"status": "complete", "platform": "test-host", "python": "3.12",
                "conditions": {"scenario": "canvas", "actual_tk_scaling": 1., "cache_state": "warm_observed"},
                "summary": {"startup_ms": 20, "rss_after_bytes": 100}, "metrics": {"stt_ms": {"median": 20}}}
        right = json.loads(json.dumps(left))
        right["summary"]["startup_ms"] = 15
        right["metrics"]["stt_ms"]["median"] = 16
        compared = benchmark.comparison(left, right)
        self.assertTrue(compared["comparable_conditions"])
        self.assertEqual(compared["metrics"]["startup_ms"]["delta"], -5)
        self.assertEqual(compared["metrics"]["stt_ms"]["delta_percent"], -20)
        for condition, value in (("actual_tk_scaling", 2), ("requested_gpu_profile", "eco"), ("model", "different")):
            changed = json.loads(json.dumps(right))
            changed["conditions"][condition] = value
            comparison = benchmark.comparison(left, changed)
            self.assertFalse(comparison["comparable_conditions"])
            self.assertIn(condition, comparison["condition_mismatches"])
            self.assertEqual(comparison["metrics"], {})
        right["platform"] = "another-host"
        self.assertFalse(benchmark.comparison(left, right)["comparable_conditions"])
        right["platform"] = left["platform"]
        right["status"] = "incomplete"
        self.assertEqual(benchmark.comparison(left, right)["metrics"], {})

    def test_json_csv_markdown_exports_and_existing_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            report = {"benchmark_version": 1, "status": "complete", "conditions": {"scenario": "command"},
                      "summary": {"startup_ms": 12.5, "rss_after_bytes": None},
                      "metrics": {"stt_ms": {"count": 2, "median": 12, "p95": 13, "p99": 13}}}
            benchmark.write_exports(folder, report)
            self.assertEqual(json.loads((Path(folder) / "report.json").read_text()), report)
            self.assertIn("pipeline,stt_ms,2,12,13,13", (Path(folder) / "metrics.csv").read_text())
            self.assertIn("pas une latence acoustique", (Path(folder) / "summary.md").read_text())
            original = (Path(folder) / "report.json").read_bytes()
            with self.assertRaises(FileExistsError):
                benchmark.write_exports(folder, {**report, "status": "error"})
            self.assertEqual((Path(folder) / "report.json").read_bytes(), original)

    def test_comparison_checks_actual_internal_gpu_resolution_and_adaptation_from_old_reports(self):
        before = {"status": "complete", "conditions": {"scenario": "gpu-balanced", "gpu_render_size": None},
                  "summary": {"startup_ms": 12}, "gpu_renderer": {"resolution": {
                      "internal_size": [960, 640], "effective_scale": 1., "adaptive_level": 0}}}
        after = json.loads(json.dumps(before))
        after["conditions"]["gpu_render_size"] = [960, 640]
        original = json.dumps(before, sort_keys=True)
        self.assertTrue(benchmark.comparison(before, after)["comparable_conditions"])
        for field, value, mismatch in (("internal_size", [720, 480], "gpu_render_size"),
                                       ("effective_scale", .75, "gpu_effective_scale"),
                                       ("adaptive_level", 1, "gpu_adaptive_level")):
            changed = json.loads(json.dumps(after))
            changed["gpu_renderer"]["resolution"][field] = value
            compared = benchmark.comparison(before, changed)
            self.assertFalse(compared["comparable_conditions"])
            self.assertIn(mismatch, compared["condition_mismatches"])
            self.assertEqual(compared["metrics"], {})
        self.assertEqual(json.dumps(before, sort_keys=True), original)

    def test_cli_rejects_existing_output_and_invalid_profile_before_launch(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(benchmark.subprocess, "Popen") as launch:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    benchmark.main(["--scenario", "piper", "--output", folder])
            destination = Path(folder) / "new"
            with contextlib.redirect_stderr(io.StringIO()):
                code = benchmark.main(["--scenario", "piper", "--output", str(destination), "--context", "512"])
            self.assertEqual(code, 2)
            self.assertFalse(destination.exists())
            launch.assert_not_called()

    def test_missing_or_dead_child_produces_failure_report_without_invented_metrics(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(benchmark.subprocess, "Popen") as launch:
            process = launch.return_value
            process.returncode = 7
            output = Path(folder) / "run"
            with contextlib.redirect_stdout(io.StringIO()):
                code = benchmark.main(["--scenario", "command", "--output", str(output), "--seconds", "1"])
            self.assertEqual(code, 2)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["error_type"], "ChildExitedWithoutReport")
            self.assertEqual(report["child_exitcode"], 7)
            self.assertEqual(report["metrics"], {})
            self.assertEqual(report["summary"], {})

    def test_timeout_reaps_owned_child_tree_and_keeps_failure_report(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(benchmark.subprocess, "Popen") as launch, patch.object(benchmark, "reap") as reap:
            process = launch.return_value
            process.returncode = -9
            process.wait.side_effect = subprocess.TimeoutExpired("benchmark", 31)
            output = Path(folder) / "timeout"
            with contextlib.redirect_stdout(io.StringIO()):
                code = benchmark.main(["--scenario", "conversation", "--output", str(output), "--seconds", "1"])
            self.assertEqual(code, 2)
            reap.assert_called_once_with(process)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["error_type"], "DeadlineOrUserInterruption")
            self.assertEqual(report["status"], "error")

    def test_grouped_baseline_selects_scenario_and_preserves_incomplete_status(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            before = {"benchmark_version": 1, "status": "complete", "conditions": {"scenario": "command"}, "summary": {}, "metrics": {}}
            baseline = folder / "before.json"
            baseline.write_text(json.dumps({"benchmark_suite_version": 1, "scenarios": {"command": before}}))
            def launched(command, **_options):
                (Path(command[-1])).write_text(json.dumps({**before, "status": "incomplete"}))
                return Mock(returncode=2)
            with patch.object(benchmark.subprocess, "Popen", side_effect=launched), contextlib.redirect_stdout(io.StringIO()):
                output = folder / "after"
                code = benchmark.main(["--scenario", "command", "--output", str(output), "--baseline", str(baseline)])
            self.assertEqual(code, 2)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["status"], "incomplete")
            self.assertFalse(report["comparison"]["comparable_conditions"])


class RuntimeBenchmarkTkTests(unittest.TestCase):
    def test_failed_close_releases_temporary_sqlite_and_keeps_private_cleanup_error_out_of_report(self):
        from tests.test_jarvis import display_available
        if not display_available():
            self.skipTest("Écran graphique indisponible")
        from jarvis.storage import Store
        from jarvis.ui import App
        original_temporary = tempfile.TemporaryDirectory
        original_close = Store.close
        closed = []
        typography = []
        private_error = "C:/Users/private-user/private-model-and-conversation-path"
        def temporary(*args, **kwargs):
            directory = original_temporary(*args, **kwargs)
            self.addCleanup(directory.cleanup)
            directory.cleanup = Mock(side_effect=PermissionError(private_error))
            return directory
        def close(store):
            original_close(store)
            closed.append(store)
        def decline_close(app):
            typography.append((app.typography.size, app.markdown.body_font.actual("size")))
        with original_temporary() as folder:
            config, report_path = Path(folder) / "config.json", Path(folder) / "report.json"
            config.write_text(json.dumps({"source": str(benchmark.REPO), "profile": {"settings": {}, "preferences": {"conversation": {"size": 18}}},
                "model": None, "context": None, "scenario": "idle", "width": 900, "height": 600,
                "tk_scaling": None, "seconds": 1, "warmup": .1, "visual_state": "idle",
                "cache_state": "unspecified", "allow_software": False}))
            with patch.object(App, "close", autospec=True, side_effect=decline_close), patch.object(Store, "close", autospec=True, side_effect=close), patch.object(benchmark.tempfile, "TemporaryDirectory", side_effect=temporary):
                code = benchmark._child(config, report_path)
            self.assertEqual(code, 2)
            report = json.loads(report_path.read_text())
            self.assertEqual(report["status"], "error")
            self.assertEqual(report["error_type"], "ApplicationCloseNotCompleted")
            self.assertEqual(report["temporary_cleanup_error_type"], "PermissionError")
            self.assertNotIn(private_error, report_path.read_text())
            self.assertEqual(len(closed), 1)
            self.assertEqual(typography[0], (18, 18))
            import sqlite3
            with self.assertRaises(sqlite3.ProgrammingError):
                closed[0].db.execute("SELECT 1")

    def test_real_idle_child_uses_disposable_sqlite_and_never_opens_audio_or_ollama(self):
        from tests.test_jarvis import display_available
        if not display_available():
            self.skipTest("Écran graphique indisponible")
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            output = folder / "idle"
            source = folder / "alternate-source"
            shutil.copytree(benchmark.REPO / "jarvis", source / "jarvis", ignore=shutil.ignore_patterns("__pycache__"))
            ui = source / "jarvis" / "ui.py"
            ui.write_bytes(b"# Explicit alternate checkout test.\n" + ui.read_bytes())
            secret = "Instruction privee qui ne doit jamais figurer dans le rapport."
            profile = folder / "explicit-profile.json"
            profile.write_text(json.dumps({"settings": {"system_prompt": secret},
                "preferences": {"voice": {"models_dir": str(folder / "PRIVATE-MODEL-PATH")}}}))
            result = subprocess.run([sys.executable, "-m", "jarvis.runtime_benchmark", "--scenario", "idle",
                                     "--output", str(output), "--seconds", "1", "--warmup", ".1",
                                     "--preferences", str(profile), "--source", str(source)],
                                    capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["status"], "complete", report)
            self.assertTrue(report["conditions"]["disposable_archive"])
            self.assertFalse(report["conditions"]["synthetic_audio"])
            self.assertFalse(report["conditions"]["interactive"])
            self.assertGreaterEqual(report["summary"]["sample_seconds"], 1)
            self.assertGreater(report["summary"]["process_sample_count"], 0)
            self.assertTrue(all(row["microphone_state"] == "disabled" for row in report["observations"]))
            self.assertEqual(report["pipeline_turns_with_metrics"], 0)
            self.assertEqual(report["metrics"], {})
            self.assertEqual(set(path.name for path in output.iterdir()), {"report.json", "metrics.csv", "summary.md"})
            self.assertEqual(report["callback_errors"], [])
            self.assertIn("tts_first_pcm_ms", report["unavailable"])
            self.assertEqual(report["source_sha256"]["ui.py"], hashlib.sha256(ui.read_bytes()).hexdigest())
            exported = "\n".join(path.read_text() for path in output.iterdir())
            self.assertNotIn(secret, exported)
            self.assertNotIn("PRIVATE-MODEL-PATH", exported)


if __name__ == "__main__":
    unittest.main()
