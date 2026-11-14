"""Run the agent for one analysis session and persist everything it did.

``AgentRunner.run(session_id)``:

1. loads the session, its dataset catalog and the conversation's earlier turns
   (conversation context; an answer to a clarification question resumes the original
   question with ``clarification_answer``);
2. builds the real tools: ``SchemaTools`` over the stored catalog and a
   ``PostgresExecutor`` on the read-only executor pool (dataset reader role);
3. runs the LangGraph workflow, writing one ``agent_node_runs`` row per node as it
   happens (observable while running);
4. stores the outcome: session status and counters, understanding, plan, the full
   result (response, steps, facts, charts, verification), every SQL attempt in
   ``query_executions`` and the assistant's message.

``RunManager`` keeps runs as asyncio tasks inside the API process (ADR-0004) with a
per-instance concurrency limit and cancellation.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agent.graph import build_graph, initial_state, run_graph
from app.agent.llm.client import StructuredLLM
from app.agent.nodes.common import plan_steps
from app.agent.runtime import AgentDeps
from app.agent.state import AgentState, Budget, NodeEvent, SQLAttempt
from app.agent.tools.executor import PostgresExecutor
from app.agent.tools.schema import DatasetCatalog, SchemaTools
from app.agent.usage import model_calls_today
from app.core.config import Settings
from app.db.engines import Databases
from app.db.models import (
    AgentNodeRun,
    AnalysisSession,
    Conversation,
    Dataset,
    DatasetTable,
    Message,
    QueryExecution,
)

log = structlog.get_logger("app.agent.runner")

PRIOR_TURNS = 3
CHART_DATA_ROWS = 200
STATUS_FOR_RESPONSE = {
    "answered": "succeeded",
    "partial": "partial",
    "clarification_needed": "awaiting_input",
    "out_of_scope": "succeeded",
    "failed": "failed",
}
FINISHED = ("succeeded", "partial", "failed", "cancelled")


class AgentRunner:
    def __init__(self, *, databases: Databases, settings: Settings, llm: StructuredLLM) -> None:
        if databases.sessions is None or databases.executor is None:
            raise RuntimeError("the agent needs the application and executor databases")
        self.sessions: async_sessionmaker[AsyncSession] = databases.sessions
        self.executor_pool = databases.executor
        self.settings = settings
        self.llm = llm
        self.graph = build_graph()

    async def run(self, session_id: uuid.UUID, cancel_event: asyncio.Event | None = None) -> None:
        started = time.perf_counter()
        try:
            await self._run(session_id, cancel_event, started)
        except Exception:
            log.exception("agent.run_crashed", session_id=str(session_id))
            await self._mark_crashed(session_id, started)

    # ------------------------------------------------------------------ steps
    async def _run(
        self, session_id: uuid.UUID, cancel_event: asyncio.Event | None, started: float
    ) -> None:
        async with self.sessions() as db:
            run = await db.get(AnalysisSession, session_id)
            if run is None or run.status != "queued":
                return
            dataset = await db.scalar(
                select(Dataset)
                .where(Dataset.id == run.dataset_id)
                .options(
                    selectinload(Dataset.tables).selectinload(DatasetTable.columns),
                    selectinload(Dataset.relationships),
                )
            )
            if dataset is None or dataset.status != "ready":
                run.status, run.error_code = "failed", "DATASET_NOT_READY"
                run.error_message = "The dataset is no longer available."
                run.finished_at = datetime.now(UTC)
                await db.commit()
                return
            remaining = self.settings.agent_max_llm_calls
            if self.settings.llm_daily_request_limit:
                used = await model_calls_today(db)
                remaining = min(remaining, self.settings.llm_daily_request_limit - used)
                if remaining <= 0:
                    run.status, run.error_code = "failed", "LLM_DAILY_LIMIT_REACHED"
                    run.error_message = (
                        "Today's model request limit (LLM_DAILY_REQUEST_LIMIT) is reached. "
                        "It resets at midnight Pacific time; no model was called."
                    )
                    run.finished_at = datetime.now(UTC)
                    await db.commit()
                    return
            question, clarification, prior = await self._conversation_context(db, run)
            catalog = DatasetCatalog.from_dataset(dataset)
            run.status = "running"
            run.started_at = datetime.now(UTC)
            run.llm_provider, run.llm_model = self.llm.label
            owner_id = run.owner_id
            await db.commit()

        deps = AgentDeps(
            llm=self.llm,
            schema=SchemaTools(catalog),
            executor=PostgresExecutor(
                self.executor_pool,
                schema=catalog.schema_name,
                reader_role=catalog.reader_role,
                max_rows=self.settings.agent_max_result_rows,
                timeout_ms=self.settings.executor_statement_timeout_ms,
            ),
            max_rows=self.settings.agent_max_result_rows,
            cancel_event=cancel_event,
        )
        deps.on_event = lambda event: self._record_event(session_id, owner_id, event)
        state = initial_state(
            run_id=str(session_id),
            question=question,
            today=date.today().isoformat(),
            prior_context=prior,
            clarification_answer=clarification,
            budget=Budget(
                max_llm_calls=remaining,
                max_sql_exec=self.settings.agent_max_sql_executions,
                deadline_ts=time.time() + self.settings.agent_deadline_seconds,
            ),
        )
        final = await run_graph(self.graph, state, deps)
        await self._persist(session_id, final, deps, started)

    async def _conversation_context(
        self, db: AsyncSession, run: AnalysisSession
    ) -> tuple[str, str | None, list[dict[str, Any]]]:
        earlier = list(
            (
                await db.scalars(
                    select(AnalysisSession)
                    .where(
                        AnalysisSession.conversation_id == run.conversation_id,
                        AnalysisSession.id != run.id,
                        AnalysisSession.created_at <= run.created_at,
                    )
                    .order_by(AnalysisSession.created_at.desc())
                    .limit(PRIOR_TURNS + 1)
                )
            ).all()
        )
        question, clarification = run.question, None
        if earlier and earlier[0].status == "awaiting_input":
            # This message answers the agent's clarification question.
            asked = earlier[0]
            question, clarification = asked.question, run.question
            asked.status, asked.termination_reason = "succeeded", "clarification_answered"
            earlier = earlier[1:]
        prior = [
            {
                "question": s.question,
                "restated": (s.understanding or {}).get("restated_question"),
                "answer": s.final_summary,
            }
            for s in reversed(earlier[:PRIOR_TURNS])
            if s.status in ("succeeded", "partial") and s.final_summary
        ]
        return question, clarification, prior

    async def _record_event(
        self, session_id: uuid.UUID, owner_id: uuid.UUID, event: NodeEvent
    ) -> None:
        async with self.sessions() as db:
            db.add(
                AgentNodeRun(
                    analysis_session_id=session_id,
                    owner_id=owner_id,
                    seq=event.seq,
                    node=event.node,
                    status=event.status,
                    started_at=datetime.fromisoformat(event.started_at),
                    duration_ms=event.duration_ms,
                    summary=_json(event.summary),
                    tool_calls=_json(event.tool_calls),
                    llm_calls=_json(event.llm_calls),
                    error=event.error,
                )
            )
            await db.commit()

    async def _persist(
        self, session_id: uuid.UUID, final: AgentState, deps: AgentDeps, started: float
    ) -> None:
        response = final["response"]
        budget = final["budget"]
        async with self.sessions() as db:
            run = await db.get(AnalysisSession, session_id, populate_existing=True)
            if run is None:
                return
            cancelled = run.status == "cancelled" or final.get("termination_reason") == "cancelled"
            run.status = "cancelled" if cancelled else STATUS_FOR_RESPONSE[response.status]
            run.termination_reason = final.get("termination_reason")
            run.understanding = (
                final["understanding"].model_dump() if final.get("understanding") else None
            )
            run.plan = final["plan"].model_dump() if final.get("plan") else None
            run.final_summary = response.summary
            run.result = build_result(final, deps)
            llm_error = final.get("llm_error") or {}
            if run.status == "failed" or llm_error:
                run.error_code = (
                    llm_error.get("code") or final.get("termination_reason") or "error"
                ).upper()[:64]
                run.error_message = response.summary
            run.llm_calls, run.sql_executions = budget.llm_calls, budget.sql_exec
            run.tokens_in, run.tokens_out = budget.tokens_in, budget.tokens_out
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            run.finished_at = datetime.now(UTC)
            for step in plan_steps(final):
                for attempt in final["step_results"][step.step_id].attempts:
                    db.add(_query_row(run, step.step_id, attempt))
            db.add(
                Message(
                    conversation_id=run.conversation_id,
                    analysis_session_id=run.id,
                    role="assistant",
                    content=response.summary,
                )
            )
            await db.execute(
                update(Conversation)
                .where(Conversation.id == run.conversation_id)
                .values(updated_at=datetime.now(UTC))
            )
            await db.commit()

    async def _mark_crashed(self, session_id: uuid.UUID, started: float) -> None:
        try:
            async with self.sessions() as db:
                run = await db.get(AnalysisSession, session_id, populate_existing=True)
                if run is None or run.status in FINISHED:
                    return
                run.status, run.error_code = "failed", "AGENT_CRASHED"
                run.error_message = (
                    "The analysis stopped unexpectedly. Nothing was guessed; try again."
                )
                run.duration_ms = int((time.perf_counter() - started) * 1000)
                run.finished_at = datetime.now(UTC)
                await db.commit()
        except Exception:
            log.exception("agent.mark_crashed_failed", session_id=str(session_id))


# ---------------------------------------------------------------- helpers


def _json(value: Any) -> Any:
    """Make tool/LLM records JSON-safe (they may contain reprs, tuples, dates)."""
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _query_row(run: AnalysisSession, step_id: str, attempt: SQLAttempt) -> QueryExecution:
    executed = attempt.exec_status != "not_run"
    error_code = attempt.error_code or (
        attempt.guard_violations[0].code if attempt.guard_violations else None
    )
    error_message = attempt.exec_error or (
        "; ".join(v.message for v in attempt.guard_violations) or None
    )
    return QueryExecution(
        analysis_session_id=run.id,
        owner_id=run.owner_id,
        dataset_id=run.dataset_id,
        origin="agent",
        plan_step_id=step_id,
        attempt=attempt.attempt,
        generated_sql=attempt.sql,
        executed_sql=attempt.normalized_sql if executed else None,
        sql_fingerprint=hashlib.sha256(attempt.normalized_sql.encode()).hexdigest()
        if attempt.normalized_sql
        else None,
        guard_status=attempt.guard_status
        if attempt.guard_status != "pending"
        else "not_applicable",
        guard_violations=[v.model_dump() for v in attempt.guard_violations],
        exec_status=attempt.exec_status,
        error_code=(error_code or None) and error_code[:16],
        error_message=error_message,
        row_count=attempt.row_count,
        truncated=False,
        exec_ms=attempt.exec_ms,
    )


def build_result(final: AgentState, deps: AgentDeps) -> dict[str, Any]:
    """Everything the UI needs, as JSON: response, steps (SQL + previews), facts, charts."""
    steps = []
    for step in plan_steps(final):
        r = final["step_results"][step.step_id]
        used = next((a for a in reversed(r.attempts) if a.exec_status == "ok"), None)
        steps.append(
            {
                **step.model_dump(),
                "status": r.status,
                "sql": used.normalized_sql if used else None,
                "explanation": used.explanation if used else None,
                "attempts": [a.model_dump() for a in r.attempts],
                "columns": [{"name": n, "type": t} for n, t in r.columns],
                "row_count": r.row_count,
                "truncated": r.truncated,
                "rows": r.preview_rows,
                "notes": r.notes,
                "failure_explanation": r.failure_explanation,
            }
        )
    charts = []
    for chart in final.get("charts", []):
        table = deps.results.get(chart.step_id)
        charts.append(
            {
                **chart.model_dump(),
                "data": table.rows[:CHART_DATA_ROWS] if table else [],
                "columns": table.columns if table else [],
            }
        )
    verification = final.get("verification")
    result: dict[str, Any] = _json(
        {
            "response": final["response"].model_dump(),
            "steps": steps,
            "facts": [f.model_dump() for f in final.get("facts", [])],
            "charts": charts,
            "verification": verification.model_dump() if verification else None,
            "schema_tables": final["schema_context"].tables if final.get("schema_context") else [],
            "budget": final["budget"].model_dump(exclude={"deadline_ts"}),
            "errors": final.get("errors", []),
            "model": {"provider": deps.llm.label[0], "name": deps.llm.label[1]},
        }
    )
    return result


class RunManager:
    """In-process run execution (ADR-0004): asyncio tasks, a concurrency cap, cancel."""

    def __init__(
        self, *, settings: Settings, llm: StructuredLLM | None, max_concurrent: int = 4
    ) -> None:
        self.settings = settings
        self.llm = llm
        self._slots = asyncio.Semaphore(max_concurrent)
        self._runs: dict[uuid.UUID, tuple[asyncio.Task[None], asyncio.Event]] = {}

    @property
    def available(self) -> bool:
        return self.llm is not None

    def start(self, session_id: uuid.UUID, databases: Databases) -> None:
        if self.llm is None:
            raise RuntimeError("no LLM configured")
        runner = AgentRunner(databases=databases, settings=self.settings, llm=self.llm)
        cancel = asyncio.Event()

        async def guarded() -> None:
            async with self._slots:
                await runner.run(session_id, cancel)

        task = asyncio.create_task(guarded(), name=f"agent-run-{session_id}")
        self._runs[session_id] = (task, cancel)
        task.add_done_callback(lambda _: self._runs.pop(session_id, None))

    def cancel(self, session_id: uuid.UUID) -> bool:
        entry = self._runs.get(session_id)
        if entry is None:
            return False
        entry[1].set()
        return True

    def is_running(self, session_id: uuid.UUID) -> bool:
        return session_id in self._runs

    async def wait(self, session_id: uuid.UUID) -> None:
        entry = self._runs.get(session_id)
        if entry is not None:
            await asyncio.shield(entry[0])

    async def shutdown(self) -> None:
        for _task, cancel in list(self._runs.values()):
            cancel.set()
        tasks = [t for t, _ in self._runs.values()]
        if tasks:
            await asyncio.wait(tasks, timeout=10)


async def fail_interrupted_runs(sessions: async_sessionmaker[AsyncSession]) -> int:
    """On startup, runs still marked running were interrupted by a restart (ADR-0004)."""
    async with sessions() as db:
        result = await db.execute(
            update(AnalysisSession)
            .where(AnalysisSession.status == "running")
            .values(
                status="failed",
                error_code="INTERRUPTED",
                error_message="The server restarted while this analysis was running. Ask again to rerun it.",
                finished_at=datetime.now(UTC),
            )
        )
        await db.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
