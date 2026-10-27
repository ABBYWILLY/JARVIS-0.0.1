"""Persistent renderer choice; Canvas remains a first-class independent engine.

Only preference metadata lives here. There is no device, process, Tk or OpenGL
import, and no probing or write at import/application startup.
"""
from dataclasses import asdict, dataclass, replace


ENGINE_LABELS = {"auto": "Automatique", "canvas": "2D classique — Canvas",
                 "gpu": "2.5D holographique — GPU"}


@dataclass(frozen=True)
class EnginePreferences:
    mode: str = "canvas"
    automatic_engine: str = ""
    gpu_failed: bool = False
    reason: str = ""

    @classmethod
    def from_dict(cls, values):
        values = values if isinstance(values, dict) else {}
        mode = values.get("mode", "canvas")
        cached = values.get("automatic_engine", "")
        return cls(mode=mode if isinstance(mode, str) and mode in ENGINE_LABELS else "canvas",
                   automatic_engine=cached if isinstance(cached, str) and cached in {"", "canvas", "gpu"} else "",
                   gpu_failed=values.get("gpu_failed") is True,
                   reason=str(values.get("reason", ""))[:512] if isinstance(values.get("reason", ""), str) else "")

    def to_dict(self):
        return asdict(self)

    @property
    def target(self):
        if self.mode == "canvas" or self.gpu_failed:
            return "canvas"
        return (self.automatic_engine or "gpu") if self.mode == "auto" else "gpu"

    def choose(self, mode):
        if not isinstance(mode, str) or mode not in ENGINE_LABELS:
            raise ValueError("Moteur PRESENCE inconnu.")
        # Choosing GPU is an explicit retry, not a background restart loop.
        return replace(self, mode=mode, gpu_failed=False if mode == "gpu" else self.gpu_failed,
                       reason="" if mode == "gpu" else self.reason)

    def ready(self):
        return replace(self, automatic_engine="gpu" if self.mode == "auto" else self.automatic_engine,
                       gpu_failed=False, reason="")

    def failed(self, reason):
        return replace(self, automatic_engine="canvas" if self.mode == "auto" else self.automatic_engine,
                       gpu_failed=True, reason=str(reason)[:512])

    def retry(self):
        return replace(self, gpu_failed=False, automatic_engine="", reason="")
