"""Blocked-STT failure recovery with synthetic PCM, never physical audio.

The held transcription is released in every test. A separate real spawn test
checks that the owning parent can stop a capture child still held in native STT.
"""
import multiprocessing as mp
import queue
import threading
import time
import unittest
from unittest.mock import patch

from jarvis.audio import FRAME
from jarvis.voice_config import VoiceSettings
from jarvis.voice_runtime import AudioProcess, capture_worker


def _blocked_capture_child(outbox, commands, profile):
    """Production capture loop in a real child, using no model or device."""
    started = threading.Event()
    release = threading.Event()

    class Outbox:
        def put(self, event, **kwargs):
            if event.kind == "speech_start":
                commands.put({"kind": "finish_turn"})
            outbox.put(event, **kwargs)

        def put_nowait(self, event):
            outbox.put_nowait(event)

    class Microphone:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            if started.is_set():
                raise RuntimeError("Synthetic USB microphone disconnected")
            return [[.02] * FRAME]

    class Vad:
        def reset(self):
            pass

        def probability(self, frame):
            return .95

    class Whisper:
        def __init__(self, *args):
            pass

        def transcribe(self, samples):
            started.set()
            release.wait(30)  # The parent must kill this isolated test child first.
            return "Never deliver after capture failure"

    with patch("jarvis.audio.Microphone", Microphone), patch("jarvis.audio.SileroFrames", Vad), \
            patch("jarvis.audio.FrenchWhisper", Whisper):
        capture_worker(Outbox(), commands, profile)


class CaptureFailureLatencyTests(unittest.TestCase):
    def assert_failure_does_not_wait_for_stt(self, failure):
        started, release, error = threading.Event(), threading.Event(), threading.Event()
        closed, queued = threading.Event(), threading.Event()
        events, calls, failures = [], [], []
        commands = queue.Queue()
        before_threads = set(threading.enumerate())
        current = [0.]

        class Outbox:
            def put(self, event, **kwargs):
                events.append(event)
                if event.kind == "stt_queued":
                    queued.set()
                if event.kind == "capture_error":
                    error.set()

            put_nowait = put

        class Microphone:
            def __init__(self, *args):
                self.sequence = iter(([.95] * 10 + [.01] * 10) * 2)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                closed.set()

            def read(self):
                try:
                    current[0] = next(self.sequence)
                except StopIteration:
                    if not started.wait(2) or not queued.wait(2):
                        raise AssertionError("Expected one active and one queued STT turn")
                    if failure == "microphone":
                        raise RuntimeError("Synthetic USB microphone unplugged")
                return [[.02] * FRAME]

        class Vad:
            def reset(self):
                pass

            def probability(self, frame):
                if failure == "vad" and queued.is_set():
                    raise ValueError("Synthetic VAD inference failure")
                return current[0]

        class Whisper:
            def __init__(self, *args):
                pass

            def transcribe(self, samples):
                calls.append(len(samples))
                started.set()
                if not release.wait(6):
                    raise AssertionError("Test forgot STT release")
                return "Do not deliver after fatal capture error"

        def worker():
            try:
                capture_worker(Outbox(), commands, VoiceSettings(silence_ms=300).to_dict())
            except BaseException as exc:
                failures.append(exc)

        with patch("jarvis.audio.Microphone", Microphone), patch("jarvis.audio.SileroFrames", Vad), \
                patch("jarvis.audio.FrenchWhisper", Whisper):
            thread = threading.Thread(target=worker, name="jarvis-test-failed-capture")
            thread.start()
            try:
                self.assertTrue(started.wait(2), "Synthetic STT must be active")
                self.assertTrue(queued.wait(2), "Second completed turn must occupy the bounded pending slot")
                self.assertTrue(error.wait(2), "Fatal capture error must be visible before STT completes")
                self.assertTrue(closed.is_set(), "Microphone must close while STT is still blocked")
                self.assertFalse(release.is_set())
                self.assertEqual(len(calls), 1)
            finally:
                release.set()
                thread.join(3)
                for other in set(threading.enumerate()) - before_threads:
                    if other.name.startswith("ThreadPoolExecutor"):
                        other.join(3)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures)
        self.assertEqual(len(calls), 1, "Pending STT must never execute after capture failure")
        self.assertFalse(any(event.kind in {"transcript", "stt_complete"} for event in events))
        self.assertEqual([event.kind for event in events].count("capture_error"), 1)
        self.assertEqual([event.kind for event in events].count("error"), 1)
        payload = next(event.payload for event in events if event.kind == "capture_error")
        self.assertIn("Synthetic USB" if failure == "microphone" else "Synthetic VAD", payload["error"])
        self.assertFalse(set(threading.enumerate()) - before_threads)

    def test_disconnect_closes_microphone_and_reports_error_before_blocked_stt_finishes(self):
        self.assert_failure_does_not_wait_for_stt("microphone")

    def test_vad_failure_drops_pending_turn_and_never_delivers_late_stt(self):
        self.assert_failure_does_not_wait_for_stt("vad")

    def test_parent_stops_real_capture_child_still_held_in_stt_after_capture_error(self):
        boundary = AudioProcess()
        before_children = {child.pid for child in mp.active_children()}
        events = []
        try:
            with patch("jarvis.voice_runtime.capture_worker", _blocked_capture_child):
                boundary.start("capture", VoiceSettings())
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                events.extend(boundary.poll())
                if any(event.kind == "error" for event in events):
                    break
                time.sleep(.01)
            self.assertTrue(any(event.kind == "capture_error" for event in events))
            self.assertTrue(any(event.kind == "error" for event in events))
            self.assertFalse(any(event.kind in {"transcript", "stt_complete"} for event in events))
            self.assertTrue(boundary.alive(), "The STT double must remain held until its parent stops it")
        finally:
            boundary.stop()
        self.assertFalse(boundary.alive())
        self.assertIsNone(boundary.process)
        self.assertIsNone(boundary.commands)
        self.assertIsNone(boundary.outbox)
        self.assertEqual({child.pid for child in mp.active_children()}, before_children)


if __name__ == "__main__":
    unittest.main()
