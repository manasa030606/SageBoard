"""The evaluation's answer comparator is itself tested: a wrong judge would invalidate every
accuracy number built on it."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from evals.compare import compare, matches


@pytest.mark.parametrize(
    ("expected", "got", "ok"),
    [
        (3000, 3000, True),
        (3000, 3001, False),  # integers are exact
        (3000, Decimal("3000.0"), True),
        (1234.5678, 1234.57, True),  # within 0.01
        (1234.5678, 1235.0, False),
        (1_000_000.5, 1_000_050.5, True),  # within 0.01 % relative
        (1_000_000.5, 1_001_500.5, False),
        (3.04, 0.0304, False),  # a fraction reported as a percent is wrong, not forgiven
        ("Garden", "garden", True),
        ("Garden", "Books", False),
        ("2026-10", "2026-10-01T00:00:00", True),  # expected month matches a timestamp in it
        ("2026-10", "2026-11-01T00:00:00", False),
        ("2026-10-31", date(2026, 10, 31), True),
        (True, 1, False),
    ],
)
def test_cell_matching(expected: object, got: object, ok: bool) -> None:
    assert matches(expected, got) is ok


def test_unordered_rows_ignore_order_and_extra_columns() -> None:
    result = compare("rows_unordered", [("a", 1), ("b", 2)], {"s1": [[2, "b", "x"], [1, "a", "y"]]})
    assert result.exec_match


def test_ordered_rows_require_the_same_order() -> None:
    expected = [("a", 1), ("b", 2)]
    assert compare("rows_ordered", expected, {"s1": [["a", 1], ["b", 2]]}).exec_match
    assert not compare("rows_ordered", expected, {"s1": [["b", 2], ["a", 1]]}).exec_match


def test_row_count_must_match() -> None:
    assert not compare("rows_unordered", [("a", 1)], {"s1": [["a", 1], ["b", 2]]}).exec_match
    assert not compare("rows_unordered", [("a", 1), ("b", 2)], {"s1": [["a", 1]]}).exec_match


def test_wrong_number_is_a_miss_and_is_counted() -> None:
    result = compare("rows_unordered", [("a", 100)], {"s1": [["a", 101]]})
    assert not result.exec_match
    assert (result.numeric_hits, result.numeric_total) == (0, 1)


def test_no_successful_step_is_a_failure() -> None:
    assert not compare("rows_unordered", [(1,)], {}).exec_match


def test_values_present_pools_every_step() -> None:
    result = compare("values_present", [(10,), (20,)], {"s1": [[10]], "s2": [[20]]})
    assert result.exec_match
    assert not compare("values_present", [(10,), (30,)], {"s1": [[10]], "s2": [[20]]}).exec_match
