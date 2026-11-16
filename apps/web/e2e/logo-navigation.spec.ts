import { type BrowserContext, type Page } from "@playwright/test";

import { expect, newIsolatedContext, test } from "./fixtures";

/*
 * Where does the Sageboard logo lead? Every scenario below runs in its own brand-new browser
 * context (own cookies and storage), never one that an earlier test signed in:
 *   - signed in (a live session confirmed by the API)  -> /app/dashboard
 *   - everything else: nobody, expired, invalid, API down, still checking -> /
 */
const apiBase = `http://localhost:${process.env.E2E_API_PORT ?? "8100"}/api/v1`;
const PASSWORD = "correct horse battery staple 9";

const logo = (page: Page) =>
  page.getByRole("link", { name: /^Sageboard (home|dashboard)$/ }).last();

/** Opens a page and waits until the session check on it has been answered. */
async function open(page: Page, path: string): Promise<number | null> {
  const answered = page.waitForResponse((r) => r.url().endsWith("/auth/me"), { timeout: 15_000 });
  await page.goto(path);
  return (await answered.catch(() => null))?.status() ?? null;
}

const cookieNames = async (context: BrowserContext) =>
  (await context.cookies()).map((c) => c.name).sort();

test.describe("a visitor (fresh browser, no cookies)", () => {
  for (const path of ["/", "/login", "/register", "/status"]) {
    test(`clicking the logo on ${path} reaches the landing page, never the dashboard`, async ({
      browser,
    }) => {
      const context = await newIsolatedContext(browser);
      try {
        expect(await cookieNames(context)).toEqual([]);
        const page = await context.newPage();
        const visited: string[] = [];
        page.on("framenavigated", (frame) => visited.push(new URL(frame.url()).pathname));

        expect(await open(page, path)).toBe(401);
        await expect(logo(page)).toHaveAttribute("href", "/");
        await expect(logo(page)).toHaveAttribute("data-auth-state", "visitor");
        await logo(page).click();
        await expect(page).toHaveURL(/\/$/);
        await page.waitForTimeout(500); // a late redirect would show up here
        expect(new URL(page.url()).pathname).toBe("/");
        expect(visited.some((p) => p.startsWith("/app"))).toBe(false);
        expect(await cookieNames(context)).toEqual([]); // checking created no session
      } finally {
        await context.close();
      }
    });
  }
});

test.describe("sessions that are not valid", () => {
  test("an expired or invalid access cookie is a visitor", async ({ browser }) => {
    const context = await newIsolatedContext(browser);
    try {
      await context.addCookies([
        { name: "sb_session", value: "expired.or.invalid", domain: "localhost", path: "/" },
      ]);
      const page = await context.newPage();
      expect(await open(page, "/login")).toBe(401);
      await expect(logo(page)).toHaveAttribute("href", "/");
      await logo(page).click();
      await expect(page).toHaveURL(/\/$/);
    } finally {
      await context.close();
    }
  });

  test("an invalid refresh cookie cannot sign the logo in, and is never even tried", async ({
    browser,
  }) => {
    const context = await newIsolatedContext(browser);
    try {
      await context.addCookies([
        { name: "sb_session", value: "expired.or.invalid", domain: "localhost", path: "/" },
        {
          name: "sb_refresh",
          value: "not-a-real-token",
          domain: "localhost",
          path: "/api/v1/auth",
        },
      ]);
      const page = await context.newPage();
      const refreshCalls: string[] = [];
      page.on("request", (r) => r.url().includes("/auth/refresh") && refreshCalls.push(r.url()));

      expect(await open(page, "/login")).toBe(401);
      await expect(logo(page)).toHaveAttribute("href", "/");
      await logo(page).click();
      await expect(page).toHaveURL(/\/$/);
      expect(refreshCalls).toEqual([]); // a logo check never uses the refresh cookie

      // and the API itself refuses that refresh token, so nothing else could sign it in
      const refresh = await context.request.post(`${apiBase}/auth/refresh`, {
        headers: { Cookie: "sb_refresh=not-a-real-token" },
      });
      expect(refresh.status()).toBe(401);
    } finally {
      await context.close();
    }
  });

  test("an unreachable or failing API is a visitor", async ({ browser }) => {
    for (const fail of ["abort", "500"] as const) {
      const context = await newIsolatedContext(browser);
      try {
        const page = await context.newPage();
        await page.route("**/auth/me", (route) =>
          fail === "abort" ? route.abort("failed") : route.fulfill({ status: 500, body: "oops" }),
        );
        await page.goto("/login");
        await expect(logo(page)).toHaveAttribute("href", "/");
        await logo(page).click();
        await expect(page).toHaveURL(/\/$/);
      } finally {
        await context.close();
      }
    }
  });

  test("while the check is still running the logo stays on the public fallback", async ({
    browser,
  }) => {
    const context = await newIsolatedContext(browser);
    try {
      const page = await context.newPage();
      let release: () => void = () => {};
      const gate = new Promise<void>((resolve) => (release = resolve));
      await page.route("**/auth/me", async (route) => {
        await gate;
        await route.fulfill({ status: 401, body: "{}", contentType: "application/json" });
      });
      await page.goto("/login");
      await expect(logo(page)).toHaveAttribute("href", "/");
      await logo(page).click();
      await expect(page).toHaveURL(/\/$/);
      release();
    } finally {
      await context.close();
    }
  });
});

test.describe("a signed-in user, with a visitor beside them", () => {
  test("only the signed-in browser reaches the dashboard", async ({ browser }) => {
    const user = {
      name: "Logo Tester",
      email: `logo-${Date.now()}@example.test`,
    };

    // Browser A: sign up (this also signs in).
    const a = await newIsolatedContext(browser);
    const visitor = await newIsolatedContext(browser);
    try {
      const pageA = await a.newPage();
      await pageA.goto("/register");
      await pageA.getByLabel("Full name").fill(user.name);
      await pageA.getByLabel("Email").fill(user.email);
      await pageA.getByLabel("Password").fill(PASSWORD);
      await pageA.getByRole("button", { name: "Create account" }).click();
      await expect(pageA).toHaveURL(/\/app/);
      expect(await cookieNames(a)).toEqual(expect.arrayContaining(["sb_refresh", "sb_session"]));

      // Test 3: signed in, the logo leads to the dashboard from the app and from public pages.
      await pageA.goto("/app/data");
      await logo(pageA).click();
      await expect(pageA).toHaveURL(/\/app\/dashboard$/);
      for (const start of ["/", "/login", "/register", "/status"]) {
        expect(await open(pageA, start)).toBe(200);
        await expect(logo(pageA)).toHaveAttribute("href", "/app/dashboard");
        await expect(logo(pageA)).toHaveAttribute("data-auth-state", "signed-in");
        await logo(pageA).click();
        await expect(pageA).toHaveURL(/\/app\/dashboard$/);
      }

      // Browser B is a different person at the same time: a visitor, even while A is signed in.
      const pageB = await visitor.newPage();
      expect(await cookieNames(visitor)).toEqual([]);
      for (const start of ["/", "/login"]) {
        expect(await open(pageB, start)).toBe(401);
        await logo(pageB).click();
        await expect(pageB).toHaveURL(/\/$/);
      }

      // Test 7: a browser that already has a session opens /login. The API confirms the
      // session, the page says so, and the logo leads to the dashboard, which is correct.
      expect(await open(pageA, "/login")).toBe(200);
      const me = await a.request.get(`${apiBase}/auth/me`);
      expect(me.status()).toBe(200);
      const notice = pageA.getByRole("status").filter({ hasText: "You’re already signed in" });
      await expect(notice).toContainText(user.name);
      await expect(logo(pageA)).toHaveAttribute("href", "/app/dashboard");
      await expect(pageA.getByRole("heading", { name: "Sign in" })).toBeVisible(); // form still there

      // Signing out from that notice ends the session: now the same page is a visitor's.
      const afterSignOut = pageA.waitForResponse(
        (r) => r.url().endsWith("/auth/me") && r.request().frame() !== null && r.status() === 401,
      );
      await notice.getByRole("button", { name: "Sign out" }).click();
      await expect(pageA).toHaveURL(/\/login$/);
      await afterSignOut; // the freshly loaded /login asked again, and was told "no session"
      await expect(pageA.getByText("You’re already signed in")).toHaveCount(0);
      await expect(logo(pageA)).toHaveAttribute("href", "/");
      await logo(pageA).click();
      await expect(pageA).toHaveURL(/\/$/);
      expect(await cookieNames(a)).not.toContain("sb_session");

      // B was never affected by any of this.
      expect(await cookieNames(visitor)).toEqual([]);
    } finally {
      await a.close();
      await visitor.close();
    }
  });
});
