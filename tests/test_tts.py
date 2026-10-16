import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jarvis.tts import PiperSpeech, SentenceBuffer
from jarvis.voice_config import VOICES, VoiceSettings


class SegmentTests(unittest.TestCase):
    def test_sentence_stream_and_final_fragment(self):
        buffer = SentenceBuffer()
        self.assertEqual(buffer.feed("Bonjour"), [])
        self.assertEqual(buffer.feed(" ! Comment ça"), ["Bonjour !"])
        self.assertEqual(buffer.feed(" va ?"), ["Comment ça va ?"])
        self.assertEqual(buffer.feed("Dernier mot", final=True), ["Dernier mot"])
        self.assertEqual(buffer.pending, "")

    def test_long_text_bounded_without_loss(self):
        text = "mot " * 1000
        buffer = SentenceBuffer()
        segments = buffer.feed(text, final=True)
        self.assertTrue(all(len(s) <= 240 for s in segments))
        self.assertEqual(' '.join(segments).split(), text.split())

    def test_missing_voice_is_explicit_no_download(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "absente"):
                PiperSpeech(VoiceSettings(models_dir=root))


@unittest.skipUnless(importlib.util.find_spec("piper"), "Piper non installé")
class PiperContractTests(unittest.TestCase):
    def test_two_distinct_voice_files_speed_and_original_sample_rate(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "piper"
            folder.mkdir()
            for voice in VOICES:
                (folder / (voice + ".onnx")).touch()
                (folder / (voice + ".onnx.json")).touch()
                with patch("piper.PiperVoice.load") as load:
                    load.return_value.synthesize.return_value = [SimpleNamespace(audio_float_array=[0.2], sample_rate=44100)]
                    engine = PiperSpeech(VoiceSettings(models_dir=root, voice=voice, speed=1.25))
                    pcm = list(engine.synthesize("Bonjour"))[0]
                    self.assertEqual(pcm.sample_rate, 44100)
                    self.assertTrue(load.call_args.args[0].endswith(voice + ".onnx"))
                    self.assertFalse(load.call_args.kwargs["use_cuda"])
                    self.assertAlmostEqual(engine.config.length_scale, 0.8)
