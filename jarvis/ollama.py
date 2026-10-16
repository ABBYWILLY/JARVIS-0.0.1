"""Real Ollama HTTP/NDJSON adapter. Never executes generated tool calls."""
import http.client
import json
import socket
import time
from dataclasses import dataclass
from typing import Iterator, Literal, Protocol
from urllib.parse import urlsplit

from .config import Settings
from .metrics import generation_metrics

MAX_LINE = 2 * 1024 * 1024


class OllamaError(Exception):
    pass


@dataclass(frozen=True)
class Event:
    kind: Literal["models", "chunk", "done", "error"]
    payload: object
    version: int = 1
    metadata: dict | None = None


class InferenceProvider(Protocol):
    def models(self) -> list[str]: ...
    def chat(self, messages: list[dict], settings: Settings) -> Iterator[Event]: ...


class Ollama:
    def __init__(self, endpoint, timeout=120):
        Settings(endpoint=endpoint).validate()
        self.url = urlsplit(endpoint)
        self.timeout = timeout

    def _request(self, method, path, payload=None):
        # Direct loopback connection: do not forward private chat to HTTP proxies.
        connection = http.client.HTTPConnection(self.url.hostname, self.url.port, timeout=self.timeout)
        try:
            connection.request(method, path, body=json.dumps(payload).encode() if payload is not None else None,
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                detail = response.read(4096).decode("utf-8", errors="replace")
                if response.status == 404:
                    raise OllamaError("Modèle ou API introuvable. Actualisez les modèles et vérifiez Ollama.")
                if "memory" in detail.lower() or "cuda" in detail.lower():
                    raise OllamaError("Mémoire insuffisante côté Ollama. Choisissez un modèle ou un contexte plus petit.")
                raise OllamaError(f"Ollama a refusé la requête (HTTP {response.status}). Consultez son journal local.")
            return connection, response
        except BaseException:
            connection.close()
            raise

    def models(self):
        connection, response = self._request("GET", "/api/tags")
        try:
            raw = response.read(MAX_LINE + 1)
            if len(raw) > MAX_LINE:
                raise OllamaError("Inventaire Ollama trop volumineux.")
            data = json.loads(raw)
            return sorted({m["name"] for m in data["models"]
                           if isinstance(m["name"], str) and not m.get("remote_host") and not m.get("remote_model")})
        finally:
            connection.close()

    def chat(self, messages, settings):
        # Client-observed latency: includes request, loading, thinking and network.
        started = time.monotonic()
        observed = {}
        connection, response = self._request("POST", "/api/chat", {
            "model": settings.model, "messages": messages, "stream": True,
            "options": {"temperature": settings.temperature, "num_ctx": settings.context,
                        "num_predict": settings.max_tokens},
        })
        try:
            while True:
                line = response.readline(MAX_LINE + 1)
                if not line:
                    raise OllamaError("Flux Ollama interrompu avant la fin. La réponse partielle est conservée.")
                if len(line) > MAX_LINE:
                    raise OllamaError("Fragment Ollama trop volumineux.")
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise OllamaError("Ollama signale une erreur de génération. Vérifiez le modèle et sa mémoire disponible.")
                received_model = generation_metrics({"model": data.get("model")})
                observed.update(received_model)
                content = data.get("message", {}).get("content", "")
                if not isinstance(content, str):
                    raise OllamaError("Format de réponse Ollama invalide.")
                if content:
                    if content.strip() and "ttft_seconds" not in observed:
                        observed.update(generation_metrics({"ttft_seconds": time.monotonic() - started}))
                    yield Event("chunk", content, metadata=dict(observed))
                if data.get("done") is True:
                    observed.update(generation_metrics(data))
                    final = generation_metrics(observed)
                    if isinstance(data.get("done_reason"), str):
                        final["done_reason"] = data["done_reason"]
                    yield Event("done", final)
                    return
        finally:
            connection.close()


def friendly_error(exc):
    if isinstance(exc, OllamaError):
        return str(exc)
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "Ollama ne répond pas depuis 120 s. Réessayez avec un modèle plus petit ou vérifiez le service."
    if isinstance(exc, (ConnectionError, OSError, http.client.HTTPException)):
        return "Connexion Ollama impossible. Démarrez Ollama (ou « ollama serve »), puis cliquez sur Actualiser."
    if isinstance(exc, (ValueError, KeyError, TypeError, AttributeError)):
        return "Réponse Ollama invalide. Vérifiez son adresse et mettez Ollama à jour."
    return "Erreur interne du moteur. Votre historique est conservé ; relancez JARVIS si nécessaire."
