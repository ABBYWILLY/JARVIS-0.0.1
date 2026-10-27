"""Standalone renderer experiment, deliberately outside JARVIS's voice/UI loop.

One existing PresenceModel and MorphController supply the state and symbols.
Manual states are labelled offline previews. WAV input is recorded PCM, never
claimed to be a live microphone or Piper playback. No model/asset downloads.
"""
import argparse
from array import array
from collections import deque
from dataclasses import replace
import json
import math
from pathlib import Path
import struct
import sys
import time
import wave
import zlib

from .audio import signal_view
from .expressions import expression_family
from .morphing import MorphController, ENTER_SECONDS, HOLD_SECONDS, RETURN_SECONDS
from .presence import PresenceModel, PresenceSettings
from .richtext import parse_text


PREVIEWS = ("Heureux de te revoir 😊", "Je t'aime ❤️", "C'est drôle 😂")
STATE_KEYS = {"idle": "silent", "listening": "listening", "thinking": "thinking",
              "speaking": "jarvis_speaking"}


class GpuUnavailable(RuntimeError):
    def __init__(self, message, reason="context"):
        super().__init__(message)
        self.reason = reason


def context_info(ctx):
    vendor, name = ctx.info.get("GL_VENDOR", ""), ctx.info.get("GL_RENDERER", "")
    software = any(word in name.casefold() for word in
                   ("llvmpipe", "softpipe", "swrast", "swiftshader", "software", "basic render"))
    return {"vendor": vendor, "renderer": name, "version": ctx.info.get("GL_VERSION"),
            "acceleration": "software" if software else "hardware_reported" if any(
                word in vendor.casefold() for word in ("nvidia", "intel", "amd", "ati")) else "unknown",
            "hardware_validation": "pending", "required_version": "OpenGL 3.3"}


class ReactorScene:
    """Thin adapter; operational state stays in the existing PresenceModel."""
    def __init__(self, reduced_motion=False, *, idle_line=False):
        self.model = PresenceModel(PresenceSettings(reduced_motion=reduced_motion))
        self.semantic = MorphController()
        self.color = (.25, .88, 1.)
        self.reactor = 0. if idle_line else 1.
        self.idle_line = bool(idle_line)
        self.orbit_phase = [0., .85, -.62]
        self.orbit_velocity = [0., 0., 0.]
        self.core_scale = 1.
        self.audio_bands = [0., 0., 0.]
        self._raw_bands = (0., 0., 0.)
        self.last_frame = None
        self.epoch = 0
        self.time_origin = None
        self._rendered_signal_active = False

    def update_state(self, state, now=None, interrupt=False):
        now = time.monotonic() if now is None else now
        self.semantic.cancel()
        self.epoch += 1
        self.model.update_event(state, now=now)
        self.reactor = 0. if state == "dormant" or self.idle_line and state == "silent" else 1.
        self._raw_bands = (0., 0., 0.)
        if interrupt or state == "dormant":
            self.audio_bands[:] = (0., 0., 0.)
        if state == "dormant":
            self.orbit_velocity[:] = (0., 0., 0.)
            self.core_scale = 1.
        self.last_frame = now

    def update_audio(self, signal, now=None, *, generation=None):
        now = time.monotonic() if now is None else now
        if generation is not None and generation != self.epoch:
            return False  # A superseded response may not illuminate a new state.
        raw = signal.get("bands", (0., 0., 0.)) if isinstance(signal, dict) else (0., 0., 0.)
        if len(raw) != 3 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in raw):
            raise ValueError("Le spectre audio attend trois bandes finies.")
        self._raw_bands = tuple(max(0., min(1., float(value))) for value in raw)
        self.model.update_event(self.model.state, signal, now=now)
        if self.model.has_signal(now):
            self.semantic.cancel()  # Physical/recorded PCM has priority over preview.
        return True

    def set_idle_line(self, enabled):
        self.idle_line = bool(enabled)
        if self.model.state == "silent":
            self.reactor = 0. if self.idle_line else 1.

    def _advance(self, now):
        # Integrate velocity, not state age: changing a state never resets any
        # orbital angle. Cap a resumed hidden interval to avoid a phase jump.
        delta = min(.1, max(0., now - self.last_frame)) if self.last_frame is not None else 0.
        self.last_frame = now
        targets = {"thinking": (.92, -.73, 1.13), "listening": (.065, -.045, .080),
                   "user_speaking": (.065, -.045, .080), "jarvis_speaking": (.12, -.09, .15)}
        target_velocity = targets.get(self.model.state, (0., 0., 0.))
        scale_target = .92 if self.model.state == "thinking" else 1.
        reduced = self.model.settings.reduced_motion
        for index, target in enumerate(target_velocity):
            before = self.orbit_velocity[index]
            if reduced:
                self.orbit_velocity[index] = 0.
            else:
                decay = math.exp(-delta / .45)
                self.orbit_phase[index] += target * delta + (before - target) * .45 * (1. - decay)
                velocity = target + (before - target) * decay
                self.orbit_velocity[index] = 0. if abs(velocity) < .0001 else velocity
        self.core_scale = (scale_target if reduced else
                           scale_target + (self.core_scale - scale_target) * math.exp(-delta / .30))
        if abs(self.core_scale - scale_target) < .0001:
            self.core_scale = scale_target
        active = self.model.has_signal(now)
        for index, value in enumerate(self._raw_bands if active else (0., 0., 0.)):
            previous = self.audio_bands[index]
            tau = .055 if value > previous else .24
            current = value + (previous - value) * math.exp(-delta / tau)
            self.audio_bands[index] = 0. if abs(current) < .0001 else current

    def set_reduced_motion(self, enabled, now=None):
        if now is not None:
            self._advance(now)
        self.model.settings = replace(self.model.settings, reduced_motion=bool(enabled))
        self.semantic.cancel()

    def preview_expression(self, text, width, height, now=None):
        if self.model.state not in {"silent", "thinking"}:
            return False
        now = time.monotonic() if now is None else now
        events = parse_text(text).events
        families = [expression_family(event.value) for event in events if event.kind == "expression"]
        family = next((family for family in families if family is not None), None)
        if family is None:
            return False
        return self.semantic.trigger(family, now, reduced_motion=self.model.settings.reduced_motion,
                                     origin=self._normal_points(width, height, now), viewport=(width, height))

    def _normal_points(self, width, height, now):
        if self.model.state != "jarvis_speaking":
            return self.model.frame(width, height, now)
        # The GPU experiment unfolds SPEAKING into a line. Reuse the existing
        # PCM-arrival filter; do not construct a carrier or a second state model.
        active = self.model.has_signal(now)
        expressivity = self.model.settings.wave_expressivity / 100
        energy = ((1 - math.exp(-self.model.signal["rms"] * (10 + 35 * expressivity))) ** .8
                  if active else 0.)
        amount = min(220, height * .24) * (.18 + .82 * expressivity) * energy
        if self.model.settings.reduced_motion:
            amount *= .55
        points = [(width * (.08 + .84 * i / 96), height / 2 + self.model._wave_line[i] * amount)
                  for i in range(97)]
        low, high = min(y for x, y in points), max(y for x, y in points)
        return [(x, y + height / 2 - (low + high) / 2) for x, y in points]

    def snapshot(self, width, height, now=None):
        now = time.monotonic() if now is None else now
        width, height = max(1, width), max(1, height)
        if self.time_origin is None:
            self.time_origin = now
        self._advance(now)
        points = self._normal_points(width, height, now)
        morph = self.semantic.frame(points, width, height, now, profile="cinematic")
        self._rendered_signal_active = self.model.has_signal(now)
        details = morph.details if morph else ()
        reactor = self.reactor
        if morph:
            points = morph.contour
            # The sole MorphController supplies phase/timing; this envelope only
            # withdraws the reactor's decorative orbits while its symbol owns
            # the foreground. It does not schedule another morph or audio event.
            elapsed = now - self.semantic._started
            smooth = lambda value: (lambda x: x*x*(3-2*x))(max(0., min(1., value)))
            if self.model.settings.reduced_motion or morph.phase == "hold":
                reactor = 0.
            elif morph.phase == "enter":
                reactor *= 1 - smooth(elapsed / ENTER_SECONDS * 2)
            else:
                reactor *= smooth(((elapsed - ENTER_SECONDS - HOLD_SECONDS) / RETURN_SECONDS - .5) * 2)
        ndc = lambda path: tuple((2 * x / width - 1, 1 - 2 * y / height) for x, y in path)
        return {"time_s": now - self.time_origin, "reactor": reactor, "points": ndc(points),
                "details": tuple(ndc(path) for path in details), "color": self.color,
                "detail_opacity": morph.detail_opacity if morph else 1.,
                "rms": self.model.signal["rms"] if self.model.has_signal(now) else 0.,
                "orbit_phase": tuple(self.orbit_phase), "core_scale": self.core_scale,
                "audio_bands": tuple(self.audio_bands), "orbit_blend": 0.,
                "reduced_motion": self.model.settings.reduced_motion}

    def moving(self, now):
        # IDLE is a static sphere after its outgoing inertia settles. Listening
        # and speaking have slow real-state orbits; audio energy is never made up.
        target_velocity = self.model.state in {"thinking", "listening", "user_speaking", "jarvis_speaking"}
        orbital = not self.model.settings.reduced_motion and (target_velocity or any(self.orbit_velocity))
        target_scale = .92 if self.model.state == "thinking" else 1.
        return (self.semantic.active or orbital or self.model.has_signal(now)
                or self.model.has_signal(now) != self._rendered_signal_active
                or any(self.audio_bands) or self.core_scale != target_scale)


class WavInput:
    """Bounded PCM16 file reader, paced from the recording's real sample rate."""
    def __init__(self, path):
        self.reader = wave.open(str(path), "rb")
        if (self.reader.getsampwidth() != 2 or self.reader.getnchannels() not in {1, 2}
                or not 1 <= self.reader.getframerate() <= 192000):
            self.reader.close()
            raise ValueError("Choisissez un WAV PCM16 mono ou stéréo, fréquence ≤192kHz ; aucune conversion automatique.")
        self.started = None
        self.generation = 0
        self.ended = False
        self.paused = False
        from .audio_spectrum import SpectrumWorker
        try:
            self.spectrum = SpectrumWorker()
        except Exception:
            self.reader.close()
            raise

    def reset_spectrum(self):
        self.generation += 1
        self.spectrum.reset(self.generation)

    def suspend(self):
        self.paused = True
        self.reset_spectrum()

    def resume(self):
        self.paused = False
        self.reset_spectrum()

    def signal(self, now):
        if self.paused:
            return {"rms": 0., "wave": [0.] * 48, "bands": (0., 0., 0.),
                    "spectrum_error": self.spectrum.diagnostic}
        if self.started is None:
            self.started = now
        rate, channels = self.reader.getframerate(), self.reader.getnchannels()
        position = min(self.reader.getnframes(), int(max(0, now - self.started) * rate))
        self.reader.setpos(position)
        samples = array("h", self.reader.readframes(max(1, int(rate * .032))))
        if sys.byteorder != "little":
            samples.byteswap()
        mono = [sum(samples[i:i + channels]) / (32768 * channels) for i in range(0, len(samples), channels)]
        result = signal_view(mono)
        if mono:
            self.spectrum.submit(mono, rate, now, generation=self.generation)
            result["bands"] = self.spectrum.snapshot(now, generation=self.generation)
        else:
            if not self.ended:
                self.reset_spectrum()
                self.ended = True
            result["bands"] = (0., 0., 0.)
        result["spectrum_error"] = self.spectrum.diagnostic
        return result

    def close(self):
        try:
            self.spectrum.close()
        finally:
            self.reader.close()


def save_png(path, size, rgb):
    """Store an actual framebuffer, RGB bottom-up, without imaging dependencies."""
    width, height = size
    if len(rgb) != width * height * 3:
        raise ValueError("Taille du framebuffer RGB incorrecte.")
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data) & 0xffffffff)
    stride = width * 3
    pixels = b"".join(b"\0" + rgb[row * stride:(row + 1) * stride] for row in reversed(range(height)))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0))
            + chunk(b"tEXt", b"Description\0Offline prototype framebuffer; hardware is identified separately in the benchmark report.")
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
    with Path(path).open("xb") as output:
        output.write(data)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prototype PRESENCE GPU autonome, sans modèle ni micro ; COMMAND OS reste Canvas.")
    parser.add_argument("--quality", choices=("eco", "balanced", "cinematic"), default="balanced")
    parser.add_argument("--state", choices=tuple(STATE_KEYS), default="idle", help="État d'aperçu hors ligne, pas une activité réelle d'Ollama.")
    parser.add_argument("--seconds", type=float, default=0., help="Durée limitée ; 0 = fenêtre interactive.")
    parser.add_argument("--headless", action="store_true", help="Contexte EGL sans fenêtre, essais développeur.")
    parser.add_argument("--probe", action="store_true", help="Diagnostic OpenGL ; aucune inférence ni capture audio.")
    parser.add_argument("--require-hardware", action="store_true", help="Refuser un renderer logiciel ou inconnu.")
    parser.add_argument("--allow-software", action="store_true", help="Essai développeur : autoriser le rendu logiciel d'une fenêtre (peut saturer le CPU).")
    parser.add_argument("--reduced-motion", action="store_true")
    parser.add_argument("--idle-line", action="store_true", help="Conserver la ligne classique au repos ; V bascule ce choix dans cet aperçu.")
    parser.add_argument("--no-bloom", action="store_true")
    parser.add_argument("--no-particles", action="store_true")
    parser.add_argument("--no-adaptive", action="store_true", help="Mesurer un profil fixe sans dégradation automatique.")
    parser.add_argument("--report", type=Path, help="Nouveau rapport JSON, jamais écrasé.")
    parser.add_argument("--capture", type=Path, help="Nouvelle capture PNG du framebuffer réel.")
    parser.add_argument("--wav", type=Path, help="WAV PCM16 local pour onde enregistrée (pas micro/Piper en direct).")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    args = parser.parse_args(argv)
    if (not math.isfinite(args.seconds) or not 0 <= args.seconds <= 3600
            or not 240 <= args.width <= 7680 or not 180 <= args.height <= 4320):
        parser.error("Durée0–3600secondes, largeur240–7680 et hauteur180–4320 attendues.")
    if args.headless and not args.probe and args.seconds <= 0:
        parser.error("--headless demande --seconds ou --probe.")
    for output in (args.report, args.capture):
        if output and (output.exists() or not output.parent.is_dir()):
            parser.error(f"Choisissez un nouveau fichier dans un dossier existant : {output}")
    if args.report and args.capture and args.report.resolve() == args.capture.resolve():
        parser.error("Capture et rapport doivent avoir des noms distincts.")
    return args


def _open_context(args):
    try:
        import moderngl
        if args.headless:
            try:
                return moderngl.create_standalone_context(require=330, backend="egl"), None, None
            except Exception as exc:
                raise GpuUnavailable("Contexte EGL OpenGL3.3 indisponible : " + str(exc)) from exc
        import glfw
    except ImportError as exc:
        raise GpuUnavailable("Composants GPU absents. JARVIS Canvas reste utilisable ; installer requirements-gpu.txt uniquement pour ce prototype.", "dependencies") from exc
    errors = deque(maxlen=8)
    glfw.set_error_callback(lambda code, description: errors.append(description.decode(errors="replace")))
    if not glfw.init():
        glfw.terminate()
        raise GpuUnavailable("OpenGL indisponible : " + "; ".join(errors))
    try:
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.VISIBLE, not args.probe)
        window = glfw.create_window(args.width, args.height, "PRESENCE GPU · PROTOTYPE HORS LIGNE", None, None)
        if not window:
            raise GpuUnavailable("OpenGL3.3 indisponible. Mettre à jour le pilote NVIDIA ; JARVIS Canvas reste utilisable. " + "; ".join(errors))
        glfw.make_context_current(window)
        glfw.swap_interval(0)  # Explicit pacing and timings, independent of monitor refresh.
        try:
            ctx = moderngl.create_context(require=330)
        except Exception as exc:
            glfw.destroy_window(window)
            raise GpuUnavailable("Contexte OpenGL3.3 indisponible : " + str(exc)) from exc
        return ctx, glfw, window
    except Exception:
        glfw.terminate()
        raise


def _run(args):
    from .gpu_benchmark import FrameTimings, ProcessSampler, NvidiaSampler, build_report, write_report
    started = time.perf_counter()
    scene = ReactorScene(args.reduced_motion, idle_line=args.idle_line)
    ctx = glfw = window = renderer = output = wav = process = gpu = None
    report = {"status": "error", "application_integrated": False, "offline_preview": True,
              "startup_scope": "Python_initialization_excludes_frozen_bootloader"}
    try:
        ctx, glfw, window = _open_context(args)
        info = context_info(ctx)
        report.update(renderer=info)
        require_hardware = args.require_hardware or not (args.headless or args.probe or args.allow_software)
        if require_hardware and info["acceleration"] != "hardware_reported":
            raise GpuUnavailable("Accélération matérielle non confirmée : " + info["renderer"], "hardware")
        from .gpu_renderer import GpuRenderer
        size = glfw.get_framebuffer_size(window) if window else (args.width, args.height)
        renderer = GpuRenderer(ctx, *size, quality=args.quality, bloom=not args.no_bloom, particles=not args.no_particles)
        if args.headless:
            output = ctx.simple_framebuffer(size, components=3)
        scene.update_state(STATE_KEYS[args.state])
        wav = WavInput(args.wav) if args.wav else None
        report.update(input_source="recorded_wav" if wav else "none", synthetic_pcm=False,
                      quality_requested=args.quality, renderer_resources_estimated_bytes=renderer.allocation_bytes)
        if args.probe:
            renderer.render(**scene.snapshot(*size), target=output)
            ctx.finish()
            if ctx.error != "GL_NO_ERROR":
                raise RuntimeError("Une erreur OpenGL est survenue pendant la sonde de rendu.")
            if args.capture:
                save_png(args.capture, renderer.size, renderer.read_rgb())
            report.update(status="supported", startup_seconds=time.perf_counter() - started,
                          shader_compile_and_frame=True, shutdown="pending")
            return report, 0
        frames, process, gpu = FrameTimings(), ProcessSampler(), NvidiaSampler(info["renderer"])
        process.start()
        gpu.start()
        startup = time.perf_counter() - started
        animation_start = time.monotonic()
        degraded, dirty, last_pcm, last_title = False, True, float("-inf"), float("-inf")
        slow_frames = quality_changes = 0
        def key(_window, key_code, _scan, action, _mods):
            nonlocal dirty, degraded, slow_frames, quality_changes
            if action != glfw.PRESS:
                return
            mapping = {glfw.KEY_I: "silent", glfw.KEY_L: "listening", glfw.KEY_T: "thinking", glfw.KEY_S: "jarvis_speaking"}
            if key_code == glfw.KEY_ESCAPE:
                glfw.set_window_should_close(window, True)
            elif key_code in mapping:
                scene.update_state(mapping[key_code], interrupt=key_code == glfw.KEY_L)
                if wav:
                    (wav.resume if mapping[key_code] in {"listening", "jarvis_speaking"} else wav.suspend)()
            elif glfw.KEY_1 <= key_code <= glfw.KEY_3:
                if scene.model.state != "thinking":
                    scene.update_state("silent", interrupt=True)
                scene.preview_expression(PREVIEWS[key_code - glfw.KEY_1], *size)
            elif key_code == glfw.KEY_R:
                scene.set_reduced_motion(not scene.model.settings.reduced_motion, now=time.monotonic())
            elif key_code == glfw.KEY_V:
                scene.set_idle_line(not scene.idle_line)
            elif key_code == glfw.KEY_X:
                scene.update_state("listening", interrupt=True)
                if wav:
                    wav.suspend()
            elif key_code == glfw.KEY_Q:
                qualities = ("eco", "balanced", "cinematic")
                renderer.set_quality(qualities[(qualities.index(renderer.quality) + 1) % len(qualities)])
                renderer.resize(*size)
                renderer.bloom, renderer.particles = not args.no_bloom, not args.no_particles
                degraded, slow_frames = False, 0
                quality_changes += 1
            elif key_code == glfw.KEY_C:
                colors = ((.25, .88, 1.), (.70, .4, 1.), (1., .6, .22), (.3, 1., .7))
                scene.color = colors[(colors.index(scene.color) + 1) % len(colors)]
            dirty = True
        if window:
            def invalidate(*_args):
                nonlocal dirty
                dirty = True
            glfw.set_key_callback(window, key)
            glfw.set_framebuffer_size_callback(window, invalidate)
            glfw.set_window_refresh_callback(window, invalidate)
            glfw.set_window_iconify_callback(window, invalidate)
        while not window or not glfw.window_should_close(window):
            frame_start = time.perf_counter()
            now = time.monotonic()
            if args.seconds and now - animation_start >= args.seconds:
                break
            if window:
                glfw.poll_events()
                visible = not glfw.get_window_attrib(window, glfw.ICONIFIED) and glfw.get_window_attrib(window, glfw.VISIBLE)
                current_size = glfw.get_framebuffer_size(window)
                if not visible or min(current_size) <= 0:
                    glfw.wait_events_timeout(.15)
                    continue  # No rendering while hidden/minimized.
                if current_size != size:
                    size = current_size
                    renderer.resize(*(tuple(max(1, value // 2) for value in size) if degraded else size))
                    ctx.screen.viewport = (0, 0, *size)
                    dirty = True
            if wav and not wav.paused and now - last_pcm >= .032 and scene.model.state in {"listening", "jarvis_speaking"}:
                scene.update_audio(wav.signal(now), now)
                last_pcm, dirty = now, True
            moving = scene.moving(now)
            if not dirty and not moving:
                if window:
                    glfw.wait_events_timeout(.1)
                else:
                    time.sleep(.1)
                continue  # IDLE is a single frame; no ornamental idle motion.
            render_started = time.perf_counter()
            renderer.render(**scene.snapshot(*size, now), target=output)
            if window:
                glfw.swap_buffers(window)
            else:
                ctx.finish()  # Headless measurements wait for actual driver completion.
            render_seconds = time.perf_counter() - render_started
            dirty = False
            if not args.no_adaptive and not degraded:
                pressure = gpu.snapshot().get("memory_pressure_fraction")
                slow_frames = slow_frames + 1 if render_seconds > .050 else 0
                if slow_frames >= 12 or pressure is not None and pressure > .94:
                    renderer.set_quality("balanced")
                    renderer.resize(*(max(1, value // 2) for value in size))
                    renderer.bloom = False
                    renderer.particles = False
                    degraded = True
                    report["adaptive_reason"] = "device_global_memory_pressure" if pressure and pressure > .94 else "frame_over_50ms"
            fps = 15 if degraded or renderer.quality == "eco" else 30 if renderer.quality == "balanced" else 60
            remaining = 1 / fps - (time.perf_counter() - frame_start)
            if remaining > 0:
                time.sleep(remaining)
            frames.record(render_seconds, time.perf_counter() - frame_start)
            if window and now - last_title >= 1:
                source = ("WAV suspendu" if wav.paused else "WAV enregistré") if wav else "sans audio"
                spectral = f" · spectre : {wav.spectrum.diagnostic}" if wav and wav.spectrum.diagnostic else ""
                glfw.set_window_title(window, f"PRESENCE · APERÇU HORS LIGNE · {scene.model.state} · {source}{spectral} · {info['acceleration']} · {renderer.quality} | I L T S · X interruption · 1 2 3 emoji · Q qualité · R mouvement · V repos · C couleur · Échap")
                last_title = now
        if args.capture:
            save_png(args.capture, renderer.size, renderer.read_rgb())
        process.stop()
        gpu.stop()
        frame_summary = frames.summary()
        duration = time.monotonic() - animation_start
        frame_summary.update(rendered_frame_wall_seconds=frame_summary["elapsed_seconds"],
                             elapsed_seconds=duration, fps=frame_summary["frame_count"] / duration if duration else None,
                             frame_scope="rendered_frame_intervals; idle_and_hidden_gaps_in_elapsed_and_fps")
        if args.headless:
            frame_summary["render_scope"] = "CPU_wall_including_driver_completion; not_GPU_timer"
        report.update(build_report(startup_seconds=startup, frames=frame_summary, process=process,
            gpu=gpu, renderer_info=info, allocation_estimate_bytes=renderer.allocation_bytes))
        report.update(status="complete", quality_effective=renderer.quality, adaptive_degraded=degraded,
                      quality_changes=quality_changes, output_size=size, internal_size=renderer.size,
                      audio_spectrum={"source": "recorded_pcm" if wav else "none", "bands": tuple(scene.audio_bands),
                                      "diagnostic": wav.spectrum.diagnostic if wav else "", "live_piper": False},
                      timings_scope="headless_render_complete_includes_driver_wait" if args.headless else "render_includes_swap; frame_includes_pacing",
                      shutdown="pending")
        return report, 0
    except Exception as exc:
        report.update(status="unsupported" if isinstance(exc, GpuUnavailable) and exc.reason != "dependencies" else "error",
                      unavailable_reason=exc.reason if isinstance(exc, GpuUnavailable) else None,
                      error=f"{type(exc).__name__}: {exc}", canvas_available="Jarvis.exe unchanged")
        return report, 2
    finally:
        cleanup_errors = []
        for sampler in (gpu, process):
            if sampler is not None:
                try:
                    sampler.stop()
                except Exception as exc:
                    cleanup_errors.append(f"{type(exc).__name__}: {exc}")
        for item in (wav, renderer, output, ctx):
            if item is not None:
                try:
                    getattr(item, "shutdown", getattr(item, "close", getattr(item, "release", lambda: None)))()
                except Exception as exc:
                    cleanup_errors.append(f"{type(exc).__name__}: {exc}")
                cleanup_errors.extend(getattr(item, "release_errors", ()))
        if glfw is not None:
            if window:
                try:
                    glfw.destroy_window(window)
                except Exception as exc:
                    cleanup_errors.append(f"{type(exc).__name__}: {exc}")
            try:
                glfw.terminate()
            except Exception as exc:
                cleanup_errors.append(f"{type(exc).__name__}: {exc}")
        report["shutdown"] = "error" if cleanup_errors else "complete"
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
            report["status"] = "error"
            report.setdefault("error", "La libération des ressources graphiques a échoué ; voir cleanup_errors.")
        if args.report:
            write_report(args.report, report)


def run(args):
    report, code = _run(args)
    return report, 2 if report.get("shutdown") == "error" else code


def main(argv=None):
    args = parse_args(argv)
    try:
        report, code = run(args)
    except (OSError, ValueError) as exc:
        report, code = {"status": "error", "error": str(exc)}, 2
    if report.get("shutdown") == "error":
        code = 2
    if sys.stdout is not None:
        print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
    if code and sys.platform == "win32" and not args.probe and not args.headless:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, report.get("error", "OpenGL indisponible"), "PRESENCE GPU — Canvas reste disponible", 0x10)
    return code
