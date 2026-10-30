// No inline script runs unless the server put it on the page for this response (stress test, 2026-10-30, K64). The
// policy allowed every inline script, so one that reached the page by any other way, injected into the HTML on its way
// or written as markup with a handler, would have run. Each page now carries a script policy with a nonce of its own
// (src/proxy.ts, src/lib/csp.ts), and Next puts that nonce on its own scripts only.

import { expect, test } from "@playwright/test";

test("an inline script the server did not put on the page does not run, and the page's own scripts do", async ({ page }) => {
  const first = await page.goto("/");
  const policy = first?.headers()["content-security-policy"] ?? "";
  expect(policy).toMatch(/script-src [^;]*'nonce-[A-Za-z0-9+/=]+'/);
  expect(policy).not.toContain("unsafe-inline");
  // The page's own scripts carry the nonce and ran: the first screen is interactive.
  await expect(page.getByRole("button", { name: "try a sample agreement" })).toBeVisible();

  // Markup with a handler, as an injection would write it.
  const handled = await page.evaluate(async () => {
    const marks: number[] = [];
    (window as unknown as { __marks: number[] }).__marks = marks;
    const holder = document.createElement("div");
    holder.innerHTML = '<img src="data:," onerror="window.__marks.push(1)">';
    document.body.append(holder);
    await new Promise((resolve) => setTimeout(resolve, 300));
    return marks;
  });
  expect(handled).toEqual([]);

  // A script injected into the page's HTML on its way to the browser, with no nonce: the response's policy refuses it.
  await page.route("**/", async (route) => {
    const response = await route.fetch();
    const body = (await response.text()).replace("</body>", "<script>window.__injected = true</script></body>");
    await route.fulfill({ response, body });
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "try a sample agreement" })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __injected?: boolean }).__injected ?? false)).toBe(false);

  // Control: the nonce is new for every response.
  const again = await page.request.get("/");
  expect(again.headers()["content-security-policy"]).not.toBe(policy);
});
