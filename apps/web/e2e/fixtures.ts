/* eslint-disable react-hooks/rules-of-hooks -- Playwright fixtures call `use`, which is not a React hook */
import { expect, test as base } from "@playwright/test";

const testApi = `http://localhost:${process.env.E2E_API_PORT ?? "8100"}/api/v1`;
const appApi = (process.env.E2E_APP_API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");

/**
 * Every browser context sends the frontend's API calls to the test backend instead of the
 * API URL baked into the running dev server. When the two URLs are the same this is a no-op.
 */
export const test = base.extend({
  context: async ({ context }, use) => {
    if (appApi !== testApi) {
      await context.route(`${appApi}/**`, (route) => {
        const url = route.request().url().replace(appApi, testApi);
        return route.continue({ url });
      });
    }
    await use(context);
  },
});

export { expect };
