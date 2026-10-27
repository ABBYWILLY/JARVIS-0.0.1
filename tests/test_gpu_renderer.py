"""Real optional OpenGL tests; no fake contexts, GUI, model or audio device.

Set JARVIS_REQUIRE_GPU=1 to fail instead of skipping when ModernGL/EGL is absent.
This checks the renderer contracts, not hardware speed: EGL may use llvmpipe.
"""
import hashlib
import os
import subprocess
import struct
import sys
import unittest
from unittest import mock

from jarvis.gpu_renderer import GpuRenderer
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

    def test_reactor_animates_and_reduced_motion_freezes_every_gpu_layer(self):
        first = self.frame(1, 1)
        self.assertNotEqual(first, self.frame(8, 1))
        self.assertEqual(self.frame(1, 1, reduced_motion=True),
                         self.frame(140, 1, reduced_motion=True))
        width, height = self.renderer.size
        self.assertGreater(sum(value > 100 for value in first[:width * 3 * (height // 3)]), 60)
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

    def test_quality_bounds_internal_resolution_without_changing_aspect(self):
        self.renderer.resize(3840, 2160)
        self.assertEqual(self.renderer.size, (1280, 720))
        balanced = self.renderer.allocation_bytes
        self.renderer.set_quality("cinematic")
        self.assertEqual(self.renderer.quality, "cinematic")
        self.assertEqual(self.renderer.size, (1920, 1080))
        self.assertGreater(self.renderer.allocation_bytes, balanced)
        self.renderer.resize(900, 1600)
        self.assertEqual(self.renderer.size, (608, 1080))
        self.renderer.set_quality("balanced")
        self.assertEqual(self.renderer.size, (405, 720))
        self.renderer.resize(1, 1)
        self.assertEqual(len(self.frame()), 3)

    def test_invalid_input_keeps_the_renderer_usable(self):
        expected = self.frame()
        for quality in ("eco", "", None):
            with self.assertRaises(ValueError):
                self.renderer.set_quality(quality)
        for size in ((0, 1), (1, -1), (1.5, 2), (True, 2)):
            with self.assertRaises(ValueError):
                self.renderer.resize(*size)
        for kwargs in ({"time_s": float("nan")}, {"reactor": float("inf")},
                       {"color": (1, 2, 3)}, {"points": [(0, 0)]},
                       {"details": (flat_line(),)},
                       {"points": [(0, 0), (float("nan"), 1)]},
                       {"detail_opacity": float("nan")}):
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


if __name__ == "__main__":
    unittest.main()
