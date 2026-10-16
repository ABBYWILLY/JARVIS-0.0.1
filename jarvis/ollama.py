"""Real Ollama HTTP/NDJSON adapter. Never executes generated tool calls."""
import http.client
import json
import re
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


class OllamaHTTPError(OllamaError):
    """Keep a bounded server rejection private, for explicit compatibility checks."""
    def __init__(self, status, detail):
        super().__init__(f"Ollama a refusé la requête (HTTP {status}). Consultez son journal local.")
        self.status = status
        self.detail = detail


def unsupported_thinking(error):
    """Only an explicit unsupported think field permits one compatibility retry."""
    if not isinstance(error, OllamaHTTPError) or error.status not in {400, 422}:
        return False
    detail = error.detail
    try:
        data = json.loads(detail)
    except (ValueError, TypeError):
        pass
    else:
        detail = data.get("error", "") if isinstance(data, dict) else ""
    if not isinstance(detail, str):
        return False
    detail = detail.casefold()
    return any(re.search(pattern, detail) for pattern in (
        r"\bdoes not support thinking\b",
        r"\bthink(?:ing)?\s+(?:is\s+)?(?:not supported|unsupported)\b",
        r"\b(?:unknown|unrecognized|unsupported)\s+(?:field|parameter|option)\s*[:=]?\s*[\"'`]?think(?:ing)?\b",
        r"\b(?:field|parameter|option)\s*[\"'`]?think(?:ing)?[\"'`]?\s+(?:is\s+)?(?:unsupported|not supported|unknown|unrecognized)\b",
    ))


@dataclass(frozen=True)
class Event:
    kind: Literal["models", "chunk", "done", "error", "notice"]
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
                raise OllamaHTTPError(response.status, detail)
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
        mode = settings.reasoning_mode
        statuses = {"fast": "requested_disabled", "deep": "requested_enabled", "auto": "model_default"}
        if mode not in statuses:
            raise ValueError("Mode de raisonnement invalide.")
        observed = {"reasoning_status": statuses[mode], "thinking_observed": False}
        payload = {
            "model": settings.model, "messages": messages, "stream": True,
            "options": {"temperature": settings.temperature, "num_ctx": settings.context,
                        "num_predict": settings.max_tokens},
        }
        # Ollama's think field is top-level. Model names do not prove support.
        if mode != "auto":
            payload["think"] = mode == "deep"
        try:
            connection, response = self._request("POST", "/api/chat", payload)
        except OllamaHTTPError as exc:
            if "think" not in payload or not unsupported_thinking(exc):
                raise
            # Only HTTP rejection is eligible: the stream has not begun, so no
            # partial reply or tool request can be duplicated by this retry.
            payload.pop("think")
            observed["reasoning_status"] = "unsupported"
            yield Event("notice", "Ce modèle ou cette version d’Ollama ne prend pas en charge le réglage de raisonnement. "
                        "Une seule reprise utilise le comportement par défaut du modèle.", metadata=dict(observed))
            connection, response = self._request("POST", "/api/chat", payload)
        visible_content = False
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
                if not isinstance(data, dict):
                    raise OllamaError("Format de réponse Ollama invalide.")
                if data.get("error"):
                    raise OllamaError("Ollama signale une erreur de génération. Vérifiez le modèle et sa mémoire disponible.")
                received_model = generation_metrics({"model": data.get("model")})
                observed.update(received_model)
                message = data.get("message", {})
                if not isinstance(message, dict):
                    raise OllamaError("Format de réponse Ollama invalide.")
                content = message.get("content", "")
                thinking = message.get("thinking", "")
                if not isinstance(content, str) or not isinstance(thinking, str):
                    raise OllamaError("Format de réponse Ollama invalide.")
                # Observe presence only; never queue, save or display internal text.
                if thinking.strip():
                    observed["thinking_observed"] = True
                if content:
                    if content.strip():
                        visible_content = True
                        if "ttft_seconds" not in observed:
                            observed.update(generation_metrics({"ttft_seconds": time.monotonic() - started}))
                    yield Event("chunk", content, metadata=dict(observed))
                if data.get("done") is True:
                    server_metrics = generation_metrics(data)
                    for key in ("ttft_seconds", "reasoning_status", "thinking_observed", "outcome", "done_reason"):
                        server_metrics.pop(key, None)
                    observed.update(server_metrics)
                    final = generation_metrics(observed)
                    # Client observations must not be replaced by server fields.
                    final.update({key: observed[key] for key in ("reasoning_status", "thinking_observed")})
                    if isinstance(data.get("done_reason"), str):
                        final["done_reason"] = data["done_reason"]
                    limited = data.get("done_reason") == "length"
                    final["outcome"] = (("length" if limited else "complete") if visible_content
                                        else ("empty_length" if limited else "empty"))
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
