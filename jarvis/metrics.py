"""Validated Ollama timings; durations from the server remain in nanoseconds.

TTFT is measured by the HTTP client, from just before the request to receipt of
the first non-whitespace content fragment. It includes transport and server
waiting time, and is not a measurement of the server's first generated token.
"""
import math


SERVER_FIELDS = ("total_duration", "load_duration", "prompt_eval_count",
                 "prompt_eval_duration", "eval_count", "eval_duration")


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
    return (f"Modèle : {metrics.get('model', '—')} · Tokens : {count} · "
            f"Tokens/s : {f'{rate:.1f}' if rate is not None else '—'} · "
            f"Génération Ollama : {seconds('eval_duration', 1_000_000_000)} · "
            f"TTFT reçu : {seconds('ttft_seconds')}")
