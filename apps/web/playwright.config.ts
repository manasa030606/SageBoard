import { defineConfig } from "@playwright/test";

/**
 * Browser tests run the real Next.js app against the real FastAPI + PostgreSQL stack.
 * Only the language model is replaced, by the evaluation "oracle" that replays reference SQL
 * (apps/api/evals/e2e_server.py), so no API key or quota is needed and runs are repeatable.
 *
 * The frontend is the one you already run on http://localhost:3001 (`reuseExistingServer`),
 * so you never need to stop it. That server was started with NEXT_PUBLIC_API_URL pointing at
 * your real backend (8000). NEXT_PUBLIC_* values are fixed when `next dev` starts, so the
 * tests cannot change it; instead `e2e/fixtures.ts` reroutes the browser's calls to that API
 * to the test backend on 8100. Your development database is never touched.
 *
 *   PLAYWRIGHT_CHROME_PATH=/path/to/chrome   use an installed Chrome instead of `playwright install`
 *   E2E_WEB_PORT      frontend port (default 3001)
 *   E2E_API_PORT      test backend port (default 8100)
 *   E2E_APP_API_URL   API URL your frontend was built with (default http://localhost:8000/api/v1)
 *
 * If nothing is running on the frontend port, Playwright starts `next dev` there itself, already
 * pointed at the test backend.
 */
const apiPort = process.env.E2E_API_PORT ?? "8100";
const webPort = process.env.E2E_WEB_PORT ?? "3001";
const webOrigin = `http://localhost:${webPort}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1, // the oracle serves one question at a time
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "e2e-results.json" }]],
  use: {
    baseURL: webOrigin,
    acceptDownloads: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROME_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROME_PATH }
      : {},
  },
  webServer: [
    {
      command: `uv run python -m evals.e2e_server ${apiPort}`,
      cwd: "../api",
      url: `http://localhost:${apiPort}/api/v1/auth/me`,
      // 401 means "up, not signed in"
      ignoreHTTPSErrors: true,
      reuseExistingServer: true,
      timeout: 60_000,
      env: { E2E_WEB_ORIGIN: webOrigin },
    },
    {
      command: `pnpm exec next dev -p ${webPort}`,
      url: webOrigin,
      reuseExistingServer: true,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: `http://localhost:${apiPort}/api/v1` },
    },
  ],
});
