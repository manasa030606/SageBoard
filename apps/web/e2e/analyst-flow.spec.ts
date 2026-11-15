import { type Page } from "@playwright/test";

import { expect, test } from "./fixtures";

// Questions from the evaluation dataset (apps/api/evals/cases.py): the test backend only
// knows these.
const ANSWERABLE = "What is the total revenue?"; // A01
const UNANSWERABLE = "What is our profit margin by product category?"; // I01

const stamp = Date.now();
const user = {
  name: "E2E Analyst",
  email: `e2e-${stamp}@example.test`,
  password: "correct horse battery staple 9",
};

async function ask(page: Page, question: string) {
  await page.locator("#analyst-question").fill(question);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
}

test.describe.configure({ mode: "serial" });

test("sign up, load the sample dataset and ask a question", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Full name").fill(user.name);
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app/);

  await page.goto("/app/data");
  // Wait for the request to finish before leaving the page: navigating away would abort it.
  const provisioned = page.waitForResponse(
    (r) => r.url().endsWith("/datasets/demo") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Load sample dataset" }).first().click();
  const response = await provisioned;
  expect(
    response.ok(),
    `POST ${response.url()} -> ${response.status()} ${await response.text()}`,
  ).toBe(true);
  const body = (await response.json()) as { dataset: { name: string; status: string } };
  expect(body.dataset.status).toBe("ready");
  await expect(page.getByText(body.dataset.name).first()).toBeVisible();

  await page.goto("/app/analyst");
  await expect(page.locator("#analyst-question")).toBeVisible();
  await ask(page, ANSWERABLE);
  await expect(page.getByRole("region", { name: "What the data shows" })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByRole("region", { name: "Queries and results" })).toBeVisible();
});

test("saving an answer as a report works, with no network error", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/analyst");
  await ask(page, ANSWERABLE);
  await expect(page.getByRole("region", { name: "What the data shows" })).toBeVisible({
    timeout: 60_000,
  });

  const save = page.waitForResponse(
    (r) => r.url().includes("/reports") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save as report" }).click();
  const response = await save;
  expect(response.status()).toBe(201);

  await expect(page.getByText("Saved as report")).toBeVisible();
  await expect(page.getByText(/Could not reach the Sageboard API/)).toHaveCount(0);
});

test("the saved report is listed, survives a reload and downloads as a PDF", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/reports");
  const link = page.getByRole("link", { name: /revenue/i }).first();
  await expect(link).toBeVisible();
  await link.click();
  await expect(page).toHaveURL(/\/app\/reports\/.+/);

  await page.reload();
  await expect(page.getByRole("button", { name: "Download PDF" })).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download PDF" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  const path = await download.path();
  const { readFileSync } = await import("node:fs");
  const bytes = readFileSync(path);
  expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
  expect(bytes.length).toBeGreaterThan(2_000);
});

test("a question about data that does not exist is refused, not answered", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/analyst");
  await ask(page, UNANSWERABLE);
  await expect(
    page.getByText(/no cost or margin data|can.t answer|not available/i).first(),
  ).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByRole("region", { name: "What the data shows" })).toHaveCount(0);
});

test("history lists the earlier questions", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/history");
  await expect(page.getByText(ANSWERABLE).first()).toBeVisible();
});

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app/);
}
