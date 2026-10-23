"""Local audio adapters, imported lazily so the text application stays independent."""
import math
import queue
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

RATE, FRAME = 16000, 512


@dataclass(frozen=True)
class AudioEvent:
    kind: str
    payload: object = None
    generation: int = 0
    version: int = 1


def signal_view(samples, points=48):
    """Ordered sample extrema and exact PCM RMS, without a generated carrier.

    Bucket means can cancel real periodic audio at certain frequencies. Keep
    two real extrema per bucket, in their original temporal order, instead.
    """
    if len(samples) == 0:
        return {"rms": 0.0, "wave": [0.0] * points}
    rms = math.sqrt(sum(float(x) ** 2 for x in samples) / len(samples))
    if points <= 1:
        return {"rms": rms, "wave": [float(samples[0])]}
    buckets = min(len(samples), max(1, points // 2))
    wave = []
    for bucket in range(buckets):
        start, end = bucket * len(samples) // buckets, (bucket + 1) * len(samples) // buckets
        low = min(range(start, end), key=lambda index: samples[index])
        high = max(range(start, end), key=lambda index: samples[index])
        wave.extend(float(samples[index]) for index in sorted({low, high}))
    return {"rms": rms, "wave": wave}


class TurnDetector:
    """Silero probabilities in, bounded complete utterances out (32 ms frames)."""
    def __init__(self, threshold=0.6, silence_ms=800, max_seconds=20):
        self.threshold = threshold
        self.silence_frames = max(1, round(silence_ms / 32))
        self.max_frames = round(max_seconds * RATE / FRAME)
        self.last_end_reason = ""
        self.last_duration = 0.0
        self.last_silence_ms = 0
        self.reset()

    def reset(self):
        self.pre = deque(maxlen=8)
        self.frames = []
        self.voiced = self.silent = 0
        self.speaking = False
        self.waiting_for_quiet = False

    @property
    def duration(self):
        return len(self.frames) * FRAME / RATE

    def finish(self, reason="manual"):
        if not self.speaking:
            return []
        trim = max(0, self.silent - 5)
        frames = self.frames[:-trim] if trim else self.frames
        self.last_end_reason, self.last_duration = reason, self.duration
        self.last_silence_ms = self.silent * FRAME * 1000 // RATE
        self.reset()
        # A stuck VAD must not submit the same constant noise every 20 seconds.
        self.waiting_for_quiet = reason in {"max_duration", "manual"}
        return [AudioEvent("utterance", [x for f in frames for x in f])]

    def feed(self, frame, probability):
        events = []
        frame = list(frame)
        if len(frame) != FRAME:
            raise ValueError("VAD attend exactement 512 échantillons à 16 kHz.")
        if self.waiting_for_quiet:
            self.silent = self.silent + 1 if probability < self.threshold else 0
            if self.silent >= self.silence_frames:
                self.reset()
            return events
        if not self.speaking:
            self.pre.append(frame)
            self.voiced = self.voiced + 1 if probability >= self.threshold else 0
            if self.voiced >= 5:  # 160 ms rejects clicks and isolated background peaks.
                self.speaking = True
                self.frames = list(self.pre)
                self.silent = 0
                events.append(AudioEvent("speech_start"))
        else:
            self.frames.append(frame)
            self.silent = 0 if probability >= self.threshold else self.silent + 1
            if self.silent >= self.silence_frames:
                events.extend(self.finish("silence"))
            elif len(self.frames) >= self.max_frames:
                events.extend(self.finish("max_duration"))
        return events


class SileroFrames:
    """Stateful streaming adapter for the pinned faster-whisper 1.2.1 VAD v6."""
    def __init__(self):
        import numpy as np
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from faster_whisper.vad import get_vad_model
        self.np = np
        self.session = get_vad_model().session
        self.reset()

    def reset(self):
        self.h = self.np.zeros((1, 1, 128), dtype="float32")
        self.c = self.np.zeros((1, 1, 128), dtype="float32")
        self.context = self.np.zeros((1, 64), dtype="float32")

    def probability(self, frame):
        frame = self.np.asarray(frame, dtype="float32").reshape(1, FRAME)
        samples = self.np.concatenate([self.context, frame], axis=1)
        out, self.h, self.c = self.session.run(None, {"input": samples, "h": self.h, "c": self.c})
        self.context = frame[:, -64:].copy()
        return float(out.reshape(-1)[0])


class Transcriber(Protocol):
    def transcribe(self, audio) -> str: ...


class FrenchWhisper:
    def __init__(self, directory, threads=4):
        if not (Path(directory) / "model.bin").is_file():
            raise ValueError("Modèle STT absent. Installez les modèles vocaux depuis le guide audio.")
        from faster_whisper import WhisperModel
        self.model = WhisperModel(str(directory), device="cpu", compute_type="int8",
                                  cpu_threads=threads, num_workers=1, local_files_only=True)

    def transcribe(self, audio):
        import numpy as np
        segments, info = self.model.transcribe(np.asarray(audio, dtype="float32"), language="fr",
            beam_size=1, vad_filter=False, condition_on_previous_text=False)
        segments = list(segments)
        # Whisper is not streaming STT: publish one final transcript per utterance.
        text = " ".join(segment.text.strip() for segment in segments if segment.no_speech_prob < 0.8).strip()
        self.last_result = {"raw_result": " ".join(segment.text.strip() for segment in segments),
                            "language_requested": "fr", "language_reported": getattr(info, "language", None),
                            "discarded_segments": sum(segment.no_speech_prob >= 0.8 for segment in segments)}
        return text


def device_inventory():
    import sounddevice as sd
    hosts = sd.query_hostapis()
    result = {"input": [], "output": []}
    for i, item in enumerate(sd.query_devices()):
        key = f"{hosts[item['hostapi']]['name']} | {item['name']}"
        for side in result:
            if item[f"max_{side}_channels"] > 0:
                result[side].append({"id": i, "key": key, "rate": int(item["default_samplerate"])})
    return result


def resolve_device(key, side):
    if not key:
        return None  # Explicit default chosen in settings; never replace a missing named device.
    for device in device_inventory()[side]:
        if device["key"] == key:
            return device["id"]
    raise ValueError("Périphérique audio déconnecté. Sélectionnez-le à nouveau dans Voix.")


class Microphone:
    """Native device rate → streaming SOXR → 16 kHz, without blocking callbacks."""
    def __init__(self, device_key):
        import numpy as np
        import sounddevice as sd
        import soxr
        self.np = np
        self.selected_device = device_key or "Par défaut Windows"
        self.device = resolve_device(device_key, "input")
        device_info = sd.query_devices(self.device, "input")
        native_rate = int(device_info["default_samplerate"])
        self.native_rate = native_rate
        self.resampler = soxr.ResampleStream(native_rate, RATE, 1, dtype="float32", quality="HQ")
        self.pending = np.empty(0, dtype="float32")
        self.inbox = queue.Queue(maxsize=64)
        self.failed = False
        self.callback_status = ""
        self.dropped_frames = 0
        self.native_frames_received = 0
        self.last_callback_at = None
        self.capture_status = "opening_microphone"

        def capture(data, frames, timing, status):
            self.last_callback_at = time.monotonic()
            self.native_frames_received += frames
            if status:
                self.failed = True
                self.callback_status = str(status)[:400]
            try:
                self.inbox.put_nowait(np.frombuffer(data, dtype="float32").copy())
            except queue.Full:
                self.failed = True
                self.dropped_frames += frames
                self.callback_status = "File PCM native saturée"
            except Exception as exc:
                # Exceptions escaping a PortAudio callback otherwise stop it
                # without reaching the normal capture-worker error boundary.
                self.failed = True
                self.callback_status = f"{type(exc).__name__}: {str(exc)[:300]}"

        self.stream = sd.RawInputStream(device=self.device, samplerate=native_rate,
            channels=1, dtype="float32", blocksize=max(128, round(native_rate * 0.032)), callback=capture)
        try:
            opened_index = getattr(self.stream, "device", self.device)
            if not isinstance(opened_index, int) or isinstance(opened_index, bool):
                opened_index = self.device
            if isinstance(opened_index, int):
                device_info = sd.query_devices(opened_index, "input")
            host_index = device_info.get("hostapi")
            host = sd.query_hostapis(host_index) if isinstance(host_index, int) else {}
            self.opened_device = {"index": opened_index, "name": device_info.get("name", "Inconnu"),
                "hostapi": host.get("name", "Inconnu") if isinstance(host, dict) else "Inconnu",
                "channels": 1, "dtype": "float32", "native_rate": native_rate}
        except BaseException:
            # __enter__ is never reached if a device disappears during metadata
            # lookup; the already allocated PortAudio stream must still close.
            self.stream.close()
            raise

    def diagnostic_info(self):
        """Bounded callback health; no device query or audio synthesis here."""
        return {"selected_device": self.selected_device, "opened_device": dict(self.opened_device),
                "native_rate": self.native_rate, "capture_status": self.capture_status,
                "last_callback_at": self.last_callback_at,
                "native_frames_received": self.native_frames_received,
                "callback_status": self.callback_status, "dropped_frames": self.dropped_frames}

    def __enter__(self):
        try:
            self.stream.start()
        except BaseException:
            self.stream.close()
            raise
        self.capture_status = "open"
        return self

    def read(self, timeout=0.1):
        if self.failed:
            raise RuntimeError("Capture audio interrompue ou saturée : " + self.callback_status
                               + ". Réduisez la charge, vérifiez le périphérique et réactivez l’écoute.")
        if not self.stream.active:
            raise RuntimeError("Microphone déconnecté. Choisissez un périphérique puis réactivez l’écoute.")
        native = self.inbox.get(timeout=timeout)
        data = self.resampler.resample_chunk(native)
        self.pending = self.np.concatenate([self.pending, data])
        frames = []
        while len(self.pending) >= FRAME:
            frames.append(self.pending[:FRAME].copy())
            self.pending = self.pending[FRAME:]
        return frames

    def __exit__(self, *args):
        self.capture_status = "closed"
        try:
            self.stream.abort()
        finally:
            self.stream.close()
