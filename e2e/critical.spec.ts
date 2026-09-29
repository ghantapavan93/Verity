// The three flows the validation brief names that the other specs did not cover: a review against
// guidance, a malformed upload from the landing, and a refresh while a run is in flight.

import { expect, test, type Page } from "@playwright/test";

const LIABILITY = "What is the limitation of liability?";
const GUIDANCE = "Our standard: the liability cap must be at least twelve months of fees; anything lower needs review.";

async function openSample(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  await expect(page).toHaveURL(/[?&]document=/);
  await expect(page.locator("section[data-section]").first()).toBeVisible();
}

test("a review against guidance runs to a finding with a status and the guidance in the drawer", async ({ page }) => {
  await openSample(page);
  await page.getByRole("button", { name: "Add guidance" }).click();
  await page.getByPlaceholder("Paste a playbook rule, a lawyer's note or a review instruction").fill(GUIDANCE);
  await page.getByRole("button", { name: "Use", exact: true }).click();
  await page.getByRole("button", { name: "Review against instructions" }).click();
  await expect(page.getByText(/Evidence · \d+ verified passage|Closest provisions read/).first()).toBeVisible();
  await page.getByRole("button", { name: "Inspect evidence" }).first().click();
  const drawer = page.locator('[aria-label="Evidence"]');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("heading", { name: "Guidance" })).toBeVisible();
  await expect(drawer.getByText("Result", { exact: true }).first()).toBeVisible();
});

test("a malformed upload is refused with the reason, and nothing is opened", async ({ page }) => {
  await page.goto("/");
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: "broken.docx", mimeType: "application/octet-stream", buffer: Buffer.from("PK\u0003\u0004 not a package") });
  await expect(page.getByText(/not a readable \.docx package/)).toBeVisible();
  await expect(page).not.toHaveURL(/[?&]document=/);
});

test("a refresh while a run is in flight loses nothing: the run finishes and the URL brings it back", async ({ page }) => {
  await openSample(page);
  const composer = page.getByPlaceholder("Ask anything about this contract…");
  await composer.fill(LIABILITY);
  const started = page.waitForResponse((r) => r.url().includes("/api/runs") && r.request().method() === "POST");
  await composer.press("Enter");
  await started;
  await page.waitForURL(/[?&]run=/);
  await page.reload();
  await expect(page.getByText(/Evidence · \d+ verified passage/)).toBeVisible();
  await expect(page.locator("section[data-section]").first()).toBeVisible();
});
