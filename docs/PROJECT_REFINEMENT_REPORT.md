# Project refinement report (pre-Phase 10)

A cleanup and restructuring pass. No features were added and Phase 10 was not started. Nothing was committed or pushed.

## 1. Repository structure

Before: `docs/` held 39 files (10 design documents, 7 ADRs, 9 per-phase reports, 4 evaluation documents, 2 dataset exports, 7 result files), plus three app-level READMEs and a stale root README that described Phase 2. The web app carried a `src/mocks/` and `src/lib/data/` tree of demo data, a `features/landing/` preview, and demo-era types.

After:

```
apps/api/        backend (README is a 3-line pointer; pyproject needs the file)
apps/web/        frontend (README is a pointer)
infra/           local PostgreSQL setup
docs/
  architecture/ARCHITECTURE.md      system, database, API, agent
  security/SECURITY.md              threat model, SQL Guard, roles, app security
  development/DEVELOPMENT.md       setup, config, tests, limitations, status
  development/DECISIONS.md         decision log and the seven ADRs
  eval/                             README, summary, failure analysis, benchmark, dataset/, results/
  archive/PRD.md                    original product brief
  PROJECT_REFINEMENT_REPORT.md
README.md        short root README
```

`docs/` is now 16 files.

## 2. Code simplifications

- The Dashboard and Settings pages read real API data instead of seeded demo series (see 5).
- The landing page no longer contains a fake product preview; it states what the product does and shows real example questions from the evaluation set.
- `types/domain.ts` is reduced to the types the UI uses; `TimelineStep.status` and `ChartSpec.chartType` use the API's own types.
- Components that exposed only internal helpers no longer export them (`SERIES_COLORS`, `buttonClasses`, `columnLabel`, upload constants).

## 3. Removed code, files and dependencies

Unused code (confirmed by ruff, knip and grep, then tests): backend `RunManager.is_running`, `RateLimiter.reset`, `uuid_pk`, `get_engine`, `group_by_category`, two unused imports; frontend `StatusDot`, `Textarea`, `Switch`, `TableCaption`, `InlineBar`, `Sparkline`, `currentActivity`, `currencyCents`, the demo-data modules, `kpi-strip`, `revenue-trend`, `dashboard-tables`, `features/landing`, and the demo-data tests (13 tests of fake analytics).

Dependency: the explicit dev dependency `httpx2` was removed from `apps/api/pyproject.toml`. It remains installed as a transitive dependency of LangGraph; `uv.lock` changed by two lines. No other dependency was added or removed, and no lockfile was regenerated.

`.gitignore` gained `.hypothesis/`.

Removed non-code files are listed in section 4.

## 4. Documentation consolidated

| Removed | Where the content lives now |
|---|---|
| `SYSTEM_ARCHITECTURE.md`, `AGENT_WORKFLOW.md`, `DATABASE_DESIGN.md`, `API_SPECIFICATION.md` | `ARCHITECTURE.md`. The generated column-level table reference is replaced by `scripts/schema_reference.py`; the request and response shapes are the live OpenAPI document. Unbuilt designs (SSE stream, pinned widgets, settings and usage APIs, planned tables) were dropped. |
| `SECURITY_DESIGN.md`, `SQL_SAFETY.md` | `SECURITY.md` (threat model, Guard specification and pipeline, self-correction, cost gate, roles, LLM controls, app security, uploads, release gate). Unbuilt items are labelled "not yet implemented". |
| `TESTING_STRATEGY.md` | `DEVELOPMENT.md` section 6, as built. The aspirational suites it described that do not exist (nightly live evaluation, visual regression, axe tests, coverage gates) were not carried over. |
| `DEVELOPMENT_ROADMAP.md` | `DEVELOPMENT.md` section 8 (status and next steps) |
| `DECISION_LOG.md`, `docs/adr/0001-0007` | `DECISIONS.md`, with status notes that say which decisions were superseded or never built |
| `docs/phases/PHASE_1-9_REPORT.md` | Their limitations are in `DEVELOPMENT.md` section 7; their measured results were already in `docs/eval/`. Per-phase reports were removed as you decided. |
| `PRD.md` | Moved to `docs/archive/PRD.md` with a note that the built system differs. It holds requirements and personas that are in none of the four new documents. |
| `apps/api/README.md`, `apps/web/README.md`, `infra/README.md`, old root README | `DEVELOPMENT.md` (setup, configuration, Neon runbook, role model), `ARCHITECTURE.md` (code layout); new short root README. |
| `docs/eval/results/safety-small.json`, `bench-small.json` | Unreferenced small-scale duplicates. The standard-scale files, `oracle-small.jsonl` and `oracle-small.before-fixes.jsonl` were kept because the generated summary and the failure analysis refer to them. |

Code comments that named the old documents now name the new ones. All relative links in the docs were checked and resolve.

## 5. UI/UX improvements

- **Dashboard:** shows your datasets, recent analyses and recent reports from the API, with skeleton, empty and error-with-retry states.
- **Settings:** account details and live system status only. The forms that never saved, the made-up usage meters and a "Delete account" button with no backend were removed.
- **Analyst page:** the duplicated "New conversation" button is gone and the toolbar no longer overflows at 390 px.
- **Report page:** long SQL no longer widens the page; the toolbar wraps; table-only results no longer show an empty chart box; "1 insight verified" is pluralised correctly.
- **Landing:** honest copy, fewer decorative elements, the mobile Sign-in button hides correctly.
- The sidebar notice "Sample analysis" was removed because nothing is sample data any more.

## 6. Design decisions

The existing visual system was kept: IBM Plex type, a restrained palette, hairline borders, no gradients or glass. The warning signs on your list were treated as signals, not rules. The landing page lost its fake terminal, icon tiles and uniform card grid; it uses one column of plain text and a real example list. Terms and Privacy pages were not written, because they would make legal claims the project cannot back.

## 7. Files reorganised

Docs moved into `architecture/`, `security/`, `development/`, `archive/`. The Playwright arrangement (frontend 3001, test backend 8100, browser API redirection) was not touched.

## 8. Security and correctness issues found

- **Fixed:** the Analyst toolbar and report page overflowed on mobile; a Tailwind conflict (`hidden` plus `inline-flex`, because `cn()` does not merge classes) kept a button visible on mobile; an empty chart box rendered for table-only results.
- **Honesty problem fixed:** the Dashboard, Settings and landing preview presented demo data as if it were the user's.
- **Open (not changed):** see section 10.

## 9. Tests and results

| Check | Result |
|---|---|
| ruff check, ruff format --check, mypy (152 source files) | clean |
| Backend pytest, full run with real PostgreSQL | 669 passed, 0 skipped (same as the baseline) |
| Web ESLint, tsc, Prettier, Vitest | clean; 84 tests in 16 files (baseline had 94: 13 tests of the removed demo analytics were deleted and 3 new dashboard tests were added) |
| `next build` | succeeded |
| Playwright E2E | 5 passed |
| Oracle evaluation, small scale, rerun | all 62 cases have the same status as the baseline run |
| Safety evaluation, standard scale | all metrics equal the committed results; only a timing field differs |
| Benchmark | ran; the committed result files were restored afterwards because timings vary run to run |
| Rendered UI | 16 pages at 1440 px and 390 px reviewed; no horizontal overflow except the SQL text inside its own scroll box |

`evals report` was not rerun, because it overwrites `EVALUATION_SUMMARY.md`; that file is unchanged.

## 10. Remaining technical debt

- Stored results can show real email addresses to the dataset owner.
- A silent-zero wrong answer (case R06) cannot be detected.
- A sensitive column that is aliased in a query can reach the model.
- CI does not run Playwright; there is no CSP, `pip-audit` or `pnpm audit` in CI.
- Live-model accuracy has not been measured.
- The PDF text says "1 insights verified" (`app/reports/pdf.py`); the web copy is fixed.
- `starlette` and `langchain_core` are imported directly but are only transitive dependencies.
- `src/lib/api/types.ts` exports some types nothing imports.
- No Terms or Privacy pages (your decision).

## 11. For Phase 10

Items for the next planning step: decide whether to add the production-hardening items above (security headers, audit checks, Playwright in CI), account deletion and password reset, and the real-model evaluation pass. Per your rules, none of it starts without your approval.
