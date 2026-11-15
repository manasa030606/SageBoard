"""The agent's typed shared state.

LangGraph passes one ``AgentState`` dict from node to node. Each node returns a
*partial* update; LangGraph merges it in. Two fields use a **reducer** (``operator.add``)
so updates are appended instead of overwritten: ``trace`` (one event per node run)
and ``errors``.

Pydantic models hold every nested value, so each piece is validated when a node
builds it and can be serialised (to the database, to the API, to a debugger).

State-size discipline: full query results never live in the state. They stay in the
run's ``ResultStore`` (see ``app.agent.deps``); the state keeps a ≤50-row preview.
"""

from __future__ import annotations

import operator
import re
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TYPE_SUFFIX = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*$")


def clean_column_name(value: object) -> object:
    """Models sometimes copy a result header like "revenue (numeric)" as a column name."""
    if isinstance(value, str):
        match = _TYPE_SUFFIX.match(value)
        return match.group(1) if match else value.strip()
    return value


# ----------------------------------------------------------------- understanding


class QueryUnderstanding(BaseModel):
    """What the user is asking, in structured form (Query Understanding Agent)."""

    status: Literal["answerable", "needs_clarification", "out_of_scope"]
    restated_question: str = Field(max_length=500)
    intent: Literal[
        "aggregate",
        "trend",
        "comparison",
        "ranking",
        "distribution",
        "lookup",
        "correlation",
        "composition",
        "explanation",
    ]
    metrics: list[str] = Field(default_factory=list, max_length=8)
    dimensions: list[str] = Field(default_factory=list, max_length=8)
    filters: list[str] = Field(default_factory=list, max_length=8)
    time_range: str | None = None
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    clarification_question: str | None = None
    clarification_options: list[str] = Field(default_factory=list, max_length=5)
    out_of_scope_reason: str | None = None


# ------------------------------------------------------------------------ schema


class ColumnContext(BaseModel):
    table: str
    column: str
    data_type: str
    description: str | None = None
    is_primary_key: bool = False
    # Personal data: values of this column are never sent to the model (SECURITY_DESIGN §6).
    is_sensitive: bool = False
    null_pct: float | None = None
    distinct_count: int | None = None
    sample_values: list[str] = Field(default_factory=list)
    min_value: str | None = None
    max_value: str | None = None


class SchemaContext(BaseModel):
    """The slice of the catalog the later nodes are allowed to rely on."""

    tables: list[str]
    columns: list[ColumnContext]
    join_paths: list[str]
    rationale: str
    tool_calls: int = 0


# ---------------------------------------------------------------------- planning


class PlanStep(BaseModel):
    """One SQL query the plan needs."""

    step_id: str = Field(pattern=r"^s[1-9]$")
    purpose: str = Field(max_length=300)
    expected_output: str = Field(max_length=300)
    depends_on: list[str] = Field(default_factory=list)


class AnalysisPlan(BaseModel):
    """The structured analytical tasks for a question (Planning Agent).

    ``steps`` are the queries to run; ``analysis_tasks`` are the deterministic
    calculations to perform on their results (percentage change, contributions…).
    """

    steps: list[PlanStep] = Field(min_length=1, max_length=6)
    analysis_tasks: list[str] = Field(default_factory=list, max_length=8)
    final_answer_shape: str = Field(max_length=300)


# --------------------------------------------------------------------------- SQL

ErrorCategory = Literal[
    "guard_rejected",
    "unsafe_query",
    "too_expensive",
    "syntax_error",
    "unknown_table",
    "unknown_column",
    "grouping_error",
    "type_mismatch",
    "undefined_function",
    "division_by_zero",
    "ambiguous_column",
    "timeout",
    "permission_denied",
    "empty_result",
    "fan_out",
    "repeated_query",
    "other",
]


class GuardViolation(BaseModel):
    code: str
    message: str


class ErrorDiagnosis(BaseModel):
    """Deterministic classification of a failed attempt (Error Recovery Agent, step 2)."""

    category: ErrorCategory
    recoverable: bool
    summary: str
    hint: str | None = None


class SQLAttempt(BaseModel):
    attempt: int
    sql: str
    explanation: str
    origin: Literal["generation", "recovery"] = "generation"
    guard_status: Literal["pending", "accepted", "rejected"] = "pending"
    guard_violations: list[GuardViolation] = Field(default_factory=list)
    normalized_sql: str | None = None
    exec_status: Literal["not_run", "ok", "error", "timeout", "cancelled"] = "not_run"
    error_code: str | None = None  # SQLSTATE
    exec_error: str | None = None  # sanitised database message
    exec_ms: int | None = None
    row_count: int | None = None
    diagnosis: ErrorDiagnosis | None = None


class StepResult(BaseModel):
    step_id: str
    status: Literal["pending", "succeeded", "failed", "skipped"] = "pending"
    attempts: list[SQLAttempt] = Field(default_factory=list)
    columns: list[tuple[str, str]] = Field(default_factory=list)  # (name, pg type)
    row_count: int = 0
    truncated: bool = False
    preview_rows: list[list[Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    needs_repair: ErrorDiagnosis | None = None  # set by check_result
    failure_explanation: str | None = None

    def latest(self) -> SQLAttempt | None:
        return self.attempts[-1] if self.attempts else None


# ------------------------------------------------------------------ analysis


class ComputedFact(BaseModel):
    fact_id: str
    step_id: str
    kind: str
    description: str
    value: float | int | str | list[dict[str, Any]] | None
    unit: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class ChartSpec(BaseModel):
    chart_type: Literal[
        "bar",
        "grouped_bar",
        "horizontal_bar",
        "line",
        "area",
        "scatter",
        "pie",
        "donut",
        "histogram",
        "kpi",
        "table",
    ]
    step_id: str
    x: str | None = None
    y: list[str] = Field(default_factory=list, max_length=4)
    series: str | None = None
    title: str = Field(max_length=120)
    subtitle: str | None = Field(default=None, max_length=200)
    value_format: Literal["number", "currency", "percent", "integer"] = "number"
    fallback_reason: str | None = None

    @field_validator("x", "series", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return clean_column_name(value)

    @field_validator("y", mode="before")
    @classmethod
    def _clean_list(cls, value: object) -> object:
        return [clean_column_name(v) for v in value] if isinstance(value, list) else value


class EvidenceRef(BaseModel):
    kind: Literal["fact", "cell"]
    fact_id: str | None = None
    step_id: str | None = None
    row_index: int | None = None
    column: str | None = None

    @field_validator("column", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return clean_column_name(value)


class Insight(BaseModel):
    insight_id: str
    headline: str = Field(max_length=160)
    detail: str = Field(max_length=800)
    category: Literal["finding", "comparison", "anomaly", "recommendation", "caveat"]
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=8)
    confidence: Literal["high", "medium", "low"]
    verification: Literal["unverified", "verified", "rejected"] = "unverified"
    rejection_reasons: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    """What the Verification Agent checked, for the final response and the inspector."""

    round: int = 0
    metrics_check: str = "not_checked"  # passed | issue: … | not_checked
    time_period_check: str = "not_checked"
    verified_insights: int = 0
    rejected_insights: int = 0
    removed: list[dict[str, Any]] = Field(default_factory=list)  # dropped after max rounds
    uncertainty: list[str] = Field(default_factory=list)


class FinalResponse(BaseModel):
    status: Literal["answered", "partial", "clarification_needed", "out_of_scope", "failed"]
    summary: str
    key_findings: list[Insight] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    clarification_options: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)
    summary_source: Literal["model", "template"] = "template"


# ------------------------------------------------------------------- control


class Budget(BaseModel):
    """Hard limits enforced by code, not by the model's goodwill."""

    model_config = ConfigDict(validate_assignment=True)

    max_llm_calls: int = 30
    llm_calls: int = 0
    max_sql_exec: int = 14
    sql_exec: int = 0
    max_attempts_per_step: int = 3
    max_verify_rounds: int = 2
    verify_rounds: int = 0
    max_schema_tool_calls: int = 6
    deadline_ts: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


NodeStatus = Literal["succeeded", "failed", "degraded"]


class NodeEvent(BaseModel):
    """One node run: the unit of observability (persisted as agent_node_runs)."""

    seq: int
    node: str
    status: NodeStatus
    started_at: str
    duration_ms: int
    summary: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    llm_calls: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


TerminationReason = Literal[
    "completed",
    "clarification_needed",
    "out_of_scope",
    "budget_exhausted",
    "cancelled",
    "all_steps_failed",
    "llm_unavailable",
    "error",
]


class AgentState(TypedDict, total=False):
    # inputs (set once by the runner)
    run_id: str
    question: str
    clarification_answer: str | None
    prior_context: list[dict[str, Any]]
    today: str

    # working memory
    table_catalog: list[dict[str, Any]]
    understanding: QueryUnderstanding
    schema_context: SchemaContext
    plan: AnalysisPlan
    current_step_idx: int
    step_results: dict[str, StepResult]
    facts: list[ComputedFact]
    charts: list[ChartSpec]
    insights: list[Insight]
    verification_feedback: list[str]
    verification: VerificationReport
    response: FinalResponse

    # control
    budget: Budget
    cancel_requested: bool
    termination_reason: TerminationReason | None
    llm_error: dict[str, str] | None  # {code, message} when the model became unavailable

    # observability (append-only)
    trace: Annotated[list[NodeEvent], operator.add]
    errors: Annotated[list[str], operator.add]
