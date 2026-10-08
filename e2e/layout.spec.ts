// Nothing the record says is cut off or pushed out of its box at the widths the workspace supports. Release review,
// 2026-10-08: at 768 px the status chip stood 30 px past its card and "every quoted passage found in the document text"
// was clipped by the panel. Boxes are compared, not scroll widths: an ellipsis already overflows by design.

import { expect, test, type Page } from "@playwright/test";

const LIABILITY = "What is the limitation of liability?";

async function openSample(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "try a sample agreement" }).click();
  await expect(page).toHaveURL(/[?&]document=/);
  await expect(page.locator("section[data-section]").first()).toBeVisible();
}

/** Every visible element inside a box whose class ends in one of `boxes`, that reaches past that box's right edge. */
async function outside(page: Page, boxes: string[]): Promise<string[]> {
  return page.evaluate((suffixes) => {
    const found: string[] = [];
    const isBox = (el: Element) => [...el.classList].some((c) => suffixes.some((s) => c.endsWith(`__${s}`)));
    for (const box of [...document.querySelectorAll("*")].filter(isBox)) {
      const edge = box.getBoundingClientRect().right;
      for (const el of box.querySelectorAll("*")) {
        const r = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        if (r.width === 0 || r.height === 0 || style.visibility === "hidden" || style.position === "absolute") continue;
        if (r.right > edge + 1) found.push(`${(el.textContent ?? "").trim().slice(0, 40)} ends at ${Math.round(r.right)}, its box at ${Math.round(edge)}`);
      }
    }
    return found;
  }, boxes);
}

test("an answer, its record and the drawer stay inside their boxes from 768 px up", async ({ page }) => {
  await openSample(page);
  const composer = page.getByPlaceholder("Ask a question about this contract");
  await composer.fill(LIABILITY);
  await composer.press("Enter");
  await expect(page.getByText(/Evidence · \d+ passages? found in the document text/).first()).toBeVisible();
  for (const width of [768, 900, 1024, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(300);
    expect(await outside(page, ["result", "assistantBody", "runMeta"]), `answer at ${width}`).toEqual([]);
  }
  await page.setViewportSize({ width: 768, height: 900 });
  await page.getByRole("button", { name: "Inspect evidence" }).first().click();
  await expect(page.locator('[aria-label="Evidence"]')).toBeVisible();
  await page.waitForTimeout(800); // the drawer slides in; boxes are measured where it comes to rest
  expect(await outside(page, ["drawer"]), "drawer at 768").toEqual([]); // the drawer clips; its sections do not
});

test("control: the documents, findings and runs views stay inside their panes at 768 px", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 });
  for (const view of ["documents", "findings", "runs"]) {
    await page.goto(`/?view=${view}`);
    await expect(page.locator("h1").first()).toBeVisible();
    await expect(page.getByText(/Could not read/)).toHaveCount(0); // the view read its records; an error page proves nothing
    await expect(page.locator("li").first()).toBeVisible();
    expect(await outside(page, ["inner"]), view).toEqual([]);
  }
});
