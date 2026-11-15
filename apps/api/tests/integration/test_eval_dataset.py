"""The evaluation dataset itself is validated: every reference query, run through the real
executor on PostgreSQL, must equal the independently computed ground truth."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.tools.executor import PostgresExecutor
from app.core.config import Settings
from app.db.engines import open_databases
from app.db.models import Dataset
from app.main import create_app
from evals.cases import CASES, CATEGORIES
from evals.frames import Frames
from evals.refcheck import check_reference
from tests.integration.conftest import run, sign_up

pytestmark = pytest.mark.integration


def test_dataset_shape() -> None:
    assert len(CASES) >= 50
    assert {c.category for c in CASES} == set(CATEGORIES)
    assert all(n >= 4 for n in Counter(c.category for c in CASES).values())
    for c in CASES:
        if c.kind == "answer":
            assert c.steps and c.truth is not None, c.id
        if c.follow_of:
            assert c.resolved, c.id


def test_reference_sql_matches_independent_truth(pg_settings: Callable[..., Settings]) -> None:
    settings = pg_settings()
    with TestClient(create_app(settings)) as client:
        sign_up(client)
        demo = client.post("/api/v1/datasets/demo").json()
        dataset_id = (demo.get("dataset") or demo)["id"]

        async def go() -> list[dict[str, Any]]:
            databases = await open_databases(settings)
            try:
                assert databases.sessions is not None and databases.executor is not None
                async with databases.sessions() as db:
                    dataset = await db.get(Dataset, uuid.UUID(dataset_id))
                    assert dataset is not None
                    schema, role = dataset.schema_name, dataset.reader_role
                executor = PostgresExecutor(
                    databases.executor,
                    schema=schema,
                    reader_role=role,
                    max_rows=5000,
                    timeout_ms=20_000,
                )
                return await check_reference(executor, Frames("small"))
            finally:
                await databases.close()

        rows = run(go())
    bad = [r for r in rows if not r["ok"]]
    assert not bad, bad
