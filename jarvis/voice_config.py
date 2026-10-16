"""Optional voice profile; old model Settings remain unchanged."""
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import data_directory

VOICES = {"fr_FR-tom-medium": "Tom · masculin français", "fr_FR-siwis-medium": "Siwis · féminin français"}


@dataclass(frozen=True)
class VoiceSettings:
    input_device: str = ""
    output_device: str = ""
    models_dir: str = ""
    voice: str = "fr_FR-tom-medium"
    speed: float = 1.0
    acoustic_mode: str = "speakers"
    vad_threshold: float = 0.6
    silence_ms: int = 800
    cpu_threads: int = 4
    personality: str = "Personnalisé"

    def validate(self):
        if self.voice not in VOICES or self.acoustic_mode not in {"speakers", "headphones"}:
            raise ValueError("Voix ou mode acoustique invalide.")
        if not 0.5 <= self.speed <= 2 or not 0.3 <= self.vad_threshold <= 0.95:
            raise ValueError("Vitesse (0,5–2) ou seuil VAD (0,3–0,95) invalide.")
        if not 300 <= self.silence_ms <= 2500 or not 1 <= self.cpu_threads <= 8:
            raise ValueError("Silence (300–2500 ms) ou threads CPU (1–8) invalide.")
        return self

    @property
    def model_root(self):
        return Path(self.models_dir) if self.models_dir else data_directory() / "models"

    def to_dict(self):
        return asdict(self)
