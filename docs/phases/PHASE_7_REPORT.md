# Phase 7 Report — Result analysis, insights, visualizations & frontend integration

| Field | Value |
|---|---|
| Phase | 7 — Result analysis, insight generation and visualizations, with full frontend integration (owner-defined, D52) |
| Status | Done 2026-11-15 |
| Verification | 525 backend tests (102 against PostgreSQL) · 67 web tests · ruff + ruff format + mypy clean · eslint (0 warnings) + tsc + next build clean |

## 1. What already existed, and what this phase added

Phase 5 built the analysis half of the agent: the deterministic analysis engine (10
calculations over real result rows), chart validation, grounding-checked insights, a
reject-only verification judge and the final response. Phase 7 **completed** that half
against the owner's spec and connected it to a real user interface:

| Requirement (owner's spec) | Where it lives |
|---|---|
| Trends, comparisons, significant changes, outliers, correlation ≠ causation, insufficient data | Phase 5 analysis engine (`app/agent/tools/analysis.py`: `trend`, `pct_change`, `group_change`, `outliers_iqr`, `correlation` with its fixed "correlation is not causation" note, `MIN_POINTS` guards) — verified, not rebuilt |
| Chart selection by intent, data types, #categories, time, #metrics | `generate_visualization.v2.md` selection rules + `validate_chart_spec` |
| Line, bar, **horizontal bar, pie/donut**, scatter, **histograms**, tables | `ChartSpec.chart_type` extended; validator rules per type (`app/agent/tools/charts.py`) |
| Structured chart specs, not frontend code | unchanged contract: the agent emits `ChartSpec`; the web app owns all rendering |
| Insights reference results/metrics/pattern/comparison/limitations, no unsupported causal claims | Phase 5 grounding + judge, `generate_insights.v2.md`; `verify_insights.v2.md` keeps uncertainty scoped to the analysis itself |
| Suggested follow-up questions | `FinalResponse.follow_up_questions` (new), grounding-filtered |
| Frontend: answer, metrics, charts, tables, SQL, evidence, follow-ups, loading/error states | new live analyst workspace (`apps/web/src/features/analyst/live/`) |
| Test the complete pipeline on multiple datasets and questions | `tests/integration/test_pipeline_multi_dataset.py` + existing `test_agent_pg.py` |

## 2. Backend changes

### 2.1 Chart vocabulary (`app/agent/state.py`, `app/agent/tools/charts.py`)

`chart_type` is now `bar | grouped_bar | horizontal_bar | line | area | scatter | pie |
donut | histogram | kpi | table`. New validator rules, all checked against the step's
**real** columns and rows:

- `pie`/`donut`: one measure, ≤ 6 slices, no negative values.
- `horizontal_bar`: same category cap as `bar` (≤ 30 rows) — meant for long labels or many categories.
- `histogram`: exactly one **numeric** y column, **no** x and no series (it bins one
  column), and ≥ 10 rows — below that a distribution is noise. The histogram check runs
  *before* the generic "charts need an x axis" rule, which would otherwise shadow it.

An invalid spec never renders a wrong picture: it degrades to `table` with
`fallback_reason` recorded in the result.

### 2.2 Follow-up suggestions (`app/agent/nodes/response.py`)

`SummaryDraft` and `FinalResponse` carry `follow_up_questions` (≤ 3, each ≤ 140 chars,
prompt `compose_response.v2.md`: same dataset, self-contained, no new numbers). The same
grounding engine that checks the summary checks each suggestion: **a suggestion whose
numbers appear in no fact and no result row is dropped, not rewritten** — the model never
gets to smuggle an unverified figure into the UI. On the `llm_unavailable` path the list
is empty; nothing is invented.

### 2.3 Prompt updates

`generate_visualization.v2.md` encodes the owner's selection rules (time → line/area;
categories → bar; two periods → grouped bar; > ~8 or long labels → horizontal bar;
parts-of-whole ≤ 6 → pie/donut; two numeric columns → scatter; distribution with ≥ 10
rows → histogram; single row → KPI; otherwise table). Prompts remain versioned
(`<node>.v<N>.md`, latest wins), so the v1 files still document history.

## 3. Frontend: the live analyst workspace

The Phase 2 workspace ran on recorded demo scenarios. It is replaced by
`src/features/analyst/live/` against the real API — the demo scenario machinery
(`workspace-state.ts`, `analyst-workspace.tsx`, `run-view.tsx`) is deleted.

- **`adapt.ts`** (unit-tested): pure wire→view adapters. PostgreSQL column types map to
  table formats (int→integer, numeric→number), `NULL` cells render empty, midnight
  timestamps trim to dates; chart payloads become typed result tables; fact/cell evidence
  resolves to labeled chips carrying the source `step_id` and row index; the node trace
  becomes the execution timeline (degraded → "recovered") plus a "what's happening now"
  line.
- **`use-live-session.ts`**: one hook per run card — fetches the session + trace, polls
  every 1.5 s while `queued`/`running` (4 s backoff on fetch errors), stops on a terminal
  status and fires `onSettled` once. Terminal sessions cost a single request.
- **`run-card.tsx`**: every session state has a face — queued/running (spinner, live
  activity, expandable trace, **Cancel**), `awaiting_input` (clarification question with
  option buttons that post the answer), `failed`/`cancelled` (error notice),
  `succeeded`/`partial` (answer notice, assumptions, chart cards with table fallback,
  insights with evidence chips that open the right step and highlight the cited rows,
  per-step tables + SQL/attempt history, limitations, usage footer, **Save as report**,
  follow-up chips that ask with one click).
- **`workspace.tsx`**: dataset selector (ready datasets only, with an empty-state CTA to
  Data sources), conversation list (today/earlier), composer (disabled while a run is
  active), optimistic session append, thread auto-scroll.
- **Charts**: `PieChartView` (donut via inner radius, side legend with % of total),
  `ScatterChartView`, histogram binning (`binValues`: nice 1/2/2.5/5×10ᵏ steps, ≤ 12
  bins, unit-tested) rendered through the existing `BarChartView`, and KPI tiles.
  `horizontal_bar` reuses `BarChartView layout="horizontal"`.

Loading, error, and empty states exist at every level: datasets, conversation list,
conversation, session fetch (retry note), and per-chart fallbacks.

## 4. Pipeline proof on multiple datasets (the owner's testing requirement)

`tests/integration/test_pipeline_multi_dataset.py` drives the **API**, not the graph
directly — upload → finalize → conversation → questions — with only the model scripted;
catalog, Guard, executor, analysis engine, grounding and persistence are all real:

- **Dataset A** — demo e-commerce (5 tables): covered by `test_agent_pg.py`
  (revenue-by-category comparison, including a real DB error + recovery, numbers checked
  against independently computed truth).
- **Dataset B** — an uploaded CSV with a different schema (one flat `sales` table:
  order_id, order_date, amount, region). Two questions in one conversation:
  1. *"Which region brought in the most revenue?"* → SQL really runs (per-region totals
     asserted equal to hand-computed truth), `top_n` fact, **pie** chart validates, the
     insight cites the fact, and of two scripted follow-ups the one containing an
     ungrounded "47%" is **dropped** while the clean one survives.
  2. *"Which region had the most orders?"* → counts asserted, **horizontal_bar**
     validates, `total` fact feeds the insight, no follow-ups.
  The conversation thread then shows both exchanges in order.

Unit coverage added alongside: chart-validator rules for donut/horizontal_bar/histogram
(including the <10-rows and histogram-with-x rejections), grounded-follow-up filtering in
the mock graph, and the web adapter/binning tests.

## 5. Verification

| Check | Result |
|---|---|
| Backend tests | **525 passed** (102 PostgreSQL integration) |
| Backend lint/format/types | ruff, ruff format, mypy — clean |
| Web tests | **67 passed** (10 files; new: `adapt.test.ts`, `histogram.test.ts`) |
| Web lint/types/build | eslint 0 warnings · tsc clean · `next build` succeeds |

## 6. Limitations (honest)

- The workspace **polls** (1.5 s) rather than streaming; SSE is Phase 8, and the run card
  is built so only `use-live-session.ts` changes when it lands.
- Scatter charts label each point but don't yet support zoom/brush; histograms bin
  client-side with a fixed ≤ 12-bin rule.
- `conversations.list` loads the first page (50); no infinite scroll yet.
- Result tables in the run card rely on the agent's row cap (500) — no server-side
  pagination of step rows.
- The multi-dataset test scripts the model (deterministic by design); live-model behaviour
  was proven in Phase 5 §9 and remains subject to free-tier quotas.
