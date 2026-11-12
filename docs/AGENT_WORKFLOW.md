# Sageboard — Agent Workflow (LangGraph)

| Field | Value |
|---|---|
| Document | AGENT_WORKFLOW v0.2 |
| Status | Approved 2026-11-12 (v0.2). Decisions: see DECISION_LOG.md |
| Depends on | SYSTEM_ARCHITECTURE.md §2.2, SECURITY_DESIGN.md §4 |

---

## 1. Concepts in brief (mentor notes)

- **LangGraph `StateGraph`.** A directed graph whose nodes are Python functions. Each node reads a shared **state** object and returns a *partial update*. Edges decide which node runs next. **Conditional edges** are functions that look at the state and return the name of the next node. This is how we get retries and branching without hiding control flow inside a prompt.
- **Why not a single "agent loop"?** In a ReAct-style loop the LLM decides everything, including when to stop. We want *explicit, auditable* control. The graph fixes the overall shape (understand → plan → query → analyse → verify) while the LLM handles judgement inside each node. Retries are bounded by code, not by the model's goodwill.
- **Structured outputs.** Each LLM call must return JSON matching a Pydantic schema. Invalid output gets one corrective re-ask, then counts as a node failure. Downstream code never parses free text.
- **Checkpointer.** LangGraph saves state after each node (to Postgres). That enables *interrupts* (pause for a clarifying question and resume later) and post-mortem inspection.
- **Reducer.** For list fields like `trace`, a reducer (`operator.add`) tells LangGraph to *append* node outputs instead of overwriting them.

## 2. Workflow overview

> **Execution order: final (D8, [ADR-0007](adr/0007-schema-retrieval-before-planning.md)).** Schema retrieval runs **before** planning. `understand_query` receives only a lightweight **table catalog** (table names, one-line descriptions, row counts). `retrieve_schema` gathers columns, data types, profiles and relationships. `plan_analysis` always receives `schema_context`: the edge `retrieve_schema → plan_analysis` is the only way in, and the node refuses to run without schema context.

```
                        START
                          │
                 ┌────────▼────────┐
                 │ understand_query│  intent, entities, metrics, time range, ambiguity
                 └────────┬────────┘
         ┌────────────────┼──────────────────────┐
  out_of_scope     needs_clarification       answerable
         │                │                      │
         │        ┌───────▼────────┐             │
         │        │ request_clarif.│ interrupt() │
         │        └───────┬────────┘             │
         │                └──(resume)──▶ understand_query
         │                                       │
         │                             ┌─────────▼────────┐
         │                             │ retrieve_schema  │  bounded tool loop (≤6 tool calls)
         │                             └─────────┬────────┘
         │                             ┌─────────▼────────┐
         │                             │  plan_analysis   │  1–5 steps
         │                             └─────────┬────────┘
         │                 ┌────────────────────▶│ (next step)
         │                 │           ┌─────────▼────────┐
         │                 │           │   generate_sql   │◀──────────────┐
         │                 │           └─────────┬────────┘               │
         │                 │           ┌─────────▼────────┐  rejected &   │
         │                 │           │   validate_sql   │──attempts<3──▶│
         │                 │           └─────────┬────────┘   (repair)    │
         │                 │                ok   │  rejected & attempts=3 ─▶ step_failed
         │                 │           ┌─────────▼────────┐               │
         │                 │           │   execute_sql    │──db error &───┘
         │                 │           └─────────┬────────┘  attempts<3
         │                 │           ┌─────────▼────────┐
         │                 │           │  check_result    │ empty / suspicious → repair or accept-with-note
         │                 │           └─────────┬────────┘
         │                 └── more steps ───────┤
         │                             ┌─────────▼────────┐
         │                             │ analyze_results  │  deterministic facts
         │                             └─────────┬────────┘
         │                             ┌─────────▼────────┐
         │                             │generate_visualiz.│  chart spec (validated)
         │                             └─────────┬────────┘
         │                             ┌─────────▼────────┐
         │                             │generate_insights │◀───────┐
         │                             └─────────┬────────┘        │
         │                             ┌─────────▼────────┐ fail & │
         │                             │ verify_insights  │─rounds<2┘
         │                             └─────────┬────────┘
         │                             ┌─────────▼────────┐
         └────────────────────────────▶│  compose_report  │  (also composes "can't answer" reports)
                                       └─────────┬────────┘
                                                END
```

Global guard: **every** conditional router first checks `budget.exhausted()` or `cancel_requested`. If either is true it routes to `compose_report` with `termination_reason` set, so the user always gets a coherent partial result and never a hang.

Mapping to the 12 requested responsibilities:

| # | Requested step | Node(s) |
|---|---|---|
| 1 | Query understanding | `understand_query`, `request_clarification` |
| 2 | Analytical planning | `plan_analysis` |
| 3 | Schema retrieval | `retrieve_schema` |
| 4 | SQL generation | `generate_sql` (also does repair when given feedback) |
| 5 | SQL validation | `validate_sql` (no LLM: SQL Guard) |
| 6 | SQL execution | `execute_sql` (no LLM: Executor) |
| 7 | Error detection & recovery | routers + `check_result` + repair branch of `generate_sql` |
| 8 | Result analysis | `analyze_results` (deterministic engine + LLM selects which analyses to run) |
| 9 | Visualisation | `generate_visualization` |
| 10 | Insight generation | `generate_insights` |
| 11 | Final verification | `verify_insights` (deterministic grounding + LLM consistency check) |
| 12 | Report generation | `compose_report` |

## 3. Agent state

`AgentState` is a `TypedDict` (LangGraph's most efficient state form). The nested values are Pydantic models, so every piece is validated and serialisable for the checkpointer.

```python
# app/agent/state.py  (blueprint — not final code)
from typing import Annotated, Literal, TypedDict
import operator
from pydantic import BaseModel, Field

class QueryUnderstanding(BaseModel):
    status: Literal["answerable", "needs_clarification", "out_of_scope"]
    restated_question: str
    intent: Literal["aggregate", "trend", "comparison", "ranking",
                    "distribution", "lookup", "correlation", "composition"]
    metrics: list[str]                 # business terms, e.g. "revenue"
    dimensions: list[str]              # e.g. "region", "category"
    filters: list[str]                 # natural-language filters
    time_range: str | None
    assumptions: list[str]             # surfaced to the user verbatim
    clarification_question: str | None = None
    clarification_options: list[str] = []
    out_of_scope_reason: str | None = None

class ColumnContext(BaseModel):
    table: str; column: str; data_type: str
    description: str | None; null_pct: float; distinct_count: int
    sample_values: list[str]           # truncated, low-cardinality only
    min_value: str | None; max_value: str | None

class SchemaContext(BaseModel):
    tables: list[str]
    columns: list[ColumnContext]
    join_paths: list[str]              # "orders.customer_id = customers.id" (declared/inferred)
    rationale: str

class PlanStep(BaseModel):
    step_id: str                       # "s1".."s5"
    purpose: str                       # what this step answers
    expected_output: str               # e.g. "one row per region with revenue"
    depends_on: list[str] = []

class AnalysisPlan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=5)
    final_answer_shape: str

class SQLAttempt(BaseModel):
    attempt: int
    sql: str
    explanation: str
    guard_status: Literal["pending", "accepted", "rejected"]
    guard_violations: list[str] = []
    normalized_sql: str | None = None  # Guard output (LIMIT injected etc.)
    exec_status: Literal["not_run", "ok", "error", "timeout"] = "not_run"
    exec_error: str | None = None      # sanitised DB message
    query_record_id: str | None = None # FK → app.sql_queries

class StepResult(BaseModel):
    step_id: str
    status: Literal["pending", "succeeded", "failed", "skipped"]
    attempts: list[SQLAttempt] = []
    result_id: str | None = None       # FK → app.query_results
    columns: list[tuple[str, str]] = []# (name, pg type)
    row_count: int = 0
    truncated: bool = False
    preview_rows: list[list] = []      # ≤ 50 rows given to LLMs
    notes: list[str] = []              # e.g. "result empty: filter year=2031 matched nothing"

class ComputedFact(BaseModel):
    fact_id: str                       # "f_s1_total_revenue"
    step_id: str
    kind: str                          # total, share, pct_change, rank, top_n, outlier, corr...
    description: str
    value: float | str | list
    unit: str | None
    inputs: dict                       # column refs + row filters used

class ChartSpec(BaseModel):            # validated against StepResult columns
    chart_type: Literal["bar", "grouped_bar", "stacked_bar", "line",
                        "area", "scatter", "pie", "kpi", "table"]
    step_id: str
    x: str | None; y: list[str]; series: str | None
    title: str; subtitle: str | None
    sort: Literal["x_asc", "x_desc", "y_asc", "y_desc", "none"] = "none"
    value_format: Literal["number", "currency", "percent", "integer"] = "number"

class EvidenceRef(BaseModel):
    kind: Literal["fact", "cell", "rows"]
    fact_id: str | None = None
    step_id: str | None = None
    row_indices: list[int] = []
    column: str | None = None

class Insight(BaseModel):
    insight_id: str
    headline: str                      # ≤ 120 chars
    detail: str
    category: Literal["finding", "comparison", "anomaly", "recommendation", "caveat"]
    evidence: list[EvidenceRef] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    verification: Literal["unverified", "verified", "rejected"] = "unverified"
    rejection_reason: str | None = None

class TraceEvent(BaseModel):
    seq: int; ts: str; node: str
    type: str                          # node.started/completed/failed, tool.called, llm.called, sql.*
    payload: dict

class Budget(BaseModel):
    max_llm_calls: int = 25; llm_calls: int = 0
    max_sql_exec: int = 12; sql_exec: int = 0
    max_attempts_per_step: int = 3
    max_verify_rounds: int = 2; verify_rounds: int = 0
    max_schema_tool_calls: int = 6
    deadline_ts: float                 # start + 120 s
    tokens_in: int = 0; tokens_out: int = 0

class AgentState(TypedDict, total=False):
    # identity / inputs (immutable after start)
    run_id: str; user_id: str; dataset_id: str; conversation_id: str
    question: str
    prior_context: list[dict]          # summaries of previous runs in conversation (D16)
    clarification_answer: str | None
    settings: dict                     # user analysis preferences

    # working memory
    table_catalog: list[dict]
    understanding: QueryUnderstanding
    schema_context: SchemaContext
    plan: AnalysisPlan
    current_step_idx: int
    step_results: dict[str, StepResult]
    facts: list[ComputedFact]
    charts: list[ChartSpec]
    insights: list[Insight]
    verification_feedback: list[str]

    # control
    budget: Budget
    cancel_requested: bool
    termination_reason: Literal["completed", "out_of_scope", "budget_exhausted",
                                "cancelled", "all_steps_failed", "error"] | None
    report_id: str | None

    # traceability (append-only via reducer)
    trace: Annotated[list[TraceEvent], operator.add]
```

**State size discipline:** full result sets never live in the state. They live in `app.query_results`; the state holds a `result_id` and a ≤50-row preview. This keeps checkpoints small and stops LLM prompts from bloating.

## 4. Node specifications

Each node is an `async def node(state, config) -> dict` wrapped by `@traced_node`. The wrapper:
- emits `node.started` / `node.completed` / `node.failed`
- measures latency
- increments budget counters
- catches exceptions and turns them into a `node.failed` trace event plus a state flag the router can act on

| Node | LLM? | Tools used | Reads | Writes | Failure behaviour |
|---|---|---|---|---|---|
| `load_context` (entry) | No | `get_table_catalog` | dataset_id, conversation | table_catalog, prior_context, budget | Dataset not ready → terminate `error` |
| `understand_query` | Yes → `QueryUnderstanding` | — | question, catalog, prior_context, clarification_answer | understanding | Invalid JSON twice → terminate `error` |
| `request_clarification` | No | — | understanding | (interrupt; run status `awaiting_input`) | Resume timeout 30 min → terminate `cancelled` |
| `retrieve_schema` | Yes, tool-calling loop | `get_table_schema`, `get_column_values`, `get_join_paths` | understanding, catalog | schema_context | Tool cap reached → proceed with collected context; no relevant tables → `out_of_scope` |
| `plan_analysis` | Yes → `AnalysisPlan` | — | understanding, schema_context (**required**) | plan, current_step_idx=0 | Missing schema_context → node error; plan referencing unknown tables/columns → one re-ask; invalid → one re-ask → terminate |
| `generate_sql` | Yes → `{sql, explanation}` | — | plan step, schema_context, previous attempts + feedback, prior step previews (for dependent steps) | new SQLAttempt | — |
| `validate_sql` | **No** | `sql_guard.validate`, `explain_cost` | latest attempt, catalog, policy | guard_status, violations, normalized_sql | — |
| `execute_sql` | **No** | `executor.run` | normalized_sql | exec_status, result_id, preview, row_count | DB error → sanitised message as feedback |
| `check_result` | No (rules) | — | step result | notes, maybe route to repair | See §5.3 |
| `analyze_results` | Yes (selects analyses) + deterministic engine | `compute_*` analysis tools | step results | facts | Analysis tool error → skip that fact, note it |
| `generate_visualization` | Yes → `list[ChartSpec]` | `validate_chart_spec` | step results (columns/types), understanding.intent | charts | Invalid spec → fall back to `table` |
| `generate_insights` | Yes → `list[Insight]` | — | facts, previews, understanding, verification_feedback | insights | — |
| `verify_insights` | Deterministic + LLM judge | `grounding.check` | insights, facts, results | insight.verification, feedback | Rejected insights are dropped after the max rounds |
| `compose_report` | Yes → summary text (verified insights only) | — | everything | report_id (persisted) | If the LLM fails, a deterministic template report is still produced |

### 4.1 Prompting conventions
- Prompts live in `app/agent/prompts/<node>.v<N>.md`; the version is recorded in each `llm.called` trace event.
- Every prompt carries a *data boundary* block: dataset values, column names and descriptions are wrapped in `<data>…</data>` with an instruction that the content is data, not instructions (prompt-injection mitigation; SECURITY_DESIGN §6).
- Temperature 0 (or the provider minimum) for SQL/plan/verification; ≤0.3 for insight wording.
- Few-shot examples come from the sample dataset only, never from user data.

### 4.2 Insight generation contract
The insight prompt receives **only**: the restated question, the plan, `ComputedFact`s (ID, description, value, unit) and capped previews (with row indices). Instructions:
1. Every number in `headline`/`detail` must equal a fact value or a preview cell (after display rounding).
2. Each insight lists the evidence IDs it used.
3. Recommendations are allowed only as `category="recommendation"`, must cite the finding they follow from, and must be phrased conditionally ("consider…", "worth investigating…").
4. No causal claims ("because", "due to") unless a fact directly supports them. Otherwise use a `caveat`.

## 5. Routing and recovery

### 5.1 Router functions
```python
def route_after_understanding(s) -> str:
    if guard_stop(s): return "compose_report"
    match s["understanding"].status:
        case "out_of_scope":        return "compose_report"
        case "needs_clarification": return ("request_clarification"
                                            if s["settings"]["clarify"] == "ask"
                                            and not s.get("clarification_answer")
                                            else "retrieve_schema")  # assume + state assumption
        case _:                     return "retrieve_schema"

def route_after_validation(s) -> str:
    if guard_stop(s): return "compose_report"
    a = current_attempt(s)
    if a.guard_status == "accepted": return "execute_sql"
    return "generate_sql" if attempts(s) < MAX_ATTEMPTS else "mark_step_failed"

def route_after_execution(s) -> str:
    if guard_stop(s): return "compose_report"
    a = current_attempt(s)
    if a.exec_status == "ok": return "check_result"
    if a.exec_status == "timeout" and attempts(s) < MAX_ATTEMPTS: return "generate_sql"  # feedback: "simplify / aggregate earlier"
    return "generate_sql" if attempts(s) < MAX_ATTEMPTS else "mark_step_failed"

def route_after_step(s) -> str:            # after check_result / mark_step_failed
    if guard_stop(s): return "compose_report"
    if has_next_step(s): return "advance_step"   # increments idx → generate_sql
    if no_step_succeeded(s): return "compose_report"  # termination_reason=all_steps_failed
    return "analyze_results"

def route_after_verification(s) -> str:
    if guard_stop(s): return "compose_report"
    if any_rejected(s) and s["budget"].verify_rounds < MAX_VERIFY: return "generate_insights"
    return "compose_report"                  # still-rejected insights are dropped, logged
```
Dependent steps: when `PlanStep.depends_on` names a failed step, that step is `skipped` with a note.

### 5.2 Repair feedback (what `generate_sql` sees on retry)
- Guard rejection: the list of violation codes plus a human message, e.g. `UNKNOWN_COLUMN: orders.revenue does not exist; available: orders.total_amount, ...`.
- DB error: SQLSTATE plus a sanitised message (no server paths), e.g. `42803 column "p.category" must appear in GROUP BY`.
- Timeout: "query exceeded 10 s; aggregate before joining, add filters, or reduce granularity".
- The previous SQL is included. The prompt asks for a *different* query, and an identical normalised SQL counts as a wasted attempt and goes straight to the next route.

### 5.3 `check_result` rules (deterministic)
| Condition | Action |
|---|---|
| `row_count == 0` and the step has filters | One repair attempt with the feedback "empty result; verify filter values using sampled values: …". If still empty, accept with the note "No matching data". |
| Result has 1 row and all values are NULL | Treat it as empty. |
| `truncated == True` (hit 10k cap) on an aggregation intent | Note that the result was truncated; feedback asks for aggregation (one repair). |
| Duplicate-key explosion heuristic (row_count > 10× the largest joined table's row count) | Repair with feedback "probable fan-out join". |
| Otherwise | Accept. |

### 5.4 Budget enforcement
`Budget` is checked in routers (`guard_stop`) and decremented in `@traced_node`. When the deadline or a call cap is exceeded, `termination_reason="budget_exhausted"` and the run goes to `compose_report`, which writes a partial report that states what was and wasn't completed.

### 5.5 Cancellation
`POST /runs/{id}/cancel` sets a flag in the Run Manager. That flag is copied into state at each node boundary (via `config["configurable"]["cancel_event"]`). The in-flight LLM HTTP call is also cancelled through asyncio task cancellation, and SQL through `pg_cancel_backend` on the executor connection.

## 6. Tools

"Tools" here are typed Python functions with Pydantic input/output models. Some are exposed to the LLM through native tool calling (in `retrieve_schema` and `analyze_results`); others are invoked by nodes directly. **Every tool invocation is recorded** as `tool.called` / `tool.completed` with its inputs, a summary of its outputs, and its latency.

| Tool | Exposed to LLM? | Input → Output | Notes |
|---|---|---|---|
| `get_table_catalog` | No | dataset_id → [{table, description, row_count}] | From `app.dataset_tables`. |
| `get_table_schema` | Yes | {table} → columns with types, descriptions, profiles | Rejects tables outside the dataset. |
| `get_column_values` | Yes | {table, column, search?, limit≤20} → distinct values | Runs a fixed, parameterised query via the Executor. The LLM never writes this SQL. Low-cardinality text columns only. |
| `get_join_paths` | Yes | {tables[]} → candidate join conditions | From declared/inferred FKs (name + type + value-overlap heuristics computed at ingestion). |
| `sql_guard.validate` | No | sql → GuardResult | Pure. See SECURITY_DESIGN §4. |
| `explain_cost` | No | normalized_sql → {total_cost, plan_rows} | `EXPLAIN (FORMAT JSON)` via the Executor. Rejects above the ceiling. |
| `executor.run` | No | normalized_sql → ResultHandle | Read-only, timed, capped. |
| `compute_total / compute_share / compute_pct_change / compute_rank / compute_top_n / compute_outliers_iqr / compute_correlation / compute_period_series` | Yes (in `analyze_results`) | {step_id, column refs, options} → ComputedFact | Implemented in `app/analysis`. They operate on the stored full result, not on the preview. |
| `validate_chart_spec` | No | ChartSpec + columns → ok / errors | E.g. a line chart needs an ordered x (date/number); pie needs ≤6 categories and non-negative values. |
| `grounding.check` | No | insights + facts + results → per-insight verdicts | §7. |

## 7. Verification (grounding) design

**Pass 1 — deterministic (authoritative):**
1. Extract numeric tokens from headline + detail (integers, decimals, percentages, currency, "1.2M", "3x").
2. Normalise each one (strip currency, expand K/M/B, % → value).
3. Collect allowed values from cited evidence only: fact values plus cited preview cells. Add derived display forms: rounding to 0–2 dp, percentages ×100, abbreviations.
4. Each extracted number must match an allowed value within tolerance (relative 0.5% or display rounding). Years and dates that appear in the question or plan's time range are allowed.
5. Evidence IDs must exist, and each referenced column must exist in that step's result.
6. Any failure → `rejected` with a reason (`UNGROUNDED_NUMBER 23.4%`, `UNKNOWN_EVIDENCE f_s9`).

**Pass 2 — LLM consistency judge (advisory, can only reject):** given the insight and its evidence, answer `{supported: bool, issue?}` for directional claims ("increased", "highest", "declined"). It can never upgrade a deterministic rejection.

Rejected insights and their reasons go back to `generate_insights` as feedback (≤2 rounds). Any that are still rejected are dropped and recorded in the trace, so the UI can show "2 insights removed by verification" in the Inspector.

## 8. Events emitted (consumed by SSE; schema in API_SPECIFICATION §5)
`run.started, node.started, node.completed, node.failed, tool.called, tool.completed, llm.called (model, prompt_version, tokens, latency — no prompt text), sql.generated, sql.validated, sql.rejected, sql.executed, sql.failed, step.completed, step.failed, facts.computed, chart.generated, insights.generated, insights.verified, run.awaiting_input, run.resumed, run.completed, run.failed, run.cancelled`.

## 9. Graph assembly (blueprint)
```python
g = StateGraph(AgentState)
for name, fn in NODES.items(): g.add_node(name, fn)
g.add_edge(START, "load_context")
g.add_edge("load_context", "understand_query")
g.add_conditional_edges("understand_query", route_after_understanding,
    ["request_clarification", "retrieve_schema", "compose_report"])
g.add_edge("request_clarification", "understand_query")
g.add_edge("retrieve_schema", "plan_analysis")
g.add_edge("plan_analysis", "generate_sql")
g.add_edge("generate_sql", "validate_sql")
g.add_conditional_edges("validate_sql", route_after_validation,
    ["execute_sql", "generate_sql", "mark_step_failed", "compose_report"])
g.add_conditional_edges("execute_sql", route_after_execution,
    ["check_result", "generate_sql", "mark_step_failed", "compose_report"])
g.add_conditional_edges("check_result", route_after_check,
    ["generate_sql", "route_step"])  # route_step is a no-op node using route_after_step
...
g.add_edge("compose_report", END)
graph = g.compile(checkpointer=AsyncPostgresSaver(...))
```
A graph-structure test asserts the compiled graph's node and edge sets, so routing can't drift unnoticed.

## 10. Example trace (sample dataset)
Q: *"Which 3 regions grew revenue fastest from Q2 to Q3 2025?"*
1. understand → intent=ranking, metric=revenue, dimension=region, time=Q2 vs Q3 2025, assumption "revenue = sum(order_items.quantity × unit_price) excluding cancelled orders"
2. retrieve_schema → tool calls: get_table_schema(orders), get_table_schema(order_items), get_table_schema(regions), get_column_values(orders.status)
3. plan → s1: revenue by region per quarter (Q2, Q3 2025)
4. generate_sql attempt 1 → guard rejects `UNKNOWN_COLUMN orders.region` → attempt 2 joins customers → regions → accepted → executed (16 rows)
5. analyze → compute_pct_change(by region, Q2→Q3), compute_rank
6. visualise → grouped_bar (x=region, y=[q2_revenue, q3_revenue])
7. insights → 3 findings + 1 caveat ("Q3 includes only orders through 2025-09-28") → all verified
8. report → persisted, `run.completed`
