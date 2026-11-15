"""Every statement in the evaluation's attack corpus must be refused by the SQL Guard."""

from __future__ import annotations

import pytest

from app.agent.tools.schema import SchemaTools
from app.agent.tools.sql_guard import validate_sql
from evals.safety import UNSAFE
from tests.agent.fakes import shop_catalog

POLICY = SchemaTools(shop_catalog()).guard_policy(max_rows=500)


def test_corpus_is_broad_enough_to_mean_something() -> None:
    assert len(UNSAFE) >= 60
    assert len({category for _, category, _ in UNSAFE}) >= 10


@pytest.mark.parametrize(("sql", "category"), [(s, c) for s, c, _ in UNSAFE])
def test_guard_refuses_attack(sql: str, category: str) -> None:
    result = validate_sql(sql, POLICY)
    assert not result.ok, f"{category} statement was accepted: {sql!r}"
    assert result.normalized_sql is None
