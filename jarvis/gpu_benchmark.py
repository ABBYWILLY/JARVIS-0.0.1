"""Bounded, local instrumentation for the opt-in OpenGL prototype.

CPU submission time is not GPU execution time. NVIDIA telemetry describes the
whole matching device, never this process, Ollama, or individual GL allocations.
"""
import csv
import io
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


class FrameTimings:
    """Exact counts/totals; percentiles describe at most the latest 6000 frames."""

    def __init__(self, max_samples=6000):
        if isinstance(max_samples, bool) or not isinstance(max_samples, int) or not 1 <= max_samples <= 6000:
            raise ValueError("max_samples must be between 1 and 6000")
        self._samples = deque(maxlen=max_samples)
        self.frame_count = 0
        self.elapsed_seconds = 0.0

    def record(self, render_seconds, frame_seconds):
        """Record CPU render submission and wall frame INCLUDING swap/pacing wait."""
        _number(render_seconds, "render_seconds")
        _number(frame_seconds, "frame_seconds")
        if render_seconds > frame_seconds:
            raise ValueError("render_seconds cannot exceed inclusive frame_seconds")
        total = self.elapsed_seconds + frame_seconds
        render_ms, frame_ms = render_seconds * 1000, frame_seconds * 1000
        for value in (total, render_ms, frame_ms):
            _number(value, "frame duration or millisecond conversion")
        if total and not math.isfinite((self.frame_count + 1) / total):
            raise ValueError("frame duration would produce a nonfinite FPS")
        self.frame_count += 1
        self.elapsed_seconds = total
        self._samples.append((render_ms, frame_ms))

    def summary(self):
        def metrics(values):
            if not values:
                return None, None
            ordered = sorted(values)
            return statistics.median(ordered), ordered[math.ceil(len(ordered) * .95) - 1]

        render_median, render_p95 = metrics([row[0] for row in self._samples])
        frame_median, frame_p95 = metrics([row[1] for row in self._samples])
        return {"frame_count": self.frame_count, "elapsed_seconds": self.elapsed_seconds,
                "fps": self.frame_count / self.elapsed_seconds if self.elapsed_seconds else None,
                "sampled_frame_count": len(self._samples), "sample_policy": "most_recent_frames",
                "sample_capacity": self._samples.maxlen, "p95_method": "nearest_rank",
                "frame_median_ms": frame_median, "frame_p95_ms": frame_p95,
                "render_median_ms": render_median, "render_p95_ms": render_p95,
                "render_scope": "CPU_submission_not_GPU_execution",
                "frame_scope": "wall_frame_including_swap_and_pacing_wait"}


def _windows_memory():
    # HANDLE is pointer-sized on Win64. GetCurrentProcess returns a pseudo-handle:
    # do not CloseHandle it and do not allocate a new process handle every sample.
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
            "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"rss_current_bytes": counters.WorkingSetSize,
            "rss_peak_bytes": counters.PeakWorkingSetSize,
            "source": "GetProcessMemoryInfo_working_set", "unavailable_reason": None}


def read_process_memory():
    """Read actual resident bytes; an unavailable current RSS is never estimated."""
    try:
        if sys.platform == "win32":
            return _windows_memory()
        if sys.platform.startswith("linux"):
            fields = {}
            with open("/proc/self/status", encoding="ascii") as stream:
                for line in stream:
                    key, _, value = line.partition(":")
                    if key in ("VmRSS", "VmHWM"):
                        amount, unit = value.split()
                        if unit != "kB" or int(amount) < 0:
                            raise ValueError("unsupported /proc memory value")
                        fields[key] = int(amount) * 1024
            return {"rss_current_bytes": fields["VmRSS"], "rss_peak_bytes": fields["VmHWM"],
                    "source": "/proc/self/status", "unavailable_reason": None}
    except (OSError, ValueError, KeyError) as error:
        reason = f"Current resident memory unavailable ({type(error).__name__})."
    else:
        reason = "Current resident memory is unavailable on this platform."
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux and the BSD resource convention use KiB.
        peak = int(peak * (1 if sys.platform == "darwin" else 1024))
        if peak < 0:
            raise ValueError("negative peak RSS")
    except (ImportError, OSError, ValueError, OverflowError):
        peak = None
    return {"rss_current_bytes": None, "rss_peak_bytes": peak,
            "source": "resource.ru_maxrss" if peak is not None else None,
            "unavailable_reason": reason}


class ProcessSampler:
    """Process CPU percent of one core (can exceed 100), plus actual resident RAM."""

    def __init__(self, interval=.5):
        self.interval = _number(interval, "interval", positive=True)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._started = None
        self._end = None
        self._cpu_start = self._previous_cpu = self._previous_wall = None
        self._cpu_peak = None
        self._samples = 0
        self._rss_total = self._rss_samples = 0
        self._memory = {"rss_current_bytes": None, "rss_peak_bytes": None, "source": None,
                        "unavailable_reason": "Sampling has not started."}

    def start(self):
        if self._started is not None:
            raise RuntimeError("ProcessSampler can only be started once")
        self._started = self._previous_wall = time.monotonic()
        self._cpu_start = self._previous_cpu = time.process_time()
        self._memory = read_process_memory()
        if self._memory["rss_current_bytes"] is not None:
            self._rss_total, self._rss_samples = self._memory["rss_current_bytes"], 1
        self._thread = threading.Thread(target=self._run, name="jarvis-process-metrics", daemon=True)
        self._thread.start()
        return self

    def _sample(self):
        with self._lock:
            now, cpu = time.monotonic(), time.process_time()
            elapsed = now - self._previous_wall
            if elapsed > 0:
                percent = max(0., (cpu - self._previous_cpu) / elapsed * 100)
                self._cpu_peak = max(self._cpu_peak or 0., percent)
                self._samples += 1
            self._previous_wall, self._previous_cpu = now, cpu
            memory = read_process_memory()
            if memory["rss_current_bytes"] is not None:
                self._rss_total += memory["rss_current_bytes"]
                self._rss_samples += 1
            peaks = [value for value in (self._memory["rss_peak_bytes"], memory["rss_peak_bytes"],
                                        memory["rss_current_bytes"]) if value is not None]
            memory["rss_peak_bytes"] = max(peaks) if peaks else None
            self._memory = memory

    def _run(self):
        while not self._stop.wait(self.interval):
            self._sample()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.)
        if self._started is not None and self._end is None:
            self._sample()
            self._end = (self._previous_wall, self._previous_cpu)
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            now, cpu = self._end if self._end else (time.monotonic(), time.process_time())
            elapsed = now - self._started if self._started is not None else 0.
            average = max(0., (cpu - self._cpu_start) / elapsed * 100) if elapsed > 0 else None
            return {"cpu_scope": "process_one_core_percent", "cpu_average_percent": average,
                    "cpu_peak_percent": self._cpu_peak, "elapsed_seconds": elapsed,
                    "interval_seconds": self.interval, "sample_count": self._samples,
                    "peak_sampling": "periodic_intervals_and_final_partial_interval",
                    "rss_current_bytes": self._memory["rss_current_bytes"],
                    "rss_average_bytes": self._rss_total / self._rss_samples if self._rss_samples else None,
                    "rss_average_scope": "sample_mean_including_initial_and_final_reads",
                    "rss_sample_count": self._rss_samples,
                    "rss_peak_bytes": self._memory["rss_peak_bytes"],
                    "rss_peak_scope": "process_lifetime_high_water_mark",
                    "memory_source": self._memory["source"],
                    "unavailable_reason": self._memory["unavailable_reason"]}


def parse_nvidia_smi(output):
    """Parse index,name,memory.used,memory.total,utilization.gpu (nounits CSV)."""
    def metric(value, scale=1, upper=None):
        if value.strip().lower() in ("n/a", "[n/a]", "not supported", "[not supported]"):
            return None
        number = float(value)
        _number(number, "nvidia-smi metric")
        if upper is not None and number > upper:
            raise ValueError("nvidia-smi metric outside range")
        scaled = number * scale
        _number(scaled, "nvidia-smi converted metric")
        return int(scaled) if scale != 1 else scaled

    devices = []
    for row in csv.reader(io.StringIO(output)):
        if not row or not any(part.strip() for part in row):
            continue
        if len(row) != 5 or not row[1].strip():
            raise ValueError("Unexpected nvidia-smi CSV columns")
        index = int(row[0])
        if index < 0 or any(device["index"] == index for device in devices):
            raise ValueError("Invalid or duplicate GPU index")
        device = {"index": index, "name": row[1].strip(),
                  "memory_used_bytes": metric(row[2], 1024 * 1024),
                  "memory_total_bytes": metric(row[3], 1024 * 1024),
                  "utilization_percent": metric(row[4], upper=100)}
        used, total = device["memory_used_bytes"], device["memory_total_bytes"]
        if used is not None and total is not None and (total <= 0 or used > total):
            raise ValueError("Inconsistent NVIDIA device memory")
        devices.append(device)
    if not devices:
        raise ValueError("No NVIDIA device rows")
    return devices


def match_nvidia_device(renderer, devices):
    """Return one unambiguous model-name match; identical cards cannot be located."""
    def normalized(value):
        return " ".join(str(value).lower().replace("nvidia", "").split())

    renderer_name = normalized(renderer)
    if any(software in renderer_name for software in ("llvmpipe", "softpipe", "swrast", "swiftshader")):
        return None
    matches = [device for device in devices if normalized(device["name"])
               and normalized(device["name"]) in renderer_name]
    return matches[0] if len(matches) == 1 else None


class NvidiaSampler:
    """Optional nvidia-smi device telemetry, one bounded subprocess at a time."""

    def __init__(self, renderer, interval=1., timeout=1.):
        self.renderer = str(renderer)
        self.interval = _number(interval, "interval", positive=True)
        self.timeout = _number(timeout, "timeout", positive=True)
        if self.timeout > 1.:
            raise ValueError("nvidia-smi timeout must not exceed one second")
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._data = {"available": False, "scope": "device_global_not_process",
                      "device_index": None, "device_name": None, "memory_used_bytes": None,
                      "memory_total_bytes": None, "utilization_percent": None,
                      "peak_memory_used_bytes": None, "peak_utilization_percent": None,
                      "memory_pressure_fraction": None, "sample_count": 0,
                      "unavailable_reason": "NVIDIA sampling has not started.",
                      "attribution": "Global device usage; no process, Ollama or GL attribution."}

    def start(self):
        if self._thread is not None or self._stop.is_set():
            raise RuntimeError("NvidiaSampler can only be started once")
        self._thread = threading.Thread(target=self._run, name="jarvis-nvidia-metrics", daemon=True)
        self._thread.start()
        return self

    def _sample(self):
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                                     "--format=csv,noheader,nounits"], shell=False, capture_output=True,
                                    text=True, timeout=self.timeout, check=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            device = match_nvidia_device(self.renderer, parse_nvidia_smi(result.stdout))
            if device is None:
                raise ValueError("GL renderer does not uniquely match an NVIDIA device name")
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            reason = (str(error) if isinstance(error, ValueError) else
                      f"NVIDIA telemetry unavailable ({type(error).__name__}).")
            with self._lock:
                self._data["available"] = False
                self._data["unavailable_reason"] = reason
                for key in ("device_index", "device_name", "memory_used_bytes", "memory_total_bytes",
                            "utilization_percent", "memory_pressure_fraction"):
                    self._data[key] = None
            return
        with self._lock:
            used, total = device["memory_used_bytes"], device["memory_total_bytes"]
            self._data.update(available=True, device_index=device["index"], device_name=device["name"],
                              memory_used_bytes=used, memory_total_bytes=total,
                              utilization_percent=device["utilization_percent"],
                              memory_pressure_fraction=used / total if used is not None and total else None,
                              unavailable_reason=("Some device counters are unsupported." if any(
                                  device[key] is None for key in ("memory_used_bytes", "memory_total_bytes",
                                                               "utilization_percent")) else None))
            self._data["sample_count"] += 1
            for target, source in (("peak_memory_used_bytes", "memory_used_bytes"),
                                   ("peak_utilization_percent", "utilization_percent")):
                value = device[source]
                if value is not None:
                    self._data[target] = max(self._data[target] or 0, value)

    def _run(self):
        while not self._stop.is_set():
            self._sample()
            if self._stop.wait(self.interval):
                break

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.timeout + .25)
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            return dict(self._data)


def build_report(*, startup_seconds, frames, process, gpu, renderer_info,
                 allocation_estimate_bytes=None):
    """Build a JSON-compatible report without inventing model/audio/GPU timing."""
    _number(startup_seconds, "startup_seconds")
    if allocation_estimate_bytes is not None:
        _number(allocation_estimate_bytes, "allocation_estimate_bytes")
    report = {"benchmark_version": 1, "platform": platform.platform(),
              "python": platform.python_version(), "startup_seconds": startup_seconds,
              "renderer": renderer_info,
              "frames": frames.summary() if hasattr(frames, "summary") else frames,
              "process": process.snapshot() if hasattr(process, "snapshot") else process,
              "gpu_device": gpu.snapshot() if hasattr(gpu, "snapshot") else gpu,
              "shader_resources": {"allocation_estimate_bytes": allocation_estimate_bytes,
                                   "estimate_scope": "application_requested_resources_not_physical_VRAM",
                                   "physical_vram_measured_bytes": None,
                                   "unavailable_reason": "Per-process physical GL VRAM is not measured."},
              "unmeasured_workloads": {name: {"latency_seconds": None, "reason": "Not measured in this render benchmark."}
                                       for name in ("ollama", "piper", "whisper", "vad")},
              "unmeasured_gpu_metrics": {"gpu_execution_ms": None,
                    "process_graphics_utilization_percent": None,
                    "reason": "No GPU timer or per-process graphics-utilization counter is collected."}}
    # Validate before creating a report file, including nested caller metadata.
    json.dumps(report, ensure_ascii=False, allow_nan=False)
    return report


def write_report(path, data):
    """Create one durable UTF-8 JSON report, preserving every existing file."""
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
