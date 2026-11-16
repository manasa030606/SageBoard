"""Phase 10 regressions that need PostgreSQL: error privacy, bounded fetch, sign-up race, run cap."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import app.agent.runner as runner_module
from app.core.config import Settings
from app.db.session import create_engine
from app.execution.readonly import run_readonly
from app.main import create_app
from app.services.auth import AuthService
from tests.integration.conftest import PgUrls, run, sign_up, signed_in
from tests.integration.test_workspace_api import new_conversation

pytestmark = pytest.mark.integration
API = "/api/v1"


def test_database_errors_do_not_contain_bound_values(
    pg_settings: Callable[..., Settings],
) -> None:
    """A failed insert must not print the email or password hash it was given."""
    secret_email, secret_hash = "leak-check@example.test", "$argon2id$SECRET-HASH-VALUE"

    async def fail() -> str:
        engine = create_engine(pg_settings())
        assert engine is not None
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO app.users (id, email, full_name, password_hash) VALUES "
                        "(gen_random_uuid(), :e, 'x', :h), (gen_random_uuid(), :e, 'x', :h)"
                    ),
                    {"e": secret_email, "h": secret_hash},
                )
        except DBAPIError as exc:
            return str(exc)
        finally:
            await engine.dispose()
        raise AssertionError("the duplicate insert should have failed")

    message = run(fail())
    assert "duplicate key" in message  # still diagnostic
    assert secret_email not in message
    assert secret_hash not in message


def test_executor_never_pulls_more_than_the_cap_plus_one_row(
    pg: PgUrls, pg_settings: Callable[..., Settings], seed: Callable[..., Any]
) -> None:
    demo = seed(replace=True)

    async def read(max_rows: int) -> Any:
        pool = await asyncpg.create_pool(PgUrls.dsn(pg.executor), min_size=0, max_size=1)
        try:
            return await run_readonly(
                pool,
                schema=demo.dataset.schema_name,
                reader_role=demo.dataset.reader_role,
                sql="SELECT 1 AS x FROM orders a, orders b, orders c",
                params=[],
                max_rows=max_rows,
                timeout_ms=5000,
            )
        finally:
            await pool.close()

    # The three-way product has billions of rows: fetching them all would hit the 5 s timeout.
    capped = run(read(10))
    assert capped.truncated is True
    assert len(capped.rows) == 10


def test_duplicate_signup_that_slips_past_the_check_is_a_conflict_not_a_500(
    pg_settings: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    with signed_in(pg_settings(), with_demo=False) as client:
        email = client.get(f"{API}/auth/me").json()["user"]["email"]

        async def never_found(self: AuthService, _email: str) -> None:
            return None  # as if two sign-ups raced between the lookup and the insert

        monkeypatch.setattr(AuthService, "_by_email", never_found)
        response = client.post(
            f"{API}/auth/register",
            json={
                "email": email,
                "password": "correct horse battery staple 9",
                "full_name": "Twin",
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_TAKEN"


class BlockedRunner:
    """Stands in for the agent: holds its slot until cancelled."""

    def __init__(self, **_: Any) -> None:
        pass

    async def run(self, session_id: uuid.UUID, cancel: asyncio.Event | None = None) -> None:
        assert cancel is not None
        await cancel.wait()


def test_one_user_cannot_fill_the_run_slots(
    pg_settings: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_module, "AgentRunner", BlockedRunner)
    settings = pg_settings(analyses_concurrent_per_user=2)
    with TestClient(create_app(settings, agent_llm=object())) as client:
        sign_up(client)
        client.post(f"{API}/datasets/demo")
        convo = new_conversation(client)
        url = f"{API}/conversations/{convo['id']}/sessions"
        assert client.post(url, json={"question": "one"}).status_code == 202
        assert client.post(url, json={"question": "two"}).status_code == 202
        refused = client.post(url, json={"question": "three"})
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "RATE_LIMITED"
        assert "Retry-After" in refused.headers
