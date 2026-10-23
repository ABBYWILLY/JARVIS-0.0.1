"""Local, inspectable generation policies and explicitly requested continuation.

No inference, truth score, hidden reasoning or personal memory is produced here.
Creative is a generation policy (temperature >= .9, think:false), not a separate
reasoning capability. Original settings and archived messages remain unchanged.
"""
import json
import re
import unicodedata
from dataclasses import replace

from .context import ContextBuilder, ContextResult, _cost, _OVERHEAD


MODE_LABELS = {"fast": "Rapide", "deep": "Approfondi", "creative": "Créatif",
               "model_default": "Choix du modèle"}
CONTINUE_PROMPT = ("Continue après le passage précédent, sans le répéter. "
                   "Conserve personnages, faits, chronologie et objectifs. "
                   "Si une donnée manque, signale-le au lieu de la contredire.")
_FINAL = frozenset({"complete", "cancelled", "interrupted", "error"})


def _fold(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def route_request(settings, text, source="text", continuation=False):
    """Select one request policy, preserving manual profiles and J2.8 budgets."""
    if not isinstance(text, str):
        raise ValueError("La demande doit être du texte.")
    request = settings.for_request(source)
    selected = settings.cognitive_mode
    origin = "manual"
    reason = "Réglage manuel conservé."
    if selected == "manual":
        selected = {"fast": "fast", "deep": "deep", "auto": "model_default"}[request.reasoning_mode]
        reason = "Réglage de raisonnement J2.8 conservé, sans routage supplémentaire."
    elif selected == "auto":
        origin = "local_heuristic"
        # Quoted/code examples are data, not requests to change policy.
        query = re.sub(r"""```.*?```|`[^`]*`|«[^»]*»|"[^"]*"|“[^”]*”|‘.*?’(?!\w)|(?<!\w)'.*?'(?!\w)""",
                       " ", text[:16000], flags=re.DOTALL)
        query = _fold(query)
        # A negated request is not a request to activate that policy. Ambiguous
        # clauses fall back to fast; other explicit clauses remain eligible.
        query = " ".join(clause for clause in re.split(r"[,.!?;\n]+", query)
                         if not re.search(r"\b(?:ne\s+\w+|n['’]\w+)\s+(?:\w+\s+){0,3}(?:pas|jamais|plus|rien|aucun(?:e|s|es)?)\b", clause))
        if re.search(r"\b(?:ecris|redige|raconte|invente|imagine|compose|cree|propose)\b.{0,80}\b(?:histoire|recit|conte|poeme|roman|scene|scenario|dialogue|chanson|personnage|idees originales)\b", query):
            selected, reason = "creative", "Demande explicite de création narrative ou artistique."
        elif re.search(r"\b(?:analyse|etudie|examine)\b.{0,80}\b(?:en profondeur|approfondi\w*|multicritere|compromis|risques|contraintes)\b|\b(?:demontre|prouve)\b.{0,60}\b(?:theoreme|proposition|mathematique|formellement)\b|\b(?:raisonne|resous)\b.{0,50}\b(?:etape par etape|probleme complexe)\b|\bcompare\b.{0,80}\b(?:criteres|compromis|risques)\b", query):
            selected, reason = "deep", "Demande explicite d'analyse structurée, de preuve ou de compromis."
        else:
            selected, reason = "fast", "Aucun indice explicite nécessitant une autre politique ; priorité à la latence."
    if settings.cognitive_mode != "manual":
        request = replace(request, reasoning_mode="deep" if selected == "deep" else "fast",
                          temperature=max(.9, request.temperature) if selected == "creative" else request.temperature)
    metadata = {"mode": selected, "origin": origin, "reason": reason,
                "budget": request.max_tokens, "usage": request.usage,
                "temperature": request.temperature, "reasoning_mode": request.reasoning_mode,
                "continuation": bool(continuation),
                "policy": "creative_temperature" if selected == "creative" else "reasoning_setting"}
    return request, metadata


def _metadata(record):
    value = record.get("metadata", {})
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ValueError("Métadonnées de continuation invalides ; l'archive reste préservée.") from exc
    if not isinstance(value, dict):
        raise ValueError("Métadonnées de continuation invalides.")
    return value


def _continuation_chain(records, target):
    rows, target = [dict(row) for row in records], dict(target)
    mid = target.get("id")
    if not isinstance(mid, int) or isinstance(mid, bool):
        raise ValueError("Choisissez une réponse archivée identifiable.")
    session = target.get("session_id")
    rows = [row for row in rows if row.get("session_id") == session]
    by_id = {row.get("id"): index for index, row in enumerate(rows)}
    index = by_id.get(mid)
    if index is None or rows[index] != target:
        raise ValueError("La réponse choisie ne correspond plus à l'archive courante.")
    eligible = [row for row in rows if row.get("role") == "assistant"
                and isinstance(row.get("content"), str) and row["content"].strip()]
    if (not eligible or eligible[-1].get("id") != mid or target.get("status") not in _FINAL
            or target.get("role") != "assistant"
            or any(row.get("status") == "streaming" for row in rows[index:])):
        raise ValueError("Continuez uniquement la dernière réponse non vide, après la fin de génération.")
    chain, seen = [], set()
    while True:
        if index < 1 or rows[index - 1].get("role") != "user":
            raise ValueError("Demande d'origine introuvable pour cette réponse.")
        record = rows[index]
        if record.get("id") in seen or len(chain) >= 16:
            raise ValueError("Chaîne de continuation cyclique ou trop longue (16 segments maximum).")
        seen.add(record["id"])
        chain.append((rows[index - 1], record))
        continuation = _metadata(record).get("continuation")
        if not isinstance(continuation, dict) or continuation.get("target_message_id") is None:
            break
        ancestor = continuation["target_message_id"]
        if not isinstance(ancestor, int) or isinstance(ancestor, bool) or ancestor not in by_id:
            raise ValueError("Segment d'origine de la continuation introuvable.")
        index = by_id[ancestor]
        if rows[index].get("role") != "assistant" or rows[index].get("status") not in _FINAL:
            raise ValueError("Segment d'origine non finalisé.")
    return rows, list(reversed(chain))


def continuation_origin(records, target):
    """Read the actual initial user request, including after repeated continuations."""
    _rows, chain = _continuation_chain(records, target)
    return dict(chain[0][0])


def _prefix(text, limit):
    return text.encode("utf-8")[:max(0, limit)].decode("utf-8", errors="ignore")


def _suffix(text, limit):
    return text.encode("utf-8")[-limit:].decode("utf-8", errors="ignore") if limit > 0 else ""


def _fit_original(text, limit):
    if len(text.encode("utf-8")) <= limit:
        return text, False
    label, gap = "[Extraits originaux non exhaustifs]\n", "\n[Passage omis]\n"
    available = limit - len((label + gap).encode("utf-8"))
    if available < 32:
        raise ValueError("Contexte insuffisant pour conserver les passages de continuation ; augmentez le contexte ou réduisez le budget de réponse.")
    head = _prefix(text, available * 2 // 5)
    tail = _suffix(text, available - len(head.encode("utf-8")))
    return label + head + gap + tail, True


def _provenance(record, excerpt, truncated):
    return {"message_id": record["id"], "session_id": record.get("session_id", ""),
            "created": record.get("created", ""), "role": record["role"],
            "method": "continuation_extract" if truncated else "continuation_original",
            "excerpt": excerpt if truncated else excerpt[:240], "original_characters": len(record["content"])}


def build_continuation(settings, records, target, memories=None):
    """Pin original objective/introduction/current passage within the context cap.

    Long archives are represented by explicitly labelled original excerpts, not
    invented summaries. Continuity is instructed and grounded in those passages;
    contradictions and repetitions cannot be guaranteed absent without inference.
    """
    settings.validate()
    rows, chain = _continuation_chain(records, target)
    user, first = chain[0]
    target = chain[-1][1]
    current = {"role": "user", "content": CONTINUE_PROMPT, "session_id": target.get("session_id")}
    system_cost = _cost({"content": settings.system_prompt}) if settings.system_prompt else 0
    available = settings.context - settings.max_tokens - _OVERHEAD - system_cost - _cost(current)
    # Both anchors must remain meaningful. Do not silently continue without them.
    if available < 256:
        raise ValueError("Contexte insuffisant pour la continuation ; augmentez le contexte ou réduisez le budget de réponse.")
    content_budget = available - 64  # Two message overheads, exactly as ContextBuilder.
    user_limit = min(len(user["content"].encode("utf-8")), max(96, content_budget // 4))
    user_text, user_cut = _fit_original(user["content"], user_limit)
    answer_limit = content_budget - len(user_text.encode("utf-8"))
    intro = ""
    intro_piece = ""
    if first["id"] != target["id"] and answer_limit >= 320:
        intro_piece = _prefix(first["content"], min(320, answer_limit // 4))
        intro = f"[Début original du segment #{first['id']}, extrait]\n{intro_piece}\n[Dernier segment #{target['id']}]\n"
    answer_text, answer_cut = _fit_original(target["content"], answer_limit - len(intro.encode("utf-8")))
    chain_size = sum(len(f"[Segment original #{record['id']}]\n".encode("utf-8"))
                     + len(record["content"].encode("utf-8")) for _question, record in chain) + 2 * (len(chain) - 1)
    full_chain = len(chain) > 1 and chain_size <= answer_limit
    whole_chain = ("\n\n".join(f"[Segment original #{record['id']}]\n{record['content']}"
                                for _question, record in chain) if full_chain else "")
    if full_chain:
        intro = intro_piece = ""
        answer_text, answer_cut = target["content"], False
    pinned_user = {**user, "content": user_text}
    pinned_answer = {**target, "content": whole_chain if full_chain else intro + answer_text}
    # Earlier incomplete turns are never silently treated as complete. Only the
    # explicitly requested target/ancestor chain receives this exception.
    earlier = []
    target_index = next(i for i, row in enumerate(rows) if row["id"] == target["id"])
    chain_ids = {record["id"] for _question, record in chain}
    for i in range(0, target_index - 1, 2):
        pair = rows[i:i + 2]
        if ([row.get("role") for row in pair] == ["user", "assistant"]
                and pair[1].get("status") == "complete"
                and pair[1]["id"] not in chain_ids):
            earlier.extend(pair)
    result = ContextBuilder(settings).build(earlier + [pinned_user, pinned_answer, current], memories)
    # The last pair fits by construction. Check defensively against future budget
    # changes; never return a continuation that dropped its only current passage.
    if len(result.messages) < 3 or result.messages[-2]["content"] != pinned_answer["content"]:
        raise ValueError("Le contexte n'a pas conservé le passage à continuer.")
    result.sources = [source for source in result.sources if source.get("message_id") not in {user["id"], target["id"]}]
    for source in result.sources:
        if source.get("message_id") in chain_ids:
            source["method"] = "continuation_original"
    result.sources.extend((_provenance(user, user_text, user_cut),
                           _provenance(target, answer_text, answer_cut)))
    if intro_piece:
        result.sources.append(_provenance(first, intro_piece, True))
    elif full_chain:
        result.sources.extend(_provenance(record, record["content"], False) for _question, record in chain[:-1])
    limitations = ["Continuité demandée au modèle, sans garantie automatique d'absence de contradiction."]
    excerpted = user_cut or answer_cut or (len(chain) > 1 and not full_chain)
    if excerpted:
        limitations.append("Extraits originaux non exhaustifs ; passages intermédiaires omis pour respecter le contexte.")
    result.stats["context_strategy"] = "continuation"
    result.stats["continuation"] = {"target_message_id": target["id"],
        "source_user_id": user["id"], "original_status": target["status"],
        "excerpted": excerpted, "chain_depth": len(chain), "limitations": limitations}
    return result
