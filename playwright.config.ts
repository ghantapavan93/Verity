// Browser flows against the real stack: the API on its own port and data directory, the production
// build of the interface on its own port, and the model's recorded answers replayed byte for byte
// (backend/app/providers/replay.py), so the same flows run in CI without a GPU.
//
//   npm run e2e                                   # replay e2e/replay.json
//   $env:E2E_PROVIDER = "record"; npm run e2e     # re-record from Ollama, then commit e2e/replay.json
//
// A recording is needed again whenever the prompt or retrieval changes: the replay provider refuses
// a request it has no answer for instead of inventing one. Traces are kept only for failures.

import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";

const API_PORT = 8001;
const WEB_PORT = 3901;
const API_URL = `http://127.0.0.1:${API_PORT}`;
const WEB_URL = `http://localhost:${WEB_PORT}`;
const provider = process.env.E2E_PROVIDER ?? "replay";

const backend = path.join(__dirname, "backend");
const venvPython = [path.join(backend, ".venv", "Scripts", "python.exe"), path.join(backend, ".venv", "bin", "python")].find((candidate) =>
  existsSync(candidate),
);
const python = venvPython ?? "python";
// The recording gets its own database so every question reaches the model instead of a reused run.
const dataDir = path.join(backend, "data", provider === "record" ? "e2e-record" : "e2e");

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: provider === "record" ? 600_000 : 90_000,
  expect: { timeout: provider === "record" ? 600_000 : 20_000 },
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: backend,
      url: `${API_URL}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        WORKBENCH_PROVIDER: provider,
        WORKBENCH_DATA_DIR: dataDir,
        WORKBENCH_CORS_ORIGINS: `${WEB_URL},http://127.0.0.1:${WEB_PORT}`,
        WORKBENCH_APP_URL: WEB_URL,
      },
    },
    {
      command: `npm run build && npm run start -- -p ${WEB_PORT}`,
      url: WEB_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: { NEXT_PUBLIC_API_URL: API_URL, NEXT_DIST_DIR: ".next-e2e" },
    },
  ],
});
