"""Test doubles for the agent: a scripted model and fake tools.

``ScriptedProvider`` stands in for the *model only*. It replays JSON replies queued per
node (purpose) and records every request so tests can assert what each node sent.
Everything else (schema validation, re-asks, the SQL Guard, routing, the analysis
engine, grounding) runs for real. It lives under tests/ and is never importable by the
running application (D42).
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agent.llm.client import Completion, LLMError, LLMMessage, StructuredLLM
from app.agent.runtime import AgentDeps
from app.agent.state import Budget, ComputedFact
from app.agent.tools.executor import ExecutionOutcome
from app.agent.tools.schema import (
    CatalogColumn,
    CatalogRelationship,
    CatalogTable,
    DatasetCatalog,
    SchemaTools,
)


def data_from(messages: list[LLMMessage], name: str) -> Any:
    """Read a ``<data name=…>`` block the node sent (lets a scripted reply copy real values)."""
    marker = f'<data name="{name}">\n'
    for message in reversed(messages):
        text = message["content"]
        if marker in text:
            body = text.split(marker, 1)[1].split("\n</data>", 1)[0]
            return json.loads(body)
    raise KeyError(name)


Reply = dict[str, Any] | Callable[[list[LLMMessage]], dict[str, Any]] | LLMError


@dataclass
class Call:
    purpose: str
    system: str
    messages: list[LLMMessage]

    @property
    def text(self) -> str:
        return "\n".join(m["content"] for m in self.messages)


class ScriptedProvider:
    name = "scripted"
    model = "scripted-test-model"

    def __init__(self, script: dict[str, list[Reply]] | None = None) -> None:
        self.script: dict[str, list[Reply]] = defaultdict(list)
        for purpose, replies in (script or {}).items():
            self.script[purpose].extend(replies)
        self.calls: list[Call] = []
        self.unexpected: list[str] = []

    def add(self, purpose: str, *replies: Reply) -> ScriptedProvider:
        self.script[purpose].extend(replies)
        return self

    def calls_for(self, purpose: str) -> list[Call]:
        return [c for c in self.calls if c.purpose == purpose]

    async def complete_json(
        self,
        *,
        purpose: str,
        system: str,
        messages: list[LLMMessage],
        schema_name: str,
        json_schema: dict[str, Any],
        temperature: float,
    ) -> Completion:
        self.calls.append(Call(purpose, system, list(messages)))
        queue = self.script.get(purpose)
        if not queue:
            self.unexpected.append(purpose)
            raise LLMError(f"script exhausted for {purpose}", code="SCRIPT_EXHAUSTED")
        reply = queue.pop(0)
        if isinstance(reply, LLMError):
            raise reply
        data = reply(messages) if callable(reply) else reply
        return Completion(data, self.model, tokens_in=100, tokens_out=20)

    def leftover(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.script.items() if v}


Rule = tuple[str, ExecutionOutcome | Callable[[str], ExecutionOutcome]]


class FakeExecutor:
    """Returns canned outcomes for SQL containing a marker (first match wins)."""

    def __init__(self, rules: list[Rule], default: ExecutionOutcome | None = None) -> None:
        self.rules = rules
        self.default = default or ExecutionOutcome(
            status="error", error_code="42601", error_message="no fake rule matched"
        )
        self.executed: list[str] = []

    async def run(self, sql: str) -> ExecutionOutcome:
        self.executed.append(sql)
        lowered = sql.lower()
        for marker, outcome in self.rules:
            if marker.lower() in lowered:
                return outcome(sql) if callable(outcome) else outcome
        return self.default


def ok(
    columns: list[tuple[str, str]], rows: list[list[Any]], *, truncated: bool = False
) -> ExecutionOutcome:
    return ExecutionOutcome(status="ok", columns=columns, rows=rows, truncated=truncated, exec_ms=3)


def db_error(code: str, message: str) -> ExecutionOutcome:
    status: Literal["error", "timeout"] = (
        "timeout" if code == "57014" else "error"
    )  # as PostgresExecutor
    return ExecutionOutcome(status=status, error_code=code, error_message=message, exec_ms=2)


def col(name: str, data_type: str, **kw: Any) -> CatalogColumn:
    return CatalogColumn(name=name, data_type=data_type, **kw)


def shop_catalog() -> DatasetCatalog:
    """A small e-commerce catalog shaped like the Sageboard sample dataset."""
    return DatasetCatalog(
        dataset_id="ds-test",
        name="Sample shop",
        schema_name="ds_0123456789abcdef",
        reader_role="ds_0123456789abcdef_r",
        tables=(
            CatalogTable(
                "customers",
                "One row per customer account.",
                400,
                (
                    col("customer_id", "integer", is_primary_key=True),
                    col("email", "text", is_sensitive=True),
                    col("region", "text", samples=("Northeast", "South", "West", "Midwest")),
                    col("segment", "text", samples=("Consumer", "Small business", "Enterprise")),
                ),
            ),
            CatalogTable(
                "order_items",
                "Line items. Line revenue = quantity × unit_price × (1 − discount).",
                6000,
                (
                    col("order_item_id", "integer", is_primary_key=True),
                    col("order_id", "integer"),
                    col("product_id", "integer"),
                    col("quantity", "integer"),
                    col("unit_price", "numeric"),
                    col("discount", "numeric"),
                ),
            ),
            CatalogTable(
                "orders",
                "One row per order. Revenue excludes cancelled orders.",
                2500,
                (
                    col("order_id", "integer", is_primary_key=True),
                    col("customer_id", "integer"),
                    col(
                        "order_date",
                        "timestamptz",
                        min_value="2024-01-01T00:00:00+00:00",
                        max_value="2025-09-30T23:00:00+00:00",
                    ),
                    col(
                        "status", "text", samples=("delivered", "shipped", "cancelled", "returned")
                    ),
                    col("channel", "text", samples=("web", "mobile", "marketplace")),
                ),
            ),
            CatalogTable(
                "products",
                "Product catalogue.",
                120,
                (
                    col("product_id", "integer", is_primary_key=True),
                    col("name", "text"),
                    col("category", "text", samples=("Electronics", "Home", "Toys")),
                ),
            ),
        ),
        relationships=(
            CatalogRelationship("orders", "customer_id", "customers", "customer_id"),
            CatalogRelationship("order_items", "order_id", "orders", "order_id"),
            CatalogRelationship("order_items", "product_id", "products", "product_id"),
        ),
    )


@dataclass
class Harness:
    provider: ScriptedProvider
    executor: FakeExecutor
    deps: AgentDeps = field(init=False)

    def __post_init__(self) -> None:
        self.deps = AgentDeps(
            llm=StructuredLLM(self.provider),
            schema=SchemaTools(shop_catalog()),
            executor=self.executor,
            max_rows=500,
        )


def items(fact: ComputedFact) -> list[dict[str, Any]]:
    """A list-valued fact's items (group_change, share, top_n…)."""
    assert isinstance(fact.value, list), fact.value
    return fact.value


def budget(**overrides: Any) -> Budget:
    return Budget(deadline_ts=time.time() + 60, **overrides)
