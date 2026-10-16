// Defects found by the final adversarial review (2026-10-13), each reproduced in a real browser against the real API with
// the model's recorded answers replayed: every test states what the reader should see, and failed before its fix.

import { expect, test, type Page } from "@playwright/test";

const LIABILITY = "What is the limitation of liability?";
const MFN = "Is there a most favoured nation clause?";
const FOUND = /Found in the document text at /;

async function openSample(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  await expect(page).toHaveURL(/[?&]document=/);
  await expect(page.locator("section[data-section]").first()).toBeVisible();
}

async function ask(page: Page, question: string): Promise<void> {
  const composer = page.getByPlaceholder("Ask a question about this contract");
  await composer.fill(question);
  await composer.press("Enter");
}

const param = (page: Page, name: string) => new URL(page.url()).searchParams.get(name);

test("a decision made on Findings is the one the evidence drawer shows when Review is opened again", async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("workbench.reviewer", "Playwright"));
  await openSample(page);
  await ask(page, LIABILITY);
  await expect(page.getByText(FOUND).first()).toBeVisible();
  const runId = param(page, "run");
  await page.getByRole("button", { name: "Inspect evidence" }).first().click();
  const drawer = page.locator('[aria-label="Evidence"]');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("Limitation of Liability")).toBeVisible();
  const shownId = param(page, "finding");

  // On Findings, change the decision on every finding of this run (Confirm, or Undo a decision an earlier flow made).
  await page.getByRole("button", { name: "Findings" }).click();
  const decisions = page.getByRole("button", { name: /^(Confirm|Undo): Limitation of Liability$/ });
  await expect(decisions.first()).toBeVisible();
  const count = await decisions.count();
  for (let i = 0; i < count; i++) {
    const posted = page.waitForResponse((r) => r.url().includes("/api/findings/") && r.request().method() === "POST");
    await page
      .getByRole("button", { name: /^(Confirm|Undo): Limitation of Liability$/ })
      .nth(i)
      .click();
    await posted;
  }

  await page.getByRole("button", { name: "Review", exact: true }).click();
  const record = await (await page.request.get(`http://127.0.0.1:8001/api/runs/${runId}`)).json();
  const finding = [...record.findings, ...record.withheld].find((f: { id: string }) => f.id === shownId);
  await expect(drawer).toBeVisible();
  if (finding.review) await expect(drawer.getByText("No one has decided on this finding yet.")).toHaveCount(0);
  else await expect(drawer.getByText("No one has decided on this finding yet.")).toBeVisible();
});

test("a memo that arrives after the reader went back to an earlier answer is not shown under it", async ({ page }) => {
  await openSample(page);
  await ask(page, LIABILITY);
  await expect(page.getByText(FOUND).first()).toBeVisible();
  const first = param(page, "run");
  await ask(page, MFN);
  await expect(page).not.toHaveURL(new RegExp(`[?&]run=${first}(&|$)`));
  await expect(page.getByRole("button", { name: "Generate review memo" })).toBeVisible();
  await page.route("**/api/memos", async (route) => {
    await new Promise((r) => setTimeout(r, 3000));
    await route.continue();
  });
  await page.getByRole("button", { name: "Generate review memo" }).click();
  // While it is being written, the reader goes back to the first answer from Runs.
  await page.getByRole("button", { name: "Runs" }).click();
  await page.getByRole("button").filter({ hasText: LIABILITY }).first().click();
  await page.getByRole("button", { name: "Open in workspace" }).click();
  await expect(page).toHaveURL(new RegExp(`[?&]run=${first}(&|$)`));
  await page.waitForTimeout(4000); // the memo for the later answer has arrived by now
  await expect(page.getByRole("button", { name: "Inspect evidence" }).first()).toBeVisible();
  await expect(page.getByText(/Review memo (ready|predates a later review)/)).toHaveCount(0);
});

test("a question whose run arrives after the reader opened another contract stays with its own contract", async ({ page }) => {
  // Contract B, then the sample (A); the question is asked on A, and B is opened from Documents while it is created.
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles({
    name: "contract-b.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("SUPPLY AGREEMENT\n\n1. Term. This Agreement lasts three years.\n\n2. Notice. Either party may end it on sixty days' notice.\n"),
  });
  await expect(page).toHaveURL(/[?&]document=/);
  const b = param(page, "document");
  await page.getByRole("button", { name: "Verity: the first screen" }).click();
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  await expect(page).not.toHaveURL(new RegExp(`[?&]document=${b}(&|$)`));
  await expect(page.locator("section[data-section]").first()).toBeVisible();

  await page.route("**/api/runs", async (route) => {
    if (route.request().method() === "POST") await new Promise((r) => setTimeout(r, 3000));
    await route.continue();
  });
  await ask(page, LIABILITY);
  await page.getByRole("button", { name: "Documents" }).click();
  await page.getByRole("button").filter({ hasText: "contract-b" }).first().click();
  await expect(page).toHaveURL(new RegExp(`[?&]document=${b}(&|$)`));
  await page.waitForTimeout(5000); // the run made for the sample has been answered by now
  await expect(page).toHaveURL(new RegExp(`[?&]document=${b}(&|$)`));
  expect(param(page, "run")).toBeNull();
  // Nothing of the sample's run on screen (the question itself is also one of the suggestion chips, so it is not looked for).
  await expect(page.getByRole("list", { name: "Run progress" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Inspect evidence" })).toHaveCount(0);
  await expect(page.getByText(FOUND)).toHaveCount(0);
});

test("a health check that fails once does not hide where the model runs for the rest of the visit", async ({ page }) => {
  // The door (AccessGate) and the workbench each ask once on arrival; both go unanswered, as on a dropped connection.
  let asked = 0;
  await page.route("**/api/health", async (route) => {
    asked++;
    if (asked <= 2) await route.abort();
    else await route.continue();
  });
  await page.goto("/");
  await expect.poll(() => asked).toBeGreaterThan(1);
  await page.waitForTimeout(500);
  // Leave the first screen and come back: health is asked again, and answers.
  await page.getByRole("button", { name: "Documents" }).click();
  await page.getByRole("button", { name: "Verity: the first screen" }).click();
  await expect.poll(() => asked).toBeGreaterThan(2);
  await expect(page.getByText(/, run on /)).toBeVisible();
});

// The drawer's decision form carried to another finding (also found 2026-10-13) needs a run with two findings, which
// no recorded answer has: it is reproduced in assistant/EvidenceDrawer.test.tsx.

// Blind contract stress test (2026-10-16): a file refused while a contract was open sent the reader to the first
// screen's top, the contract gone and the refusal below the fold (896 px down at 900, 968 at 812).
async function refuseWhileOpen(page: Page, width: number, height: number): Promise<void> {
  await page.setViewportSize({ width, height });
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  await expect(page).toHaveURL(/[?&]document=/);
  // A phone opens a new contract on its answer, so the composer, shown at every width, says it is open.
  await expect(page.getByPlaceholder("Ask a question about this contract")).toBeVisible();
  const opened = param(page, "document");
  await page.getByRole("button", { name: "Documents" }).click();
  const title = page.getByRole("heading", { name: /Contracts in this workbench/ });
  await expect(title).toBeVisible();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Add a contract" }).first().click();
  await (await chooser).setFiles({ name: "not-a-pdf.pdf", mimeType: "application/pdf", buffer: Buffer.from("VERITY: this file is not a PDF.") });
  const refusal = page.getByRole("alert").filter({ hasText: "not-a-pdf.pdf was not added: the file is not a readable PDF" });
  await expect(refusal).toBeVisible();
  await expect(refusal).toBeInViewport();
  await expect(title).toBeVisible();
  expect(param(page, "document")).toBe(opened);
}

test("a file refused while a contract is open leaves the reader where they added it, the refusal on screen", async ({ page }) => {
  await refuseWhileOpen(page, 1440, 900);
});

test("a file refused while a contract is open, on a phone, leaves the reader where they added it, the refusal on screen", async ({ page }) => {
  await refuseWhileOpen(page, 375, 812);
});
