"""Validated, non-secret model settings. No external endpoint in this milestone."""
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    endpoint: str = "http://127.0.0.1:11434"
    model: str = ""
    temperature: float = 0.7
    context: int = 4096
    max_tokens: int = 1024
    system_prompt: str = ""
    reasoning_mode: str = "fast"
    usage: str = "chat"
    voice_tokens: int = 256
    mission_tokens: int = 4096
    targeted_context: bool = True
    retrieval_budget: int = 768

    def validate(self):
        try:
            url = urlsplit(self.endpoint)
            port = url.port
        except ValueError as exc:
            raise ValueError("Adresse Ollama invalide.") from exc
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.username or url.password or url.path not in {"", "/"}
                or url.query or url.fragment or not port or not 1 <= port <= 65535):
            raise ValueError("Utilisez une adresse locale, par exemple http://127.0.0.1:11434.")
        if not 0 <= self.temperature <= 2:
            raise ValueError("La température doit être comprise entre 0 et 2.")
        if not 512 <= self.context <= 131072:
            raise ValueError("Le contexte doit être compris entre 512 et 131072 tokens.")
        if not 1 <= self.max_tokens <= self.context // 2:
            raise ValueError("La réponse doit réserver entre 1 token et la moitié du contexte.")
        if len(self.system_prompt.encode("utf-8")) > self.context // 2:
            raise ValueError("L’instruction système est trop longue pour ce contexte.")
        if self.reasoning_mode not in {"fast", "auto", "deep"}:
            raise ValueError("Choisissez un raisonnement Rapide, Automatique ou Approfondi.")
        if self.usage not in {"voice", "chat", "mission"}:
            raise ValueError("Choisissez un budget vocal, discussion ou mission.")
        for value in (self.voice_tokens, self.mission_tokens):
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65536:
                raise ValueError("Les budgets vocal et mission doivent être compris entre 1 et 65536 tokens.")
        if not isinstance(self.targeted_context, bool):
            raise ValueError("Le contexte ciblé doit être activé ou désactivé.")
        if (not isinstance(self.retrieval_budget, int) or isinstance(self.retrieval_budget, bool)
                or not 0 <= self.retrieval_budget <= 8192):
            raise ValueError("Le budget des extraits doit être compris entre 0 et 8192 tokens estimés.")
        return self

    def for_request(self, source="text"):
        """Output budgets are independent of thinking; never change the profile.

        Old saved profiles acquire defaults without a database migration. A
        voice turn uses its own budget; all budgets respect the context cap.
        Explicit deep reasoning remains available, including during voice use.
        """
        self.validate()
        usage = "voice" if source == "voice" else self.usage
        limit = {"voice": self.voice_tokens, "chat": self.max_tokens,
                 "mission": self.mission_tokens}[usage]
        return replace(self, usage=usage, max_tokens=min(limit, self.context // 2))

    def to_dict(self):
        return asdict(self)


def data_directory():
    if os.environ.get("JARVIS_DATA_DIR"):
        return Path(os.environ["JARVIS_DATA_DIR"])
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Jarvis"
    return Path.home() / ".local/share/jarvis"


def active_context(messages, settings):
    """Compatibility facade; all callers share the same context accounting."""
    from .context import ContextBuilder
    result = ContextBuilder(settings).build(messages)
    return result.messages, result.stats["omitted_messages"]
