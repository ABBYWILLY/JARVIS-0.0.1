"""Deterministic PCM doubles through the real capture loop, no physical mic/STT.

These regressions validate data flow and diagnostics only. They do not validate
Windows hardware, microphone permissions or a real Whisper model.
"""
import math
import importlib.util
import queue
import unittest
from unittest.mock import Mock, patch

from jarvis.audio import FRAME, signal_view
from jarvis.presence import PresenceModel
from jarvis.voice_config import VoiceSettings
from jarvis.voice_runtime import capture_worker


class EndCapture(BaseException):
    """Stop the otherwise live worker without converting it into an audio error."""


DEVICE_KEY = "MME | USB Condenser"
DEVICE = {"index": 7, "name": "USB Condenser", "hostapi": "MME",
          "channels": 1, "dtype": "float32", "native_rate": 48000}
EMPTY_BATCH = object()  # SOXR can need more native PCM before emitting 512 samples.


def pcm(amplitude):
    return [amplitude * math.sin(2 * math.pi * sample / 79) for sample in range(FRAME)]


def run_health(readings, *, probability=.05, muted=False, whisper_error=None):
    """None = read timeout; a sequence = one real-shaped 16 kHz PCM frame."""
    messages, commands = queue.Queue(), queue.Queue()
    if muted:
        commands.put({"kind": "mute", "value": True})
    clock = [10.]
    calls = []

    def monotonic():
        clock[0] += .1
        return clock[0]

    class Microphone:
        native_rate = 48000

        def __init__(self, selected):
            self.readings = iter(readings)
            calls.append(("open", selected))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls.append(("close",))

        def diagnostic_info(self):
            return {"selected_device": DEVICE_KEY, "opened_device": dict(DEVICE),
                    "native_rate": self.native_rate, "callback_status": "", "dropped_frames": 0}

        def read(self):
            try:
                item = next(self.readings)
            except StopIteration:
                raise EndCapture
            if item is None:
                raise queue.Empty
            if item is EMPTY_BATCH:
                return []
            return [item]

    vad = Mock()
    vad.probability.return_value = probability
    whisper = Mock()
    with patch("jarvis.audio.Microphone", Microphone), \
         patch("jarvis.audio.SileroFrames", return_value=vad), \
         patch("jarvis.audio.FrenchWhisper", side_effect=whisper_error, return_value=whisper), \
         patch("jarvis.voice_runtime.time.monotonic", side_effect=monotonic):
        try:
            capture_worker(messages, commands, VoiceSettings(input_device=DEVICE_KEY).to_dict())
        except EndCapture:
            pass
    return list(messages.queue), calls, vad, whisper


class CaptureHealthTests(unittest.TestCase):
    def test_real_rms_and_wave_are_not_replaced_with_zero_when_vad_rejects_speech(self):
        frames = [pcm(.02), pcm(.2), pcm(.02)]
        events, _, vad, whisper = run_health(frames)
        levels = [event.payload for event in events if event.kind == "mic_level"]
        self.assertEqual(len(levels), len(frames))
        for level, samples in zip(levels, frames):
            expected = signal_view(samples)
            self.assertAlmostEqual(level["rms"], expected["rms"])
            self.assertEqual(level["wave"], expected["wave"])
            self.assertEqual(level["vad"], .05)
            self.assertFalse(level["speaking"])
        self.assertGreater(levels[1]["rms"], levels[0]["rms"] * 9)
        self.assertAlmostEqual(levels[-1]["rms"], levels[0]["rms"])
        self.assertEqual(vad.probability.call_count, len(frames))
        whisper.transcribe.assert_not_called()
        self.assertNotIn("speech_start", [event.kind for event in events])

    def test_listening_reports_selected_and_actually_opened_device(self):
        events, calls, _, _ = run_health([pcm(.02)])
        listening = next(event.payload for event in events if event.kind == "listening")
        self.assertEqual(listening["selected_device"], DEVICE_KEY)
        self.assertEqual(listening["opened_device"], DEVICE)
        self.assertEqual(listening["native_rate"], 48000)
        self.assertEqual(listening["rate"], 16000)
        self.assertEqual(calls, [("open", DEVICE_KEY), ("close",)])

    def test_endpoint_diagnostics_expose_frame_calibration_without_changing_threshold(self):
        events, _, _, _ = run_health([pcm(.02)] * 5, probability=.59)
        diagnostic = next(event.payload for event in events if event.kind == "diagnostic")
        self.assertEqual(diagnostic["silence_target_ms"], 800)
        self.assertEqual(diagnostic["silence_elapsed_ms"], 0)
        self.assertEqual(diagnostic["onset_ms"], 160)
        self.assertFalse(diagnostic["resume_pending"])
        self.assertFalse(any(event.kind == "speech_start" for event in events))

    def test_open_capture_without_pcm_publishes_heartbeats_without_fabricated_zero_rms(self):
        for item in (None, EMPTY_BATCH):
            with self.subTest(read_timeout=item is None):
                events, _, vad, whisper = run_health([item] * 20)
                diagnostics = [event.payload for event in events if event.kind == "diagnostic"
                               and event.payload.get("capture_status") == "waiting_for_pcm"]
                self.assertGreaterEqual(len(diagnostics), 2)
                for detail in diagnostics:
                    self.assertIsNone(detail["rms"])
                    self.assertIsNone(detail["vad"])
                    self.assertIsNone(detail["last_frame_at"])
                    self.assertEqual(detail["frames_received"], 0)
                    self.assertEqual(detail["opened_device"], DEVICE)
                self.assertNotIn("mic_level", [event.kind for event in events])
                vad.probability.assert_not_called()
                whisper.transcribe.assert_not_called()

    def test_timeout_after_pcm_keeps_last_frame_identity_and_marks_data_unavailable(self):
        events, _, _, _ = run_health([pcm(.12)] + [None] * 20)
        diagnostics = [event.payload for event in events if event.kind == "diagnostic"
                       and event.payload.get("capture_status") == "waiting_for_pcm"]
        self.assertGreaterEqual(len(diagnostics), 2)
        timestamps = [detail["last_frame_at"] for detail in diagnostics]
        self.assertIsNotNone(timestamps[0])
        self.assertEqual(len(set(timestamps)), 1)
        self.assertTrue(all(detail["rms"] is None for detail in diagnostics))
        self.assertTrue(all(detail["frames_received"] == 1 for detail in diagnostics))

    def test_suspension_keeps_real_diagnostics_without_voice_or_stt_events(self):
        events, _, vad, whisper = run_health([pcm(.12)] * 5, muted=True)
        diagnostics = [event.payload for event in events if event.kind == "diagnostic"
                       and event.payload.get("capture_status") == "suspended"]
        self.assertTrue(diagnostics)
        self.assertTrue(all(detail["rms"] > .05 for detail in diagnostics))
        self.assertTrue(all(detail["vad"] is None for detail in diagnostics))
        self.assertFalse(any(event.kind in {"mic_level", "speech_start", "transcribing"} for event in events))
        vad.probability.assert_not_called()
        whisper.transcribe.assert_not_called()

    def test_missing_whisper_model_reports_stage_and_never_claims_open_capture(self):
        events, calls, _, _ = run_health([], whisper_error=ValueError("Modèle STT absent"))
        kinds = [event.kind for event in events]
        self.assertIn("capture_error", kinds)
        self.assertIn("error", kinds)
        failure = next(event.payload for event in events if event.kind == "capture_error")
        self.assertEqual(failure["stage"], "initialisation STT")
        self.assertIn("Modèle STT absent", failure["error"])
        self.assertNotIn("listening", kinds)
        self.assertEqual(calls, [])


class SignalTelemetryTests(unittest.TestCase):
    def test_high_frequency_pcm_retains_rms_and_a_real_visible_wave(self):
        # A mean of ten samples erases each complete 1.6 kHz period at 16 kHz.
        # This fixture reproduces that aliasing independently of VAD or devices.
        samples = [.1 * math.sin(2 * math.pi * 1600 * index / 16000)
                   for index in range(1600)]
        summary = signal_view(samples)
        self.assertAlmostEqual(summary["rms"], .1 / math.sqrt(2), places=12)
        self.assertLessEqual(len(summary["wave"]), 48)
        self.assertGreater(max(summary["wave"]), .08)
        self.assertLess(min(summary["wave"]), -.08)
        self.assertTrue(all(value in samples for value in summary["wave"]),
                        "The visual summary must use actual PCM extrema")
        model = PresenceModel()
        model.update_event("user_speaking", summary, now=1.)
        points = model.target_geometry(1000, 700, now=1.)
        self.assertGreater(max(y for _, y in points) - min(y for _, y in points), 1.)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "Dépendance PCM numpy non installée")
class MicrophoneHealthTests(unittest.TestCase):
    """Real callback/error handling with PortAudio/SOXR doubles, no hardware."""

    def setUp(self):
        import numpy as np
        self.np = np
        self.sd = Mock()
        self.sd.query_devices.return_value = {
            "name": "USB réellement ouvert", "hostapi": 0, "default_samplerate": 48000}
        self.sd.query_hostapis.return_value = {"name": "MME"}
        self.sd.RawInputStream.return_value.device = 7
        self.sd.RawInputStream.return_value.active = True
        self.soxr = Mock()
        self.soxr.ResampleStream.return_value.resample_chunk.side_effect = lambda pcm: pcm

    def microphone(self):
        from jarvis.audio import Microphone
        with patch.dict("sys.modules", {"sounddevice": self.sd, "soxr": self.soxr}):
            return Microphone(None)

    def callback(self, microphone, *, frames=FRAME, status=None, data=None):
        if data is None:
            data = self.np.ones(frames, dtype="float32").tobytes()
        self.sd.RawInputStream.call_args.kwargs["callback"](data, frames, None, status)

    def test_actual_stream_device_and_native_format_are_reported_without_requerying(self):
        microphone = self.microphone()
        self.sd.reset_mock()
        info = microphone.diagnostic_info()
        self.assertEqual(info["selected_device"], "Par défaut Windows")
        self.assertEqual(info["opened_device"], {
            "index": 7, "name": "USB réellement ouvert", "hostapi": "MME",
            "channels": 1, "dtype": "float32", "native_rate": 48000})
        self.sd.query_devices.assert_not_called()
        self.sd.query_hostapis.assert_not_called()
        info["opened_device"]["name"] = "Ne pas modifier le diagnostic source"
        self.assertEqual(microphone.diagnostic_info()["opened_device"]["name"], "USB réellement ouvert")

    def test_portaudio_status_reaches_read_error_and_health_without_silent_loss(self):
        microphone = self.microphone()
        self.callback(microphone, status="input overflow")
        with self.assertRaisesRegex(RuntimeError, "input overflow"):
            microphone.read()
        info = microphone.diagnostic_info()
        self.assertEqual(info["native_frames_received"], FRAME)
        self.assertIsNotNone(info["last_callback_at"])
        self.assertEqual(info["callback_status"], "input overflow")

    def test_queue_overflow_counts_lost_native_frames_and_stops_capture_explicitly(self):
        microphone = self.microphone()
        microphone.inbox = queue.Queue(maxsize=1)
        self.callback(microphone)
        self.callback(microphone)
        with self.assertRaisesRegex(RuntimeError, "File PCM native saturée"):
            microphone.read()
        info = microphone.diagnostic_info()
        self.assertEqual(info["dropped_frames"], FRAME)
        self.assertEqual(info["native_frames_received"], 2 * FRAME)

    def test_malformed_callback_buffer_is_reported_instead_of_silently_stopping_portaudio(self):
        microphone = self.microphone()
        self.callback(microphone, data=b"bad")
        with self.assertRaisesRegex(RuntimeError, "ValueError"):
            microphone.read()
        self.assertIn("ValueError", microphone.diagnostic_info()["callback_status"])

    def test_device_metadata_failure_closes_the_already_created_stream(self):
        self.sd.query_hostapis.side_effect = OSError("Périphérique retiré")
        with self.assertRaisesRegex(OSError, "Périphérique retiré"):
            self.microphone()
        self.sd.RawInputStream.return_value.close.assert_called_once()

    def test_close_is_attempted_even_if_abort_fails(self):
        microphone = self.microphone()
        microphone.stream.abort.side_effect = OSError("Abort refusé")
        with self.assertRaisesRegex(OSError, "Abort refusé"):
            microphone.__exit__()
        microphone.stream.close.assert_called_once()
        self.assertEqual(microphone.diagnostic_info()["capture_status"], "closed")


if __name__ == "__main__":
    unittest.main()
