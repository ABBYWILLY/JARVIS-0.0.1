import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis.tts import AudioPlayer, PCM, PiperSpeech, SentenceBuffer
from jarvis.voice_config import VOICES, VoiceSettings


class SegmentTests(unittest.TestCase):
    def test_first_phrase_starts_before_240_characters_without_losing_french_text(self):
        buffer = SentenceBuffer()
        text = "Je vous propose une réponse détaillée et précise qui commence sans ponctuation et garde tous les mots français "
        phrases = buffer.feed(text)
        self.assertTrue(phrases)
        self.assertLessEqual(len(phrases[0]), 96)
        phrases.extend(buffer.feed("jusqu’à la conclusion.", final=True))
        self.assertEqual(" ".join(phrases), (text + "jusqu’à la conclusion.").strip())

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


@unittest.skipUnless(importlib.util.find_spec("numpy") and importlib.util.find_spec("soxr"), "Audio natif non installé")
class PlaybackTimingTests(unittest.TestCase):
    def test_pcm_callbacks_report_same_first_dac_time_after_resampling(self):
        import numpy as np
        emitted = []

        class CallbackStop(Exception):
            pass

        class Stream:
            active = True

            def __init__(self, **options):
                self.options = options

            def __enter__(self):
                for _ in range(20):
                    try:
                        self.options["callback"](np.empty((128, 1), dtype="float32"), 128,
                            SimpleNamespace(outputBufferDacTime=100.03, currentTime=100), None)
                    except CallbackStop:
                        self.options["finished_callback"]()
                        return self
                raise AssertionError("Playback did not finish")

            def __exit__(self, *args):
                pass

        sd = SimpleNamespace(query_devices=Mock(return_value={"default_samplerate": 48000}),
                             OutputStream=Stream, CallbackStop=CallbackStop)
        with patch.dict("sys.modules", {"sounddevice": sd}), patch("jarvis.tts.resolve_device", return_value=7), \
                patch("jarvis.tts.time.monotonic", side_effect=[10 + i * 0.04 for i in range(20)]):
            AudioPlayer("selected output").play(PCM(np.full(160, 0.2, dtype="float32"), 16000), "Bonjour", emitted.append, 9)
        sd.query_devices.assert_called_once_with(7, "output")
        self.assertGreater(len(emitted), 1)
        self.assertTrue(all(e.kind == "played" and e.generation == 9 for e in emitted))
        self.assertTrue(all(abs(e.payload["started_at"] - 10.03) < 1e-6 for e in emitted))
        self.assertGreater(emitted[-1].payload["emitted_at"], emitted[0].payload["emitted_at"])
        self.assertEqual(emitted[-1].payload["fraction"], 1)
        self.assertGreater(emitted[0].payload["rms"], 0)
