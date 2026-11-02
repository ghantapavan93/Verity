import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import original from "./playwright.config";

const servers = Array.isArray(original.webServer) ? original.webServer : [original.webServer!];
// Each audit starts genuinely empty. Never reuse or delete a visitor's or owner's database.
const dataDir = mkdtempSync(path.join(tmpdir(), "verity-session-audit-"));

export default defineConfig({
  ...original,
  testMatch: /sessions\.audit\.ts/,
  timeout: 90_000,
  reporter: [["list"], ["html", { outputFolder: "playwright-report/sessions", open: "never" }]],
  projects: ["chromium", "firefox", "webkit"].map((browserName) => ({
    name: browserName,
    use: { browserName: browserName as "chromium" | "firefox" | "webkit", viewport: { width: 1440, height: 900 } },
  })),
  webServer: [
    { ...servers[0], reuseExistingServer: false, env: { ...servers[0].env, WORKBENCH_DATA_DIR: dataDir } },
    {
      ...servers[1],
      reuseExistingServer: false,
      // Webpack also supports local checkouts whose node_modules is a junction outside the checkout.
      command: "node node_modules/next/dist/bin/next build --webpack && node node_modules/next/dist/bin/next start --port 3901",
    },
  ],
});
