"""ORM models against PostgreSQL: relationships, cascades, RESTRICT and CHECK constraints.

Connects as ``sageboard_app`` — the same role the API uses.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.identifiers import new_dataset_identifiers
from app.db.models import (
    AnalysisSession,
    Conversation,
    DatabaseConnection,
    Dataset,
    DatasetColumn,
    DatasetRelationship,
    DatasetTable,
    IngestionJob,
    Message,
    QueryExecution,
    Report,
    User,
)
from tests.integration.conftest import PgUrls

pytestmark = pytest.mark.integration


@pytest.fixture
async def session(pg: PgUrls) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(pg.app, connect_args={"statement_cache_size": 0})
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            yield s
    finally:
        await engine.dispose()


async def make_graph(session: AsyncSession) -> dict[str, uuid.UUID]:
    """A user with one of everything, linked the way the product links them."""
    user = User(email=f"model-{uuid.uuid4().hex[:8]}@example.test", full_name="Model Test")
    session.add(user)
    await session.flush()
    conn = DatabaseConnection(owner_id=user.id, name="warehouse", kind="internal_warehouse")
    session.add(conn)
    await session.flush()
    schema, role = new_dataset_identifiers()
    dataset = Dataset(
        owner_id=user.id,
        connection_id=conn.id,
        name="Sales",
        source_type="upload_csv",
        schema_name=schema,
        reader_role=role,
        status="ready",
    )
    session.add(dataset)
    await session.flush()
    orders = DatasetTable(
        dataset_id=dataset.id, table_name="orders", display_name="Orders", row_count=2
    )
    customers = DatasetTable(
        dataset_id=dataset.id, table_name="customers", display_name="Customers", row_count=1
    )
    session.add_all([orders, customers])
    await session.flush()
    session.add_all(
        [
            DatasetColumn(
                table_id=orders.id,
                column_name="customer_id",
                display_name="Customer ID",
                ordinal=1,
                data_type="integer",
            ),
            DatasetColumn(
                table_id=customers.id,
                column_name="customer_id",
                display_name="Customer ID",
                ordinal=1,
                data_type="integer",
            ),
            DatasetRelationship(
                dataset_id=dataset.id,
                from_table_id=orders.id,
                from_column="customer_id",
                to_table_id=customers.id,
                to_column="customer_id",
                origin="declared",
            ),
            IngestionJob(dataset_id=dataset.id, status="succeeded"),
        ]
    )
    convo = Conversation(owner_id=user.id, dataset_id=dataset.id, title="Q3 revenue")
    session.add(convo)
    await session.flush()
    run = AnalysisSession(
        conversation_id=convo.id,
        owner_id=user.id,
        dataset_id=dataset.id,
        dataset_version=1,
        question="What was revenue last quarter?",
    )
    session.add(run)
    await session.flush()
    session.add_all(
        [
            Message(
                conversation_id=convo.id,
                analysis_session_id=run.id,
                role="user",
                content="Revenue?",
            ),
            QueryExecution(
                analysis_session_id=run.id,
                owner_id=user.id,
                dataset_id=dataset.id,
                origin="agent",
                guard_status="accepted",
                exec_status="ok",
            ),
            Report(owner_id=user.id, analysis_session_id=run.id, dataset_id=dataset.id, title="Q3"),
        ]
    )
    await session.commit()
    return {
        "user": user.id,
        "connection": conn.id,
        "dataset": dataset.id,
        "conversation": convo.id,
        "run": run.id,
    }


async def count(session: AsyncSession, model: type, **where: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(model)
    for key, value in where.items():
        stmt = stmt.where(getattr(model, key) == value)
    return int(await session.scalar(stmt) or 0)


async def test_relationships_load(session: AsyncSession) -> None:
    ids = await make_graph(session)
    session.expunge_all()
    dataset = await session.get(Dataset, ids["dataset"])
    assert dataset is not None
    await session.refresh(dataset, ["tables", "relationships", "jobs"])
    assert {t.table_name for t in dataset.tables} == {"orders", "customers"}
    assert dataset.relationships[0].from_column == "customer_id"
    assert dataset.jobs[0].status == "succeeded"
    convo = await session.get(Conversation, ids["conversation"])
    assert convo is not None
    await session.refresh(convo, ["messages", "sessions"])
    assert convo.messages[0].analysis_session_id == ids["run"]
    assert convo.sessions[0].status == "queued"
    await session.delete(await session.get(User, ids["user"]))
    await session.commit()


async def test_deleting_a_dataset_cascades_to_catalog_and_analysis(session: AsyncSession) -> None:
    ids = await make_graph(session)
    await session.delete(await session.get(Dataset, ids["dataset"]))
    await session.commit()
    session.expunge_all()
    for model in (
        DatasetTable,
        DatasetRelationship,
        IngestionJob,
        Conversation,
        AnalysisSession,
        QueryExecution,
    ):
        assert await count(session, model, dataset_id=ids["dataset"]) == 0, model.__name__
    # Reports outlive their dataset (dataset_id SET NULL) so exported work isn't lost.
    reports = (await session.scalars(select(Report).where(Report.owner_id == ids["user"]))).all()
    assert len(reports) == 1
    assert reports[0].dataset_id is None
    assert reports[0].analysis_session_id is None
    await session.delete(await session.get(User, ids["user"]))
    await session.commit()


async def test_deleting_a_user_removes_everything_they_own(session: AsyncSession) -> None:
    ids = await make_graph(session)
    await session.delete(await session.get(User, ids["user"]))
    await session.commit()
    session.expunge_all()
    for model in (
        DatabaseConnection,
        Dataset,
        Conversation,
        AnalysisSession,
        QueryExecution,
        Report,
    ):
        assert await count(session, model, owner_id=ids["user"]) == 0, model.__name__
    assert await count(session, Message, conversation_id=ids["conversation"]) == 0


async def test_connection_in_use_cannot_be_deleted(session: AsyncSession) -> None:
    ids = await make_graph(session)
    conn = await session.get(DatabaseConnection, ids["connection"])
    await session.delete(conn)
    with pytest.raises(IntegrityError, match="fk_datasets_connection_id"):
        await session.commit()
    await session.rollback()
    await session.delete(await session.get(User, ids["user"]))
    await session.commit()


async def test_email_is_unique_case_insensitively(session: AsyncSession) -> None:
    email = f"Case-{uuid.uuid4().hex[:8]}@Example.test"
    first = User(email=email, full_name="A")
    session.add(first)
    await session.commit()
    session.add(User(email=email.lower(), full_name="B"))
    with pytest.raises(IntegrityError, match="uq_users_email_lower"):
        await session.commit()
    await session.rollback()
    await session.delete(first)
    await session.commit()


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("status", "exploded", "ck_datasets_status"),
        ("schema_name", "public", "ck_datasets_schema_name"),
        ("source_type", "ftp", "ck_datasets_source_type"),
    ],
)
async def test_dataset_check_constraints(
    session: AsyncSession, field: str, value: str, constraint: str
) -> None:
    user = User(email=f"ck-{uuid.uuid4().hex[:8]}@example.test", full_name="C")
    session.add(user)
    await session.flush()
    conn = DatabaseConnection(owner_id=user.id, name="w", kind="internal_warehouse")
    session.add(conn)
    await session.flush()
    schema, role = new_dataset_identifiers()
    values = {
        "owner_id": user.id,
        "connection_id": conn.id,
        "name": "x",
        "source_type": "upload_csv",
        "schema_name": schema,
        "reader_role": role,
        "status": "ready",
        field: value,
    }
    session.add(Dataset(**values))
    with pytest.raises(IntegrityError, match=constraint):
        await session.commit()
    await session.rollback()


async def test_analysis_question_length_is_enforced(session: AsyncSession) -> None:
    ids = await make_graph(session)
    session.add(
        AnalysisSession(
            conversation_id=ids["conversation"],
            owner_id=ids["user"],
            dataset_id=ids["dataset"],
            dataset_version=1,
            question="",
        )
    )
    with pytest.raises(IntegrityError, match="ck_analysis_sessions"):
        await session.commit()
    await session.rollback()
    await session.delete(await session.get(User, ids["user"]))
    await session.commit()
