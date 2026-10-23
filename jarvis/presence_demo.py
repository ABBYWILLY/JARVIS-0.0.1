"""Explicit offline rehearsal using the production Canvas and state machine.

There is no audio capture, playback, inference or preference write here. The
small deterministic PCM summaries exist only while this labelled demo runs.
"""
from dataclasses import asdict
import math
import time

from .richtext import parse_text
from .spectrum import Tone


# Label, seconds, operational visual state. These are a script, not telemetry.
STAGES = (
    ("Repos", .8, "silent"),
    ("Écoute", 1.5, "listening"),
    ("Réflexion", 1.8, "thinking"),
    ("Parole", 1.8, "jarvis_speaking"),
    ("Émotion", 1.8, "jarvis_speaking"),
    ("Emoji", 2., "silent"),
    ("Interruption", .7, "user_speaking"),
    ("Repos final", .8, "silent"),
)
DEMO_LABEL = "DÉMONSTRATION · PCM synthétique · aucun micro ni modèle"


def synthetic_signal(elapsed):
    """Deterministic bounded samples with an RMS computed from those samples."""
    envelope = .06 + .12 * (.5 + .5 * math.sin(elapsed * 4.1))
    samples = tuple(envelope * (math.sin(n * .37 + elapsed * 7.)
                    + .35 * math.sin(n * .91 - elapsed * 3.)) / 1.35 for n in range(97))
    return {"rms": math.sqrt(sum(value * value for value in samples) / len(samples)),
            "wave": samples}


class DemoController:
    """One cancellable timer; real input always owns the renderer first.

    PresenceView checks ``dispatching`` before cancelling synthetic events. Its
    real-input, hide and close paths cancel this controller synchronously.
    """
    def __init__(self, view, *, clock=time.monotonic, on_stage=None, on_finish=None):
        self.view, self.clock = view, clock
        self.on_stage, self.on_finish = on_stage, on_finish
        self.active = self.dispatching = False
        self.after_id = None
        self.stage = -1
        self.reason = None
        self._started = 0.
        self._response = -1
        self._old_response = -1
        self._old_closed = True
        self._caption = None

    def start(self):
        view = self.view
        if (self.active or view.app.voice.listening or getattr(view.app, "operation", None)
                or view.state != "silent" or not view._visible()):
            return False
        previous = getattr(view, "_demo", None)
        if previous is not None and previous is not self and previous.active:
            previous.cancel("replaced")
        view.clear_preview()
        view._demo = self
        self._old_response, self._old_closed = view._semantic_response, view._semantic_closed
        self._response = max(0, self._old_response + 1)
        self._started = self.clock()
        self.active, self.reason, self.stage = True, None, -1
        view._trace_semantic("demo", "offline_synthetic_pcm")
        self._tick()
        return True

    def _tick(self):
        self.after_id = None
        if not self.active:
            return
        view = self.view
        if (view.app.voice.listening or getattr(view.app, "operation", None)
                or not view._visible()):
            self.cancel("real_input_or_hidden")
            return
        elapsed = max(0., self.clock() - self._started)
        edge = 0.
        selected = None
        for index, (_, duration, _) in enumerate(STAGES):
            if elapsed < edge + duration:
                selected = index
                break
            edge += duration
        if selected is None:
            self.cancel("completed")
            return
        changed = selected != self.stage
        self.dispatching = True
        try:
            self.stage = selected
            self._paint(selected, elapsed - edge, changed)
            if changed and self.on_stage is not None:
                self.on_stage(selected, STAGES[selected][0])
        except Exception:
            # A failed capture/renderer must not leave a synthetic state active.
            # The application still receives the exception through Tk's normal
            # visible error handler; this does not hide the underlying fault.
            self.cancel("error")
            raise
        finally:
            self.dispatching = False
        if self.active:
            self.after_id = view.app.root.after(40, self._tick)

    def _prepare_caption(self, text, segment):
        view = self.view
        document = parse_text(text)
        events, plan = view.prepare_segment(text, document.text, 0)
        view.queue_expressions(self._response, segment, text, 0, len(text), document.events)
        return {"text": document.text, "response_id": self._response, "segment_id": segment,
                "original_start": 0, "original_end": len(text), "fraction": 0.,
                "spectrum_events": [asdict(event) for event in events],
                "caption_plan": asdict(plan), "spectrum_mode": view.settings.spectrum_mode}

    def _paint(self, index, local, changed):
        view = self.view
        label, duration, state = STAGES[index]
        if changed:
            self._caption = None
            if index == 3:
                view.begin_response()
                self._caption = self._prepare_caption("Voici une phrase de démonstration hors ligne.", 1)
            elif index == 4:
                self._caption = self._prepare_caption("Je ressens de la tendresse et de l'affection.", 2)
            elif index == 5:
                # Exercise exactly the terminal-expression path used by voice:
                # prepared text -> synthetic PCM boundary -> reliable completion.
                self._caption = self._prepare_caption("Heureux de te revoir 😊", 3)
                self._caption["fraction"] = 1.
                view.update_event("jarvis_speaking", {"rms": 0., "wave": (0.,) * 97}, self._caption)
                view.complete_segment(self._caption)
            else:
                view.update_event(state)
        if index in {1, 3, 4, 6}:
            signal = synthetic_signal(local)
            if self._caption is not None:
                self._caption["fraction"] = min(1., local / duration)
            view.update_event(state, signal, self._caption)
        # Set after update_event, which correctly clears normal preview text on
        # each actual event. Every visible stage explicitly declares its origin.
        view._preview_text = DEMO_LABEL + " · " + label
        view._overlay_key = None
        view._render()
        # The normal renderer labels all previews as offline, but does not print
        # their full text. Declare synthetic PCM explicitly on the visible UI.
        view.state_label.configure(text="DÉMO · PCM SYNTHÉTIQUE\n" + label.upper())

    def cancel(self, reason="cancelled"):
        if not self.active:
            return
        self.active, self.reason = False, reason
        if self.after_id is not None:
            self.view.app.root.after_cancel(self.after_id)
            self.after_id = None
        self.dispatching = True
        view = self.view
        try:
            view._cancel_semantics("demo:" + reason)
            view.clear_preview()
            view._clear_playback()
            view.model.update_event("silent")
            view._preview_text = None
            view._workshop_preview = False
            view._semantic_response, view._semantic_closed = self._old_response, self._old_closed
            view._set_tone(Tone())
            view._overlay_key = None
            if view._visible():
                view._render()
        finally:
            self.dispatching = False
        if self.on_finish is not None:
            self.on_finish(reason)

    def stop(self):
        self.cancel("stopped")
