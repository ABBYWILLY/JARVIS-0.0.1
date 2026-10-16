"""Validated Ollama timings; durations from the server remain in nanoseconds.

TTFT is measured by the HTTP client, from just before the request to receipt of
the first non-whitespace content fragment. It includes transport and server
waiting time, and is not a measurement of the server's first generated token.
"""
import math


SERVER_FIELDS = ("total_duration", "load_duration", "prompt_eval_count",
                 "prompt_eval_duration", "eval_count", "eval_duration", "response_tokens")

REASONING_LABELS = {"requested_disabled": "désactivation demandée",
                    "requested_enabled": "activation demandée",
                    "model_default": "choix du modèle (automatique)",
                    "unsupported": "paramètre non pris en charge, choix du modèle"}


def generation_metrics(values):
    """Keep real, valid observations only; never estimate missing token counts."""
    if not isinstance(values, dict):
        return {}
    result = {}
    model = values.get("model")
    if isinstance(model, str) and model.strip():
        result["model"] = model.strip()
    for key in SERVER_FIELDS:
        value = values.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[key] = value
    if isinstance(values.get("reasoning_status"), str) and values["reasoning_status"] in REASONING_LABELS:
        result["reasoning_status"] = values["reasoning_status"]
    if isinstance(values.get("thinking_observed"), bool):
        result["thinking_observed"] = values["thinking_observed"]
    if isinstance(values.get("outcome"), str) and values["outcome"] in {"complete", "empty", "empty_length", "length"}:
        result["outcome"] = values["outcome"]
    if isinstance(values.get("done_reason"), str):
        result["done_reason"] = values["done_reason"]
    ttft = values.get("ttft_seconds")
    if isinstance(ttft, (int, float)) and not isinstance(ttft, bool):
        try:
            if math.isfinite(ttft) and ttft >= 0:
                result["ttft_seconds"] = float(ttft)
        except OverflowError:
            pass
    count, duration = result.get("eval_count"), result.get("eval_duration")
    if count is not None and duration:
        try:
            rate = count * 1_000_000_000 / duration
            if math.isfinite(rate):
                result["tokens_per_second"] = rate
        except OverflowError:
            pass
    return result


def metrics_label(values):
    """Compact French presentation; a dash means the observation is absent."""
    metrics = generation_metrics(values)
    def seconds(key, scale=1):
        value = metrics.get(key)
        if value is None:
            return "—"
        try:
            return f"{value / scale:.2f} s"
        except OverflowError:
            return "—"

    count = metrics.get("eval_count", "—")
    rate = metrics.get("tokens_per_second")
    label = (f"Modèle : {metrics.get('model', '—')} · Tokens : {count} · "
            f"Tokens/s : {f'{rate:.1f}' if rate is not None else '—'} · "
            f"Génération Ollama : {seconds('eval_duration', 1_000_000_000)} · "
            f"TTFT reçu : {seconds('ttft_seconds')}")
    # eval_count includes all generated tokens. Visible text is not a tokenizer:
    # neither its length nor eval_count minus an estimate is a valid count.
    label += (f" · Tokens de génération totaux : {count}"
              f" · Tokens de réponse visibles : {metrics.get('response_tokens', 'indisponibles')}"
              f" · Tokens du prompt : {metrics.get('prompt_eval_count', '—')}"
              f" · Traitement du prompt : {seconds('prompt_eval_duration', 1_000_000_000)}")
    reasoning = REASONING_LABELS.get(metrics.get("reasoning_status"), "indisponible")
    if metrics.get("thinking_observed"):
        reasoning += " ; pensée interne reçue"
    label += " · Raisonnement : " + reasoning
    if metrics.get("outcome") in {"empty_length", "length"}:
        label += " · Limite de génération atteinte"
    elif metrics.get("outcome") == "empty":
        label += " · Aucun texte visible"
    return label
