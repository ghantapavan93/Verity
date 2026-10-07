// The story page in a real browser, against the production build: the record's API answer is the committed fixture
// (three arrivals of the contract-state record), so the flow runs where the experiment's record is not checked out.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import record from "../src/components/story/__fixtures__/contract-state.json";

async function serveRecord(page: Page, status = 200): Promise<string[]> {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.route("**/api/engineering/contract-state", (route) =>
    status === 200 ? route.fulfill({ json: record }) : route.fulfill({ status, json: { detail: "the record is unavailable" } }),
  );
  return errors;
}

async function serious(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.length} node(s)`);
}

async function storyHolds(page: Page, viewport: { width: number; height: number }): Promise<void> {
  await page.setViewportSize(viewport);
  const errors = await serveRecord(page);
  await page.goto("/state");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("One contract changes.");
  await expect(page.getByText("0 observed changes outside the envelope.")).toBeVisible();
  await expect(page.getByRole("article", { name: "Derivation certificate" })).toContainText("Exactly 1 visible text satisfies this reference.");
  await expect(page.getByRole("heading", { name: "We preregistered 0.85 recall. The system reached 0.836, so this run failed." })).toBeVisible();
  for (const details of await page.locator("details").all()) await details.evaluate((el) => ((el as HTMLDetailsElement).open = true));
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  expect(await serious(page)).toEqual([]);
  expect(errors).toEqual([]);
}

test("state page on desktop: the story from the record, no overflow, no console errors, axe clean", async ({ page }) => {
  await storyHolds(page, { width: 1280, height: 800 });
});

test("state page on a phone: the story from the record, no overflow, no console errors, axe clean", async ({ page }) => {
  await storyHolds(page, { width: 390, height: 844 });
});

test("state page: section links and the arrival picker work from the keyboard, and the choice is in the URL", async ({ page }) => {
  await serveRecord(page);
  await page.goto("/state");
  await expect(page.locator("#arrival-pick")).toBeVisible();
  await page.getByRole("link", { name: "What didn't pass" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#audit$/);
  await page.locator("#arrival-pick").focus();
  await page.keyboard.press("ArrowDown");
  await expect(page).toHaveURL(/[?&]arrival=2/);
  await expect(page.getByText("This arrival established no relationship.")).toBeVisible();
  await page.reload();
  await expect(page.locator("#arrival-pick")).toHaveValue("1");
});

test("state page: an unavailable record is said, with a way to try again, and nothing is invented", async ({ page }) => {
  await serveRecord(page, 503);
  await page.goto("/state");
  // (Next's route announcer is a second, empty alert region)
  await expect(page.getByRole("alert").filter({ hasText: "The recorded evidence did not load." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.getByText("57,121")).toHaveCount(0);
});
