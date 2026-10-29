"""Opt-in, bounded measurements of the real JARVIS application.

No models are downloaded, no user archive is opened, and reports contain no
conversation, prompt, transcript or PCM. Voice scenarios retain the application's
microphone permission dialog. Run ``python -m jarvis.runtime_benchmark --help``.
"""
import argparse
from collections import Counter, OrderedDict, deque
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import statistics
import subprocess
import sys
import tempfile
import time


SCENARIOS = ("idle", "command", "canvas", "gpu-eco", "gpu-balanced", "gpu-cinematic",
             "ollama", "ollama-gpu", "piper", "capture", "conversation", "interruptions-toggle")
INTERACTIVE = frozenset(("ollama", "ollama-gpu", "capture", "conversation", "interruptions-toggle"))
VOICE_SCENARIOS = frozenset(("piper", "capture", "conversation", "interruptions-toggle"))
METRIC_KEYS = frozenset(("total_duration", "load_duration", "prompt_eval_count", "prompt_eval_duration",
                         "eval_count", "eval_duration", "response_tokens", "ttft_seconds", "tokens_per_second",
                         "stt_ms", "context_ms", "piper_ms", "tts_first_pcm_ms", "end_to_pcm_estimate_ms",
                         "silence_ms", "audio_start_estimate_ms"))
PREFERENCES = frozenset(("voice", "presence", "presence_engine", "presence_gpu", "conversation", "cognitive_hud"))
REPO = Path(__file__).resolve().parents[1]


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def numeric_metrics(values):
    """An allowlist prevents free-form model/debug content entering a report."""
    return {key: value for key, value in values.items() if key in METRIC_KEYS and finite(value)} if isinstance(values, dict) else {}


def read_json(path, limit=4 * 1024 * 1024):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError("Fichier JSON trop volumineux.")
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("JSON non fini.")))


def load_profile(path):
    """Explicit JSON only; never query/copy a personal SQLite archive."""
    values = read_json(path, 65536) if path else {}
    if not isinstance(values, dict) or set(values) - {"settings", "preferences"}:
        raise ValueError("Profil attendu : {settings: {...}, preferences: {...}}.")
    settings, preferences = values.get("settings", {}), values.get("preferences", {})
    if not isinstance(settings, dict) or not isinstance(preferences, dict) or set(preferences) - PREFERENCES:
        raise ValueError("Préférences de benchmark inconnues.")
    if any(not isinstance(value, dict) for value in preferences.values()):
        raise ValueError("Chaque famille de préférences doit être un objet JSON.")
    return {"settings": settings, "preferences": preferences}


def percentile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def metric_summary(rows):
    return {key: {"count": len(values), "median": statistics.median(values),
                  "p95": percentile(values, .95), "p99": percentile(values, .99)}
            for key in sorted(METRIC_KEYS)
            if (values := [row[key] for row in rows if key in row and finite(row[key])])}


def comparison(before, after):
    """Compare only matching workload conditions; a delta is not a speedup claim."""
    keys = ("scenario", "model", "context", "max_tokens", "requested_size", "requested_tk_scaling",
            "visual_state", "cache_state", "audio_input", "audio_output", "voice", "speech_profile",
            "speed", "acoustic_mode", "requested_gpu_profile", "actual_engine", "actual_size",
            "actual_tk_scaling", "tk_patchlevel", "silence_ms", "vad_threshold", "cpu_threads",
            "software_gpu_explicitly_allowed", "reasoning_mode", "cognitive_mode",
            "gpu_render_size", "gpu_window_size", "gpu_dpi_scale", "sample_seconds_requested",
            "warmup_seconds", "input_preferences_sha256", "effective_voice_sha256",
            "effective_canvas_sha256", "effective_gpu_sha256", "effective_settings_sha256")
    mismatches = [key for key in keys if before.get("conditions", {}).get(key) != after.get("conditions", {}).get(key)]
    for key in ("platform", "python", "renderer"):
        if before.get(key) != after.get(key):
            mismatches.append(key)
    result = {"comparable_conditions": not mismatches, "condition_mismatches": mismatches,
              "scope": "Short observations; no statistical significance or hardware extrapolation.", "metrics": {}}
    if mismatches or before.get("status") != "complete" or after.get("status") != "complete":
        result["comparable_conditions"] = False
        result["incomplete_run"] = before.get("status") != "complete" or after.get("status") != "complete"
        return result
    for key in ("startup_ms", "shutdown_ms", "process_cpu_percent_one_core", "rss_after_bytes"):
        left, right = before.get("summary", {}).get(key), after.get("summary", {}).get(key)
        if finite(left) and finite(right):
            result["metrics"][key] = {"before": left, "after": right, "delta": right - left,
                                      "delta_percent": (right-left) * 100 / left if left else None}
    for key, values in after.get("metrics", {}).items():
        left = before.get("metrics", {}).get(key, {}).get("median")
        right = values.get("median")
        if key in METRIC_KEYS and finite(left) and finite(right):
            result["metrics"][key] = {"before": left, "after": right, "delta": right-left,
                                      "delta_percent": (right-left) * 100 / left if left else None}
    return result


def write_exports(directory, report, before=None):
    """The caller reserves a new directory before any model/device is touched."""
    directory = Path(directory)
    if before is not None:
        report["comparison"] = comparison(before, report)
    with (directory / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    with (directory / "metrics.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("section", "metric", "count", "median_or_value", "p95", "p99"))
        for key, value in report.get("summary", {}).items():
            if finite(value):
                writer.writerow(("summary", key, "", value, "", ""))
        for key, value in report.get("metrics", {}).items():
            writer.writerow(("pipeline", key, value["count"], value["median"], value["p95"], value["p99"]))
    lines = ["# JARVIS — benchmark local", "", f"Statut : **{report['status']}**.",
             f"Scénario : `{report['conditions']['scenario']}`. Aucun texte ou PCM exporté.", "",
             "| Mesure | Valeur |", "| --- | ---: |"]
    for key, value in report.get("summary", {}).items():
        lines.append(f"| {key} | {value if value is not None else 'indisponible'} |")
    lines += ["", "Les temps PCM/DAC sont des estimations, pas une latence acoustique. Les mesures GPU",
              "du renderer concernent son processus ; aucune VRAM physique attribuable ni puissance",
              "électrique n'est mesurée ici. Voir report.json pour conditions et mesures manquantes."]
    if "comparison" in report:
        comp = report["comparison"]
        lines += ["", f"Comparaison des conditions : {'compatibles' if comp['comparable_conditions'] else 'différentes, deltas refusés'}.",
                  "", "| Mesure | Avant | Après | Delta |", "| --- | ---: | ---: | ---: |"]
        for key, value in comp["metrics"].items():
            lines.append(f"| {key} | {value['before']} | {value['after']} | {value['delta']} |")
    with (directory / "summary.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def _child(config_path, report_path):
    """One real Tk owner; sampling timers exist only in this explicit tool."""
    started = time.perf_counter()
    options = read_json(config_path, 131072)
    sys.path.insert(0, options["source"])
    import tkinter as tk
    from dataclasses import replace
    from jarvis.config import Settings
    from jarvis.storage import Store
    from jarvis.ui import App
    from jarvis.gpu_benchmark import NvidiaSampler, read_process_memory
    from jarvis.gpu_config import GpuSettings
    from jarvis.gpu_session import GpuSession

    import jarvis.ui as imported_ui
    if Path(imported_ui.__file__).resolve() != (Path(options["source"]) / "jarvis" / "ui.py").resolve():
        raise RuntimeError("Le code importé ne correspond pas au checkout demandé.")

    settings = Settings(**options["profile"]["settings"]).validate()
    if options["model"] is not None:
        settings = replace(settings, model=options["model"])
    if options["context"] is not None:
        settings = replace(settings, context=options["context"])
    settings.validate()
    scenario = options["scenario"]
    profile = scenario.removeprefix("gpu-") if scenario.startswith("gpu-") else "balanced"
    gpu_requested = scenario.startswith("gpu-") or scenario == "ollama-gpu"
    observations = deque(maxlen=7200)
    gpu_windows = deque(maxlen=120)
    pipeline = OrderedDict()
    callback_errors = []
    counts = Counter()
    report = {"benchmark_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "python": platform.python_version(),
              "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "status": "incomplete", "conditions": {
                  "scenario": scenario, "model": settings.model, "context": settings.context,
                  "max_tokens": settings.max_tokens, "reasoning_mode": settings.reasoning_mode,
                  "cognitive_mode": settings.cognitive_mode,
                  "requested_size": [options["width"], options["height"]],
                  "requested_tk_scaling": options["tk_scaling"], "visual_state": options["visual_state"],
                  "cache_state": options["cache_state"], "requested_gpu_profile": profile if gpu_requested else None,
                  "sample_seconds_requested": options["seconds"], "warmup_seconds": options["warmup"],
                  "input_preferences_sha256": hashlib.sha256(json.dumps(options["profile"], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                  "disposable_archive": True, "synthetic_visual_state": options["visual_state"] != "idle",
                  "synthetic_audio": False, "interactive": scenario in INTERACTIVE,
                  "software_gpu_explicitly_allowed": options["allow_software"]},
              "summary": {}, "metrics": {}, "observations": [],
              "unavailable": {"physical_vram_bytes": "No attributable physical VRAM counter read.",
                              "electrical_power_watts": "No power meter sampled.",
                              "acoustic_latency_ms": "No acoustic loopback measured.",
                              "inference_audio_child_cpu": "No per-process OS counters for inference/audio children read."},
              "limitations": ["Bounded opt-in run; not proof of absence of memory leaks.",
                              "Sampled metrics may miss transient events; numeric observations only.",
                              "An idle visualizer does not establish animation performance.",
                              "Closing the window early shortens the sample; no automatic restart."]}
    report["startup_scope"] = "Child imports, temporary Store and real Tk/App initialization; excludes OS process launch."
    source = Path(options["source"])
    report["source_sha256"] = {name: hashlib.sha256((source / "jarvis" / name).read_bytes()).hexdigest()
        for name in ("ui.py", "voice_ui.py", "voice_runtime.py", "gpu_session.py", "gpu_renderer.py", "storage.py")}
    root = app = store = None
    state = {}
    nvidia = None
    sample_id = finish_id = start_id = None
    temporary_store = tempfile.TemporaryDirectory(prefix="jarvis-runtime-benchmark-")
    try:
        folder = temporary_store.name
        try:
            store = Store(Path(folder) / "benchmark.sqlite3")
            store.save_settings(settings)
            for key, value in options["profile"]["preferences"].items():
                store.set_preference(key, value)
            store.set_preference("presence_engine", {"mode": "gpu" if gpu_requested else "canvas"})
            gpu = GpuSettings.from_dict(store.get_preference("presence_gpu", {}))
            store.set_preference("presence_gpu", replace(gpu, profile=profile).to_dict())
            root = tk.Tk()
            if options["tk_scaling"] is not None:
                root.tk.call("tk", "scaling", options["tk_scaling"])
            app = App(root, store, refresh=False)
            root.geometry(f"{options['width']}x{options['height']}")
            root.title("JARVIS — BENCHMARK LOCAL · " + scenario)
            if scenario == "idle":
                root.withdraw()
            class ObservedGpuSession(GpuSession):
                def poll(self):
                    nonlocal nvidia
                    events = super().poll()
                    for event in events:
                        if event.get("kind") == "ready":
                            report["renderer"] = event.get("renderer", {})
                            if nvidia is None:
                                nvidia = NvidiaSampler(report["renderer"].get("renderer", "")).start()
                    return events
            app.presence.session_factory = lambda: ObservedGpuSession(allow_software=options["allow_software"])
            if scenario == "canvas" or gpu_requested:
                app.presence.show()
                if options["visual_state"] == "thinking":
                    app.presence.update_event("thinking")
            voice = app.voice.settings
            report["conditions"].update(
                audio_input=voice.input_device or "system_default", audio_output=voice.output_device or "system_default",
                voice=voice.voice, speed=voice.speed, speech_profile=voice.speech_profile,
                acoustic_mode=voice.acoustic_mode, silence_ms=voice.silence_ms,
                vad_threshold=voice.vad_threshold, cpu_threads=voice.cpu_threads,
                tk_patchlevel=str(root.tk.call("info", "patchlevel")),
                actual_tk_scaling=float(root.tk.call("tk", "scaling")))
            original_poll = app.poll
            def poll():
                counts["app_poll_callbacks"] += 1
                original_poll()
            app.poll = poll
            def exception(kind, _error, _traceback):
                if len(callback_errors) < 32:
                    callback_errors.append(kind.__name__)
            root.report_callback_exception = exception
            def observe():
                nonlocal sample_id
                if app.closed:
                    return
                snap = app.cognitive.snapshot()
                metrics = numeric_metrics(snap.get("metrics", {}))
                if metrics:
                    pipeline.setdefault(snap["generation"], {}).update(metrics)
                    if len(pipeline) > 512:
                        pipeline.popitem(last=False)
                counts["observed_state_" + snap["primary"]] += 1
                counts["observed_microphone_" + app.voice.microphone_state] += 1
                memory = read_process_memory()
                capture = {key: value for key, value in app.voice.diagnostics.items()
                           if key in {"rms", "vad", "native_rate", "rate", "frame_samples", "turn_seconds"} and finite(value)}
                observations.append({"elapsed_seconds": time.perf_counter()-state["wall"],
                                     "process_cpu_seconds": time.process_time()-state["cpu"],
                                     "rss_bytes": memory.get("rss_current_bytes"),
                                     "active_engine": app.presence.active_engine,
                                     "microphone_state": app.voice.microphone_state,
                                     "capture": capture,
                                     "state": snap["primary"]})
                opened = app.voice.diagnostics.get("opened_device")
                if isinstance(opened, dict):
                    report["conditions"]["opened_microphone"] = {key: value[:128] if isinstance(value, str) else value
                        for key, value in opened.items() if key in {"name", "hostapi", "index"}
                        and (isinstance(value, str) or finite(value))}
                diagnostic = app.presence.gpu_diagnostics
                if diagnostic:
                    # This existing heartbeat is a metrics-only projection, not a frame/caption packet.
                    report["gpu_renderer"] = diagnostic
                    if not gpu_windows or diagnostic != gpu_windows[-1]:
                        gpu_windows.append(diagnostic)
                sample_id = root.after(500, observe)
            def finish():
                nonlocal sample_id
                if app.closed:
                    return
                if sample_id is not None:
                    root.after_cancel(sample_id)
                    sample_id = None
                now = time.perf_counter()
                elapsed = now-state.get("wall", now)
                cpu = time.process_time()-state.get("cpu", time.process_time())
                report["summary"].update(
                    sample_seconds=elapsed, process_cpu_percent_one_core=100*cpu/elapsed if elapsed else None,
                    process_cpu_ms=cpu*1000, rss_before_bytes=state.get("rss"),
                    rss_after_bytes=read_process_memory().get("rss_current_bytes"))
                report["conditions"].update(actual_size=[root.winfo_width(), root.winfo_height()],
                    actual_engine=app.presence.active_engine)
                diagnostic = app.presence.gpu_diagnostics
                resolution = diagnostic.get("resolution", {})
                report["conditions"].update(gpu_render_size=resolution.get("render_size", resolution.get("main_size")),
                    gpu_window_size=diagnostic.get("size"), gpu_dpi_scale=diagnostic.get("dpi_scale"))
                from dataclasses import asdict
                for key, value in (("effective_voice_sha256", asdict(app.voice.settings)),
                                   ("effective_canvas_sha256", asdict(app.presence.settings)),
                                   ("effective_gpu_sha256", asdict(app.presence.gpu_settings)),
                                   ("effective_settings_sha256", asdict(app.settings))):
                    report["conditions"][key] = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                closing = time.perf_counter()
                app.close()
                report["summary"]["shutdown_ms"] = (time.perf_counter()-closing)*1000
                if nvidia is not None:
                    report["gpu_device_global"] = nvidia.stop()
                report["status"] = "error" if callback_errors or not app.closed else "complete" if state else "incomplete"
                if not app.closed:
                    report["error_type"] = "ApplicationCloseNotCompleted"
                    root.quit()
            def start():
                nonlocal finish_id
                state.update(wall=time.perf_counter(), cpu=time.process_time(),
                             rss=read_process_memory().get("rss_current_bytes"))
                observe()
                finish_id = root.after(round(options["seconds"]*1000), finish)
                if scenario in INTERACTIVE:
                    app.set_status("BENCHMARK : échangez / interrompez / basculez maintenant ; aucune conversation ne sera exportée.")
                    if scenario in {"ollama", "ollama-gpu", "conversation", "interruptions-toggle"}:
                        app.refresh_models()
                    # The microphone is only enabled by the normal permission button.
                if scenario == "piper":
                    app.voice.preview()
            root.protocol("WM_DELETE_WINDOW", finish)
            root.update_idletasks()
            report["summary"]["startup_ms"] = (time.perf_counter()-started)*1000
            start_id = root.after(round(options["warmup"]*1000), start)
            root.mainloop()
            report["metrics"] = metric_summary(list(pipeline.values()))
            report["pipeline_turns_with_metrics"] = len(pipeline)
            report["pipeline_sample_capacity"] = 512
            report["observations"] = list(observations)
            report["sampled_gpu_heartbeat_windows"] = list(gpu_windows)
            report["gpu_window_sample_capacity"] = 120
            report["event_counts"] = dict(counts)
            report["callback_errors"] = callback_errors
            report["summary"]["process_sample_count"] = len(observations)
            actual_engines = [row["active_engine"] for row in observations]
            report["summary"]["observed_engine_changes"] = sum(left != right for left, right in zip(actual_engines, actual_engines[1:]))
            for key in ("actual_draw_fps", "animated_fps", "frame_p95_ms", "frame_p99_ms", "render_p95_ms", "render_p99_ms"):
                value = report.get("gpu_renderer", {}).get("timing", {}).get(key)
                if finite(value):
                    report["summary"]["gpu_last_heartbeat_" + key] = value
            checks = {"sample_received": bool(observations)}
            if gpu_requested:
                checks["requested_gpu_active"] = "gpu" in actual_engines
            if scenario in {"ollama", "ollama-gpu", "conversation"}:
                checks["ollama_generation_metrics_received"] = "eval_count" in report["metrics"]
            if scenario in {"capture", "conversation"}:
                checks["stt_metrics_received"] = "stt_ms" in report["metrics"]
            if scenario in {"piper", "conversation"}:
                checks["tts_first_pcm_received"] = "tts_first_pcm_ms" in report["metrics"]
            if scenario == "interruptions-toggle":
                checks["engine_change_observed"] = report["summary"]["observed_engine_changes"] > 0
                checks["interruption_observed"] = bool(counts["observed_state_interrupted"] or counts["observed_state_cancelled"])
            report["workload_checks"] = checks
            if report["status"] == "complete" and not all(checks.values()):
                report["status"] = "incomplete"
            if gpu_requested and not report.get("gpu_renderer"):
                report["unavailable"]["gpu_renderer"] = "No renderer heartbeat received; inspect fallback on screen."
            for key in ("stt_ms", "ttft_seconds", "tokens_per_second", "piper_ms", "tts_first_pcm_ms", "end_to_pcm_estimate_ms"):
                if key not in report["metrics"]:
                    report["unavailable"][key] = "No valid observation in this run; no value inferred."
        except Exception as error:
            report["status"] = "error"
            report["error_type"] = type(error).__name__
        finally:
            if nvidia is not None:
                report["gpu_device_global"] = nvidia.stop()
            if app is not None and not app.closed:
                try:
                    app.close()
                except Exception as error:
                    report["status"] = "error"
                    report["cleanup_error_type"] = type(error).__name__
            if store is not None:
                # This database belongs only to this bounded tool. Even a
                # declined/failed App.close must release its Windows file lock.
                try:
                    store.close()
                except Exception as error:
                    report["status"] = "error"
                    report["store_cleanup_error_type"] = type(error).__name__
            if root is not None:
                try:
                    root.destroy()
                except tk.TclError:
                    pass
    finally:
        try:
            temporary_store.cleanup()
        except OSError as error:
            report["status"] = "error"
            report["temporary_cleanup_error_type"] = type(error).__name__
    with Path(report_path).open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False)
    return 0 if report["status"] == "complete" else 2


def reap(process):
    """Kill only this benchmark's process group/tree after its bounded deadline."""
    if os.name == "nt":
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Nouveau dossier, jamais écrasé.")
    parser.add_argument("--seconds", type=float, default=10, help="1–3600 ; 60+ recommandé pour les essais interactifs.")
    parser.add_argument("--warmup", type=float, default=1)
    parser.add_argument("--preferences", type=Path, help="Profil JSON explicite ; aucune base personnelle ouverte.")
    parser.add_argument("--model", help="Nom exact d'un modèle déjà installé ; aucun téléchargement.")
    parser.add_argument("--context", type=int)
    parser.add_argument("--width", type=int, default=1100)
    parser.add_argument("--height", type=int, default=760)
    parser.add_argument("--tk-scaling", type=float, help="Échelle Tk, pas un DPI matériel simulé.")
    parser.add_argument("--visual-state", choices=("idle", "thinking"), default="idle", help="THINKING est un état synthétique explicitement identifié.")
    parser.add_argument("--cache-state", choices=("unspecified", "cold_observed", "warm_observed"), default="unspecified")
    parser.add_argument("--allow-software", action="store_true", help="Essai développeur Mesa ; aucune extrapolation RTX.")
    parser.add_argument("--source", type=Path, default=REPO, help="Checkout à mesurer avec le même outil (comparaison avant/après).")
    parser.add_argument("--baseline", type=Path, help="report.json antérieur pour comparaison contrôlée.")
    args = parser.parse_args(argv)
    if not finite(args.seconds) or not 1 <= args.seconds <= 3600 or not finite(args.warmup) or not .1 <= args.warmup <= 30:
        parser.error("Durée1–3600s, préchauffage0,1–30s attendus.")
    if not 560 <= args.width <= 7680 or not 400 <= args.height <= 4320:
        parser.error("Dimensions hors limites.")
    if args.tk_scaling is not None and (not finite(args.tk_scaling) or not .5 <= args.tk_scaling <= 5):
        parser.error("Échelle Tk0,5–5 attendue.")
    if args.model is not None and (not args.model.strip() or len(args.model) > 256):
        parser.error("Nom de modèle invalide.")
    if args.context is not None and not 512 <= args.context <= 131072:
        parser.error("Contexte512–131072 attendu.")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Choisissez un nouveau dossier dans un parent existant.")
    source = args.source.resolve()
    if not (source / "jarvis" / "ui.py").is_file():
        parser.error("Checkout JARVIS introuvable.")
    try:
        profile = load_profile(args.preferences)
        from dataclasses import replace
        from .config import Settings
        from .voice_config import VoiceSettings
        validated = Settings(**profile["settings"]).validate()
        validated = replace(validated, **({"model": args.model} if args.model is not None else {}),
                            **({"context": args.context} if args.context is not None else {})).validate()
        if "voice" in profile["preferences"]:
            VoiceSettings(**profile["preferences"]["voice"]).validate()
        before = read_json(args.baseline) if args.baseline else None
        if isinstance(before, dict) and before.get("benchmark_suite_version") == 1:
            before = before.get("scenarios", {}).get(args.scenario)
            if before is None:
                raise ValueError("Scénario absent de la référence.")
        if before is not None and (not isinstance(before, dict) or before.get("benchmark_version") != 1):
            raise ValueError("Rapport de référence inconnu.")
        options = vars(args).copy()
        options.update(source=str(source), profile=profile)
        for key in ("output", "preferences", "baseline"):
            options.pop(key)
        args.output.mkdir()
        with tempfile.TemporaryDirectory(prefix="jarvis-benchmark-supervisor-") as temporary:
            config = Path(temporary) / "config.json"
            raw = Path(temporary) / "report.json"
            config.write_text(json.dumps(options, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
            command = [sys.executable, str(Path(__file__).resolve()), "--_child", str(config), str(raw)]
            process = subprocess.Popen(command, cwd=source, env=environment, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=os.name != "nt",
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0)
            timed_out = False
            try:
                process.wait(timeout=args.seconds + args.warmup + 30)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                reap(process)
                timed_out = True
            report = read_json(raw) if raw.exists() else {
                "benchmark_version": 1, "status": "error", "conditions": {"scenario": args.scenario},
                "error_type": "DeadlineOrUserInterruption" if timed_out else "ChildExitedWithoutReport", "child_exitcode": process.returncode,
                "summary": {}, "metrics": {}}
            if process.returncode not in (0, 2) or process.returncode == 2 and report.get("status") == "complete":
                report["status"] = "error"
                report["child_exitcode"] = process.returncode
            write_exports(args.output, report, before)
        print(str(args.output / "summary.md"))
        return 0 if report["status"] == "complete" else 2
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) == 4 and sys.argv[1] == "--_child":
        raise SystemExit(_child(sys.argv[2], sys.argv[3]))
    raise SystemExit(main())
