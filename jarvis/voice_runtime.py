"""Spawn boundaries for live capture/STT and TTS, with bounded queues and epochs."""
import multiprocessing as mp
import os
import queue
import time
from concurrent.futures import ThreadPoolExecutor

from .audio import AudioEvent
from .voice_config import VoiceSettings


def audio_error(exc):
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return "Composants vocaux absents. Installez requirements-voice.txt ; le chat texte reste disponible."
    if isinstance(exc, ValueError):
        return str(exc)
    return "Audio indisponible : vérifiez microphone, sortie, autorisation Windows et installation PortAudio/DLL. Le chat texte reste disponible."


def emit_event(outbox, event):
    try:
        if event.kind in {"mic_level", "played"}:
            outbox.put_nowait(event)  # Never block an audio callback on the UI.
        else:
            outbox.put(event, timeout=1)
    except queue.Full:
        if event.kind not in {"mic_level", "played"}:
            raise RuntimeError("File d’événements vocaux saturée ; redémarrez l’écoute.")


def capture_worker(outbox, commands, profile):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        from .audio import FrenchWhisper, Microphone, SileroFrames, TurnDetector, signal_view
        settings = VoiceSettings(**profile).validate()
        stt = FrenchWhisper(settings.model_root / "whisper", settings.cpu_threads)
        vad = SileroFrames()
        detector = TurnDetector(settings.vad_threshold, settings.silence_ms)
        with Microphone(settings.input_device) as microphone, ThreadPoolExecutor(max_workers=1) as executor:
            emit_event(outbox, AudioEvent("listening"))
            future = None
            future_generation = 0
            generation = 0
            muted = False
            last_level = 0.0
            while True:
                try:
                    while True:
                        command = commands.get_nowait()
                        if command["kind"] == "mute":
                            muted = command["value"]
                            detector.reset()
                            vad.reset()
                except queue.Empty:
                    pass
                if future is not None and future.done():
                    text = future.result()
                    emit_event(outbox, AudioEvent("transcript", text, future_generation))
                    future = None
                try:
                    frames = microphone.read()
                except queue.Empty:
                    continue
                if muted:
                    continue
                for frame in frames:
                    probability = vad.probability(frame)
                    for event in detector.feed(frame, probability):
                        if event.kind == "speech_start":
                            generation += 1
                            emit_event(outbox, AudioEvent("speech_start", generation=generation))
                        elif event.kind == "utterance":
                            if future is not None:
                                emit_event(outbox, AudioEvent("warning", "Transcription occupée : cette intervention n’a pas été envoyée. Répétez après l’indicateur d’écoute.", generation))
                            else:
                                future_generation = generation
                                future = executor.submit(stt.transcribe, event.payload)
                                emit_event(outbox, AudioEvent("transcribing", generation=generation))
                    now = time.monotonic()
                    if now - last_level > 0.05:
                        view = signal_view(frame if detector.speaking and probability >= settings.vad_threshold else [0.0])
                        view["speaking"] = detector.speaking
                        emit_event(outbox, AudioEvent("mic_level", view, generation))
                        last_level = now
    except Exception as exc:
        emit_event(outbox, AudioEvent("error", audio_error(exc)))


def speech_worker(outbox, commands, profile, generation):
    try:
        from .tts import AudioPlayer, PiperSpeech
        settings = VoiceSettings(**profile).validate()
        speech = PiperSpeech(settings)
        player = AudioPlayer(settings.output_device)
        emit = lambda event: emit_event(outbox, event)
        emit(AudioEvent("tts_ready", generation=generation))
        while True:
            text = commands.get()
            if text is None:
                emit(AudioEvent("speech_done", generation=generation))
                return
            # Piper may split a phrase; report per-chunk captions as an approximation.
            for pcm in speech.synthesize(text):
                player.play(pcm, text, emit, generation)
    except Exception as exc:
        emit_event(outbox, AudioEvent("error", audio_error(exc), generation))


class AudioProcess:
    def __init__(self):
        self.context = mp.get_context("spawn")
        self.process = self.outbox = self.commands = None

    def start(self, kind, settings, generation=0):
        self.stop()
        self.outbox = self.context.Queue(maxsize=128)
        self.commands = self.context.Queue(maxsize=8)
        target = capture_worker if kind == "capture" else speech_worker
        args = (self.outbox, self.commands, settings.to_dict())
        if kind != "capture":
            args += (generation,)
        self.process = self.context.Process(target=target, args=args, daemon=True)
        self.process.start()

    def send(self, command):
        if self.commands is None:
            return False
        try:
            self.commands.put_nowait(command)
            return True
        except queue.Full:
            return False

    def poll(self):
        events = []
        if self.outbox is not None:
            for _ in range(128):
                try:
                    events.append(self.outbox.get_nowait())
                except queue.Empty:
                    break
        return events

    def alive(self):
        return self.process is not None and self.process.is_alive()

    def stop(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=0.25)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=0.25)
            self.process.close()
            self.process = None
        for channel in (self.commands, self.outbox):
            if channel is not None:
                channel.cancel_join_thread()
                channel.close()
        self.commands = self.outbox = None
