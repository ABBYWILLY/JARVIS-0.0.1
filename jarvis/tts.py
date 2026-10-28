"""Piper CPU synthesis and real device playback; no synthesized visual activity."""
import re
import math
import threading
import time
from dataclasses import dataclass, replace
from typing import Iterable, Protocol

from .audio import AudioEvent, resolve_device, signal_view
from .audio_spectrum import PCMSpectrum, ZERO_BANDS
from .speech_normalization import normalize_french_speech, sentence_boundary


@dataclass
class PCM:
    samples: object
    sample_rate: int


class SpeechText(str):
    """Clean speech plus source metadata, picklable across Windows spawn IPC."""
    def __new__(cls, text, *, original=None, display_text=None, start=0, end=None,
                events=(), segment_id=0, response_id=0, spectrum_events=(), spectrum_mode="expression", caption_plan=None,
                rate=1.0, pause_ms=0):
        instance = super().__new__(cls, text)
        instance.original = text if original is None else original
        instance.display_text = text if display_text is None else display_text
        instance.start = start
        instance.end = start + len(instance.original) if end is None else end
        instance.events = tuple(events)
        instance.segment_id = segment_id
        instance.response_id = response_id
        instance.spectrum_events = tuple(spectrum_events)
        instance.spectrum_mode = spectrum_mode
        instance.caption_plan = caption_plan
        instance.rate = rate
        instance.pause_ms = pause_ms
        return instance


class SpeechProvider(Protocol):
    def synthesize(self, text: str) -> Iterable[PCM]: ...


class PiperSpeech:
    engine = "piper"

    def __init__(self, settings):
        path = settings.model_root / "piper" / (settings.voice + ".onnx")
        if not path.is_file() or not path.with_suffix(".onnx.json").is_file():
            raise ValueError("Voix Piper absente. Installez les modèles depuis le guide audio.")
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from piper import PiperVoice
        from piper.config import SynthesisConfig
        self.voice = PiperVoice.load(str(path), use_cuda=False)
        self.config = SynthesisConfig(length_scale=1.0 / settings.speed)
        self.speed = settings.speed

    def synthesize(self, text):
        rate, pause_ms = getattr(text, "rate", 1.), getattr(text, "pause_ms", 0)
        if (isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate)
                or not .25 <= rate <= 4 or type(pause_ms) is not int or not 0 <= pause_ms <= 300):
            raise ValueError("Prosodie invalide : facteur 0,25–4 et pause 0–300 ms attendus.")
        speed = min(2., max(.5, self.speed * rate))
        config = replace(self.config, length_scale=1. / speed)
        for chunk in self.voice.synthesize(normalize_french_speech(text), syn_config=config):
            samples = chunk.audio_float_array
            if pause_ms:
                # Piper yields sentence chunks. Append a small, real PCM pause
                # without waiting for the next chunk or opening another stream.
                import numpy as np
                samples = np.concatenate((samples, np.zeros(round(chunk.sample_rate * pause_ms / 1000), dtype="float32")))
            yield PCM(samples, chunk.sample_rate)


class SentenceBuffer:
    """Bounded phrase segmentation of actual LLM text, not token-by-token TTS."""
    def __init__(self):
        self.pending = ""
        self.emitted = False

    def feed(self, text, final=False):
        self.pending += text
        result = []
        while self.pending:
            # A long opening sentence need not delay the first audio until 240
            # characters. Following phrases retain the existing batching bound.
            limit = 240 if self.emitted else 96
            match = next((candidate for candidate in re.finditer(r"[.!?;:\n](?:\s|$)", self.pending)
                          if sentence_boundary(self.pending, candidate.start(), final=final)), None)
            clause = re.search(r",\s", self.pending[40:limit]) if not self.emitted else None
            if match and match.end() <= limit:
                end = match.end()
            elif clause:
                end = 40 + clause.end()
            elif len(self.pending) >= limit:
                end = self.pending.rfind(" ", 0, limit)
                if end <= 0:
                    end = limit
            elif final:
                end = len(self.pending)
            else:
                break
            phrase = self.pending[:end].strip()
            self.pending = self.pending[end:]
            if phrase:
                result.append(phrase)
                self.emitted = True
        return result


class _PlaybackSpectrum:
    """One upcoming device block, analysed outside PortAudio and Tk.

    The first block is prepared before stream startup. Afterwards one daemon
    worker prepares only the latest requested upcoming block, at most 25 Hz.
    The immutable result includes its exact resampled offset/count; a late
    result can never be attached to another block's DAC notification.
    """
    def __init__(self, samples, rate, blocksize, start=0, *, analyzer=None):
        self.samples, self.rate, self.blocksize = samples, rate, blocksize
        self.analyzer = analyzer or PCMSpectrum()
        self._closed, self._wake = threading.Event(), threading.Event()
        self._request_lock = threading.Lock()
        self._requested = None
        self._ready = self._analyse(start, min(blocksize, len(samples)-start))
        self._thread = threading.Thread(target=self._run, name="jarvis-playback-spectrum", daemon=True)
        self._thread.start()

    def _analyse(self, start, count):
        try:
            bands = tuple(self.analyzer.analyze(self.samples[start:start+count], self.rate))
            if len(bands) != 3 or not all(math.isfinite(value) and 0 <= value <= 1 for value in bands):
                raise ValueError("Le spectre doit produire trois bandes finies entre 0 et 1.")
            return start, count, bands, ""
        except Exception as error:
            return start, count, ZERO_BANDS, f"Spectre audio indisponible : {type(error).__name__}: {str(error)[:400]}"

    def block(self, start, count):
        ready = self._ready
        if not self._closed.is_set() and ready is not None and ready[:2] == (start, count):
            return ready[2], "error" if ready[3] else "ready", ready[3]
        return ZERO_BANDS, "waiting", ""

    def request(self, start, count):
        # Tuple assignment and the event are bounded; no FFT or wait in callback.
        if not self._closed.is_set() and count > 0:
            with self._request_lock:
                self._requested = (start, count)
            self._wake.set()

    def _run(self):
        next_at = float("-inf")
        while not self._closed.is_set():
            self._wake.wait()
            self._wake.clear()
            remaining = max(0., next_at-time.perf_counter())
            if self._closed.wait(remaining):
                return
            with self._request_lock:
                requested, self._requested = self._requested, None
            if requested is None:
                continue
            next_at = time.perf_counter()+.04
            result = self._analyse(*requested)
            if not self._closed.is_set():
                self._ready = result

    def close(self):
        self._closed.set()
        self._ready = None
        self._wake.set()
        self._thread.join(timeout=2.)
        self._ready = self._requested = None
        if self._thread.is_alive():
            raise RuntimeError("Le worker du spectre de lecture ne s’est pas arrêté.")


class AudioPlayer:
    def __init__(self, device_key):
        self.device_key = device_key
        self.spectrum_enabled = False
        self.spectrum_control = None  # Optional spawn-shared boolean; no audio restart.

    def _spectrum_enabled(self):
        return bool(self.spectrum_control.value if self.spectrum_control is not None else self.spectrum_enabled)

    def play(self, pcm, text, emit, generation=0):
        import numpy as np
        import sounddevice as sd
        import soxr
        device = resolve_device(self.device_key, "output")
        rate = int(sd.query_devices(device, "output")["default_samplerate"])
        samples = np.asarray(pcm.samples, dtype="float32").reshape(-1)
        if rate != pcm.sample_rate:
            samples = soxr.resample(samples, pcm.sample_rate, rate)
        if len(samples) == 0:
            return
        finished = threading.Event()
        blocksize = max(128, round(rate * 0.04))
        position = 0
        started_at = None
        failed = []
        spectrum = None
        spectrum_failure = ""

        def update_spectrum():
            nonlocal spectrum, spectrum_failure
            enabled = self._spectrum_enabled()
            if spectrum is not None and not enabled:
                previous, spectrum = spectrum, None
                try:
                    previous.close()
                except Exception as error:
                    spectrum_failure = str(error)
                    emit(AudioEvent("spectrum_diagnostic", spectrum_failure, generation))
            elif spectrum is None and enabled and position < len(samples) and not spectrum_failure:
                try:
                    spectrum = _PlaybackSpectrum(samples, rate, blocksize, start=position)
                except Exception as error:
                    spectrum_failure = f"Spectre audio indisponible : {type(error).__name__}: {error}"

        # Only the next block is prepared, never the complete phrase/WAV.
        update_spectrum()

        def callback(output, frames, timing, status):
            nonlocal position, started_at
            if status:
                failed.append(str(status))
            sample_start = position
            count = min(frames, len(samples) - position)
            output.fill(0)
            output[:count, 0] = samples[position:position + count]
            position += count
            view = signal_view(output[:count, 0])
            delay = max(0.0, timing.outputBufferDacTime - timing.currentTime)
            emitted_at = time.monotonic()
            if started_at is None:
                started_at = emitted_at + delay
            view.update(text=text, fraction=position / len(samples), delay=delay,
                        emitted_at=emitted_at, started_at=started_at)
            if self._spectrum_enabled():
                bands, spectral_status, error = (spectrum.block(sample_start, count) if spectrum is not None else
                    (ZERO_BANDS, "error" if spectrum_failure else "waiting", spectrum_failure))
                view.update(bands=bands, spectrum_status=spectral_status, spectrum_error=error,
                            spectrum_sample_start=sample_start, spectrum_sample_count=count,
                            sample_rate=rate)
                if spectrum is not None:
                    spectrum.request(position, min(frames, len(samples)-position))
            emit(AudioEvent("played", view, generation))
            if position >= len(samples):
                raise sd.CallbackStop

        # The callback reports PCM submitted to the selected output at its DAC time.
        try:
            with sd.OutputStream(device=device, samplerate=rate, channels=1, dtype="float32",
                    blocksize=blocksize, callback=callback, finished_callback=finished.set) as stream:
                deadline = time.monotonic() + len(samples) / rate + 5
                while not finished.wait(.01 if self._spectrum_enabled() else .05):
                    update_spectrum()
                    if time.monotonic() > deadline or not stream.active:
                        raise RuntimeError("Sortie audio interrompue. Vérifiez le périphérique de lecture.")
        finally:
            if spectrum is not None:
                try:
                    spectrum.close()
                except Exception as error:
                    emit(AudioEvent("spectrum_diagnostic", str(error), generation))
        if failed:
            raise RuntimeError("Sortie audio saturée. Réduisez la charge ou changez de périphérique.")
