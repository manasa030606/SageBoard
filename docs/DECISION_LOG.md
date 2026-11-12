# Sageboard — Decision Log

The single list of architectural decisions. Details live in `docs/adr/`. Statuses:
**Final** = explicitly approved by the project owner · **Default** = blueprint recommendation accepted by approving the roadmap · **Pending** = to be decided at the named phase.

| ID | Decision | Status | Outcome | Record |
|---|---|---|---|---|
| D1 | LLM provider & model | **Final** (2026-11-12) | Provider-agnostic `LLMClient` adapter; Anthropic / OpenAI / Gemini / mock selected by `LLM_PROVIDER`. Mock in development and tests, refused in production. Provider evaluation (access, pricing, tool calling, structured outputs) at the start of Phase 5 | [ADR-0006](adr/0006-provider-agnostic-llm-layer.md) |
| D2 | MVP data sources | Default | CSV/XLSX upload + sample dataset; external Postgres post-MVP | PRD §4.2 |
| D3 | Auth approach | Default | Custom FastAPI auth: argon2id, JWT access + rotating refresh, httpOnly cookies | SECURITY_DESIGN §7 |
| D4 | Tenancy | Default | Single-user workspaces | PRD §10 |
| D5 | Database host & permissions | **Final** (2026-11-12) | Neon PostgreSQL 16 in production (subject to the role-management checks in ADR-0002); native PostgreSQL 16 locally (Docker optional). App role, per-dataset read-only roles, NOINHERIT executor, `SET LOCAL ROLE` per transaction | [ADR-0002](adr/0002-database-topology-and-permissions.md) |
| D6 | Run execution | Default | In-process asyncio tasks + persisted events and checkpoints | [ADR-0004](adr/0004-in-process-run-execution.md) |
| D7 | Streaming transport | Default | SSE + polling fallback | [ADR-0003](adr/0003-sse-for-run-streaming.md) |
| D8 | Step order | **Final** (2026-11-12) | `understand_query` (table catalog only) → `retrieve_schema` (full schema) → `plan_analysis` (must receive schema) | [ADR-0007](adr/0007-schema-retrieval-before-planning.md) |
| D9 | Ambiguity handling | Default | Hybrid: ask only when blocking; user setting can force ask/assume | AGENT_WORKFLOW §5.1 |
| D10 | Report export | Default | In-app report + Markdown + print-CSS PDF | PRD §5.6 |
| D11 | Dashboard semantics | Default | Pinned widgets re-execute stored, re-validated SQL; no LLM | PRD §5.2 |
| D12 | What the LLM sees | Default | Schema + profiles + ≤ 50-row previews + facts; sensitive columns masked | SECURITY_DESIGN §6 |
| D13 | Package managers & tooling | Default (implemented) | pnpm + uv; ruff, mypy strict, ESLint, Prettier, Vitest, pytest | [ADR-0001](adr/0001-monorepo-and-tooling.md) |
| D14 | Typography | Default (implemented) | IBM Plex Sans / Mono and Source Serif 4 (display/headings), all self-hosted via Fontsource | PRD §8 |
| D23 | Brand palette | **Final** (2026-11-12, owner) | Navy #192C35 · forest #315B50 · sage #C4DDCB · warm white #F4F2EC · amber #D99A57 · text #202925 · secondary #727B76. For AA contrast, small secondary text uses #66706A (4.6:1); #727B76 is kept for icons, placeholders and large text. Amber is never small text on light surfaces | PRD §8, `apps/web/src/app/globals.css` |
| D24 | Phase order | **Final** (2026-11-12, owner) | Frontend UI with demo data is Phase 2; authentication moves to Phase 3 and later phases shift by one | DEVELOPMENT_ROADMAP §2 |
| D25 | Demo data policy (Phase 2) | **Final** | Mock data only in `src/mocks`, read through `src/lib/data`; every figure is derived from one seeded series; the analyst replays recorded sample runs only for their exact questions and never answers other questions; demo state is labelled in the UI | ADR-0006, PHASE_2_REPORT |
| D15 | Upload limits | Default | 25 MB, 1M rows, 200 columns, 10 sheets | SECURITY_DESIGN §8 |
| D16 | Follow-up questions | Default | Summaries of the last 3 runs in the conversation | AGENT_WORKFLOW §3 |
| D17 | Tracing | Default | DB trace always; LangSmith optional, off | SYSTEM_ARCHITECTURE §4 |
| D18 | Business glossary | Default | Table/column descriptions + semantic role | DATABASE_DESIGN §3.2 |
| D19 | Data retention | Default | Query results 30 days unless referenced | DATABASE_DESIGN §6 |
| D20 | Usage limits | Default | 100 runs/day, 2 concurrent, configurable token cap | API_SPECIFICATION §11 |
| D21 | Component base | Default | Radix primitives for behaviour + custom styling | SYSTEM_ARCHITECTURE §2.1 |
| D22 | Team split | Pending | Owner to confirm ownership per area | DEVELOPMENT_ROADMAP §6 |
| — | Structured outputs, no code execution | Accepted | | [ADR-0005](adr/0005-structured-outputs-no-code-execution.md) |

## Change history
| Date | Change |
|---|---|
| 2026-11-11 | Blueprint v0.1 published with open decisions D1–D22 |
| 2026-11-12 | Phase 2 (frontend UI/UX with demo data) implemented; palette D23, phase order D24 and demo-data policy D25 recorded |
| 2026-11-12 | Owner has no Docker: local setup switched to native PostgreSQL via `infra/postgres/setup-local.sh`; Docker Compose kept as optional. Role bootstrap now re-syncs passwords on every run |
| 2026-11-12 | D1, D5, D8 finalised by the owner. ADR-0001…0007 written. Phase 1 approved and implemented. Application tables (`users`, `user_settings`, `refresh_tokens`, `audit_log`) moved from Phase 1 to Phase 2 (they belong with authentication); Phase 1 delivers the `app` schema, roles and migration baseline |
