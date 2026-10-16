"""Real HTTP/Tk/SQLite metrics contracts; no model or audio downloads."""
import gc
import json
import tempfile
import threading
import time
import tkinter as tk
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.metrics import generation_metrics, metrics_label
from jarvis.ollama import Ollama
from jarvis.storage import SCHEMA_VERSION, Store
from jarvis.ui import App
from tests.test_jarvis import display_available


STATS = {"model": "real-abliterated:latest", "eval_count": 12,
         "eval_duration": 2_000_000_000, "total_duration": 5_000_000_000,
         "load_duration": 500_000_000, "prompt_eval_count": 30,
         "prompt_eval_duration": 1_000_000_000}


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.server.request_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.end_headers()
        try:
            for data in self.server.messages:
                if data == "wait":
                    self.server.release.wait(5)
                    continue
                line = (json.dumps(data, ensure_ascii=False) + "\n").encode()
                for index in range(0, len(line), 3):
                    self.wfile.write(line[index:index + 3])
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class MetricsFixture:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MetricsHandler)
        self.server.messages = [
            {"message": {"thinking": "Réflexion interne"}},
            {"message": {"content": ""}},
            {"model": "stream-model", "message": {"content": "Bonjour été 🚀"}},
            {"done": True, "done_reason": "stop", **STATS},
        ]
        self.server.release = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *args):
        self.server.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class MetricsTests(unittest.TestCase):
    def test_real_server_counts_and_nanosecond_durations_define_rate(self):
        metrics = generation_metrics({**STATS, "ttft_seconds": 1.25})
        self.assertEqual(metrics, {**STATS, "ttft_seconds": 1.25, "tokens_per_second": 6})
        label = metrics_label(metrics)
        self.assertIn("Modèle : real-abliterated:latest", label)
        self.assertIn("Tokens : 12", label)
        self.assertIn("Tokens/s : 6.0", label)
        self.assertIn("Génération Ollama : 2.00 s", label)
        self.assertIn("TTFT reçu : 1.25 s", label)
        self.assertIn("Tokens de génération totaux : 12", label)
        self.assertIn("Tokens de réponse visibles : indisponibles", label)
        self.assertIn("Tokens du prompt : 30", label)
        self.assertIn("Traitement du prompt : 1.00 s", label)

    def test_missing_and_invalid_values_are_never_estimated(self):
        for invalid in (None, -1, True, "12", 1.5, float("nan"), float("inf")):
            with self.subTest(invalid=invalid):
                self.assertEqual(generation_metrics({key: invalid for key in STATS if key != "model"}), {})
        metrics = generation_metrics({"model": " ", "ttft_seconds": float("nan"),
                                      "eval_count": 0, "eval_duration": 0,
                                      "tokens_per_second": 12345})
        self.assertEqual(metrics, {"eval_count": 0, "eval_duration": 0})
        self.assertIn("Tokens/s : —", metrics_label(metrics))
        self.assertEqual(metrics_label(None), "Modèle : — · Tokens : — · Tokens/s : — · Génération Ollama : — · TTFT reçu : —"
                         " · Tokens de génération totaux : — · Tokens de réponse visibles : indisponibles"
                         " · Tokens du prompt : — · Traitement du prompt : — · Raisonnement : indisponible")

    def test_reasoning_and_visible_tokens_are_distinct_validated_observations(self):
        values = {**STATS, "reasoning_status": "requested_disabled", "thinking_observed": True,
                  "outcome": "length", "done_reason": "length", "response_tokens": 4}
        metrics = generation_metrics(values)
        self.assertEqual(metrics["response_tokens"], 4)
        self.assertEqual(metrics["eval_count"], 12)
        label = metrics_label(metrics)
        self.assertIn("Tokens de réponse visibles : 4", label)
        self.assertIn("désactivation demandée ; pensée interne reçue", label)
        self.assertIn("Limite de génération atteinte", label)
        for key, invalid in (("reasoning_status", []), ("outcome", []),
                             ("thinking_observed", 1), ("response_tokens", True)):
            with self.subTest(key=key):
                self.assertEqual(generation_metrics({key: invalid}), {})

    def test_http_done_preserves_real_stats_and_received_ttft(self):
        with MetricsFixture() as fixture, patch("jarvis.ollama.time") as clock:
            clock.monotonic.side_effect = [100, 101.25]
            events = list(Ollama(fixture.endpoint).chat([], Settings(model="requested-alias")))
        self.assertEqual([event.kind for event in events], ["chunk", "done"])
        self.assertEqual(events[0].payload, "Bonjour été 🚀")
        self.assertEqual(events[0].metadata, {"model": "stream-model", "ttft_seconds": 1.25,
                                             "reasoning_status": "requested_disabled", "thinking_observed": True})
        self.assertEqual(events[-1].payload, {**STATS, "ttft_seconds": 1.25,
                                             "tokens_per_second": 6, "done_reason": "stop",
                                             "reasoning_status": "requested_disabled", "thinking_observed": True,
                                             "outcome": "complete"})
        self.assertEqual(clock.monotonic.call_count, 2)

    def test_http_empty_output_has_no_ttft_or_invented_stats(self):
        with MetricsFixture() as fixture, patch("jarvis.ollama.time") as clock:
            clock.monotonic.return_value = 100
            fixture.server.messages = [{"message": {"thinking": "Interne"}},
                                       {"done": True, "eval_count": "5", "eval_duration": -1,
                                        "load_duration": True, "total_duration": None}]
            events = list(Ollama(fixture.endpoint).chat([], Settings(model="requested-alias")))
        self.assertEqual([(event.kind, event.payload) for event in events], [("done", {
            "reasoning_status": "requested_disabled", "thinking_observed": True, "outcome": "empty"})])
        self.assertEqual(clock.monotonic.call_count, 1)

    def test_http_whitespace_is_preserved_but_ttft_waits_for_visible_text(self):
        with MetricsFixture() as fixture, patch("jarvis.ollama.time") as clock:
            clock.monotonic.side_effect = [10, 12]
            fixture.server.messages = [{"message": {"content": " \n"}},
                                       {"message": {"content": "été 🚀"}}, {"done": True}]
            events = list(Ollama(fixture.endpoint).chat([], Settings()))
        self.assertEqual(events[0].payload, " \n")
        flags = {"reasoning_status": "requested_disabled", "thinking_observed": False}
        self.assertEqual(events[0].metadata, flags)
        self.assertEqual(events[1].metadata, {**flags, "ttft_seconds": 2})
        self.assertEqual(events[-1].payload, {**flags, "ttft_seconds": 2, "outcome": "complete"})


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class MetricsDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "metrics.sqlite3"
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.addCleanup(self.close_app)

    def close_app(self):
        if self.app is not None and not self.app.closed:
            self.app.close()
        self.app = self.root = self.store = None
        # Tk objects must be finalized here, before HTTP fixture threads allocate.
        gc.collect()

    def pump_until(self, predicate):
        deadline = time.monotonic() + 8
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertTrue(predicate(), self.app.status.get())

    def send(self, fixture):
        self.app.settings = Settings(endpoint=fixture.endpoint, model="requested-alias")
        self.app.models = ["requested-alias"]
        self.app.send(text="Question française 🚀")

    def metric_text(self):
        start, end = self.app.chat.tag_ranges("metrics")
        return self.app.chat.get(start, end).rstrip("\n")

    def test_http_worker_sqlite_metrics_render_identically_after_reopen(self):
        with MetricsFixture() as fixture:
            self.send(fixture)
            self.pump_until(lambda: self.app.operation is None)
        sid = self.app.session_id
        user, assistant = self.store.messages(sid)
        metrics = json.loads(assistant["metadata"])["generation_metrics"]
        self.assertEqual(assistant["content"], "Bonjour été 🚀")
        self.assertEqual(assistant["status"], "complete")
        self.assertEqual(json.loads(user["metadata"]), {})
        self.assertEqual({key: metrics[key] for key in STATS}, STATS)
        self.assertEqual(metrics["tokens_per_second"], 6)
        self.assertGreaterEqual(metrics["ttft_seconds"], 0)
        label = self.metric_text()
        self.assertEqual(label, metrics_label(metrics))
        self.assertEqual(self.store.db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.close_app()
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.assertEqual(self.app.session_id, sid)
        self.assertEqual(self.metric_text(), label)

    def test_toggle_during_stream_does_not_interrupt_and_persists(self):
        with MetricsFixture() as fixture:
            fixture.server.messages.insert(3, "wait")
            self.send(fixture)
            self.pump_until(lambda: bool(self.app.response))
            self.app.metrics_toggle.invoke()
            self.assertEqual(self.app.operation, "chat")
            self.assertTrue(self.app.worker.alive())
            self.assertFalse(self.store.get_preference("show_generation_metrics"))
            self.assertTrue(self.app.chat.tk.getboolean(self.app.chat.tag_cget("metrics", "elide")))
            fixture.server.release.set()
            self.pump_until(lambda: self.app.operation is None)
        self.assertEqual(self.store.messages(self.app.session_id)[1]["content"], "Bonjour été 🚀")
        self.assertIn("Tokens : 12", self.metric_text())
        self.close_app()
        self.store = Store(self.path)
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.assertFalse(self.app.metrics_visible.get())
        self.assertTrue(self.app.chat.tk.getboolean(self.app.chat.tag_cget("metrics", "elide")))
        self.app.metrics_toggle.invoke()
        self.assertFalse(self.app.chat.tk.getboolean(self.app.chat.tag_cget("metrics", "elide")))
        self.assertIn("Tokens/s : 6.0", self.metric_text())

    def test_cancelled_and_failed_streams_keep_ttft_without_fabricated_tokens(self):
        for status in ("cancelled", "error"):
            with self.subTest(status=status), MetricsFixture() as fixture:
                self.app.new_session()
                fixture.server.messages = [fixture.server.messages[2], "wait"]
                if status == "error":
                    fixture.server.messages.append({"error": "generation failed"})
                self.send(fixture)
                self.pump_until(lambda: bool(self.app.response))
                if status == "cancelled":
                    self.app.cancel()
                else:
                    fixture.server.release.set()
                    self.pump_until(lambda: self.app.operation is None)
                assistant = self.store.messages(self.app.session_id)[1]
                metrics = json.loads(assistant["metadata"])["generation_metrics"]
                self.assertEqual(assistant["status"], status)
                self.assertEqual(assistant["content"], "Bonjour été 🚀")
                self.assertEqual(metrics["model"], "stream-model")
                self.assertIn("ttft_seconds", metrics)
                self.assertNotIn("eval_count", metrics)
                self.assertNotIn("eval_duration", metrics)
                self.assertNotIn("tokens_per_second", metrics)
                self.assertIn("Tokens : — · Tokens/s : — · Génération Ollama : —", self.metric_text())
                self.app.render_session()
                self.assertIn("Tokens : —", self.metric_text())

    def test_old_history_with_no_metrics_displays_dashes_and_keeps_voice_metadata(self):
        mid = self.store.begin_turn(self.app.session_id, "Question vocale", "old-model",
                                    source="voice", metadata={"final_transcript": "Question vocale"})
        self.store.update_response(mid, "Réponse ancienne", "complete")
        self.store.update_message_metadata(mid, {"audio_status": "complete"})
        self.app.render_session()
        self.assertEqual(self.metric_text(), metrics_label({}))
        self.assertEqual(json.loads(self.store.messages(self.app.session_id)[1]["metadata"]),
                         {"final_transcript": "Question vocale", "audio_status": "complete"})


if __name__ == "__main__":
    unittest.main()
