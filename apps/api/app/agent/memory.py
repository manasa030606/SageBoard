"""Conversation memory: what a finished turn leaves behind, and what a new question gets back.

Design (D53):

* **Storing.** When a turn finishes, :func:`build_turn_memory` distils it into a small,
  structured record (question, restated question, metrics, dimensions, filters, period,
  tables, the SQL that answered it, verified headlines, the answer). It is built by code
  from what the run really produced, never by a model, so a memory can't contain anything
  the run didn't establish. Old sessions without a stored record are distilled the same
  way on demand.
* **Retrieving.** :func:`select_relevant` looks back over a bounded window of earlier
  turns and returns only the ones that matter to the new question: the previous turn when
  the question refers back to it ("compare *it* with last month", "and by region?"), plus
  earlier turns that share real topic words. An unrelated question gets no prior context.
* **Isolation.** This module only ranks what it is given. The caller
  (``AgentRunner._conversation_context``) fetches candidates with the owner, dataset and
  conversation of the running session in the WHERE clause, so a turn from another user,
  dataset or conversation is never even a candidate. Turns recorded against another
  version of the dataset keep their *shape* (so "and by region?" still resolves) but lose
  their numbers.
"""

from __future__ import annotations

import json
import re
from typing import Any

MEMORY_VERSION = 1
SCAN_TURNS = 20  # how many earlier turns are considered at all
MAX_RELEVANT = 3  # how many are handed to the agent
CONTEXT_CHARS = 3500  # serialized budget for the whole prior-context block
MIN_OVERLAP = 0.34  # share of the question's topic words a turn must cover

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "get",
        "give",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "over",
        "per",
        "please",
        "show",
        "tell",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "up",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "all",
        "any",
        "each",
        "every",
        "some",
        "more",
        "most",
        "less",
        "least",
        "much",
        "many",
        "also",
        "just",
        "about",
        "between",
    ]
)

# A question that points back at the previous turn rather than standing alone.
_PRONOUN = re.compile(r"\b(it|its|that|this|these|those|them|they|same|former|latter)\b", re.I)
_OPENER = re.compile(
    r"^\s*(and|also|now|then|but|so|what about|how about|what if|compare|break|split|"
    r"drill|show (?:me )?(?:the )?(?:same|that|it|this))\b",
    re.I,
)
_CONTINUATION = re.compile(
    r"\b(compare|compared|versus|vs\.?|instead|previous|previously|prior|earlier|before|"
    r"again|as well|rather|same (?:thing|metric|analysis)|that one|the other)\b",
    re.I,
)
_SHORT_WORDS = 5  # "by region?" "and last year?" depend on the turn before them
_MIN_WORD = 3  # shorter words carry no topic ("by", "of", "to")


def content_tokens(text: str) -> set[str]:
    """Lower-cased topic words: no stop words, plurals folded (``regions`` → ``region``)."""
    out: set[str] = set()
    for raw in _WORD.findall(text.lower()):
        if raw in _STOP or len(raw) < _MIN_WORD:
            continue
        plural = len(raw) > _MIN_WORD and raw.endswith("s") and not raw.endswith("ss")
        out.add(raw[:-1] if plural else raw)
    return out


def followup_reason(question: str) -> str | None:
    """Why this question looks like it depends on the previous turn, or ``None``."""
    text = question.strip()
    if m := _OPENER.match(text):
        return f"starts with “{m.group(1).lower()}”"
    if m := _PRONOUN.search(text):
        return f"refers back with “{m.group(1).lower()}”"
    if m := _CONTINUATION.search(text):
        return f"continues the previous analysis (“{m.group(1).lower()}”)"
    if len(_WORD.findall(text.lower())) <= _SHORT_WORDS:
        return "too short to stand alone"
    return None


# ------------------------------------------------------------------------ storing


def _clip(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_turn_memory(
    *,
    question: str,
    understanding: dict[str, Any] | None,
    result: dict[str, Any] | None,
    final_summary: str | None,
    dataset_version: int,
) -> dict[str, Any]:
    """Distil one finished turn into a compact, structured memory record."""
    u = understanding or {}
    r = result or {}
    response = r.get("response") or {}
    steps = r.get("steps") or []
    sql = [
        {
            "step": s.get("step_id"),
            "purpose": _clip(s.get("purpose"), 120),
            "sql": _clip(s.get("sql"), 700),
        }
        for s in steps
        if s.get("status") == "succeeded" and s.get("sql")
    ][-2:]
    findings = [
        _clip(f.get("headline"), 160)
        for f in (response.get("key_findings") or [])
        if f.get("category") != "caveat"
    ][:3]
    tables = list(r.get("schema_tables") or [])
    memory: dict[str, Any] = {
        "v": MEMORY_VERSION,
        "question": _clip(question, 300),
        "restated": _clip(u.get("restated_question"), 300) or None,
        "intent": u.get("intent"),
        "metrics": list(u.get("metrics") or []),
        "dimensions": list(u.get("dimensions") or []),
        "filters": list(u.get("filters") or []),
        "time_range": u.get("time_range"),
        "tables": tables,
        "sql": sql,
        "findings": findings,
        "answer": _clip(final_summary, 600) or None,
        "dataset_version": dataset_version,
    }
    keyword_source = " ".join(
        [
            question,
            memory["restated"] or "",
            *memory["metrics"],
            *memory["dimensions"],
            *memory["filters"],
            *tables,
        ]
    )
    memory["keywords"] = sorted(content_tokens(keyword_source))[:40]
    return memory


# ---------------------------------------------------------------------- retrieving


def _overlap(question_tokens: set[str], keywords: set[str]) -> tuple[float, list[str]]:
    shared = sorted(question_tokens & keywords)
    if not question_tokens:
        return 0.0, []
    return len(shared) / len(question_tokens), shared


def _size(entry: dict[str, Any]) -> int:
    return len(json.dumps(entry, default=str))


def _fit(entries: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """Shrink the least important parts first until the block fits the budget."""
    for field in ("sql", "findings", "answer"):
        if sum(_size(e) for e in entries) <= budget:
            break
        for entry in entries:
            entry.pop(field, None)
    return entries


def select_relevant(
    question: str,
    turns: list[dict[str, Any]],
    *,
    dataset_version: int,
    limit: int = MAX_RELEVANT,
    budget: int = CONTEXT_CHARS,
) -> list[dict[str, Any]]:
    """Pick the earlier turns that bear on ``question``.

    ``turns`` are memory records, oldest first, all from this conversation. The result is
    chronological and carries a ``relevance`` note per turn saying why it was included.
    """
    window = turns[-SCAN_TURNS:]
    if not window:
        return []
    q_tokens = content_tokens(question)
    reason = followup_reason(question)

    chosen: dict[int, str] = {}
    if reason:
        chosen[len(window) - 1] = f"the question {reason}, so the previous turn is included"
    scored: list[tuple[float, int, list[str]]] = []
    for index, turn in enumerate(window):
        if index in chosen:
            continue
        score, shared = _overlap(q_tokens, set(turn.get("keywords") or []))
        if shared and score >= MIN_OVERLAP:
            scored.append((score, index, shared))
    # Best topical match first; on a tie the more recent turn wins.
    for _score, index, shared in sorted(scored, key=lambda s: (-s[0], -s[1])):
        if len(chosen) >= limit:
            break
        chosen[index] = "shares topic words: " + ", ".join(shared)

    entries: list[dict[str, Any]] = []
    for index in sorted(chosen):
        entry = {k: v for k, v in window[index].items() if k not in ("keywords", "v")}
        entry["relevance"] = chosen[index]
        if entry.get("dataset_version") != dataset_version:
            # Same conversation, different data: keep the question's shape, drop its numbers.
            for field in ("answer", "findings", "sql"):
                entry.pop(field, None)
            entry["stale"] = (
                "the dataset changed after this turn, so its results are not carried over"
            )
        entries.append(entry)
    return _fit(entries, budget)
