# Sageboard decisions

The record of architectural decisions (D-numbers are referenced from code and tests) followed by the seven architecture decision records. Statuses: **Final** = approved by the project owner; **Default** = accepted blueprint recommendation; **Implemented** = built as described. For the current system see [ARCHITECTURE.md](../architecture/ARCHITECTURE.md).

## Decision log

| ID | Decision | Status | Outcome | Record |
|---|---|---|---|---|
| D1 | LLM provider & model | **Final** (2026-11-12) | Provider-agnostic `LLMClient` adapter; Anthropic / OpenAI / Gemini / mock selected by `LLM_PROVIDER`. Mock in development and tests, refused in production. Provider evaluation (access, pricing, tool calling, structured outputs) moved to Phase 6. Adapters for all three built in Phase 5; mock = no model (D42) | ADR-0006 |
| D2 | MVP data sources | Default | CSV/XLSX upload + sample dataset; external Postgres post-MVP | archive/PRD.md |
| D3 | Auth approach | Default | Custom FastAPI auth: argon2id, JWT access + rotating refresh, httpOnly cookies | SECURITY.md |
| D4 | Tenancy | Default | Single-user workspaces | archive/PRD.md |
| D5 | Database host & permissions | **Final** (2026-11-12) | Neon PostgreSQL 16 in production (subject to the role-management checks in ADR-0002); native PostgreSQL 16 locally (Docker optional). App role, per-dataset read-only roles, NOINHERIT executor, `SET LOCAL ROLE` per transaction | ADR-0002 |
| D6 | Run execution | Default | In-process asyncio tasks + persisted events and checkpoints | ADR-0004 |
| D7 | Streaming transport | Default | SSE + polling fallback | ADR-0003 |
| D8 | Step order | **Final** (2026-11-12) | `understand_query` (table catalog only) → `retrieve_schema` (full schema) → `plan_analysis` (must receive schema) | ADR-0007 |
| D9 | Ambiguity handling | Default | Hybrid: ask only when blocking; user setting can force ask/assume | ARCHITECTURE.md |
| D10 | Report export | Default | In-app report + Markdown + print-CSS PDF | archive/PRD.md |
| D11 | Dashboard semantics | Default | Pinned widgets re-execute stored, re-validated SQL; no LLM | archive/PRD.md |
| D12 | What the LLM sees | Default | Schema + profiles + ≤ 50-row previews + facts; sensitive columns masked | SECURITY.md |
| D13 | Package managers & tooling | Default (implemented) | pnpm + uv; ruff, mypy strict, ESLint, Prettier, Vitest, pytest | ADR-0001 |
| D14 | Typography | Default (implemented) | IBM Plex Sans / Mono and Source Serif 4 (display/headings), all self-hosted via Fontsource | archive/PRD.md |
| D23 | Brand palette | **Final** (2026-11-12, owner) | Navy #192C35 · forest #315B50 · sage #C4DDCB · warm white #F4F2EC · amber #D99A57 · text #202925 · secondary #727B76. For AA contrast, small secondary text uses #66706A (4.6:1); #727B76 is kept for icons, placeholders and large text. Amber is never small text on light surfaces | archive/PRD.md, `apps/web/src/app/globals.css` |
| D24 | Phase order | **Final** (2026-11-12, owner) | Frontend UI with demo data is Phase 2; authentication moves to Phase 3 and later phases shift by one | DEVELOPMENT.md |
| D25 | Demo data policy (Phase 2) | **Final** | Mock data only in `src/mocks`, read through `src/lib/data`; every figure is derived from one seeded series; the analyst replays recorded sample runs only for their exact questions and never answers other questions; demo state is labelled in the UI | ADR-0006, |
| D15 | Upload limits | Default | 25 MB, 1M rows, 200 columns, 10 sheets | SECURITY.md |
| D16 | Follow-up questions | Default | Summaries of the last 3 runs in the conversation | ARCHITECTURE.md |
| D17 | Tracing | Default | DB trace always; LangSmith optional, off | ARCHITECTURE.md |
| D18 | Business glossary | Default | Table/column descriptions + semantic role | ARCHITECTURE.md |
| D19 | Data retention | Default | Query results 30 days unless referenced | ARCHITECTURE.md |
| D20 | Usage limits | Default | 100 runs/day, 2 concurrent, configurable token cap | ARCHITECTURE.md |
| D21 | Component base | Default | Radix primitives for behaviour + custom styling | ARCHITECTURE.md |
| D22 | Team split | Pending | Owner to confirm ownership per area | DEVELOPMENT.md |
| D26 | Phase order v0.3 | **Final** (2026-11-13, owner) | Phase 3 = database & data ingestion; authentication moves after it (its exact slot to be confirmed) | DEVELOPMENT.md |
| D27 | Identity before auth | Default (implemented) | `AUTH_MODE=demo`: every request acts as the seeded `demo@sageboard.local`. Startup refuses it when `ENV=production`. All services take the user explicitly, so auth replaces one dependency (`get_current_user`) | `app/api/deps.py`, `app/core/config.py` |
| D28 | Upload format | Default (implemented) | CSV (UTF-8, BOM ok; `,` `;` tab `\|` sniffed) only. Excel is refused with “save as CSV UTF-8”. Limits: 25 MB, 1 M rows, 200 columns, 10 000 chars per cell (configurable) | SECURITY.md, `app/ingestion` |
| D29 | Upload flow | Default (implemented) | Two steps: upload → analysis/review (nothing loaded) → finalize with optional type overrides. Rows with the wrong field count or values that don't fit the chosen type are skipped and reported up to 5 %; above that the load is refused and fully rolled back. Unreviewed files are deleted after 60 min | ARCHITECTURE.md |
| D30 | Uploaded table naming | Default (implemented) | One table per uploaded CSV, named after the normalised dataset name. Headers that collide after normalisation are **rejected** with both names shown, rather than silently suffixed `_2` (replaces ARCHITECTURE.md v0.2 §4) | ARCHITECTURE.md |
| D31 | Sensitive columns | Default (implemented) | Detected by name and value shape; stored with counts only (no samples, min/max); masked `«redacted»` in previews unless the owner passes `reveal_sensitive=true`; owners can toggle per column. The schema catalog never emits their values | ARCHITECTURE.md, SECURITY.md |
| D32 | Connection FK | Implemented (migration 0003) | `datasets.connection_id` is `NO ACTION DEFERRABLE INITIALLY DEFERRED`, so user deletion cascades while deleting an in-use connection is still refused | ARCHITECTURE.md |
| D33 | Preview auditing | Default (implemented) | Previews run through the read-only executor and are recorded in `query_executions` (`origin=preview`, `guard_status=not_applicable`: the SQL is built from catalog identifiers, never from user text) | `app/services/datasets.py` |
| D34 | Auth in Phase 4 | **Final** (2026-11-14, owner) | Authentication and user-level dataset ownership ship with the backend API, before the app is made public | DEVELOPMENT.md |
| D35 | Session model | Default (implemented) | JWT access cookie (15 min) + rotating refresh cookie (14 days, hashed, family reuse detection, 30 s race grace) + CSRF double-submit (token also in the response body). `AUTH_MODE=session` is the default; `demo` stays for local experiments only | SECURITY.md |
| D36 | Refresh is CSRF-exempt | Implemented | After a reload the client has no CSRF token until it refreshes. A forged refresh only rotates the victim's own cookies. Found by the browser test (silent refresh was 403) | ARCHITECTURE.md |
| D37 | Per-user sample data | Implemented | `POST /datasets/demo` gives each user their own copy of the e-commerce demo (own schema and reader role), on request from the Data page; not at sign-up | ARCHITECTURE.md |
| D38 | Sessions without an agent | Implemented | Asking a question stores a `queued` session and says `agent_available: false`. No answer is generated until the agent phase (no fake responses) | ARCHITECTURE.md |
| D39 | API naming | Implemented | v0.2 "runs" are exposed as `/analysis-sessions` (plain `/sessions` would clash with sign-in sessions); questions are posted to `/conversations/{id}/sessions` | ARCHITECTURE.md |
| D40 | Frontend data access | Implemented | Client-side fetching through one typed client (CSRF header, single-flight refresh, one error type). Sign-in, data sources, history and reports are live; Dashboard and Analyst keep labelled sample runs until the agent exists | apps/web |
| D41 | Session changes reload the page | Implemented | Next.js keeps visited pages' state alive; a full page load on sign-in, sign-out and expiry guarantees nothing from the previous session (data or "signed out" state) survives. Found by the browser test | SECURITY.md |
| D42 | Mock provider = no model | **Implemented** (Phase 5) | `LLM_PROVIDER=mock` builds no model: questions stay `queued` with an explanation. Scripted model replies exist only in the test suite (`tests/agent/fakes.py`), where they drive the real graph, Guard and (in integration tests) the real database. Amends ADR-0006 §3, which allowed the mock in development: a development mock would be a fake AI response | ADR-0006 |
| D43 | Phase 5 scope | **Final** (2026-11-14, owner) | Phase 5 = the full agentic core (12 responsibilities as LangGraph nodes, SQL Guard, error recovery, analysis, charts, insights, verification, final response) — the former roadmap phases 5–7. Remaining items move to Phases 6–7 | DEVELOPMENT.md |
| D44 | Separate Error Recovery node | Implemented | `recover_error` classifies the failure in code (Guard code / SQLSTATE → category + hint), gathers error-specific schema, regenerates, and sends the new SQL back through the Guard. ≤ 3 attempts per step; identical SQL is rejected as `REPEATED_QUERY` | ARCHITECTURE.md |
| D45 | Tool calling via structured outputs | Implemented | `retrieve_schema` is a bounded loop where each model turn is a validated `SchemaAction`; tools run in code; errors return as observations. Same behaviour on every provider | ARCHITECTURE.md |
| D46 | Clarification is a conversation turn | Implemented | A run that needs clarification ends `awaiting_input`; the next message re-runs the original question with `clarification_answer`. No LangGraph checkpointer/interrupt (no extra Postgres driver, survives restarts) | ARCHITECTURE.md |
| D47 | Grounding is authoritative, the judge is reject-only | Implemented | Numbers must match cited facts/cells within display rounding; the model judge can only reject. Still-rejected insights are removed after 2 rounds and listed; the final summary is grounding-checked with a deterministic fallback | ARCHITECTURE.md |
| D48 | In-process run manager | Implemented | Runs are asyncio tasks in the API (ADR-0004), with a concurrency cap and cancel at node boundaries. Node events are persisted live in `agent_node_runs` (migration 0005); runs left `running` by a restart are marked `failed: INTERRUPTED` | ADR-0004 |
| D49 | Agent cost controls | Implemented | Per run: ≤ 30 model calls, ≤ 14 SQL executions, 180 s deadline, ≤ 5,000 result rows (all configurable). Per user: 30 questions/hour | ARCHITECTURE.md |
| D50 | Free LLM for development | **Final** (2026-11-14, owner) | Google Gemini via Google AI Studio's free tier: `LLM_PROVIDER=google`, `LLM_MODEL=gemini-3.8-flash`, `GOOGLE_API_KEY` (backend `.env` only). No paid usage: key from a project without billing; no automatic provider/model/tier switching. Client-side pacing (`LLM_REQUESTS_PER_MINUTE`), a daily model-call cap counted from live traces (`LLM_DAILY_REQUEST_LIMIT`, midnight Pacific), Google 429s classified (per-minute → wait `retryDelay`; daily quota / `limit: 0` / bad key → stop the run with the reason). Free-tier prompts may be used by Google to improve its products, so use non-sensitive data | ADR-0006 |
| D51 | Phase 6 = SQL safety, execution & self-correction | **Final** (2026-11-15, owner) | Owner-defined scope (the former Phase 7 hardening): unsafe queries (writes, DDL, other schemas, server functions, stacked statements) and permission errors are **never retried** — recovery is for honest mistakes only; SQLSTATE 25006 (DB read-only defence fired) is treated as a Guard bug, not retried. Design caps enforced: recursive CTEs rejected, ≤ 6 joins, subquery depth ≤ 4. EXPLAIN cost gate (`EXECUTOR_MAX_PLAN_COST`, default 5M units, recoverable `too_expensive`). In-flight SQL cancelled via asyncpg task cancellation (`pg_cancel_backend` mechanism). Hypothesis fuzzing + Guard-bypass isolation tests. Real-model evaluation moves to Phase 7 | [SECURITY.md](../security/SECURITY.md) |
| D52 | Phase 7 = result analysis, insights, visualizations & frontend integration | **Final** (2026-11-15, owner) | Owner-defined scope, superseding the roadmap's "real-model evaluation" slot (evaluation now runs continuously and gets a dedicated pass before deployment). Backend: chart vocabulary extended to `horizontal_bar`, `pie`/`donut`, `scatter`, `histogram` (all validated against real step results, falling back to a table with the reason recorded); `FinalResponse.follow_up_questions` (≤ 3, grounding-checked — a suggestion with an ungrounded number is dropped, not rewritten). Frontend: the analyst workspace switches from recorded demo scenarios to the live API (conversations, polling run cards with live trace + cancel, charts via Recharts incl. pie/donut/scatter/histogram/KPI tiles, evidence chips that highlight source rows, per-step SQL + attempts, follow-up chips, save-as-report). Pipeline proven end-to-end on two datasets (demo e-commerce + an uploaded CSV with a different schema) with multiple questions | [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) |
| D53 | Conversation memory is deterministic, per conversation, relevance-gated | **Final** (2026-11-15, owner spec) | Each finished turn stores a compact memory record in `analysis_sessions.memory` (JSONB, migration 0006), built **by code** from the stored understanding, result and summary — no model call, so it cannot invent anything. A new question is shown at most 3 earlier turns of *its own conversation*: the previous turn when the wording is a follow-up ("and…", "compare it…", pronouns, very short), otherwise turns whose topic words overlap (≥ 34% of the question's topic words) with the question; scan window 20 turns, 3,500-character budget. Candidates are fetched with owner, dataset and conversation in the WHERE clause, so another user's, conversation's or dataset's turns are never candidates; a turn recorded against an older dataset version keeps its shape but drops its numbers. `understand_query.v2` teaches reference resolution ("compare it with last month" → restated standalone question) and forbids carrying numbers forward. Memory across conversations is deliberately not built (it would be the main isolation risk) | [ARCHITECTURE.md §7](../architecture/ARCHITECTURE.md) |
| D54 | History reuses what runs already store | **Final** (2026-11-15) | The owner's "save question, dataset, status, plan, SQL, results, insights, timestamp" was already satisfied by `analysis_sessions` (+ `result` JSONB) and `query_executions`; Phase 8 adds no duplicate tables. `GET /history/sessions` now returns `HistoryItem` (dataset and conversation names, answer snippet, finding and query counts, newest report id — counts computed in SQL so the stored result is never loaded for a list) and searches question, answer **and** dataset name. Reopening and continuing are deep links (`/app/analyst?conversation=&session=`) onto the same conversation, so a follow-up uses the memory in D53 | [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) |
| D55 | Reports: snapshot v2, server-rendered PDF, numbers re-checked at read time | **Final** (2026-11-15) | A report copies everything from the stored result when saved (dataset tables, methodology, SQL per step, verified findings, recommendations, chart data, limitations); nothing is regenerated and no model is called. The PDF is rendered on the server with reportlab (pure Python, bundled Bitstream Vera font, vector charts, `asyncio.to_thread`) — all text is XML-escaped and glyph-sanitised. "Numbers match the stored results" is enforced by the same grounding engine the agent uses, run when a report is **read or exported** (not just saved): a user-edited summary with a number absent from the stored rows/facts is flagged in the API, the PDF and the UI. Old (v1) reports still open and export; they say what they lack | [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) |
| D56 | Two evaluation modes, labelled | **Final** (2026-11-15) | **Oracle** mode replays each case's reference SQL through the real Guard, executor, analysis engine, verification, persistence and API; it measures the pipeline and is always labelled "not model accuracy". **Live** mode uses the configured real provider, is resumable, honours the daily model cap and stops on quota/auth errors; only it may produce model-accuracy claims. The build sandbox had no model access, so no live numbers exist yet. |
| D57 | Ground truth computed independently of SQL | **Final** (2026-11-15) | Expected results come from plain-Python functions over the seeded generator, and every reference query is checked against them on PostgreSQL (`test_eval_dataset.py`). The comparator is value-based (columns and order of columns free, integers exact, other numbers within 0.01 or 0.01 %, percent versus fraction not forgiven) and is itself unit-tested. |
| D58 | Sensitive result values never reach the model | **Final** (2026-11-15) | Result columns marked `is_sensitive` are replaced by `«redacted»` in all five model-bound payloads, and the payload names the hidden columns (SECURITY.md, which already required it; the implementation had a gap found by eval case X02). Matching is by result column name, so an aliased column escapes (documented limit). Stored results shown to the owner are unchanged; masking them in the UI is left to the owner. |
| D59 | Executor pins the session time zone to UTC | **Final** (2026-11-15) | `SET LOCAL TIME ZONE 'UTC'` in every read-only transaction, so month and day boundaries do not depend on server or role defaults. Regression test uses an Asia/Kolkata default. |
| D60 | `CARTESIAN_JOIN` Guard rule implemented | **Final** (2026-11-15) | A join of two real tables with no condition (no `ON`/`USING`, `ON TRUE`, no column-equals-column in `WHERE`) is rejected as a recoverable Guard error. A `CROSS JOIN` against a subquery or CTE stays allowed (share-of-total pattern). Reason: measured, the EXPLAIN cost gate alone let two-table cross joins run. |
| D61 | Browser tests use the real stack with the oracle model | **Final** (2026-11-15) | Playwright runs the real Next.js app against the real FastAPI + PostgreSQL, with the model replaced by the oracle (`evals/e2e_server.py`, test databases, backend on 8100). The existing frontend on 3001 is reused (`reuseExistingServer`); because `NEXT_PUBLIC_*` values are fixed when `next dev` starts, `e2e/fixtures.ts` reroutes the browser's calls from the app's API URL (8000) to the test backend instead. No API key, repeatable. Chrome is selected with `PLAYWRIGHT_CHROME_PATH` or `playwright install chromium`. The Save-as-report test was verified to fail when the earlier GET/POST bug is reintroduced. |
| — | Structured outputs, no code execution | Accepted | See ADR-0005 below | ADR-0005 |

## Status notes (as of the pre-Phase 10 cleanup)

Some recorded decisions were later changed or never built. The table above is the historical record; these are the current facts.

- **D7 / ADR-0003 (SSE streaming):** not implemented. The UI polls `GET /analysis-sessions/{id}`.
- **D6 / ADR-0004 (in-process runs):** as built; implies a single API instance.
- **D11 (pinned dashboard widgets) and D10 (print-CSS PDF):** not built. The dashboard lists your datasets, recent analyses and reports; reports export a server-rendered PDF and Markdown (D55).
- **D25 (demo data policy) and D40 (sample Dashboard and Analyst):** superseded. All sample/mock UI data was removed; every page reads the real API.
- **D27 (`AUTH_MODE=demo`):** still exists for local experiments, refused in production.
- **D28 (CSV only):** still true; XLSX is not supported.
- **D19 (retention), D20 (usage limits), D2 (external Postgres), D22 (team split):** not implemented or still pending. Rate limits exist per process (login, registration, uploads, analyses per hour).
- **D1 / ADR-0006:** `mock` provider means "no model" (D42), not canned replies.
- **ADR-0001 and ADR-0002:** the `lg` schema mentioned there was never created (no LangGraph checkpointer, D46).

## Change history
| Date | Change |
|---|---|
| 2026-11-11 | Blueprint v0.1 published with open decisions D1–D22 |
| 2026-11-12 | Phase 2 (frontend UI/UX with demo data) implemented; palette D23, phase order D24 and demo-data policy D25 recorded |
| 2026-11-12 | Owner has no Docker: local setup switched to native PostgreSQL via `infra/postgres/setup-local.sh`; Docker Compose kept as optional. Role bootstrap now re-syncs passwords on every run |
| 2026-11-12 | D1, D5, D8 finalised by the owner. ADR-0001…0007 written. Phase 1 approved and implemented. Application tables (`users`, `user_settings`, `refresh_tokens`, `audit_log`) moved from Phase 1 to Phase 2 (they belong with authentication); Phase 1 delivers the `app` schema, roles and migration baseline |
| 2026-11-13 | Phase 3 (database & data ingestion) implemented; decisions D26–D33 recorded; migration 0003 added after the cascade test exposed an immediate-RESTRICT problem |
| 2026-11-14 | Phase 4 (backend API, authentication, frontend wiring) implemented; D34–D41 recorded; migration 0004 adds refresh_tokens and audit_log |
| 2026-11-14 | D50: Google Gemini free tier chosen for development (provider `google`, `GOOGLE_API_KEY`), with free-tier protections |
| 2026-11-15 | Phase 6 (SQL safety hardening) implemented; D51 recorded; SQL safety documentation written |
| 2026-11-15 | Phase 7 (result analysis, insights, visualizations, frontend integration) implemented; D52 recorded; analyst workspace now live against the API; multi-dataset pipeline test added |
| 2026-11-15 | Phase 8 (conversation memory, query history, PDF reports) implemented; D53–D55 recorded; roadmap phases 8–15 renumbered 9–16 (the old Phase 8, SSE streaming, is now Phase 9); migration 0006 adds `analysis_sessions.memory` |
| 2026-11-15 | Phase 9 (testing and evaluation) implemented; D56–D61 recorded; roadmap phases 9–16 renumbered 10–17 (the old Phase 9, SSE streaming, is now Phase 10); evaluation findings F1–F6 in docs/eval/FAILURE_ANALYSIS.md |
| 2026-11-14 | Phase 5 (agentic AI core, LangGraph) implemented; D42–D49 recorded; ADR-0006 amended (mock = no model); roadmap phases 5–7 merged into Phase 5, remaining work moved to new Phases 6–7; migration 0005 adds agent_node_runs |

## Architecture decision records

### ADR-0001 — Monorepo layout and tooling

| Status | Accepted (2026-11-12) — resolves Open Decision **D13** |
|---|---|

#### Decision
- One repository with independent apps: `apps/web` (Next.js) and `apps/api` (FastAPI). They share no code at runtime. The only contract between them is the HTTP API (OpenAPI at `/api/v1/openapi.json`; generated TypeScript types from Phase 8).
- **Python:** `uv` (lockfile `apps/api/uv.lock`, virtualenv `apps/api/.venv`), Python ≥ 3.12 (developed on 3.13). Quality: `ruff` (lint, including `S` security rules, and format) and `mypy --strict`.
- **Web:** `pnpm` (lockfile `apps/web/pnpm-lock.yaml`), Node ≥ 20.9. Quality: ESLint (`eslint-config-next` + `eslint-config-prettier`), Prettier (+ Tailwind class sorting), `tsc --noEmit` after `next typegen`, Vitest.
- Root `Makefile` for common commands. CI workflows per app (`.github/workflows/ci-api.yml`, `ci-web.yml`) plus a gitleaks secrets scan.

#### Versions resolved at Phase 1 (from the lockfiles)
Next.js 16.4.6, React 19.3.0, Tailwind CSS 4.3.3, TypeScript 5.9.3, Vitest 5.1 · FastAPI 0.162.5, Starlette 1.10, Pydantic 2.14.3, pydantic-settings 2.16.2, SQLAlchemy 2.1.8, asyncpg 0.32.0, Alembic 1.20.1, structlog 26.1, ruff 0.17.4, mypy 2.4.1, pytest 9.2.

#### Notes
- Next.js 16 has changed conventions (Cache Components, `LayoutProps` globals, `next typegen`). Its bundled docs in `node_modules/next/dist/docs/` are the reference, per `apps/web/AGENTS.md`.
- The Starlette test client now uses `httpx2`. `httpx2` is the backend's test HTTP dependency.

### ADR-0002 — Database topology and permission model

| Status | Accepted (2026-11-12) — resolves Open Decision **D5** |
|---|---|
| Implemented in | Phase 1 (base roles, `app` schema, hardening) · Phase 3 (per-dataset schemas/roles) · Phase 4 (executor sessions) |

#### Context
Sageboard runs SQL written by an LLM against user data. Whatever the SQL says, it must not be able to write data, read application metadata (users, sessions, traces), or read another user's dataset. Prompts can be wrong and validators can have bugs, so PostgreSQL's own privilege system has to be a real security boundary, not an afterthought.

#### Decision

#### Hosting
- **Production:** Neon PostgreSQL 16. Neon supports creating roles and granting privileges through SQL. Roles created that way do **not** get `neon_superuser` membership; they start with only the basic privileges of a new role in standalone Postgres. That's what we want for restricted roles. The project owner role (a `neon_superuser` member, holding `CREATEROLE`) runs the bootstrap script.
- **Local development:** native PostgreSQL 16 (Homebrew or Postgres.app), prepared by `infra/postgres/setup-local.sh`. **Docker is optional** (`infra/docker-compose.yml`). **CI:** a PostgreSQL 16 service container in GitHub Actions.

#### One database, separated by schema and role
| Schema | Owner | Holds |
|---|---|---|
| `app` | `sageboard_owner` | Application metadata (users, datasets, runs, traces, reports…), managed by Alembic |
| `lg` | `sageboard_owner` | LangGraph checkpoints (Phase 5) |
| `ds_<32-hex>` | `sageboard_ingest` | One schema per uploaded dataset (Phase 3) |
| `public` | — | Unused; `ALL` is revoked from `PUBLIC` |

#### Roles
| Role | Login | Used by | Can | Cannot |
|---|---|---|---|---|
| `sageboard_owner` | yes | Alembic migrations, bootstrap | Own and alter `app`/`lg` objects | Superuser, create databases |
| `sageboard_app` | yes | FastAPI runtime (SQLAlchemy pool) | `SELECT/INSERT/UPDATE/DELETE` on `app` tables (default privileges) | DDL anywhere; any access to `ds_*`; create schemas/temp tables |
| `sageboard_ingest` | yes | Ingestion code path only (Phase 3) | Create `ds_*` schemas, load data, create per-dataset reader roles (`CREATEROLE`) | Access `app` |
| `sageboard_executor` | yes, `NOINHERIT` | Query Executor pool only (Phase 4) | `SET ROLE` into a `ds_<id>_r` it has been granted | Anything on its own: it has no direct privileges; sessions default to read-only with a 10 s statement timeout |
| `ds_<id>_r` | no | Assumed by the executor per query | `USAGE` on one `ds_<id>` schema + `SELECT` on its tables | Everything else |

Because `sageboard_executor` is `NOINHERIT`, being a member of every dataset reader role gives it nothing until it explicitly does `SET ROLE ds_<id>_r`. It can never `SET ROLE` to the app, owner or ingest roles because it isn't a member of them. (This is verified by `tests/test_db_permissions.py`.)

#### Session safety for analytical SQL (Phase 4)
Every analytical query runs in one transaction on an executor connection:
```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL ROLE ds_<id>_r;            -- identifier from the datasets row, regex-checked, quoted
SET LOCAL search_path = ds_<id>;
SET LOCAL statement_timeout = '10s';
EXPLAIN (FORMAT JSON) <validated sql>;  -- cost gate
<validated sql>;                         -- fetch up to row_limit + 1
ROLLBACK;
```
Only `SET LOCAL` is used. It's scoped to the transaction, so a pooled connection can never carry a dataset role or `search_path` over to the next query.

#### Connection pooling
- **Application pool:** SQLAlchemy async pool (asyncpg) as `sageboard_app`. On Neon it may use the **pooled** endpoint (`-pooler` host). Neon's PgBouncer runs in transaction mode, which drops session-level `SET`. We don't depend on session state, and asyncpg's statement cache is disabled (`statement_cache_size=0`) for compatibility.
- **Executor pool:** a separate asyncpg pool as `sageboard_executor` (Phase 4). The transaction-scoped `SET LOCAL` design above works through a transaction-mode pooler. We'll still default the executor to the **direct** endpoint so `pg_cancel_backend` can target the right backend when a run is cancelled. This gets re-checked in the Phase 4 spike.
- **Migrations and LangGraph checkpointer:** the **direct** (non-pooled) endpoint, because migrations and checkpoint setup rely on session behaviour the pooler doesn't keep.

#### Hardening applied in Phase 1 (`infra/postgres/init/001_roles.sh`)
- `REVOKE ALL ON DATABASE … FROM PUBLIC`, then `CONNECT` granted only to Sageboard roles. `CREATE` on the database is granted only to owner and ingest. `TEMP` is not granted to anyone.
- `REVOKE ALL ON SCHEMA public FROM PUBLIC`.
- No role has `SUPERUSER`, `CREATEDB`, `REPLICATION` or `BYPASSRLS`.
- Per-role defaults: app `statement_timeout=30s`; executor `statement_timeout=10s`, `default_transaction_read_only=on`, `idle_in_transaction_session_timeout=15s`.
- Passwords come from environment variables. The script contains none.

#### Verified in Phase 1 (real PostgreSQL 16, see the phase report)
- The app role can read `app.alembic_version` (default privileges work) but can't create tables in `app` or `public`, create schemas, or drop the migration table.
- Executor sessions are read-only by default (a temp table fails with `ReadOnlySQLTransactionError`), can't read `app.*`, and can't `SET ROLE` to `sageboard_app`, `sageboard_owner`, `sageboard_ingest` or `postgres`.

#### Open items to verify on Neon before Phase 3
1. Whether Neon requires a password for `NOLOGIN` roles created through SQL (its docs say SQL-created roles need a password). If it does, the per-dataset reader roles get a random password that's never stored.
2. That a `neon_superuser` member can grant SQL-created roles to `sageboard_executor` and that `sageboard_ingest` (with `CREATEROLE`) can administer the reader roles it creates (PostgreSQL 16 `ADMIN OPTION` semantics).
3. Plan limits on roles/schemas per project.

If (2) fails, the fallback is a single `sageboard_reader` role with `SELECT` on all `ds_*` schemas. The SQL Guard's schema allowlist then becomes the only cross-tenant control above the database, and this reduced-assurance mode is flagged in SECURITY.md

#### Consequences
- Strong isolation: even a validator bypass yields at most a read-only `SELECT` on the user's own dataset.
- Role management is extra operational work (the bootstrap script; per-dataset role lifecycle in Phase 3).
- Two kinds of connection strings per environment (pooled for the app, direct for migrations and the executor), documented in `apps/api/.env.example`.

### ADR-0003 — Server-Sent Events for run streaming

| Status | Accepted (2026-11-12, as default) — resolves Open Decision **D7** |
|---|---|
| Implemented in | Phase 7 |

#### Decision
Agent run progress is streamed with SSE (`GET /api/v1/runs/{id}/events`). Every event is persisted to `app.run_events` *before* it's published, so reconnecting with `Last-Event-ID` replays without loss. If SSE stalls behind a proxy, there's a polling fallback (`GET /runs/{id}` every 2 s).

#### Why not WebSockets
The stream only goes one way (server → client). SSE uses plain HTTP, gets automatic reconnects from `EventSource`, and works with cookie auth and CORS without a custom protocol. User actions (cancel, resume) are ordinary REST calls.

#### Phase 1 groundwork
The request-context middleware is pure ASGI rather than `BaseHTTPMiddleware`, so it doesn't buffer streaming responses.

### ADR-0004 — In-process run execution with a persisted event log

| Status | Accepted (2026-11-12, as default) — resolves Open Decision **D6** |
|---|---|
| Implemented in | Phase 7 |

#### Decision
Agent runs execute as asyncio tasks inside the API process, managed by a Run Manager. Limits: 2 concurrent runs per user and a per-instance semaphore. State survives in two places: the LangGraph Postgres checkpointer (`lg` schema) and `app.run_events`. One API instance is deployed.

#### Consequences
- Simple deployment: no Redis or worker process.
- A restart interrupts in-flight runs. On startup, runs still marked `running` are set to `failed` with reason `interrupted`, and the UI offers a re-run.
- Upgrade path, if needed later: move graph execution to an `arq` worker (Redis) without changing the API contract, since clients only see the event stream.

### ADR-0005 — Structured outputs only; no execution of generated code

| Status | Accepted (2026-11-12) |
|---|---|
| Implemented in | Phases 4–6 (enforced by lint rules from Phase 1) |

#### Decision
- Every LLM call returns JSON validated against a Pydantic schema. Free text is never parsed for control flow.
- LLM output is never executed as code. SQL goes through the SQL Guard and the restricted executor (ADR-0002). Analysis uses a fixed set of typed Python functions the model can only *select*. Charts are declarative `ChartSpec` objects rendered by the frontend.
- From Phase 1, ruff's `S` (bandit) rules run in CI. They flag `eval`/`exec`, `subprocess` with a shell, unsafe deserialisation, hardcoded secrets and similar.

#### Consequences
Model mistakes show up as validation failures that can be retried, never as arbitrary execution. Analyses are limited to the toolset we implement. That's a deliberate trade-off.

### ADR-0006 — Provider-agnostic LLM layer with a mock provider

| Status | Accepted (2026-11-12) — resolves Open Decision **D1** |
|---|---|
| Implemented in | Phase 1 (configuration and validation only) · Phase 5 (adapters for Anthropic, OpenAI, Gemini; mock = no model, see Amendment 2) |

#### Context
The team hasn't confirmed which LLM API credits are available. The agent workflow must not depend on any one vendor, and the early phases must not be blocked by this.

#### Decision
1. **One interface, many providers.** The agent nodes depend only on an `LLMClient` protocol in `app/agent/llm/client.py`:
   - `structured(messages, schema: type[BaseModel], *, purpose) -> BaseModel`
   - `with_tools(messages, tools, *, max_calls) -> ToolLoopResult`

   Provider modules (`anthropic.py`, `openai.py`, `gemini.py`, `mock.py`) implement it. The LangGraph graph, nodes and prompts never import a provider SDK.
2. **Configured by environment only.** `LLM_PROVIDER` (`mock | anthropic | openai | gemini`), `LLM_MODEL`, and one API key per provider. Settings validation (already implemented in Phase 1) refuses:
   - a real provider without its key or a model name
   - `LLM_PROVIDER=mock` when `ENV=production`

   No key or model name appears in code.
3. **Mock provider for development and automated tests.** It returns deterministic, schema-valid outputs from scripted fixtures (keyed by node purpose) so the graph, SQL Guard, executor and UI can be built and tested without credentials. Rules that keep it honest (project instruction #8):
   - Only the *model's* outputs are simulated. SQL validation, execution against the real database, statistics and verification all run for real.
   - Every run produced with the mock is labelled (`llm_calls.provider = "mock"`, a visible "Mock model" badge in the Run Inspector). It must never be presented as real model output in a demo or evaluation.
   - Accuracy metrics (the eval suite) are only reported from real-provider runs.
4. **Provider evaluation gate (start of Phase 5).** Before integrating a real provider, we record in `docs/LLM_PROVIDER_EVALUATION.md`: available API access and credits, pricing per 1M input/output tokens, tool-calling support, native structured output (JSON Schema) support and its limits, rate limits, context window, and data-retention terms. Default model selection is decided from that table and approved by you.
5. **Per-purpose model selection (optional).** `LLM_MODEL` is the default. Optional overrides (`LLM_MODEL_SQL`, `LLM_MODEL_JUDGE`) let a cheaper model handle classification or verification. These are added in Phase 5 only if the evaluation supports it.

#### Consequences
- Switching providers is a configuration change plus that provider's own conformance tests. There are no workflow changes.
- Each provider's structured-output differences (JSON Schema subset, tool-call formats) are absorbed by its adapter. A shared conformance test suite runs against every adapter.
- The mock adds a module we have to maintain. It's kept deliberately small and covered by the "never in production" validator test (`tests/test_config.py::test_mock_llm_is_refused_in_production`).

#### Amends
- DEVELOPMENT.md previously placed the fake LLM only under `tests/`. Per your decision, the mock becomes a first-class provider usable in **development** too. It stays forbidden in production by settings validation.

#### Amendment 2 (2026-11-14, Phase 5) — D42
- In the running application, `LLM_PROVIDER=mock` now builds **no model**. Analysis sessions stay `queued`, and the API says why (`agent_available: false`). A development mock that answered arbitrary questions would be a fabricated AI response, which the project rules forbid.
- Scripted model replies live only in `tests/agent/fakes.py` (`ScriptedProvider`). They stand in for the model alone. The graph, structured-output validation and re-asks, SQL Guard, routing, analysis engine and grounding all run for real, and integration tests use the real database. Runs persist the provider name (`scripted` in tests), so a scripted run can never pass as a real one.
- The adapters call each provider's HTTP API directly (no SDKs). Anthropic uses one forced tool whose `input_schema` is the JSON Schema; OpenAI and Gemini (through its OpenAI-compatible endpoint) use `response_format: json_schema` with `strict: false`, because Pydantic defaults aren't strict-mode compatible. Every reply is validated with one corrective re-ask.
- The provider evaluation (§4) moves to Phase 6, where a real key is available. Accuracy is reported only from real-provider runs.

#### Amendment 3 (2026-11-14) — D50: free Gemini tier for development
- Provider name `google` (`gemini` still accepted). Key: `GOOGLE_API_KEY` (`GEMINI_API_KEY` accepted). The owner's model choice is `gemini-3.8-flash`, subject to it having free-tier quota on her key; `scripts/check_llm.py` verifies that with one request.
- Google's 429s are classified from the error body (`QuotaFailure.quotaId`, `RetryInfo.retryDelay`):
  - per-minute → wait and retry (bounded);
  - per-day or `limit: 0` → `LLM_QUOTA_EXCEEDED` / `LLM_MODEL_NOT_FREE`, never retried.

  Fatal model errors (`FATAL_LLM_CODES`) end the run as `llm_unavailable` with the reason, instead of being absorbed by node fallbacks.
- Free-tier protection:
  - one per-process request pacer;
  - a daily model-call cap counted from `agent_node_runs`;
  - no automatic provider, model or tier fallback;
  - readiness probes never call the model.
- Schema compatibility: for Google, cosmetic JSON Schema keywords (`title`, `default`, `description`, `examples`) are dropped. If the endpoint still rejects the schema (400), the adapter switches once to `json_object` mode with the schema in the system prompt. Pydantic validation and the corrective re-ask are unchanged.

### ADR-0007 — Schema retrieval before analysis planning

| Status | Accepted (2026-11-12) — resolves Open Decision **D8** |
|---|---|
| Implemented in | Phase 5 |

#### Context
The original requirement listed analytical planning before schema retrieval. A plan written without knowing the real columns tends to reference fields that don't exist, which wastes repair attempts and invites hallucinated analysis.

#### Decision
Node order: `load_context → understand_query → retrieve_schema → plan_analysis → …`

- `understand_query` receives only a **lightweight table catalog**: table names, one-line descriptions and row counts. That's enough to tell answerable from out-of-scope or ambiguous questions.
- `retrieve_schema` collects the **detailed schema** for the relevant tables: columns, data types, profiles, descriptions, sample values for low-cardinality columns, and join paths. It uses a bounded tool loop (≤ 6 tool calls).
- `plan_analysis` **must** receive `schema_context`. Enforced in code:
  1. The graph edge `retrieve_schema → plan_analysis` is fixed. No route reaches `plan_analysis` any other way (asserted by `test_graph_structure`).
  2. `plan_analysis` raises if `schema_context` is missing or empty.
  3. Each `PlanStep` may name the tables/columns it intends to use. These are checked against `schema_context`, and an unknown reference triggers one re-ask before the plan is accepted.

#### Consequences
Plans are grounded in the actual schema from the start. Retrieving the schema costs one more LLM interaction for questions that turn out to be out of scope. To avoid that, out-of-scope questions are caught by `understand_query` first.
