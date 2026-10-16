"""Opt-in, local Ollama comparison; run with ``python -m jarvis.inference_benchmark``.

This compares two combined settings, not isolated causal effects. The corpus is
synthetic, responses need human inspection, and no model is ever downloaded.
"""
import argparse
import json
import os
import platform
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .context import ContextBuilder
from .metrics import generation_metrics
from .ollama import Ollama, OllamaError, friendly_error


_VARIANTS = (("baseline", "auto", False), ("optimized", "fast", True))
_FIELDS = {"eval_count": "tokens", "response_tokens": "tokens",
           "prompt_eval_count": "tokens", "total_duration": "ns",
           "load_duration": "ns", "prompt_eval_duration": "ns",
           "eval_duration": "ns", "ttft_seconds": "s",
           "tokens_per_second": "tokens/s", "wall_seconds": "s"}


def corpus():
    """Fixed six-turn fixtures: no personal history, database or model access."""
    turns = (
        ("Pour le projet Zephyr, quel port local avons-nous retenu ?",
         "Le serveur local du projet Zephyr utilise le port 8765. Ne pas l’exposer sur Internet."),
        ("Nous préparons une démonstration locale de cinq minutes.",
         "La démonstration présentera la conversation, les réglages et la recherche locale."),
        ("Quelle couleur convient à l’interface ?",
         "Gardons le cyan sur fond sombre pour conserver une bonne lisibilité."),
        ("Les documents de démonstration doivent-ils être confidentiels ?",
         "Utilisons uniquement des exemples synthétiques et aucune donnée personnelle."),
        ("Propose deux étapes pour vérifier la démonstration.",
         "Première étape : vérifier la connexion locale. Deuxième étape : tester une conversation."),
        ("Ajoute aussi une vérification du son avant la présentation.",
         "Vérifions le périphérique de sortie et son volume avant de commencer."),
    )
    history = [{"id": index * 2 + offset + 1, "session_id": "benchmark-synthetic",
                "created": "2026-10-17T00:00:00Z", "role": role, "content": text}
               for index, pair in enumerate(turns)
               for offset, (role, text) in enumerate(zip(("user", "assistant"), pair))]
    return [(name, [dict(message) for message in history] + [{
        "role": "user", "content": prompt, "session_id": "benchmark-synthetic"}])
        for name, prompt in (
            ("math", "2 + 2 ?"),
            ("followup", "Développe la première étape du plan."),
            ("recall", "Quel port local avons-nous retenu pour le projet Zephyr ?"))]


def _write(stream, row):
    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _measure(client, settings, messages):
    context = ContextBuilder(settings).build(messages)
    row = {"requested_model": settings.model, "reasoning_mode": settings.reasoning_mode,
           "targeted_context": settings.targeted_context,
           "request_options": {"num_ctx": settings.context, "num_predict": settings.max_tokens,
                               "temperature": settings.temperature},
           "context": context.stats, "sources": context.sources,
           "metrics": {}, "visible_text": "", "warnings": [], "status": "error"}
    chunks = []
    started = time.monotonic()
    events = iter(client.chat(context.messages, settings))
    done = False
    try:
        for event in events:
            if event.metadata:
                row["metrics"].update(generation_metrics(event.metadata))
            if event.kind == "chunk":
                chunks.append(event.payload)
            elif event.kind == "notice":
                row["warnings"].append(str(event.payload))
            elif event.kind == "done":
                row["metrics"].update(generation_metrics(event.payload))
                done = True
                break
        if not done:
            raise OllamaError("Flux Ollama interrompu avant la fin du benchmark.")
        row["status"] = row["metrics"].get("outcome", "error")
        if not "".join(chunks).strip():
            row["status"] = "empty_length" if row["status"] == "empty_length" else "empty"
    except KeyboardInterrupt:
        row["status"] = "interrupted"
    except Exception as error:
        row["error"] = friendly_error(error)
    finally:
        close = getattr(events, "close", None)
        if close:
            close()
        row["wall_seconds"] = time.monotonic() - started
        row["visible_text"] = "".join(chunks)
    return row


def _comparisons(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault((row["case"], row["repeat"]), {})[row["variant"]] = row
    comparisons = []
    for (case, repeat), pair in grouped.items():
        entry = {"case": case, "repeat": repeat, "comparable": False, "deltas": {}}
        before, after = pair.get("baseline"), pair.get("optimized")
        if not before or not after:
            entry["reason"] = "Paire interrompue avant les deux mesures."
        elif any(row["status"] != "complete" or not row["visible_text"].strip()
                 for row in (before, after)):
            entry["reason"] = "Réponse vide, tronquée, interrompue ou en erreur ; aucun gain calculé."
        elif (before["metrics"].get("model") and after["metrics"].get("model")
              and before["metrics"]["model"] != after["metrics"]["model"]):
            entry["reason"] = "Les modèles renvoyés par le serveur diffèrent."
        else:
            entry["comparable"] = True
            for key, unit in _FIELDS.items():
                left = before.get(key) if key == "wall_seconds" else before["metrics"].get(key)
                right = after.get(key) if key == "wall_seconds" else after["metrics"].get(key)
                if left is None or right is None:
                    continue
                entry["deltas"][key] = {"baseline": left, "optimized": right,
                                        "delta": right - left, "unit": unit,
                                        "better_when": "higher" if key == "tokens_per_second" else "lower",
                                        "reduction_percent": ((left - right) / left * 100
                                                              if left else None)}
        comparisons.append(entry)
    return comparisons


def run_benchmark(settings, output, repeats=1, client=None):
    """Write durable JSONL records. Errors retain earlier completed samples."""
    settings.validate()
    if not settings.model.strip():
        raise ValueError("Indiquez le nom exact d’un modèle Ollama installé.")
    if not isinstance(repeats, int) or isinstance(repeats, bool) or not 1 <= repeats <= 10:
        raise ValueError("Choisissez entre 1 et 10 répétitions.")
    rows = []
    interrupted = False
    with Path(output).open("x", encoding="utf-8", newline="\n") as stream:
        _write(stream, {"type": "header", "benchmark_version": 1,
                        "created_utc": datetime.now(timezone.utc).isoformat(),
                        "platform": platform.platform(), "python": platform.python_version(),
                        "requested_settings": settings.to_dict(), "repeats": repeats,
                        "corpus": "synthetic-six-turn-v1", "synthetic_corpus": True,
                        "variants": [{"name": name, "reasoning_mode": reasoning,
                                      "targeted_context": targeted}
                                     for name, reasoning, targeted in _VARIANTS],
                        "limitations": [
                            "Comparaison combinée du raisonnement et du contexte ; effets non isolés.",
                            "Warmup commun fast/16 tokens hors mesures ; aucun essai à froid garanti.",
                            "Ordre alterné ; caches de modèle et de prompt restent influents.",
                            "Qualité des réponses non évaluée : inspecter le texte visible.",
                            "Contexte UTF8 estimé ; tokens comptés uniquement lorsqu’Ollama les fournit.",
                            "Réduction négative = augmentation ; un débit supérieur donne une réduction négative.",
                            "Aucune extrapolation à Windows ou à un autre matériel."]})
        client = client if client is not None else Ollama(settings.endpoint)
        try:
            if settings.model not in client.models():
                raise ValueError("Modèle absent de l’inventaire local Ollama ; aucun téléchargement ni génération effectué.")
        except Exception as error:
            _write(stream, {"type": "error", "stage": "preflight",
                            "error": str(error) if isinstance(error, ValueError) else friendly_error(error)})
            raise
        try:
            warmup_settings = replace(settings, reasoning_mode="fast", targeted_context=True, max_tokens=16)
            warmup = _measure(client, warmup_settings, [{"role": "user", "content": "Réponds simplement : prêt."}])
            _write(stream, {"type": "warmup", "excluded_from_measurements": True, **warmup})
            if warmup["status"] == "interrupted":
                raise KeyboardInterrupt
            if warmup["status"] == "error":
                raise OllamaError("Le warmup local a échoué ; consultez le fichier JSONL.")
            for repeat in range(repeats):
                for case_index, (case, messages) in enumerate(corpus()):
                    variants = _VARIANTS if (repeat + case_index) % 2 == 0 else _VARIANTS[::-1]
                    for order, (variant, reasoning, targeted) in enumerate(variants):
                        profile = replace(settings, reasoning_mode=reasoning, targeted_context=targeted)
                        row = {"type": "measurement", "case": case, "repeat": repeat + 1,
                               "order_in_pair": order + 1, "variant": variant,
                               **_measure(client, profile, messages)}
                        rows.append(row)
                        _write(stream, row)
                        if row["status"] == "interrupted":
                            raise KeyboardInterrupt
        except KeyboardInterrupt:
            interrupted = True
        except Exception as error:
            _write(stream, {"type": "error", "stage": "measurements",
                            "error": str(error) if isinstance(error, ValueError) else friendly_error(error)})
            raise
        comparisons = _comparisons(rows)
        good = sum(pair["comparable"] for pair in comparisons)
        summary = {"type": "summary", "status": "interrupted" if interrupted else
                   "complete" if good == len(corpus()) * repeats else "incomplete",
                   "measured_runs": len(rows), "complete_pairs": good,
                   "excluded_pairs": len(comparisons) - good, "comparisons": comparisons}
        _write(stream, summary)
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Comparer localement Ollama sans télécharger de modèle.")
    parser.add_argument("--model", required=True, help="Nom exact d’un modèle déjà installé dans Ollama.")
    parser.add_argument("--output", required=True, type=Path, help="Nouveau fichier JSONL, jamais écrasé.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--repeats", type=int, default=1, help="Répétitions : 1 à 10 (défaut : 1).")
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args(argv)
    settings = Settings(endpoint=args.endpoint, model=args.model, context=args.context,
                        max_tokens=args.max_tokens, temperature=args.temperature,
                        system_prompt="Réponds en français. Utilise le contexte pour les questions de suivi.")
    try:
        summary = run_benchmark(settings, args.output, args.repeats)
    except FileExistsError:
        print("Le fichier de sortie existe déjà ; choisissez un autre nom. Aucun fichier écrasé.", file=sys.stderr)
        return 1
    except Exception as error:
        print(str(error) if isinstance(error, ValueError) else friendly_error(error), file=sys.stderr)
        return 1
    print(json.dumps({"output": str(args.output), "status": summary["status"],
                      "measured_runs": summary["measured_runs"],
                      "complete_pairs": summary["complete_pairs"],
                      "excluded_pairs": summary["excluded_pairs"]}, ensure_ascii=False))
    return 130 if summary["status"] == "interrupted" else 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
