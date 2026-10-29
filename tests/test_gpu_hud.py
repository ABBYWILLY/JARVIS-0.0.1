"""GPU HUD layout and actual optional EGL rasterization, without audio/model."""
import os
import subprocess
import sys
import unittest

from jarvis.gpu_hud import BUTTONS, ENGINE_BUTTONS, GpuHud, caption_runs, hit_test, layout


class HudLayoutTests(unittest.TestCase):
    def test_import_does_not_load_gpu_pillow_or_tk(self):
        subprocess.run([sys.executable, "-c", "import sys; import jarvis.gpu_hud; "
                        "assert not any(n in sys.modules for n in ('moderngl','PIL','tkinter','glfw'))"],
                       check=True, capture_output=True)

    def test_all_buttons_remain_in_window_at_small_sizes_portrait_and_dpi(self):
        for width, height in ((320, 240), (560, 320), (440, 900), (1920, 1080), (3840, 2160)):
            for dpi in (1., 1.5, 2.5, 3.):
                with self.subTest(size=(width, height), dpi=dpi):
                    spec = layout(width, height, dpi)
                    self.assertEqual(tuple(action for action, _ in spec["buttons"]), BUTTONS)
                    self.assertEqual(tuple(action for action, _ in spec["engine_buttons"]), ENGINE_BUTTONS)
                    for action, (left, top, right, bottom) in (*spec["engine_buttons"], *spec["buttons"]):
                        self.assertTrue(0 <= left < right <= width)
                        self.assertTrue(0 <= top < bottom <= height)
                        self.assertEqual(hit_test((left+right)/2, (top+bottom)/2, width, height, dpi), action)
                    self.assertIsNone(hit_test(width/2, height/2, width, height, dpi))
                    for _action, (_left, top, _right, bottom) in spec["engine_buttons"]:
                        self.assertLess(bottom, spec["header_height"])
                        self.assertLess(top, height * .1)
        self.assertEqual(GpuHud.buttons, ENGINE_BUTTONS + BUTTONS)

    def test_caption_offsets_keep_french_and_only_prepared_words_are_accented(self):
        original = "La colère et la\nrage, le cœur ❤️"
        first, cursor = caption_runs(original, "La colère et la", 0, ((3, 9), (16, 20)))
        second, _ = caption_runs(original, "rage, le cœur ❤️", cursor, ((3, 9), (16, 20)))
        self.assertEqual("".join(text for text, _ in first), "La colère et la")
        self.assertEqual("".join(text for text, _ in second), "rage, le cœur ❤️")
        self.assertEqual("".join(text for text, active in first if active), "colère")
        self.assertEqual("".join(text for text, active in second if active), "rage")
        self.assertEqual(original, "La colère et la\nrage, le cœur ❤️")


class HudEglTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import moderngl
            import PIL
            cls.ctx = moderngl.create_standalone_context(require=330, backend="egl")
        except Exception as error:
            if os.environ.get("JARVIS_REQUIRE_GPU") == "1":
                raise RuntimeError("Required HUD EGL/Pillow unavailable") from error
            raise unittest.SkipTest(f"Optional HUD EGL/Pillow unavailable: {error}") from error

    @classmethod
    def tearDownClass(cls):
        cls.ctx.release()

    def setUp(self):
        self.hud = GpuHud(self.ctx)
        self.target = self.ctx.simple_framebuffer((960, 640))
        self.addCleanup(self.target.release)
        self.addCleanup(self.hud.shutdown)

    def draw(self, data=None, focused=-1, width=960, height=640, target=None):
        target = target or self.target
        target.clear(.11, .22, .33, 1.)
        self.hud.render(data or {"state": "thinking", "caption": "Bonjour, déjà de retour ❤️ !",
                                  "microphone": "désactivé", "caption_note": "Synchronisation estimée par segment"},
                        width, height, focused, target=target)
        return target.read(components=3, alignment=1)

    def test_actual_hud_keeps_center_pixels_and_paints_readable_controls(self):
        self.target.clear(.11, .22, .33, 1.)
        before = self.target.read(components=3, alignment=1)
        after = self.draw()
        center = (320 * 960 + 480) * 3
        self.assertEqual(before[center:center+3], after[center:center+3])
        self.assertNotEqual(before[:960*130*3], after[:960*130*3])
        self.assertNotEqual(before[-960*60*3:], after[-960*60*3:])
        self.assertTrue(self.hud.caption_lines)
        self.assertLessEqual(len(self.hud.caption_lines), 2)

    def test_engine_controls_are_real_pixels_active_state_and_six_keyboard_focuses(self):
        payload = {"state": "thinking", "active_engine": "gpu"}
        gpu = self.draw(payload)
        payload["active_engine"] = "canvas"
        canvas = self.draw(payload)
        spec = layout(960, 640)
        # Read back the actual target. No geometry model/mock can satisfy this.
        for _action, (left, top, right, bottom) in spec["engine_buttons"]:
            rows = range(640 - bottom, 640 - top)
            before = b"".join(gpu[(row * 960 + left)*3:(row * 960 + right)*3] for row in rows)
            after = b"".join(canvas[(row * 960 + left)*3:(row * 960 + right)*3] for row in rows)
            self.assertNotEqual(before, after)
        payload["active_engine"] = "gpu"
        focused_pixels = set()
        for index in range(len(self.hud.buttons)):
            focused_pixels.add(self.draw(payload, focused=index))
        self.assertEqual(len(focused_pixels), 6)
        self.assertEqual(self.hud.buttons[-1], "stop")

    def test_measured_performance_is_only_displayed_in_diagnostic_mode(self):
        data = {"state": "thinking", "shortcuts": "F9 Diagnostic", "performance": "59.8 FPS · rendu 3840×2160"}
        immersion = self.draw(data)
        uploaded = self.hud.upload_count
        data["performance"] = "60.0 FPS · rendu 3840×2160"
        self.assertEqual(immersion, self.draw(data))
        self.assertEqual(self.hud.upload_count, uploaded)
        data["diagnostic"] = True
        diagnostic = self.draw(data)
        self.assertNotEqual(immersion, diagnostic)
        data["performance"] = "58.2 FPS · rendu 2560×1440"
        self.assertNotEqual(diagnostic, self.draw(data))

    def test_atlas_is_reused_and_text_is_not_rasterized_on_unchanged_frames(self):
        self.draw()
        texture, size = self.hud.texture, self.hud._size
        self.assertEqual(self.hud.upload_count, 1)
        self.draw()
        self.assertEqual(self.hud.upload_count, 1)
        self.assertIs(self.hud.texture, texture)
        self.draw(focused=2)
        self.assertEqual(self.hud.upload_count, 2)
        self.assertIs(self.hud.texture, texture)
        self.assertEqual(self.hud._size, size)
        self.assertLessEqual(self.hud.allocation_bytes, 4096 * 1024 * 4)

    def test_cognitive_text_changes_only_the_header_and_reuses_the_atlas(self):
        source = {"state": "thinking", "caption": "Sous-titres préservés 😊"}
        original = self.draw(source)
        texture, size = self.hud.texture, self.hud._size
        source["cognitive"] = "Transcription locale · modèle Qwen · Rapide"
        cognitive = self.draw(source)
        self.assertNotEqual(original, cognitive)
        self.assertIs(self.hud.texture, texture)
        self.assertEqual(self.hud._size, size)
        # OpenGL readback starts at the bottom: the top band is at the end.
        unchanged_bytes = (640 - layout(960, 640)["header_height"]) * 960 * 3
        self.assertEqual(original[:unchanged_bytes], cognitive[:unchanged_bytes])
        uploads = self.hud.upload_count
        self.assertEqual(cognitive, self.draw(source))
        self.assertEqual(self.hud.upload_count, uploads)
        source["cognitive"] = ""
        self.assertEqual(original, self.draw(source))

    def test_hidpi_text_uses_physical_pixels_and_releases_atlas_on_monitor_change(self):
        # The HUD goes directly to presentation pixels, never the scene's
        # adaptive/bloom resolution. A 4K monitor must not stretch 1920px text.
        target = self.ctx.simple_framebuffer((3840, 2160))
        self.addCleanup(target.release)
        payload = {"state": "thinking", "caption": "Déjà net : l'été, cœur et 125 €.",
                   "dpi_scale": 2.}
        self.draw(payload, width=3840, height=2160, target=target)
        first = self.hud.texture
        self.assertEqual(self.hud._size[0], 3840)
        self.assertEqual(self.hud.raster_info["physical_pixel_ratio"], 1.)
        self.assertFalse(self.hud.raster_info["limited"])
        self.assertEqual(self.hud._size[1], 344)
        uploaded = self.hud.upload_count
        self.draw(payload, width=3840, height=2160, target=target)
        self.assertIs(self.hud.texture, first)
        self.assertEqual(self.hud.upload_count, uploaded)
        payload["dpi_scale"] = 1.5
        self.draw(payload, width=3840, height=2160, target=target)
        self.assertEqual(type(first.mglo).__name__, "InvalidObject")
        self.assertEqual(self.hud._size, (3840, 258))
        self.assertLessEqual(self.hud.allocation_bytes, 4096 * 1024 * 4)

    def test_extreme_framebuffer_keeps_explicit_atlas_limit_instead_of_unbounded_allocation(self):
        # Exercise raster allocation only: no huge presentation framebuffer.
        spec, _top, _bottom = self.hud._raster({"dpi_scale": 3., "caption": "Texte borné"},
                                             12000, 6000, -1)
        self.assertEqual(spec["width"], 12000)
        self.assertLessEqual(self.hud._size[0], 4096)
        self.assertLessEqual(self.hud._size[1], 1024)
        self.assertTrue(self.hud.raster_info["limited"])
        self.assertIsNotNone(self.hud.raster_info["limit_reason"])

    def test_long_original_caption_is_bounded_two_lines_and_accents_change_real_pixels(self):
        original = "La colère et la rage, le cœur et l'été. " * 100
        payload = {"state": "jarvis_speaking", "caption": original}
        neutral = self.draw(payload)
        payload["caption_marks"] = [(3, 9)]
        payload["caption_accent"] = (255, 120, 70)
        accented = self.draw(payload)
        self.assertNotEqual(neutral, accented)
        self.assertEqual(payload["caption"], original)
        self.assertEqual(len(self.hud.caption_lines), 2)
        self.assertTrue(self.hud.caption_lines[-1].endswith("…"))
        uploaded = self.hud.upload_count
        payload["caption_accent"] = (70, 190, 255)
        changed_palette = self.draw(payload)
        self.assertNotEqual(accented, changed_palette)
        self.assertEqual(self.hud.upload_count, uploaded)

    def test_resize_releases_old_texture_and_shutdown_preserves_callers_context(self):
        self.draw()
        old = self.hud.texture
        small = self.ctx.simple_framebuffer((320, 240))
        try:
            self.draw(width=320, height=240, target=small)
            self.assertEqual(type(old.mglo).__name__, "InvalidObject")
            self.assertEqual(len(small.read(components=3)), 320 * 240 * 3)
        finally:
            small.release()
        self.hud.shutdown()
        self.hud.shutdown()
        self.assertEqual(self.hud.allocation_bytes, 0)
        with self.assertRaisesRegex(RuntimeError, "fermé"):
            self.draw()
        self.target.clear(.2, .1, .3, 1.)
        self.assertTrue(self.target.read())


if __name__ == "__main__":
    unittest.main()
