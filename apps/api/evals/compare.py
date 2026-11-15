"""Judge an agent result against the expected result.

The agent chooses its own column names, column order and (for time series) label format, so
comparison is value-based:

* numbers: integers must match exactly, other numbers within 0.01 or 0.01 % (whichever is larger);
* strings: case-insensitive equality; an expected ``YYYY-MM`` / ``YYYY-MM-DD`` also matches a
  longer ISO timestamp that starts with it;
* ``rows_ordered`` / ``rows_unordered``: each expected row must be *contained* in one result row
  (extra columns are fine) and the row counts must be equal;
* ``values_present``: every expected value must appear somewhere in the rows of any step.

Percent-versus-fraction is deliberately not forgiven: a share reported as 0.03 when 3.04 was
asked for counts as wrong, because a reader would be misled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

REL_TOL = 1e-4
ABS_TOL = 0.01


def norm(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, Decimal | float):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        return float(text) if re.fullmatch(r"-?\d+(\.\d+)?", text) else text
    return value


def _is_number(value: Any) -> bool:
    """Integers count as numeric cells too: a wrong count is a wrong number."""
    n = norm(value)
    return isinstance(n, int | float) and not isinstance(n, bool)


def _is_int(x: float) -> bool:
    return float(x).is_integer()


def matches(expected: Any, got: Any) -> bool:
    e, g = norm(expected), norm(got)
    if isinstance(e, bool) or isinstance(g, bool):
        return e is g
    if isinstance(e, int):
        e = float(e)
    if isinstance(g, int):
        g = float(g)
    if isinstance(e, float) and isinstance(g, float):
        if _is_int(e) and _is_int(g):
            return e == g
        return abs(e - g) <= max(ABS_TOL, abs(e) * REL_TOL)
    if isinstance(e, str) and isinstance(g, str):
        el, gl = e.lower(), g.lower()
        if el == gl:
            return True
        return (
            len(el) in (7, 10)
            and re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", el) is not None
            and gl.startswith(el)
        )
    return bool(e == g)


def _row_contains(expected_row: tuple[Any, ...], got_row: list[Any]) -> tuple[bool, int, int]:
    """(all matched, numeric cells matched, numeric cells expected)."""
    hits = total = 0
    ok = True
    for e in expected_row:
        found = any(matches(e, g) for g in got_row)
        numeric = _is_number(e)
        total += numeric
        hits += numeric and found
        ok &= found
    return ok, hits, total


@dataclass
class Comparison:
    exec_match: bool
    numeric_hits: int
    numeric_total: int
    step_id: str | None = None
    detail: str = ""
    missing: list[Any] = field(default_factory=list)


def _numeric_cells(expected: list[tuple[Any, ...]]) -> int:
    return sum(_is_number(v) for row in expected for v in row)


def compare(
    mode: str, expected: list[tuple[Any, ...]], steps: dict[str, list[list[Any]]]
) -> Comparison:
    """``steps`` maps each *succeeded* step to its result rows (≤ 50 previewed)."""
    if not steps:
        return Comparison(False, 0, _numeric_cells(expected), None, "no step produced a result")
    if mode == "values_present":
        pool = [cell for rows in steps.values() for row in rows for cell in row]
        hits = total = 0
        missing: list[Any] = []
        for row in expected:
            for e in row:
                found = any(matches(e, g) for g in pool)
                if _is_number(e):
                    total += 1
                    hits += found
                if not found:
                    missing.append(e)
        detail = "" if not missing else f"{len(missing)} expected values absent"
        return Comparison(not missing, hits, total, ",".join(steps), detail, missing)

    best: Comparison | None = None
    for step_id, rows in steps.items():
        result = _compare_rows(mode == "rows_ordered", expected, rows)
        result.step_id = step_id
        if best is None or (result.exec_match, result.numeric_hits) > (
            best.exec_match,
            best.numeric_hits,
        ):
            best = result
    assert best is not None
    return best


def _compare_rows(
    ordered: bool, expected: list[tuple[Any, ...]], rows: list[list[Any]]
) -> Comparison:
    hits = total = 0
    all_ok = len(rows) == len(expected)
    used: set[int] = set()
    missing: list[Any] = []
    for i, erow in enumerate(expected):
        candidates = (
            [i] if ordered and i < len(rows) else ([] if ordered else list(range(len(rows))))
        )
        best: tuple[bool, int, int] | None = None
        best_idx = -1
        for j in candidates:
            if j in used:
                continue
            res = _row_contains(erow, rows[j])
            if best is None or (res[0], res[1]) > (best[0], best[1]):
                best, best_idx = res, j
            if res[0]:
                break
        if best is None:
            total += sum(_is_number(v) for v in erow)
            all_ok = False
            missing.append(erow)
            continue
        used.add(best_idx)
        ok, h, t = best
        hits, total = hits + h, total + t
        if not ok:
            all_ok = False
            missing.append(erow)
    if all_ok:
        detail = ""
    elif len(rows) != len(expected):
        detail = f"expected {len(expected)} rows, got {len(rows)}"
    else:
        detail = f"{len(missing)} rows differ"
    return Comparison(all_ok, hits, total, None, detail, missing)
