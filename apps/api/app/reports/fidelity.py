"""Numeric fidelity: every number a report states must exist in the stored results.

Reuses the agent's grounding engine (same tolerance and rounding rules the Verification
Agent applied when the insights were first written). It runs when a report is read or
exported, not just when it is saved, so an edited summary is checked too.
"""

from __future__ import annotations

from typing import Any

from app.agent.tools.grounding import Grounder, numbers_in

VERIFIED = "verified"
FLAGGED = "flagged"
NOT_CHECKABLE = "not_checkable"
MIN_VERSION = 2  # v1 snapshots stored no result rows to check against


def allowed_values(content: dict[str, Any]) -> list[float]:
    """Every number the stored analysis actually produced."""
    values: list[float] = []
    for step in content.get("steps") or []:
        values.extend(numbers_in(step.get("rows") or []))
        if isinstance(step.get("row_count"), int):
            values.append(float(step["row_count"]))
    for fact in content.get("facts") or []:
        values.extend(numbers_in(fact.get("value")))
        supporting = fact.get("supporting") or {}
        values.extend(numbers_in(supporting))
        before, after = supporting.get("before"), supporting.get("after")
        if isinstance(before, int | float) and isinstance(after, int | float) and before:
            values.append(after / before)
    for chart in content.get("charts") or []:
        values.extend(numbers_in(chart.get("data") or []))
    return values


def check_report(content: dict[str, Any], summary: str) -> dict[str, Any]:
    """Compare the report's narrative numbers with the stored results.

    Returns ``{"status", "checked", "issues": [{"where", "numbers"}]}``. Findings and
    recommendations were verified when written, so they should always pass; the summary
    is what a user can edit, and is where drift would show up.
    """
    if content.get("version", 1) < MIN_VERSION or not content.get("steps"):
        return {"status": NOT_CHECKABLE, "checked": 0, "issues": []}
    allowed = allowed_values(content)
    dataset = content.get("dataset") or {}
    context = " ".join(
        str(x)
        for x in (
            content.get("question"),
            dataset.get("name"),
            (content.get("methodology") or {}).get("time_range"),
        )
        if x
    )
    grounder = Grounder([], {}, context)
    texts: list[tuple[str, str]] = [("Executive summary", summary)]
    texts += [
        (f"Finding: {f['headline']}", f"{f['headline']}\n{f['detail']}")
        for f in content.get("findings") or []
    ]
    texts += [
        (f"Recommendation: {r['headline']}", f"{r['headline']}\n{r['detail']}")
        for r in content.get("recommendations") or []
    ]
    issues = []
    for where, text in texts:
        bad = grounder.ungrounded_numbers(text, allowed)
        if bad:
            issues.append({"where": where, "numbers": bad})
    return {"status": FLAGGED if issues else VERIFIED, "checked": len(texts), "issues": issues}
