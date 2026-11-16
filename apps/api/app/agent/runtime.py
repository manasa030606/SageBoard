"""Per-run dependencies and the ``traced_node`` wrapper.

``AgentDeps`` is everything a run needs that is *not* state: the LLM, the tools, the
store of full query results and hooks. It travels in LangGraph's
``config["configurable"]["deps"]``, so one compiled graph serves every run and tests
swap in fakes without touching the graph.

``traced_node`` wraps every node. It:

- skips the node (quickly, with a recorded event) once the run is cancelled, out of
  time or already terminated, so routers can send the run to the final response;
- gives the node a ``NodeContext`` for budgeted LLM calls and recorded tool calls;
- measures duration and records a ``NodeEvent`` (status, summary, tool and LLM calls);
- turns exceptions into a failed or degraded event instead of crashing the workflow:
  nodes with a ``fallback`` degrade gracefully; critical nodes end the run with
  ``termination_reason = "error"`` and the final response explains what happened.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.agent.llm.client import FATAL_LLM_CODES, LLMError, LLMMessage, StructuredLLM
from app.agent.prompts import Prompt
from app.agent.state import AgentState, Budget, NodeEvent, NodeStatus
from app.agent.tools.analysis import ResultTable
from app.agent.tools.executor import SqlExecutor
from app.agent.tools.schema import SchemaTools

log = structlog.get_logger("app.agent")

MAX_TOOL_SUMMARY_CHARS = 400


class BudgetExhaustedError(RuntimeError):
    pass


@dataclass
class AgentDeps:
    llm: StructuredLLM
    schema: SchemaTools
    executor: SqlExecutor
    max_rows: int = 5000
    preview_rows: int = 50
    results: dict[str, ResultTable] = field(default_factory=dict)
    cancel_event: asyncio.Event | None = None
    on_event: Callable[[NodeEvent], Awaitable[None]] | None = None
    clock: Callable[[], float] = time.time


def deps_from(config: RunnableConfig) -> AgentDeps:
    deps = (config.get("configurable") or {}).get("deps")
    if not isinstance(deps, AgentDeps):
        raise RuntimeError("AgentDeps missing from config['configurable']['deps']")
    return deps


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= MAX_TOOL_SUMMARY_CHARS else text[:MAX_TOOL_SUMMARY_CHARS] + "…"


class NodeContext:
    def __init__(self, name: str, deps: AgentDeps, budget: Budget) -> None:
        self.name = name
        self.deps = deps
        self.budget = budget
        self.summary: dict[str, Any] = {}
        self.tool_calls: list[dict[str, Any]] = []
        self.llm_calls: list[dict[str, Any]] = []
        self.degraded_reason: str | None = None

    def time_left(self) -> float:
        return self.budget.deadline_ts - self.deps.clock()

    async def llm[T: BaseModel](
        self,
        prompt: Prompt,
        messages: str | list[LLMMessage],
        schema: type[T],
        *,
        temperature: float = 0.0,
    ) -> T:
        if self.budget.llm_calls >= self.budget.max_llm_calls:
            raise BudgetExhaustedError(f"LLM call limit ({self.budget.max_llm_calls}) reached")
        if self.time_left() <= 0:
            raise BudgetExhaustedError("time limit reached")
        convo: list[LLMMessage] = (
            [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        )
        try:
            result = await self.deps.llm.structured(
                purpose=self.name,
                prompt_version=prompt.version,
                system=prompt.system,
                messages=convo,
                schema=schema,
                temperature=temperature,
            )
        except LLMError as exc:
            self._count(len(exc.records) or 1, exc.tokens_in, exc.tokens_out)
            self.llm_calls.extend(r.as_dict() for r in exc.records)
            raise
        self._count(result.calls, result.tokens_in, result.tokens_out)
        self.llm_calls.extend(r.as_dict() for r in result.records)
        return result.value

    def _count(self, calls: int, tokens_in: int, tokens_out: int) -> None:
        self.budget.llm_calls += calls
        self.budget.tokens_in += tokens_in
        self.budget.tokens_out += tokens_out

    async def tool[R](self, name: str, inputs: dict[str, Any], fn: Callable[[], R]) -> R:
        """Run and record one synchronous tool call; errors are recorded and re-raised."""
        start = time.perf_counter()
        record: dict[str, Any] = {"tool": name, "input": inputs}
        try:
            out = fn()
        except Exception as exc:
            record.update(ok=False, error=_short(str(exc)))
            raise
        else:
            record.update(ok=True, output=_short(out))
            return out
        finally:
            record["ms"] = int((time.perf_counter() - start) * 1000)
            self.tool_calls.append(record)

    async def atool[R](
        self, name: str, inputs: dict[str, Any], fn: Callable[[], Awaitable[R]]
    ) -> R:
        """Run and record one asynchronous tool call (database work)."""
        start = time.perf_counter()
        record: dict[str, Any] = {"tool": name, "input": inputs}
        try:
            out = await fn()
        except Exception as exc:
            record.update(ok=False, error=_short(str(exc)))
            raise
        else:
            record.update(ok=True, output=_short(out))
            return out
        finally:
            record["ms"] = int((time.perf_counter() - start) * 1000)
            self.tool_calls.append(record)


NodeFn = Callable[[AgentState, NodeContext], Awaitable[dict[str, Any]]]
Fallback = Callable[[AgentState, Exception, "NodeContext"], dict[str, Any]]


def stop_reason(state: AgentState, deps: AgentDeps) -> str | None:
    """Why the run must stop now, or None."""
    if deps.cancel_event is not None and deps.cancel_event.is_set():
        return "cancelled"
    if state.get("cancel_requested"):
        return "cancelled"
    if state.get("termination_reason"):
        return state["termination_reason"]
    budget = state.get("budget")
    if budget is not None and budget.deadline_ts and deps.clock() > budget.deadline_ts:
        return "budget_exhausted"
    return None


def _contain(
    name: str, state: AgentState, exc: Exception, fallback: Fallback | None, ctx: NodeContext
) -> tuple[dict[str, Any], NodeStatus, str]:
    """Turn an exception into a degraded (fallback) or failed (critical) node result."""
    error = f"{type(exc).__name__}: {_short(str(exc))}"
    log.warning("agent.node_failed", node=name, error_type=type(exc).__name__)
    if fallback is not None:
        update = fallback(state, exc, ctx)
        status: NodeStatus = "degraded"
    else:
        update, status = {"termination_reason": "error"}, "failed"
    update["errors"] = [f"{name}: {error}"]
    return update, status, error


def traced_node(
    name: str,
    fn: NodeFn,
    *,
    fallback: Fallback | None = None,
    always_run: bool = False,
) -> Callable[[AgentState, RunnableConfig], Awaitable[dict[str, Any]]]:
    async def node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        deps = deps_from(config)
        seq = len(state.get("trace", [])) + 1
        started = datetime.now(UTC)
        start = time.perf_counter()
        budget = (state.get("budget") or Budget()).model_copy()
        ctx = NodeContext(name, deps, budget)
        update: dict[str, Any]
        status: NodeStatus = "succeeded"
        error: str | None = None

        reason = None if always_run else stop_reason(state, deps)
        if reason is not None:
            update = {"termination_reason": state.get("termination_reason") or reason}
            if reason == "cancelled":
                update["cancel_requested"] = True
            ctx.summary = {"skipped": reason}
            status = "degraded"
        else:
            try:
                update = await fn(state, ctx)
                if ctx.degraded_reason:
                    status, error = "degraded", ctx.degraded_reason
            except BudgetExhaustedError as exc:
                status, error = "failed", str(exc)
                update = fallback(state, exc, ctx) if fallback else {}
                update.setdefault("termination_reason", "budget_exhausted")
            except LLMError as exc:
                if exc.code not in FATAL_LLM_CODES:
                    update, status, error = _contain(name, state, exc, fallback, ctx)
                else:  # quota, auth, model: retrying or degrading can't help — stop now
                    status, error = "failed", f"{exc.code}: {_short(str(exc))}"
                    log.warning("agent.llm_unavailable", node=name, code=exc.code)
                    update = {
                        "termination_reason": "llm_unavailable",
                        "llm_error": {"code": exc.code, "message": str(exc)},
                        "errors": [f"{name}: {error}"],
                    }
            except Exception as exc:
                update, status, error = _contain(name, state, exc, fallback, ctx)

        update["budget"] = ctx.budget
        event = NodeEvent(
            seq=seq,
            node=name,
            status=status,
            started_at=started.isoformat(),
            duration_ms=int((time.perf_counter() - start) * 1000),
            summary=ctx.summary,
            tool_calls=ctx.tool_calls,
            llm_calls=ctx.llm_calls,
            error=error,
        )
        update["trace"] = [event]
        if deps.on_event is not None:
            try:
                await deps.on_event(event)
            except Exception as exc:  # observability must never break the run
                log.warning("agent.on_event_failed", node=name, error_type=type(exc).__name__)
        return update

    node.__name__ = name
    return node
