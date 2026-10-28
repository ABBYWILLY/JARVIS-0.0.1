#!/usr/bin/env python3
"""Capture the real integrated parent → packet → GL/HUD path, offline.

The audio process and GPU transport are explicit doubles. Synthesised PCM and
manual states demonstrate software routing only, never microphone/Piper/RTX
validation. No model, sound device, network request or user database is opened.
Requires Tk/X11, EGL, optional GPU requirements, NumPy and ffmpeg.
"""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class OfflineAudio:
    """Intentionally disabled device boundary; never emits pretend audio."""
    process = None
    kind = None

    def alive(self):
        return False

    def poll(self):
        return []

    def send(self, _command):
        return False

    def stop(self):
        pass


class CaptureTransport:
    """Retain one validated latest packet for the actual EGL render path."""
    def __init__(self):
        self.events = []
        self.running = False
        self.latest = None

    def start(self):
        self.running = True
        self.events.append({"kind": "ready", "renderer": {"acceleration": "capture_transport_double"}})
        return True

    def alive(self):
        return self.running

    def poll(self):
        events, self.events = self.events, []
        return events

    def submit(self, packet):
        from jarvis.gpu_session import validate_packet
        self.latest = validate_packet(packet)
        return self.running

    def stop(self):
        self.running = False


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_widget(window, path):
    from PIL import ImageGrab
    window.deiconify()
    window.lift()
    window.update()
    x, y = window.winfo_rootx(), window.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height())).save(path)


def capture_toggle(app, renderer, hud, target, output, fps, ffmpeg):
    """Record actual Tk/GPU frames while exercising the parent's engine commands.

    The capture transport is an explicit local double. Native spawned IPC and
    real GLFW mouse input are checked separately; this is a visual walkthrough.
    """
    from PIL import Image, ImageGrab
    import queue
    import threading
    from jarvis.gpu_hud import layout
    from jarvis.gpu_session import _dispatch_action, _fresh_frame
    width, height = 960, 640
    path = output / "presence-gpu31-toggle.mp4"
    encoder = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast",
        "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    view = app.presence
    origin = max(time.monotonic(), view.model.last_frame or 0.,
                 getattr(view._gpu_scene, "last_frame", 0.) or 0.) + .05
    transitions = []
    try:
        view.set_engine("canvas")
        view.window.geometry("960x640+20+20")
        app.root.update()
        for index in range(3 * fps):
            now = origin + index/fps
            with patch("time.monotonic", return_value=now):
                if index == fps:
                    view.engine_buttons["gpu"].invoke()  # Actual Tk control.
                    app.root.update()
                    transitions.append({"frame": index, "command": "Tk engine_buttons[gpu].invoke", "active": view.active_engine})
                elif index == 2*fps:
                    _action, (left, top, right, bottom) = layout(width, height)["engine_buttons"][0]
                    action = hud.hit_test((left+right)/2, (top+bottom)/2, width, height)
                    channel = queue.Queue(16)
                    _dispatch_action(channel, threading.Event(), action)
                    view._gpu.events.append(channel.get_nowait())
                    view._poll_gpu()  # The same parent action handler; transport is a double.
                    app.root.update()
                    transitions.append({"frame": index, "command": "GpuHud.hit_test → validated action → parent", "active": view.active_engine})
                view.update_event("thinking")
                view._render()
                view._cancel_animation()
                if view.active_engine == "gpu":
                    packet = view._gpu.latest
                    frame, _mask = _fresh_frame(packet, now)
                    frame.pop("art", None)
                    renderer.set_settings(packet["art"])
                    renderer.render(**frame, target=target)
                    hud.render({**packet["hud"], "preview": "DÉMO HORS LIGNE · transport de capture doublé · aucun audio"}, width, height, target=target)
                    renderer.ctx.finish()
                    image = Image.frombytes("RGB", (width, height), target.read(components=3, alignment=1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                else:
                    app.root.update()
                    view.state_label.configure(text="DÉMO HORS LIGNE · aucun audio ni modèle")
                    x, y = view.window.winfo_rootx(), view.window.winfo_rooty()
                    if (view.window.winfo_width(), view.window.winfo_height()) != (width, height):
                        raise RuntimeError("Toggle capture must remain at native 960×640.")
                    image = ImageGrab.grab(bbox=(x, y, x+width, y+height)).convert("RGB")
                if index in (fps//2, fps+fps//2, 2*fps+fps//2):
                    name = ("canvas", "gpu", "canvas-return")[index//fps]
                    image.save(output / ("presence-gpu31-toggle-" + name + ".png"))
            encoder.stdin.write(image.tobytes())
        encoder.stdin.close()
        error = encoder.stderr.read().decode("utf-8", "replace")
        if encoder.wait(timeout=30):
            raise RuntimeError("ffmpeg: " + error)
        if [entry["active"] for entry in transitions] != ["gpu", "canvas"]:
            raise RuntimeError("Toggle walkthrough did not reach both actual parent engines.")
        return {"video": path.name, "duration_s": 3, "encoded_fps": fps, "frames": 3*fps,
                "scope": "Actual Tk and EGL/HUD frames; capture transport double, native IPC tested separately; not a FPS benchmark", "transitions": transitions}
    finally:
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait(timeout=10)


def capture_hud_comparison(output):
    """Compare actual 4K text rasterization, with no bitmap resampling."""
    import moderngl
    from jarvis.presence_gpu import context_info, save_png
    output.mkdir(parents=True, exist_ok=False)
    width, height = 3840, 2160
    context = moderngl.create_standalone_context(require=330, backend="egl")
    target = context.simple_framebuffer((width, height), components=3)
    report = {"physical_framebuffer_size": [width, height], "dpi_scale": 2.,
              "method": "Actual EGL HUD drawn on a black native 3840x2160 framebuffer; no resize, crop or bitmap sharpening",
              "context": context_info(context), "audio_and_models": "not_opened",
              "hardware_validation": "pending", "captures": {}}
    values = {"state": "thinking", "microphone": "désactivé · aucune capture matérielle",
              "caption": "Heureux de vous revoir 😊 — cœur, été et 12,50 €.",
              "caption_marks": [(0, 7)], "caption_note": "Comparaison de netteté HiDPI · rendu natif · aucune voix ni microphone",
              "preview": "DÉMO HORS LIGNE · texte rasterisé à DPI 200 %", "dpi_scale": 2.}
    try:
        for name, revision in (("before", "4ae4f71"), ("after", "current")):
            raw = ((REPO / "jarvis/gpu_hud.py").read_bytes() if revision == "current" else
                   subprocess.check_output(["git", "show", revision + ":jarvis/gpu_hud.py"], cwd=REPO))
            with tempfile.TemporaryDirectory(prefix="jarvis-hud-capture-") as directory:
                path = Path(directory) / "gpu_hud.py"
                path.write_bytes(raw)
                module_name = "_jarvis_gpu31_hud_capture_" + name
                spec = importlib.util.spec_from_file_location(module_name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                hud = None
                try:
                    spec.loader.exec_module(module)
                    hud = module.GpuHud(context)
                    target.clear(0., 0., 0., 1.)
                    hud.render(values, width, height, target=target)
                    context.finish()
                    image = output / ("presence-gpu31-hud-4k-" + name + ".png")
                    save_png(image, (width, height), target.read(components=3, alignment=1))
                    report["captures"][name] = {"revision": revision, "source_sha256": hashlib.sha256(raw).hexdigest(),
                        "path": image.name, "sha256": digest(image), "atlas_size": hud._size,
                        "raster_info": getattr(hud, "raster_info", None),
                        "allocation_bytes_estimate": hud.allocation_bytes}
                finally:
                    if hud is not None:
                        hud.shutdown()
                    sys.modules.pop(module_name, None)
        (output / "presence-gpu31-hud-4k.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(output), "physical_size": [width, height],
                          "atlas_before": report["captures"]["before"]["atlas_size"],
                          "atlas_after": report["captures"]["after"]["atlas_size"]}))
    finally:
        target.release()
        context.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing data is never overwritten")
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--hud-comparison", action="store_true", help="Capture native 4K before/after HUD text only; no video or audio")
    parser.add_argument("--gpu31", action="store_true", help="Capture GPU 3.1 state clips, visible engine toggles and Studio additions")
    args = parser.parse_args(argv)
    if args.hud_comparison:
        return capture_hud_comparison(args.output)
    if not 8 <= args.fps <= 30:
        parser.error("Choose 8–30 frames/s for this offline recording.")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        parser.error("ffmpeg is required to produce the MP4 proof.")
    args.output.mkdir(parents=True, exist_ok=False)

    import moderngl
    import numpy as np
    from PIL import Image
    import tkinter as tk
    from jarvis.audio import signal_view
    from jarvis.audio_spectrum import PCMSpectrum
    from jarvis.gpu_hud import GpuHud
    from jarvis.gpu_renderer import GpuRenderer
    from jarvis.gpu_session import _fresh_frame
    from jarvis.presence_gpu import context_info
    from jarvis.richtext import parse_text
    from jarvis.storage import Store
    from jarvis.ui import App

    width, height = 960, 640
    context = moderngl.create_standalone_context(require=330, backend="egl")
    renderer = GpuRenderer(context, width, height, quality="balanced")
    hud = GpuHud(context)
    target = context.simple_framebuffer((width, height), components=3)
    trace, timings, snapshots = [], [], {}
    before_cpu, before_wall = time.process_time(), time.perf_counter()
    duration = 12 if args.gpu31 else 9
    video = args.output / ("presence-gpu31-demo.mp4" if args.gpu31 else "presence-integrated-demo.mp4")
    encoder = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(args.fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast",
        "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video)], stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis-offline-capture-") as folder, \
                patch("jarvis.voice_ui.AudioProcess", OfflineAudio):
            store, root = Store(Path(folder) / "capture.sqlite3"), tk.Tk()
            app = App(root, store, refresh=False)
            try:
                view = app.presence
                view.session_factory = CaptureTransport
                view.set_engine("gpu")
                root.update()
                view._cancel_animation()
                if view.active_engine != "gpu":
                    raise RuntimeError("Integrated parent did not accept the capture transport.")
                origin = time.monotonic()
                phrase = "Heureux de te revoir 😊"
                document = parse_text(phrase)
                events, plan = view.prepare_segment(phrase, document.text, 0)
                queued = completed = False
                spectrum = PCMSpectrum()
                rate = 16000
                for index in range(duration * args.fps):
                    elapsed = index / args.fps
                    now = origin + elapsed
                    if args.gpu31:
                        edges = ((.75, "repos", "silent"), (1.5, "micro ouvert · silence", "listening"),
                                 (3.25, "écoute", "user_speaking"), (5.25, "thinking", "thinking"),
                                 (8., "parole", "jarvis_speaking"), (9.6, "expression", "silent"),
                                 (10.5, "interruption", "user_speaking"), (12., "retour au repos", "silent"))
                        _edge, stage, state = next(row for row in edges if elapsed < row[0])
                    elif elapsed < .75:
                        stage, state = "repos", "silent"
                    elif elapsed < 2:
                        stage, state = "écoute", "user_speaking"
                    elif elapsed < 3.5:
                        stage, state = "thinking", "thinking"
                    elif elapsed < 5.5:
                        stage, state = "parole", "jarvis_speaking"
                    elif elapsed < 7.1:
                        stage, state = "expression", "silent"
                    elif elapsed < 8:
                        stage, state = "interruption", "user_speaking"
                    else:
                        stage, state = "retour au repos", "silent"
                    with patch("time.monotonic", return_value=now):
                        caption = None
                        samples = np.zeros(640, dtype="float32")
                        if state in {"user_speaking", "jarvis_speaking"}:
                            amplitude = (.075 * max(0., math.sin(elapsed*math.pi*5))**.7
                                         if args.gpu31 else .035 + .055 * (.5 + .5 * math.sin(elapsed * 7)))
                            position = np.arange(640) / rate + elapsed
                            samples = (amplitude * (np.sin(2*np.pi*180*position) + .5*np.sin(2*np.pi*950*position)
                                        + .2*np.sin(2*np.pi*3200*position))).astype("float32")
                        signal = signal_view(samples)
                        signal.update(captured_at=now, emitted_at=now, delay=0., bands=tuple(spectrum.analyze(samples, rate)))
                        if state == "jarvis_speaking":
                            if not queued:
                                view.begin_response()
                                view.queue_expressions(1, 1, phrase, 0, len(phrase), document.events)
                                queued = True
                            caption = {"response_id": 1, "segment_id": 1, "text": document.text,
                                       "fraction": min(1., (elapsed-(5.25 if args.gpu31 else 3.5))/(2.75 if args.gpu31 else 2)), "caption_plan": asdict(plan),
                                       "spectrum_events": [asdict(event) for event in events]}
                        if stage == "expression" and not completed:
                            view.complete_segment({"response_id": 1, "segment_id": 1, "completed_at": now})
                            completed = True
                        # A repeated silent event would clear the prepared caption;
                        # preserve the real segment completion's existing hold.
                        if stage != "expression":
                            view.update_event(state, signal=signal, caption=caption)
                        view._render()
                        view._cancel_animation()
                        packet = view._gpu.latest
                        frame, _mask = _fresh_frame(packet, now)
                        frame.pop("art", None)
                        values = {**packet["hud"], "preview": "DÉMO HORS LIGNE · signaux synthétiques · aucun micro / Piper",
                                  "caption_note": "Événements de test ; synchronisation audio matérielle non validée"}
                        renderer.set_settings(packet["art"])
                        started = time.perf_counter()
                        renderer.render(**frame, target=target)
                        hud.render(values, width, height, target=target)
                        context.finish()
                        timings.append((time.perf_counter()-started)*1000)
                        image = Image.frombytes("RGB", (width, height), target.read(components=3, alignment=1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    encoder.stdin.write(image.tobytes())
                    trace.append({"time_s": round(elapsed, 4), "state": packet["hud"]["state"], "stage": stage,
                                  "surface_family": frame.get("surface_family"), "surface_amount": frame.get("surface_amount"),
                                  "rms": frame["rms"], "bands": frame["audio_bands"],
                                  **{key: frame.get(key) for key in ("visual_state", "visual_mix", "voice_envelopes", "receipt", "input_energy")}})
                    requests = ({"écoute": 2.9, "thinking": 4.8, "parole": 7.7, "expression": 8.6,
                                 "interruption": 9.85, "retour au repos": 11.8} if args.gpu31 else
                                {"thinking": 2.9, "parole": 4.7, "expression": 6.1,
                                 "interruption": 7.5, "retour au repos": 8.8})
                    if stage in requests and elapsed >= requests[stage] and stage not in snapshots:
                        name = {"retour au repos": "idle", "parole": "speaking", "expression": "smile"}.get(stage, stage)
                        path = args.output / (("presence-gpu31-" if args.gpu31 else "presence-integrated-") + name + ".png")
                        image.save(path)
                        snapshots[stage] = path.name
                if not any(row["surface_family"] == "smile" and row["surface_amount"] > .95 for row in trace):
                    raise RuntimeError("No fully visible smile reached the actual renderer.")
                if any(row["surface_family"] is not None for row in trace if row["stage"] == "interruption"):
                    raise RuntimeError("The interruption failed to cancel the expression.")
                if args.gpu31:
                    if not any(max(row["voice_envelopes"] or (0.,)) > .1 for row in trace if row["stage"] == "parole"):
                        raise RuntimeError("No expressive envelope reached the speaking renderer.")
                    if any(max(row["voice_envelopes"] or (0.,)) > 0 for row in trace if row["stage"] == "interruption"):
                        raise RuntimeError("Interruption retained an outgoing voice envelope.")
                    toggle = capture_toggle(app, renderer, hud, target, args.output, args.fps, ffmpeg)
                # True Tk editors, independent of any audio/GPU hardware.
                view.set_engine("canvas")
                view.window.geometry("960x640+20+20")
                root.update()
                view.update_event("silent")
                view.preview_workshop()
                view._cancel_animation()
                canvas_clock = max(time.monotonic(), view.model.last_frame or 0.)
                for step in range(12):
                    with patch("time.monotonic", return_value=canvas_clock+(step+1)/10):
                        view._render()
                        view._cancel_animation()
                capture_widget(view.window, args.output / "presence-integrated-classic-thinking.png")
                view.clear_preview()
                selector = view.open_engine_settings()
                selector.geometry("540x560+20+20")
                capture_widget(selector, args.output / "presence-integrated-engine-selector.png")
                selector.destroy()
                studio = view.open_canvas_settings()
                studio.geometry("700x730+20+20")
                capture_widget(studio, args.output / "presence-integrated-studio-2d.png")
                view.studio.cancel()
                studio = view.open_gpu_settings()
                studio.geometry("700x760+20+20")
                capture_widget(studio, args.output / "presence-integrated-studio-gpu.png")
                if args.gpu31:
                    if not studio.focus_control("render_scale"):
                        raise RuntimeError("The render-scale editor is unavailable.")
                    capture_widget(studio, args.output / "presence-gpu31-studio-scale.png")
                    reference_button = view.gpu_studio.profile_row.children["reference_30"]
                    reference_button.invoke()
                    reference_button.focus_force()
                    root.update()
                    if any(getattr(view.gpu_studio.draft, key) != 0 for key in
                           ("pulse_radius", "converging_intensity", "radiating_intensity")):
                        raise RuntimeError("The 3.0 reference artwork preset did not reach the draft.")
                    capture_widget(studio, args.output / "presence-gpu31-studio-reference.png")
            finally:
                app.close()
        encoder.stdin.close()
        error = encoder.stderr.read().decode("utf-8", "replace")
        if encoder.wait(timeout=30):
            raise RuntimeError("ffmpeg: " + error)
        if args.gpu31:
            clips = {"listening": (.75, 2.5), "thinking": (3.25, 2.), "speaking": (5.25, 4.35)}
            for name, (start, length) in clips.items():
                subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video), "-ss", str(start),
                    "-t", str(length), "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(args.output / ("presence-gpu31-" + name + ".mp4"))], check=True)
        elapsed_wall = time.perf_counter()-before_wall
        elapsed_cpu = time.process_time()-before_cpu
        try:
            import resource
            maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            maximum_rss *= 1 if sys.platform == "darwin" else 1024
        except ImportError:
            maximum_rss = None
        files = sorted(path for path in args.output.iterdir() if path.is_file())
        source_names = ("jarvis/presence_host.py", "jarvis/presence.py", "jarvis/presence_gpu.py", "jarvis/gpu_config.py",
                        "jarvis/gpu_renderer.py", "jarvis/reactor_shaders.py", "jarvis/gpu_hud.py", "jarvis/gpu_session.py",
                        "jarvis/gpu_studio.py", "jarvis/gpu_pacing.py",
                        "scripts/capture_presence_integration.py")
        metrics = {"scope": "Offline capture including GUI setup, readback, image saves and video pipe; not a live Jarvis/Ollama benchmark",
                   "render_scope": "Real EGL GpuRenderer + GpuHud and context.finish; readback/encoding excluded",
                   "mean_render_ms": sum(timings)/len(timings), "p95_render_ms": sorted(timings)[math.ceil(.95*len(timings))-1],
                   "wall_seconds_including_capture": elapsed_wall, "process_cpu_seconds_including_capture": elapsed_cpu,
                   "renderer_hud_owned_bytes_estimate_excluding_capture_framebuffer": renderer.allocation_bytes + hud.allocation_bytes,
                   "maximum_process_rss_bytes_including_capture": maximum_rss,
                   "real_vram_measurement": None, "ollama_impact": "not measured", "audio_latency": "not measured"}
        report = {"context": context_info(context), "platform": platform.platform(), "resolution": [width, height],
                  "video_seconds": duration, "video_fps": args.fps, "frames": len(trace), "hardware_validation": "pending",
                  "video_fps_scope": "Offline animation encoding cadence, not measured live draw/presentation FPS",
                  "method": "Actual IntegratedPresence queue_expressions/update_event/complete_segment, validated latest packet, actual EGL GpuRenderer+GpuHud; explicit audio and transport doubles",
                  "audio_source": "Synthetic 16kHz PCM tones; no microphone, Piper or Ollama", "metrics": metrics,
                  "snapshots": snapshots, "source_sha256": {name: digest(REPO/name) for name in source_names},
                  "artifacts_sha256": {path.name: digest(path) for path in files}, "trace": trace,
                  "semantic_diagnostics": view.semantic_diagnostics()}
        if args.gpu31:
            report["toggle_walkthrough"] = toggle
        (args.output / "presence-integrated-evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "frames": len(trace), "context": report["context"], "metrics": metrics}, ensure_ascii=False))
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
