"""Optional GPU window controls, drawn over the same OpenGL framebuffer.

Pillow only rasterizes changed text into a bounded atlas. No Tk interpreter,
audio device, model, or GPU package is imported until this HUD is constructed.
The center is never covered by a second visualizer or a full-window texture.
"""
from pathlib import Path


BUTTONS = ("command", "studio", "microphone", "stop")
_LABELS = ("COMMAND OS", "Studio", "Micro", "Arrêt")
_STATES = {"silent": "Repos", "listening": "Écoute", "user_speaking": "Voix détectée",
           "thinking": "Réflexion", "jarvis_speaking": "Parole", "dormant": "Sommeil"}
_MAX_ATLAS_WIDTH = 4096
_MAX_ATLAS_HEIGHT = 1024


def layout(width, height, scale=1.):
    """Return framebuffer-pixel rectangles, also used for mouse hit testing."""
    width, height = max(1, int(width)), max(1, int(height))
    scale = max(.65, min(3., float(scale), width / 440, height / 260))
    gap = max(4, round(10 * scale))
    button_height = max(25, round(34 * scale))
    footer_height = min(height // 2, round(112 * scale))
    header_height = min(height // 3, round(60 * scale))
    top = height - gap - button_height
    available = max(4, width - gap * 5)
    buttons = []
    for index, action in enumerate(BUTTONS):
        left = gap + index * (available / 4 + gap)
        right = gap + (index + 1) * available / 4 + index * gap
        buttons.append((action, (round(left), top, round(right), top + button_height)))
    return {"width": width, "height": height, "scale": scale,
            "header_height": header_height, "footer_height": footer_height,
            "buttons": tuple(buttons)}


def hit_test(x, y, width, height, scale=1.):
    for action, (left, top, right, bottom) in layout(width, height, scale)["buttons"]:
        if left <= x < right and top <= y < bottom:
            return action
    return None


def _lines(text, font, width, limit=2):
    """Pixel-wrap a bounded caption without changing its archived/source text."""
    text = " ".join(str(text or "").split())[:4096]
    if not text or width <= 0:
        return ()
    lines, current = [], ""
    for char in text:
        if current and font.getlength(current + char) > width:
            # Keep words together when possible; a long word still wraps.
            split = current.rfind(" ")
            if split > 0:
                lines.append(current[:split])
                current = current[split + 1:] + char
            else:
                lines.append(current)
                current = char
            if len(lines) == limit:
                break
        else:
            current += char
    else:
        if current:
            lines.append(current)
        return tuple(lines[:limit])
    # More source text remains: mark truncation on the last displayed line.
    final = lines[-1].rstrip()
    while final and font.getlength(final + "…") > width:
        final = final[:-1]
    lines[-1] = final + "…"
    return tuple(lines)


def caption_runs(source, line, cursor, marks):
    """Map prepared source offsets through whitespace wrapping, without NLP."""
    normalized, offsets = [], []
    for index, char in enumerate(source[:4096]):
        if char.isspace():
            if normalized and normalized[-1] != " ":
                normalized.append(" ")
                offsets.append(index)
        else:
            normalized.append(char)
            offsets.append(index)
    text = "".join(normalized).rstrip()
    literal = line[:-1] if line.endswith("…") else line
    start = text.find(literal, cursor)
    if start < 0:
        return ((line, False),), cursor
    runs = []
    for relative, char in enumerate(line):
        position = start + relative
        accented = (position < start + len(literal) and position < len(offsets)
                    and any(begin <= offsets[position] < end for begin, end in marks))
        if runs and runs[-1][1] == accented:
            runs[-1] = (runs[-1][0] + char, accented)
        else:
            runs.append((char, accented))
    return tuple(runs), start + len(literal)


class GpuHud:
    buttons = BUTTONS

    def __init__(self, ctx):
        import moderngl
        from PIL import Image, ImageDraw, ImageFont
        self.ctx, self._gl = ctx, moderngl
        self._Image, self._ImageDraw, self._ImageFont = Image, ImageDraw, ImageFont
        self._font_path = next((str(path) for path in (
            Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf")) if path.is_file()), None)
        self._fonts = {}
        self.texture = self.program = self.vao = None
        self._size = self._key = None
        self.raster_info = {}
        self._closed = False
        self.upload_count = 0
        self.caption_lines = ()
        self._accent = (93 / 255, 227 / 255, 247 / 255)
        self._objects = []
        try:
            self.program = ctx.program(vertex_shader="""#version 330
                uniform vec2 u_size;
                uniform vec4 u_rect, u_tex;
                out vec2 uv;
                void main() {
                    vec2 p=vec2(gl_VertexID&1,(gl_VertexID>>1)&1);
                    vec2 pixel=u_rect.xy+p*u_rect.zw;
                    gl_Position=vec4(pixel.x/u_size.x*2.0-1.0,1.0-pixel.y/u_size.y*2.0,0.0,1.0);
                    uv=u_tex.xy+p*u_tex.zw;
                }
                """, fragment_shader="""#version 330
                uniform sampler2D u_image;
                uniform vec3 u_accent;
                in vec2 uv;
                out vec4 frag;
                void main() {
                    frag=texture(u_image,uv);
                    // Pure-red atlas pixels mark prepared caption accents.
                    // Palette interpolation changes a uniform, not the bitmap.
                    if (frag.r>frag.g*3.0 && frag.r>frag.b*3.0 && max(frag.g,frag.b)<.05)
                        frag.rgb=u_accent*frag.r;
                }
                """)
            self._objects.append(self.program)
            self.vao = ctx.vertex_array(self.program, [])
            self._objects.append(self.vao)
            self.program["u_image"].value = 0
        except Exception as error:
            try:
                self.shutdown()
            except Exception as cleanup_error:
                error.add_note(str(cleanup_error))
            raise

    @property
    def allocation_bytes(self):
        return 0 if self.texture is None else self._size[0] * self._size[1] * 4

    def _font(self, size):
        size = max(10, min(64, round(size)))
        if size not in self._fonts:
            if len(self._fonts) >= 12:
                self._fonts.clear()
            self._fonts[size] = (self._ImageFont.truetype(self._font_path, size) if self._font_path else
                                 self._ImageFont.load_default(size=size))
        return self._fonts[size]

    @staticmethod
    def hit_test(x, y, width, height, scale=1.):
        return hit_test(x, y, width, height, scale)

    def resize(self, width, height):
        """Invalidate layout; allocation changes lazily on the next useful draw."""
        self._key = None

    def _raster(self, hud, width, height, focused):
        if not isinstance(hud, dict):
            raise ValueError("Le HUD attend un état structuré.")
        dpi = hud.get("dpi_scale", 1.)
        spec = layout(width, height, dpi)
        # Rasterize in physical pixels, independent of the scene/bloom render
        # scale. The old 1920px cap enlarged every glyph 2x on a 4K display.
        # Only two screen bands share the atlas, bounded to 16 MiB, not a
        # full-frame RGBA buffer and never a fresh upload on unchanged frames.
        driver_limit = int(self.ctx.info.get("GL_MAX_TEXTURE_SIZE", _MAX_ATLAS_WIDTH))
        atlas_width = min(_MAX_ATLAS_WIDTH, max(1, driver_limit), width)
        ratio = atlas_width / width
        top = max(1, round(spec["header_height"] * ratio))
        bottom = max(1, round(spec["footer_height"] * ratio))
        atlas_height = min(_MAX_ATLAS_HEIGHT, max(2, driver_limit), top + bottom)
        top = min(top, atlas_height - 1)
        bottom = atlas_height - top
        scale = spec["scale"] * ratio
        self.raster_info = {"framebuffer_size": (width, height),
                            "atlas_size": (atlas_width, atlas_height),
                            "physical_pixel_ratio": ratio,
                            "dpi_scale": spec["scale"],
                            "limited": atlas_width < width,
                            "limit_reason": ("HUD texture width bound" if atlas_width < width else None),
                            "allocation_bytes_estimate": atlas_width * atlas_height * 4}
        diagnostic = hud.get("diagnostic") is True
        strings = tuple(str(hud.get(key, ""))[:limit] for key, limit in (
            ("state", 64), ("engine", 120), ("microphone", 180), ("caption", 4096),
            ("caption_note", 160), ("operation", 200), ("preview", 160), ("shortcuts", 200),
            ("performance", 300)))
        if not diagnostic:
            strings = strings[:-1] + ("",)
        marks = tuple((mark[0], mark[1]) for mark in hud.get("caption_marks", ())[:64]
                      if isinstance(mark, (list, tuple)) and len(mark) == 2
                      and all(type(value) is int for value in mark) and 0 <= mark[0] < mark[1] <= 4096)
        accent = hud.get("caption_accent", (93, 227, 247))
        accent = tuple(accent) if isinstance(accent, (tuple, list)) else ()
        if len(accent) != 3 or not all(type(value) is int and 0 <= value <= 255 for value in accent):
            accent = (93, 227, 247)
        self._accent = tuple(value / 255 for value in accent)
        key = (atlas_width, atlas_height, top, focused, round(scale, 3), strings, marks, diagnostic)
        if key == self._key:
            return spec, top, bottom
        image = self._Image.new("RGBA", (atlas_width, atlas_height), (0, 0, 0, 0))
        draw = self._ImageDraw.Draw(image)
        pad = max(5, round(12 * scale))
        heading, body, small = self._font(17 * scale), self._font(19 * scale), self._font(12 * scale)
        cyan, white, muted = (93, 227, 247, 255), (229, 241, 250, 255), (162, 184, 203, 255)
        state, engine, microphone, caption, note, operation, preview, shortcuts, performance = strings
        title = "PRESENCE · 2.5D GPU · " + _STATES.get(state, state or "Repos")
        draw.text((pad, 4), title, font=heading, fill=cyan)
        second = "Micro : " + (microphone or "désactivé")
        if operation:
            second += " · " + operation
        detail = _lines(second, small, atlas_width - pad * 2, 1)
        if detail:
            draw.text((pad, min(top - 15, round(26 * scale))), detail[0], font=small,
                      fill=muted)
        if preview:
            notice = _lines(preview, small, atlas_width - pad * 2, 1)
            if notice:
                draw.text((pad, min(top - 11, round(42 * scale))), notice[0], font=small,
                          fill=(255, 207, 118, 255))
        elif diagnostic and performance or shortcuts:
            notice = _lines(performance if diagnostic and performance else shortcuts,
                            small, atlas_width - pad * 2, 1)
            if notice:
                draw.text((pad, min(top - 11, round(42 * scale))), notice[0], font=small, fill=muted)
        # Opaque black remains black; subtle UI bands are intentional overlays.
        draw.rectangle((0, top, atlas_width, atlas_height), fill=(0, 0, 0, 180))
        self.caption_lines = _lines(caption, body, atlas_width - pad * 2, 2)
        line_height = max(13, round(24 * scale))
        cursor = 0
        for index, line in enumerate(self.caption_lines):
            span = body.getlength(line)
            x = (atlas_width - span) / 2
            runs, cursor = caption_runs(caption, line, cursor, marks)
            for run, accented in runs:
                draw.text((x, top + index * line_height), run, font=body,
                          fill=(255, 0, 0, 255) if accented else white)
                x += body.getlength(run)
        if note and bottom > 75 * ratio:
            fitting = _lines(note, small, atlas_width - pad * 2, 1)
            if fitting:
                draw.text((pad, top + line_height * 2), fitting[0], font=small, fill=muted)
        compact = width < 540 * max(.8, spec["scale"])
        labels = ("Chat", "Studio", "Micro", "Arrêt") if compact else _LABELS
        for index, ((_action, bounds), label) in enumerate(zip(spec["buttons"], labels)):
            x0, y0, x1, y1 = bounds
            y0, y1 = top + (y0 - (height - spec["footer_height"])) * ratio, top + (y1 - (height - spec["footer_height"])) * ratio
            bounds = (round(x0 * ratio), round(y0), round(x1 * ratio), round(y1))
            selected = index == focused
            draw.rounded_rectangle(bounds, radius=max(3, round(5 * scale)),
                                   fill=(25, 53, 66, 250) if selected else (15, 26, 36, 245),
                                   outline=cyan if selected else (48, 75, 91, 255), width=1)
            font = self._font(14 * scale)
            while font.getlength(label) > bounds[2] - bounds[0] - 6 and font.size > 10:
                font = self._font(font.size - 1)
            draw.text(((bounds[0] + bounds[2] - font.getlength(label)) / 2,
                       bounds[1] + max(1, (bounds[3] - bounds[1] - font.size) / 2 - 2)),
                      label, font=font, fill=(255, 174, 174, 255) if index == 3 else white)
        if self._size != image.size:
            replacement = self.ctx.texture(image.size, 4)
            replacement.filter = (self._gl.LINEAR, self._gl.LINEAR)
            replacement.repeat_x = replacement.repeat_y = False
            previous, self.texture = self.texture, replacement
            self._size = image.size
            if previous is not None:
                previous.release()
        self.texture.write(image.tobytes())
        self.upload_count += 1
        self._key = key
        return spec, top, bottom

    def render(self, hud, width, height, focused=-1, target=None):
        if self._closed:
            raise RuntimeError("Le HUD GPU est fermé.")
        width, height = max(1, int(width)), max(1, int(height))
        destination = self.ctx.screen if target is None else target
        if destination is None:
            raise RuntimeError("Le HUD attend un framebuffer de présentation.")
        spec, top, bottom = self._raster(hud, width, height, focused)
        destination.use()
        self.ctx.disable(self._gl.DEPTH_TEST | self._gl.CULL_FACE)
        self.ctx.enable(self._gl.BLEND)
        self.ctx.blend_func = self._gl.SRC_ALPHA, self._gl.ONE_MINUS_SRC_ALPHA
        self.program["u_size"].value = (width, height)
        self.program["u_accent"].value = self._accent
        self.texture.use(location=0)
        atlas_height = top + bottom
        for screen_y, screen_height, atlas_y, atlas_part in (
                (0, spec["header_height"], 0, top),
                (height - spec["footer_height"], spec["footer_height"], top, bottom)):
            self.program["u_rect"].value = (0, screen_y, width, screen_height)
            self.program["u_tex"].value = (0, atlas_y / atlas_height, 1, atlas_part / atlas_height)
            self.vao.render(mode=self._gl.TRIANGLE_STRIP, vertices=4)
        self.ctx.disable(self._gl.BLEND)

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        failures = []
        for resource in ([self.texture] if self.texture is not None else []) + list(reversed(self._objects)):
            try:
                resource.release()
            except Exception as error:
                failures.append(f"{type(error).__name__}: {error}")
        self.texture = None
        self._objects.clear()
        self._fonts.clear()
        if failures:
            raise RuntimeError("Fermeture du HUD GPU : " + "; ".join(failures))
