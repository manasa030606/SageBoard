"""Build the immutable report snapshot (v2) from what a finished analysis stored.

Everything in the snapshot is copied from the stored session (its ``result`` JSON, plan,
understanding and the SQL that actually ran); nothing is regenerated and no model is called,
so a report can only say what the analysis already established.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.db.models import AnalysisSession, Dataset, QueryExecution
from app.db.models.datasets import DatasetTable

SNAPSHOT_VERSION = 2
CHART_ROWS = 40  # rows kept per chart
TABLE_ROWS = 10  # rows kept per result table
MAX_TABLES = 4
RECOMMENDATION = "recommendation"
CAVEAT = "caveat"


def build_snapshot(
    run: AnalysisSession,
    dataset: Dataset | None,
    tables: Sequence[DatasetTable],
    queries: Sequence[QueryExecution],
) -> dict[str, Any]:
    result: dict[str, Any] = run.result or {}
    response: dict[str, Any] = result.get("response") or {}
    understanding: dict[str, Any] = run.understanding or {}
    plan: dict[str, Any] = run.plan or {}
    steps: list[dict[str, Any]] = result.get("steps") or []
    findings = [
        f for f in response.get("key_findings") or [] if f.get("verification") != "rejected"
    ]
    return {
        "version": SNAPSHOT_VERSION,
        "question": run.question,
        "status": run.status,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "dataset": {
            "name": dataset.name if dataset else None,
            "description": dataset.description if dataset else None,
            "version": run.dataset_version,
            "source_type": dataset.source_type if dataset else None,
            "tables": [
                {"name": t.display_name or t.table_name, "rows": int(t.row_count)} for t in tables
            ],
        },
        "executive_summary": run.final_summary or response.get("summary") or "",
        "methodology": {
            "restated_question": understanding.get("restated_question"),
            "intent": understanding.get("intent"),
            "metrics": understanding.get("metrics") or [],
            "dimensions": understanding.get("dimensions") or [],
            "filters": understanding.get("filters") or [],
            "time_range": understanding.get("time_range"),
            "plan_steps": [
                {"step_id": s.get("step_id"), "purpose": s.get("purpose")}
                for s in plan.get("steps") or []
            ],
            "analysis_tasks": plan.get("analysis_tasks") or [],
            "verification": _verification(result.get("verification")),
        },
        "steps": [
            {
                "step_id": s.get("step_id"),
                "purpose": s.get("purpose"),
                "status": s.get("status"),
                "sql": s.get("sql"),
                "row_count": s.get("row_count"),
                "truncated": bool(s.get("truncated")),
                "columns": [c.get("name") for c in s.get("columns") or []],
                "rows": (s.get("rows") or [])[:TABLE_ROWS],
            }
            for s in steps
        ],
        "findings": [
            {
                "headline": f.get("headline", ""),
                "detail": f.get("detail", ""),
                "category": f.get("category", "finding"),
                "confidence": f.get("confidence", "medium"),
                "verification": f.get("verification", "unverified"),
            }
            for f in findings
            if f.get("category") not in (RECOMMENDATION, CAVEAT)
        ],
        "recommendations": [
            {
                "headline": f.get("headline", ""),
                "detail": f.get("detail", ""),
                "confidence": f.get("confidence", "medium"),
            }
            for f in findings
            if f.get("category") == RECOMMENDATION
        ],
        "facts": [
            {
                "fact_id": f.get("fact_id"),
                "step_id": f.get("step_id"),
                "kind": f.get("kind"),
                "description": f.get("description"),
                "value": f.get("value"),
                "unit": f.get("unit"),
                "supporting": (f.get("inputs") or {}).get("supporting"),
            }
            for f in result.get("facts") or []
        ],
        "charts": [
            {
                "chart_type": c.get("chart_type"),
                "title": c.get("title"),
                "subtitle": c.get("subtitle"),
                "step_id": c.get("step_id"),
                "x": c.get("x"),
                "y": c.get("y") or [],
                "series": c.get("series"),
                "value_format": c.get("value_format") or "number",
                "columns": c.get("columns") or [],
                "data": (c.get("data") or [])[:CHART_ROWS],
                "rows_total": len(c.get("data") or []),
            }
            for c in result.get("charts") or []
        ],
        "limitations": _limitations(run, response, steps, result),
        # Kept so v1 consumers (and the Markdown export) still find the SQL list.
        "queries": [
            {"sql": q.executed_sql, "row_count": q.row_count, "truncated": q.truncated}
            for q in queries
            if q.executed_sql
        ],
    }


def _verification(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    return {
        "metrics_check": raw.get("metrics_check"),
        "time_period_check": raw.get("time_period_check"),
        "verified_insights": raw.get("verified_insights", 0),
        "rejected_insights": raw.get("rejected_insights", 0),
    }


def _limitations(
    run: AnalysisSession,
    response: dict[str, Any],
    steps: list[dict[str, Any]],
    result: dict[str, Any],
) -> list[str]:
    out: list[str] = []
    if run.status == "partial":
        out.append("This analysis finished partially; some steps did not complete.")
    for s in steps:
        if s.get("status") == "failed":
            out.append(
                f"Step {s.get('step_id')} failed: {s.get('failure_explanation') or 'no result'}."
            )
        elif s.get("truncated"):
            out.append(
                f"Step {s.get('step_id')} returned more rows than were kept; "
                "figures from it describe the rows returned."
            )
    out += [str(c) for c in response.get("caveats") or []]
    out += [f"Assumption: {a}" for a in response.get("assumptions") or []]
    verification = result.get("verification") or {}
    out += [str(u) for u in verification.get("uncertainty") or []]
    return list(dict.fromkeys(out))
