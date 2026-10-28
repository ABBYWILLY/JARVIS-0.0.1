"""Bounded presentation clocks; no audio, conversation, GUI or GPU dependency."""
import math


MAX_ANIMATION_AGE = .35


def native_window_size(logical_size, window_size, framebuffer_size, content_scale):
    """Convert desired logical units using observed GLFW ratios, not OS guesses.

    GLFW screen coordinates are physical pixels on Windows, while macOS may
    expose logical points. Content scale / observed framebuffer ratio handles
    both without applying DPI twice.
    """
    return tuple(max(1, round(wanted*scale*screen/max(1, physical)))
                 for wanted, screen, physical, scale in zip(
                     logical_size, window_size, framebuffer_size, content_scale))


def advance_frame(packet, frame, now):
    """Evaluate a parent-owned visual anchor between bounded IPC updates.

    Only continuous artwork is extrapolated: time, the established orbital
    phases/velocities and core transition. PCM, captions and semantic selection
    are never fabricated. A stalled parent freezes this clock within 350 ms.
    """
    frame = dict(frame)
    animation = packet.get("animation", {})
    running = bool(animation.get("active", False) and not frame.get("reduced_motion", False))
    age = max(0., now-packet.get("frame_at", now))
    delta = min(age, MAX_ANIMATION_AGE)
    if running:
        frame["time_s"] += delta
        velocity = animation.get("orbit_velocity", (0., 0., 0.))
        target = animation.get("orbit_target", velocity)
        tau = animation.get("orbit_tau", .45)
        if "orbit_phase" in frame:
            frame["orbit_phase"] = tuple(phase + aim*delta + (speed-aim)*tau*(1.-math.exp(-delta/tau))
                                         for phase, speed, aim in zip(frame["orbit_phase"], velocity, target))
        if "core_scale" in frame:
            goal = animation.get("core_target", frame["core_scale"])
            frame["core_scale"] = goal + (frame["core_scale"]-goal)*math.exp(-delta/animation.get("core_tau", .3))
        # The parent has already selected/started this family. Evaluate only
        # its existing transition envelope until its authoritative deadline.
        if frame.get("surface_family") and "expression_until" in packet:
            art = packet.get("art", {})
            enter = max(.12, min(1., art.get("expression_transition_ms", 360)/1000))
            hold = max(.25, min(2.5, art.get("expression_hold_ms", 650)/1000))
            started = packet["expression_until"]-(enter*2+hold)
            elapsed = max(0., now-started)
            edge = max(0., min(elapsed, enter*2+hold-elapsed))
            smooth = lambda value: (lambda x: x*x*(3.-2.*x))(max(0., min(1., value)))
            frame["surface_amount"] = smooth(edge/enter)
            speed = max(.4, min(2., art.get("expression_ring_speed", 100)/100))
            frame["orbit_blend"] = smooth(edge/(enter/speed))
    return frame, running and age < MAX_ANIMATION_AGE


class RenderGovernor:
    """Slow, reversible cost adaptation; never changes nominal animation time."""
    def __init__(self, *, level=0):
        self.level = max(0, min(4, int(level)))
        self._poor_since = self._healthy_since = None
        self._changed_at = float("-inf")

    def observe(self, cost_seconds, now, target_fps):
        if not all(math.isfinite(value) for value in (cost_seconds, now, target_fps)) or cost_seconds < 0 or target_fps <= 0:
            raise ValueError("Mesure de frame invalide.")
        budget = 1./target_fps
        if cost_seconds > budget*1.15:
            self._healthy_since = None
            if self._poor_since is None:
                self._poor_since = now
            if self.level < 4 and now-self._poor_since >= 2. and now-self._changed_at >= 2.:
                self.level += 1
                self._changed_at, self._poor_since = now, None
        elif cost_seconds < budget*1.08:
            self._poor_since = None
            if self._healthy_since is None:
                self._healthy_since = now
            if self.level > 0 and now-self._healthy_since >= 8. and now-self._changed_at >= 2.:
                self.level -= 1
                self._changed_at, self._healthy_since = now, None
        else:
            self._poor_since = self._healthy_since = None
        return self.level

    def suspend(self):
        self._poor_since = self._healthy_since = None


def next_deadline(previous, now, interval):
    """Advance the absolute cadence, skipping missed slots without a catch-up burst."""
    candidate = previous+interval
    if candidate <= now:
        candidate += (math.floor((now-candidate)/interval)+1)*interval
    return candidate
