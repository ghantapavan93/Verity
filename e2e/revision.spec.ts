// A contractual change and its consequence, through the real stack: the sample's prepared revision (one change, said
// so: the cure period in §5.3(a), 30 days → 10 days) is read, recorded as the next version and diffed, then the same
// question with the same guidance is asked of it. Both answers are recorded runs, replayed byte for byte here; the
// status of each is code's or the model's as the record says, and the panel says which.

import { expect, test } from "@playwright/test";

const GUIDANCE = "A party must be given at least 30 days to cure a material breach before the other party may terminate.";
const QUESTION = "How long does a party have to cure a material breach before the other party may terminate?";

test("the prepared revision is asked the same question, and the decision change is set side by side, said by whom", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  await expect(page.locator("section[data-section]").first()).toBeVisible();
  await page.getByRole("button", { name: "Add guidance" }).click();
  await page.getByPlaceholder("Paste a playbook rule, a lawyer's note or a review instruction").fill(GUIDANCE);
  await page.getByRole("button", { name: "Use", exact: true }).click();
  // The popover closes once the guidance is saved and in scope. Asked before that, the question went without it, and the
  // recording had no answer for a question without guidance (a release gate, 2026-10-14: 33 ms between the two posts).
  await expect(page.getByPlaceholder("Paste a playbook rule, a lawyer's note or a review instruction")).toBeHidden();
  await page.getByPlaceholder(/Ask a question about this contract/i).fill(QUESTION);
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Found in the document text at /).first()).toBeVisible();

  const panel = page.getByTestId("revision-check");
  await expect(panel.getByText(/The prepared revision makes one change by Verity/)).toBeVisible();
  await panel.getByRole("button", { name: "Use a prepared revision" }).click();
  await panel.getByRole("button", { name: "Record as the next version" }).click();
  await expect(panel.getByText(/1 finding is stale/)).toBeVisible();
  await expect(panel.getByText(/changed: §5\.3\(a\) Termination/)).toBeVisible();

  await panel.getByRole("button", { name: "Ask the same question of the revision" }).click();
  await expect(panel.getByText("The same question, both versions")).toBeVisible();
  await expect(panel).toContainText(/Within guidance \(model's view\)\s*→\s*became\s*Needs review, set by code/);
  await expect(panel).toContainText("Code set this status: the contract provides 10 calendar days; the guidance requires at least 30 calendar days");
  await expect(panel).not.toContainText("sec_"); // a model's handle is never shown as a citation
});
