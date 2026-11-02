import { expect, test } from "@playwright/test";

test("a delayed contracts read announces loading and then shows its real records", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/documents", async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto("/?view=documents");
  try {
    await expect(page.getByRole("status")).toHaveText("Loading contracts…");
    await expect(page.getByLabel("Contracts, loading")).toBeVisible();
  } finally {
    release();
  }
  await expect(page.getByLabel("Contracts, loading")).toHaveCount(0);
  await expect(page.getByText(/Could not read the contracts/)).toHaveCount(0);
});

test("question fields grow, shrink and reflow without hiding Send", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  const question = page.getByPlaceholder("Ask a question about this contract");
  await expect(question).toBeVisible();
  const height = async () => (await question.boundingBox())!.height;
  const initial = await height();
  await question.fill("What is the limitation of liability? ".repeat(18));
  await expect.poll(height).toBeGreaterThan(initial);
  for (const width of [1440, 768, 375, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByLabel("Send", { exact: true })).toBeInViewport();
    expect(await height()).toBeLessThanOrEqual(160);
    expect(await question.evaluate((el) => el.scrollHeight >= el.clientHeight)).toBe(true);
  }
  await question.fill("");
  await expect.poll(height).toBeLessThan(60);
});

test("inspecting quote context keeps the sheet header and keyboard return reachable", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  const question = page.getByPlaceholder("Ask a question about this contract");
  await question.fill("What is the limitation of liability?");
  await question.press("Enter");
  const inspect = page.getByRole("button", { name: "Inspect evidence" }).first();
  await expect(inspect).toBeVisible();
  for (const width of [1440, 768, 375, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await inspect.click();
    const sheet = page.getByLabel("Evidence", { exact: true });
    const context = sheet.getByText("Text around this quote", { exact: true }).first();
    await context.click();
    await expect(context.locator("..").locator("strong")).toBeVisible();
    await expect(sheet.getByLabel("Close evidence", { exact: true })).toBeInViewport();
    expect(await sheet.locator("..").evaluate((el) => el.scrollTop)).toBe(0);
    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
    await expect(inspect).toBeFocused();
  }
});
