"""Exercise the real spawned renderer in source and frozen Windows builds.

No microphone, audio model or network is opened. An explicitly unavailable
driver is reported as an unavailable GPU, never as a rendered frame.
"""
import re
import time
from pathlib import Path


def expected_driver_absence(event):
    if event.get("kind") != "error" or event.get("stage") != "context":
        return False
    message = event.get("message", "")
    if (event.get("renderer", {}).get("acceleration") == "software"
            and "Accélération GPU non confirmée" in message):
        return True
    return bool(re.search(
        r"WGL: (The driver does not appear to support OpenGL|"
        r"Driver does not support OpenGL version 3\.3|"
        r"OpenGL version 3\.3 requested but WGL_ARB_create_context is unavailable|"
        r"OpenGL profile requested but WGL_ARB_create_context_profile is unavailable)",
        message))


def run_smoke(directory, *, headless=False, allow_software=False, timeout=20.):
    """Write a fresh diagnostic report; return nonzero on unexpected failures."""
    from .gpu_benchmark import write_report
    from .gpu_session import GpuSession
    from .storage import Store
    directory = Path(directory)
    store = Store(directory / "jarvis.sqlite3")
    store.close()
    report = {"status": "failed", "shader_compile_and_frame": False,
              "shutdown": "pending", "hardware_validation": "pending",
              "microphone_and_models": "not_opened", "stage": "native_imports"}
    session = None
    result = 1
    started = time.monotonic()
    try:
        # Eager native imports prevent DLL or frozen hook failures being mistaken
        # for a runner with no usable display driver.
        import importlib
        import os
        for module in ("moderngl", "moderngl.mgl", "_moderngl", "glcontext", "glfw", "PIL.Image"):
            importlib.import_module(module)
        if os.name == "nt":
            importlib.import_module("glcontext.wgl")
        session = GpuSession(headless=headless, allow_software=allow_software,
                             startup_timeout=min(20., timeout))
        session.start()
        deadline = time.monotonic() + timeout
        report["stage"] = "spawn"
        terminal = False
        while time.monotonic() < deadline and not terminal:
            for event in session.poll():
                if event.get("kind") == "ready":
                    report["renderer"] = event["renderer"]
                    report["stage"] = "frame"
                    session.submit({"seq": 1, "visible": True,
                        "frame_at": time.monotonic(),
                        "frame": {"time_s": 0., "reactor": 1.,
                                  "points": ((-.8, 0.), (.8, 0.))},
                        "hud": {"state": "Test de compilation · aucun audio", "preview": True},
                        "window": {"width": 480, "height": 360}})
                elif event.get("kind") == "heartbeat" and event.get("frames", 0) > 0:
                    report.update(status="supported", shader_compile_and_frame=True)
                    result, terminal = 0, True
                    break
                elif event.get("kind") == "error":
                    report.update(stage=event.get("stage", "process"),
                                  error=event.get("message", "Unknown GPU error"),
                                  renderer=event.get("renderer", {}))
                    if expected_driver_absence(event):
                        report["status"] = "driver_unavailable"
                        result = 0
                    terminal = True
                    break
                elif event.get("kind") == "closed":
                    raise RuntimeError("Renderer closed before the frame check completed.")
            if not terminal:
                time.sleep(.02)
        if not terminal:
            raise TimeoutError("GPU smoke check exceeded its bounded deadline.")
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            if session is not None:
                session.stop(timeout=2.)
            report["shutdown"] = "complete"
        except Exception as error:
            result = 1
            report["shutdown"] = f"failed: {type(error).__name__}: {error}"
        report["elapsed_seconds"] = time.monotonic() - started
        write_report(directory / "gpu-smoke.json", report)
    return result
