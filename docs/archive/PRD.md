# Sageboard — Product Requirements Document (archived)

> **Archived.** This is the original product brief (v0.2, 2026-11-12). It records intent, users and requirements, but the built system differs in places: no streaming transport (the UI polls), no pinned dashboard widgets, CSV upload only, no XLSX. For the system as built see [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) and [DEVELOPMENT.md](../development/DEVELOPMENT.md). Names of other documents below refer to the pre-consolidation set.

| Field | Value |
|---|---|
| Product | Sageboard — An Agentic AI System for Autonomous Business Data Analysis |
| Document | PRD v0.2 |
| Status | Approved 2026-11-12 (v0.2). Decisions: see DECISION_LOG.md |
| Related | SYSTEM_ARCHITECTURE.md, AGENT_WORKFLOW.md, DEVELOPMENT_ROADMAP.md (open decisions live there, §6) |

---

## 1. Problem statement

Business analysts, students and small-business owners have data (sales exports, CRM dumps, inventory sheets) but answering a question like *"Which product categories lost revenue share in Q3, and in which regions?"* takes SQL fluency, knowledge of the schema, and the discipline to check results before drawing conclusions.

General-purpose chatbots make this worse: they write plausible SQL against columns that don't exist, or describe "trends" they never computed.

Sageboard is an **autonomous data analyst**. It answers business questions in natural language and **shows its work**: the plan, every SQL query, every result set, the charts, and evidence for every claim. When it is unsure or a query fails, it recovers or says so. It never makes up a number.

## 2. Product principles

1. **Evidence before prose.** Every insight is linked to the query result rows or computed statistic that supports it. An insight that can't be linked gets dropped.
2. **Visible agency.** The user sees each agent step as it runs (understanding → plan → SQL → validation → execution → analysis → verification), not a spinner followed by an answer.
3. **Safe by construction.** Read-only access, independent SQL validation, no execution of LLM-generated code. Security is enforced in layers, not just by the prompt.
4. **Honest failure.** "I couldn't answer this because the dataset has no cost column" beats a guessed margin.
5. **Analyst-grade craft.** The UI is a professional tool: dense where it should be, calm, and typographically strong.

## 3. Target users and personas

| Persona | Context | Primary need | SQL skill |
|---|---|---|---|
| **Priya — Business Analyst** (mid-size retailer) | Answers ad-hoc questions from managers each week | Fast, trustworthy answers with SQL she can audit and reuse | Intermediate |
| **Arjun — Data Analyst** | Owns reporting; tired of one-off requests | Lets stakeholders self-serve while he checks the SQL trail | Advanced |
| **Meera — Student** | Learning analytics, working on case-study datasets | Learns *how* a question becomes a query; sees the plan and SQL | Beginner |
| **Rahul — Small business owner** | Shop with exported POS/inventory CSVs | Plain-language answers and recommendations; no SQL | None |

## 4. Goals and non-goals

### 4.1 Goals (MVP)
- G1. A user can upload a CSV/XLSX dataset (or use a bundled sample) and ask questions about it in natural language.
- G2. The agent produces a correct, validated, read-only SQL analysis with a visible execution trace.
- G3. Every answer includes ≥1 result table, a chart when the data suits one, and grounded insights with evidence links.
- G4. Results can be saved as reports and pinned to a dashboard.
- G5. All query history is browsable and re-runnable (with re-validation).

### 4.2 Non-goals (MVP)
- Writing to user data (no INSERT/UPDATE/DELETE, ever).
- Executing LLM-generated Python, R, or shell code.
- Live connections to arbitrary external databases (post-MVP; see Open Decision D2).
- Real-time / streaming data sources.
- Team collaboration, shared workspaces and permissions (post-MVP; D4).
- Forecasting and ML models. Simple descriptive statistics only; trend statements are limited to what the data directly shows.

## 5. Scope by page

Each page below lists its purpose, core elements and required states. **All pages must have designed loading, empty, error and success states.**

### 5.1 Landing page (`/`)
- **Purpose:** explain the product to evaluators and new users; drive sign-up.
- **Sections:** hero (headline + a static, real screenshot of a workspace run, no illustrations), "How it works" (the agent pipeline shown as a horizontal step diagram), trust and safety (read-only, validated SQL, grounded insights), sample questions, footer.
- **Constraints:** no gradients, no stock AI imagery, no ornamental animation. One subtle reveal on the pipeline diagram at most.

### 5.2 Analytics dashboard (`/app/dashboard`)
- **Purpose:** workspace home. Pinned charts/KPIs from past analyses plus workspace activity.
- **Elements:** KPI tiles (pinned single-value results), pinned chart widgets (grid, reorderable), "Recent analyses" list, dataset health summary (row counts, last updated).
- **Behaviour:** refreshing a widget re-runs its **stored, re-validated SQL** directly. No LLM call happens on refresh (D11).
- **Empty state:** guide to "Ask your first question" with 3 sample questions for the active dataset.

### 5.3 AI analyst workspace (`/app/analyst`, `/app/analyst/[conversationId]`)
- **Purpose:** the core experience.
- **Layout (desktop):** three regions:
  - left: conversation list (collapsible)
  - centre: the thread (question → run card)
  - right: the **Run Inspector** (trace timeline, SQL, schema used, token/latency stats)
- **Run card contents (in order):**
  1. Interpreted question and assumptions
  2. Analysis plan (numbered steps)
  3. Live step timeline (streamed)
  4. Result tables (sortable, paginated, CSV export)
  5. Chart(s)
  6. Insights, each with an evidence chip that opens the supporting rows/statistic
  7. Limitations / caveats
  8. Actions: *Save as report*, *Pin chart*, *Copy SQL*, *Re-run*
- **Clarification:** when the agent asks a clarifying question, the run pauses and shows answer chips plus a free-text box (D9).
- **Dataset selector** sits in the composer; a conversation is bound to one dataset.
- **Error states:** recoverable error (shown inline with the recovery attempt in the trace), terminal failure (a plain-language reason plus what the user could try), cancelled run.

### 5.4 Data sources & dataset management (`/app/data`)
- **Purpose:** upload, inspect and describe datasets.
- **Elements:**
  - upload (drag and drop, CSV/XLSX, progress, validation report)
  - dataset list
  - dataset detail: tables, columns, inferred types, null %, distinct counts, min/max, sample values, 50-row preview
  - editable column descriptions (a business glossary; D18)
  - delete dataset
- **Ingestion report:** rows loaded, rows rejected (with reasons), type inference decisions the user can override before finalising.

### 5.5 Query history (`/app/history`)
- **Purpose:** audit trail of every analysis run and SQL query.
- **Elements:** filterable table (date, dataset, question, status, duration, #queries), detail drawer with full trace and SQL, "re-run" (creates a new run), "open in workspace".
- **Filters:** status (succeeded / failed / cancelled / needs clarification), dataset, date range, text search on question.

### 5.6 Reports (`/app/reports`, `/app/reports/[id]`)
- **Purpose:** durable, shareable write-ups generated from runs.
- **Report structure:** title, question, executive summary (grounded), sections (charts + tables + insights with evidence), methodology (SQL appendix), limitations, generated-at and dataset version.
- **Actions:** rename, edit summary text (user edits are marked as user-authored), export Markdown, print-to-PDF (print stylesheet; D10), delete.

### 5.7 Settings (`/app/settings`)
- Profile (name, email, password change).
- Analysis preferences: default row-limit, whether to auto-generate charts, clarification behaviour (ask vs. assume-and-state).
- Usage: runs this month, LLM tokens used, per-day limit (D20).
- Danger zone: delete account and all data.

## 6. Functional requirements

IDs are referenced by the tests in TESTING_STRATEGY.md.

### 6.1 Datasets
| ID | Requirement |
|---|---|
| FR-D1 | Users can upload CSV (UTF-8, comma/semicolon/tab auto-detected) and XLSX (first sheet or chosen sheets) up to the configured size limit (default 25 MB; D15). |
| FR-D2 | The system infers column types (integer, numeric, boolean, date, timestamp, text) and lets the user override them before finalising. |
| FR-D3 | Column names are normalised to safe snake_case identifiers. The original header is kept as `display_name`. |
| FR-D4 | Each dataset is stored in an isolated PostgreSQL schema accessible only through a dataset-scoped read-only role. |
| FR-D5 | The system computes and stores a column profile: null %, distinct count, min/max, top-k values for low-cardinality text. |
| FR-D6 | Users can add descriptions to tables and columns. Descriptions are included in the agent's schema context. |
| FR-D7 | A bundled sample dataset (retail sales: orders, order_items, products, customers, regions) is available to every new user. |

### 6.2 Analysis runs
| ID | Requirement |
|---|---|
| FR-A1 | A user submits a natural-language question against a selected dataset; a run is created and starts asynchronously. |
| FR-A2 | Run progress is streamed to the client as typed events (SSE). |
| FR-A3 | The agent classifies the question as answerable, ambiguous, or out-of-scope before generating any SQL. |
| FR-A4 | The agent produces an explicit analysis plan of 1–5 steps (D-config), each mapped to ≥1 SQL query. |
| FR-A5 | Every generated SQL statement passes the SQL Guard (AGENT_WORKFLOW §6, SECURITY_DESIGN §4) before execution. Rejected SQL is never executed. |
| FR-A6 | On a validation or execution error, the agent attempts bounded repair (default max 3 attempts per step) using the error message as feedback. |
| FR-A7 | Result analysis uses deterministic, pre-written statistics functions. The LLM interprets computed facts; it doesn't compute numbers itself. |
| FR-A8 | Visualisation specs come from a fixed set of chart types and are validated against the result columns and types. |
| FR-A9 | Every insight references ≥1 evidence item (query result cell/row range or computed fact ID). The verifier rejects insights whose numbers can't be traced to evidence. |
| FR-A10 | Users can cancel a running analysis. |
| FR-A11 | Follow-up questions in the same conversation can reference the prior run (D16). |
| FR-A12 | The full trace is persisted: node executions, tool calls, LLM calls (with token counts), SQL attempts, validation outcomes. |

### 6.3 Reports, dashboard, history
| ID | Requirement |
|---|---|
| FR-R1 | A successful run can be saved as a report; the report snapshot is immutable apart from title and summary edits. |
| FR-R2 | Reports export as Markdown and print cleanly to PDF. |
| FR-B1 | A chart or single-value result can be pinned to the dashboard as a widget. |
| FR-B2 | Refreshing a widget re-validates and re-executes the stored SQL without any LLM call. |
| FR-H1 | All runs and SQL queries are listed with filters and full-text search on the question. |

### 6.4 Accounts
| ID | Requirement |
|---|---|
| FR-U1 | Email + password registration and login; session via httpOnly secure cookie (D3). |
| FR-U2 | Users only see their own datasets, runs, reports and widgets. |
| FR-U3 | Users can delete their account; all their datasets (schemas), runs and reports are hard-deleted. |

## 7. Non-functional requirements

| ID | Category | Target |
|---|---|---|
| NFR-1 | Latency | Time to first streamed event < 1.5 s. Simple single-query question end-to-end p50 < 20 s, p95 < 45 s. |
| NFR-2 | Bounded execution | Hard limits per run: 120 s wall clock, 25 LLM calls, 12 SQL executions, 3 repair attempts per step, 2 insight re-verifications. |
| NFR-3 | Query safety | SQL `statement_timeout` 10 s; result fetch cap 10,000 rows; EXPLAIN cost ceiling (configurable). |
| NFR-4 | Accuracy | ≥ 80% execution accuracy on the internal evaluation set (TESTING_STRATEGY §7). Hallucinated-number rate in verified insights = 0 on the eval set. |
| NFR-5 | Security | Zero write operations possible from the agent path, verified by the adversarial test suite. |
| NFR-6 | Accessibility | WCAG 2.2 AA contrast; full keyboard navigation of the workspace; charts have table alternatives. |
| NFR-7 | Responsiveness | Fully usable ≥ 1280 px; workspace adapts to tablet (Inspector becomes a drawer); read-only views (reports, history) usable at 375 px. |
| NFR-8 | Observability | Every run has a trace ID. Logs are structured JSON with run_id and user_id; no secrets or raw dataset rows in logs. |
| NFR-9 | Data minimisation | The LLM receives schema, profiles and **capped** result samples/aggregates (default ≤ 50 rows per result), never full tables (D12). |

## 8. Design direction (summary — full tokens are defined in Phase 7)

**Palette (final, D23 — implemented as tokens in `apps/web/src/app/globals.css`):**

| Token | Hex | Use |
|---|---|---|
| `navy` | `#192C35` | Brand headings, dark bands, emphasis surfaces |
| `forest` | `#315B50` | Primary actions, selection, positive change, chart series 1 |
| `sage` | `#C4DDCB` | Selection, light fills, chart comparison series (`sage-600`) |
| `warm` | `#F4F2EC` | App background |
| `paper` | `#FFFFFF` | Tables, charts and content surfaces |
| `amber` | `#D99A57` | Accent, evidence highlight, warnings (fills only; `amber-ink` #8A5A1F for text) |
| `ink` | `#202925` | Main text (13.4:1 on warm) |
| `ink-2` / `ink-3` | `#66706A` / `#727B76` | Secondary text (AA-tuned) / icons, placeholders, large text |
| `rust` | `#A3412E` | Errors, negative change, destructive |

- **Shape:** 4 px radius default and 6 px for overlays. Separate regions with hairline borders (1 px `sage-300`) rather than card shadows.
- **Typography (D14):** IBM Plex Sans (UI), IBM Plex Mono (SQL, axis labels, figures), Source Serif 4 for page titles, landing and report headings (editorial voice).
- **Motion:** 120–180 ms ease-out for state changes; streamed trace steps fade in; no looping or decorative motion; respects `prefers-reduced-motion`.
- **Charts:** Recharts with a restrained categorical palette (forest, navy, sage, amber, slate). Axis labels in mono tabular figures; no 3D, no pie charts above 5 slices.

## 9. Success metrics (for evaluation/demo)

- Eval-set execution accuracy (NFR-4) reported with the test run that produced it.
- % of runs that needed at least one repair and then succeeded (shows recovery works).
- Median run latency; median LLM calls per run.
- 0 SQL Guard bypasses in the adversarial suite.
- Qualitative: a reviewer can trace any insight back to a SQL result in ≤ 2 clicks.

## 10. Assumptions made explicit

| # | Assumption | Why | If wrong |
|---|---|---|---|
| A1 | MVP data sources are uploaded files + sample dataset | Avoids SSRF/credential handling in MVP; keeps demo reliable | Add Phase 12b "External Postgres connectors" |
| A2 | Single-user workspaces | Enough for evaluation; isolation still enforced | Add workspace_members and roles |
| A3 | English questions only | Prompting and eval set are in English | Add multilingual eval cases |
| A4 | Datasets ≤ ~1M rows | Free-tier managed Postgres sizes | Add a warehouse (DuckDB/ClickHouse) |
| A5 | One LLM provider configured at a time, behind an adapter | Simpler ops and cost control | Adapter already allows switching |

All other open questions are consolidated in **DEVELOPMENT_ROADMAP.md §6 (Open Decisions)**.
