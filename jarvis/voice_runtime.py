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
        if event.kind in {"mic_level", "played", "diagnostic"}:
            outbox.put_nowait(event)  # Never block an audio callback on the UI.
        else:
            outbox.put(event, timeout=1)
        return True
    except queue.Full:
        if event.kind not in {"mic_level", "played", "diagnostic"}:
            raise RuntimeError("File d’événements vocaux saturée ; redémarrez l’écoute.")
        return False


def capture_worker(outbox, commands, profile):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    startup_at = time.monotonic()
    stage = "initialisation STT"
    microphone = None
    generation = 0
    event_drops = 0
    selected_device = profile.get("input_device") or "Par défaut Windows"

    def emit(event):
        nonlocal event_drops
        if emit_event(outbox, event) is False:
            event_drops += 1

    def startup(status):
        emit(AudioEvent("capture_stage", {"stage": stage, "capture_status": status,
             "selected_device": selected_device, "opened_device": None,
             "started_at": startup_at}))

    try:
        from .audio import FrenchWhisper, Microphone, SileroFrames, TurnDetector, signal_view
        settings = VoiceSettings(**profile).validate()
        startup("loading_stt")
        stt = FrenchWhisper(settings.model_root / "whisper", settings.cpu_threads)
        stage = "initialisation VAD"
        startup("loading_vad")
        vad = SileroFrames()
        detector = TurnDetector(settings.vad_threshold, settings.silence_ms)
        stage = "ouverture microphone"
        startup("opening_microphone")
        with Microphone(settings.input_device) as microphone, ThreadPoolExecutor(max_workers=1) as executor:
            def device_health():
                info = getattr(microphone, "diagnostic_info", None)
                return info() if callable(info) else {"selected_device": selected_device,
                    "opened_device": None, "native_rate": getattr(microphone, "native_rate", None),
                    "callback_status": "", "dropped_frames": 0}

            emit(AudioEvent("listening", {**device_health(),
                "startup_ms": round((time.monotonic() - startup_at) * 1000),
                "capture_status": "open", "rate": 16000}))
            future = None
            future_generation = 0
            active_job = pending_job = None
            generation = 0
            muted = False
            last_level = 0.0
            last_diagnostic = 0.0
            last_stt = "Aucun segment soumis"
            sample_path = None
            frames_received = 0
            last_frame_at = None
            last_rms = None

            def diagnostic(status, now, *, frame=None, probability=None):
                nonlocal last_diagnostic
                if now - last_diagnostic <= .25:
                    return
                phase = ("suspendu pendant la lecture" if muted else "attente de silence"
                         if detector.waiting_for_quiet else "parole" if detector.speaking else "silence")
                emit(AudioEvent("diagnostic", {**device_health(),
                    "rms": signal_view(frame, points=1)["rms"] if frame is not None else None,
                    "last_rms": last_rms, "vad": probability,
                    "state": phase, "capture_status": status, "stage": stage,
                    "turn_seconds": detector.duration, "end_reason": detector.last_end_reason,
                    "last_stt": last_stt, "rate": 16000,
                    "frame_samples": len(frame) if frame is not None else 0,
                    "frames_received": frames_received, "last_frame_at": last_frame_at,
                    "event_drops": event_drops}, generation))
                last_diagnostic = now

            def transcribe(job):
                if job.get("sample_path"):
                    from .audio_diagnostics import save_wav, signal_quality
                    try:
                        quality = signal_quality(job["samples"])
                        save_wav(job["sample_path"], job["samples"])
                        job["sample_result"] = {"path": job["sample_path"], "quality": quality,
                                                "end_reason": job["reason"]}
                    except Exception as exc:
                        job["sample_error"] = f"{type(exc).__name__}: {exc}"
                job["started_at"] = time.monotonic()
                try:
                    return stt.transcribe(job["samples"])
                finally:
                    job["finished_at"] = time.monotonic()

            def start_job(job):
                nonlocal future, future_generation, active_job, last_stt
                active_job = job
                future_generation = job["generation"]
                last_stt = "STT démarré"
                future = executor.submit(transcribe, job)
                emit(AudioEvent("transcribing", generation=future_generation))

            def submit(event):
                nonlocal pending_job, last_stt, sample_path
                ended_at = time.monotonic()
                emit(AudioEvent("turn_end", {
                    "reason": detector.last_end_reason, "duration": detector.last_duration,
                    "samples": len(event.payload), "ended_at": ended_at,
                    "silence_ms": detector.last_silence_ms}, generation))
                if detector.last_end_reason == "max_duration":
                    emit(AudioEvent("warning", "Tour limité à 20 s : segment envoyé au STT. Attendez un silence avant de reprendre.", generation))
                    vad.reset()
                job = {"samples": event.payload, "generation": generation, "ended_at": ended_at}
                if sample_path:
                    job.update(sample_path=sample_path, reason=detector.last_end_reason)
                    sample_path = None
                if future is not None:
                    # One bounded latest-turn slot, never an unbounded stale backlog.
                    pending_job = job
                    last_stt = "Tour conservé en attente du STT"
                    emit(AudioEvent("stt_queued", generation=generation))
                else:
                    start_job(job)
            while True:
                try:
                    while True:
                        command = commands.get_nowait()
                        if command["kind"] == "mute":
                            # Idempotent: speech_start triggers an unmute from the UI.
                            # Resetting False→False here used to destroy every new turn.
                            requested = bool(command["value"])
                            if requested != muted:
                                muted = requested
                                detector.reset()
                                vad.reset()
                                if pending_job is not None:
                                    emit(AudioEvent("stt_superseded", "Microphone suspendu", pending_job["generation"]))
                                    if pending_job.get("sample_path"):
                                        emit(AudioEvent("sample_error", "Demande WAV annulée : microphone suspendu.", pending_job["generation"]))
                                    pending_job = None
                        elif command["kind"] == "finish_turn" and not muted:
                            for event in detector.finish():
                                submit(event)
                        elif command["kind"] == "sample_next":
                            sample_path = command["path"]
                            emit(AudioEvent("sample_armed", sample_path))
                except queue.Empty:
                    pass
                if future is not None and future.done():
                    completed = future
                    future = None
                    timing = {"elapsed_ms": round((active_job["finished_at"] - active_job["started_at"]) * 1000),
                              "queue_ms": round((active_job["started_at"] - active_job["ended_at"]) * 1000)}
                    if "sample_result" in active_job:
                        emit(AudioEvent("sample_saved", active_job["sample_result"], future_generation))
                    elif "sample_error" in active_job:
                        emit(AudioEvent("sample_error", active_job["sample_error"], future_generation))
                    try:
                        text = completed.result()
                    except Exception as exc:
                        last_stt = f"{type(exc).__name__}: {str(exc)[:400]}"
                        emit(AudioEvent("stt_error", {"error": last_stt, **timing}, future_generation))
                    else:
                        last_stt = "Terminé : " + (text[:400] if text else "aucun texte reconnu")
                        detail = getattr(stt, "last_result", {})
                        detail = {**detail, "raw_result": detail.get("raw_result", "")[:2000]}
                        emit(AudioEvent("stt_complete", {"result": text[:2000], **detail, **timing}, future_generation))
                        emit(AudioEvent("transcript", text, future_generation))
                    active_job = None
                    if pending_job is not None:
                        job, pending_job = pending_job, None
                        start_job(job)
                try:
                    stage = "capture / rééchantillonnage PCM"
                    frames = microphone.read()
                except queue.Empty:
                    diagnostic("suspended" if muted else "waiting_for_pcm", time.monotonic())
                    continue
                if not frames:
                    diagnostic("suspended" if muted else "waiting_for_pcm", time.monotonic())
                    continue
                frames_received += len(frames)
                last_frame_at = time.monotonic()
                last_rms = signal_view(frames[-1], points=1)["rms"]
                if muted:
                    diagnostic("suspended", time.monotonic(), frame=frames[-1])
                    continue
                for frame in frames:
                    stage = "VAD / détection de fin de tour"
                    probability = vad.probability(frame)
                    for event in detector.feed(frame, probability):
                        if event.kind == "speech_start":
                            generation += 1
                            if pending_job is not None:
                                emit(AudioEvent("stt_superseded", "Nouvelle prise de parole", pending_job["generation"]))
                                if pending_job.get("sample_path"):
                                    emit(AudioEvent("sample_error", "Demande WAV annulée : tour remplacé par une nouvelle prise de parole.", pending_job["generation"]))
                                pending_job = None
                            emit(AudioEvent("speech_start", generation=generation))
                        elif event.kind == "utterance":
                            submit(event)
                    now = time.monotonic()
                    if now - last_level > 0.05:
                        view = signal_view(frame)
                        view.update(speaking=detector.speaking, vad=probability,
                                    frames_received=frames_received, captured_at=last_frame_at)
                        emit(AudioEvent("mic_level", view, generation))
                        last_level = now
                    diagnostic("receiving_pcm", now, frame=frame, probability=probability)

    except Exception as exc:
        info = getattr(microphone, "diagnostic_info", None)
        detail = info() if callable(info) else {"selected_device": selected_device, "opened_device": None}
        emit(AudioEvent("capture_error", {**detail, "capture_status": "error", "stage": stage,
                   "event_drops": event_drops,
                   "error": f"{type(exc).__name__}: {str(exc)[:400]}"}))
        emit(AudioEvent("error", audio_error(exc)))


def speech_worker(outbox, commands, profile, generation, persistent=False):
    loading = True
    try:
        from .tts import AudioPlayer, PiperSpeech, SpeechText
        settings = VoiceSettings(**profile).validate()
        loaded_at = time.monotonic()
        speech = PiperSpeech(settings)
        player = AudioPlayer(settings.output_device)
        emit = lambda event: emit_event(outbox, event)
        emit(AudioEvent("tts_ready", {"load_ms": round((time.monotonic() - loaded_at) * 1000)}, generation))
        loading = False
        while True:
            text = commands.get()
            if persistent:
                generation, text = text["generation"], text["text"]
            if text is None:
                emit(AudioEvent("speech_done", generation=generation))
                if persistent:
                    continue  # Keep the loaded CPU voice only; no open audio stream.
                return
            # Piper may split a phrase; report per-chunk captions as an approximation.
            playback_emit = emit
            caption_metadata = None
            played_any = False
            if isinstance(text, SpeechText):
                from dataclasses import asdict
                caption_metadata = {"text": text.display_text, "spoken_text": str(text),
                    "original_start": text.start, "original_end": text.end,
                    "segment_id": text.segment_id, "response_id": generation,
                    "text_events": [dict(asdict(event), value=event.value[:256]) for event in text.events],
                    "spectrum_events": [dict(asdict(event), text=event.text[:512]) for event in text.spectrum_events],
                    "spectrum_mode": text.spectrum_mode,
                    "alignment": "phrase / bloc PCM approximatif"}
                if text.caption_plan is not None:
                    caption_metadata["caption_plan"] = asdict(text.caption_plan)

                def playback_emit(event):
                    nonlocal played_any
                    if event.kind == "played":
                        played_any = True
                        event = AudioEvent(event.kind, {**event.payload, **caption_metadata}, event.generation)
                    emit(event)

            synthesis_at = time.monotonic()
            for pcm in speech.synthesize(str(text)):
                emit(AudioEvent("tts_pcm_ready", {"elapsed_ms": round((time.monotonic() - synthesis_at) * 1000)}, generation))
                player.play(pcm, str(text), playback_emit, generation)
                synthesis_at = time.monotonic()
            if caption_metadata is not None and played_any:
                # AudioPlayer returns after the device stream finishes. This is
                # a whole-segment boundary, unlike per-Piper-block fractions.
                emit(AudioEvent("segment_done", {**caption_metadata,
                    "completed_at": time.monotonic()}, generation))
    except Exception as exc:
        emit_event(outbox, AudioEvent("tts_load_error" if persistent and loading else "error", audio_error(exc), generation))


def diagnostics_worker(outbox, commands, profile):
    """No microphone/model download: exercise bundled native dependencies in spawn."""
    try:
        import numpy as np
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        import ctranslate2
        import sounddevice as sd
        import soxr
        from piper.phonemize_espeak import EspeakPhonemizer
        from .audio import SileroFrames
        phonemes = EspeakPhonemizer().phonemize("fr", "Bonjour, je suis JARVIS.")
        vad = SileroFrames()
        silent = vad.probability(np.zeros(512, dtype="float32"))
        samples = soxr.resample(np.zeros(480, dtype="float32"), 48000, 16000)
        if not phonemes or silent >= 0.6 or len(samples) != 160:
            raise RuntimeError("Voice native diagnostic failed")
        emit_event(outbox, AudioEvent("diagnostics_done", {"phonemes": True, "vad": True,
                  "resampling": True, "portaudio": sd.get_portaudio_version()[0]}))
    except Exception as exc:
        emit_event(outbox, AudioEvent("error", audio_error(exc)))


def sample_worker(outbox, commands, profile, generation):
    """Explicit local WAV replay, no TTS/STT model or device opened beforehand."""
    try:
        from .audio_diagnostics import read_wav
        from .tts import AudioPlayer, PCM
        settings = VoiceSettings(**profile).validate()
        path = commands.get()
        AudioPlayer(settings.output_device).play(PCM(read_wav(path), 16000), "",
            lambda event: emit_event(outbox, event), generation)
        emit_event(outbox, AudioEvent("speech_done", generation=generation))
    except Exception as exc:
        emit_event(outbox, AudioEvent("error", audio_error(exc), generation))


class AudioProcess:
    def __init__(self):
        self.context = mp.get_context("spawn")
        self.process = self.outbox = self.commands = None
        self.kind = None
        self.generation = 0

    def start(self, kind, settings, generation=0):
        self.stop()
        self.kind, self.generation = kind, generation
        self.outbox = self.context.Queue(maxsize=128)
        self.commands = self.context.Queue(maxsize=8)
        target = {"capture": capture_worker, "speech": speech_worker, "sample": sample_worker,
                  "diagnostics": diagnostics_worker}[kind]
        args = (self.outbox, self.commands, settings.to_dict())
        if kind == "speech":
            args += (generation, True)
        elif kind == "sample":
            args += (generation,)
        self.process = self.context.Process(target=target, args=args, daemon=True)
        self.process.start()

    def send(self, command):
        if self.commands is None:
            return False
        try:
            if self.kind == "speech":
                command = {"generation": self.generation, "text": command}
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
