// The flows a reviewer walks through, against the real API and the production build, with the
// model's recorded answers replayed (see playwright.config.ts). Every assertion is about what the
// interface shows of a record the API made; none of them decides anything the API did not.

import { expect, test, type Page } from "@playwright/test";

const LIABILITY = "What is the limitation of liability?";
const MFN = "Is there a most favoured nation clause?";

/** Whitespace and typographic quotes, the only differences the verifier's normalized tier forgives. */
function comparable(text: string): string {
  return text.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/\s+/g, " ").trim();
}

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

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  (page as Page & { collectedErrors?: string[] }).collectedErrors = errors;
});

test.afterEach(async ({ page }) => {
  expect((page as Page & { collectedErrors?: string[] }).collectedErrors ?? []).toEqual([]);
});

test("the landing offers the sample and the three ways in", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "try a sample agreement" })).toBeVisible();
  for (const way of ["Review a contract", "Compare against guidance", "Ask about a clause"]) {
    await expect(page.getByRole("button", { name: way })).toBeVisible();
  }
});

test("the sample opens as numbered sections and the URL carries the document", async ({ page }) => {
  await openSample(page);
  expect(await page.locator("section[data-section]").count()).toBeGreaterThan(50);
  await expect(page.getByText(/\d+ sections/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
});

test("a question ends in a finding whose citation opens the document's own text", async ({ page }) => {
  await openSample(page);
  await ask(page, LIABILITY);

  const evidenceHead = page.getByText(/Evidence · \d+ verified passage/);
  await expect(evidenceHead).toBeVisible();
  await expect(page).toHaveURL(/[?&]run=/);

  await page.getByTitle("Show in the document").first().click();
  const mark = page.locator("section[data-section] mark").first();
  await expect(mark).toBeVisible();

  await page.getByRole("button", { name: "Inspect evidence" }).first().click();
  const drawer = page.locator('[aria-label="Evidence"]');
  await expect(drawer).toBeVisible();
  const tag = drawer.getByText(/Verified verbatim in the document text · /).first();
  await expect(tag).toBeVisible();
  const quoted = (await drawer.locator("blockquote").first().innerText()).replace(/^[“"]|[”"]$/g, "");
  const highlighted = await mark.innerText();
  if ((await tag.innerText()).endsWith("· exact")) {
    expect(highlighted).toBe(quoted);
  } else {
    expect(comparable(highlighted)).toBe(comparable(quoted));
  }
  await page.getByRole("button", { name: "Close evidence" }).click();
});

test("the most favoured nation question is not answered with an invented clause", async ({ page }) => {
  await openSample(page);
  await ask(page, MFN);
  await expect(page.getByText(/Unresolved|Closest provisions read/).first()).toBeVisible();
  const withheld = page.getByText("What the model proposed · withheld by the verifier");
  const nothing = page.getByText("No supporting passage found");
  const coverage = page.getByText(/Closest provisions read · \d+ · none states the point/);
  await expect(withheld.or(nothing).or(coverage).first()).toBeVisible();
  await expect(page.getByText(/Evidence · \d+ verified passage/)).toHaveCount(0);
});

test("a reload restores the run from the URL", async ({ page }) => {
  await openSample(page);
  await ask(page, LIABILITY);
  await expect(page.getByText(/Evidence · \d+ verified passage/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Evidence · \d+ verified passage/)).toBeVisible();
  await expect(page.locator("section[data-section]").first()).toBeVisible();
});

test("Findings and Runs show the record, and the evidence pack downloads", async ({ page }) => {
  await openSample(page);
  await ask(page, LIABILITY);
  await expect(page.getByText(/Evidence · \d+ verified passage/)).toBeVisible();

  await page.getByRole("button", { name: "Findings" }).click();
  await expect(page.getByText("Finding", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Runs" }).click();
  await expect(page.getByText("Every model run, as recorded")).toBeVisible();
  const pack = page.getByRole("link", { name: "Download evidence pack" });
  if (!(await pack.isVisible().catch(() => false))) {
    await page.getByText(LIABILITY).first().click();
  }
  await expect(pack).toBeVisible();
  await expect(page.getByRole("heading", { name: "Stages" })).toBeVisible();
  for (const stage of ["Reading contract", "Finding relevant language", "Checking", "Verifying citations"]) {
    await expect(page.getByText(stage).first()).toBeVisible();
  }
  const href = await pack.getAttribute("href");
  expect(href).toBeTruthy();
  const response = await page.request.get(href as string);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"] ?? "").toContain("zip");
});

test("the review memo is written from the stored findings, with no second model call", async ({ page }) => {
  await openSample(page);
  await ask(page, LIABILITY);
  await expect(page.getByText(/Evidence · \d+ verified passage/)).toBeVisible();
  await page.getByRole("button", { name: /memo/i }).click();
  await expect(page.getByText("Review memo ready")).toBeVisible();
  const docx = page.getByRole("link", { name: "Download .docx" });
  const href = await docx.getAttribute("href");
  expect(href).toBeTruthy();
  const response = await page.request.get(href as string);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"] ?? "").toContain("wordprocessingml");
});
