// /break in a real browser, against the production build, on a desktop and a phone: the recorded failure reads at
// once, the investigation's controls work, the page asks the API nothing, and no WCAG A/AA violation is serious.
// One flow, two widths: it starts no run, so it costs nothing of the API's run-start budget the other flows share.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import record from "../src/components/break/break-record.json";

async function serious(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.length} node(s)`);
}

test("Break Verity tells one recorded failure, its record, the rejected fix and the rule's false alarm", async ({ page }) => {
  const errors: string[] = [];
  const api: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => message.type() === "error" && errors.push(message.text()));
  page.on("request", (request) => request.url().includes("/api/") && api.push(request.url()));
  const headline = record.headline;

  for (const viewport of [
    { width: 1280, height: 800 },
    { width: 375, height: 812 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/break");
    const exhibit = page.getByRole("figure", { name: /the question, the answer and the quote/i });
    await expect(exhibit).toContainText(headline.sessions[0].finding.conclusion);
    await expect(exhibit).toContainText("status: pass");
    await expect(exhibit).toContainText("Wrong party");
    await expect(exhibit.locator("mark").first()).toContainText("Representative notifies Buyer");
    await expect(page.getByRole("link", { name: "the filing on SEC EDGAR" })).toHaveAttribute("href", headline.source.url);

    // The investigation: the quote checked in the browser, the section opened at the quote.
    await page.getByRole("tab", { name: /What code checked/ }).click();
    await page.getByRole("button", { name: "Check it in your browser" }).click();
    await expect(page.getByText(/^Same \d+ words in the same order\./)).toBeVisible();
    await page.getByRole("tab", { name: /Retrieved/ }).click();
    const span = headline.sessions[0].finding.spans[0];
    await expect(page.getByLabel(`Section text: ${headline.sections[span.sectionId as keyof typeof headline.sections].heading}`).locator("mark")).toBeVisible();

    // Who is who in the quoted clause: the recorded definitions, beside the quote, on load.
    const key = page.getByRole("group", { name: "Who is who in this clause" });
    await expect(key).toContainText("Axogen, Inc., a Minnesota corporation");
    // The heading in quotation marks reads as the section's heading in the record, case included: innerText is the
    // text as rendered, after any CSS text-transform.
    const defining = headline.decisivePassages.find((p) => p.sectionId !== span.sectionId);
    const heading = headline.sections[defining?.sectionId as keyof typeof headline.sections].heading;
    await expect(key).toContainText(`“${heading}”`, { useInnerText: true });

    // The rejected fix, both sets side by side, and why it missed this page's headline.
    const unseen = page.getByRole("region", { name: "Unseen cases", exact: true });
    await expect(unseen).toContainText(/0\s+of 4\s+wrong-party questions caught in every session/);
    await expect(page.getByRole("region", { name: "Cases it was built on", exact: true })).toContainText(
      /4\s+of 5\s+wrong-party questions caught in every session/,
    );
    const list = page.getByRole("list", { name: /Unseen cases: each question/ });
    await list.getByRole("button", { name: new RegExp(`^${headline.id}(?![0-9])`) }).click();
    await expect(list).toContainText("acting in the quote too");

    // The counterexample: the correct answer, kept where its quote states the figure and flagged where it does not.
    const sessions = page.getByRole("group", { name: "Model session for this question" });
    await sessions.getByRole("button", { name: "Session 1" }).click();
    await expect(page.getByText("Kept: its quote states the figure")).toBeVisible();

    await expect(page.getByRole("link", { name: "Open the workbench" })).toHaveAttribute("href", "/");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    expect(await serious(page)).toEqual([]);
  }
  expect(api).toEqual([]);
  expect(errors).toEqual([]);
});
