#!/usr/bin/env python3
"""Compare bounded PRESENCE costs using synthetic PCM and a real Tk display.

Run each mode in the same Python/Tk/display environment, for example:
    DISPLAY=:99 python scripts/benchmark_presence.py baseline --output /tmp/before.json
    DISPLAY=:99 python scripts/benchmark_presence.py candidate --output /tmp/after.json

The baseline defaults to git revision 55311d1; --baseline-revision selects a SHA.
Both modes import
jarvis.spectrum and jarvis.audio from the current checkout. Source snapshots are
temporary files outside the checkout. No models, microphone or playback are used.
Only standard-library modules and the local repository are imported.
"""
import argparse
import gc
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import tracemalloc
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[1]
BASE_REV = "55311d1"
REPEATS, MODEL_FRAMES, TK_FRAMES, ALLOC_FRAMES = 3, 100, 24, 24
CASES = [("balanced", "silent"), ("balanced", "dormant"),
         ("eco", "thinking"), ("balanced", "thinking"), ("cinematic", "thinking"),
         ("balanced", "user_speaking"), ("balanced", "jarvis_speaking")]
ACTIVE = {"user_speaking", "jarvis_speaking"}


def parse_args():
    parser = argparse.ArgumentParser(description=(
        "Measure PRESENCE process CPU/frame and Python allocation peaks with "
        "a real Tk display and a generated synthetic PCM fixture. No real "
        "microphone, playback, models or audio-latency measurements are used. "
        "Baseline: selected commit's presence.py, with current checkout dependencies."))
    parser.add_argument("mode", choices=("baseline", "candidate"))
    parser.add_argument("--baseline-revision", default=BASE_REV,
                        help="Baseline commit SHA (7–40 hex digits; default: %(default)s)")
    parser.add_argument("--output", type=Path, required=True,
                        help="New JSON output path; an existing file is never overwritten")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", args.baseline_revision):
        parser.error("Baseline revision must be a commit SHA")
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    if not args.output.parent.is_dir():
        parser.error(f"Output directory does not exist: {args.output.parent}")
    return args


def cpu_us(factory, frames):
    runs = []
    for _ in range(REPEATS):
        run = factory(frames)
        gc.collect()
        started = time.process_time_ns()
        run()
        runs.append((time.process_time_ns() - started) / frames / 1000)
    return round(statistics.median(runs), 2)


def peak_kib(factory):
    run = factory(ALLOC_FRAMES)
    gc.collect()
    tracemalloc.start()
    try:
        run()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return round(peak / 1024, 2), round(current / 1024, 2)


def measure(p, signal, result):
    clock = SimpleNamespace(value=1000.0)
    # Controlled frame times avoid a dependence on the speed of an unpaced loop.
    p.time = SimpleNamespace(monotonic=lambda: clock.value)

    def feed(model, state, index, fps):
        clock.value += 1 / fps
        # Refresh the fixture at rendering opportunities after at least 32 ms.
        if state in ACTIVE and (index == 0 or clock.value - model.signal_at >= .032):
            model.update_event(state, signal, now=clock.value)

    def model_probe(profile, state, method, frames):
        model = p.PresenceModel(p.PresenceSettings(profile=profile))
        model.update_event(state, signal if state in ACTIVE else None, now=clock.value)
        fps = p.PROFILES[profile][0]
        operation = getattr(model, method)
        for index in range(8):
            feed(model, state, index, fps)
            operation(960, 640, now=clock.value)

        def run():
            for index in range(frames):
                feed(model, state, index, fps)
                operation(960, 640, now=clock.value)
        return run

    def make_view(root, profile, state):
        store = SimpleNamespace(get_preference=lambda key, default: {"profile": profile},
                                set_preference=lambda *args: None)
        app = SimpleNamespace(root=root, store=store, font_family="DejaVu Sans",
                              voice=SimpleNamespace(listening=False))
        view = p.PresenceView(app)
        view.show()
        view.window.geometry("960x640+10+10")
        root.update_idletasks()
        view._cancel_animation()
        view.model.update_event(state, signal if state in ACTIVE else None, now=clock.value)
        fps = p.PROFILES[profile][0]
        for index in range(16):
            feed(view.model, state, index, fps)
            view._render()
            root.update_idletasks()
        view._cancel_animation()
        return view

    def tk_factory(root, view, state, profile, frames):
        fps = p.PROFILES[profile][0]

        def run():
            for index in range(frames):
                feed(view.model, state, index, fps)
                view._render()
                # Includes Tcl dispatch, excludes X server CPU and timer waits.
                root.update_idletasks()
            view._cancel_animation()
        return run

    started = time.perf_counter()
    root = tk.Tk()
    root.withdraw()
    result["tk_patchlevel"] = root.tk.call("info", "patchlevel")
    result["tk_scaling"] = float(root.tk.call("tk", "scaling"))
    try:
        for profile, state in CASES:
            row = {"profile": profile, "state": state}
            for method in ("target_geometry", "frame"):
                factory = lambda frames, m=method: model_probe(profile, state, m, frames)
                row[method + "_cpu_us"] = cpu_us(factory, MODEL_FRAMES)
                row[method + "_peak_kib"], row[method + "_retained_kib"] = peak_kib(factory)
            view = make_view(root, profile, state)
            factory = lambda frames: tk_factory(root, view, state, profile, frames)
            row["tk_render_cpu_us"] = cpu_us(factory, TK_FRAMES)
            row["tk_render_peak_kib"], row["tk_render_retained_kib"] = peak_kib(factory)
            view._render()
            row["timer_scheduled"] = view.after_id is not None
            view._cancel_animation()
            row["canvas_items_start"] = len(view.canvas.find_all())
            factory(48)()
            row["canvas_items_end"] = len(view.canvas.find_all())
            view.window.withdraw()
            root.update_idletasks()
            view._render()
            row["hidden_timer_scheduled"] = view.after_id is not None
            view.close()
            result["rows"].append(row)
    finally:
        root.destroy()
    result["elapsed_seconds"] = round(time.perf_counter() - started, 2)


def main():
    args = parse_args()
    if args.mode == "baseline":
        source_bytes = subprocess.check_output([
            "git", "-C", str(REPO), "show", args.baseline_revision + ":jarvis/presence.py"])
        source_label = "git:" + args.baseline_revision + ":jarvis/presence.py"
    else:
        source_bytes = (REPO / "jarvis/presence.py").read_bytes()
        source_label = str(REPO / "jarvis/presence.py")
    sys.path.insert(0, str(REPO))
    from jarvis.audio import signal_view

    # Generated mono PCM fixture, not recorded audio or a microphone simulation.
    pcm = tuple(0.13 * math.sin(2 * math.pi * 205 * n / 16000)
                + 0.035 * math.sin(2 * math.pi * 510 * n / 16000) for n in range(512))
    result = {
        "mode": args.mode, "source": source_label,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "baseline_revision": args.baseline_revision,
        "dependencies": "jarvis.spectrum and jarvis.audio from current checkout in both modes",
        "python": platform.python_version(), "platform": platform.platform(),
        "display": os.environ.get("DISPLAY"), "dimensions": [960, 640],
        "repeats": REPEATS, "model_frames_per_repeat": MODEL_FRAMES,
        "tk_frames_per_repeat": TK_FRAMES, "allocation_frames": ALLOC_FRAMES,
        "fixture": "generated synthetic mono PCM, 16kHz/512 samples; no microphone or playback",
        "scope": ("process CPU us/frame, median of 3; separate Python tracemalloc peak KiB; "
                  "no audio latency, Windows, X server CPU, GPU, RSS or hardware measurements"),
        "rows": [],
    }
    # Freeze exactly the hashed source outside the checkout, including candidate.
    with tempfile.TemporaryDirectory(prefix="jarvis-presence-benchmark-") as directory:
        snapshot = Path(directory) / "presence.py"
        snapshot.write_bytes(source_bytes)
        name = "jarvis._presence_" + args.mode
        spec = importlib.util.spec_from_file_location(name, snapshot)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # Required by dataclasses for this package module.
        try:
            spec.loader.exec_module(module)
            measure(module, signal_view(pcm), result)
        finally:
            sys.modules.pop(name, None)
    # Exclusive creation also protects against an output-path race after parsing.
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"Saved {len(result['rows'])} cases to {args.output} ({result['elapsed_seconds']:.2f}s)")


if __name__ == "__main__":
    main()
