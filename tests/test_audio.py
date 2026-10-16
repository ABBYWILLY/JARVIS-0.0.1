import importlib.util
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock
from jarvis.audio import FRAME, RATE, TurnDetector, signal_view
from jarvis.voice_config import VoiceSettings


class TurnTests(unittest.TestCase):
    def test_silence_and_click_never_create_turn(self):
        detector = TurnDetector(silence_ms=320)
        for i in range(200):
            self.assertEqual(detector.feed([0.0] * FRAME, 0.99 if i == 20 else 0), [])
        self.assertFalse(detector.speaking)
        self.assertEqual(len(detector.frames), 0)

    def test_hesitation_preroll_end_and_reset(self):
        detector = TurnDetector(silence_ms=320)
        events = []
        for probability in [0] * 8 + [0.9] * 10 + [0] * 4 + [0.9] * 8 + [0] * 10:
            events.extend(detector.feed([0.1] * FRAME, probability))
        self.assertEqual([e.kind for e in events], ["speech_start", "utterance"])
        self.assertGreater(len(events[1].payload), 20 * FRAME)
        self.assertFalse(detector.speaking)

    def test_long_turn_bounded(self):
        detector = TurnDetector(max_seconds=1)
        events = []
        for _ in range(32):
            events.extend(detector.feed([0.1] * FRAME, 0.9))
        utterances = [e for e in events if e.kind == "utterance"]
        self.assertEqual(len(utterances), 1)
        self.assertLessEqual(len(utterances[0].payload), RATE)

    def test_waveform_is_real_zero_and_nonzero_signal(self):
        self.assertEqual(signal_view([0] * 512)["rms"], 0)
        view = signal_view([0.25] * 512)
        self.assertAlmostEqual(view["rms"], 0.25)
        self.assertTrue(all(v == 0.25 for v in view["wave"]))

    def test_settings_bounds_and_legacy_defaults(self):
        self.assertEqual(VoiceSettings().validate().acoustic_mode, "speakers")
        with self.assertRaises(ValueError):
            VoiceSettings(speed=0).validate()

    def test_failed_capture_start_closes_device(self):
        from jarvis.audio import Microphone
        microphone = object.__new__(Microphone)
        microphone.stream = Mock()
        microphone.stream.start.side_effect = OSError("device disconnected")
        with self.assertRaises(OSError):
            microphone.__enter__()
        microphone.stream.close.assert_called_once()


@unittest.skipUnless(importlib.util.find_spec("faster_whisper"), "Dépendances vocales non installées")
class RealVadTests(unittest.TestCase):
    def test_stt_contract_local_only_french_cpu(self):
        from jarvis.audio import FrenchWhisper
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "absent"):
                FrenchWhisper(directory)
            (Path(directory) / "model.bin").touch()
            with patch("faster_whisper.WhisperModel") as model:
                model.return_value.transcribe.return_value = ([SimpleNamespace(text=" Bonjour ", no_speech_prob=0.1)], None)
                stt = FrenchWhisper(directory, threads=2)
                self.assertEqual(stt.transcribe([0.0] * RATE), "Bonjour")
                self.assertTrue(model.call_args.kwargs["local_files_only"])
                self.assertEqual(model.call_args.kwargs["device"], "cpu")
                self.assertEqual(model.return_value.transcribe.call_args.kwargs["language"], "fr")

    def test_packaged_silero_onnx_silence_and_reset(self):
        from jarvis.audio import SileroFrames
        vad = SileroFrames()
        probabilities = [vad.probability([0] * FRAME) for _ in range(20)]
        self.assertTrue(all(0 <= p < 0.6 for p in probabilities))
        first = probabilities[0]
        vad.reset()
        self.assertAlmostEqual(vad.probability([0] * FRAME), first, places=5)
