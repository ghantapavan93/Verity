// What the interface does when things go wrong, and what it promises when they go right, checked
// against the real API. Faults come from markers the replay provider honours ([[fault:provider]],
// [[fault:garbage]]); nothing else on the path is mocked.

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const LIABILITY = "What is the limitation of liability?";
const API = "http://127.0.0.1:8001";

async function openSample(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  await expect(page).toHaveURL(/[?&]document=/);
  await expect(page.locator("section[data-section]").first()).toBeVisible();
}

async function ask(page: Page, question: string): Promise<void> {
  const composer = page.getByPlaceholder("Ask anything about this contract…");
  await composer.fill(question);
  await composer.press("Enter");
}

const finding = (page: Page) => page.getByText(/Evidence · \d+ verified passage/);

/** Letters only: the question is also the retrieval query, and a digit would be a term the contract has. */
function nonce(): string {
  return Array.from({ length: 8 }, () => "abcdefghijklmnopqrstuvwxyz"[Math.floor(Math.random() * 26)]).join("");
}

test.describe("failure states", () => {
  // The fault markers are an affordance of the replay provider; a recording run asks the real model.
  test.skip(process.env.E2E_PROVIDER === "record", "faults are injected by the replay provider only");

  test("a provider outage ends as a failed run with a retry, never a verdict", async ({ page }) => {
    await openSample(page);
    await ask(page, "What is the cap on liability? [[fault:provider]]");
    await expect(page.locator("span", { hasText: "The model could not be reached" })).toBeVisible();
    await expect(page.getByText("Failed", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
    await expect(finding(page)).toHaveCount(0);
  });

  test("output that is not the schema ends as a failed run after the corrected retry", async ({ page }) => {
    await openSample(page);
    await ask(page, "What is the cap on liability? [[fault:garbage]]");
    await expect(page.getByText(/did not return a valid result/)).toBeVisible();
    await expect(page.getByText("Failed", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
    await expect(finding(page)).toHaveCount(0);
  });

  test("a dropped event stream still ends in the finished run through polling", async ({ page }) => {
    let streams = 0;
    await page.route("**/api/runs/*/events", (route) => {
      streams += 1;
      void route.abort();
    });
    await openSample(page);
    // A new run held in flight by the replay provider, so a stream is opened (and dropped) rather than a finished run reused.
    await ask(page, `${LIABILITY} [[zzdelay:${nonce()}]]`);
    await expect(finding(page)).toBeVisible({ timeout: 30_000 });
    expect(streams).toBeGreaterThan(0);
  });
});

test.describe("promises on the wire", () => {
  test("asking the same question twice returns the same run, and the document travels compressed", async ({ page }) => {
    await openSample(page);
    const first = page.waitForResponse((r) => r.url().includes("/api/runs") && r.request().method() === "POST");
    await ask(page, LIABILITY);
    const created = await first;
    expect([200, 202]).toContain(created.status());
    await expect(finding(page)).toBeVisible();

    const second = page.waitForResponse((r) => r.url().includes("/api/runs") && r.request().method() === "POST");
    await ask(page, LIABILITY);
    const reused = await second;
    expect(reused.status()).toBe(200);
    expect((await reused.json()).reused).toBe(true);

    const document = await page.request.get(`${API}/api/documents/${new URL(page.url()).searchParams.get("document")}`, {
      headers: { "Accept-Encoding": "gzip" },
    });
    expect(document.headers()["content-encoding"]).toBe("gzip");
  });

  test("the memo names the run it was written from", async ({ page }) => {
    await openSample(page);
    await ask(page, LIABILITY);
    await expect(finding(page)).toBeVisible();
    const runId = new URL(page.url()).searchParams.get("run");
    expect(runId).toBeTruthy();
    await page.getByRole("button", { name: /memo/i }).click();
    await expect(page.getByText("Review memo ready")).toBeVisible();
    const html = page.getByRole("link", { name: /Open|HTML|memo/i }).first();
    const href = await html.getAttribute("href");
    const body = await (await page.request.get(href as string)).text();
    expect(body).toContain(runId as string);
  });
});

test.describe("state that must survive", () => {
  test("a confirmed finding stays confirmed after a reload", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("workbench.reviewer", "Playwright"));
    await openSample(page);
    await ask(page, LIABILITY);
    await expect(finding(page)).toBeVisible();
    await page.getByRole("button", { name: "Findings" }).click();
    // The flows share one data directory across runs and the run is reused by fingerprint, so a previous run may
    // have confirmed this finding already; a review is append-only and undo is a review too.
    await expect(page.getByText(/awaiting review/)).toBeVisible(); // the list has loaded
    const undo = page.getByRole("button", { name: "Undo" }).first();
    if (await undo.isVisible().catch(() => false)) {
      await undo.click();
    }
    const confirm = page.getByRole("button", { name: "Confirm" }).first();
    await confirm.click();
    const name = page.getByPlaceholder("Your name, asked once");
    if (await name.isVisible().catch(() => false)) {
      await name.fill("Playwright");
      await page.getByRole("button", { name: "Confirm" }).first().click();
    }
    await expect(page.getByRole("button", { name: "Undo" }).first()).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: "Findings" }).click();
    await expect(page.getByRole("button", { name: "Undo" }).first()).toBeVisible();
  });

  test("the URL alone restores the run and the document cold", async ({ page }) => {
    await openSample(page);
    await ask(page, LIABILITY);
    await expect(finding(page)).toBeVisible();
    await page.getByTitle("Show in the document").first().click();
    await expect(page.locator("section[data-section] mark").first()).toBeVisible();
    const url = page.url();
    await page.goto("about:blank");
    await page.goto(url);
    await expect(finding(page)).toBeVisible();
    await expect(page.locator("section[data-section]").first()).toBeVisible();
  });
});

test.describe("interaction and accessibility", () => {
  test("Escape closes the evidence drawer", async ({ page }) => {
    await openSample(page);
    await ask(page, LIABILITY);
    await expect(finding(page)).toBeVisible();
    await page.getByRole("button", { name: "Inspect evidence" }).first().click();
    const drawer = page.locator('[aria-label="Evidence"]');
    await expect(drawer).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
  });

  test("a narrow window gets a plain note instead of a cramped split", async ({ page }) => {
    await page.setViewportSize({ width: 600, height: 700 });
    await page.goto("/");
    await page.getByRole("button", { name: "try a sample agreement" }).click();
    await expect(page).toHaveURL(/[?&]document=/);
    await expect(page.getByText(/needs a wider window/)).toBeVisible();
  });

  test("no serious or critical accessibility violations on the landing, the workspace and the open drawer", async ({ page }) => {
    const serious = async (): Promise<string[]> => {
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
      return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.length} node(s)`);
    };
    await page.goto("/");
    expect(await serious()).toEqual([]);
    await openSample(page);
    await ask(page, LIABILITY);
    await expect(finding(page)).toBeVisible();
    expect(await serious()).toEqual([]);
    await page.getByRole("button", { name: "Inspect evidence" }).first().click();
    await expect(page.locator('[aria-label="Evidence"]')).toBeVisible();
    expect(await serious()).toEqual([]);
  });
});
