"""Opt-in real local models, never downloaded or substituted by fixtures."""
import os
import unittest
from dataclasses import replace


@unittest.skipUnless(os.environ.get("JARVIS_TEST_VOICE") == "1", "Modèles vocaux réels : définir JARVIS_TEST_VOICE=1")
class LiveVoiceTests(unittest.TestCase):
    def profile(self):
        from jarvis.voice_config import VoiceSettings
        return VoiceSettings(models_dir=os.environ.get("JARVIS_TEST_MODELS", ""))

    def test_both_real_french_voices_produce_different_non_silent_pcm(self):
        import numpy as np
        from jarvis.tts import PiperSpeech
        from jarvis.voice_config import VOICES
        waves = []
        for name in VOICES:
            chunks = list(PiperSpeech(replace(self.profile(), voice=name)).synthesize("Bonjour. Comment allez-vous aujourd’hui ?"))
            self.assertTrue(chunks)
            audio = np.concatenate([c.samples for c in chunks])
            self.assertGreater(len(audio), chunks[0].sample_rate * 0.2)
            self.assertGreater(float(np.max(np.abs(audio))), 0.001)
            waves.append(audio)
        self.assertFalse(np.array_equal(waves[0], waves[1]))

    def test_real_french_tts_stt_round_trip(self):
        import numpy as np
        import soxr
        from jarvis.audio import FrenchWhisper
        from jarvis.spectrum import normalized
        from jarvis.tts import PiperSpeech
        settings = self.profile()
        chunks = list(PiperSpeech(settings).synthesize("Bonjour. Comment allez-vous aujourd’hui ?"))
        audio = np.concatenate([soxr.resample(c.samples, c.sample_rate, 16000) for c in chunks])
        text = FrenchWhisper(settings.model_root / "whisper", settings.cpu_threads).transcribe(audio)
        self.assertIn("bonjour", normalized(text), text)
