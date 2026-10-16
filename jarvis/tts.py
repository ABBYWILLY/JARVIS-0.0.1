"""Piper CPU synthesis and real device playback; no synthesized visual activity."""
import re
import threading
import time
from dataclasses import dataclass
from typing import Iterable, Protocol

from .audio import AudioEvent, resolve_device, signal_view


@dataclass
class PCM:
    samples: object
    sample_rate: int


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

    def synthesize(self, text):
        for chunk in self.voice.synthesize(text, syn_config=self.config):
            yield PCM(chunk.audio_float_array, chunk.sample_rate)


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
            match = re.search(r"[.!?;:\n](?:\s|$)", self.pending)
            if match and match.end() <= limit:
                end = match.end()
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


class AudioPlayer:
    def __init__(self, device_key):
        self.device_key = device_key

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
        position = 0
        started_at = None
        failed = []

        def callback(output, frames, timing, status):
            nonlocal position, started_at
            if status:
                failed.append(str(status))
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
            emit(AudioEvent("played", view, generation))
            if position >= len(samples):
                raise sd.CallbackStop

        # The callback reports PCM submitted to the selected output at its DAC time.
        with sd.OutputStream(device=device, samplerate=rate, channels=1, dtype="float32",
                blocksize=max(128, round(rate * 0.04)), callback=callback, finished_callback=finished.set) as stream:
            deadline = time.monotonic() + len(samples) / rate + 5
            while not finished.wait(0.05):
                if time.monotonic() > deadline or not stream.active:
                    raise RuntimeError("Sortie audio interrompue. Vérifiez le périphérique de lecture.")
        if failed:
            raise RuntimeError("Sortie audio saturée. Réduisez la charge ou changez de périphérique.")
