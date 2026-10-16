"""HTTP fixtures test protocol handling; only LiveOllama uses a real model."""
import json
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from jarvis.config import Settings, active_context
from jarvis.ollama import Ollama, OllamaError, friendly_error
from jarvis.storage import Store
from jarvis.worker import Worker


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"models": [
            {"name": "test-abliterated:latest"},
            {"name": "remote-model", "remote_host": "https://example.invalid"}
        ]}).encode())

    def do_POST(self):
        self.server.request_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        mode = self.server.mode
        self.send_response(404 if mode == "missing" else 500 if mode == "oom" else 200)
        self.end_headers()
        try:
            if mode in {"missing", "oom"}:
                self.wfile.write(b'{"error":"requires more memory"}')
                return
            if mode == "invalid":
                self.wfile.write(b'not json\n')
                return
            if mode == "error":
                self.wfile.write(b'{"error":"load failed"}\n')
                return
            if mode == "oversize":
                self.wfile.write(b'x' * (2 * 1024 * 1024 + 2))
                return
            for text in ("Bonjour ", "été 🚀"):
                line = (json.dumps({"message": {"content": text}}, ensure_ascii=False) + '\n').encode()
                # Deliberate byte fragmentation, including multibyte UTF-8.
                for i in range(0, len(line), 3):
                    self.wfile.write(line[i:i + 3])
                self.wfile.flush()
                if mode == "slow":
                    self.server.release.wait(5)
            if mode != "truncated":
                self.wfile.write(b'{"done":true,"eval_count":3}\n')
        except (BrokenPipeError, ConnectionResetError):
            pass


class Fixture:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.mode = "ok"
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


class SettingsTests(unittest.TestCase):
    def test_reject_external_and_credential_endpoints(self):
        for endpoint in ("https://example.com:443", "http://127.0.0.1:11434@evil.com:80",
                         "http://127.0.0.1:11434/api", "http://localhost:99999", "http://127.0.0.2:11434"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                Settings(endpoint=endpoint).validate()

    def test_validate_parameters(self):
        for values in ({"temperature": float('nan')}, {"temperature": 3}, {"context": 64},
                       {"max_tokens": 0}, {"context": 512, "max_tokens": 300}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Settings(**values).validate()

    def test_context_keeps_complete_recent_turns_without_mutation(self):
        history = [{"role": role, "content": "x" * 100} for role in ("user", "assistant", "user", "assistant", "user")]
        selected, omitted = active_context(history, Settings(context=1024, max_tokens=256))
        self.assertEqual(omitted, 2)
        self.assertEqual(selected, history[2:])
        self.assertEqual(len(history), 5)

    def test_context_counts_utf8_and_reserves_system_and_output(self):
        with self.assertRaises(ValueError):
            active_context([{"role": "user", "content": "🚀" * 150}], Settings(context=1024, max_tokens=256))
        selected, _ = active_context([{"role": "user", "content": "Salut"}], Settings(system_prompt="Parle français"))
        self.assertEqual(selected[0]["role"], "system")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "data.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_persistence_and_recovery(self):
        sid = self.store.new_session()
        mid = self.store.begin_turn(sid, "Salut ' ; DROP TABLE sessions; --", "abliterated")
        self.store.update_response(mid, "Réponse partielle")
        self.store.save_settings(Settings(model="abliterated", temperature=0.4))
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.settings().model, "abliterated")
        self.assertEqual(self.store.messages(sid)[1]["status"], "interrupted")
        self.assertEqual(self.store.messages(sid)[1]["content"], "Réponse partielle")
        self.assertEqual(len(self.store.sessions()), 1)

    def test_failed_turn_excluded_complete_turn_resumed(self):
        sid = self.store.new_session()
        mid = self.store.begin_turn(sid, "failed", "test")
        self.store.update_response(mid, "partial", "cancelled")
        mid = self.store.begin_turn(sid, "question", "test")
        self.store.update_response(mid, "answer", "complete")
        self.assertEqual(self.store.context(sid), [{"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"}])

    def test_delete_cascades_only_selected_session(self):
        sid = self.store.new_session()
        other = self.store.new_session()
        self.store.begin_turn(sid, "secret", "test")
        self.store.delete_session(sid)
        self.assertEqual(self.store.messages(sid), [])
        self.assertEqual(self.store.sessions()[0]["id"], other)

    def test_version_guard_and_schema(self):
        self.assertEqual(self.store.db.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(self.store.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.store.db.execute("PRAGMA user_version=2")
        with self.assertRaisesRegex(ValueError, "récente"):
            Store(self.path)


class ProtocolTests(unittest.TestCase):
    def test_models_and_streaming_real_http_fixture(self):
        with Fixture() as fixture:
            client = Ollama(fixture.endpoint)
            self.assertEqual(client.models(), ["test-abliterated:latest"])
            settings = Settings(endpoint=fixture.endpoint, model="test-abliterated:latest")
            events = list(client.chat([{"role": "user", "content": "Bonjour"}], settings))
            self.assertEqual([e.kind for e in events], ["chunk", "chunk", "done"])
            self.assertEqual(''.join(e.payload for e in events if e.kind == "chunk"), "Bonjour été 🚀")
            self.assertTrue(fixture.server.request_body["stream"])
            self.assertEqual(fixture.server.request_body["options"]["num_ctx"], 4096)
            self.assertNotIn("tools", fixture.server.request_body)

    def test_errors_and_incomplete_stream_never_report_done(self):
        with Fixture() as fixture:
            client = Ollama(fixture.endpoint)
            for mode in ("missing", "oom", "invalid", "error", "truncated", "oversize"):
                fixture.server.mode = mode
                with self.subTest(mode=mode), self.assertRaises((OllamaError, ValueError)):
                    list(client.chat([], Settings(endpoint=fixture.endpoint)))

    def test_connection_refused_and_timeout_explanation(self):
        with Fixture() as fixture:
            endpoint = fixture.endpoint
        with self.assertRaises(OSError) as caught:
            Ollama(endpoint, timeout=0.1).models()
        self.assertIn("Démarrez Ollama", friendly_error(caught.exception))
        self.assertIn("120 s", friendly_error(TimeoutError()))

    def test_spawn_worker_can_cancel_blocked_stream_and_restart(self):
        with Fixture() as fixture:
            fixture.server.mode = "slow"
            worker = Worker()
            self.addCleanup(worker.stop)
            settings = Settings(endpoint=fixture.endpoint, model="test")
            worker.start("chat", settings, [{"role": "user", "content": "test"}])
            events = []
            deadline = time.monotonic() + 8
            while not events and time.monotonic() < deadline:
                events.extend(worker.poll())
                time.sleep(0.02)
            self.assertEqual(events[0].kind, "chunk")
            started = time.monotonic()
            worker.stop()
            self.assertLess(time.monotonic() - started, 1)
            self.assertFalse(worker.alive())
            worker.start("models", settings)
            events = []
            deadline = time.monotonic() + 8
            while not events and time.monotonic() < deadline:
                events.extend(worker.poll())
                time.sleep(0.02)
            self.assertEqual(events[0].kind, "models")


def display_available():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(display_available(), "Écran graphique indisponible")
class DesktopTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from jarvis.ui import App
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "ui.sqlite3")
        self.root = tk.Tk()
        self.app = App(self.root, self.store, refresh=False)
        self.addCleanup(self.app.close)

    def pump_until(self, predicate):
        deadline = time.monotonic() + 8
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertTrue(predicate(), self.app.status.get())

    def test_desktop_model_list_send_stream_save_and_reopen_history(self):
        with Fixture() as fixture:
            self.app.settings = replace(self.app.settings, endpoint=fixture.endpoint)
            self.app.refresh_models()
            self.pump_until(lambda: not self.app.operation)
            self.assertEqual(self.app.model_var.get(), "test-abliterated:latest")
            self.app.input.insert("1.0", "Bonjour")
            self.app.send()
            self.pump_until(lambda: not self.app.operation)
            self.assertIn("Bonjour été 🚀", self.app.chat.get("1.0", "end"))
            sid = self.app.session_id
            self.assertEqual(self.store.messages(sid)[1]["status"], "complete")
            self.app.new_session()
            self.assertNotEqual(self.app.session_id, sid)
            self.app.session_id = sid
            self.app.render_session()
            self.assertIn("Bonjour été 🚀", self.app.chat.get("1.0", "end"))

    def test_desktop_stop_preserves_partial_and_recovers(self):
        with Fixture() as fixture:
            fixture.server.mode = "slow"
            self.app.settings = Settings(endpoint=fixture.endpoint, model="test")
            self.app.models = ["test"]
            self.app.input.insert("1.0", "Question")
            self.app.send()
            self.pump_until(lambda: bool(self.app.response))
            self.app.cancel()
            row = self.store.messages(self.app.session_id)[1]
            self.assertEqual(row["status"], "cancelled")
            self.assertEqual(row["content"], "Bonjour ")
            self.assertFalse(self.app.worker.alive())
            self.assertIsNone(self.app.operation)

    def test_desktop_offline_keeps_history_and_settings_accessible(self):
        with Fixture() as fixture:
            endpoint = fixture.endpoint
        self.app.settings = Settings(endpoint=endpoint)
        self.app.refresh_models()
        self.pump_until(lambda: not self.app.operation)
        self.assertIn("Connexion Ollama impossible", self.app.status.get())
        self.app.new_session()
        self.app.open_settings()
        self.assertTrue(self.root.winfo_children())


@unittest.skipUnless(os.environ.get("JARVIS_TEST_MODEL"), "Inférence réelle : définir JARVIS_TEST_MODEL")
class LiveOllamaTests(unittest.TestCase):
    def test_real_local_model(self):
        settings = Settings(model=os.environ["JARVIS_TEST_MODEL"], max_tokens=32, context=1024)
        provider = Ollama(settings.endpoint)
        self.assertIn(settings.model, provider.models())
        events = list(provider.chat([{"role": "user", "content": "Dis bonjour en français."}], settings))
        self.assertEqual(events[-1].kind, "done")
        self.assertTrue(''.join(e.payload for e in events if e.kind == "chunk").strip())


if __name__ == "__main__":
    unittest.main()
