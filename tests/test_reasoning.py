"""Real loopback HTTP fixtures; no model, thinking text or download is needed."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.ollama import Ollama, OllamaError


class ReasoningHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(payload)
        status, messages = self.server.responses.pop(0)
        self.send_response(status)
        self.end_headers()
        try:
            for message in messages:
                raw = (json.dumps(message, ensure_ascii=False) + "\n").encode()
                for index in range(0, len(raw), 3):
                    self.wfile.write(raw[index:index + 3])
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class ReasoningFixture:
    def __init__(self, *responses):
        self.responses = responses

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ReasoningHandler)
        self.server.responses = list(self.responses)
        self.server.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def chat(self, **settings):
        return Ollama(self.endpoint).chat([], Settings(endpoint=self.endpoint, **settings))


def answer(text="Bonjour été 🚀", **stats):
    return 200, [{"message": {"content": text}}, {"done": True, **stats}]


class ReasoningProtocolTests(unittest.TestCase):
    def test_fast_default_requests_top_level_false_for_abliterated_4b_and_9b(self):
        with ReasoningFixture(answer(), answer()) as fixture:
            for model in ("qwen3.5-abliterated:4b", "qwen3.5-abliterated:9b"):
                events = list(fixture.chat(model=model))
                payload = fixture.server.requests[-1]
                self.assertEqual(payload["model"], model)
                self.assertIs(payload["think"], False)
                self.assertNotIn("think", payload["options"])
                self.assertNotIn("tools", payload)
                self.assertEqual(events[-1].payload["reasoning_status"], "requested_disabled")
                self.assertEqual(events[-1].payload["outcome"], "complete")
                self.assertIs(events[-1].payload["thinking_observed"], False)

    def test_deep_requests_true_and_auto_does_not_send_think(self):
        with ReasoningFixture(answer(), answer()) as fixture:
            for mode, status in (("deep", "requested_enabled"), ("auto", "model_default")):
                events = list(fixture.chat(reasoning_mode=mode))
                payload = fixture.server.requests[-1]
                if mode == "deep":
                    self.assertIs(payload["think"], True)
                else:
                    self.assertNotIn("think", payload)
                self.assertNotIn("think", payload["options"])
                self.assertEqual(events[-1].payload["reasoning_status"], status)

    def test_internal_thinking_is_observed_but_never_emitted_or_timed_as_text(self):
        secret = "Contenu interne qui ne doit jamais être conservé"
        messages = [
            {"message": {"thinking": secret}},
            {"message": {"content": " \n"}},
            {"message": {"thinking": "Encore interne", "content": "L’été "}},
            {"message": {"content": "est là. 🚀"}},
            {"done": True, "eval_count": 100, "eval_duration": 2_000_000_000},
        ]
        with ReasoningFixture((200, messages)) as fixture, patch("jarvis.ollama.time") as clock:
            clock.monotonic.side_effect = [100, 103]
            events = list(fixture.chat())
        self.assertEqual([event.kind for event in events], ["chunk", "chunk", "chunk", "done"])
        self.assertEqual("".join(event.payload for event in events if event.kind == "chunk"), " \nL’été est là. 🚀")
        self.assertNotIn(secret, repr(events))
        self.assertNotIn("Encore interne", repr(events))
        self.assertNotIn("ttft_seconds", events[0].metadata)
        self.assertEqual(events[1].metadata["ttft_seconds"], 3)
        self.assertEqual(events[-1].payload["ttft_seconds"], 3)
        self.assertIs(events[-1].payload["thinking_observed"], True)
        # This is a request status, never a claim that the model obeyed it.
        self.assertEqual(events[-1].payload["reasoning_status"], "requested_disabled")
        self.assertEqual(events[-1].payload["eval_count"], 100)
        self.assertNotIn("response_tokens", events[-1].payload)
        self.assertEqual(clock.monotonic.call_count, 2)

    def test_thinking_only_length_keeps_real_server_metrics_and_no_ttft(self):
        messages = [{"message": {"thinking": "Réflexion interne"}},
                    {"done": True, "done_reason": "length", "eval_count": 512,
                     "eval_duration": 4_000_000_000, "prompt_eval_count": 20}]
        with ReasoningFixture((200, messages)) as fixture, patch("jarvis.ollama.time") as clock:
            clock.monotonic.return_value = 1
            events = list(fixture.chat())
        self.assertEqual([event.kind for event in events], ["done"])
        final = events[0].payload
        self.assertEqual(final["outcome"], "empty_length")
        self.assertEqual(final["done_reason"], "length")
        self.assertEqual(final["eval_count"], 512)
        self.assertEqual(final["eval_duration"], 4_000_000_000)
        self.assertEqual(final["tokens_per_second"], 128)
        self.assertEqual(final["prompt_eval_count"], 20)
        self.assertIs(final["thinking_observed"], True)
        self.assertNotIn("ttft_seconds", final)
        self.assertEqual(clock.monotonic.call_count, 1)

    def test_empty_and_whitespace_only_are_not_successful_visible_answers(self):
        responses = [(200, [{"message": {"thinking": "Interne"}}, {"done": True}]),
                     answer(" \n", done_reason="stop"), answer("", done_reason="length")]
        with ReasoningFixture(*responses) as fixture:
            for index, expected in enumerate(("empty", "empty", "empty_length")):
                with self.subTest(index=index):
                    events = list(fixture.chat())
                    self.assertEqual(events[-1].payload["outcome"], expected)
                    self.assertNotIn("ttft_seconds", events[-1].payload)
                    if index == 1:
                        self.assertEqual(events[0].payload, " \n")

    def test_visible_text_with_length_is_reported_as_partial_without_truncating_it(self):
        text = "Début réel : 42. "
        with ReasoningFixture(answer(text, done_reason="length", eval_count=12)) as fixture:
            events = list(fixture.chat())
        self.assertEqual(events[0].payload, text)
        self.assertEqual(events[-1].payload["outcome"], "length")
        self.assertEqual(events[-1].payload["eval_count"], 12)

    def test_explicit_unsupported_rejection_retries_once_without_think_and_reports_it(self):
        cases = [(400, '"qwen" does not support thinking'),
                 (422, 'unknown field "think"'),
                 (400, "thinking is not supported for this model")]
        for status, error in cases:
            with self.subTest(status=status, error=error), ReasoningFixture(
                    (status, [{"error": error}]), answer()) as fixture:
                events = list(fixture.chat())
                self.assertEqual([event.kind for event in events], ["notice", "chunk", "done"])
                self.assertIn("Une seule reprise", events[0].payload)
                self.assertEqual(len(fixture.server.requests), 2)
                self.assertIs(fixture.server.requests[0]["think"], False)
                self.assertNotIn("think", fixture.server.requests[1])
                self.assertEqual(events[0].metadata["reasoning_status"], "unsupported")
                self.assertEqual(events[1].metadata["reasoning_status"], "unsupported")
                self.assertEqual(events[-1].payload["reasoning_status"], "unsupported")

    def test_deep_rejection_also_reports_fallback_and_does_not_claim_enabled(self):
        with ReasoningFixture((400, [{"error": "thinking is unsupported"}]), answer()) as fixture:
            events = list(fixture.chat(reasoning_mode="deep"))
            self.assertIs(fixture.server.requests[0]["think"], True)
            self.assertNotIn("think", fixture.server.requests[1])
        self.assertEqual(events[-1].payload["reasoning_status"], "unsupported")

    def test_second_unsupported_rejection_never_causes_a_third_request(self):
        rejection = 400, [{"error": '"model" does not support thinking'}]
        with ReasoningFixture(rejection, rejection) as fixture:
            stream = fixture.chat()
            self.assertEqual(next(stream).kind, "notice")
            with self.assertRaises(OllamaError):
                list(stream)
            self.assertEqual(len(fixture.server.requests), 2)

    def test_generic_http_errors_oom_bad_types_and_other_statuses_never_retry(self):
        cases = [(400, "invalid request"), (422, "think must be a boolean"),
                 (400, "model needs more memory; does not support thinking"),
                 (400, "CUDA out of memory"), (404, "thinking is unsupported"),
                 (500, 'unknown field "think"'), (400, "unknown field think_time"),
                 (422, "invalid parameter think")]
        responses = [(status, [{"error": error}]) for status, error in cases]
        with ReasoningFixture(*responses) as fixture:
            for index, (status, error) in enumerate(cases):
                with self.subTest(status=status, error=error), self.assertRaises(OllamaError):
                    list(fixture.chat())
                self.assertEqual(len(fixture.server.requests), index + 1)

    def test_auto_cannot_fallback_a_field_it_did_not_send(self):
        with ReasoningFixture((400, [{"error": "thinking is unsupported"}])) as fixture:
            with self.assertRaises(OllamaError):
                list(fixture.chat(reasoning_mode="auto"))
            self.assertEqual(len(fixture.server.requests), 1)
            self.assertNotIn("think", fixture.server.requests[0])

    def test_stream_error_never_retries_or_duplicates_visible_text(self):
        messages = [{"message": {"content": "Déjà reçu"}},
                    {"error": '"model" does not support thinking'}]
        with ReasoningFixture((200, messages)) as fixture:
            stream = fixture.chat()
            self.assertEqual(next(stream).payload, "Déjà reçu")
            with self.assertRaises(OllamaError):
                list(stream)
            self.assertEqual(len(fixture.server.requests), 1)

    def test_connection_failures_are_never_retried(self):
        with patch.object(Ollama, "_request", side_effect=ConnectionRefusedError()) as request:
            with self.assertRaises(ConnectionRefusedError):
                list(Ollama("http://127.0.0.1:11434").chat([], Settings()))
        self.assertEqual(request.call_count, 1)

    def test_non_string_content_or_thinking_and_bad_message_shape_are_rejected(self):
        messages = [{"message": {key: invalid}} for key in ("content", "thinking")
                    for invalid in (None, 1, True, ["fragment"], {"text": "fragment"})]
        messages.extend([{"message": None}, {"message": []}, []])
        with ReasoningFixture(*[(200, [message]) for message in messages]) as fixture:
            for index, message in enumerate(messages):
                with self.subTest(message=message), self.assertRaisesRegex(OllamaError, "Format"):
                    list(fixture.chat())
                self.assertEqual(len(fixture.server.requests), index + 1)

    def test_server_fields_cannot_override_client_reasoning_or_received_ttft(self):
        poisoned = {"thinking_observed": False, "reasoning_status": "model_default",
                    "ttft_seconds": 0, "outcome": "empty", "done_reason": "stop"}
        messages = [{"message": {"thinking": "Interne", "content": "Texte"}},
                    {"done": True, **poisoned}]
        with ReasoningFixture((200, messages)) as fixture, patch("jarvis.ollama.time") as clock:
            clock.monotonic.side_effect = [10, 14]
            events = list(fixture.chat())
        final = events[-1].payload
        self.assertIs(final["thinking_observed"], True)
        self.assertEqual(final["reasoning_status"], "requested_disabled")
        self.assertEqual(final["ttft_seconds"], 4)
        self.assertEqual(final["outcome"], "complete")


if __name__ == "__main__":
    unittest.main()
