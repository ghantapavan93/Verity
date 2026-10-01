// Screenshots of the production build for the static proof page. Run from the contract-workbench root:
//   node proof/shots.mjs proof/img
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const out = process.argv[2];
mkdirSync(out, { recursive: true });
const base = "http://localhost:3900";
const hero = `${base}/?document=7b8ed34fd627491c&run=e5a20e2283e8416e`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 2, colorScheme: "dark" });

await page.goto(hero);
await page.getByRole("button", { name: "Inspect evidence" }).waitFor({ timeout: 20000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: path.join(out, "finding.png") });

await page.getByRole("button", { name: "View in document" }).click();
await page.waitForTimeout(1200);
await page.screenshot({ path: path.join(out, "highlight.png") });

await page.getByRole("button", { name: "Inspect evidence" }).click();
const drawer = page.locator('[aria-label="Evidence"]');
await drawer.waitFor();

await drawer.getByRole("button", { name: "Why this answer?" }).click();
const why = drawer.getByTestId("why-this-answer");
await why.waitFor();
await page.waitForTimeout(1200);
await why.getByTestId("source-match").first().scrollIntoViewIfNeeded();
// the drawer alone, tall, for the walk-down
await page.waitForTimeout(500);
await drawer.screenshot({ path: path.join(out, "why-drawer.png") });

await page.goto(`${base}/?view=runs&document=7b8ed34fd627491c&run=e5a20e2283e8416e`);
await page.waitForTimeout(4000);
await page.getByText("e5a20e2283e8416e").first().click();
await page.waitForTimeout(4000);
await page.screenshot({ path: path.join(out, "runs.png") });

await browser.close();
console.log("wrote screenshots to", out);
