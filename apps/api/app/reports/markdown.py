"""Markdown export of a report (same sections as the PDF)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.reports.fidelity import FLAGGED


def _fence(sql: str) -> str:
    return "```sql\n" + sql.replace("```", "``\u200b`") + "\n```"


def render_markdown(  # noqa: PLR0912 - one linear document
    *,
    title: str,
    summary: str,
    content: dict[str, Any],
    fidelity: dict[str, Any],
    saved_at: datetime,
) -> str:
    dataset = content.get("dataset") or {}
    method = content.get("methodology") or {}
    lines = [f"# {title}", ""]
    meta = [f"Question: {content.get('question', '')}"]
    if dataset.get("name"):
        meta.append(f"Dataset: {dataset['name']} (version {dataset.get('version')})")
    meta.append(f"Saved: {saved_at:%Y-%m-%d %H:%M} UTC")
    lines += [f"- {m}" for m in meta] + [""]
    if dataset.get("tables"):
        lines += (
            ["## Dataset", ""]
            + [f"- {t['name']}: {t['rows']:,} rows" for t in dataset["tables"]]
            + [""]
        )
    if summary:
        lines += ["## Executive summary", "", summary, ""]
    if fidelity.get("status") == FLAGGED:
        lines += ["> **Numbers not found in the stored results:**"]
        lines += [f"> - {i['where']}: {', '.join(i['numbers'])}" for i in fidelity["issues"]] + [""]
    if method:
        lines += ["## Analysis methodology", ""]
        for label, key in (("Intent", "intent"), ("Time range", "time_range")):
            if method.get(key):
                lines.append(f"- {label}: {method[key]}")
        for label, key in (
            ("Metrics", "metrics"),
            ("Dimensions", "dimensions"),
            ("Filters", "filters"),
        ):
            if method.get(key):
                lines.append(f"- {label}: {', '.join(method[key])}")
        lines += [f"- {s['step_id']}: {s['purpose']}" for s in method.get("plan_steps") or []] + [
            ""
        ]
    steps = [s for s in content.get("steps") or [] if s.get("sql")]
    queries = content.get("queries") or []
    if steps or queries:
        lines += ["## SQL queries", ""]
        for i, q in enumerate(steps or queries, 1):
            rows = q.get("row_count")
            lines += [
                f"Query {i}" + (f" ({rows} rows)" if rows is not None else ""),
                "",
                _fence(q["sql"]),
                "",
            ]
    if content.get("findings"):
        lines += ["## Key findings", ""]
        lines += [f"- **{f['headline']}** {f['detail']}" for f in content["findings"]] + [""]
    if content.get("charts"):
        lines += (
            ["## Visualizations", ""]
            + [f"- {c['title']} ({c['chart_type']})" for c in content["charts"]]
            + [""]
        )
    if content.get("recommendations"):
        lines += ["## Business recommendations", ""]
        lines += [f"- **{r['headline']}** {r['detail']}" for r in content["recommendations"]] + [""]
    limits = content.get("limitations")
    if limits is None and content.get("status") == "partial":
        limits = ["This analysis finished partially; some steps did not complete."]
    if limits:
        lines += ["## Limitations", ""] + [f"- {x}" for x in limits] + [""]
    return "\n".join(lines).rstrip() + "\n"
