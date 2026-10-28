"""Real optional OpenGL tests; no fake contexts, GUI, model or audio device.

Set JARVIS_REQUIRE_GPU=1 to fail instead of skipping when ModernGL/EGL is absent.
This checks the renderer contracts, not hardware speed: EGL may use llvmpipe.
"""
import hashlib
import math
import os
import subprocess
import struct
import sys
import unittest
from array import array
from unittest import mock

from jarvis.gpu_renderer import GpuRenderer, MAX_RENDER_DIMENSION, MAX_RENDER_PIXELS
from jarvis.gpu_config import FIELD_SPECS, GpuSettings
from jarvis.morphing import CATALOGUE
from jarvis import reactor_shaders as shaders


def flat_line(y=0.0):
    return tuple((-.84 + 1.68 * i / 96, y) for i in range(97))


class GpuImportTests(unittest.TestCase):
    def test_import_does_not_load_optional_gpu_or_gui_packages(self):
        code = ("import sys; import jarvis.gpu_renderer; "
                "assert not any(name in sys.modules for name in "
                "('moderngl', 'glcontext', 'glfw', 'tkinter'))")
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


class GpuRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import moderngl
            cls.ctx = moderngl.create_standalone_context(require=330, backend="egl")
        except Exception as error:
            if os.environ.get("JARVIS_REQUIRE_GPU") == "1":
                raise RuntimeError("Required real OpenGL/EGL context unavailable") from error
            raise unittest.SkipTest(f"Optional ModernGL/EGL unavailable: {error}") from error

    @classmethod
    def tearDownClass(cls):
        cls.ctx.release()

    def setUp(self):
        self.renderer = GpuRenderer(self.ctx, 256, 192)
        self.target = self.ctx.simple_framebuffer((256, 192))

    def tearDown(self):
        self.renderer.shutdown()
        self.target.release()

    def frame(self, time_s=0.0, reactor=0.0, points=None, **kwargs):
        self.renderer.render(time_s, reactor, flat_line() if points is None else points,
                             target=self.target, **kwargs)
        return self.renderer.read_rgb()

    def test_all_shader_artwork_controls_change_real_pixels_in_their_relevant_context(self):
        # Timing, state multipliers and frame scheduling are checked against
        # the state adapter below, rather than pretending an uploaded-but-unused
        # uniform proves that a slider has an effect.
        scene_controls = {"ring_speed", "audio_attack_ms", "audio_release_ms",
                          "thinking_contraction", "thinking_speed", "speaking_speed",
                          "listening_speed", "idle_speed", "transition_ms",
                          "ring_acceleration_ms", "expression_transition_ms",
                          "expression_hold_ms", "expression_ring_speed", "fps_limit"}
        symbol = CATALOGUE["smile"]
        context = dict(rms=.35, orbit_phase=(.8, -.7, 1.1),
                       audio_bands=(.5, .4, .6))
        defaults = GpuSettings()
        for key, spec in FIELD_SPECS.items():
            if key in scene_controls:
                continue
            with self.subTest(control=key):
                frame = dict(context)
                if key.startswith("expression_"):
                    frame.update(points=symbol.contour, details=symbol.details,
                                 surface_family="smile", surface_amount=.8)
                self.renderer.set_settings(defaults)
                if key == "particle_colors":
                    # Sparse warm accents can be behind the core at a given
                    # orbital pose; use the supported dense/large preview to
                    # exercise their colour rather than counting hidden points.
                    self.renderer.set_settings({"particle_density": 200, "particle_size": 300})
                original = self.frame(4.2, 1., **frame)
                self.renderer.set_settings({key: spec.low if spec.default != spec.low else spec.high})
                changed = self.frame(4.2, 1., **frame)
                self.assertTrue(original != changed, f"{key} has no rendered effect")

    def test_artwork_changes_keep_geometry_and_texture_allocations_bounded(self):
        geometry = self.renderer._vertex_buffer
        attachments = tuple(self.renderer._attachments)
        allocated = self.renderer.allocation_bytes
        for raw in ({key: spec.low for key, spec in FIELD_SPECS.items()},
                    {key: spec.high for key, spec in FIELD_SPECS.items()}):
            self.renderer.set_settings(raw)
            self.frame(1., 1.)
            self.assertIs(self.renderer._vertex_buffer, geometry)
            self.assertEqual(tuple(self.renderer._attachments), attachments)
            self.assertEqual(self.renderer.allocation_bytes, allocated)
        for profile in ("eco", "balanced", "cinematic"):
            self.renderer.resize(1440, 960)
            self.renderer.set_settings({"profile": profile})
            self.assertEqual(self.renderer.size, (1440, 960))
            self.assertLessEqual(self.renderer.allocation_bytes, 100 * 1024**2)

    def test_halo_radius_changes_spread_and_intensity_changes_light_independently(self):
        self.renderer.bloom = self.renderer.particles = False
        measured = []
        for radius, intensity in ((100, 100), (200, 100), (100, 200)):
            self.renderer.set_settings({"core_brightness": 0, "ring_brightness": 0,
                                        "halo_radius": radius, "halo_intensity": intensity})
            self.frame(0., 1.)
            # Read linear HDR before tone mapping, isolating the physical
            # intensity control from display gamma and bloom amplification.
            linear = array("f")
            linear.frombytes(self.renderer._targets["scene"][1].read(components=4, dtype="f4"))
            row = [max(linear[(96*256+x)*4:(96*256+x)*4+3]) for x in range(128, 220)]
            peak = max(row)
            measured.append((peak, sum(value > peak*.5 for value in row)))
        self.assertAlmostEqual(measured[1][0]/measured[0][0], 1., delta=.03)
        self.assertGreater(measured[1][1], measured[0][1]*1.5)
        self.assertAlmostEqual(measured[2][0]/measured[0][0], 2., delta=.01)
        self.assertEqual(measured[2][1], measured[0][1])

    def test_real_gl_frame_is_rgb_nonblack_and_bottom_up(self):
        raw = self.frame(points=flat_line(.5))
        width, height = self.renderer.size
        self.assertEqual(len(raw), width * height * 3)
        self.assertGreater(max(raw), 170)
        row_peak = [max(raw[y * width * 3:(y + 1) * width * 3]) for y in range(height)]
        brightest = max(range(height), key=row_peak.__getitem__)
        self.assertLess(abs(brightest - height * .75), 3)
        # The presentation framebuffer contains the same orientation and pixels.
        self.assertEqual(self.target.read(components=3, alignment=1), raw)

    def test_idle_is_the_exact_flat_curve_with_no_time_animation(self):
        first = self.frame(0)
        self.assertEqual(first, self.frame(140))
        width, height = self.renderer.size
        rows = [y for y in range(height)
                if max(first[y * width * 3:(y + 1) * width * 3]) > 130]
        self.assertTrue(rows)
        self.assertLessEqual(max(rows) - min(rows), 6)
        self.assertLess(abs(sum(rows) / len(rows) - height / 2), 2)
        self.assertLess(max(first[:width * 3 * (height // 4)]), 45)

    def test_background_is_exact_black_beyond_object_halos_with_or_without_bloom(self):
        # Check real resolved RGB, not the framebuffer clear colour: an ambient
        # term or a tone-mapping offset must not tint the empty composition.
        for size in ((256, 192), (192, 256)):
            self.renderer.resize(*size)
            for bloom in (False, True):
                self.renderer.bloom = bloom
                for reactor, time_s in ((0., 0.), (1., 0.), (1., 7.)):
                    with self.subTest(size=size, bloom=bloom, reactor=reactor, time_s=time_s):
                        raw = self.frame(time_s, reactor)
                        width, height = self.renderer.size
                        margin = min(width, height) // 20
                        for x0, y0 in ((0, 0), (width-margin, 0),
                                       (0, height-margin), (width-margin, height-margin)):
                            for y in range(y0, y0+margin):
                                start = (y*width+x0)*3
                                self.assertEqual(raw[start:start+margin*3], bytes(margin*3))
                        # Black is empty space, not a hidden or disabled renderer.
                        self.assertGreater(max(raw), 170)

    def test_reactor_animates_and_reduced_motion_freezes_every_gpu_layer(self):
        first = self.frame(1, 1)
        self.assertNotEqual(first, self.frame(8, 1))
        self.assertEqual(self.frame(1, 1, reduced_motion=True),
                         self.frame(140, 1, reduced_motion=True))
        width, height = self.renderer.size
        # The simplified composition is centred, rather than required to fill
        # the upper third. It must still form a visible two-dimensional core
        # and orbits, never collapse into the idle horizontal line.
        lit_rows = [y for y in range(height)
                    if max(first[y*width*3:(y+1)*width*3]) > 100]
        self.assertGreater(len(lit_rows), height*.15)
        self.assertLess(min(lit_rows), height*.45)
        self.assertGreater(max(lit_rows), height*.55)
        # HDR is bright locally, with most of the frame retaining dark space.
        self.assertLess(sum(value > 245 for value in first) / len(first), .08)

    def test_all_eight_real_symbols_keep_distinct_visible_details(self):
        hashes = set()
        for family, symbol in CATALOGUE.items():
            with self.subTest(family=family):
                points = tuple((x * .4, -y * .53) for x, y in symbol.contour)
                details = tuple(tuple((x * .4, -y * .53) for x, y in contour)
                                for contour in symbol.details)
                raw = self.frame(points=points, details=details)
                self.assertGreater(max(raw), 170)
                hashes.add(hashlib.sha256(raw).digest())
                if details:
                    self.assertNotEqual(raw, self.frame(points=points))
        self.assertEqual(len(hashes), 8)

    def test_surface_expression_cannot_request_the_old_flat_reactor_replacement(self):
        symbol = CATALOGUE["smile"]
        kwargs = dict(points=symbol.contour, details=symbol.details,
                      surface_family="smile", surface_amount=1., orbit_blend=1.)
        visible = self.frame(2., 1., **kwargs)
        self.assertEqual(visible, self.frame(2., 0., **kwargs))

    def test_bloom_and_particles_share_a_fixed_resource_pool(self):
        allocated = self.renderer.allocation_bytes
        attachments = self.renderer.attachment_bytes
        self.assertEqual(attachments, 256 * 192 * 11 + 64 * 48 * 16)
        self.assertGreater(allocated, attachments)
        glowing = self.frame(2, 1)
        for index in range(8):
            self.frame(index * .1, index / 7)
        self.assertEqual(self.renderer.allocation_bytes, allocated)
        self.renderer.bloom = False
        self.renderer.particles = False
        self.assertNotEqual(glowing, self.frame(2, 1))
        self.assertEqual(self.renderer.allocation_bytes, allocated)

    def test_hdr_extraction_keeps_black_and_subthreshold_material_out_of_bloom(self):
        # Exercise the real extraction shader and HDR targets. Bloom must come
        # from highlights, not lift the entire dark/translucent core or black.
        source, framebuffer = self.renderer._targets["scene"]
        extracted = self.renderer._targets["bloom_a"][1]
        self.ctx.disable(self.renderer._gl.BLEND)
        source.use(location=0)
        self.renderer._extract["u_source_size"].value = self.renderer.size

        def extract(color):
            framebuffer.clear(*color, 1.)
            extracted.use()
            self.renderer._extract_vao.render(vertices=3)
            return struct.unpack("3f", extracted.read(viewport=(0, 0, 1, 1),
                                                      components=3, dtype="f4"))

        for color in ((0., 0., 0.), (.1, .1, .1), (.4, .2, .3)):
            with self.subTest(color=color):
                self.assertEqual(extract(color), (0., 0., 0.))
        high = extract((2., 1., .5))
        higher = extract((4., 2., 1.))
        self.assertGreater(high[0], 0.)
        self.assertGreater(high[1], high[2])
        self.assertGreater(higher[0], high[0])
        self.assertGreater(higher[0], 1.)  # Extraction retains HDR before resolve.

    def test_real_material_fresnel_increases_at_grazing_view_and_clamps_inputs(self):
        fragment = """#version 330
        uniform float u_ndv;
        out vec4 frag;
        """ + shaders.MATERIAL_GLSL + """
        void main() { frag = vec4(fresnel_view(u_ndv),0.0,0.0,1.0); }
        """
        program = self.ctx.program(vertex_shader=shaders.FULLSCREEN_VERTEX,
                                   fragment_shader=fragment)
        vao = self.ctx.vertex_array(program, [])
        texture = self.ctx.texture((1, 1), 4, dtype="f4")
        target = self.ctx.framebuffer(color_attachments=[texture])
        try:
            values = []
            for ndv in (1., .75, .25, 0., -1., 2.):
                program["u_ndv"].value = ndv
                target.use()
                vao.render(vertices=3)
                values.append(struct.unpack("4f", target.read(components=4, dtype="f4"))[0])
            self.assertTrue(0. < values[0] < values[1] < values[2] < values[3] <= 1.)
            self.assertEqual(values[3], values[4])
            self.assertEqual(values[0], values[5])
        finally:
            target.release()
            texture.release()
            vao.release()
            program.release()

    def test_detail_opacity_fades_details_without_modifying_the_main_curve(self):
        symbol = CATALOGUE["smile"]
        points = tuple((x * .4, -y * .53) for x, y in symbol.contour)
        details = tuple(tuple((x * .4, -y * .53) for x, y in contour)
                        for contour in symbol.details)
        zero = self.frame(points=points, details=details, detail_opacity=0)
        partial = self.frame(points=points, details=details, detail_opacity=.3)
        full = self.frame(points=points, details=details, detail_opacity=1)
        self.assertEqual(zero, self.frame(points=points))
        self.assertLess(sum(zero), sum(partial))
        self.assertLess(sum(partial), sum(full))
        self.assertEqual(zero, self.frame(points=points, details=details, detail_opacity=-1))
        self.assertEqual(full, self.frame(points=points, details=details, detail_opacity=2))

    def test_resize_releases_old_attachments_and_preserves_capture_dimensions(self):
        old = tuple(self.renderer._attachments)
        allocated = self.renderer.allocation_bytes
        self.renderer.resize(311, 177)
        self.assertTrue(all(type(resource.mglo).__name__ == "InvalidObject" for resource in old))
        self.assertEqual(self.renderer.size, (311, 177))
        self.assertEqual(len(self.frame()), 311 * 177 * 3)
        current = tuple(self.renderer._attachments)
        self.renderer.resize(311, 177)
        self.assertEqual(tuple(self.renderer._attachments), current)
        self.renderer.resize(256, 192)
        self.assertEqual(self.renderer.allocation_bytes, allocated)

    def test_profile_preserves_physical_geometry_and_portrait_aspect(self):
        self.renderer.resize(3840, 2160)
        self.assertEqual(self.renderer.size, (3840, 2160))
        balanced = self.renderer.allocation_bytes
        self.renderer.set_quality("cinematic")
        self.assertEqual(self.renderer.quality, "cinematic")
        self.assertEqual(self.renderer.size, (3840, 2160))
        self.assertEqual(self.renderer.allocation_bytes, balanced)
        self.renderer.resize(900, 1600)
        self.assertEqual(self.renderer.size, (900, 1600))
        self.renderer.set_quality("balanced")
        self.assertEqual(self.renderer.size, (900, 1600))
        self.renderer.resize(1, 1)
        self.assertEqual(len(self.frame()), 3)

    def test_eco_profile_reduces_secondary_cost_without_blurring_native_core(self):
        self.renderer.resize(640, 360)
        balanced = self.renderer.allocation_bytes
        core_texture = self.renderer._targets["scene"][0]
        self.renderer.set_quality("eco")
        self.assertEqual(self.renderer.quality, "eco")
        self.assertEqual(self.renderer.size, (640, 360))
        self.assertIs(self.renderer._targets["scene"][0], core_texture)
        self.assertLess(self.renderer.allocation_bytes, balanced)
        self.assertGreater(max(self.frame(1., 1.)), 170)

    def test_supersampling_is_relative_to_physical_framebuffer_with_explicit_caps(self):
        for setting, expected in (("auto", (256, 192)), ("100", (256, 192)),
                                  ("125", (320, 240)), ("150", (384, 288)), ("200", (512, 384))):
            with self.subTest(scale=setting):
                self.renderer.set_settings({"render_scale": setting})
                self.assertEqual(self.renderer.size, expected)
                self.assertEqual(self.renderer.resolution_info["physical_size"], (256, 192))
                self.assertFalse(self.renderer.resolution_info["capped"])
                self.assertEqual(len(self.frame(1., 1.)), expected[0]*expected[1]*3)
                # Presentation/HUD target remains physical, not supersampled.
                self.assertEqual(len(self.target.read(components=3)), 256*192*3)
        size, bloom = self.renderer._resolution_plan((7680, 4320), "cinematic")
        self.assertLessEqual(size[0]*size[1], MAX_RENDER_PIXELS)
        self.assertLessEqual(max(size), MAX_RENDER_DIMENSION)
        self.assertAlmostEqual(size[0]/size[1], 16/9, delta=.002)

    def test_supersampling_preserves_apparent_fine_strokes_particles_and_engraving(self):
        self.renderer.bloom = False
        # Isolate fine ink from the unchanged volumetric material. Read the
        # actual physical presentation target, not an artificially resized PNG.
        for kind in ("line", "particles", "glyph"):
            energies, bright_pixels = [], []
            for scale in ("100", "200"):
                self.renderer.set_settings({"render_scale": scale, "core_brightness": 0,
                    "halo_intensity": 0, "ring_brightness": 0, "particle_brightness": 200,
                    "particle_size": 200, "particle_density": 200})
                self.renderer.particles = kind == "particles"
                kwargs = {}
                if kind == "glyph":
                    symbol = CATALOGUE["smile"]
                    kwargs.update(points=symbol.contour, details=symbol.details,
                                  surface_family="smile", surface_amount=1.)
                self.frame(4.2, 0. if kind == "line" else 1., **kwargs)
                raw = self.target.read(components=3, alignment=1)
                energies.append(sum(raw))
                bright_pixels.append(sum(value > 80 for value in raw))
            with self.subTest(layer=kind):
                self.assertGreater(energies[0], 1000)
                self.assertAlmostEqual(energies[1]/energies[0], 1., delta=.15)
                self.assertAlmostEqual(bright_pixels[1]/bright_pixels[0], 1., delta=.15)

    def test_bloom_radius_keeps_its_physical_scale_across_internal_resolutions(self):
        for scale, adaptive in (("100", 0), ("200", 0), ("100", 2), ("auto", 4)):
            with self.subTest(scale=scale, adaptive=adaptive):
                self.renderer.set_settings({"render_scale": scale, "bloom_radius": 150})
                self.renderer.set_adaptive_level(adaptive)
                self.frame(2., 1.)
                # Last blur pass is vertical. Inspect the real program uniform
                # used for its framebuffer, not an unrelated settings field.
                step = self.renderer._blur["u_step"].value
                self.assertAlmostEqual(step[0], 0.)
                self.assertAlmostEqual(step[1], 1.5*4/192, places=6)

    def test_adaptation_reduces_bloom_then_particles_before_auto_main_resolution(self):
        self.renderer.resize(640, 360)
        core = self.renderer._targets["scene"][0]
        settings = self.renderer.settings
        bloom_sizes = []
        for level in range(4):
            self.renderer.set_adaptive_level(level)
            self.assertEqual(self.renderer.size, (640, 360))
            self.assertIs(self.renderer._targets["scene"][0], core)
            bloom_sizes.append(self.renderer.resolution_info["bloom_size"])
            self.assertIs(self.renderer.settings, settings)
        self.assertLess(bloom_sizes[1][0], bloom_sizes[0][0])
        self.assertLess(bloom_sizes[2][0], bloom_sizes[1][0])
        self.assertEqual(bloom_sizes[3], bloom_sizes[2])
        self.renderer.set_adaptive_level(4)
        self.assertEqual(self.renderer.size, (480, 270))
        self.assertTrue(self.renderer.resolution_info["capped"])
        self.renderer.set_settings({"render_scale": "100"})
        self.assertEqual(self.renderer.size, (640, 360))
        self.renderer.set_adaptive_level(0)
        self.assertEqual(self.renderer.resolution_info["bloom_size"], bloom_sizes[0])
        for invalid in (-1, 5, True, 2.5):
            with self.subTest(level=invalid), self.assertRaises(ValueError):
                self.renderer.set_adaptive_level(invalid)

    def test_animated_material_reuses_unchanged_geometry_upload(self):
        with mock.patch.object(self.renderer._vertex_buffer, "write", wraps=self.renderer._vertex_buffer.write) as write:
            first = self.frame(1., 1.)
            second = self.frame(1.2, 1.)
            self.assertNotEqual(first, second)
            self.assertEqual(write.call_count, 1)
            self.frame(1.2, 1., points=flat_line(.1))
            self.assertEqual(write.call_count, 2)

    def test_failed_scale_or_adaptive_allocation_preserves_preference_and_live_frame(self):
        before, original = self.renderer.settings, self.renderer.size
        with mock.patch.object(self.ctx, "texture", side_effect=RuntimeError("allocation denied")):
            with self.assertRaisesRegex(RuntimeError, "allocation denied"):
                self.renderer.set_settings({"render_scale": "200"})
            self.assertEqual(self.renderer.settings, before)
            self.assertEqual(self.renderer.size, original)
            with self.assertRaisesRegex(RuntimeError, "allocation denied"):
                self.renderer.set_adaptive_level(1)
            self.assertEqual(self.renderer.adaptive_level, 0)
        self.assertGreater(max(self.frame()), 170)

    def test_spectral_bands_change_object_light_without_changing_allocations(self):
        baseline = self.frame(2., 1., orbit_phase=(.3, -.5, .8))
        allocated = self.renderer.allocation_bytes
        frames = set()
        for bands in ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)):
            raw = self.frame(2., 1., orbit_phase=(.3, -.5, .8), audio_bands=bands)
            self.assertNotEqual(raw, baseline)
            frames.add(hashlib.sha256(raw).digest())
            self.assertEqual(self.renderer.allocation_bytes, allocated)
        self.assertEqual(len(frames), 3)

    def test_all_eight_surface_expressions_add_visible_traits_without_erasing_the_sphere(self):
        self.renderer.bloom = False
        self.renderer.particles = False
        hashes = set()
        allocated = self.renderer.allocation_bytes
        for family, symbol in CATALOGUE.items():
            with self.subTest(family=family):
                kwargs = dict(points=symbol.contour, details=symbol.details,
                              surface_family=family, orbit_blend=1., orbit_phase=(.8, -.4, 1.2))
                bare = self.frame(2., 1., surface_amount=0., **kwargs)
                partial = self.frame(2., 1., surface_amount=.35, **kwargs)
                full = self.frame(2., 1., surface_amount=1., **kwargs)
                width, height = self.renderer.size
                centre = ((height//2)*width+width//2)*3
                self.assertGreater(max(bare[centre:centre+3]), 50)
                # The original iridescent sphere is still there in every frame;
                # glyphs add light to it instead of substituting a flat mesh.
                self.assertTrue(all(a >= b for a, b in zip(full, bare)))
                self.assertLess(sum(bare), sum(partial))
                self.assertLess(sum(partial), sum(full))
                hashes.add(hashlib.sha256(full).digest())
                self.assertEqual(self.renderer.allocation_bytes, allocated)
        self.assertEqual(len(hashes), 8)

    def test_reduced_motion_respects_explicit_frozen_orientations(self):
        phases = (.8, -.4, 1.2)
        first = self.frame(1., 1., orbit_phase=phases, reduced_motion=True)
        self.assertEqual(first, self.frame(500., 1., orbit_phase=phases, reduced_motion=True))
        self.assertNotEqual(first, self.frame(1., 1., orbit_phase=(0., 0., 0.), reduced_motion=True))

    def test_invalid_input_keeps_the_renderer_usable(self):
        expected = self.frame()
        for quality in ("ultra", "", None):
            with self.assertRaises(ValueError):
                self.renderer.set_quality(quality)
        for size in ((0, 1), (1, -1), (1.5, 2), (True, 2)):
            with self.assertRaises(ValueError):
                self.renderer.resize(*size)
        for kwargs in ({"time_s": float("nan")}, {"reactor": float("inf")},
                       {"color": (1, 2, 3)}, {"points": [(0, 0)]},
                       {"details": (flat_line(),)},
                       {"points": [(0, 0), (float("nan"), 1)]},
                       {"detail_opacity": float("nan")}, {"core_scale": .5},
                       {"core_scale": float("nan")}, {"orbit_phase": (0., 1.)},
                       {"orbit_phase": (0., 1., float("inf"))},
                       {"audio_bands": (0., 0., 2.)}, {"orbit_blend": -1.},
                       {"surface_family": "unknown"}, {"surface_family": []},
                       {"surface_amount": float("nan")}, {"surface_amount": 2.}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.frame(**kwargs)
        self.assertEqual(expected, self.frame())

    def test_failed_resize_preserves_previous_live_attachments(self):
        expected = self.frame()
        previous = tuple(self.renderer._attachments)
        with mock.patch.object(self.ctx, "texture", side_effect=RuntimeError("allocation failed")):
            with self.assertRaisesRegex(RuntimeError, "allocation failed"):
                self.renderer.resize(321, 241)
        self.assertEqual(self.renderer.size, (256, 192))
        self.assertEqual(tuple(self.renderer._attachments), previous)
        self.assertEqual(expected, self.frame())

    def test_partial_initialization_cleans_up_owned_gl_resources(self):
        created = []
        real_program = self.ctx.program

        def create_program(**kwargs):
            if len(created) == 2:
                raise RuntimeError("shader creation failed")
            program = real_program(**kwargs)
            created.append(program)
            return program

        with mock.patch.object(self.ctx, "program", side_effect=create_program):
            with self.assertRaisesRegex(RuntimeError, "shader creation failed"):
                GpuRenderer(self.ctx, 64, 48)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(type(program.mglo).__name__ == "InvalidObject" for program in created))
        self.assertGreater(max(self.frame()), 170)

    def test_shutdown_is_idempotent_and_does_not_release_callers_context(self):
        self.renderer.shutdown()
        self.renderer.shutdown()
        self.assertEqual(self.renderer.allocation_bytes, 0)
        for operation in (self.renderer.read_rgb, lambda: self.renderer.resize(3, 3),
                          lambda: self.renderer.set_quality("balanced"), self.frame):
            with self.assertRaisesRegex(RuntimeError, "shut down"):
                operation()
        self.target.clear(.1, .2, .3, 1)
        self.assertTrue(self.target.read())

    def test_cleanup_errors_are_observable_and_do_not_stop_other_releases(self):
        failed = self.renderer._curve_vao
        real_release = failed.release
        with mock.patch.object(failed, "release", side_effect=RuntimeError("context lost")):
            self.renderer.shutdown()
        try:
            self.assertEqual(len(self.renderer.release_errors), 1)
            self.assertIn("RuntimeError: context lost", self.renderer.release_errors[0])
            self.assertEqual(type(self.renderer._scene.mglo).__name__, "InvalidObject")
            self.renderer.shutdown()
            self.assertEqual(len(self.renderer.release_errors), 1)
        finally:
            real_release()

    def test_real_shader_projects_near_objects_larger_and_preserves_aspect(self):
        fragment = """#version 330
        uniform vec3 u_world;
        uniform vec2 u_size;
        out vec4 frag;
        """ + shaders.SPACE_GLSL + """
        void main() {
            vec2 projected = project_world(u_world);
            vec2 round_trip = scene_plane(plane_ndc(projected,u_size),u_size);
            frag = vec4(projected,round_trip);
        }
        """
        program = self.ctx.program(vertex_shader=shaders.FULLSCREEN_VERTEX,
                                   fragment_shader=fragment)
        vao = self.ctx.vertex_array(program, [])
        texture = self.ctx.texture((1, 1), 4, dtype="f4")
        target = self.ctx.framebuffer(color_attachments=[texture])
        try:
            values = []
            for size in ((900, 600), (600, 900)):
                program["u_size"].value = size
                for depth in (-.4, 0., .4):
                    program["u_world"].value = (.1, .05, depth)
                    target.use()
                    vao.render(vertices=3)
                    x, y, restored_x, restored_y = struct.unpack("4f", target.read(components=4, dtype="f4"))
                    self.assertAlmostEqual(x / y, 2., places=5)
                    self.assertAlmostEqual(x, restored_x, places=6)
                    self.assertAlmostEqual(y, restored_y, places=6)
                    values.append(x)
            self.assertLess(values[0], values[1])
            self.assertLess(values[1], values[2])
            self.assertAlmostEqual(values[0], values[3])
            self.assertAlmostEqual(values[2], values[5])
        finally:
            target.release()
            texture.release()
            vao.release()
            program.release()

    def test_actual_particle_shader_occludes_rear_objects_but_keeps_front_and_idle(self):
        vertex = """#version 330
        uniform vec3 u_world;
        uniform vec2 u_size;
        out float v_power, v_warm;
        flat out float v_depth;
        """ + shaders.SPACE_GLSL + """
        void main() {
            gl_Position = vec4(plane_ndc(project_world(u_world),u_size),0.0,1.0);
            gl_PointSize = 9.0;
            v_power = 1.0;
            v_warm = 0.0;
            v_depth = u_world.z;
        }
        """
        program = self.ctx.program(vertex_shader=vertex,
                                   fragment_shader=shaders.PARTICLE_FRAGMENT)
        vao = self.ctx.vertex_array(program, [])
        target = self.ctx.simple_framebuffer((96, 96))
        try:
            program["u_size"].value = (96, 96)
            program["u_color"].value = (.25, .9, 1.)
            self.ctx.enable(self.renderer._gl.PROGRAM_POINT_SIZE)
            self.ctx.disable(self.renderer._gl.BLEND)
            def point(x, depth, activation=1.):
                program["u_world"].value = (x, 0., depth)
                program["u_reactor"].value = activation
                target.use()
                target.clear()
                vao.render(mode=self.renderer._gl.POINTS, vertices=1)
                return max(target.read(components=3))
            self.assertGreater(point(0., .4), 150)
            self.assertEqual(point(0., -.4), 0)
            self.assertGreater(point(.5, -.4), 150)
            self.assertGreater(point(0., -.4, activation=0.), 150)
        finally:
            self.ctx.disable(self.renderer._gl.PROGRAM_POINT_SIZE)
            target.release()
            vao.release()
            program.release()

    def test_real_orbital_bases_rotate_independently_in_depth_about_the_origin(self):
        fragment = """#version 330
        in vec2 uv;
        uniform float u_ring, u_angle;
        out vec4 frag;
        """ + shaders.SPACE_GLSL + """
        void main() {
            vec3 a,b; orbit_axes(u_ring,0.0,a,b);
            vec3 p=(a*cos(u_angle)+b*sin(u_angle))*(.48+u_ring*.11);
            frag=vec4(p,1.0);
        }
        """
        program = self.ctx.program(vertex_shader=shaders.FULLSCREEN_VERTEX, fragment_shader=fragment)
        vao = self.ctx.vertex_array(program, [])
        texture = self.ctx.texture((1, 1), 4, dtype="f4")
        target = self.ctx.framebuffer(color_attachments=[texture])
        try:
            def position(ring, angle, phases):
                program["u_ring"].value = ring
                program["u_angle"].value = angle
                program["u_orbit_phase"].value = phases
                target.use()
                vao.render(vertices=3)
                return struct.unpack("4f", target.read(components=4, dtype="f4"))[:3]
            initial, moved = [], []
            for ring in range(3):
                phases = tuple(.9 if index == ring else 0. for index in range(3))
                a = position(ring, 0., (0., 0., 0.))
                b = position(ring, 0., phases)
                opposite = position(ring, 3.141592653589793, phases)
                initial.append(a)
                moved.append(b)
                self.assertNotEqual(a, b)
                self.assertGreater(abs(a[2]-b[2]), .001)
                for coordinate, opposite_coordinate in zip(b, opposite):
                    self.assertAlmostEqual(coordinate+opposite_coordinate, 0., places=6)
                self.assertAlmostEqual(sum(x*x for x in b), (.48+ring*.11)**2, places=6)
                other = (ring+1) % 3
                self.assertEqual(position(other, .7, (0., 0., 0.)), position(other, .7, phases))
            self.assertEqual(len(set(moved)), 3)
        finally:
            target.release()
            texture.release()
            vao.release()
            program.release()

    def test_scaled_sphere_uses_the_same_radius_for_actual_depth_occlusion(self):
        fragment = """#version 330
        out vec4 frag;
        """ + shaders.SPACE_GLSL + """
        void main() { frag=vec4(core_front(vec2(.28,0.0)),0.0,0.0,1.0); }
        """
        program = self.ctx.program(vertex_shader=shaders.FULLSCREEN_VERTEX, fragment_shader=fragment)
        vao = self.ctx.vertex_array(program, [])
        texture = self.ctx.texture((1, 1), 4, dtype="f4")
        target = self.ctx.framebuffer(color_attachments=[texture])
        try:
            values = []
            for scale in (1., .92):
                program["u_core_scale"].value = scale
                target.use()
                vao.render(vertices=3)
                values.append(struct.unpack("4f", target.read(components=4, dtype="f4"))[0])
            self.assertLess(values[0], 2.)
            self.assertGreater(values[1], 2.)
        finally:
            target.release()
            texture.release()
            vao.release()
            program.release()

    def test_real_surface_projection_follows_the_visible_spherical_hemisphere(self):
        fragment = """#version 330
        uniform vec2 u_local;
        out vec4 frag;
        """ + shaders.SPACE_GLSL + """
        void main() { vec3 p=surface_point(u_local); frag=vec4(p,dot(p,p)); }
        """
        program = self.ctx.program(vertex_shader=shaders.FULLSCREEN_VERTEX, fragment_shader=fragment)
        vao = self.ctx.vertex_array(program, [])
        texture = self.ctx.texture((1, 1), 4, dtype="f4")
        target = self.ctx.framebuffer(color_attachments=[texture])
        try:
            program["u_core_scale"].value = .92
            values = []
            for point in ((0., 0.), (.5, 0.), (0., .5), (.8, .2), (-.8, -.2)):
                program["u_local"].value = point
                target.use()
                vao.render(vertices=3)
                x, y, z, radius2 = struct.unpack("4f", target.read(components=4, dtype="f4"))
                self.assertAlmostEqual(radius2, (.30*.92)**2, places=6)
                self.assertGreater(z, 0.)
                values.append((x, y, z))
            self.assertGreater(values[0][2], values[1][2])
            self.assertGreater(values[1][0], values[0][0])
            self.assertLess(values[2][1], values[0][1])  # Catalogue Y points down.
        finally:
            target.release()
            texture.release()
            vao.release()
            program.release()

    def test_surface_alignment_remains_finite_and_continuous_at_long_phase_boundaries(self):
        fragment = """#version 330
        uniform float u_ring;
        uniform int u_axis;
        out vec4 frag;
        """ + shaders.SPACE_GLSL + """
        void main() { vec3 a,b; orbit_axes(u_ring,0.0,a,b); frag=vec4(u_axis==0 ? a : b,1.0); }
        """
        program = self.ctx.program(vertex_shader=shaders.FULLSCREEN_VERTEX, fragment_shader=fragment)
        vao = self.ctx.vertex_array(program, [])
        texture = self.ctx.texture((1, 1), 4, dtype="f4")
        target = self.ctx.framebuffer(color_attachments=[texture])
        try:
            def basis(ring, phases, blend):
                program["u_ring"].value = ring
                program["u_orbit_phase"].value = tuple(math.remainder(p, math.tau*2) for p in phases)
                program["u_orbit_blend"].value = blend
                vectors = []
                for axis in (0, 1):
                    program["u_axis"].value = axis
                    target.use()
                    vao.render(vertices=3)
                    vector = struct.unpack("4f", target.read(components=4, dtype="f4"))[:3]
                    self.assertTrue(all(math.isfinite(x) for x in vector))
                    self.assertAlmostEqual(sum(x*x for x in vector), 1., places=5)
                    vectors.append(vector)
                self.assertAlmostEqual(sum(a*b for a, b in zip(*vectors)), 0., places=5)
                return vectors
            for ring in range(3):
                for phase in (-math.pi, math.pi, 2.373, -math.tau, math.tau, 10000*math.tau+math.pi):
                    phases = [.3, -.7, 1.1]
                    phases[ring] = phase
                    program["u_orbit_targets"].value = self.renderer._orbital_target_signs(phases)
                    before, after = list(phases), list(phases)
                    before[ring] -= .00001
                    after[ring] += .00001
                    a, b = basis(ring, before, .5), basis(ring, after, .5)
                    self.assertLess(max(abs(x-y) for av, bv in zip(a, b) for x, y in zip(av, bv)), .001)
                    aligned = basis(ring, phases, 1.)
                    self.assertEqual(aligned, [(1., 0., 0.), (0., 1., 0.)])
        finally:
            target.release()
            texture.release()
            vao.release()
            program.release()

    def test_alignment_target_sign_is_held_until_the_expression_has_returned(self):
        # A full turn preserves the world pose while changing the equivalent
        # quaternion sign. An active alignment must keep its entry target.
        symbol = CATALOGUE["smile"]
        kwargs = dict(points=symbol.contour, details=symbol.details,
                      surface_family="smile", surface_amount=.5, orbit_blend=.5)
        self.frame(1., 1., orbit_phase=(0., 0., 0.), **kwargs)
        initial = self.renderer._alignment_signs
        self.frame(1., 1., orbit_phase=(math.tau, 0., 0.), **kwargs)
        self.assertEqual(self.renderer._alignment_signs, initial)
        self.frame(1., 1., orbit_phase=(math.tau, 0., 0.), orbit_blend=0.)
        self.assertIsNone(self.renderer._alignment_signs)
        self.frame(1., 1., orbit_phase=(math.tau, 0., 0.), **kwargs)
        self.assertNotEqual(self.renderer._alignment_signs[0], initial[0])


if __name__ == "__main__":
    unittest.main()
