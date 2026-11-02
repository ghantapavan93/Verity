import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

const LIABILITY = "What is the limitation of liability?";
const MFN = "Is there a most favoured nation clause?";
const inspect = (page: Page) => page.getByRole("button", { name: "Inspect evidence" }).first();

async function sample(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  await expect(page.getByPlaceholder("Ask a question about this contract")).toBeVisible();
}

async function ask(page: Page, question: string) {
  const input = page.getByPlaceholder("Ask a question about this contract");
  await input.fill(question);
  const created = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/api/runs"));
  await input.press("Enter");
  const id = ((await (await created).json()) as { id: string }).id;
  await expect(page).toHaveURL(new RegExp(`[?&]run=${id}(&|$)`));
  await expect(inspect(page)).toBeVisible();
  return id;
}

async function capture(page: Page, info: TestInfo, name: string) {
  // Capture the settled surface, not a frame halfway through its entrance transition.
  await expect(page.locator("main")).toHaveCSS("opacity", "1");
  await expect
    .poll(() => page.locator('main [style*="opacity"]').evaluateAll((nodes) => nodes.every((node) => getComputedStyle(node).opacity === "1")))
    .toBe(true);
  const imagePath = info.outputPath(`${name}.png`);
  await page.screenshot({ path: imagePath });
  await info.attach(name, { path: imagePath, contentType: "image/png" });
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
}

test("genuinely empty ledgers remain distinct and actionable", async ({ page, browserName }, info) => {
  test.skip(browserName !== "chromium", "The first project checks the fresh store before later projects populate it.");
  for (const [view, message] of [
    ["documents", /No documents yet/],
    ["findings", /No findings yet/],
    ["runs", /No runs yet/],
  ] as const) {
    await page.goto(`/?view=${view}`);
    await expect(page.getByText(message)).toBeVisible();
    await capture(page, info, `empty-${view}`);
  }
});

test("failed ledger reads recover without claiming empty results", async ({ page }, info) => {
  for (const view of ["documents", "findings", "runs"]) {
    let unavailable = true;
    await page.route(`**/api/${view}`, (route) => (unavailable ? route.abort() : route.continue()));
    await page.goto(`/?view=${view}`);
    await expect(page.getByRole("alert").filter({ hasText: "Could not read" })).toBeVisible();
    await expect(page.getByText(/No (documents|findings|runs) yet/)).toHaveCount(0);
    await capture(page, info, `failed-${view}`);
    unavailable = false;
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Could not read" })).toHaveCount(0);
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
    await page.unroute(`**/api/${view}`);
  }
});

test("record navigation restores reading position and the initiating keyboard control", async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 600 });
  await sample(page);
  const id = await ask(page, LIABILITY);
  await page.getByRole("button", { name: "Runs", exact: true }).click();
  const pane = page.getByRole("region", { name: "Execution records" });
  const row = page.locator(`[data-run-id="${id}"]`);
  for (let cycle = 0; cycle < 6; cycle += 1) {
    await pane.evaluate((el) => {
      el.scrollTop = 120;
    });
    await row.scrollIntoViewIfNeeded();
    const position = await pane.evaluate((el) => el.scrollTop);
    expect(position).toBeGreaterThan(0);
    await row.focus();
    await row.press("Enter");
    const heading = page.getByRole("heading", { level: 1, name: LIABILITY });
    await expect(heading).toBeFocused();
    expect(await pane.evaluate((el) => el.scrollTop)).toBe(0);
    await page.getByRole("heading", { name: /^Raw model output/ }).scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: "All runs" }).click();
    await expect(row).toBeFocused();
    expect(Math.abs((await pane.evaluate((el) => el.scrollTop)) - position)).toBeLessThanOrEqual(1);
  }
  await capture(page, info, "record-list-after-six-cycles");
});

test("the newest record selection survives a late earlier response", async ({ page }) => {
  await sample(page);
  const earlier = await ask(page, LIABILITY);
  const latest = await ask(page, MFN);
  await page.getByRole("button", { name: "Runs", exact: true }).click();
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/runs/${earlier}/detail`, async (route) => {
    await held;
    await route.continue();
  });
  const earlierResponse = page.waitForResponse((response) => response.url().endsWith(`/api/runs/${earlier}/detail`));
  try {
    await page.locator(`[data-run-id="${earlier}"]`).click();
    await page.locator(`[data-run-id="${latest}"]`).click();
    await expect(page.getByRole("heading", { level: 1, name: MFN })).toBeVisible();
  } finally {
    release();
  }
  await earlierResponse;
  await expect(page.getByRole("heading", { level: 1, name: MFN })).toBeFocused();
  await page.getByRole("button", { name: "All runs" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Every model run/ })).toBeVisible();
});

test("failed review feedback stays with its finding and retry records the decision", async ({ page, context }, info) => {
  await context.addInitScript(() => localStorage.setItem("workbench.reviewer", "Session audit"));
  await sample(page);
  await ask(page, LIABILITY);
  await page.getByRole("button", { name: "Findings", exact: true }).click();
  const row = page
    .locator("li")
    .filter({ has: page.getByText(`Asked: ${LIABILITY}`, { exact: true }) })
    .first();
  const action = row.getByRole("button", { name: /^(Confirm|Clear decision):/ }).first();
  let unavailable = true;
  await page.route("**/api/findings/*/review", (route) => (unavailable ? route.abort() : route.continue()));
  await action.click();
  await expect(row.getByRole("alert")).toBeVisible();
  await expect(action).toBeInViewport();
  await capture(page, info, "failed-decision-in-place");
  unavailable = false;
  const recorded = page.waitForResponse((response) => response.url().includes("/review") && response.request().method() === "POST");
  await action.click();
  expect((await recorded).ok()).toBe(true);
  await expect(row.getByRole("alert")).toHaveCount(0);
});

test("a disconnected run shows recovery instead of live progress and reconnects to the same run", async ({ page }, info) => {
  await sample(page);
  await page.route("**/api/runs/*/events", (route) => route.abort());
  await page.route("**/api/runs/*/detail", (route) => route.abort());
  const question = `${LIABILITY} [[zzdelay:a${crypto.randomUUID().replace(/[^a-z]/g, "")}]]`;
  let starts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/runs")) starts += 1;
  });
  const input = page.getByPlaceholder("Ask a question about this contract");
  await input.fill(question);
  await input.press("Enter");
  await expect(page.getByRole("heading", { name: "Connection interrupted" })).toBeVisible({ timeout: 30_000 });
  const runId = new URL(page.url()).searchParams.get("run");
  expect(runId).toBeTruthy();
  await expect(page.getByRole("list", { name: "Run progress" })).toHaveCount(0);
  await capture(page, info, "interrupted-run");
  await page.unroute("**/api/runs/*/events");
  await page.unroute("**/api/runs/*/detail");
  await page.getByRole("button", { name: "Reconnect", exact: true }).click();
  await expect(inspect(page)).toBeVisible();
  expect(new URL(page.url()).searchParams.get("run")).toBe(runId);
  expect(starts).toBe(1);
});

test("a failed question request preserves its text and offers an explicit retry", async ({ page }, info) => {
  await sample(page);
  let unavailable = true;
  await page.route("**/api/runs", (route) => (route.request().method() === "POST" && unavailable ? route.abort() : route.continue()));
  const input = page.getByPlaceholder("Ask a question about this contract");
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  await input.fill(LIABILITY);
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeEnabled();
  await input.press("Enter");
  await expect(page.getByRole("heading", { name: "Question request failed" })).toBeVisible();
  await expect(input).toHaveValue(LIABILITY);
  await capture(page, info, "failed-question-request");
  unavailable = false;
  await page.getByRole("button", { name: "Try question again" }).click();
  await expect(inspect(page)).toBeVisible();
});
