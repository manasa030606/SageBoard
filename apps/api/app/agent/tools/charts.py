"""Chart-spec validation (Visualization agent).

Charts are declarative ``ChartSpec`` objects rendered by the frontend; nothing the
model writes is executed (ADR-0005). A spec is only kept if it fits the actual result:
the columns exist, measures are numeric, a line chart has an ordered x axis, a pie has
few non-negative slices, a KPI has one row. Otherwise the step falls back to a table.
"""

from __future__ import annotations

import re

from app.agent.state import ChartSpec, StepResult
from app.agent.tools.analysis import to_number

NUMERIC_PG_TYPES = frozenset(
    {"int2", "int4", "int8", "numeric", "float4", "float8", "money", "integer", "bigint"}
)
ORDERED_PG_TYPES = NUMERIC_PG_TYPES | {"date", "timestamp", "timestamptz", "interval"}
DATE_LIKE = re.compile(r"^\d{4}(-\d{2}){0,2}([T ]\d{2}:\d{2}.*)?$|^\d{4}-?Q[1-4]$")
MAX_PIE_SLICES = 6
MAX_BAR_CATEGORIES = 50
MIN_HISTOGRAM_ROWS = 10
MIN_GROUPED_MEASURES = 2


def validate_chart(spec: ChartSpec, step: StepResult | None) -> list[str]:  # noqa: PLR0912, PLR0911 - one flat rule per chart type reads best
    if step is None or step.status != "succeeded":
        return [f"step {spec.step_id} has no successful result"]
    types = dict(step.columns)
    errors: list[str] = []
    for name in [spec.x, spec.series, *spec.y]:
        if name and name not in types:
            errors.append(f"column {name} is not in {spec.step_id}")
    if errors or spec.chart_type == "table":
        return errors
    if not spec.y:
        return ["a chart needs at least one measure (y)"]
    for y in spec.y:
        if types[y] not in NUMERIC_PG_TYPES:
            errors.append(f"{y} is {types[y]}, not numeric")
    if spec.chart_type == "kpi":
        if step.row_count != 1:
            errors.append("a KPI needs exactly one row")
        return errors
    if spec.chart_type == "histogram":
        # the frontend bins the single numeric column; no x axis in the spec
        if len(spec.y) != 1 or spec.series or spec.x:
            errors.append("a histogram shows the distribution of exactly one numeric column")
        if step.row_count < MIN_HISTOGRAM_ROWS:
            errors.append(
                f"a histogram needs ≥{MIN_HISTOGRAM_ROWS} rows (result has {step.row_count})"
            )
        return errors
    if not spec.x:
        return [*errors, f"{spec.chart_type} needs an x column"]
    if spec.chart_type in {"line", "area"} and not _ordered(spec.x, types[spec.x], step):
        errors.append(f"{spec.x} is not ordered (dates or numbers) for a line chart")
    if spec.chart_type == "scatter" and types[spec.x] not in NUMERIC_PG_TYPES:
        errors.append("a scatter plot needs a numeric x")
    if spec.chart_type in {"pie", "donut"}:
        kind = spec.chart_type
        if len(spec.y) != 1 or spec.series:
            errors.append(f"a {kind} shows one measure without series")
        if step.row_count > MAX_PIE_SLICES:
            errors.append(f"a {kind} needs ≤{MAX_PIE_SLICES} slices (result has {step.row_count})")
        i = [c for c, _ in step.columns].index(spec.y[0]) if spec.y else 0
        if any((to_number(r[i]) or 0) < 0 for r in step.preview_rows):
            errors.append(f"a {kind} can't show negative values")
    if spec.chart_type == "grouped_bar" and len(spec.y) < MIN_GROUPED_MEASURES and not spec.series:
        errors.append("a grouped bar needs two measures or a series column")
    if (
        spec.chart_type in {"bar", "grouped_bar", "horizontal_bar"}
        and step.row_count > MAX_BAR_CATEGORIES
    ):
        errors.append(f"too many categories for a bar chart ({step.row_count})")
    return errors


def _ordered(column: str, pg_type: str, step: StepResult) -> bool:
    if pg_type in ORDERED_PG_TYPES:
        return True
    i = [c for c, _ in step.columns].index(column)
    values = [str(r[i]) for r in step.preview_rows if r[i] is not None]
    return bool(values) and all(DATE_LIKE.match(v) for v in values)


def table_fallback(step: StepResult, title: str, reason: str) -> ChartSpec:
    return ChartSpec(
        chart_type="table", step_id=step.step_id, title=title[:120], fallback_reason=reason[:200]
    )
