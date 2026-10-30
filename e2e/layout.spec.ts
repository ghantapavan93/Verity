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
  await expect(page.getByText(/Found in the document text at /).first()).toBeVisible();
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

test("every stop Tab reaches in an answered workbench is visible and moves nothing, both ways, at 1440 and 375 px", async ({ page }) => {
  // A clipped one-pixel file input took focus with no indicator and scrolled the answer pane 434 px (UX-01, 2026-10-13).
  // Every stop is visited, round the whole cycle back to the composer, and after each one: it is at least 8 x 8 px, its
  // centre is on screen and inside every box that clips it, and no box that does not scroll for the reader has moved
  // (counter-review, 2026-10-13: a fixed forty presses, and panes compared only at the end, could miss a stop).
  await openSample(page);
  const composer = page.getByPlaceholder("Ask a question about this contract");
  await composer.fill(LIABILITY);
  await composer.press("Enter");
  await expect(page.getByText(/Found in the document text at /).first()).toBeVisible();
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: width > 400 ? 900 : 812 });
    await page.waitForTimeout(300);
    // Only boxes that do not scroll for the reader (overflow hidden or clip, either way): a scrollable list follows focus
    // by design, but a hidden-overflow box that moves cannot be moved back (the 434 px shift).
    const panes = () =>
      page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("main *, body > div *")]
          .filter((el) => {
            const style = getComputedStyle(el);
            const fixed = (overflow: string) => overflow === "hidden" || overflow === "clip";
            return (fixed(style.overflowY) && el.scrollHeight > el.clientHeight) || (fixed(style.overflowX) && el.scrollWidth > el.clientWidth);
          })
          .map((el) => `${el.scrollTop},${el.scrollLeft}`),
      );
    const measure = () =>
      page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        const r = el.getBoundingClientRect();
        const [x, y] = [r.left + r.width / 2, r.top + r.height / 2];
        let shown = x >= 0 && y >= 0 && x <= window.innerWidth && y <= window.innerHeight;
        // A fixed element (the skip link) is placed against the viewport, and no ancestor's overflow clips it.
        if (getComputedStyle(el).position !== "fixed") {
          for (let box = el.parentElement; box && shown; box = box.parentElement) {
            const style = getComputedStyle(box);
            if (style.overflowX === "visible" && style.overflowY === "visible") continue;
            const b = box.getBoundingClientRect();
            if (b.width === 0 && b.height === 0) continue; // display: contents draws no box of its own
            shown = x >= b.left && x <= b.right && y >= b.top && y <= b.bottom;
          }
        }
        return { label: el.getAttribute("aria-label") ?? el.textContent?.trim().slice(0, 30) ?? el.tagName, w: r.width, h: r.height, shown };
      });
    const before = await panes();
    expect(before.length, `at ${width}: the fixed panes are found`).toBeGreaterThan(0);
    for (const key of ["Tab", "Shift+Tab"]) {
      await composer.focus();
      let stops = 0;
      for (;;) {
        await page.keyboard.press(key);
        if (await composer.evaluate((el) => el === document.activeElement)) break;
        stops += 1;
        expect(stops, `${key} at ${width}: focus comes back to the composer`).toBeLessThan(300);
        const focused = await measure();
        if (!focused) continue; // between the last stop and the first, focus leaves the page
        expect(focused.w >= 8 && focused.h >= 8, `${key} at ${width}: ${focused.label} is ${focused.w}x${focused.h}`).toBe(true);
        // A stop may slide into view as it takes focus (the skip link's transform transition); measured at once it is still
        // off screen. It must be shown once that settles, within a second; one that never arrives still fails.
        await expect.poll(async () => (await measure())?.shown ?? true, { message: `${key} at ${width}: ${focused.label} is shown`, timeout: 1000 }).toBe(true);
        expect(await panes(), `${key} at ${width}: no hidden-overflow pane moved at ${focused.label}`).toEqual(before);
      }
      expect(stops, `${key} at ${width}: the stops of an answered workbench`).toBeGreaterThan(5);
    }
  }
});

// A file name with no break point, as document-management exports name contracts. 68 characters widened the questions
// pane past the screen at 375, 768 and 1024 px, 91 at 1280 and 1440: the pane's one implicit grid track grew to the
// header's document chip, and its hidden overflow clipped the status, the conclusion, Ctrl K and Send (stress test,
// 2026-10-30). The check is the class, not a named box that grows with its content: every element is compared with its
// nearest box that clips (overflow hidden or clip) and with the viewport, and no clipping pane is wider inside than out.
const LONG_NAMES = [
  "Master_Services_Agreement_AcmeCorp_v12_FINAL_executed_2026-10-01.txt",
  "Master_Services_Agreement_AcmeCorp_Holdings_International_v12_FINAL_executed_2026-10-01.txt",
];

/** Every visible element that reaches past the box that clips it, or past the screen; and every clipping pane wider inside. */
async function clipped(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const found: string[] = [];
    const clips = (style: CSSStyleDeclaration) => ["hidden", "clip"].includes(style.overflowX);
    const scrolls = (style: CSSStyleDeclaration) => ["auto", "scroll"].includes(style.overflowX);
    for (const el of document.querySelectorAll<HTMLElement>("body *")) {
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      // A fixed or absolute box is placed against something other than its parent (the skip link, a visually hidden label).
      if (r.width === 0 || r.height === 0 || style.visibility === "hidden" || style.position === "fixed" || style.position === "absolute") continue;
      if (clips(style) && el.scrollWidth > el.clientWidth + 1 && style.textOverflow !== "ellipsis")
        found.push(`a pane that clips is ${el.scrollWidth} px inside and ${el.clientWidth} out: ${el.className}`);
      let box = el.parentElement;
      while (box && !clips(getComputedStyle(box)) && !scrolls(getComputedStyle(box))) box = box.parentElement;
      if (box && scrolls(getComputedStyle(box))) continue; // inside a box the reader can scroll, it can be reached
      const edge = Math.min(window.innerWidth, box ? box.getBoundingClientRect().right : window.innerWidth);
      if (r.right > edge + 1) found.push(`${(el.textContent ?? "").trim().slice(0, 40)} ends at ${Math.round(r.right)}, past ${Math.round(edge)}`);
    }
    return found;
  });
}

test("a long file name with no break point keeps every row of the questions pane on screen at 375, 768 and 1280 px", async ({ page }) => {
  for (const name of LONG_NAMES) {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/");
    const text = `${name}\n\n1. Notices\n\nNotices shall be sent to the address the Customer names in writing.\n\n2. Term\n\nThis Agreement runs for one year.\n`;
    await page.locator('input[type="file"]').setInputFiles({ name, mimeType: "text/plain", buffer: Buffer.from(text) });
    await expect(page.locator("section[data-section]").first()).toBeAttached();
    for (const width of [375, 768, 1280]) {
      await page.setViewportSize({ width, height: width < 400 ? 812 : 900 });
      await page.waitForTimeout(300);
      expect(await clipped(page), `${name.length} characters at ${width} px`).toEqual([]);
      for (const label of ["Send", "Open commands"]) {
        const box = await page.getByLabel(label).boundingBox();
        expect(box !== null && box.x >= 0 && box.x + box.width <= width + 1, `${label} at ${width} px is on screen`).toBe(true);
      }
    }
  }
});
