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
    """Conservative UTF-8 byte estimate, NOT an exact model tokenizer.

    Keep whole completed turns, reserve output + template overhead, never
    mutate the archive. The UI reports omitted messages explicitly.
    """
    system = ([{"role": "system", "content": settings.system_prompt}]
              if settings.system_prompt else [])
    budget = settings.context - settings.max_tokens - 256
    cost = lambda m: len(m["content"].encode("utf-8")) + 32
    budget -= sum(cost(m) for m in system)
    if not messages or messages[-1]["role"] != "user":
        raise ValueError("Un message utilisateur est requis.")
    last = messages[-1]
    if cost(last) > budget:
        raise ValueError("Message trop long pour ce contexte. Réduisez-le ou augmentez le contexte.")
    selected = [last]
    budget -= cost(last)
    # Only contiguous complete user/assistant pairs enter the active history.
    previous = messages[:-1]
    for index in range(len(previous) - 2, -1, -2):
        pair = previous[index:index + 2]
        if [m["role"] for m in pair] != ["user", "assistant"]:
            break
        size = sum(cost(m) for m in pair)
        if size > budget:
            break
        selected[0:0] = pair
        budget -= size
    return system + selected, len(messages) - len(selected)
