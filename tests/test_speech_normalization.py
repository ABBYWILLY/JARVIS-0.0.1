"""Speech-only French rules and the actual Piper configuration contract."""
import importlib.util
import pickle
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis.richtext import SpeechBuffer, parse_text
from jarvis.speech_normalization import french_integer, normalize_french_speech
from jarvis.tts import PiperSpeech, SentenceBuffer, SpeechText
from jarvis.voice_config import VoiceSettings


class FrenchSpeechTests(unittest.TestCase):
    def test_cardinals_include_french_irregular_and_large_values(self):
        expected = {0: "zéro", 21: "vingt et un", 71: "soixante et onze", 80: "quatre-vingts",
                    81: "quatre-vingt-un", 200: "deux cents", 201: "deux cent un",
                    80_000: "quatre-vingt mille", 200_000: "deux cent mille",
                    1_000_001: "un million un", -32: "moins trente-deux"}
        for number, words in expected.items():
            with self.subTest(number=number):
                self.assertEqual(french_integer(number), words)

    def test_decimals_preserve_fractional_zeros_and_sign(self):
        self.assertEqual(normalize_french_speech("Valeurs : -0,05 ; +2.140 ; 1 234."),
                         "Valeurs : moins zéro virgule zéro cinq ; plus deux virgule un quatre zéro ; mille deux cent trente-quatre.")
        self.assertEqual(normalize_french_speech("Code 0012."), "Code zéro zéro un deux.")

    def test_amounts_speak_currency_and_cents_without_latex_confusion(self):
        self.assertEqual(normalize_french_speech(parse_text("**Prix** $12.50 et 1,01 €, puis 1 $.").speech),
                         "Prix douze dollars et cinquante centimes et un euro et un centime, puis un dollar.")
        self.assertEqual(normalize_french_speech("£2,00 ; -12,50 € ; 1,5 €"),
                         "deux livres sterling ; moins douze euros et cinquante centimes ; un virgule cinq euro")
        self.assertEqual(normalize_french_speech("£1,01 et 1 £"), "une livre sterling et un centime et une livre sterling")
        spoken = normalize_french_speech(parse_text(r"\(\frac{12}{2} = 6\)").speech)
        self.assertIn("fraction de douze sur deux égal à six", spoken)
        self.assertEqual(normalize_french_speech(parse_text("$1 234,50 et $-12,05.").speech),
                         "mille deux cent trente-quatre dollars et cinquante centimes et moins douze dollars et cinq centimes.")

    def test_metre_is_distinct_from_title_and_scientific_value_stays_whole(self):
        self.assertEqual(normalize_french_speech("M. Martin parcourt 10 m. chaque jour, puis 1 m."),
                         "monsieur Martin parcourt dix mètres. chaque jour, puis un mètre.")
        self.assertEqual(normalize_french_speech("La mesure est 3e-4, puis -2.05E+3."),
                         "La mesure est trois fois dix puissance moins quatre, puis moins deux virgule zéro cinq fois dix puissance plus trois.")
        self.assertEqual(normalize_french_speech("Valeur 4-2, article 3-4-1."), "Valeur 4-2, article 3-4-1.")

    def test_valid_dates_hours_and_seconds_are_unambiguous(self):
        self.assertEqual(normalize_french_speech("Rdv le 01/02/2024 à 14 h 05. Le 2026-10-28 à 01:00:03."),
                         "rendez-vous le premier février deux mille vingt-quatre à quatorze heures cinq. Le vingt-huit octobre deux mille vingt-six à une heure et trois secondes.")
        self.assertEqual(normalize_french_speech("À 0h et 1h."), "À zéro heures et une heure.")

    def test_invalid_dates_and_times_and_technical_identifiers_remain_literal(self):
        source = "31/02/2024 25:70 Qwen3.5 RTX3070 version 3.12 Python 3.12 192.168.1.1"
        self.assertEqual(normalize_french_speech(source), source)
        self.assertEqual(normalize_french_speech("https://example.org/12.5"), "https://example.org/12.5")

    def test_known_abbreviations_and_acronyms_leave_ordinary_french_unchanged(self):
        self.assertEqual(normalize_french_speech("M. Dupont, Dr. Martin, Mme. Durand. CPU, GPU, USB, API ; cpu, ram."),
                         "monsieur Dupont, docteur Martin, madame Durand. cé pé u, gé pé u, u ès bé, a pé i ; cpu, ram.")
        source = "Élève, cœur et forêt ; oui ? Bien sûr !"
        self.assertEqual(normalize_french_speech(source), source)

    def test_original_display_and_semantic_events_remain_unchanged(self):
        source = "**Rdv** le 28/10/2026, 12,50 € 😊."
        document = parse_text(source)
        events = document.events
        spoken = normalize_french_speech(document.speech)
        self.assertEqual(document.original, source)
        self.assertIn("12,50 € 😊", document.text)
        self.assertIn("douze euros et cinquante centimes", spoken)
        self.assertNotIn("😊", spoken)
        self.assertEqual(document.events, events)
        self.assertEqual(source[events[-1].start:events[-1].end], events[-1].value)
        self.assertEqual(normalize_french_speech(spoken), spoken)

    def test_huge_magnitude_is_preserved_without_integer_conversion_overflow(self):
        source = "9" * 5000
        self.assertEqual(normalize_french_speech(source), source)
        self.assertEqual(normalize_french_speech(source + " €"), source + " €")

    def test_stream_does_not_cut_titles_initials_decimal_or_time_prefix(self):
        for prefix in ("Dr.", "Mme.", "M.", "J.", "p.", "c.", "La valeur 2.", "À 14:"):
            with self.subTest(prefix=prefix):
                self.assertEqual(SpeechBuffer().feed(prefix), [])
                self.assertEqual(SentenceBuffer().feed(prefix), [])
        buffer = SpeechBuffer()
        self.assertEqual(buffer.feed("Dr."), [])
        segments = buffer.feed(" Martin arrive à 14:05. ")
        self.assertEqual([segment.text for segment in segments], ["Dr. Martin arrive à 14:05."])

    def test_french_stream_and_complete_normalization_keep_same_meaning(self):
        source = "Dr. Martin indique 12,50 € le 01/02/2024 à 14:05. La mesure vaut 2.14. 😊"
        buffer, segments = SpeechBuffer(), []
        for char in source:
            segments.extend(buffer.feed(char))
        segments.extend(buffer.feed("", final=True))
        spoken = " ".join(normalize_french_speech(segment.text) for segment in segments if segment.text)
        self.assertEqual(spoken, normalize_french_speech(parse_text(source).speech))
        for segment in segments:
            self.assertEqual(segment.original, source[segment.start:segment.end])

    def test_multi_part_abbreviation_waits_and_sentence_stop_is_retained(self):
        source = "Des exemples, p. ex. ce calcul, c.-à-d. une somme, etc. Ensuite nous concluons."
        buffer, segments = SpeechBuffer(), []
        for char in source:
            segments.extend(buffer.feed(char))
        segments.extend(buffer.feed("", final=True))
        self.assertEqual(" ".join(normalize_french_speech(segment.text) for segment in segments),
                         normalize_french_speech(parse_text(source).speech))
        self.assertIn("et cetera. Ensuite", normalize_french_speech(source))

    def test_first_long_sentence_can_start_at_a_safe_clause(self):
        source = "Bonjour, voici une première explication claire, "
        segments = SpeechBuffer().feed(source)
        self.assertEqual([segment.text for segment in segments], [source.strip()])
        buffer = SpeechBuffer()
        source = "Explication " * 7 + "1 234,50 euros pour finir."
        segments = buffer.feed(source, final=True)
        self.assertEqual("".join(segment.original for segment in segments), source)
        self.assertTrue(any("1 234,50 euros" in segment.original for segment in segments))


@dataclass
class _SynthesisConfig:
    length_scale: float = 1.


class PiperProsodyTests(unittest.TestCase):
    def engine(self, folder, speed=1.):
        profile = VoiceSettings(models_dir=folder, speed=speed)
        path = Path(folder) / "piper" / (profile.voice + ".onnx")
        path.parent.mkdir(exist_ok=True)
        path.touch()
        path.with_suffix(".onnx.json").touch()
        return PiperSpeech(profile)

    def modules(self, voice):
        return {"piper": SimpleNamespace(PiperVoice=SimpleNamespace(load=Mock(return_value=voice))),
                "piper.config": SimpleNamespace(SynthesisConfig=_SynthesisConfig),
                "onnxruntime": SimpleNamespace(disable_telemetry_events=Mock())}

    def test_per_segment_rate_uses_real_length_scale_without_reloading_voice(self):
        voice = Mock()
        voice.synthesize.return_value = [SimpleNamespace(audio_float_array=[.2], sample_rate=22050)]
        modules = self.modules(voice)
        with tempfile.TemporaryDirectory() as folder, patch.dict("sys.modules", modules):
            engine = self.engine(folder, speed=1.25)
            first = list(engine.synthesize(SpeechText("12 euros.", rate=.8)))[0]
            self.assertEqual(first.sample_rate, 22050)
            self.assertEqual(voice.synthesize.call_args.args, ("douze euros.",))
            self.assertAlmostEqual(voice.synthesize.call_args.kwargs["syn_config"].length_scale, 1.)
            list(engine.synthesize(SpeechText("Suite.", rate=4.)))
            self.assertEqual(voice.synthesize.call_args.kwargs["syn_config"].length_scale, .5)
            list(engine.synthesize(SpeechText("Suite.", rate=.25)))
            self.assertEqual(voice.synthesize.call_args.kwargs["syn_config"].length_scale, 2.)
            self.assertEqual(engine.config.length_scale, .8)
        modules["piper"].PiperVoice.load.assert_called_once()

    def test_invalid_prosody_does_not_reach_piper(self):
        voice = Mock()
        with tempfile.TemporaryDirectory() as folder, patch.dict("sys.modules", self.modules(voice)):
            engine = self.engine(folder)
            for options in ({"rate": True}, {"rate": float("nan")}, {"rate": .1}, {"rate": 5},
                            {"pause_ms": -1}, {"pause_ms": 301}, {"pause_ms": True}):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, "Prosodie"):
                    list(engine.synthesize(SpeechText("Bonjour", **options)))
        voice.synthesize.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy vocal optionnel absent")
    def test_profile_pause_is_real_pcm_zeros_and_does_not_prefetch_next_chunk(self):
        import numpy as np
        produced = []

        def chunks(*args, **kwargs):
            produced.append(1)
            yield SimpleNamespace(audio_float_array=np.array([.2, .3], dtype="float32"), sample_rate=16000)
            produced.append(2)
            yield SimpleNamespace(audio_float_array=np.array([.4], dtype="float32"), sample_rate=16000)

        voice = Mock()
        voice.synthesize.side_effect = chunks
        with tempfile.TemporaryDirectory() as folder, patch.dict("sys.modules", self.modules(voice)):
            engine = self.engine(folder)
            stream = engine.synthesize(SpeechText("Bonjour. Suite.", pause_ms=80))
            first = next(stream)
            self.assertEqual(produced, [1])
            self.assertEqual(len(first.samples), 2 + 1280)
            self.assertTrue(np.all(first.samples[2:] == 0))
            self.assertEqual(first.sample_rate, 16000)
            second = next(stream)
            self.assertEqual(produced, [1, 2])
            self.assertEqual(len(second.samples), 1 + 1280)

    def test_spawn_retains_per_segment_prosody_and_source_metadata(self):
        command = SpeechText("douze euros.", original="**12 €**.", rate=.92, pause_ms=120)
        restored = pickle.loads(pickle.dumps(command))
        self.assertEqual(restored.__dict__, command.__dict__)
        self.assertEqual(restored.original, "**12 €**.")


if __name__ == "__main__":
    unittest.main()
