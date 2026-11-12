# Sageboard Web

Next.js 16 (App Router) + TypeScript + Tailwind CSS 4 + Recharts. **Phase 2** delivers the complete product UI on **demo data**: landing, dashboard, analyst workspace, data sources, query history, reports and settings.

> Next.js 16 changed several conventions (Cache Components, `LayoutProps`, `next typegen`). Before changing framework-level code, read the bundled docs in `node_modules/next/dist/docs/` (see `AGENTS.md`).

## Setup & run

```bash
cd apps/web
pnpm install
cp .env.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
pnpm dev                        # http://localhost:3000
```

Production build: `pnpm build && pnpm start`.

| Route                               | Purpose                                                          |
| ----------------------------------- | ---------------------------------------------------------------- |
| `/`                                 | Landing page                                                     |
| `/app/dashboard`                    | Analytics dashboard                                              |
| `/app/analyst`                      | AI analyst workspace (replays recorded sample runs in demo mode) |
| `/app/data`                         | Data sources and datasets                                        |
| `/app/history`                      | Query history                                                    |
| `/app/reports`, `/app/reports/[id]` | Reports                                                          |
| `/app/settings`                     | Settings (includes live system status)                           |
| `/status`                           | Connectivity check (web ↔ API ↔ database)                        |
| `GET /api/health`                   | Frontend liveness                                                |

## Configuration

| Variable              | Notes                                                                                                                                                                               |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | Base URL of the API **including** `/api/v1`. It is inlined into the browser bundle at **build** time, so rebuild after changing it. Never put secrets in `NEXT_PUBLIC_*` variables. |

## Code layout

```
src/
├── app/                     routes (App Router); app/app/* = product area
│   └── globals.css          design tokens (@theme) + text styles
├── components/
│   ├── ui/                  design-system primitives (Button, Tabs, Drawer, Table, states…)
│   ├── charts/              Recharts views + ChartRenderer (ChartSpec → chart)
│   ├── data/                ResultTableView (sort, evidence highlight, CSV export)
│   ├── shell/               app shell (sidebar, mobile nav, page container)
│   └── brand/               logo
├── features/                one folder per page: landing, dashboard, analyst, data, history, reports, settings
├── lib/
│   ├── data/                ← the ONLY data access used by components (reads src/mocks today)
│   ├── api/                 typed API client (system status today; all data in later phases)
│   └── format.ts · csv.ts · sql-highlight.ts · csv-preview.ts · report-markdown.ts
├── mocks/                   DEMO DATA ONLY (seeded series, datasets, sample runs, history, reports)
└── types/domain.ts          shared interfaces (mirror docs/API_SPECIFICATION.md)
```

**Demo mode:** every figure comes from one seeded series and is derived in `lib/data/analytics.ts`, so the numbers always agree. The analyst replays recorded sample runs only for their exact questions and never invents an answer to any other question.

## Quality

```bash
pnpm lint          # ESLint (next + typescript + prettier-compat), zero warnings allowed
pnpm typecheck     # next typegen && tsc --noEmit
pnpm format:check  # Prettier (+ Tailwind class ordering)
pnpm test          # Vitest: unit + component tests
pnpm check         # all of the above
```
