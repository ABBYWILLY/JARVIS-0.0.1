"""Bounded measurements of actual renderer work, with no sampling thread.

Swap-buffer completion is observable; physical scanout is not. The caller
records a frame only after drawing it, never for a queue poll or repeated count.
Resident RAM uses the existing process-memory reader; VRAM stays unmeasured.
"""
from collections import deque
import math
import statistics
import time

from .gpu_benchmark import read_process_memory


def _finite(value, name, *, nonnegative=False):
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and (not nonnegative or value >= 0))
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be finite" + (" and nonnegative" if nonnegative else ""))
    return value


def _rate(amount, elapsed):
    if elapsed <= 0:
        return None
    result = amount / elapsed
    return result if math.isfinite(result) else None


def _stats(values, prefix):
    ordered = sorted(values)
    result = {prefix + "_mean_ms": statistics.mean(ordered) if ordered else None}
    for percentile in (50, 95, 99):
        result[f"{prefix}_p{percentile}_ms"] = (
            ordered[max(0, math.ceil(len(ordered)*percentile/100)-1)] if ordered else None)
    return result


class RenderTelemetry:
    """Exact counters plus at most 600 recent timing samples per window.

    Frame intervals only connect consecutive animated draws. A pause or static
    draw breaks that chain, so returning from hidden/idle does not invent a
    multi-second graphics stutter. ``actual_draw_fps`` includes such pauses;
    ``animated_fps`` describes the sampled animated intervals separately.
    """

    def __init__(self, target_fps=60, max_samples=600, *, clock=None, cpu_clock=None,
                 memory_reader=None):
        if type(max_samples) is not int or not 1 <= max_samples <= 600:
            raise ValueError("max_samples must be between 1 and 600")
        self._clock, self._cpu_clock = clock or time.monotonic, cpu_clock or time.process_time
        self._memory_reader = memory_reader or read_process_memory
        self._render = deque(maxlen=max_samples)
        self._intervals = deque(maxlen=max_samples)
        self._target_fps = 60
        self.target_fps = target_fps
        self._reset(_finite(self._clock(), "clock"), _finite(self._cpu_clock(), "cpu_clock"))

    @property
    def target_fps(self):
        return self._target_fps

    @target_fps.setter
    def target_fps(self, value):
        _finite(value, "target_fps")
        if not 1 <= value <= 240:
            raise ValueError("target_fps must be between 1 and 240")
        self._target_fps = float(value)

    def _reset(self, now, cpu):
        self._started, self._cpu_started = now, cpu
        self._render.clear()
        self._intervals.clear()
        self._frames = self._animated_frames = self._swaps = self._long = 0
        self._last_frame = None
        self._last_animated = False

    def pause(self):
        """Break the animated interval chain when no frame needs to be drawn."""
        self._last_animated = False

    def record(self, render_seconds, frame_at, *, presented=False, animated=False):
        """Record one completed draw, with its monotonic draw-start timestamp.

        ``render_seconds`` may include driver/swap waits if the caller measures
        them. The exported scope explicitly describes this as wall time, never
        a GPU timestamp query or proof of physical presentation.
        """
        _finite(render_seconds, "render_seconds", nonnegative=True)
        _finite(frame_at, "frame_at")
        render_ms = _finite(render_seconds*1000, "render milliseconds", nonnegative=True)
        if not isinstance(presented, bool) or not isinstance(animated, bool):
            raise ValueError("presented and animated must be boolean")
        if frame_at < self._started or self._last_frame is not None and frame_at < self._last_frame:
            raise ValueError("frame_at must not move backwards")
        interval = None
        if animated and self._last_animated and self._last_frame is not None:
            interval = _finite((frame_at-self._last_frame)*1000,
                               "frame milliseconds", nonnegative=True)
        self._frames += 1
        self._animated_frames += int(animated)
        self._swaps += int(presented)
        self._render.append(render_ms)
        if interval is not None:
            self._intervals.append(interval)
            self._long += int(interval > 1500/self.target_fps)
        self._last_frame, self._last_animated = frame_at, animated

    def snapshot(self, now=None, reset=False):
        """Read counters/RAM at the caller's low-rate heartbeat, without a thread."""
        now = _finite(self._clock() if now is None else now, "now")
        if now < self._started or self._last_frame is not None and now < self._last_frame:
            raise ValueError("snapshot time must not precede its frames")
        if not isinstance(reset, bool):
            raise ValueError("reset must be boolean")
        cpu = _finite(self._cpu_clock(), "cpu_clock")
        elapsed = now-self._started
        render = tuple(self._render)
        intervals = tuple(self._intervals)
        mean_interval = statistics.mean(intervals) if intervals else None
        try:
            memory = self._memory_reader()
        except (OSError, ValueError, RuntimeError) as error:
            memory = {"rss_current_bytes": None, "rss_peak_bytes": None, "source": None,
                      "unavailable_reason": f"Resident memory unavailable ({type(error).__name__})."}
        result = {"frames_drawn": self._frames, "animated_frames_drawn": self._animated_frames,
                  "swap_calls": self._swaps, "presentation_observation": "swap_buffers_returned_not_physical_scanout",
                  "actual_draw_fps": _rate(self._frames, elapsed),
                  "animated_fps": _rate(1000, mean_interval) if mean_interval is not None else None,
                  "elapsed_seconds": elapsed, "target_fps": self.target_fps,
                  "long_frames": self._long, "long_frame_threshold_ms": 1500/self.target_fps,
                  "sample_capacity": self._render.maxlen, "sampled_render_frames": len(render),
                  "sampled_frame_intervals": len(intervals), "percentile_method": "nearest_rank",
                  "render_scope": "draw_wall_time_including_recorded_driver_and_swap_wait_not_GPU_query",
                  "frame_scope": "consecutive_animated_draw_start_intervals_excluding_idle_and_hidden",
                  "cpu_percent": _rate(max(0., cpu-self._cpu_started)*100, elapsed),
                  "cpu_scope": "renderer_process_one_core_percent_may_exceed_100",
                  "rss_current_bytes": memory.get("rss_current_bytes"),
                  "rss_peak_bytes": memory.get("rss_peak_bytes"),
                  "memory_source": memory.get("source"),
                  "memory_unavailable_reason": memory.get("unavailable_reason"),
                  "physical_vram_bytes": None,
                  "physical_vram_unavailable_reason": "No attributable process VRAM counter was read."}
        result.update(_stats(render, "render"))
        result.update(_stats(intervals, "frame"))
        if reset:
            self._reset(now, cpu)
        return result
