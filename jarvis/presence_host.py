"""One conversation model, two permanent visual engines, isolated GPU failures."""
from dataclasses import asdict
import json
import math
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .gpu_config import GpuSettings
from .presence import PresenceView
from .presence_engine import ENGINE_LABELS, EnginePreferences


class IntegratedPresence(PresenceView):
    def __init__(self, app):
        self.active_engine = "canvas"
        self._gpu = self._gpu_scene = None
        self._gpu_poll_id = None
        self._gpu_ready = self._gpu_desired = self._gpu_visible = False
        self._gpu_size = (960, 640)
        self._gpu_seq = 0
        self._gpu_bands = (0., 0., 0.)
        self.gpu_diagnostics = {}
        self._ignore_unmap = False
        self._preview_restore = None
        self._preview_art = None
        self._pending_gpu_preview = None
        self._canvas_preview_restore = None
        self.gpu_studio = None
        self._engine_dialog = None
        self._closing_host = False
        self._engine_bar = None
        super().__init__(app)
        self._saved_engine = self._read("presence_engine")
        self.engine_preferences = EnginePreferences.from_dict(self._saved_engine)
        self._saved_gpu = self._read("presence_gpu")
        self.gpu_settings = GpuSettings.from_dict(self._saved_gpu)
        self.engine_status = tk.StringVar(app.root)
        self.engine_choice = tk.StringVar(app.root, value="canvas")
        self._status()

    def _read(self, key):
        try:
            value = self.app.store.get_preference(key, {})
        except Exception:
            value = {}
        return dict(value) if isinstance(value, dict) else {}

    @property
    def _keep_speech_expression(self):
        return self.active_engine == "gpu"

    def _status(self, detail=""):
        active = ENGINE_LABELS[self.active_engine]
        reason = detail or self.engine_preferences.reason
        self.engine_status.set("Actif : " + active + (" · " + reason if reason else ""))
        self.engine_choice.set(self.active_engine)

    def toggle_engine(self, _event=None):
        self.set_engine("canvas" if self.active_engine == "gpu" else "gpu")
        return "break"

    def _show_canvas(self):
        super().show()
        if self._engine_bar is None or not self._engine_bar.winfo_exists():
            self._engine_bar = tk.Frame(self.window, bg="#000000")
            style = ttk.Style(self.window)
            style.configure("PresenceEngine.Toolbutton", padding=(8, 3),
                font=(self.app.font_family, 9), background="#11202b", foreground="#caedff")
            style.map("PresenceEngine.Toolbutton", background=[("selected", "#174456")],
                      foreground=[("selected", "#ffffff")])
            self.engine_buttons = {}
            for mode, label in (("canvas", "2D"), ("gpu", "2.5D")):
                button = ttk.Radiobutton(self._engine_bar, text=label, value=mode,
                    variable=self.engine_choice, style="PresenceEngine.Toolbutton",
                    command=lambda chosen=mode: self.set_engine(chosen), takefocus=True)
                button.pack(side="left", padx=1)
                self.engine_buttons[mode] = button
            self.window.bind("<Control-F7>", self.toggle_engine)
        self._layout_controls(self.canvas.winfo_width(), self.canvas.winfo_height())

    def _layout_controls(self, width, height):
        super()._layout_controls(width, height)
        if self._engine_bar is None or not self._engine_bar.winfo_exists():
            return
        self._engine_bar.place(x=12, y=8, anchor="nw")
        self._engine_bar.lift()
        bar_width = self._engine_bar.winfo_reqwidth()
        if self.settings.mini_mode:
            self.state_label.place(x=12+bar_width+12, y=12, relx=0, rely=0)
        elif width > bar_width+self.identity.winfo_reqwidth()+self.header_controls.winfo_reqwidth()+64:
            self.identity.place(x=bar_width+24, y=8, relx=0, rely=0)
        else:
            self.identity.place_forget()

    def _save_engine(self, candidate):
        values = {**self._saved_engine, **candidate.to_dict()}
        try:
            self.app.store.set_preference("presence_engine", values)
        except Exception:
            self.app.set_status("Choix PRESENCE non enregistré : vérifiez les droits et l'espace disque.", True)
            return False
        self._saved_engine, self.engine_preferences = values, candidate
        return True

    def set_engine(self, mode):
        candidate = self.engine_preferences.choose(mode)
        if not self._save_engine(candidate):
            return False
        self.end_gpu_preview(restore=False)
        self._canvas_preview_restore = None
        if self.studio is not None:
            self.studio.cancel()
        self.show()
        return True

    def retry_gpu(self):
        candidate = self.engine_preferences.retry()
        if candidate.mode == "canvas":
            candidate = candidate.choose("gpu")
        if self._save_engine(candidate):
            self.show()

    def show(self):
        self._closing_host = False
        if self._canvas_preview_restore is not None:
            self._canvas(show=True)
            return
        if self._preview_restore is not None or self.engine_preferences.target == "gpu":
            # The hidden native caption/control widgets are also used by the
            # existing rehearsal/accessibility code. They never draw alongside
            # a visible GPU window; Canvas supplies the safe loading view.
            if self.window is None or not self.window.winfo_exists():
                self._show_canvas()
            self._gpu_desired = True
            if self._gpu is None:
                from .gpu_session import GpuSession
                factory = getattr(self, "session_factory", GpuSession)
                self._gpu = factory()
                try:
                    self._gpu.start()
                except Exception as error:
                    self._gpu_failed(f"Initialisation GPU : {type(error).__name__}: {error}")
                    return
                self._status("Initialisation GPU ; le moteur 2D reste disponible")
                self._poll_gpu()
            elif self._gpu_ready:
                self.active_engine = "gpu"
                self._hide_canvas()
                self._gpu_visible = True
                self._request_spectrum(True)
                self._render()
            return
        self._canvas(show=True)

    def _hide_canvas(self):
        self._cancel_animation()
        if self.window is not None and self.window.winfo_exists() and self.window.winfo_ismapped():
            self._ignore_unmap = True
            self.window.withdraw()

    def _stop_gpu(self):
        if self._gpu_poll_id is not None:
            self.app.root.after_cancel(self._gpu_poll_id)
            self._gpu_poll_id = None
        session, self._gpu = self._gpu, None
        self._gpu_ready = self._gpu_visible = False
        if session is not None:
            session.stop()
        self._request_spectrum(False)

    def _canvas(self, *, show):
        self._cancel_animation()
        self._stop_gpu()
        self.active_engine = "canvas"
        self._gpu_desired = False
        self._status()
        if show:
            self._show_canvas()
        else:
            self._hide_canvas()

    def _request_spectrum(self, enabled):
        setter = getattr(self.app.voice, "set_visual_spectrum", None)
        if callable(setter):
            setter(enabled)

    def gpu_runtime_summary(self):
        """Measured renderer diagnostics, never monitor Hz presented as FPS."""
        timing = self.gpu_diagnostics.get("timing", {})
        resolution = self.gpu_diagnostics.get("resolution", {})
        fps = timing.get("actual_draw_fps")
        parts = [f"{fps:.1f} FPS dessinés" if isinstance(fps, (int, float)) else "FPS non mesurés"]
        size = resolution.get("render_size", resolution.get("internal_size", resolution.get("main_size")))
        if isinstance(size, (list, tuple)) and len(size) == 2:
            parts.append(f"rendu {size[0]} × {size[1]} px")
        physical = self.gpu_diagnostics.get("size")
        if isinstance(physical, (list, tuple)) and len(physical) == 2:
            parts.append(f"écran {physical[0]} × {physical[1]} px")
        return " · ".join(parts)

    def semantic_diagnostics(self):
        # Reuse the existing copyable diagnostic surface. Sampling lives in
        # the child; opening/copying this text performs no benchmark or I/O.
        result = super().semantic_diagnostics()
        if self.gpu_diagnostics:
            result += "\nPRESENCE GPU · mesures du processus (pas de validation RTX)\n"
            result += json.dumps(self.gpu_diagnostics, ensure_ascii=False, indent=2)
        return result

    def _gpu_failed(self, reason):
        reason = str(reason)[:512]
        visible = self._preview_restore[1] if self._preview_restore is not None else self._gpu_desired
        preview = self._preview_restore is not None
        self._preview_restore = self._preview_art = None
        self._pending_gpu_preview = None
        if not preview:
            failed = self.engine_preferences.failed(reason)
            self._save_engine(failed)
            # A full/read-only database must never turn a GPU failure into an
            # automatic restart loop. Persistence can fail; the live latch cannot.
            self.engine_preferences = failed
        self.clear_preview()
        self._canvas(show=visible)
        self._status("GPU indisponible : " + reason + " · Réessayer manuellement")
        self.app.set_status("PRESENCE utilise Canvas : " + reason, True)
        if self.gpu_studio is not None:
            self.gpu_studio.previewing = False
            self.gpu_studio.status.set("Aperçu GPU indisponible : " + reason)

    def _poll_gpu(self):
        self._gpu_poll_id = None
        session = self._gpu
        if session is None or self._closing_host:
            return
        try:
            events = session.poll()
            for event in events:
                kind = event.get("kind")
                if kind == "error":
                    self._gpu_failed(event.get("message", event.get("error", "Le renderer ne répond plus.")))
                    return
                if kind == "ready":
                    self._gpu_ready = True
                    self._gpu_visible = self._gpu_desired
                    self.active_engine = "gpu"
                    self._hide_canvas()
                    if self._preview_restore is None:
                        self._save_engine(self.engine_preferences.ready())
                    self._status("Aperçu non enregistré" if self._preview_restore is not None else "")
                    self._request_spectrum(self._gpu_desired)
                    self._render()
                    pending, self._pending_gpu_preview = self._pending_gpu_preview, None
                    if pending is not None and self._preview_restore is not None:
                        self.preview_gpu_state(pending)
                elif kind == "heartbeat":
                    before = self._gpu_visible
                    self._gpu_visible = bool(event.get("visible", self._gpu_visible))
                    self._request_spectrum(self._gpu_desired and self._gpu_visible)
                    size = event.get("size")
                    if isinstance(size, (tuple, list)) and len(size) == 2 and min(size) > 0:
                        self._gpu_size = tuple(size)
                    self.gpu_diagnostics = {key: event[key] for key in (
                        "timing", "process", "resolution", "presentation", "size", "logical_size", "dpi_scale")
                        if key in event}
                    if self._gpu_visible and not before:
                        self._render()
                elif kind == "action":
                    self._gpu_action(event.get("action"))
                elif kind == "closed":
                    self.return_to_command()
                    self._stop_gpu()
                    self.active_engine = "canvas"
                    self._status()
                    return
            if self._gpu is session:
                self._gpu_poll_id = self.app.root.after(50, self._poll_gpu)
        except Exception as error:
            self._gpu_failed(f"Canal GPU : {type(error).__name__}: {error}")

    def _gpu_action(self, action):
        actions = {"command": self.return_to_command, "studio": self.open_gpu_settings,
                   "microphone": self.toggle_listening, "stop": self.emergency,
                   "sleep": self.toggle_sleep, "mini": self.toggle_mini,
                   "diagnostic": self.toggle_diagnostic}
        actions.update(engine_canvas=lambda: self.set_engine("canvas"),
                       engine_gpu=lambda: self.set_engine("gpu"), toggle_engine=self.toggle_engine)
        if action in actions:
            actions[action]()

    def _visible(self):
        if self.active_engine == "gpu":
            return bool(self._gpu is not None and self._gpu_ready and self._gpu_desired and self._gpu_visible)
        return super()._visible()

    def _layout_caption(self):
        if self.active_engine != "gpu":
            return super()._layout_caption()
        if self._caption_plan is not None:
            self._caption_window = self._caption_plan.window(self._segment_fraction)
            self.caption_text = self._caption_window.text

    def _trigger_morph(self, family, now):
        if self.active_engine != "gpu":
            return super()._trigger_morph(family, now)
        width, height = self._gpu_size
        return self.semantic.trigger(family, now, intensity=self.settings.morph_intensity,
            reduced_motion=self.settings.reduced_motion or not self.settings.animations,
            origin=self.model.frame(width, height, now), viewport=(width, height))

    def _advance_expressions(self, key, fraction, signal):
        if self.active_engine == "gpu":
            if any((cue.response_id, cue.segment_id) == key and not cue.terminal
                   and cue.fraction <= fraction for cue in self._semantic_cues):
                self._start_expression(key, fraction=fraction)
        else:
            super()._advance_expressions(key, fraction, signal)

    def _trace_semantic(self, stage, reason, key=None, family=None):
        if self.active_engine == "gpu" and reason == "quiet_pcm":
            reason = "pcm_fraction_estimate"
        return super()._trace_semantic(stage, reason, key, family)

    def update_event(self, state, signal=None, caption=None):
        synthetic = self._demo is not None and self._demo.dispatching
        if self.gpu_studio is not None and not synthetic:
            self.gpu_studio.suspend_preview()
        bands = (signal or {}).get("bands", (0., 0., 0.)) if isinstance(signal, dict) else (0., 0., 0.)
        self._gpu_bands = tuple(max(0., min(1., float(x))) for x in bands) if (
            isinstance(bands, (tuple, list)) and len(bands) == 3
            and all(isinstance(x, (int, float)) and math.isfinite(x) for x in bands)) else (0., 0., 0.)
        if state in {"user_speaking", "dormant"} and self._gpu_scene is not None:
            self._gpu_bands = (0., 0., 0.)
            self._gpu_scene.clear_output_energy()
        super().update_event(state, signal, caption)
        if self.active_engine == "gpu" and not self._visible() and self._gpu_ready:
            self._render()

    def begin_response(self):
        self._gpu_bands = (0., 0., 0.)
        if self._gpu_scene is not None:
            self._gpu_scene.clear_output_energy()
        super().begin_response()

    def update_operation(self, key, detail=""):
        if key == "error":
            self._gpu_bands = (0., 0., 0.)
            if self._gpu_scene is not None:
                self._gpu_scene.clear_output_energy()
        super().update_operation(key, detail)

    def _render(self):
        if self.active_engine != "gpu":
            return super()._render()
        self._cancel_animation()
        if not self._gpu_ready or self._gpu is None:
            return
        try:
            self._render_gpu()
        except Exception as error:
            self._gpu_failed(f"Rendu GPU : {type(error).__name__}: {error}")

    def _render_gpu(self):
        from .presence_gpu import ReactorScene
        now = time.monotonic()
        if self._gpu_scene is None:
            self._gpu_scene = ReactorScene()
            self._gpu_scene.model, self._gpu_scene.semantic = self.model, self.semantic
        scene = self._gpu_scene
        art = self._preview_art or self.gpu_settings
        scene.set_settings(art)
        scene.reactor = 0. if self.state == "dormant" else 1.
        scene._raw_bands = self._gpu_bands
        color = self.mesh_accent(now)
        scene.color = tuple(int(color[index:index+2], 16)/255 for index in (1, 3, 5))
        was_semantic = self.semantic.active
        frame = scene.snapshot(*self._gpu_size, now=now)
        if was_semantic and not self.semantic.active:
            self._semantic_preview, self._preview_text = False, None
        self._layout_caption()
        self._gpu_seq += 1
        marks = [(mark.start, mark.end) for mark in self._caption_window.marks
                 if self.settings.emotional_subtitles and self.settings.accent_mode != "none"
                 and self.settings.spectrum_mode != "neutral" and mark.tone in {self.tone.name, self.dominant_tone.name}]
        until = (self.semantic._started + (art.expression_hold_ms +
                 (0 if self.settings.reduced_motion else 2*art.expression_transition_ms))/1000
                 if self.semantic.active else now)
        self._gpu.submit({"seq": self._gpu_seq, "frame": frame, "art": art.to_dict(),
            "visible": self._gpu_desired, "pcm_at": self.model.signal_at, "frame_at": now,
            "animation": {"active": bool(scene.moving(now) and self.model.motion_allowed),
                "orbit_velocity": tuple(scene.orbit_velocity), "orbit_target": scene._orbit_targets(),
                "orbit_tau": (.18/(art.expression_ring_speed/100) if self.semantic.active else
                              art.ring_acceleration_ms/1000),
                "core_target": 1.-art.thinking_contraction/100 if self.state == "thinking" else 1.,
                "core_tau": art.transition_ms/1000},
            "expression_until": until, "window": {"width": 960, "height": 640, "mini": self.settings.mini_mode},
            "hud": {"state": self.state, "microphone": self.microphone_state,
                "caption": self.caption_text if self.settings.subtitles else "",
                "caption_copy": self.caption_text, "caption_marks": marks,
                "caption_accent": tuple(round(channel*255) for channel in scene.color),
                "caption_note": "Synchronisation approximative par bloc PCM Piper",
                "operation": self.operation_detail, "diagnostic": self.settings.diagnostic_mode,
                "performance": self.gpu_runtime_summary(),
                "preview": self._preview_text or "", "engine": ENGINE_LABELS["gpu"]}})
        self._update_engine_text()
        if self._visible() and (scene.moving(now) or self._accent.active(now)):
            # Actual drawing is paced in the isolated GPU process. Tk sends
            # bounded state/audio anchors, not one IPC packet per display frame.
            self.after_id = self.app.root.after(round(1000/min(25, art.frames_per_second)), self._tick)

    def _update_engine_text(self):
        if self.active_engine == "canvas" and self.window is not None:
            self.window.title("JARVIS · PRESENCE · 2D classique — Canvas")

    def _on_unmap(self, event):
        if event.widget is self.window and self._ignore_unmap:
            self._ignore_unmap = False
            return
        super()._on_unmap(event)

    def _apply_window_mode(self):
        if self.active_engine != "gpu":
            return super()._apply_window_mode()

    def return_to_command(self):
        if self.active_engine != "gpu" and self._gpu is None:
            return super().return_to_command()
        self._gpu_desired = False
        self._request_spectrum(False)
        self._hide_canvas()
        self._cancel_semantics("return_to_command")
        self.clear_preview()
        self._cancel_animation()
        if self._gpu is not None and self._gpu_ready:
            self._render()
        self.app.root.deiconify()
        self.app.root.lift()

    def set_gpu_options(self, **changes):
        baseline = self.gpu_studio.baseline if self.gpu_studio is not None else self.gpu_settings
        candidate = GpuSettings.from_dict({**baseline.to_dict(), **changes})
        values = {**self._saved_gpu, **candidate.to_dict()}
        try:
            self.app.store.set_preference("presence_gpu", values)
        except Exception:
            self.app.set_status("Réglages GPU non enregistrés : vérifiez les droits et l'espace disque.", True)
            return False
        self._saved_gpu, self.gpu_settings = values, candidate
        if self.gpu_studio is not None:
            self.gpu_studio.rebase(candidate, set(changes))
        if self._preview_restore is None:
            self._preview_art = None
        self._render()
        return True

    def preview_gpu_options(self, candidate):
        if self.app.voice.listening or self.app.operation or self.state not in {"silent", "dormant"} and self._preview_restore is None:
            self.app.set_status("Aperçu GPU indisponible pendant l'écoute ou une réponse réelle.")
            return False
        if self._preview_restore is None:
            self._preview_restore = (self.active_engine, self._visible())
        self._preview_art = GpuSettings.from_dict(candidate.to_dict())
        self.show()
        return self._gpu is not None

    def end_gpu_preview(self, *, restore=True):
        self._pending_gpu_preview = None
        if self._preview_restore is not None:
            self.clear_preview()
        previous, self._preview_restore = self._preview_restore, None
        self._preview_art = None
        if previous is None or not restore:
            return
        if previous[0] == "canvas":
            self._canvas(show=previous[1])
        else:
            self._gpu_desired = previous[1]
            self._render()

    def preview_gpu_state(self, label):
        # The existing rehearsal owns cancellation; it is never actual telemetry.
        if not self._gpu_ready or not self._visible():
            if self._preview_restore is not None and self._gpu is not None:
                self._pending_gpu_preview = label
                self.app.set_status("Initialisation de l'aperçu GPU hors ligne…")
                return True
            self.app.set_status("Attendez l'initialisation du GPU avant cet aperçu.")
            return False
        from .presence_demo import DemoController
        mapping = {"Repos": 0, "Écoute": 1, "THINKING": 2, "Parole": 3, "Interruption": 6}
        if self._demo is not None and self._demo.active:
            self._demo.cancel("replaced")
        if label in {"Sourire 😊", "Rire 😂", "Cœur ❤️"}:
            family = {"Sourire 😊": "smile", "Rire 😂": "laughter", "Cœur ❤️": "affection"}[label]
            self._semantic_preview = True
            self._preview_text = "APERÇU HORS LIGNE · expression"
            self._trigger_morph(family, time.monotonic())
            self._render()
            return True
        if label not in mapping:
            return False
        if self._demo is None:
            self._demo = DemoController(self)
        return self._demo.start(stage=mapping[label])

    def open_gpu_settings(self):
        if self.studio is not None:
            self.studio.cancel()
        if self.gpu_studio is None or self.gpu_studio.closed:
            from .gpu_studio import GpuStudio
            self.gpu_studio = GpuStudio(self)
        self.gpu_studio.window.deiconify()
        self.gpu_studio.window.lift()
        return self.gpu_studio.window

    def open_canvas_settings(self):
        if self.gpu_studio is not None:
            self.gpu_studio.cancel()
            self.gpu_studio = None
        if self.active_engine == "gpu" and self._canvas_preview_restore is None:
            self._canvas_preview_restore = ("gpu", self._visible())
            self._canvas(show=self._canvas_preview_restore[1])
            self._status("Configuration 2D temporaire ; préférence GPU conservée")
        dialog = super().open_settings()
        def restore(event):
            if event.widget is dialog and self._canvas_preview_restore is not None:
                previous, self._canvas_preview_restore = self._canvas_preview_restore, None
                if not self._closing_host and previous[1]:
                    self.show()
        dialog.bind("<Destroy>", restore, add="+")
        return dialog

    def open_settings(self):
        return self.open_gpu_settings() if self.active_engine == "gpu" else self.open_canvas_settings()

    def open_engine_settings(self):
        if self._engine_dialog is not None and self._engine_dialog.winfo_exists():
            self._engine_dialog.sync_preferences()
            self._engine_dialog.deiconify()
            self._engine_dialog.lift()
            return self._engine_dialog
        window = self._engine_dialog = tk.Toplevel(self.app.root)
        window.title("PRESENCE · moteurs 2D / 2.5D")
        window.geometry("540x440")
        window.minsize(320, 260)
        window.configure(bg="#121c29", padx=10, pady=10)
        if self.app.root.winfo_viewable():
            window.transient(self.app.root)
        # Reserve the close action before the scrollable content, even with
        # large Windows fonts/DPI or a short landscape window.
        footer = ttk.Frame(window)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        window.close_button = ttk.Button(footer, text="Fermer", command=window.destroy)
        window.close_button.pack(fill="x")
        frame = ttk.Frame(window)
        frame.pack(fill="both", expand=True)
        canvas = window.scroll_canvas = tk.Canvas(frame, bg="#121c29", highlightthickness=0,
                                                   width=1, height=1, takefocus=False)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = window.content = ttk.Frame(canvas, padding=(2, 0, 8, 8))
        content_item = canvas.create_window(0, 0, anchor="nw", window=body)
        labels = []

        def label(text=None, **options):
            item = ttk.Label(body, text=text, wraplength=300, justify="left", **options)
            item.pack(fill="x", pady=(0, 8))
            labels.append(item)
            return item

        label("Deux identités, votre choix", font=(self.app.font_family, 14, "bold"))
        label(textvariable=self.engine_status)
        label("Choix conservé entre les sessions. Canvas 2D reste une expérience complète ; "
              "une panne GPU conserve ce choix et permet un nouvel essai manuel.")
        label("Moteur préféré")
        choice = window.engine_choice = tk.StringVar(window, value=ENGINE_LABELS[self.engine_preferences.mode])
        widget = window.engine_combo = ttk.Combobox(body, state="readonly", width=1,
            values=list(ENGINE_LABELS.values()), textvariable=choice)
        widget.pack(fill="x", pady=(0, 10))
        common_variables = window.common_variables = {}
        window.common_controls = {}

        def sync_preferences(_event=None):
            choice.set(ENGINE_LABELS[self.engine_preferences.mode])
            for key, variable in common_variables.items():
                variable.set(getattr(self.settings, key))

        window.sync_preferences = sync_preferences

        def choose(_event=None):
            selected = next((key for key, value in ENGINE_LABELS.items() if value == choice.get()), None)
            if selected is not None:
                self.set_engine(selected)
            # A failed write must not leave the combo announcing a preference
            # that was never accepted. The actual engine has its own status.
            sync_preferences()

        widget.bind("<<ComboboxSelected>>", choose)
        window.editor_buttons = {}
        for key, text, command in (("canvas", "Configurer PRESENCE 2D", self.open_canvas_settings),
                                   ("gpu", "Configurer PRESENCE 2.5D", self.open_gpu_settings),
                                   ("retry", "Réessayer le GPU", self.retry_gpu)):
            def invoke(action=command):
                action()
                if window.winfo_exists():
                    sync_preferences()
            button = ttk.Button(body, text=text, command=invoke)
            button.pack(fill="x", pady=(0, 6))
            window.editor_buttons[key] = button
        label("Accessibilité commune aux deux moteurs")
        for key, text in (("reduced_motion", "Réduire les mouvements"), ("subtitles", "Afficher les sous-titres")):
            variable = common_variables[key] = tk.BooleanVar(window, value=getattr(self.settings, key))
            def change(k=key, value=variable):
                self.set_options(**{k: value.get()})
                sync_preferences()
            control = ttk.Checkbutton(body, text=text, variable=variable, command=change)
            control.pack(anchor="w", pady=(0, 8))
            window.common_controls[key] = control

        def resize(event):
            canvas.itemconfigure(content_item, width=event.width)
            for item in labels:
                item.configure(wraplength=max(100, event.width-16))

        def reveal(event):
            target = event.widget
            if target is not body and not str(target).startswith(str(body) + "."):
                return
            window.update_idletasks()
            top = target.winfo_rooty() - body.winfo_rooty()
            bottom = top + target.winfo_height()
            visible_top = canvas.canvasy(0)
            height = max(1, body.winfo_height())
            if top < visible_top:
                canvas.yview_moveto(top/height)
            elif bottom > visible_top + canvas.winfo_height():
                canvas.yview_moveto(max(0, bottom-canvas.winfo_height())/height)

        def wheel(event):
            direction = (-1 if event.num == 4 else 1 if event.num == 5 else
                         -1 if event.delta > 0 else 1)
            canvas.yview_scroll(direction * 3, "units")
            return "break"

        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", resize)
        window.bind("<FocusIn>", reveal, add="+")
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            window.bind(sequence, wheel, add="+")
        window.bind("<Control-Home>", lambda _event: canvas.yview_moveto(0))
        window.bind("<Control-End>", lambda _event: canvas.yview_moveto(1))
        window.bind("<Escape>", lambda _event: window.destroy())
        widget.focus_set()
        return window

    def close(self):
        self._closing_host = True
        if self.gpu_studio is not None:
            self.gpu_studio.cancel()
            self.gpu_studio = None
        self._stop_gpu()
        self.active_engine = "canvas"
        if self._engine_dialog is not None and self._engine_dialog.winfo_exists():
            self._engine_dialog.destroy()
        super().close()
