"""Bounded local visual transport; importing it opens no window or GPU context.

Only presentation snapshots cross this boundary. Microphone, audio playback,
models, history and the authoritative conversation state remain in JARVIS.
"""
import json
import math


PROTOCOL_VERSION = 1
FRAME_QUEUE_SIZE = 1
EVENT_QUEUE_SIZE = 16
MAX_PACKET_BYTES = 131072
ACTIONS = ("command", "studio", "microphone", "stop", "sleep", "mini", "diagnostic",
           "engine_canvas", "engine_gpu", "toggle_engine")
_FRAME_KEYS = frozenset(("time_s", "reactor", "points", "details", "color", "rms",
                         "reduced_motion", "detail_opacity", "orbit_phase", "core_scale",
                         "audio_bands", "orbit_blend", "surface_family", "surface_amount", "art",
                         "visual_state", "visual_mix", "voice_envelopes", "receipt", "input_energy"))


def _finite(value, label):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{label} doit être un nombre fini.")
    return value


def _bounded(value, depth=0):
    if depth > 6:
        raise ValueError("Paquet PRESENCE trop profondément imbriqué.")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _finite(value, "Valeur PRESENCE")
    if isinstance(value, str):
        if len(value) > 8192:
            raise ValueError("Texte PRESENCE trop long pour le canal visuel.")
        return value
    if isinstance(value, dict):
        if len(value) > 128 or any(not isinstance(key, str) or len(key) > 80 for key in value):
            raise ValueError("Dictionnaire PRESENCE invalide ou trop grand.")
        return {key: _bounded(item, depth+1) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        if len(value) > 512:
            raise ValueError("Liste PRESENCE trop longue.")
        return tuple(_bounded(item, depth+1) for item in value)
    raise ValueError("Le canal PRESENCE n'accepte que des données visuelles simples.")


def _path(value, maximum):
    if not isinstance(value, (tuple, list)) or not 2 <= len(value) <= maximum:
        raise ValueError("Contour PRESENCE invalide.")
    result = []
    for point in value:
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            raise ValueError("Chaque point PRESENCE attend deux coordonnées.")
        result.append(tuple(_finite(item, "Coordonnée") for item in point))
    return tuple(result)


def validate_packet(packet):
    """Copy and validate a complete bounded snapshot, without GPU imports.

    ``pcm_at`` and ``expression_until`` share the host monotonic clock. They
    allow a child to clear expired audio/expression data if Tk stops sending.
    The original caption is preserved as Unicode; wrapping is presentation only.
    """
    if not isinstance(packet, dict):
        raise ValueError("Le paquet PRESENCE doit être un dictionnaire.")
    allowed = {"version", "seq", "frame", "art", "visible", "hud", "window", "pcm_at", "frame_at", "expression_until", "animation"}
    if set(packet)-allowed:
        raise ValueError("Champ de protocole PRESENCE inconnu.")
    if type(packet.get("version", PROTOCOL_VERSION)) is not int or packet.get("version", PROTOCOL_VERSION) != PROTOCOL_VERSION:
        raise ValueError("Version de protocole PRESENCE incompatible.")
    seq = packet.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq <= 2**63-1:
        raise ValueError("Séquence PRESENCE invalide.")
    if not isinstance(packet.get("visible", True), bool):
        raise ValueError("La visibilité PRESENCE doit être booléenne.")
    frame = packet.get("frame")
    if not isinstance(frame, dict) or set(frame)-_FRAME_KEYS:
        raise ValueError("Image PRESENCE invalide ou paramètres inconnus.")
    if not {"time_s", "reactor", "points"}.issubset(frame):
        raise ValueError("Image PRESENCE incomplète.")
    frame = dict(frame)
    frame["points"] = _path(frame["points"], 97)
    details = frame.get("details", ())
    if not isinstance(details, (tuple, list)) or len(details) > 8:
        raise ValueError("Trop de détails PRESENCE.")
    frame["details"] = tuple(_path(path, 25) for path in details)
    for key in ("time_s", "reactor", "rms", "detail_opacity", "core_scale", "orbit_blend", "surface_amount"):
        if key in frame:
            _finite(frame[key], key)
    for key in ("color", "orbit_phase", "audio_bands"):
        if key in frame:
            values = frame[key]
            if not isinstance(values, (tuple, list)) or len(values) != 3:
                raise ValueError(f"{key} attend trois valeurs.")
            frame[key] = tuple(_finite(value, key) for value in values)
    if "visual_state" in frame and (type(frame["visual_state"]) is not int or not 0 <= frame["visual_state"] <= 5):
        raise ValueError("État visuel PRESENCE invalide.")
    for key in ("visual_mix", "voice_envelopes"):
        if key in frame:
            values = frame[key]
            if not isinstance(values, (tuple, list)) or len(values) != 3:
                raise ValueError(f"{key} attend trois valeurs.")
            frame[key] = tuple(_finite(value, key) for value in values)
            if any(not 0 <= value <= 1 for value in frame[key]):
                raise ValueError(f"{key} dépasse les limites visuelles.")
    for key in ("receipt", "input_energy"):
        if key in frame and not 0 <= _finite(frame[key], key) <= 1:
            raise ValueError(f"{key} dépasse les limites visuelles.")
    result = {"version": PROTOCOL_VERSION, "seq": seq, "frame": frame,
              "visible": packet.get("visible", True)}
    for key in ("art", "hud", "window"):
        value = packet.get(key, {})
        if not isinstance(value, dict):
            raise ValueError(f"{key} attend un dictionnaire.")
        if key == "hud" and "cognitive" in value:
            status = value["cognitive"]
            if (not isinstance(status, str) or len(status) > 300
                    or any(ord(char) < 32 for char in status)):
                raise ValueError("Le résumé cognitif PRESENCE attend au plus 300 caractères sur une ligne.")
        result[key] = _bounded(value)
    for key in ("pcm_at", "frame_at", "expression_until"):
        if packet.get(key) is not None:
            result[key] = _finite(packet[key], key)
    animation = packet.get("animation", {})
    animation_keys = {"active", "orbit_velocity", "orbit_target", "orbit_tau", "core_target", "core_tau"}
    if not isinstance(animation, dict) or set(animation)-animation_keys:
        raise ValueError("Horloge d'animation PRESENCE invalide.")
    if not isinstance(animation.get("active", False), bool):
        raise ValueError("L'activité de l'animation doit être booléenne.")
    for key in ("orbit_velocity", "orbit_target"):
        if key in animation:
            values = animation[key]
            if (not isinstance(values, (tuple, list)) or len(values) != 3
                    or any(abs(_finite(value, key)) > 20. for value in values)):
                raise ValueError("Vitesse orbitale PRESENCE invalide.")
    for key, low, high in (("orbit_tau", .01, 5.), ("core_tau", .01, 5.), ("core_target", .2, 2.)):
        if key in animation and not low <= _finite(animation[key], key) <= high:
            raise ValueError("Transition PRESENCE hors limites.")
    if animation:
        result["animation"] = _bounded(animation)
    result["frame"] = _bounded(result["frame"])
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_PACKET_BYTES:
        raise ValueError("Le paquet visuel PRESENCE dépasse sa limite de taille.")
    return result


def _context_metadata(context):
    vendor = str(context.info.get("GL_VENDOR", ""))
    renderer = str(context.info.get("GL_RENDERER", ""))
    software = any(word in renderer.casefold() for word in
                   ("llvmpipe", "softpipe", "swrast", "swiftshader", "software", "basic render"))
    hardware = any(word in vendor.casefold() for word in ("nvidia", "intel", "amd", "ati"))
    return {"vendor": vendor, "renderer": renderer,
            "version": context.info.get("GL_VERSION"),
            "acceleration": "software" if software else "hardware_reported" if hardware else "unknown",
            "hardware_validation": "pending"}


def _send_status(events, event, *, critical=False):
    """A full heartbeat queue never blocks rendering or hides terminal status."""
    import queue
    try:
        events.put_nowait(event)
        return True
    except queue.Full:
        if not critical:
            return False
    # User commands and terminal errors displace old heartbeat/status entries.
    # This is the child, never Tk or an audio callback; the retry is bounded.
    try:
        events.get(timeout=.05)
    except queue.Empty:
        pass
    try:
        events.put(event, timeout=.1)
        return True
    except queue.Full:
        return False


def _dispatch_action(events, urgent_stop, name):
    """Only declared UI commands cross IPC; shutdown/stop retains priority."""
    if not isinstance(name, str) or name not in ACTIONS:
        raise ValueError("Commande PRESENCE GPU inconnue.")
    if name == "stop":
        urgent_stop.set()
        return True
    return _send_status(events, {"kind": "action", "action": name}, critical=True)


def _fresh_frame(packet, now):
    """Clear stale energy without cutting a fresh parent release envelope."""
    frame = dict(packet["frame"])
    frame_old = now - packet.get("frame_at", now) > .20
    pcm_old = "pcm_at" in packet and now - packet["pcm_at"] > .20
    if frame_old or pcm_old:
        frame["rms"] = 0.
    if frame_old:
        frame["audio_bands"] = (0., 0., 0.)
        for key, value in (("voice_envelopes", (0., 0., 0.)), ("input_energy", 0.), ("receipt", 0.)):
            if key in frame:
                frame[key] = value
        if not frame.get("surface_family") and frame.get("reactor", 0.) <= 0:
            frame["points"] = tuple((point[0], 0.) for point in frame["points"])
            frame["details"] = ()
    expression_old = ("expression_until" in packet and now >= packet["expression_until"])
    if expression_old:
        frame["surface_family"], frame["surface_amount"], frame["orbit_blend"] = None, 0., 0.
        frame["details"] = ()
    return frame, (frame_old, pcm_old, expression_old)


def _release_gpu_resources(items):
    """Release every owned resource and preserve deferred renderer failures."""
    failures = []
    for label, resource in items:
        if resource is None:
            continue
        try:
            if label in {"hud", "renderer"}:
                resource.shutdown()
            else:
                resource.release()
        except Exception as error:
            failures.append(f"{label}: {type(error).__name__}: {error}")
        # GpuRenderer deliberately finishes all releases before exposing a
        # bounded error journal. shutdown() need not raise for cleanup to fail.
        failures.extend(f"{label}: {error}" for error in getattr(resource, "release_errors", ()))
    return failures


def _gpu_child(frames, events, quit_event, urgent_stop, options):
    """One isolated GL context. It consumes presentation, never conversation."""
    import os
    import queue
    import time
    from collections import deque
    context = glfw = window = renderer = hud = output = None
    cleanup_errors = []
    shown = False
    current = None
    info = {}
    last_seq = -1
    stage = "imports"
    heartbeat = options["heartbeat"]
    parent = __import__("multiprocessing").parent_process()
    try:
        # This process only receives frames; close its duplicate pipe writer so
        # an abruptly terminated parent cannot leave a partial get waiting forever.
        writer = getattr(frames, "_writer", None)
        if writer is not None:
            writer.close()
        import moderngl
        from .gpu_config import GpuSettings
        from .gpu_renderer import GpuRenderer
        from .gpu_hud import GpuHud
        from .gpu_pacing import advance_frame, next_deadline, native_window_size, RenderGovernor
        from .gpu_telemetry import RenderTelemetry
        stage = "context"
        if options["headless"]:
            context = moderngl.create_standalone_context(require=330, backend="egl")
        else:
            import glfw as glfw_module
            glfw = glfw_module
            errors = deque(maxlen=8)
            glfw.set_error_callback(lambda _code, text: errors.append(text.decode(errors="replace")))
            if not glfw.init():
                raise RuntimeError("GLFW ne peut pas initialiser l'affichage : " + "; ".join(errors))
            glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
            glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
            glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
            glfw.window_hint(glfw.VISIBLE, False)
            glfw.window_hint(glfw.SCALE_TO_MONITOR, True)
            if hasattr(glfw, "SCALE_FRAMEBUFFER"):
                glfw.window_hint(glfw.SCALE_FRAMEBUFFER, True)
            window = glfw.create_window(960, 640, "PRESENCE · 2.5D holographique — GPU", None, None)
            if not window:
                raise RuntimeError("OpenGL 3.3 indisponible. Vérifiez le pilote graphique : " + "; ".join(errors))
            monitor = glfw.get_primary_monitor()
            if monitor and hasattr(glfw, "get_monitor_workarea"):
                _x, _y, available_width, available_height = glfw.get_monitor_workarea(monitor)
                actual = glfw.get_window_size(window)
                fitted = (min(actual[0], max(320, available_width-40)),
                          min(actual[1], max(240, available_height-60)))
                if fitted != tuple(actual):
                    glfw.set_window_size(window, *fitted)
            glfw.make_context_current(window)
            # Synchronize real swaps when the display driver supports it.
            glfw.swap_interval(1)
            glfw.set_window_size_limits(window, 320, 240, glfw.DONT_CARE, glfw.DONT_CARE)
            context = moderngl.create_context(require=330)
        info = _context_metadata(context)
        if not options["allow_software"] and info["acceleration"] != "hardware_reported":
            raise RuntimeError("Accélération GPU non confirmée (" + info["renderer"]
                               + "). Le rendu classique 2D reste disponible.")
        stage = "renderer"
        size = (960, 640) if window is None else glfw.get_framebuffer_size(window)
        renderer = GpuRenderer(context, *size)
        hud = GpuHud(context)
        if window is None:
            output = context.simple_framebuffer(size, components=3)
        focused = -1
        drawn = 0
        rendered_seq = -1
        dirty = False
        last_mask = None
        last_art = None
        # SCALE_TO_MONITOR may make the initial native window larger than
        # 960×640 screen units. Do not immediately undo that DPI-aware choice.
        requested_window = (960, 640)
        last_mini = False
        normal_geometry = None
        fullscreen_geometry = None
        last_heartbeat = float("-inf")
        next_frame = 0.
        animation_running = False
        telemetry = RenderTelemetry()
        governor = RenderGovernor()
        last_visual_time = None
        monitor_refresh = None
        if window is not None:
            monitor = glfw.get_primary_monitor()
            video = glfw.get_video_mode(monitor) if monitor else None
            monitor_refresh = getattr(video, "refresh_rate", None)

        def action(name):
            return _dispatch_action(events, urgent_stop, name)

        if window is not None:
            def fullscreen(enabled=None):
                nonlocal fullscreen_geometry, dirty
                enabled = fullscreen_geometry is None if enabled is None else enabled
                if enabled and fullscreen_geometry is None:
                    monitor = glfw.get_primary_monitor()
                    video = glfw.get_video_mode(monitor)
                    position = glfw.get_monitor_pos(monitor)
                    fullscreen_geometry = (*glfw.get_window_pos(window), *glfw.get_window_size(window))
                    glfw.set_window_attrib(window, glfw.DECORATED, False)
                    glfw.set_window_pos(window, *position)
                    glfw.set_window_size(window, video.size.width, video.size.height)
                elif not enabled and fullscreen_geometry is not None:
                    x, y, width, height = fullscreen_geometry
                    glfw.set_window_attrib(window, glfw.DECORATED, True)
                    glfw.set_window_pos(window, x, y)
                    glfw.set_window_size(window, width, height)
                    fullscreen_geometry = None
                dirty = True
            def on_key(_window, key, _scan, pressed, modifiers):
                nonlocal focused, dirty
                if pressed != glfw.PRESS:
                    return
                if key == glfw.KEY_TAB:
                    direction = -1 if modifiers & glfw.MOD_SHIFT else 1
                    focused = (focused + direction) % len(hud.buttons)
                    dirty = True
                elif key in {glfw.KEY_ENTER, glfw.KEY_KP_ENTER} and focused >= 0:
                    action(hud.buttons[focused])
                elif key == glfw.KEY_ESCAPE:
                    if fullscreen_geometry is not None:
                        fullscreen(False)
                    else:
                        action("command")
                elif key == glfw.KEY_F6:
                    action("studio")
                elif key == glfw.KEY_F7 and modifiers & glfw.MOD_CONTROL:
                    action("toggle_engine")
                elif key == glfw.KEY_F8:
                    action("command")
                elif key == glfw.KEY_F9:
                    action("diagnostic")
                elif key == glfw.KEY_F10:
                    action("mini")
                elif key == glfw.KEY_F11:
                    fullscreen()
                elif key == glfw.KEY_D:
                    action("sleep")
                elif key == glfw.KEY_SPACE and modifiers & glfw.MOD_CONTROL:
                    action("stop")
                elif key == glfw.KEY_M:
                    action("microphone")
                elif key == glfw.KEY_C and modifiers & glfw.MOD_CONTROL and current:
                    glfw.set_clipboard_string(window, str(current["hud"].get("caption_copy",
                                                                           current["hud"].get("caption", ""))))
            def on_click(_window, button, pressed, _modifiers):
                if button != glfw.MOUSE_BUTTON_LEFT or pressed != glfw.PRESS:
                    return
                cursor = glfw.get_cursor_pos(window)
                logical = glfw.get_window_size(window)
                physical = glfw.get_framebuffer_size(window)
                name = hud.hit_test(cursor[0]*physical[0]/max(1, logical[0]),
                                    cursor[1]*physical[1]/max(1, logical[1]), *physical,
                                    scale=max(glfw.get_window_content_scale(window)))
                if name:
                    action(name)
            def invalidate(*_arguments):
                nonlocal dirty
                dirty = True
            def close_window(_window):
                glfw.set_window_should_close(window, False)
                action("command")
            glfw.set_key_callback(window, on_key)
            glfw.set_mouse_button_callback(window, on_click)
            glfw.set_framebuffer_size_callback(window, invalidate)
            glfw.set_window_refresh_callback(window, invalidate)
            glfw.set_window_iconify_callback(window, invalidate)
            glfw.set_window_content_scale_callback(window, invalidate)
            glfw.set_window_close_callback(window, close_window)
        heartbeat.value = time.monotonic()
        _send_status(events, {"kind": "ready", "renderer": info, "size": size,
                              "pid": os.getpid()}, critical=True)
        stage = "runtime"
        while not quit_event.is_set() and (parent is None or parent.is_alive()):
            now = time.monotonic()
            heartbeat.value = now
            for _index in range(4):
                try:
                    received = frames.get_nowait()
                except queue.Empty:
                    break
                packet = validate_packet(received)
                if packet["seq"] <= last_seq:
                    continue
                last_seq, current = packet["seq"], packet
                # frame_at absent is supported for the initial contract, while
                # fresh app snapshots always supply their source timestamp.
                current.setdefault("frame_at", now)
                dirty = True
            if window is not None:
                glfw.poll_events()
            requested_visible = bool(current and current["visible"])
            if window is not None and requested_visible != shown:
                (glfw.show_window if requested_visible else glfw.hide_window)(window)
                shown = requested_visible
                dirty = True
            physical_visible = requested_visible and (window is None or
                not glfw.get_window_attrib(window, glfw.ICONIFIED)
                and glfw.get_window_attrib(window, glfw.VISIBLE))
            if now - last_heartbeat >= .5:
                measured = telemetry.snapshot(now, reset=True)
                measured.update({"adaptive_level": governor.level, "frame_time_s": last_visual_time})
                scale = tuple(glfw.get_window_content_scale(window)) if window is not None else (1., 1.)
                _send_status(events, {"kind": "heartbeat", "at": now, "rendered_seq":
                    rendered_seq, "frames": drawn, "visible": physical_visible, "size": size,
                    "logical_size": tuple(round(value/max(.1, density)) for value, density in zip(size, scale)),
                    "window_size": tuple(glfw.get_window_size(window)) if window is not None else tuple(size),
                    "dpi_scale": scale,
                    "presentation": {"monitor_refresh_hz": monitor_refresh, "vsync_requested": window is not None,
                                     "physical_scanout_observable": False},
                    "timing": measured, "process": {"pid": os.getpid(), **{key: value for key, value in measured.items()
                        if key.startswith(("cpu_", "rss_", "memory_", "physical_vram"))}},
                    "resolution": getattr(renderer, "resolution_info", {})})
                last_heartbeat = now
            if current and physical_visible:
                requested = current["window"]
                if window is not None:
                    mini = bool(requested.get("mini", False))
                    if mini != last_mini:
                        if fullscreen_geometry is not None:
                            fullscreen(False)
                        if mini:
                            normal_geometry = (*glfw.get_window_pos(window), *glfw.get_window_size(window))
                            glfw.set_window_size(window, *native_window_size((420, 300),
                                glfw.get_window_size(window), glfw.get_framebuffer_size(window),
                                glfw.get_window_content_scale(window)))
                        elif normal_geometry is not None:
                            x, y, width, height = normal_geometry
                            glfw.set_window_pos(window, x, y)
                            glfw.set_window_size(window, width, height)
                            normal_geometry = None
                        last_mini = mini
                    dimensions = (requested.get("width"), requested.get("height"))
                    if not mini and fullscreen_geometry is None and all(
                            isinstance(value, int) and not isinstance(value, bool) for value in dimensions):
                        dimensions = (max(320, min(3840, dimensions[0])), max(240, min(2160, dimensions[1])))
                        if dimensions != requested_window:
                            glfw.set_window_size(window, *native_window_size(dimensions,
                                glfw.get_window_size(window), glfw.get_framebuffer_size(window),
                                glfw.get_window_content_scale(window)))
                            requested_window = dimensions
                    new_size = glfw.get_framebuffer_size(window)
                else:
                    new_size = (max(320, min(1920, int(requested.get("width", 960)))),
                                max(240, min(1080, int(requested.get("height", 640)))))
                if min(new_size) > 0 and new_size != size:
                    size = new_size
                    renderer.resize(*size)
                    if output is not None:
                        output.release()
                        output = context.simple_framebuffer(size, components=3)
                    dirty = True
                frame, mask = _fresh_frame(current, now)
                frame, animate = advance_frame(current, frame, now)
                if mask != last_mask:
                    dirty = True
                    last_mask = mask
                if animate != animation_running:
                    dirty = True
                    animation_running = animate
                if current["art"] != last_art:
                    old_profile = last_art.get("profile", "balanced") if last_art is not None else None
                    renderer.set_settings(current["art"])
                    if old_profile != current["art"].get("profile", "balanced"):
                        governor = RenderGovernor()
                        if hasattr(renderer, "set_adaptive_level"):
                            renderer.set_adaptive_level(0)
                    last_art = dict(current["art"])
                interval = 1 / GpuSettings.from_dict(current["art"]).frames_per_second
                telemetry.target_fps = 1./interval
                if (dirty or animate) and min(size) > 0 and now >= next_frame:
                    started = time.monotonic()
                    destination = output if output is not None else context.screen
                    destination.viewport = (0, 0, *size)
                    # The packet's validated art block is the single settings
                    # source in integrated mode, even if a standalone snapshot
                    # also carries its own optional art argument.
                    frame.pop("art", None)
                    renderer.render(**frame, target=destination)
                    values = dict(current["hud"])
                    values.setdefault("shortcuts", "Tab / Entrée · Ctrl+F7 2D / 2.5D · F6 Studio · M Micro · Ctrl+Espace Arrêt · D Sommeil · F9 Mode · F10 Mini · F11 Plein écran")
                    if window is not None:
                        values["dpi_scale"] = max(glfw.get_window_content_scale(window))
                    hud.render(values, *size, focused=focused, target=destination)
                    if window is not None:
                        glfw.set_window_title(window, "PRESENCE · 2.5D GPU · " + str(values.get("state", ""))[:80])
                        glfw.swap_buffers(window)
                    else:
                        context.finish()
                    completed = time.monotonic()
                    telemetry.record(completed-started, started, presented=window is not None, animated=animate)
                    last_visual_time = frame["time_s"]
                    if animate:
                        nominal = 1./interval
                        target = min(nominal, monitor_refresh) if monitor_refresh and monitor_refresh > 0 else nominal
                        level = governor.observe(completed-started, completed, target)
                        if hasattr(renderer, "set_adaptive_level"):
                            renderer.set_adaptive_level(level)
                    else:
                        governor.suspend()
                    drawn += 1
                    rendered_seq = current["seq"]
                    dirty = False
                    # Advance from draw START, not after a blocking VSync swap:
                    # adding another frame interval after swap would halve FPS.
                    next_frame = next_deadline(next_frame if next_frame else started, started, interval)
            else:
                animation_running = False
                governor.suspend()
                telemetry.pause()
            # An incoming IPC frame does not wake GLFW, hence bounded idle
            # polling. Animated scenes wait to their absolute next deadline.
            pause = min(.05, max(0., next_frame-time.monotonic())) if (dirty or animation_running) and physical_visible else .05
            if window is not None and pause > 0:
                glfw.wait_events_timeout(pause)
            elif window is None:
                quit_event.wait(pause)
    except Exception as error:
        _send_status(events, {"kind": "error", "message":
            f"PRESENCE GPU indisponible : {type(error).__name__}: {error}",
            "stage": stage, "renderer": info}, critical=True)
    finally:
        cleanup_errors.extend(_release_gpu_resources((("hud", hud), ("renderer", renderer),
                                                     ("framebuffer", output), ("context", context))))
        if glfw is not None:
            try:
                if window is not None:
                    glfw.destroy_window(window)
                glfw.terminate()
            except Exception as error:
                cleanup_errors.append(f"GLFW: {type(error).__name__}: {error}")
        if cleanup_errors:
            _send_status(events, {"kind": "error", "message": "Fermeture GPU : " + "; ".join(cleanup_errors)}, critical=True)
        _send_status(events, {"kind": "closed", "cleanup_errors": cleanup_errors}, critical=True)


class GpuSession:
    """One spawned renderer, one latest snapshot and bounded status messages.

    Public methods belong to JARVIS's UI thread. ``submit`` never waits for the
    driver or a queue feeder. A local latest item is retried by ``poll`` so a
    terminal state cannot be lost in multiprocessing.Queue's feeder race.
    """
    def __init__(self, *, context=None, target=None, allow_software=False, headless=False,
                 startup_timeout=6., heartbeat_timeout=2., clock=None):
        import time
        if not math.isfinite(startup_timeout) or not 0 < startup_timeout <= 30:
            raise ValueError("Délai d'initialisation GPU invalide.")
        if not math.isfinite(heartbeat_timeout) or not 0 < heartbeat_timeout <= 10:
            raise ValueError("Délai de surveillance GPU invalide.")
        self._context, self._target = context, target or _gpu_child
        self._allow_software, self._headless = bool(allow_software), bool(headless)
        self._startup_timeout, self._heartbeat_timeout = startup_timeout, heartbeat_timeout
        self._clock = clock or time.monotonic
        self._process = self._frames = self._events = self._quit = self._urgent = self._heartbeat = None
        self._pending = None
        self._seq = -1
        self._started_at = self._last_seen = 0.
        self._ready = self._failure_reported = self._seen_closed = False
        self._terminal_events = []
        self._shutdown_report = None
        self._frame_errors = []

    def alive(self):
        return bool(self._process is not None and self._process.is_alive())

    @property
    def ready(self):
        return self._ready

    @property
    def shutdown_report(self):
        """Last bounded closure evidence, separate from process liveness."""
        if self._shutdown_report is None:
            return None
        return {**self._shutdown_report,
                "cleanup_errors": list(self._shutdown_report["cleanup_errors"]),
                "errors": [{**event, "renderer": dict(event["renderer"])}
                           for event in self._shutdown_report["errors"]]}

    def _remember_terminal(self, event):
        if not isinstance(event, dict) or event.get("kind") not in ("error", "closed"):
            return
        if event["kind"] == "closed":
            errors = event.get("cleanup_errors", ())
            errors = errors if isinstance(errors, (tuple, list)) else ("Invalid cleanup diagnostic",)
            value = {"kind": "closed", "cleanup_errors": [str(error)[:512] for error in errors[:16]]}
        else:
            renderer = event.get("renderer", {})
            acceleration = renderer.get("acceleration", "") if isinstance(renderer, dict) else ""
            value = {"kind": "error", "message": str(event.get("message", "Unknown GPU error"))[:512],
                     "stage": str(event.get("stage", ""))[:80],
                     "renderer": {"acceleration": str(acceleration)[:32]}}
        self._terminal_events.append(value)
        del self._terminal_events[:-16]

    def _drain_shutdown_events(self):
        # No callbacks/actions during closure and no wait on the feeder: the
        # completed child's joined feeder makes its final records readable.
        if self._events is None:
            return
        import queue
        for _index in range(EVENT_QUEUE_SIZE):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._remember_terminal(event)

    def _closure_report(self, forced, termination_failed=False):
        closed = [event for event in self._terminal_events if event["kind"] == "closed"]
        cleanup = [error for event in closed for error in event["cleanup_errors"]][-16:]
        errors = [dict(event) for event in self._terminal_events if event["kind"] == "error"]
        if not cleanup:
            cleanup = [event["message"] for event in errors if event["message"].startswith("Fermeture GPU :")]
        status = ("termination_failed" if termination_failed else "cleanup_failed" if cleanup else
                  "forced" if forced else "complete" if closed else "unconfirmed")
        self._shutdown_report = {"status": status, "acknowledged": bool(closed),
                                 "forced": forced, "cleanup_errors": cleanup, "errors": errors}
        return self.shutdown_report

    def start(self, packet=None):
        if self.alive():
            return False
        if self._process is not None:
            self.stop()
        import multiprocessing as mp
        context = self._context or mp.get_context("spawn")
        self._frames = context.Queue(maxsize=FRAME_QUEUE_SIZE)
        self._events = context.Queue(maxsize=EVENT_QUEUE_SIZE)
        self._quit, self._urgent = context.Event(), context.Event()
        # An intentionally abandoned large packet must not strand its feeder
        # or print a broken-pipe traceback during shutdown. Unexpected runtime
        # transport errors remain observable by the existing parent poll.
        stop_flag, frame_errors = self._quit, []
        self._frame_errors = frame_errors
        def frame_error(error, _packet):
            if not stop_flag.is_set() and not frame_errors:
                frame_errors.append(f"Canal visuel GPU : {type(error).__name__}: {error}"[:512])
        self._frames._on_queue_feeder_error = frame_error
        self._heartbeat = context.Value("d", 0., lock=False)
        options = {"allow_software": self._allow_software, "headless": self._headless,
                   "heartbeat": self._heartbeat}
        self._process = context.Process(target=self._target,
            args=(self._frames, self._events, self._quit, self._urgent, options),
            name="jarvis-presence-gpu", daemon=True)
        self._pending = None
        self._seq = -1
        self._ready = self._failure_reported = self._seen_closed = False
        self._terminal_events = []
        self._shutdown_report = None
        self._started_at = self._last_seen = self._clock()
        try:
            self._process.start()
            if packet is not None:
                self.submit(packet)
        except BaseException:
            self.stop()
            raise
        return True

    def _flush(self):
        if self._pending is None or self._frames is None:
            return
        import queue
        try:
            self._frames.put_nowait(self._pending)
        except queue.Full:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                return
            try:
                self._frames.put_nowait(self._pending)
            except queue.Full:
                return
        self._pending = None

    def submit(self, packet):
        value = validate_packet(packet)
        if self._process is None or self._seen_closed or value["seq"] <= self._seq:
            return False
        self._seq, self._pending = value["seq"], value
        self._flush()
        return True

    def poll(self):
        if self._process is None:
            return []
        import queue
        self._flush()
        now = self._clock()
        result = []
        if self._urgent.is_set():
            self._urgent.clear()
            result.append({"kind": "action", "action": "stop"})
        for _index in range(EVENT_QUEUE_SIZE):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if not isinstance(event, dict):
                event = {"kind": "error", "message": "Réponse GPU invalide."}
            if event.get("kind") == "action" and (not isinstance(event.get("action"), str)
                                                   or event["action"] not in ACTIONS):
                event = {"kind": "error", "message": "Commande PRESENCE GPU inconnue."}
            kind = event.get("kind")
            if kind == "ready":
                self._ready = True
                self._last_seen = now
            elif kind == "heartbeat":
                self._last_seen = now
            elif kind == "closed":
                self._seen_closed = True
            if kind == "error":
                self._failure_reported = True
            self._remember_terminal(event)
            result.append(event)
        last_beat = max(self._last_seen, self._heartbeat.value)
        error = None
        if self._frame_errors:
            error = self._frame_errors[0]
        elif not self.alive() and not self._seen_closed:
            error = "Le processus PRESENCE GPU s'est arrêté (code " + str(self._process.exitcode) + ")."
        elif not self._ready and now-self._started_at > self._startup_timeout:
            error = "Le moteur PRESENCE GPU ne répond pas pendant son initialisation."
        elif self._ready and now-last_beat > self._heartbeat_timeout:
            error = "Le moteur PRESENCE GPU ne répond plus."
        if error and not self._failure_reported:
            self._failure_reported = True
            event = {"kind": "error", "message": error}
            self._remember_terminal(event)
            result.append(event)
        self._flush()
        return result

    def stop(self, timeout=.6):
        """Bounded stop returning actual cleanup evidence, not just exit status.

        A forced exit releases OS resources but does not prove renderer cleanup.
        Failed termination retains all handles so an explicit retry is possible.
        """
        if not math.isfinite(timeout) or not 0 < timeout <= 5:
            raise ValueError("Délai de fermeture GPU invalide.")
        import time
        deadline = time.monotonic()+timeout
        process = self._process
        if process is None and self._shutdown_report is not None:
            return self.shutdown_report
        forced = False
        if process is not None:
            if self._quit is not None:
                self._quit.set()
            self._drain_shutdown_events()
            try:
                process.join(timeout*.5)
                self._drain_shutdown_events()
                if process.is_alive():
                    forced = True
                    process.terminate()
                    process.join(timeout*.4)
                    self._drain_shutdown_events()
                if process.is_alive() and hasattr(process, "kill"):
                    process.kill()
                    process.join(timeout*.1)
                    self._drain_shutdown_events()
                if process.is_alive():
                    self._closure_report(forced, termination_failed=True)
                    raise RuntimeError("Le processus GPU n'a pas pu être fermé ; aucun second moteur n'a été ouvert.")
            except AssertionError:
                # Process.start itself failed: it has no child to join.
                pass
            self._drain_shutdown_events()
            process.close()
        for channel in (self._frames, self._events):
            if channel is not None:
                channel.cancel_join_thread()
                channel.close()
                # Queue.close only enqueues a sentinel. A feeder writing a
                # packet larger than the OS pipe can never reach that sentinel
                # if the child has exited and this parent keeps its reader open.
                # The child is confirmed dead here; abandon only visual data.
                reader = getattr(channel, "_reader", None)
                if reader is not None:
                    reader.close()
                feeder = getattr(channel, "_thread", None)
                if feeder is not None:
                    feeder.join(max(0., deadline-time.monotonic()))
                writer = getattr(channel, "_writer", None)
                if writer is not None:
                    writer.close()
                if feeder is not None and feeder.is_alive():
                    self._remember_terminal({"kind": "error", "message":
                        "Fermeture GPU : le fil du canal visuel n'a pas terminé dans le délai borné."})
        result = self._closure_report(forced)
        self._process = self._frames = self._events = self._quit = self._urgent = self._heartbeat = None
        self._pending = None
        self._ready = False
        return result
