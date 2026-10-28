"""Optional ModernGL reactor, independent of Tk, audio and model inference.

The caller owns the current OpenGL 3.3 context and presentation framebuffer.
No GPU dependency is imported until construction. Geometry supplied by the
single MorphController remains the only foreground at reactor=0.
"""
from array import array
import math

from . import reactor_shaders as shaders
from .gpu_config import GpuSettings


_LIMITS = {"eco": (960, 540), "balanced": (1280, 720), "cinematic": (1920, 1080)}
_PARTICLES = {"eco": 24, "balanced": 96, "cinematic": 192}
_SURFACE_FAMILIES = frozenset(("smile", "laughter", "affection", "sadness",
                               "anger", "surprise", "thinking", "wink"))
_MAX_MAIN = 97
_MAX_DETAILS = 8
_MAX_DETAIL_POINTS = 25
_MAX_SEGMENTS = _MAX_MAIN - 1 + _MAX_DETAILS * (_MAX_DETAIL_POINTS - 1)


class GpuRenderer:
    """A bounded HDR scene, quarter-size bloom and an internal RGB capture.

    ``size`` is the aspect-preserving internal resolution, capped at 1280×720
    (balanced) or 1920×1080 (cinematic). Presentation scales to the target.
    ``allocation_bytes`` estimates owned texture attachments and vertex buffer
    payloads. It is *not* physical VRAM usage and excludes driver/program costs.
    All methods must run on the thread with the caller's context current.
    """

    def __init__(self, ctx, width, height, quality="balanced", bloom=True, particles=True):
        import moderngl  # The regular Canvas application does not need this package.

        self.ctx = ctx
        self._gl = moderngl
        self._objects = []
        self._attachments = []
        self._release_errors = []
        self._targets = {}
        self._closed = False
        self._alignment_signs = None
        self._quality = self._validate_quality(quality)
        self.settings = GpuSettings.from_dict({"profile": quality})
        self._requested_size = self._validate_size(width, height)
        self._size = (0, 0)
        self._bloom_size = (0, 0)
        self.bloom = bool(bloom)
        self.particles = bool(particles)
        self._geometry = array("f", [0.0]) * (_MAX_SEGMENTS * 7)
        try:
            if ctx.version_code < 330:
                raise ValueError("The GPU reactor requires OpenGL 3.3 or newer.")
            self._scene = self._program(shaders.REACTOR_VERTEX, shaders.REACTOR_FRAGMENT)
            self._curve = self._program(shaders.CURVE_VERTEX, shaders.CURVE_FRAGMENT)
            self._filament = self._program(shaders.FILAMENT_VERTEX, shaders.CURVE_FRAGMENT)
            self._particle = self._program(shaders.PARTICLE_VERTEX, shaders.PARTICLE_FRAGMENT)
            self._extract = self._program(shaders.FULLSCREEN_VERTEX, shaders.EXTRACT_FRAGMENT)
            self._blur = self._program(shaders.FULLSCREEN_VERTEX, shaders.BLUR_FRAGMENT)
            self._resolve = self._program(shaders.FULLSCREEN_VERTEX, shaders.RESOLVE_FRAGMENT)
            self._copy = self._program(shaders.FULLSCREEN_VERTEX, shaders.COPY_FRAGMENT)
            self._vertex_buffer = ctx.buffer(reserve=len(self._geometry) * 4, dynamic=True)
            self._objects.append(self._vertex_buffer)
            self._scene_vao = self._vao(self._scene)
            self._curve_vao = self._vao(self._curve, [(self._vertex_buffer,
                                                    "2f 2f 2f 1f /i",
                                                    "a_start", "a_end", "a_range", "a_main")])
            self._filament_vao = self._vao(self._filament)
            self._particle_vao = self._vao(self._particle)
            self._extract_vao = self._vao(self._extract)
            self._blur_vao = self._vao(self._blur)
            self._resolve_vao = self._vao(self._resolve)
            self._copy_vao = self._vao(self._copy)
            for program in (self._extract, self._blur, self._resolve, self._copy):
                program["u_image"].value = 0
            self._resolve["u_bloom"].value = 1
            self._replace_attachments(self._bounded_size(self._requested_size, self._quality))
            self._upload_art()
        except Exception as error:
            self.shutdown()
            if self._release_errors:
                error.add_note("GPU cleanup failures: " + "; ".join(self._release_errors))
            raise

    @staticmethod
    def _validate_quality(quality):
        if quality not in _LIMITS:
            raise ValueError("quality must be 'eco', 'balanced' or 'cinematic'")
        return quality

    @staticmethod
    def _validate_size(width, height):
        if (isinstance(width, bool) or isinstance(height, bool)
                or not isinstance(width, int) or not isinstance(height, int)
                or width < 1 or height < 1):
            raise ValueError("Framebuffer dimensions must be positive integers.")
        return width, height

    @staticmethod
    def _bounded_size(requested, quality):
        width, height = requested
        max_width, max_height = _LIMITS[quality]
        scale = min(1.0, max_width / width, max_height / height)
        return max(1, round(width * scale)), max(1, round(height * scale))

    def _check_open(self):
        if self._closed:
            raise RuntimeError("GpuRenderer has been shut down.")

    def _program(self, vertex, fragment):
        program = self.ctx.program(vertex_shader=vertex, fragment_shader=fragment)
        self._objects.append(program)
        return program

    def _vao(self, program, content=()):
        vao = self.ctx.vertex_array(program, content)
        self._objects.append(vao)
        return vao

    def _release(self, resources):
        for resource in reversed(resources):
            try:
                resource.release()
            except Exception as error:
                # Complete every release even after context loss. Failures stay
                # explicit without replacing an original initialization error.
                if len(self._release_errors) == 16:
                    self._release_errors.pop(0)
                self._release_errors.append(
                    f"{type(resource).__name__}: {type(error).__name__}: {error}")

    def _replace_attachments(self, size):
        """Build first, then swap: allocation failure preserves the last frame."""
        if size == self._size:
            return
        bloom_size = tuple(max(1, (value + 3) // 4) for value in size)
        resources, targets = [], {}
        try:
            for name, dimensions, components, dtype in (
                    ("scene", size, 4, "f2"), ("resolved", size, 3, "f1"),
                    ("bloom_a", bloom_size, 4, "f2"),
                    ("bloom_b", bloom_size, 4, "f2")):
                texture = self.ctx.texture(dimensions, components, dtype=dtype)
                resources.append(texture)
                texture.filter = (self._gl.LINEAR, self._gl.LINEAR)
                texture.repeat_x = texture.repeat_y = False
                framebuffer = self.ctx.framebuffer(color_attachments=[texture])
                resources.append(framebuffer)
                targets[name] = (texture, framebuffer)
            # A disabled bloom path samples a cleared texture at weight zero.
            targets["bloom_a"][1].clear()
            targets["bloom_b"][1].clear()
        except Exception:
            self._release(resources)
            raise
        previous = self._attachments
        self._targets, self._attachments = targets, resources
        self._size, self._bloom_size = size, bloom_size
        self._release(previous)

    @property
    def size(self):
        return self._size

    @property
    def quality(self):
        return self._quality

    @property
    def attachment_bytes(self):
        """Estimated attachment storage, separate from physical GPU telemetry."""
        if self._closed:
            return 0
        width, height = self._size
        bloom_width, bloom_height = self._bloom_size
        return width * height * 11 + bloom_width * bloom_height * 16

    @property
    def allocation_bytes(self):
        return self.attachment_bytes + (0 if self._closed else len(self._geometry) * 4)

    @property
    def release_errors(self):
        """Last 16 cleanup errors, including context-loss errors, if any."""
        return tuple(self._release_errors)

    def resize(self, width, height):
        self._check_open()
        requested = self._validate_size(width, height)
        self._replace_attachments(self._bounded_size(requested, self._quality))
        self._requested_size = requested

    def set_quality(self, quality):
        self._check_open()
        quality = self._validate_quality(quality)
        self._replace_attachments(self._bounded_size(self._requested_size, quality))
        self._quality = quality

    def _upload_art(self):
        packed = self.settings.uniforms()
        for program in (self._scene, self._curve, self._filament, self._particle, self._extract):
            if "u_art" in program:
                count = program["u_art"].array_length * 4
                program["u_art"].write(array("f", packed[:count]).tobytes())
                program["u_art_enabled"].value = True

    def set_settings(self, settings):
        """Apply artistic settings without writing preferences or allocating geometry."""
        self._check_open()
        if isinstance(settings, GpuSettings):
            candidate = GpuSettings.from_dict(settings.to_dict())
        elif isinstance(settings, dict):
            candidate = GpuSettings.from_dict({**self.settings.to_dict(), **settings})
        else:
            raise ValueError("GPU artwork settings must be a dictionary or GpuSettings.")
        if candidate == self.settings:
            return False
        if candidate.profile != self.settings.profile:
            self.set_quality(candidate.profile)
        self.settings = candidate
        self._alignment_signs = None
        self._upload_art()
        return True

    @staticmethod
    def _path(path, maximum):
        # Geometry is small and bounded. Particles are generated entirely on GPU.
        path = tuple(path)
        if not 2 <= len(path) <= maximum:
            raise ValueError("A curve has an invalid number of points.")
        for point in path:
            if len(point) != 2 or not all(math.isfinite(value) for value in point):
                raise ValueError("Curve points must contain two finite coordinates.")
        return path

    def _upload_geometry(self, points, details):
        points = self._path(points, _MAX_MAIN)
        details = tuple(details)
        if len(details) > _MAX_DETAILS:
            raise ValueError("At most eight detail contours are supported.")
        paths = (points,) + tuple(self._path(path, _MAX_DETAIL_POINTS) for path in details)
        index = 0
        for path_index, path in enumerate(paths):
            count = len(path) - 1
            for i in range(count):
                start, end = path[i], path[i + 1]
                for value in (start[0], start[1], end[0], end[1],
                              i / count, (i + 1) / count, float(path_index == 0)):
                    self._geometry[index] = value
                    index += 1
        self._vertex_buffer.write(memoryview(self._geometry)[:index])
        return index // 7

    @staticmethod
    def _uniforms(program, values):
        for name, value in values.items():
            if name in program:
                program[name].value = value

    def _pass(self, name, vao):
        self._targets[name][1].use()
        vao.render(mode=self._gl.TRIANGLES, vertices=3)

    def _orbital_target_signs(self, phases):
        """Choose equivalent frontal quaternions once at expression entry.

        Formula matches R_axis(phase) * R_z(yaw) * R_x(tilt). Keeping the
        selected signs until alignment returns to zero prevents a per-frame
        shortest-path flip at 180 degrees. Only three scalars are cached.
        """
        signs = []
        for ring, (phase, axis) in enumerate(zip(phases, ((.72, .24, .61), (-.18, .88, .44), (.48, -.61, .63)))):
            yaw = (-.34+ring*.13+math.radians(self.settings.ring_orientation))*.5
            offset = math.radians((self.settings.ring_1_tilt, self.settings.ring_2_tilt, self.settings.ring_3_tilt)[ring])
            tilt = max(.10,min(1.47,math.acos(.30+ring*.11)+offset))*.5
            vector = (math.cos(yaw)*math.sin(tilt), math.sin(yaw)*math.sin(tilt),
                      math.sin(yaw)*math.cos(tilt))
            base_w = math.cos(yaw)*math.cos(tilt)
            length = math.sqrt(sum(value*value for value in axis))
            scalar = math.cos(phase*.5)*base_w - math.sin(phase*.5)*sum(a*b/length for a, b in zip(axis, vector))
            signs.append(1. if scalar >= 0. else -1.)
        return tuple(signs)

    def render(self, time_s, reactor, points, details=(), color=(.25, .9, 1.),
               rms=0., reduced_motion=False, target=None, detail_opacity=1.,
               orbit_phase=None, core_scale=1., audio_bands=(0., 0., 0.), orbit_blend=0.,
               surface_family=None, surface_amount=0., art=None):
        """Render the actual supplied curve or its progressive reactor form.

        ``points`` and ``details`` use OpenGL NDC (positive Y is up). No line or
        particle motion is introduced at reactor=0. Reduced motion freezes all
        internally generated motion; caller-supplied geometry remains authoritative.
        ``detail_opacity`` preserves the MorphController's detail fade, in [0, 1].
        ``target=None`` presents to ``ctx.screen``; EGL callers pass a framebuffer.
        ``orbit_phase`` contains continuous world-space angles supplied by the
        state adapter. Audio bands are already analysed/smoothed outside GL.
        When ``surface_family`` is present, points/details are original local
        catalogue paths (positive Y down) and are projected onto the sphere.
        A surface expression always keeps its supporting sphere visible.
        """
        self._check_open()
        if art is not None:
            self.set_settings(art)
        if not all(math.isfinite(value) for value in (time_s, reactor, rms, detail_opacity,
                                                       core_scale, orbit_blend, surface_amount)):
            raise ValueError("Animation parameters must be finite.")
        if not .85 <= core_scale <= 1.1 or not 0. <= orbit_blend <= 1.:
            raise ValueError("Invalid core scale or orbital alignment.")
        if (surface_family is not None and (not isinstance(surface_family, str) or surface_family not in _SURFACE_FAMILIES)
                or not 0. <= surface_amount <= 1.):
            raise ValueError("Invalid surface expression or opacity.")
        orbit_phase = (tuple((0. if reduced_motion else float(time_s))*speed for speed in (.70, -.91, 1.13))
                       if orbit_phase is None else tuple(orbit_phase))
        audio_bands = tuple(audio_bands)
        if len(orbit_phase) != 3 or not all(math.isfinite(value) for value in orbit_phase):
            raise ValueError("orbit_phase must contain three finite angles.")
        if len(audio_bands) != 3 or not all(math.isfinite(value) and 0. <= value <= 1. for value in audio_bands):
            raise ValueError("audio_bands must contain three values from zero to one.")
        color = tuple(color)
        if len(color) != 3 or not all(math.isfinite(value) and 0 <= value <= 1 for value in color):
            raise ValueError("color must contain three finite values from zero to one.")
        destination = self.ctx.screen if target is None else target
        if destination is None:
            raise RuntimeError("This context has no screen; pass a target framebuffer.")
        segments = self._upload_geometry(points, details)
        # Reduce only the transport representation, not the scene's continuous
        # counters. Four pi preserves quaternion sign and avoids float32 drift
        # in long sessions while remaining continuous at the wrap boundary.
        orbit_phase = tuple(math.remainder(value, math.tau*2) for value in orbit_phase)
        if orbit_blend <= 0.:
            self._alignment_signs = None
        elif self._alignment_signs is None:
            self._alignment_signs = self._orbital_target_signs(orbit_phase)
        reactor = 1. if surface_family is not None else max(0.0, min(1.0, reactor))
        values = {"u_time": 0.0 if reduced_motion else float(time_s),
                  "u_reactor": reactor, "u_rms": max(0.0, min(1.0, rms)),
                  "u_detail_opacity": max(0.0, min(1.0, detail_opacity)),
                  "u_core_scale": core_scale, "u_orbit_blend": orbit_blend,
                  "u_orbit_phase": orbit_phase,
                  "u_audio_bands": tuple(value*.4 for value in audio_bands) if reduced_motion else audio_bands,
                  "u_orbit_targets": self._alignment_signs or (1., 1., 1.),
                  "u_surface_kind": 0. if surface_family is None else 2. if surface_family == "affection" else 1.,
                  "u_surface_amount": surface_amount,
                  "u_color": color, "u_size": self._size}
        self.ctx.disable(self._gl.DEPTH_TEST | self._gl.CULL_FACE | self._gl.BLEND)
        for program in (self._scene, self._curve, self._filament, self._particle):
            self._uniforms(program, values)
        self._pass("scene", self._scene_vao)
        self.ctx.enable(self._gl.BLEND)
        self.ctx.blend_func = self._gl.ONE, self._gl.ONE
        self._curve_vao.render(mode=self._gl.TRIANGLE_STRIP, vertices=4, instances=segments)
        if reactor > 0:
            # Sparse accents require actual supplied audio energy; the stable
            # THINKING core is not buried under a permanent filament cage.
            if rms > 0 and surface_family is None:
                self._filament_vao.render(mode=self._gl.TRIANGLE_STRIP, vertices=4,
                                          instances=72 * 2)
            if self.particles:
                self.ctx.enable(self._gl.PROGRAM_POINT_SIZE)
                self._particle_vao.render(mode=self._gl.POINTS,
                                          vertices=min(384, round(_PARTICLES[self._quality]*self.settings.particle_density/100)))
                self.ctx.disable(self._gl.PROGRAM_POINT_SIZE)
        self.ctx.disable(self._gl.BLEND)
        if self.bloom:
            self._targets["scene"][0].use(location=0)
            self._extract["u_source_size"].value = self._size
            self._pass("bloom_a", self._extract_vao)
            for _ in range(2 if self._quality == "cinematic" else 1):
                self._targets["bloom_a"][0].use(location=0)
                self._blur["u_step"].value = (self.settings.bloom_radius / 100 / self._bloom_size[0], 0)
                self._pass("bloom_b", self._blur_vao)
                self._targets["bloom_b"][0].use(location=0)
                self._blur["u_step"].value = (0, self.settings.bloom_radius / 100 / self._bloom_size[1])
                self._pass("bloom_a", self._blur_vao)
        self._targets["scene"][0].use(location=0)
        self._targets["bloom_a"][0].use(location=1)
        self._resolve["u_bloom_amount"].value = .94*self.settings.bloom_intensity/100 if self.bloom else 0.0
        self._pass("resolved", self._resolve_vao)
        self._targets["resolved"][0].use(location=0)
        destination.use()
        self._copy_vao.render(mode=self._gl.TRIANGLES, vertices=3)

    def read_rgb(self):
        """Return the last internal frame as packed RGB bytes, bottom row first.

        The byte length is ``size[0] * size[1] * 3``. Flip vertically when saving
        in conventional image formats. Readback synchronizes with the GPU and
        should be kept outside timed render loops unless capture is intended.
        """
        self._check_open()
        return self._targets["resolved"][0].read(alignment=1)

    def shutdown(self):
        """Release only owned resources. Safe after partial init and repeated calls."""
        if self._closed:
            return
        self._closed = True
        self._release(self._attachments)
        self._release(self._objects)
        self._attachments.clear()
        self._objects.clear()
        self._targets.clear()
        self._alignment_signs = None
