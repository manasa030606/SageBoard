# Sageboard Web

Next.js 16 (App Router) + TypeScript + Tailwind CSS 4. **Phase 1** provides the foundation: design tokens, self-hosted fonts, the typed API client, a frontend health route, and a system status page that proves browser ↔ API connectivity.

> Next.js 16 changed several conventions (Cache Components, `LayoutProps`, `next typegen`). Before changing framework-level code, read the bundled docs in `node_modules/next/dist/docs/` (see `AGENTS.md`).

## Setup & run

```bash
cd apps/web
pnpm install
cp .env.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
pnpm dev                        # http://localhost:3000
```

Production build: `pnpm build && pnpm start`.

| Route             | Purpose                                                    |
| ----------------- | ---------------------------------------------------------- |
| `/`               | System status (replaced by the landing page in Phase 8)    |
| `GET /api/health` | Frontend liveness: `{status, service, version, timestamp}` |

## Configuration

| Variable              | Notes                                                                                                                                                                               |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | Base URL of the API **including** `/api/v1`. It is inlined into the browser bundle at **build** time, so rebuild after changing it. Never put secrets in `NEXT_PUBLIC_*` variables. |

## Code layout

```
src/
├── app/                    routes (layout, page, api/health)
│   └── globals.css         design tokens (@theme): colour, type, radius, motion
├── features/system-status/ status page (hook + panel)
└── lib/
    ├── env.ts              validated public config
    ├── version.ts
    └── api/                client.ts (typed fetch wrapper) · errors.ts (ApiError) · health.ts
```

**API client:** `apiRequest<T>(path, options)` sends cookies (`credentials: "include"`), applies a timeout, and turns every failure (HTTP error envelope, network or CORS failure, timeout, malformed body) into a single `ApiError` type with `status`, `code`, `message` and `requestId`.

## Quality

```bash
pnpm lint          # ESLint (next + typescript + prettier-compat), zero warnings allowed
pnpm typecheck     # next typegen && tsc --noEmit
pnpm format:check  # Prettier (+ Tailwind class ordering)
pnpm test          # Vitest unit tests
pnpm check         # all of the above
```
