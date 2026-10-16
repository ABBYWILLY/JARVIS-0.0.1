"""Synthetic PCM/VAD probabilities through the real capture/STT control loop.

No microphone or real speech recognition is claimed by these regression tests.
"""
import queue
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.audio import FRAME, TurnDetector
from jarvis.voice_config import VoiceSettings
from jarvis.voice_runtime import capture_worker


class EndCapture(BaseException):
    pass


def run_capture(probabilities, *, silence=300, fail_first=False, mute_on_start=False,
                finish_on_start=False, hold_until_turns=0, mute_when_queued=False,
                initial_commands=(), commands_after_first_turn=(), worker=capture_worker):
    commands = queue.Queue()
    for command in initial_commands:
        commands.put(command)
    events, calls = [], []
    current = [0.0]
    release = threading.Event()

    class Outbox:
        def put(self, event, **kwargs):
            events.append(event)
            if event.kind == "turn_end" and sum(e.kind == "turn_end" for e in events) == 1:
                for command in commands_after_first_turn:
                    commands.put(command)
            if event.kind == "turn_end" and sum(e.kind == "turn_end" for e in events) >= hold_until_turns:
                release.set()
            if event.kind == "stt_queued" and mute_when_queued:
                commands.put({"kind": "mute", "value": True})
            if event.kind == "speech_start":
                # Exactly the feedback sent by VoiceControls.cancel_speech().
                commands.put({"kind": "mute", "value": mute_on_start})
                if finish_on_start:
                    commands.put({"kind": "finish_turn"})

        put_nowait = put

    class Microphone:
        native_rate = 48000

        def __init__(self, *args):
            self.sequence = iter(probabilities)
            self.drain = 20

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            time.sleep(0.001)  # Allow the real single STT executor to complete.
            try:
                current[0] = next(self.sequence)
            except StopIteration:
                self.drain -= 1
                if self.drain == 0:
                    raise EndCapture
                raise queue.Empty
            return [[0.02] * FRAME]  # Nonzero background; VAD decides independently.

    class Vad:
        def reset(self):
            pass

        def probability(self, frame):
            return current[0]

    class Whisper:
        def __init__(self, *args):
            pass

        def transcribe(self, samples):
            calls.append(samples)
            if hold_until_turns and len(calls) == 1:
                if not release.wait(5):
                    raise AssertionError("Capture did not reach the expected following turn")
            if fail_first and len(calls) == 1:
                raise ValueError("STT failure for regression test")
            return "Bonjour"

    with patch("jarvis.audio.Microphone", Microphone), patch("jarvis.audio.SileroFrames", Vad), patch("jarvis.audio.FrenchWhisper", Whisper):
        try:
            worker(Outbox(), commands, VoiceSettings(silence_ms=silence).to_dict())
        except EndCapture:
            pass
    return events, calls


class CaptureTurnTests(unittest.TestCase):
    def test_superseded_queued_sample_reports_cancellation_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cancelled.wav"
            events, _ = run_capture(([0.95] * 10 + [0.01] * 30) * 3, hold_until_turns=3,
                commands_after_first_turn=[{"kind": "sample_next", "path": str(path)}])
            self.assertFalse(path.exists())
            self.assertIn("annulée", next(e.payload for e in events if e.kind == "sample_error"))

    def test_wav_never_written_without_an_explicit_request(self):
        with patch("jarvis.audio_diagnostics.save_wav") as save:
            run_capture([0.95] * 10 + [0.01] * 30)
        save.assert_not_called()

    def test_explicit_sample_exports_one_real_wav_even_when_stt_fails(self):
        from jarvis.audio_diagnostics import read_wav
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            events, calls = run_capture(([0.95] * 10 + [0.01] * 30) * 2, fail_first=True,
                initial_commands=[{"kind": "sample_next", "path": str(path)}])
            self.assertEqual(len(calls), 2)
            self.assertTrue(path.exists())
            self.assertEqual(len(read_wav(path)), len(calls[0]))
            self.assertEqual(len([e for e in events if e.kind == "sample_saved"]), 1)
            report = next(e.payload for e in events if e.kind == "sample_saved")
            self.assertGreater(report["quality"]["rms"], 0)
            self.assertEqual(report["end_reason"], "silence")
            self.assertIn("stt_error", [e.kind for e in events])

    def test_sample_export_failure_preserves_existing_file_and_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keep.wav"
            path.write_bytes(b"preserved")
            events, _ = run_capture([0.95] * 10 + [0.01] * 30,
                initial_commands=[{"kind": "sample_next", "path": str(path)}])
            self.assertEqual(path.read_bytes(), b"preserved")
            self.assertIn("sample_error", [e.kind for e in events])
            self.assertIn("transcript", [e.kind for e in events])

    def test_muting_discards_queued_stt_before_it_can_start(self):
        sequence = ([0.95] * 10 + [0.01] * 30) * 2
        events, calls = run_capture(sequence, hold_until_turns=2, mute_when_queued=True)
        self.assertEqual(len(calls), 1)
        self.assertIn("stt_superseded", [e.kind for e in events])
        self.assertNotIn(2, [e.generation for e in events if e.kind == "transcribing"])

    def test_slow_stt_keeps_latest_completed_turn_instead_of_dropping_it(self):
        sequence = ([0.95] * 10 + [0.01] * 30) * 2
        events, calls = run_capture(sequence, hold_until_turns=2)
        self.assertEqual(len(calls), 2)
        self.assertIn("stt_queued", [e.kind for e in events])
        self.assertIn(2, [e.generation for e in events if e.kind == "transcript"])

    def test_latest_speech_supersedes_queued_turn_even_after_first_stt_error(self):
        sequence = ([0.95] * 10 + [0.01] * 30) * 3
        events, calls = run_capture(sequence, hold_until_turns=3, fail_first=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual([e.generation for e in events if e.kind == "transcript"], [3])
        self.assertIn("stt_superseded", [e.kind for e in events])
        self.assertNotIn("error", [e.kind for e in events])

    def test_real_mute_still_discards_active_turn_and_prevents_stt(self):
        events, calls = run_capture([0.95] * 15 + [0.01] * 55, mute_on_start=True)
        self.assertIn("speech_start", [e.kind for e in events])
        self.assertEqual(calls, [])
        self.assertNotIn("transcribing", [e.kind for e in events])

    def test_manual_command_reaches_whisper_once_without_waiting_for_vad_silence(self):
        events, calls = run_capture([0.95] * 100, finish_on_start=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual([e.payload["reason"] for e in events if e.kind == "turn_end"], ["manual"])
        self.assertIn("transcript", [e.kind for e in events])

    def test_ui_unmute_feedback_preserves_short_turn_for_each_silence_setting(self):
        for silence in (300, 800, 1500):
            with self.subTest(silence=silence):
                events, calls = run_capture([0.95] * 15 + [0.01] * 55, silence=silence)
                kinds = [event.kind for event in events]
                self.assertEqual(len(calls), 1)
                self.assertEqual(kinds.count("speech_start"), 1)
                self.assertLess(kinds.index("speech_start"), kinds.index("turn_end"))
                self.assertLess(kinds.index("turn_end"), kinds.index("transcribing"))
                self.assertLess(kinds.index("transcribing"), kinds.index("stt_complete"))
                self.assertIn("transcript", kinds)
                self.assertEqual(next(e.payload["reason"] for e in events if e.kind == "turn_end"), "silence")

    def test_long_speech_then_silence_reaches_whisper(self):
        events, calls = run_capture([0.95] * 300 + [0.01] * 30)
        self.assertEqual(len(calls), 1)
        self.assertGreater(len(calls[0]), 9 * 16000)
        self.assertIn("transcript", [e.kind for e in events])

    def test_constant_background_without_speech_never_submits(self):
        events, calls = run_capture([0.05] * 100)
        self.assertEqual(calls, [])
        self.assertNotIn("speech_start", [e.kind for e in events])
        diagnostic = next(e.payload for e in events if e.kind == "diagnostic")
        self.assertGreater(diagnostic["rms"], 0)
        self.assertEqual(diagnostic["vad"], 0.05)

    def test_speech_with_nonzero_constant_background_submits(self):
        events, calls = run_capture([0.05] * 10 + [0.9] * 40 + [0.05] * 30)
        self.assertEqual(len(calls), 1)
        self.assertEqual(next(e.payload for e in events if e.kind == "transcript"), "Bonjour")

    def test_abnormally_continuous_vad_is_bounded_then_rearms_after_quiet(self):
        events, calls = run_capture([0.99] * 1300 + [0.01] * 30 + [0.95] * 10 + [0.01] * 30)
        self.assertEqual(len(calls), 2)  # One bounded segment, then one new real turn.
        self.assertLessEqual(len(calls[0]), 20 * 16000)
        self.assertEqual([e.payload["reason"] for e in events if e.kind == "turn_end"], ["max_duration", "silence"])

    def test_stt_exception_is_visible_and_next_turn_recovers(self):
        events, calls = run_capture([0.95] * 10 + [0.01] * 30 + [0.95] * 10 + [0.01] * 30, fail_first=True)
        self.assertEqual(len(calls), 2)
        self.assertIn("STT failure", next(e.payload["error"] for e in events if e.kind == "stt_error"))
        self.assertEqual(len([e for e in events if e.kind == "transcript"]), 1)
        self.assertNotIn("error", [e.kind for e in events])  # Capture remains alive.

    def test_manual_endpoint_is_explicit_and_does_not_submit_idle_noise(self):
        detector = TurnDetector()
        self.assertEqual(detector.finish(), [])
        for _ in range(10):
            detector.feed([0.1] * FRAME, 0.9)
        self.assertEqual(len(detector.finish()), 1)
        self.assertEqual(detector.last_end_reason, "manual")
        self.assertTrue(detector.waiting_for_quiet)
