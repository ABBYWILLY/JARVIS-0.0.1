"""Opt-in audio checks and local model measurements, without recording devices.

The first/last 20 ms energy flags are only hints of a possible cut: background
noise or speech near a boundary can trigger them. They do not prove truncation.
WAV export is explicit and exclusive; corpus/benchmark commands never save audio.
"""
import argparse
import json
import math
import operator
import os
import struct
import sys
import time
import unicodedata
import wave
from contextlib import redirect_stdout
from pathlib import Path


REFERENCE_PHRASES = (
    "Bonjour JARVIS, peux-tu me dire quelle heure il est ?",
    "J’aimerais préparer une réunion jeudi à quinze heures trente.",
    "Écoute bien : le café est à côté de la fenêtre ouverte.",
    "Il reste vingt-trois kilomètres avant d’arriver à Lyon.",
    "Arrête la lecture, puis explique-moi la prochaine étape.",
)


def _rate(rate):
    try:
        value = operator.index(rate)
    except TypeError as exc:
        raise ValueError("La fréquence audio doit être un entier positif.") from exc
    if isinstance(rate, bool) or value <= 0:
        raise ValueError("La fréquence audio doit être un entier positif.")
    return value


def _samples(samples):
    values = [float(sample) for sample in samples]
    if not all(math.isfinite(sample) for sample in values):
        raise ValueError("Les échantillons audio doivent être finis.")
    return values


def signal_quality(samples, rate=16000):
    """Measure normalized mono PCM; clipping means abs(sample) >= 0.999.

    Boundary flags mean RMS >= 0.01 in the first/last 20 ms (or the available
    samples for shorter audio). These heuristics are not evidence of a cut.
    """
    rate = _rate(rate)
    values = _samples(samples)
    count = len(values)

    def rms(part):
        return math.sqrt(math.fsum(sample * sample for sample in part) / len(part)) if part else 0.0

    edge = max(1, round(rate * 0.020))
    return {
        "rms": rms(values),
        "peak": max((abs(sample) for sample in values), default=0.0),
        "duration_ms": count * 1000 / rate,
        "clipped_percent": 100 * sum(abs(sample) >= 0.999 for sample in values) / count if count else 0.0,
        "dc_offset": math.fsum(values) / count if count else 0.0,
        "possible_cut_start": rms(values[:edge]) >= 0.01,
        "possible_cut_end": rms(values[-edge:]) >= 0.01,
    }


def save_wav(path, samples, rate=16000):
    """Explicitly create a mono PCM16 WAV; never overwrite an existing path.

    Samples outside [-1, 1] are saturated during PCM16 conversion. Invalid
    samples/rates are rejected before creating the destination.
    """
    rate = _rate(rate)
    values = _samples(samples)
    integers = [max(-32768, min(32767, round(max(-1, min(1, sample)) * 32768))) for sample in values]
    data = struct.pack(f"<{len(integers)}h", *integers)
    with Path(path).open("xb") as destination:
        with wave.open(destination, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(data)


def read_wav(path):
    """Return normalized samples from a complete, mono PCM16 16 kHz WAV."""
    try:
        with wave.open(str(path), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("WAV attendu : PCM16 mono à 16000 Hz, sans compression.")
            frames = source.getnframes()
            data = source.readframes(frames)
            if len(data) != frames * 2:
                raise ValueError("WAV tronqué : données PCM incomplètes.")
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"WAV invalide : {exc}") from exc
    return [sample[0] / 32768 for sample in struct.iter_unpack("<h", data)]


def _words(text):
    normalized = unicodedata.normalize("NFC", text).casefold()
    # Spaces for punctuation make curly/straight apostrophes and hyphens agree,
    # while retaining French accents ("été" is different from "ete").
    return "".join(" " if unicodedata.category(char).startswith("P") else char
                   for char in normalized).split()


def _error_report(counts, words):
    errors = counts["substitutions"] + counts["deletions"] + counts["insertions"]
    return {"counts": counts, "errors": errors, "words": words,
            "wer": errors / words if words else (0.0 if errors == 0 else None)}


def word_error(reference, hypothesis):
    """Word-level Levenshtein counts after NFC/casefold/punctuation handling.

    WER is a ratio and can exceed 1. A nonempty hypothesis against an empty
    reference has no defined ratio (None); two empty texts have WER 0.
    """
    expected, actual = _words(reference), _words(hypothesis)
    table = [list(range(len(actual) + 1))]
    for i, word in enumerate(expected, 1):
        row = [i]
        for j, other in enumerate(actual, 1):
            row.append(min(table[i - 1][j] + 1, row[j - 1] + 1,
                           table[i - 1][j - 1] + (word != other)))
        table.append(row)
    counts = {"substitutions": 0, "deletions": 0, "insertions": 0, "correct": 0}
    i, j = len(expected), len(actual)
    while i or j:
        if i and j and expected[i - 1] == actual[j - 1] and table[i][j] == table[i - 1][j - 1]:
            counts["correct"] += 1
            i, j = i - 1, j - 1
        elif i and j and table[i][j] == table[i - 1][j - 1] + 1:
            counts["substitutions"] += 1
            i, j = i - 1, j - 1
        elif i and table[i][j] == table[i - 1][j] + 1:
            counts["deletions"] += 1
            i -= 1
        else:
            counts["insertions"] += 1
            j -= 1
    return _error_report(counts, len(expected))


def _milliseconds(start, end):
    return round((end - start) * 1000, 3)


def _corpus_report(manifest_path, models_dir):
    from .audio import FrenchWhisper

    started_at = time.monotonic()
    manifest_path = Path(manifest_path).expanduser().resolve()
    with manifest_path.open(encoding="utf-8-sig") as source:
        manifest = json.load(source)
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Le manifeste doit être une liste JSON non vide de {wav, reference}.")
    for entry in manifest:
        if (not isinstance(entry, dict) or not isinstance(entry.get("wav"), str)
                or not entry["wav"].strip() or not isinstance(entry.get("reference"), str)):
            raise ValueError("Chaque entrée doit contenir wav (chemin) et reference (texte).")
    model_dir = Path(models_dir).expanduser().resolve() / "whisper"
    loading_at = time.monotonic()
    transcriber = FrenchWhisper(model_dir)
    load_ms = _milliseconds(loading_at, time.monotonic())
    results = []
    counts = {"substitutions": 0, "deletions": 0, "insertions": 0, "correct": 0}
    for entry in manifest:
        wav_path = (manifest_path.parent / entry["wav"]).resolve()
        samples = read_wav(wav_path)
        transcribing_at = time.monotonic()
        hypothesis = transcriber.transcribe(samples)
        transcription_ms = _milliseconds(transcribing_at, time.monotonic())
        error = word_error(entry["reference"], hypothesis)
        for key in counts:
            counts[key] += error["counts"][key]
        results.append({"wav": str(wav_path), "reference": entry["reference"], "hypothesis": hypothesis,
                        **error, "audio_ms": len(samples) * 1000 / 16000,
                        "transcription_ms": transcription_ms})
    return {
        "mode": "stt_corpus", "corpus": str(manifest_path), "model_dir": str(model_dir),
        "model_load_ms": load_ms, "results": results,
        "global": {**_error_report(counts, sum(row["words"] for row in results)),
                   "audio_ms": sum(row["audio_ms"] for row in results),
                   "transcription_ms": sum(row["transcription_ms"] for row in results)},
        "total_ms": _milliseconds(started_at, time.monotonic()),
        "limitations": ["Fichiers WAV et modèle locaux ; aucun microphone ni téléchargement.",
                        "Le WER dépend des références et ne mesure pas la latence de capture."],
    }


def _measure_tts_turn(speech, text, load_ms, reused):
    started_at = time.monotonic()
    first_pcm_ms = None
    samples = 0
    rates = set()
    for pcm in speech.synthesize(text):
        if not len(pcm.samples):
            continue
        if first_pcm_ms is None:
            first_pcm_ms = _milliseconds(started_at, time.monotonic())
        samples += len(pcm.samples)
        rates.add(pcm.sample_rate)
    total_pcm_ms = _milliseconds(started_at, time.monotonic())
    if not samples:
        raise ValueError("Piper n’a produit aucun échantillon PCM.")
    return {"load_ms": load_ms, "reused": reused, "first_pcm_ms": first_pcm_ms,
            "total_pcm_ms": total_pcm_ms, "samples": samples, "sample_rates": sorted(rates)}


def _tts_report(models_dir):
    from .tts import PiperSpeech
    from .voice_config import VoiceSettings

    settings = VoiceSettings(models_dir=str(Path(models_dir).expanduser().resolve())).validate()
    text = REFERENCE_PHRASES[0]
    strategies = {}
    for name, reuse in (("baseline", False), ("reused", True)):
        strategy_at = time.monotonic()
        turns = []
        for index in range(2):
            load_ms = None
            if not reuse or index == 0:
                loading_at = time.monotonic()
                speech = PiperSpeech(settings)
                load_ms = _milliseconds(loading_at, time.monotonic())
            turns.append(_measure_tts_turn(speech, text, load_ms, reused=reuse and index > 0))
            if not reuse:
                del speech
        if reuse:
            del speech
        strategies[name] = {"loads": 1 if reuse else 2, "turns": turns,
                            "total_ms": _milliseconds(strategy_at, time.monotonic())}
    return {
        "mode": "tts_benchmark", "text": text, "models_dir": settings.models_dir,
        "voice": settings.voice, **strategies,
        "timing": {"load_ms": "Construction locale de PiperSpeech ; null si moteur réutilisé.",
                   "first_pcm_ms": "Du début de synthesize au premier bloc PCM non vide.",
                   "total_pcm_ms": "Du début de synthesize à la fin de tous les blocs PCM."},
        "limitations": ["Engine-only : aucun spawn, microphone, WAV ni sortie physique.",
                        "Ordre baseline puis reused : les caches système peuvent favoriser la seconde série.",
                        "Deux tours par stratégie ; aucune conclusion sur la latence audible ou les percentiles."],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--corpus", metavar="MANIFEST.json", help="Liste JSON de {wav, reference} ; WAV relatifs au manifeste.")
    mode.add_argument("--benchmark-tts", action="store_true", help="Comparer deux chargements Piper à un moteur réutilisé.")
    parser.add_argument("--models-dir", required=True, metavar="DIR", help="Dossier local contenant whisper/ et/ou piper/.")
    args = parser.parse_args(argv)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        # Keep stdout machine-readable if an optional engine prints diagnostics.
        with redirect_stdout(sys.stderr):
            report = _tts_report(args.models_dir) if args.benchmark_tts else _corpus_report(args.corpus, args.models_dir)
    except (OSError, ValueError, ImportError, RuntimeError) as exc:
        parser.exit(2, f"Erreur de diagnostic audio local : {exc}\n")
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
