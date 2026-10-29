"""Bounded spawn/stop regressions without models, devices or audio playback."""
import multiprocessing as mp
import time
import unittest
from unittest.mock import Mock, patch

from jarvis.audio import AudioEvent
from jarvis.voice_config import VoiceSettings
from jarvis.voice_runtime import AudioProcess


def _idle_audio_child(outbox, commands, profile, generation, *rest):
    """Real spawn and queues; deliberately no native audio/model imports."""
    outbox.put(AudioEvent("probe_ready", generation=generation))
    commands.get()


class AudioLifecycleTests(unittest.TestCase):
    def test_failed_spawn_closes_unstarted_process_and_channels_and_allows_retry(self):
        boundary = AudioProcess()
        process = Mock(pid=None)
        process.start.side_effect = OSError("synthetic spawn failure")
        process.join.side_effect = AssertionError("can only join a started process")
        channels = [Mock(), Mock()]
        with patch.object(boundary.context, "Queue", side_effect=channels), \
                patch.object(boundary.context, "Process", return_value=process):
            with self.assertRaisesRegex(OSError, "synthetic spawn failure"):
                boundary.start("speech", VoiceSettings())
        self.assertIsNone(boundary.process)
        self.assertIsNone(boundary.commands)
        self.assertIsNone(boundary.outbox)
        self.assertIsNone(boundary.spectrum_control)
        for channel in channels:
            channel.close.assert_called_once()
        boundary.stop()  # Failed startup must leave an idempotently closed boundary.
        process.join.assert_not_called()
        process.terminate.assert_not_called()
        process.close.assert_called_once()

    def test_partial_channel_allocation_failure_is_recoverable(self):
        boundary = AudioProcess()
        first = Mock()
        with patch.object(boundary.context, "Queue", side_effect=[first, OSError("queue allocation")]):
            with self.assertRaisesRegex(OSError, "queue allocation"):
                boundary.start("capture", VoiceSettings())
        self.assertIsNone(boundary.outbox)
        self.assertIsNone(boundary.commands)
        self.assertIsNone(boundary.process)
        first.close.assert_called_once()
        boundary.stop()

    def test_shared_control_or_process_allocation_failure_closes_both_channels(self):
        for allocation in ("Value", "Process"):
            with self.subTest(allocation=allocation):
                boundary = AudioProcess()
                channels = [Mock(), Mock()]
                with patch.object(boundary.context, "Queue", side_effect=channels), \
                        patch.object(boundary.context, allocation, side_effect=OSError("allocation failed")):
                    with self.assertRaisesRegex(OSError, "allocation failed"):
                        boundary.start("speech", VoiceSettings())
                self.assertIsNone(boundary.process)
                self.assertIsNone(boundary.outbox)
                self.assertIsNone(boundary.commands)
                self.assertIsNone(boundary.spectrum_control)
                for channel in channels:
                    channel.close.assert_called_once()

    def test_invalid_kind_allocates_no_channel_and_preserves_existing_worker(self):
        boundary = AudioProcess()
        existing = boundary.process = Mock(pid=42)
        with patch.object(boundary.context, "Queue") as create:
            with self.assertRaises(KeyError):
                boundary.start("unknown", VoiceSettings())
        create.assert_not_called()
        self.assertIs(boundary.process, existing)
        existing.terminate.assert_not_called()
        boundary.process = None

    def test_stubborn_process_retains_resources_for_explicit_stop_retry(self):
        boundary = AudioProcess()
        process = Mock(pid=42)
        process.is_alive.return_value = True
        boundary.process = process
        boundary.commands, boundary.outbox = Mock(), Mock()
        channels = (boundary.commands, boundary.outbox)
        control = boundary.spectrum_control = object()
        with self.assertRaisesRegex(RuntimeError, "processus audio"):
            boundary.stop()
        self.assertIs(boundary.process, process)
        self.assertIs(boundary.spectrum_control, control)
        self.assertEqual((boundary.commands, boundary.outbox), channels)
        process.close.assert_not_called()
        for channel in channels:
            channel.close.assert_not_called()
        process.is_alive.return_value = False
        boundary.stop()
        self.assertIsNone(boundary.process)
        self.assertIsNone(boundary.commands)
        self.assertIsNone(boundary.outbox)
        self.assertIsNone(boundary.spectrum_control)
        for channel in channels:
            channel.close.assert_called_once()

    def test_ten_real_spawn_stop_cycles_after_failed_spawn_leave_no_child(self):
        boundary = AudioProcess()
        children_before = {child.pid for child in mp.active_children()}
        try:
            # Exercise the real unstarted multiprocessing object, not just mocks.
            with patch("multiprocessing.process.BaseProcess.start", side_effect=OSError("spawn unavailable")):
                with self.assertRaisesRegex(OSError, "spawn unavailable"):
                    boundary.start("speech", VoiceSettings())
            with patch("jarvis.voice_runtime.speech_worker", _idle_audio_child):
                for generation in range(10):
                    boundary.start("speech", VoiceSettings(), generation)
                    events = []
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        events.extend(boundary.poll())
                        if any(event.kind == "probe_ready" for event in events):
                            break
                        time.sleep(.01)
                    self.assertEqual([(event.kind, event.generation) for event in events],
                                     [("probe_ready", generation)])
                    self.assertTrue(boundary.alive())
                    boundary.stop()
                    self.assertIsNone(boundary.process)
                    self.assertIsNone(boundary.commands)
                    self.assertIsNone(boundary.outbox)
                    self.assertIsNone(boundary.spectrum_control)
                    self.assertFalse(boundary.poll())
                    self.assertFalse(boundary.send("stale command"))
                    self.assertEqual({child.pid for child in mp.active_children()}, children_before)
        finally:
            boundary.stop()
        self.assertEqual({child.pid for child in mp.active_children()}, children_before)


if __name__ == "__main__":
    unittest.main()
