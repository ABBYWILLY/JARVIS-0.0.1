#!/usr/bin/env python3
"""Measure one isolated prototype case and capture its real framebuffer.

Run each case in a fresh process, before and after a change. A reference commit
loads only its renderer and shaders in a temporary package; the working tree is
never overwritten. Requires the optional GPU dependencies and a real GL context.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
CASES = ("idle", "eco", "balanced", "cinematic", "reduced", "expression")


def validate_revision(value):
    if value != "current" and not re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
        raise ValueError("Use current or a commit SHA of 7–40 hexadecimal digits.")
    return value


@contextmanager
def renderer_source(revision):
    """Yield a renderer class and exact source hashes, with no persistent copy."""
    validate_revision(revision)
    sources = {}
    for name in ("gpu_renderer.py", "reactor_shaders.py"):
        sources[name] = ((REPO / "jarvis" / name).read_bytes() if revision == "current" else
                         subprocess.check_output(["git", "show", revision + ":jarvis/" + name], cwd=REPO))
    support = REPO / "jarvis/gpu_config.py"
    if revision == "current":
        if support.exists():
            sources["gpu_config.py"] = support.read_bytes()
    elif subprocess.run(["git", "cat-file", "-e", revision + ":jarvis/gpu_config.py"],
                        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        sources["gpu_config.py"] = subprocess.check_output(
            ["git", "show", revision + ":jarvis/gpu_config.py"], cwd=REPO)
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}
    # Copy current before import, so lazy relative imports do not re-read later
    # edits. Callers keep both source files stable while this copy is prepared.
    with tempfile.TemporaryDirectory(prefix="jarvis-gpu-comparison-") as folder:
        root = Path(folder)
        (root / "__init__.py").write_text("")
        for name, raw in sources.items():
            (root / name).write_bytes(raw)
        package = "_jarvis_gpu_comparison_source_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(package, root / "__init__.py",
                                                      submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[package] = module
        try:
            spec.loader.exec_module(module)
            yield importlib.import_module(package + ".gpu_renderer").GpuRenderer, hashes
        finally:
            for name in tuple(sys.modules):
                if name == package or name.startswith(package + "."):
                    del sys.modules[name]


@contextmanager
def scene_source(revision):
    """Freeze the selected state adapter; shared Canvas/morph code is unchanged.

    Its temporary module belongs to jarvis so relative, model-free imports use
    the existing common modules. No old files are installed over the worktree.
    """
    validate_revision(revision)
    raw = ((REPO / "jarvis/presence_gpu.py").read_bytes() if revision == "current" else
           subprocess.check_output(["git", "show", revision + ":jarvis/presence_gpu.py"], cwd=REPO))
    with tempfile.TemporaryDirectory(prefix="jarvis-gpu-scene-") as folder:
        path = Path(folder) / "presence_gpu.py"
        path.write_bytes(raw)
        name = "jarvis._gpu_comparison_scene_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
            yield module.ReactorScene, hashlib.sha256(raw).hexdigest()
        finally:
            sys.modules.pop(name, None)


def compatible_frame(snapshot, parameters):
    """Adapt an explicitly shared scene to an older renderer, recording omissions."""
    return ({key: value for key, value in snapshot.items() if key in parameters},
            sorted(set(snapshot) - set(parameters)))


def measure(args):
    import moderngl
    from jarvis.gpu_benchmark import FrameTimings, ProcessSampler
    from jarvis.presence_gpu import context_info, save_png

    args.output.mkdir(parents=True, exist_ok=False)
    context = moderngl.create_standalone_context(require=330, **({"backend": "egl"} if args.backend == "egl" else {}))
    renderer = target = sampler = None
    try:
        info = context_info(context)
        quality = args.case if args.case in {"eco", "cinematic"} else "balanced"
        scene_revision = args.revision if args.historical_scene else "current"
        with renderer_source(args.revision) as (factory, hashes), scene_source(scene_revision) as (scene_factory, scene_hash):
            renderer = factory(context, args.width, args.height, quality=quality)
            target = context.simple_framebuffer((args.width, args.height))
            scene = scene_factory(reduced_motion=args.case == "reduced")
            if hasattr(scene, "set_settings"):
                scene.set_settings({"profile": quality})
            parameters = frozenset(inspect.signature(factory.render).parameters)
            scene.update_state("silent" if args.case == "idle" else "thinking", now=0.)
            for index in range(121):
                snapshot = scene.snapshot(args.width, args.height, now=index / 30)
                if args.case == "expression" and index == 108:
                    scene.preview_expression("Heureux de te revoir 😊", args.width, args.height, now=index/30)
            # Fixed t=4s, color/state/resolution/policy are identical in both versions.
            frame, omitted = compatible_frame(snapshot, parameters)
            renderer.render(**frame, target=target)
            context.finish()
            save_png(args.output / "frame.png", renderer.size, renderer.read_rgb())
            timings = FrameTimings()
            sampler = ProcessSampler(interval=.5).start()
            started = time.monotonic()
            last_expression = 3.6
            interval = 1 / (15 if quality == "eco" else 45 if quality == "cinematic" else 30)
            static = args.case in {"idle", "reduced"}
            while time.monotonic() - started < args.seconds:
                frame_start = time.monotonic()
                scene_time = 4 + frame_start - started
                if args.case == "expression" and scene_time - last_expression >= 1.5:
                    scene.preview_expression("Heureux de te revoir 😊", args.width, args.height, now=scene_time)
                    last_expression = scene_time
                snapshot = scene.snapshot(args.width, args.height, now=scene_time)
                frame, dropped = compatible_frame(snapshot, parameters)
                omitted = sorted(set(omitted) | set(dropped))
                renderer.render(**frame, target=target)
                context.finish()
                rendered = time.monotonic() - frame_start
                remaining = (args.seconds - (time.monotonic() - started) if static else interval - rendered)
                if remaining > 0:
                    time.sleep(remaining)
                timings.record(rendered, time.monotonic() - frame_start)
                if static:
                    break
            process = sampler.stop()
            sampler = None
            report = {"revision": args.revision, "case": args.case, "quality": quality,
                      "environment": {"os": platform.platform(), "python": sys.version},
                      "source_sha256": hashes, "context": info, "size": renderer.size,
                      "scene_revision": scene_revision, "scene_source_sha256": scene_hash,
                      "omitted_snapshot_fields": omitted,
                      "shared_scene_sha256": {name: hashlib.sha256((REPO / "jarvis" / name).read_bytes()).hexdigest()
                                              for name in ("presence.py", "morphing.py")},
                      "reference_scope": ("Renderer, shaders and state adapter from each revision; shared Canvas/morph modules unchanged."
                                          if args.historical_scene else
                                          "Renderer/shaders snapshot; current shared state adapter. Unsupported fields explicitly listed."),
                      "capture_time_seconds": 4., "capture_origin": "actual OpenGL RGB framebuffer",
                      "capture_benchmark_note": "Capture/readback/shader warm-up excluded from measurement.",
                      "expression_policy": ("Offline smile every 1.5s, existing controller owns duration; no audio or live Piper."
                                            if args.case == "expression" else None),
                      "timing": timings.summary(), "process": process,
                      "requested_graphics_bytes": renderer.allocation_bytes,
                      "attachment_bytes": renderer.attachment_bytes,
                      "physical_vram_bytes": None, "gpu_time_ms": None, "power_watts": None,
                      "ai_voice_latency_ms": None,
                      "unavailable_reasons": {"physical_vram_bytes": "No per-process physical graphics-memory measurement.",
                                              "gpu_time_ms": "No GPU timestamp query measured.",
                                              "power_watts": "No device power counter measured.",
                                              "ai_voice_latency_ms": "AI/audio engines are not active in this isolated prototype."},
                      "limitations": ["Software Mesa is not an RTX measurement.",
                                       "Requested resource bytes exclude driver/program/default framebuffer costs.",
                                       "No Ollama, microphone, Whisper or Piper is active."]}
            report["timing"]["render_scope"] = "wall_submission_and_driver_finish"
            report["timing"]["frame_scope"] = "wall_frame_including_pacing_wait"
            renderer.shutdown()
            if renderer.release_errors:
                raise RuntimeError("Renderer cleanup failed: " + "; ".join(renderer.release_errors))
            renderer = None
            with (args.output / "report.json").open("x", encoding="utf-8") as output:
                json.dump(report, output, indent=2, allow_nan=False)
            return report
    finally:
        if sampler is not None:
            sampler.stop()
        if renderer is not None:
            renderer.shutdown()
        if target is not None:
            target.release()
        context.release()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="current", type=validate_revision)
    parser.add_argument("--historical-scene", action="store_true",
                        help="Also use that revision's state adapter; recommended when comparing state changes")
    parser.add_argument("--case", choices=CASES, default="balanced")
    parser.add_argument("--seconds", type=float, default=5.)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--backend", choices=("egl", "default"), default="egl")
    parser.add_argument("--output", type=Path, required=True, help="New output directory, never overwritten")
    args = parser.parse_args(argv)
    if (not math.isfinite(args.seconds) or not .1 <= args.seconds <= 60
            or not 64 <= args.width <= 1920 or not 64 <= args.height <= 1080):
        parser.error("Duration must be .1–60s; dimensions 64–1920 by 64–1080.")
    if args.output.exists():
        parser.error("Output directory already exists; choose a new path.")
    return args


def main(argv=None):
    args = parse_args(argv)
    report = measure(args)
    print(json.dumps({"case": report["case"], "fps": report["timing"]["fps"],
                      "cpu_percent": report["process"]["cpu_average_percent"],
                      "rss_bytes": report["process"]["rss_average_bytes"],
                      "context": report["context"]["renderer"]}))


if __name__ == "__main__":
    main()
