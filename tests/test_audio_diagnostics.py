"""Real temporary WAVs; all model inference below is explicitly simulated."""
import io
import json
import math
import os
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jarvis.audio_diagnostics import REFERENCE_PHRASES, main, read_wav, save_wav, signal_quality, word_error
from jarvis.tts import PCM


class SignalQualityTests(unittest.TestCase):
    def test_measured_signal_and_boundary_hints(self):
        samples = [0.0] * 320 + [0.5, -0.5] * 160 + [0.0] * 320
        result = signal_quality(samples)
        self.assertAlmostEqual(result["rms"], math.sqrt(1 / 12))
        self.assertEqual(result["peak"], 0.5)
        self.assertEqual(result["duration_ms"], 60)
        self.assertEqual(result["clipped_percent"], 0)
        self.assertEqual(result["dc_offset"], 0)
        self.assertFalse(result["possible_cut_start"])
        self.assertFalse(result["possible_cut_end"])
        active = signal_quality([0.25] * 320)
        self.assertTrue(active["possible_cut_start"])
        self.assertTrue(active["possible_cut_end"])
        self.assertEqual(active["dc_offset"], 0.25)

    def test_clipping_empty_audio_and_rate_validation(self):
        self.assertEqual(signal_quality([-1, 0, 1, 0])["clipped_percent"], 50)
        empty = signal_quality([])
        self.assertEqual(empty["rms"], 0)
        self.assertEqual(empty["duration_ms"], 0)
        self.assertFalse(empty["possible_cut_start"])
        self.assertFalse(empty["possible_cut_end"])
        self.assertEqual(signal_quality([0] * 80, rate=8000)["duration_ms"], 10)
        for rate in (0, -1, 16000.5, True):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                signal_quality([], rate)
        for sample in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                signal_quality([sample])


class WavTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_real_pcm16_round_trip_and_exclusive_creation(self):
        path = self.root / "échantillon.wav"
        original = [-1.2, -1.0, -0.25, 0, 0.25, 0.999, 1.2]
        save_wav(path, original)
        with wave.open(str(path), "rb") as source:
            self.assertEqual((source.getnchannels(), source.getsampwidth(), source.getframerate()), (1, 2, 16000))
        actual = read_wav(path)
        self.assertEqual(len(actual), len(original))
        for expected, sample in zip(original, actual):
            self.assertAlmostEqual(sample, min(32767 / 32768, max(-1, expected)), delta=1 / 32768)
        preserved = path.read_bytes()
        with self.assertRaises(FileExistsError):
            save_wav(path, [0.5])
        self.assertEqual(path.read_bytes(), preserved)

    def test_empty_wav_and_invalid_samples_do_not_create_a_file(self):
        save_wav(self.root / "empty.wav", [])
        self.assertEqual(read_wav(self.root / "empty.wav"), [])
        path = self.root / "invalid.wav"
        with self.assertRaises(ValueError):
            save_wav(path, [float("nan")])
        self.assertFalse(path.exists())

    def test_rejects_wrong_format_and_truncated_data(self):
        for channels, width, rate in ((2, 2, 16000), (1, 1, 16000), (1, 2, 8000)):
            path = self.root / f"wrong-{channels}-{width}-{rate}.wav"
            with wave.open(str(path), "wb") as destination:
                destination.setparams((channels, width, rate, 0, "NONE", "not compressed"))
                destination.writeframes(b"\0" * channels * width * 10)
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "PCM16 mono"):
                read_wav(path)
        path = self.root / "truncated.wav"
        save_wav(path, [0.1] * 10)
        path.write_bytes(path.read_bytes()[:-2])
        with self.assertRaisesRegex(ValueError, "tronqué"):
            read_wav(path)
        path.write_bytes(b"not a WAV")
        with self.assertRaisesRegex(ValueError, "WAV invalide"):
            read_wav(path)


class WordErrorTests(unittest.TestCase):
    def test_french_unicode_punctuation_case_and_accents(self):
        result = word_error("L’ÉTÉ, à côté : vingt-trois !", "l'e\u0301te\u0301 à côté vingt trois")
        self.assertEqual(result["words"], 6)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["wer"], 0)
        self.assertEqual(word_error("été", "ete")["counts"]["substitutions"], 1)

    def test_levenshtein_counts_deletions_insertions_and_substitutions(self):
        result = word_error("bonjour le monde", "bonjour ce monde demain")
        self.assertEqual(result, {"counts": {"substitutions": 1, "deletions": 0, "insertions": 1, "correct": 2},
                                  "errors": 2, "words": 3, "wer": 2 / 3})
        self.assertEqual(word_error("un deux trois", "un trois")["counts"]["deletions"], 1)
        self.assertEqual(word_error("a b c", "b c")["errors"], 1)
        self.assertGreater(word_error("un", "un deux trois")["wer"], 1)

    def test_empty_reference_and_fixed_french_prompts(self):
        self.assertEqual(word_error("", "")["wer"], 0)
        result = word_error("", "bonjour")
        self.assertIsNone(result["wer"])
        self.assertEqual(result["counts"]["insertions"], 1)
        self.assertEqual(word_error("bonjour", "")["counts"]["deletions"], 1)
        self.assertIsInstance(REFERENCE_PHRASES, tuple)
        self.assertEqual(len(REFERENCE_PHRASES), 5)
        self.assertTrue(all(isinstance(phrase, str) and phrase.strip() for phrase in REFERENCE_PHRASES))


class SimulatedModelCliTests(unittest.TestCase):
    """Exercise command orchestration only; these tests perform no recognition."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_corpus_uses_one_simulated_engine_relative_wavs_and_global_wer(self):
        recordings = self.root / "recordings"
        recordings.mkdir()
        save_wav(recordings / "one.wav", [0.125] * 160)
        save_wav(recordings / "two.wav", [-0.25] * 320)
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps([
            {"wav": "recordings/one.wav", "reference": "Bonjour le monde"},
            {"wav": "recordings/two.wav", "reference": "À bientôt"},
        ]), encoding="utf-8-sig")  # Windows editors may include a UTF-8 BOM.
        before = {path.relative_to(self.root) for path in self.root.rglob("*")}
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("jarvis.audio.FrenchWhisper") as model, redirect_stdout(stdout), redirect_stderr(stderr):
            model.return_value.transcribe.side_effect = ["bonjour monde", "à très bientôt"]
            self.assertEqual(main(["--corpus", str(manifest), "--models-dir", str(self.root / "models")]), 0)
        model.assert_called_once_with((self.root / "models" / "whisper").resolve())
        self.assertEqual(model.return_value.transcribe.call_count, 2)
        self.assertEqual(len(model.return_value.transcribe.call_args_list[0].args[0]), 160)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["global"]["words"], 5)
        self.assertEqual(report["global"]["errors"], 2)
        self.assertEqual(report["global"]["wer"], 0.4)
        self.assertEqual(report["global"]["audio_ms"], 30)
        self.assertEqual(report["results"][1]["hypothesis"], "à très bientôt")
        self.assertEqual(report["results"][0]["wav"], str((recordings / "one.wav").resolve()))
        self.assertGreaterEqual(report["model_load_ms"], 0)
        self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
        self.assertEqual(before, {path.relative_to(self.root) for path in self.root.rglob("*")})
        self.assertEqual(stderr.getvalue(), "")

    def test_tts_benchmark_simulated_engines_two_loads_against_one(self):
        stdout = io.StringIO()
        with patch("jarvis.tts.PiperSpeech") as model, redirect_stdout(stdout):
            model.return_value.synthesize.side_effect = [[PCM([0.1] * 16, 16000), PCM([0.2] * 8, 16000)] for _ in range(4)]
            self.assertEqual(main(["--benchmark-tts", "--models-dir", str(self.root)]), 0)
        self.assertEqual(model.call_count, 3)
        self.assertEqual(model.return_value.synthesize.call_count, 4)
        self.assertTrue(all(call.args == (REFERENCE_PHRASES[0],) for call in model.return_value.synthesize.call_args_list))
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["baseline"]["loads"], 2)
        self.assertEqual(report["reused"]["loads"], 1)
        for strategy in ("baseline", "reused"):
            self.assertEqual(len(report[strategy]["turns"]), 2)
            for turn in report[strategy]["turns"]:
                self.assertEqual(turn["samples"], 24)
                self.assertEqual(turn["sample_rates"], [16000])
                self.assertGreaterEqual(turn["total_pcm_ms"], turn["first_pcm_ms"])
        self.assertIsNone(report["reused"]["turns"][1]["load_ms"])
        self.assertTrue(report["reused"]["turns"][1]["reused"])
        self.assertIn("sortie physique", " ".join(report["limitations"]))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_local_models_fail_explicitly_without_output_or_download(self):
        save_wav(self.root / "one.wav", [0.0] * 160)
        manifest = self.root / "manifest.json"
        manifest.write_text('[{"wav":"one.wav","reference":"bonjour"}]', encoding="utf-8")
        for mode in (["--corpus", str(manifest)], ["--benchmark-tts"]):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(mode=mode), redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as exited:
                main([*mode, "--models-dir", str(self.root / "missing")])
            self.assertEqual(exited.exception.code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("absent", stderr.getvalue())
            self.assertFalse((self.root / "missing").exists())

    def test_invalid_manifest_and_exclusive_cli_modes(self):
        manifest = self.root / "invalid.json"
        for value in ({"wav": "one.wav"}, [], [{"wav": "one.wav", "reference": 12}]):
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with patch("jarvis.audio.FrenchWhisper") as model, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--corpus", str(manifest), "--models-dir", str(self.root)])
            model.assert_not_called()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["--corpus", str(manifest), "--benchmark-tts", "--models-dir", str(self.root)])


if __name__ == "__main__":
    unittest.main()
