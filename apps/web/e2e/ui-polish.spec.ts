import { expect, test } from "./fixtures";

const stamp = Date.now();
const user = {
  // Long on purpose: both used to push the sidebar footer past the sidebar's edge.
  name: "Manasa Chinnam Venkata Subramanyam",
  email: `manasa.chinnam.longaddress-${stamp}@subdomain.example.test`,
  password: "correct horse battery staple 9",
};

test.describe.configure({ mode: "serial" });

for (const path of ["/login", "/register"]) {
  test(`password field on ${path} is hidden by default and can be revealed`, async ({ page }) => {
    await page.goto(path);
    const password = page.getByLabel("Password");
    await expect(password).toHaveAttribute("type", "password");

    await password.fill(user.password);
    await page.getByRole("button", { name: "Show characters" }).click();
    await expect(password).toHaveAttribute("type", "text");
    await expect(password).toHaveValue(user.password);
    await expect(password).toBeFocused(); // pressing the eye does not pull focus off the field

    await page.getByRole("button", { name: "Hide characters" }).click();
    await expect(password).toHaveAttribute("type", "password");
  });
}

const SIGNED_IN_REPLY = {
  user: { id: "u-1", email: "x@example.test", full_name: "X" },
  csrf_token: "t",
  auth_mode: "session",
};

for (const path of ["/login", "/register"]) {
  test(`a visitor's logo on ${path} leads to the landing page`, async ({ page }) => {
    const me = page.waitForResponse((r) => r.url().endsWith("/auth/me"));
    await page.goto(path);
    expect((await me).status()).toBe(401);
    const logo = page.getByRole("link", { name: "Sageboard home" }).last();
    await expect(logo).toHaveAttribute("href", "/");
    await logo.click();
    await expect(page).toHaveURL(/\/$/);
  });
}

test("when the session check answers 401 the logo leads to the landing page", async ({ page }) => {
  await page.route("**/auth/me", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "UNAUTHENTICATED", message: "Sign in." } }),
    }),
  );
  await page.goto("/login");
  await page.getByRole("link", { name: "Sageboard home" }).last().click();
  await expect(page).toHaveURL(/\/$/);
});

test("when the session check fails the logo leads to the landing page", async ({ page }) => {
  await page.route("**/auth/me", (route) => route.abort("failed")); // API unreachable
  await page.goto("/login");
  await page.getByRole("link", { name: "Sageboard home" }).last().click();
  await expect(page).toHaveURL(/\/$/);

  await page.route("**/auth/me", (route) => route.fulfill({ status: 500, body: "oops" }));
  await page.goto("/login");
  await page.getByRole("link", { name: "Sageboard home" }).last().click();
  await expect(page).toHaveURL(/\/$/);
});

test("while the session check is still running the logo does not lead to the dashboard", async ({
  page,
}) => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/auth/me", async (route) => {
    await gate; // a slow API that will eventually say "signed in"
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SIGNED_IN_REPLY),
    });
  });
  await page.goto("/login");
  const logo = page.getByRole("link", { name: "Sageboard home" }).last();
  await expect(logo).toHaveAttribute("href", "/");
  await logo.click(); // pressed before the answer arrives
  await expect(page).toHaveURL(/\/$/);
  release();
});

test("the API's demo mode (nobody signs in) is not treated as signed in", async ({ page }) => {
  await page.route("**/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...SIGNED_IN_REPLY, auth_mode: "demo" }),
    }),
  );
  await page.goto("/login");
  await page.waitForResponse((r) => r.url().endsWith("/auth/me"));
  await expect(page.getByRole("link", { name: "Sageboard home" }).last()).toHaveAttribute(
    "href",
    "/",
  );
});

test.describe("sign-in illustration", () => {
  const viewports = [
    { width: 1920, height: 1080 },
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
    { width: 1280, height: 720 },
    { width: 1280, height: 600 },
    { width: 1100, height: 700 },
    { width: 1024, height: 640 },
  ];
  for (const viewport of viewports) {
    test(`is visible and fits at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/login");
      const art = page.locator("aside svg.sb-illo");
      await expect(art).toBeVisible();
      const box = (await art.boundingBox())!;
      expect(box.width).toBeGreaterThan(220);
      expect(box.height).toBeGreaterThan(130);
      const aside = (await page.locator("aside").boundingBox())!;
      expect(box.x + box.width).toBeLessThanOrEqual(aside.x + aside.width);
      const overflow = await page.evaluate(() => ({
        x: document.documentElement.scrollWidth - innerWidth,
        y: document.documentElement.scrollHeight - innerHeight,
      }));
      expect(overflow.x).toBeLessThanOrEqual(0);
      expect(overflow.y).toBeLessThanOrEqual(0); // the panel never pushes the page taller
      await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    });
  }

  test("animates, and stands still (fully drawn) for reduced motion", async ({ page }) => {
    const names = () =>
      page.evaluate(() =>
        [".sb-bar", ".sb-line", ".sb-flow", ".sb-spin", ".sb-float"].map(
          (sel) => getComputedStyle(document.querySelector(`.sb-illo ${sel}`)!).animationName,
        ),
      );
    await page.goto("/login");
    for (const name of await names()) expect(name).not.toBe("none");

    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const name of await names()) expect(name).toBe("none");
    // nothing is left half-drawn: the bars are at full height
    const scale = await page.evaluate(
      () => getComputedStyle(document.querySelector(".sb-bar")!).transform,
    );
    expect(scale === "none" || scale === "matrix(1, 0, 0, 1, 0, 0)").toBe(true);
  });

  test("the form stays usable beside it", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 600 });
    await page.goto("/login");
    await page.getByLabel("Email").fill("someone@example.test");
    await page.getByLabel("Password").fill("a long enough password");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });
});

// One account for the signed-in checks: sign-ups are rate limited, so each test does not make its own.
test("signed-in layout and logo navigation, with a long name and email", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Full name").fill(user.name);
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app/);

  for (const width of [1024, 1280, 1440]) {
    await test.step(`sidebar keeps Settings and the user menu inside it at ${width}px`, async () => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto("/app/data");
      const aside = page.locator("aside");
      await expect(aside.getByText(user.name)).toBeVisible();

      const box = await aside.boundingBox();
      expect(box).not.toBeNull();
      const right = box!.x + box!.width;
      for (const target of [
        aside.getByRole("link", { name: "Settings" }),
        aside.getByRole("button", { name: "Sign out" }),
        aside.getByText(user.name),
        aside.getByText(user.email),
      ]) {
        const b = await target.boundingBox();
        expect(b!.x + b!.width).toBeLessThanOrEqual(right);
      }
      // nothing inside is wider than the sidebar, so nothing is being cut off
      const overflow = await aside.evaluate((el) => el.scrollWidth - el.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }

  await page.setViewportSize({ width: 1280, height: 800 });
  for (const start of ["/app/data", "/login", "/"]) {
    await test.step(`the logo on ${start} leads to the dashboard`, async () => {
      await page.goto(start);
      // the link's label changes once the page knows the user is signed in
      const logo = page.getByRole("link", { name: "Sageboard dashboard" }).first();
      await expect(logo).toBeVisible();
      await logo.click();
      await expect(page).toHaveURL(/\/app\/dashboard$/);
      await expect(page.locator("aside").getByText(user.name)).toBeVisible();
    });
  }

  // still signed in after a reload: the session was not touched
  await page.reload();
  await expect(page).toHaveURL(/\/app\/dashboard$/);
  await expect(page.locator("aside").getByText(user.name)).toBeVisible();

  // The browser still holds a refresh cookie but the access cookie has expired (as after 15
  // minutes). That is not "signed in" for a logo, and checking must not rotate the session.
  await page.context().clearCookies({ name: "sb_session" });
  const refreshBefore = (await page.context().cookies()).find((c) => c.name === "sb_refresh");
  expect(refreshBefore).toBeDefined();
  const refreshCalls: string[] = [];
  page.on("request", (r) => r.url().includes("/auth/refresh") && refreshCalls.push(r.url()));
  const me = page.waitForResponse((r) => r.url().endsWith("/auth/me"));
  await page.goto("/login");
  expect((await me).status()).toBe(401);
  const logo = page.getByRole("link", { name: "Sageboard home" }).last();
  await expect(logo).toHaveAttribute("href", "/");
  await logo.click();
  await expect(page).toHaveURL(/\/$/);
  expect(refreshCalls).toEqual([]);
  const refreshAfter = (await page.context().cookies()).find((c) => c.name === "sb_refresh");
  expect(refreshAfter?.value).toBe(refreshBefore!.value);
});
