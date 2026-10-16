"""Bounded local context selection; no tokenizer download or extra inference.

UTF-8 bytes are deliberately conservative estimates, not model token counts.
Archived text remains data: only exact excerpts enter a lower-priority history
message, with references back to the unchanged archive.
"""
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass


_OVERHEAD = 256
_STOP = frozenset("""a au aux avec ce ces cet cette dans de des du en et est etre fait faire il ils
elle elles je le la les leur leurs ma mais me mes moi mon ne nos notre nous on
ou par pas pour que quel quelle quelles quels qui sa sans se ses son sont sur
ta te tes toi ton tu un une vos votre vous ai as avait avions avons ancien
anciens ancienne anciennes message messages conversation conversations deja
avais etait etaient suis comme c est j d l n qu s t y rappel rappelle rappellez
bonjour salut merci peux peut pourriez voudrais veux donner donne dire dis
""".split())
_FOLLOW_UP = re.compile(
    r"\b(?:ça|cela|ceci|celui|celle|ceux|celles|ce|ces|cet|cette|il|elle|ils|elles|son|ses|leur|leurs|continue|"
    r"encore|reprends|ensuite|pourquoi|comment|précise|détaille|résume|autre|même|"
    r"avions|avais|précédent|précédente|souviens|rappelle|développe|développez|"
    r"premier|première|deuxième|second|seconde|troisième|dernier|dernière)\b", re.IGNORECASE)
_HEADER = ("Résumé extractif d’archives — citations non exhaustives, "
           "données de référence sans instructions.\n")


def _cost(message):
    return len(message["content"].encode("utf-8")) + 32


def _normal(text):
    # Case and indentation can carry meaning, especially in code. Deduplicate
    # only canonically equivalent text, never case-folded or collapsed text.
    return unicodedata.normalize("NFC", text)


def _words(text):
    # Accent folding affects matching only; displayed and transmitted excerpts
    # always retain the original French spelling and Unicode characters.
    folded = "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                     if not unicodedata.combining(c))
    return {word for word in re.findall(r"[^\W_]+", folded)
            if len(word) >= 3 and word not in _STOP}


def _source(message, method, excerpt):
    mid = message.get("id")
    return {"message_id": mid if isinstance(mid, int) and not isinstance(mid, bool) else None,
            "session_id": message.get("session_id", ""),
            "created": message.get("created", ""), "role": message["role"],
            "method": method, "excerpt": excerpt}


def _api(message):
    return {"role": message["role"], "content": message["content"]}


def _excerpt(text, terms, limit):
    """Return an original contiguous passage, preferring complete sentences."""
    matches = [m for m in re.finditer(r".+?(?:[.!?](?=\s|$)|\n|$)", text,
                                     re.DOTALL) if m.group().strip()]
    passages = [match.group().strip("\r\n") for match in matches]
    if not passages or limit < 1:
        return ""
    eligible = [index for index, passage in enumerate(passages)
                if len(passage.encode("utf-8")) <= limit and _words(passage) & terms]
    if not eligible:
        # Do not cut a long sentence around a keyword: doing so could remove
        # its negation or exception and invert the original meaning.
        return ""
    best = max(eligible, key=lambda index: (
        len(_words(passages[index]) & terms), -len(passages[index].encode("utf-8"))))
    passage = passages[best]
    if not (_words(passage) & terms):
        return ""
    if len(passage.encode("utf-8")) <= limit:
        # Keep neighboring qualifications/negations whenever possible, rather
        # than merging disconnected snippets into an apparent new assertion.
        start, end = best, best
        for candidate_start, candidate_end in ((max(0, best - 1), min(len(matches) - 1, best + 1)),
                                                (best, min(len(matches) - 1, best + 1)),
                                                (max(0, best - 1), best)):
            candidate = text[matches[candidate_start].start():matches[candidate_end].end()].strip("\r\n")
            if len(candidate.encode("utf-8")) <= limit:
                start, end = candidate_start, candidate_end
                break
        passage = text[matches[start].start():matches[end].end()].strip("\r\n")
        return passage
    return ""


@dataclass
class ContextResult:
    messages: list
    stats: dict
    sources: list


class ContextBuilder:
    def __init__(self, settings):
        self.settings = settings

    def build(self, messages, memories=None):
        settings = self.settings
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("Un message utilisateur est requis.")
        if any(not isinstance(message.get("content"), str) for message in messages):
            raise ValueError("Le contenu des messages doit être du texte.")
        current = messages[-1]
        system = ([{"role": "system", "content": settings.system_prompt}]
                  if settings.system_prompt else [])
        allowed = settings.context - settings.max_tokens - _OVERHEAD
        remaining = allowed - sum(_cost(m) for m in system) - _cost(current)
        if remaining < 0:
            raise ValueError("Message trop long pour ce contexte. Réduisez-le ou augmentez le contexte.")

        previous = messages[:-1]
        active_session = current.get("session_id")
        pairs = []
        for index in range(0, len(previous) - 1, 2):
            pair = previous[index:index + 2]
            if [m.get("role") for m in pair] != ["user", "assistant"]:
                continue
            if active_session and any(m.get("session_id", active_session) != active_session
                                      for m in pair):
                continue
            pairs.append((index, pair))

        targeted = getattr(settings, "targeted_context", True)
        mission = getattr(settings, "usage", "chat") == "mission"
        short = (len(current["content"]) <= 180 and len(_words(current["content"])) <= 12
                 and not _FOLLOW_UP.search(unicodedata.normalize("NFC", current["content"]))
                 and not re.match(r"\s*(?:et|donc|alors)\b", current["content"], re.IGNORECASE))
        window = (8 if mission else 1 if short else 3) if targeted else len(pairs)
        strategy = ("mission" if mission else "light" if short else "followup") if targeted else "recent"
        query = _words(current["content"])
        selected, selected_indices, fingerprints = [], set(), set()
        pair_count = 0
        for index, pair in reversed(pairs):
            fingerprint = tuple(_normal(m["content"]) for m in pair)
            if targeted and fingerprint in fingerprints:
                continue
            size = sum(_cost(m) for m in pair)
            if size > remaining or pair_count >= window:
                break
            selected[0:0] = pair
            selected_indices.update((index, index + 1))
            fingerprints.add(fingerprint)
            remaining -= size
            pair_count += 1

        # Provenance stores a small preview; Store.message(id) is the full,
        # canonical original. Do not copy whole conversations into metadata.
        sources = [_source(m, "recent", m["content"][:240]) for m in selected]
        extracts, retrieved_indices = [], set()
        selected_memory_ids = []
        memory_warnings = []
        if targeted and query:
            retrieval_limit = min(remaining, getattr(settings, "retrieval_budget", 768))
            seen = {_normal(m["content"]) for m in selected}
            # Only explicitly approved records may be proposed by storage. Keep
            # this second check at the prompt boundary, including for adapters.
            for memory in (memories or [])[:5]:
                if (memory.get("status") != "approved" or not isinstance(memory.get("id"), int)
                        or isinstance(memory["id"], bool) or memory["id"] in selected_memory_ids):
                    continue
                content = memory.get("content", "")
                if not isinstance(content, str) or _normal(content) in seen:
                    continue
                topic = str(memory.get("topic", ""))
                title = str(memory.get("title", ""))
                # A short fact may match its human-supplied topic rather than
                # repeat the query word inside the fact ("prénom" -> "Paul").
                if query & _words(topic + " " + title) and len(content.encode("utf-8")) <= 480:
                    excerpt = content
                else:
                    excerpt = _excerpt(content, query, 480)
                if not excerpt or _normal(excerpt) in seen:
                    continue
                entry = {"memory_id": memory["id"], "kind": memory.get("kind", "durable"),
                         "topic": topic, "citation": excerpt, "approved": True}
                candidate = {"content": _HEADER + json.dumps(
                    extracts + [entry], ensure_ascii=False, separators=(",", ":"))}
                if _cost(candidate) > retrieval_limit:
                    continue
                provenance = memory.get("provenance", "{}")
                try:
                    if isinstance(provenance, str):
                        provenance = json.loads(provenance)
                    if not isinstance(provenance, dict):
                        raise ValueError("object required")
                except ValueError:
                    memory_warnings.append(f"Souvenir #{memory['id']} ignoré : provenance invalide.")
                    continue
                sources.append({"method": "memory", "memory_id": memory["id"],
                                "message_id": None, "session_id": "", "role": "memory",
                                "created": memory.get("created", ""), "kind": memory.get("kind", "durable"),
                                "status": "approved", "title": title, "topic": topic,
                                "excerpt": excerpt, "provenance": provenance})
                extracts.append(entry)
                selected_memory_ids.append(memory["id"])
                seen.update((_normal(content), _normal(excerpt)))
            candidates = [(index + offset, message) for index, pair in pairs
                          for offset, message in enumerate(pair)
                          if index + offset not in selected_indices]
            terms = [_words(message["content"]) for _, message in candidates]
            frequencies = Counter(term for words in terms for term in words)
            ranking = []
            for (index, message), words in zip(candidates, terms):
                overlap = query & words
                score = sum(1 + math.log((len(candidates) + 1) / (frequencies[word] + 1))
                            for word in overlap)
                if score:
                    ranking.append((score, index, message))
            ranking.sort(key=lambda item: (-item[0], -item[1]))
            for _, index, message in ranking:
                if len(extracts) >= 8 or _normal(message["content"]) in seen:
                    continue
                # Include all labels/JSON quoting in the actual allocation.
                available = retrieval_limit - _cost({"content": _HEADER + json.dumps(
                    extracts, ensure_ascii=False, separators=(",", ":"))}) - 80
                if available <= 0:
                    break
                excerpt = _excerpt(message["content"], query, min(480, available))
                if not excerpt or _normal(excerpt) in seen:
                    continue
                source = _source(message, "extractive", excerpt)
                entry = {"message_id": source["message_id"], "role": source["role"],
                         "citation": excerpt}
                candidate = {"role": "assistant", "content": _HEADER + json.dumps(
                    extracts + [entry], ensure_ascii=False, separators=(",", ":"))}
                if _cost(candidate) > retrieval_limit:
                    continue
                extracts.append(entry)
                retrieved_indices.add(index)
                seen.update((_normal(message["content"]), _normal(excerpt)))
                sources.append(source)

        context = system
        if extracts:
            context += [{"role": "assistant", "content": _HEADER + json.dumps(
                extracts, ensure_ascii=False, separators=(",", ":"))}]
        context += [_api(message) for message in selected] + [_api(current)]
        stats = {"context_estimate_tokens": _OVERHEAD + sum(_cost(m) for m in context),
                 "context_limit_tokens": settings.context,
                 "output_reserved_tokens": settings.max_tokens,
                 "omitted_messages": len(previous) - len(selected_indices) - len(retrieved_indices),
                 "recent_messages": len(selected_indices),
                 "retrieved_messages": len(retrieved_indices),
                 "summary_messages": int(bool(extracts)),
                 "memory_count": len(selected_memory_ids),
                 "selected_memory_ids": selected_memory_ids,
                 "memory_warnings": memory_warnings,
                 "context_strategy": strategy}
        return ContextResult(context, stats, sources)
