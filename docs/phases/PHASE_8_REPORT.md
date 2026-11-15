# Phase 8 Report — Conversation memory, query history & report generation

| Field | Value |
|---|---|
| Phase | 8 — Conversation memory, query history and report generation (owner-defined, D53–D55) |
| Status | Done 2026-11-15 |
| Verification | 559 backend tests (113 marked integration, run against PostgreSQL) · 71 web tests · ruff + ruff format + mypy clean · eslint (0 warnings) + tsc + next build clean · PDFs rendered and inspected page by page |
| Migration | 0006 — `analysis_sessions.memory` (JSONB) |
| New dependencies | `reportlab` (PDF), `pypdf` (dev: PDF text extraction in tests) |

## 1. What already existed, and what this phase added

| Requirement (owner's spec) | State before | Phase 8 |
|---|---|---|
| Preserve context, follow-ups | last 3 finished turns passed verbatim | per-turn memory record + relevance-gated retrieval |
| Resolve "compare it with last month" | not handled | `understand_query.v2` reference-resolution rules, tested through the real pipeline |
| Store conversation summaries | — | `analysis_sessions.memory`, built by code (no model call) |
| Retrieve only relevant context | all recent turns | ≤ 3 turns, follow-up detection + topic overlap, 3,500-char budget; an unrelated question gets none |
| Never mix datasets or users | scoped by conversation only | candidates fetched with owner + dataset + conversation in the WHERE clause; stale dataset versions drop their numbers |
| Save question, dataset, status, plan, SQL, results, insights, timestamp | already stored (`analysis_sessions`, `result`, `query_executions`) | no duplicate tables; verified and exposed through an enriched history list and deep links |
| PDF report with the 10 sections | Markdown export of question/summary/SQL only | report snapshot v2 + server-rendered PDF with all ten sections |
| Numbers in reports match stored results | — | grounding engine re-run on every read/export; mismatches flagged |
| Frontend: search, reopen, save, download PDF, continue | SQL-log table only | History = Analyses (search, filters, open, continue, save, PDF) + SQL log; run-card report actions; richer report view |
| User-level access control | per-owner scoping | extended and tested on every new route |

## 2. Backend

- **Memory** (`app/agent/memory.py`, `runner._conversation_context`, `understand_query.v2.md`) — see AGENT_WORKFLOW §7. Deterministic, per conversation, isolated, never reuses earlier numbers as facts.
- **History** (`HistoryItem`, `HistoryService.list_sessions`) — dataset and conversation names, answer snippet, finding/query counts and newest report id computed in SQL; `q` searches question, answer and dataset name (LIKE wildcards literal); new `since` filter; every join re-checks `owner_id`.
- **Reports** (`app/reports/`): `snapshot.py` (v2 snapshot from the stored result), `fidelity.py` (grounding re-check), `markdown.py`, `pdf.py` (reportlab: Bitstream Vera, vector charts with legends, headings kept with their content, SQL wrapped, XML-escaped text). `GET /reports/{id}/export.pdf`, `GET /reports?analysis_session_id=`, `ReportDetail.fidelity`.
- **Two real bugs found by the new tests and fixed:** a NUL character in a report title/summary produced a PostgreSQL 500 (now dropped at the schema boundary); a non-ASCII title produced an un-encodable `Content-Disposition` header and a 500 on export (filenames are now ASCII-slugged — this also fixed the existing Markdown export).

## 3. Frontend

- `features/history/{history-screen,analysis-history}.tsx` — search (debounced), outcome/dataset/date filters, status badges, answer preview, counts, **Open analysis**, **Continue conversation**, **Save as report** / **View report** / **Download PDF**, empty/no-match/loading/error states, "Load more".
- `features/analyst/live/report-actions.tsx` — saved state comes from the server (`GET /reports?analysis_session_id=`), so a reopened analysis shows the truth.
- `workspace.tsx` — `/app/analyst?conversation=<id>&session=<id>` deep link (Suspense boundary on the page); the linked conversation's dataset is selected, the analysis is opened and scrolled into view; a failed link shows a notice and falls back to a fresh thread.
- `features/reports/report-view.tsx` — all sections from snapshot v2 (charts re-drawn from stored data), fidelity notice, **Download PDF**; v1 reports still render with a note.
- `lib/api/client.ts` — `responseType: "blob"`; `lib/download.ts` — `saveFile`, `fileSlug`.

## 4. Tests added

| File | Proves |
|---|---|
| `tests/agent/test_memory.py` (24) | follow-up detection, record building, relevance selection, budget, stale versions, prompt rules |
| `tests/integration/test_phase8_memory.py` (2) | the model receives exactly the previous turn for a follow-up, none for a first question or a new conversation, and never another user's data (asserted on the prompt text) |
| `tests/integration/test_phase8_history_reports.py` (8) | history fields, search, persistence across an app restart, snapshot v2, PDF contains all ten sections and the stored figures (compared with the uploaded CSV), edited summary with an invented number flagged, markup/NUL/CJK safe, owner isolation on every report route |
| `client-auth.test.ts`, `download.test.ts` (4) | blob responses and error envelopes, filename slugs |

## 5. Limitations (honest list)

- Memory is **within one conversation** only. Asking "like last time" in a new conversation does not recall the old one — deliberate (D53), because cross-conversation recall is the main isolation risk.
- Follow-up detection is rule-based; an unusual phrasing of a follow-up that matches none of the rules and shares no topic words will be treated as a standalone question (the model can still ask for clarification).
- Reference resolution quality depends on the model; it is covered by prompt rules and by tests of what the model is *shown*, and needs a live check with the real model (see checklist).
- PDF charts: bar/grouped/horizontal/histogram, line/area, pie/donut and KPI are drawn; scatter and undrawable specs fall back to a data table. Charts show at most 40 stored rows; step tables at most 10.
- Fidelity covers the summary, findings and recommendations. It cannot judge whether a number is *meaningful*, only that it exists in the stored results.
- Reports saved before Phase 8 (v1) have no findings/charts/limitations; they open and export with a note.
- PDF fonts are Latin-only (Bitstream Vera); other scripts are shown as `?` rather than boxes.

## 6. Run it yourself — checklist

1. `cd apps/api && uv sync` (adds reportlab, pypdf) then `uv run alembic upgrade head` (migration 0006).
2. `set -a && source .env.test && set +a && uv run pytest` — expect 559 passed.
3. `uv run ruff check . && uv run ruff format --check . && uv run mypy` — clean.
4. `cd apps/web && pnpm install && pnpm lint && pnpm typecheck && pnpm test && pnpm build` — 71 tests.
5. Start API and web; with your Gemini key set, open **Analyst**, pick the sample dataset and ask: *"What was revenue by region in 2026?"*, then *"Compare it with 2025"* — the second run's trace (`understand_query`) should show `prior_turns: 1`, and its restated question should name revenue and region.
6. Click **Save as report**, then **Download PDF**; open the PDF and check the ten sections and that the numbers match the answer.
7. Open **History**: search for a word from an answer, open an old analysis, and press **Continue conversation**.
8. On the report page edit the summary to include a number that is not in the data (e.g. "grew 97%") — the warning notice should appear on the page and in a new PDF.
9. Sign in as a second user: History and Reports must be empty, and pasting the first user's report URL must show "Report not found".
