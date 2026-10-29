#!/usr/bin/env python3
"""Offline Cognitive HUD proof with the existing Tk/packet/OpenGL components.

States are explicitly injected, PCM is synthetic and no model/device is opened.
The optional benchmark includes the production sphere/halo, but is software EGL,
not a measurement of RTX/Ollama/Whisper/Piper or acoustic latency.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import types
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.capture_presence_integration import CaptureTransport, OfflineAudio, capture_widget, digest


STAGES = (("idle", "silent"), ("listening", "listening"),
          ("user_speaking", "user_speaking"), ("transcribing", "thinking"),
          ("context", "thinking"), ("waiting", "thinking"),
          ("generating", "thinking"), ("synthesis", "thinking"),
          ("speaking", "jarvis_speaking"), ("interrupted", "user_speaking"),
          ("error", "silent"), ("cancelled", "silent"), ("idle", "silent"))


class RecordedOfflineAudio(OfflineAudio):
    """Record real orchestration requests; no process, model or PCM is produced."""
    def __init__(self):
        self.process, self.kind = None, None
        self.commands, self.starts = [], []

    def start(self, kind, settings, generation=0):
        self.process, self.kind, self.generation = object(), kind, generation
        self.starts.append({"kind": kind, "generation": generation, "voice": settings.voice,
                            "speed": settings.speed})

    def alive(self):
        return self.process is not None

    def send(self, command):
        if self.process is None:
            return False
        self.commands.append(command)
        return True

    def stop(self):
        self.process = None


def _capture_actions(app, output):
    from dataclasses import asdict, replace
    from PIL import ImageGrab
    import tkinter as tk
    from jarvis.cognition import route_request
    from jarvis.context import ContextBuilder
    from jarvis.provenance import context_observations

    request = "DÉMONSTRATION HORS LIGNE — sélection de texte, aucun son ni modèle actif."
    source = ("# DÉMONSTRATION HORS LIGNE\n\n"
              "Voici **un passage français** avec [un lien](https://example.org), 12,50 € et 😊.\n\n"
              "- Sélection liée à son message SQLite original.\n"
              "- Lecture demandée au double audio ; aucun son émis.\n\n"
              "| Action | Traitement |\n| --- | --- |\n| Lire | Piper local réutilisé |\n"
              "| Expliquer | Demande explicite à Ollama |\n")
    settings, decision = route_request(replace(app.settings,
        system_prompt="DÉMONSTRATION HORS LIGNE : ces instructions synthétiques ne contiennent aucune donnée personnelle."), request)
    started = time.perf_counter()
    retrieved = app.store.memory.search(request, approved_only=True)
    context = ContextBuilder(settings).build([{"role": "user", "content": request}], memories=retrieved)
    observed = context_observations(context, retrieved_memories=retrieved, prepared_ms=(time.perf_counter()-started)*1000)
    mid = app.store.begin_turn(app.session_id, request, "DÉMO HORS LIGNE", metadata={"demo": True})
    app.store.update_response(mid, source, "complete")
    app.store.update_message_metadata(mid, {"context": {**context.stats, "sources": context.sources, **observed}, "cognition": decision})
    app.presence.return_to_command()
    app.render_session()
    app.root.geometry("1100x760+20+20")
    app.root.update()
    region = next(region for region in app.markdown.regions if region.message_id == mid)
    chosen = "Voici un passage français avec un lien, 12,50 € et 😊."
    left = region.text.index(chosen)
    first = app.markdown.offset(region.start, region.text[:left])
    last = app.markdown.offset(region.start, region.text[:left+len(chosen)])
    app.chat.tag_remove("sel", "1.0", "end")
    app.chat.tag_add("sel", first, last)
    app.chat.see(first)
    app.chat.focus_force()
    selection = app.markdown.prepare_actions()
    if selection is None or selection.display_text != chosen:
        raise RuntimeError("Native Rich Text selection was not reconstructed exactly")
    capture_widget(app.root, output/"command-os-selection.png")
    menu = app.markdown.source_menu
    menu.post(app.chat.winfo_rootx()+120, app.chat.winfo_rooty()+100)
    menu.activate(app.markdown._action_entries["read"])
    app.root.update()
    x, y = app.root.winfo_rootx(), app.root.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x+app.root.winfo_width(), y+app.root.winfo_height())).save(output/"command-os-selection-menu.png")
    menu.unpost()
    with patch.object(app.worker, "start") as inference:
        accepted = app.selection_action("read", selection)
        app.voice.poll()
        inference.assert_not_called()
    requests = [command for command in app.voice.speech.commands if hasattr(command, "original")]
    if not accepted or not requests or app.voice.capture.starts or app.operation is not None:
        raise RuntimeError("Selected local read did not remain within the audio double")
    scope = app.voice.selection_scope
    if scope is None or scope.message_id != mid or app.store.message(mid)["content"] != source:
        raise RuntimeError("Selected replay lost its canonical source")
    actions = {"scope": "Actual MarkdownView selection and App.selection_action(read) → VoiceControls; audio boundary is an explicit recording double. No Piper model/process, sound or Ollama call.",
               "selection": asdict(selection), "accepted": accepted, "ollama_worker_starts": 0,
               "capture_starts": app.voice.capture.starts, "audio_boundary_starts": app.voice.speech.starts,
               "tts_requests": [{"speech": str(command), "original": command.original,
                                 "start": command.start, "end": command.end,
                                 "segment_id": command.segment_id} for command in requests],
               "original_sqlite_text_preserved": True,
               "menu_actions": tuple(app.markdown._action_entries), "context_delivery": observed["delivery"]}
    app.voice.cancel_speech()
    inspector = app.open_context()
    app.root.update()
    sources = next(widget for widget in inspector.winfo_children() if isinstance(widget, tk.Listbox))
    instruction_row = next(index for index, line in enumerate(sources.get(0, "end")) if "Instructions effectives" in line)
    sources.selection_clear(0, "end")
    sources.selection_set(instruction_row)
    sources.event_generate("<<ListboxSelect>>")
    inspector.summary_canvas.yview_moveto(0)
    capture_widget(inspector, output/"context-inspector-demo.png")
    (output/"selection-actions-trace.json").write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")
    return actions


def _benchmark(context, renderer, frame, target, settings, baseline):
    """Same production scene/size for cached and changed-title observations."""
    from jarvis.gpu_hud import GpuHud
    before = types.ModuleType("reference_hud")
    raw = subprocess.check_output(["git", "show", baseline + ":jarvis/gpu_hud.py"], cwd=REPO)
    exec(compile(raw, baseline + ":jarvis/gpu_hud.py", "exec"), before.__dict__)
    source = {"state": "thinking", "caption": "Texte français, cœur et été.",
              "cognitive": "Génération locale · DÉMO · Rapide"}
    results = {}
    renderer.set_settings(settings)
    for name, cls, enabled, changing in (("before_cached", before.GpuHud, False, False),
            ("disabled_cached", GpuHud, False, False), ("enabled_cached", GpuHud, True, False),
            ("changed_title_each_frame", GpuHud, True, True)):
        runs = []
        for _repeat in range(3):
            hud, data = cls(context), dict(source)
            if not enabled:
                data.pop("cognitive")
            renderer.render(**frame, target=target)
            hud.render(data, 960, 640, target=target)
            context.finish()
            values, cpu = [], time.process_time()
            for index in range(40):
                if changing:
                    data["cognitive"] = f"Génération locale · DÉMO · {index} s"
                stamp = time.perf_counter()
                renderer.render(**frame, target=target)
                hud.render(data, 960, 640, target=target)
                context.finish()
                values.append((time.perf_counter()-stamp)*1000)
            runs.append({"mean_ms": statistics.mean(values), "p95_ms": sorted(values)[37],
                         "process_cpu_ms": (time.process_time()-cpu)*1000,
                         "hud_upload_count": hud.upload_count, "hud_owned_bytes": hud.allocation_bytes,
                         "renderer_owned_bytes": renderer.allocation_bytes})
            hud.shutdown()
        results[name] = {"mean_ms_median_run": statistics.median(row["mean_ms"] for row in runs),
                         "p95_ms_median_run": statistics.median(row["p95_ms"] for row in runs), "runs": runs}
    return {"scope": "Real production sphere+HUD at960x640, fixed THINKING frame, EGL software; CPU includes driver worker threads. No pacing, swap, readback or encoding. Changed-title case deliberately stresses rasterization, not live1Hz updates.",
            "baseline": baseline, "baseline_hud_sha256": hashlib.sha256(raw).hexdigest(),
            "repetitions": 3, "frames_per_run": 40, "results": results,
            "physical_vram": None, "power": None, "ollama_ttft": None, "piper_latency": None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory; never overwritten")
    parser.add_argument("--fps", type=int, choices=range(8, 31), default=12)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--baseline", default="1985a99")
    args = parser.parse_args(argv)
    if not all(char in "0123456789abcdefABCDEF" for char in args.baseline) or not 7 <= len(args.baseline) <= 40:
        parser.error("Baseline must be a7–40character commit SHA")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        parser.error("ffmpeg is required")
    args.output.mkdir(parents=True, exist_ok=False)
    import moderngl
    import numpy as np
    from PIL import Image, ImageChops
    import tkinter as tk
    from jarvis.audio import signal_view
    from jarvis.cognitive_state import CognitiveHudSettings
    from jarvis.gpu_hud import GpuHud, layout
    from jarvis.gpu_renderer import GpuRenderer
    from jarvis.gpu_session import _fresh_frame
    from jarvis.presence_gpu import context_info
    from jarvis.richtext import parse_text
    from jarvis.storage import Store
    from jarvis.ui import App

    width, height = 960, 640
    context = moderngl.create_standalone_context(require=330, backend="egl")
    renderer, hud = GpuRenderer(context, width, height, quality="balanced"), GpuHud(context)
    target = context.simple_framebuffer((width, height), components=3)
    encoder = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(args.fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast",
        "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.output/"cognitive-hud-demo.mp4")],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    trace, timings = [], []
    cpu_start, wall_start = time.process_time(), time.perf_counter()
    benchmark = None
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis-cognitive-proof-") as folder, patch("jarvis.voice_ui.AudioProcess", RecordedOfflineAudio):
            store, root = Store(Path(folder)/"demo.sqlite3"), tk.Tk()
            app = App(root, store, refresh=False)
            try:
                view = app.presence
                view.session_factory = CaptureTransport
                view.set_engine("gpu")
                root.update()
                root.after_cancel(app.poll_id)
                view._cancel_animation()
                if view.active_engine != "gpu":
                    raise RuntimeError("Actual integrated parent rejected offline transport")
                origin = time.monotonic()
                # Feed the application's one real owner, using deliberately
                # injected demo events rather than opening a model or device.
                owner = app.cognitive
                owner.begin(1, owner.generation+1, model="DÉMO HORS LIGNE", policy="fast", now=origin)
                prefs = CognitiveHudSettings(level="standard", show_durations=False)
                app.cognitive_view.settings = prefs
                last_stage, thinking_frame, thinking_art = None, None, None
                phrase = "Heureux de te revoir 😊"
                document = parse_text(phrase)
                events, plan = view.prepare_segment(phrase, document.text, 0)
                for index in range(len(STAGES)*args.fps):
                    elapsed = index/args.fps
                    stage, visual = STAGES[int(elapsed)]
                    now = origin + elapsed
                    with patch("time.monotonic", return_value=now):
                        if stage != last_stage:
                            owner.update("idle", now=now)
                            if stage != "idle":
                                owner.update(stage, now=now)
                            if stage == "speaking":
                                owner.update("generating", now=now)
                                view.begin_response()
                                view.queue_expressions(1, 1, phrase, 0, len(phrase), document.events)
                            last_stage = stage
                        samples = np.zeros(640, dtype="float32")
                        if visual in {"user_speaking", "jarvis_speaking"}:
                            phase = np.arange(640)/16000 + elapsed
                            amplitude = .075*max(0., math.sin(elapsed*math.pi*5))**.7
                            samples = (amplitude*(np.sin(2*np.pi*180*phase)+.4*np.sin(2*np.pi*950*phase))).astype("float32")
                        signal = signal_view(samples)
                        caption = None
                        if visual == "jarvis_speaking":
                            from dataclasses import asdict
                            caption = {"response_id": 1, "segment_id": 1, "text": document.text,
                                       "fraction": elapsed % 1., "caption_plan": asdict(plan),
                                       "spectrum_events": [asdict(event) for event in events]}
                        view.update_event(visual, signal=signal, caption=caption)
                        app.cognitive_view.refresh(force=True)
                        text = app.cognitive_view.text.get()
                        view._render()
                        view._cancel_animation()
                        packet = view._gpu.latest
                        frame, _ = _fresh_frame(packet, now)
                        frame.pop("art", None)
                        values = {**packet["hud"], "preview": "DÉMO HORS LIGNE · états injectés · PCM synthétique · aucun micro / Piper / Ollama",
                                  "operation": "", "caption_note": "Scénario logiciel ; synchronisation matérielle non validée"}
                        renderer.set_settings(packet["art"])
                        stamp = time.perf_counter()
                        renderer.render(**frame, target=target)
                        hud.render(values, width, height, target=target)
                        context.finish()
                        timings.append((time.perf_counter()-stamp)*1000)
                        image = Image.frombytes("RGB", (width, height), target.read(components=3, alignment=1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        if index % args.fps == args.fps//2:
                            image.save(args.output/(f"{int(elapsed):02d}-"+stage+".png"))
                            if stage == "generating":
                                thinking_frame, thinking_art = dict(frame), dict(packet["art"])
                                image.save(args.output/"gpu-thinking-hud-on.png")
                                renderer.render(**frame, target=target)
                                hud.render({**values, "cognitive": ""}, width, height, target=target)
                                context.finish()
                                off = Image.frombytes("RGB", (width, height), target.read(components=3, alignment=1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                                off.save(args.output/"gpu-thinking-hud-off.png")
                                bounds = (0, layout(width, height)["header_height"], width, height)
                                if ImageChops.difference(image, off).crop(bounds).getbbox() is not None:
                                    raise RuntimeError("Cognitive HUD changed pixels outside its existing header")
                        encoder.stdin.write(image.tobytes())
                        trace.append({"frame": index, "time_s": elapsed, "injected_activity": stage,
                                      "observed_contract": owner.snapshot(now=now), "hud": text,
                                      "visual_state": packet["hud"]["state"], "rms": frame["rms"]})
                encoder.stdin.close()
                if encoder.wait(timeout=30):
                    raise RuntimeError(encoder.stderr.read().decode())
                if thinking_frame is None:
                    raise RuntimeError("THINKING proof missing")
                with patch("time.monotonic", return_value=origin+len(STAGES)):
                    view.update_event("thinking")
                    view._gpu_size = (400, 300)
                    view._render()
                    view._cancel_animation()
                    mini_packet = view._gpu.latest
                    mini_frame, _ = _fresh_frame(mini_packet, origin+len(STAGES))
                    mini_frame.pop("art", None)
                small = context.simple_framebuffer((400, 300), components=3)
                try:
                    renderer.render(**mini_frame, target=small)
                    hud.render({"state": "thinking", "cognitive": "Préparation du contexte · DÉMO",
                                "preview": "DÉMO HORS LIGNE · aucun audio"}, 400, 300, target=small)
                    context.finish()
                    Image.frombytes("RGB", (400, 300), small.read(components=3, alignment=1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(args.output/"gpu-mini-hud.png")
                finally:
                    small.release()
                if args.benchmark:
                    benchmark = _benchmark(context, renderer, thinking_frame, target, thinking_art, args.baseline)
                owner.update("idle")
                owner.update("generating")
                app.cognitive_view.refresh(force=True)
                view.set_engine("canvas")
                view.window.geometry("960x640+20+20")
                view.update_event("thinking")
                view.update_cognitive("DÉMO HORS LIGNE · Génération locale · aucun modèle ouvert")
                capture_widget(view.window, args.output/"canvas-thinking-hud.png")
                view.set_options(mini_mode=True)
                view.window.geometry("400x300+20+20")
                view.update_cognitive("DÉMO · Génération locale")
                capture_widget(view.window, args.output/"canvas-mini-hud.png")
                actions = _capture_actions(app, args.output)
            finally:
                app.close()
        try:
            import resource
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform == "darwin" else 1024)
        except ImportError:
            rss = None
        sources = ("jarvis/cognitive_state.py", "jarvis/cognitive_ui.py", "jarvis/ui.py",
                   "jarvis/presence.py", "jarvis/presence_host.py", "jarvis/gpu_hud.py",
                   "jarvis/gpu_session.py", "jarvis/gpu_renderer.py", "jarvis/reactor_shaders.py", "scripts/capture_cognitive_hud.py")
        report = {"scope": "Real IntegratedPresence→validated packet→production GpuRenderer+GpuHud; injected CognitiveState activities, synthetic16kHz PCM, audio and transport doubles. No microphone/Piper/Ollama/network/userDB. Header on/off comparison leaves all other pixels identical.",
                  "platform": platform.platform(), "context": context_info(context), "resolution": [width, height],
                  "video_seconds": len(STAGES), "video_fps": args.fps, "video_fps_scope": "Encoding cadence only, not real rendered/presented FPS", "trace": trace,
                  "selection_demo": actions,
                  "capture_metrics": {"render_gl_hud_finish_mean_ms": statistics.mean(timings), "render_gl_hud_finish_p95_ms": sorted(timings)[math.ceil(.95*len(timings))-1],
                                      "process_cpu_seconds_including_capture_and_benchmark": time.process_time()-cpu_start,
                                      "wall_seconds_including_capture_and_benchmark": time.perf_counter()-wall_start,
                                      "max_rss_bytes_entire_capture_process": rss,
                                      "owned_renderer_hud_bytes_estimate": renderer.allocation_bytes+hud.allocation_bytes,
                                      "physical_vram": None, "piper_latency": None, "ollama_ttft": None},
                  "benchmark": benchmark, "source_sha256": {name: digest(REPO/name) for name in sources},
                  "artifact_sha256": {path.name: digest(path) for path in args.output.iterdir() if path.is_file()}}
        (args.output/"cognitive-hud-evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "frames": len(trace), "capture_metrics": report["capture_metrics"]}, ensure_ascii=False))
    finally:
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait()
        hud.shutdown()
        renderer.shutdown()
        target.release()
        context.release()


if __name__ == "__main__":
    main()
