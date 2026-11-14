"""Deterministic grounding checks (Verification agent, pass 1: authoritative).

Every number written in an insight must equal a value from the evidence the insight
cites: a computed fact (and its supporting values) or a cited result cell, allowing for
display rounding ("$1.2M" for 1,234,567, "12.5%" for 12.47). Years, dates and small
counts are allowed only when they appear in the question or its time range.
Evidence ids must exist, causal wording needs explicit support, and recommendations
must be phrased conditionally. Anything that fails is rejected with a reason code.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.agent.state import ComputedFact, EvidenceRef, Insight, StepResult
from app.agent.tools.analysis import to_number

_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?(?:[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?\b")
_NUMBER = re.compile(
    r"(?<![\w.])(?P<sign>[-−+])?(?P<cur>[$€£₹])?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<suffix>%|percent\b|pp\b|[kKmMbB](?![a-zA-Z])|x(?![a-zA-Z])|"
    r"thousand\b|million\b|billion\b))?"
)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
_CAUSAL = re.compile(
    r"\b(because|due to|caused by|as a result of|resulted in|led to|leads to|causes?)\b",
    re.IGNORECASE,
)
_CONDITIONAL = re.compile(r"\b(consider|may|might|could|worth|investigate|review|explore)\b", re.I)
SMALL_COUNT = 20
REL_TOLERANCE = 0.005
MAX_FRACTION = 1.5  # values this small may be fractions written as percentages
YEAR_RANGE = (1900, 2100)


@dataclass(frozen=True)
class NumberToken:
    raw: str
    value: float
    decimals: int
    scale: float
    percent: bool
    multiplier: bool
    plain_integer: bool


def extract_numbers(text: str) -> list[NumberToken]:
    stripped = _DATE.sub(" ", text)
    tokens = []
    for m in _NUMBER.finditer(stripped):
        digits = m.group("num").replace(",", "")
        suffix = (m.group("suffix") or "").lower()
        scale = _SCALE.get(suffix, 1.0)
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        value = float(digits) * scale
        if m.group("sign") in {"-", "−"}:
            value = -value
        tokens.append(
            NumberToken(
                raw=m.group(0).strip(),
                value=value,
                decimals=decimals,
                scale=scale,
                percent=suffix in {"%", "percent", "pp"},
                multiplier=suffix == "x",
                plain_integer=not suffix and not m.group("cur") and decimals == 0,
            )
        )
    return tokens


def numbers_in(value: Any) -> Iterable[float]:
    if isinstance(value, dict):
        for v in value.values():
            yield from numbers_in(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from numbers_in(v)
    else:
        number = to_number(value)
        if number is not None:
            yield number


def _matches(token: NumberToken, allowed: Iterable[float]) -> bool:
    tolerance_display = 0.5 * 10 ** (-token.decimals) * token.scale
    for a in allowed:
        candidates = {a, abs(a)}
        if token.percent and abs(a) <= MAX_FRACTION:
            candidates |= {a * 100, abs(a) * 100}
        for c in candidates:
            tol = max(REL_TOLERANCE * abs(c), tolerance_display, 1e-9)
            if math.isclose(abs(token.value), abs(c), abs_tol=tol):
                return True
    return False


class Grounder:
    def __init__(
        self,
        facts: list[ComputedFact],
        steps: dict[str, StepResult],
        context_text: str,
    ) -> None:
        self.facts = {f.fact_id: f for f in facts}
        self.steps = steps
        self.context_text = context_text
        self._context_numbers = {t.value for t in extract_numbers(_DATE.sub(" ", context_text))}
        self._context_years = set(re.findall(r"\b(19\d{2}|20\d{2}|2100)\b", context_text))

    # --------------------------------------------------------------- evidence
    def evidence_problems(self, evidence: list[EvidenceRef]) -> list[str]:
        problems = []
        for ref in evidence:
            if ref.kind == "fact":
                if not ref.fact_id or ref.fact_id not in self.facts:
                    problems.append(f"UNKNOWN_EVIDENCE {ref.fact_id}")
                continue
            step = self.steps.get(ref.step_id or "")
            if step is None or step.status != "succeeded":
                problems.append(f"UNKNOWN_EVIDENCE step {ref.step_id}")
                continue
            names = [c for c, _ in step.columns]
            if ref.column is not None and ref.column not in names:
                problems.append(f"UNKNOWN_EVIDENCE column {ref.step_id}.{ref.column}")
            if ref.row_index is not None and not 0 <= ref.row_index < len(step.preview_rows):
                problems.append(f"UNKNOWN_EVIDENCE row {ref.step_id}[{ref.row_index}]")
        return problems

    def allowed_values(self, evidence: list[EvidenceRef]) -> list[float]:
        values: list[float] = []
        for ref in evidence:
            if ref.kind == "fact" and ref.fact_id in self.facts:
                fact = self.facts[ref.fact_id or ""]
                values.extend(numbers_in(fact.value))
                values.extend(numbers_in(fact.inputs.get("supporting", {})))
                supporting = fact.inputs.get("supporting", {})
                before, after = supporting.get("before"), supporting.get("after")
                if isinstance(before, int | float) and isinstance(after, int | float) and before:
                    values.append(after / before)  # "1.4x"
            elif ref.kind == "cell":
                step = self.steps.get(ref.step_id or "")
                if step is None or step.status != "succeeded":
                    continue
                names = [c for c, _ in step.columns]
                rows = (
                    step.preview_rows
                    if ref.row_index is None
                    else step.preview_rows[ref.row_index : ref.row_index + 1]
                )
                for row in rows:
                    if ref.column is None:
                        values.extend(numbers_in(row))
                    elif ref.column in names:
                        values.extend(numbers_in(row[names.index(ref.column)]))
        return values

    # ---------------------------------------------------------------- numbers
    def ungrounded_numbers(self, text: str, allowed: list[float]) -> list[str]:
        bad = []
        for token in extract_numbers(text):
            if token.plain_integer:
                if (
                    YEAR_RANGE[0] <= token.value <= YEAR_RANGE[1]
                    and token.raw.lstrip("+-−") in self._context_years
                ):
                    continue
                if abs(token.value) <= SMALL_COUNT and abs(token.value) in self._context_numbers:
                    continue
            if not _matches(token, allowed):
                bad.append(token.raw)
        return bad

    def check_insight(self, insight: Insight) -> list[str]:
        reasons = self.evidence_problems(insight.evidence)
        allowed = self.allowed_values(insight.evidence)
        text = f"{insight.headline}\n{insight.detail}"
        reasons += [f"UNGROUNDED_NUMBER {raw}" for raw in self.ungrounded_numbers(text, allowed)]
        if insight.category != "caveat" and (m := _CAUSAL.search(text)):
            reasons.append(f"UNSUPPORTED_CAUSAL_CLAIM “{m.group(0)}”")
        if insight.category == "recommendation" and not _CONDITIONAL.search(text):
            reasons.append("NON_CONDITIONAL_RECOMMENDATION")
        return reasons
