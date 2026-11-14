# Sageboard Web

Next.js 16 (App Router) + TypeScript + Tailwind CSS 4 + Recharts.

- **Phase 2**: the complete product UI.
- **Phase 4**: connected to the real API. Sign-in and sign-up, data sources (upload, review, load, preview, sensitivity, delete, sample dataset), query history and reports are live.

Dashboard and Analyst still show labelled, recorded sample runs until the AI analyst exists.

> Next.js 16 changed several conventions (Cache Components, `LayoutProps`, `next typegen`). Before changing framework-level code, read the bundled docs in `node_modules/next/dist/docs/` (see `AGENTS.md`).

## Setup & run

```bash
cd apps/web
pnpm install
cp .env.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
pnpm dev                        # http://localhost:3000
```

Open **http://localhost:3000** (not 127.0.0.1) so the web app and the API at `localhost:8000` count as the same site. Otherwise the browser won't send the sign-in cookies.

Production build: `pnpm build && pnpm start`.

| Route                               | Purpose                                                         |
| ----------------------------------- | --------------------------------------------------------------- |
| `/`                                 | Landing page                                                    |
| `/login`, `/register`               | Sign in / create an account                                     |
| `/app/*`                            | Signed-in area (redirects to `/login?next=…` without a session) |
| `/app/dashboard`                    | Analytics dashboard (sample data)                               |
| `/app/analyst`                      | AI analyst workspace (replays recorded sample runs)             |
| `/app/data`                         | Data sources: live                                              |
| `/app/history`                      | Query history: live SQL audit trail                             |
| `/app/reports`, `/app/reports/[id]` | Reports: live                                                   |
| `/app/settings`                     | Settings (includes live system status)                          |
| `/status`                           | Connectivity check (web ↔ API ↔ database)                       |
| `GET /api/health`                   | Frontend liveness                                               |

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
│   ├── api/                 client.ts (cookies, CSRF header, one silent refresh, ApiError)
│   │                        · endpoints.ts (one function per endpoint) · types.ts (API shapes)
│   ├── use-api.ts           data-loading hook (loading / error / reload, stale-response safe)
│   ├── data/                sample data for Dashboard and Analyst only (reads src/mocks)
│   └── format.ts · csv.ts · sql-highlight.ts · csv-preview.ts
├── features/auth/           sign-in / sign-up form, SessionProvider (guard, sign-out)
├── mocks/                   SAMPLE DATA ONLY for Dashboard and Analyst
└── types/domain.ts          shared interfaces (mirror docs/API_SPECIFICATION.md)
```

**Sample pages:** every Dashboard figure comes from one seeded series (`lib/data/analytics.ts`). The Analyst replays recorded sample runs only for their exact questions and never invents an answer to any other question. Both are labelled in the sidebar.

**Sessions:** pages under `/app` wait for `GET /auth/me`. Sign-in, sign-out and an expired session each trigger a full page load, so nothing from a previous session stays in memory.

## Quality

```bash
pnpm lint          # ESLint (next + typescript + prettier-compat), zero warnings allowed
pnpm typecheck     # next typegen && tsc --noEmit
pnpm format:check  # Prettier (+ Tailwind class ordering)
pnpm test          # Vitest: unit + component tests
pnpm check         # all of the above
```
