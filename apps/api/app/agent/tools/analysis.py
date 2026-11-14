"""Deterministic analysis tools (Result Analysis agent).

The model only **selects** which calculation to run and on which columns; the
arithmetic happens here, in plain Python over the full stored result (not the
preview). Every output is a ``ComputedFact`` with an id the insights must cite, so
the Verification agent can check each number later (ADR-0005).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.agent.state import ComputedFact, clean_column_name

MAX_LIST_ITEMS = 25
MIN_TREND_POINTS = 2
MIN_CORRELATION_ROWS = 3
MIN_OUTLIER_ROWS = 4
PERIOD_PREFIX_CHARS = 7  # "2025-09"


class AnalysisToolError(ValueError):
    pass


@dataclass(frozen=True)
class ResultTable:
    step_id: str
    columns: list[str]
    rows: list[list[Any]]

    def index(self, column: str) -> int:
        try:
            return self.columns.index(column)
        except ValueError:
            raise AnalysisToolError(
                f"{self.step_id} has no column “{column}” (columns: {', '.join(self.columns)})"
            ) from None

    def values(self, column: str) -> list[Any]:
        i = self.index(column)
        return [row[i] for row in self.rows]

    def numbers(self, column: str) -> list[float]:
        out = [num for v in self.values(column) if (num := to_number(v)) is not None]
        if not out:
            raise AnalysisToolError(f"{self.step_id}.{column} has no numeric values")
        return out


def to_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _round(value: float, digits: int = 4) -> float:
    return round(value, digits)


def _pct(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return _round((after - before) / abs(before) * 100, 2)


# ------------------------------------------------------------------ call models


class ValueRef(BaseModel):
    """Either an earlier fact (``fact_id``) or one cell: a column in the row matching ``where``."""

    fact_id: str | None = None
    step_id: str | None = None
    column: str | None = None
    where: dict[str, str | int | float] = Field(default_factory=dict)

    @field_validator("column", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return clean_column_name(value)

    @field_validator("where", mode="before")
    @classmethod
    def _clean_keys(cls, value: object) -> object:
        return (
            {clean_column_name(k): v for k, v in value.items()}
            if isinstance(value, dict)
            else value
        )


class AnalysisCall(BaseModel):
    tool: Literal[
        "total",
        "average",
        "lookup",
        "pct_change",
        "share",
        "top_n",
        "group_change",
        "trend",
        "correlation",
        "outliers_iqr",
    ]
    step_id: str | None = None
    description: str = Field(max_length=200)
    column: str | None = None
    label_column: str | None = None
    value_column: str | None = None
    before_column: str | None = None
    after_column: str | None = None
    period_column: str | None = None
    before_period: str | None = None
    after_period: str | None = None
    x_column: str | None = None
    y_column: str | None = None
    where: dict[str, str | int | float] = Field(default_factory=dict)
    before: ValueRef | None = None
    after: ValueRef | None = None
    n: int = Field(default=5, ge=1, le=MAX_LIST_ITEMS)
    order: Literal["desc", "asc"] = "desc"
    unit: str | None = None

    @field_validator(
        "column",
        "label_column",
        "value_column",
        "before_column",
        "after_column",
        "period_column",
        "x_column",
        "y_column",
        mode="before",
    )
    @classmethod
    def _clean(cls, value: object) -> object:
        return clean_column_name(value)

    @field_validator("where", mode="before")
    @classmethod
    def _clean_keys(cls, value: object) -> object:
        return (
            {clean_column_name(k): v for k, v in value.items()}
            if isinstance(value, dict)
            else value
        )


# --------------------------------------------------------------------- engine


class AnalysisEngine:
    def __init__(self, tables: dict[str, ResultTable]) -> None:
        self.tables = tables
        self.facts: list[ComputedFact] = []

    def run(self, call: AnalysisCall) -> ComputedFact:
        handler: Callable[[AnalysisCall], tuple[Any, dict[str, float], dict[str, Any]]] = getattr(
            self, f"_{call.tool}"
        )
        value, supporting, inputs = handler(call)
        fact = ComputedFact(
            fact_id=f"f{len(self.facts) + 1}",
            step_id=call.step_id or (call.before.step_id if call.before else None) or "derived",
            kind=call.tool,
            description=call.description,
            value=value,
            unit=call.unit,
            inputs={**inputs, "supporting": supporting},
        )
        self.facts.append(fact)
        return fact

    # -- helpers
    def _table(self, call: AnalysisCall) -> ResultTable:
        if not call.step_id or call.step_id not in self.tables:
            raise AnalysisToolError(f"unknown or failed step “{call.step_id}”")
        return self.tables[call.step_id]

    @staticmethod
    def _need(call: AnalysisCall, *names: str) -> list[str]:
        values = [getattr(call, n) for n in names]
        missing = [n for n, v in zip(names, values, strict=True) if not v]
        if missing:
            raise AnalysisToolError(f"{call.tool} needs {', '.join(missing)}")
        return [str(v) for v in values]

    def _cell(self, table: ResultTable, column: str, where: dict[str, Any]) -> float:
        i = table.index(column)
        rows = table.rows
        for key, expected in where.items():
            k = table.index(key)
            rows = [r for r in rows if _same(r[k], expected)]
        if len(rows) != 1:
            raise AnalysisToolError(
                f"{table.step_id}: expected exactly one row for {where or 'the step'}, got {len(rows)}"
            )
        number = to_number(rows[0][i])
        if number is None:
            raise AnalysisToolError(f"{table.step_id}.{column} is not numeric in that row")
        return number

    def _resolve(self, ref: ValueRef | None) -> tuple[float, dict[str, Any]]:
        if ref is None:
            raise AnalysisToolError("pct_change needs before and after")
        if ref.fact_id:
            fact = next((f for f in self.facts if f.fact_id == ref.fact_id), None)
            if fact is None or not isinstance(fact.value, int | float):
                raise AnalysisToolError(f"{ref.fact_id} is not an earlier numeric fact")
            return float(fact.value), {"fact_id": ref.fact_id}
        if not ref.step_id or not ref.column or ref.step_id not in self.tables:
            raise AnalysisToolError("a value reference needs fact_id or step_id + column")
        value = self._cell(self.tables[ref.step_id], ref.column, ref.where)
        return value, ref.model_dump(exclude_none=True)

    # -- tools
    def _total(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        (column,) = self._need(call, "column")
        nums = self._table(call).numbers(column)
        return _round(math.fsum(nums)), {"count": len(nums)}, {"column": column}

    def _average(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        (column,) = self._need(call, "column")
        nums = self._table(call).numbers(column)
        return _round(statistics.fmean(nums)), {"count": len(nums)}, {"column": column}

    def _lookup(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        (column,) = self._need(call, "column")
        value = self._cell(self._table(call), column, call.where)
        return _round(value), {}, {"column": column, "where": call.where}

    def _pct_change(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        before, before_in = self._resolve(call.before)
        after, after_in = self._resolve(call.after)
        pct = _pct(before, after)
        if pct is None:
            raise AnalysisToolError("percentage change is undefined when the baseline is 0")
        supporting = {
            "before": _round(before),
            "after": _round(after),
            "change": _round(after - before),
        }
        return pct, supporting, {"before": before_in, "after": after_in}

    def _share(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        label, value = self._need(call, "label_column", "value_column")
        table = self._table(call)
        pairs = _pairs(table, label, value)
        total = math.fsum(v for _, v in pairs)
        if total == 0:
            raise AnalysisToolError("shares are undefined when the total is 0")
        items: list[dict[str, Any]] = sorted(
            (
                {"label": k, "value": _round(v), "share_pct": _round(v / total * 100, 2)}
                for k, v in pairs
            ),
            key=lambda d: float(d["value"]),
            reverse=True,
        )
        return items[:MAX_LIST_ITEMS], {"total": _round(total)}, {"label": label, "value": value}

    def _top_n(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        label, value = self._need(call, "label_column", "value_column")
        pairs = _pairs(self._table(call), label, value)
        items = sorted(pairs, key=lambda p: p[1], reverse=call.order == "desc")[: call.n]
        return (
            [{"rank": i + 1, "label": k, "value": _round(v)} for i, (k, v) in enumerate(items)],
            {},
            {"label": label, "value": value, "n": call.n, "order": call.order},
        )

    def _group_change(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        """Per-group change between two periods and each group's share of the total change."""
        table = self._table(call)
        (label,) = self._need(call, "label_column")
        if call.period_column:
            value, before_p, after_p = self._need(
                call, "value_column", "before_period", "after_period"
            )
            groups: dict[str, list[float]] = {}
            li, pi, vi = table.index(label), table.index(call.period_column), table.index(value)
            for row in table.rows:
                slot = 0 if _same(row[pi], before_p) else 1 if _same(row[pi], after_p) else None
                num = to_number(row[vi])
                if slot is None or num is None:
                    continue
                groups.setdefault(str(row[li]), [0.0, 0.0])[slot] += num
            inputs: dict[str, Any] = {
                "label": label,
                "period": call.period_column,
                "value": value,
                "before_period": before_p,
                "after_period": after_p,
            }
        else:
            before_c, after_c = self._need(call, "before_column", "after_column")
            li, bi, ai = table.index(label), table.index(before_c), table.index(after_c)
            groups = {}
            for row in table.rows:
                b, a = to_number(row[bi]) or 0.0, to_number(row[ai]) or 0.0
                pair = groups.setdefault(str(row[li]), [0.0, 0.0])
                pair[0] += b
                pair[1] += a
            inputs = {"label": label, "before": before_c, "after": after_c}
        if not groups:
            raise AnalysisToolError("no rows matched the two periods")
        total_before = math.fsum(g[0] for g in groups.values())
        total_after = math.fsum(g[1] for g in groups.values())
        total_change = total_after - total_before
        items: list[dict[str, Any]] = []
        for name, (b, a) in groups.items():
            change = a - b
            items.append(
                {
                    "label": name,
                    "before": _round(b),
                    "after": _round(a),
                    "change": _round(change),
                    "pct_change": _pct(b, a),
                    "contribution_pct": _round(change / total_change * 100, 2)
                    if total_change
                    else None,
                }
            )
        items.sort(key=lambda d: float(d["change"]), reverse=total_change >= 0)
        supporting = {
            "total_before": _round(total_before),
            "total_after": _round(total_after),
            "total_change": _round(total_change),
        }
        if (total_pct := _pct(total_before, total_after)) is not None:
            supporting["total_pct_change"] = total_pct
        return items[:MAX_LIST_ITEMS], supporting, inputs

    def _trend(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        x, y = self._need(call, "x_column", "y_column")
        table = self._table(call)
        xi, yi = table.index(x), table.index(y)
        points = [(r[xi], n) for r in table.rows if (n := to_number(r[yi])) is not None]
        if len(points) < MIN_TREND_POINTS:
            raise AnalysisToolError("a trend needs at least two points")
        numeric_x = all(to_number(p[0]) is not None for p in points)
        points.sort(key=lambda p: (to_number(p[0]) or 0.0, "") if numeric_x else (0.0, str(p[0])))
        first, last = points[0], points[-1]
        hi = max(points, key=lambda p: p[1])
        lo = min(points, key=lambda p: p[1])
        value = {
            "first_x": str(first[0]),
            "first": _round(first[1]),
            "last_x": str(last[0]),
            "last": _round(last[1]),
            "max_x": str(hi[0]),
            "max": _round(hi[1]),
            "min_x": str(lo[0]),
            "min": _round(lo[1]),
            "points": len(points),
        }
        supporting = {"change": _round(last[1] - first[1])}
        if (pct := _pct(first[1], last[1])) is not None:
            supporting["pct_change"] = pct
        return [value], supporting, {"x": x, "y": y}

    def _correlation(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        x, y = self._need(call, "x_column", "y_column")
        table = self._table(call)
        xi, yi = table.index(x), table.index(y)
        pairs = [
            (a, b)
            for r in table.rows
            if (a := to_number(r[xi])) is not None and (b := to_number(r[yi])) is not None
        ]
        if len(pairs) < MIN_CORRELATION_ROWS:
            raise AnalysisToolError("correlation needs at least three rows")
        try:
            r = statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs])
        except statistics.StatisticsError as exc:
            raise AnalysisToolError(f"correlation undefined: {exc}") from None
        return _round(r, 3), {"n": len(pairs)}, {"x": x, "y": y}

    def _outliers_iqr(self, call: AnalysisCall) -> tuple[Any, dict[str, float], dict[str, Any]]:
        label, value = self._need(call, "label_column", "value_column")
        pairs = _pairs(self._table(call), label, value)
        if len(pairs) < MIN_OUTLIER_ROWS:
            raise AnalysisToolError("outlier detection needs at least four rows")
        q1, _, q3 = statistics.quantiles([v for _, v in pairs], n=4, method="inclusive")
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = [
            {"label": k, "value": _round(v), "side": "high" if v > high else "low"}
            for k, v in pairs
            if v < low or v > high
        ]
        return (
            outliers[:MAX_LIST_ITEMS],
            {
                "q1": _round(q1),
                "q3": _round(q3),
                "low_fence": _round(low),
                "high_fence": _round(high),
            },
            {"label": label, "value": value},
        )


def _same(cell: Any, expected: Any) -> bool:
    if cell == expected:
        return True
    a, b = to_number(cell), to_number(expected)
    if a is not None and b is not None:
        return math.isclose(a, b, rel_tol=1e-9)
    text, wanted = str(cell), str(expected)
    # Period labels: "2025-09" matches a cell "2025-09-01T00:00:00+00:00".
    return text == wanted or (
        len(wanted) >= PERIOD_PREFIX_CHARS and wanted[:4].isdigit() and text.startswith(wanted)
    )


def _pairs(table: ResultTable, label: str, value: str) -> list[tuple[str, float]]:
    li, vi = table.index(label), table.index(value)
    pairs = [(str(r[li]), n) for r in table.rows if (n := to_number(r[vi])) is not None]
    if not pairs:
        raise AnalysisToolError(f"{table.step_id}.{value} has no numeric values")
    return pairs
