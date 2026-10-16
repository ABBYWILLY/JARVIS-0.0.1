"""Real loopback HTTP and CLI execution; no inference model is installed or run."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jarvis.config import Settings
from jarvis.inference_benchmark import run_benchmark
from jarvis.ollama import Event


MODEL = "qwen3.5-abliterated:4b"
SECRET_THOUGHT = "INTERNE-NON-PERSISTE-ÉTÉ"
REPO = Path(__file__).resolve().parents[1]


def response(body):
    optimized = body.get("think") is False
    return [{"message": {"thinking": SECRET_THOUGHT}},
            {"message": {"content": "Réponse visible été 👩🏽‍💻."}},
            {"done": True, "done_reason": "stop", "model": MODEL,
             "eval_count": 6 if optimized else 12,
             "eval_duration": 1_000_000_000 if optimized else 2_000_000_000,
             "total_duration": 2_000_000_000 if optimized else 4_000_000_000,
             "prompt_eval_count": 600 if optimized else 1200,
             "prompt_eval_duration": 400_000_000 if optimized else 800_000_000}]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.gets.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"models": [{"name": name} for name in self.server.models]}).encode())

    def do_POST(self):
        self.server.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        body = self.server.requests[-1]
        if self.server.inspect:
            self.server.inspect(body)
        chunks = self.server.respond(body)
        self.send_response(200)
        self.end_headers()
        try:
            for chunk in chunks:
                self.wfile.write((json.dumps(chunk, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class Fixture:
    def __init__(self, respond=response, models=(MODEL,), inspect=None):
        self.respond, self.models, self.inspect = respond, models, inspect

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.requests, self.server.gets = [], []
        self.server.respond, self.server.models, self.server.inspect = self.respond, self.models, self.inspect
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class BenchmarkTests(unittest.TestCase):
    def test_http_combined_profiles_same_options_alternate_order_and_never_save_thinking(self):
        with tempfile.TemporaryDirectory() as temporary, Fixture() as fixture:
            output = Path(temporary) / "benchmark.jsonl"
            settings = Settings(endpoint=fixture.endpoint, model=MODEL)
            summary = run_benchmark(settings, output, repeats=2)
            written = rows(output)
            requests = fixture.server.requests
            self.assertEqual(fixture.server.gets, ["/api/tags"])
            self.assertEqual(len(requests), 13)  # one warmup, three cases x two modes x two repeats
            self.assertEqual(requests[0]["options"]["num_predict"], 16)
            self.assertIs(requests[0]["think"], False)
            for body in requests[1:]:
                self.assertEqual(body["model"], MODEL)
                self.assertEqual(body["options"], {"temperature": settings.temperature,
                                                    "num_ctx": settings.context, "num_predict": settings.max_tokens})
            measurements = [row for row in written if row["type"] == "measurement"]
            first_modes = [measurements[i]["variant"] for i in range(0, len(measurements), 2)]
            self.assertEqual(first_modes, ["baseline", "optimized", "baseline",
                                           "optimized", "baseline", "optimized"])
            for body, record in zip(requests[1:], measurements):
                if record["variant"] == "baseline":
                    self.assertNotIn("think", body)
                else:
                    self.assertIs(body["think"], False)
                self.assertEqual(record["requested_model"], MODEL)
                self.assertEqual(record["metrics"]["model"], MODEL)
                self.assertTrue(record["metrics"]["thinking_observed"])
                self.assertEqual(record["visible_text"], "Réponse visible été 👩🏽‍💻.")
                self.assertGreaterEqual(record["wall_seconds"], 0)
            self.assertNotIn(SECRET_THOUGHT, output.read_text(encoding="utf-8"))
            self.assertTrue(written[0]["synthetic_corpus"])
            self.assertTrue(any("effets non isolés" in text for text in written[0]["limitations"]))
            self.assertEqual([r["type"] for r in written].count("warmup"), 1)
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["complete_pairs"], 6)
            self.assertEqual(summary["measured_runs"], 12)
            for pair in summary["comparisons"]:
                self.assertEqual(pair["deltas"]["eval_count"], {
                    "baseline": 12, "optimized": 6, "delta": -6, "unit": "tokens",
                    "better_when": "lower", "reduction_percent": 50.0})
                self.assertNotIn("context_estimate_tokens", pair["deltas"])

    def test_previous_result_is_readable_before_the_next_http_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "durable.jsonl"
            inspected = []

            def inspect(body):
                inspected.append([row["type"] for row in rows(output)])

            with Fixture(inspect=inspect) as fixture:
                run_benchmark(Settings(endpoint=fixture.endpoint, model=MODEL), output)
            self.assertEqual(inspected[0], ["header"])
            self.assertEqual(inspected[1], ["header", "warmup"])
            self.assertEqual(inspected[2], ["header", "warmup", "measurement"])
            self.assertEqual(len(inspected[-1]), 7)

    def test_empty_length_and_stream_errors_never_produce_comparison_gains(self):
        def incomplete(body):
            if body["options"]["num_predict"] == 16 or body.get("think") is False:
                return response(body)
            prompt = body["messages"][-1]["content"]
            if prompt == "2 + 2 ?":
                return [{"message": {"content": "Réponse tronquée"}},
                        {"done": True, "done_reason": "length", "eval_count": 1024}]
            if "première" in prompt:
                return [{"message": {"thinking": SECRET_THOUGHT}}, {"done": True}]
            return [{"message": {"content": "Réponse partielle"}}]

        with tempfile.TemporaryDirectory() as temporary, Fixture(respond=incomplete) as fixture:
            output = Path(temporary) / "incomplete.jsonl"
            summary = run_benchmark(Settings(endpoint=fixture.endpoint, model=MODEL), output)
            self.assertEqual(summary["status"], "incomplete")
            self.assertEqual(summary["complete_pairs"], 0)
            self.assertEqual(summary["excluded_pairs"], 3)
            self.assertTrue(all(pair["deltas"] == {} for pair in summary["comparisons"]))
            baselines = [row for row in rows(output) if row.get("variant") == "baseline"]
            self.assertEqual([row["status"] for row in baselines], ["length", "empty", "error"])
            self.assertEqual(baselines[-1]["visible_text"], "Réponse partielle")

    def test_missing_server_counts_are_not_replaced_by_text_estimates_or_zero(self):
        def missing(body):
            return [{"message": {"content": "Visible"}}, {"done": True}]

        with tempfile.TemporaryDirectory() as temporary, Fixture(respond=missing) as fixture:
            output = Path(temporary) / "missing.jsonl"
            summary = run_benchmark(Settings(endpoint=fixture.endpoint, model=MODEL), output)
            self.assertEqual(summary["complete_pairs"], 3)
            for pair in summary["comparisons"]:
                self.assertNotIn("eval_count", pair["deltas"])
                self.assertNotIn("response_tokens", pair["deltas"])
                self.assertNotIn("prompt_eval_count", pair["deltas"])
                self.assertIn("wall_seconds", pair["deltas"])

    def test_zero_baseline_and_negative_savings_remain_explicit(self):
        def slower(body):
            chunks = response(body)
            chunks[-1]["eval_count"] = 18 if body.get("think") is False else 12
            chunks[-1]["prompt_eval_count"] = 10 if body.get("think") is False else 0
            return chunks

        with tempfile.TemporaryDirectory() as temporary, Fixture(respond=slower) as fixture:
            result = run_benchmark(Settings(endpoint=fixture.endpoint, model=MODEL),
                                   Path(temporary) / "slower.jsonl")
            for pair in result["comparisons"]:
                self.assertEqual(pair["deltas"]["eval_count"]["reduction_percent"], -50)
                self.assertEqual(pair["deltas"]["prompt_eval_count"]["delta"], 10)
                self.assertIsNone(pair["deltas"]["prompt_eval_count"]["reduction_percent"])

    def test_server_model_change_makes_pair_noncomparable(self):
        def mismatch(body):
            chunks = response(body)
            if body.get("think") is False:
                chunks[-1]["model"] = "another-actual-model"
            return chunks

        with tempfile.TemporaryDirectory() as temporary, Fixture(respond=mismatch) as fixture:
            result = run_benchmark(Settings(endpoint=fixture.endpoint, model=MODEL),
                                   Path(temporary) / "different.jsonl")
            self.assertEqual(result["complete_pairs"], 0)
            self.assertTrue(all("diffèrent" in pair["reason"] for pair in result["comparisons"]))

    def test_interruption_preserves_partial_text_and_completed_rows(self):
        class InterruptedClient:
            calls = 0

            def models(self):
                return [MODEL]

            def chat(self, messages, settings):
                self.calls += 1
                yield Event("chunk", "Prêt" if self.calls == 1 else "Partiel été")
                if self.calls > 1:
                    raise KeyboardInterrupt
                yield Event("done", {"outcome": "complete", "model": MODEL})

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "interrupted.jsonl"
            summary = run_benchmark(Settings(model=MODEL), output, client=InterruptedClient())
            written = rows(output)
            self.assertEqual([row["type"] for row in written], ["header", "warmup", "measurement", "summary"])
            self.assertEqual(written[-2]["visible_text"], "Partiel été")
            self.assertEqual(written[-2]["status"], "interrupted")
            self.assertEqual(summary["status"], "interrupted")
            self.assertEqual(summary["complete_pairs"], 0)

    def cli(self, output, endpoint, *extra):
        # Match the child's redirected streams to the strict UTF-8 decoder.
        # Windows otherwise uses its locale code page for French errors.
        return subprocess.run([sys.executable, "-m", "jarvis.inference_benchmark", "--model", MODEL,
                               "--output", str(output), "--endpoint", endpoint, *extra],
                              cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=30,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def test_cli_default_one_repeat_uses_real_loopback_adapter(self):
        with tempfile.TemporaryDirectory() as temporary, Fixture() as fixture:
            output = Path(temporary) / "cli.jsonl"
            result = self.cli(output, fixture.endpoint, "--temperature", "0.25", "--max-tokens", "128")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["complete_pairs"], 3)
            self.assertEqual(len(fixture.server.requests), 7)
            self.assertTrue(all(body["options"]["num_predict"] == 128 for body in fixture.server.requests[1:]))
            self.assertTrue(all(body["options"]["temperature"] == 0.25 for body in fixture.server.requests))
            self.assertNotIn(SECRET_THOUGHT, result.stdout + result.stderr + output.read_text(encoding="utf-8"))

    def test_cli_missing_installed_model_stops_before_any_post_and_records_error(self):
        with tempfile.TemporaryDirectory() as temporary, Fixture(models=("other",)) as fixture:
            output = Path(temporary) / "missing-model.jsonl"
            result = self.cli(output, fixture.endpoint)
            self.assertEqual(result.returncode, 1)
            self.assertIn("absent", result.stderr)
            self.assertEqual(fixture.server.requests, [])
            self.assertEqual([row["type"] for row in rows(output)], ["header", "error"])

    def test_cli_never_overwrites_an_existing_file_or_contacts_ollama(self):
        with tempfile.TemporaryDirectory() as temporary, Fixture() as fixture:
            output = Path(temporary) / "existing.jsonl"
            original = "Données utilisateur existantes 👩🏽‍💻\n"
            output.write_text(original, encoding="utf-8")
            result = self.cli(output, fixture.endpoint)
            self.assertEqual(result.returncode, 1)
            self.assertIn("existe déjà", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), original)
            self.assertEqual(fixture.server.gets, [])
            self.assertEqual(fixture.server.requests, [])

    def test_invalid_repeat_count_never_starts_network_or_creates_output(self):
        with tempfile.TemporaryDirectory() as temporary, Fixture() as fixture:
            for value in ("0", "11"):
                output = Path(temporary) / f"invalid-{value}.jsonl"
                result = self.cli(output, fixture.endpoint, "--repeats", value)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(output.exists())
            self.assertEqual(fixture.server.gets, [])
            self.assertEqual(fixture.server.requests, [])

    def test_cli_empty_results_return_incomplete_status_instead_of_success(self):
        def empty(body):
            return [{"message": {"thinking": SECRET_THOUGHT}}, {"done": True, "done_reason": "length"}]

        with tempfile.TemporaryDirectory() as temporary, Fixture(respond=empty) as fixture:
            output = Path(temporary) / "empty.jsonl"
            result = self.cli(output, fixture.endpoint)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "incomplete")
            self.assertEqual(rows(output)[-1]["complete_pairs"], 0)


if __name__ == "__main__":
    unittest.main()
