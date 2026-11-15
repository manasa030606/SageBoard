# Sageboard — Development Roadmap

| Field | Value |
|---|---|
| Document | DEVELOPMENT_ROADMAP v0.6 |
| Status | Approved 2026-11-12 (v0.2). **No phase starts without explicit approval.** Phases 1–5 done (Phase 3 re-sequenced on 2026-11-13; Phase 4 = backend API + authentication on 2026-11-14; Phase 5 = the full agentic core on 2026-11-14, merging former Phases 5–7, D43; Phase 6 = SQL safety hardening on 2026-11-15, D51 — real-model evaluation moves to Phase 7) |
| Rule | Each phase follows the 10-step process in the project instructions (inspect → explain → list files → implement → test → fix → explain → limitations → run commands → commit message). |

---

## 1. Implementation order (why this sequence)

1. **Foundations first** (repo, config, DB, auth). Everything depends on them.
2. **Data layer before the agent.** The agent needs real schemas and real data to reason over. Per the project rules, no mock data stands in for the real thing.
3. **Safety core before any LLM code.** SQL Guard + Executor are built and attacked first, so the agent is born inside a safe box.
4. **Agent in two halves.** First query → SQL → results (correctness), then analysis → insights → verification (grounding).
5. **Streaming API, then frontend.** The UI is built against real events, not a mocked stream.
6. **Hardening, deployment, demo prep** last, but with tests written alongside every phase.

## 2. Phase plan

| Phase | Name | Key deliverables | Depends on | Exit criteria |
|---|---|---|---|---|
| **1** | Monorepo & platform foundation | Monorepo skeleton (§SYSTEM_ARCH 6); `docker-compose` Postgres 16; FastAPI app with settings, structlog, error envelope, `/healthz` `/readyz`; SQLAlchemy async session; base DB roles + hardening script (ADR-0002); Alembic baseline (`app` schema only; app tables move to Phase 2); Next.js app scaffold with Tailwind + design tokens file (colour/typography/spacing only); Makefile; CI for lint/typecheck/unit; pre-commit with gitleaks; ADR-0001..0007 + decision log; web↔API system-status page | — | **Done 2026-11-12** — web + API start; `/readyz` 200 with DB; browser calls API across origins; lint/type/tests green (see phase report) |
| **2** | Frontend UI/UX (demo data) — *re-sequenced by the owner on 2026-11-12* | All 7 pages (landing, dashboard, analyst workspace, data sources, history, reports, settings) with the final design system, Recharts visualisations, empty/loading/error/success states, responsive layouts and keyboard support. Demo data lives in `src/mocks` behind one data-access layer (`src/lib/data`) and is labelled "Demo data" / "Sample run" in the UI. No backend changes. | 1 | **Done 2026-11-12**. Every page inspected at 1440 px and 390 px; lint/type/test/build green (docs/phases/PHASE_2_REPORT.md) |
| **3** | Database & data ingestion — *re-sequenced by the owner on 2026-11-13* | PostgreSQL + SQLAlchemy models for users, database connections, datasets (+ tables, columns, relationships, ingestion jobs), conversations, messages, analysis sessions, query executions, reports; migrations 0002–0003; PK/FK/CHECK/indexes; separate app / ingest / executor / owner connections; synthetic e-commerce dataset (customers, products, orders, order_items, payments) + idempotent seed; CSV upload → validation → review → load; schema inspection + catalog (types, PKs, FKs, relationships, privacy-controlled samples); dataset preview through the read-only executor. **Demo identity** instead of auth (D27). No agents | 1 | **Done 2026-11-13** — 201 backend tests green incl. 53 PostgreSQL integration tests (docs/phases/PHASE_3_REPORT.md) |
| **4** | Backend API & authentication — *defined by the owner on 2026-11-14* | Separate routers + services for auth, datasets, uploads, metadata, schema, connections, conversations, analysis sessions (stored, not executed), history, reports (+ Markdown export), health/readiness (incl. migration head); register/login/logout/refresh/me with argon2id, JWT + rotating refresh, CSRF, rate limits, audit log (migration 0004); user-level ownership on every route; per-user sample dataset; DB-failure → 503 without leaks; Next.js sign-in/sign-up, session guard, live Data sources / History / Reports. No agents | 3 | **Done 2026-11-14** — 283 backend tests (91 against PostgreSQL) + 66 web tests + 10-step browser journey (docs/phases/PHASE_4_REPORT.md) |
| **5** | Agentic AI core (LangGraph) — *defined by the owner on 2026-11-14 (D43)* | Typed `AgentState`; 15-node `StateGraph` (the 12 requested agents/tools + 3 control nodes) with explicit and conditional edges, bounded retries, node status/duration tracing, contained failures, conversation context; SQL Guard (SQLGlot) with adversarial + benign corpora; read-only execution tool; Error Recovery agent; deterministic analysis engine; chart validation; grounding verification + reject-only judge; final response; provider-agnostic LLM layer (Anthropic/OpenAI/Gemini over HTTP, mock = no model); Run Manager + `agent_node_runs` (migration 0005); trace API; `scripts/ask.py` | 4 | **Done 2026-11-14** — 476 backend tests (187 agent unit/graph tests with scripted model + fake tools; 6 agent tests on PostgreSQL) (docs/phases/PHASE_5_REPORT.md) |
| **6** | SQL safety, execution & self-correction — *defined by the owner on 2026-11-15 (D51)* | Validation pipeline verified against the spec (docs/SQL_SAFETY.md); unsafe queries and permission errors made non-retryable; recursive-CTE/join/depth caps (SECURITY_DESIGN §4.2/4.6); EXPLAIN cost gate; in-flight query cancellation (asyncpg cancel → `pg_cancel_backend` mechanism); Hypothesis property-based fuzzing; Guard-bypass isolation tests on real PostgreSQL; consolidated security & recovery doc | 5 | **Done 2026-11-15** — 518 backend tests (docs/phases/PHASE_6_REPORT.md) |
| **7** | Real-model evaluation | Provider evaluation (`docs/LLM_PROVIDER_EVALUATION.md`, ADR-0006 §4) with your API key; evaluation set of sample-dataset questions (incl. a recovery and a refusal case); execution accuracy and grounding-violation rate reported honestly; prompt tuning from failures | 6 | Eval report committed; regressions tracked |
| **8** | Run streaming | SSE stream of node events with replay (Run Manager, cancel and node-event persistence already built in Phase 5); usage counters | 5 | SSE integration tests incl. reconnect; cancel/resume tests |
| **9** | Design system & app shell + landing | Tokens finalised with contrast checks; primitives (Button, Input, Table, Tabs, Drawer, Dialog, Badge, Skeleton, EmptyState, ErrorState, Toast); app shell (sidebar, dataset switcher, ⌘K); landing page; typed API client generation | 3 (can start in parallel after 8 for API types) | Storybook-free component gallery route `/app/_gallery` (dev only); a11y checks pass; landing reviewed against UI rules |
| **10** | Data sources UI | Upload flow with review step, dataset list/detail, profiles, column description editing, delete; all states | 4, 9 | Playwright `dataset-upload` passes |
| **11** | Analyst workspace UI | Conversation list, composer with dataset selector, streaming run card, Run Inspector, result tables (sort/paginate/CSV), ChartRenderer, evidence popovers, clarification UI, cancel, error/partial states | 8, 9, 10 | Playwright analyst specs pass; reducer unit tests |
| **12** | Reports, dashboard, history, settings | Reports CRUD + Markdown export + print CSS; dashboard widgets (pin, layout, refresh); history table + drawer; settings + usage + account deletion | 11 | Remaining Playwright specs pass |
| **13** | Hardening | Full E2E + visual regression + a11y + responsive; performance pass (query timing, bundle size); retention job; security acceptance criteria (§SECURITY 12) | 12 | All CI gates green; security checklist signed off |
| **14** | Deployment | Dockerfile; Render/Railway service; managed Postgres with role bootstrap runbook; Vercel project; env/secrets; cookie/CORS for prod domains; smoke tests against prod; nightly eval | 13 | Public URL works end-to-end; runbook in `docs/DEPLOYMENT.md` |
| **15** | Documentation & demo prep | README, architecture diagrams, ADRs complete, eval report, demo script with sample questions (incl. a recovery and a refusal case), known limitations | 14 | Rehearsed demo |

Optional post-MVP phases: external Postgres connectors (D2), team workspaces (D4), job queue (D6), multi-dataset conversations.

## 3. Critical path and parallelism

> Phase numbers above were shifted by one on 2026-11-12 when the frontend UI moved to Phase 2. The UI phases later in the plan (design system, data sources UI, workspace UI, reports/dashboard/history/settings) now mean *wiring the existing UI to the real API*, not designing it.
```
1 → 2 (UI, done) → 3 → 4 → 5 → 6 → 7 → 8 → 11 → 12 → 13 → 14 → 15
                         └──── 9 (wire design system) ─┘ 10 ┘
```
Phase 8 can start any time after Phase 2 if you want frontend work in parallel (useful for a 5-person team). The highest-risk items are on the critical path: the Guard (4) and grounding (6).

## 4. Key dependencies (packages)

| Area | Packages (pin in lockfiles) |
|---|---|
| API | `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `sqlalchemy[asyncio]>=2`, `asyncpg`, `alembic`, `argon2-cffi`, `pyjwt`, `structlog`, `sse-starlette`, `python-multipart`, `openpyxl`, `slowapi` (rate limiting) |
| Agent | `langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary,pool]` (required by the checkpointer), `sqlglot`, provider SDK (`anthropic` or `openai`), `tenacity` |
| Analysis | stdlib `statistics` + `decimal`. **No pandas in MVP** (smaller surface, deterministic; reconsider if needed) |
| Testing | `pytest`, `pytest-asyncio`, `pytest-cov`, `hypothesis`, `httpx`, `testcontainers[postgres]` (or compose service), `respx` |
| Web | `next`, `react`, `typescript`, `tailwindcss`, `recharts`, `@tanstack/react-query`, `@radix-ui/react-*` (behaviour only), `openapi-typescript`, `zod` (form validation), `react-markdown` + `rehype-sanitize`, `@playwright/test`, `@axe-core/playwright`, `vitest`, `@testing-library/react` |
| Tooling | `uv`, `pnpm`, `ruff`, `mypy`, `eslint`, `prettier`, `pre-commit`, `gitleaks`, `pip-audit` |

Version note: exact versions get pinned in Phase 1 after checking the current releases (LangGraph and SQLGlot APIs change between minor versions; we'll pin and record them in ADR-0005).

## 5. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Managed Postgres disallows `CREATE ROLE` | Weakens tenant isolation | Pick Neon/Railway (allow it) or use documented fallback mode (D5) |
| Free-tier backend sleeps / restarts kill in-process runs | Runs lost mid-way | Persisted events + checkpoints; on startup mark orphaned `running` runs as `failed: interrupted`; paid tier for the demo (D6) |
| LLM accuracy below target | Weak evaluation | Schema descriptions, join-path hints, few-shot from sample data, repair loop; report the real number regardless |
| LLM cost overrun | Budget | Per-run/per-day caps; small model for understanding/verification judge, larger for SQL (configurable per node) |
| Scope creep (7 pages + agent) | Missed deadline | Strict phase gates; reports/dashboard kept simple (snapshot + pin) |
| SSE through proxies/CDN buffering | Stream stalls | `X-Accel-Buffering: no`, heartbeat, polling fallback (`GET /runs/{id}` every 2 s) |

## 6. Open decisions

> **Status (2026-11-12):** D1, D5 and D8 are **final**. The rest are accepted defaults. The authoritative, up-to-date list is **[DECISION_LOG.md](DECISION_LOG.md)**; the table below is the original proposal, kept for reference.

| ID | Decision | Options | **Recommended default** | Why |
|---|---|---|---|---|
| D1 | LLM provider & model | Anthropic Claude / OpenAI / Google Gemini / local | **Provider-agnostic adapter; one provider configured via env. Which provider do you have API credits for?** | The adapter keeps us portable; your credits decide the default |
| D2 | MVP data sources | Uploads only / + external Postgres | **CSV/XLSX upload + bundled sample dataset; external Postgres post-MVP** | External DBs bring SSRF and credential-storage work |
| D3 | Auth approach | Custom FastAPI JWT / Auth.js / Clerk | **Custom FastAPI auth (argon2id, JWT + rotating refresh, httpOnly cookies)** | No third-party dependency; good learning value; full control |
| D4 | Tenancy | Single-user / teams | **Single-user workspaces** | Enough for evaluation; isolation still enforced |
| D5 | DB topology | 1 DB w/ schemas / separate app & warehouse DBs | **One Postgres, `app` + `ds_*` schemas, role-per-dataset; provider that supports CREATE ROLE (Neon or Railway)** | Cheapest with strong isolation |
| D6 | Run execution | In-process asyncio / Redis + arq worker | **In-process asyncio with persisted events + checkpoints; 1 API instance** | Simpler deploy; upgrade path documented |
| D7 | Streaming transport | SSE / WebSocket / polling | **SSE + polling fallback** | One-way stream fits; simpler through proxies |
| D8 | Step order | Plan → schema (as requested) / schema → plan | **Schema retrieval before planning** (understanding gets the table catalog) | Avoids plans over non-existent columns (AGENT_WORKFLOW §2) |
| D9 | Ambiguity handling | Always ask / assume & state / hybrid | **Hybrid: ask when the ambiguity blocks a correct answer; otherwise assume and state it. User setting can force either** | Fewer interruptions, still transparent |
| D10 | Report export | Markdown / PDF (server) / print CSS | **In-app report + Markdown export + print-optimised CSS for PDF** | No headless-browser dependency on the server |
| D11 | Dashboard semantics | Pinned snapshots / live re-execution / LLM refresh | **Pinned widgets re-execute stored, re-validated SQL; no LLM** | Deterministic, cheap, safe |
| D12 | What the LLM sees | Full data / capped previews + facts | **Schema + profiles + ≤50-row previews + computed facts; sensitive columns masked** | Privacy, cost, grounding |
| D13 | Package managers | npm / pnpm; pip / poetry / uv | **pnpm + uv** | Fast, lockfile-first |
| D14 | Typography | Plex / Inter / custom | **IBM Plex Sans + IBM Plex Mono; Source Serif 4 for landing/report headings** | Distinctive, open-licence, good tabular figures |
| D15 | Upload limits | — | **25 MB, 1M rows, 200 columns, 10 sheets** | Fits free-tier DB sizes |
| D16 | Follow-up questions | Stateless / previous run context | **Include summaries (question, plan, final SQL, columns) of the last 3 runs in the conversation** | Natural follow-ups ("now split by month") without huge prompts |
| D17 | Tracing | DB only / + LangSmith | **DB trace always; LangSmith optional via env, off by default** | No third-party data flow by default |
| D18 | Business glossary | None / column descriptions / metrics layer | **Table & column descriptions + semantic role in MVP; named metric definitions post-MVP** | Big accuracy gain for small effort |
| D19 | Data retention | — | **Query results 30 days unless referenced by report/widget; runs/SQL metadata kept until deletion** | Bounded storage |
| D20 | Usage limits | — | **100 runs/day/user, 2 concurrent, token cap configurable (default 500k/day)** | Cost safety for a public demo |
| D21 | Frontend component base | Fully custom / Radix primitives / shadcn | **Radix primitives for behaviour (a11y) + fully custom styling** | Avoids the generic look while keeping accessibility |
| D22 | Team split (5 people) | — | Suggested: (1) backend platform+auth, (2) ingestion+DB, (3) Guard+executor+tests, (4) agent+eval, (5) frontend+design system. Phases stay sequential for review; parallel work happens inside a phase | You confirm actual ownership |

## 7. Definition of Done (applies to every phase)
- Code passes lint, typecheck and tests in CI. Results come from real runs.
- New behaviour has tests at the appropriate level.
- No secrets in code. `.env.example` is updated.
- Docs/ADRs are updated for any architectural decision.
- The phase report covers what was built, its limitations, run commands and a suggested commit message.
