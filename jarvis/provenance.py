"""Bounded, local observations of prepared context, never hidden reasoning.

Capture once when preparing a request. Inspect only on explicit user action;
there is no database, model call, timer, telemetry, or renderer dependency here.
The private instruction/excerpt data returned here must never enter a GPU HUD.
"""
import hashlib
import json
import math
import re


MAX_CANDIDATES = 5
MAX_SOURCES = 128
MAX_SYSTEM_CHARACTERS = 65536
_REFERENCE = re.compile(r"\[(?:mémoire|memoire|souvenir)\s+#([1-9][0-9]{0,11})\]", re.I)


def _object(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    try:
        return dict(value) if value is not None else {}
    except (TypeError, ValueError):
        return {}


def _text(value, limit=256):
    return value[:limit] if isinstance(value, str) else ""


def _id(value):
    return value if type(value) is int and value > 0 else None


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def context_observations(context_result, retrieved_memories=None, prepared_ms=None):
    """Extra fields to merge into the existing archived ``context`` object.

    ``None`` means no memory search was observed; ``[]`` is a search with no
    candidates. Only IDs/small metadata/digests are copied from search results.
    Effective instructions come from actual prepared messages, not settings
    which may have changed by the time this answer is inspected.
    """
    candidates = []
    seen = set()
    for value in (retrieved_memories or ())[:MAX_CANDIDATES]:
        memory = _object(value)
        mid = _id(memory.get("id"))
        if mid is None or mid in seen:
            continue
        seen.add(mid)
        content = memory.get("content")
        candidates.append({"memory_id": mid, "title": _text(memory.get("title")),
            "kind": _text(memory.get("kind"), 32), "status": _text(memory.get("status"), 32),
            "created": _text(memory.get("created"), 64), "updated": _text(memory.get("updated"), 64),
            "content_sha256": _digest(content) if isinstance(content, str) else ""})
    instructions, remaining, truncated = [], MAX_SYSTEM_CHARACTERS, False
    messages = context_result.messages
    # ContextBuilder emits at most one system message. Keep a defensive bound
    # for another adapter, and explicitly report any incomplete capture.
    systems = [message for message in messages if message.get("role") == "system"]
    for message in systems[:8]:
        content = message.get("content", "")
        if not isinstance(content, str):
            truncated = True
            continue
        piece = content[:remaining]
        instructions.append({"role": "system", "content": piece})
        remaining -= len(piece)
        truncated |= len(piece) != len(content)
    truncated |= len(systems) > 8
    encoded = json.dumps(instructions, ensure_ascii=False, separators=(",", ":"))
    result = {"delivery": "prepared", "retrieval_observed": retrieved_memories is not None,
        "retrieved_memory_candidates": candidates,
        "system_instructions": instructions, "system_instructions_sha256": _digest(encoded),
        "system_instructions_truncated": truncated}
    if (isinstance(prepared_ms, (int, float)) and not isinstance(prepared_ms, bool)
            and math.isfinite(prepared_ms) and prepared_ms >= 0):
        result["preparation_ms"] = round(prepared_ms, 3)
    return result


def _memory_condition(source, candidate, current):
    if current is None:
        return "not_checked"
    memory = _object(current.get(source["memory_id"]))
    if not memory:
        return "missing"
    expected_created = candidate.get("created") or source.get("created")
    if expected_created and memory.get("created") != expected_created:
        return "identity_mismatch"
    fingerprint = candidate.get("content_sha256")
    if fingerprint and isinstance(memory.get("content"), str):
        if _digest(memory["content"]) != fingerprint:
            return "modified"
        if memory.get("status") != source.get("status", candidate.get("status")):
            return "status_changed"
        return "unchanged"
    return "unverified"


def inspect_provenance(metadata, *, response_text="", memory_current=None):
    """Return a JSON-compatible report for the existing explicit inspector.

    A formal textual marker is only an observed reference, not evidence that
    any supplied fact was used or true. Without a marker, included text is never
    promoted to a citation. Code examples do not become source references.
    ``memory_current=None`` means not checked; an empty mapping means checked
    and no recorded memory is currently present.
    """
    metadata = _object(metadata)
    memory_current = _object(memory_current) if memory_current is not None else None
    context = _object(metadata.get("context"))
    raw_candidates = context.get("retrieved_memory_candidates", [])
    raw_candidates = raw_candidates if isinstance(raw_candidates, list) else []
    candidates = []
    for value in raw_candidates[:MAX_CANDIDATES]:
        candidate = _object(value)
        if _id(candidate.get("memory_id")) is not None:
            candidates.append({key: candidate[key] for key in (
                "memory_id", "title", "kind", "status", "created", "updated", "content_sha256") if key in candidate})
    indexed = {candidate["memory_id"]: candidate for candidate in candidates}
    included = []
    raw_sources = context.get("sources", [])
    raw_sources = raw_sources if isinstance(raw_sources, list) else []
    for value in raw_sources[:MAX_SOURCES]:
        source = _object(value)
        if not source:
            continue
        record = {key: source[key] for key in ("memory_id", "message_id", "session_id", "role", "method", "created",
                  "kind", "status", "title", "topic", "excerpt", "provenance") if key in source}
        for key, limit in (("excerpt", 4096), ("title", 256), ("topic", 256)):
            if key in record:
                value = record[key]
                record[key] = _text(value, limit)
                if isinstance(value, str) and len(value) > limit:
                    record[key + "_truncated"] = True
        if source.get("method") == "memory" and _id(source.get("memory_id")) is not None:
            record["current_condition"] = _memory_condition(record, indexed.get(source["memory_id"], {}), memory_current)
        included.append(record)
    memory_sources = {source["memory_id"]: source for source in included
                      if source.get("method") == "memory" and _id(source.get("memory_id")) is not None}
    for candidate in candidates:
        candidate["included"] = candidate["memory_id"] in memory_sources
    # This is not a citation generator and changes no prompt. It recognizes
    # only this documented qualified notation when the model actually emits it.
    plain = re.sub(r"```.*?(?:```|$)|~~~.*?(?:~~~|$)|`[^`]*(?:`|$)", "", _text(response_text, 1_000_000), flags=re.S)
    cited, unknown, seen = [], [], set()
    for match in _REFERENCE.finditer(plain):
        mid = int(match[1])
        if mid in seen:
            continue
        seen.add(mid)
        if len(seen) > MAX_SOURCES:
            break
        record = {"memory_id": mid, "marker": match.group(), "kind": "explicit_text_reference"}
        (cited if mid in memory_sources else unknown).append(record)
    instructions_available = "system_instructions" in context
    instructions = context.get("system_instructions", [])
    instructions = instructions if isinstance(instructions, list) else []
    captured, remaining = [], MAX_SYSTEM_CHARACTERS
    for value in instructions[:8]:
        record = _object(value)
        if record.get("role") == "system":
            content = _text(record.get("content"), remaining)
            captured.append({"role": "system", "content": content})
            remaining -= len(content)
    instructions = captured
    observed = context.get("retrieval_observed") is True
    delivery = context.get("delivery")
    delivery = delivery if isinstance(delivery, str) and delivery in {"prepared", "submitted", "accepted"} else "unknown"
    delivery_line = {"prepared": "Contexte préparé ; acceptation HTTP par Ollama non observée.",
                     "submitted": "Requête soumise ; acceptation HTTP par Ollama non observée.",
                     "accepted": "Requête acceptée par Ollama (HTTP) ; utilisation de chaque source non démontrée.",
                     "unknown": "État de transmission non enregistré pour cette ancienne réponse."}[delivery]
    lines = [delivery_line,
             f"Souvenirs récupérés par la recherche : {len(candidates)}." if observed else "Recherche mémoire non enregistrée pour cette réponse.",
             f"Souvenirs insérés dans le contexte préparé : {len(memory_sources)}.",
             f"Références textuelles explicites reliées à ces souvenirs : {len(cited)}."]
    if not cited:
        lines.append("Aucune citation explicite vérifiable ; l’inclusion ne prouve pas l’utilisation par Ollama.")
    if unknown:
        lines.append("Des marqueurs de souvenir ne correspondent à aucune source incluse connue.")
    if instructions_available:
        lines.append("Instructions système effectives conservées pour cette requête (inspecteur privé).")
    else:
        lines.append("Instructions système non enregistrées ; les réglages actuels ne les reconstituent pas.")
    omitted = context.get("omitted_messages")
    if type(omitted) is int and omitted > 0:
        lines.append(f"Budget : {omitted} messages hors contexte, toujours archivés.")
    if context.get("system_instructions_truncated") is True:
        lines.append("Capture des instructions incomplète : limite de taille atteinte.")
    return {"delivery": delivery, "retrieval_observed": observed, "retrieved": candidates, "included": included,
        "cited": cited, "unknown_references": unknown,
        "instructions_available": instructions_available, "system_instructions": instructions,
        "instructions_sha256": _text(context.get("system_instructions_sha256"), 64),
        "instructions_truncated": context.get("system_instructions_truncated") is True,
        "summary": "\n".join(lines),
        "usage_note": "Contexte préparé pour l’appel : aucune preuve d’utilisation, de vérité ou de raisonnement interne."}
