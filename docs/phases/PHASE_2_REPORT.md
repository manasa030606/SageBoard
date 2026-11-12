# Phase 2 — Frontend UI/UX (demo data): completion report

| Field | Value |
|---|---|
| Date | 2026-11-12 |
| Status | Implemented and inspected; awaiting owner review before Phase 3 |
| Scope | Frontend only (`apps/web`). No backend changes. |

## Delivered

**Design system** (`src/app/globals.css`, `src/components/ui`): owner palette as tokens (D23); IBM Plex Sans/Mono and Source Serif 4, self-hosted; reusable text styles (`text-display`, `text-title`, `eyebrow`, `tabular`). Primitives: Button/ButtonLink/IconButton, Badge/StatusDot, Input/Textarea/Select/Field/Switch, Tabs (WAI-ARIA keyboard pattern) and Segmented, Table + InlineBar, Drawer (native `<dialog>`: focus trap, Esc), Toast, Skeleton, EmptyState, ErrorState, Notice, PageHeader, Section, Kbd.

**Charts** (`src/components/charts`): Recharts line and bar views (vertical, horizontal, grouped) with one tooltip, axis style and palette; Sparkline; `ChartRenderer` that maps the backend `ChartSpec` contract to components; chart/table toggles.

**Pages**
| Route | What it shows |
|---|---|
| `/` | Editorial landing: hero, live-rendered product preview, 6-step method, safety section with a real validation example, audience, CTA. No invented logos, testimonials or statistics. |
| `/app/dashboard` | KPI strip (revenue, orders, customers, growth with sparklines), revenue trend vs prior year (chart/table), sales by region, top products, recent analyses |
| `/app/analyst` | Dataset selector, conversation history, welcome + example questions, composer (Enter / Shift+Enter), live agent timeline (inspector on desktop, inline trace on smaller screens), interpretation and assumptions, plan, Chart/Table/SQL tabs, SQL viewer with highlighting and attempt switcher, sortable result table with CSV export, insights with evidence chips that highlight their rows, limitations, save/pin actions, follow-up suggestions, cancel |
| `/app/data` | Dataset table (ready/loading/failed states), dataset detail with per-table column profiles and inline description editing, upload drawer with real client-side validation and CSV type inference |
| `/app/history` | Search and filters, status badges, empty-filter state, run detail drawer with SQL and failure reasons |
| `/app/reports`, `/app/reports/[id]` | Editorial report list; report reading view with chart, data table, findings, limitations, SQL methodology; Markdown export and print/PDF |
| `/app/settings` | Profile form with validation, analysis preferences, data & privacy, usage meters, live system status (real API), guarded account deletion |
| `/status` | Phase 1 connectivity page (kept) |
| app-level | `loading.tsx`, `error.tsx`, `not-found.tsx` |

## Demo data policy (D25)
- All mock data is in `src/mocks`; components read it only through `src/lib/data`. Later phases swap those function bodies for API calls without changing the components.
- One seeded monthly series feeds every figure. KPIs, regional totals, segment totals and insight numbers are computed in `src/lib/data/analytics.ts`, and unit tests assert that they add up.
- The analyst replays **recorded sample runs** step by step, only for their exact questions. Any other question shows "Live analysis isn't connected yet" with no invented answer. Sample runs are labelled "Sample run", and the shell shows a "Demo data" notice.
- Actions that need the backend (save report, pin chart, load dataset, re-run, delete account) show an honest "not persisted" toast.

## Verification (actual results)
| Check | Result |
|---|---|
| Vitest | 55 passed (8 files): data consistency, grounding rules for sample runs, SQL tokenizer round-trip, CSV formula escaping, CSV preview and type inference, workspace reducer, Markdown export, Tabs keyboard and Composer behaviour |
| ESLint (0 warnings), `tsc` (strict), Prettier | Clean |
| `next build` | 18 routes generated |
| Headless Chrome inspection (production build) | 29 checks: every page at 1440 px and 390 px, plus analyst mid-run, completed, evidence click (exactly 2 rows highlighted), SQL attempts, unanswerable question, free-form question, upload error and CSV review, failed dataset, empty history filter, history drawer, settings validation, mobile nav, keyboard focus and 404. 0 console errors and 0 horizontal overflow in every check. |
| Settings → System status | Live: web, API liveness and readiness (database ok) |

Issues found during inspection and fixed: misaligned dashboard row; compact currency precision ("$481.04K" → "$481K"); missing dataset-select chevron (new Select with icon); hidden dataset icon (z-index); a responsive badge that didn't hide on mobile; inspector totals shown before a run finished; a heavy pre-result placeholder; preview text clipping on the landing page; chart axis label crowding on mobile; duplicate header on the embedded status panel.

## Known limitations
- No authentication: the user (Priya Raman, Northwind Retail) is demo data. Real auth is Phase 3.
- Nothing persists. Saved reports, pinned charts, edits and preferences reset on reload.
- Charts render client-side, so a moment of empty chart area appears on first load.
- Not yet automated: Playwright E2E and axe accessibility checks run in CI (planned for the hardening phase). This phase's inspection used a one-off headless-Chrome script.
